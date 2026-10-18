from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from django.test import override_settings
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied

from ai_engine.tool_permissions import filter_tools
from core.utils import apply_institution_filter
from users.permissions import get_user_capabilities, is_institution_teacher, is_platform_admin


def user(**changes):
    values = dict(pk=1, id=1, is_authenticated=True, is_active=True, is_staff=False,
                  is_superuser=False, institution_id=None, institution=None,
                  institution_role='student', access_profile=None)
    return SimpleNamespace(**(values | changes))


def tools(*names):
    return [{'function': {'name': name}} for name in names]


def test_no_identity_or_non_course_student_has_no_tools():
    with patch('users.learning.is_course_student', return_value=False):
        assert filter_tools('planner', Mock(), tools('search_courses')) == []
        assert filter_tools('planner', Mock(), tools('run_diagnostic'), user=user()) == []
        assert get_user_capabilities(user()) == ['member.access', 'ai.assistant']


def test_historical_teacher_and_owner_have_no_admin_permission():
    for role in ('teacher', 'owner'):
        assert not is_institution_teacher(user(institution_id=5, institution=Mock(), institution_role=role))


def test_course_tools_follow_feature_switches_and_never_open_workbench():
    with patch('users.learning.is_course_student', return_value=True), \
            patch('users.feature_access.learning_features', return_value=['ai.assistant', 'course.video']):
        available = tools('search_courses', 'run_diagnostic', 'quick_generate')
        assert filter_tools('planner', None, available, user=user()) == tools('search_courses')
        assert filter_tools('exam_generator', None, available, user=user()) == []


@override_settings(UNIMIND_DIRECTUS_ADMIN_MAP={'00000000-0000-4000-8000-000000000001': 1, '00000000-0000-4000-8000-000000000002': 2})
def test_only_mapped_platform_admin_gets_workbench_tools():
    admin = user(is_staff=True, is_superuser=True)
    available = tools('quick_generate', 'get_student_detail')
    assert is_platform_admin(admin)
    assert filter_tools('exam_generator', None, available, user=admin) == available
    assert not is_platform_admin(user(pk=3, is_staff=True, is_superuser=True))
    with override_settings(UNIMIND_DIRECTUS_ADMIN_MAP={}):
        assert not is_platform_admin(admin)


def test_unconfigured_scope_denies_and_explicit_global_never_means_all_tenants():
    query = Mock()
    with override_settings(UNIMIND_CONTENT_INSTITUTION_ID=''):
        with pytest.raises(PermissionDenied):
            apply_institution_filter(query, user())
    with override_settings(UNIMIND_CONTENT_INSTITUTION_ID='global'):
        apply_institution_filter(query, user(is_staff=True, is_superuser=True))
        query.filter.assert_called_once_with(institution_id=None)
    with override_settings(UNIMIND_CONTENT_INSTITUTION_ID='7'):
        apply_institution_filter(query, user())
        query.filter.assert_called_with(institution_id=7)


def test_tool_execution_denies_non_course_direct_call_even_without_route_filter():
    from ai_assistant.services.tool_executor import BaseToolExecutor
    with patch('users.learning.is_course_student', return_value=False):
        executor = BaseToolExecutor(user())
        executor._handle_run_diagnostic = Mock()
        assert 'Tool not allowed' in executor('run_diagnostic', {})
        executor._handle_run_diagnostic.assert_not_called()


def test_old_external_api_credentials_are_disabled():
    from core.authentication import APIKeyAuthentication
    authentication = APIKeyAuthentication()
    assert authentication.authenticate(SimpleNamespace(META={})) is None
    with pytest.raises(AuthenticationFailed):
        authentication.authenticate(SimpleNamespace(META={'HTTP_X_API_KEY': 'legacy-key'}))


def test_retired_activation_invite_role_and_external_routes_are_not_reachable():
    from django.urls import resolve
    from users.views_institution import RetiredInstitutionView
    for path in (
        '/api/users/me/activate/', '/api/users/institution/join-by-invite-slug/',
        '/api/users/institution/me/members/1/role/', '/api/users/institutions/1/change-plan/',
        '/api/users/institutions/1/preview/', '/api/users/admin/plan-invite-codes/generate/',
        '/api/users/institution/me/api-keys/', '/api/v1/questions/',
    ):
        assert resolve(path).func.view_class is RetiredInstitutionView


def test_non_course_direct_learning_requests_are_denied_before_queries():
    from django.urls import resolve
    from rest_framework.test import APIRequestFactory, force_authenticate
    factory = APIRequestFactory()
    with patch('users.learning.is_course_student', return_value=False):
        for path in ('/api/ai/dashboard/', '/api/ai/memory/profile/',
                     '/api/ai/memory/due/', '/api/ai/memory/stats/',
                     '/api/ai/practice/start/', '/api/ai/grading/grade/'):
            request = factory.post(path, {}) if '/practice/' in path or '/grading/' in path else factory.get(path)
            force_authenticate(request, user=user())
            assert resolve(path).func(request).status_code == 403


@override_settings(
    UNIMIND_CONTENT_INSTITUTION_ID='global',
    UNIMIND_DIRECTUS_ADMIN_MAP={'00000000-0000-4000-8000-000000000001': 1,
                               '00000000-0000-4000-8000-000000000002': 2},
)
def test_workbench_executor_requires_registered_permission_and_preserves_own_handler():
    from ai_assistant.services.exam_generator_tool_executor import ExamGeneratorToolExecutor
    from ai_assistant.services.tool_executor import set_permitted_tools
    executor = ExamGeneratorToolExecutor(user(is_staff=True, is_superuser=True))
    executor._handle_search_knowledge = Mock(return_value={'found': 1})
    assert 'Tool not allowed' in executor('search_knowledge', {})
    executor._handle_search_knowledge.assert_not_called()
    set_permitted_tools(executor, tools('search_knowledge'))
    assert '"found": 1' in executor('search_knowledge', {})
    executor._handle_search_knowledge.assert_called_once_with({})
