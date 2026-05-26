# Multi-Step Visible Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make exam_generator and planner bots show their intermediate tool call steps in real-time via WebSocket, with collapsible cards and full-chain text streaming.

**Architecture:** Add an `on_step` callback to `call_ai_with_tools`. Each tool call/result sends a step event. A new WebSocket consumer streams these events to the frontend. The frontend renders `AgentStepCard` components for each step plus streaming text for the final response.

**Tech Stack:** Django Channels (WebSocket), React hooks, existing `AIEngine.call_ai_with_tools` + `call_ai_stream`

---

## File Structure

| Operation | File | Responsibility |
|-----------|------|----------------|
| Modify | `backend/ai_engine/service.py` | Add `call_ai_with_streaming_tools()` — agent loop with streaming + on_step callback |
| Modify | `backend/ai_assistant/services/tool_executor.py` | Add `generate_step_label()`, add `on_step` callback support to executor |
| New | `backend/ai_assistant/consumers.py` | WebSocket consumer for agent chat |
| New | `backend/ai_assistant/routing.py` | WebSocket URL routing |
| Modify | `backend/school_system/asgi.py` | Register new WS routes |
| New | `frontend/src/hooks/useAgentChat.ts` | WebSocket hook for agent chat |
| New | `frontend/src/components/AgentStepCard.tsx` | Collapsible step card component |
| Modify | `frontend/src/pages/AIAssistant.tsx` | Integrate agent step rendering |

---

## Task 1: Step Label Generation

**Files:**
- Modify: `backend/ai_assistant/services/tool_executor.py:1-28`

- [ ] **Step 1: Add `generate_step_label` function**

Add this function at the top of `tool_executor.py`, after the imports:

```python
def generate_step_label(tool_name: str, args: dict) -> str:
    """根据 tool name 和 args 动态生成中文步骤描述。"""
    labels = {
        'search_knowledge_tree': lambda a: f"检索「{a.get('query', '')}」相关知识点",
        'get_user_weak_points': lambda a: "分析你的薄弱知识点",
        'get_user_wrong_questions': lambda a: f"查看{a.get('topic', '')}错题" if a.get('topic') else "查看你的错题记录",
        'get_class_weak_points': lambda a: "分析班级薄弱知识点",
        'get_class_performance_summary': lambda a: "获取班级表现概览",
        'lookup_question': lambda a: f"查找题目（ID: {a.get('question_id', '')}）",
        'get_learning_stats': lambda a: "获取学习统计数据",
        'get_knowledge_mastery_map': lambda a: f"生成{a.get('subject', '')}知识掌握图谱" if a.get('subject') else "生成知识掌握图谱",
        'get_due_reviews': lambda a: f"查询未来{a.get('days', 7)}天的复习任务",
        'get_exam_history': lambda a: "查询考试历史",
        'save_study_plan': lambda a: "保存学习计划",
        'get_active_plan': lambda a: "获取当前学习计划",
        'update_plan_task': lambda a: f"更新计划任务「{a.get('task_id', '')}」",
        'set_dashboard_layout': lambda a: "更新仪表盘布局",
        'search_courses': lambda a: f"搜索课程「{a.get('query', '')}」",
        'search_asr': lambda a: f"搜索视频字幕「{a.get('query', '')}」",
        'search_articles': lambda a: f"搜索文章「{a.get('query', '')}」",
        'search_knowledge_points': lambda a: f"搜索知识点「{a.get('query', '')}」",
        'generate_questions': lambda a: f"基于{len(a.get('knowledge_point_ids', []))}个知识点生成{a.get('count', 5)}道题",
        'launch_arc_pipeline': lambda a: "启动题目审查（ARC 管线）",
        'check_pipeline_status': lambda a: "检查管线执行进度",
        'save_questions_to_library': lambda a: f"保存{len(a.get('question_ids', []))}道题到题库",
    }
    generator = labels.get(tool_name)
    if generator:
        try:
            return generator(args)
        except Exception:
            pass
    return f"执行 {tool_name}"
```

