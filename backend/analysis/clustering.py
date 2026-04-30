"""社区发现/聚类模块"""
import networkx as nx
import community as community_louvain


def detect_communities(G: nx.Graph) -> dict:
    """
    使用Louvain算法进行社区发现。

    Args:
        G: networkx Graph 对象

    Returns:
        dict: {股票代码: 社区编号}
    """
    if G.number_of_nodes() == 0:
        return {}

    partition = community_louvain.best_partition(G, weight="weight")
    return partition


def get_community_summary(partition: dict) -> list:
    """
    汇总各社区的成员列表。

    Returns:
        list: [{"cluster_id": 0, "members": ["000001", "600036", ...], "size": 5}, ...]
    """
    clusters = {}
    for code, cluster_id in partition.items():
        clusters.setdefault(cluster_id, []).append(code)

    summary = []
    for cluster_id in sorted(clusters.keys()):
        members = sorted(clusters[cluster_id])
        summary.append({
            "cluster_id": cluster_id,
            "members": members,
            "size": len(members),
        })

    summary.sort(key=lambda x: x["size"], reverse=True)
    return summary
