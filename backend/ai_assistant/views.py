import asyncio
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
from ai_assistant.services.tool_executor import AssistantToolExecutor

logger = logging.getLogger(__name__)

_AI_CHAT_SEMAPHORE = threading.Semaphore(5)  # max 5 concurrent AI chats


def process_ai_chat(user, bot, user_message, pending_msg_id, conversation_id=None, history_limit=10):
    base_qs = AIChatMessage.objects.filter(user=user, bot=bot)
    if conversation_id:
        base_qs = base_qs.filter(conversation_id=conversation_id)
    history_objs = base_qs.order_by('-timestamp')[:history_limit]
    history_msgs = [{"role": h.role, "content": h.content} for h in reversed(history_objs) if h.content != "[Thinking...]"]

    student_context = ""
    if bot and bot.is_exclusive:
        student_context = get_student_academic_context(user)

    # 获取记忆上下文 (dual-layer: structured + mem0 semantic + adaptive directives)
    from ai_assistant.services.memory_service import build_memory_context
    memory_context, adaptive_directives = build_memory_context(user, user_message, bot_type=bot.bot_type if bot else 'assistant')

    from ai_assistant.services.chat_dispatch import dispatch_bot_chat

    try:
        with _AI_CHAT_SEMAPHORE:
            dispatch_result = dispatch_bot_chat(
                bot=bot,
                user=user,
                message=user_message,
                history=history_msgs,
                student_context=student_context,
                memory_context=memory_context,
                adaptive_directives=adaptive_directives,
            )
            res = dispatch_result['result']
            tool_executor = dispatch_result['tool_executor']

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
                # 写入出题 Agent 的结构化数据
                if hasattr(tool_executor, '_last_generated') and tool_executor._last_generated:
                    pending_msg.metadata = {
                        'generated_questions': tool_executor._last_generated,
                        'pipeline_task_id': getattr(tool_executor, '_last_pipeline_task_id', None),
                    }
                elif hasattr(tool_executor, '_last_pipeline_task_id') and tool_executor._last_pipeline_task_id:
                    pending_msg.metadata = {
                        'pipeline_task_id': tool_executor._last_pipeline_task_id,
                    }
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
            pass
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
        thread = threading.Thread(
            target=process_ai_chat,
            args=(request.user, bot, user_message, pending_msg.id, conversation_id),
            daemon=True,
        )
        thread.start()

        return Response({'status': 'pending'})


class AIChatListView(generics.ListAPIView):
    serializer_class = AIChatMessageSerializer
    permission_classes = [IsMember]
    def get_queryset(self):
        bot_id = self.request.query_params.get('bot_id')
        conversation_id = self.request.query_params.get('conversation_id')
        qs = AIChatMessage.objects.filter(user=self.request.user)
        if bot_id:
            qs = qs.filter(bot_id=bot_id)
        if conversation_id:
            qs = qs.filter(conversation_id=conversation_id)
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

            messages, tools, tool_executor, profile = dispatch_bot_chat_sync(
                bot=bot,
                user=request.user,
                message=user_message,
                history=history_msgs,
                student_context=student_context,
                memory_context=memory_context,
                adaptive_directives=adaptive_directives,
            )

            return history_msgs, messages, tools, tool_executor

        async def generate():
            history_msgs = []
            collected = []
            try:
                history_msgs, messages, tools, tool_executor = await sync_to_async(_sync_setup)()

                step_queue: asyncio.Queue = asyncio.Queue()
                _SENTINEL = object()
                _result_container = [None]

                def on_step(event):
                    step_queue.put_nowait(event)

                forced_tool_choice = "required" if bot.bot_type in ('planner', 'exam_generator') else "auto"

                def _run_agent():
                    try:
                        with _AI_CHAT_SEMAPHORE:
                            _result_container[0] = AIEngine.call_ai_with_streaming_tools(
                                messages=messages,
                                tools=tools,
                                tool_executor=tool_executor,
                                on_step=on_step,
                                tool_choice=forced_tool_choice,
                                temperature=0.6,
                                max_tokens=2500,
                                operation='assistant.chat',
                                max_tool_rounds=5,
                            )
                    except Exception as e:
                        logger.exception("Agent thread error: %s", e)
                        _result_container[0] = {"content": "AI 服务暂时不可用，请稍后再试。"}
                    finally:
                        step_queue.put_nowait(_SENTINEL)

                agent_thread = threading.Thread(target=_run_agent, daemon=True)
                agent_thread.start()

                while True:
                    event = await step_queue.get()
                    if event is _SENTINEL:
                        break
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

                agent_thread.join(timeout=5)
                result = _result_container[0]

                # P1-11: 如果 5 秒内 agent 未完成，再等 10 秒
                if result is None:
                    agent_thread.join(timeout=10)
                    result = _result_container[0]

                ai_content = ""
                is_error = False
                if result is None:
                    # agent 超时未返回结果，发送超时提示，不写入数据库
                    ai_content = "AI 正在处理中，请稍候重试。"
                    is_error = True
                elif isinstance(result, dict) and 'content' in result:
                    ai_content = result['content']
                elif result and 'choices' in result:
                    ai_content = result['choices'][0]['message']['content'] or ''

                error_patterns = ("AI 服务暂时不可用", "AI 暂时无法响应", "LLM_API_KEY")
                if not is_error:
                    is_error = any(p in ai_content for p in error_patterns) if ai_content else True

                ai_content = ai_content.replace('\\[', ' $$ ').replace('\\]', ' $$ ').replace('\\(', ' $ ').replace('\\)', ' $ ')

                if ai_content and not is_error:
                    msg_kwargs = {
                        'user': request.user,
                        'role': 'assistant',
                        'content': ai_content,
                        'bot': bot,
                        'conversation_id': conversation_id,
                    }
                    # 写入出题 Agent 的结构化数据
                    if hasattr(tool_executor, '_last_generated') and tool_executor._last_generated:
                        msg_kwargs['metadata'] = {
                            'generated_questions': tool_executor._last_generated,
                            'pipeline_task_id': getattr(tool_executor, '_last_pipeline_task_id', None),
                        }
                    elif hasattr(tool_executor, '_last_pipeline_task_id') and tool_executor._last_pipeline_task_id:
                        msg_kwargs['metadata'] = {
                            'pipeline_task_id': tool_executor._last_pipeline_task_id,
                        }
                    await sync_to_async(AIChatMessage.objects.create)(**msg_kwargs)
                    if hasattr(tool_executor, 'user'):
                        await sync_to_async(request.user.refresh_from_db)()

                yield f"data: {json.dumps({'done': True, 'full_content': ai_content, 'is_error': is_error}, ensure_ascii=False)}\n\n"

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
                    pass
                await sync_to_async(close_old_connections)()

                from users.quota import increment_quota
                if request.user.institution:
                    await sync_to_async(increment_quota)(request.user.institution, 'ai_call_total')

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

        new_status = request.data.get('status')
        if new_status not in ('pending', 'completed', 'skipped'):
            return Response({'error': 'Invalid status'}, status=400)

        data = plan.plan_data or {}
        tasks = data.get('tasks', [])
        updated = False
        for task in tasks:
            if task.get('id') == task_id:
                task['status'] = new_status
                task['completed_at'] = timezone.now().isoformat() if new_status == 'completed' else None
                updated = True
                break

        if not updated:
            return Response({'error': 'Task not found'}, status=404)

        all_done = all(t.get('status') in ('completed', 'skipped') for t in tasks)
        if all_done:
            plan.status = 'completed'
            plan.completed_at = timezone.now()

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
