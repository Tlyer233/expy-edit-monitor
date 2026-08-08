"""common 包：公共工具。含 __init__.py 以便壳子 L3 隔离可 shadow 本包"""
from .logger import shared_logger  # 独立 Logger 实例（api 侧用，不污染全局 loguru）
