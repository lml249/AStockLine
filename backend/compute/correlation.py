"""相关性矩阵计算模块"""
import pandas as pd
import numpy as np
from typing import List, Tuple


def compute_correlation_matrix(
    returns: pd.DataFrame,
    min_periods: int = 60,
) -> pd.DataFrame:
    """
    计算全配对皮尔逊相关系数矩阵。

    Args:
        returns: 收益率矩阵，index=日期，columns=股票代码
        min_periods: 最少重叠交易日数，低于此值的配对结果为NaN

    Returns:
        N×N 相关性矩阵
    """
    corr = returns.corr(min_periods=min_periods)
    return corr


def compute_rolling_correlations(
    returns: pd.DataFrame,
    window: int = 120,
    step: int = 20,
    min_periods: int = 60,
) -> List[Tuple[str, str, pd.DataFrame]]:
    """
    滚动窗口计算相关性矩阵序列。

    Args:
        returns: 收益率矩阵
        window: 窗口大小（交易日）
        step: 滑动步长（交易日）
        min_periods: 最少重叠期数

    Returns:
        列表，每个元素为 (start_date, end_date, corr_matrix)
    """
    dates = returns.index
    total = len(dates)
    snapshots = []

    for start_idx in range(0, total - window + 1, step):
        end_idx = start_idx + window
        window_returns = returns.iloc[start_idx:end_idx]

        start_date = str(dates[start_idx].date())
        end_date = str(dates[end_idx - 1].date())

        corr = window_returns.corr(min_periods=min_periods)
        snapshots.append((start_date, end_date, corr))

    return snapshots
