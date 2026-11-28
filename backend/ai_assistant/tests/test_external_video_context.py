"""External lecture questions preserve sources across SSE, polling and DSH."""
import asyncio
import base64
import copy
import io
import json
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.exceptions import ValidationError

from ai_assistant.models import AIChatMessage, Bot, Conversation
from ai_assistant.services.external_video_context import (
    external_video_context_text, external_video_visual_messages,
    prepare_external_video_context,
)
from courses.asr import ASRProvider, ASRProviderRegistry, TranscriptResult, TranscriptSegment
from users.models import AIUsageReservation, WeeklyAIQuotaConfig, WeeklyAIUsage


@pytest.fixture
def external_bot(db, settings):
    settings.UNIMIND_DSH_XIAOYU_ENABLED = False
    settings.UNIMIND_DSH_TITLE_ENABLED = settings.UNIMIND_DSH_MEMORY_ENABLED = False
    WeeklyAIQuotaConfig.objects.update_or_create(pk=1,
        defaults={'experience_calls': 100, 'course_calls': 200})
    cache.clear()
    return Bot.objects.create(name='外部视频小宇', bot_type='planner', is_xiaoyu=True,
                              system_prompt='帮助学生理解公开课。')


def jpeg(color='red', size=(100, 80)):
    output = io.BytesIO()
    Image.new('RGB', size, color).save(output, format='JPEG')
    return 'data:image/jpeg;base64,' + base64.b64encode(output.getvalue()).decode('ascii')


@pytest.fixture
def external_context():
    return {
        'platform': 'bilibili', 'external_id': 'BV1test', 'part': 1,
        'url': 'https://www.bilibili.com/video/BV1test?p=1&special=[a]',
        'title': '折现与债券定价', 'video_seconds': 120.0,
        'transcript_source': 'platform_ai_subtitle',
        'segments': [{'start_time': 110.5, 'end_time': 125.0,
                      'text': 'FULL_EXTERNAL_TRANSCRIPT 折现将未来现金流换算到今天。'}],
        'visual': {
            'current': {'video_seconds': 120.0, 'image': jpeg()},
            'previous': {'video_seconds': 112.0, 'image': jpeg('blue')},
        },
        'integration_hooks': {'knowledge_tree_id': 9, 'knowledge_node_id': 'node-1',
                              'memory_event_target': None},
    }


def request_body(bot, context=None, conversation_id=None):
    body = {'bot_id': bot.pk, 'message': '为什么这里要折现？',
            'request_id': str(uuid4()), 'conversation_id': str(conversation_id or uuid4())}
    if context is not None:
        body['external_video_context'] = copy.deepcopy(context)
    return body


def prepare(user, bot, context, **extra):
    body = request_body(bot, context)
    body.update(extra)
    return prepare_external_video_context(
        SimpleNamespace(user=user, data=body), bot, body['conversation_id'])


async def collect_stream(response):
    return b''.join([frame async for frame in response.streaming_content]).decode()


def stream_events(response):
    frames = asyncio.run(collect_stream(response))
    return [json.loads(line[6:]) for line in frames.splitlines() if line.startswith('data: ')]


def assert_injected(messages, context):
    text = '\n'.join(row['content'] for row in messages if isinstance(row['content'], str))
    assert context['title'] in text
    if context['segments']:
        assert 'FULL_EXTERNAL_TRANSCRIPT' in text
    images = [block['image_url']['url'] for row in messages if isinstance(row['content'], list)
              for block in row['content'] if block['type'] == 'image_url']
    assert images == [context['visual'][key]['image'] for key in ('previous', 'current')
                      if key in context.get('visual', {})]


