"""
eslogger 事件监听 — verify 管线 + deal_mid + MERGE/NEW 逻辑
作为三个平级线程之一运行：接收 eslogger 事件 → 过滤 → 写入 event 表

数据库连接生命周期：每次事件打开 → 用完即关，禁止长连接
"""

import os  # stat / path
import shutil  # 文件快照复制
import sys  # sys.path
import time  # 防抖时间戳
import uuid  # 新 mid 生成
from datetime import datetime  # 时间解析
from fnmatch import fnmatch  # glob 模式匹配
from pathlib import Path  # 路径

from loguru import logger  # 日志

# 项目根目录加入搜索路径
BASE_DIR = Path(__file__).resolve().parent.parent  # core/../ = 5_edit_monitor_magic/
sys.path.insert(0, str(BASE_DIR))

from common.utils import load_config  # 配置加载
from common.xattr import get_file_mid, update_file_mid  # xattr 魔法 ID 读写
from db.repository import (  # 数据库操作
    get_conn, init_db, insert_meta, get_meta_by_mid, update_meta, get_last_event, insert_event, update_event,
)

# ── 模块级状态（首次调用时懒初始化）──
_state = None  # {"keywords":[...], "kw_configs":[...], "noise_dirs":set(), ...}
_db_path = BASE_DIR / "data" / "file_events.db"  # 数据库文件路径
_tmp_dir = BASE_DIR / "data" / "tmp"  # 快照临时目录（verify 白名单：快照文件不许进入处理管线）

# ═══════════════════════════════════════════════════════════
# 初始化
# ═══════════════════════════════════════════════════════════


def _init_state() -> dict:
    """
    懒加载：加载配置 → 构建关键词映射 → 建表
    @returns 管线状态 dict
    """
    cfg = load_config()  # 读取 config.json

    # PART1: # ── 构建关键词列表（按 app_path 提取 .app 目录名）──
    def _kw(app_path: str) -> str:  # 提取 .app 目录名作为关键词
        i = app_path.find(".app/")  # 定位 .app/
        return app_path[:i].rsplit("/", 1)[-1] if i != -1 else app_path.rsplit("/", 1)[-1]  # 截目录名 / 取文件名

    # 过滤启用的应用 → 提取关键词 → 去重 → 按长度降序（长关键词优先匹配）
    seen = set()  # 去重集合
    keyword_entries = []  # [(keyword, app_cfg), ...]
    for a in cfg.get("apps", []):  # 遍历
        if not (a.get("enabled") and not a.get("is_delete") and a.get("app_path")):  # 跳过禁用/已删/无路径
            continue  # 跳过
        kw = _kw(a["app_path"])  # 提取关键词
        if kw not in seen:  # 未重复
            seen.add(kw)  # 标记
            keyword_entries.append((kw, a))  # 加入
    keyword_entries.sort(key=lambda x: len(x[0]), reverse=True)  # 长优先

    # PART2: # ── 建表（幂等，用完即关）──
    init_db(_db_path)  # init_db 内部 get_conn → with → close

    logger.debug(f"[eslistener] 初始化完成，{len(keyword_entries)} 个应用")  # 日志

    return {  # 返回管线状态
        "keywords": [k for k, _ in keyword_entries],  # 关键词列表
        "kw_configs": [c for _, c in keyword_entries],  # 对应配置列表
        "noise_dirs": set(cfg.get("global_noise_dir", [])),  # 全局噪声目录
        "noise_postfix": cfg.get("global_noise_postfix", []),  # 全局噪声后缀
        "merge_ms": cfg.get("merge_threshold_ms", 60000),  # 合并阈值（毫秒）
        "max_size_mb": cfg.get("max_file_size_mb", 5),  # 最大文件大小（MB）
        "seen": {},  # 防抖 dict: (proc_full, file_path) → timestamp
    }


# ═══════════════════════════════════════════════════════════
# Verify 管线（5 层过滤）
# ═══════════════════════════════════════════════════════════


