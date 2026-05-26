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
        from .utils import get_student_academic_context

        loop = _asyncio.new_event_loop()

        def send_sync(event_dict):
            future = _asyncio.run_coroutine_threadsafe(
                self.send(text_data=json.dumps(event_dict, ensure_ascii=False)),
                loop,
            )
            future.result(timeout=5)

        def on_step(event):
            send_sync(event)

        try:
            user_msg = self._save_message(self.user, self.bot, 'user', message)

            history_limit = 10
            history_objs = AIChatMessage.objects.filter(
                user=self.user, bot=self.bot,
            ).order_by('-timestamp')[:history_limit]
            history_msgs = [
                {"role": h.role, "content": h.content}
                for h in reversed(history_objs)
                if h.content != '[Thinking...]'
            ]

            student_context = ""
            if self.bot.is_exclusive:
                student_context = get_student_academic_context(self.user)

            memory_context = ""
            try:
                from .services.memory_service import get_memories_for_injection
                memory_context = get_memories_for_injection(self.user)
            except Exception:
                pass

            if self.bot.bot_type == 'planner':
                from .services.tool_executor import PlannerToolExecutor
                tool_executor = PlannerToolExecutor(self.user)
            elif self.bot.bot_type == 'exam_generator':
                from .services.exam_generator_tool_executor import ExamGeneratorToolExecutor
                tool_executor = ExamGeneratorToolExecutor(self.user)
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

            if isinstance(result, dict) and 'content' in result:
                ai_content = result['content']
            elif result and 'choices' in result:
                ai_content = result['choices'][0]['message']['content']
            else:
                ai_content = "AI 助教暂时无法响应，请稍后再试。"

            ai_content = ai_content.replace('\\[', ' $$ ').replace('\\]', ' $$ ')
            ai_content = ai_content.replace('\\(', ' $ ').replace('\\)', ' $ ')

            on_step({"type": "done", "full_content": ai_content})

            self._save_message(self.user, self.bot, 'assistant', ai_content,
                              metadata=self._build_metadata(tool_executor))

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
