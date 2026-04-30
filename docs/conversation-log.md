# AStockLine 架构演进与优化记录

## ClickHouse 数据源收敛 (2026-04)

项目已收敛为只使用 ClickHouse 数据源，不再保留 CSV 运行路径。

关键改造：

1. **ClickHouse loader**
   - `backend/data_loader/clickhouse_loader.py` 使用 `clickhouse-connect` 通过 HTTP 端口接入。
   - 输出标准价格宽表：`DataFrame(index=DatetimeIndex, columns=ts_code, values=close)`。
   - 使用 `FINAL` 处理 `ReplacingMergeTree` 未合并重复行。
   - 使用 `turnover_rate > 0` 近似过滤停牌日。

2. **配置收敛**
   - `settings.py` 固定 `DATA_SOURCE = "clickhouse"`。
   - `.env.example` 只保留 ClickHouse 连接参数。
   - `scripts/preprocess.py` 直接导入 ClickHouse loader。

3. **缓存校验**
   - 预处理输出 `cache_meta.json`，记录 ClickHouse host/database/table、日期范围、股票数和交易日数。
   - API 请求前校验缓存是否由 ClickHouse 生成，以及配置是否与当前环境一致。
   - 校验失败时返回 `HTTP 503`，提示重新运行预处理。

4. **局域网访问**
   - 前端 API 地址根据当前页面 host 动态生成，避免局域网设备请求自己的 `127.0.0.1`。
   - 后端启动命令使用 `--host 0.0.0.0 --port 8000`。
   - 前端静态服务使用 `python3 -m http.server 5173 --bind 0.0.0.0`。
