"""Owned submission lookup restores cards on a second client without model calls."""
from uuid import uuid4

import pytest
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_exam_submission_restores_only_the_owners_saved_answers(auth_client, user):
    from users.models import CourseStudentStatus
    from quizzes.models import QuizExam, ExamQuestionResult, PracticeSubmission
    CourseStudentStatus.objects.create(user=user, is_course_student=True)
    exam = QuizExam.objects.create(user=user, status='completed', total_questions=1)
    ExamQuestionResult.objects.create(exam=exam, position=1, user_answer='越敏感',
        score=10, max_score=10, status='graded', question_snapshot={'correct_answer': 'A'})
    submission_id = uuid4()
    PracticeSubmission.objects.create(user=user, session_id=submission_id, answers_hash='synthetic', response={'exam_id': exam.pk})
    url = f'/api/quizzes/submissions/{submission_id}/'
    response = auth_client.get(url)
    assert response.status_code == 200
    assert response.json() == {'exam_id': exam.pk, 'answers': [{'position': 1, 'answer': '越敏感'}]}
    assert APIClient().get(url).status_code == 401
    other = type(user).objects.create_user(username='other-submission-owner')
    CourseStudentStatus.objects.create(user=other, is_course_student=True)
    client = APIClient()
    client.force_authenticate(user=other)
    assert client.get(url).status_code == 404
    legacy_id = uuid4()
    PracticeSubmission.objects.create(user=user, session_id=legacy_id, answers_hash='legacy', response={'score': 8})
    assert auth_client.get(f'/api/quizzes/submissions/{legacy_id}/').status_code == 404
    assert QuizExam.objects.count() == 1 and PracticeSubmission.objects.count() == 2
