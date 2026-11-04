from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from ai_assistant.models import AIChatMessage, Bot
from courses.models import Course, CourseModule
from notes.models import Note


@pytest.fixture
def course_reply(user, settings):
    settings.UNIMIND_CONTENT_INSTITUTION_ID = 'global'
    course = Course.objects.create(is_published=True, title='债券估值',
        module=CourseModule.objects.create(name='公开课程', is_public=True))
    bot = Bot.objects.create(name='小宇', bot_type='planner')
    context = {'course_id': course.pk, 'course_title': course.title,
        'video_seconds': 615.5, 'start_seconds': 555.0, 'end_seconds': 690.0}
    conversation = uuid4()
    question = AIChatMessage.objects.create(user=user, bot=bot, role='user',
        conversation_id=conversation, content='为什么利息和本金要分别折现？',
        metadata={'course_context': context})
    answer = AIChatMessage.objects.create(user=user, bot=bot, role='assistant',
        conversation_id=conversation, content='利息是年金，本金到期支付。\n\n$$V=\\sum_{t=1}^n \\frac{I}{(1+r)^t}+\\frac{F}{(1+r)^n}$$',
        metadata={'course_context': context, 'engine': 'dsh'})
    return course, question, answer


@pytest.mark.django_db
def test_save_course_reply_keeps_formula_question_and_replay_links(auth_client, user, course_reply):
    course, question, answer = course_reply
    answer.content += f'\n讲解依据：[讲稿 09:15](/course/{course.pk}?t=555#segment-42)'
    answer.save(update_fields=['content'])
    url = f'/api/notes/course-replies/{answer.pk}/'
    result = auth_client.post(url, {}, format='json')
    assert result.status_code == 201
    note = Note.objects.get(pk=result.data['id'], user=user)
    assert note.title == '债券估值 · 10:15'
    assert question.content in note.content and answer.content in note.content
    assert f'[10:15](/course/{course.pk}?t=615.5)' in note.content
    assert f'[09:15–11:30](/course/{course.pk}?t=555)' in note.content
    answer.refresh_from_db()
    assert answer.metadata['saved_note_id'] == note.pk

    note.content += '\n\n我自己补充的内容。'
    note.save(update_fields=['content'])
    replay = auth_client.post(url, {}, format='json')
    assert replay.status_code == 200 and replay.data['id'] == note.pk
    assert Note.objects.count() == 1
    assert replay.data['content'].endswith('我自己补充的内容。')


@pytest.mark.django_db
def test_save_course_reply_checks_owner_and_course_access(auth_client, course_reply):
    course, question, answer = course_reply
    other = get_user_model().objects.create_user(username='another-note-owner')
    auth_client.force_authenticate(other)
    assert auth_client.post(f'/api/notes/course-replies/{answer.pk}/', {}).status_code == 404
    auth_client.force_authenticate(answer.user)
    assert auth_client.post(f'/api/notes/course-replies/{question.pk}/', {}).status_code == 404
    course.module.is_public = False
    course.module.save(update_fields=['is_public'])
    assert auth_client.post(f'/api/notes/course-replies/{answer.pk}/', {}).status_code == 404
    assert not Note.objects.exists()


@pytest.mark.django_db
def test_incomplete_or_non_course_reply_cannot_be_saved(auth_client, course_reply):
    _, _, answer = course_reply
    answer.content = '[Thinking...]'
    answer.save(update_fields=['content'])
    assert auth_client.post(f'/api/notes/course-replies/{answer.pk}/', {}).status_code == 400
    answer.content, answer.metadata = '普通聊天内容', {}
    answer.save(update_fields=['content', 'metadata'])
    assert auth_client.post(f'/api/notes/course-replies/{answer.pk}/', {}).status_code == 400
    assert not Note.objects.exists()


@pytest.mark.django_db
def test_deleted_saved_note_is_not_recreated(auth_client, course_reply):
    _, _, answer = course_reply
    url = f'/api/notes/course-replies/{answer.pk}/'
    saved = auth_client.post(url, {}, format='json')
    assert saved.status_code == 201
    Note.objects.filter(pk=saved.data['id']).update(deleted_at=timezone.now())
    assert auth_client.post(url, {}, format='json').status_code == 404
    assert Note.objects.count() == 1