def _verify(proc_full: str, file_path: str) -> tuple[dict | None, str | None]:
    """
    5 层过滤管线，全部通过才放行
    @param proc_full 进程完整路径
    @param file_path 被修改文件路径
    @returns (matched_app_cfg, display_name) 或 (None, None)
    """
    global _state
    if _state is None:  # 首次调用
        _state = _init_state()  # 懒加载

    # ── verify1: 应用匹配（关键词包含，忽略大小写）──
    matched_app = None  # 匹配到的应用配置
    proc_lower = proc_full.lower()  # 小写一次，避免每轮重复转换
    for i, keyword in enumerate(_state["keywords"]):  # 按长度降序遍历
        if keyword.lower() in proc_lower:  # 关键词在进程路径中出现
            matched_app = _state["kw_configs"][i]  # 取对应配置
            break  # 命中即停
    if not matched_app:  # 未命中任何应用
        return None, None  # 跳过

    # ── verify2: 全局噪声后缀过滤（~$*, *.sb-*, *~, *.db 等）──
    basename = os.path.basename(file_path)  # 文件名
    for pattern in _state["noise_postfix"]:  # 遍历噪声模式
        if fnmatch(basename, pattern):  # 命中噪声
            return None, None  # 跳过

    # ── verify3: 全局噪声目录过滤（.git, node_modules 等）──
    parts = file_path.split(os.sep)  # 按路径分隔符拆段
    for part in parts:  # 遍历每段
        if part in _state["noise_dirs"]:  # 命中噪声目录
            return None, None  # 跳过

    # ── verify4: per-app 过滤 ──
    # 后缀白名单
    allow_postfix = matched_app.get("allow_postfix", [])  # 该应用允许的后缀
    if allow_postfix:  # 有限制
        _, ext = os.path.splitext(file_path)  # 取扩展名
        if ext.lower() not in {p.lower() for p in allow_postfix}:  # 不在白名单
            return None, None  # 跳过
    # fileignore 规则
    fileignore = matched_app.get("fileignore", [])  # 该应用的忽略规则
    for pattern in fileignore:  # 遍历规则
        if fnmatch(basename, pattern):  # 文件名匹配
            return None, None  # 跳过
        if fnmatch(file_path, pattern):  # 全路径匹配
            return None, None  # 跳过
        if pattern.endswith("/*"):  # 目录模式
            dir_part = pattern[:-2]  # 去 /*
            if f"/{dir_part}/" in file_path or file_path.startswith(f"{dir_part}/"):  # 命中目录
                return None, None  # 跳过

    # ── verify5: 防抖（同一进程+文件 2s 内不重复处理）──
    key = (proc_full, file_path)  # 防抖 key
    now = time.time()  # 当前时间戳
    if key in _state["seen"] and now - _state["seen"][key] < 2:  # 2s 内已处理
        return None, None  # 跳过
    _state["seen"][key] = now  # 记录本次时间

    display_name = matched_app.get("displayName", proc_full)  # 显示名
    return matched_app, display_name  # 放行


# ═══════════════════════════════════════════════════════════
# deal_mid — 递归 mid 匹配逻辑（conn 由调用方传入，用完即关）
# ═══════════════════════════════════════════════════════════