@pytest.mark.django_db
def test_normalization_and_prompt_keep_original_sources(user, external_bot, external_context):
    original = copy.deepcopy(external_context)
    external_context.update(platform='BiLiBiLi', external_id=' BV1test ', part=None)
    external_context['url'] = 'http://localhost/watch?value=[x]\n\t'
    context = prepare(user, external_bot, external_context)
    assert context['video_key'] == 'bilibili:BV1test:p1'
    assert context['part'] == 1 and context['platform'] == 'bilibili'
    assert '\n' not in context['url'] and '\t' not in context['url']
    assert context['integration_hooks'] == original['integration_hooks']
    prompt = external_video_context_text(context)
    assert 'FULL_EXTERNAL_TRANSCRIPT' in prompt and '系统规则' in prompt
    assert '[讲稿 MM:SS](#seek:' in prompt
    assert original['visual']['current']['image'] not in prompt
    blocks = external_video_visual_messages(context)
    assert len(blocks) == 4
    assert blocks[1]['image_url']['url'] == original['visual']['previous']['image']
    assert blocks[3]['image_url']['url'] == original['visual']['current']['image']
    assert '[画面 02:00](#seek:120.0)' in blocks[2]['text']
    external_context['segments'][0]['text'] = 'CHANGED_AFTER_PREPARATION'
    assert context['segments'][0]['text'] == original['segments'][0]['text']


@pytest.mark.django_db
@pytest.mark.parametrize(('platform', 'part', 'key'), [
    ('bilibili', -2, 'bilibili:BV1test:p1'),
    ('youtube', 1, 'youtube:BV1test'),
    ('youtube', 2, 'youtube:BV1test:p2'),
    ('generic', 1, 'generic:BV1test'),
])
def test_video_key_and_part_defaults(user, external_bot, external_context, platform, part, key):
    external_context.update(platform=platform, part=part)
    assert prepare(user, external_bot, external_context)['video_key'] == key


@pytest.mark.django_db
def test_segments_are_sorted_trimmed_filtered_and_repaired(user, external_bot, external_context):
    external_context['video_seconds'] = 50
    external_context['segments'] = [
        {'start_time': index, 'end_time': index - 1, 'text': ' x ' * 500}
        for index in reversed(range(100))
    ] + [{'start_time': 50, 'end_time': 51, 'text': '  '}]
    context = prepare(user, external_bot, external_context)
    segments = context['segments']
    assert len(segments) == 80
    assert [row['start_time'] for row in segments] == sorted(row['start_time'] for row in segments)
    assert all(len(row['text']) == 1000 for row in segments)
    assert all(row['end_time'] == row['start_time'] for row in segments)
    assert all(abs(row['start_time'] - 50) <= 40 for row in segments)


@pytest.mark.django_db
@pytest.mark.parametrize(('field', 'value'), [
    ('video_seconds', -1), ('video_seconds', float('nan')),
    ('video_seconds', float('inf')), ('external_id', '  '),
    ('external_id', 'x' * 129), ('platform', 'unsupported'),
    ('title', 'x' * 301), ('url', 'x' * 1001),
])
def test_invalid_required_fields_raise_validation_error(user, external_bot, external_context, field, value):
    external_context[field] = value
    with pytest.raises(ValidationError):
        prepare(user, external_bot, external_context)


@pytest.mark.django_db
@pytest.mark.parametrize('bad_time', [-1, float('nan'), float('inf')])
def test_nonfinite_or_negative_segment_time_is_rejected(user, external_bot, external_context, bad_time):
    external_context['segments'][0]['start_time'] = bad_time
    with pytest.raises(ValidationError):
        prepare(user, external_bot, external_context)


@pytest.mark.django_db
def test_missing_context_returns_none_and_bot_and_mutual_exclusion_are_checked(user, external_bot, external_context):
    assert prepare(user, external_bot, None) is None
    with pytest.raises(ValidationError, match='不能同时传入站内课程与外部视频上下文'):
        prepare(user, external_bot, external_context, course_context={'course_id': 1})
    external_bot.bot_type = 'exam_generator'
    with pytest.raises(ValidationError, match='视频伴学提问仅支持小宇'):
        prepare(user, external_bot, external_context)
    assert prepare(user, external_bot, None) is None


