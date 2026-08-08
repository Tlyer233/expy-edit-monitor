# 文件编辑监控 (edit\_monitor)

**层级**：![BASIC](https://img.shields.io/badge/-BASIC-3088d1)![✓](https://img.shields.io/badge/-%E2%9C%93-2ea44f)─── ![AGENT](https://img.shields.io/badge/-AGENT-8250df) <======= ![WorkFlow](https://img.shields.io/badge/-WorkFlow-d97706) =======> ![INTERACT](https://img.shields.io/badge/-INTERACT-2ea44f)

**定位**：[![daemon](https://img.shields.io/badge/daemon-%E2%9C%93-2ea44f)](#一-daemon) [![api](https://img.shields.io/badge/api-%E2%9C%93-2ea44f)](#二-api) [![db](https://img.shields.io/badge/db-%E2%9C%93-2ea44f)](#三-db) [![ui](https://img.shields.io/badge/ui-%E2%9C%93-2ea44f)](#四-ui) [![skills](https://img.shields.io/badge/skills-%E2%9C%93-2ea44f)](#五-skill)

> macOS 内核级文件编辑监控插件 —— 记录每次保存、算 diff、生成 LLM 修改摘要，回答「某天我到底改了什么」。

1. 基于 macOS 内置的 `eslogger`（Endurance Security 事件流，10.15+ 内核级文件事件）内核级事件流

2. **按应用粒度勾选监控**（PyCharm、WPS Office 等），对命中应用的保存行为做快照、diff、LLM 摘要，持久化到本地 SQLite，并提供 REST API 与 Web 配置界面。

3. 内容解析**目前**支持普通文本（unified diff）与 Office/PDF 等含图文档（markitdown + 视觉模型），

4. reader 按文件类型自由扩展（PS 导出文件、PR 视频工程等, 后续会进一步支持），拓展性极强。
5. 是旧版 `5_edit_monitor`（inode追踪）的升级版，核心改进为 **xattr 持久化身份标识**(魔法标识)，解决 Office / Typora 等应用原子保存（先 create 临时文件再 rename）导致 inode 变化、文件追踪链断裂的问题。

## 一. Daemon ![✓](https://img.shields.io/badge/-%E2%9C%93-2ea44f)

#### Q1: 是否需要sudo?

需要! 因为mac的eslogger需要

#### Q2: 为什么需要常驻? 哪里需要常驻?
1. eslogger 是流式事件源，不是查询接口 —— 必须进程活着持续接收 write/rename/create/clone 事件，事件发生当下没人听就 永远丢失
2. 处理是异步接力 —— 事件不能同步算完 diff（含图修改要 本地模型 llm 来 vision，），必须入队 db 后由 Worker 轮询驱动，进程不在状态机就停摆
3. 文件快照时机依赖进程存活 —— 修改事件触发瞬间要临时记录文件快照(后面处理完成会删除)，错过即断链



## 二. API ![✓](https://img.shields.io/badge/-%E2%9C%93-2ea44f)

#### 1. GET /api/edit_monitor/discovered

**① 定位**：![前端UI ✓](https://img.shields.io/badge/前端UI-%E2%9C%93-2ea44f) ![其他插件 ✗](https://img.shields.io/badge/其他插件-%E2%9C%97-red) ![能力暴露 ✗](https://img.shields.io/badge/能力暴露-%E2%9C%97-red)

**② Method**：![GET](https://img.shields.io/badge/-GET-61affe)

**③ Parameters**

| 参数       | 位置  | 必填 | 类型   | 说明                     |
| ---------- | ----- | ---- | ------ | ------------------------ |
| `app_name` | query | 是   | string | 应用显示名，如 `PyCharm` |

**④ Response**

| 状态 | 参数      | 类型   | 说明 |
| ----- | --------- | ------ | ---- |
| ![200](https://img.shields.io/badge/-200-2ea44f) | file_path | string | 文件绝对路径 |
|       | hit_count | int    | 该文件被命中修改的次数 |
| ![400](https://img.shields.io/badge/-400-red) | error     | string | 错误原因，如缺少 app_name |

**⑤ 示例（curl）**

```bash
# 请求：GET /api/edit_monitor/discovered?app_name=PyCharm
# 参数解释：
#   app_name: 应用显示名（必填），如 PyCharm，仅返回该应用的修改记录
curl "http://127.0.0.1:9723/api/edit_monitor/discovered?app_name=PyCharm"

# 成功(200):
#   [{"file_path": "/Users/you/proj/a.py", "hit_count": 12},
#    {"file_path": "/Users/you/proj/b.py", "hit_count": 3}]
# 缺参(400):
#   {"error": "缺少 app_name"}
```

**⑥ 备注**：返回平铺数据，树结构由前端构建；`hit_count` = 该文件被命中修改的次数。

---

#### 2. GET /api/edit_monitor/config

**① 定位**：![前端UI ✓](https://img.shields.io/badge/前端UI-%E2%9C%93-2ea44f) ![其他插件 ✗](https://img.shields.io/badge/其他插件-%E2%9C%97-red) ![能力暴露 ✗](https://img.shields.io/badge/能力暴露-%E2%9C%97-red)

**② Method**：![GET](https://img.shields.io/badge/-GET-61affe)

**③ Parameters**

无

**④ Response**

| 状态 | 参数                | 类型   | 说明 |
| ----- | ------------------- | ------ | ---- |
| ![200](https://img.shields.io/badge/-200-2ea44f) | apps               | array  | 监控应用白名单 |
|       | global_noise_dir   | array  | 全局噪声目录 |
|       | global_noise_postfix | array | 全局噪声后缀 |
|       | timezone_offset    | int    | 时区偏移（默认 8） |
|       | merge_threshold_ms | int    | MERGE 合并时间窗（毫秒） |
|       | max_file_size_mb   | int    | 快照大小上限（MB） |
|       | post_llm           | object | LLM 摘要配置 |

**⑤ 示例（curl）**

```bash
# 请求：GET /api/edit_monitor/config
# 无参数
curl "http://127.0.0.1:9723/api/edit_monitor/config"

# 成功(200): 完整 config 对象
#   {"apps": [{"allow_postfix": [".py"], "app_path": "...", "displayName": "PyCharm", ...}],
#    "global_noise_dir": [".git", "node_modules"], ...}
```

**⑥ 备注**：返回 `config.json` 完整配置，前端 UI 加载用。

---

#### 3. PUT /api/edit_monitor/config

**① 定位**：![前端UI ✓](https://img.shields.io/badge/前端UI-%E2%9C%93-2ea44f) ![其他插件 ✗](https://img.shields.io/badge/其他插件-%E2%9C%97-red) ![能力暴露 ✗](https://img.shields.io/badge/能力暴露-%E2%9C%97-red)

**② Method**：![PUT](https://img.shields.io/badge/-PUT-fca130)

**③ Parameters**

| 参数 | 位置 | 必填 | 类型   | 说明 |
| ----- | ---- | ---- | ------ | ---- |
| body  | body | 是   | object | 完整的新 config 对象（结构同 GET /config 返回） |

**④ Response**

| 状态 | 参数    | 类型   | 说明 |
| ----- | ------- | ------ | ---- |
| ![200](https://img.shields.io/badge/-200-2ea44f) | success | bool   | true |
| ![400](https://img.shields.io/badge/-400-red)   | success | bool   | false |
|       | error   | string | 错误原因（空请求体） |

**⑤ 示例（curl）**

```bash
# 请求：PUT /api/edit_monitor/config
# 参数解释：
#   body: 完整新 config 对象（JSON），需包含 apps/global_noise_dir 等全部字段
curl -X PUT "http://127.0.0.1:9723/api/edit_monitor/config" \
  -H "Content-Type: application/json" \
  -d '{"apps": [], "global_noise_dir": [".git"], "timezone_offset": 8, "merge_threshold_ms": 6000, "max_file_size_mb": 5, "post_llm": {"enable": true, "model": "qwen/qwen3-vl-4b@q4_k_m"}}'

# 成功(200): {"success": true}
# 空体(400): {"success": false, "error": "空请求体"}
```

**⑥ 备注**：写回 `config.json`，保存后 UI 会触发 daemon 重启生效。

---

#### 4. GET /api/edit_monitor/mac_apps

**① 定位**：![前端UI ✓](https://img.shields.io/badge/前端UI-%E2%9C%93-2ea44f) ![其他插件 ✗](https://img.shields.io/badge/其他插件-%E2%9C%97-red) ![能力暴露 ✗](https://img.shields.io/badge/能力暴露-%E2%9C%97-red)

**② Method**：![GET](https://img.shields.io/badge/-GET-61affe)

**③ Parameters**

无

**④ Response**

| 状态 | 参数      | 类型   | 说明 |
| ----- | --------- | ------ | ---- |
| ![200](https://img.shields.io/badge/-200-2ea44f) | name      | string | App 显示名 |
|       | exec_path | string | 可执行文件完整路径 |

**⑤ 示例（curl）**

```bash
# 请求：GET /api/edit_monitor/mac_apps
# 无参数
curl "http://127.0.0.1:9723/api/edit_monitor/mac_apps"

# 成功(200):
#   [{"name": "PyCharm", "exec_path": "/Applications/PyCharm.app/Contents/MacOS/pycharm"},
#    {"name": "TextEdit", "exec_path": "/System/Applications/TextEdit.app/Contents/MacOS/TextEdit"}, ...]
```

**⑥ 备注**：扫描 `/Applications`、`/System/Applications`、`~/Applications` 下的 `.app`，按名称排序、按 exec_path 去重。

## 三. DB ![✓](https://img.shields.io/badge/-%E2%9C%93-2ea44f)

- `file_events.db` 包含两张表：

```sql
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
```

#### 重要字段解析

- 整体分析：meta 表存每个文件的元信息（一行一个文件）；该文件的所有编辑记录在 event 表，通过 `ref_meta` 关联
- `event.status`（状态机，由两个 Worker 接力驱动）：
  - ① `diffing`：已入队，缺 `diff` 字段，Worker A — Diff Worker 抓取此状态
  - ② `descing`：已有 `diff`，缺 `diff_des` 字段，Worker B — Desc Worker 抓取此状态
  - ③ `done`：`diff` 与 `diff_des` 均处理完毕
  - ④ `failed`：任一阶段失败即转为该状态
- `event.diff`：`difflib` 生成的 unified diff（`diff -u file1 file2` 格式）；含图片内容需本地 LLM 参与
- `event.diff_des`：对 `event.diff` 的自然语言描述（由本地 LLM 生成）
- `meta.mid`：所有被监控文件都带有 `expy.edit.monitor: <uuid.uuid4()>` 的 xattr 属性

## 四. UI ![✓](https://img.shields.io/badge/-%E2%9C%93-2ea44f)

React 19 + Vite 6 + Tailwind CSS v4 + Zustand 5（`ui/package.json`）。

由宿主以 **iframe** 加载（`manifest.json:12` `ui.entry=index.html`），支持明暗双主题（CSS 变量 + `html.dark` 切换）。

主要功能：

- **应用侧栏**：已配置应用列表，`enabled` 开关一键启停，支持添加 / 移除本机 App
- **主面板**：应用详情 + 「文件后缀 / 忽略规则」标签编辑器
- **文件树**：某应用发现过的文件树（前端 `buildTree.js` 自建），支持忽略规则过滤与刷新
- **弹层**：忽略规则候选、本机 App 列表（`mac_apps` 接口扫描）、新应用后缀多选

***

## 五. SKILL ![✓](https://img.shields.io/badge/-%E2%9C%93-2ea44f)

**`skills/file_edit_query`**（351 行 SKILL.md，`manifest.json:27-29`）

面向 Agent（Hermes 等）的查询 skill：直接读 `data/file_events.db`，回答「某天做了什么 / 哪些文件被修改过」，并从原始编辑数据提炼「主任务 + 子任务」的当日工作总结。

- **两阶段流程**：Phase 1 查询（8 个 SQL 模板：按天 / 按应用 / 去重文件 / 项目分布 / 迭代追踪等）→ Phase 2 分析（观察 → 过滤噪声 → 归并主任务 → 提炼子任务 → 反问验证）
- **两种输出**：标准表格模式（主任务/分组/投入时段 + 子任务表）与快速语音模式（口语化总结）
- 内置噪声过滤速查表、合并规则、Pitfalls（如 `diff_des` 可能为 NULL、`mode=llm` 的 diff 含 `[[IMG]] DESC:` 占位符）



## 七、整体架构

```
main.py               Daemon 入口：root 校验 → 起 Worker A/B 线程 → 起 eslogger → 主事件循环
core/eslistener.py    5 层 verify 过滤 + deal_mid 身份判定 + MERGE/NEW（主线程调用）
core/diff_worker.py   Worker A：轮询 status='diffing' → 算 diff → 'descing'
core/desc_worker.py   Worker B：轮询 status='descing' → 投递 LLM → 'done'
db/repository.py      SQLite：meta + event 两表 CRUD + 轮询/聚合查询
reader/               planin.py（纯文本 unified diff）/ with_image.py（markitdown + vision）
common/               logger / utils（config 读写）/ xattr（mid 读写）
api/router.py         FastAPI 路由（config / discovered / mac_apps）
ui/                   React 配置界面（iframe）
skills/file_edit_query  Agent 查询 skill
```

**端到端数据流**（三线程通过 `event.status` 状态机接力）：

```
eslogger 内核事件(JSON)
  → main.py 解析（_extract_path、UTC→本地时间）
  → eslistener.handle_file_event
      ① 跳过目录  ② 5 层 verify：应用匹配→全局噪声→per-app 后缀/忽略→2s 防抖
      ③ deal_mid 身份判定（首次 / 重命名复制 / MERGE·NEW）
      ④ 快照 copy2 到 data/tmp/ → insert_event(status='diffing')
  → diff_worker 每 1s 轮询：读快照 → 算 diff → 回填 diff/mode → 'descing'（删快照）
       · plain: difflib.unified_diff 新旧全文
       · llm: markitdown 提取 → 图片 [[IMG:md5]] 占位 → vision 描述 → 骨架 diff
  → desc_worker 每 1s 轮询：按 mode 选 prompt → POST /lms/task → 'done'
  → 7_lms_daemon 异步把摘要写回 event.diff_des
  → UI / API / Skill 侧查询
```

***

## 八、实现思路 (Key Design)

1. **xattr 魔法 ID 身份追踪**（核心）：`common/xattr.py` 用固定 key `expy.edit.monitor` 读写 xattr。Finder 注释 xattr 在「Office 原子保存 / 重命名 / 移动 / 复制」时均保留，可作为跨 inode 的稳定身份。`deal_mid` 三分支：首次→生成新 UUID；重命名/复制→分配新 mid（副本获得独立身份，天然去重）；正常→判 MERGE / NEW。
2. **MERGE / NEW 判定**：同应用 + 上条事件 `diff_des` 未关闭 + 时间差 ≤ `merge_threshold_ms`（默认 6000ms）→ MERGE 只延长 `et`（禁止回填 file\_path）；否则 NEW 建快照。
3. **快照机制**：事件发生时立即 `shutil.copy2` 到 `data/tmp/` 并 `chmod 0644`（root 复制的快照需放行其他用户进程读取），Worker A 算完即删。大小上限 5MB。
4. **含图文档（Office/PDF）**：markitdown 转换 + 图片 `[[IMG:md5]]` 占位符（md5 判同图），`meta.content` 存「骨架 + 图片描述 json」，同 md5 复用旧描述、新图才调 vision（同步 130s 超时）。
5. **防抖**：对 `(进程, 文件路径)` 组合 2 秒内存级去重，避免一次保存触发多条事件。
6. **时区**：eslogger 输出 UTC，统一加 `timezone_offset`（默认 8）转本地存储。
7. **日志双轨**：daemon 侧全局 loguru（`log/` 按天滚动 30 天），api 侧独立 logger 实例，避免壳子多插件间 loguru 污染。

***

<br />

***

## 配置 (config.json)

```json
{
  // 监控应用白名单：eslogger 事件按 app_path 提取的 .app 关键词匹配到这里的某个应用
  "apps": [ 
    {
      // 允许监控的后缀白名单（忽略大小写匹配，不在列表内的文件直接跳过；空数组=不限制）
      "allow_postfix": [ ".py", ".js", ".ts", ".json", ".md", ".html", ".css", ".yaml", ".yml", ".xml", ".sh", ".sql", ".toml", ".cfg", ".ini", ".env" ],
      // 应用可执行文件完整路径，用于提取 .app 目录名作为事件匹配关键词（eslistener.py:47-49）
      "app_path": "/Applications/PyCharm.app/Contents/MacOS/pycharm",
      // 前端 UI 显示名
      "displayName": "PyCharm",
      // 启用开关：false 时该应用不参与事件匹配
      "enabled": true,
      // 该应用专属忽略规则（fnmatch 匹配文件名，命中即跳过；其余应用字段含义同上）
      "fileignore": [ ".idea/*", "__pycache__/*", "/Users/xi/Library/Logs/JetBrains/*", "/Users/xi/Library/Application Support/JetBrains/*", "/Users/xi/Library/Caches/JetBrains/*", "/Users/xi/.Trash/*", "/Users/xi/.local/state/opencode/*", "/Users/xi/.cache/opencode/*" ],
      // 假删标记：true 视为已移除该应用，不参与匹配（保留配置便于以后恢复）
      "is_delete": false
    },
    {
      "allow_postfix": [ ".docx", ".xlsx", ".pptx", ".doc", ".xls", ".ppt", ".pdf" ],
      "app_path": "/Applications/wpsoffice.app/Contents/MacOS/wpsoffice",
      "displayName": "WPS Office",
      "enabled": true,
      "fileignore": [ ".~*" ],
      "is_delete": false
    },],
  
  // 全局噪声目录：文件路径命中任一目录即忽略（.git / __pycache__ / node_modules 等）
  "global_noise_dir": [ ".git", "__pycache__", ".DS_Store", "node_modules", ".venv", "venv", "dist", "build", ".idea" ],
  
  // 全局噪声后缀（glob 模式）：命中即忽略（Office 临时锁文件、数据库等）
  "global_noise_postfix": [ "~$*", "*.sb-*", "*~", "*.db" ],
  
  // 时区偏移：eslogger 输出 UTC，加该值转为本地时间存储
  "timezone_offset": 8,
  
  // MERGE 合并时间窗（毫秒）：同一应用同一文件，上条事件未关闭且间隔 ≤ 该值时合并为一条事件
  "merge_threshold_ms": 6000,
  
  // 快照大小上限（MB）：文件超过该大小直接跳过不记录
  "max_file_size_mb": 5,
  
  // LLM 摘要投递配置（desc_worker 使用）
  "post_llm": {
    // 总开关：false 时跳过 LLM 投递，diff 生成后直接置为 done
    "enable": true,
    // 纯文本（plain）diff 的摘要 prompt
    "plain_diff_prompt": "你是一个资深代码审查员。以下是一个 unified diff，请用一句话总结用户对代码做了哪些修改，只讲做了什么、不讲为什么。如果修改了多个地方，用分号分隔。",
    // 含图文档（llm）diff 的摘要 prompt：提示模型忽略 [IMG] 占位符后的 DESC 自动描述
    "llm_diff_prompt": "你是一个资深diff审查员。diff中 [IMG] 图片占位符后面的 DESC: 是系统对该图片的自动描述，不是用户编辑的内容。请用一句话总结用户对文档做了什么修改，只讲做了什么、不讲为什么。如果修改了多个地方，用分号分隔。",
    // 视觉/摘要使用的本地模型
    "model": "qwen/qwen3-vl-4b@q4_k_m"
  }
}
```

***

## 目录结构

```
5_edit_monitor_magic/
├── main.py               # Daemon 入口（root 校验 → Worker A/B → eslogger → 事件循环）
├── manifest.json         # 插件元数据（宿主识别唯一依据）
├── config.json           # 监控配置
├── env_check.py          # 部署前环境检测
├── api/router.py         # FastAPI 路由（config / discovered / mac_apps）
├── common/               # logger / utils / xattr / office_reader
├── core/                 # eslistener（verify+deal_mid）/ diff_worker / desc_worker
├── db/repository.py      # SQLite meta + event 两表
├── reader/               # planin（纯文本 diff）/ with_image（markitdown+vision）
├── skills/file_edit_query/SKILL.md   # Agent 查询 skill
├── ui/                   # React 配置界面（构建产物经宿主 iframe 加载）
├── data/                 # file_events.db + 事件快照 tmp/
└── log/                  # 按天滚动日志
```

## License

MIT



## 架构

```
┌────────────────────┐ ┌───────────────────┐ ┌───────────────────────────────────────────────────────────────┐ ┌────────────────────┐
│ Daemon             │ │ HERMES AGENT      │ │Normal                                                         │ │ Mincorsoft TO DO   │
│ 后台常驻插件,适用于   │ │  - chat(api)      │ │              1.clean_input             2. suit_for_talk       │ │  - todo_operat     │
│ 需要实时获取最新数据  │ │                   │ │ HERMES ◄──────────────────────────────────────────────── SIRI │ │                    │
│ 的插件  │ │ OPENCLAW          │ │                                                               │ │ SIRI               │
│ 2.edit_monitor     │ │  - chat(api)      │ │                                                               │ │                    │
│   - edit_query     │ │                   │ │                                                               │ │                    │
│ 3.siri_daemon      │ │ CODEX             │ │                                                               │ │                    │
│   - clean_input    │ │  - chat(api)      │ │                                                               │ │ WECAHT             │
│   - suit_for_talk  │ │                   │ │                                                               │ │                    │
│                    │ │ CLAUDE CODE       │ │                                                               │ │ FEISHU             │
│ Script             │ │  - chat(api)      │ │                                                               │ │  - daily_summary   │
│ 1.health_monitor   │ │                   │ │                                                               │ │                    │
│   - health_query   │ │                   │ │                                                               │ │                    │
│   - health_summary │ │                   │ ├───────────────────────────────────────────────────────────────┤ │                    │
│ 2.hisroty_monitor  │ │                   │ │Cron                                                           │ │                    │
│   - history_query  │ │                   │ │        1.todo_operat 2.chat_query 3.todo_identity [2min]      │ │                    │
│                    │ │                   │ │ HERMES ────────────────────────────────────────────────► MTD  │ │                    │
│                    │ │                   │ │                                                               │ │                    │
│                    │ │                   │ │        1.todo_operat 2.health_summary 3.history   [2min]      │ │                    │
│ ASSIST Daemon      │ │                   │ │ HERMES ──────────────────────────────────────────────► FEISHU │ │                    │
│ 1.audio_pipline    │ │                   │ │        4.edit_query 5.daily_summary                           │ │                    │
│ 2.ollama_pipline   │ │                   │ │                                                               │ │                    │
│                    │ │                   │ │                                                               │ │                    │
│ OTHER              │ │                   │ │                                                               │ │                    │
│ - reply_rule       │ │                   │ │                                                               │ │                    │
│ - feedback_rule    │ │                   │ │                                                               │ │                    │
│ - think_twice      │ │                   │ │                                                               │ │                    │
└────────────────────┘ └───────────────────┘ └───────────────────────────────────────────────────────────────┘ └────────────────────┘
       BASIC                  AGENT                                 SCHEDULE WORK FLOW                                INTERACT       
```

