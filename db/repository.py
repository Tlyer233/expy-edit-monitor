"""
SQLite 持久化层：meta（文件实体注册表）+ event（编辑事件流水）
连接管理遵循：WAL 模式 + busy_timeout 让 fillback 不被阻塞
调用方自行管理连接生命周期，写操作用 with conn: 自动提交
"""

import sqlite3  # 数据库
from pathlib import Path  # 路径
from typing import TypedDict  # **fields 的 IDE 字段类型
from typing_extensions import Unpack  # **fields 的 IDE 字段解包（跨 Python 版本兼容）

from loguru import logger  # 日志

# ── TypedDict：给 insert/update 的 **fields 提供 IDE 自动补全 ──


class MetaFields(TypedDict, total=False):  # total=False → 所有字段可选
    """meta 表可写字段 — 用于 update_meta 的 IDE 提示"""
    mid: str  # xattr 魔法 ID
    file_path: str  # 文件路径
    content: str  # 文件内容
    updated_at: str  # 更新时间


class EventFields(TypedDict, total=False):
    """event 表字段 — 用于 insert_event / update_event 的 IDE 提示"""
    ref_meta: int  # 外键 → meta.id
    file_path: str  # 事件发生时文件路径
    proc_name: str  # 触发进程名
    st: str  # 开始时间
    et: str  # 结束时间
    size_bytes: int  # 文件大小
    diff: str  # 差异文本
    diff_des: str  # 差异描述
    status: str  # 处理状态
    tmpfilepath: str  # 快照临时文件路径
    mode: str  # 可选值 llm 或者 plain


def get_conn(db_path: Path) -> sqlite3.Connection:
    """
    创建 WAL 模式连接，设置 busy_timeout 防 fillback 冲突
    @param db_path 数据库文件路径
    @returns sqlite3 连接（调用方负责 conn.close()）
    """
    conn = sqlite3.connect(str(db_path))  # 打开连接
    conn.execute("PRAGMA journal_mode=WAL")  # 读写不互斥
    conn.execute("PRAGMA busy_timeout=5000")  # 写冲突等待 5s 而非立即报错
    conn.row_factory = sqlite3.Row  # 查询结果可 dict() 转换
    return conn  # 返回给调用方