@pytest.mark.django_db
@pytest.mark.parametrize('bad_image', ['data:image/jpeg;base64,!bad!', jpeg(size=(1281, 1))])
def test_external_visual_reuses_jpeg_validation(user, external_bot, external_context, bad_image):
    external_context['visual']['current']['image'] = bad_image
    with pytest.raises(ValidationError):
        prepare(user, external_bot, external_context)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(('empty_segments', 'current_time', 'previous_time', 'include_visual'), [
    (False, 120.0, 112.0, True),
    (True, 120.0, 112.0, True),
    (True, 120.0, 112.0, False),
    (False, 121.8, 112.0, True),
    (False, 130.0, 112.0, True),
    (False, 120.0, 100.0, True),
    (False, 120.0, 121.0, True),
])
def test_standard_stream_accepts_tolerances_and_saves_sources(
        auth_client, user, external_bot, external_context, empty_segments, current_time,
        previous_time, include_visual):
    if empty_segments:
        external_context['segments'] = []
    external_context['visual']['current']['video_seconds'] = current_time
    external_context['visual']['previous']['video_seconds'] = previous_time
    if not include_visual:
        external_context.pop('visual')
    body = request_body(external_bot, external_context)
    normalized = prepare(user, external_bot, external_context)

    def answer(**kwargs):
        assert_injected(kwargs['messages'], normalized)
        if empty_segments:
            assert '暂无字幕文本' in '\n'.join(row['content'] for row in kwargs['messages']
                                              if isinstance(row['content'], str))
        return {'content': '外部视频讲解完成。', 'finish_reason': 'completed'}

    with patch('ai_engine.service.AIEngine.call_ai_with_streaming_tools', side_effect=answer), \
         patch('ai_assistant.services.title_generator.sync_generate_title', return_value='视频答疑'):
        response = auth_client.post('/api/ai/chat/stream/', body, format='json')
        assert response.status_code == 200
        events = stream_events(response)
    done = next(event for event in events if event.get('done'))
    assert done['full_content'] == '外部视频讲解完成。'
    saved = done['metadata']['external_video_context']
    assert saved['video_key'] == 'bilibili:BV1test:p1'
    assert saved == normalized
    if include_visual:
        assert saved['visual']['current']['video_seconds'] == current_time
        assert ('previous' in saved['visual']) == (0 < current_time - previous_time <= 15)
    messages = AIChatMessage.objects.filter(conversation_id=body['conversation_id']).order_by('id')
    assert messages.count() == 2
    assert all(row.metadata['external_video_context'] == normalized for row in messages)


@pytest.mark.django_db(transaction=True)
def test_followup_without_context_and_switching_part_are_allowed(auth_client, external_bot, external_context):
    cid = uuid4()
    bodies = [request_body(external_bot, external_context, cid), request_body(external_bot, None, cid)]
    external_context['part'] = 2
    bodies.append(request_body(external_bot, external_context, cid))
    with patch('ai_engine.service.AIEngine.call_ai_with_streaming_tools', return_value={
            'content': '继续举例。', 'finish_reason': 'completed'}), \
         patch('ai_assistant.services.title_generator.sync_generate_title', return_value='连续提问'):
        for body in bodies:
            response = auth_client.post('/api/ai/chat/stream/', body, format='json')
            assert response.status_code == 200
            assert any(event.get('full_content') == '继续举例。' for event in stream_events(response))
    rows = list(AIChatMessage.objects.filter(conversation_id=cid, role='user').order_by('id'))
    assert len(rows) == 3
    assert rows[0].metadata['external_video_context']['video_key'].endswith(':p1')
    assert 'external_video_context' not in rows[1].metadata
    assert rows[2].metadata['external_video_context']['video_key'].endswith(':p2')


