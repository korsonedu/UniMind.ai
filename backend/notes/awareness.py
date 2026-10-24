"""Private derived learning clues; never write the student's note or shared memory."""
import hashlib
import logging

from django.db import transaction
from django.http import Http404
from rest_framework.exceptions import NotFound, PermissionDenied

from .access import accessible_bot
from .models import Note, NoteAISettings, NoteUnderstanding

logger = logging.getLogger(__name__)


def xiaoyu_bot(user, bot=None):
    from ai_assistant.models import Bot
    canonical = Bot.objects.filter(name='小宇', bot_type='planner', institution__isnull=True, is_active=True).order_by('pk').first()
    if canonical is None or (bot is not None and bot.pk != canonical.pk):
        return None
    try:
        return accessible_bot(user, canonical.pk)
    except (PermissionDenied, NotFound, Http404):
        return None


def content_signature(note):
    return hashlib.sha256((note.title + '\0' + note.content).encode()).hexdigest()


def enqueue(task, *args, **kwargs):
    # Broker outages must not roll back a student's successful save.
    try:
        task.apply_async(args=args, retry=False, **kwargs)
    except Exception:
        logger.exception('Unable to queue private note understanding')


def schedule_note(note):
    settings = NoteAISettings.objects.filter(user_id=note.user_id, enabled=True).first()
    if not settings or note.deleted_at:
        NoteUnderstanding.objects.filter(note=note).update(status='invalid', result={})
        return
    with transaction.atomic():
        # All derived-state writers lock the note first, then settings, then result.
        note = Note.objects.select_for_update().get(pk=note.pk)
        settings = NoteAISettings.objects.select_for_update().get(pk=settings.pk)
        if not settings.enabled or note.deleted_at:
            return
        signature = content_signature(note)
        understanding, _ = NoteUnderstanding.objects.select_for_update().get_or_create(
            note=note, defaults={'version': note.version, 'epoch': settings.epoch, 'signature': signature})
        if (understanding.signature == signature and understanding.epoch == settings.epoch
                and understanding.status == 'ready'):
            understanding.version = note.version
            understanding.save(update_fields=['version'])
            return
        if understanding.version != note.version or understanding.epoch != settings.epoch or understanding.signature != signature:
            understanding.version, understanding.epoch, understanding.signature = note.version, settings.epoch, signature
            understanding.status, understanding.result, understanding.attempts, understanding.run_id = 'pending', {}, 0, ''
            understanding.save()
        from .tasks import understand_note
        transaction.on_commit(lambda: enqueue(understand_note, note.pk, note.version, settings.epoch, signature, countdown=20))


def after_note_save(note):
    def run():
        try:
            schedule_note(note)
        except Exception:
            logger.exception('Unable to prepare private note understanding')
    transaction.on_commit(run)


def note_message_metadata(context, sources, selection=''):
    if not context:
        return {}
    return {
        'notes_context_used': True,
        'note_selection': selection,
        'note_attachments': [{'note_id': source['note_id'], 'title': source['title'], 'version': source['version']}
                             for source in sources if source['kind'] == 'temporary'],
    }
