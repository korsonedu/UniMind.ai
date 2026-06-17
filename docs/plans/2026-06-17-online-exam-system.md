# 在线考试系统 Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** 将 TeacherExam 从纯 PDF 上传扩展到支持在线考试（组卷+限时+自动评分+基础防作弊）。

**Architecture:** 扩展 TeacherExam 模型（加 exam_type 等字段），新增 ExamQuestion M2M through 模型和 OnlineExamAttempt 模型，后端 6 个新 View，前端 2 个新页面 + 教师管理面板改造。判分完全复用现有 `grade_answer_for_user` + `run_exam_grading` 引擎。

**Tech Stack:** Django 6.0 + DRF + React 19 + TypeScript + shadcn/ui

---

## Task 1: 本地终端中项目初始状态检查

**Objective:** 确认项目可正常启动，当前 migration 状态。

**Files:** None

**Step 1:** 检查项目状态

```bash
cd /Users/eular/Desktop/UniMind/UniMindCode/backend
python manage.py check
```

**Step 2:** 查看 migration 状态

```bash
python manage.py showmigrations --plan | tail -10
```

**Expected:** quizzes migrations 到 0045，users 到 0055，无未应用的 migration。

---

## Task 2: 扩展 TeacherExam 模型 + 新增 ExamQuestion 模型

**Objective:** 在 TeacherExam 上加 online 考试字段，新增 ExamQuestion through 模型。

**Files:**
- Modify: `backend/quizzes/models.py`（TeacherExam 模型，约 282 行）
- Create: `backend/quizzes/migrations/0046_add_online_exam.py`

**Step 1:** 编辑 `backend/quizzes/models.py`，修改 TeacherExam 模型

在现有 TeacherExam 模型字段后添加：

```python
class TeacherExam(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    exam_pdf = models.FileField(upload_to="teacher_exams/", blank=True, null=True, help_text="PDF 模式试卷文件，online 模式可空")
    # ── 新增 online 考试字段 ──
    EXAM_TYPES = (
        ('pdf', 'PDF试卷'),
        ('online', '在线考试'),
    )
    exam_type = models.CharField(max_length=10, choices=EXAM_TYPES, default='pdf', verbose_name='考试类型')
    duration_minutes = models.PositiveIntegerField(null=True, blank=True, verbose_name='考试时长(分钟)')
    start_time = models.DateTimeField(null=True, blank=True, verbose_name='开考时间')
    end_time = models.DateTimeField(null=True, blank=True, verbose_name='截止时间')
    shuffle_questions = models.BooleanField(default=True, verbose_name='题目乱序')
    shuffle_options = models.BooleanField(default=True, verbose_name='选项乱序')
    max_attempts = models.PositiveIntegerField(default=1, verbose_name='最大尝试次数')
    passing_score = models.FloatField(null=True, blank=True, verbose_name='及格分数')
    # ── 原有字段 ──
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="teacher_exams")
    institution = models.ForeignKey("users.Institution", on_delete=models.SET_NULL, null=True, blank=True, related_name="teacher_exams", verbose_name="所属机构")
```

**Step 2:** 在 `AssignmentQuestionResult` 和 `ExamTemplate` 之间，新增 ExamQuestion 和 OnlineExamAttempt 模型：

```python
class ExamQuestion(models.Model):
    """在线考试的题目关联（带排序和分值）"""
    exam = models.ForeignKey('TeacherExam', on_delete=models.CASCADE, related_name='exam_questions')
    question = models.ForeignKey('Question', on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=0)
    points = models.FloatField(default=1.0, verbose_name='本题分值')

    class Meta:
        ordering = ['order']
        unique_together = [('exam', 'question')]


class OnlineExamAttempt(models.Model):
    """学生在线考试作答记录"""
    STATUS_CHOICES = (
        ('in_progress', '作答中'),
        ('submitted', '已提交'),
        ('graded', '已批改'),
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='online_exam_attempts')
    exam = models.ForeignKey('TeacherExam', on_delete=models.CASCADE, related_name='attempts')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='in_progress')
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    answers = models.JSONField(default=dict, help_text='{question_id: user_answer}')
    question_order = models.JSONField(default=list, help_text='该学生看到的题目顺序 [question_id, ...]')
    score = models.FloatField(null=True, blank=True)
    max_score = models.FloatField(null=True, blank=True)
    # 逐题结果（判分后填充）
    question_results = models.JSONField(default=list, blank=True, help_text='[{question_id, score, max_score, is_correct, feedback}]')

    class Meta:
        ordering = ['-started_at']
        unique_together = [('user', 'exam')]  # 默认只有一次有效尝试
```

