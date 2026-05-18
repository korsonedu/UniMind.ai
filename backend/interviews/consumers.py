import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async

from .models import InterviewSession, InterviewTurn
from .services import InterviewAIService

logger = logging.getLogger(__name__)

class InterviewConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.session_id = self.scope['url_route']['kwargs']['session_id']
        try:
            session_id = int(self.session_id)
        except Exception:
            await self.close(code=4400)
            return

        user = self.scope.get('user')
        if not user or not user.is_authenticated:
            await self.close(code=4401)
            return

        session = await self._get_owned_session(session_id, user.id)
        if not session:
            await self.close(code=4403)
            return

        await self.accept()
        logger.info(f"WebSocket connected for interview session: {self.session_id}")

    async def disconnect(self, close_code):
        logger.info(f"WebSocket disconnected for interview session: {self.session_id}")

    async def receive(self, text_data=None, bytes_data=None):
        """
        处理前端通过 WebSocket 发送来的音频 Chunk 或文字。
        全双工语音流：
        Frontend -> audio_chunk -> STT -> LLM -> TTS -> audio_chunk -> Frontend
        """
        if bytes_data:
            # 当前部署未启用实时 STT/TTS 服务，保持会话不中断并显式降级提示。
            await self.send(text_data=json.dumps({
                'type': 'degraded',
                'message': '语音通道暂不可用，已降级为文本面试模式。',
                'bytes_received': len(bytes_data),
            }))
            return
            
        if text_data:
            try:
                data = json.loads(text_data)
                action = data.get('action')
                
                if action == 'text_input':
                    user_text = str(data.get('text') or '').strip()
                    if not user_text:
                        await self.send(text_data=json.dumps({
                            'type': 'error',
                            'message': 'text 不能为空',
                        }))
                        return

                    user_id = self.scope['user'].id
                    session = await self._get_owned_session(int(self.session_id), user_id)
                    if not session:
                        await self.send(text_data=json.dumps({
                            'type': 'error',
                            'message': '会话不存在或无权限',
                        }))
                        return

                    candidate_turn = await self._append_turn(session.id, 'candidate', user_text)
                    history = await self._build_messages_for_ai(session.id)
                    institution = await database_sync_to_async(lambda: session.user.institution)()
                    ai_reply = await self._generate_reply(session.session_type, session.interviewer_style, history, institution)
                    interviewer_turn = await self._append_turn(session.id, 'interviewer', ai_reply)

                    await self.send(text_data=json.dumps({
                        'type': 'interviewer_reply',
                        'text': ai_reply,
                        'audio_url': '',
                        'candidate_turn_id': candidate_turn.id,
                        'interviewer_turn_id': interviewer_turn.id,
                    }))
            except Exception as e:
                logger.error(f"Error processing WebSocket message: {e}")

    @database_sync_to_async
    def _get_owned_session(self, session_id: int, user_id: int):
        return InterviewSession.objects.filter(id=session_id, user_id=user_id).first()

    @database_sync_to_async
    def _append_turn(self, session_id: int, speaker: str, text: str):
        last = InterviewTurn.objects.filter(session_id=session_id).order_by('-turn_number', '-created_at').first()
        next_turn = int(last.turn_number + 1) if last else 1
        return InterviewTurn.objects.create(
            session_id=session_id,
            turn_number=next_turn,
            speaker=speaker,
            content_text=text,
        )

    @database_sync_to_async
    def _build_messages_for_ai(self, session_id: int):
        turns = list(InterviewTurn.objects.filter(session_id=session_id).order_by('turn_number', 'created_at'))
        messages = []
        for turn in turns:
            role = 'assistant' if turn.speaker == 'interviewer' else 'user'
            messages.append({'role': role, 'content': turn.content_text})
        return messages

    @database_sync_to_async
    def _generate_reply(self, session_type: str, style: str, history: list, institution=None):
        try:
            generated = InterviewAIService.generate_interview_reply(
                session_type=session_type,
                style=style,
                chat_history=history,
                institution=institution,
            )
            if generated:
                return generated
        except Exception:
            logger.exception("InterviewConsumer AI generate failed")
        return "我收到了你的回答。请继续展开刚才提到的关键细节。"