- [ ] **Step 2: Commit**

```bash
git add backend/ai_assistant/services/tool_executor.py
git commit -m "feat: add step label generation for agent tool calls"
```

---

## Task 2: Streaming Agent Loop in AIEngine

**Files:**
- Modify: `backend/ai_engine/service.py:416-471`

- [ ] **Step 1: Add `call_ai_with_streaming_tools` method**

Add this new method to the `AIEngine` class, right after the existing `call_ai_with_tools` method (after line 471). Do NOT modify the existing `call_ai_with_tools` — it stays for non-streaming callers.

```python
@classmethod
def call_ai_with_streaming_tools(cls, messages, tools, tool_executor,
                                  on_step=None, tool_choice="auto",
                                  temperature=0.7, max_tokens=8192,
                                  operation='general', max_tool_rounds=5,
                                  raise_on_error=False):
    """
    多轮 Agent 循环 + 流式输出 + 步骤回调。

    与 call_ai_with_tools 相同逻辑，但：
    1. LLM 调用使用 stream=True，逐 token 推送 text_delta
    2. 每步 tool call/result 通过 on_step 回调推送

    on_step: callable(event_dict) — 接收 step/text_delta/done/error 事件
    返回: {"content": str} 最终文本
    """
    from .config import get_model_for_task
    from .circuit_breaker import AICircuitBreaker, CircuitBreakerError

    all_messages = list(messages)
    accumulated_text = ""

    for round_i in range(max_tool_rounds):
        # ── 流式调用 LLM ──
        config = get_model_for_task(operation)
        if not config['api_key']:
            if on_step:
                on_step({"type": "error", "message": "LLM_API_KEY 未设置"})
            return {"content": ""}

        try:
            AICircuitBreaker.check(operation)
        except CircuitBreakerError:
            if on_step:
                on_step({"type": "error", "message": "AI 服务熔断中，请稍后重试"})
            return {"content": ""}

        body = {
            "model": config['model'],
            "messages": all_messages,
            "temperature": temperature,
            "max_completion_tokens": max_tokens,
            "stream": True,
        }
        if tools is not None:
            body["tools"] = tools
        _is_deepseek = 'deepseek' in config.get('model', '').lower()
        if tool_choice is not None and not _is_deepseek:
            body["tool_choice"] = tool_choice
        if config.get('thinking'):
            body["thinking"] = {"type": "enabled"}

        timeout_seconds = max(30, int(getattr(settings, "LLM_REQUEST_TIMEOUT_SECONDS", 120) or 120))

        try:
            r = _session.post(
                config['base_url'],
                headers={
                    "Authorization": f"Bearer {config['api_key'].strip()}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=timeout_seconds,
                stream=True,
            )
            r.raise_for_status()
        except Exception as e:
            AICircuitBreaker.record_failure(operation)
            if on_step:
                on_step({"type": "error", "message": f"AI 调用失败: {e}"})
            return {"content": accumulated_text or "AI 服务暂时不可用，请稍后重试。"}

        # ── 消费 SSE stream ──
        tool_calls_map = {}  # id -> {id, function: {name, arguments}}
        text_delta_buffer = ""
        finish_reason = None

        for line in r.iter_lines(decode_unicode=True):
            if not line or not line.startswith('data: '):
                continue
            data_str = line[6:]
            if data_str.strip() == '[DONE]':
                break
            try:
                data = json.loads(data_str)
            except json.JSONDecodeError:
                continue

            choice = data.get('choices', [{}])[0]
            delta = choice.get('delta', {})
            finish_reason = choice.get('finish_reason') or finish_reason

            # 文本 token
            content = delta.get('content', '')
            if content:
                accumulated_text += content
                if on_step:
                    on_step({"type": "text_delta", "delta": content})

            # tool_calls chunk（流式拼接）
            for tc_chunk in delta.get('tool_calls', []):
                idx = tc_chunk.get('index', 0)
                if idx not in tool_calls_map:
                    tool_calls_map[idx] = {
                        "id": tc_chunk.get('id', ''),
                        "function": {"name": '', "arguments": ''},
                    }
                tc = tool_calls_map[idx]
                if tc_chunk.get('id'):
                    tc['id'] = tc_chunk['id']
                func_chunk = tc_chunk.get('function', {})
                if func_chunk.get('name'):
                    tc['function']['name'] = func_chunk['name']
                if func_chunk.get('arguments'):
                    tc['function']['arguments'] += func_chunk['arguments']

        AICircuitBreaker.record_success(operation)

        tool_calls = [tool_calls_map[k] for k in sorted(tool_calls_map.keys())] if tool_calls_map else []

        if not tool_calls:
            # 模型不再调用工具，返回最终文本
            return {"content": accumulated_text}

        # ── 执行 tool calls ──
        # 构建 assistant message（含 tool_calls）
        assistant_msg = {"role": "assistant", "content": None, "tool_calls": tool_calls}
        all_messages.append(assistant_msg)

        for tc in tool_calls:
            func = tc.get('function', {})
            name = func.get('name', '')
            call_id = tc.get('id', '')
            try:
                args = json.loads(func.get('arguments', '{}'))
            except (json.JSONDecodeError, TypeError):
                args = {}

            # 生成 label
            try:
                from ai_assistant.services.tool_executor import generate_step_label
                label = generate_step_label(name, args)
            except ImportError:
                label = f"执行 {name}"

            # 发送 step calling 事件
            if on_step:
                on_step({
                    "type": "step",
                    "call_id": call_id,
                    "step": round_i + 1,
                    "status": "calling",
                    "name": name,
                    "label": label,
                    "args_summary": json.dumps(args, ensure_ascii=False)[:200],
                })

            # 执行 tool
            try:
                result = tool_executor(name, args)
            except Exception as e:
                result = json.dumps({"error": str(e)}, ensure_ascii=False)

            # 发送 step done 事件
            if on_step:
                on_step({
                    "type": "step",
                    "call_id": call_id,
                    "step": round_i + 1,
                    "status": "done",
                    "name": name,
                    "label": label,
                    "result_summary": str(result)[:300],
                })

            all_messages.append({
                "role": "tool",
                "tool_call_id": call_id,
                "content": str(result),
            })

        # 重置 text buffer（下一轮会重新累积）
        accumulated_text = ""
        tool_choice = "auto"

    logger.warning(
        "call_ai_with_streaming_tools: exhausted max_tool_rounds=%s",
        max_tool_rounds,
    )
    return {"content": accumulated_text}
```

