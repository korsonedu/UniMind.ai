import hashlib
import json
import logging

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework import serializers
from rest_framework.views import APIView

from core.analytics import record_event
from quizzes.ai_workflow import validate_exam_answers
from quizzes.models import ExamQuestionResult, PracticeSubmission, QuizExam
from quizzes.services.practice_results import (
    exam_history_items,
    exam_result_payload,
    exam_status_payload,
    question_snapshot,
)
from quizzes.services.task_dispatcher import dispatch_exam_grading
from users.views import IsMember

logger = logging.getLogger(__name__)


class SubmitExamView(APIView):
    permission_classes = [IsMember]

    def post(self, request):
        questions_data = request.data.get('answers', [])
        questions = validate_exam_answers(request.user, questions_data, request=request)
        submission_id = request.data.get('submission_id')
        if submission_id:
            submission_id = serializers.UUIDField().run_validation(submission_id)
        answers_hash = hashlib.sha256(json.dumps({
            'kind': 'exam', 'answers': sorted([
                {'question_id': int(item['question_id']), 'answer': item.get('answer') or ''}
                for item in questions_data
            ], key=lambda item: item['question_id']),
        }, sort_keys=True).encode()).hexdigest()

        with transaction.atomic():
            if submission_id:
                request.user.__class__.objects.select_for_update().get(pk=request.user.pk)
                prior = PracticeSubmission.objects.filter(session_id=submission_id).first()
                if prior:
                    if prior.user_id != request.user.pk or prior.answers_hash != answers_hash:
                        return Response({'error': '这组练习已提交，不能更换答案。'}, status=409)
                    return Response(prior.response, status=202)
            exam = QuizExam.objects.create(
                user=request.user,
                status='pending',
                total_questions=len(questions_data),
            )
            results = []
            for position, item in enumerate(questions_data, start=1):
                question = questions[int(item['question_id'])]
                results.append(ExamQuestionResult(
                    exam=exam,
                    question=question,
                    position=position,
                    user_answer=item.get('answer') or '',
                    score=0,
                    max_score=question.get_max_score(),
                    status='pending',
                    question_snapshot=question_snapshot(question),
                ))
            ExamQuestionResult.objects.bulk_create(results)
            response = {'status': 'processing', 'exam_id': exam.id, 'total_questions': len(questions_data)}
            if submission_id:
                PracticeSubmission.objects.create(user=request.user, session_id=submission_id,
                    answers_hash=answers_hash, response=response)
            transaction.on_commit(
                lambda: dispatch_exam_grading(request.user.id, exam.id, questions_data)
            )

        record_event('quiz_attempt', user=request.user, properties={
            'exam_id': exam.id,
            'question_count': len(questions_data),
        })

        return Response(response, status=202)


class ExamDetailView(APIView):
    """Return the full review payload for one exam owned by the current user."""

    permission_classes = [IsMember]

    def get(self, request, pk):
        exam = get_object_or_404(QuizExam, pk=pk, user=request.user)
        return Response(exam_result_payload(exam))


class ExamSubmissionView(APIView):
    permission_classes = [IsMember]

    def get(self, request, submission_id):
        submission = get_object_or_404(PracticeSubmission, user=request.user, session_id=submission_id)
        saved = submission.response if isinstance(submission.response, dict) else {}
        exam = get_object_or_404(QuizExam, user=request.user, pk=saved.get('exam_id'))
        return Response({'exam_id': exam.pk, 'answers': [
            {'position': item.position, 'answer': item.user_answer}
            for item in exam.results.order_by('position', 'id')
        ]})


class ExamStatusView(APIView):
    permission_classes = [IsMember]

    def get(self, request, pk):
        exam = get_object_or_404(QuizExam, pk=pk, user=request.user)
        return Response(exam_status_payload(exam))


class ExamListView(APIView):
    permission_classes = [IsMember]

    def get(self, request):
        limit = request.query_params.get('limit', 20)
        return Response({'items': exam_history_items(request.user, limit)})


class ExamRetryView(APIView):
    permission_classes = [IsMember]

    def post(self, request, pk):
        exam = get_object_or_404(QuizExam, pk=pk, user=request.user)
        if exam.status in ('pending', 'grading'):
            return Response(exam_status_payload(exam))

        failed = exam.results.filter(status='failed')
        question_id = request.data.get('question_id')
        if question_id not in (None, ''):
            try:
                question_id = int(question_id)
            except (TypeError, ValueError):
                return Response({'error': '题目 ID 无效'}, status=400)
            failed = failed.filter(question_id=question_id)

        failed_items = list(failed.select_related('question'))
        if not failed_items:
            return Response(exam_status_payload(exam))

        retry_data = [
            {'question_id': item.question_id, 'answer': item.user_answer or ''}
            for item in failed_items if item.question_id is not None
        ]
        with transaction.atomic():
            failed.update(status='pending', error_metadata={}, graded_at=None)
            exam.status = 'grading'
            exam.last_error = ''
            exam.grading_completed_at = None
            exam.notified_at = None
            exam.save(update_fields=['status', 'last_error', 'grading_completed_at', 'notified_at'])
            transaction.on_commit(
                lambda: dispatch_exam_grading(request.user.id, exam.id, retry_data)
            )

        return Response(exam_status_payload(exam), status=202)
