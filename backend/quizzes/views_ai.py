import logging
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView
from quizzes.models import KnowledgePoint, ContentPipelineTask
from quizzes.serializers import ContentPipelineTaskSerializer
from users.permissions import HasPlanFeature, HasAIQuota
from users.quota import increment_ai_quota
from ai_service import AIService
from ai_engine.service import AICallError
from quizzes.services.single_generate_pipeline import run_single_generate_pipeline
from quizzes.services.ai_schema_guard import validate_question_list_payload
from quizzes.ai_workflow import save_confirmed_questions
from quizzes.services.ai_parse_service import (
    build_parse_task_id, extract_raw_text, get_parse_task, init_parse_task,
)
from quizzes.services.task_dispatcher import dispatch_ai_parse_task

logger = logging.getLogger(__name__)


class AIPreviewGenerateView(APIView):
    """
    智能出题预览：返回生成的数据但不存库
    """
    permission_classes = [HasPlanFeature, HasAIQuota]
    required_feature = 'ai.generate'
    def post(self, request):
        kp_ids = request.data.get('kp_ids', [])
        count = int(request.data.get('count', 1))
        target_types = request.data.get('types', []) # 新增题型过滤
        target_difficulty = request.data.get('difficulty_level', 'normal')
        target_type_ratio = request.data.get('type_ratio')

        if not kp_ids:
            return Response({'error': '未提供知识点 ID'}, status=400)

        pipeline_task = ContentPipelineTask.objects.create(
            task_type="ai_generate",
            status="running",
            title="AI 智能出题（快速模式）",
            description="Author -> Reviewer -> Classifier 单一出题预览任务",
            payload={
                "pipeline_mode": "single_generate_v1",
                "kp_ids": kp_ids,
                "count_per_kp": count,
                "target_types": target_types,
                "target_difficulty": target_difficulty,
            },
            progress=5,
            created_by=request.user,
            assignee=request.user,
            request_id=getattr(request, "request_id", ""),
            started_at=timezone.now(),
        )

        try:
            pipeline_result = run_single_generate_pipeline(
                kp_ids=kp_ids,
                count_per_kp=count,
                target_types=target_types,
                target_difficulty=target_difficulty,
                target_type_ratio=target_type_ratio,
                skip_review=True,
            )
            questions = pipeline_result.get('questions') or []
        except AICallError as e:
            pipeline_task.status = "failed"
            pipeline_task.progress = 100
            pipeline_task.error_message = e.message
            pipeline_task.finished_at = timezone.now()
            pipeline_task.save(update_fields=["status", "progress", "error_message", "finished_at", "updated_at"])
            return Response({'error': e.message}, status=e.status_code)
        except Exception as exc:
            logger.exception("AI smart generate pipeline 未预期异常")
            pipeline_task.status = "failed"
            pipeline_task.progress = 100
            pipeline_task.error_message = str(exc)[:500]
            pipeline_task.finished_at = timezone.now()
            pipeline_task.save(update_fields=["status", "progress", "error_message", "finished_at", "updated_at"])
            return Response({'error': f'AI 命题服务异常：{str(exc)[:200]}'}, status=500)

        if not questions:
            pipeline_task.status = "failed"
            pipeline_task.progress = 100
            pipeline_task.error_message = "AI 生成失败，请重试"
            pipeline_task.finished_at = timezone.now()
            pipeline_task.save(update_fields=["status", "progress", "error_message", "finished_at", "updated_at"])
            return Response({'error': 'AI 生成失败，请重试'}, status=500)

        pipeline_task.status = "completed"
        pipeline_task.progress = 100
        pipeline_task.result = {
            "pipeline": pipeline_result.get("pipeline", {}),
            "generated_count": len(questions),
            "review_report_preview": (pipeline_result.get("review_report") or [])[:20],
        }
        pipeline_task.finished_at = timezone.now()
        pipeline_task.save(update_fields=["status", "progress", "result", "finished_at", "updated_at"])

        increment_ai_quota(request.user.institution)

        return Response({
            'questions': questions,
            'pipeline': pipeline_result.get('pipeline', {}),
            'review_report': pipeline_result.get('review_report', []),
            'pipeline_task_id': pipeline_task.id,
        })


