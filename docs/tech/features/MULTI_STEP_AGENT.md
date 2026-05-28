# Multi-Step Visible Agent（多步可见 Agent）

> 2026-05-26 实施，2026-05-27 流式修复 + 自定义指标卡片，2026-05-28 简化为逐步气泡模式

## 概述

exam_generator（出题助手）和 planner（小宇学习规划）升级为**多步可见 Agent**——用户发消息后，Agent 的每一步 tool call 以独立气泡逐步展示在对话流中，最终文本回复作为独立气泡出现在最后。

**对比改动前：**

| | 改动前 | 改动后 |
|---|---|---|
| 中间步骤 | `[Thinking...]` 转圈等待 | 每步独立气泡，显示中文描述 + 状态图标 |
| 文本回复 | 一次性返回 | 作为独立气泡在所有步骤后出现 |
| 通信方式 | HTTP Polling（2s 间隔） | WebSocket（exam_gen）/ SSE（小宇）实时推送 |
| 等待体验 | 10-30s 看不到任何进展 | 步骤卡片逐步出现，随时知道 Agent 在做什么 |
| Dashboard | 固定区块 | AI 可创建自定义指标卡片 |

## 业务价值

- **消除等待焦虑**：用户看到"正在检索「导数」相关知识点"、"正在基于 3 个知识点生成 5 道题"等具体步骤，而不是空白等待
- **建立信任**：透明的执行过程让用户理解 Agent 在做什么，增加对 AI 结果的信任
- **逐步呈现**：步骤卡片以 600ms 间隔逐步出现，模拟自然对话节奏
- **AI 定制化**：小宇可根据学生数据创建个性化指标卡片（如"本周学习概览"、"薄弱点统计"），呈现在 Dashboard 中间栏

## 适用范围

| Bot | 是否升级 | 通信方式 | 原因 |
|-----|----------|----------|------|
| exam_generator（出题助手） | ✅ | WebSocket | 出题流程多步（搜索→生成→审查→修改），最需要可见性 |
| planner（小宇） | ✅ | SSE (HTTP Streaming) | 查询学习数据、制定计划，多步 tool call + 自定义卡片 |
| assistant（通用助教） | ❌ | HTTP Polling | 保持现有简单对话模式 |

## 技术架构

### 通信路径

| Bot | 通信方式 | 端点 | 原因 |
|-----|----------|------|------|
| exam_generator | WebSocket | `ws/ai/chat/<bot_id>/` | 教师端，需要持久连接 |
| planner (小宇) | SSE (HTTP Streaming) | `POST /api/ai/chat/stream/` | 学生端，复用现有 HTTP 基础设施 |

### 共享核心

两条路径共用同一个 `AIEngine.call_ai_with_streaming_tools()` 方法：
- 流式 SSE 解析 LLM 响应
- 捕获 `reasoning_content`（DeepSeek thinking 模式回传要求）
- 重建 assistant message 时 `tool_calls` 包含 `"type": "function"`
- `on_step` 回调推送 step 事件（calling/done）

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend (React)                         │
│                                                                 │
│  XiaoYu.tsx / AIAssistant.tsx                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  messages: Message[]                                    │    │
│  │  每条 message 可含 toolStep (AgentStep)                  │    │
│  │  渐进渲染: visible 字段 + 600ms 延迟                     │    │
│  └───────────────────┬─────────────────────────────────────┘    │
│                      │ SSE / WebSocket                           │
│                      ▼                                          │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  步骤 1: ✓ 检索「导数」知识点                            │    │
│  │  步骤 2: ✓ 基于 3 个知识点生成 5 道题                    │    │
│  │  步骤 3: ⟳ 启动 ARC 审查...                              │    │
│  │  ──────────────────────────────                          │    │
│  │  最终回复: "好的，我为你生成了 5 道导数题..."             │    │
│  └─────────────────────────────────────────────────────────┘    │
└────────────────────────┬────────────────────────────────────────┘
                         │ SSE: POST /api/ai/chat/stream/
                         │ WS:  ws://host/ws/ai/chat/{bot_id}/
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Backend (Django + Daphne)                     │
│                                                                 │
│  AIChatStreamView / AgentChatConsumer                           │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  _sync_setup() → dispatch_bot_chat_sync()              │    │
│  │    ├─ 加载历史 10 条 + 构建上下文                        │    │
│  │    ├─ BotRegistry 选择 ToolExecutor + tools              │    │
│  │    └─ 构建 messages + system prompt（文件模板）           │    │
│  │                                                         │    │
│  │  _run_agent() → dispatch_bot_chat()                     │    │
│  │    │                                                     │    │
│  │    └─ call_ai_with_streaming_tools()                     │    │
│  │         for round in max(5):                            │    │
│  │           ├─ stream LLM response                        │    │
│  │           ├─ if tool_call:                               │    │
│  │           │    ├─ on_step(step_calling) → queue          │    │
│  │           │    ├─ execute tool                           │    │
│  │           │    └─ on_step(step_done) → queue             │    │
│  │           └─ if no tool_call: return text                │    │
│  │                                                         │    │
│  │  async generate()           [asyncio.Queue → SSE]       │    │
│  │    └─ yield events from queue in real-time              │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

