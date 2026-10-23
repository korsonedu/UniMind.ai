# Agent-linked Notes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 用户可独立编辑、组织笔记，并允许现有 Agent 在会话内及跨会话只读参考。

**Architecture:** Django notes app 管理个人内容和关联，统一上下文服务供现有三个聊天入口读取。前端独立笔记页复用现有 AgentChatLayout 和 useAgentConversation，正文以 Markdown 保存。

**Tech Stack:** Django / DRF、React / TypeScript、Tiptap、现有 Markdown 数学渲染。

**Spec:** `docs/superpowers/specs/2026-10-22-agent-linked-notes-design.md`（用户已确认）。

## Global Constraints

- Agent 不能创建、修改、删除笔记，不能移动目录或调整标签。
- 个人私有，按 user + Bot 限定参考范围，不共享 Bot 全局正文，不从笔记生成跨 Agent 自动记忆。
- 不改现有未提交的 landing、截图、FullAppPreview 或数据库备份。
- 不引入向量服务、协同编辑、离线同步及附件系统。
- 遵照用户要求只做冒烟验证和必要构建，不采用完整 TDD / 全量回归。

## Review Focus

- 其他用户的 note/notebook/Bot/Conversation ID 不可借关联泄漏内容。
- 切换笔记或多标签页更新不会静默覆盖正文，冲突保留编辑内容。
- 笔记本循环移动被拒绝；删除只提升直属子项；导出重名不覆盖。
- 临时参考按会话恢复，长期范围动态展开，回收站与解除关联立即停止后续检索。
- polling / SSE / WS 都持久化真实来源，笔记对话不进入自动记忆及跨会话画像。

## Task 1: 私人笔记数据与 API

**Files:** 新增 `backend/notes/{apps,models,serializers,views,urls,exports}.py` 及 migration，注册 settings 和 urls。

**Interfaces:**
- `Notebook(user,parent,name,position)`；`Note(user,notebook,title,content,is_favorite,version,deleted_at,created_at,updated_at,tags)`；`Tag(user,name)`；`NoteLink(source,target)`；`AgentNoteBinding(user,bot,note,notebook)`；`ConversationNoteReference(user,bot,conversation,note)`。
- `/api/notes/notebooks/` 与 `/<id>/`：GET/POST/PATCH/DELETE，字段 `id,name,parent,position`。
- `/api/notes/items/` 与 `/<id>/`：GET/POST/PATCH/DELETE，字段 `id,title,content,notebook,tags,is_favorite,version,deleted_at,updated_at,backlinks`；tags 是标签名数组，backlinks 是 `{id,title}` 数组；PATCH 必须提供 version，冲突返回 409。
- 列表支持 `q,notebook,tag,favorite,trash,bot`；未分类用 notebook=unfiled；默认只查未删除笔记；列表为无分页数组。
- POST `/items/<id>/restore/`；DELETE `/items/<id>/?permanent=1` 仅作用于已回收笔记。
- GET `/items/<id>/export/` 与 `/notebooks/<id>/export/`；GET `/tags/`。
- `/bindings/` GET/POST，`/<id>/` DELETE；字段 `id,bot,note,notebook`，目标二选一。
- `/references/?bot=<id>&conversation_id=<uuid>` GET/PUT，返回 `{note_ids:[int]}`；PUT 首次可创建属于该 user + bot 的 Conversation。
- 公用 `accessible_bot(user, bot_id)` 校验既有 ai.assistant 权限与当前可见 Bot，`notebook_ids(user, root_ids)` 展开子树；给上下文服务复用。

- [x] 实现 owner 过滤、显式序列化、原子版本更新、稳定内部链接索引、回收与层级操作。
- [x] 实现个人关联和参考接口及带目录、标签、相对链接的 Markdown / ZIP 导出。
- [x] 使用 manage.py makemigrations 生成新增 migration，不修改开发数据库。
- [x] 冒烟：用户隔离、409、回收与恢复、循环移动、同名导出及关联目标校验。

## Task 2: Agent 只读上下文和来源

**Files:** 新增 `backend/notes/context.py`，修改 `ai_assistant/{views,consumers}.py` 与必要的 memory / profile 查询。

**Interfaces:** `prepare_note_context(user, bot, conversation_id, message, note_ids=None, selection='') -> (context: str, sources: list)`。参考列表可用请求 `note_ids` 覆盖；省略时沿用会话绑定。sources 字段为 `source_id,note_id,title,version,excerpt,kind`，模型引用格式 `[N1]`。