def _deal_mid(conn, file_path: str, proc_name: str, ts_str: str, display_name: str) -> None:
    """
    递归处理 mid：按 README 流程图的 deal_mid 分支
    ┌─ mid = ""     → [首次] xattr.update → insert_meta → 递归
    ├─ mid√ fp×     → [重命名/复制] xattr.update → update_meta mid/fp → 递归
    └─ mid√ fp√     → [MERGE] 或 [NEW]

    @param conn 数据库连接（由 handle_file_event 打开，递归间复用）
    @param file_path 被修改文件路径
    @param proc_name 进程显示名
    @param ts_str 事件时间（ISO 格式）
    @param display_name 应用显示名
    """
    global _state
    assert _state is not None  # _init_state 必须已调用
    mid = get_file_mid(file_path)  # 读取文件的 xattr 魔法 ID
    meta = get_meta_by_mid(conn, mid) if mid else None  # 有 mid 才查 DB（避免无效查询）

    # ── 分支 1: mid 未命中 DB（空 或 xattr有但DB丢失）→ [首次] ──
    if not mid or meta is None:  # 从未记录过
        new_mid = str(uuid.uuid4())  # 生成新 ID
        update_file_mid(file_path, new_mid)  # 写入 xattr
        insert_meta(conn, new_mid, file_path, ts_str)  # 插入 meta 表
        logger.info(f"[eslistener] [首次] file={file_path} mid={new_mid}")  # 日志
        _deal_mid(conn, file_path, proc_name, ts_str, display_name)  # 递归：new_mid 必命中
        return  # 结束

    # ── 分支 2: mid√ file_path× → [重命名/复制/移动] ──
    if meta["file_path"] != file_path:  # mid 相同但路径不同
        new_mid = str(uuid.uuid4())  # 给当前文件分配新 mid
        update_file_mid(file_path, new_mid)  # 写入 xattr
        update_meta(conn, meta["id"], mid=new_mid, file_path=file_path)  # 更新 DB: mid + file_path
        logger.info(f"[eslistener] [更新mid] old_fp={meta['file_path']} new_fp={file_path} old_mid={mid} new_mid={new_mid}")  # 日志
        _deal_mid(conn, file_path, proc_name, ts_str, display_name)  # 递归：new_mid 必命中
        return  # 结束

    # ── 分支 3: mid√ file_path√ → [MERGE] 或 [NEW] ──
    meta_id = meta["id"]  # meta 主键

    # 获取文件大小
    try:  # stat 可能失败
        size = os.stat(file_path).st_size  # 字节
    except OSError:  # 文件已不存在
        logger.warning(f"[eslistener] stat 失败: {file_path}")  # 日志
        return  # 跳过

    # 检查文件大小上限
    max_size = _state["max_size_mb"] * 1024 * 1024  # 字节
    if size > max_size:  # 超大文件
        logger.trace(f"[eslistener] 跳过超大文件: {file_path} ({size // 1024 // 1024}MB)")  # 日志
        return  # 跳过

    # 查最近一条事件（用于判断 MERGE/NEW）
    last = get_last_event(conn, meta_id)  # 按 ref_meta 倒序取第一条

    # ── 判断合并 ──
    can_merge = False  # 是否合并
    prev_id = None  # 上一条 id
    merge_ms = _state["merge_ms"]  # 合并阈值
    if last:  # 存在上一条
        p_et = datetime.fromisoformat(last["et"])  # 上一条结束时间
        cur_st = datetime.fromisoformat(ts_str)  # 当前开始时间
        delta_ms = (cur_st - p_et).total_seconds() * 1000  # 时间差（毫秒）
        # 合并条件：同应用、未关闭（diff_des 为空）、时间差在阈值内
        if (last["proc_name"] == proc_name  # 同应用
                and not last.get("diff_des")  # 未关闭
                and delta_ms <= merge_ms):  # 未超阈值
            can_merge = True  # 可合并
            prev_id = last["id"]  # 记录上一条 id
            logger.trace(f"[eslistener] [MERGE] delta={delta_ms:.0f}ms<={merge_ms}ms file={file_path}")  # 日志

    if can_merge:  # ── [MERGE] ──
        assert prev_id is not None  # can_merge=True 保证 prev_id 已赋值
        update_event(conn, prev_id, et=ts_str, size_bytes=size)  # 只延长结束时间（file_path 只允许分支2 修改，此处严禁回填）
        logger.info(f"[MERGE] et={ts_str[:19]} size={size}B proc={proc_name} file={file_path}")  # 日志

    else:  # ── [NEW]：只插入 event，diff/content 全部留给 Worker A ──
        # 创建文件快照 → tmpfilepath
        _tmp_dir.mkdir(parents=True, exist_ok=True)  # 确保存在
        tmp_name = f"{uuid.uuid4().hex}_{os.path.basename(file_path)}"  # 唯一文件名
        tmp_path = _tmp_dir / tmp_name  # 完整路径
        try:  # 复制可能失败
            shutil.copy2(file_path, str(tmp_path))  # 复制文件, 不保留 mid!!!! 是对的!!!!
            os.chmod(str(tmp_path), 0o644)  # 放宽权限：root 复制的快照可能权限过严，其他用户进程（如 llm_agent）需可读 → 0644
        except OSError:  # 复制失败
            logger.warning(f"[eslistener] 快照复制失败: {file_path}")  # 日志
            tmp_path = None  # 不写 tmpfilepath
        status = "diffing" if tmp_path else "failed"  # 有快照待 Worker A 算 diff；无快照无法算 diff 直接失败

        # 插入新事件（显式 status，Worker A/B 按状态轮询）
        event_id = insert_event(  # 插入
            conn,
            ref_meta=meta_id,  # 外键
            file_path=file_path,  # 文件路径
            proc_name=display_name,  # 显示名
            st=ts_str,  # 开始时间
            et=ts_str,  # 结束时间（初始 = st）
            size_bytes=size,  # 文件大小
            tmpfilepath=str(tmp_path) if tmp_path else "",  # 快照路径（空字符串表示无快照）
            status=status,  # 显式状态：diffing / failed
        )
        logger.info(f"[NEW] id={event_id} meta={meta_id} proc={proc_name} size={size}B file={file_path} status={status}")  # 日志


# ═══════════════════════════════════════════════════════════
# 公开入口 — 每次事件打开连接 → 处理 → 关闭
# ═══════════════════════════════════════════════════════════


def handle_file_event(proc_full: str, file_path: str, ts_dt) -> None:
    """
    处理一次文件写入事件（由 main.py 事件循环调用）
    每次事件独立打开连接 → verify 管线 → deal_mid → MERGE/NEW → 关闭连接

    @param proc_full 进程完整路径（来自 eslogger）
    @param file_path 被修改文件路径
    @param ts_dt 本地时间 datetime 对象
    """
    # 跳过文件夹
    if os.path.isdir(file_path):  # 目录
        return  # 跳过

    # ── verify 管线（不需要数据库）──
    matched_app, display_name = _verify(proc_full, file_path)  # 5 层过滤
    if not matched_app or not display_name:  # 未通过
        return  # 跳过

    # ── 打开连接 → 处理 → 关闭 ──
    conn = get_conn(_db_path)  # 每次事件新开连接
    ts_str = ts_dt.isoformat()  # datetime → ISO 字符串
    try:  # 异常不阻塞事件循环
        with conn:  # 自动提交 / 回滚
            _deal_mid(conn, file_path, matched_app.get("displayName", proc_full), ts_str, display_name)  # 核心逻辑
    except FileNotFoundError:  # 文件消失竞态（xattr.py 向上抛的 FileNotFoundError），属正常跳过
        logger.warning(f"[eslistener] 文件不存在跳过 file={file_path} proc={proc_full}")  # 降级为 warning，不刷 ERROR 堆栈
    except Exception:  # 捕获所有异常
        logger.exception(f"[eslistener] deal_mid 异常 file={file_path} proc={proc_full}")  # 日志
    finally:  # 无论如何都要关闭
        conn.close()  # 用完即关，禁止长连接
