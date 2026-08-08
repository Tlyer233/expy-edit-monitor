"""
Worker A — Diff Worker：轮询 event.status='diffing'，填充 diff + mode
与 eslistener / desc_worker 平级，通过 event.status 状态机接力：
主线程写 diffing → 本线程算 diff 写 descing → Worker B 投 LLM 写 done

数据库连接生命周期：每次轮询打开 → 用完即关，禁止长连接
"""

import sys  # sys.path
import time  # 轮询间隔
from pathlib import Path  # 快照存在性判断 / 删除

from loguru import logger  # 日志

BASE_DIR = Path(__file__).resolve().parent.parent  # core/../ = 5_edit_monitor_magic/
sys.path.insert(0, str(BASE_DIR))

from db.repository import (  # 数据库操作
    get_conn, init_db, poll_events, update_event, update_meta, get_meta_by_id,
)
from reader import read_file  # 统一入口：按后缀分发 Reader，返回 (diff, new_content, mode)

_db_path = BASE_DIR / "data" / "file_events.db"  # 数据库文件路径
POLL_LIMIT = 10  # 每轮最多处理条数
POLL_INTERVAL = 1.0  # 轮询间隔（秒）


def _process_event(conn, ev: dict) -> None:
    """
    处理单条 diffing 事件：读快照 → reader 算 diff → 更新 meta → 删快照 → 标 descing
    @param conn 数据库连接
    @param ev 事件字典（来自 poll_events）
    """
    event_id = ev["id"]  # 事件主键
    # STEP1: 先用tmpfile读这一时刻的文件内容 ==> newContent
    tmp_path = ev.get("tmpfilepath") or ""  # 快照路径（可能为空字符串）
    if not tmp_path or not Path(tmp_path).exists():  # 快照缺失
        update_event(conn, event_id, status="failed")  # 无快照无法算 diff → 失败
        logger.warning(f"[diff_worker] 快照缺失 id={event_id} tmp={tmp_path} → failed")  # 日志
        return  # 结束本条

    meta = get_meta_by_id(conn, ev["ref_meta"])  # 查 meta 取旧内容
    old_content = (meta or {}).get("content") or ""  # 旧内容（meta 缺失时空兜底）

    try:  # reader 算 diff 可能失败（不支持格式 / 读取错误 / vision 超时）
        diff_text, new_content, mode = read_file(old_content, tmp_path)  # 统一入口：内部按后缀分发 planin/with_image
        logger.info(f"[diff_worker] diff_text:{diff_text}, mode:{mode}")
    except Exception:  # 任意异常
        update_event(conn, event_id, status="failed")  # 无法提取内容 → 失败
        logger.exception(f"[diff_worker] 读取快照失败 id={event_id} tmp={tmp_path} → failed")  # 日志
        return  # 结束本条

    update_event(conn, event_id, diff=diff_text, mode=mode, status="descing")  # 回填 diff + mode + 转 descing
    update_meta(conn, ev["ref_meta"], content=new_content, updated_at=ev["et"])  # 更新 meta 内容 + 最后修改时间（不更新 file_path）

    try:  # 删除快照可能失败
        Path(tmp_path).unlink()  # 快照用完即删
    except OSError:  # 删除失败
        logger.warning(f"[diff_worker] 快照删除失败 id={event_id} tmp={tmp_path}")  # 日志

    logger.info(f"[diff_worker] id={event_id} meta={ev['ref_meta']} mode={mode} diff_len={len(diff_text)} → descing")  # 日志


def _process_batch(conn) -> int:
    """
    处理一批 diffing 事件
    @param conn 数据库连接
    @returns 本批实际处理条数
    """
    events = poll_events(conn, "diffing", POLL_LIMIT)  # 按 st 正序取最早一批
    for ev in events:  # 逐条处理
        try:  # 单条失败不影响批次
            _process_event(conn, ev)  # 处理
        except Exception:  # 兜底
            logger.exception(f"[diff_worker] 处理异常 id={ev['id']}")  # 日志
    return len(events)  # 返回条数


def run(interval: float = POLL_INTERVAL) -> None:
    """
    常驻轮询循环：diffing → 算 diff → descing（由 main.py 以线程启动）
    @param interval 轮询间隔（秒）
    """
    init_db(_db_path)  # 幂等建表
    logger.info(f"[diff_worker] 启动，轮询间隔 {interval}s")  # 日志
    while True:  # 常驻循环
        conn = get_conn(_db_path)  # 每轮新开连接
        try:  # 异常不退出循环
            with conn:  # 自动提交 / 回滚
                _process_batch(conn)  # 处理一批
        except Exception:  # 兜底
            logger.exception("[diff_worker] 轮询异常")  # 日志
        finally:  # 无论如何关闭
            conn.close()  # 用完即关，禁止长连接
        time.sleep(interval)  # 等待下一轮
