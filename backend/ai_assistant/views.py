import asyncio
import os
import threading
import logging
from asgiref.sync import sync_to_async
from django.db import models, close_old_connections
from users.permissions import IsAdmin, HasQuota, HasPlanFeature, IsInstitutionAdmin, IsMemberOrReadOnlyList
from rest_framework import generics, permissions, serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import AIChatMessage, AgentMemory, Bot, BotVisibility, StudyPlan
from .serializers import AIChatMessageSerializer, AgentMemorySerializer, BotSerializer, StudyPlanSerializer
from .utils import get_student_academic_context
from .prompt_sync import (
    delete_bot_prompt_file,
    get_bot_prompt_template_name,
    sync_bot_prompt,
    write_bot_prompt_file,
)
from users.views import IsMember
from core.analytics import record_event
from core.rate_limit import user_rate_limit
from ai_service import AIService
from ai_assistant.services.tool_executor import BaseToolExecutor

logger = logging.getLogger(__name__)

_AI_CHAT_SEMAPHORE = threading.Semaphore(
    int(os.getenv('AI_MAX_CONCURRENT_CHATS', '50'))
)


def _get_chat_semaphore(bot):
    """按 bot_type 返回对应信号量，未匹配时回退到全局信号量。"""
    bot_type = getattr(bot, 'bot_type', None) if bot else 'planner'
    if bot_type == 'exam_generator':
        return _AI_CHAT_SEMAPHORE  # 共享池，exam_generator 调用频率低
    return _AI_CHAT_SEMAPHORE


def process_ai_chat(user, bot, user_message, pending_msg_id, conversation_id=None, history_limit=10):
    base_qs = AIChatMessage.objects.filter(user=user, bot=bot)
    if conversation_id:
        base_qs = base_qs.filter(conversation_id=conversation_id)
    history_objs = base_qs.order_by('-timestamp')[:history_limit]
    history_msgs = [{"role": h.role, "content": h.content} for h in reversed(history_objs)
                    if h.content != "[Thinking...]" and not (h.role == 'user' and h.content == user_message)]

    student_context = ""
    if bot and bot.is_exclusive:
        student_context = get_student_academic_context(user)

    # 获取记忆上下文 (dual-layer: structured + mem0 semantic + adaptive directives)
    from ai_assistant.services.memory_service import build_memory_context
    memory_context, adaptive_directives = build_memory_context(user, user_message, bot_type=bot.bot_type if bot else 'planner')

    from ai_assistant.services.chat_dispatch import dispatch_bot_chat

    try:
        with _AI_CHAT_SEMAPHORE:
            dispatch_result = dispatch_bot_chat(
                bot=bot,
                user=user,
                message=user_message,
                history=history_msgs,
                institution=getattr(user, 'institution', None),
                student_context=student_context,
                memory_context=memory_context,
                adaptive_directives=adaptive_directives,
            )
            res = dispatch_result['result']
            tool_executor = dispatch_result['tool_executor']
            poll_variant_name = dispatch_result.get('prompt_variant', 'baseline')

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
                # 统一 metadata 构建
                msg_metadata = {}
                if hasattr(tool_executor, '_last_generated') and tool_executor._last_generated:
                    msg_metadata['generated_questions'] = tool_executor._last_generated
                if hasattr(tool_executor, '_last_pipeline_task_id') and tool_executor._last_pipeline_task_id:
                    msg_metadata['pipeline_task_id'] = tool_executor._last_pipeline_task_id
                if hasattr(tool_executor, 'pending_visuals') and tool_executor.pending_visuals:
                    visuals = tool_executor.pending_visuals
                    msg_metadata['visual'] = visuals[-1]
                    if len(visuals) > 1:
                        msg_metadata['all_visuals'] = visuals
                if msg_metadata:
                    pending_msg.metadata = msg_metadata
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
            pending_msg.content = "抱歉，连接中断，请稍后再试。"
            pending_msg.save()
    finally:
        # 异步提取记忆（不阻塞响应）
        try:
            from ai_assistant.services.memory_service import (
                extract_memories_async,
                extract_memories_with_mem0,
            )
            full_history = history_msgs + [{'role': 'user', 'content': user_message}]
            extract_memories_async(user, full_history)
            extract_memories_with_mem0(user, full_history)
        except Exception:
            logger.warning("Memory extraction failed (polling)", exc_info=True)

        # MUTAR 轨迹记录（异步，不阻塞响应）
        try:
            from ai_assistant.services.trajectory_recorder import record_trajectory
            all_msgs = history_msgs + [
                {'role': 'user', 'content': user_message},
                {'role': 'assistant', 'content': ai_content if 'ai_content' in dir() else ''},
            ]
            record_trajectory(
                user_id=user.id,
                bot_id=bot.id if bot else 0,
                conversation_id=str(conversation_id) if conversation_id else '',
                messages=all_msgs,
                tool_calls=getattr(tool_executor, 'tool_call_log', []),
                tool_outputs=getattr(tool_executor, 'tool_output_log', []),
                prompt_variant=poll_variant_name,
            )
        except Exception:
            logger.warning("Trajectory recording failed (polling)", exc_info=True)

        # 新会话首次对话时，异步生成标题
        if conversation_id:
            try:
                chat_count = AIChatMessage.objects.filter(
                    conversation_id=conversation_id, role='user'
                ).count()
                if chat_count <= 1:
                    from ai_assistant.tasks import generate_conversation_title
                    generate_conversation_title.delay(
                        str(conversation_id), user.id, bot.id if bot else 0
                    )
            except Exception:
                logger.debug("Title generation skipped", exc_info=True)

        close_old_connections()


