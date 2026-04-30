# AStockLine ClickHouse 数据源接入计划

## 背景

AStockLine 当前是一个本地 CSV 数据源驱动的 A 股走势关系网络分析工具：

- `backend/data_loader/csv_loader.py` 读取 CSV 并输出价格宽表
- `scripts/preprocess.py` 计算收益率、相关矩阵和多阈值网络缓存
- `backend/api/main.py` 从缓存提供 FastAPI 接口
- `frontend/` 直接消费 API，前端不关心数据源

本次目标是将数据源扩展为可配置的 CSV / ClickHouse 双模式，并保持下游计算层和前端行为不变。

---

## 目标

1. 新增 ClickHouse loader，使其输出格式与 CSV loader 一致：
   - `pd.DataFrame`
   - `index=交易日期`
   - `columns=股票代码`
   - `values=收盘价`
2. 通过环境变量选择数据源：
   - `ASTOCK_DATA_SOURCE=csv`
   - `ASTOCK_DATA_SOURCE=clickhouse`
3. 增加缓存元数据，避免 CSV / ClickHouse 缓存混用。
4. 保持 `backend/compute/*`、`backend/analysis/*`、`frontend/*` 不变。

非目标：

- 不在本阶段实现 API 每次请求都直连 ClickHouse 实时查询。
- 不在本阶段引入 Spec Kit。当前改动面较小，先完成数据源切换；如果后续要长期规范流程，再单独初始化 Spec Kit。

---

## ClickHouse 数据源确认

以下信息来自目标 ClickHouse 服务器的实际检查。

| 参数 | 值 |
|------|-----|
| 主机地址 | 远程 Debian 服务器，需通过环境变量配置 |
| HTTP 端口 | `8123` |
| 用户名 | `default` |
| 密码 | 空 |
| 数据库名 | `default` |

目标表：`tushare_daily_basic`

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `ts_code` | LowCardinality(String) | 股票代码，格式如 `000001.SZ` |
| `trade_date` | String | 交易日期，格式为 `YYYYMMDD` |
| `close` | Float64 | 当日收盘价 |
| `turnover_rate` | Float64 | 换手率 |
| `total_mv` | Float64 | 总市值，万元 |
| `circ_mv` | Float64 | 流通市值，万元 |

已知约束：

- `trade_date` 不是 Date 类型，SQL 查询前必须把 `YYYY-MM-DD` 转成 `YYYYMMDD`。
- 表中没有 `is_suspended` / `is_st` 字段。
- 该表是 `ReplacingMergeTree`，同一 `(trade_date, ts_code)` 可能存在未合并重复记录，不能直接假设 `pivot()` 一定成功。

---

## 设计原则

### 数据源契约

CSV 和 ClickHouse loader 都必须返回同一种价格矩阵：

```python
DataFrame(index=DatetimeIndex, columns=stock_code, values=close_price)
```

下游只依赖这个契约，不感知数据来自 CSV 还是 ClickHouse。

### 日期契约

Python 层统一使用 `YYYY-MM-DD` 或 `pd.Timestamp`。

ClickHouse 查询前转换为 `YYYYMMDD`：

```python
def normalize_trade_date(value: str | None) -> str | None:
    if not value:
        return None
    return pd.Timestamp(value).strftime("%Y%m%d")
```

禁止直接拿 `YYYY-MM-DD` 和 ClickHouse 的 `trade_date='YYYYMMDD'` 字符串比较。

### 缓存契约

预处理输出除了现有文件：

- `returns.pkl`
- `corr_matrix.pkl`
- `network_t50.json` ~ `network_t90.json`

还必须新增：

- `cache_meta.json`

示例：

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

API 读取缓存时应校验 `cache_meta.json` 是否存在、`data_source` 是否与当前配置一致。若不一致，应返回明确错误，要求重新运行预处理。

---

