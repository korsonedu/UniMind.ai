import os
import json
import csv
import io
import logging
from django.db.models import Case, Count, IntegerField, Q, When
from django.conf import settings
from django.utils import timezone
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView
from quizzes.models import Question, UserQuestionStatus, KnowledgePoint
from core.utils import apply_institution_filter, get_content_institution
from quizzes.serializers import QuestionSerializer, QuestionListSerializer
from users.views import IsMember
from users.models import User
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
    """给定 SUB 级知识点 ID 列表，递归收集所有下层 KP 级节点 ID。

    .. deprecated::
        Use :func:`quizzes.services.knowledge_tree.get_descendant_kp_ids` instead.
        Kept as a thin wrapper for backward compatibility.
    """
    import warnings
    from quizzes.services.knowledge_tree import get_descendant_kp_ids
    warnings.warn(
        '_get_descendant_kp_ids is deprecated; '
        'use quizzes.services.knowledge_tree.get_descendant_kp_ids directly.',
        DeprecationWarning,
        stacklevel=2,
    )
    return get_descendant_kp_ids(sub_ids)


class QuestionListView(generics.ListCreateAPIView):
    quota_resource = 'question'

    def get_serializer(self, *args, **kwargs):
        serializer = super().get_serializer(*args, **kwargs)
        if self.request.method in ('POST', 'PUT', 'PATCH'):
            serializer.fields['knowledge_point'].queryset = apply_institution_filter(
                KnowledgePoint.objects.filter(level='kp'), self.request.user, self.request)
            serializer.fields['institution'].read_only = True
        return serializer

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

        qs = apply_institution_filter(qs, user, self.request)

        # Shared filters
        q = self.request.query_params.get('search')
        kp_id = self.request.query_params.get('kp')
        q_type = self.request.query_params.get('type')

        if q: qs = qs.filter(text__icontains=q)
        if kp_id: qs = qs.filter(knowledge_point_id=kp_id)
        if q_type: qs = qs.filter(q_type=q_type)
        difficulty_level = self.request.query_params.get('difficulty_level')
        if difficulty_level in dict(Question.DIFFICULTY_LEVELS):
            qs = qs.filter(difficulty_level=difficulty_level)

        # 按知识点名称模糊匹配（小宇 action_cards 传的是 kp_name 而非 ID）
        kp_name = self.request.query_params.get('kp_name')
        if kp_name:
            qs = qs.filter(knowledge_point__name__icontains=kp_name)

        # 按学科（SUB 级知识点）过滤；若过滤后为空则返回空集
        sub_ids = self.request.query_params.get('sub_ids', '')
        if sub_ids:
            sub_id_list = [int(x) for x in str(sub_ids).split(',') if x.strip().isdigit()]
            if sub_id_list:
                kp_ids = _get_descendant_kp_ids(sub_id_list)
                filtered = qs.filter(knowledge_point_id__in=kp_ids)
                if filtered.exists():
                    qs = filtered
                else:
                    qs = Question.objects.none()

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
        question = serializer.save(institution=get_content_institution())
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

    def get_serializer(self, *args, **kwargs):
        serializer = super().get_serializer(*args, **kwargs)
        if self.request.method in ('POST', 'PUT', 'PATCH'):
            serializer.fields['knowledge_point'].queryset = apply_institution_filter(
                KnowledgePoint.objects.filter(level='kp'), self.request.user, self.request)
            serializer.fields['institution'].read_only = True
        return serializer

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()
        qs = apply_institution_filter(qs, user, self.request)
        return qs

    def perform_update(self, serializer):
        serializer.save(institution=get_content_institution())


class AdminQuestionListView(APIView):
    """
    管理员专用分页题目列表接口，支持搜索、知识点筛选和题型筛选。
    用于前端题库管理面板，性能优化版本，面向5000题以上的大规模题库。
    """
    permission_classes = [IsAdmin]

    def get(self, request):
        from users.permissions import is_platform_admin

        qs = Question.objects.select_related('knowledge_point').order_by('-created_at')
        qs = apply_institution_filter(qs, request.user, request)

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