def _user_can_access_bot(user, bot):
    """验证用户是否有权使用指定 bot。"""
    from users.permissions import is_platform_admin
    if is_platform_admin(user):
        return True
    # 全局 bot：检查可见性
    if bot.institution is None:
        if not bot.is_active:
            return False
        # planner/exam_generator 始终可见，不允许租户隐藏
        if bot.bot_type in ('planner', 'exam_generator'):
            return True
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
        return [IsMemberOrReadOnlyList()]

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
            # planner/exam_generator 始终可见，不参与隐藏过滤
            hidden_ids = BotVisibility.objects.filter(
                institution=user.institution, is_visible=False,
            ).exclude(bot__bot_type__in=('planner', 'exam_generator')).values_list('bot_id', flat=True)
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
        return [IsMemberOrReadOnlyList()]

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
        # 排除始终可见的 planner/exam_generator
        global_bots = Bot.objects.filter(
            institution__isnull=True,
        ).exclude(bot_type__in=('planner', 'exam_generator'))
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

        if bot.bot_type in ('planner', 'exam_generator'):
            return Response({'error': '该机器人始终可见，不允许调整'}, status=403)

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
        import uuid as _uuid
        user_message = request.data.get('message')
        bot_id = request.data.get('bot_id')
        conversation_id = request.data.get('conversation_id')
        if not user_message:
            return Response({'error': 'Message is required'}, status=400)

        if conversation_id:
            try:
                conversation_id = _uuid.UUID(conversation_id)
            except (ValueError, AttributeError):
                conversation_id = _uuid.uuid4()
        else:
            conversation_id = _uuid.uuid4()

        bot = Bot.objects.filter(id=bot_id).first()
        if bot:
            if not _user_can_access_bot(request.user, bot):
                return Response({'error': '无权使用此机器人'}, status=403)
            sync_bot_prompt(bot)

        # 1. Save User Message
        AIChatMessage.objects.create(user=request.user, role='user', content=user_message, bot=bot, conversation_id=conversation_id)
        record_event('ai_chat_start', user=request.user, properties={'bot_id': bot_id})

        # 2. Create Pending Assistant Message
        pending_msg = AIChatMessage.objects.create(user=request.user, role='assistant', content="[Thinking...]", bot=bot, conversation_id=conversation_id)

        # 3. Start Background Thread
        from ai_assistant.utils import _THREAD_POOL
        _THREAD_POOL.submit(
            process_ai_chat,
            request.user, bot, user_message, pending_msg.id, conversation_id,
        )

        return Response({'status': 'pending'})