def init_db(db_path: Path) -> None:
    """
    建表 + 索引（幂等），执行完即关闭连接
    @param db_path 数据库文件路径
    """
    # 确保目录存在
    db_path.parent.mkdir(parents=True, exist_ok=True)  # 自动创建 data/ 目录

    conn = get_conn(db_path)  # 获取 WAL 连接
    with conn:  # 自动提交 / 回滚
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS meta (
                id         INTEGER PRIMARY KEY,        -- 自增主键
                mid        TEXT    UNIQUE NOT NULL,    -- xattr 魔法 ID，跨 inode 稳定
                file_path  TEXT    NOT NULL,           -- 当前文件路径
                content    TEXT,                       -- 最新文件内容（用于 diff）
                updated_at TEXT    NOT NULL            -- 最后更新时间
            );

            CREATE TABLE IF NOT EXISTS event (
                id          INTEGER PRIMARY KEY AUTOINCREMENT, -- 自增事件 ID
                ref_meta    INTEGER NOT NULL,                  -- 外键 → meta.id
                file_path   TEXT    NOT NULL,                  -- 事件发生时文件路径
                proc_name   TEXT    NOT NULL,                  -- 触发进程名（显示名）
                st          TEXT    NOT NULL,                  -- 事件开始时间
                et          TEXT    NOT NULL,                  -- 事件结束时间
                size_bytes  INTEGER,                           -- 文件大小（字节）
                diff        TEXT,                              -- 差异文本（Worker A 回填）
                diff_des    TEXT,                              -- 差异描述（Worker B 回填）
                status      TEXT    NOT NULL DEFAULT 'diffing', -- 处理状态：diffing→descing→done|failed
                tmpfilepath TEXT,                              -- 事件快照临时文件路径
                mode        TEXT,                              -- 可选值llm或者plain
                FOREIGN KEY (ref_meta) REFERENCES meta(id)     -- 关联 meta 表
            );

            CREATE INDEX IF NOT EXISTS idx_meta_file_path
                ON meta(file_path);                            -- mid√ file_path× 场景反查

            CREATE INDEX IF NOT EXISTS idx_meta_updated_at
                ON meta(updated_at);                           -- 按更新时间排序/过滤

            CREATE INDEX IF NOT EXISTS idx_event_ref_meta
                ON event(ref_meta);                            -- 按 meta 查所有事件

            CREATE INDEX IF NOT EXISTS idx_event_ref_meta_st
                ON event(ref_meta, st);                        -- 按文件 + 时间查最近事件

            CREATE INDEX IF NOT EXISTS idx_event_proc_name
                ON event(proc_name);                           -- get_discovered GROUP BY

            CREATE INDEX IF NOT EXISTS idx_event_st
                ON event(st);                                  -- 按开始时间范围查询

            CREATE INDEX IF NOT EXISTS idx_event_et
                ON event(et);                                  -- 按结束时间范围查询

            CREATE INDEX IF NOT EXISTS idx_event_status
                ON event(status);                              -- Worker 按状态轮询
        """)
    conn.close()  # 用完即关，不持有连接
    logger.info("数据库就绪: {}", db_path)  # 日志


# ═══════════════════════════════════════════════════════════
# Meta CRUD
# ═══════════════════════════════════════════════════════════


def insert_meta(conn: sqlite3.Connection, mid: str, file_path: str, updated_at: str) -> int:
    """
    插入新文件实体 → 返回 meta.id
    @param conn 数据库连接
    @param mid xattr 魔法 ID
    @param file_path 当前文件路径
    @param updated_at 更新时间
    @returns 新插入的 meta.id
    """
    conn.execute(  # 插入 meta
        "INSERT INTO meta (mid, file_path, content, updated_at) VALUES (?,?,?,?)",
        (mid, file_path, "", updated_at),  # content 初始为空
    )
    meta_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]  # 获取新 ID
    logger.trace("[META] 首次插入 mid={} file_path={} id={}", mid, file_path, meta_id)  # 日志
    return meta_id  # 返回自增 id


def get_meta_by_mid(conn: sqlite3.Connection, mid: str) -> dict | None:
    """
    按 mid 查找 meta 记录
    @param conn 数据库连接
    @param mid xattr 魔法 ID
    @returns meta 字典或 None
    """
    row = conn.execute(  # 按 mid 查
        "SELECT id, mid, file_path, content, updated_at FROM meta WHERE mid=?",
        (mid, ),
    ).fetchone()
    return dict(row) if row else None  # 有结果转 dict，无结果返回 None


def get_meta_by_id(conn: sqlite3.Connection, meta_id: int) -> dict | None:
    """
    按 meta 主键 id 查记录（Worker A 取 oldContent 用）
    @param conn 数据库连接
    @param meta_id meta.id
    @returns meta 字典或 None
    """
    row = conn.execute(  # 按 id 查
        "SELECT id, mid, file_path, content, updated_at FROM meta WHERE id=?",
        (meta_id, ),
    ).fetchone()
    return dict(row) if row else None  # 有结果转 dict，无返回 None


def update_meta(conn: sqlite3.Connection, meta_id: int, **fields: Unpack[MetaFields]) -> None:
    """
    更新 meta 表中指定 id 的任意字段
    @param conn 数据库连接
    @param meta_id meta 主键 (不是mid!!!)
    @param **fields 要更新的字段键值对
    """
    if not fields:  # 无字段更新
        return  # 空操作
    set_clause = ", ".join(f"{k}=?" for k in fields)  # 构建 SET k1=?, k2=?, ...
    values = list(fields.values()) + [meta_id]  # 参数：字段值 + WHERE id
    conn.execute(f"UPDATE meta SET {set_clause} WHERE id=?", values)  # 执行更新


# ═══════════════════════════════════════════════════════════
# Event CRUD
# ═══════════════════════════════════════════════════════════


def get_last_event(conn: sqlite3.Connection, meta_id: int) -> dict | None:
    """
    按 ref_meta 查最近一条事件（用于判断 MERGE/NEW）
    @param conn 数据库连接
    @param meta_id meta.id
    @returns 最近一条 event 字典或 None
    """
    row = conn.execute(  # 按 ref_meta 倒序取第一条
        "SELECT * FROM event WHERE ref_meta=? ORDER BY st DESC LIMIT 1",
        (meta_id, ),
    ).fetchone()
    if not row:
        logger.error(f"注意! 请查看{meta_id},该项的event为空")
    return dict(row) if row else None  # 有结果转 dict，无返回 None


def insert_event(conn: sqlite3.Connection, **fields: Unpack[EventFields]) -> int:
    """
    插入新事件 → 返回 event.id，status 默认 'diffing'
    @param conn 数据库连接
    @param **fields 事件字段键值对（ref_meta, file_path, proc_name, st, et, ...）
    @returns 新插入的 event.id
    """
    if "status" not in fields:  # 未指定状态
        fields["status"] = "diffing"  # 默认 diffing
    columns = ", ".join(fields.keys())  # 列名列表
    placeholders = ", ".join("?" for _ in fields)  # 占位符
    values = list(fields.values())  # 值列表
    conn.execute(  # 插入
        f"INSERT INTO event ({columns}) VALUES ({placeholders})",
        values,
    )
    event_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]  # 获取新 ID
    logger.debug(  # 日志
        "[EVENT] 新增 id={} ref_meta={} proc={} st={}",
        event_id,
        fields.get("ref_meta"),
        fields.get("proc_name"),
        fields.get("st"),
    )
    return event_id  # 返回自增 id


def update_event(conn: sqlite3.Connection, event_id: int, **fields: Unpack[EventFields]) -> None:
    """
    更新 event 表中指定 id 的任意字段（diff / diff_des / status 等）
    @param conn 数据库连接
    @param event_id event 主键
    @param **fields 要更新的字段键值对
    """
    if not fields:  # 无字段更新
        return  # 空操作
    set_clause = ", ".join(f"{k}=?" for k in fields)  # 构建 SET k1=?, k2=?, ...
    values = list(fields.values()) + [event_id]  # 参数：字段值 + WHERE id
    conn.execute(f"UPDATE event SET {set_clause} WHERE id=?", values)  # 执行更新


# ═══════════════════════════════════════════════════════════
# Worker 轮询
# ═══════════════════════════════════════════════════════════


def poll_events(conn: sqlite3.Connection, status: str, limit: int = 10) -> list[dict]:
    """
    Worker 按 status 轮询待处理事件
    @param conn 数据库连接
    @param status 处理状态（'diffing' 或 'descing'）
    @param limit 每次最多取几条
    @returns 事件字典列表
    """
    rows = conn.execute(  # 按 st 正序取最早的事件先处理
        "SELECT * FROM event WHERE status=? ORDER BY st ASC LIMIT ?",
        (status, limit),
    ).fetchall()
    return [dict(r) for r in rows]  # Row → dict 列表


# ═══════════════════════════════════════════════════════════
# 文件树（替代旧 discovered_files 表）
# ═══════════════════════════════════════════════════════════


def get_discovered(conn: sqlite3.Connection, proc_name: str) -> list[sqlite3.Row]:
    """
    从 event 表 GROUP BY file_path 获取发现文件列表（替代旧 discovered_files 表）
    @param conn 数据库连接
    @param proc_name 进程显示名
    @returns [(file_path, hit_count), ...] 按命中次数降序
    """
    rows = conn.execute(  # 按进程名聚合并计数
        "SELECT file_path, COUNT(*) AS hit_count "
        "FROM event WHERE proc_name=? "
        "GROUP BY file_path ORDER BY hit_count DESC",
        (proc_name, ),
    ).fetchall()
    return rows  # 返回 Row 列表，调用方自行 dict() 或 .keys()