class AIConfirmSaveQuestionsView(APIView):
    """
    确认入库：保存前端编辑后的题目
    """
    permission_classes = [HasPlanFeature, HasAIQuota]
    required_feature = 'ai.generate'
    def post(self, request):
        questions_data = request.data.get('questions', [])
        if not isinstance(questions_data, list) or not questions_data:
            return Response({'error': '未提供可入库题目'}, status=400)

        schema_ok, schema_errors = validate_question_list_payload(questions_data, allow_empty=False)
        if not schema_ok:
            return Response(
                {
                    'error': '题目结构校验未通过，请先修正后再入库。',
                    'schema_errors': schema_errors[:20],
                },
                status=400,
            )

        created_count = 0
        failed_items = []

        for idx, q_data in enumerate(questions_data, start=1):
            text = str((q_data or {}).get('question') or (q_data or {}).get('text') or '').strip()
            if not text:
                failed_items.append({'index': idx, 'error': '题干为空'})
                continue

            try:
                created = save_confirmed_questions([q_data], institution=request.user.institution)
                if created <= 0:
                    failed_items.append({'index': idx, 'error': '题目格式无效，未写入'})
                else:
                    created_count += created
            except Exception as exc:  # noqa: BLE001
                logger.exception("ai-smart-generate confirm save failed at item=%s", idx)
                error_msg = str(exc).strip() or exc.__class__.__name__
                failed_items.append({'index': idx, 'error': error_msg[:200]})

        if failed_items:
            msg = f"成功 {created_count} 题，失败 {len(failed_items)} 题"
            payload = {
                'status': 'partial_success' if created_count > 0 else 'failed',
                'count': created_count,
                'failed_count': len(failed_items),
                'errors': failed_items[:10],
                'error': msg,
            }
            return Response(payload, status=207 if created_count > 0 else 500)

        return Response({'status': 'success', 'count': created_count})


class GenerateFromTextView(APIView):
    permission_classes = [HasPlanFeature, HasAIQuota]
    required_feature = 'ai.generate'
    def post(self, request):
        text = request.data.get('text')
        kp_id = request.data.get('kp_id')
        num_obj = request.data.get('num_objective', 3)
        num_short = request.data.get('num_short', 1)
        num_essay = request.data.get('num_essay', 1)
        num_calc = request.data.get('num_calc', 0)

        generated = AIService.generate_questions_from_text(
            text=text or '',
            num_obj=num_obj,
            num_short=num_short,
            num_essay=num_essay,
            num_calc=num_calc,
            kp_id=kp_id,
        )
        if not generated:
            return Response({'error': 'AI 生成失败'}, status=500)

        created_count = save_confirmed_questions(generated, institution=request.user.institution)
        increment_ai_quota(request.user.institution)
        return Response({'status': 'success', 'count': created_count})


class AIPreviewParseView(APIView):
    """
    整理功能：改用高性能异步模式
    """
    permission_classes = [HasPlanFeature, HasAIQuota]
    required_feature = 'ai.generate'
    def post(self, request):
        raw_text = extract_raw_text(
            request.data.get('raw_text', ''),
            request.FILES.get('file'),
        )

        if not raw_text.strip(): return Response({'error': '内容为空'}, status=400)

        upload_file = request.FILES.get('file')
        payload = {
            "raw_text_chars": len(raw_text),
            "has_file": bool(upload_file),
            "file_name": getattr(upload_file, "name", "") if upload_file else "",
        }
        pipeline_task = ContentPipelineTask.objects.create(
            task_type="ai_parse",
            status="running",
            title="AI 语料解析任务",
            description="维护中心发起的原始语料 AI 结构化整理任务",
            payload=payload,
            progress=0,
            created_by=request.user,
            assignee=request.user,
            request_id=getattr(request, "request_id", ""),
            started_at=timezone.now(),
        )

        task_id = build_parse_task_id()
        init_parse_task(task_id, pipeline_task_id=pipeline_task.id)

        try:
            dispatch_ai_parse_task(raw_text, task_id)
        except Exception as exc:  # noqa: BLE001
            pipeline_task.status = "failed"
            pipeline_task.progress = 100
            pipeline_task.error_message = str(exc)
            pipeline_task.finished_at = timezone.now()
            pipeline_task.save(update_fields=["status", "progress", "error_message", "finished_at", "updated_at"])
            raise

        return Response({
            'task_id': task_id,
            'status': 'processing',
            'pipeline_task_id': pipeline_task.id,
        })

    def get(self, request):
        """前端轮询此接口获取结果"""
        task_id = request.query_params.get('task_id')
        result = get_parse_task(task_id)
        if not result: return Response({'error': '任务不存在'}, status=404)

        pipeline_task_id = result.get("pipeline_task_id")
        if pipeline_task_id:
            task_obj = ContentPipelineTask.objects.filter(id=pipeline_task_id).first()
            if task_obj:
                parse_status = str(result.get("status", "")).strip()
                parse_progress = int(result.get("progress", 0) or 0)
                update_fields = []

                if parse_status == "processing":
                    if task_obj.status != "running":
                        task_obj.status = "running"
                        update_fields.append("status")
                    if task_obj.progress != parse_progress:
                        task_obj.progress = max(0, min(parse_progress, 99))
                        update_fields.append("progress")
                elif parse_status == "completed":
                    if task_obj.status != "completed":
                        task_obj.status = "completed"
                        update_fields.append("status")
                    if task_obj.progress != 100:
                        task_obj.progress = 100
                        update_fields.append("progress")
                    parsed_data = result.get("data") or []
                    task_obj.result = {"parsed_count": len(parsed_data)}
                    update_fields.append("result")
                    if not task_obj.finished_at:
                        task_obj.finished_at = timezone.now()
                        update_fields.append("finished_at")
                elif parse_status == "failed":
                    if task_obj.status != "failed":
                        task_obj.status = "failed"
                        update_fields.append("status")
                    if task_obj.progress != 100:
                        task_obj.progress = 100
                        update_fields.append("progress")
                    err = str(result.get("error") or "解析失败")
                    if task_obj.error_message != err:
                        task_obj.error_message = err
                        update_fields.append("error_message")
                    if not task_obj.finished_at:
                        task_obj.finished_at = timezone.now()
                        update_fields.append("finished_at")

                if update_fields:
                    update_fields.append("updated_at")
                    task_obj.save(update_fields=update_fields)

        return Response(result)