class AIChatListView(generics.ListAPIView):
    serializer_class = AIChatMessageSerializer
    permission_classes = [IsMember]
    def get_queryset(self):
        from django.db.models import OuterRef, Subquery
        from .models import Conversation

        bot_id = self.request.query_params.get('bot_id')
        conversation_id = self.request.query_params.get('conversation_id')
        qs = AIChatMessage.objects.filter(user=self.request.user)
        if bot_id:
            qs = qs.filter(bot_id=bot_id)
        if conversation_id:
            qs = qs.filter(conversation_id=conversation_id)

        # 注解 conversation_title
        title_subquery = Conversation.objects.filter(
            conversation_id=OuterRef('conversation_id'),
        ).values('title')[:1]
        qs = qs.annotate(_conversation_title=Subquery(title_subquery))
        return qs


class AIChatResetView(APIView):
    permission_classes = [IsMember]
    @user_rate_limit(key_prefix='chat_reset', max_requests=10, window_seconds=3600)
    def post(self, request):
        bot_id = request.data.get('bot_id')
        qs = AIChatMessage.objects.filter(user=request.user)
        if bot_id:
            qs = qs.filter(bot_id=bot_id)
        qs.delete()
        return Response({'status': 'cleared'})


class AIChatDeleteConversationView(APIView):
    """删除指定 conversation_id 的对话记录。"""
    permission_classes = [IsMember]

    def post(self, request):
        conversation_id = request.data.get('conversation_id')
        if not conversation_id:
            return Response({'error': 'conversation_id is required'}, status=400)
        deleted, _ = AIChatMessage.objects.filter(
            user=request.user, conversation_id=conversation_id
        ).delete()
        return Response({'status': 'deleted', 'count': deleted})


