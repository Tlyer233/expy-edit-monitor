# 文件编辑监控 (edit\_monitor)

**层级**：![BASIC](https://img.shields.io/badge/-BASIC-3088d1)![✓](https://img.shields.io/badge/-%E2%9C%93-2ea44f)─── ![AGENT](https://img.shields.io/badge/-AGENT-8250df) <======= ![WorkFlow](https://img.shields.io/badge/-WorkFlow-d97706) =======> ![INTERACT](https://img.shields.io/badge/-INTERACT-2ea44f)

**定位**：[![daemon](https://img.shields.io/badge/daemon-%E2%9C%93-2ea44f)](#daemon) [![api](https://img.shields.io/badge/api-%E2%9C%93-2ea44f)](#api) [![db](https://img.shields.io/badge/db-%E2%9C%93-2ea44f)](#db) [![ui](https://img.shields.io/badge/ui-%E2%9C%93-2ea44f)](#ui) [![skills](https://img.shields.io/badge/skills-%E2%9C%93-2ea44f)](#skills)

> macOS 内核级文件编辑监控插件 —— 记录每次保存、算 diff、生成 LLM 修改摘要，回答「某天我到底改了什么」。

1. 基于 macOS 内置的 `eslogger`（Endurance Security 事件流，10.15+ 内核级文件事件）内核级事件流

2. **按应用粒度勾选监控**（PyCharm、WPS Office 等），对命中应用的保存行为做快照、diff、LLM 摘要，持久化到本地 SQLite，并提供 REST API 与 Web 配置界面。

3. 内容解析**目前**支持普通文本（unified diff）与 Office/PDF 等含图文档（markitdown + 视觉模型），

4. reader 按文件类型自由扩展（PS 导出文件、PR 视频工程等, 后续会进一步支持），拓展性极强。
5. 是旧版 `5_edit_monitor`（inode追踪）的升级版，核心改进为 **xattr 持久化身份标识**(魔法标识)，解决 Office / Typora 等应用原子保存（先 create 临时文件再 rename）导致 inode 变化、文件追踪链断裂的问题。

<a id="daemon"></a>

## 一. Daemon ![✓](https://img.shields.io/badge/-%E2%9C%93-2ea44f)

#### Q1: 是否需要sudo?

需要! 因为mac的eslogger需要

#### Q2: 为什么需要常驻? 哪里需要常驻?
1. eslogger 是流式事件源，不是查询接口 —— 必须进程活着持续接收 write/rename/create/clone 事件，事件发生当下没人听就 永远丢失
2. 处理是异步接力 —— 事件不能同步算完 diff（含图修改要 本地模型 llm 来 vision，），必须入队 db 后由 Worker 轮询驱动，进程不在状态机就停摆
3. 文件快照时机依赖进程存活 —— 修改事件触发瞬间要临时记录文件快照(后面处理完成会删除)，错过即断链

<a id="api"></a>

## 二. API ![✓](https://img.shields.io/badge/-%E2%9C%93-2ea44f)

#### 1/4. GET /api/edit_monitor/discovered

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

#### 2/4. GET /api/edit_monitor/config

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

#### 3/4. PUT /api/edit_monitor/config

**① 定位**：![前端UI ✓](https://img.shields.io/badge/前端UI-%E2%9C%93-2ea44f) ![其他插件 ✗](https://img.shields.io/badge/其他插件-%E2%9C%97-red) ![能力暴露 ✗](https://img.shields.io/badge/能力暴露-%E2%9C%97-red)

**② Method**：![PUT](https://img.shields.io/badge/-PUT-fca130)

**③ Parameters**

| 参数                      | 位置 | 必填 | 类型   | 说明 |
| ------------------------- | ---- | ---- | ------ | ---- |
| `body.apps`               | body | 是   | array  | 监控应用白名单 |
| `body.global_noise_dir`   | body | 否   | array  | 全局噪声目录 |
| `body.global_noise_postfix` | body | 否 | array | 全局噪声后缀 |
| `body.timezone_offset`    | body | 否   | int    | 时区偏移（默认 8） |
| `body.merge_threshold_ms` | body | 否   | int    | MERGE 合并时间窗（毫秒） |
| `body.max_file_size_mb`   | body | 否   | int    | 快照大小上限（MB） |
| `body.post_llm`           | body | 否   | object | LLM 摘要配置 |

**④ Response**

| 状态 | 参数    | 类型   | 说明 |
| ----- | ------- | ------ | ---- |
| ![200](https://img.shields.io/badge/-200-2ea44f) | success | bool   | true |
| ![400](https://img.shields.io/badge/-400-red)   | success | bool   | false |
|       | error   | string | 错误原因（空请求体） |

**⑤ 示例（curl）**

```bash
# 请求：PUT /api/edit_monitor/config
# 参数解释（body 各字段，缺字段将被覆盖为空）：
#   body.apps:                array   监控应用白名单（必填）
#   body.global_noise_dir:    array   全局噪声目录
#   body.global_noise_postfix: array  全局噪声后缀
#   body.timezone_offset:     int     时区偏移（默认 8）
#   body.merge_threshold_ms:  int     MERGE 合并时间窗（毫秒）
#   body.max_file_size_mb:    int     快照大小上限（MB）
#   body.post_llm:            object  LLM 摘要配置
curl -X PUT "http://127.0.0.1:9723/api/edit_monitor/config" \
  -H "Content-Type: application/json" \
  -d '{"apps": [], "global_noise_dir": [".git"], "timezone_offset": 8, "merge_threshold_ms": 6000, "max_file_size_mb": 5, "post_llm": {"enable": true, "model": "qwen/qwen3-vl-4b@q4_k_m"}}'

# 成功(200): {"success": true}
# 空体(400): {"success": false, "error": "空请求体"}
```

**⑥ 备注**：写回 `config.json`，保存后 UI 会触发 daemon 重启生效。

---

#### 4/4. GET /api/edit_monitor/mac_apps

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

<a id="db"></a>

## 三. DB ![✓](https://img.shields.io/badge/-%E2%9C%93-2ea44f)

#### 1/1. `file_events.db` 包含两张表：

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

##### 整体分析

meta 表存每个文件的元信息；该文件的所有编辑记录在 event 表，通过 `ref_meta` 关联

##### 重要字段解析

- `event.status`（状态机，由两个 Worker 接力驱动）：
  - ① `diffing`：已入队，缺 `diff` 字段，Worker A — Diff Worker 抓取此状态
  - ② `descing`：已有 `diff`，缺 `diff_des` 字段，Worker B — Desc Worker 抓取此状态
  - ③ `done`：`diff` 与 `diff_des` 均处理完毕
  - ④ `failed`：任一阶段失败即转为该状态
- `event.diff`：`difflib` 生成的 unified diff（`diff -u file1 file2` 格式）；含图片内容需本地 LLM 参与
- `event.diff_des`：对 `event.diff` 的自然语言描述（由本地 LLM 生成）
- `meta.mid`：所有被监控文件都带有 `expy.edit.monitor: <uuid.uuid4()>` 的 xattr 属性

<a id="ui"></a>

## 四. UI ![✓](https://img.shields.io/badge/-%E2%9C%93-2ea44f)

- **应用侧栏**：已配置应用列表，`enabled` 开关一键启停，支持添加 / 移除本机 App
- **主面板**：应用详情 + 「文件后缀 / 忽略规则」标签编辑器
- **文件树**：某应用发现过的文件树（前端 `buildTree.js` 自建），支持忽略规则过滤与刷新
- **弹层**：忽略规则候选、本机 App 列表（`mac_apps` 接口扫描）、新应用后缀多选

***

<a id="skills"></a>

## 五. SKILL ![✓](https://img.shields.io/badge/-%E2%9C%93-2ea44f)

#### 1/1. file_edit_query 

TODO: 维护中.... 就算读db,skill里面路径也不应该写死, 应该api暴露db文件的路径

面向 Agent（Hermes 等）的查询 skill —— 直接读 `data/file_events.db`，回答「某天做了什么 / 哪些文件被修改过」，并提炼「主任务 + 子任务」当日总结。

- **直读 db，不走 API**：skill 直接用 SQL 查 `file_events.db`，比封装 API 更灵活
- **两阶段流程**：Phase 1 查询（8 个 SQL 模板）→ Phase 2 分析（观察 → 过滤噪声 → 归并 → 提炼 → 反问验证）
- **两种输出**：标准表格模式 / 快速语音模式
- **噪声过滤**：内置过滤速查表 + 合并规则 + Pitfalls（如 `diff_des` 为 NULL、`[[IMG]] DESC:` 占位符）

## 六. Config ![✓](https://img.shields.io/badge/-%E2%9C%93-2ea44f)

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

## 七. 整体架构 + 实现思路

#### 文件树

```
5_edit_monitor_magic/
├── main.py                    # Daemon 入口：root 校验 → 起 Worker A/B → eslogger → 事件循环
├── manifest.json              # 插件元数据（壳子识别唯一依据）
├── config.json                # 插件自己配置
├── env_check.py               # 部署前环境检测
├── requirements.txt           # Python 依赖
├── api/
│   └── router.py              # FastAPI 路由（config / discovered / mac_apps）
├── common/
│   ├── logger.py              # 日志（独立 loguru 实例）
│   ├── utils.py               # config 读写工具
│   └── xattr.py               # xattr mid 读写（魔法标识）
├── core/
│   ├── eslistener.py          # 5 层 verify 过滤 + deal_mid 身份判定 + MERGE/NEW
│   ├── diff_worker.py         # Worker A：轮询 diffing → 算 diff → descing
│   └── desc_worker.py         # Worker B：轮询 descing → 投递 LLM → done
├── db/
│   └── repository.py          # SQLite meta + event 两表 CRUD + 聚合查询
├── reader/
│   ├── planin.py              # 纯文本阅读器: unified diff
│   └── with_image.py          # Office/PD阅读器: markitdown + vision（[[IMG]] 占位）
├── skills/
│   └── file_edit_query/
│       └── SKILL.md           # Agent 查询 skill（直读 db，两阶段总结）
└── ui/
    ├── package.json           
    ├── vite.config.js         
    ├── index.html             # 入口 HTML
    ├── dist/                  # 构建产物（壳子 iframe 加载）
    └── src/
        ├── main.jsx           
        ├── index.css          # 全局样式(暗色/亮色)
        ├── components/
        │   └── ui/            # shdcn基础组件（button/dialog/input/switch/tabs）
        ├── lib/
        │   └── utils.js       
        └── pages/
            ├── EditMonitorPage.jsx       # 页面入口
            └── edit-monitor/
                ├── Sidebar.jsx           # 应用侧栏
                ├── MainPanel.jsx         # 主面板（后缀/忽略规则）
                ├── FileTree.jsx          # 文件树
                ├── store.js              # Zustand 状态
                ├── constants.js          # 常量
                ├── components/           # 弹层/标签等子组件
                └── utils/
                    ├── buildTree.js      # 前端树构建
                    └── fileignore.js     # 忽略规则匹配
```

#### 架构数据流

> **端到端数据流**（三线程通过 `event.status` 状态机接力）：

```
主线程（eslogger 监听）
  → 收到事件
  → [verify 5 层] ①应用匹配 → ②全局噪声后缀 → ③全局噪声目录 → ④per-app 后缀/忽略 → ⑤防抖(2s)
  → 产出 file_path + proc_full
  → deal_mid(mid):
      ├─ mid 未命中 DB → [首次] xattr 写新 mid + insert_meta → 递归
      ├─ mid√ file_path× → [重命名/复制] xattr 写新 mid + update_meta(mid, file_path) → 递归
      └─ mid√ file_path√ → 判 MERGE / NEW:
            ├─ 同应用 + diff_des 未关闭 + 时间差≤merge_ms → [MERGE] 仅延长 et
            └─ 否则 → 建快照 → [NEW] insert_event(status=diffing)

Worker A — Diff Worker（轮询 status=diffing → 目标: 填充 diff + mode）
  → 读快照 newContent + 查 meta 旧内容
  → reader 按后缀分发:
      ├─ planin      → difflib.unified_diff, mode=plain
      └─ with_image  → markitdown + vision(同步阻塞调 7_lms /lms/task_sync, 130s 超时), mode=llm   [失败→failed]
  → 回填 diff + mode → status=descing
  → 更新 meta(content, updated_at)（不更新 file_path）
  → 删快照

Worker B — Desc Worker（轮询 status=descing → 目标: 投递 LLM）
  → 按 mode 选 prompt → POST /lms/task 投递      [失败→failed]
  → descing → done（投递成功即 done，LLM 结果由 7_lms_daemon 异步回填 diff_des）
```

**运行细节**（主图省略的实现要点）：

```
- 快照:[NEW] 时 copy2 到 data/tmp/ + chmod 0644（root 复制的快照需放行其他进程读）; 复制失败 → status=failed
- 大小上限: 文件 > max_file_size_mb（默认 5MB）直接跳过, 不产生事件
- enable=false: Worker B 跳过投递直接 done（diff_des 留空）
- 空 diff:   Worker B 直接 done（避免投递 400 → failed）
- MERGE 条件: 同应用 + 上条事件 diff_des 为空 + 时间差 ≤ merge_threshold_ms
```

***

## 八. Key Design

#### 1/2. xattr 持久化身份标识（魔法标识🔮）
> 给每个被监控文件打一个「跨 inode 不变」的身份标签，解决原子保存导致的追踪断链。

   - **是什么**：macOS 文件系统的扩展属性（Extended Attributes，`xattr -l 文件` 可查看）—— 挂在文件 inode 上的 key-value 元数据，如 Finder 注释等都属于 xattr。本插件用固定 key `expy.edit.monitor` 存一个 UUID（`common/xattr.py`）。
   - **生命周期**：xattr 随 inode 走 —— 重命名 / 移动 / 修改内容**不变**；删除文件则随 inode **消失**；复制（Finder、`cp -p`）会**保留**到新文件。
   - **Office / Typora 的原子保存**：修改文件后触发保存时，先把原文件**复制**成临时文件（`copy` 保留 xattr，mid 随之复制），在临时文件上写新内容，再 `rename` 原子覆盖原文件—— 任一时刻文件要么是完整旧版、要么是完整新版，防写一半崩溃损坏；代价是 **inode 被替换**（旧版 inode 追踪方案因此断链），但 xattr/mid(魔法标识) 因复制而保留。
   - **为什么能保留**：原子保存会把原文件的 xattr/mid（魔法标识）带到新 inode，所以路径不变、mid 不变、追踪链不断。

#### 2/2. 含图文件(docx, ppt, pdf....📃)

>  全文按「骨架 + 图片描述」两段处理。

* **内容提取**：PDF 用 `pdfplumber` 逐页转为png => base64 ；docx/pptx/xlsx 用 `markitdown` 转换（`keep_data_uris=True` 保留base64）。

* **骨架占位符**：所有 `![](data:image/...;base64,xxx)` 替换为 `[[IMG:md5]]`（b64→md5，同图必同 md5，用于判同图）。

* **描述复用**：`meta.content` 存「骨架 + `DESC_SEP` 界定符 + 骨架中图片描述 json」；本次图片 md5 命中旧描述 → 直接复用（省 LLM）；新图 → `_vision` 同步调 本地LLM 生成描述。

* **diff 生成**：旧骨架 vs 新骨架（含占位符）做 unified diff，再在 diff 内把 `[[IMG:md5]]` 注入 `DESC:描述`（换行转义为字面 `\n` 防 diff 行被拆断；被删除的图用旧描述兜底）。最终 `meta.content` = 新骨架 + 全量描述 json，供下次解析复用。

#### 3/3. 覆盖几乎所有文件! 无论你是什么行业!

> 后期要解析各种格式文件, 都只需要新增一个reader方法即可, 后期自定义和拓展极强!
>
> 目前阶段没有做, 因为不了解这方面的工作, 后续需要大家共同构建!

* psd(PhotoShop的工程文件——绘画工作者)
* prproj(Premiere Pro的工程文件——视频工作者)
* ptx(Pro Tools的工程文件——音频工作者)

## License
> 涉及用户最高隐私,可以做应用,但是强制开源!

**AGPLv3**