- [ ] **Step 2: Commit**

```bash
git add backend/ai_engine/service.py
git commit -m "feat: add call_ai_with_streaming_tools with on_step callback"
```

---

## Task 3: Pass on_step Callback Through Chat Service + AIService Facade

**Files:**
- Modify: `backend/ai_assistant/services/chat_service.py:118-158`
- Modify: `backend/ai_engine/ai_service.py:310-319`

- [ ] **Step 1: Add `on_step` parameter to `AIService.chat_with_assistant_agent` facade**

The facade at `backend/ai_engine/ai_service.py:310-319` must also accept and pass `on_step`:

```python
@classmethod
def chat_with_assistant_agent(cls, bot, history_messages, user_message,
                               tool_executor, student_context='',
                               memory_context='', on_step=None):
    from ai_assistant.services.chat_service import AssistantChatService
    return AssistantChatService.chat_with_assistant_agent(
        bot=bot, history_messages=history_messages,
        user_message=user_message, tool_executor=tool_executor,
        student_context=student_context, memory_context=memory_context,
        on_step=on_step,
    )
```

- [ ] **Step 2: Add `on_step` parameter to `chat_with_assistant_agent`**

Replace the `chat_with_assistant_agent` method (lines 118-158) with:

```python
@classmethod
def chat_with_assistant_agent(
    cls,
    bot,
    history_messages,
    user_message,
    tool_executor,
    student_context='',
    memory_context='',
    on_step=None,
):
    """Agent 化对话：模型可自主调用工具获取信息后再回答。"""
    from ai_engine.service import AIEngine

    system_prompt = cls._build_agent_system_prompt(bot, student_context, memory_context)

    messages = [{'role': 'system', 'content': system_prompt}]

    for msg in history_messages or []:
        role = str(msg.get('role', '')).strip()
        content = str(msg.get('content', '')).strip()
        if role in {'user', 'assistant'} and content:
            messages.append({'role': role, 'content': content})

    messages.append({'role': 'user', 'content': user_message})

    if bot and bot.bot_type == 'planner':
        tools = get_planner_tools()
    elif bot and bot.bot_type == 'exam_generator':
        tools = get_exam_generator_tools()
    else:
        tools = get_assistant_tools()

    # 如果有 on_step 回调，使用流式版本
    if on_step:
        return AIEngine.call_ai_with_streaming_tools(
            messages=messages,
            tools=tools,
            tool_executor=tool_executor,
            on_step=on_step,
            tool_choice="auto",
            temperature=0.6,
            max_tokens=2500,
            operation='assistant.chat',
            max_tool_rounds=5,
        )
    else:
        return AIEngine.call_ai_with_tools(
            messages=messages,
            tools=tools,
            tool_executor=tool_executor,
            tool_choice="auto",
            temperature=0.6,
            max_tokens=2500,
            operation='assistant.chat',
            max_tool_rounds=5,
        )
```

