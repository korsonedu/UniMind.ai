"""Synthetic-user smoke: status recovery never executes or consumes quota."""
from datetime import timedelta
from uuid import uuid4

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from ai_assistant.models import AIChatMessage, Bot
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
