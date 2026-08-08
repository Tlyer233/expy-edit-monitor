import json  # 解析/序列化 config.json
import re  # 正则折叠 JSON 数组
import sys  # sys.path
from pathlib import Path  # 路径

sys.path.insert(0, str(Path(__file__).parent.parent))  # 项目根目录加入搜索路径

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"  # 配置文件绝对路径


def load_config() -> dict:
    """
    加载根目录下的 config.json 文件
    @return dict: config 字典，文件不存在或损坏返回 {}
    """
    try:  # 捕获文件不存在 / JSON 损坏
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:  # 打开配置
            return json.load(f)  # 解析返回
    except (FileNotFoundError, json.JSONDecodeError):  # 文件不存在或格式错误
        return {}  # 返回空字典兜底


def save_config(data: dict) -> None:
    """
    写回 config.json（带数组折叠美化）
    @param data 完整 config 字典
    """
    text = json.dumps(data, ensure_ascii=False, indent=2)  # 序列化
    # 折叠所有数组为单行（allow_postfix / fileignore / global_noise_dir 等），减少行数
    text = re.sub(  # 匹配 "key": [ ... ] → 折叠为单行
        r'"([^"]+)": \[\s+(.*?)\s+\]',
        lambda m: '"{}": [{}]'.format(
            m.group(1),
            re.sub(r'\s+', ' ',
                   m.group(2).strip()),
        ),
        text,
        flags=re.DOTALL,
    )
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:  # 写回文件
        f.write(text + "\n")  # 末尾换行
