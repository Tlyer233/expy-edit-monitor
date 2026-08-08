"""
Office 文件文本提取器 — 将 docx / xlsx / pptx 转为可 diff 的纯文本
Office Open XML 格式本质是 zip 压缩包，内部 XML 需要解析后提取文本内容
"""

import os  # 文件大小检查
import re  # XML 标签剥离
import zipfile  # Office 文件解压
from xml.etree import ElementTree as ET  # XML 解析

from loguru import logger  # 日志

# ─── 文件大小上限 ──────────────────────────────────────

MAX_OFFICE_SIZE = 10 * 1024 * 1024  # 10MB（office 文件通常较小）

# ─── 工具函数 ──────────────────────────────────────────


def _safe_read(filepath: str) -> str | None:
    """安全读取文件大小检查，超限返回 None"""
    try:
        if os.path.getsize(filepath) > MAX_OFFICE_SIZE:
            logger.debug("[OFFICE] {} 超过 {} MB，跳过", filepath, MAX_OFFICE_SIZE // (1024 * 1024))
            return None
        return filepath
    except OSError:
        return None


def _strip_ns(tag: str) -> str:
    """去掉 XML 命名空间前缀，如 {http://...}t → t"""
    return tag.split("}", 1)[-1] if "}" in tag else tag


# ─── DOCX ──────────────────────────────────────────────


def read_docx(filepath: str) -> str:
    """提取 .docx 文件的纯文本内容"""
    if not _safe_read(filepath):
        return "[DOCX 文件过大，跳过]"
    try:
        with zipfile.ZipFile(filepath, "r") as z:
            if "word/document.xml" not in z.namelist():
                return "[DOCX 无 document.xml]"
            xml_bytes = z.read("word/document.xml")
    except (zipfile.BadZipFile, OSError) as e:
        logger.warning("[DOCX] 读取失败 {}: {}", filepath, e)
        return "[DOCX 读取失败]"

    try:
        text = xml_bytes.decode("utf-8", errors="ignore")
    except Exception:
        return "[DOCX 解码失败]"

    # 提取 <w:t> 标签内的文本
    parts = re.findall(r"<w:t[^>]*>(.*?)</w:t>", text)
    lines = []
    for p in parts:
        p = p.strip()
        if p:
            lines.append(p)
    return "\n".join(lines) if lines else "[DOCX 无文本内容]"


# ─── XLSX ──────────────────────────────────────────────


def read_xlsx(filepath: str) -> str:
    """提取 .xlsx 文件的纯文本内容（单元格值按行列排列）"""
    if not _safe_read(filepath):
        return "[XLSX 文件过大，跳过]"
    try:
        with zipfile.ZipFile(filepath, "r") as z:
            names = z.namelist()
            # 1. 读取共享字符串表
            shared_strings = []
            if "xl/sharedStrings.xml" in names:
                ss_xml = z.read("xl/sharedStrings.xml").decode("utf-8", errors="ignore")
                ss_parts = re.findall(r"<t[^>]*>(.*?)</t>", ss_xml)
                shared_strings = [s.strip() for s in ss_parts]

            # 2. 找到所有 sheet 文件
            sheet_files = sorted([n for n in names if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")], key=lambda n: int(re.search(r"sheet(\d+)", n).group(1)))

            # 3. 解析每个 sheet 的单元格
            result_lines = []
            for sf in sheet_files:
                sheet_name = os.path.basename(sf).replace(".xml", "")
                sheet_xml = z.read(sf).decode("utf-8", errors="ignore")
                lines = _parse_sheet_xml(sheet_xml, shared_strings)
                if lines:
                    result_lines.append(f"--- {sheet_name} ---")
                    result_lines.extend(lines)
            return "\n".join(result_lines) if result_lines else "[XLSX 无文本内容]"
    except (zipfile.BadZipFile, OSError) as e:
        logger.warning("[XLSX] 读取失败 {}: {}", filepath, e)
        return "[XLSX 读取失败]"


def _parse_sheet_xml(xml_text: str, shared_strings: list[str]) -> list[str]:
    """解析 sheet XML，提取每行的单元格文本"""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    # 使用 iter() 递归查找所有 row 元素（避免 XPath 路径兼容问题）
    rows = list(root.iter(f"{{{ns}}}row"))
    if not rows:
        rows = list(root.iter("row"))  # 无命名空间回退

    lines = []
    for row in rows:
        cells = list(row.iter(f"{{{ns}}}c")) or list(row.iter("c"))
        row_values = []
        for cell in cells:
            ref = cell.get("r", "")
            cell_type = cell.get("t", "")
            value_el = cell.find(f"{{{ns}}}v")
            if value_el is None:
                value_el = cell.find("v")
            if value_el is not None and value_el.text:
                if cell_type == "s":
                    idx = int(value_el.text)
                    if 0 <= idx < len(shared_strings):
                        row_values.append((ref, shared_strings[idx]))
                elif cell_type == "b":
                    row_values.append((ref, "TRUE" if value_el.text == "1" else "FALSE"))
                else:
                    row_values.append((ref, value_el.text))

        if row_values:
            row_values.sort(key=lambda x: _col_sort_key(x[0]))
            lines.append(" | ".join(v for _, v in row_values))
    return lines


def _col_sort_key(ref: str) -> tuple[int, int]:
    """将单元格引用（如 A1、AB12）转为排序键 (row, col)"""
    match = re.match(r"([A-Z]+)(\d+)", ref)
    if not match:
        return (0, 0)
    col_letters, row_str = match.groups()
    col = 0
    for c in col_letters:
        col = col * 26 + (ord(c) - ord("A") + 1)
    return (int(row_str), col)


# ─── PPTX ──────────────────────────────────────────────


def read_pptx(filepath: str) -> str:
    """提取 .pptx 文件的纯文本内容（按幻灯片排列）"""
    if not _safe_read(filepath):
        return "[PPTX 文件过大，跳过]"
    try:
        with zipfile.ZipFile(filepath, "r") as z:
            names = z.namelist()
            # 找到所有幻灯片文件
            slide_files = sorted([n for n in names if n.startswith("ppt/slides/slide") and n.endswith(".xml")], key=lambda n: int(re.search(r"slide(\d+)", n).group(1)))

            result_lines = []
            for sf in slide_files:
                slide_num = re.search(r"slide(\d+)", sf).group(1)
                slide_xml = z.read(sf).decode("utf-8", errors="ignore")
                # 提取 <a:t> 标签内的文本
                text_parts = re.findall(r"<a:t[^>]*>(.*?)</a:t>", slide_xml)
                slide_lines = [t.strip() for t in text_parts if t.strip()]
                if slide_lines:
                    result_lines.append(f"--- 幻灯片 {slide_num} ---")
                    result_lines.extend(slide_lines)
            return "\n".join(result_lines) if result_lines else "[PPTX 无文本内容]"
    except (zipfile.BadZipFile, OSError) as e:
        logger.warning("[PPTX] 读取失败 {}: {}", filepath, e)
        return "[PPTX 读取失败]"


# ─── 对外接口 ──────────────────────────────────────────

# 支持的文件扩展名 → 读取函数映射
EXTRACTORS = {
    ".docx": read_docx,
    ".xlsx": read_xlsx,
    ".pptx": read_pptx,
}


def read_office(filepath: str) -> str | None:
    """根据扩展名自动选择提取器，返回纯文本；不支持则返回 None"""
    ext = os.path.splitext(filepath)[1].lower()
    extractor = EXTRACTORS.get(ext)
    if extractor:
        return extractor(filepath)
    return None
