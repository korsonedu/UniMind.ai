from datetime import timedelta
from uuid import uuid4

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from ai_assistant.models import AIChatMessage, Bot
from courses.models import Course, CourseModule
from notes.models import Note, NoteAISettings
from users.learning import reserve_ai_call, confirm_ai_call, usage_info
from users.login_sessions import LoginSession
from users.models import User, Institution, WeeklyAIQuotaConfig
from users.models_workspace import Workspace, WorkspaceMembership, WorkspaceLearner, WorkspaceCourse, WorkspaceInvite, WorkspaceEnrollment

pytestmark = pytest.mark.django_db


@pytest.fixture
def spaces(settings):
    settings.UNIMIND_CONTENT_INSTITUTION_ID = 'global'
    root = User.objects.create_user(username='space-account', is_member=True, password='SmokePass123!', email='spaces@example.com')
    inst = Institution.objects.create(name='Space school', slug='space-school')
    workspace = Workspace.objects.create(institution=inst, service_ends_on=timezone.localdate() + timedelta(days=30), max_students=3)
    member = WorkspaceMembership.objects.create(workspace=workspace, user=root)
    personal, school = APIClient(), APIClient()
    token = LoginSession.issue(root)
    for client in (personal, school):
        client.cookies['auth_token'] = token.key
    personal.credentials(HTTP_X_UNIMIND_WORKSPACE='personal')
    school.credentials(HTTP_X_UNIMIND_WORKSPACE=str(workspace.pk))
    assert personal.post('/api/users/workspace/select/', {'workspace_id': workspace.pk}, format='json').status_code == 200
    learner = WorkspaceLearner.objects.get(account=root, workspace=workspace).user
    return root, workspace, member, learner, personal, school


def rows(response):
    data = response.data
    return data.get('results', data.get('items', data)) if isinstance(data, dict) else data


def test_learning_features_follow_the_selected_identity(spaces):
    root, workspace, member, learner, personal, school = spaces
    assert personal.get('/api/users/me/').data['workspace_id'] is None
    identity = school.get('/api/users/me/').data
    assert identity['id'] == learner.pk and identity['account_id'] == root.pk
    assert identity['username'] == root.username and identity['email'] == root.email
    assert personal.get('/api/users/workspace/').data['workspace']['id'] == workspace.pk
    for client, title in ((personal, 'Private note'), (school, 'School note')):
        assert client.post('/api/notes/items/', {'title': title, 'content': title}, format='json').status_code == 201
        assert client.post('/api/ai/projects/', {'name': title}, format='json').status_code == 201
        assert [item['title'] for item in rows(client.get('/api/notes/items/'))] == [title]
        assert [item['name'] for item in rows(client.get('/api/ai/projects/'))] == [title]
        features = client.get('/api/users/institution/me/features/').data['features']
        assert {'ai.assistant', 'quiz.exam', 'full.report', 'study.room', 'faq.system'} <= set(features)
        assert ('course.video' in features) == (client is school)
    private = Note.objects.get(user=root)
    school_note = Note.objects.get(user=learner)
    assert school.get(f'/api/notes/items/{private.pk}/').status_code == 404
    assert personal.get(f'/api/notes/items/{school_note.pk}/').status_code == 404
    assert school.patch(f'/api/notes/items/{private.pk}/', {'title': 'overwritten'}, format='json').status_code == 404
    assert school.patch('/api/users/me/update/', {'bio': 'School profile'}, format='json').status_code == 200
    root.refresh_from_db()
    learner.refresh_from_db()
    assert root.bio != learner.bio
    NoteAISettings.objects.create(user=root, enabled=True)
    assert school.get('/api/notes/ai-settings/').data['enabled'] is False
    bot = Bot.objects.create(name='小宇', bot_type='planner')
    AIChatMessage.objects.create(user=root, bot=bot, role='user', content='Private chat')
    AIChatMessage.objects.create(user=learner, bot=bot, role='user', content='School chat')
    assert [row['content'] for row in personal.get('/api/ai/history/').data] == ['Private chat']
    assert [row['content'] for row in school.get('/api/ai/history/').data] == ['School chat']
    root.is_member = False
    root.save(update_fields=['is_member'])
    assert 'quiz.exam' not in personal.get('/api/users/institution/me/features/').data['features']
    assert 'quiz.exam' in school.get('/api/users/institution/me/features/').data['features']


