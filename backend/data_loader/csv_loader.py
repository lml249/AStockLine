"""CSV数据加载器：读取A股历史日线数据"""
import pandas as pd
import numpy as np
from pathlib import Path
from backend.config.settings import DATA_DIR, MIN_TRADING_DAYS, EXCLUDE_ST, EXCLUDE_SUSPENDED


def load_single_stock(filepath: Path) -> pd.DataFrame:
    """读取单只股票的CSV文件"""
    df = pd.read_csv(
        filepath,
        parse_dates=["日期"],
        dtype={"证券代码": str},
    )
    df = df.sort_values("日期").reset_index(drop=True)
    return df


def clean_stock_data(df: pd.DataFrame) -> pd.DataFrame:
    """清洗单只股票数据：剔除停牌日、ST标记"""
    if EXCLUDE_SUSPENDED:
        df = df[df["是否停牌"] == 0.0]
    if EXCLUDE_ST:
        df = df[df["是否ST"] != True]  # noqa: E712
    # 剔除收盘价为空或为0的行
    df = df[df["收盘"].notna() & (df["收盘"] > 0)]
    return df.reset_index(drop=True)


def load_all_stocks(
    data_dir: Path = DATA_DIR,
    start_date: str = None,
    end_date: str = None,
) -> pd.DataFrame:
    """
    加载所有股票数据，返回收盘价矩阵。

    Returns:
        DataFrame，index=日期，columns=股票代码，values=收盘价
    """
    csv_files = sorted(data_dir.glob("*.csv"))
    if not csv_files:
        raise FileNotFoundError(f"在 {data_dir} 中未找到CSV文件")

    price_series = {}
    skipped = 0

    for filepath in csv_files:
        code = filepath.stem
        try:
            df = load_single_stock(filepath)
            df = clean_stock_data(df)

            if start_date:
                df = df[df["日期"] >= pd.Timestamp(start_date)]
            if end_date:
                df = df[df["日期"] <= pd.Timestamp(end_date)]

            if len(df) < MIN_TRADING_DAYS:
                skipped += 1
                continue

            series = df.set_index("日期")["收盘"]
            series.name = code
            price_series[code] = series
        except Exception as e:
            print(f"加载 {code} 失败: {e}")
            skipped += 1

    print(f"成功加载 {len(price_series)} 只股票，跳过 {skipped} 只")

    # 合并为宽表，日期对齐
    price_matrix = pd.DataFrame(price_series)
    price_matrix = price_matrix.sort_index()

    return price_matrix
