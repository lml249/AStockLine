const API_BASE = `${window.location.protocol}//${window.location.hostname}:8000`;

const CLUSTER_COLORS = [
    "#e53935", "#1e88e5", "#43a047", "#fb8c00", "#8e24aa",
    "#00acc1", "#ffb300", "#6d4c41", "#546e7a", "#d81b60",
    "#3949ab", "#00897b", "#7cb342", "#f4511e", "#5e35b1",
    "#039be5", "#c0ca33", "#757575", "#e91e63", "#2196f3",
];

let chart = null;

function initChart() {
    chart = echarts.init(document.getElementById("network-chart"), "dark");
    window.addEventListener("resize", () => chart.resize());
}

async function loadNetwork() {
    const startDate = document.getElementById("startDate").value;
    const endDate = document.getElementById("endDate").value;
    const threshold = document.getElementById("threshold").value;

    const btn = document.getElementById("loadBtn");
    const loading = document.getElementById("loading");
    btn.disabled = true;
    loading.classList.add("active");

    try {
        const params = new URLSearchParams();
        params.set("threshold", threshold);
        if (startDate) params.set("start_date", startDate);
        if (endDate) params.set("end_date", endDate);

        const url = `${API_BASE}/api/network?${params}`;
        console.log("请求URL:", url);

        const res = await fetch(url);
        console.log("响应状态:", res.status);
        if (!res.ok) {
            if (res.status === 503) {
                const detail = await res.json().catch(() => null);
                throw new Error(detail?.detail || "缓存未就绪，请先运行 python -m scripts.preprocess");
            }
            throw new Error(`HTTP ${res.status}`);
        }
        const data = await res.json();

        if (data.error) {
            alert(data.error);
            return;
        }

        console.log(`节点: ${data.nodes?.length}, 边: ${data.edges?.length}`);

        currentData = data;  // 保存完整数据
        renderNetwork(data);
        updateStats(data.stats);
        updateClusterList(data.nodes);
        drawHistogram(data.edges);
    } catch (err) {
        console.error("加载错误:", err);
        alert("加载失败: " + err.message);
    } finally {
        btn.disabled = false;
        loading.classList.remove("active");
    }
}

function renderNetwork(data) {
    const clusterSet = new Set(data.nodes.map((n) => n.cluster));
    const categories = [...clusterSet].sort((a, b) => a - b).map((id) => ({
        name: `聚类 ${id}`,
    }));

    const clusterIndex = {};
    categories.forEach((c, i) => {
        clusterIndex[parseInt(c.name.replace("聚类 ", ""))] = i;
    });

    const nodes = data.nodes.map((n) => ({
        id: n.id,
        name: n.id,
        symbolSize: Math.max(4, Math.min(30, n.degree * 150)),
        category: clusterIndex[n.cluster] ?? 0,
        value: n.degree,
        cluster: n.cluster,
    }));

    const edges = data.edges.map((e) => {
        const isNegative = e.weight < 0;
        return {
            source: e.source,
            target: e.target,
            value: Math.abs(e.weight),
            lineStyle: {
                width: 1.5,
                opacity: 0.5,
                color: isNegative ? "#ef5350" : "#42a5f5",
            },
        };
    });

    const option = {
        backgroundColor: "#0a0e27",
        tooltip: {
            trigger: "item",
            formatter: (params) => {
                if (params.dataType === "node") {
                    return `<b>${params.data.id}</b><br/>聚类: ${params.data.cluster}<br/>度中心性: ${params.data.value?.toFixed(4) ?? "-"}`;
                }
                if (params.dataType === "edge") {
                    return `${params.data.source} ↔ ${params.data.target}<br/>相关系数: ${params.data.value?.toFixed(4) ?? "-"}`;
                }
                return "";
            },
        },
        legend: {
            data: categories.map((c) => c.name),
            orient: "vertical",
            left: 10,
            top: 10,
            textStyle: { color: "#aaa", fontSize: 10 },
            type: "scroll",
            pageTextStyle: { color: "#aaa" },
        },
        series: [
            {
                type: "graph",
                layout: "force",
                data: nodes,
                edges: edges,
                categories: categories,
                roam: true,
                draggable: true,
                force: {
                    repulsion: 120,
                    gravity: 0.05,
                    edgeLength: [80, 300],
                    layoutAnimation: true,
                    friction: 0.6,
                },
                emphasis: {
                    focus: "adjacency",
                    lineStyle: { width: 3, opacity: 0.8 },
                },
                label: {
                    show: false,
                },
            },
        ],
    };

    chart.setOption(option, true);

    chart.on("mouseover", { dataType: "node" }, (params) => {
        document.getElementById("floatDetailPanel").style.display = "block";
        document.getElementById("nodeDetail").innerHTML = `
            <b style="color:#4fc3f7">${params.data.id}</b><br/>
            聚类: ${params.data.cluster}<br/>
            度中心性: ${params.data.value?.toFixed(4) ?? "-"}
        `;
    });
}