class AdversarialPipelineView(APIView):
    """对抗性 AI 出题管线（三 Agent 迭代博弈）。"""
    permission_classes = [HasPlanFeature, HasAIQuota]
    required_feature = 'ai.generate'

    def post(self, request):
        kp_ids = request.data.get('kp_ids', [])
        if not kp_ids:
            return Response({'error': '请选择知识点'}, status=400)

        questions_per_kp = int(request.data.get('questions_per_kp', 3))
        title = str(request.data.get('title', '')).strip()

        try:
            from quizzes.services.adversarial_pipeline import run_adversarial_pipeline
            task_id = run_adversarial_pipeline(
                kp_ids=kp_ids,
                created_by=request.user,
                task_title=title,
                questions_per_kp=questions_per_kp,
            )
            increment_ai_quota(request.user.institution)
            return Response({'task_id': task_id, 'status': 'running'}, status=201)
        except Exception as exc:
            logger.exception("Adversarial pipeline launch failed")
            return Response({'error': str(exc)}, status=500)


class PipelineReviewListView(APIView):
    """列出待审核的管线任务。"""
    permission_classes = [HasPlanFeature, HasAIQuota]
    required_feature = 'ai.generate'

    def get(self, request):
        from users.permissions import is_platform_admin
        from django.db.models import Q
        qs = ContentPipelineTask.objects.filter(status='review').select_related('created_by').order_by('-created_at')
        if not is_platform_admin(request.user):
            inst = getattr(request.user, 'institution', None)
            if inst:
                qs = qs.filter(Q(created_by__institution=inst) | Q(created_by__institution__isnull=True))
            else:
                qs = qs.filter(created_by__institution__isnull=True)
        tasks = qs
        serializer = ContentPipelineTaskSerializer(tasks, many=True)
        return Response({'results': serializer.data})


class PipelineReviewActionView(APIView):
    """批准或拒绝待审核的管线任务，将题目入库。"""
    permission_classes = [HasPlanFeature, HasAIQuota]
    required_feature = 'ai.generate'

    def post(self, request, pk):
        action = str(request.data.get('action', '')).strip().lower()
        if action not in {'approve', 'reject'}:
            return Response({'error': 'action 必须为 approve 或 reject'}, status=400)

        task = get_object_or_404(ContentPipelineTask, pk=pk, status='review')
        if action == 'approve':
            questions = (task.result or {}).get('questions', [])
            if not questions:
                return Response({'error': '任务中没有待入库的题目'}, status=400)
            from quizzes.ai_workflow import save_confirmed_questions
            created = save_confirmed_questions(questions, institution=request.user.institution)
            task.status = 'completed'
            task.progress = 100
            task.finished_at = timezone.now()
            task.description = (task.description or '') + f' | 已批准入库 {created} 题'
            task.save(update_fields=['status', 'progress', 'finished_at', 'description'])
            return Response({'status': 'approved', 'questions_created': created})

        # reject
        task.status = 'cancelled'
        task.finished_at = timezone.now()
        task.description = (task.description or '') + ' | 已拒绝'
        task.save(update_fields=['status', 'finished_at', 'description'])
        return Response({'status': 'rejected'})
