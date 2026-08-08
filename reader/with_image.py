"""
含有图片的文件
docx, pdf, ppt....
"""
import base64  # b64 解码 → 临时图片文件
import difflib  # 骨架 unified diff
import hashlib  # b64 → md5（判断图片是否同一张）
import json  # last_image_dict 序列化/反序列化
import os  # 删除临时文件
import re  # 图片 data URI 提取
import tempfile  # 临时图片文件（b64 → 文件喂 vision）
from pathlib import Path  # shell_url 文件路径
import io  # 字节缓冲
import pdfplumber  # PDF 逐页渲染

import requests  # POST /lms/task_sync

from markitdown import MarkItDown
from common.utils import load_config  # 配置加载（post_llm 块，复用 desc_worker 同款方式）

DESC_SEP = "\n@#IMG_DESC_JSON#@\n"  # meta.content中分割 old_content 和 last_image_dict 的界定符


def _vision(b64: str) -> str:
    """
    接收 base64，通过 7_lms_daemon 的 /lms/task_sync 同步获取图片描述
    b64 → 临时图片文件 → POST task_sync（内部投队列 + 轮询 done）→ 返回 result
    @param b64 图片 base64 内容
    @returns 图片描述文本（OCR + 描述）
    @raises requests.HTTPError 同步超时（504）/ LLM 失败（500）
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)  # 建临时图片文件
    tmp.write(base64.b64decode(b64))  # b64 解码写入
    tmp.close()  # 关闭句柄
    os.chmod(tmp.name, 0o644)  # 放宽权限：root 建的临时图默认 0600，llm_agent(其他用户进程) 读不到 → 0644 全员可读
    try:  # 确保异常时也删临时文件
        shell_url = Path("~/.expy/shell_url").expanduser().read_text().strip()  # 从壳子启动时写入的文件读取地址
        model = load_config()["post_llm"]["model"]  # 读 config.json 的 post_llm.model（与 desc_worker 同源，不再硬编码）
        resp = requests.post(  # 同步请求（daemon 内部投队列 + 轮询，done 了才返回响应）
            f"{shell_url}/lms/task_sync",  # 拼 daemon 的同步接口
            json={
                "content": tmp.name,
                "method": "vision",  # 图片路径 + vision
                "model": model,  # 模型（来自 config，LLM Worker 按此分组调度）
                "config": {
                    "contextLength": 3000
                }
            },  # 模型透传（LLM Worker 按此分组调度）
            timeout=130,  # 略大于 daemon 侧 120s 轮询超时
        )  # ← 阻塞等待，响应回来即结果
        resp.raise_for_status()  # 非 2xx 抛错（504=超时，500=LLM 失败）
        return resp.json()["result"]  # 返回描述文本
    finally:  # 清理
        os.unlink(tmp.name)  # 删临时图片文件（b64 不落库原则）


def _process_pdf(input_path: str, resolution: int = 150):
    """
    将 PDF 每一页渲染为 PNG 并转 base64，输出 markdown 图片语法
    适用于扫描/无文本层 PDF：markitdown 提不出文本时，用整页图片喂 vision

    @param input_path (str): PDF 文件路径，不存在直接 assert
    @param resolution (int): 渲染 DPI（150 平衡质量与体积，b64 约 1.1MB/页）
    @returns str: 每页一行的 `![](data:image/png;base64,xxx)` markdown
    """
    if not Path(input_path).exists():  # 前置校验：文件已消失（事件与处理之间的竞态），改为显式抛内置异常
        raise FileNotFoundError(f"文件不存在: {input_path}")

    lines = []  # 每页 md 行
    with pdfplumber.open(input_path) as pdf:  # 打开 PDF
        for page in pdf.pages:  # 逐页遍历
            img = page.to_image(resolution=resolution)  # 整页渲染为 PIL 图像
            buf = io.BytesIO()  # 字节缓冲
            img.original.save(buf, format="PNG")  # 保存 PNG
            b64 = base64.b64encode(buf.getvalue()).decode()  # 转 base64 字符串
            lines.append(f"![](data:image/png;base64,{b64})")  # markdown 图片语法
    content = "\n\n".join(lines)  # 每页之间空行拼接
    return content  # 返回 markdown


def read(old_content: str, tmpfilepath: str) -> tuple[str, str]:
    """
    处理docx,pdf,ppt等带有图片的内容

    TODO 这里要全量写清楚, 
    TODO doc与docx
    支持后缀: docx, 

    @param old_content (str): 该项event对应的meta表的 content 值: "内容#原内容中的image字典"
    @param tmpfilepath (str): 该项event的快照文件路径
    @returns tuple[str, str]: [0]:diff内容,写入该项event的diff字段; [1]:为new_content的内容,用于更新meta表的content;
    """
    md = MarkItDown()  # 转换器
    if Path(tmpfilepath).suffix.lower() == ".pdf":  # PDF 后缀：markitdown 提不出扫描 PDF 文本，改用逐页渲染
        content = _process_pdf(tmpfilepath)  # 每页 b64 md 图片
    else:  # 非 PDF 格式
        result = md.convert(tmpfilepath, keep_data_uris=True)  # markitdown 转换
        content = result.text_content  # markitdown 输出（图片为 data URI）
    print(content)
    # ── ② new_content: 所有图片替换为 [[IMG:md5]] 占位符 ──
    image_dict = {}  # 占位符 → b64（本次新提取的图片）

    def _img_repl(m: re.Match) -> str:  # 单个 markdown 图片语法 → 占位符
        b64 = m.group(1)  # 提取 base64 内容
        md5 = hashlib.md5(b64.encode("utf-8")).hexdigest()  # b64 → md5（同图必同 md5）
        ph = f"[[IMG:{md5}]]"  # 占位符格式（32位 hex，正则校验防碰撞）
        image_dict[ph] = b64  # 记录 占位符 → b64（供后续 vision）
        return ph  # 用占位符替换原文

    # 匹配完整 markdown 图片语法 ![alt](data:image/xxx;base64,xxx)，整体替换为占位符（否则会残留 ![]() 外层）
    new_content = re.sub(r'!\[[^\]]*\]\(data:image/[a-zA-Z0-9.+-]+;base64,([a-zA-Z0-9+/=]+)\)', _img_repl, content)  # 全部图片替换
    print(new_content)

    # ── ③ 从 old_content 解析旧图描述（"骨架 + DESC_SEP + 描述json"）──
    old_content, _sep, last_image_dict = old_content.partition(DESC_SEP)  # 拆 骨架 + 分隔标记 + 描述json
    last_image_dict = json.loads(last_image_dict) if _sep and last_image_dict.strip() else {}  # 旧图 占位符→描述（上次 vision 结果）

    # ── ④ 复用旧描述：image_dict(new) 中在 last_image_dict 已有 md5 的 → 直接复用旧描述；没有的 → 调 _vision(b64) 生成描述 ──
    for k, v in image_dict.items():  # 遍历本次所有图片（占位符→b64）
        if k in last_image_dict.keys():  # 旧描述已有此图
            image_dict[k] = last_image_dict[k]  # 复用旧描述（md5 相同无需 vision）
        else:  # 新图
            image_dict[k] = _vision(v)  # vision 生成描述，此时 image_dict 变为 占位符→描述

    # ── ⑥ or_diff: 骨架 unified diff（old 骨架 vs new 骨架）──
    or_diff = "".join(difflib.unified_diff(
        old_content.splitlines(keepends=True),  # 旧骨架行（③ 已拆出，不含描述 json）
        new_content.splitlines(keepends=True),  # 新骨架行（含 [[IMG:md5]] 占位符）
    ))  # 标准 unified diff 文本

    # ── ⑦ 占位符替换：or_diff 中所有 [[IMG:md5]] → [[IMG:md5]] DESC:<描述>（新增图用本次描述，删除图用旧描述兜底）──
    def _desc_repl(m: re.Match) -> str:  # 单个占位符 → 占位符 + DESC
        ph = m.group(0)  # 完整占位符 [[IMG:xxx]]
        desc = image_dict.get(ph) or last_image_dict.get(ph, "")  # 新图查本次描述，删除图查旧描述兜底
        if not desc:  # 无描述
            return ph  # 保持占位符原样
        desc = desc.replace("\r\n", "\\n").replace("\r", "\\n").replace("\n", "\\n")  # 转义所有换行变体为字面 \n（防 diff 行被拆断）
        return f"{ph} DESC:{desc}"  # 占位符 + 转义后的描述

    final_diff = re.sub(r'\[\[IMG:[0-9a-f]{32}\]\]', _desc_repl, or_diff)  # 全量替换占位符（32位 hex 精确匹配）

    # ── ⑧ 组装返回：diff 文本 + new_content 骨架#全量描述 json（供下次 ③ 解析）──
    new_meta = new_content + DESC_SEP + json.dumps(image_dict, ensure_ascii=False)  # 骨架 + 分隔符 + 描述字典（全量，供下次复用）
    return final_diff, new_meta  # (diff 给 event.diff, new_meta 给 meta.content)


if __name__ == "__main__":
    # temp_file = "/Volumes/SAMSUNG_1T/Documents/CodeBeach/Hermes_ASSISTANT/5_edit_monitor_magic/ref/mid_test_resource/docx/sample-simple.docx"
    temp_file = "/Volumes/SAMSUNG_1T/Documents/CodeBeach/Hermes_ASSISTANT/5_edit_monitor_magic/ref/mid_test_resource/docx/sample-simple_new.docx"

    read("", temp_file)
