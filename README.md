# AStockLine

A股股票价格走势关系网络分析工具。

基于有效市场假说（EMH），通过计算A股股票之间历史价格日收益率的皮尔逊相关系数，构建交互式关系网络图，发现市场中隐藏的结构性关联。

## 功能特性

- **相关性网络构建**：基于4899只A股的历史日级别后复权价格数据，计算两两之间的皮尔逊相关系数
- **Louvain社区检测**：自动识别高度相关的股票聚类群组
- **度中心性分析**：识别网络中连接最广泛的核心股票
- **自定义日期范围**：支持选择任意时间段进行分析（实时计算）
- **阈值调节**：滑块调整相关系数阈值（0.5~0.9），预计算缓存快速切换
- **交互式可视化**：
  - ECharts力导向图，正相关（蓝）/负相关（红）边着色
  - 股票搜索定位
  - 聚类列表点击过滤
  - 右键菜单（查看关联网络/复制代码/查看详情）
  - 浮动面板显示聚类成员和节点详情
  - 隐藏孤立节点
  - 相关系数分布直方图

## 技术架构

```
backend/
├── config/settings.py                  # 全局配置（数据源选择 + ClickHouse 连接）
├── data_loader/
│   ├── csv_loader.py                   # CSV 数据加载与清洗
│   └── clickhouse_loader.py            # ClickHouse 数据加载
├── compute/
│   ├── returns.py                      # 日收益率计算
│   ├── correlation.py                  # 皮尔逊相关矩阵
│   └── network_builder.py              # 网络构建（numpy向量化优化）
├── analysis/
│   ├── clustering.py                   # Louvain社区检测
│   ├── centrality.py                   # 度中心性
│   └── dynamics.py                     # 滚动窗口动态分析（预留）
├── api/main.py                         # FastAPI服务（混合缓存+实时模式 + 缓存校验）
scripts/preprocess.py                   # 预处理脚本（自动选择数据源 + 写入缓存元数据）
.env.example                            # 环境变量模板

frontend/
├── index.html                          # 主页面（深色主题）
└── src/main.js                         # 前端逻辑（ECharts可视化）
```

## 快速开始

### 1. 环境准备

```bash
# 安装Python依赖
cd backend
pip install -r requirements.txt
```

### 2. 配置数据源

项目支持两种数据源模式：**CSV**（默认）和 **ClickHouse**。

#### 模式 A：CSV（默认）

将CSV数据放入 `data/` 目录（或通过 `ASTOCK_DATA_DIR` 环境变量指定路径）：

```bash
export ASTOCK_DATA_SOURCE=csv
export ASTOCK_DATA_DIR=/path/to/csv/data
```

#### 模式 B：ClickHouse

配置 ClickHouse 连接环境变量：

```bash
export ASTOCK_DATA_SOURCE=clickhouse
export CLICKHOUSE_HOST=<your-server-ip>
export CLICKHOUSE_PORT=8123
export CLICKHOUSE_DATABASE=default
export CLICKHOUSE_USER=default
export CLICKHOUSE_PASSWORD=
export CLICKHOUSE_TABLE=tushare_daily_basic
```

也可将上述配置写入项目根目录的 `.env` 文件，参考 `.env.example`。

### 3. 数据预处理

```bash
python3 -m scripts.preprocess
```

预处理输出：
- `cache/returns.pkl` - 收益率矩阵
- `cache/corr_matrix.pkl` - 完整相关矩阵
- `cache/network_t50.json` ~ `network_t90.json` - 不同阈值的预计算网络
- `cache/cache_meta.json` - 缓存元数据（数据源、日期范围等）

> **注意**：切换数据源后必须重新运行预处理。API 启动时会校验 `cache_meta.json`，如果当前数据源与缓存来源不一致会报错。

### 4. 启动服务

```bash
# 终端1：启动后端API（端口8000，从项目根目录运行，允许局域网访问）
uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8000

# 终端2：启动前端（端口5173，允许局域网访问）
cd frontend
python3 -m http.server 5173 --bind 0.0.0.0
```

浏览器访问 `http://localhost:5173` 或 `http://<本机局域网IP>:5173`

> **注意**：API 日期筛选基于预计算缓存的切片，不会每次请求实时查询数据库。若需覆盖新日期范围，请重新运行预处理。

## 数据准备

本项目**不包含股票数据**，你需要自行准备数据。支持 CSV 文件或 ClickHouse 数据库两种数据源。

### CSV 模式

默认读取项目根目录下的 `data/` 文件夹，也可通过环境变量自定义：

```bash
# Linux/macOS
export ASTOCK_DATA_DIR=/path/to/your/csv/data

# Windows PowerShell
$env:ASTOCK_DATA_DIR = "D:\your\csv\data"
```

#### CSV格式要求

每只股票一个CSV文件，文件名任意。每个CSV必须包含以下列：

| 列名 | 说明 | 示例 |
|------|------|------|
| 证券代码 | 股票代码 | 000001.SZ |
| 日期 | 交易日期 | 2024-01-02 |
| 收盘 | 收盘价（后复权） | 15.32 |
| 是否ST | ST标记（可选） | 0 或 1 |

其他可选列：开盘、最高、最低、成交量、成交额、昨收、均价、涨停价、跌停价、前复权因子、是否停牌

```
data/
├── 000001.csv
├── 000002.csv
├── 600000.csv
└── ...
```

### ClickHouse 模式

需要一个包含日线行情数据的 ClickHouse 表（如 tushare_daily_basic），至少包含以下字段：

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `ts_code` | String | 股票代码（如 `000001.SZ`） |
| `trade_date` | String | 交易日期（`YYYYMMDD` 格式） |
| `close` | Float64 | 收盘价 |
| `turnover_rate` | Float64 | 换手率（用于近似过滤停牌日） |

已知限制：
- ClickHouse 模式不支持严格 ST 过滤（表中无 ST 字段），仅通过 `turnover_rate > 0` 近似过滤停牌日
- `close` 字段是否为后复权价格取决于数据源，请确认数据口径一致性

## 文档

- [开发文档](docs/development.md)
- [交谈记录](docs/conversation-log.md)
