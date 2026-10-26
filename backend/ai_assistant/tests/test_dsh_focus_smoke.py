"""Owner-scoped focus queries, DB facts plus synthetic Redis snapshot."""
import time
from unittest.mock import patch
import pytest
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied
from ai_assistant.services.dsh_service import build_context, execute_tool
from study_room.models import StudySession
from users.models import CourseStudentStatus, UserAccessProfile


@pytest.mark.django_db
def test_focus_queries_keep_owner_and_eight_tool_budget(user, settings):
    settings.UNIMIND_CONTENT_INSTITUTION_ID = 'global'
    CourseStudentStatus.objects.create(user=user, is_course_student=True)
    other = type(user).objects.create_user(username='other-focus-owner')
    now = timezone.now()
    StudySession.objects.create(user=user, status='ended', ended_at=now, total_focus_seconds=1500)
    StudySession.objects.create(user=other, status='ended', ended_at=now, total_focus_seconds=5940, task_name='OTHER_PRIVATE_TASK')
    current = StudySession.objects.create(user=user, task_name='合成专注任务')
    context = build_context(user, '看看我的自习专注状态和最近一周专注历史')
    names = {tool['function']['name'] for tool in context['tools']}
    assert {'get_study_status', 'get_focus_history'} <= names
    assert len(names) <= 8 and context['routing']['initial_group'] == 'focus'
    snapshot = {'status': 'active', 'task_name': current.task_name, 'duration': 25,
        'timer_end_ts': time.time()+1200, 'total_focus': 0, 'remaining_seconds': 1500, 'db_session_id': current.pk}
    with patch('study_room.session_manager.get_session', return_value=snapshot) as redis:
        status = execute_tool(user, 'get_study_status', {}, context['memory']['version'])
        redis.assert_called_once_with(user.pk)
    history = execute_tool(user, 'get_focus_history', {'days': 7}, context['memory']['version'])
    assert 29 <= status['today_total_focus_minutes'] <= 30
    assert history['total_focus_minutes'] == 25 and history['total_sessions'] == 1
    assert status['visual']['payload']['cta']['link'] == '/study'
    assert history['visual']['payload']['title'] == '自习专注历史'
    current.refresh_from_db(); assert current.status == 'active'
    with patch('study_room.session_manager.get_session', return_value={**snapshot, 'timer_end_ts': time.time()-1}):
        expired = execute_tool(user, 'get_study_status', {}, context['memory']['version'])
    assert '本次已专注' not in [row['label'] for row in expired['visual']['payload']['items']]
    assert expired['today_total_focus_minutes'] == 50
    current.refresh_from_db(); assert current.status == 'ended'
    with pytest.raises(PermissionDenied):
        execute_tool(other, 'get_focus_history', {}, build_context(other, '')['memory']['version'])
    profile, _ = UserAccessProfile.objects.get_or_create(user=user)
    profile.blocked_permissions = ['study.room']; profile.save()
    blocked = build_context(user, '自习专注状态')
    assert 'get_focus_history' not in {tool['function']['name'] for tool in blocked['available_tools']}
