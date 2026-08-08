"""db 包 — 数据库连接 + 表操作 + IDE 字段提示"""  # 连接管理 / Meta CRUD / Event CRUD / Worker 轮询 / 文件树

from .repository import (  # noqa: E402,F401  # re-export 供外部调用
    MetaFields,  # update_meta 的 IDE 字段提示
    EventFields,  # insert_event / update_event 的 IDE 字段提示
    get_conn,  # 连接工厂
    init_db,  # 建表
    insert_meta,  # Meta：插入
    get_meta_by_mid,  # Meta：按 mid 查询
    update_meta,  # Meta：通用更新
    get_last_event,  # Event：查最近一条
    insert_event,  # Event：通用插入
    update_event,  # Event：通用更新
    poll_events,  # Worker：按状态轮询
    get_discovered,  # 文件树：GROUP BY file_path
)

__all__ = [  # 显式声明导出，消除 IDE "未使用导入" 提示
    "MetaFields",
    "EventFields",
    "get_conn",
    "init_db",
    "insert_meta",
    "get_meta_by_mid",
    "update_meta",
    "get_last_event",
    "insert_event",
    "update_event",
    "poll_events",
    "get_discovered",
]