- [ ] **Step 3: Commit**

```bash
git add backend/ai_engine/ai_service.py backend/ai_assistant/services/chat_service.py
git commit -m "feat: pass on_step callback through chat service and AIService facade"
```

---

## Task 4: WebSocket Consumer

**Files:**
- New: `backend/ai_assistant/consumers.py`

- [ ] **Step 1: Create the WebSocket consumer**

```python
import json
import logging
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async

logger = logging.getLogger(__name__)


class AgentChatConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for multi-step visible agent chat.
    每步 tool call/result 实时推送给前端，最终文本流式输出。
    """

    async def connect(self):
        self.bot_id = self.scope['url_route']['kwargs']['bot_id']
        self.user = self.scope.get('user')

        if not self.user or not self.user.is_authenticated:
            await self.close(code=4001)
            return

        # 验证 bot 存在且用户有权访问
        bot = await self._get_bot(self.bot_id)
        if not bot:
            await self.close(code=4004)
            return

        self.bot = bot
        await self.accept()

    async def disconnect(self, code):
        pass

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps(
                {"type": "error", "message": "Invalid JSON"},
                ensure_ascii=False,
            ))
            return

        message = data.get('message', '').strip()
        if not message:
            await self.send(text_data=json.dumps(
                {"type": "error", "message": "Empty message"},
                ensure_ascii=False,
            ))
            return

        # 在线程池中运行同步的 agent loop
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(None, self._run_agent, message)
        except Exception as e:
            logger.exception("Agent WS error: %s", e)
            await self.send(text_data=json.dumps(
                {"type": "error", "message": f"Agent 执行失败: {e}"},
                ensure_ascii=False,
            ))

    def _run_agent(self, message: str):
        """同步方法，在线程池中执行完整的 agent loop。"""
        import asyncio as _asyncio
        from .models import AIChatMessage
        from .services.chat_service import AssistantChatService
        from .utils import get_student_academic_context

        loop = _asyncio.new_event_loop()

        def send_sync(event_dict):
            """线程安全地发送 WebSocket 消息。"""
            future = _asyncio.run_coroutine_threadsafe(
                self.send(text_data=json.dumps(event_dict, ensure_ascii=False)),
                loop,
            )
            future.result(timeout=5)

        def on_step(event):
            send_sync(event)

        try:
            # 1. 保存用户消息
            user_msg = self._save_message(self.user, self.bot, 'user', message)

            # 2. 加载历史
            history_limit = 10
            history_objs = AIChatMessage.objects.filter(
                user=self.user, bot=self.bot,
            ).order_by('-timestamp')[:history_limit]
            history_msgs = [
                {"role": h.role, "content": h.content}
                for h in reversed(history_objs)
                if h.content != '[Thinking...]'
            ]

            # 3. 构建上下文
            student_context = ""
            if self.bot.is_exclusive:
                student_context = get_student_academic_context(self.user)

            memory_context = ""
            try:
                from .services.memory_service import get_memories_for_injection
                memory_context = get_memories_for_injection(self.user)
            except Exception:
                pass

            # 4. 选择 tool_executor
            if self.bot.bot_type == 'planner':
                from .services.tool_executor import PlannerToolExecutor
                tool_executor = PlannerToolExecutor(self.user)
            elif self.bot.bot_type == 'exam_generator':
                from .services.exam_generator_tool_executor import ExamGeneratorToolExecutor
                tool_executor = ExamGeneratorToolExecutor(self.user)
                # 恢复题目缓存
                last_with_questions = AIChatMessage.objects.filter(
                    user=self.user, bot=self.bot, role='assistant',
                ).exclude(metadata={}).order_by('-timestamp').first()
                if last_with_questions:
                    cached = last_with_questions.metadata.get('generated_questions')
                    if cached:
                        tool_executor._last_generated = cached
            else:
                from .services.tool_executor import AssistantToolExecutor
                tool_executor = AssistantToolExecutor(self.user)

            # 5. 调用 agent
            from ai_service import AIService
            result = AIService.chat_with_assistant_agent(
                bot=self.bot,
                history_messages=history_msgs,
                user_message=message,
                tool_executor=tool_executor,
                student_context=student_context,
                memory_context=memory_context,
                on_step=on_step,
            )

            # 6. 提取最终文本
            if isinstance(result, dict) and 'content' in result:
                ai_content = result['content']
            elif result and 'choices' in result:
                ai_content = result['choices'][0]['message']['content']
            else:
                ai_content = "AI 助教暂时无法响应，请稍后再试。"

            # 格式化数学
            ai_content = ai_content.replace('\\[', ' $$ ').replace('\\]', ' $$ ')
            ai_content = ai_content.replace('\\(', ' $ ').replace('\\)', ' $ ')

            # 7. 发送 done 事件
            on_step({"type": "done", "full_content": ai_content})

            # 8. 保存最终消息到 DB
            self._save_message(self.user, self.bot, 'assistant', ai_content,
                              metadata=self._build_metadata(tool_executor))

            # 9. 异步提取记忆
            try:
                from .services.memory_service import extract_memories_async
                extract_memories_async(self.user, history_msgs + [{'role': 'user', 'content': message}])
            except Exception:
                pass

        except Exception as e:
            logger.exception("Agent execution error: %s", e)
            on_step({"type": "error", "message": str(e)})

    @database_sync_to_async
    def _get_bot(self, bot_id):
        from .models import Bot
        from users.permissions import is_platform_admin
        try:
            bot = Bot.objects.get(id=bot_id)
            user = self.user
            if is_platform_admin(user):
                return bot
            if bot.is_exclusive and hasattr(user, 'institution') and user.institution:
                if bot.institution == user.institution:
                    return bot
            if not bot.is_exclusive:
                return bot
            return None
        except Bot.DoesNotExist:
            return None

    def _save_message(self, user, bot, role, content, metadata=None):
        from .models import AIChatMessage
        msg = AIChatMessage(user=user, bot=bot, role=role, content=content)
        if metadata:
            msg.metadata = metadata
        msg.save()
        return msg

    def _build_metadata(self, tool_executor):
        metadata = {}
        if hasattr(tool_executor, '_last_generated') and tool_executor._last_generated:
            metadata['generated_questions'] = tool_executor._last_generated
        if hasattr(tool_executor, '_last_pipeline_task_id') and tool_executor._last_pipeline_task_id:
            metadata['pipeline_task_id'] = tool_executor._last_pipeline_task_id
        return metadata or None
```

