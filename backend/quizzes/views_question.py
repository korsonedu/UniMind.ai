import os
import json
import csv
import io
import logging
from django.db.models import Case, IntegerField, When
from django.conf import settings
from django.utils import timezone
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView
from quizzes.models import Question, UserQuestionStatus, KnowledgePoint
from quizzes.serializers import QuestionSerializer
from users.models import User
from users.views import IsMember
from users.permissions import IsAdmin, is_platform_admin
from ai_service import AIService
from quizzes.services.study_planner import build_adaptive_question_ids
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
    serializer_class = QuestionSerializer

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAdmin()]
        return [IsMember()]

    def get_queryset(self):
        user = self.request.user
        qs = Question.objects.all().order_by('-created_at')

        # 机构数据隔离：机构成员可见本机构题库 + 全局题库；独立用户仅见全局题库
        if not is_platform_admin(user):
            inst = getattr(user, 'institution', None)
            if inst:
                from django.db.models import Q
                qs = qs.filter(Q(institution=inst) | Q(institution__isnull=True))
            else:
                qs = qs.filter(institution__isnull=True)

        # Shared filters
        q = self.request.query_params.get('search')
        kp_id = self.request.query_params.get('kp')
        q_type = self.request.query_params.get('type')

        if q: qs = qs.filter(text__icontains=q)
        if kp_id: qs = qs.filter(knowledge_point_id=kp_id)
        if q_type: qs = qs.filter(q_type=q_type)

        # 按学科（SUB 级知识点）过滤
        sub_ids = self.request.query_params.get('sub_ids', '')
        if sub_ids:
            sub_id_list = [int(x) for x in str(sub_ids).split(',') if x.strip().isdigit()]
            if sub_id_list:
                # 递归收集 sub 级下的所有 kp 节点
                kp_ids = _get_descendant_kp_ids(sub_id_list)
                qs = qs.filter(knowledge_point_id__in=kp_ids)

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
        question = serializer.save()
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
        from django.db.models import Q
        user = self.request.user
        qs = super().get_queryset()
        if not is_platform_admin(user):
            inst = getattr(user, 'institution', None)
            if inst:
                qs = qs.filter(Q(institution=inst) | Q(institution__isnull=True))
            else:
                qs = qs.filter(institution__isnull=True)
        return qs


class BulkImportQuestionsView(APIView):
    permission_classes = [IsAdmin]
    def post(self, request):
        questions_data = request.data.get('questions', [])
        kp_id = request.data.get('kp_id')
        if kp_id:
            for q in questions_data:
                q['kp_id'] = q.get('kp_id') or kp_id

        created_count = save_confirmed_questions(questions_data, institution=request.user.institution)
        return Response({'status': 'success', 'count': created_count})


class AdminQuestionListView(APIView):
    """
    管理员专用分页题目列表接口，支持搜索、知识点筛选和题型筛选。
    用于前端题库管理面板，性能优化版本，面向5000题以上的大规模题库。
    """
    permission_classes = [IsAdmin]

    def get(self, request):
        from users.permissions import is_platform_admin
        from django.db.models import Q

        qs = Question.objects.select_related('knowledge_point').order_by('-created_at')
        if not is_platform_admin(request.user):
            inst = getattr(request.user, 'institution', None)
            if inst:
                qs = qs.filter(Q(institution=inst) | Q(institution__isnull=True))
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
        from django.db.models import Q

        kp_id = request.query_params.get('kp_id')
        qs = Question.objects.select_related('knowledge_point').all()
        if not is_platform_admin(request.user):
            inst = getattr(request.user, 'institution', None)
            if inst:
                qs = qs.filter(Q(institution=inst) | Q(institution__isnull=True))
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

        # 写入 MEDIA_ROOT 而非源码目录
        export_dir = os.path.join(settings.MEDIA_ROOT, 'exports')
        os.makedirs(export_dir, exist_ok=True)
        file_path = os.path.join(export_dir, "seed_questions.json")
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            file_url = request.build_absolute_uri(settings.MEDIA_URL + 'exports/seed_questions.json')
            return Response({
                "status": "success",
                "total": len(structured),
                "message": "已成功导出",
                "file_url": file_url,
            })
        except Exception as e:
            return Response({"error": f"写入文件失败: {str(e)}"}, status=500)


class ImportCSVQuestionsView(APIView):
    MAX_SIZE = 5 * 1024 * 1024  # 5MB
    permission_classes = [IsAdmin]

    def post(self, request):
        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({'error': '未上传文件'}, status=400)

        if file_obj.size > self.MAX_SIZE:
            return Response({'error': f'CSV 文件大小不能超过 {self.MAX_SIZE // (1024*1024)}MB'}, status=400)
        if not file_obj.name.lower().endswith('.csv'):
            return Response({'error': '仅支持 .csv 格式文件'}, status=400)

        try:
            decoded_file = file_obj.read().decode('utf-8-sig')
            io_string = io.StringIO(decoded_file)
            reader = csv.DictReader(io_string)

            count = 0
            errors = []

            for row in reader:
                try:
                    # Expected CSV headers: text, answer, type(optional), difficulty(optional)
                    # Mapping flexible headers
                    text = row.get('text') or row.get('question') or row.get('题目')
                    answer = row.get('answer') or row.get('correct_answer') or row.get('答案')
                    q_type = row.get('type') or row.get('q_type') or row.get('题型') or 'objective'
                    difficulty = row.get('difficulty') or row.get('难度') or '1000'

                    if not text: continue

                    # Clean type
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
