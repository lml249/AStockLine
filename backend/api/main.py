"""FastAPI 服务入口 —— 预计算缓存 + 实时计算混合模式"""
from __future__ import annotations

import json
import logging
import pickle
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd

from backend.config.settings import CACHE_DIR, DATA_SOURCE
from backend.compute.returns import compute_returns
from backend.compute.correlation import compute_correlation_matrix
from backend.compute.network_builder import build_network, get_network_stats
from backend.analysis.clustering import detect_communities
from backend.analysis.centrality import compute_centrality

logger = logging.getLogger(__name__)

# 内存缓存
_cache = {}


def _load_cache_meta() -> dict | None:
    """加载缓存元数据"""
    path = CACHE_DIR / "cache_meta.json"
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _validate_cache_meta():
    """校验缓存元数据与当前配置是否一致。

    Returns:
        (is_valid, error_message) 元组
    """
    meta = _load_cache_meta()
    if meta is None:
        return False, (
            "缓存元数据 cache_meta.json 不存在。"
            "请运行 python -m scripts.preprocess 生成缓存。"
        )
    cached_source = meta.get("data_source", "unknown")
    if cached_source != DATA_SOURCE:
        return False, (
            f"缓存来源不匹配：缓存由 '{cached_source}' 生成，"
            f"但当前配置为 '{DATA_SOURCE}'。"
            f"请重新运行 python -m scripts.preprocess。"
        )
    # 进一步校验数据源参数是否一致
    if DATA_SOURCE == "clickhouse":
        from backend.config.settings import (
            CLICKHOUSE_HOST, CLICKHOUSE_DATABASE, CLICKHOUSE_TABLE,
        )
        mismatches = []
        if meta.get("clickhouse_host") and meta["clickhouse_host"] != CLICKHOUSE_HOST:
            mismatches.append(f"host: {meta['clickhouse_host']} → {CLICKHOUSE_HOST}")
        if meta.get("clickhouse_database") and meta["clickhouse_database"] != CLICKHOUSE_DATABASE:
            mismatches.append(f"database: {meta['clickhouse_database']} → {CLICKHOUSE_DATABASE}")
        if meta.get("clickhouse_table") and meta["clickhouse_table"] != CLICKHOUSE_TABLE:
            mismatches.append(f"table: {meta['clickhouse_table']} → {CLICKHOUSE_TABLE}")
        if mismatches:
            return False, (
                f"ClickHouse 配置已变更（{', '.join(mismatches)}），"
                f"请重新运行 python -m scripts.preprocess。"
            )
    elif DATA_SOURCE == "csv":
        from backend.config.settings import DATA_DIR
        if meta.get("csv_data_dir") and meta["csv_data_dir"] != str(DATA_DIR):
            return False, (
                f"CSV 数据目录已变更：缓存使用 '{meta['csv_data_dir']}'，"
                f"当前配置为 '{DATA_DIR}'。"
                f"请重新运行 python -m scripts.preprocess。"
            )
    return True, None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时校验缓存"""
    is_valid, error = _validate_cache_meta()
    if not is_valid:
        logger.warning(f"[AStockLine] 缓存校验失败: {error}")
    yield


app = FastAPI(title="AStockLine API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)



def _ensure_cache_valid():
    """校验缓存有效性，无效时抛出 HTTPException"""
    is_valid, error = _validate_cache_meta()
    if not is_valid:
        raise HTTPException(status_code=503, detail=error)


def _load_returns() -> pd.DataFrame:
    """加载预计算的收益率矩阵"""
    if "returns" not in _cache:
        _ensure_cache_valid()
        path = CACHE_DIR / "returns.pkl"
        if not path.exists():
            raise HTTPException(
                status_code=503,
                detail="请先运行 python -m scripts.preprocess",
            )
        with open(path, "rb") as f:
            _cache["returns"] = pickle.load(f)
    return _cache["returns"]


def _load_corr() -> pd.DataFrame:
    """加载预计算的全量相关性矩阵"""
    if "corr" not in _cache:
        _ensure_cache_valid()
        path = CACHE_DIR / "corr_matrix.pkl"
        if not path.exists():
            raise HTTPException(
                status_code=503,
                detail="请先运行 python -m scripts.preprocess",
            )
        with open(path, "rb") as f:
            _cache["corr"] = pickle.load(f)
    return _cache["corr"]



def _build_network_response(corr, threshold):
    """从相关性矩阵构建网络响应JSON"""
    G = build_network(corr, threshold=threshold)
    partition = detect_communities(G)
    centrality = compute_centrality(G)
    stats = get_network_stats(G)

    degree_vals = centrality.get("degree", {})
    nodes = [
        {"id": node, "cluster": partition.get(node, -1), "degree": round(degree_vals.get(node, 0), 6)}
        for node in G.nodes()
    ]
    edges = [
        {"source": u, "target": v, "weight": round(data.get("weight", 0), 4)}
        for u, v, data in G.edges(data=True)
    ]
    stats["cluster_count"] = len(set(partition.values())) if partition else 0

    return {"nodes": nodes, "edges": edges, "stats": stats}


@app.get("/api/network")
def get_network(
    threshold: float = Query(0.7, ge=0.0, le=1.0, description="相关性阈值"),
    start_date: str = Query(None, description="开始日期"),
    end_date: str = Query(None, description="结束日期"),
):
    """获取网络数据：无日期参数时用预计算缓存，有日期参数时实时计算"""
    _ensure_cache_valid()
    if start_date or end_date:
        # 实时计算模式：从收益率矩阵切片
        returns = _load_returns()
        if start_date:
            returns = returns[returns.index >= pd.Timestamp(start_date)]
        if end_date:
            returns = returns[returns.index <= pd.Timestamp(end_date)]

        cache_key = f"corr_{start_date}_{end_date}"
        if cache_key in _cache:
            corr = _cache[cache_key]
        else:
            corr = compute_correlation_matrix(returns)
            _cache[cache_key] = corr

        return _build_network_response(corr, threshold)
    else:
        # 尝试读预计算缓存
        available = [50, 60, 70, 80, 90]
        t_int = int(threshold * 100)
        closest = min(available, key=lambda x: abs(x - t_int))
        cache_path = CACHE_DIR / f"network_t{closest}.json"

        if cache_path.exists():
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        else:
            # 没有预计算缓存，实时计算
            corr = _load_corr()
            return _build_network_response(corr, threshold)


@app.get("/api/dynamics")
def get_dynamics():
    """获取网络动态演化数据"""
    path = CACHE_DIR / "dynamics.json"
    if not path.exists():
        return {"error": "动态演化数据未计算，请在预处理脚本中启用步骤5"}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/api/date-range")
def get_date_range():
    """获取数据的日期范围"""
    returns = _load_returns()
    return {
        "start": str(returns.index.min().date()),
        "end": str(returns.index.max().date()),
        "trading_days": len(returns),
    }
