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
        logger.info("WS connect: bot_id=%s, session_user=%s", self.bot_id, self.user)

        # Try session auth first, then fallback to token query param
        if not self.user or not self.user.is_authenticated:
            from urllib.parse import parse_qs
            qs = self.scope.get('query_string', b'').decode()
            params = parse_qs(qs)
            token = params.get('token', [None])[0]
            logger.info("WS auth fallback: token=%s", bool(token))
            if token:
                self.user = await self._authenticate_token(token)
                logger.info("WS token auth result: %s", self.user)
            if not self.user or not self.user.is_authenticated:
                logger.warning("WS rejected: unauthenticated")
                await self.close(code=4001)
                return

        bot = await self._get_bot(self.bot_id)
        if not bot:
            logger.warning("WS rejected: bot %s not found or no access", self.bot_id)
            await self.close(code=4004)
            return

        self.bot = bot
        logger.info("WS accepted: user=%s, bot=%s (%s)", self.user, bot.name, bot.bot_type)
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
        conversation_id = data.get('conversation_id')
        logger.info("WS received: bot=%s, user=%s, msg=%s", self.bot_id, self.user, message[:50])
        if not message:
            await self.send(text_data=json.dumps(
                {"type": "error", "message": "Empty message"},
                ensure_ascii=False,
            ))
            return

        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(None, self._run_agent, message, loop, conversation_id)
        except Exception as e:
            logger.exception("Agent WS error: %s", e)
            await self.send(text_data=json.dumps(
                {"type": "error", "message": f"Agent 执行失败: {e}"},
                ensure_ascii=False,
            ))

    def _run_agent(self, message: str, loop=None, conversation_id=None):
        """同步方法，在线程池中执行完整的 agent loop。"""
        import asyncio as _asyncio
        from .models import AIChatMessage
        from .utils import get_student_academic_context

        # Use the consumer's event loop (passed from receive) so run_coroutine_threadsafe works
        if loop is None:
            loop = _asyncio.get_event_loop()

        def send_sync(event_dict):
            logger.info("WS send_sync: type=%s", event_dict.get('type'))
            future = _asyncio.run_coroutine_threadsafe(
                self.send(text_data=json.dumps(event_dict, ensure_ascii=False)),
                loop,
            )
            future.result(timeout=5)

        def on_step(event):
            send_sync(event)

        try:
            user_msg = self._save_message(self.user, self.bot, 'user', message, conversation_id=conversation_id)

            history_limit = 10
            base_qs = AIChatMessage.objects.filter(user=self.user, bot=self.bot)
            if conversation_id:
                base_qs = base_qs.filter(conversation_id=conversation_id)
            history_objs = base_qs.order_by('-timestamp')[:history_limit]
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

            from .services.chat_dispatch import dispatch_bot_chat

            dispatch_result = dispatch_bot_chat(
                bot=self.bot,
                user=self.user,
                message=message,
                history=history_msgs,
                institution=getattr(self, 'institution', None),
                stream=True,
                on_step=on_step,
                student_context=student_context,
                memory_context=memory_context,
            )
            result = dispatch_result['result']
            tool_executor = dispatch_result['tool_executor']

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
                              metadata=self._build_metadata(tool_executor),
                              conversation_id=conversation_id)

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

    @database_sync_to_async
    def _authenticate_token(self, token: str):
        from rest_framework.authtoken.models import Token
        try:
            auth_token = Token.objects.get(key=token)
            return auth_token.user
        except Token.DoesNotExist:
            return None

    def _save_message(self, user, bot, role, content, metadata=None, conversation_id=None):
        from .models import AIChatMessage
        msg = AIChatMessage(user=user, bot=bot, role=role, content=content)
        if conversation_id:
            msg.conversation_id = conversation_id
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
        if hasattr(tool_executor, 'pending_visual') and tool_executor.pending_visual:
            metadata['visual'] = tool_executor.pending_visual
            tool_executor.pending_visual = None  # Clear cache after persisting
        return metadata or None
