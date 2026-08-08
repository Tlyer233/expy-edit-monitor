"""
5_edit_monitor_magic Daemon — 三线程文件编辑监控
主线程：eslogger 子进程 → 事件循环 → eslistener.handle_file_event（verify 管线 + deal_mid）
Worker A：diff_worker 轮询（diffing → descing）
Worker B：desc_worker 轮询（descing → done）

三个平级线程通过 event.status 状态机接力，数据库连接各自用完即关
"""

import json  # 解析 eslogger JSON
import os  # 权限检查
import subprocess  # eslogger 子进程
import sys  # sys.path
import threading  # Worker A/B 线程
from datetime import datetime, timedelta  # 时区转换
from pathlib import Path  # 路径

from loguru import logger  # 日志（common.logger 已初始化 handlers）

BASE = Path(__file__).parent  # 项目根目录
sys.path.insert(0, str(BASE))  # 加入搜索路径

import common.logger  # noqa: E402  # 导入即初始化日志（daemon 文件 handler → log/，与 api 侧解耦）
from common.utils import load_config  # 配置加载（timezone_offset）
from core import handle_file_event, run_diff_worker, run_desc_worker  # 三线程入口


def _extract_path(ev: dict) -> str:
    """
    从 eslogger 事件体中提取目标文件路径（新架构只关心 dst，rename 的 src 由 deal_mid 分支2 兜底）
    @param ev eslogger 事件体（d["event"]）
    @returns 文件路径，提取失败返回空串
    """
    if "write" in ev:  # 写入事件
        return ev["write"]["target"]["path"]  # 目标文件路径
    if "create" in ev:  # 创建事件
        return ev["create"].get("destination", {}).get("path", "")  # 目标路径
    if "rename" in ev:  # 重命名事件（xattr mid 保留，dst 的追踪交给 deal_mid 分支2）
        rn = ev["rename"]  # 重命名事件体
        dst = rn.get("destination", {}).get("existing_file", {}).get("path", "")  # existing_file 携带完整路径
        if not dst:  # 无 existing_file 则拼接 new_path
            d = rn.get("destination", {}).get("new_path", {})  # 目录 + 文件名
            dst = f"{d.get('dir', {}).get('path', '')}/{d.get('filename', '')}"  # 拼接完整路径
        return dst  # 返回重命名后路径
    if "clone" in ev:  # 克隆事件
        return ev["clone"].get("target_file", {}).get("path", "")  # 目标路径
    if "exchangedata" in ev:  # 数据交换事件
        for k in ("file1", "file2"):  # 两个文件任取其一
            fp = ev["exchangedata"].get(k, {}).get("path", "")  # 文件路径
            if fp:  # 非空即返回
                return fp  # 返回路径
    return ""  # 未识别事件类型


def main():
    """主入口：权限检查 → 启动 Worker A/B → 启动 eslogger → 事件循环"""
    # ── 权限检查（eslogger 需要 root）──
    if os.geteuid() != 0:  # 非 root 无法监听
        logger.error("eslogger 需要 root 权限，请使用 sudo 运行")  # 提示
        sys.exit(1)  # 退出

    # ── 启动 Worker A/B 线程（平级，daemon 随主进程退出）──
    threading.Thread(target=run_diff_worker, name="diff_worker", daemon=True).start()  # Worker A
    threading.Thread(target=run_desc_worker, name="desc_worker", daemon=True).start()  # Worker B

    # ── 启动 eslogger 子进程（内核级文件事件）──
    events = ["write", "rename", "create", "clone", "exchangedata"]  # 只监督这几个事件
    proc = subprocess.Popen(
        ["eslogger"] + events,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )

    logger.info("eslogger 监听中，Worker A/B 已启动")  # 启动提示
    sys.stdout.flush()  # 立即输出

    # ── 主事件循环 ──
    if proc.stdout is None:  # Popen 指定了 PIPE，类型兜底
        logger.error("eslogger stdout 为空")  # 错误
        sys.exit(1)  # 退出

    tz_offset = load_config().get("timezone_offset", 8)  # 时区偏移（config.json 默认东八区）
    try:  # 捕获中断以便清理 eslogger
        for line in proc.stdout:  # eslogger 每行一个 JSON 事件
            try:  # 单条解析异常不影响主循环
                d = json.loads(line)  # 解析 JSON
                ev = d["event"]  # 事件体
                file_path = _extract_path(ev)  # 提取目标文件路径
                if not file_path:  # 未识别事件
                    continue  # 跳过
                proc_full = d["process"]["executable"]["path"]  # 进程完整路径
                dt_utc = datetime.fromisoformat(d["time"][:19])  # UTC 时间
                ts_dt = dt_utc + timedelta(hours=tz_offset)  # UTC → 本地时间
                handle_file_event(proc_full, file_path, ts_dt)  # eslistener 入口（verify 管线 + deal_mid）
            except Exception:  # 兜底
                logger.error("[main] 事件处理异常")  # 记录单条异常
    except KeyboardInterrupt:  # Ctrl+C
        logger.trace("收到中断，正在退出...")  # 提示
    finally:  # 无论如何
        proc.terminate()  # 关闭 eslogger 子进程


if __name__ == "__main__":
    main()
