"""Timestamped questions use owned course transcripts and keep their original anchor."""
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch

import pytest
from rest_framework.exceptions import NotFound, ValidationError

from ai_assistant.models import AIChatMessage, Bot
from ai_assistant.services.course_context import prepare_course_context
from courses.models import Course, CourseModule, TranscriptSegment, VideoTranscript


@pytest.fixture
def lesson(user, settings):
    settings.UNIMIND_CONTENT_INSTITUTION_ID = 'global'
    module = CourseModule.objects.create(name='公开课程', is_public=True)
    course = Course.objects.create(title='时间价值', module=module)
    transcript = VideoTranscript.objects.create(course=course, asr_status='completed',
        is_manually_edited=True, revision=3)
    for index, (start, end, text) in enumerate([
        (0, 60, 'OUTSIDE_BEFORE'),
        (60, 90, '折现是把未来现金流换算到今天。'),
        (90, 140, '完整推导' * 80 + 'FULL_SEGMENT_END'),
        (140, 180, '终值需要考虑时间和利率。'),
        (180, 200, 'OUTSIDE_AFTER'),
    ]):
        TranscriptSegment.objects.create(transcript=transcript, start_time=start,
            end_time=end, text=text, index=index)
    bot = Bot.objects.create(name='小宇', bot_type='planner')
    return course, transcript, bot


def question(user, course, position=120, conversation_id=None):
    return SimpleNamespace(user=user, query_params={}, data={
        'message': '这里为什么要折现？', 'request_id': str(uuid4()),
        'conversation_id': str(conversation_id or uuid4()),
        'course_context': {'course_id': course.pk, 'video_seconds': position},
    })


@pytest.mark.django_db
def test_timestamp_reads_complete_nearby_transcript_and_freezes_revision(user, lesson):
    course, transcript, bot = lesson
    request = question(user, course)
    context = prepare_course_context(request, bot, request.data['conversation_id'])
    assert context['video_seconds'] == 120 and context['revision'] == 3
    assert [segment['start_time'] for segment in context['segments']] == [60, 90, 140]
    assert context['segments'][1]['text'].endswith('FULL_SEGMENT_END')
    TranscriptSegment.objects.filter(transcript=transcript, index=1).update(text='修订内容')
    assert context['segments'][0]['text'] == '折现是把未来现金流换算到今天。'


@pytest.mark.django_db
def test_course_context_checks_access_missing_transcript_and_invalid_time(user, lesson):
    course, transcript, bot = lesson
    private = Course.objects.create(title='无权读取')
    request = question(user, private)
    with pytest.raises(NotFound):
        prepare_course_context(request, bot, request.data['conversation_id'])
    request = question(user, course)
    request.data['course_context']['video_seconds'] = float('nan')
    with pytest.raises(ValidationError):
        prepare_course_context(request, bot, request.data['conversation_id'])
    request = question(user, course, 9999)
    with pytest.raises(ValidationError, match='附近没有讲稿'):
        prepare_course_context(request, bot, request.data['conversation_id'])
    transcript.delete()
    request = question(user, course)
    with pytest.raises(ValidationError, match='暂无可用讲稿'):
        prepare_course_context(request, bot, request.data['conversation_id'])


@pytest.mark.django_db
def test_course_history_and_conversations_stay_separate(auth_client, user, lesson):
    course, _, bot = lesson
    cid = uuid4()
    context = {'course_id': course.pk, 'video_seconds': 120}
    AIChatMessage.objects.create(user=user, bot=bot, conversation_id=cid, role='user',
        content='COURSE_QUESTION', metadata={'course_context': context})
    AIChatMessage.objects.create(user=user, bot=bot, conversation_id=cid, role='assistant',
        content='COURSE_ANSWER', metadata={'course_context': context})
    AIChatMessage.objects.create(user=user, bot=bot, role='user', content='GENERAL_QUESTION')
    assert [row['content'] for row in auth_client.get('/api/ai/history/', {'course_id': course.pk}).data] == ['COURSE_QUESTION', 'COURSE_ANSWER']
    assert [row['content'] for row in auth_client.get('/api/ai/history/').data] == ['GENERAL_QUESTION']
    other = Course.objects.create(title='其他课', module=course.module)
    request = question(user, other, conversation_id=cid)
    with pytest.raises(ValidationError, match='独立对话'):
        prepare_course_context(request, bot, cid)
    request.data.pop('course_context')
    with pytest.raises(ValidationError, match='附带本课时间戳'):
        prepare_course_context(request, bot, cid)


