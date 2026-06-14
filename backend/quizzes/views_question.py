import os
import json
import csv
import io
import logging
from django.db.models import Case, IntegerField, Q, When
from django.conf import settings
from django.utils import timezone
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView
from quizzes.models import Question, UserQuestionStatus, KnowledgePoint
from quizzes.serializers import QuestionSerializer, QuestionListSerializer
from users.models import User
from users.views import IsMember
from users.permissions import IsAdmin, is_platform_admin, HasQuota
from ai_service import AIService
from quizzes.services.memorix_scheduler import build_adaptive_question_ids
from quizzes.ai_workflow import save_confirmed_questions

logger = logging.getLogger(__name__)


def _normalize_options(options):
    """Normalize options to list format. Handles legacy dict-format data."""
    if isinstance(options, dict):
        return [options[k] for k in sorted(options.keys())]
    return options


def _get_descendant_kp_ids(sub_ids):
    """给定 SUB 级知识点 ID 列表，递归收集所有下层 KP 级节点 ID。"""
    from quizzes.models import KnowledgePoint
    kp_ids = set()
    # 先收集所有 sub 的直接和间接后代
    queue = list(KnowledgePoint.objects.filter(id__in=sub_ids, level='sub'))
    while queue:
        node = queue.pop()
        children = KnowledgePoint.objects.filter(parent=node)
        for child in children:
            if child.level == 'kp':
                kp_ids.add(child.id)
            else:
                queue.append(child)
    return list(kp_ids)


class QuestionListView(generics.ListCreateAPIView):
    quota_resource = 'question'

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return QuestionSerializer  # 管理员创建题目需要完整字段
        return QuestionListSerializer  # 学生列表不含答案

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAdmin(), HasQuota()]
        return [IsMember()]

    def get_queryset(self):
        user = self.request.user
        qs = Question.objects.all().order_by('-created_at')

        # 预览模式：平台管理员查看指定机构题库
        preview_inst_id = self.request.query_params.get('preview_institution')
        if preview_inst_id:
            if not is_platform_admin(user):
                qs = qs.filter(institution__isnull=True)
            else:
                qs = qs.filter(institution_id=preview_inst_id)
        elif not is_platform_admin(user):
            # 机构数据隔离：机构成员可见本机构题库 + 全局题库；独立用户仅见全局题库
            inst = getattr(user, 'institution', None)
            if inst:
                qs = qs.filter(institution=inst)
            else:
                qs = qs.filter(institution__isnull=True)

        # Shared filters
        q = self.request.query_params.get('search')
        kp_id = self.request.query_params.get('kp')
        q_type = self.request.query_params.get('type')

        if q: qs = qs.filter(text__icontains=q)
        if kp_id: qs = qs.filter(knowledge_point_id=kp_id)
        if q_type: qs = qs.filter(q_type=q_type)

        # 按知识点名称模糊匹配（小宇 action_cards 传的是 kp_name 而非 ID）
        kp_name = self.request.query_params.get('kp_name')
        if kp_name:
            qs = qs.filter(knowledge_point__name__icontains=kp_name)

        # 按学科（SUB 级知识点）过滤；若过滤后为空则 fallback 到全量
        sub_ids = self.request.query_params.get('sub_ids', '')
        if sub_ids:
            sub_id_list = [int(x) for x in str(sub_ids).split(',') if x.strip().isdigit()]
            if sub_id_list:
                kp_ids = _get_descendant_kp_ids(sub_id_list)
                filtered = qs.filter(knowledge_point_id__in=kp_ids)
                if filtered.exists():
                    qs = filtered

        if is_platform_admin(user) and not self.request.query_params.get('limit'):
            return qs

        ids_param = self.request.query_params.get('ids') or self.request.query_params.get('question_ids')
        if ids_param:
            ids = []
            for raw in str(ids_param).split(','):
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    ids.append(int(raw))
                except (ValueError, TypeError):
                    continue
            if ids:
                ordering = Case(
                    *[When(id=qid, then=idx) for idx, qid in enumerate(ids)],
                    output_field=IntegerField(),
                )
                return qs.filter(id__in=ids).order_by(ordering)
            return Question.objects.none()

        if kp_id:
            return qs
        # 搜索场景优先返回检索结果，不启用训练抽题策略
        if q:
            return qs

        try:
            limit = int(self.request.query_params.get('limit', 10))
        except (ValueError, TypeError):
            limit = 10
        limit = max(1, min(limit, 50))

        preference = str(self.request.query_params.get('preference', 'balanced')).strip().lower()
        if preference not in {'balanced', 'new_first', 'review_first'}:
            preference = 'balanced'

        adaptive_plan = build_adaptive_question_ids(
            user=user,
            limit=limit,
            base_queryset=qs,
            preference=preference,
        )

        selected_ids = adaptive_plan['question_ids']
        self._study_mix_meta = adaptive_plan['meta']

        if not selected_ids:
            return Question.objects.none()

        ordering = Case(
            *[When(id=qid, then=idx) for idx, qid in enumerate(selected_ids)],
            output_field=IntegerField(),
        )
        return Question.objects.filter(id__in=selected_ids).order_by(ordering)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        records = list(page) if page is not None else list(queryset)

        context = self.get_serializer_context()
        if request.user.is_authenticated and records:
            qids = [q.id for q in records]
            statuses = UserQuestionStatus.objects.filter(
                user=request.user,
                question_id__in=qids,
            ).only('question_id', 'is_favorite', 'is_mastered')
            context['status_map'] = {s.question_id: s for s in statuses}

        serializer = self.get_serializer(records, many=True, context=context)
        if page is not None:
            return self.get_paginated_response(serializer.data)

        include_meta = str(request.query_params.get('include_meta', '0')).strip().lower() in {'1', 'true', 'yes'}
        if include_meta:
            return Response({
                'items': serializer.data,
                'meta': getattr(self, '_study_mix_meta', {}),
            })
        return Response(serializer.data)

    def perform_create(self, serializer):
        question = serializer.save(institution=self.request.user.institution)
        if not question.ai_answer:
            self.generate_ai_answer(question)

    def generate_ai_answer(self, question):
        ai_answer = AIService.generate_ai_answer(question)
        if ai_answer:
            question.ai_answer = ai_answer
            question.save(update_fields=['ai_answer'])


class QuestionDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Question.objects.all()
    serializer_class = QuestionSerializer
    permission_classes = [IsAdmin]

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()
        if not is_platform_admin(user):
            inst = getattr(user, 'institution', None)
            if inst:
                qs = qs.filter(institution=inst)
            else:
                qs = qs.filter(institution__isnull=True)
        return qs


class AdminQuestionListView(APIView):
    """
    管理员专用分页题目列表接口，支持搜索、知识点筛选和题型筛选。
    用于前端题库管理面板，性能优化版本，面向5000题以上的大规模题库。
    """
    permission_classes = [IsAdmin]

    def get(self, request):
        from users.permissions import is_platform_admin

        qs = Question.objects.select_related('knowledge_point').order_by('-created_at')
        if not is_platform_admin(request.user):
            inst = getattr(request.user, 'institution', None)
            if inst:
                qs = qs.filter(institution=inst)
            else:
                qs = qs.filter(institution__isnull=True)

        # 过滤条件
        search = request.query_params.get('search', '').strip()
        kp_id = request.query_params.get('kp_id')
        q_type = request.query_params.get('q_type')

        if search:
            qs = qs.filter(text__icontains=search)
        if kp_id and kp_id != '0':
            qs = qs.filter(knowledge_point_id=kp_id)
        if q_type and q_type != 'all':
            qs = qs.filter(q_type=q_type)

        # 分页
        total = qs.count()
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 50))
        offset = (page - 1) * page_size
        questions = qs[offset:offset + page_size]

        data = []
        for q in questions:
            data.append({
                'id': q.id,
                'text': q.text,
                'q_type': q.q_type,
                'subjective_type': q.subjective_type,
                'correct_answer': q.correct_answer or '',
                'grading_points': q.grading_points or '',
                'ai_answer': q.ai_answer or '',
                'difficulty': q.difficulty,
                'difficulty_level': q.difficulty_level,
                'difficulty_level_display': q.get_difficulty_level_display(),
                'options': _normalize_options(q.options),
                'knowledge_point': q.knowledge_point.id if q.knowledge_point else None,
                'knowledge_point_name': q.knowledge_point.name if q.knowledge_point else '无',
            })

        return Response({
            'total': total,
            'page': page,
            'page_size': page_size,
            'total_pages': (total + page_size - 1) // page_size,
            'results': data
        })


