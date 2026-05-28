import logging
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView
from quizzes.models import KnowledgePoint, ContentPipelineTask
from quizzes.serializers import ContentPipelineTaskSerializer
from users.permissions import HasPlanFeature, HasQuota, IsAdmin
from users.quota import increment_ai_quota
from quizzes.services.ai_parse_service import (
    build_parse_task_id, extract_raw_text, get_parse_task, init_parse_task,
)
from quizzes.services.task_dispatcher import dispatch_ai_parse_task

logger = logging.getLogger(__name__)


class AIPreviewParseView(APIView):
    """
    整理功能：改用高性能异步模式
    """
    permission_classes = [HasPlanFeature, HasQuota]
    required_feature = 'ai.generate'
    quota_resource = 'ai_question'
    def post(self, request):
        raw_text = extract_raw_text(
            request.data.get('raw_text', ''),
            request.FILES.get('file'),
        )

        if not raw_text.strip(): return Response({'error': '内容为空'}, status=400)

        upload_file = request.FILES.get('file')
        if upload_file:
            from core.file_validation import validate_upload_file
            validate_upload_file(upload_file, allowed_extensions={'.pdf', '.doc', '.docx', '.txt', '.md'})
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
    permission_classes = [IsAdmin, HasPlanFeature, HasQuota]
    required_feature = 'ai.generate'
    quota_resource = 'ai_question'

    def post(self, request):
        kp_ids = request.data.get('kp_ids', [])
        if not kp_ids:
            return Response({'error': '请选择知识点'}, status=400)

        questions_per_kp = int(request.data.get('questions_per_kp', 3))
        difficulty = str(request.data.get('difficulty', 'normal')).strip()
        title = str(request.data.get('title', '')).strip()
        types = request.data.get('types', [])

        try:
            from quizzes.services.adversarial_pipeline import run_adversarial_pipeline
            task_id = run_adversarial_pipeline(
                kp_ids=kp_ids,
                created_by=request.user,
                task_title=title,
                questions_per_kp=questions_per_kp,
                difficulty=difficulty,
                types=types,
                institution=getattr(request.user, 'institution', None),
            )
            increment_ai_quota(request.user.institution)
            return Response({'task_id': task_id, 'status': 'running'}, status=201)
        except Exception as exc:
            logger.exception("Adversarial pipeline launch failed")
            return Response({'error': str(exc)}, status=500)


class PipelineReviewListView(APIView):
    """列出待审核的管线任务。"""
    permission_classes = [HasPlanFeature, HasQuota]
    required_feature = 'ai.generate'
    quota_resource = 'ai_question'

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
    """批准或拒绝待审核的管线任务，将题目入库。支持逐题选择和手动编辑。"""
    permission_classes = [IsAdmin, HasPlanFeature, HasQuota]
    required_feature = 'ai.generate'
    quota_resource = 'ai_question'

    def post(self, request, pk):
        action = str(request.data.get('action', '')).strip().lower()
        if action not in {'approve', 'reject'}:
            return Response({'error': 'action 必须为 approve 或 reject'}, status=400)

        task = get_object_or_404(ContentPipelineTask, pk=pk, status='review')
        if action == 'approve':
            questions = list((task.result or {}).get('questions', []))
            if not questions:
                return Response({'error': '任务中没有待入库的题目'}, status=400)

            # 支持手动编辑：前端可传 edited_questions（原始索引→新题），先应用到原题再筛选
            edited = request.data.get('edited_questions')
            if isinstance(edited, dict):
                for idx_str, q_data in edited.items():
                    try:
                        i = int(idx_str)
                        if 0 <= i < len(questions):
                            questions[i] = q_data
                    except (ValueError, TypeError):
                        continue

            # 支持逐题选择：前端可传 question_indices 指定要入库的题目序号
            selected_indices = request.data.get('question_indices')
            if isinstance(selected_indices, list) and selected_indices:
                selected = [questions[i] for i in selected_indices if 0 <= i < len(questions)]
            else:
                selected = questions

            if not selected:
                return Response({'error': '没有选中任何题目'}, status=400)

            from quizzes.ai_workflow import save_confirmed_questions
            created = save_confirmed_questions(selected, institution=request.user.institution)
            task.status = 'completed'
            task.progress = 100
            task.finished_at = timezone.now()
            task.description = (task.description or '') + f' | 已批准入库 {created}/{len(selected)} 题'
            task.save(update_fields=['status', 'progress', 'finished_at', 'description'])
            return Response({'status': 'approved', 'questions_created': created, 'total_selected': len(selected)})

        # reject
        task.status = 'cancelled'
        task.finished_at = timezone.now()
        task.description = (task.description or '') + ' | 已拒绝'
        task.save(update_fields=['status', 'finished_at', 'description'])
        return Response({'status': 'rejected'})


