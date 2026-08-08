---
name: file-edit-query
description: 查询 5_edit_monitor_magic 后台采集的文件编辑事件数据库（file_events.db），分析每天修改了哪些文件、由哪些应用触发，并提炼总结当天的工作内容。当用户询问某天做了什么、哪些文件被修改过、或需要总结某天工作内容时调用。
version: "1.0.0"
author: mts
license: MIT
platforms: [macos]
metadata:
  hermes:
    tags: [productivity, file-monitor, sqlite, edit-monitor, analysis, task-management, summarization]
---

# File Edit Query + Daily Summary

5_edit_monitor_magic 是后台常驻的 macOS 文件编辑监控服务：通过 eslogger（内核级事件）实时捕获编辑器/IDE/办公软件的写文件事件，按「meta（文件实体）+ event（编辑事件流水）」写入 SQLite。本 skill 提供两阶段能力：

1. **查询阶段**：获取某天的原始编辑事件数据（改了什么文件、哪个应用、改了啥）
2. **分析阶段**：从原始数据中提炼主任务与子任务，生成"对，我今天确实做了这些"的总结

**核心原则：不要简单罗列数据行，而是先观察 → 再分析 → 总结 → 提炼得出结论。**

## When to Use

- 用户要求查询某天修改过的文件
- 用户要求总结某天做了什么 / 当天的工作内容
- 用户要求知道某天在哪些文件上真正花了时间编辑
- 需要从逐行原始数据 → 结构化任务总结的场景
- **不要**在只有单条记录或无实质内容时调用（无需提炼）

## Quick Reference

### 数据库信息

- 插件根目录: `/Volumes/SAMSUNG_1T/Documents/CodeBeach/Hermes_ASSISTANT/5_edit_monitor_magic`
- 数据库文件: `/Volumes/SAMSUNG_1T/Documents/CodeBeach/Hermes_ASSISTANT/5_edit_monitor_magic/data/file_events.db`
- WAL 模式，读操作无需特殊处理；只读建议使用 `sqlite3` CLI 或 `mode=ro` 连接

### 表结构

#### `event` — 编辑事件流水（核心查询表，包含 file_path 字段）

```sql
CREATE TABLE event (
    id          INTEGER PRIMARY KEY AUTOINCREMENT, -- 自增事件 ID
    ref_meta    INTEGER NOT NULL,                  -- 外键 → meta.id
    file_path   TEXT    NOT NULL,                  -- 事件发生时文件路径
    proc_name   TEXT    NOT NULL,                  -- 触发进程名（显示名，如 Trae/TextEdit/WPS Office）
    st          TEXT    NOT NULL,                  -- 事件开始时间（本地 ISO）
    et          TEXT    NOT NULL,                  -- 事件结束时间（本地 ISO）
    size_bytes  INTEGER,                           -- 文件大小（字节）
    diff        TEXT,                              -- 差异文本（Worker A 回填）
    diff_des    TEXT,                              -- 差异描述（Worker B 回填，LLM 总结，可能为 NULL）
    status      TEXT    NOT NULL DEFAULT 'diffing', -- diffing→descing→done|failed
    tmpfilepath TEXT,                              -- 事件快照临时文件路径（历史残留，无查询价值）
    mode        TEXT,                              -- plain（纯文本 unified diff）/ llm（复杂文件 markdown 提取）
    FOREIGN KEY (ref_meta) REFERENCES meta(id)
);
```

> `file_path` 直接存储在 `event` 表中，大部分查询无需 JOIN。`diff_des` 为 LLM 自动生成的修改摘要（可能为 NULL，需判空）。`status` 通常只看 `done`；`failed` 的事件 `diff/diff_des` 缺失。

#### `meta` — 文件实体注册表（辅助表）

```sql
CREATE TABLE meta (
    id         INTEGER PRIMARY KEY,     -- 自增主键
    mid        TEXT    UNIQUE NOT NULL, -- xattr 魔法 ID，跨重命名/复制稳定追踪
    file_path  TEXT    NOT NULL,        -- 当前文件路径
    content    TEXT,                    -- 最新文件内容（用于 diff，可能很大）
    updated_at TEXT    NOT NULL         -- 最后更新时间
);
```

> `meta.mid` 是写入文件 xattr（Finder 注释 `expy.edit.monitor`）的 UUID，用于文件被重命名/复制后仍能追踪同一实体的历史。`meta.content` 单文件可达 5MB，仅在需要完整内容时才 JOIN 读取。

### 噪声过滤速查

