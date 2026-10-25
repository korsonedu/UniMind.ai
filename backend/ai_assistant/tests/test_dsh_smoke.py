import pytest

from ai_assistant.models import AgentMemory
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
    assert context['tools'] == []
    assert [m['value'] for m in context['memory']['items']] == ['先举例再解释']

    CourseStudentStatus.objects.create(user=user, is_course_student=True)
    context = auth_client.post(url, {'message': '推荐课程'}, format='json').json()
    names = {t['function']['name'] for t in context['tools']}
    assert 'search_courses' in names
    assert names <= {'get_learning_stats', 'get_recent_practice_result', 'get_user_weak_points', 'search_courses', 'search_asr'}
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
