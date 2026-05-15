import logging
from django.conf import settings
from django.db.models import F
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView
from quizzes.models import Question, QuizAttempt, QuizExam, TeacherExam, StudentExamSubmission
from quizzes.serializers import QuizAttemptSerializer, QuizExamSerializer, TeacherExamSerializer
from users.models import User
from users.serializers import UserSerializer
from users.permissions import IsAdmin
from users.views import IsMember
from quizzes.ai_workflow import grade_single_question_submission, mark_questions_reviewed
from quizzes.services.task_dispatcher import dispatch_exam_grading

logger = logging.getLogger(__name__)


def _build_media_abs_url(request, raw_path: str) -> str:
    text = str(raw_path or "").strip()
    if not text:
        return ""
    if text.startswith("http://") or text.startswith("https://"):
        return text
    normalized = text.replace("\\", "/")
    marker = "/media/"
    if marker in normalized:
        rel = normalized.split(marker, 1)[1]
    else:
        rel = normalized.lstrip("/")
    return request.build_absolute_uri(f"/media/{rel}")


class TeacherExamListView(APIView):
    permission_classes = [IsMember]

    def get(self, request):
        from users.permissions import is_platform_admin
        from django.db.models import Q
        qs = TeacherExam.objects.all().order_by('-created_at')
        if not is_platform_admin(request.user):
            inst = getattr(request.user, 'institution', None)
            if inst:
                qs = qs.filter(Q(institution=inst) | Q(institution__isnull=True))
            else:
                qs = qs.filter(institution__isnull=True)
        exams = qs
        submission_map = {
            s.exam_id: s
            for s in StudentExamSubmission.objects.filter(
                user=request.user,
                exam__in=exams,
            ).select_related('exam')
        }
        data = []
        for e in exams:
            submission = submission_map.get(e.id)
            data.append({
                'id': e.id,
                'title': e.title,
                'description': e.description,
                'exam_pdf_url': _build_media_abs_url(request, e.exam_pdf.name) if e.exam_pdf else "",
                'created_at': e.created_at,
                'submission': {
                    'id': submission.id,
                    'answer_pdf_url': _build_media_abs_url(request, submission.answer_pdf.name) if submission.answer_pdf else "",
                    'score': submission.score,
                    'feedback': submission.feedback,
                } if submission else None
            })
        return Response({'results': data})


class TeacherExamCreateView(APIView):
    """教师/管理员上传发布试卷 PDF"""
    permission_classes = [IsAdmin]

    def post(self, request):
        title = request.data.get('title', '').strip()
        description = request.data.get('description', '').strip()
        exam_file = request.FILES.get('exam_pdf')

        if not title or not exam_file:
            return Response({'error': '请填写试卷标题并上传 PDF 文件'}, status=400)

        exam = TeacherExam.objects.create(
            title=title,
            description=description,
            exam_pdf=exam_file,
            created_by=request.user,
            institution=request.user.institution,
        )
        return Response(TeacherExamSerializer(exam).data, status=201)


class TeacherExamDeleteView(APIView):
    """教师/管理员删除已发布试卷"""
    permission_classes = [IsAdmin]

    def delete(self, request, pk):
        exam = get_object_or_404(TeacherExam, id=pk)
        exam.delete()
        return Response({'status': 'deleted'})


class StudentExamSubmissionView(APIView):
    permission_classes = [IsMember]

    def post(self, request, pk):
        exam = get_object_or_404(TeacherExam, id=pk)
        answer_file = request.FILES.get('file')
        if not answer_file:
            return Response({'error': '未上传解答文件'}, status=400)

        submission, created = StudentExamSubmission.objects.update_or_create(
            exam=exam, user=request.user,
            defaults={'answer_pdf': answer_file}
        )
        return Response({'status': 'success', 'submission_id': submission.id})


class TeacherExamSubmissionsView(APIView):
    """教师查看某试卷的所有学生提交"""
    permission_classes = [IsAdmin]

    def get(self, request, pk):
        exam = get_object_or_404(TeacherExam, id=pk)
        submissions = exam.submissions.select_related('user').order_by('-created_at')
        data = []
        for s in submissions:
            data.append({
                'id': s.id,
                'student_name': s.user.nickname or s.user.username,
                'student_email': s.user.email,
                'answer_pdf_url': _build_media_abs_url(request, s.answer_pdf.name) if s.answer_pdf else '',
                'score': s.score,
                'feedback': s.feedback,
                'created_at': s.created_at,
            })
        return Response({'results': data})


