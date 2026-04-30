"""网络动态演化分析模块"""
import networkx as nx
import pandas as pd
from typing import List, Tuple
from backend.compute.correlation import compute_rolling_correlations
from backend.compute.network_builder import build_network, get_network_stats
from backend.analysis.clustering import detect_communities


def compute_dynamics(
    returns: pd.DataFrame,
    window: int = 120,
    step: int = 20,
    threshold: float = 0.7,
    min_periods: int = 60,
) -> list:
    """
    计算网络动态演化序列。

    Returns:
        列表，每个元素为一个时间快照的统计信息和网络数据
    """
    snapshots = compute_rolling_correlations(
        returns, window=window, step=step, min_periods=min_periods
    )

    dynamics = []
    for start_date, end_date, corr in snapshots:
        G = build_network(corr, threshold=threshold)
        stats = get_network_stats(G)
        partition = detect_communities(G)

        cluster_count = len(set(partition.values())) if partition else 0

        dynamics.append({
            "start_date": start_date,
            "end_date": end_date,
            "density": stats["density"],
            "node_count": stats["node_count"],
            "edge_count": stats["edge_count"],
            "cluster_count": cluster_count,
            "connected_components": stats["connected_components"],
        })

    return dynamics
