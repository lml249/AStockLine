"""收益率计算模块"""
import pandas as pd
import numpy as np


def compute_returns(price_matrix: pd.DataFrame) -> pd.DataFrame:
    """
    计算简单日收益率。

    Args:
        price_matrix: 收盘价矩阵，index=日期，columns=股票代码

    Returns:
        收益率矩阵，第一行为NaN（已被删除）
    """
    returns = price_matrix.pct_change(fill_method=None)
    returns = returns.iloc[1:]  # 删除第一行NaN
    return returns