@pytest.mark.django_db
@pytest.mark.parametrize('route', ['/api/ai/chat/stream/', '/api/ai/chat/'])
def test_context_conflict_rejects_before_quota_or_messages(auth_client, user, external_bot, external_context, route):
    body = request_body(external_bot, external_context)
    body['course_context'] = {'course_id': 1, 'video_seconds': 120}
    response = auth_client.post(route, body, format='json')
    assert response.status_code == 400
    assert '不能同时传入站内课程与外部视频上下文' in str(response.data)
    assert not AIUsageReservation.objects.filter(user=user).exists()
    assert not AIChatMessage.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_request_fingerprint_tracks_video_and_image_changes(user, external_bot, external_context):
    from ai_assistant.views import _reserve_chat_request
    body = request_body(external_bot, external_context)
    fingerprints = []
    with patch('users.learning.reserve_ai_call') as reserve:
        for _ in range(2):
            _reserve_chat_request(user, body, external_bot)
            fingerprints.append(reserve.call_args.kwargs['fingerprint'])
        body['external_video_context']['part'] = 2
        _reserve_chat_request(user, body, external_bot)
        fingerprints.append(reserve.call_args.kwargs['fingerprint'])
        body['external_video_context']['visual']['current']['image'] = jpeg('green')
        _reserve_chat_request(user, body, external_bot)
        fingerprints.append(reserve.call_args.kwargs['fingerprint'])
    assert fingerprints[0] == fingerprints[1]
    assert len(set(fingerprints)) == 3


@pytest.mark.django_db
def test_polling_path_injects_transcript_and_frame_descriptions_and_persists_metadata(
        auth_client, user, external_bot, external_context):
    body = request_body(external_bot, external_context)
    normalized = prepare(user, external_bot, external_context)

    def dispatch(**kwargs):
        reference = '\n'.join(row['content'] for row in kwargs['history'])
        assert 'FULL_EXTERNAL_TRANSCRIPT' in reference and external_context['title'] in reference
        assert '112.0' in reference and '120.0' in reference
        assert 'data:image' not in reference
        return {'result': {'choices': [{'message': {'content': '轮询视频讲解。'},
                                       'finish_reason': 'stop'}]},
                'tool_executor': SimpleNamespace(), 'prompt_variant': 'baseline'}

    with patch('ai_assistant.utils._THREAD_POOL.submit', side_effect=lambda fn, *a, **kw: fn(*a, **kw)), \
         patch('ai_assistant.services.chat_dispatch.dispatch_bot_chat', side_effect=dispatch) as run, \
         patch('ai_assistant.services.trajectory_recorder.record_trajectory'), \
         patch('ai_assistant.tasks.generate_conversation_title.delay'):
        response = auth_client.post('/api/ai/chat/', body, format='json')
    assert response.status_code == 200
    run.assert_called_once()
    rows = list(AIChatMessage.objects.filter(conversation_id=body['conversation_id']).order_by('id'))
    assert len(rows) == 2 and rows[1].content == '轮询视频讲解。'
    assert all(row.metadata['external_video_context'] == normalized for row in rows)


@pytest.mark.django_db(transaction=True)
def test_dsh_stream_reads_external_transcript_and_dual_frames(
        auth_client, user, external_bot, external_context, settings, tmp_path):
    from ai_assistant.services.dsh_xiaoyu import task_context, task_course_visual
    settings.UNIMIND_DSH_ENABLED = settings.UNIMIND_DSH_SITE_ENABLED = True
    settings.UNIMIND_DSH_XIAOYU_ENABLED = True
    settings.UNIMIND_DSH_STATE_DIR = str(tmp_path)
    body = request_body(external_bot, external_context)
    normalized = prepare(user, external_bot, external_context)

    def runtime(owner, action, **kwargs):
        text = task_context(owner, kwargs['chat_context'], body['message'])
        assert 'FULL_EXTERNAL_TRANSCRIPT' in text and external_context['title'] in text
        assert external_context['visual']['current']['image'] not in text
        assert task_course_visual(owner, kwargs['chat_context'], body['message']) == external_video_visual_messages(normalized)
        return {'finish_reason': 'completed', 'content': 'DSH 视频回答。',
                'session': {'id': 'a' * 32, 'messages': [{'role': 'assistant', 'cards': []}]}}

    # The production lock uses POSIX fcntl, while this suite also runs on Windows.
    with patch('ai_assistant.services.dsh_xiaoyu.site_request_lock', side_effect=lambda *a: nullcontext()), \
         patch('ai_assistant.services.dsh_xiaoyu.quota_write_lock', side_effect=lambda: nullcontext()), \
         patch('ai_assistant.services.dsh_xiaoyu.run_site_action', side_effect=runtime) as run:
        response = auth_client.post('/api/ai/chat/stream/', body, format='json')
        assert response.status_code == 200
        done = next(event for event in stream_events(response) if event.get('done'))
    assert done['full_content'] == 'DSH 视频回答。', done
    run.assert_called_once()
    assert done['metadata']['external_video_context'] == normalized
    rows = AIChatMessage.objects.filter(conversation_id=body['conversation_id'])
    assert rows.count() == 2 and all(row.metadata['external_video_context'] == normalized for row in rows)


