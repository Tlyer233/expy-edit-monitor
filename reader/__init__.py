from pathlib import Path  # 路径

from .planin import read as _plain_read  # 纯文本读取 + diff
from .with_image import read as _image_read  # 复杂文件（含图片）读取 + diff

# 纯文本后缀集合（直接 utf-8 读取 + unified diff）
_PLAIN_SUFFIXES = {  # 按需扩展
    "py",
    "js",
    "ts",
    "jsx",
    "tsx",
    "json",
    "yaml",
    "yml",
    "xml",
    "sh",
    "sql",
    "go",
    "rs",
    "java",
    "c",
    "cpp",
    "h",
    "rb",
    "php",
    "swift",
    "toml",
    "cfg",
    "ini",
    "env",
    "txt",
    "md",
    "html",
    "css",
}

# 复杂文件后缀集合（markitdown 提取，含图片）
# HACK 目前只能处理docx
_IMAGE_SUFFIXES = {  # 按需扩展
    "docx",
    "pptx",
    "xlsx",
    "xls",
    "pdf",
    "doc",
    "ppt",
}


def read_file(old_content: str, tmpfilepath: str) -> tuple[str, str, str]:
    """
    按后缀分发 Reader，返回 (diff, new_content, mode)
    @param old_content 旧内容（meta.content，plain 为纯文本；llm 为 骨架+DESC_SEP+描述json）
    @param tmpfilepath 快照文件绝对路径
    @returns (diff文本, new_content, mode) — mode: "plain" 纯文本 / "llm" 复杂文件（markitdown 提取）
    """
    assert Path(tmpfilepath).exists(), f"文件不存在: {tmpfilepath}"  # 前置校验
    suffix = Path(tmpfilepath).suffix.lstrip(".").lower()  # 获取后缀（无点，统一小写）
    if suffix in _PLAIN_SUFFIXES:  # 纯文本
        diff, new_content = _plain_read(old_content, tmpfilepath)  # 调纯文本 reader（内部算 unified diff）
        return diff, new_content, "plain"  # 返回 (diff, content, mode=plain)
    if suffix in _IMAGE_SUFFIXES:  # 复杂文件（含图片）
        diff, new_content = _image_read(old_content, tmpfilepath)  # 调含图 reader（内部 骨架diff+图片vision）
        return diff, new_content, "llm"  # 返回 (diff, content, mode=llm)
    raise NotImplementedError(f"不支持的后缀: .{suffix}")  # 未知后缀直接失败