class TeacherGradeSubmissionView(APIView):
    """教师为学生提交打分并填写评语"""
    permission_classes = [IsAdmin]

    def post(self, request, pk):
        submission = get_object_or_404(StudentExamSubmission, id=pk)
        score = request.data.get('score')
        feedback = request.data.get('feedback', '')
        if score is not None:
            try:
                submission.score = float(score)
            except (TypeError, ValueError):
                return Response({'error': '分数格式不正确'}, status=400)
        if feedback:
            submission.feedback = str(feedback)
        submission.save(update_fields=['score', 'feedback'])
        return Response({
            'id': submission.id,
            'score': submission.score,
            'feedback': submission.feedback,
        })


class GradeSubjectiveView(APIView):
    permission_classes = [IsMember]

    def post(self, request):
        question_id = request.data.get('question_id')
        user_answer = request.data.get('answer')

        if not user_answer:
            return Response({'error': '请提供答题内容'}, status=400)

        try:
            question = Question.objects.get(id=question_id)
        except Question.DoesNotExist:
            return Response({'error': '题目不存在'}, status=404)

        max_score = question.get_max_score()

        try:
            result = grade_single_question_submission(request.user, question, user_answer)
            return Response({
                'score': result['score'],
                'max_score': max_score,
                'feedback': result['feedback'],
                'analysis': result['analysis'],
                'ai_answer': question.ai_answer,
                'elo_change': result['elo_change']
            })
        except Exception as e:
            return Response({'error': f'评分逻辑错误: {str(e)}'}, status=500)


class SubmitExamView(APIView):
    permission_classes = [IsMember]

    def post(self, request):
        questions_data = request.data.get('answers', [])
        if not questions_data:
            return Response({'error': '无答题数据'}, status=400)

        exam = QuizExam.objects.create(user=request.user)

        mark_questions_reviewed(
            user=request.user,
            question_ids=[item.get('question_id') for item in questions_data if item.get('question_id') is not None],
        )

        dispatch_exam_grading(request.user.id, exam.id, questions_data)

        # 统一走后台批改，避免前端刷新/离开导致用户侧状态丢失。
        message = '试卷已提交后台批改，结果将通过通知发送。'
        if len(questions_data) == 1:
            message = '特训已提交后台判分，完成后将通过通知发送。'

        return Response({
            'status': 'processing',
            'exam_id': exam.id,
            'message': message,
        })


class LatestExamReportView(APIView):
    """
    获取最近一次考试报告。
    """
    permission_classes = [IsMember]

    def get(self, request):
        latest_exam = QuizExam.objects.filter(user=request.user).first()
        if not latest_exam:
            return Response({'error': '报告不存在'}, status=404)

        serializer = QuizExamSerializer(latest_exam)
        return Response(serializer.data)


class ExamDetailView(generics.RetrieveAPIView):
    """
    获取某次考试的详细报告
    """
    queryset = QuizExam.objects.all()
    serializer_class = QuizExamSerializer
    permission_classes = [IsMember]

    def get_queryset(self):
        return QuizExam.objects.filter(user=self.request.user)


class QuizAttemptCreateView(generics.CreateAPIView):
    serializer_class = QuizAttemptSerializer
    permission_classes = [IsMember]

    def perform_create(self, serializer):
        from django.db.models import F
        user = self.request.user
        is_initial = not user.has_completed_initial_assessment
        avg_difficulty = 1000
        expected_score = 1 / (1 + 10**((avg_difficulty - user.elo_score) / 400))
        score = serializer.validated_data.get('score', 0)
        elo_change = int(getattr(settings, 'ELO_K_FACTOR', 32) * (score - expected_score))
        if is_initial and score > getattr(settings, 'ELO_INITIAL_BONUS_THRESHOLD', 0.8):
            elo_change += getattr(settings, 'ELO_INITIAL_BONUS', 200)
        attempt = serializer.save(user=user, is_initial_placement=is_initial, elo_change=elo_change)
        update_fields = {'elo_score': F('elo_score') + elo_change}
        if is_initial:
            update_fields['has_completed_initial_assessment'] = True
        User.objects.filter(id=user.id).update(**update_fields)


class LeaderboardView(generics.ListAPIView):
    def get_queryset(self):
        from users.permissions import is_platform_admin
        from django.db.models import Q
        size = getattr(settings, 'LEADERBOARD_SIZE', 50)
        qs = User.objects.filter(is_active=True)
        user = self.request.user
        if not is_platform_admin(user):
            inst = getattr(user, 'institution', None)
            if inst:
                qs = qs.filter(Q(institution=inst) | Q(institution__isnull=True))
            else:
                qs = qs.filter(institution__isnull=True)
        return qs.order_by('-elo_score')[:size]
    serializer_class = UserSerializer
    permission_classes = [IsMember]
