import logging
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView
from quizzes.models import KnowledgePoint, ContentPipelineTask
from quizzes.serializers import ContentPipelineTaskSerializer
from users.permissions import HasPlanFeature, HasQuota, IsAdmin
from users.quota import increment_ai_quota

logger = logging.getLogger(__name__)



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


class BulkPipelineView(APIView):
    """批量出题管线（Author → Classifier，跳过 Reviewer 以提速）。"""
    permission_classes = [IsAdmin, HasPlanFeature, HasQuota]
    required_feature = 'ai.generate'
    quota_resource = 'ai_question'

    def post(self, request):
        subject = str(request.data.get('subject', '')).strip()
        if not subject:
            return Response({'error': '请提供学科名称（subject）'}, status=400)

        total_target = int(request.data.get('total_target', 500))
        difficulty_dist = request.data.get('difficulty_dist')
        type_dist = request.data.get('type_dist')
        kp_code = request.data.get('kp_code')

        # 机构一次性额度检查
        institution = getattr(request.user, 'institution', None)
        if institution and institution.has_used_bulk_init:
            return Response({
                'error': '该机构已使用过批量初始化出题，如需新增题目请使用 ARC 精修管线或手动出题。',
                'code': 'bulk_init_already_used',
            }, status=403)

        try:
            from quizzes.services.bulk_pipeline import run_bulk_pipeline
            task_id = run_bulk_pipeline(
                subject=subject,
                total_target=total_target,
                difficulty_dist=difficulty_dist,
                type_dist=type_dist,
                kp_code=kp_code,
                institution=institution,
                created_by=request.user,
                institution_only=bool(institution),  # 机构用户仅限自有 KP
            )

            # 标记机构已使用
            if institution and not institution.has_used_bulk_init:
                institution.has_used_bulk_init = True
                institution.save(update_fields=['has_used_bulk_init'])

            increment_ai_quota(request.user.institution)
            return Response({'task_id': task_id, 'status': 'running'}, status=201)
        except Exception as exc:
            logger.exception("Bulk pipeline launch failed")
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

        from users.permissions import is_platform_admin
        from django.db.models import Q
        if is_platform_admin(request.user):
            task = get_object_or_404(ContentPipelineTask, pk=pk, status='review')
        else:
            inst = getattr(request.user, 'institution', None)
            if inst:
                task = get_object_or_404(
                    ContentPipelineTask,
                    Q(created_by__institution=inst) | Q(created_by__institution__isnull=True),
                    pk=pk, status='review',
                )
            else:
                task = get_object_or_404(ContentPipelineTask, pk=pk, status='review',
                    created_by__institution__isnull=True)
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
        data = {
            'id': task.id,
            'status': task.status,
            'progress': task.progress,
            'title': task.title,
            'current_stage': payload.get('current_stage', ''),
            'status_text': payload.get('status_text', ''),
            'stages': payload.get('stages', []),
            'created_at': task.created_at,
            'finished_at': task.finished_at,
        }
        if task.status == 'completed' and task.result:
            data['questions'] = task.result.get('questions', [])
        return Response(data)


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
