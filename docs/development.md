# AStockLine 开发文档

## 架构概览

AStockLine 采用后端预计算 + 前端轻量可视化的架构。数据流如下：

1. **数据源层** (`backend/data_loader/`)
   - 当前只支持远程 ClickHouse (`clickhouse_loader.py`)。
   - loader 返回契约：`DataFrame(index=DatetimeIndex, columns=stock_code, values=close_price)`。

2. **计算层** (`backend/compute/` & `backend/analysis/`)
   - 依赖标准化价格矩阵。
   - 包含：日收益率计算、皮尔逊相关性计算、网络构建、Louvain 社区检测和网络统计。
   - 此层不得直接访问 ClickHouse，仅接收 DataFrame。

3. **预处理机制** (`scripts/preprocess.py`)
   - 全量相关矩阵计算昂贵，项目在这一步预先计算结果。
   - 输出序列化到 `backend/cache/`。
   - `cache_meta.json` 记录 ClickHouse host/database/table 和数据日期范围，防止缓存与当前配置不一致。

4. **API 层** (`backend/api/`)
   - FastAPI 向前端提供查询接口。
   - 不带日期参数的请求读取预处理 JSON；带日期参数的请求读取缓存收益率矩阵并按日期切片计算。
   - 启动和请求时都会校验 `cache_meta.json`。

## ClickHouse 配置

项目通过 `.env` 或环境变量读取以下配置：

- `CLICKHOUSE_HOST`
- `CLICKHOUSE_PORT`
- `CLICKHOUSE_DATABASE`
- `CLICKHOUSE_USER`
- `CLICKHOUSE_PASSWORD`
- `CLICKHOUSE_TABLE`

目标表至少需要字段：

- `ts_code`
- `trade_date`
- `close`
- `turnover_rate`

`trade_date` 在库中为 `YYYYMMDD` 字符串；Python/API 层使用 `YYYY-MM-DD`，loader 查询前会转换格式。

## 数据口径

- `turnover_rate > 0` 用作停牌日的近似过滤。
- 当前表没有 ST 字段，因此不能严格过滤 ST 股票。
- `close` 是否为后复权价格取决于 ClickHouse 表数据本身，需要在数据源侧确认。
