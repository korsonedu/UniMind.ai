import random
from django.utils import timezone
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from quizzes.models import (
    TeacherExam, ExamQuestion, OnlineExamAttempt, Question,
    ExamQuestionResult, QuizExam,
)
from quizzes.serializers import (
    TeacherExamSerializer, ExamQuestionSerializer, OnlineExamAttemptSerializer,
)
from quizzes.ai_workflow import grade_answer_for_user, mark_questions_reviewed
from users.permissions import IsAdmin, IsMember

import logging
logger = logging.getLogger(__name__)


def _inst_q(user):
    """返回机构数据隔离 Q 对象"""
    from users.permissions import is_platform_admin
    if is_platform_admin(user):
        return Q()
    inst = getattr(user, 'institution', None)
    if inst:
        return Q(institution=inst) | Q(institution__isnull=True)
    return Q(institution__isnull=True)


class OnlineExamCreateView(APIView):
    """教师创建/更新在线考试。POST = create, PUT = update"""
    permission_classes = [IsAdmin]

    def post(self, request):
        """创建在线考试"""
        title = request.data.get('title', '').strip()
        if not title:
            return Response({'error': '考试标题不能为空'}, status=400)

        question_ids = request.data.get('question_ids', [])
        points = request.data.get('points', 1.0)
        points_map = request.data.get('points_map', {})  # {qid: points}

        inst = request.user.institution

        exam = TeacherExam.objects.create(
            title=title,
            description=request.data.get('description', ''),
            exam_type='online',
            duration_minutes=request.data.get('duration_minutes'),
            start_time=request.data.get('start_time'),
            end_time=request.data.get('end_time'),
            shuffle_questions=request.data.get('shuffle_questions', True),
            shuffle_options=request.data.get('shuffle_options', True),
            max_attempts=request.data.get('max_attempts', 1),
            passing_score=request.data.get('passing_score'),
            created_by=request.user,
            institution=inst,
        )

        # 关联题目
        for idx, qid in enumerate(question_ids):
            q_points = points_map.get(str(qid), points)
            ExamQuestion.objects.create(
                exam=exam,
                question_id=qid,
                order=idx + 1,
                points=float(q_points),
            )

        return Response(TeacherExamSerializer(exam).data, status=201)

    def put(self, request, pk=None):
        """更新在线考试"""
        pk = pk or request.data.get('id')
        exam = get_object_or_404(TeacherExam, Q(id=pk) & _inst_q(request.user))
        if exam.exam_type != 'online':
            return Response({'error': '仅支持编辑在线考试'}, status=400)

        for field in ['title', 'description', 'duration_minutes', 'start_time',
                       'end_time', 'shuffle_questions', 'shuffle_options',
                       'max_attempts', 'passing_score']:
            if field in request.data:
                setattr(exam, field, request.data[field])
        exam.save()

        # 更新题目（如果提供）
        if 'question_ids' in request.data:
            question_ids = request.data['question_ids']
            points = request.data.get('points', 1.0)
            points_map = request.data.get('points_map', {})
            exam.exam_questions.all().delete()
            for idx, qid in enumerate(question_ids):
                q_points = points_map.get(str(qid), points)
                ExamQuestion.objects.create(
                    exam=exam, question_id=qid,
                    order=idx + 1, points=float(q_points),
                )

        return Response(TeacherExamSerializer(exam).data)


