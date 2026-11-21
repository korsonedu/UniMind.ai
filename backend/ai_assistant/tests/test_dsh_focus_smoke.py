import pytest
from rest_framework.exceptions import PermissionDenied

from ai_assistant.services.dsh_service import build_context, execute_tool
from users.models import CourseStudentStatus


@pytest.mark.django_db
def test_retired_study_tools_are_unavailable(user, settings):
    settings.UNIMIND_CONTENT_INSTITUTION_ID = 'global'
    CourseStudentStatus.objects.create(user=user, is_course_student=True)
    context = build_context(user, '这周学了多久')
    names = {tool['function']['name'] for tool in context['available_tools']}
    assert 'get_learning_sessions' in names
    for name in ('get_study_status', 'get_focus_history'):
        assert name not in names
        with pytest.raises(PermissionDenied):
            execute_tool(user, name, {}, context['memory']['version'])
