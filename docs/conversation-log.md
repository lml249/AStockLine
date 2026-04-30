# AStockLine 架构演进与优化记录

## 阶段一：本地 CSV 数据流优化

- 实现了 `csv_loader.py` 用于快速读取并清洗单支股票 CSV 数据。
- 开发预处理脚本，提前计算完整的相关性矩阵并生成多阈值网络结构 JSON 缓存。
- 构建 FastAPI 服务以分发预计算好的 JSON。

## 阶段二：ClickHouse 远程数据源接入 (2026-04)

**目标**：在不改变核心计算逻辑和 API 结构的情况下，平滑接入 ClickHouse 数据库。

**关键改造记录**：

1. **Loader 抽象设计**
   - 编写 `clickhouse_loader.py` 适配 `clickhouse-connect`，利用 HTTP 协议接入。
   - 约定返回与 CSV Loader 结构完全一致的价格宽表 DataFrame。
   - SQL 处理策略：采用 `FINAL` 和 `turnover_rate > 0` 联合进行重复合并与近似停牌过滤。

2. **环境变量与平滑回退**
   - 新增 `ASTOCK_DATA_SOURCE` 控制路由。
   - 默认回退为 `csv` 以防旧运行环境崩溃。
   - 配置引入 `python-dotenv` 支持通过 `.env` 覆写。

3. **缓存污染防御机制**
   - 问题：CSV 缓存和 ClickHouse 缓存如未隔离，会导致查询结果与配置源不一致。
   - 解决：`preprocess.py` 结束后输出 `cache_meta.json` 包含数据源签名；`main.py` 提供 `_validate_cache_meta()` 验证防御，未通过校验抛出 `HTTP 503` 要求重新生成。

4. **代码规范化升级**
   - 从 `on_event("startup")` 迁移至 `lifespan` context manager 修复 FastAPI 弃用警告。
   - 引入 `__future__ import annotations` 以兼容 Python 3.9 环境。
   - 修复前端错误异常处理不够友好的问题。
