import json
import uuid
from pathlib import Path
from datetime import timedelta
from hashlib import blake2b

from celery import shared_task
from django.db import connection, transaction
from django.conf import settings as django_settings
from django.utils import timezone

from ai_assistant.services.ulr_config import standalone_ulr
from .awareness import content_signature, enqueue, schedule_note, xiaoyu_bot
from .models import Note, NoteAISettings, NoteUnderstanding


FIELDS = ('topics', 'explanations', 'questions')
ITEM_SCHEMA = {'type': 'object', 'required': ['text', 'evidence'], 'additionalProperties': False, 'properties': {
    'text': {'type': 'string', 'minLength': 1, 'maxLength': 300},
    'evidence': {'type': 'string', 'minLength': 1, 'maxLength': 500},
}}
UNDERSTANDING_SCHEMA = {'type': 'object', 'required': list(FIELDS), 'additionalProperties': False,
    'properties': {field: {'type': 'array', 'items': ITEM_SCHEMA, 'maxItems': 8} for field in FIELDS}}
# A plain UUID may belong to a worker that started before advisory locking.
LOCKED_RUN_PREFIX = 'pg:'


def validated_result(raw, text):
    if not isinstance(raw, str) or len(raw) > 14000:
        raise ValueError('Invalid note understanding size')
    result = json.loads(raw)
    if not isinstance(result, dict) or set(result) != set(FIELDS):
        raise ValueError('Invalid note understanding fields')
    for items in result.values():
        if not isinstance(items, list) or len(items) > 8:
            raise ValueError('Invalid note understanding list')
        for item in items:
            if (not isinstance(item, dict) or set(item) != {'text', 'evidence'}
                    or not isinstance(item['text'], str) or not 1 <= len(item['text']) <= 300
                    or not isinstance(item['evidence'], str) or not 1 <= len(item['evidence']) <= 500
                    or item['evidence'] not in text):
                raise ValueError('Note understanding lacks original evidence')
    return result


@shared_task(soft_time_limit=60, time_limit=90)
def understand_user_notes(user_id, epoch, after_id=0):
    settings = NoteAISettings.objects.filter(user_id=user_id, enabled=True, epoch=epoch).select_related('user').first()
    if not settings or not xiaoyu_bot(settings.user):
        return
    notes = list(Note.objects.filter(user_id=user_id, deleted_at__isnull=True, pk__gt=after_id).order_by('pk')[:50])
    for note in notes:
        schedule_note(note)
    if len(notes) == 50:
        enqueue(understand_user_notes, user_id, epoch, notes[-1].pk, countdown=20)


def current_locked(note_id, version, epoch, signature):
    note = Note.objects.select_for_update().filter(pk=note_id, version=version, deleted_at__isnull=True).select_related('user').first()
    if not note or content_signature(note) != signature:
        return None
    settings = NoteAISettings.objects.select_for_update().filter(user_id=note.user_id, enabled=True, epoch=epoch).first()
    if not settings or not xiaoyu_bot(note.user):
        return None
    understanding = NoteUnderstanding.objects.select_for_update().filter(note=note, version=version, epoch=epoch, signature=signature).first()
    return (note, understanding) if understanding else None


@shared_task(bind=True, max_retries=2, soft_time_limit=150, time_limit=180, acks_late=True)
def understand_note(self, note_id, version, epoch, signature):
    if not standalone_ulr() or connection.vendor != 'postgresql':
        return _understand_note(self, note_id, version, epoch, signature, locked=False)
    digest = blake2b(f'{note_id}:{version}:{epoch}'.encode(), digest_size=8, person=b'note-understand').digest()
    key = int.from_bytes(digest, 'big', signed=True)
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_try_advisory_lock(%s)', [key])
        if not cursor.fetchone()[0]:
            if not (self.request.delivery_info or {}).get('redelivered'):
                return
            cursor.execute('SELECT pg_advisory_lock(%s)', [key])
    try:
        return _understand_note(self, note_id, version, epoch, signature, locked=True)
    finally:
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_unlock(%s)', [key])


def _understand_note(task, note_id, version, epoch, signature, *, locked):
    run_id = LOCKED_RUN_PREFIX + uuid.uuid4().hex if locked else str(uuid.uuid4())
    with transaction.atomic():
        current = current_locked(note_id, version, epoch, signature)
        if not current:
            return
        note, understanding = current
        if understanding.status in ('ready', 'invalid'):
            return
        if (understanding.status == 'processing' and understanding.started_at
                and not (locked and understanding.run_id.startswith(LOCKED_RUN_PREFIX))
                and understanding.started_at > timezone.now() - timedelta(minutes=4)):
            return
        if understanding.attempts >= 3:
            if understanding.status == 'processing':
                understanding.status = 'failed'
                understanding.save(update_fields=['status'])
            return
        understanding.status, understanding.run_id = 'processing', run_id
        understanding.started_at = timezone.now()
        understanding.attempts += 1
        understanding.save()
        text = (note.title + '\n' + note.content)[:12000]
    try:
        instruction = (Path(django_settings.BASE_DIR) / 'prompts/notes/understanding_system.txt').read_text().replace(
            '{language}', 'English' if note.user.preferred_language == 'en' else '简体中文')
        if standalone_ulr():
            from ai_assistant.services.ulr_structured import run_collector
            output = run_collector(text, instruction=instruction + '请调用 submit_note_understanding 提交结果。',
                operation='notes.understanding',
                name='submit_note_understanding', schema=UNDERSTANDING_SCHEMA, max_tokens=2500, temperature=0)
            raw = json.dumps(output, ensure_ascii=False)
        else:
            from ai_engine.service import AIEngine
            response = AIEngine.call_ai(
                messages=[{'role': 'system', 'content': instruction + '只返回 JSON 对象。'},
                          {'role': 'user', 'content': text}],
                temperature=0, max_tokens=2500, raise_on_error=True, operation='notes.understanding',
                _response_format={'type': 'json_object'},
            )
            raw = AIEngine._extract_content(response)
        result = validated_result(raw, text)
    except Exception as error:
        with transaction.atomic():
            current = current_locked(note_id, version, epoch, signature)
            if not current or current[1].run_id != run_id:
                return
            understanding = current[1]
            understanding.status = 'failed'
            understanding.save(update_fields=['status'])
        raise task.retry(exc=error, countdown=60)
    with transaction.atomic():
        current = current_locked(note_id, version, epoch, signature)
        if not current or current[1].run_id != run_id:
            return
        understanding = current[1]
        understanding.result, understanding.status = result, 'ready'
        understanding.save(update_fields=['result', 'status'])