function updateStats(stats) {
    document.getElementById("statNodes").textContent = stats.node_count;
    document.getElementById("statEdges").textContent = stats.edge_count;
    document.getElementById("statDensity").textContent = stats.density?.toFixed(6) ?? "-";
    document.getElementById("statClusters").textContent = stats.cluster_count ?? "-";
}

function updateClusterList(nodes) {
    const clusters = {};
    nodes.forEach((n) => {
        clusters[n.cluster] = (clusters[n.cluster] || 0) + 1;
    });

    const sorted = Object.entries(clusters).sort((a, b) => b[1] - a[1]);
    const container = document.getElementById("clusterList");
    container.innerHTML = sorted
        .map(([id, count]) => {
            const color = CLUSTER_COLORS[id % CLUSTER_COLORS.length];
            return `<div class="cluster-item">
                <span class="cluster-color" style="background:${color}"></span>
                聚类 ${id}: ${count} 只股票
            </div>`;
        })
        .join("");

    // 给聚类项绑定点击事件
    container.querySelectorAll(".cluster-item").forEach((el, idx) => {
        el.addEventListener("click", () => {
            const clusterId = parseInt(sorted[idx][0]);
            showCluster(clusterId);
        });
    });
}

// 阈值滑块实时显示
document.getElementById("threshold").addEventListener("input", (e) => {
    document.getElementById("thresholdValue").textContent = e.target.value;
});

// 保存当前完整数据用于搜索/筛选
let currentData = null;

// 搜索定位股票
function searchStock() {
    const code = document.getElementById("searchCode").value.trim();
    if (!code || !chart) return;

    // ECharts 力导图中高亮节点
    chart.dispatchAction({
        type: "highlight",
        seriesIndex: 0,
        name: code,
    });

    // 显示详情
    if (currentData) {
        const node = currentData.nodes.find((n) => n.id === code);
        if (node) {
            const neighbors = currentData.edges
                .filter((e) => e.source === code || e.target === code)
                .map((e) => (e.source === code ? e.target : e.source));
            document.getElementById("nodeDetail").innerHTML = `
                <b style="color:#4fc3f7">${code}</b><br/>
                聚类: ${node.cluster}<br/>
                度中心性: ${node.degree?.toFixed(4) ?? "-"}<br/>
                关联股票(${neighbors.length}): ${neighbors.join(", ") || "无"}
            `;
        } else {
            document.getElementById("nodeDetail").innerHTML = `
                <span style="color:#ef5350">未找到 ${code}</span>
            `;
        }
    }
}

