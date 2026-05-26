# 多步可见 Agent 设计

> 状态：待实施 | 日期：2026-05-26

## 目标

让 exam_generator（出题助手）和 planner（小宇）的 agent 执行过程对用户可见——每一步 tool call 的名称、参数摘要、结果摘要实时推送到前端，以折叠卡片形式展示，消除等待空白感。

## 非目标

- 通用助教（assistant bot）保持现状
- 中间步骤不持久化到 DB，仅当前 WebSocket 会话可见
- 不改变现有 agent 循环逻辑（max 5 轮），只增加可见性

---

## 架构

```
用户发消息
  → 前端 WebSocket 发送 {message, bot_id}
  → WS Consumer 调用 chat_service，传入 on_step 回调
  → call_ai_with_tools 循环：
      每轮 LLM 调用（流式 SSE）
        → 如果返回 tool_call：
            发送 step(status=calling) → 执行 tool → 发送 step(status=done)
        → 如果返回文本：
            逐 token 发送 text_delta
      循环结束 → 发送 done(full_content)
  → 前端逐步渲染折叠卡片 + 流式文本
```

---

## WebSocket 消息协议

### 服务端 → 客户端

```typescript
type AgentEvent =
  | {
      type: "step";
      call_id: string;        // tool call 唯一 ID，用于配对 calling→done
      step: number;           // 第几轮（从 1 开始）
      status: "calling" | "done";
      name: string;           // tool 名称，如 "search_knowledge_tree"
      label: string;          // 中文描述，如 "检索「导数」相关知识点"
      args_summary?: string;  // 参数 JSON 摘要（可选，前端折叠显示）
      result_summary?: string; // 结果摘要（仅 status=done 时，前端折叠显示）
    }
  | { type: "text_delta"; delta: string }           // 单个 token
  | { type: "thinking"; content: string }            // 模型思考内容（如果支持）
  | { type: "done"; full_content: string }           // 完整最终文本
  | { type: "error"; message: string }               // 错误
```

### 客户端 → 服务端

```typescript
type AgentMessage = { message: string; bot_id: number }
```

---

## 后端改动

### 1. `call_ai_with_tools` 增加回调 + 流式消费

**文件**: `backend/ai_engine/service.py`

改动 `call_ai_with_tools` 方法签名，增加 `on_step` 回调参数。内部改为流式调用 LLM（`stream=True`），通过 `_consume_stream` 方法消费 SSE stream，区分 tool_call chunks 和 text chunks：

- tool_call chunks → 执行 tool，发送 step 事件
- text chunks → 通过 on_step 发送 text_delta 事件

新增 `_consume_stream(cls, stream, on_step)` 类方法：读取 SSE stream，累积 tool_calls 和 text，text chunk 实时通过 `on_step` 推送。

### 2. Step Label 生成

**文件**: `backend/ai_assistant/services/tool_executor.py`（或新建 `step_labels.py`）

新增 `generate_step_label(tool_name: str, args: dict) -> str` 函数，根据 tool name 和 args 动态生成中文描述。

示例映射：

| tool_name | args | label |
|-----------|------|-------|
| `search_knowledge_tree` | `{query: "导数"}` | "检索「导数」相关知识点" |
| `get_user_wrong_questions` | `{topic: "三角函数"}` | "查看你的三角函数错题" |
| `generate_questions` | `{knowledge_point_ids: [1,2,3], count: 5}` | "基于 3 个知识点生成 5 道题" |
| `search_questions` | `{difficulty: "hard", limit: 10}` | "搜索 10 道高难度题目" |
| `run_arc_pipeline` | `{question_ids: [42]}` | "启动题目审查（ARC 管线）" |
| `get_study_stats` | `{}` | "获取学习统计数据" |
| `get_due_reviews` | `{days: 7}` | "查询未来 7 天的复习任务" |

### 3. WebSocket Consumer

**新建文件**: `backend/ai_assistant/consumers.py`