## 文件变更

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/data_loader/clickhouse_loader.py` | NEW | ClickHouse 数据加载模块 |
| `.env.example` | NEW | CSV / ClickHouse 环境变量模板 |
| `backend/config/settings.py` | MODIFY | 新增数据源和 ClickHouse 配置 |
| `scripts/preprocess.py` | MODIFY | 根据 `DATA_SOURCE` 选择 loader，并写入缓存元数据 |
| `backend/api/main.py` | MODIFY | 读取缓存前校验 `cache_meta.json` |
| `backend/requirements.txt` | MODIFY | 新增 `clickhouse-connect` |
| `README.md` | MODIFY | 补充 CSV / ClickHouse 两种启动方式 |
| `backend/compute/*` | 不变 | 继续消费价格矩阵 / 收益率矩阵 |
| `backend/analysis/*` | 不变 | 网络分析逻辑不变 |
| `frontend/*` | 不变 | API 契约不变 |

---

## 实施步骤

### Step 1: 配置项

修改 `backend/config/settings.py`：

```python
DATA_SOURCE = os.environ.get("ASTOCK_DATA_SOURCE", "csv").lower()

CLICKHOUSE_HOST = os.environ.get("CLICKHOUSE_HOST", "")
CLICKHOUSE_PORT = int(os.environ.get("CLICKHOUSE_PORT", "8123"))
CLICKHOUSE_DATABASE = os.environ.get("CLICKHOUSE_DATABASE", "default")
CLICKHOUSE_USER = os.environ.get("CLICKHOUSE_USER", "default")
CLICKHOUSE_PASSWORD = os.environ.get("CLICKHOUSE_PASSWORD", "")
CLICKHOUSE_TABLE = os.environ.get("CLICKHOUSE_TABLE", "tushare_daily_basic")
```

默认值保留为 `csv`，避免破坏当前 README 描述的本地 CSV 快速启动。

ClickHouse 模式下，如果 `CLICKHOUSE_HOST` 为空，应在 loader 中抛出清晰错误。

---

### Step 2: 新增 ClickHouse loader

新增 `backend/data_loader/clickhouse_loader.py`。

核心要求：

- 使用 `clickhouse-connect` 的 HTTP 连接，端口默认 `8123`。
- 函数签名与 CSV loader 对齐：

```python
def load_all_stocks(start_date: str = None, end_date: str = None) -> pd.DataFrame:
    ...
```

- 将 `start_date/end_date` 从 `YYYY-MM-DD` 转成 `YYYYMMDD` 后再用于 SQL。
- 使用参数化查询，不拼接日期输入。
- 表名不能作为查询参数传入，`CLICKHOUSE_TABLE` 必须只允许安全标识符，例如 `tushare_daily_basic` 或 `db.table`。
- SQL 侧过滤：
  - `close > 0`
  - `turnover_rate > 0`，作为停牌日的近似过滤
- 对重复 `(trade_date, ts_code)` 做处理，避免 `pivot()` 失败。
- pivot 后按 `MIN_TRADING_DAYS` 过滤股票列。

推荐 SQL 形态：

```sql
SELECT
    trade_date,
    ts_code,
    close
FROM {safe_table} FINAL
WHERE trade_date >= {start_date:String}
  AND trade_date <= {end_date:String}
  AND close > 0
  AND turnover_rate > 0
ORDER BY trade_date, ts_code
```

说明：

- `FINAL` 用于处理 `ReplacingMergeTree` 尚未后台合并的重复行，优先保证正确性。
- 如果 `FINAL` 在全量预处理时性能不可接受，应确认表是否有版本列或更新时间列，再改为按 `(trade_date, ts_code)` 聚合取最新记录。
- 如果没有版本列，不要使用 `argMax(close, trade_date)` 作为去重依据，因为重复行的 `trade_date` 相同，结果不稳定。
- `start_date/end_date` 为空时应动态省略对应 WHERE 条件，不要传入空字符串比较。

Python 侧处理：

```python
df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d")
price_matrix = df.pivot_table(
    index="trade_date",
    columns="ts_code",
    values="close",
    aggfunc="last",
)
price_matrix = price_matrix.sort_index()
min_required_days = min(MIN_TRADING_DAYS, len(price_matrix.index))
price_matrix = price_matrix.dropna(axis=1, thresh=min_required_days)
```

注意：ClickHouse 模式本阶段不支持严格 ST 过滤。若需要排除 ST，应另接股票名称 / 状态元数据表后再实现。

---

### Step 3: 修改预处理入口

修改 `scripts/preprocess.py`。

加载数据源：

```python
from backend.config.settings import DATA_SOURCE

if DATA_SOURCE == "clickhouse":
    from backend.data_loader.clickhouse_loader import load_all_stocks
elif DATA_SOURCE == "csv":
    from backend.data_loader.csv_loader import load_all_stocks
else:
    raise ValueError(f"不支持的数据源: {DATA_SOURCE}")
```

预处理完成后写入 `cache_meta.json`。

建议在 `main()` 中记录：

- 当前数据源
- ClickHouse host/database/table，或 CSV data dir
- 价格矩阵日期范围
- 股票数
- 交易日数
- 生成时间

不要只提示“清空 cache”。程序应通过 meta 校验主动发现缓存来源不匹配。

---

### Step 4: 修改 API 缓存校验

修改 `backend/api/main.py`。

新增 `_load_cache_meta()` 和 `_validate_cache_meta()`：

- `cache_meta.json` 不存在：返回明确错误，要求重新运行预处理。
- 当前 `DATA_SOURCE` 与 meta 中的 `data_source` 不一致：返回明确错误。
- 可选：ClickHouse 模式下校验 host/database/table 是否一致。

现阶段 `/api/network?start_date=&end_date=` 仍从 `returns.pkl` 切片实时计算相关矩阵，不直连 ClickHouse。

这意味着：

- 任意日期范围只支持预处理缓存覆盖的数据区间。
- 若需要覆盖新日期，必须重新运行 `scripts/preprocess.py`。

---

### Step 5: 依赖与环境模板

修改 `backend/requirements.txt`：

```txt
clickhouse-connect>=0.7
```

新增 `.env.example`：

```env
# csv / clickhouse
ASTOCK_DATA_SOURCE=csv

# CSV 模式
ASTOCK_DATA_DIR=/path/to/csv/data

# ClickHouse 模式
# ASTOCK_DATA_SOURCE=clickhouse
# CLICKHOUSE_HOST=<your-debian-server-ip>
# CLICKHOUSE_PORT=8123
# CLICKHOUSE_DATABASE=default
# CLICKHOUSE_USER=default
# CLICKHOUSE_PASSWORD=
# CLICKHOUSE_TABLE=tushare_daily_basic
```

---

### Step 6: README 更新

README 需要说明：

1. 默认模式仍是 CSV。
2. ClickHouse 模式需要配置环境变量。
3. 切换数据源后必须重新运行预处理。
4. API 日期筛选基于缓存，不是每次请求实时查库。

---

## 验证计划

### 静态验证

1. Python 语法检查：

```bash
PYTHONPYCACHEPREFIX=/tmp/astockline-pycache python3 -m compileall backend scripts
```

2. 确认 `requirements.txt` 包含 `clickhouse-connect`。

### Loader 验证

1. `load_all_stocks(start_date="2024-01-01", end_date="2024-01-31")` 能返回非空 DataFrame。
2. SQL 实际传入的日期是 `20240101` 和 `20240131`。
3. 返回结果满足：
   - index 是 `DatetimeIndex`
   - columns 是股票代码
   - 没有重复 index/column 组合导致 pivot 失败
   - 每列至少 `MIN_TRADING_DAYS` 个有效价格，除非查询区间本身更短

### 缓存验证

1. CSV 模式运行预处理后，`cache_meta.json` 中 `data_source=csv`。
2. ClickHouse 模式运行预处理后，`cache_meta.json` 中 `data_source=clickhouse`。
3. 手动切换 `ASTOCK_DATA_SOURCE` 后不重新预处理，API 应返回缓存来源不匹配错误。
4. 删除 `cache_meta.json` 后，API 应返回明确错误，而不是静默读取旧 pickle。

### API 验证

1. `/api/date-range` 返回缓存覆盖的日期范围。
2. `/api/network?threshold=0.7` 返回节点、边和统计信息。
3. `/api/network?threshold=0.7&start_date=2024-01-01&end_date=2024-03-31` 基于缓存切片计算。
4. 日期区间超出缓存范围时，应返回空结果或明确提示，不能静默返回误导性网络。

### 端到端验证

1. 启动后端：

```bash
uvicorn backend.api.main:app --reload
```

2. 启动前端：

```bash
cd frontend
npx serve . -l 3000
```

3. 在浏览器中验证：
   - 加载网络
   - 调整阈值
   - 日期筛选
   - 搜索股票
   - 聚类点击
   - 隐藏孤立节点

---

## 风险与后续优化

### 风险 1: ClickHouse 表不是复权收盘价

项目 README 描述的是“后复权价格”。`tushare_daily_basic.close` 是否为后复权价需要再次确认。

如果不是复权价，相关性结果会与原 CSV 口径不一致。应优先寻找后复权行情表，或在 ClickHouse / Python 侧补复权逻辑。

### 风险 2: ST 过滤不完整

`tushare_daily_basic` 没有 ST 字段。本阶段只能用 `turnover_rate > 0` 近似过滤停牌日，不能严格排除 ST 股票。

后续可接入股票基础信息表或名称历史表，实现按日期排除 ST。

### 风险 3: 全量数据内存压力

约 1100 万行数据 pivot 成宽表后仍可接受，但预处理阶段会占用较多内存。

后续可优化为：

- ClickHouse 侧按日期范围分批查询
- 本地分块写 parquet
- 仅缓存收益率矩阵
- 按用户选择的股票池预处理

### 风险 4: API 实时模式仍依赖缓存

本阶段 API 日期筛选是对 `returns.pkl` 切片，不会查询 ClickHouse 最新数据。

后续如需真正实时，可在 `backend/api/main.py` 中增加 ClickHouse 日期区间直查路径，但需要配套请求超时、结果缓存和并发控制。
