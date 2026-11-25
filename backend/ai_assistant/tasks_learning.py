"""Durable, idempotent follow-ups; delivery does not consume a model request."""
from celery import shared_task
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from ai_assistant.models import AIChatMessage, Conversation, ProjectLearning, ProjectLearningEvent, chat_receipt_deleted
from .services.ulr_config import ulr_enabled
from notifications.models import Notification
from users.feature_access import has_learning_feature
from users.learning import CHAT_RESERVATION_TTL


@shared_task
def send_project_learning_followups():
    now = timezone.now()
    sent = 0
    # Timed pauses still expire when notifications are muted.
    ProjectLearning.objects.filter(status='paused', planning_enabled=True, reminders_enabled=False,
        resume_at__lte=now).update(status='active', resume_at=None, revision=F('revision') + 1)
    due = ProjectLearning.objects.filter(planning_enabled=True, reminders_enabled=True, followup_at__lte=now,
        status__in=['active', 'paused', 'completed']).values_list('pk', 'last_conversation_id')[:100]
    for pk, conversation_pk in list(due):
        with transaction.atomic():
            # A XiaoYu turn acquires the conversation before the project state.
            conversation = None
            if conversation_pk is not None:
                conversation = Conversation.objects.select_for_update(of=('self',)).select_related('bot').filter(pk=conversation_pk).first()
            state = ProjectLearning.objects.select_for_update(of=('self',)).select_related('project__user').filter(
                pk=pk, last_conversation_id=conversation_pk, planning_enabled=True, reminders_enabled=True,
                followup_at__lte=now).first()
            if not state:
                continue
            user = state.project.user
            if not user.is_active or not has_learning_feature(user, 'ai.assistant'):
                state.followup_at = None
                state.save(update_fields=['followup_at'])
                continue
            if state.status == 'paused':
                if not state.resume_at or state.resume_at > now:
                    continue
                state.status = 'active'
                state.resume_at = None
            if state.status not in ('active', 'completed') or not conversation or conversation.project_id != state.project_id:
                state.followup_at = None
                state.save(update_fields=['followup_at'])
                continue
            if ulr_enabled():
                from .services.project_learning import model_event_reservation, unconfirmed_progress_ids
                source = state.project.learning_events.filter(kind__in=(
                    'plan', 'progress', 'pause', 'resume', 'complete', 'schedule', 'accept', 'reminders',
                )).exclude(kind='plan', content__has_key='proposed_plan').exclude(
                    kind='progress', content__has_key='mainline', content__mainline=False).select_related('message').first()
                requires_receipt, receipt = model_event_reservation(source)
                if receipt and receipt.status == 'pending' and receipt.updated_at >= now - CHAT_RESERVATION_TTL:
                    continue
                unverified_receipt = requires_receipt and (
                    not receipt or receipt.status != 'succeeded' or chat_receipt_deleted(receipt))
                if unverified_receipt or (source and source.kind == 'progress'
                        and source.pk in unconfirmed_progress_ids(user.pk, state.project_id)):
                    state.followup_at = None
                    state.followup_text = ''
                    state.revision += 1
                    state.save(update_fields=['status', 'resume_at', 'followup_at', 'followup_text', 'revision', 'updated_at'])
                    continue
            from .services.language import message_language
            latest_question = AIChatMessage.objects.filter(user=user, conversation_id=conversation.conversation_id, bot_id=conversation.bot_id, role='user').order_by('-id').first()
            english = bool(latest_question and message_language(latest_question) == 'en')
            text = state.followup_text or state.next_action
            if state.followup_text == state.next_action and state.project.learning_tasks.exists():
                from .services.project_learning import learning_data
                text = learning_data(state.project, language='en' if english else 'zh-CN')['followup_text']
            if not text:
                state.followup_at = None
                state.save(update_fields=['followup_at'])
                continue
            event = ProjectLearningEvent.objects.create(project=state.project, kind='followup',
                content={'text': text, 'revision': state.revision, 'notice': 'Learning follow-up; does not indicate completed learning.' if english else '跟进内容，不代表已完成学习。'})
            message = AIChatMessage.objects.create(user=user, bot=conversation.bot,
                conversation_id=conversation.conversation_id, role='assistant', content=text,
                metadata={'learning_followup': {'project_id': state.project_id, 'event_id': event.pk}})
            notification = Notification.objects.create(recipient=user, ntype='learning_followup', title=f'XiaoYu · {state.project.name}' if english else f'小宇 · {state.project.name}',
                content=text[:2000], link=f'/xiaoyu?project={state.project_id}&conversation={conversation.conversation_id}')
            event.content.update(message_id=message.pk, notification_id=notification.pk)
            event.save(update_fields=['content'])
            conversation.updated_at = now
            conversation.save(update_fields=['updated_at'])
            state.followup_at = None
            state.revision += 1
            state.save(update_fields=['status', 'resume_at', 'followup_at', 'revision', 'updated_at'])
            sent += 1
    return {'sent': sent}