## 消息协议

### 服务端 → 客户端

```typescript
// 步骤事件（同一个 call_id 发两次：calling → done）
{
  type: "step";
  call_id: string;          // tool call 唯一 ID
  step: number;             // 第几轮（从 1 开始）
  status: "calling" | "done";
  name: string;             // tool 名称，如 "search_knowledge_tree"
  label: string;            // 中文描述，如 "检索「导数」相关知识点"
  args_summary?: string;    // 参数 JSON（仅 status=calling）
  result_summary?: string;  // 结果摘要（仅 status=done）
}

// 完成事件（携带完整最终文本，用于存 DB 和消息列表）
{ type: "done"; full_content: string; is_error?: boolean }

// 错误事件
{ type: "error"; message: string }
```

### 客户端 → 服务端

```typescript
{ message: string; bot_id: number }
```

## Step Label 映射

每个 tool call 的中文描述由 `generate_step_label()` 动态生成：

| tool_name | 示例 label |
|-----------|-----------|
| `search_knowledge_tree` | 检索「导数」相关知识点 |
| `get_user_wrong_questions` | 查看三角函数错题 |
| `generate_questions` | 基于 3 个知识点生成 5 道题 |
| `launch_arc_pipeline` | 启动题目审查（ARC 管线） |
| `get_learning_stats` | 获取学习统计数据 |
| `get_due_reviews` | 查询未来 7 天的复习任务 |
| `search_courses` | 搜索课程「高等数学」 |
| `search_knowledge_points` | 搜索知识点「货币银行学」 |
| `create_indicator_card` | 创建自定义指标卡片（小宇专用） |

## 文件清单

### 新增文件

| 文件 | 说明 |
|------|------|
| `backend/ai_assistant/consumers.py` | WebSocket Consumer，agent loop 在线程池中执行 |
| `backend/ai_assistant/routing.py` | WS 路由 `ws/ai/chat/<bot_id>/` |
| `frontend/src/hooks/useAgentChat.ts` | WebSocket hook（连接管理、状态维护、事件解析） |
| `frontend/src/components/AgentStepCard.tsx` | 折叠卡片组件（状态图标、label、可展开详情） |
| `frontend/src/pages/xiaoyu/DashboardPanel.tsx` | Dashboard 面板（含 `IndicatorCards` 自定义指标组件） |

### 修改文件

| 文件 | 改动 |
|------|------|
| `backend/ai_engine/service.py` | `call_ai_with_streaming_tools()` 流式 agent 循环 + `reasoning_content` 捕获 + `type:function` |
| `backend/ai_engine/tools.py` | 新增 `CREATE_INDICATOR_CARD_SCHEMA`，注册到 planner tools |
| `backend/ai_engine/tool_permissions.py` | free plan 新增 planner 基础工具（之前为空） |
| `backend/ai_engine/ai_service.py` | AIService facade 透传 `on_step` 参数 |
| `backend/ai_assistant/services/chat_service.py` | `chat_with_assistant_agent` 根据 on_step 路由到流式/非流式；prompt 从文件模板加载（见 PROMPT_MANAGEMENT_SYSTEM.md） |
| `backend/ai_assistant/bot_registry.py` | Bot 注册表：bot_type → (Executor, tools, prompt_dir) |
| `backend/ai_assistant/services/chat_dispatch.py` | 统一调度：3 个入口共用，消除重复的 if/elif |
| `backend/ai_assistant/services/tool_executor.py` | `generate_step_label()` + `summarize_tool_result()` + `_handle_create_indicator_card` |
| `backend/ai_assistant/views.py` | SSE async generator（`sync_to_async` 包装 ORM 操作，`asyncio.Queue` 实时 yield） |
| `backend/ai_assistant/views_dashboard.py` | 返回 `custom_cards` 字段 |
| `backend/school_system/asgi.py` | 注册 `ai_assistant_ws` 路由 |
| `frontend/src/pages/AIAssistant.tsx` | 集成 agent 步骤渲染 |
| `frontend/src/pages/XiaoYu.tsx` | SSE 解析 step 事件，逐步气泡渲染 + inline 指标卡片 |