@pytest.mark.django_db(transaction=True)
def test_ulr_external_video_stream_and_polling_share_the_same_receipt(
        auth_client, user, external_bot, external_context, settings, tmp_path):
    settings.UNIMIND_LEARNING_RUNTIME = 'ulr'
    settings.UNIMIND_DSH_ENABLED = False
    settings.UNIMIND_DSH_STATE_DIR = str(tmp_path)
    settings.USE_MEM0 = False
    body = request_body(external_bot, external_context)
    normalized = prepare(user, external_bot, external_context)
    answer = '把现金流换算到今天，才能在同一时间点比较。'

    def model(messages, **kwargs):
        assert_injected(messages, external_context)
        assert external_context['visual']['current']['image'] not in messages[0]['content']
        return {'choices': [{'finish_reason': 'stop', 'message': {'content': answer}}]}

    with patch('ai_engine.service.AIEngine.call_provider', side_effect=model) as provider, \
         patch('ai_assistant.services.ulr_outbox.publish_after_commit'):
        response = auth_client.post('/api/ai/chat/stream/', body, format='json')
        assert response.status_code == 200
        done = next(event for event in stream_events(response) if event.get('done'))
        replay = auth_client.post('/api/ai/chat/', body, format='json')
        assert replay.status_code == 200
        assert replay.data['status'] == 'completed'
        assert replay.data['full_content'] == done['full_content'] == answer
        changed = copy.deepcopy(body)
        changed['external_video_context']['part'] = 2
        rejected = auth_client.post('/api/ai/chat/', changed, format='json')
        assert rejected.status_code == 400
        assert '请求标识已用于另一条提问' in str(rejected.data)

    provider.assert_called_once()
    assert done['metadata']['engine'] == 'ulr'
    rows = AIChatMessage.objects.filter(user=user, conversation_id=body['conversation_id'])
    assert rows.count() == 2 and all(row.metadata['external_video_context'] == normalized for row in rows)
    assert WeeklyAIUsage.objects.get(user=user).ai_calls == 1


@pytest.mark.django_db
def test_signed_dsh_context_callback_exposes_only_authorized_external_sources(
        api_client, user, external_bot, external_context, settings):
    from ai_assistant.dsh_authentication import make_task_token
    settings.UNIMIND_DSH_ENABLED = settings.UNIMIND_DSH_XIAOYU_ENABLED = True
    normalized = prepare(user, external_bot, external_context)
    current = AIChatMessage.objects.create(user=user, bot=external_bot, role='user',
        content='签名视频提问', metadata={'external_video_context': normalized})
    claims = {'message_id': current.pk, 'bot_id': external_bot.pk,
              'conversation_id': str(current.conversation_id)}
    api_client.credentials(HTTP_AUTHORIZATION='DSH ' + make_task_token(user, chat_context=claims))
    response = api_client.post('/api/ai/dsh/context/', {'message': current.content}, format='json')
    assert response.status_code == 200
    assert 'FULL_EXTERNAL_TRANSCRIPT' in response.data['system_prompt']
    assert response.data['course_visual_content'] == external_video_visual_messages(normalized)
    assert response.data['course_visual_message'] == current.content
    assert api_client.post('/api/ai/dsh/context/', {'message': '篡改问题'}, format='json').status_code == 403
    other = type(user).objects.create_user(username='foreign-external-context')
    foreign = AIChatMessage.objects.create(user=other, bot=external_bot, role='user', content='他人视频资料',
        metadata={'external_video_context': normalized})
    forged_context = {**claims, 'message_id': foreign.pk, 'conversation_id': str(foreign.conversation_id)}
    api_client.credentials(HTTP_AUTHORIZATION='DSH ' + make_task_token(user, chat_context=forged_context))
    assert api_client.post('/api/ai/dsh/context/', {'message': foreign.content}, format='json').status_code == 403


