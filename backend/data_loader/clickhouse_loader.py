"""ClickHouse 数据加载器：从 ClickHouse 读取 A 股历史日线数据"""
from __future__ import annotations

import re
import pandas as pd
from backend.config.settings import (
    CLICKHOUSE_HOST,
    CLICKHOUSE_PORT,
    CLICKHOUSE_DATABASE,
    CLICKHOUSE_USER,
    CLICKHOUSE_PASSWORD,
    CLICKHOUSE_TABLE,
    MIN_TRADING_DAYS,
)


def _validate_table_name(table: str) -> str:
    """校验表名为安全标识符，防止 SQL 注入。

    允许格式: 字母/数字/下划线，或 database.table 形式。
    """
    pattern = r"^[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)?$"
    if not re.match(pattern, table):
        raise ValueError(f"不安全的表名: {table!r}")
    return table


def _normalize_trade_date(value: str | None) -> str | None:
    """将 YYYY-MM-DD 格式日期转换为 ClickHouse 中的 YYYYMMDD 格式。"""
    if not value:
        return None
    return pd.Timestamp(value).strftime("%Y%m%d")


def _get_client():
    """创建 ClickHouse HTTP 连接客户端。"""
    if not CLICKHOUSE_HOST:
        raise ValueError(
            "ClickHouse 模式需要设置 CLICKHOUSE_HOST 环境变量。"
            "请在 .env 或环境中配置 CLICKHOUSE_HOST=<your-server-ip>"
        )
    import clickhouse_connect

    return clickhouse_connect.get_client(
        host=CLICKHOUSE_HOST,
        port=CLICKHOUSE_PORT,
        database=CLICKHOUSE_DATABASE,
        username=CLICKHOUSE_USER,
        password=CLICKHOUSE_PASSWORD,
    )


def load_all_stocks(
    start_date: str = None,
    end_date: str = None,
) -> pd.DataFrame:
    """
    从 ClickHouse 加载股票收盘价矩阵。

    Args:
        start_date: 开始日期，格式 YYYY-MM-DD（可选）
        end_date:   结束日期，格式 YYYY-MM-DD（可选）

    Returns:
        DataFrame，index=DatetimeIndex，columns=股票代码，values=收盘价
    """
    safe_table = _validate_table_name(CLICKHOUSE_TABLE)

    # 构建 WHERE 子句
    conditions = [
        "close > 0",
        "turnover_rate > 0",  # 近似过滤停牌日
    ]
    params = {}

    ch_start = _normalize_trade_date(start_date)
    ch_end = _normalize_trade_date(end_date)

    if ch_start:
        conditions.append("trade_date >= {start_date:String}")
        params["start_date"] = ch_start
    if ch_end:
        conditions.append("trade_date <= {end_date:String}")
        params["end_date"] = ch_end

    where_clause = " AND ".join(conditions)

    query = f"""
        SELECT
            trade_date,
            ts_code,
            close
        FROM {safe_table} FINAL
        WHERE {where_clause}
        ORDER BY trade_date, ts_code
    """

    print(f"  ClickHouse 查询: {CLICKHOUSE_HOST}:{CLICKHOUSE_PORT}/{CLICKHOUSE_DATABASE}.{safe_table}")
    if ch_start or ch_end:
        print(f"  日期范围: {ch_start or '(无限制)'} ~ {ch_end or '(无限制)'}")

    client = _get_client()
    try:
        result = client.query(query, parameters=params)

        # 转换为 DataFrame
        df = pd.DataFrame(result.result_rows, columns=["trade_date", "ts_code", "close"])
        print(f"  查询返回 {len(df)} 条记录")
    finally:
        client.close()

    if df.empty:
        raise ValueError("ClickHouse 查询未返回任何数据，请检查日期范围和表内容")

    # 转换日期格式
    df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d")

    # 使用 pivot_table + aggfunc="last" 处理 ReplacingMergeTree 可能的未合并重复行
    price_matrix = df.pivot_table(
        index="trade_date",
        columns="ts_code",
        values="close",
        aggfunc="last",
    )
    price_matrix = price_matrix.sort_index()

    # 按最少交易日数过滤股票列
    min_required_days = min(MIN_TRADING_DAYS, len(price_matrix.index))
    before_filter = price_matrix.shape[1]
    price_matrix = price_matrix.dropna(axis=1, thresh=min_required_days)
    after_filter = price_matrix.shape[1]

    print(f"  收盘价矩阵: {price_matrix.shape[0]} 个交易日 × {after_filter} 只股票"
          f"（过滤掉 {before_filter - after_filter} 只交易日不足的股票）")

    return price_matrix