```python
class AgentChatConsumer(AsyncWebsocketConsumer):
    """通用 agent WS consumer，根据 bot_id 路由到对应 executor"""

    async def connect(self):
        self.bot_id = self.scope['url_route']['kwargs']['bot_id']
        self.user = self.scope['user']
        if self.user.is_anonymous:
            await self.close(code=4001)
            return
        await self.accept()

    async def disconnect(self, code):
        pass  # 清理（如有）

    async def receive(self, text_data):
        data = json.loads(text_data)
        message = data['message']
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._run_agent, message)

    def _run_agent(self, message: str):
        """同步方法，在线程池中执行完整的 agent loop"""
        import asyncio
        loop = asyncio.new_event_loop()

        def on_step(event: dict):
            asyncio.run_coroutine_threadsafe(
                self.send(text_data=json.dumps(event, ensure_ascii=False)),
                loop
            )

        try:
            # 1. 保存用户消息
            # 2. 加载历史、构建 messages
            # 3. 选择 ToolExecutor（根据 bot.bot_type）
            # 4. 调用 call_ai_with_tools(on_step=on_step)
            # 5. 发送 done 事件
            # 6. 保存最终消息到 DB
        except Exception as e:
            on_step({"type": "error", "message": str(e)})
```

### 4. ASGI 路由

**文件**: `backend/school_system/asgi.py` 或 `backend/ai_assistant/urls.py`

新增 WebSocket 路由：
```python
path("ws/ai/chat/<int:bot_id>/", AgentChatConsumer.as_asgi())
```

### 5. 标签生成集成

在 `tool_executor.py` 的 `__call__` 方法中，执行 tool 前后分别调用 `on_step`（如果提供了的话）。executor 初始化时接收 `on_step` 回调。

---

## 前端改动

### 1. `useAgentChat` Hook

**新建文件**: `frontend/src/hooks/useAgentChat.ts`

```typescript
function useAgentChat(botId: number) {
  const [steps, setSteps] = useState<AgentStep[]>([])
  const [streamingText, setStreamingText] = useState("")
  const [isDone, setIsDone] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const wsRef = useRef<WebSocket>()

  const sendMessage = (message: string) => {
    reset()
    const ws = new WebSocket(`${wsBaseUrl}/ws/ai/chat/${botId}/`)
    ws.onmessage = (e) => {
      const event = JSON.parse(e.data)
      switch (event.type) {
        case "step":
          setSteps(prev => upsertStep(prev, event))
          break
        case "text_delta":
          setStreamingText(prev => prev + event.delta)
          break
        case "done":
          setStreamingText(event.full_content)
          setIsDone(true)
          break
        case "error":
          setError(event.message)
          break
      }
    }
    ws.onopen = () => ws.send(JSON.stringify({ message }))
    wsRef.current = ws
  }

  const reset = () => {
    setSteps([])
    setStreamingText("")
    setIsDone(false)
    setError(null)
    wsRef.current?.close()
  }

  return { steps, streamingText, isDone, error, sendMessage, reset }
}
```

### 2. `AgentStepCard` 组件

**新建文件**: `frontend/src/components/AgentStepCard.tsx`

折叠卡片组件，接收 `AgentStep` 数据：
- 收起状态：显示 status icon（✓ spinner ○）+ label
- 展开状态：显示 args_summary + result_summary
- `calling` 状态：spinner 动画
- `done` 状态：绿色勾 + 结果摘要

### 3. 对话流整合

**修改文件**: `frontend/src/pages/AIAssistant.tsx`（或对应 bot 的页面）

消息渲染逻辑：
1. 当前活跃的 agent 会话（WS 连接中）：渲染 steps + streamingText
2. 历史消息：保持现有渲染方式（只显示最终 content）
3. 发送消息后，切换到 agent 模式；done 之后，将最终消息加入历史列表

---

## 文件清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 改 | `backend/ai_engine/service.py` | `call_ai_with_tools` 增加 on_step 回调 + 流式消费 |
| 改 | `backend/ai_assistant/services/tool_executor.py` | executor 接收 on_step 回调，执行前后发送事件；新增 label 生成 |
| 新 | `backend/ai_assistant/consumers.py` | WebSocket consumer |
| 改 | `backend/school_system/asgi.py` | 注册 WS 路由 |
| 新 | `frontend/src/hooks/useAgentChat.ts` | WebSocket hook |
| 新 | `frontend/src/components/AgentStepCard.tsx` | 折叠卡片组件 |
| 改 | `frontend/src/pages/AIAssistant.tsx`（或 bot 页面） | 整合 agent 步骤渲染 |

---

## 不做的事

- 中间步骤不存 DB，刷新页面后只保留最终消息
- 不改通用助教（assistant bot）
- 不改现有 agent 循环逻辑（max 5 轮、tool_choice 策略）
- 不引入 async 重写——保持同步 agent loop + 回调模式