class AIChatStreamView(APIView):
    """SSE 流式聊天 — 前端逐 token 渲染小宇回复。"""
    permission_classes = [IsMember, HasQuota]
    quota_resource = 'ai_call_total'

    def post(self, request):
        import json
        import uuid as _uuid
        from django.http import StreamingHttpResponse
        from ai_engine.service import AIEngine

        user_message = request.data.get('message', '').strip()
        bot_id = request.data.get('bot_id')
        web_search = request.data.get('web_search', False)
        conversation_id = request.data.get('conversation_id')
        class_id = request.data.get('class_id')

        if not user_message:
            return Response({'error': 'Message is required'}, status=400)

        if conversation_id:
            try:
                conversation_id = _uuid.UUID(conversation_id)
            except (ValueError, AttributeError):
                conversation_id = _uuid.uuid4()
        else:
            conversation_id = _uuid.uuid4()

        bot = Bot.objects.filter(id=bot_id).first()
        if not bot:
            return Response({'error': 'Bot not found'}, status=404)

        if not _user_can_access_bot(request.user, bot):
            return Response({'error': '无权使用此机器人'}, status=403)

        sync_bot_prompt(bot)

        # Save user message
        AIChatMessage.objects.create(user=request.user, role='user', content=user_message, bot=bot, conversation_id=conversation_id)
        
        # Create pending assistant message (for refresh recovery)
        pending_msg = AIChatMessage.objects.create(
            user=request.user, role='assistant', content="[Thinking...]",
            bot=bot, conversation_id=conversation_id
        )

        def _sync_setup():
            """All sync DB/ORM work — called once via sync_to_async."""
            history_objs = AIChatMessage.objects.filter(
                user=request.user, bot=bot, conversation_id=conversation_id
            ).order_by('-timestamp')[:10]
            history_msgs = [
                {"role": h.role, "content": h.content}
                for h in reversed(history_objs)
                if h.content != "[Thinking...]" and h.content != user_message
            ]

            student_context = ""
            if bot.is_exclusive:
                student_context = get_student_academic_context(request.user)

            from ai_assistant.services.memory_service import build_memory_context
            memory_context, adaptive_directives = build_memory_context(request.user, user_message, bot_type=bot.bot_type)

            from ai_assistant.services.chat_dispatch import dispatch_bot_chat_sync

            messages, tools, tool_executor, profile, variant_name = dispatch_bot_chat_sync(
                bot=bot,
                user=request.user,
                message=user_message,
                history=history_msgs,
                institution=getattr(request.user, 'institution', None),
                class_id=class_id,
                student_context=student_context,
                memory_context=memory_context,
                adaptive_directives=adaptive_directives,
            )

            # 意图路由（与 WS/Polling 路径一致）
            if profile.use_intent_router and user_message:
                from ai_engine.tool_router import route_tools
                tools = route_tools(user_message, tools, recent_messages=history_msgs, bot_type=bot.bot_type)

            # 工具白名单（防止 prompt injection 调用非预期工具）
            tool_executor._allowed_tool_names = {t['function']['name'] for t in tools}

            return history_msgs, messages, tools, tool_executor, profile, variant_name

        async def generate():
            history_msgs = []
            try:
                history_msgs, messages, tools, tool_executor, profile, sse_variant_name = await sync_to_async(_sync_setup)()

                step_queue: asyncio.Queue = asyncio.Queue()
                _SENTINEL = object()
                _result_container = [None]
                _sent_any_message = False

                def on_step(event):
                    step_queue.put_nowait(event)

                def on_message(text):
                    nonlocal _sent_any_message
                    _sent_any_message = True
                    step_queue.put_nowait({"type": "message", "content": text})

                # 挂到 tool_executor，让工具内部也能发进度事件
                tool_executor.on_step = on_step

                from ai_assistant.services.chat_dispatch import resolve_tool_choice
                forced_tool_choice = resolve_tool_choice(profile, bot.bot_type)
                # 意图路由后工具为空时，降级为 auto
                if not tools:
                    forced_tool_choice = "auto"

                def _run_agent():
                    try:
                        with _AI_CHAT_SEMAPHORE:
                            _result_container[0] = AIEngine.call_ai_with_streaming_tools(
                                messages=messages,
                                tools=tools,
                                tool_executor=tool_executor,
                                on_step=on_step,
                                on_message=on_message,
                                tool_choice=forced_tool_choice,
                                temperature=0.6,
                                max_tokens=2500,
                                operation=f'assistant.chat.{bot.bot_type}',
                                max_tool_rounds=8 if bot.bot_type == 'exam_generator' else 12,
                            )
                    except Exception as e:
                        logger.exception("Agent thread error: %s", e)
                        _result_container[0] = {"content": "AI 服务暂时不可用，请稍后再试。"}
                    finally:
                        step_queue.put_nowait(_SENTINEL)

                from ai_assistant.utils import _THREAD_POOL
                agent_future = _THREAD_POOL.submit(_run_agent)

                while True:
                    event = await step_queue.get()
                    if event is _SENTINEL:
                        break
                    # ── 诊断日志：空卡片追踪 ──
                    if event.get("type") == "step":
                        _ev_vis = event.get("visual")
                        _ev_diag = ""
                        if _ev_vis:
                            _ev_payload = _ev_vis.get("payload", {}) if isinstance(_ev_vis, dict) else {}
                            _ev_diag = (
                                f"vtype={_ev_vis.get('type')} "
                                f"vcards={len(_ev_payload.get('cards', [])) if isinstance(_ev_payload, dict) else '?'} "
                                f"vtitle={repr(_ev_payload.get('title', '')) if isinstance(_ev_payload, dict) else '?'}"
                            )
                        logging.getLogger("agent_debug").info(
                            "SSE out step: name=%s status=%s has_visual=%s %s label=%s",
                            event.get("name"), event.get("status"), bool(_ev_vis),
                            _ev_diag, event.get("label", ""),
                        )
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

                agent_future.result(timeout=5)
                result = _result_container[0]

                if result is None:
                    try:
                        agent_future.result(timeout=10)
                    except Exception:
                        pass
                    result = _result_container[0]

                ai_content = ""
                is_error = False
                if result is None:
                    ai_content = "AI 正在处理中，请稍候重试。"
                    is_error = True
                elif isinstance(result, dict) and 'content' in result:
                    ai_content = result['content']
                elif result and 'choices' in result:
                    ai_content = result['choices'][0]['message']['content'] or ''

                error_patterns = ("AI 服务暂时不可用", "AI 暂时无法响应", "LLM_API_KEY")
                if not is_error:
                    is_error = any(p in ai_content for p in error_patterns) if ai_content else False

                metadata = {}
                if hasattr(tool_executor, '_last_generated') and tool_executor._last_generated:
                    metadata['generated_questions'] = tool_executor._last_generated
                    metadata['pipeline_task_id'] = getattr(tool_executor, '_last_pipeline_task_id', None)
                if hasattr(tool_executor, '_last_pipeline_task_id') and tool_executor._last_pipeline_task_id:
                    metadata['pipeline_task_id'] = tool_executor._last_pipeline_task_id
                if hasattr(tool_executor, 'pending_visuals') and tool_executor.pending_visuals:
                    visuals = tool_executor.pending_visuals
                    metadata['visual'] = visuals[-1]  # Last visual for backward compat
                    if len(visuals) > 1:
                        metadata['all_visuals'] = visuals
                    tool_executor.pending_visuals = []

                # Save assistant message even when ai_content is empty (tool-only responses)
                has_metadata = bool(metadata)
                should_save = (ai_content or has_metadata or _sent_any_message) and not is_error
                logger.info("[SSE done] ai_content_len=%s has_metadata=%s sent_any=%s is_error=%s should_save=%s pending_visuals=%s metadata_keys=%s",
                    len(ai_content), has_metadata, _sent_any_message, is_error, should_save,
                    len(tool_executor.pending_visuals) if hasattr(tool_executor, 'pending_visuals') else 'N/A',
                    list(metadata.keys()) if metadata else [])
                if should_save:
                    save_content = ai_content or ' '  # Empty content breaks some queries
                    # Update pending message instead of creating new one
                    def _update_pending():
                        pending_msg.content = save_content
                        if metadata:
                            pending_msg.metadata = metadata
                        pending_msg.save()
                    await sync_to_async(_update_pending)()
                    if hasattr(tool_executor, 'user'):
                        await sync_to_async(request.user.refresh_from_db)()

                    from users.quota import increment_quota
                    def _bump_quota():
                        if request.user.institution:
                            increment_quota(request.user.institution, 'ai_call_total')
                    await sync_to_async(_bump_quota)()
                else:
                    # Delete pending message if not saving
                    await sync_to_async(pending_msg.delete)()

                # 先同步生成标题，再 yield done（确保前端刷新时 title 已入库）
                conv_title = None
                try:
                    from ai_assistant.services.title_generator import sync_generate_title
                    conv_title = await sync_to_async(sync_generate_title)(
                        str(conversation_id), request.user.id, bot.id
                    )
                except Exception:
                    logger.warning("Title generation failed before done", exc_info=True)

                done_payload = {'done': True, 'full_content': ai_content, 'is_error': is_error, 'has_intermediate': _sent_any_message, 'message_id': pending_msg.id}
                if metadata:
                    done_payload['metadata'] = metadata
                if conv_title:
                    done_payload['conversation_title'] = conv_title
                yield f"data: {json.dumps(done_payload, ensure_ascii=False)}\n\n"

            except Exception as e:
                logger.exception("AI Chat Stream Error [%s]: %s", type(e).__name__, e)
                error_msg = "抱歉，连接中断，请稍后再试。"
                yield f"data: {json.dumps({'error': error_msg})}\n\n"
            finally:
                try:
                    from ai_assistant.services.memory_service import (
                        extract_memories_async,
                        extract_memories_with_mem0,
                    )
                    full_history = history_msgs + [{'role': 'user', 'content': user_message}]
                    await sync_to_async(extract_memories_async)(request.user, full_history)
                    await sync_to_async(extract_memories_with_mem0)(request.user, full_history)
                except Exception:
                    logger.warning("Memory extraction failed (SSE)", exc_info=True)

                # MUTAR 轨迹记录（异步，不阻塞响应）
                try:
                    from ai_assistant.services.trajectory_recorder import record_trajectory
                    all_msgs = history_msgs + [
                        {'role': 'user', 'content': user_message},
                        {'role': 'assistant', 'content': ai_content},
                    ]
                    record_trajectory(
                        user_id=request.user.id,
                        bot_id=bot.id,
                        conversation_id=str(conversation_id),
                        messages=all_msgs,
                        tool_calls=getattr(tool_executor, 'tool_call_log', []),
                        tool_outputs=getattr(tool_executor, 'tool_output_log', []),
                        prompt_variant=sse_variant_name,
                    )
                except Exception:
                    logger.warning("Trajectory recording failed (SSE)", exc_info=True)

                await sync_to_async(close_old_connections)()

        response = StreamingHttpResponse(
            generate(),
            content_type='text/event-stream',
        )
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        return response