| 类型 | 处理方式 |
|------|---------|
| 系统临时目录（`/Volumes/SAMSUNG_1T/.TemporaryItems/`、`*NSIRD_*`、`*.TemporaryItems*`） | 完全忽略 |
| IDE/构建缓存（`.trae-history`、`.vscode`、`node_modules`、`dist`、`build`、`__pycache__`、`.git`） | 完全忽略 |
| Office 临时文件（`~$` 开头） | 完全忽略 |
| 验证链路随手写（一次性测试文件、临时 md） | 完全忽略 |
| 微小维护改动（单行修复、变量重命名） | 归入备注，不独立成子任务 |
| 一次性初始化配置（创建空文件、写一行配置） | 属于主任务的一个步骤，非独立子任务 |

### 合并规则

- ✅ 同一项目 + 同一时段 + 同一目标 → 归为一个主任务
- ✅ 跨不同工具做同一件事 → 归为一个主任务
- ❌ 不同项目不同目标 → 禁止合并
- ❌ 系统行为与用户工作 → 禁止混合

### 主任务命名

- ✅ `编写 file-edit-query SKILL 文档` — 体现目标
- ❌ `Trae + TextEdit 文档工作` — 仅罗列工具

### 常用查询模板

以下 `DB` 均指 `/Volumes/SAMSUNG_1T/Documents/CodeBeach/Hermes_ASSISTANT/5_edit_monitor_magic/data/file_events.db`。

#### 1. 轻量探测 — 确认数据范围

```
sqlite3 -header -column <DB> \
  "SELECT COUNT(1) AS total_events,
          COUNT(DISTINCT proc_name) AS apps,
          date(MIN(st)) AS first_date,
          date(MAX(st)) AS last_date
   FROM event;"
```

#### 2. 某天所有编辑事件（完整详情，含 diff_des）

```
sqlite3 -header -column <DB> \
  "SELECT e.file_path, e.proc_name, e.st, e.et, e.mode, e.status, e.diff_des
   FROM event e
   WHERE date(e.st) = 'YYYY-MM-DD'
   ORDER BY e.st;"
```

#### 3. 某天某个应用修改的文件

```
sqlite3 -header -column <DB> \
  "SELECT e.file_path, e.st, e.et, e.diff_des
   FROM event e
   WHERE date(e.st) = 'YYYY-MM-DD' AND e.proc_name = 'Trae'
   ORDER BY e.st;"
```

#### 4. 某天被修改的文件列表（去重）

```
sqlite3 -header -column <DB> \
  "SELECT DISTINCT e.file_path, e.proc_name
   FROM event e
   WHERE date(e.st) = 'YYYY-MM-DD'
   ORDER BY e.file_path;"
```

#### 5. 某天各应用修改统计

```
sqlite3 -header -column <DB> \
  "SELECT proc_name, COUNT(*) AS events, COUNT(DISTINCT file_path) AS files
   FROM event
   WHERE date(st) = 'YYYY-MM-DD'
   GROUP BY proc_name
   ORDER BY events DESC;"
```

#### 6. 某天项目分布（去重 + 统计）

```
sqlite3 -header -column <DB> \
  "SELECT CASE
     WHEN e.file_path LIKE '%Hermes_ASSISTANT/5_edit_monitor_magic%' THEN '5_edit_monitor_magic'
     WHEN e.file_path LIKE '%Hermes_ASSISTANT/7_lms_daemon%' THEN '7_lms_daemon'
     WHEN e.file_path LIKE '%Hermes_ASSISTANT/ExposeYourself%' THEN 'ExposeYourself'
     WHEN e.file_path LIKE '%Hermes_ASSISTANT/1_wecat_monitor%' THEN '1_wecat_monitor'
     WHEN e.file_path LIKE '%/.hermes/%' THEN '.hermes'
     ELSE 'Other'
   END AS project,
   COUNT(DISTINCT e.file_path) AS files,
   COUNT(*) AS events
   FROM event e
   WHERE date(e.st) = 'YYYY-MM-DD'
   GROUP BY project
   ORDER BY events DESC;"
```

> **关键点**：需根据实际项目路径维护 `CASE WHEN` 分支；`Other` 类目几乎都是 IDE 缓存/临时文件，统计时可用 `WHERE e.file_path NOT LIKE '%cache%' AND e.file_path NOT LIKE '%TemporaryItems%'` 等排除。

#### 7. diff_des 为空的候选（需要读 diff 字段自行总结）