class ExportStructuredQuestionsView(APIView):
    """
    导出结构化题目数据（AI 可读格式）。
    直接同步至服务器本地 seed_questions.json。
    """
    permission_classes = [IsAdmin]

    def get(self, request):
        from users.permissions import is_platform_admin

        kp_id = request.query_params.get('kp_id')
        qs = Question.objects.select_related('knowledge_point').all()
        if not is_platform_admin(request.user):
            inst = getattr(request.user, 'institution', None)
            if inst:
                qs = qs.filter(institution=inst)
            else:
                qs = qs.filter(institution__isnull=True)
        if kp_id and kp_id != '0':
            qs = qs.filter(knowledge_point_id=kp_id)

        structured = []
        for q in qs:
            structured.append({
                "id": q.id,
                "knowledge_point": q.knowledge_point.name if q.knowledge_point else None,
                "question_type": q.q_type,
                "subjective_type": q.subjective_type,
                "difficulty_elo": q.difficulty,
                "difficulty_level": q.difficulty_level,
                "question_text": q.text,
                "options": _normalize_options(q.options),
                "correct_answer": q.correct_answer,
                "grading_points": q.grading_points,
                "ai_explanation": q.ai_answer,
            })

        data = {
            "total": len(structured),
            "format_version": "1.1",
            "description": "UniMind.ai Question Bank - Structured Export",
            "format_reference": {
                "question_type": "objective | subjective",
                "subjective_type": "noun | short | essay | calculate",
                "difficulty_elo": "800-1800 integer (harder = higher)",
                "options": "list of 4 strings for objective, null for subjective",
                "correct_answer": "option text for objective, reference answer for subjective",
                "grading_points": "scoring rubric, required for subjective questions"
            },
            "questions": structured
        }

        # 写入非公开目录，不通过 MEDIA_URL 暴露
        export_dir = os.path.join(settings.BASE_DIR, 'exports')
        os.makedirs(export_dir, exist_ok=True)
        file_path = os.path.join(export_dir, "seed_questions.json")
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return Response({
                "status": "success",
                "total": len(structured),
                "message": "已成功导出",
                "file": "seed_questions.json",
            })
        except Exception as e:
            return Response({"error": f"写入文件失败: {str(e)}"}, status=500)


class ImportCSVQuestionsView(APIView):
    MAX_SIZE = 5 * 1024 * 1024  # 5MB
    permission_classes = [IsAdmin, HasQuota]
    quota_resource = 'question'

    def post(self, request):
        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({'error': '未上传文件'}, status=400)

        if file_obj.size > self.MAX_SIZE:
            return Response({'error': f'CSV 文件大小不能超过 {self.MAX_SIZE // (1024*1024)}MB'}, status=400)
        if not file_obj.name.lower().endswith('.csv'):
            return Response({'error': '仅支持 .csv 格式文件'}, status=400)

        try:
            from django.db import transaction
            decoded_file = file_obj.read().decode('utf-8-sig')
            io_string = io.StringIO(decoded_file)
            reader = csv.DictReader(io_string)

            count = 0
            errors = []

            with transaction.atomic():
                for row in reader:
                    try:
                        text = row.get('text') or row.get('question') or row.get('题目')
                        answer = row.get('answer') or row.get('correct_answer') or row.get('答案')
                        q_type = row.get('type') or row.get('q_type') or row.get('题型') or 'objective'
                        difficulty = row.get('difficulty') or row.get('难度') or '1000'

                        if not text: continue

                        if '客观' in q_type or 'choice' in q_type: q_type = 'objective'
                        elif '主观' in q_type: q_type = 'subjective'

                        Question.objects.create(
                            text=text,
                            correct_answer=answer,
                            q_type=q_type,
                            difficulty=int(difficulty) if str(difficulty).isdigit() else 1000,
                            institution=request.user.institution,
                        )
                        count += 1
                    except Exception as e:
                        errors.append(f"Row error: {str(e)}")

            return Response({'status': 'success', 'count': count, 'errors': errors[:5]})

        except Exception as e:
            return Response({'error': f'CSV解析失败: {str(e)}'}, status=400)


# ── Assignment API ──────────────────────────────────────────────────

from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from quizzes.models import Assignment, AssignmentQuestion
from users.models import Class as ClassModel


class AssignmentCreateView(APIView):
    """POST /api/quizzes/assignments/create/ — 教师创建作业并发布给学生。"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        institution = getattr(user, 'institution', None)
        if not institution:
            return Response({'error': '无机构归属'}, status=403)

        role = getattr(user, 'institution_role', '')
        if role not in ('teacher', 'owner'):
            return Response({'error': '仅教师/机构主可创建作业'}, status=403)

        title = (request.data.get('title') or '').strip()
        question_ids = request.data.get('question_ids', [])
        class_ids = request.data.get('class_ids', [])
        due_date = request.data.get('due_date') or None
        points_per_q = int(request.data.get('points_per_question', 1))

        if not title:
            return Response({'error': '作业标题不能为空'}, status=400)
        if not question_ids:
            return Response({'error': '请选择至少一道题'}, status=400)

        try:
            assignment = Assignment.objects.create(
                title=title,
                institution=institution,
                created_by=user,
                due_date=due_date,
                status='published',
            )

            # 关联题目
            for i, qid in enumerate(question_ids):
                AssignmentQuestion.objects.create(
                    assignment=assignment,
                    question_id=int(qid),
                    order=i,
                    points=points_per_q,
                )

            # 关联班级
            if class_ids:
                classes = ClassModel.objects.filter(
                    id__in=class_ids, institution=institution
                )
                assignment.target_classes.set(classes)

            return Response({
                'id': assignment.id,
                'title': assignment.title,
                'question_count': len(question_ids),
                'class_count': assignment.target_classes.count(),
                'status': assignment.status,
                'due_date': assignment.due_date.isoformat() if assignment.due_date else None,
            })
        except Exception as e:
            logger.exception("Assignment creation failed")
            return Response({'error': f'创建失败: {str(e)}'}, status=500)


class ClassListView(APIView):
    """GET /api/quizzes/classes/ — 获取当前机构的班级列表。"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        institution = getattr(request.user, 'institution', None)
        if not institution:
            return Response([], safe=False)

        classes = ClassModel.objects.filter(institution=institution).values('id', 'name')
        return Response(list(classes))


