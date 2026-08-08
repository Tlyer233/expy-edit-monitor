import difflib  # unified diff 计算


def read(old_content: str, tmpfilepath: str) -> tuple[str, str]:
    """
    读取普通文本文件并计算 unified diff（与 with_image 签名对齐）
    @param old_content 旧内容（meta.content，纯文本）
    @param tmpfilepath 快照文件绝对路径（上游已验证存在）
    @returns tuple[str, str]: [0] diff 文本（unified diff）；[1] new_content（本次全文，写入 meta.content）
    """
    with open(tmpfilepath, "r", encoding="utf-8", errors="ignore") as f:  # 读快照文件
        new_content = f.read()  # 本次全文
    diff_text = "".join(difflib.unified_diff(  # 算 unified diff
        old_content.splitlines(keepends=True),  # 旧内容分行（保留换行符）
        new_content.splitlines(keepends=True),  # 新内容分行（保留换行符）
    ))  # 拼接为完整 diff 文本
    return diff_text, new_content  # (diff 给 event.diff, new_content 给 meta.content)