@pytest.mark.django_db
def test_video_conversations_are_exact_ordered_and_user_scoped(auth_client, user, external_bot):
    from django.utils import timezone
    from datetime import timedelta
    other = type(user).objects.create_user(username='external-other')
    keys = ['bilibili:BV1test:p1', 'bilibili:BV1test:p1', 'bilibili:BV1test:p2', 'youtube:BV1test']
    chats = []
    for index, key in enumerate(keys):
        cid = uuid4()
        chat = Conversation.objects.create(user=user, bot=external_bot, conversation_id=cid, title=str(index))
        Conversation.objects.filter(pk=chat.pk).update(updated_at=timezone.now() + timedelta(minutes=index))
        AIChatMessage.objects.create(user=user, bot=external_bot, conversation_id=cid, role='user',
            content='本人问题', metadata={'external_video_context': {'video_key': key}})
        chats.append(chat)
    foreign_cid = uuid4()
    Conversation.objects.create(user=other, bot=external_bot, conversation_id=foreign_cid)
    AIChatMessage.objects.create(user=other, bot=external_bot, conversation_id=foreign_cid, role='user',
        content='他人问题', metadata={'external_video_context': {'video_key': keys[0]}})
    # Matching another user's malformed message UUID cannot select our conversation.
    AIChatMessage.objects.create(user=other, bot=external_bot, conversation_id=chats[2].conversation_id,
        role='user', content='他人消息', metadata={'external_video_context': {'video_key': keys[0]}})
    response = auth_client.get('/api/ai/conversations/', {'external_video_key': ' ' + keys[0] + ' '})
    assert response.status_code == 200
    rows = response.data.get('results', []) if isinstance(response.data, dict) else response.data
    assert [row['conversation_id'] for row in rows] == [str(chats[1].conversation_id), str(chats[0].conversation_id)]


@pytest.fixture
def no_asr(settings, monkeypatch):
    settings.ASR_PROVIDER_CONFIG = {}
    monkeypatch.delenv('EXTERNAL_SNIPPET_ASR_PROVIDER', raising=False)
    cache.clear()


def snippet_upload(name='clip.m4s', mime='application/octet-stream', payload=b'fake fragment'):
    return SimpleUploadedFile(name, payload, content_type=mime)


def snippet_body(**kwargs):
    return {'audio': snippet_upload(), 'platform': 'bilibili', 'external_id': 'BV1test',
            'part': 1, 'clip_start_seconds': 260.0, **kwargs}


@pytest.mark.django_db
def test_audio_without_credentials_returns_available_false_and_never_charges(auth_client, user, no_asr):
    response = auth_client.post('/api/ai/external-audio-snippet/', snippet_body(), format='multipart')
    assert response.status_code == 200
    assert response.data == {'available': False, 'provider': 'unconfigured', 'cached': False,
                              'segments': [], 'full_text': ''}
    assert not AIUsageReservation.objects.filter(user=user).exists()
    assert not WeeklyAIUsage.objects.filter(user=user, ai_calls__gt=0).exists()


@pytest.mark.django_db
@pytest.mark.parametrize(('name', 'mime'), [
    ('clip.m4s', 'application/octet-stream'), ('clip.mp4', 'video/mp4'),
    ('clip.m4s', 'audio/mp4'), ('clip.aac', 'audio/aac'),
])
def test_audio_permissive_mime_contract(auth_client, no_asr, name, mime):
    response = auth_client.post('/api/ai/external-audio-snippet/',
        snippet_body(audio=snippet_upload(name, mime)), format='multipart')
    assert response.status_code == 200 and response.data['segments'] == []