## 数据流（一次完整请求）

```
用户输入 "帮我出 5 道导数题"
  │
  ▼
前端 SSE POST /api/ai/chat/stream/ {message: "帮我出 5 道导数题", bot_id: 5}
  │
  ▼
AIChatStreamView.post()
  │
  ├─ 保存用户消息到 AIChatMessage
  ├─ sync_to_async(_sync_setup): 加载历史 + 构建上下文 + 选择 ToolExecutor
  │
  ▼
后台线程: AIEngine.call_ai_with_streaming_tools(on_step=callback)
  │
  ├─ Round 1: LLM 流式返回 → tool_call: search_knowledge_tree({query:"导数"})
  │   ├─ SSE: step(calling) "检索「导数」相关知识点"
  │   ├─ 执行 ORM 查询
  │   └─ SSE: step(done) + result_summary
  │
  ├─ Round 2: LLM 流式返回 → tool_call: generate_questions({kp_ids:[...], count:5})
  │   ├─ SSE: step(calling) "基于 3 个知识点生成 5 道题"
  │   ├─ 调用 AI 出题
  │   └─ SSE: step(done) + result_summary
  │
  └─ Round 3: 无 tool_call → 返回 {content: "好的，我为你生成了..."}
      │
      ▼
  SSE: done(full_content="好的，我为你生成了...")
  保存最终消息到 AIChatMessage
  异步提取记忆
```

## 前端组件结构

```
XiaoYu.tsx
├── messages: Message[]
│   ├── role: 'user' | 'assistant'
│   ├── content: string
│   ├── toolStep?: AgentStep     ← 工具步骤数据
│   └── visible?: boolean        ← 渐进渲染控制
│
├── SSE 事件处理
│   ├── step(calling) → 新增 message (toolStep + visible:false)
│   ├── step(done)    → 按 call_id 匹配更新 toolStep
│   ├── done          → 新增最终文本 message
│   └── 渐进渲染: scheduleShow() 600ms 间隔
│
└── 渲染逻辑
    ├── toolStep message → ToolStepMessage (AgentStepCard)
    └── 普通 message     → ChatBubble

AgentStepCard.tsx
├── 状态图标: ✓(done) / ⟳(calling) / ○(waiting)
└── label: 中文步骤描述
```

## 自定义指标卡片（create_indicator_card）

小宇可通过 `create_indicator_card` 工具在 Dashboard 中创建个性化指标卡片。

**工具 Schema**：
```json
{
  "title": "本周学习概览",
  "indicators": [
    {"name": "做题量", "value": "120", "trend": "up"},
    {"name": "正确率", "value": "85%", "trend": "neutral"},
    {"name": "薄弱知识点", "value": "3 个", "trend": "down"}
  ]
}
```

**数据流**：
1. AI 调用 `create_indicator_card` → `PlannerToolExecutor._handle_create_indicator_card`
2. 卡片数据持久化到 `user.dashboard_config['custom_cards']`（保留最近 10 张）
3. SSE step event 携带完整卡片 JSON（`result_summary`）
4. 前端 `XiaoYu.tsx` 解析 step event，实时渲染 inline 指标卡片
5. `done` 事件触发 `fetchDashboard()`，Dashboard 面板的 `IndicatorCards` 组件也渲染卡片

**渲染位置**：
- 聊天区域：inline 卡片（实时，当次对话有效）
- Dashboard 中间栏：`IndicatorCards` 组件（持久化，刷新后仍在）

## 注意事项

- 中间步骤**不持久化**到 DB，刷新页面后只保留最终消息
- `custom_cards` **持久化**到 `user.dashboard_config`，刷新后仍在 Dashboard 中显示
- WS 连接断开时前端无自动重连（单次请求-响应模式）
- SSE 路径（小宇）使用 `threading.Thread` + `asyncio.Queue` + `sync_to_async` 实现实时事件推送（Django 6 ASGI 兼容）
- agent loop 最多 5 轮（`max_tool_rounds=5`），与非流式版本一致
- `call_ai_with_tools`（非流式）和 `call_ai_with_streaming_tools`（流式）均支持 `reasoning_content` 回传
- DeepSeek thinking 模式要求后续轮次完整回传 `reasoning_content`，两个方法均已处理
- planner/exam_generator 的工具调用靠 `tool_choice="required"` + system prompt 驱动。Free plan 的 planner 有 4 个基础工具（`get_learning_stats`/`get_knowledge_mastery_map`/`get_due_reviews`/`search_knowledge_tree`），定义在 `tool_permissions.py`
- 前端渐进渲染：步骤卡片以 600ms 间隔逐步出现，通过 `visible` 字段 + `scheduleShow()` setTimeout 实现
