"""AStockLine 全局配置"""
import os
from pathlib import Path

# 加载 .env 文件（如果 python-dotenv 已安装）
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent.parent / ".env")
except ImportError:
    pass

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.parent

# 数据源固定为 ClickHouse
DATA_SOURCE = "clickhouse"

# ClickHouse 连接配置
CLICKHOUSE_HOST = os.environ.get("CLICKHOUSE_HOST", "")
CLICKHOUSE_PORT = int(os.environ.get("CLICKHOUSE_PORT", "8123"))
CLICKHOUSE_DATABASE = os.environ.get("CLICKHOUSE_DATABASE", "default")
CLICKHOUSE_USER = os.environ.get("CLICKHOUSE_USER", "default")
CLICKHOUSE_PASSWORD = os.environ.get("CLICKHOUSE_PASSWORD", "")
CLICKHOUSE_TABLE = os.environ.get("CLICKHOUSE_TABLE", "tushare_daily_basic")

# 计算参数
CORRELATION_THRESHOLD = 0.7       # 默认相关性阈值
ROLLING_WINDOW_SIZE = 120         # 滚动窗口大小（交易日）
ROLLING_STEP_SIZE = 20            # 滚动步长（交易日）

# 数据筛选
MIN_TRADING_DAYS = 200            # 最少交易日数（少于此数的股票排除）
EXCLUDE_ST = True                 # 是否排除ST股票
EXCLUDE_SUSPENDED = True          # 是否排除停牌日数据

# 缓存
CACHE_DIR = Path(__file__).parent.parent / "cache"

# API
API_HOST = "127.0.0.1"
API_PORT = 8000
