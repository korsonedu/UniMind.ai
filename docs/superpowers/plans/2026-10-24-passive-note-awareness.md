# Passive Note Awareness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 纯笔记页、小宇无感理解与会话内 @ 重点引用，全部保持学生独占编辑权。

**Architecture:** 复用 notes app、Celery、现有三种聊天入口和 AgentChatLayout。后台理解与通用记忆分开保存，按用户、启用代次和笔记内容版本校验；主动引用复用 ConversationNoteReference。

**Tech Stack:** Django/DRF、Celery、React/TypeScript、Tiptap、现有 AIEngine。

**Spec:** `docs/superpowers/specs/2026-10-24-passive-note-awareness-design.md`（已确认，用户已要求开始）。

## Global Constraints

- AI 不创建、改写、删除、移动或重标记笔记。只供本人小宇自动了解，其他 Agent 不扩大范围。
- 首次确认前不自动处理；关闭自动了解后仍可主动 @。后台学习线索不进入共享画像或通用记忆。
- 保留版本冲突及 busy/导航保护、历史来源、图标工具栏和站内弹窗。
- 不改其他任务的 landing 和数据库备份，不引入新 RAG 服务、不修改商业套餐。
- 用户只要求冒烟，不做完整 TDD 或全量回归；不在生产账号测试。

## Review Focus

- 关闭又开启、修改又恢复、任务迟到时，旧结果不能复活。
- 会话变化和异步加载期间不得用旧会话的参考发问；失败保留问题草稿。
- @ 的菜单 Enter/方向键/Escape/中文输入法不能误发问题，邮箱普通 @ 不应劫持输入。
- 非小宇、权限撤销、他人笔记、回收站不会通过自动了解扩大访问。
- 真实来源版本、用户附件与实际提供给模型的片段不混淆。

## Task 1: 后端设置、版本化理解与聊天接入

**Files:** `backend/notes/{models,views,urls,context}.py`，新增 `awareness.py`、`tasks.py`、`tests_awareness.py`、migration；必要修改 `backend/ai_assistant/{views,consumers}.py`。

**Interfaces:**
- GET/PATCH `/api/notes/ai-settings/` -> `{enabled: boolean, acknowledged: boolean}`。PATCH `{enabled: boolean}` 同时记录已告知；启用需小宇使用资格。
- GET `/api/notes/lookup/?q=标题` -> 非回收站本人笔记的轻量数组 `{id,title,notebook,version}`；`ids=1,2` 可恢复引用详情，最多30项。无输入搜索可返回最近20篇。
- `prepare_note_context` 保持既有 `(context, sources)` 合同；开启自动了解的小宇可按相关性从本人有效笔记及有效理解检索；会话重点参考优先。非小宇保留旧显式范围，不自动扩大。
- 后台理解按内容签名、版本、设置代次保存，结构包括主题/明确解释/疑问/依据，所有依据来自原文；不写 AgentMemory 或共享画像。
- 用户消息 metadata `note_attachments` 保存实际本次发送的重点笔记快照 `{note_id,title,version}`；三个入口一致。可基于实际来源中 temporary 项构建，不把未提供的片段标成已提供。

- [x] 新增设置及理解模型，生成增量 migration；后台任务采用短延迟合并（20秒），同内容避免重复模型调用，权限/设置/内容变化均在完成时重新校验。
- [x] 保存、恢复、回收与设置变化触发处理或失效；队列和模型失败不能导致保存失败。后台 AI 调用复用 AIEngine，有限输入/输出，验证结构及原文依据，失败有限重试。
- [x] 接入上下文，保留通用记忆/轨迹排除；新增设置和 lookup 私有接口及用户附件 metadata。
- [x] 隔离 DB 冒烟：默认不读、启用后理解/检索、关闭后失效但 @ 可用、迟到结果不覆盖、非小宇不自动读取、本人/他人隔离、来源版本。
- [x] 提交后报告接口和运行命令，主线程不修改同一后端文件。

## Task 2: 纯笔记页与个人设置

**Files:** `frontend/src/pages/notes/{NotesPage,NoteEditor}.tsx`，新增 `NoteAISettings.tsx`，修改 `frontend/src/pages/Settings.tsx`、`frontend/src/lib/notes.ts`、必要 notes CSS。

- [x] 移除笔记侧聊天面板、讨论按钮、选中文字发送和 Agent 筛选；手机仅目录/笔记。保留保存与导航保护。
- [x] 首次进入仅一次启用说明，选择启用或直接书写都通过设置接口确认；取消/关闭不启用，失败可重试且编辑可用。
- [x] 个人设置增加统一开关；不在笔记页增加常驻提示小字。

## Task 3: 小宇输入器 @ 与会话附件

**Files:** 新增 `frontend/src/pages/notes/NoteMentions.tsx`，修改 `AgentChatLayout.tsx`、`useAgentConversation.ts`、`ChatBubble.tsx`、`XiaoYu.tsx`、notes CSS。

**Interfaces:** AgentChatLayout 新增仅小宇启用的 `enableNoteMentions?: boolean`，两个 native composer 复用同一个 NoteMentions。对菜单键盘及输入光标进行最小接入，不重建聊天 hook。

- [x] @ 在空白边界触发，搜索标题，展示路径、键盘/触摸选择、多篇和移除；未选中的 @ 保持普通输入。菜单事件优先于 Enter 发问。
- [x] 根据 bot+conversation 加载/保存 references；输入草稿不因加载或错误丢失；发送前确保当前会话引用已同步。
- [x] 发送后标签保留，切换会话恢复，新会话为空；引用列表持久化失败阻止发问且可重试。
- [x] 用户消息显示可点击附件，历史使用后端快照，当前乐观消息复用刚校验的标签元数据；回答引用沿用 NoteSources。

## Task 4: 集成与交付

- [x] 在隔离 DB 执行新冒烟及既有 notes 必要冒烟；迁移检查、TypeScript/Vite 构建。
- [x] 实际本地 UI：无 AI 面板、首次说明、个人设置、@ 搜索/键盘选择/中文/移除、会话恢复/新会话及手机布局。
- [x] 一次全分支审查并修复重要问题，完成计划记录；准确区分本地与发布状态。

执行裁决：用户已批准设计并明确要求开始，直接实施，不重复请求开工批准。后端由专职 worker 拥有，主线程负责前端与集成；只做必要冒烟。

## 本轮验证结果

- 后端提交：`9994770`、`54debff`。隔离 SQLite 的 notes 范围共23项冒烟通过，迁移检查无遗漏。模型及 broker 使用桩，未接生产数据库。
- 前端：TypeScript 与完整 Vite 构建通过，`git diff --check` 通过。
- 真实本地浏览器：首次说明、个人开关、纯编辑页、@ 搜索、邮箱不触发、键盘选择、会话切换恢复、移除、Esc、390px 手机布局及零浏览器异常通过。
- 本地模型桩：中文输入法不误选/误发、引用保存失败保留问题且阻止请求、重试、当前 note_ids 提交、服务端权威附件和发送后保留标签通过。
- 独立审查提出跨标签页引用同步、乐观附件与真实来源不一致两项问题，均已修复并复核，无遗留重要问题。
- 本地预览：前端5186，临时后端8196。本轮未推送或部署；真实模型与运行中的 Celery broker/worker 未联调。后台队列失败会保留待处理状态，可在恢复后保存或再次启用重入队。
- 主工作区未修改；原有数据库备份保留。隔离目录中的调试配置与 `.superpowers/sdd` 为本地临时工作材料，不提交。
