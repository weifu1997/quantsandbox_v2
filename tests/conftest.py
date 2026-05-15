import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 测试环境：强制使用 memory 数据源，不受 .env 或环境变量影响
# pydantic-settings 会优先读取环境变量，再读 .env 文件
os.environ["QS_MARKET_DATA_MODE"] = "memory"
os.environ["QS_FUNDAMENTAL_DATA_MODE"] = "memory"
os.environ.pop("QS_TUSHARE_TOKEN", None)
os.environ.pop("QS_TUSHARE_HTTP_URL", None)