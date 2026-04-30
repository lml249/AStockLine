# AStockLine ClickHouse-only 实施计划

## 当前决策

项目只保留 ClickHouse 数据源，不再支持本地 CSV 读取、CSV/ClickHouse 双模式切换或 CSV 缓存校验。

## 数据源

目标 ClickHouse 表：`tushare_daily_basic`

必要字段：

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `ts_code` | String | 股票代码，如 `000001.SZ` |
| `trade_date` | String | 交易日期，格式 `YYYYMMDD` |
| `close` | Float64 | 收盘价 |
| `turnover_rate` | Float64 | 换手率，用于近似过滤停牌日 |

已知限制：

- `trade_date` 不是 Date 类型，loader 会将 Python 层 `YYYY-MM-DD` 转成 `YYYYMMDD`。
- 当前表没有 ST 字段，不能严格排除 ST 股票。
- `close` 是否为后复权价格取决于 ClickHouse 表数据口径。

## 文件职责

| 文件 | 说明 |
|------|------|
| `backend/data_loader/clickhouse_loader.py` | 从 ClickHouse 加载价格宽表 |
| `backend/config/settings.py` | 读取 `.env` 和 ClickHouse 连接配置，固定 `DATA_SOURCE = "clickhouse"` |
| `scripts/preprocess.py` | 预处理 ClickHouse 数据并生成缓存 |
| `backend/api/main.py` | 提供 API，并校验 ClickHouse 缓存元数据 |
| `.env.example` | ClickHouse 环境变量模板 |
| `README.md` | ClickHouse-only 使用说明 |

## 预处理输出

- `backend/cache/returns.pkl`
- `backend/cache/corr_matrix.pkl`
- `backend/cache/network_t50.json` ~ `network_t90.json`
- `backend/cache/cache_meta.json`

`cache_meta.json` 必须包含：

```json
{
  "data_source": "clickhouse",
  "clickhouse_host": "10.0.0.1",
  "clickhouse_database": "default",
  "clickhouse_table": "tushare_daily_basic",
  "date_start": "2015-01-05",
  "date_end": "2026-04-22",
  "stock_count": 4899,
  "trading_days": 2700,
  "generated_at": "2026-04-30T12:00:00+08:00"
}
```

## 验证

1. 配置 `.env`：

```env
CLICKHOUSE_HOST=<your-server-ip>
CLICKHOUSE_PORT=8123
CLICKHOUSE_DATABASE=default
CLICKHOUSE_USER=default
CLICKHOUSE_PASSWORD=
CLICKHOUSE_TABLE=tushare_daily_basic
```

2. 生成缓存：

```bash
.venv/bin/python -m scripts.preprocess
```

3. 启动服务：

```bash
.venv/bin/uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8000
cd frontend
python3 -m http.server 5173 --bind 0.0.0.0
```

4. 验证 API：

```bash
curl 'http://127.0.0.1:8000/api/network?threshold=0.7'
curl 'http://127.0.0.1:8000/api/date-range'
```
