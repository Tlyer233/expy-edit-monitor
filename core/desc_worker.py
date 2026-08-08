"""
Worker B — Desc Worker：轮询 event.status='descing'，按 mode 投递 LLM 总结
与 eslistener / diff_worker 平级，通过 event.status 状态机接力：
Worker A 写 descing → 本线程按 mode 投 POST /lms/task → 标 done（投递成功即 done）

数据库连接生命周期：每次轮询打开 → 用完即关，禁止长连接
"""

import sys  # sys.path
import time  # 轮询间隔
from pathlib import Path  # shell_url 文件路径

import requests  # HTTP 投递
from loguru import logger  # 日志

BASE_DIR = Path(__file__).resolve().parent.parent  # core/../ = 5_edit_monitor_magic/
sys.path.insert(0, str(BASE_DIR))

from common.utils import load_config  # 配置加载（post_llm 块）
from db.repository import get_conn, init_db, poll_events, update_event  # 数据库操作

_db_path = BASE_DIR / "data" / "file_events.db"  # 数据库文件路径
POLL_LIMIT = 10  # 每轮最多处理条数
POLL_INTERVAL = 1.0  # 轮询间隔（秒）


def _submit(ev: dict, config: dict) -> None:
    """
    投递单条事件到 LLM 队列（POST /lms/task），失败抛异常由调用方处理
    @param ev 事件字典（poll_events 返回）
    @param config config.json 的 post_llm 块（enable / plain_diff_prompt / llm_diff_prompt / model）
    @api POST /lms/task
    """
    mode = ev.get("mode") or "plain"  # mode 缺失按 plain 兜底
    shell_url = Path("~/.expy/shell_url").expanduser().read_text().strip()  # 从壳子启动时写入的文件读取地址
    payload = {  # 请求体（7_lms_daemon 的 TaskRequest）
        "content": ev.get("diff") or "",  # diff 文本（投递后 daemon 异步回填 diff_des）
        "method": "chat",  # 文本总结
        "prompt": config["plain_diff_prompt"] if mode == "plain" else config["llm_diff_prompt"],  # 按 mode 选 prompt
        "model": config["model"],  # 统一模型（plain / llm 共用）
        "config": {
            "contextLength": 3000
        },  # LlmLoadModelConfigDict，透传空
        "target_db": str(_db_path),  # 目标数据库路径
        "target_table": "event",  # 目标表名
        "target_row_id": str(ev["id"]),  # 目标行 id
        "target_field": "diff_des",  # LLM 结果异步回填字段
    }
    logger.trace(f"[desc_worker] 投递 id={ev['id']} mode={mode} url={shell_url}/lms/task content_len={len(payload['content'])}")  # 投递前全量日志
    resp = requests.post(f"{shell_url}/lms/task", json=payload, timeout=10)  # POST 请求
    resp.raise_for_status()  # 非 2xx 抛异常
    logger.trace(f"[desc_worker] 投递响应 id={ev['id']} status={resp.status_code} body={resp.text[:200]}")  # 响应全量日志


def _process_event(conn, ev: dict, config: dict) -> None:
    """
    处理单条 descing 事件：按 mode 投递 LLM 总结 → 标 done / failed
    @param conn 数据库连接
    @param ev 事件字典（来自 poll_events）
    @param config config.json 的 post_llm 块
    """
    event_id = ev["id"]  # 事件主键
    if not config["enable"]:  # LLM 总开关关闭
        update_event(conn, event_id, status="done")  # 跳过投递直接 done（diff_des 留空，后续可手动补齐）
        logger.trace(f"[desc_worker] post_llm.enable=false 跳过投递 id={event_id} → done")  # 日志
        return  # 结束本条

    diff_text = ev.get("diff") or ""  # diff 内容（可能为 None / 空串）
    if not diff_text.strip():  # 空 diff（新旧内容相同，无变化无需总结）
        update_event(conn, event_id, status="done")  # 空 diff 直接 done，避免投递 400 → failed
        logger.info(f"[desc_worker] 空 diff 跳过投递 id={event_id} → done")  # 日志
        return  # 结束本条

    try:  # 投递可能失败（shell_url 缺失 / 网络不通 / API 异常）
        _submit(ev, config)  # 投递到 LLM 队列
    except Exception:  # 任意异常
        update_event(conn, event_id, status="failed")  # 投递失败标 failed（README 明确此语义）
        logger.exception(f"[desc_worker] 投递失败 id={event_id} → failed")  # 日志
        return  # 结束本条

    update_event(conn, event_id, status="done")  # 投递成功即 done（LLM 结果由 daemon 异步回填 diff_des）
    logger.info(f"[desc_worker] 投递成功 id={event_id} meta={ev['ref_meta']} mode={ev.get('mode') or 'plain'} → done")  # 日志


def _process_batch(conn, config: dict) -> int:
    """
    处理一批 descing 事件
    @param conn 数据库连接
    @param config config.json 的 post_llm 块
    @returns 本批实际处理条数
    """
    events = poll_events(conn, "descing", POLL_LIMIT)  # 按 st 正序取最早一批
    for ev in events:  # 逐条处理
        try:  # 单条失败不影响批次
            _process_event(conn, ev, config)  # 处理
        except Exception:  # 兜底
            logger.exception(f"[desc_worker] 处理异常 id={ev['id']}")  # 日志
    return len(events)  # 返回条数


def run(interval: float = POLL_INTERVAL) -> None:
    """
    常驻轮询循环：descing → 投递 LLM → done（由 main.py 以线程启动）
    @param interval 轮询间隔（秒）
    """
    init_db(_db_path)  # 幂等建表
    config = load_config()["post_llm"]  # 直接取 post_llm 块（enable / prompt / model）
    logger.info(f"[desc_worker] 启动，轮询间隔 {interval}s，post_llm.enable={config['enable']}")  # 日志
    while True:  # 常驻循环
        conn = get_conn(_db_path)  # 每轮新开连接
        try:  # 异常不退出循环
            with conn:  # 自动提交 / 回滚
                _process_batch(conn, config)  # 处理一批
        except Exception:  # 兜底
            logger.exception("[desc_worker] 轮询异常")  # 日志
        finally:  # 无论如何关闭
            conn.close()  # 用完即关，禁止长连接
        time.sleep(interval)  # 等待下一轮