- [ ] **Step 2: Commit**

```bash
git add backend/ai_assistant/consumers.py
git commit -m "feat: add WebSocket consumer for multi-step agent chat"
```

---

## Task 5: WebSocket Routing

**Files:**
- New: `backend/ai_assistant/routing.py`
- Modify: `backend/school_system/asgi.py`

- [ ] **Step 1: Create routing file**

```python
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/ai/chat/(?P<bot_id>\d+)/$', consumers.AgentChatConsumer.as_asgi()),
]
```

- [ ] **Step 2: Register in ASGI**

Replace the content of `backend/school_system/asgi.py`:

```python
"""
ASGI config for school_system project.
"""

import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "school_system.settings")

django_asgi_app = get_asgi_application()

from interviews.routing import websocket_urlpatterns as interviews_ws
from notifications.routing import websocket_urlpatterns as notifications_ws
from ai_assistant.routing import websocket_urlpatterns as ai_assistant_ws

websocket_urlpatterns = interviews_ws + notifications_ws + ai_assistant_ws

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(websocket_urlpatterns)
    ),
})
```

- [ ] **Step 3: Commit**

```bash
git add backend/ai_assistant/routing.py backend/school_system/asgi.py
git commit -m "feat: register WebSocket routes for agent chat"
```

---