**Step 3:** 生成 migration

```bash
cd /Users/eular/Desktop/UniMind/UniMindCode/backend
python manage.py makemigrations quizzes --name add_online_exam
```

**Step 4:** 应用 migration

```bash
python manage.py migrate
```

**Verification:** `python manage.py check` 通过，`python manage.py showmigrations quizzes | grep online_exam` 显示 `[X]`。

---

## Task 3: 更新 Serializers

**Objective:** 更新 TeacherExamSerializer 支持新字段，新增 ExamQuestionSerializer、OnlineExamAttemptSerializer。

**Files:**
- Modify: `backend/quizzes/serializers.py`

**Step 1:** 更新 TeacherExamSerializer（约 146-150 行）

```python
class TeacherExamSerializer(serializers.ModelSerializer):
    question_count = serializers.SerializerMethodField()
    attempt_count = serializers.SerializerMethodField()

    class Meta:
        model = TeacherExam
        fields = (
            'id', 'title', 'description', 'exam_pdf',
            'exam_type', 'duration_minutes', 'start_time', 'end_time',
            'shuffle_questions', 'shuffle_options', 'max_attempts', 'passing_score',
            'created_at', 'created_by', 'institution',
            'question_count', 'attempt_count',
        )
        read_only_fields = ('id', 'created_at', 'created_by', 'institution')

    def get_question_count(self, obj):
        return obj.exam_questions.count() if hasattr(obj, 'exam_questions') else 0

    def get_attempt_count(self, obj):
        return obj.attempts.count() if hasattr(obj, 'attempts') else 0
```

**Step 2:** 新增 ExamQuestionSerializer 和 OnlineExamAttemptSerializer：

```python
class ExamQuestionSerializer(serializers.ModelSerializer):
    question_text = serializers.CharField(source='question.question_text', read_only=True)
    question_type = serializers.CharField(source='question.question_type', read_only=True)
    options = serializers.JSONField(source='question.options', read_only=True)
    correct_answer = serializers.CharField(source='question.correct_answer', read_only=True)

    class Meta:
        model = ExamQuestion
        fields = ('id', 'exam', 'question', 'order', 'points',
                  'question_text', 'question_type', 'options', 'correct_answer')


class OnlineExamAttemptSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='user.nickname', read_only=True, default='')

    class Meta:
        model = OnlineExamAttempt
        fields = ('id', 'user', 'student_name', 'exam', 'status',
                  'started_at', 'submitted_at', 'score', 'max_score',
                  'question_results', 'question_order')
        read_only_fields = ('id', 'user', 'started_at', 'question_order')
```

**Verification:** `python manage.py check` 通过。

---

## Task 4: 新增后端 API Views

**Objective:** 创建 6 个在线考试相关 View。

**Files:**
- Create: `backend/quizzes/views_online_exam.py`
- Modify: `backend/quizzes/urls.py`

**Step 1:** 创建 `backend/quizzes/views_online_exam.py`

```python
import random
import time
from django.utils import timezone
from django.db.models import Q, Prefetch
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
from quizzes.ai_workflow import run_exam_grading, mark_questions_reviewed
from users.permissions import IsAdmin, IsMember
from users.views import IsMember

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

        answers = request.data.get('answers', {})
        attempt.answers = answers
        attempt.submitted_at = timezone.now()
        attempt.status = 'submitted'
        attempt.save()

        # 构造判分数据（复用现有 run_exam_grading 的格式）
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
        from quizzes.ai_workflow import grade_answer_for_user
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
```

**Step 2:** 编辑 `backend/quizzes/urls.py`，添加路由：

在现有 teacher-exams 路由附近添加：

```python
from .views_online_exam import (
    OnlineExamCreateView, OnlineExamStartView, OnlineExamSubmitView,
    OnlineExamResultView, OnlineExamTeacherResultsView, OnlineExamQuestionListView,
)
```

在 urlpatterns 中添加：

