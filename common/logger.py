"""日志配置 — daemon 用全局 logger；api 用独立 shared_logger（壳子多插件隔离）"""
import sys
from pathlib import Path

from loguru._logger import Core, Logger  # 独立实例构造
from loguru import logger  # 全局 logger（daemon 侧使用，独立进程无冲突）


def _file_format(record):
    """文件 handler 格式化：消息里的控制字符转义为可读形式，保证一条日志只占一行
    @param record loguru record
    @returns 命名字段模板（callable 模式不自动补 \\n，需显式结尾）
    """
    record["message"] = str(record["message"]).replace("\\", "\\\\").replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    return "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <7} | {name}:{line} | {message}{exception}\n"


_project_root = Path(__file__).resolve().parent.parent
_log_dir = _project_root / "log"
_log_dir.mkdir(exist_ok=True)

# ── 全局 logger（daemon 侧：main.py / core / reader 等 from loguru import logger）──
logger.remove()
logger.add(sys.stderr, level="TRACE", format="<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> | {name}:{line} |  <level>{message}</level>")
logger.add(str(_log_dir / "{time:YYYY-MM-DD}.log"), level="TRACE", rotation="1 day", retention="30 days", format=_file_format, encoding="utf-8")

# ── 独立 Logger 实例（api 侧：router.py from common import shared_logger，互不干扰）──
_plugin_core = Core()
shared_logger = Logger(core=_plugin_core, exception=None, depth=1, record=False, lazy=False, colors=False, raw=False, capture=True, patchers=[], extra={})
shared_logger.add(sys.stderr, level="TRACE", format="<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> | {name}:{line} |  <level>{message}</level>")
shared_logger.add(str(_log_dir / "{time:YYYY-MM-DD}.log"), level="TRACE", rotation="1 day", retention="30 days", format=_file_format, encoding="utf-8")
