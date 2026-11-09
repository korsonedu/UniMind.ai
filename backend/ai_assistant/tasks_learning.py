"""Durable, idempotent follow-ups; delivery does not consume a model request."""
from celery import shared_task
from django.db import transaction
from django.utils import timezone
from ai_assistant.models import AIChatMessage, ProjectLearning, ProjectLearningEvent
from notifications.models import Notification
from users.feature_access import has_learning_feature


@shared_task
def send_project_learning_followups():
    now = timezone.now()
    sent = 0
    ids = ProjectLearning.objects.filter(followup_at__lte=now,
        status__in=['active', 'paused']).values_list('pk', flat=True)[:100]
    for pk in list(ids):
        with transaction.atomic():
            state = ProjectLearning.objects.select_for_update().select_related(
                'project__user', 'last_conversation__bot').filter(pk=pk, followup_at__lte=now).first()
            if not state:
                continue
            user = state.project.user
            conversation = state.last_conversation
            if not user.is_active or not has_learning_feature(user, 'ai.assistant'):
                state.followup_at = None
                state.save(update_fields=['followup_at'])
                continue
            if state.status == 'paused':
                if not state.resume_at or state.resume_at > now:
                    continue
                state.status = 'active'
                state.resume_at = None
            if state.status != 'active' or not conversation or conversation.project_id != state.project_id:
                state.followup_at = None
                state.save(update_fields=['followup_at'])
                continue
            text = state.followup_text or state.next_action
            if not text:
                state.followup_at = None
                state.save(update_fields=['followup_at'])
                continue
            event = ProjectLearningEvent.objects.create(project=state.project, kind='followup',
                content={'text': text, 'revision': state.revision, 'notice': '跟进内容，不代表已完成学习。'})
            AIChatMessage.objects.create(user=user, bot=conversation.bot,
                conversation_id=conversation.conversation_id, role='assistant', content=text,
                metadata={'learning_followup': {'project_id': state.project_id, 'event_id': event.pk}})
            Notification.objects.create(recipient=user, ntype='learning_followup', title=f'小宇 · {state.project.name}',
                content=text[:2000], link=f'/xiaoyu?project={state.project_id}&conversation={conversation.conversation_id}')
            conversation.updated_at = now
            conversation.save(update_fields=['updated_at'])
            state.followup_at = None
            state.revision += 1
            state.save(update_fields=['status', 'resume_at', 'followup_at', 'revision', 'updated_at'])
            sent += 1
    return {'sent': sent}
