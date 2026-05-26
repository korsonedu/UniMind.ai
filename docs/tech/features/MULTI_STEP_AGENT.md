# Multi-Step Visible Agent（多步可见 Agent）

> 2026-05-26 实施完成

## 概述

exam_generator（出题助手）和 planner（小宇学习规划）升级为**多步可见 Agent**——用户发消息后，Agent 的每一步 tool call（搜索知识点、生成题目、审查等）实时以折叠卡片形式展示在对话流中，最终文本回复逐 token 流式输出。

**对比改动前：**

| | 改动前 | 改动后 |
|---|---|---|
| 中间步骤 | `[Thinking...]` 转圈等待 | 每步显示中文描述 + 可展开详情 |
| 文本回复 | 一次性返回 | 逐 token 流式输出 |
| 通信方式 | HTTP Polling（2s 间隔） | WebSocket 实时推送 |
| 等待体验 | 10-30s 看不到任何进展 | 随时知道 Agent 在做什么 |

## 业务价值

- **消除等待焦虑**：用户看到"正在检索「导数」相关知识点"、"正在基于 3 个知识点生成 5 道题"等具体步骤，而不是空白等待
- **建立信任**：透明的执行过程让用户理解 Agent 在做什么，增加对 AI 结果的信任
- **调试可见性**：出题过程中每步 tool call 的参数和结果可展开查看，方便教师验证 AI 行为

## 适用范围

| Bot | 是否升级 | 原因 |
|-----|----------|------|
| exam_generator（出题助手） | ✅ | 出题流程多步（搜索→生成→审查→修改），最需要可见性 |
| planner（小宇） | ✅ | 查询学习数据、制定计划，多步 tool call |
| assistant（通用助教） | ❌ | 保持现有简单对话模式 |

## 技术架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend (React)                         │
│                                                                 │
│  AIAssistant.tsx                                                │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  useAgentChat(botId)                                    │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │    │
│  │  │  steps[] │ │ streaming│ │ isDone   │ │ error    │   │    │
│  │  │          │ │ Text     │ │          │ │          │   │    │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘   │    │
│  └───────────────────┬─────────────────────────────────────┘    │
│                      │ WebSocket                                 │
│                      ▼                                          │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  AgentStepCard × N        <ChatMessage streamingText /> │    │
│  │  ✓ 检索「导数」知识点     "首先，导数的定义是..."        │    │
│  │  ⟳ 生成 5 道题...                                       │    │
│  │  ○ 启动 ARC 审查                                        │    │
│  └─────────────────────────────────────────────────────────┘    │
└────────────────────────┬────────────────────────────────────────┘
                         │ ws://host/ws/ai/chat/{bot_id}/
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Backend (Django Channels)                     │
│                                                                 │
│  AgentChatConsumer (AsyncWebsocketConsumer)                     │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  _run_agent(message)        [线程池执行]                 │    │
│  │    │                                                     │    │
│  │    ├─ 1. 保存用户消息到 DB                               │    │
│  │    ├─ 2. 加载历史 10 条 + 构建上下文                     │    │
│  │    ├─ 3. 选择 ToolExecutor (planner/exam_gen)            │    │
│  │    ├─ 4. AIService.chat_with_assistant_agent(            │    │
│  │    │      on_step=callback)                              │    │
│  │    │      │                                              │    │
│  │    │      ▼                                              │    │
│  │    │  call_ai_with_streaming_tools()                     │    │
│  │    │    for round in max(5):                             │    │
│  │    │      ├─ stream LLM → text_delta events             │    │
│  │    │      ├─ if tool_call:                               │    │
│  │    │      │    ├─ on_step(step_calling) → WS push        │    │
│  │    │      │    ├─ execute tool                           │    │
│  │    │      │    └─ on_step(step_done) → WS push           │    │
│  │    │      └─ if text: on_step(text_delta) → WS push     │    │
│  │    │                                                     │    │
│  │    ├─ 5. on_step(done) → WS push                        │    │
│  │    ├─ 6. 保存最终消息到 DB                               │    │
│  │    └─ 7. 异步提取记忆                                    │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

## WebSocket 消息协议

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
  args_summary?: string;    // 参数 JSON（可选，前端折叠显示）
  result_summary?: string;  // 结果摘要（仅 status=done）
}

// 文本 token（逐字符流式）
{ type: "text_delta"; delta: string }