class AgentMemoryListCreateView(generics.ListCreateAPIView):
    serializer_class = AgentMemorySerializer
    permission_classes = [IsMember]

    def get_queryset(self):
        qs = AgentMemory.objects.filter(user=self.request.user)
        memory_type = self.request.query_params.get('type')
        if memory_type:
            qs = qs.filter(memory_type=memory_type)
        return qs

    def perform_create(self, serializer):
        serializer.save(user=self.request.user, source='manual')


class AgentMemoryDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = AgentMemorySerializer
    permission_classes = [IsMember]

    def get_queryset(self):
        return AgentMemory.objects.filter(user=self.request.user)


class StudyPlanListView(generics.ListAPIView):
    serializer_class = StudyPlanSerializer
    permission_classes = [IsMember]

    def get_queryset(self):
        return StudyPlan.objects.filter(user=self.request.user)


class StudyPlanDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = StudyPlanSerializer
    permission_classes = [IsMember]

    def get_queryset(self):
        return StudyPlan.objects.filter(user=self.request.user)


class StudyPlanTaskUpdateView(APIView):
    permission_classes = [IsMember]

    def patch(self, request, plan_id, task_id):
        from django.utils import timezone

        plan = StudyPlan.objects.filter(id=plan_id, user=request.user).first()
        if not plan:
            return Response({'error': 'Plan not found'}, status=404)

        data = plan.plan_data or {}
        tasks = data.get('tasks', [])
        updated = False
        task_to_update = None
        for task in tasks:
            if task.get('id') == task_id:
                task_to_update = task
                break

        if task_to_update is None:
            return Response({'error': 'Task not found'}, status=404)

        # Update status
        new_status = request.data.get('status')
        if new_status is not None:
            if new_status not in ('pending', 'completed', 'skipped'):
                return Response({'error': 'Invalid status'}, status=400)
            task_to_update['status'] = new_status
            task_to_update['completed_at'] = timezone.now().isoformat() if new_status == 'completed' else None
            updated = True

        # Update title
        if 'title' in request.data:
            task_to_update['title'] = request.data['title']
            updated = True

        # Update action
        if 'action' in request.data:
            task_to_update['action'] = request.data['action']
            updated = True

        # Update estimated_minutes
        if 'estimated_minutes' in request.data:
            val = request.data['estimated_minutes']
            task_to_update['estimated_minutes'] = int(val) if val is not None else None
            updated = True

        # Update target_accuracy
        if 'target_accuracy' in request.data:
            val = request.data['target_accuracy']
            task_to_update['target_accuracy'] = int(val) if val is not None else None
            updated = True

        # Update question_count
        if 'question_count' in request.data:
            val = request.data['question_count']
            task_to_update['question_count'] = int(val) if val is not None else None
            updated = True

        if not updated:
            return Response({'error': 'No valid fields to update'}, status=400)

        # Auto-complete plan if all tasks done
        all_done = all(t.get('status') in ('completed', 'skipped') for t in tasks)
        if all_done:
            plan.status = 'completed'
            plan.completed_at = timezone.now()

        plan.plan_data = data
        plan.save()

        return Response(StudyPlanSerializer(plan).data)

    def delete(self, request, plan_id, task_id):
        from django.utils import timezone

        plan = StudyPlan.objects.filter(id=plan_id, user=request.user).first()
        if not plan:
            return Response({'error': 'Plan not found'}, status=404)

        data = plan.plan_data or {}
        tasks = data.get('tasks', [])
        tasks = [t for t in tasks if t.get('id') != task_id]

        if len(tasks) == len(data.get('tasks', [])):
            return Response({'error': 'Task not found'}, status=404)

        data['tasks'] = tasks
        plan.plan_data = data
        plan.save()

        return Response(StudyPlanSerializer(plan).data)