@pytest.mark.django_db
def test_audio_provider_timestamp_offset_bucket_cache_and_temp_cleanup(
        auth_client, settings, monkeypatch, no_asr):
    paths = []

    class LocalProvider(ASRProvider):
        def transcribe(self, audio_path):
            assert Path(audio_path).read_bytes() == b'fake fragment'
            paths.append(audio_path)
            return TranscriptResult(segments=[TranscriptSegment(1.234, 4.567, '绝对时间讲稿')],
                                    full_text='绝对时间讲稿')

    settings.ASR_PROVIDER_CONFIG = {'mimo_asr': {'api_key': 'synthetic-key'}}
    monkeypatch.setitem(ASRProviderRegistry._providers, 'mimo_asr', LocalProvider)
    first = auth_client.post('/api/ai/external-audio-snippet/', snippet_body(), format='multipart')
    assert first.status_code == 200
    assert first.data == {'available': True, 'provider': 'mimo_asr', 'cached': False,
        'segments': [{'start_time': 261.23, 'end_time': 264.57, 'text': '绝对时间讲稿'}],
        'full_text': '绝对时间讲稿'}
    second = auth_client.post('/api/ai/external-audio-snippet/',
        snippet_body(clip_start_seconds=263), format='multipart')
    assert second.status_code == 200 and second.data['cached'] is True
    assert second.data['segments'] == first.data['segments']
    assert len(paths) == 1 and not Path(paths[0]).exists()


def test_audio_cache_failure_does_not_block_transcription(settings, monkeypatch, no_asr):
    from ai_assistant.services.external_audio_asr import transcribe_external_snippet
    provider = MagicMock()
    provider.transcribe.return_value = TranscriptResult(
        segments=[TranscriptSegment(1.111, 2.222, '缓存异常仍可转写')], full_text='缓存异常仍可转写')
    with patch('ai_assistant.services.external_audio_asr._select_provider', return_value=('mimo_asr', provider)), \
         patch('ai_assistant.services.external_audio_asr.cache.get', side_effect=RuntimeError('cache unavailable')), \
         patch('ai_assistant.services.external_audio_asr.cache.set', side_effect=RuntimeError('cache unavailable')):
        response = transcribe_external_snippet(snippet_upload(), platform='generic',
                                              external_id='cache-failure', clip_start_seconds=-5)
    assert response['available'] is True and response['cached'] is False
    assert response['segments'] == [{'start_time': 1.11, 'end_time': 2.22, 'text': '缓存异常仍可转写'}]
    assert not Path(provider.transcribe.call_args.args[0]).exists()


def test_audio_provider_priority_and_qwen_require_complete_oss(settings, monkeypatch, no_asr):
    from ai_assistant.services.external_audio_asr import _select_provider
    settings.ASR_PROVIDER_CONFIG = {
        name: {'api_key': 'synthetic-key'}
        for name in ('mimo_asr', 'glm_asr', 'whisper_openai', 'qwen_filetrans')
    }
    monkeypatch.setenv('EXTERNAL_SNIPPET_ASR_PROVIDER', 'glm_asr')
    assert _select_provider()[0] == 'glm_asr'
    monkeypatch.setenv('EXTERNAL_SNIPPET_ASR_PROVIDER', 'unknown')
    assert _select_provider()[0] == 'mimo_asr'
    settings.ASR_PROVIDER_CONFIG['mimo_asr']['api_key'] = ''
    assert _select_provider()[0] == 'glm_asr'
    settings.ASR_PROVIDER_CONFIG['glm_asr']['api_key'] = ''
    assert _select_provider()[0] == 'whisper_openai'
    settings.ASR_PROVIDER_CONFIG['whisper_openai']['api_key'] = ''
    for name in ('OSS_ACCESS_KEY_ID', 'OSS_ACCESS_KEY_SECRET', 'OSS_BUCKET_NAME', 'OSS_ENDPOINT'):
        setattr(settings, name, '')
    assert _select_provider() == (None, None)
    for name in ('OSS_ACCESS_KEY_ID', 'OSS_ACCESS_KEY_SECRET', 'OSS_BUCKET_NAME', 'OSS_ENDPOINT'):
        setattr(settings, name, 'synthetic-value')
    assert _select_provider()[0] == 'qwen_filetrans'
    monkeypatch.setenv('EXTERNAL_SNIPPET_ASR_PROVIDER', 'dummy')
    assert _select_provider()[0] == 'dummy'