```
sqlite3 -header -column <DB> \
  "SELECT e.id, e.file_path, e.proc_name, e.st, length(e.diff) AS diff_len
   FROM event e
   WHERE date(e.st) = 'YYYY-MM-DD' AND e.status = 'done'
     AND (e.diff_des IS NULL OR e.diff_des = '')
   ORDER BY e.st;"
```

> 命中后逐条读取 `diff` 字段判断：空 diff（内容无变化）直接忽略；非空则自行总结。读取单条 diff：`sqlite3 <DB> "SELECT diff FROM event WHERE id = <id>;"`

#### 8. 追踪单个文件的某天迭代（多次保存合并成一段）

```
sqlite3 -header -column <DB> \
  "SELECT e.id, e.proc_name, e.st, e.et, e.diff_des, length(e.diff) AS diff_len
   FROM event e
   WHERE date(e.st) = 'YYYY-MM-DD' AND e.file_path LIKE '%目标文件名%'
   ORDER BY e.st;"
```

### 时间说明

- `st`/`et` 是**本地时区** ISO 字符串：`2026-08-03T13:19:19`；`date(st)` 可直接取 `YYYY-MM-DD`
- 一天范围既可用 `WHERE date(e.st) = 'YYYY-MM-DD'`，也可用 `WHERE e.st LIKE 'YYYY-MM-DD%'`

## Procedure

### Phase 1: 查询 — 获取原始数据

1. **确认时间范围和目标**: 从用户问题中提取日期、应用名。日期使用 `YYYY-MM-DD` 格式。
2. **轻量探测**: 用模板 #1 确认 DB 可用、日期范围内有数据。
3. **收窄范围**: 按用户关注点细化查询：
   - 查全部活动 → 模板 #2
   - 查某个应用 → 模板 #3
   - 查文件列表 → 模板 #4
   - 查统计 → 模板 #5
   - 查项目分布 → 模板 #6
   - 查 diff_des 缺失 → 模板 #7
4. **读取修改描述优先用 `diff_des`**。`diff_des` 为 NULL/空时，读 `diff` 字段自行总结（模板 #7）。
5. **补充文件内容（可选）**: 若 `diff` 不足以判断，再通过 `meta.content` 或 Hermes File Operations 查看文件（`SELECT content FROM meta WHERE id = <ref_meta>;`，注意大文件）。

### Phase 2: 分析 — 提炼任务

#### Step 1: 观察 — 阅读原始数据

先整体通读，标记关键维度：

| 维度 | 观察点 |
|------|--------|
| 时间线 | 连续编辑行为的起止，是否存在跨工具接力 |
| 操作工具 | 哪个 IDE/编辑器/办公软件，是否切换工具做同一件事 |
| 文件路径 | 归属于哪个项目/模块 |
| 修改描述 (diff_des / diff) | 是实质性改动（重构/写作/决策）还是微调 |
| 操作频率 | 一次性写入 vs 多次迭代（≥2 次是关键信号） |

#### Step 2: 分析 — 过滤噪声

应用 Quick Reference 中的噪声过滤规则。**保留的判断标准：用户是否在此文件上投入了思考、做了决策、经历了迭代？**

- ✅ 多次修改同一文件（≥2 次编辑且内容有实质变化）
- ✅ 修改涉及逻辑重构、结构设计、内容创作
- ✅ 修改描述提到决策（"重构为"、"新增了"、"规范了"）
- ❌ 一次性写入 / 自动产生 / 仅为配置文件开关

#### Step 3: 归并 — 识别主任务

将保留下来的修改记录按**目标**而非**工具**分组为主任务。遵循 Quick Reference 中的合并规则。

#### Step 4: 提炼 — 从修改记录 → 子任务

**核心：不是每个文件 = 一个子任务，而是 N 个相关文件修改 → 提炼为一个子任务。**

```
原始记录：
  api/router.py 新增 mac_apps 扫描 /System/Applications 目录
  api/router.py 修正扫描目录注释
  core/eslistener.py 增加 FileNotFoundError 降级 warning
  common/xattr.py assert 改为 raise FileNotFoundError

提炼后：
  子任务 ① 修复 mac_apps 接口 — 补扫系统应用目录
  子任务 ② 处理文件消失竞态 — xattr 断言改显式异常并降级日志
```

**子任务书写原则：**
- 以动词开头，说明做了什么决策/创造
- 包含具体的技术动作（重构、优化、补充、规范）
- 提到涉及的文件但不以文件名为子任务名

#### Step 5: 反问验证 — 输出前逐条核对