- [x] 从 Task 1 公用 owner / Bot 校验与模型构造临时参考和长期关联并集，按显式参考优先、关键词相关度排序，限制 12000 字符上下文及单篇 3000 字符。
- [x] 将资料作为参考消息注入三个入口，metadata 保存 `note_sources`，用户问题标记 `notes_context_used`，选中片段仅单次有效。
- [x] 自动记忆和画像/轨迹内容处理排除使用过笔记的会话；旧普通对话行为保持。
- [x] 来源快照仅显示实际提供过的 ID，前端不将模型自行输出的 ID 视为真实引用。
- [x] 冒烟：跨会话长期范围、笔记本新成员、回收与移出、无关联不读取、不产生任何写笔记工具。

## Task 3: 笔记编辑、组织和 Agent 面板

**Files:** 新增 `frontend/src/pages/notes/{NotesPage,NoteEditor,NoteSources}.tsx`、`frontend/src/lib/notes.ts`、`frontend/src/styles/notes.css`；修改 App、MainLayout、AgentChatLayout 和 useAgentConversation 的最小接入。

**Interfaces:** Task 1 REST API；`AgentChatLayout` 新增异步 `beforeSend` 用于保存、`contextPanel` 显示当前会话参考与长期关联入口，沿用 `getExtraPayload` 和 `initialConversationId`；NoteSources 接收 sources 和 content，区分实际参考与 `[N#]` 引用。

- [x] 构建多级目录、收藏/最近/回收站、标签和组合筛选、笔记本及笔记的新增重命名移动删除恢复和导出。
- [x] 独立 Tiptap 编辑器，支持富文本、公式 Markdown 预览、稳定 note ID 链接与 `[[` 搜索选择、反向链接。
- [x] 保存防抖与串行请求，版本冲突保留本地正文；切换/离开前保存，失败不得发 Agent 请求。
- [x] 笔记侧打开现有 Agent 对话，临时参考可加减，长期关联支持单篇或笔记本，清晰显示只读；会话变化恢复自己的参考列表。
- [x] 将 NoteSources 接入公共 AgentChatLayout 的消息渲染，引用能打开笔记及显示历史片段。
- [x] 路由 `/notes` `/notes/:id` 和导航入口；小屏切换目录/笔记/讨论，不创建第二套聊天状态。

## Task 4: 集成、冒烟、交付

- [x] 在独立临时数据库中执行 notes 冒烟及 Django check / migration check。
- [x] TypeScript 检查及 Vite 构建；用本地浏览器验证实际笔记页的保存重开和移动端布局，必要时修复。
- [x] 只审阅本任务 diff，修复所有影响首版的问题，核对设计覆盖。
- [x] 更新本计划完成状态和本地交付说明。部署另按用户发布指令执行，准确区分本地实现与线上状态。

执行方式：按现有授权直接实施，不再重复请求开工确认。为避免文件冲突，数据/API 与前端可由分别拥有文件的 worker 实施，主线程负责聊天运行时接入和集成；使用 subagent-driven-development 指导分工与最终审阅。

## 本地验证记录（2026-10-23）

- 独立临时 SQLite 中 `manage.py test notes`：15 项通过，覆盖 owner 隔离、版本冲突、层级及回收、导出、动态参考范围和来源快照。三个聊天入口使用替身模型验证，不调用外部模型、不使用线上账号。Django system check 无问题。
- `makemigrations notes --check --dry-run`：无缺失迁移；未迁移现有开发或生产数据库。
- TypeScript 检查与 Vite/PWA 构建通过。真实临时后端的浏览器冒烟通过：保存重开、Markdown/富文本公式保留与 KaTeX 预览、临时参考移除后不被重新加入、长期笔记本关联、390px 编辑视图无横向溢出、无浏览器异常。
- 全分支静态审查及范围复核发现删除笔记本期间编辑和导航的同类竞态，已在 `35bbb2d`、`4ab97e2` 修复：操作时暂停编辑和离开，已排队离开时拒绝启动其他操作。针对性浏览器冒烟通过：延迟删除期间输入受阻、后退等待完成、URL 与正文一致；正常新建/回收跳转不死锁；离开前保存等待期间不会并行启动删除。其余未发现影响首版的重要问题。
- 工作保存在独立分支 `feat/agent-linked-notes`；主目录原有 landing 与截图等未提交改动保留。尚未合并、推送或生产发布。

交付状态：本地实现及冒烟验收完成。最终前端检查和构建覆盖 `4ab97e2`。发布前仍需按既有流程完成合并或推送、数据库备份、生产迁移及构建切换，再检查服务健康、公共资源和笔记入口；目前未执行这些生产操作。