class StudentAssignmentListView(APIView):
    """GET /api/quizzes/assignments/my/ — 学生端：我的作业列表。"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        institution = getattr(user, 'institution', None)
        if not institution:
            return Response([], safe=False)

        assignments = Assignment.objects.filter(
            institution=institution, status='published'
        ).order_by('-created_at')

        result = []
        for a in assignments:
            # Check if student has submitted
            try:
                sub = AssignmentSubmission.objects.get(assignment=a, student=user)
                submitted = True
                score = sub.score
            except AssignmentSubmission.DoesNotExist:
                submitted = False
                score = None

            result.append({
                'id': a.id,
                'title': a.title,
                'due_date': a.due_date.isoformat() if a.due_date else None,
                'question_count': a.assignment_questions.count(),
                'submitted': submitted,
                'score': score,
                'created_at': a.created_at.isoformat(),
            })

        return Response(result)


class StudentAssignmentDetailView(APIView):
    """GET /api/quizzes/assignments/<id>/questions/ — 学生端：获取作业题目（不含答案）。"""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        user = request.user
        institution = getattr(user, 'institution', None)

        try:
            assignment = Assignment.objects.get(id=pk, institution=institution, status='published')
        except Assignment.DoesNotExist:
            return Response({'error': '作业不存在'}, status=404)

        questions = []
        for aq in assignment.assignment_questions.select_related('question').order_by('order'):
            q = aq.question
            questions.append({
                'id': q.id,
                'text': q.text,
                'q_type': q.q_type,
                'options': q.options if q.q_type == 'objective' else None,
                'difficulty_level': q.difficulty_level,
                'kp_name': q.knowledge_point.name if q.knowledge_point else '',
                'points': aq.points,
                'order': aq.order,
            })

        # Check existing submission
        sub = AssignmentSubmission.objects.filter(assignment=assignment, student=user).first()

        return Response({
            'id': assignment.id,
            'title': assignment.title,
            'due_date': assignment.due_date.isoformat() if assignment.due_date else None,
            'questions': questions,
            'submitted': sub is not None,
            'previous_answers': sub.answers if sub else {},
            'score': sub.score if sub else None,
        })


class StudentAssignmentSubmitView(APIView):
    """POST /api/quizzes/assignments/submit/ — 学生提交作业。"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        assignment_id = request.data.get('assignment_id')
        answers = request.data.get('answers', {})

        if not assignment_id:
            return Response({'error': '缺少作业 ID'}, status=400)
        if not answers:
            return Response({'error': '请回答至少一题'}, status=400)

        institution = getattr(user, 'institution', None)
        try:
            assignment = Assignment.objects.get(id=int(assignment_id), institution=institution, status='published')
        except Assignment.DoesNotExist:
            return Response({'error': '作业不存在'}, status=404)

        # Check due date
        if assignment.due_date and timezone.now() > assignment.due_date:
            return Response({'error': '作业已截止'}, status=400)

        # Auto-grade objective questions
        total_score = 0
        max_score = 0
        graded_count = 0
        for aq in assignment.assignment_questions.all():
            q = aq.question
            max_score += aq.points
            user_answer = str(answers.get(str(q.id), '')).strip()
            if q.q_type == 'objective' and q.answer:
                if user_answer == q.answer.strip():
                    total_score += aq.points
                    graded_count += 1
                elif user_answer:
                    graded_count += 1

        sub, created = AssignmentSubmission.objects.update_or_create(
            assignment=assignment, student=user,
            defaults={
                'answers': answers,
                'score': round(total_score / max_score * 100, 1) if max_score > 0 else None,
            },
        )

        return Response({
            'id': sub.id,
            'submitted': True,
            'graded_count': graded_count,
            'total_questions': assignment.assignment_questions.count(),
            'score': sub.score,
            'message': f'已提交，客观题自动批改 {graded_count} 题',
        })