// 显示自我网络（只显示目标股票及其直接关联的股票和边）
function showEgoNetwork() {
    const code = document.getElementById("searchCode").value.trim();
    if (!code || !currentData) return;

    const relatedEdges = currentData.edges.filter(
        (e) => e.source === code || e.target === code
    );

    if (relatedEdges.length === 0) {
        alert(`股票 ${code} 在当前阈值下没有关联股票`);
        return;
    }

    const neighborCodes = new Set();
    neighborCodes.add(code);
    relatedEdges.forEach((e) => {
        neighborCodes.add(e.source);
        neighborCodes.add(e.target);
    });

    const filteredData = {
        nodes: currentData.nodes.filter((n) => neighborCodes.has(n.id)),
        edges: relatedEdges,
        stats: {
            node_count: neighborCodes.size,
            edge_count: relatedEdges.length,
            density: 0,
            cluster_count: new Set(
                currentData.nodes
                    .filter((n) => neighborCodes.has(n.id))
                    .map((n) => n.cluster)
            ).size,
        },
    };

    renderNetwork(filteredData);
    updateStats(filteredData.stats);
    updateClusterList(filteredData.nodes);
}

// 显示指定聚类的股票和边
function showCluster(clusterId) {
    if (!currentData) return;

    const clusterNodes = new Set(
        currentData.nodes.filter((n) => n.cluster === clusterId).map((n) => n.id)
    );

    if (clusterNodes.size === 0) return;

    const filteredEdges = currentData.edges.filter(
        (e) => clusterNodes.has(e.source) && clusterNodes.has(e.target)
    );

    const filteredData = {
        nodes: currentData.nodes.filter((n) => clusterNodes.has(n.id)),
        edges: filteredEdges,
        stats: {
            node_count: clusterNodes.size,
            edge_count: filteredEdges.length,
            density: 0,
            cluster_count: 1,
        },
    };

    renderNetwork(filteredData);
    updateStats(filteredData.stats);

    // 显示聚类成员列表（浮动面板）
    const members = currentData.nodes
        .filter((n) => n.cluster === clusterId)
        .sort((a, b) => b.degree - a.degree);

    const container = document.getElementById("clusterMembers");
    const panel = document.getElementById("floatClusterPanel");
    document.getElementById("clusterDetailTitle").textContent = `聚类 ${clusterId} (${members.length}只)`;
    panel.style.display = "block";
    container.innerHTML = members
        .map((m) => {
            return `<div class="cluster-item" 
                oncontextmenu="memberContextMenu(event, '${m.id}')"
                onclick="memberClick('${m.id}')">
                ${m.id} <span style="color:#4fc3f7; font-size:10px; float:right;">度:${m.degree.toFixed(4)}</span>
            </div>`;
        })
        .join("");
}

// 聚类成员点击 → 定位
function memberClick(code) {
    document.getElementById("searchCode").value = code;
    searchStock();
}

// 聚类成员右键 → 使用和节点一样的右键菜单
function memberContextMenu(event, code) {
    event.preventDefault();
    ctxTargetCode = code;
    const menu = document.getElementById("contextMenu");
    menu.style.display = "block";
    menu.style.left = event.clientX + "px";
    menu.style.top = event.clientY + "px";
}

// 重置为完整网络
function resetView() {
    if (currentData) {
        renderNetwork(currentData);
        updateStats(currentData.stats);
        updateClusterList(currentData.nodes);
    }
    document.getElementById("searchCode").value = "";
    document.getElementById("clusterMembers").innerHTML = "";
}

// 切换隐藏/显示孤立节点
function toggleIsolated() {
    if (!currentData) return;
    const hide = document.getElementById("hideIsolated").checked;

    if (hide) {
        // 找出有连接的节点
        const connectedNodes = new Set();
        currentData.edges.forEach((e) => {
            connectedNodes.add(e.source);
            connectedNodes.add(e.target);
        });

        const filteredData = {
            nodes: currentData.nodes.filter((n) => connectedNodes.has(n.id)),
            edges: currentData.edges,
            stats: {
                node_count: connectedNodes.size,
                edge_count: currentData.edges.length,
                density: currentData.stats.density,
                cluster_count: new Set(
                    currentData.nodes
                        .filter((n) => connectedNodes.has(n.id))
                        .map((n) => n.cluster)
                ).size,
            },
        };

        renderNetwork(filteredData);
        updateStats(filteredData.stats);
        updateClusterList(filteredData.nodes);
    } else {
        renderNetwork(currentData);
        updateStats(currentData.stats);
        updateClusterList(currentData.nodes);
    }
}