class WorkbenchTaskListView(APIView):
    """当前教师的出题任务列表（工作台用）。"""
    permission_classes = [IsAdmin, HasPlanFeature]
    required_feature = 'ai.generate'

    def get(self, request):
        qs = ContentPipelineTask.objects.filter(
            created_by=request.user,
            task_type='ai_generate',
        ).order_by('-created_at')[:20]
        serializer = ContentPipelineTaskSerializer(qs, many=True)
        return Response({'results': serializer.data})


class WorkbenchTaskStatusView(APIView):
    """轻量轮询端点：返回任务进度，不含 result 大字段。"""
    permission_classes = [IsAdmin]

    def get(self, request, pk):
        from users.permissions import is_platform_admin

        task = get_object_or_404(ContentPipelineTask, pk=pk)
        # 机构隔离
        if not is_platform_admin(request.user):
            user_inst = getattr(request.user, 'institution', None)
            task_inst = getattr(task.created_by, 'institution', None) if task.created_by else None
            if user_inst != task_inst:
                return Response({'error': '任务不存在'}, status=404)

        payload = task.payload or {}
        return Response({
            'id': task.id,
            'status': task.status,
            'progress': task.progress,
            'title': task.title,
            'current_stage': payload.get('current_stage', ''),
            'status_text': payload.get('status_text', ''),
            'stages': payload.get('stages', []),
            'created_at': task.created_at,
            'finished_at': task.finished_at,
        })


class WorkbenchSaveQuestionsView(APIView):
    """直接将前端题目数据存入题库。"""
    permission_classes = [IsAdmin]

    def post(self, request):
        from quizzes.models import Question

        questions = request.data.get('questions', [])
        if not questions:
            return Response({'error': '没有可保存的题目'}, status=400)

        saved_count = 0
        errors = []
        for q in questions:
            try:
                kp = None
                kp_id = q.get('kp_id')
                if kp_id:
                    kp = KnowledgePoint.objects.filter(id=kp_id).first()

                question = Question(
                    text=q.get('question', ''),
                    q_type=q.get('q_type', 'objective'),
                    subjective_type=q.get('subjective_type'),
                    difficulty_level=q.get('difficulty_level', 'normal'),
                    options=q.get('options'),
                    correct_answer=q.get('answer', ''),
                    grading_points='\n'.join(q.get('grading_points', []) or []) if q.get('grading_points') else None,
                    knowledge_point=kp,
                    institution=getattr(request.user, 'institution', None),
                )
                question.save()
                saved_count += 1
            except Exception as e:
                errors.append(str(e))

        return Response({
            'saved': saved_count,
            'total': len(questions),
            'errors': errors[:3] if errors else [],
        })


class WorkbenchLaunchArcView(APIView):
    """直接启动 ARC 精修管线。"""
    permission_classes = [IsAdmin]

    def post(self, request):
        from quizzes.services.adversarial_pipeline import run_adversarial_pipeline

        questions = request.data.get('questions', [])
        kp_ids = request.data.get('kp_ids', [])
        difficulty = request.data.get('difficulty', 'normal')
        questions_per_kp = int(request.data.get('questions_per_kp', 3))

        # 从前端题目中提取 kp_id（如果未显式提供）
        if not kp_ids:
            kp_ids = list({q['kp_id'] for q in questions if q.get('kp_id')})

        if not kp_ids:
            return Response({'error': '请提供知识点 ID 或包含 kp_id 的题目'}, status=400)

        try:
            task_id = run_adversarial_pipeline(
                kp_ids=kp_ids,
                created_by=request.user,
                task_title='ARC 精修管线',
                questions_per_kp=questions_per_kp,
                difficulty=difficulty,
                institution=getattr(request.user, 'institution', None),
            )
        except Exception as e:
            return Response({'error': str(e)}, status=500)

        return Response({'task_id': task_id})
