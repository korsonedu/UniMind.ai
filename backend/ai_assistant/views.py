import threading
import logging
from django.db import models, connections
from users.permissions import IsAdmin, HasQuota, HasPlanFeature, IsInstitutionAdmin
from rest_framework import generics, permissions, serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import AIChatMessage, Bot, BotVisibility
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
from ai_assistant.services.tool_executor import AssistantToolExecutor

logger = logging.getLogger(__name__)

_AI_CHAT_SEMAPHORE = threading.Semaphore(5)  # max 5 concurrent AI chats


def process_ai_chat(user, bot, user_message, pending_msg_id, history_limit=10):
    # Filter out pending messages from history
    history_objs = AIChatMessage.objects.filter(user=user, bot=bot).order_by('-timestamp')[:history_limit]
    history_msgs = [{"role": h.role, "content": h.content} for h in reversed(history_objs) if h.content != "[Thinking...]"]

    student_context = ""
    if bot and bot.is_exclusive:
        student_context = get_student_academic_context(user)

    tool_executor = AssistantToolExecutor(user)

    try:
        with _AI_CHAT_SEMAPHORE:
            res = AIService.chat_with_assistant_agent(bot, history_msgs, user_message, tool_executor, student_context)

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

            # 计入 AI 调用总次数
            from users.quota import increment_quota
            if user.institution:
                increment_quota(user.institution, 'ai_call_total')
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


def _user_can_access_bot(user, bot):
    """验证用户是否有权使用指定 bot。"""
    from users.permissions import is_platform_admin
    if is_platform_admin(user):
        return True
    # 全局 bot：检查可见性
    if bot.institution is None:
        if not bot.is_active:
            return False
        if user.institution:
            vis = BotVisibility.objects.filter(
                institution=user.institution, bot=bot
            ).first()
            if vis and not vis.is_visible:
                return False
        return True
    # 机构 bot：必须匹配用户机构
    return bot.institution == user.institution


class BotListCreateView(generics.ListCreateAPIView):
    serializer_class = BotSerializer

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAdmin(), HasPlanFeature()]
        return [IsMember()]

    required_feature = 'ai.bot.custom'

    def get_queryset(self):
        user = self.request.user
        from users.permissions import is_platform_admin, is_institution_admin

        if is_platform_admin(user):
            qs = Bot.objects.all()
        elif is_institution_admin(user) and user.institution:
            qs = Bot.objects.filter(
                models.Q(institution__isnull=True) |
                models.Q(institution=user.institution)
            )
        elif user.institution:
            hidden_ids = BotVisibility.objects.filter(
                institution=user.institution, is_visible=False
            ).values_list('bot_id', flat=True)
            qs = Bot.objects.filter(
                models.Q(institution__isnull=True, is_active=True) |
                models.Q(institution=user.institution, is_active=True)
            ).exclude(
                models.Q(institution__isnull=True) & models.Q(id__in=hidden_ids)
            )
        else:
            qs = Bot.objects.filter(institution__isnull=True, is_active=True)

        return qs

    def perform_create(self, serializer):
        user = self.request.user
        from users.permissions import is_platform_admin
        from users.quota import check_quota

        if is_platform_admin(user):
            bot = serializer.save(institution=None)
        else:
            inst = user.institution
            if not inst:
                raise serializers.ValidationError("您需要先加入机构。")
            if not check_quota(inst, 'custom_bot'):
                raise serializers.ValidationError("自定义机器人数量已达上限，请升级方案。")
            bot = serializer.save(institution=inst)

        sync_bot_prompt(bot)
        logger.info("Bot created: bot_id=%s, institution=%s", bot.id, bot.institution_id)


class BotDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Bot.objects.all()
    serializer_class = BotSerializer

    def get_permissions(self):
        if self.request.method in ('PUT', 'PATCH', 'DELETE'):
            return [IsAdmin()]
        return [IsMember()]

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        user = request.user
        from users.permissions import is_platform_admin
        if is_platform_admin(user):
            return
        if obj.institution is None:
            raise PermissionDenied("无法编辑全局机器人。")
        if user.institution != obj.institution:
            raise PermissionDenied("无法编辑其他机构的机器人。")

    def perform_update(self, serializer):
        bot = serializer.save()
        write_bot_prompt_file(bot, bot.system_prompt or '')
        sync_bot_prompt(bot)

    def perform_destroy(self, instance):
        delete_bot_prompt_file(instance)
        instance.delete()


class BotVisibilityView(APIView):
    """机构对全局 bot 的可见性管理。"""
    permission_classes = [permissions.IsAuthenticated, IsInstitutionAdmin]

    def get(self, request):
        inst = request.user.institution
        global_bots = Bot.objects.filter(institution__isnull=True)
        vis_map = {
            v.bot_id: v.is_visible
            for v in BotVisibility.objects.filter(institution=inst)
        }
        result = []
        for bot in global_bots:
            result.append({
                'bot_id': bot.id,
                'name': bot.name,
                'avatar': bot.avatar.url if bot.avatar else None,
                'is_visible': vis_map.get(bot.id, True),
            })
        return Response(result)

    def patch(self, request):
        inst = request.user.institution
        bot_id = request.data.get('bot_id')
        is_visible = request.data.get('is_visible')

        if bot_id is None or is_visible is None:
            return Response({'error': 'bot_id and is_visible required'}, status=400)

        bot = Bot.objects.filter(id=bot_id, institution__isnull=True).first()
        if not bot:
            return Response({'error': '全局机器人不存在'}, status=404)

        vis, _ = BotVisibility.objects.update_or_create(
            institution=inst, bot=bot,
            defaults={'is_visible': bool(is_visible)},
        )
        return Response({
            'bot_id': bot.id,
            'is_visible': vis.is_visible,
        })


class AIChatView(APIView):
    permission_classes = [IsMember, HasQuota]
    quota_resource = 'ai_call_total'

    def post(self, request):
        user_message = request.data.get('message')
        bot_id = request.data.get('bot_id')
        if not user_message:
            return Response({'error': 'Message is required'}, status=400)

        bot = Bot.objects.filter(id=bot_id).first()
        if bot:
            if not _user_can_access_bot(request.user, bot):
                return Response({'error': '无权使用此机器人'}, status=403)
            sync_bot_prompt(bot)

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
        if bot_id:
            qs = qs.filter(bot_id=bot_id)
        return qs


class AIChatResetView(APIView):
    permission_classes = [IsMember]
    def post(self, request):
        bot_id = request.data.get('bot_id')
        qs = AIChatMessage.objects.filter(user=request.user)
        if bot_id:
            qs = qs.filter(bot_id=bot_id)
        qs.delete()
        return Response({'status': 'cleared'})
