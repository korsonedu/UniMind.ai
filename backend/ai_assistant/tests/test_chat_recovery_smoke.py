"""Synthetic-user smoke: status recovery never executes or consumes quota."""
from datetime import timedelta
import json
from unittest.mock import patch
from uuid import uuid4

from asgiref.sync import async_to_sync
import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from ai_assistant.models import AIChatMessage, Bot, Conversation
from users.models import AIUsageReservation, WeeklyAIUsage


@pytest.mark.django_db
def test_request_status_is_read_only_and_owner_scoped(auth_client, user):
    request_id = uuid4()
    conversation_id = uuid4()
    url = f'/api/ai/chat-requests/{request_id}/'
    assert APIClient().get(url).status_code == 401
    assert auth_client.get(url).data['status'] == 'unknown'
    reservation = AIUsageReservation.objects.create(user=user, request_id=request_id,
        attempt_id=uuid4(), conversation_id=conversation_id, week=timezone.now().date())
    assert auth_client.get(url).data['status'] == 'pending'
    AIUsageReservation.objects.filter(pk=reservation.pk).update(updated_at=timezone.now() - timedelta(hours=2))
    assert auth_client.get(url).data['status'] == 'unknown'
    reservation.refresh_from_db()
    assert reservation.status == 'pending'
    bot = Bot.objects.create(name='小宇', is_xiaoyu=True)
    answer = AIChatMessage.objects.create(user=user, bot=bot, conversation_id=conversation_id,
                                          role='assistant', content='synthetic answer')
    reservation.status = 'succeeded'
    reservation.response = {'done': True, 'message_id': answer.pk, 'full_content': answer.content}
    reservation.save()
    response = auth_client.get(url)
    assert response.data['status'] == 'completed'
    assert response.data['response'] == reservation.response
    assert response['Cache-Control'] == 'no-store'
    other = type(user).objects.create_user(username='recovery-other')
    client = APIClient()
    client.force_authenticate(other)
    assert client.get(url).data == {'request_id': str(request_id), 'status': 'unknown'}
    answer.delete()
    assert auth_client.get(url).data['status'] == 'unknown'
    reservation.response = {'deleted': True}
    reservation.save()
    assert auth_client.get(url).data['status'] == 'unknown'
    reservation.status = 'released'
    reservation.response = {'done': True, 'is_error': True, 'full_content': '合成失败'}
    reservation.save()
    failed = auth_client.get(url).data
    assert failed['status'] == 'failed' and failed['response'] == reservation.response
    assert not WeeklyAIUsage.objects.filter(user=user).exists()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize('engine', ['dsh', 'ulr'])
def test_course_receipt_rechecks_original_sources_without_using_quota(auth_client, user, settings, engine):
    from ai_assistant.views import _reserve_chat_request
    from courses.models import Course, TranscriptSegment, VideoTranscript
    from users.learning import confirm_ai_call
    from users.models import CourseStudentStatus, WeeklyAIQuotaConfig

    settings.UNIMIND_LEARNING_RUNTIME = 'ulr'
    settings.UNIMIND_DSH_ENABLED = False
    settings.UNIMIND_CONTENT_INSTITUTION_ID = 'global'
    CourseStudentStatus.objects.create(user=user, is_course_student=True)
    WeeklyAIQuotaConfig.objects.update_or_create(pk=1, defaults={'course_calls': 30})
    bot = Bot.objects.create(name='小宇', is_xiaoyu=True, bot_type='planner')
    conversation = Conversation.objects.create(user=user, bot=bot, conversation_id=uuid4())
    course = Course.objects.create(is_published=True, title='合成来源课程')
    transcript = VideoTranscript.objects.create(course=course, asr_status='completed')
    marker = 'SYNTHETIC_COURSE_RECEIPT'
    segment = TranscriptSegment.objects.create(transcript=transcript, text=marker, start_time=60, end_time=70, index=0)
    card = {'tool': 'search_asr', 'type': 'data_card', 'payload': {'items': [
        {'action_link': f'/course/{course.pk}?t=60', 'value': marker}]}}
    scope = {'user': user, 'bot': bot, 'conversation_id': conversation.conversation_id}
    metadata = {'engine': engine, 'dsh_cards': [card] if engine == 'ulr' else []}
    if engine == 'ulr':
        metadata['ulr_context_sources'] = {'courses': [course.pk], 'transcripts': [[course.pk, transcript.pk, transcript.revision]]}
    else:
        AIChatMessage.objects.create(**scope, role='assistant', content=marker,
            metadata={'engine': 'dsh', 'dsh_cards': [card]})
    answer = AIChatMessage.objects.create(**scope, role='assistant', content=marker, metadata=metadata)
    body = {'bot_id': bot.pk, 'conversation_id': str(conversation.conversation_id),
            'request_id': str(uuid4()), 'message': '复述这段讲稿。'}
    reservation = _reserve_chat_request(user, body, bot, conversation_id=conversation.conversation_id)
    receipt = {'engine': engine, 'done': True, 'message_id': answer.pk, 'full_content': marker,
               'metadata': {key: value for key, value in metadata.items() if key != 'ulr_context_sources'}}
    confirm_ai_call(reservation, response=receipt)
    url = f"/api/ai/chat-requests/{body['request_id']}/"

    async def stream(response):
        return [json.loads(frame[6:]) async for frame in response.streaming_content if frame.startswith(b'data: ')][-1]

    def deny_replay(detail, polling_status):
        recovered = auth_client.get(url).data
        assert recovered['status'] == 'failed' and detail in recovered['response']['full_content']
        polling = auth_client.post('/api/ai/chat/', body, format='json')
        assert polling.status_code == polling_status and detail in str(polling.data)
        final = async_to_sync(stream)(auth_client.post('/api/ai/chat/stream/', body, format='json'))
        assert final['is_error'] and detail in final['full_content']
        assert marker not in str((recovered, polling.data, final))

    with patch('ai_engine.service.AIEngine.call_provider') as model:
        assert auth_client.get(url).data['response'] == receipt
        assert async_to_sync(stream)(auth_client.post('/api/ai/chat/stream/', body, format='json')) == receipt
        VideoTranscript.objects.filter(pk=transcript.pk).update(revision=transcript.revision + 1)
        TranscriptSegment.objects.filter(pk=segment.pk).update(text='新版片段')
        deny_replay('讲稿已更新', 400)
        VideoTranscript.objects.filter(pk=transcript.pk).update(revision=transcript.revision)
        TranscriptSegment.objects.filter(pk=segment.pk).update(text=marker)
        assert auth_client.get(url).data['response'] == receipt
        Course.objects.filter(pk=course.pk).update(is_published=False)
        deny_replay('引用课程已不可访问', 403)
        model.assert_not_called()
    reservation.refresh_from_db()
    assert reservation.status == 'succeeded' and reservation.response == receipt
    assert WeeklyAIUsage.objects.get(user=user).ai_calls == 1
