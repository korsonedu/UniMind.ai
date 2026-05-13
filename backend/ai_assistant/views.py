import threading
import logging
from django.db import connections
from users.permissions import IsAdmin
from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import AIChatMessage, Bot
from .serializers import AIChatMessageSerializer, BotSerializer
from .utils import get_student_academic_context
from .prompt_sync import (
    delete_bot_prompt_file,
    get_bot_prompt_template_name,
    sync_bot_prompt,
    write_bot_prompt_file,
)
from users.views import IsMember
from ai_service import AIService

logger = logging.getLogger(__name__)


def process_ai_chat(user, bot, user_message, pending_msg_id, history_limit=10):
    # Filter out pending messages from history
    history_objs = AIChatMessage.objects.filter(user=user, bot=bot).order_by('-timestamp')[:history_limit]
    history_msgs = [{"role": h.role, "content": h.content} for h in reversed(history_objs) if h.content != "[Thinking...]"]
    
    student_context = ""
    if bot and bot.is_exclusive:
        student_context = get_student_academic_context(user)

    try:
        res = AIService.chat_with_assistant(bot, history_msgs, user_message, student_context)
        
        pending_msg = AIChatMessage.objects.filter(id=pending_msg_id).first()
        
        if res and 'choices' in res:
            ai_content = res['choices'][0]['message']['content']
            finish_reason = res['choices'][0].get('finish_reason')
            
            # Format math
            ai_content = ai_content.replace('\\[', ' $$ ').replace('\\]', ' $$ ').replace('\\(', ' $ ').replace('\\)', ' $ ')
            
            if finish_reason == 'length':
                ai_content += "\n\n(已达到单次回复上限...)"
            
            if pending_msg:
                pending_msg.content = ai_content
                pending_msg.save()
        else:
            if pending_msg:
                pending_msg.content = "AI 助教暂时无法响应，请稍后再试。"
                pending_msg.save()
                
    except Exception as e:
        logger.exception("AI Chat Thread Error: %s", e)
        pending_msg = AIChatMessage.objects.filter(id=pending_msg_id).first()
        if pending_msg:
            pending_msg.content = f"抱歉，连接中断: {str(e)}"
            pending_msg.save()
    finally:
        connections.close_all()

class BotListCreateView(generics.ListCreateAPIView):
    serializer_class = BotSerializer
    def get_permissions(self):
        if self.request.method == 'POST': return [IsAdmin()]
        return [IsMember()]

    def get_queryset(self):
        bots = Bot.objects.all()
        for bot in bots:
            sync_bot_prompt(bot)
        return bots

    def perform_create(self, serializer):
        bot = serializer.save()
        sync_bot_prompt(bot)  # 创建时立即生成物理文件
        logger.info(
            "Bot created and prompt synced: bot_id=%s, template=%s",
            bot.id,
            get_bot_prompt_template_name(bot),
        )

class BotDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Bot.objects.all()
    serializer_class = BotSerializer
    permission_classes = [IsAdmin]

    def perform_update(self, serializer):
        bot = serializer.save()
        # 前端修改后，强制覆盖物理文件，再反向校验一次。
        write_bot_prompt_file(bot, bot.system_prompt or '')
        sync_bot_prompt(bot)

    def perform_destroy(self, instance):
        # 删除数据库记录前，先删除物理文件
        delete_bot_prompt_file(instance)
        instance.delete()

class AIChatView(APIView):
    permission_classes = [IsMember]

    def post(self, request):
        user_message = request.data.get('message')
        bot_id = request.data.get('bot_id')
        if not user_message: return Response({'error': 'Message is required'}, status=400)

        bot = Bot.objects.filter(id=bot_id).first()
        if bot: sync_bot_prompt(bot) 

        # 1. Save User Message
        AIChatMessage.objects.create(user=request.user, role='user', content=user_message, bot=bot)
        
        # 2. Create Pending Assistant Message
        pending_msg = AIChatMessage.objects.create(user=request.user, role='assistant', content="[Thinking...]", bot=bot)
        
        # 3. Start Background Thread
        thread = threading.Thread(
            target=process_ai_chat,
            args=(request.user, bot, user_message, pending_msg.id),
            daemon=True,
        )
        thread.start()

        return Response({'status': 'pending'})

class AIChatListView(generics.ListAPIView):
    serializer_class = AIChatMessageSerializer
    permission_classes = [IsMember]
    def get_queryset(self):
        bot_id = self.request.query_params.get('bot_id')
        qs = AIChatMessage.objects.filter(user=self.request.user)
        if bot_id: qs = qs.filter(bot_id=bot_id)
        return qs

class AIChatResetView(APIView):
    permission_classes = [IsMember]
    def post(self, request):
        bot_id = request.data.get('bot_id')
        qs = AIChatMessage.objects.filter(user=request.user)
        if bot_id: qs = qs.filter(bot_id=bot_id)
        qs.delete()
        return Response({'status': 'cleared'})
