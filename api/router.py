"""
5_edit_monitor_magic 业务 API — 配置管理 / 文件发现记录 / 本机 App 扫描
基于 xattr UUID 魔法标识方案的 REST API，挂载到壳子 FastAPI app
（L3：壳子 plugin_isolation 按插件隔离同名顶层包，插件侧恢复正常导入，无需 _load 样板）
"""

import glob  # 扫描 Applications
import os  # 路径/文件
from pathlib import Path  # 跨平台路径

# 插件根目录 = api/ 的父目录 = 5_edit_monitor_magic/
BASE_DIR = Path(__file__).resolve().parent.parent  # 项目根目录
# 无需 sys.path.insert：壳子 L3 隔离按"发起者归属"绝对路径解析插件自身顶层包（common/db/...）

# ── 正常导包（L3 验证：同名顶层包 common/db 由壳子按插件 shadow 隔离）──
import common.logger  # ① import pkg.sub → 绑定顶层名 common（副作用：初始化 loguru handlers）
import common.utils  # ② import pkg.sub → 验证子模块挂到 shadow common 包属性
from common import shared_logger  # ③ 独立 Logger 实例（壳子多插件隔离，不污染全局 loguru）
from common.utils import load_config, save_config  # ④ from pkg.sub import 属性（多属性）
from db.repository import get_conn, get_discovered as _db_get_discovered  # ⑤ from pkg.sub import 属性（db 包同样隔离 + 别名）

from fastapi import APIRouter, Body, HTTPException, Query  # FastAPI 路由 + 请求体 + 异常 + 查询参数

EVENT_DB_PATH = BASE_DIR / "data" / "file_events.db"  # 事件数据库（替代旧 discovered.db）

router = APIRouter(prefix="/api/edit_monitor", tags=["edit_monitor"])  # 业务路由前缀

# ── 配置读写 ──────────────────────────────────────────────


@router.get("/config")
async def get_config():
    """
    读取 config.json（委托给 common.utils.load_config）
    @returns config 完整对象
    """
    return load_config()  # 调用工具函数


@router.put("/config")
async def update_config(body: dict = Body(...)):
    """
    写回 config.json（委托给 common.utils.save_config）
    @param body 完整的新 config 对象
    @returns { success: bool }
    """
    if not body:  # 空请求体
        raise HTTPException(400, {"success": False, "error": "空请求体"})  # 400
    save_config(body)  # 调用工具函数（含数组折叠）
    return {"success": True}  # 成功


# ── 文件发现（discovered.db） ───────────────────────────────
# 去树化：树构建移交给前端 utils/buildTree.js（后端只管平铺数据）


@router.get("/discovered")
async def get_discovered(app_name: str = Query(...)):
    """
    查询指定应用的文件发现记录（平铺数据，树构建交给前端 buildTree.js）
    @param app_name 应用名
    @returns [{file_path, hit_count}, ...] 平铺列表
    """
    if not app_name:  # 缺参
        raise HTTPException(400, {"error": "缺少 app_name"})  # 400

    conn = get_conn(EVENT_DB_PATH)  # 打开事件数据库
    rows = _db_get_discovered(conn, app_name)  # GROUP BY file_path 查询
    conn.close()  # 用完即关

    return [  # 平铺返回（不再构建嵌套树）
        {
            "file_path": r["file_path"],
            "hit_count": r["hit_count"]
        }  # 字段对齐前端 buildTree 输入
        for r in rows  # 遍历查询结果
    ]


# ── 本机 App 扫描（添加应用弹层） ──────────────────────────────


@router.get("/mac_apps")
async def mac_apps():
    """
    扫描本机 /Applications 和 ~/Applications 下的 .app，用于 + 按钮选择
    @returns [{name, exec_path}, ...] 仅返回必需的 name + exec_path
    """
    # 扫描目录：/Applications + /System/Applications（macOS 系统应用，如 Preview/Safari）+ ~/Applications
    scan_dirs = ["/Applications", "/System/Applications", os.path.expanduser("~/Applications")]  # 扫描目录
    result = []  # 输出列表
    seen = set()  # 去重 exec_path

    for d in scan_dirs:  # 每个 Applications
        if not os.path.isdir(d):  # 不存在
            continue  # 跳过
        for app_bundle in glob.glob(os.path.join(d, "*.app")):  # 每个 .app
            if not os.path.isdir(app_bundle):  # 非目录
                continue  # 跳过
            name = os.path.basename(app_bundle).replace(".app", "")  # 显示名
            macos_dir = os.path.join(app_bundle, "Contents", "MacOS")  # MacOS 目录
            if not os.path.isdir(macos_dir):  # 无可执行目录
                continue  # 跳过

            # 查找可执行文件：先试同名（macOS 标准），没有再扫第一个
            exec_path = os.path.join(macos_dir, name)  # 同名候选
            if not (os.path.isfile(exec_path) and os.access(exec_path, os.X_OK)):  # 不是可执行
                exec_path = None  # 重置
                try:  # 扫 MacOS 目录
                    for n in os.listdir(macos_dir):  # 遍历
                        fp = os.path.join(macos_dir, n)  # 全路径
                        if os.path.isfile(fp) and os.access(fp, os.X_OK):  # 可执行
                            exec_path = fp  # 命中
                            break  # 取第一个
                except OSError:  # 读失败
                    continue  # 跳过
            if not exec_path:  # 没有可执行文件
                continue  # 跳过
            if exec_path in seen:  # 去重
                continue  # 跳过
            seen.add(exec_path)  # 标记

            result.append({"name": name, "exec_path": exec_path})  # 仅保留必需字段

    result.sort(key=lambda x: x["name"].lower())  # 按名称排序
    return result  # 返回列表