class OnlineExamStartView(APIView):
    """学生开始在线考试 — 返回题目列表 + 倒计时信息"""
    permission_classes = [IsMember]

    def post(self, request, pk):
        exam = get_object_or_404(TeacherExam, id=pk, exam_type='online')
        user = request.user

        # 检查时间窗口
        now = timezone.now()
        if exam.start_time and now < exam.start_time:
            return Response({'error': '考试尚未开始'}, status=400)
        if exam.end_time and now > exam.end_time:
            return Response({'error': '考试已结束'}, status=400)

        # 检查尝试次数
        existing_attempts = OnlineExamAttempt.objects.filter(user=user, exam=exam).count()
        if existing_attempts >= exam.max_attempts:
            return Response({'error': f'已达到最大尝试次数（{exam.max_attempts}）'}, status=400)

        # 检查是否有进行中的尝试
        attempt = OnlineExamAttempt.objects.filter(
            user=user, exam=exam, status='in_progress'
        ).first()

        if not attempt:
            # 生成题目顺序
            eqs = list(exam.exam_questions.select_related('question').order_by('order'))
            question_ids = [eq.question_id for eq in eqs]
            if exam.shuffle_questions:
                random.shuffle(question_ids)

            # 重新按 id 顺序映射 order
            qid_to_eq = {eq.question_id: eq for eq in eqs}
            ordered_eqs = [qid_to_eq[qid] for qid in question_ids]

            attempt = OnlineExamAttempt.objects.create(
                user=user, exam=exam,
                question_order=question_ids,
            )
        else:
            # 恢复进行中的考试
            qid_to_eq = {eq.question_id: eq for eq in exam.exam_questions.select_related('question').all()}
            ordered_eqs = [qid_to_eq[qid] for qid in attempt.question_order if qid in qid_to_eq]

        # 计算剩余时间
        remaining_seconds = None
        if exam.duration_minutes:
            elapsed = (now - attempt.started_at).total_seconds()
            remaining_seconds = max(0, exam.duration_minutes * 60 - elapsed)

        # 如果有截止时间，取两者最小值
        if exam.end_time:
            end_remaining = (exam.end_time - now).total_seconds()
            if remaining_seconds is None:
                remaining_seconds = max(0, end_remaining)
            else:
                remaining_seconds = max(0, min(remaining_seconds, end_remaining))

        questions_data = []
        for eq in ordered_eqs:
            q = eq.question
            q_data = {
                'id': q.id,
                'question_text': q.question_text,
                'question_type': q.question_type,
                'options': q.options,
                'points': float(eq.points),
            }
            # 选项乱序
            if exam.shuffle_options and q.options and isinstance(q.options, list):
                opts = list(q.options)
                # 给每个选项加 original_label 以便映射答案
                for i, opt in enumerate(opts):
                    if isinstance(opt, dict):
                        opt['_original_label'] = opt.get('label', chr(65 + i))
                random.shuffle(opts)
                q_data['options'] = opts
            questions_data.append(q_data)

        return Response({
            'attempt_id': attempt.id,
            'exam_title': exam.title,
            'duration_minutes': exam.duration_minutes,
            'remaining_seconds': int(remaining_seconds) if remaining_seconds is not None else None,
            'started_at': attempt.started_at,
            'questions': questions_data,
            'saved_answers': attempt.answers,
        })


