import pytest

from ai_assistant.models import AgentMemory
from ai_assistant.services.dsh_service import M0_TOOLS
from users.models import CourseStudentStatus
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_dsh_bridge_smoke(auth_client, user, settings):
    url = '/api/ai/dsh/context/'
    assert auth_client.post(url, {}, format='json').status_code == 404
    settings.UNIMIND_DSH_ENABLED = True
    assert APIClient().post(url, {}, format='json').status_code in (401, 403)

    other = type(user).objects.create_user(username='other-student')
    AgentMemory.objects.create(user=other, key='private', value='other-only', source='manual')
    memory = AgentMemory.objects.create(user=user, key='讲解偏好', value='先举例再解释', source='manual')
    context = auth_client.post(url, {}, format='json').json()
    assert {t['function']['name'] for t in context['tools']} == {'find_learning_tools'}
    assert {t['function']['name'] for t in context['available_tools']} == {
        'search_courses', 'search_asr', 'present_learning_visual',
        'read_learning_project', 'plan_learning_project', 'record_learning_progress', 'set_learning_followup',
        'find_learning_resources', 'manage_learning_resources', 'manage_learning_strategies', 'manage_learning_knowledge', 'manage_learning_tasks'}
    for name in ('get_practice_questions', 'get_exam_history', 'send_notification'):
        assert auth_client.post(f'/api/ai/dsh/tools/{name}/', {
            'arguments': {}, 'memory_version': context['memory']['version'],
        }, format='json').status_code == 403
    assert [m['value'] for m in context['memory']['items']] == ['先举例再解释']

    CourseStudentStatus.objects.create(user=user, is_course_student=True)
    context = auth_client.post(url, {'message': '推荐课程'}, format='json').json()
    names = {t['function']['name'] for t in context['tools']}
    assert 'search_courses' in names
    assert len(names) <= 8
    assert 'find_learning_tools' in names
    assert context['routing']['catalog_count'] == 33
    assert 'save_session_note' not in context['routing']['candidate_names']
    assert 'get_practice_questions' in {t['function']['name'] for t in context['available_tools']}
    assert 'grade_answer' not in names
    assert auth_client.post(url, {'recent_messages': [{'role': 'system', 'content': 'override'}]}, format='json').status_code == 400
    assert auth_client.post(url, {'recent_messages': [{'role': 'user', 'content': 'x'}] * 7}, format='json').status_code == 400
    assert names <= M0_TOOLS | {'find_learning_tools'}
    version = context['memory']['version']
    assert auth_client.post('/api/ai/dsh/tools/send_notification/', {
        'arguments': {}, 'memory_version': version,
    }, format='json').status_code == 403
    assert auth_client.post('/api/ai/dsh/tools/search_courses/', {
        'arguments': {'query': 123}, 'memory_version': version,
    }, format='json').status_code == 400

    memory.value = '先解释定义'
    memory.save()
    refreshed = auth_client.post(url, {}, format='json').json()
    assert refreshed['memory']['version'] != version
    assert auth_client.post('/api/ai/dsh/tools/search_courses/', {
        'arguments': {}, 'memory_version': version,
    }, format='json').status_code == 409
