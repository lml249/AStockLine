"""图网络构建模块"""
import pandas as pd
import numpy as np
import networkx as nx


def build_network(
    corr_matrix: pd.DataFrame,
    threshold: float = 0.7,
) -> nx.Graph:
    """
    根据相关性矩阵构建图网络（numpy向量化版本）。

    Args:
        corr_matrix: N×N 相关性矩阵
        threshold: 相关性阈值，|ρ| >= threshold 时建立边

    Returns:
        networkx Graph 对象
    """
    G = nx.Graph()
    codes = corr_matrix.columns.tolist()
    G.add_nodes_from(codes)

    corr_values = corr_matrix.values
    n = len(codes)

    # 用numpy向量化获取上三角中满足阈值条件的索引
    # 构建上三角掩码（排除对角线）
    mask = np.triu(np.ones((n, n), dtype=bool), k=1)
    # 排除NaN
    valid = ~np.isnan(corr_values)
    # 满足阈值条件
    above_threshold = np.abs(corr_values) >= threshold
    # 综合条件
    edges_mask = mask & valid & above_threshold

    # 获取所有满足条件的(i, j)索引
    rows, cols = np.where(edges_mask)

    # 批量添加边
    edge_list = []
    for idx in range(len(rows)):
        i, j = rows[idx], cols[idx]
        val = corr_values[i, j]
        edge_list.append((codes[i], codes[j], {"weight": float(val), "abs_weight": float(abs(val))}))

    G.add_edges_from(edge_list)

    return G


def get_network_stats(G: nx.Graph) -> dict:
    """获取网络统计指标"""
    return {
        "node_count": G.number_of_nodes(),
        "edge_count": G.number_of_edges(),
        "density": nx.density(G),
        "connected_components": nx.number_connected_components(G),
    }