```python
    # 在线考试
    path('online-exams/create/', OnlineExamCreateView.as_view(), name='online-exam-create'),
    path('online-exams/<int:pk>/update/', OnlineExamCreateView.as_view(), name='online-exam-update'),
    path('online-exams/<int:pk>/questions/', OnlineExamQuestionListView.as_view(), name='online-exam-questions'),
    path('online-exams/<int:pk>/start/', OnlineExamStartView.as_view(), name='online-exam-start'),
    path('online-exams/<int:pk>/submit/', OnlineExamSubmitView.as_view(), name='online-exam-submit'),
    path('online-exams/<int:pk>/result/', OnlineExamResultView.as_view(), name='online-exam-result'),
    path('online-exams/<int:pk>/results/', OnlineExamTeacherResultsView.as_view(), name='online-exam-teacher-results'),
```

**Verification:** `python manage.py check` 通过，无 import 错误。

---

## Task 5: 后端集成测试

**Objective:** 验证后端 API 可正常访问。

**Files:** None

**Step 1:** 启动后端服务

```bash
cd /Users/eular/Desktop/UniMind/UniMindCode/backend
python manage.py runserver 0.0.0.0:8020 &
sleep 3
```

**Step 2:** 测试 API 端点（需先登录获取 cookie）

用 `curl` 测试创建在线考试：

```bash
# 先登录获取 session
curl -c /tmp/cookies.txt -X POST http://localhost:8020/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"testpass"}'

# 创建在线考试
curl -b /tmp/cookies.txt -X POST http://localhost:8020/api/quizzes/online-exams/create/ \
  -H "Content-Type: application/json" \
  -d '{"title":"测试在线考试","duration_minutes":30,"question_ids":[1,2,3]}'
```

**Step 3:** 验证访问

```bash
curl -b /tmp/cookies.txt http://localhost:8020/api/quizzes/teacher-exams/ | python -m json.tool
```

**Expected:** 返回包含新创建在线考试的列表。

---

## Task 6: 前端 — 学生在线考试页面

**Objective:** 学生可以开始在线考试、答题、提交。

**Files:**
- Create: `frontend/src/pages/OnlineExam.tsx`

**New Route（暂不注册路由，先创建页面组件）:** `/exam/:examId`

**Step 1:** 创建 `frontend/src/pages/OnlineExam.tsx`

完整组件代码（约 250 行）：