@pytest.mark.django_db
def test_dsh_gets_signed_course_snapshot_and_preserves_sources_on_replay(user, lesson, settings, tmp_path):
    from ai_assistant.services.dsh_xiaoyu import complete_turn, task_context
    from users.models import WeeklyAIQuotaConfig
    settings.UNIMIND_DSH_STATE_DIR = str(tmp_path)
    settings.UNIMIND_DSH_TITLE_ENABLED = settings.UNIMIND_DSH_MEMORY_ENABLED = False
    WeeklyAIQuotaConfig.objects.update_or_create(pk=1, defaults={'experience_calls': 20, 'course_calls': 200})
    course, _, bot = lesson
    request = question(user, course)
    cid = request.data['conversation_id']
    context = prepare_course_context(request, bot, cid)
    def runtime(user, action, **kwargs):
        injected = task_context(user, kwargs['chat_context'], request.data['message'])
        assert 'FULL_SEGMENT_END' in injected and 'OUTSIDE_AFTER' not in injected
        assert '120.0' in injected and '时间价值' in injected
        return {'finish_reason': 'completed', 'content': '根据本课讲稿说明折现。',
                'session': {'id': 'a' * 32, 'messages': [{'role': 'assistant', 'cards': []}]}}
    with patch('ai_assistant.services.dsh_xiaoyu.run_site_action', side_effect=runtime) as run:
        result = complete_turn(request, bot, cid, request.data['message'], lambda event: None, course_context=context)
        replay = complete_turn(request, bot, cid, request.data['message'], lambda event: None, course_context=context)
        assert replay == result and run.call_count == 1
    assert result['metadata']['course_context']['video_seconds'] == 120
    assert result['metadata']['course_context']['revision'] == 3
    assert AIChatMessage.objects.filter(user=user, conversation_id=cid).count() == 2
    request.data['course_context']['video_seconds'] = 121
    with pytest.raises(ValidationError):
        complete_turn(request, bot, cid, request.data['message'], lambda event: None, course_context=context)


@pytest.mark.django_db
def test_stream_entry_validates_course_before_reserving_or_running(auth_client, user, lesson, settings):
    from users.models import AIUsageReservation
    settings.UNIMIND_DSH_XIAOYU_ENABLED = True
    private = Course.objects.create(title='PRIVATE_TRANSCRIPT')
    _, _, bot = lesson
    body = question(user, private).data
    body['bot_id'] = bot.pk
    with patch('ai_assistant.services.dsh_xiaoyu.run_site_action') as runtime:
        response = auth_client.post('/api/ai/chat/stream/', body, format='json')
    assert response.status_code == 404
    assert not AIUsageReservation.objects.filter(user=user).exists()
    runtime.assert_not_called()


@pytest.mark.django_db(transaction=True)
def test_legacy_stream_uses_same_transcript_and_persists_time(auth_client, user, lesson, settings):
    import asyncio
    import json
    from users.models import WeeklyAIQuotaConfig
    settings.UNIMIND_DSH_XIAOYU_ENABLED = False
    WeeklyAIQuotaConfig.objects.update_or_create(pk=1, defaults={'experience_calls': 20, 'course_calls': 200})
    course, _, bot = lesson
    body = question(user, course).data
    body['bot_id'] = bot.pk
    def answer(**kwargs):
        reference = '\n'.join(message['content'] for message in kwargs['messages'])
        assert 'FULL_SEGMENT_END' in reference and 'OUTSIDE_AFTER' not in reference
        return {'content': '折现将未来现金流换算到今天。', 'finish_reason': 'completed'}
    async def collect(response):
        return b''.join([frame async for frame in response.streaming_content]).decode()
    with patch('ai_engine.service.AIEngine.call_ai_with_streaming_tools', side_effect=answer), \
         patch('ai_assistant.services.title_generator.sync_generate_title', return_value='课程答疑'):
        response = auth_client.post('/api/ai/chat/stream/', body, format='json')
        assert response.status_code == 200
        frames = asyncio.run(collect(response))
    events = [json.loads(line[6:]) for line in frames.splitlines() if line.startswith('data: ')]
    done = next(event for event in events if event.get('done'))
    assert done['full_content'] == '折现将未来现金流换算到今天。'
    assert done['metadata']['course_context']['video_seconds'] == 120
    messages = list(AIChatMessage.objects.filter(conversation_id=body['conversation_id']).order_by('id'))
    assert len(messages) == 2
    assert all(message.metadata['course_context']['course_id'] == course.pk for message in messages)
