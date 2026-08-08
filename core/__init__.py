"""core 包 — 三层平级线程：eslistener / diff_worker / desc_worker"""  # 各自独立运行，通过 event.status 接力

from .eslistener import handle_file_event  # eslogger 事件处理入口
from .diff_worker import run as run_diff_worker  # Worker A 轮询线程入口
from .desc_worker import run as run_desc_worker  # Worker B 轮询线程入口

__all__ = ["handle_file_event", "run_diff_worker", "run_desc_worker"]  # 显式导出（消除未使用导入提示）
