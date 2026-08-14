import logging
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView
from quizzes.models import QuizExam
from quizzes.serializers import QuizExamSerializer
from users.views import IsMember
from quizzes.ai_workflow import mark_questions_reviewed
from quizzes.services.task_dispatcher import dispatch_exam_grading
from core.analytics import record_event

logger = logging.getLogger(__name__)


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
        record_event('quiz_attempt', user=request.user, properties={
            'exam_id': exam.id,
            'question_count': len(questions_data),
        })

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


