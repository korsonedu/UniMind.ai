# AI 出题工作台

## 概述

AI 出题工作台是老师/机构主的核心工作界面，采用**对话式 Agent 架构**——教师通过自然语言描述出题需求，Agent 自主调用工具搜索知识点、生成题目、精修入库。结构与小宇（XiaoYu）学习规划 Agent 对齐：未对话时大片留白，对话后左右分栏。

## 页面布局

### 空状态（无对话）

```
┌─────────────────────────────────────────────────┐
│                 大片留白居中                       │
│          [Gradient Icon]                         │
│          出题助手                                  │
│          你的 AI 出题工作台                        │
│                                                  │
│    ┌─────────────────────────────────────┐       │
│    │ 描述你的出题需求...          [发送]  │       │
│    └─────────────────────────────────────┘       │
│                                                  │
│  [针对薄弱点出题] [出一套模拟卷] [自定义出题]       │
└─────────────────────────────────────────────────┘
```

### 对话状态（有对话后）

```
┌──────────────────────────┬──────────────────────┐
│ 左侧 flex-1              │ 右侧 360px           │
│                          │                      │
│ 生成的题目卡片列表        │ [Header] 出题助手     │
│ (QuestionPanel)          │                      │
│                          │ [Messages]           │
│ ┌──────────────────────┐ │  用户: 出10道微积分    │
│ │ Q1: 求极限...        │ │  助手: 好的，已生成    │
│ │ [✓] 客观题 normal    │ │  [题目预览卡片]       │
│ ├──────────────────────┤ │                      │
│ │ Q2: 证明...          │ │  ...                 │
│ │ [✓] 主观题 hard      │ │                      │
│ └──────────────────────┘ │                      │
│                          │ [Input]              │
│ [全选] [存入题库]        │                      │
│ [ARC 精修选中题]         │                      │
└──────────────────────────┴──────────────────────┘
```

## Agent 架构

工作台复用 **Bot + BotRegistry + chat_dispatch + tool_executor** 基础设施：

| 组件 | 位置 | 职责 |
|------|------|------|
| Bot | `ai_assistant/models.py` (`bot_type='exam_generator'`) | 出题助手 Bot |
| BotRegistry | `ai_assistant/bot_registry.py` | 注册表：bot_type → (Executor, tools, prompt_dir) |
| chat_dispatch | `ai_assistant/services/chat_dispatch.py` | 统一调度：3 个入口共用 |
| Prompt 模板 | `prompts/ai_assistant/bots/exam_generator/` | system_prompt.txt + tool_guide.txt + personality.txt |
| ToolExecutor | `ai_assistant/services/exam_generator_tool_executor.py` | 5 个出题专用工具的执行器 |
| Seed 命令 | `ai_assistant/management/commands/seed_exam_agent.py` | 创建/更新出题助手 Bot（prompt 从文件读取） |

### 工具列表

| 工具 | 用途 | 模式 |
|------|------|------|
| `search_knowledge_points` | 搜索可用知识点（按名称+学科） | 同步 |
| `generate_questions` | 快速管线出题（~10 秒） | 同步 |
| `launch_arc_pipeline` | 启动 ARC 精修管线（2-5 分钟） | 异步 Celery |
| `check_pipeline_status` | 查询 ARC 管线进度 | 同步 |
| `save_questions_to_library` | 将题目存入机构题库 | 同步 |

继承自 `AssistantToolExecutor` 的基础工具（`search_knowledge_tree`、`get_user_weak_points` 等）也可用。

### 对话式指令

Agent 识别口语化指令，直接调用对应工具，不反问确认：

| 用户说 | Agent 做 |
|--------|----------|
| "入库" / "保存" / "存入题库" | `save_questions_to_library` |
| "ARC精修" / "精修一下" | `launch_arc_pipeline` |
| "看看进度" / "跑完没" | `check_pipeline_status` |
| "再来一组" / "换XX出题" | 重新 `search_knowledge_points` + `generate_questions` |
| "难度改成hard" / "加到10题" | 用新参数重新 `generate_questions` |

## 消息 Metadata

`AIChatMessage.metadata` (JSONField) 承载工具产出的结构化数据：

```json
{
  "generated_questions": [
    {"question": "...", "q_type": "objective", "difficulty_level": "normal", "kp_name": "极限", "answer_preview": "..."},
    ...
  ],
  "pipeline_task_id": 42
}
```

前端通过 `GET /ai/history/` 获取消息列表，从 `metadata` 中提取题目渲染到左侧面板，提取 `pipeline_task_id` 显示进度。

### 跨轮次缓存

`process_ai_chat` 在每次调用时从最近一条助手消息的 `metadata` 中恢复 `tool_executor._last_generated`，使"入库"等指令在后续对话轮次中仍能找到之前生成的题目。

## 核心流程

### 快速出题

```
教师: "出10道微积分极限的客观题"
  ↓ Agent 调用 search_knowledge_points → 获取知识点 ID
  ↓ Agent 调用 generate_questions → 同步生成题目
  ↓ metadata.generated_questions 写入消息
  ↓ 前端轮询 GET /ai/history/ → 渲染题目卡片到左侧面板
教师: "入库"
  ↓ Agent 调用 save_questions_to_library → 题目存入 Question 表
```

### ARC 精修

```
教师: "精修一下"
  ↓ Agent 调用 launch_arc_pipeline → 返回 task_id
  ↓ metadata.pipeline_task_id 写入消息
  ↓ 前端显示 PipelineProgress 组件，轮询 /quizzes/workbench/tasks/{id}/status/
  ↓ ARC 4-Agent 管线（Author→Reviewer→Revise→Classifier）异步执行
教师: "看看进度"
  ↓ Agent 调用 check_pipeline_status → 返回进度信息
```

## 路由

- 路径：`/workbench`
- 权限：`RequireInstitution`（teacher/owner/admin）
- HomeRedirect：teacher/owner → `/workbench`（所有方案级别）
- 侧边栏：institution admin 首位入口

## 前端组件

| 组件 | 文件 | 说明 |
|------|------|------|
| Workbench | `pages/Workbench.tsx` | 主页面，空状态 / 对话状态两态切换 |
| QuestionPanel | `pages/workbench/QuestionPanel.tsx` | 左侧题目卡片列表 + 全选/入库/ARC精修操作栏 |
| PipelineProgress | `pages/workbench/PipelineProgress.tsx` | ARC 管线 4 阶段 stepper + 实时进度条 |
| QuestionReviewCard | `pages/workbench/QuestionReviewCard.tsx` | 单题展示（复用于 QuestionPanel） |

## 相关模型

- `Bot` (`bot_type='exam_generator'`) — 出题助手 Bot 定义
- `AIChatMessage` (`metadata`) — 消息级结构化数据
- `Question` — 生成的题目（入库后）
- `ContentPipelineTask` — ARC 异步任务跟踪
- `KnowledgePoint` — 知识点（搜索目标）

## ARC 管线详情

见 [AI_MULTI_AGENT_PIPELINE.md](./AI_MULTI_AGENT_PIPELINE.md)
