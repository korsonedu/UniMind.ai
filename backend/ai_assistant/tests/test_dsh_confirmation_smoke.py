"""Student-confirmed business writes; no model/provider calls."""
import json
from datetime import date
from unittest.mock import patch
import pytest
from rest_framework.test import APIClient
from rest_framework.exceptions import ValidationError
from ai_assistant.services.dsh_service import build_context, execute_tool
from quizzes.models import Question, KnowledgePoint, UserKnowledgeState, UserQuestionStatus
from faq_system.models import Question as FAQQuestion
from users.models import CourseStudentStatus, Institution


def enable(settings, user, tmp_path):
    settings.UNIMIND_DSH_ENABLED = settings.UNIMIND_DSH_SITE_ENABLED = True
    settings.UNIMIND_CONTENT_INSTITUTION_ID = 'global'
    settings.UNIMIND_DSH_STATE_DIR = str(tmp_path)
    CourseStudentStatus.objects.create(user=user, is_course_student=True)


@pytest.mark.django_db
def test_diagnostic_requires_student_and_grades_once(auth_client, user, settings, tmp_path):
    enable(settings, user, tmp_path)
    kp = KnowledgePoint.objects.create(name='合成诊断考点', level='kp')
    question = Question.objects.create(knowledge_point=kp, text='合成诊断题', q_type='objective', options=['选项甲', '选项乙'], correct_answer='B')
    private = Institution.objects.create(name='Private', slug='private-confirmation')
    Question.objects.create(institution=private, text='PRIVATE_QUESTION', q_type='objective', correct_answer='A')
    context = build_context(user, '做一次诊断测试')
    draft = execute_tool(user, 'run_diagnostic', {'mode': 'generate'}, context['memory']['version'])
    card = draft['visual']['payload']
    assert card['questions'][0]['id'] == question.pk
    assert 'PRIVATE_QUESTION' not in json.dumps(draft)
    assert 'correct_answer' not in json.dumps(draft)
    assert not UserKnowledgeState.objects.exists()
    body = {'token': card['token'], 'answers': [{'question': {'id': question.pk, 'answer': 'FAKE'}, 'answer': 'B'}]}
    url = '/api/ai/dsh/actions/confirm/'
    assert auth_client.post(url, body, format='json').status_code == 400
    body['confirmed'] = True
    response = auth_client.post(url, body, format='json')
    assert response.status_code == 200, response.data
    assert response.data['total_score'] == 1
    recorded = UserQuestionStatus.objects.get(user=user, question=question).last_review
    assert auth_client.post(url, body, format='json').data == response.data
    assert UserQuestionStatus.objects.get(user=user, question=question).last_review == recorded
    assert auth_client.get(f"/api/ai/dsh/actions/{card['request_id']}/").data == response.data
    changed = {**body, 'answers': [{'question': {'id': question.pk}, 'answer': 'A'}]}
    assert auth_client.post(url, changed, format='json').status_code == 409
    assert not FAQQuestion.objects.exists()
    with pytest.raises(ValidationError):
        execute_tool(user, 'run_diagnostic', {'mode': 'submit', 'answers': []}, build_context(user, '')['memory']['version'])


@pytest.mark.django_db
def test_faq_is_editable_draft_until_confirmed_and_owner_scoped(auth_client, user, settings, tmp_path):
    enable(settings, user, tmp_path)
    context = build_context(user, '我想请老师人工答疑')
    from ai_engine.tools import CREATE_FAQ_TICKET_SCHEMA
    assert CREATE_FAQ_TICKET_SCHEMA.get('additionalProperties') is not False
    draft = execute_tool(user, 'create_faq_ticket', {'question_text': '合成提问', 'context_summary': '合成背景', 'reason': 'student_request'}, context['memory']['version'])
    card = draft['visual']['payload']
    assert not FAQQuestion.objects.exists()
    body = {'token': card['token'], 'content': '学生核对后修改的合成提问'}
    url = '/api/ai/dsh/actions/confirm/'
    assert auth_client.post(url, body, format='json').status_code == 400
    other = type(user).objects.create_user(username='other-confirmation')
    CourseStudentStatus.objects.create(user=other, is_course_student=True)
    client = APIClient(); client.force_authenticate(user=other)
    assert client.post(url, {**body, 'confirmed': True}, format='json').status_code == 403
    response = auth_client.post(url, {**body, 'confirmed': True}, format='json')
    assert response.status_code == 200, response.data
    assert FAQQuestion.objects.get(user=user).content == body['content']
    assert auth_client.post(url, {**body, 'confirmed': True}, format='json').data == response.data
    assert FAQQuestion.objects.count() == 1
    assert auth_client.post(url, {**body, 'confirmed': True, 'content': '另一个问题'}, format='json').status_code == 409
    assert client.get(f"/api/ai/dsh/actions/{card['request_id']}/").status_code == 404
    from users.models import UserAccessProfile
    profile, _ = UserAccessProfile.objects.get_or_create(user=user)
    profile.blocked_permissions = ['faq.system']; profile.save()
    assert auth_client.post(url, {**body, 'confirmed': True}, format='json').status_code == 403


@pytest.mark.django_db
def test_expired_or_deleted_source_cannot_write_and_task_token_cannot_confirm(auth_client, user, settings, tmp_path):
    from ai_assistant.dsh_authentication import make_task_token
    from ai_assistant.services.dsh_actions import prepare_diagnostic, prepare_faq
    from ai_assistant.models import DshSubmission
    from users.models import AIUsageReservation
    from uuid import uuid4
    enable(settings, user, tmp_path)
    question = Question.objects.create(text='合成过期题', q_type='objective', correct_answer='A')
    card = prepare_diagnostic(user)['visual']['payload']
    body = {'token': card['token'], 'confirmed': True, 'answers': [{'question': {'id': question.pk}, 'answer': 'A'}]}
    url = '/api/ai/dsh/actions/confirm/'
    with patch('ai_assistant.services.dsh_actions.time.time', return_value=card['expires_at']+1):
        assert auth_client.post(url, body, format='json').status_code == 400
    assert not UserQuestionStatus.objects.exists() and not DshSubmission.objects.exists()
    reservation = AIUsageReservation.objects.create(user=user, request_id=uuid4(), attempt_id=uuid4(), week=date(2026,10,26))
    faq = prepare_faq(user, {'question_text': '合成来源', 'reason': 'student_request'}, reservation.pk)['visual']['payload']
    body = {'token': faq['token'], 'confirmed': True}
    callback = APIClient(); callback.credentials(HTTP_AUTHORIZATION='DSH ' + make_task_token(user, reservation))
    assert callback.post(url, body, format='json').status_code == 401
    assert auth_client.post(url, body, format='json').status_code == 409
    reservation.status = 'succeeded'; reservation.response = {'engine': 'dsh'}; reservation.save()
    assert auth_client.post(url, body, format='json').status_code == 200
    pending = prepare_faq(user, {'question_text': '尚未确认的另一个草稿', 'reason': 'student_request'}, reservation.pk)['visual']['payload']
    body = {'token': pending['token'], 'confirmed': True}
    reservation.response = {'engine': 'dsh', 'deleted': True}; reservation.save()
    assert auth_client.post(url, body, format='json').status_code == 409
    assert auth_client.post(url, {**body, 'token': faq['token']+'tampered'}, format='json').status_code == 400
    assert FAQQuestion.objects.count() == 1