```tsx
import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { toast } from 'sonner';
import { Clock, AlertTriangle, ChevronLeft, ChevronRight, Send } from 'lucide-react';
import api from '@/lib/api';

interface QuestionData {
  id: number;
  question_text: string;
  question_type: string;
  options: Array<{ label: string; text: string; _original_label?: string }>;
  points: number;
}

interface ExamSession {
  attempt_id: number;
  exam_title: string;
  duration_minutes: number | null;
  remaining_seconds: number | null;
  questions: QuestionData[];
  saved_answers: Record<string, string>;
}

export function OnlineExam() {
  const { examId } = useParams<{ examId: string }>();
  const navigate = useNavigate();
  const [session, setSession] = useState<ExamSession | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [currentIdx, setCurrentIdx] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [timeLeft, setTimeLeft] = useState<number | null>(null);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState('');
  const timerRef = useRef<ReturnType<typeof setInterval>>();

  // 开始考试
  const startExam = useCallback(async () => {
    try {
      const r = await api.post(`/quizzes/online-exams/${examId}/start/`);
      setSession(r.data);
      setAnswers(r.data.saved_answers || {});
      if (r.data.remaining_seconds != null) {
        setTimeLeft(r.data.remaining_seconds);
      }
    } catch (e: any) {
      setError(e.response?.data?.error || '开始考试失败');
    }
  }, [examId]);

  useEffect(() => {
    if (examId) startExam();
  }, [examId, startExam]);

  // 倒计时
  useEffect(() => {
    if (timeLeft == null || timeLeft <= 0) return;
    timerRef.current = setInterval(() => {
      setTimeLeft(prev => {
        if (prev == null || prev <= 1) {
          clearInterval(timerRef.current);
          handleSubmit();
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timerRef.current);
  }, [timeLeft != null]);

  // 保存答案（每次切换题目时自动保存到后端？不，前端暂存即可）
  const saveAnswer = (qid: number, answer: string) => {
    setAnswers(prev => ({ ...prev, [String(qid)]: answer }));
  };

  // 提交考试
  const handleSubmit = async () => {
    if (submitting) return;
    // 确认
    const unanswered = session?.questions.filter(q => !answers[String(q.id)]).length || 0;
    if (unanswered > 0) {
      if (!confirm(`还有 ${unanswered} 题未作答，确定提交吗？`)) return;
    }
    setSubmitting(true);
    try {
      const r = await api.post(`/quizzes/online-exams/${examId}/submit/`, { answers });
      setResult(r.data);
      clearInterval(timerRef.current);
      toast.success('提交成功');
    } catch (e: any) {
      toast.error(e.response?.data?.error || '提交失败');
    } finally {
      setSubmitting(false);
    }
  };

  // 格式化倒计时
  const formatTime = (seconds: number) => {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    return `${m}:${String(s).padStart(2, '0')}`;
  };

  // 结果页
  if (result) {
    const passed = result.passed;
    return (
      <div className="max-w-2xl mx-auto p-6 space-y-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-2xl text-center">
              {session?.exam_title || '考试'} — 成绩报告
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-6 text-center">
            <div className="text-5xl font-black">
              <span className={passed ? 'text-green-500' : 'text-red-500'}>
                {result.score}
              </span>
              <span className="text-2xl text-muted-foreground"> / {result.max_score}</span>
            </div>
            {passed !== undefined && (
              <Badge variant={passed ? 'default' : 'destructive'} className="text-lg px-4 py-2">
                {passed ? '通过 ✓' : '未通过'}
              </Badge>
            )}
            <div className="space-y-4 text-left">
              {result.question_results?.map((qr: any, i: number) => {
                const q = session?.questions.find(q => q.id === qr.question_id);
                return (
                  <Card key={qr.question_id} className="p-4">
                    <div className="flex justify-between items-start mb-2">
                      <p className="font-medium text-sm">第 {i + 1} 题</p>
                      <Badge variant={qr.is_correct ? 'secondary' : 'destructive'}>
                        {qr.score} / {qr.max_score}
                      </Badge>
                    </div>
                    <p className="text-sm text-muted-foreground">{q?.question_text?.slice(0, 100)}...</p>
                    {qr.feedback && (
                      <p className="text-xs text-muted-foreground mt-2 border-t pt-2">{qr.feedback}</p>
                    )}
                  </Card>
                );
              })}
            </div>
            <Button onClick={() => navigate('/home')} className="w-full">
              返回首页
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  // 错误状态
  if (error) {
    return (
      <div className="max-w-md mx-auto p-6">
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
        <Button onClick={() => navigate(-1)} className="mt-4 w-full" variant="outline">
          返回
        </Button>
      </div>
    );
  }

  // 未开始/加载中
  if (!session) return <div className="p-10 text-center text-muted-foreground">加载考试...</div>;

  const currentQ = session.questions[currentIdx];
  const answeredCount = Object.keys(answers).length;
  const totalCount = session.questions.length;
  const progress = totalCount > 0 ? (answeredCount / totalCount) * 100 : 0;

  return (
    <div className="max-w-3xl mx-auto p-4 space-y-4">
      {/* 顶栏 */}
      <Card className="p-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="font-bold text-lg">{session.exam_title}</h2>
            <p className="text-xs text-muted-foreground">
              第 {currentIdx + 1} / {totalCount} 题
            </p>
          </div>
          <div className="flex items-center gap-4">
            {timeLeft != null && (
              <Badge variant={timeLeft < 60 ? 'destructive' : 'secondary'} className="text-lg gap-1">
                <Clock className="h-4 w-4" />
                {formatTime(timeLeft)}
              </Badge>
            )}
            <Progress value={progress} className="w-24" />
            <p className="text-xs text-muted-foreground">{answeredCount}/{totalCount}</p>
          </div>
        </div>
      </Card>

      {/* 题目区 */}
      {currentQ && (
        <Card className="p-6">
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <Badge variant="outline">{currentQ.question_type === 'objective' ? '客观题' : '主观题'}</Badge>
              <Badge variant="secondary">{currentQ.points} 分</Badge>
            </div>
            <p className="text-base leading-relaxed whitespace-pre-wrap">{currentQ.question_text}</p>

            {/* 客观题选项 */}
            {currentQ.question_type === 'objective' && currentQ.options && (
              <RadioGroup
                value={answers[String(currentQ.id)] || ''}
                onValueChange={v => saveAnswer(currentQ.id, v)}
                className="space-y-2"
              >
                {currentQ.options.map((opt, i) => (
                  <div key={i} className="flex items-center space-x-2 border rounded-lg p-3 hover:bg-muted/50 cursor-pointer">
                    <RadioGroupItem value={opt._original_label || opt.label || String.fromCharCode(65 + i)} id={`opt-${i}`} />
                    <Label htmlFor={`opt-${i}`} className="flex-1 cursor-pointer">
                      <span className="font-semibold mr-2">{opt.label || String.fromCharCode(65 + i)}.</span>
                      {opt.text}
                    </Label>
                  </div>
                ))}
              </RadioGroup>
            )}

            {/* 主观题输入 */}
            {currentQ.question_type !== 'objective' && (
              <Textarea
                placeholder="请输入你的答案..."
                value={answers[String(currentQ.id)] || ''}
                onChange={e => saveAnswer(currentQ.id, e.target.value)}
                rows={6}
                className="mt-2"
              />
            )}
          </div>
        </Card>
      )}

      {/* 底部导航 */}
      <div className="flex justify-between items-center">
        <Button
          variant="outline"
          disabled={currentIdx === 0}
          onClick={() => setCurrentIdx(i => i - 1)}
        >
          <ChevronLeft className="h-4 w-4 mr-1" />上一题
        </Button>

        {/* 题号快速跳转 */}
        <div className="flex gap-1 flex-wrap justify-center">
          {session.questions.map((q, i) => (
            <Button
              key={q.id}
              variant={i === currentIdx ? 'default' : answers[String(q.id)] ? 'secondary' : 'ghost'}
              size="sm"
              className="w-8 h-8 p-0 text-xs"
              onClick={() => setCurrentIdx(i)}
            >
              {i + 1}
            </Button>
          ))}
        </div>

        <div className="flex gap-2">
          {currentIdx < totalCount - 1 ? (
            <Button onClick={() => setCurrentIdx(i => Math.min(i + 1, totalCount - 1))}>
              下一题<ChevronRight className="h-4 w-4 ml-1" />
            </Button>
          ) : (
            <Button onClick={handleSubmit} disabled={submitting}>
              <Send className="h-4 w-4 mr-1" />{submitting ? '提交中...' : '提交试卷'}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

export default OnlineExam;
```