// 完成事件（携带完整最终文本，用于存 DB 和消息列表）
{ type: "done"; full_content: string }

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

## 文件清单

### 新增文件

| 文件 | 说明 |
|------|------|
| `backend/ai_assistant/consumers.py` | WebSocket Consumer，agent loop 在线程池中执行 |
| `backend/ai_assistant/routing.py` | WS 路由 `ws/ai/chat/<bot_id>/` |
| `frontend/src/hooks/useAgentChat.ts` | WebSocket hook（连接管理、状态维护、事件解析） |
| `frontend/src/components/AgentStepCard.tsx` | 折叠卡片组件（状态图标、label、可展开详情） |

### 修改文件

| 文件 | 改动 |
|------|------|
| `backend/ai_engine/service.py` | 新增 `call_ai_with_streaming_tools()` 方法（流式 agent 循环 + on_step 回调） |
| `backend/ai_engine/ai_service.py` | AIService facade 透传 `on_step` 参数 |
| `backend/ai_assistant/services/chat_service.py` | `chat_with_assistant_agent` 根据 on_step 路由到流式/非流式 |
| `backend/ai_assistant/services/tool_executor.py` | 新增 `generate_step_label()` 函数（22 个 tool 的中文标签） |
| `backend/school_system/asgi.py` | 注册 `ai_assistant_ws` 路由 |
| `frontend/src/pages/AIAssistant.tsx` | 集成 agent 步骤渲染 + 流式文本 |

## 数据流（一次完整请求）

```
用户输入 "帮我出 5 道导数题"
  │
  ▼
前端 WebSocket 发送 {message: "帮我出 5 道导数题", bot_id: 5}
  │
  ▼
AgentChatConsumer.receive()
  │
  ├─ 保存用户消息到 AIChatMessage
  ├─ 加载最近 10 条历史
  ├─ 选择 ExamGeneratorToolExecutor
  │
  ▼
AIEngine.call_ai_with_streaming_tools(on_step=callback)
  │
  ├─ Round 1: LLM 流式返回 → tool_call: search_knowledge_tree({query:"导数"})
  │   ├─ WS push: step(calling) "检索「导数」相关知识点"
  │   ├─ 执行 ORM 查询
  │   └─ WS push: step(done) "检索「导数」相关知识点" + result_summary
  │
  ├─ Round 2: LLM 流式返回 → tool_call: generate_questions({kp_ids:[...], count:5})
  │   ├─ WS push: step(calling) "基于 3 个知识点生成 5 道题"
  │   ├─ 调用 AI 出题
  │   └─ WS push: step(done) + result_summary
  │
  ├─ Round 3: LLM 流式返回 → 文本 "好的，我为你生成了 5 道导数题..."
  │   ├─ WS push: text_delta "好"
  │   ├─ WS push: text_delta "的"
  │   ├─ WS push: text_delta "，"
  │   └─ ... (逐 token)
  │
  └─ 无更多 tool_call → 返回 {content: "好的，我为你生成了..."}
      │
      ▼
  WS push: done(full_content="好的，我为你生成了...")
  保存最终消息到 AIChatMessage
  异步提取记忆
```

## 前端组件结构

```
AIAssistant.tsx
├── useAgentChat(botId) hook
│   ├── steps: AgentStep[]       ← 实时步骤列表
│   ├── streamingText: string    ← 流式累积文本
│   ├── isDone: boolean          ← 是否完成
│   ├── isConnected: boolean     ← WS 是否连接中
│   ├── sendMessage(msg)         ← 发起请求
│   └── reset()                  ← 清理状态
│
├── 渲染逻辑
│   ├── agentChat.steps → AgentStepCard × N
│   ├── agentChat.streamingText → <ChatMessage />
│   └── messages (历史) → <ChatMessage /> × N
│
└── AgentStepCard.tsx
    ├── 状态图标: ✓(done) / ⟳(calling) / ○(waiting)
    ├── label: 中文步骤描述
    └── 折叠详情: args_summary + result_summary
```

## 注意事项

- 中间步骤**不持久化**到 DB，刷新页面后只保留最终消息
- WS 连接断开时前端无自动重连（单次请求-响应模式）
- agent loop 最多 5 轮（`max_tool_rounds=5`），与非流式版本一致
- `call_ai_with_tools` 保持不变，供不需要流式的调用方使用