def test_ai_pending_capacity_and_usage_are_shared(spaces):
    root, workspace, member, learner, personal, school = spaces
    WeeklyAIQuotaConfig.objects.update_or_create(pk=1, defaults={'experience_calls': 1, 'course_calls': 2})
    a = reserve_ai_call(root, uuid4())
    b = reserve_ai_call(learner, uuid4())
    assert b.user_id == learner.pk and b.workspace_id == workspace.pk
    assert usage_info(root)['remaining'] == usage_info(learner)['remaining'] == 0
    from rest_framework.exceptions import PermissionDenied
    with pytest.raises(PermissionDenied):
        reserve_ai_call(learner, uuid4())
    confirm_ai_call(b)
    confirm_ai_call(a)
    assert usage_info(root)['used'] == usage_info(learner)['used'] == 2
    assert personal.get('/api/users/learning/access/').data['ai_usage'] == school.get('/api/users/learning/access/').data['ai_usage']


def test_courses_community_and_revocation_stay_in_their_space(spaces):
    root, workspace, member, learner, personal, school = spaces
    module = CourseModule.objects.create(institution=workspace.institution, subject='Finance', name='School module')
    course = Course.objects.create(institution=workspace.institution, module=module, title='School course', is_published=True, video_file='school.mp4')
    WorkspaceCourse.objects.create(workspace=workspace, course=course)
    invite = WorkspaceInvite.objects.create(workspace=workspace, created_by=root, name='Service', expires_on=workspace.service_ends_on, service_ends_on=workspace.service_ends_on, max_uses=2)
    grant = WorkspaceEnrollment.objects.create(membership=member, invite=invite, service_ends_on=workspace.service_ends_on)
    grant.courses.add(course)
    assert school.get(f'/api/courses/{course.pk}/').status_code == 200
    assert personal.get(f'/api/courses/{course.pk}/').status_code == 403
    assert school.get(f'/api/courses/{course.pk}/').data['video_file'].endswith(f'?space={workspace.pk}')
    school_post = school.post('/api/qa/questions/', {'content': 'School discussion'}, format='json')
    assert school_post.status_code == 201
    from faq_system.models import Question
    assert Question.objects.get(pk=school_post.data['id']).institution_id == workspace.institution_id
    assert personal.get(f"/api/qa/questions/{school_post.data['id']}/").status_code == 404
    member.is_active = False
    member.save(update_fields=['is_active'])
    assert school.get('/api/notes/items/').status_code == 403
    assert personal.get('/api/notes/items/').status_code == 200
    assert personal.post('/api/users/workspace/select/', {'workspace_id': workspace.pk}, format='json').status_code == 403
    with pytest.raises(ValueError):
        LoginSession.issue(learner)
    assert personal.post('/api/users/me/delete/', {'password': 'SmokePass123!'}, format='json').status_code == 200
    learner.refresh_from_db()
    assert not learner.is_active


def test_institution_selection_is_per_tab_not_account_current(spaces):
    root, workspace, member, learner, personal, first = spaces
    from users.workspaces.identity import select_learner
    other_inst = Institution.objects.create(name='Second school', slug='second-school')
    other = Workspace.objects.create(institution=other_inst, service_ends_on=workspace.service_ends_on, max_students=3)
    WorkspaceMembership.objects.create(user=root, workspace=other, is_current=False)
    other_learner = select_learner(root, str(other.pk))
    Note.objects.create(user=learner, title='First school')
    Note.objects.create(user=other_learner, title='Second school')
    second = APIClient()
    second.cookies['auth_token'] = LoginSession.issue(root).key
    second.credentials(HTTP_X_UNIMIND_WORKSPACE=str(other.pk))
    assert second.post('/api/users/workspace/switch/', {'workspace_id': other.pk}, format='json').status_code == 200
    assert [row['title'] for row in rows(first.get('/api/notes/items/'))] == ['First school']
    assert [row['title'] for row in rows(second.get('/api/notes/items/'))] == ['Second school']
    assert first.get('/api/users/workspace/').data['workspace']['id'] == workspace.pk
    assert second.get('/api/users/workspace/').data['workspace']['id'] == other.pk
    assert rows(personal.get('/api/notes/items/')) == []
    assert first.post('/api/users/workspace/leave/', {'workspace_id': workspace.pk}, format='json').status_code == 200
    assert first.get('/api/notes/items/').status_code == 403
    assert second.get('/api/notes/items/').status_code == 200
    assert personal.get('/api/notes/items/').status_code == 200