## Task 6: Frontend useAgentChat Hook

**Files:**
- New: `frontend/src/hooks/useAgentChat.ts`

- [ ] **Step 1: Create the hook**

```typescript
import { useState, useRef, useCallback } from 'react';

export interface AgentStep {
  call_id: string;
  step: number;
  status: 'calling' | 'done';
  name: string;
  label: string;
  args_summary?: string;
  result_summary?: string;
}

type AgentEvent =
  | { type: 'step' } & AgentStep
  | { type: 'text_delta'; delta: string }
  | { type: 'done'; full_content: string }
  | { type: 'error'; message: string };

const WS_BASE = import.meta.env.VITE_WS_URL || (
  window.location.protocol === 'https:' ? 'wss://' : 'ws://'
) + window.location.host;

export function useAgentChat(botId: number) {
  const [steps, setSteps] = useState<AgentStep[]>([]);
  const [streamingText, setStreamingText] = useState('');
  const [isDone, setIsDone] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const upsertStep = useCallback((prev: AgentStep[], event: AgentStep): AgentStep[] => {
    const idx = prev.findIndex(s => s.call_id === event.call_id);
    if (idx >= 0) {
      const updated = [...prev];
      updated[idx] = { ...updated[idx], ...event };
      return updated;
    }
    return [...prev, event];
  }, []);

  const sendMessage = useCallback((message: string) => {
    // 清理上一轮状态
    reset();
    setIsConnected(true);

    const ws = new WebSocket(`${WS_BASE}/ws/ai/chat/${botId}/`);
    wsRef.current = ws;

    ws.onopen = () => {
      ws.send(JSON.stringify({ message }));
    };

    ws.onmessage = (e) => {
      try {
        const event: AgentEvent = JSON.parse(e.data);
        switch (event.type) {
          case 'step':
            setSteps(prev => upsertStep(prev, event as AgentStep));
            break;
          case 'text_delta':
            setStreamingText(prev => prev + (event as any).delta);
            break;
          case 'done':
            setStreamingText((event as any).full_content);
            setIsDone(true);
            setIsConnected(false);
            break;
          case 'error':
            setError((event as any).message);
            setIsConnected(false);
            break;
        }
      } catch (err) {
        console.error('Failed to parse WS message:', err);
      }
    };

    ws.onerror = () => {
      setError('WebSocket 连接失败');
      setIsConnected(false);
    };

    ws.onclose = () => {
      setIsConnected(false);
    };
  }, [botId, upsertStep]);

  const reset = useCallback(() => {
    setSteps([]);
    setStreamingText('');
    setIsDone(false);
    setError(null);
    setIsConnected(false);
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  return {
    steps,
    streamingText,
    isDone,
    isConnected,
    error,
    sendMessage,
    reset,
  };
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/hooks/useAgentChat.ts
git commit -m "feat: add useAgentChat WebSocket hook"
```

---

## Task 7: AgentStepCard Component