// 初始化
initChart();

// === 右键菜单 ===
let ctxTargetCode = null;

document.addEventListener("click", () => {
    document.getElementById("contextMenu").style.display = "none";
});

function setupContextMenu() {
    const chartDom = document.getElementById("network-chart");
    chartDom.addEventListener("contextmenu", (e) => e.preventDefault());

    chart.on("contextmenu", { dataType: "node" }, (params) => {
        params.event.event.preventDefault();
        ctxTargetCode = params.data.id;
        const menu = document.getElementById("contextMenu");
        menu.style.display = "block";
        menu.style.left = params.event.event.clientX + "px";
        menu.style.top = params.event.event.clientY + "px";
    });
}

function ctxShowEgo() {
    if (!ctxTargetCode) return;
    document.getElementById("searchCode").value = ctxTargetCode;
    showEgoNetwork();
    document.getElementById("contextMenu").style.display = "none";
}

function ctxCopyCode() {
    if (!ctxTargetCode) return;
    navigator.clipboard.writeText(ctxTargetCode);
    document.getElementById("contextMenu").style.display = "none";
}

function ctxShowDetail() {
    if (!ctxTargetCode || !currentData) return;
    const node = currentData.nodes.find((n) => n.id === ctxTargetCode);
    const neighbors = currentData.edges
        .filter((e) => e.source === ctxTargetCode || e.target === ctxTargetCode)
        .map((e) => {
            const other = e.source === ctxTargetCode ? e.target : e.source;
            return `${other}(${e.weight.toFixed(3)})`;
        });
    document.getElementById("nodeDetail").innerHTML = `
        <b style="color:#4fc3f7">${ctxTargetCode}</b><br/>
        聚类: ${node?.cluster ?? "-"}<br/>
        度中心性: ${node?.degree?.toFixed(4) ?? "-"}<br/>
        关联股票(${neighbors.length}):<br/>
        <span style="font-size:11px">${neighbors.join(", ") || "无"}</span>
    `;
    document.getElementById("contextMenu").style.display = "none";
}

// === 迷你统计面板（相关系数分布直方图）===
function drawHistogram(edges) {
    const panel = document.getElementById("miniStats");
    if (!edges || edges.length === 0) {
        panel.style.display = "none";
        return;
    }
    panel.style.display = "block";

    const canvas = document.getElementById("histCanvas");
    const ctx = canvas.getContext("2d");
    const w = canvas.width;
    const h = canvas.height;
    ctx.clearRect(0, 0, w, h);

    // 构建直方图数据（按边权重分布）
    const bins = 10;
    const counts = new Array(bins).fill(0);
    const weights = edges.map((e) => e.weight);
    const minW = Math.min(...weights);
    const maxW = Math.max(...weights);
    const range = maxW - minW || 1;

    weights.forEach((v) => {
        let idx = Math.floor(((v - minW) / range) * bins);
        if (idx >= bins) idx = bins - 1;
        counts[idx]++;
    });

    const maxCount = Math.max(...counts);
    const barW = w / bins - 2;

    counts.forEach((c, i) => {
        const barH = maxCount > 0 ? (c / maxCount) * (h - 15) : 0;
        const x = i * (w / bins) + 1;
        const y = h - 15 - barH;
        ctx.fillStyle = "#1e88e5";
        ctx.fillRect(x, y, barW, barH);
    });

    // 绘制轴标签（每个bin都标注）
    ctx.fillStyle = "#90a4ae";
    ctx.font = "9px sans-serif";
    for (let i = 0; i <= bins; i++) {
        const val = minW + (range / bins) * i;
        const x = i * (w / bins);
        ctx.fillText(val.toFixed(2), x, h - 2);
    }

    // 统计信息
    const avg = weights.reduce((a, b) => a + b, 0) / weights.length;
    document.getElementById("histInfo").textContent =
        `边数: ${weights.length} | 平均: ${avg.toFixed(3)} | 范围: [${minW.toFixed(3)}, ${maxW.toFixed(3)}]`;
}

setupContextMenu();
