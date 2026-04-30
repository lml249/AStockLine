# AStockLine 开发文档

## 架构概览

AStockLine 采用后端预计算 + 前端轻量可视化的架构。数据流如下：

1. **数据源层** (`backend/data_loader/`)
   - 支持多数据源：本地 CSV (`csv_loader.py`) 和远程 ClickHouse (`clickhouse_loader.py`)。
   - 所有数据加载器必须返回相同的契约：`DataFrame(index=DatetimeIndex, columns=stock_code, values=close_price)`。

2. **计算层** (`backend/compute/` & `backend/analysis/`)
   - 依赖标准化价格矩阵。
   - 包含：日收益率计算、皮尔逊相关性计算、网络构建（基于阈值）、Louvain 社区检测和网络统计。
   - 设计约束：此层不得直接访问底层数据库或文件，仅接收 DataFrame。

3. **预处理机制** (`scripts/preprocess.py`)
   - 由于 4000+ 股票全量相关矩阵计算昂贵，项目在这一步预先计算结果。
   - 输出序列化到 `backend/cache/` (pickle 和 json 格式)。
   - **安全机制**：将数据源配置和执行环境写入 `cache_meta.json`，防止不同环境配置发生数据串扰。

4. **API 层** (`backend/api/`)
   - FastAPI 轻量封装，负责向前端提供查询接口。
   - **混合模式**：不带日期参数的请求直接读取预处理生成的 JSON；带日期的请求读取缓存的收益率矩阵进行实时切片计算。
   - 包含启动时验证（校验 `cache_meta.json` 有效性）。

## 数据源配置

修改环境中的 `ASTOCK_DATA_SOURCE` 环境变量进行数据源切换：

### CSV 模式 (默认)
- 数据流：`data/` 目录下的 `.csv` 文件 -> Pandas DataFrame。
- 使用：适合本地测试与单机部署。

### ClickHouse 模式
- 数据流：连接目标 ClickHouse，执行 SQL 提取 -> Pandas DataFrame。
- 配置项：
  - `CLICKHOUSE_HOST`
  - `CLICKHOUSE_PORT`
  - `CLICKHOUSE_DATABASE`
  - `CLICKHOUSE_USER`
  - `CLICKHOUSE_PASSWORD`
  - `CLICKHOUSE_TABLE` (需确保包含 `ts_code`, `trade_date`, `close`, `turnover_rate` 字段)。
- 使用 `FINAL` 关键字和按日期聚合的最后一条记录作为多重复数据防护策略。

## 添加新数据源

要添加例如 MySQL 或 API 实时拉取等新数据源：
1. 在 `data_loader/` 目录下创建新的 loader，暴露 `load_all_stocks(start_date=None, end_date=None) -> pd.DataFrame` 方法。
2. 在 `config/settings.py` 里添加相应的环境变量。
3. 在 `scripts/preprocess.py` 和 `backend/api/main.py` 的 cache_meta 相关验证中添加支持路由。
