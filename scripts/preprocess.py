"""预处理脚本：加载数据、计算相关性、构建网络，结果保存为JSON供前端直接使用"""
import sys
import json
import pickle
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.config.settings import (
    CACHE_DIR,
    CLICKHOUSE_DATABASE,
    CLICKHOUSE_HOST,
    CLICKHOUSE_TABLE,
    CORRELATION_THRESHOLD,
    DATA_SOURCE,
    ROLLING_STEP_SIZE,
    ROLLING_WINDOW_SIZE,
)
from backend.data_loader.clickhouse_loader import load_all_stocks
from backend.compute.returns import compute_returns
from backend.compute.correlation import compute_correlation_matrix, compute_rolling_correlations
from backend.compute.network_builder import build_network, get_network_stats
from backend.analysis.clustering import detect_communities
from backend.analysis.centrality import compute_centrality


def build_network_json(corr, threshold):
    """构建网络并返回可序列化的dict"""
    G = build_network(corr, threshold=threshold)
    partition = detect_communities(G)
    centrality = compute_centrality(G)
    stats = get_network_stats(G)

    degree_vals = centrality.get("degree", {})
    nodes = []
    for node in G.nodes():
        nodes.append({
            "id": node,
            "cluster": partition.get(node, -1),
            "degree": round(degree_vals.get(node, 0), 6),
        })

    edges = []
    for u, v, data in G.edges(data=True):
        edges.append({
            "source": u,
            "target": v,
            "weight": round(data.get("weight", 0), 4),
        })

    stats["cluster_count"] = len(set(partition.values())) if partition else 0
    return {"nodes": nodes, "edges": edges, "stats": stats}


def main():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # 删除旧的缓存元数据，防止预处理中途失败时残留旧 meta 误导 API
    old_meta = CACHE_DIR / "cache_meta.json"
    if old_meta.exists():
        old_meta.unlink()

    print("=" * 60)
    print("AStockLine 数据预处理")
    print(f"数据源: {DATA_SOURCE}")
    print("=" * 60)

    # 1. 加载数据
    print("\n[1/5] 加载股票数据...")
    price_matrix = load_all_stocks()
    print(f"  收盘价矩阵: {price_matrix.shape[0]} 个交易日 × {price_matrix.shape[1]} 只股票")

    # 2. 计算收益率
    print("\n[2/5] 计算日收益率...")
    returns = compute_returns(price_matrix)
    print(f"  收益率矩阵: {returns.shape}")

    # 3. 计算全量相关性矩阵
    print("\n[3/5] 计算全量相关性矩阵...")
    corr = compute_correlation_matrix(returns)
    print(f"  相关性矩阵: {corr.shape}")

    # 保存相关性矩阵和收益率（pickle）
    with open(CACHE_DIR / "corr_matrix.pkl", "wb") as f:
        pickle.dump(corr, f)
    with open(CACHE_DIR / "returns.pkl", "wb") as f:
        pickle.dump(returns, f)
    print("  已保存 corr_matrix.pkl, returns.pkl")

    # 4. 构建不同阈值的网络JSON
    print("\n[4/5] 构建网络JSON（多阈值）...")
    thresholds = [0.5, 0.6, 0.7, 0.8, 0.9]
    for idx, t in enumerate(thresholds):
        print(f"  [{idx+1}/{len(thresholds)}] 阈值={t}...", end=" ", flush=True)
        result = build_network_json(corr, threshold=t)
        out_path = CACHE_DIR / f"network_t{int(t*100)}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False)
        print(f"{result['stats']['node_count']}节点, {result['stats']['edge_count']}边 → {out_path.name}")

    # 5. 计算滚动窗口动态演化（可选，耗时较长）
    # 取消注释以下代码块来启用
    # print(f"\n[5/5] 计算滚动窗口动态演化 (窗口={ROLLING_WINDOW_SIZE}, 步长={ROLLING_STEP_SIZE})...")
    # snapshots = compute_rolling_correlations(
    #     returns, window=ROLLING_WINDOW_SIZE, step=ROLLING_STEP_SIZE
    # )
    # dynamics = []
    # for i, (start_date, end_date, snap_corr) in enumerate(snapshots):
    #     G = build_network(snap_corr, threshold=CORRELATION_THRESHOLD)
    #     stats = get_network_stats(G)
    #     partition = detect_communities(G)
    #     cluster_count = len(set(partition.values())) if partition else 0
    #     dynamics.append({
    #         "start_date": start_date,
    #         "end_date": end_date,
    #         "density": round(stats["density"], 6),
    #         "node_count": stats["node_count"],
    #         "edge_count": stats["edge_count"],
    #         "cluster_count": cluster_count,
    #     })
    #     if (i + 1) % 20 == 0:
    #         print(f"  已处理 {i+1}/{len(snapshots)} 个窗口")
    # with open(CACHE_DIR / "dynamics.json", "w", encoding="utf-8") as f:
    #     json.dump({"snapshots": dynamics}, f, ensure_ascii=False)
    # print(f"  共 {len(dynamics)} 个时间快照 → dynamics.json")
    print("\n[5/5] 滚动窗口动态演化（已跳过，前端暂未使用）")

    # 写入缓存元数据
    cache_meta = {
        "data_source": "clickhouse",
        "date_start": str(price_matrix.index.min().date()),
        "date_end": str(price_matrix.index.max().date()),
        "stock_count": price_matrix.shape[1],
        "trading_days": price_matrix.shape[0],
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "clickhouse_host": CLICKHOUSE_HOST,
        "clickhouse_database": CLICKHOUSE_DATABASE,
        "clickhouse_table": CLICKHOUSE_TABLE,
    }

    with open(CACHE_DIR / "cache_meta.json", "w", encoding="utf-8") as f:
        json.dump(cache_meta, f, ensure_ascii=False, indent=2)
    print("\n  已保存 cache_meta.json")

    print("\n" + "=" * 60)
    print("预处理完成！缓存文件：")
    for p in sorted(CACHE_DIR.glob("*")):
        if p.name != ".gitkeep":
            size_mb = p.stat().st_size / 1024 / 1024
            print(f"  {p.name} ({size_mb:.1f} MB)")
    print("=" * 60)


if __name__ == "__main__":
    main()
