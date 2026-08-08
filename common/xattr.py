"""
给文件写入 Finder 注释（com.apple.metadata:kMDItemFinderComment），作为跨 inode 变化的持久标识
@command
# 列出所有 xattr

"""
import plistlib  # binary plist 序列化（Finder 注释需要的格式）
import subprocess  # 调用 macOS xattr 命令
import uuid  # 唯一 ID
from pathlib import Path  # 路径

MAGIC_KEY = "expy.edit.monitor"  # 所有都用这个key固定!


def update_file_mid(file_path: str, uid: str) -> None:
    """
    写入/覆盖文件的 MAGIC_KEY xattr 值为 uid
    @param file_path 文件绝对路径（调用方保证存在）
    @param uid 要写入的 uid 字符串
    """
    if not Path(file_path).exists():  # 前置校验：文件已消失（事件与处理之间的竞态），改为显式抛内置异常
        raise FileNotFoundError(f"文件不存在: {file_path}")  # 向上抛 FileNotFoundError，由 eslistener 精确捕获并降级
    subprocess.run(["xattr", "-w", MAGIC_KEY, uid, file_path], check=True, capture_output=True)  # 写入 xattr


def get_file_mid(file_path: str) -> str:
    """
    读取文件的 MAGIC_KEY xattr 值
    @param file_path 文件绝对路径
    @returns uid 字符串，文件不存在或无 xattr 则返回 ""
    """
    if not Path(file_path).exists():  # 文件不存在
        return ""  # 直接返回空
    r = subprocess.run(["xattr", "-p", MAGIC_KEY, file_path], capture_output=True, text=True)  # 读取 xattr
    return r.stdout.strip() if r.returncode == 0 else ""  # 成功返回 uid，失败返回空
