import json

import pytest
from django.contrib.auth import get_user_model

from ai_assistant.services.tool_executor import PlannerToolExecutor, set_permitted_tools


@pytest.fixture
def user(db, settings):
    from users.models import CourseStudentStatus
    settings.UNIMIND_CONTENT_INSTITUTION_ID = 'global'
    user = get_user_model().objects.create_user(username='visual-user')
    CourseStudentStatus.objects.create(user=user, is_course_student=True)
    return user


def visual_executor(user):
    executor = PlannerToolExecutor(user)
    set_permitted_tools(executor, [{'function': {'name': name}} for name in (
        'get_learning_stats', 'get_knowledge_mastery_map', 'get_due_reviews', 'render_visual',
    )])
    return executor


@pytest.mark.django_db
def test_learning_stats_returns_card_without_misleading_zero(user):
    executor = visual_executor(user)

    data = json.loads(executor('get_learning_stats', {}))

    assert data['visual']['type'] == 'data_card'
    payload = data['visual']['payload']
    assert payload['title'] == '学习概览'
    assert all('0.0%' not in str(item.get('value')) for item in payload['items'])
    assert data['has_attempts'] is False


@pytest.mark.django_db
def test_mastery_without_diagnosis_returns_prompt_card(user):
    executor = visual_executor(user)

    data = json.loads(executor('get_knowledge_mastery_map', {}))

    assert data['mastery']['kp_count'] == 0
    assert data['visual']['type'] == 'data_card'
    assert data['visual']['payload']['items'][0]['value'] == '尚未完成'


@pytest.mark.django_db
def test_duplicate_visual_is_registered_once(user):
    executor = visual_executor(user)

    first = json.loads(executor('get_learning_stats', {}))
    second = json.loads(executor('get_learning_stats', {}))

    assert first.get('duplicate') is None
    assert second.get('duplicate') is True
    assert len(executor.pending_visuals) == 1


@pytest.mark.django_db
def test_unexpected_exception_is_masked(monkeypatch, caplog, user):
    caplog.set_level('ERROR')
    executor = visual_executor(user)

    def boom(args):
        raise RuntimeError('INTERNAL_SECRET')

    monkeypatch.setattr(executor, '_handle_get_due_reviews', boom)
    data = json.loads(executor('get_due_reviews', {}))

    assert data['error'] == {
        'code': 'tool_execution_failed',
        'message': '数据查询失败，请稍后重试',
    }
    assert 'INTERNAL_SECRET' not in json.dumps(data, ensure_ascii=False)
    assert 'INTERNAL_SECRET' in caplog.text


@pytest.mark.django_db
def test_business_error_keeps_original_message(user):
    executor = visual_executor(user)

    data = json.loads(executor('render_visual', {'type': 'invalid'}))

    assert '可视化类型无效' in data['error']
