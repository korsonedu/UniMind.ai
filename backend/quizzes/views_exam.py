import logging
from django.db.models import Q
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView
from quizzes.models import QuizExam, TeacherExam, StudentExamSubmission
from quizzes.serializers import QuizExamSerializer, TeacherExamSerializer
from users.permissions import IsAdmin, HasQuota
from users.views import IsMember
from quizzes.ai_workflow import mark_questions_reviewed
from users.quota import increment_quota
from quizzes.services.task_dispatcher import dispatch_exam_grading

logger = logging.getLogger(__name__)


def _inst_q(user):
    """返回机构数据隔离 Q 对象，用于 get_object_or_404 等查询"""
    from users.permissions import is_platform_admin
    if is_platform_admin(user):
        return Q()
    inst = getattr(user, 'institution', None)
    if inst:
        return Q(institution=inst) | Q(institution__isnull=True)
    return Q(institution__isnull=True)


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
                    'graded_pdf_url': _build_media_abs_url(request, submission.graded_pdf.name) if submission.graded_pdf else "",
                    'score': submission.score,
                    'feedback': submission.feedback,
                } if submission else None
            })
        return Response({'results': data})


class TeacherExamCreateView(APIView):
    """教师/管理员上传发布试卷 PDF"""
    permission_classes = [IsAdmin, HasQuota]
    quota_resource = 'pdf_export'

    def post(self, request):
        title = request.data.get('title', '').strip()
        description = request.data.get('description', '').strip()
        exam_file = request.FILES.get('exam_pdf')

        if not title or not exam_file:
            return Response({'error': '请填写试卷标题并上传 PDF 文件'}, status=400)
        from core.file_validation import validate_upload_file
        validate_upload_file(exam_file, allowed_extensions={'.pdf'})

        exam = TeacherExam.objects.create(
            title=title,
            description=description,
            exam_pdf=exam_file,
            created_by=request.user,
            institution=request.user.institution,
        )
        # 计入 PDF 导出配额
        if request.user.institution:
            increment_quota(request.user.institution, 'pdf_export')
        return Response(TeacherExamSerializer(exam).data, status=201)


class TeacherExamDeleteView(APIView):
    """教师/管理员删除已发布试卷"""
    permission_classes = [IsAdmin]

    def delete(self, request, pk):
        exam = get_object_or_404(TeacherExam, Q(id=pk) & _inst_q(request.user))
        exam.delete()
        return Response({'status': 'deleted'})


class StudentExamSubmissionView(APIView):
    permission_classes = [IsMember]

    def post(self, request, pk):
        exam = get_object_or_404(TeacherExam, id=pk)
        user = request.user
        from users.permissions import is_platform_admin
        if not is_platform_admin(user):
            inst = getattr(user, 'institution', None)
            if inst and exam.institution != inst:
                return Response({'detail': '无权操作'}, status=403)
        answer_file = request.FILES.get('file')
        if not answer_file:
            return Response({'error': '未上传解答文件'}, status=400)
        from core.file_validation import validate_upload_file
        validate_upload_file(answer_file, allowed_extensions={'.pdf', '.jpg', '.jpeg', '.png'})

        submission, created = StudentExamSubmission.objects.update_or_create(
            exam=exam, user=request.user,
            defaults={'answer_pdf': answer_file}
        )
        return Response({'status': 'success', 'submission_id': submission.id})


class TeacherExamSubmissionsView(APIView):
    """教师查看某试卷的所有学生提交"""
    permission_classes = [IsAdmin]

    def get(self, request, pk):
        exam = get_object_or_404(TeacherExam, Q(id=pk) & _inst_q(request.user))
        submissions = exam.submissions.select_related('user').order_by('-created_at')
        data = []
        for s in submissions:
            data.append({
                'id': s.id,
                'student_name': s.user.nickname or s.user.username,
                'student_email': s.user.email,
                'answer_pdf_url': _build_media_abs_url(request, s.answer_pdf.name) if s.answer_pdf else '',
                'graded_pdf_url': _build_media_abs_url(request, s.graded_pdf.name) if s.graded_pdf else '',
                'score': s.score,
                'feedback': s.feedback,
                'created_at': s.created_at,
            })
        return Response({'results': data})


class TeacherGradeSubmissionView(APIView):
    """教师为学生提交打分、上传批改后PDF、填写评语"""
    permission_classes = [IsAdmin]

    def post(self, request, pk):
        from users.permissions import is_platform_admin
        if is_platform_admin(request.user):
            submission = get_object_or_404(StudentExamSubmission, id=pk)
        else:
            inst = request.user.institution
            if inst:
                submission = get_object_or_404(StudentExamSubmission, Q(id=pk) & (Q(exam__institution=inst) | Q(exam__institution__isnull=True)))
            else:
                submission = get_object_or_404(StudentExamSubmission, Q(id=pk) & Q(exam__institution__isnull=True))
        score = request.data.get('score')
        feedback = request.data.get('feedback', '')
        graded_file = request.FILES.get('graded_pdf')
        if graded_file:
            from core.file_validation import validate_upload_file
            validate_upload_file(graded_file, allowed_extensions={'.pdf'})
        if score is not None:
            try:
                submission.score = float(score)
            except (TypeError, ValueError):
                return Response({'error': '分数格式不正确'}, status=400)
        if feedback:
            submission.feedback = str(feedback)
        if graded_file:
            submission.graded_pdf = graded_file
        submission.save()
        return Response({
            'id': submission.id,
            'score': submission.score,
            'feedback': submission.feedback,
            'graded_pdf_url': _build_media_abs_url(request, submission.graded_pdf.name) if submission.graded_pdf else '',
        })


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


class ExamDetailView(generics.RetrieveAPIView):
    """
    获取某次考试的详细报告
    """
    queryset = QuizExam.objects.all()
    serializer_class = QuizExamSerializer
    permission_classes = [IsMember]

    def get_queryset(self):
        return QuizExam.objects.filter(user=self.request.user)