class SemanticMemoryListView(APIView):
    """List semantic memories for the current user from mem0."""
    permission_classes = [IsMember]

    def get(self, request):
        user = request.user
        if not user.institution_id:
            return Response({"memories": []})

        try:
            from ai_assistant.services.tenant_memory import TenantMemoryManager
            manager = TenantMemoryManager(institution_id=user.institution_id)
            limit = min(int(request.query_params.get('limit', 100)), 200)
            memories = manager.get_all(user_id=user.id)[:limit]
            return Response({"memories": memories})
        except Exception:
            logger.exception("Failed to list semantic memories")
            return Response({"error": "获取记忆失败"}, status=500)


class SemanticMemoryDeleteView(APIView):
    """Delete a single semantic memory or clear all."""
    permission_classes = [IsMember]

    def delete(self, request, memory_id=None):
        user = request.user
        if not user.institution_id:
            return Response({"error": "无机构信息"}, status=400)

        try:
            from ai_assistant.services.tenant_memory import TenantMemoryManager
            manager = TenantMemoryManager(institution_id=user.institution_id)
            if memory_id:
                # Verify ownership: only delete if memory belongs to this user
                user_memories = manager.get_all(user_id=user.id)
                user_memory_ids = {m.get('id') for m in user_memories if m.get('id')}
                if memory_id not in user_memory_ids:
                    return Response({"error": "记忆不存在"}, status=404)
                manager.delete(memory_id=memory_id)
            else:
                manager.delete_all(user_id=user.id)
            return Response({"status": "ok"})
        except Exception:
            logger.exception("Failed to delete semantic memory")
            return Response({"error": "删除记忆失败"}, status=500)