class OnlineExamSubmitView(APIView):
    """学生提交考试答案 → 后台判分"""
    permission_classes = [IsMember]

    def post(self, request, pk):
        exam = get_object_or_404(TeacherExam, id=pk, exam_type='online')
        user = request.user

        attempt = get_object_or_404(OnlineExamAttempt, user=user, exam=exam, status='in_progress')

        # 检查考试是否超时
        if exam.duration_minutes and attempt.started_at:
            elapsed = (timezone.now() - attempt.started_at).total_seconds()
            if elapsed > exam.duration_minutes * 60:
                return Response({'error': '考试时间已到'}, status=400)

        answers = request.data.get('answers', {})
        attempt.answers = answers
        attempt.submitted_at = timezone.now()
        attempt.status = 'submitted'
        attempt.save()

        # 构造判分数据
        questions_data = []
        eqs = {eq.question_id: eq for eq in exam.exam_questions.all()}
        for qid_str, answer in answers.items():
            qid = int(qid_str)
            eq = eqs.get(qid)
            questions_data.append({
                'question_id': qid,
                'user_answer': str(answer),
                'max_score': float(eq.points) if eq else 1.0,
            })

        # 创建 QuizExam 用于判分引擎
        quiz_exam = QuizExam.objects.create(user=user)

        # 标记题目为已复习
        mark_questions_reviewed(
            user=user,
            question_ids=[d['question_id'] for d in questions_data],
        )

        # 同步判分（在线考试需要即时反馈）
        total_score = 0.0
        total_max = 0.0
        question_results = []

        for qd in questions_data:
            try:
                question = Question.objects.get(id=qd['question_id'])
            except Question.DoesNotExist:
                continue
            result = grade_answer_for_user(user, question, qd['user_answer'])
            actual_score = result['score']
            actual_max = result.get('max_score', qd['max_score'])
            total_score += actual_score
            total_max += actual_max

            question_results.append({
                'question_id': qd['question_id'],
                'score': actual_score,
                'max_score': actual_max,
                'is_correct': result.get('is_correct', False),
                'feedback': result.get('feedback', ''),
                'analysis': result.get('analysis', ''),
            })

            # 持久化逐题结果
            ExamQuestionResult.objects.update_or_create(
                exam=quiz_exam,
                question=question,
                defaults={
                    'user_answer': qd['user_answer'],
                    'score': actual_score,
                    'max_score': actual_max,
                    'is_correct': result.get('is_correct', False),
                    'feedback': result.get('feedback', ''),
                    'analysis': result.get('analysis', ''),
                },
            )

        # 更新 attempt
        attempt.score = total_score
        attempt.max_score = total_max
        attempt.question_results = question_results
        attempt.status = 'graded'
        attempt.save()

        # 更新 quiz_exam
        quiz_exam.total_score = total_score
        quiz_exam.max_score = total_max
        quiz_exam.save()

        return Response({
            'attempt_id': attempt.id,
            'score': total_score,
            'max_score': total_max,
            'passed': total_score >= exam.passing_score if exam.passing_score else None,
            'question_results': question_results,
        })


class OnlineExamResultView(APIView):
    """学生查看考试成绩详情"""
    permission_classes = [IsMember]

    def get(self, request, pk):
        exam = get_object_or_404(TeacherExam, id=pk, exam_type='online')
        user = request.user

        attempts = OnlineExamAttempt.objects.filter(
            user=user, exam=exam
        ).order_by('-started_at')

        data = []
        for attempt in attempts:
            data.append(OnlineExamAttemptSerializer(attempt).data)

        return Response({
            'exam': TeacherExamSerializer(exam).data,
            'attempts': data,
        })


class OnlineExamTeacherResultsView(APIView):
    """教师查看全班考试成绩"""
    permission_classes = [IsAdmin]

    def get(self, request, pk):
        exam = get_object_or_404(TeacherExam, Q(id=pk) & _inst_q(request.user))

        attempts = OnlineExamAttempt.objects.filter(
            exam=exam, status='graded'
        ).select_related('user').order_by('-score')

        data = []
        for attempt in attempts:
            data.append(OnlineExamAttemptSerializer(attempt).data)

        # 统计
        scores = [a.score for a in attempts if a.score is not None]
        stats = {
            'total_attempts': len(attempts),
            'graded_count': len(scores),
            'avg_score': round(sum(scores) / len(scores), 1) if scores else 0,
            'max_score_achieved': max(scores) if scores else 0,
            'min_score_achieved': min(scores) if scores else 0,
            'pass_count': len([s for s in scores if exam.passing_score and s >= exam.passing_score]) if exam.passing_score else None,
        }

        return Response({
            'exam': TeacherExamSerializer(exam).data,
            'stats': stats,
            'results': data,
        })


class OnlineExamQuestionListView(APIView):
    """获取在线考试的题目列表（教师管理用）"""
    permission_classes = [IsAdmin]

    def get(self, request, pk):
        exam = get_object_or_404(TeacherExam, Q(id=pk) & _inst_q(request.user))
        eqs = exam.exam_questions.select_related('question').order_by('order')
        return Response({
            'questions': ExamQuestionSerializer(eqs, many=True).data,
        })