---

## Task 7: 前端 — 注册路由

**Objective:** 在 App.tsx 中注册在线考试路由。

**Files:**
- Modify: `frontend/src/App.tsx`

**Step 1:** 添加 import

```tsx
const OnlineExam = lazyNamed(() => import('./pages/OnlineExam'), 'OnlineExam');
```

**Step 2:** 在 student 路由区添加：

```tsx
{ path: "exam/:examId", element: lazyPage(OnlineExam) },
```

**Step 3:** 运行前端检查

```bash
cd /Users/eular/Desktop/UniMind/UniMindCode/frontend
npx tsc -b --noEmit 2>&1 | head -20
```

---

## Task 8: 前端 — 教师考试管理面板改造

**Objective:** 在现有的 TeacherAssignments 页或工作台增加"创建在线考试"入口和考试列表。

**Files:**
- Modify: `frontend/src/pages/TeacherAssignments.tsx`（或新建简单面板）

**Step 1:** 在 TeacherAssignments 页面增加"在线考试"Tab 或区域。

简单方案：在页面顶部增加一个 `CreateOnlineExamDialog` 组件，允许教师：
1. 输入标题、时长
2. 从题库选择题目（复用现有 QuestionPanel）
3. 设置分值、乱序等
4. 提交创建

（此处代码较复杂，约 200 行，涉及 QuestionPanel 复用和题目多选逻辑）

**简化方案（推荐先做）:** 在工作台 Agent 对话中通过 `create_online_exam` tool 创建。

---

## Task 9: 运行系统检查

**Objective:** 全面验证无 regression。

```bash
cd /Users/eular/Desktop/UniMind/UniMindCode
make backend-check 2>&1 | tail -20
make frontend-check 2>&1 | tail -20
```

---

## 实现顺序和依赖

```
Task 1 (检查) → Task 2 (Model/Migration) → Task 3 (Serializer)
  → Task 4 (Views/URLs) → Task 5 (后端测试)
  → Task 6 (前端考试页) → Task 7 (路由) → Task 9 (系统检查)
```

Task 8（教师管理面板）可以后续迭代——学生能参加在线考试是 MVP。