**Files:**
- New: `frontend/src/components/AgentStepCard.tsx`

- [ ] **Step 1: Create the component**

```tsx
import React, { useState } from 'react';
import { ChevronDown, Check, Loader2, Circle } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { AgentStep } from '@/hooks/useAgentChat';

interface AgentStepCardProps {
  step: AgentStep;
}

export const AgentStepCard: React.FC<AgentStepCardProps> = ({ step }) => {
  const [expanded, setExpanded] = useState(false);

  const icon = step.status === 'done' ? (
    <Check className="h-3.5 w-3.5 text-green-500" />
  ) : step.status === 'calling' ? (
    <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
  ) : (
    <Circle className="h-3.5 w-3.5 text-muted-foreground" />
  );

  const hasDetails = step.args_summary || step.result_summary;

  return (
    <div className={cn(
      "rounded-xl border text-[13px] transition-all",
      step.status === 'calling'
        ? "border-primary/30 bg-primary/5"
        : step.status === 'done'
          ? "border-green-500/20 bg-green-500/5"
          : "border-border bg-muted/50"
    )}>
      <button
        className={cn(
          "w-full flex items-center gap-2.5 px-3.5 py-2.5 text-left",
          hasDetails && "cursor-pointer hover:bg-muted/30",
        )}
        onClick={() => hasDetails && setExpanded(!expanded)}
        disabled={!hasDetails}
      >
        {icon}
        <span className="flex-1 font-medium text-foreground">{step.label}</span>
        {hasDetails && (
          <ChevronDown className={cn(
            "h-3.5 w-3.5 text-muted-foreground transition-transform",
            expanded && "rotate-180",
          )} />
        )}
      </button>

      {expanded && (
        <div className="px-3.5 pb-2.5 space-y-2 border-t border-border/50">
          {step.args_summary && (
            <div className="pt-2">
              <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">参数</span>
              <pre className="mt-1 text-[12px] text-muted-foreground bg-muted rounded-lg p-2 overflow-x-auto">
                {step.args_summary}
              </pre>
            </div>
          )}
          {step.result_summary && (
            <div>
              <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">结果</span>
              <pre className="mt-1 text-[12px] text-muted-foreground bg-muted rounded-lg p-2 overflow-x-auto max-h-40 overflow-y-auto">
                {step.result_summary}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/AgentStepCard.tsx
git commit -m "feat: add AgentStepCard collapsible component"
```

---

## Task 8: Integrate into AIAssistant Page

**Files:**
- Modify: `frontend/src/pages/AIAssistant.tsx`

- [ ] **Step 1: Add imports and hook usage**

Add imports at the top of the file:

```typescript
import { useAgentChat } from '@/hooks/useAgentChat';
import { AgentStepCard } from '@/components/AgentStepCard';
```

Inside the `AIAssistant` component, add the hook (after existing state declarations, around line 39):

```typescript
const agentChat = useAgentChat(selectedBot?.id || 0);
```

- [ ] **Step 2: Modify `doSend` to use WebSocket for agent bots**

Replace the `doSend` function (lines 113-127) with:

```typescript
const doSend = async (text: string) => {
  // 对 exam_generator 和 planner 使用 WebSocket agent 模式
  if (selectedBot && (selectedBot.bot_type === 'exam_generator' || selectedBot.bot_type === 'planner')) {
    // 添加用户消息到列表
    setMessages(prev => [...prev, { role: 'user', content: text }]);
    agentChat.sendMessage(text);
    return;
  }

  // 其他 bot 保持原有 polling 模式
  setLoading(true);
  try {
    await api.post('/ai/chat/', { message: text, bot_id: selectedBot!.id });
    const res = await api.get('/ai/history/', { params: { bot_id: selectedBot!.id } });
    if (res.data.length > 0) {
      setMessages(res.data.map((m: any) => ({ ...m, content: processMathContent(m.content) })));
    }
  } catch (err: any) {
    toast.error(t('sendFailed'));
    setInput(text);
  } finally {
    setLoading(false);
  }
};
```

