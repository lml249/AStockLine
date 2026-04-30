"""中心性分析模块"""
import networkx as nx


def compute_centrality(G: nx.Graph) -> dict:
    """
    计算中心性指标（仅degree，其他指标在大图上太慢）。

    Returns:
        dict: {"degree": {code: value, ...}}
    """
    if G.number_of_nodes() == 0:
        return {"degree": {}}

    return {
        "degree": nx.degree_centrality(G),
    }


def get_top_central_nodes(centrality: dict, metric: str = "degree", top_n: int = 20) -> list:
    """获取中心性最高的前N个节点"""
    values = centrality.get(metric, {})
    sorted_nodes = sorted(values.items(), key=lambda x: x[1], reverse=True)
    return [{"code": code, "value": round(val, 6)} for code, val in sorted_nodes[:top_n]]