1. 这些子任务读起来像"人做的事"吗？还是像"数据库的每一行"？
2. 有没有把"我查到的数据"当成了"用户的工作量"？
3. 如果拿掉这个子任务，主任务功能上还完整吗？→ 是则保留，否则归入备注
4. 有没有两个不同项目、不同目标的东西被硬塞到一起？→ 拆开
5. 主任务是按"目标"命名的吗？还是按"工具"命名的？→ 按目标

## Output Shape

### 标准模式（表格详情）

适用于文本对话场景，输出格式如下：

```
## 主任务一：〈完成的目标〉
**分组：**〈分组名 / 项目名〉
**投入时段：** HH:MM-HH:MM
**为什么是主任务：** 一句话说明投入了思考/决策/迭代

| # | 子任务（动词开头） | 开始 | 结束 | 对应产出 |
|---|-------------------|:----:|:----:|---------|
| ① | 做了什么决策/创造 | HH:MM | HH:MM | 涉及的文件简述 |
| ② | ... | ... | ... | ... |

> **备注：** 忽略的噪声记录及原因
```

### 快速 / 语音输出模式

当用户要求「快速查询」「语音输出」「说结论」「简短点」时——使用纯文本口语化总结，规则：

1. **按天分段**，每天一段话
2. **每段开头**用日期 + 星期几（如「8月3号周一」）
3. **先总览后细节**：「今天主要在开发 5_edit_monitor_magic，做了 xxx」
4. **文件名转述为人话**：不说「修改了 router.py」，说「修了 mac_apps 接口」
5. **工具名不提**：不说「用 Trae 改了 xxx」，直接说「做了 xxx」
6. **IDE 缓存噪声一句话带过**或直接忽略
7. **每段一两句话**，不要分点或表格

## Pitfalls

- **`diff_des` 可能为 NULL**: 空 diff（内容无变化）不会投递 LLM、投递失败也会导致 NULL；使用时必须判空，NULL 时段需读 `diff` 字段自行总结
- **`mode=llm` 的 `diff` 含 `[[IMG:md5]] DESC:xxx` 占位符**: 这是 markitdown 提取后图片的视觉描述，不是文件正文，总结时按图片内容理解
- **一行事件 = 一个编辑段**: 同一文件的多次连续保存会被 MERGE 合并为一段（`st` 到 `et`），也可能拆成多行；统计文件数务必用 `DISTINCT`/`GROUP BY` 去重
- **`status=failed` 的事件无 diff/diff_des**: 不能代表真实工作内容，查询时用 `status = 'done'` 过滤
- **`file_path` 会随重命名变化**: 同一实体的历史通过 `meta.mid`（xattr UUID）追踪；按路径查历史时用 `LIKE` 模糊匹配
- **`proc_name` 不是标准枚举**: 先 `SELECT DISTINCT proc_name FROM event` 确认当前值
- **`sqlite3` 中 `date()` 直接识别 ISO 字符串**: `date('2026-08-03T13:19:19')` = `'2026-08-03'`
- **数据库 schema 可能随项目迭代变化**: 务必先用 `.schema event` / `.schema meta` 确认当前表结构
- **不要一次读所有 `meta.content`**: 单文件可达 5MB，只读真正需要的
- **把"都是基础层工具"当合并理由**: 即使同为基础设施，不同项目目标不同，必须拆为独立主任务
- **系统行为混入用户工作**: 系统临时目录（`.TemporaryItems`、`NSIRD_`）、token 刷新、自动备份等非用户主动行为，必须完全排除
- **文件名当子任务名**: 子任务应体现决策和动作，而非单纯罗列文件名

## Verification

### 查询阶段验证
- 确认 `file_events.db` 存在且非空
- 确认 `event` 表存在且有行
- 确认查询日期范围内有数据
- 确认 `diff_des` 为 NULL 时已读 `diff` 字段自行总结

### 分析阶段验证
- [ ] 子任务总数远小于原始记录行数（通常压缩 60% 以上）
- [ ] 没有把系统自动行为（TemporaryItems/缓存/token 刷新）列进去
- [ ] 没有把随手测试文件列进去
- [ ] 主任务之间界限清晰（不同项目 / 不同目标）
- [ ] 主任务命名体现"完成的目标"而非"使用的工具"
- [ ] 每个主任务都回答了"为什么这个值得成为一个主任务"

验证命令:

```
sqlite3 -header -column <DB> \
  "SELECT e.proc_name,
          COUNT(DISTINCT e.file_path) AS files,
          COUNT(*) AS events
   FROM event e
   WHERE date(e.st) = 'YYYY-MM-DD'
   GROUP BY e.proc_name
   ORDER BY events DESC;"
```