- [ ] **Step 3: Add agent message rendering**

In the message list rendering section (around lines 179-200), add agent step + streaming text rendering before the regular messages:

```tsx
<div className="p-8 space-y-8 max-w-4xl mx-auto w-full">
  {/* Agent 模式：显示步骤卡片 + 流式文本 */}
  {agentChat.steps.length > 0 && (
    <div className="space-y-3">
      {agentChat.steps.map(step => (
        <AgentStepCard key={step.call_id} step={step} />
      ))}
    </div>
  )}
  {agentChat.streamingText && (
    <ChatMessage
      msg={{ role: 'assistant', content: agentChat.streamingText }}
      isUser={false}
      avatar={selectedBot!.avatar}
      botName={selectedBot!.name}
      userName=""
    />
  )}

  {/* 历史消息（agent done 后也会进入这里） */}
  {messages.filter(msg => msg.content !== '[Thinking...]').map((msg, i) => (
    <ChatMessage
      key={i}
      msg={msg}
      isUser={msg.role === 'user'}
      avatar={selectedBot!.avatar}
      botName={selectedBot!.name}
      userName={user?.nickname || user?.username || 'User'}
    />
  ))}
  {/* Thinking 指示器（非 agent 模式） */}
  {agentChat.steps.length === 0 && messages.length > 0 && messages[messages.length - 1].content === '[Thinking...]' && (
    <ChatMessage
      msg={{ role: 'assistant', content: '' }}
      isUser={false}
      avatar={selectedBot!.avatar}
      botName={selectedBot!.name}
      userName=""
      isThinking
    />
  )}
</div>
```

- [ ] **Step 4: Handle agent done — merge into history**

Add an effect to handle agent completion. When `agentChat.isDone` becomes true, add the final message to the messages list and reset agent state:

```typescript
useEffect(() => {
  if (agentChat.isDone && agentChat.streamingText) {
    setMessages(prev => [...prev, {
      role: 'assistant' as const,
      content: processMathContent(agentChat.streamingText),
    }]);
    // 延迟清理 agent 状态，让用户看到最终文本
    const timer = setTimeout(() => agentChat.reset(), 500);
    return () => clearTimeout(timer);
  }
}, [agentChat.isDone, agentChat.streamingText]);
```

- [ ] **Step 5: Wire up loading state for agent mode**

Modify the send button and input disabled logic to also respect `agentChat.isConnected`:

```typescript
// In the Input disabled prop and Button disabled prop, replace `loading` with:
disabled={(loading || agentChat.isConnected) || !selectedBot}
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/AIAssistant.tsx
git commit -m "feat: integrate multi-step agent into AIAssistant page"
```

---

## Task 9: Backend Smoke Test

**Files:**
- None (manual verification)

- [ ] **Step 1: Start Django dev server**

```bash
cd backend && python manage.py runserver
```

- [ ] **Step 2: Verify WS endpoint is reachable**

```bash
# Install wscat if not present
npm install -g wscat

# Connect to WS (should accept, then close on invalid message)
wscat -c "ws://localhost:8000/ws/ai/chat/1/"
# Expected: Connected (press Ctrl+C to disconnect)
```

- [ ] **Step 3: Run backend checks**

```bash
make backend-check
```

Expected: All checks pass, no migration issues.

---

## Task 10: Frontend Build Check

**Files:**
- None (verification)

- [ ] **Step 1: TypeScript check**

```bash
cd frontend && npx tsc -b
```

Expected: No type errors.

- [ ] **Step 2: Build**

```bash
cd frontend && npm run build
```

Expected: Build succeeds.

- [ ] **Step 3: Final commit with all changes**

```bash
git add -A
git status  # Review what's staged
git commit -m "feat: multi-step visible agent with WebSocket streaming

- exam_generator and planner bots show real-time tool call steps
- Collapsible AgentStepCard with granular Chinese labels
- Full-chain streaming: intermediate steps + text token output
- WebSocket-based push, no polling for agent-mode bots
- Steps not persisted to DB, only visible in current session"
```
