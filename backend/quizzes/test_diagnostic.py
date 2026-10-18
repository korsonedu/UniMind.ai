from datetime import timedelta

import pytest
from django.utils import timezone

from quizzes.models import KnowledgePoint, Question, UserKnowledgeState, UserQuestionStatus
from users.models import Institution


@pytest.fixture
def diagnostic_user(user, settings):
    institution = Institution.objects.create(
        name='Diagnostic school', slug='diagnostic-school',
        contact_name='Teacher', contact_email='teacher@example.com', plan='growth',
    )
    settings.UNIMIND_CONTENT_INSTITUTION_ID = str(institution.id)
    user.institution = institution
    user.is_member = True
    user.save()
    return user


@pytest.fixture
def diagnostic_question(diagnostic_user):
    point = KnowledgePoint.objects.create(
        name='货币政策', code='DIAG-1', level='kp',
        institution=diagnostic_user.institution,
    )
    return Question.objects.create(
        text='央行买入债券的结果是？', q_type='objective',
        options=['A. 货币供给减少', 'B. 货币供给增加'], correct_answer='B',
        knowledge_point=point, institution=diagnostic_user.institution,
    )


@pytest.mark.django_db
def test_generation_does_not_disclose_answer(api_client, diagnostic_user, diagnostic_question):
    api_client.force_authenticate(user=diagnostic_user)
    response = api_client.post('/api/users/me/diagnostic/generate/')
    assert response.status_code == 200
    assert response.data['questions'][0]['id'] == diagnostic_question.pk
    assert 'answer' not in response.data['questions'][0]


@pytest.mark.django_db
def test_grading_uses_database_answer_and_knowledge_point(api_client, diagnostic_user, diagnostic_question):
    api_client.force_authenticate(user=diagnostic_user)
    response = api_client.post('/api/users/me/diagnostic/submit/', {
        'answers': [{'question': {'id': diagnostic_question.pk, 'answer': 'FAKE',
                                 'knowledge_point_id': 999999, 'q_type': 'subjective'},
                     'answer': 'FAKE'}],
    }, format='json')
    assert response.status_code == 200
    assert response.data['total_score'] == 0
    state = UserKnowledgeState.objects.get(user=diagnostic_user)
    assert state.knowledge_point_id == diagnostic_question.knowledge_point_id
    assert state.mastery_score == 0


@pytest.mark.django_db
def test_option_text_from_web_ui_is_graded_correctly(api_client, diagnostic_user, diagnostic_question):
    api_client.force_authenticate(user=diagnostic_user)
    response = api_client.post('/api/users/me/diagnostic/submit/', {
        'answers': [{'question': {'id': diagnostic_question.pk}, 'answer': 'B. 货币供给增加'}],
    }, format='json')
    assert response.status_code == 200
    assert response.data['total_score'] == 1


@pytest.mark.django_db
def test_foreign_question_is_rejected_without_completing_diagnostic(api_client, diagnostic_user):
    foreign_question = Question.objects.create(
        text='Other school question', q_type='objective', correct_answer='A',
    )
    api_client.force_authenticate(user=diagnostic_user)
    response = api_client.post('/api/users/me/diagnostic/submit/', {
        'answers': [{'question': {'id': foreign_question.pk}, 'answer': 'A'}],
    }, format='json')
    assert response.status_code == 400
    diagnostic_user.refresh_from_db()
    assert not diagnostic_user.has_completed_initial_assessment
    assert not UserKnowledgeState.objects.filter(user=diagnostic_user).exists()


@pytest.mark.django_db
def test_duplicate_question_cannot_inflate_diagnostic(api_client, diagnostic_user, diagnostic_question):
    api_client.force_authenticate(user=diagnostic_user)
    answer = {'question': {'id': diagnostic_question.pk}, 'answer': 'B'}
    response = api_client.post('/api/users/me/diagnostic/submit/', {'answers': [answer, answer]}, format='json')
    assert response.status_code == 400
    assert not UserKnowledgeState.objects.filter(user=diagnostic_user).exists()


@pytest.mark.django_db
def test_memorix_stats_with_review_history(api_client, diagnostic_user, diagnostic_question):
    UserQuestionStatus.objects.create(
        user=diagnostic_user, question=diagnostic_question, wrong_count=2, reps=1,
        last_correct=False, stability=2, next_review_at=timezone.now() - timedelta(days=1),
    )
    api_client.force_authenticate(user=diagnostic_user)
    response = api_client.get('/api/quizzes/stats/')
    assert response.status_code == 200
    assert response.data['review_goal'] == 1
    assert response.data['weak_focus_count'] == 1