@pytest.mark.parametrize('fails', [False, True])
def test_qwen_upload_uses_signed_url_and_always_deletes_temporary_object(
        settings, monkeypatch, tmp_path, fails):
    from ai_assistant.services.external_audio_asr import _transcribe_with_oss
    source = tmp_path / 'snippet.m4a'
    source.write_bytes(b'synthetic audio')
    for name in ('OSS_ACCESS_KEY_ID', 'OSS_ACCESS_KEY_SECRET', 'OSS_BUCKET_NAME', 'OSS_ENDPOINT'):
        setattr(settings, name, 'synthetic-value')
    bucket = MagicMock()
    bucket.sign_url.return_value = 'https://oss.invalid/signed-audio'
    oss = MagicMock()
    oss.Bucket.return_value = bucket
    monkeypatch.setitem(__import__('sys').modules, 'oss2', oss)
    provider = MagicMock()
    result = TranscriptResult(full_text='远程音频讲稿')
    if fails:
        provider.transcribe_url.side_effect = RuntimeError('provider failed')
        with pytest.raises(RuntimeError, match='provider failed'):
            _transcribe_with_oss(provider, str(source))
    else:
        provider.transcribe_url.return_value = result
        assert _transcribe_with_oss(provider, str(source)) is result
    provider.transcribe_url.assert_called_once_with('https://oss.invalid/signed-audio')
    key = bucket.put_object.call_args.args[0]
    assert key.startswith('tmp/ext-asr/') and key.endswith('.m4a')
    assert bucket.sign_url.call_args.args[:2] == ('GET', key)
    bucket.delete_object.assert_called_once_with(key)


@pytest.mark.django_db
@pytest.mark.parametrize(('payload', 'error'), [
    (b'', None), (b'x' * (4 * 1024 * 1024 + 1), '音频切片不能超过 4 MiB'),
])
def test_audio_empty_and_oversize_rejected(auth_client, no_asr, payload, error):
    response = auth_client.post('/api/ai/external-audio-snippet/',
        snippet_body(audio=snippet_upload(payload=payload)), format='multipart')
    assert response.status_code == 400
    if error:
        assert error in str(response.data)


@pytest.mark.django_db
def test_audio_endpoint_has_independent_rate_limit(auth_client, no_asr):
    for _ in range(30):
        response = auth_client.post('/api/ai/external-audio-snippet/', snippet_body(), format='multipart')
        assert response.status_code == 200
    assert auth_client.post('/api/ai/external-audio-snippet/', snippet_body(), format='multipart').status_code == 429


@pytest.mark.django_db
@pytest.mark.parametrize('origin', ['chrome-extension://' + 'a' * 32,
                                   'moz-extension://12345678-abcd-1234-abcd-123456789abc'])
def test_extension_origins_support_authorization_preflight(api_client, settings, origin):
    assert settings.CORS_ALLOW_EXTENSION_ORIGINS is True
    response = api_client.options('/api/ai/external-audio-snippet/',
        HTTP_ORIGIN=origin, HTTP_ACCESS_CONTROL_REQUEST_METHOD='POST',
        HTTP_ACCESS_CONTROL_REQUEST_HEADERS='authorization,content-type')
    assert response.status_code == 200
    assert response['Access-Control-Allow-Origin'] == origin
    assert 'authorization' in response['Access-Control-Allow-Headers'].lower()