class ActionCardInteractionView(APIView):
    """行动卡片交互追踪：记录点击/完成，查询完成状态。"""
    permission_classes = [IsMember]

    def get(self, request):
        """查询当前用户所有卡片完成状态。可选 ?type=quiz 过滤。"""
        from .models import ActionCardInteraction
        qs = ActionCardInteraction.objects.filter(user=request.user)
        action_type = request.query_params.get('type')
        if action_type:
            qs = qs.filter(card_action_type=action_type)

        interactions = qs.values(
            'card_action_url', 'card_title', 'card_action_type',
            'completed', 'clicked_at', 'completed_at',
        )
        return Response({"interactions": list(interactions)})

    def post(self, request):
        """记录或更新卡片交互。

        body: {card_title, card_action_type, card_action_url, card_icon?, card_description?, completed?, metadata?}
        如果 completed=true，同时更新 completed_at。
        """
        from .models import ActionCardInteraction
        from django.utils import timezone

        data = request.data
        url = data.get('card_action_url', '')
        if not url:
            return Response({"error": "card_action_url 必填"}, status=400)

        completed = data.get('completed', False)
        interaction, created = ActionCardInteraction.objects.update_or_create(
            user=request.user,
            card_action_url=url,
            defaults={
                'card_title': data.get('card_title', ''),
                'card_action_type': data.get('card_action_type', 'quiz'),
                'card_icon': data.get('card_icon', ''),
                'card_description': data.get('card_description', ''),
                'completed': completed,
                'completed_at': timezone.now() if completed else None,
                'metadata': data.get('metadata', {}),
            },
        )
        return Response({
            "id": interaction.id,
            "created": created,
            "completed": interaction.completed,
            "completed_at": interaction.completed_at.isoformat() if interaction.completed_at else None,
        })
