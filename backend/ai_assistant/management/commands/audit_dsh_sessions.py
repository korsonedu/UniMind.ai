"""Inventory the histories that must survive retirement of the DSH worker."""
from collections import Counter, defaultdict
from datetime import timedelta
import hashlib
from itertools import chain, groupby
import json
from operator import itemgetter
from pathlib import Path
import re
from urllib.parse import urlsplit
from uuid import UUID

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.db.models import Q
from django.db.models.fields.json import KeyTextTransform
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from ai_assistant.models import AIChatMessage, Bot, Conversation, ProjectLearningEvent
from ai_assistant.services.ulr_config import standalone_ulr
from users.learning import AI_RESERVATION_TTL, CHAT_RESERVATION_TTL
from users.models import AIUsageReservation


SESSION_ID = re.compile(r'[0-9a-f]{32}')
HEX_DIGEST = re.compile(r'[0-9a-f]{64}')
MAX_TRANSCRIPT_BYTES = 2 * 1024 * 1024
MIGRATION_BLOCKERS = frozenset({
    'pending_import', 'import_conflict', 'invalid_site_link', 'invalid_ledger_link', 'unreadable_owner',
    'unreadable_file', 'conflict', 'native_file_only', 'unmatched_owners', 'deleted_with_site_history',
    'deleted_with_active_ledger', 'deleted_with_imported_history', 'import_without_source', 'invalid_imported_link',
    'missing_site_receipt', 'invalid_site_receipt', 'duplicate_site_receipt', 'active_chat_requests',
    'active_unpinned_teaching_tasks', 'unsettled_unpinned_exam_grading', 'queued_exam_grading_not_ready',
    'running_unpinned_knowledge_builds',
    'unsettled_legacy_question_pipelines',
    'cross_owner_session', 'running_unpinned_block_assessments', 'state_fingerprint_mismatch', 'database_fingerprint_mismatch',
    'database_restore_fingerprint_mismatch', 'target_runtime_not_ulr',
})


def valid_id(value):
    return isinstance(value, str) and SESSION_ID.fullmatch(value) is not None


def blocked_queued_exam_ids():
    from ai_assistant.services.learning_tasks import task_result_snapshot
    from core.utils import get_content_institution_id
    from quizzes.models import ExamQuestionResult
    from quizzes.services.practice_results import validate_grading_question
    from users.feature_access import has_learning_feature

    pending = ExamQuestionResult.objects.filter(status='pending', exam__requires_ulr=False).filter(
        Q(exam__status='pending') | Q(exam__status='grading', exam__started_at__isnull=True),
    ).select_related('exam__user', 'exam__learning_task__project', 'question__knowledge_point').order_by('exam_id', 'pk')
    blocked = []
    for exam_id, rows in groupby(pending.iterator(), key=lambda item: item.exam_id):
        first = next(rows)
        user = first.exam.user
        task = getattr(first.exam, 'learning_task', None)
        try:
            if not has_learning_feature(user, 'quiz.exam'):
                raise PermissionDenied()
            scope = None if task else get_content_institution_id(user)
            for item in chain((first,), rows):
                if not isinstance(item.question_snapshot, dict):
                    raise ValidationError('原提交快照无法核验。')
                if task:
                    task_result_snapshot(task, item)
                else:
                    question = item.question
                    if not question or question.institution_id != scope:
                        raise ValidationError('题目不存在或不在当前内容范围。')
                    validate_grading_question(question, item.question_snapshot, scope)
        except (PermissionDenied, ValidationError):
            blocked.append(exam_id)
    return blocked


def restored_database_fingerprint():
    if connection.vendor != 'postgresql':
        return None
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT split_part(option, '=', 2)
            FROM pg_db_role_setting AS setting
            JOIN pg_database AS db ON db.oid = setting.setdatabase
            CROSS JOIN LATERAL unnest(setting.setconfig) AS options(option)
            WHERE db.datname = current_database() AND setting.setrole = 0
              AND split_part(option, '=', 1) = 'unimind.restore_sha256'
        """)
        row = cursor.fetchone()
    return row[0] if row and HEX_DIGEST.fullmatch(row[0]) else None


def transcript(value, session_id):
    if not isinstance(value, dict) or value.get('id') != session_id or not isinstance(value.get('messages'), list):
        raise ValueError()
    rows = []
    for index, message in enumerate(value['messages']):
        role = 'assistant' if index % 2 else 'user'
        if not isinstance(message, dict) or message.get('role') != role or not isinstance(message.get('content'), str):
            raise ValueError()
        cards = message.get('cards', []) if role == 'assistant' else []
        if not isinstance(cards, list) or any(not isinstance(card, dict) for card in cards):
            raise ValueError()
        rows.append((role, message['content'], cards))
    if len(rows) % 2:
        raise ValueError()
    return rows


def read_file(directory):
    path = directory / 'transcript.json'
    if directory.is_symlink() or path.is_symlink() or not path.is_file():
        raise ValueError()
    with path.open('rb') as stream:
        raw = stream.read(MAX_TRANSCRIPT_BYTES + 1)
    if len(raw) > MAX_TRANSCRIPT_BYTES:
        raise ValueError()
    return transcript(json.loads(raw), directory.name)


def fingerprint_state(owners, api_url):
    digest = hashlib.sha256(json.dumps(['dsh-transcripts-v1', api_url]).encode())
    total = 0
    for owner_name, owner in sorted(owners.items()):
        if owner.is_symlink() or not owner.is_dir():
            raise ValueError()
        digest.update(b'owner:' + owner_name.encode())
        for directory in sorted(owner.iterdir()):
            if not valid_id(directory.name):
                continue
            path = directory / 'transcript.json'
            if directory.is_symlink() or path.is_symlink() or not directory.is_dir():
                raise ValueError()
            digest.update(b'session:' + directory.name.encode())
            if not path.exists():
                digest.update(b'missing:')
                continue
            if not path.is_file():
                raise ValueError()
            with path.open('rb') as stream:
                digest.update(b'file:' + hashlib.file_digest(stream, 'sha256').digest())
            total += 1
    return {'state_fingerprint': digest.hexdigest(), 'state_owners': len(owners), 'state_transcripts': total}


def prompt_id(answer):
    turn = answer.metadata.get('learning_turn')
    return turn.get('message_id') if isinstance(turn, dict) else None


def cross_owner_sessions(answers, replies, user_id):
    site_claims = answers.filter(metadata__dsh_handoff__isnull=True).order_by().annotate(
        session_key=KeyTextTransform('dsh_session_id', 'metadata'))
    ledger_claims = replies.filter(response__metadata__dsh_handoff__isnull=True).order_by().annotate(
        session_key=KeyTextTransform('session_id', 'response'))
    claims = site_claims.values_list('session_key', 'user_id').union(ledger_claims.values_list('session_key', 'user_id'))
    conflicts = set()
    for session_id, group in groupby(claims.order_by('session_key').iterator(), key=itemgetter(0)):
        if valid_id(session_id):
            owners = {owner_id for _, owner_id in group}
            if len(owners) > 1 and (user_id is None or user_id in owners):
                conflicts.add(session_id)
    return conflicts


def site_histories(user_id, answers, counts):
    prompts = AIChatMessage.objects.filter(user_id=user_id, role='user').in_bulk([
        value for answer in answers if type(value := prompt_id(answer)) is int
    ])
    conversations = {row.conversation_id: row.bot_id for row in Conversation.objects.filter(user_id=user_id,
        conversation_id__in={answer.conversation_id for answer in answers})}
    histories, sessions, previous_answers, invalid = defaultdict(list), {}, {}, set()
    product_prompts = {}
    for answer in answers:
        handoff = answer.metadata.get('dsh_handoff') is True
        session_id = answer.metadata.get('dsh_session_id')
        if (handoff and session_id is not None) or (not handoff and not valid_id(session_id)):
            counts['invalid_site_link'] += 1
            continue
        message_id = prompt_id(answer)
        prompt = prompts.get(message_id) if type(message_id) is int else None
        source = (answer.conversation_id, answer.bot_id)
        cards = answer.metadata.get('dsh_cards', [])
        key = answer.conversation_id if handoff else session_id
        if (not prompt or (prompt.conversation_id, prompt.bot_id) != source or not previous_answers.get(key, 0) < prompt.pk < answer.pk
                or conversations.get(answer.conversation_id) != answer.bot_id or not answer.bot_id
                or sessions.setdefault(key, source) != source or not isinstance(cards, list)):
            if handoff:
                counts['invalid_site_link'] += 1
            else:
                invalid.add(session_id)
            continue
        previous_answers[key] = answer.pk
        if not handoff:
            histories[session_id].extend([('user', prompt.content, []), ('assistant', answer.content, cards)])
        product_prompts[answer.pk] = prompt
    return histories, invalid, product_prompts


def valid_site_receipt(answer, original_prompt, request_id, conversation_id, fingerprint, reply):
    metadata = reply.get('metadata')
    original_request_id = original_prompt.metadata.get('runtime_request_id')
    if not isinstance(metadata, dict) or metadata.get('engine') != 'dsh':
        return False
    user_event = reply['user_message']
    replayed_context = user_event.get('metadata', {})
    if (user_event.get('type', 'user_message') != 'user_message' or not isinstance(replayed_context, dict)
            or replayed_context.get('runtime_request_id', str(request_id)) != str(request_id)):
        return False
    for field in ('course_context', 'note_attachments', 'note_selection', 'learning_activity'):
        if field in replayed_context and replayed_context[field] != original_prompt.metadata.get(field):
            return False
    external_video = original_prompt.metadata.get('external_video_context')
    if any(payload.get('external_video_context') != external_video
           for payload in (replayed_context, metadata, answer.metadata)):
        return False
    if answer.metadata.get('dsh_handoff') is True:
        if (metadata.get('dsh_handoff') is not True or metadata.get('dsh_session_id') is not None
                or conversation_id != answer.conversation_id or original_request_id != str(request_id)):
            return False
    elif metadata.get('dsh_session_id') != reply['session_id']:
        return False
    return (reply.get('done') is True and not reply.get('is_error')
            and HEX_DIGEST.fullmatch(fingerprint) is not None
            and reply.get('request_id', str(request_id)) == str(request_id)
            and (conversation_id is None or conversation_id == answer.conversation_id)
            and reply.get('conversation_id', str(answer.conversation_id)) == str(answer.conversation_id)
            and (original_request_id is None or original_request_id == str(request_id))
            and metadata.get('dsh_cards', []) == answer.metadata.get('dsh_cards', [])
            and metadata.get('course_context') == answer.metadata.get('course_context'))


def imported_state(user_id, bot, session_id, rows):
    conversation_id = UUID(hex=session_id)
    messages = AIChatMessage.objects.filter(conversation_id=conversation_id)
    existing = Conversation.objects.filter(conversation_id=conversation_id).first()
    if not existing:
        return 'import_conflict' if messages.exists() else 'pending_import'
    if existing.user_id != user_id or existing.bot_id != bot.pk or messages.exclude(user_id=user_id, bot=bot).exists():
        return 'import_conflict'
    prefix = list(messages.order_by('timestamp', 'pk').values_list('role', 'content', 'metadata')[:len(rows)])
    if len(prefix) != len(rows):
        return 'import_conflict'
    for (role, content, metadata), (expected_role, expected_content, cards) in zip(prefix, rows):
        if (role, content) != (expected_role, expected_content):
            return 'import_conflict'
        if role == 'assistant' and (metadata.get('engine') != 'dsh_import'
                or metadata.get('dsh_imported_session_id') != session_id or metadata.get('dsh_cards', []) != cards):
            return 'import_conflict'
    if messages.filter(metadata__engine='dsh_import').count() != len(rows) // 2:
        return 'import_conflict'
    return 'already_imported'


def import_history(user_id, bot, session_id, rows, completed_at):
    state = imported_state(user_id, bot, session_id, rows)
    if state != 'pending_import':
        return state

    conversation_id = UUID(hex=session_id)
    conversation, created = Conversation.objects.get_or_create(conversation_id=conversation_id, defaults={
        'user_id': user_id, 'bot': bot, 'title': rows[0][1][:60].strip() or '新会话',
    })
    if not created:
        return 'import_conflict'
    messages = AIChatMessage.objects.bulk_create([
        AIChatMessage(user_id=user_id, bot=bot, conversation_id=conversation_id, role=role, content=content,
            metadata={'engine': 'dsh_import', 'dsh_imported_session_id': session_id, 'dsh_cards': cards}
            if role == 'assistant' else {})
        for role, content, cards in rows
    ])
    for index, message in enumerate(messages, start=1):
        message.timestamp = completed_at - timedelta(microseconds=len(messages) - index)
    AIChatMessage.objects.bulk_update(messages, ['timestamp'])
    Conversation.objects.filter(pk=conversation.pk).update(created_at=messages[0].timestamp, updated_at=completed_at)
    return 'imported'


def audit_owner(user_id, owner, answers, replies, imported, conflicts, counts, target_bot, *, write=False):
    site, invalid, product_prompts = site_histories(user_id, answers, counts)
    by_id = {answer.pk: answer for answer in answers}
    native, completed_at, deleted, links = {}, {}, set(), set()
    seen_receipts = set()
    for request_id, conversation_id, fingerprint, reply, timestamp in replies:
        metadata = reply.get('metadata')
        handoff = isinstance(metadata, dict) and metadata.get('dsh_handoff') is True
        session_id = reply.get('session_id')
        if (handoff and session_id is not None) or (not handoff and not valid_id(session_id)):
            counts['invalid_ledger_link'] += 1
            continue
        if reply.get('deleted') is True:
            if not handoff:
                deleted.add(session_id)
        elif handoff or 'message_id' in reply:
            if not handoff:
                links.add(session_id)
            message_id = reply.get('message_id')
            answer = by_id.get(message_id) if type(message_id) is int else None
            prompt = reply.get('user_message')
            if (not answer or (answer.metadata.get('dsh_handoff') is True) != handoff
                    or answer.metadata.get('dsh_session_id') != session_id
                    or answer.content != reply.get('full_content') or not isinstance(prompt, dict)
                    or type(prompt.get('message_id')) is not int
                    or prompt.get('message_id') != prompt_id(answer)):
                if handoff:
                    counts['invalid_site_receipt'] += 1
                else:
                    invalid.add(session_id)
            elif original_prompt := product_prompts.get(message_id):
                duplicate = message_id in seen_receipts
                if duplicate:
                    counts['duplicate_site_receipt'] += 1
                seen_receipts.add(message_id)
                if not valid_site_receipt(answer, original_prompt, request_id, conversation_id, fingerprint, reply):
                    counts['invalid_site_receipt'] += 1
                elif handoff and not duplicate:
                    counts['handoff_receipts_verified'] += 1
        else:
            try:
                if reply.get('finish_reason') != 'completed' or reply.get('request_id', str(request_id)) != str(request_id):
                    raise ValueError()
                rows = transcript(reply.get('session'), session_id)
                if not rows or rows[-1][1] != reply.get('content'):
                    raise ValueError()
                previous = native.get(session_id, [])
                common = min(len(previous), len(rows))
                if rows[:common] != previous[:common]:
                    raise ValueError()
            except ValueError:
                invalid.add(session_id)
            else:
                native[session_id] = max(previous, rows, key=len)
                completed_at[session_id] = max(completed_at.get(session_id, timestamp), timestamp)

    if missing := product_prompts.keys() - seen_receipts:
        counts['missing_site_receipt'] += len(missing)

    valid_imports, invalid_imports = set(), set()
    for session_id, conversation_id, bot_id, role, engine in imported.order_by().values_list(
            'metadata__dsh_imported_session_id', 'conversation_id', 'bot_id', 'role', 'metadata__engine').distinct():
        if (not valid_id(session_id) or UUID(hex=session_id) != conversation_id or role != 'assistant'
                or engine != 'dsh_import' or (target_bot and bot_id != target_bot.pk)):
            counts['invalid_imported_link'] += 1
            if valid_id(session_id):
                invalid_imports.add(session_id)
        else:
            valid_imports.add(session_id)
    if missing_sources := valid_imports - native.keys() - deleted - invalid - conflicts:
        counts['import_without_source'] += len(missing_sources)

    try:
        if owner and owner.is_symlink():
            raise ValueError()
        files = {item.name: item for item in owner.iterdir() if valid_id(item.name)} if owner else {}
    except (OSError, ValueError):
        counts['unreadable_owner'] += 1
        return
    for session_id in (site.keys() | native.keys() | files.keys() | deleted | invalid | links) - conflicts:
        path = files.get(session_id)
        if session_id in deleted:
            counts['deleted_with_file' if path else 'deleted'] += 1
            if session_id in site:
                counts['deleted_with_site_history'] += 1
            if session_id in native or session_id in links:
                counts['deleted_with_active_ledger'] += 1
            if session_id in valid_imports:
                counts['deleted_with_imported_history'] += 1
            continue
        try:
            rows = read_file(path) if path else None
        except (OSError, ValueError, RecursionError):
            counts['unreadable_file'] += 1
            continue
        if session_id in invalid or (session_id in links and session_id not in site) or (session_id in site and session_id in native):
            counts['conflict'] += 1
        elif session_id in site:
            counts['site_history_only' if rows is None else 'site_matched' if rows == site[session_id] else 'conflict'] += 1
        elif session_id in native:
            if rows is not None and rows != native[session_id]:
                counts['conflict'] += 1
                continue
            counts['native_ledger_only' if rows is None else 'native_matched'] += 1
            if session_id in invalid_imports:
                continue
            if write:
                counts[import_history(user_id, target_bot, session_id, native[session_id], completed_at[session_id])] += 1
            elif target_bot:
                counts[imported_state(user_id, target_bot, session_id, native[session_id])] += 1
        else:
            counts['native_file_only' if rows else 'empty_native_session'] += 1


class Command(BaseCommand):
    help = 'Inventory DSH histories. Optionally import verified standalone histories into XiaoYu.'

    def add_arguments(self, parser):
        parser.add_argument('--state-dir', default=settings.UNIMIND_DSH_STATE_DIR)
        parser.add_argument('--api-url', default=settings.UNIMIND_DSH_API_URL)
        parser.add_argument('--user-id', type=int)
        parser.add_argument('--import-verified', action='store_true')
        parser.add_argument('--require-migrated', action='store_true',
                            help='Fail if the full read-only audit finds unresolved histories or running legacy work.')
        parser.add_argument('--state-fingerprint', action='store_true', help='Record the full source state fingerprint.')
        parser.add_argument('--expected-state-fingerprint', help='Verify the source state fingerprint at the migration gate.')
        parser.add_argument('--database-backup', help='Fingerprint the database backup paired with the source state.')
        parser.add_argument('--expected-database-fingerprint', help='Verify the paired database backup at the migration gate.')

    def handle(self, *args, **options):
        root = Path(options['state_dir'])
        api_url = options['api_url']
        parsed = urlsplit(api_url)
        if not root.is_absolute() or not root.is_dir() or parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost', '::1'):
            raise CommandError('需要绝对路径的 DSH 状态目录和该目录原先使用的本机 API 地址。')
        write, gate = options['import_verified'], options['require_migrated']
        if gate and (write or options['user_id'] is not None):
            raise CommandError('迁移验收须对完整快照执行只读盘点。')
        expected_state = options['expected_state_fingerprint']
        record_state = options['state_fingerprint']
        if expected_state is not None and (not gate or not HEX_DIGEST.fullmatch(expected_state)):
            raise CommandError('请在全量迁移验收中提供源快照的 SHA-256 指纹。')
        if record_state and (write or options['user_id'] is not None):
            raise CommandError('状态快照指纹须对完整目录只读记录。')
        database_backup = options['database_backup']
        expected_database = options['expected_database_fingerprint']
        if expected_database is not None and (
                not database_backup or expected_state is None or not HEX_DIGEST.fullmatch(expected_database)):
            raise CommandError('验证数据库备份须提供配对的源状态指纹和数据库 SHA-256 指纹。')
        if database_backup is not None and not (expected_database if gate else record_state):
            raise CommandError('数据库备份须与状态目录一并记录或核对。')
        target_bot = None
        if write or gate:
            if settings.UNIMIND_DSH_ENABLED:
                raise CommandError('请在停止 DSH 后导入，避免旧会话在导入期间继续写入。')
            try:
                target_bot = Bot.objects.get(is_xiaoyu=True, is_active=True)
            except (Bot.DoesNotExist, Bot.MultipleObjectsReturned):
                raise CommandError('需要一个启用中的平台小宇。') from None
        users = get_user_model().objects.all()
        if options['user_id'] is not None:
            users = users.filter(pk=options['user_id'])
            if not users.exists():
                raise CommandError('指定的账号不存在。')
        owners = {entry.name: entry for entry in root.iterdir() if HEX_DIGEST.fullmatch(entry.name)}
        report, counts = {}, Counter()
        if record_state or expected_state is not None:
            try:
                report.update(fingerprint_state(owners, api_url))
            except (OSError, ValueError):
                raise CommandError('源状态快照包含无法读取的会话文件。') from None
            if expected_state is not None:
                report['state_fingerprint_verified'] = report['state_fingerprint'] == expected_state
                if not report['state_fingerprint_verified']:
                    counts['state_fingerprint_mismatch'] = 1
        if database_backup is not None:
            path = Path(database_backup)
            try:
                if not path.is_file():
                    raise OSError()
                with path.open('rb') as stream:
                    report['database_fingerprint'] = hashlib.file_digest(stream, 'sha256').hexdigest()
            except OSError:
                raise CommandError('无法读取配对的数据库备份文件。') from None
            if expected_database is not None:
                verified = report['database_fingerprint'] == expected_database
                report['database_fingerprint_verified'] = verified
                report['snapshot_pair_verified'] = report['state_fingerprint_verified'] and verified
                report['database_restore_fingerprint'] = restored_database_fingerprint()
                report['database_restore_verified'] = report['database_restore_fingerprint'] == expected_database
                report['target_runtime'] = settings.UNIMIND_LEARNING_RUNTIME
                if not standalone_ulr():
                    counts['target_runtime_not_ulr'] = 1
                if not report['database_restore_verified']:
                    counts['database_restore_fingerprint_mismatch'] = 1
                if not verified:
                    counts['database_fingerprint_mismatch'] = 1
        answers = AIChatMessage.objects.filter(role='assistant', metadata__engine='dsh')
        replies = AIUsageReservation.objects.filter(status='succeeded', response__engine='dsh')
        imported = AIChatMessage.objects.filter(Q(metadata__engine='dsh_import') |
                                               Q(metadata__has_key='dsh_imported_session_id'))
        conflicts = cross_owner_sessions(answers, replies, options['user_id'])
        linked_users = set(answers.order_by().values_list('user_id', flat=True).distinct())
        linked_users.update(replies.order_by().values_list('user_id', flat=True).distinct())
        linked_users.update(imported.order_by().values_list('user_id', flat=True).distinct())
        if conflicts:
            counts['cross_owner_session'] = len(conflicts)
        for user_id in users.values_list('pk', flat=True).iterator():
            digest = hashlib.sha256(json.dumps([api_url, user_id]).encode()).hexdigest()
            owner = owners.pop(digest, None)
            if owner or user_id in linked_users:
                owned_answers = list(answers.filter(user_id=user_id).order_by('pk'))
                owned_replies = replies.filter(user_id=user_id).order_by('pk').values_list(
                    'request_id', 'conversation_id', 'fingerprint', 'response', 'updated_at')
                owned_imports = imported.filter(user_id=user_id)
                if write:
                    with transaction.atomic():
                        audit_owner(user_id, owner, owned_answers, owned_replies.select_for_update(), owned_imports,
                                    conflicts, counts, target_bot, write=True)
                else:
                    audit_owner(user_id, owner, owned_answers, owned_replies.iterator(), owned_imports,
                                conflicts, counts, target_bot)
        if options['user_id'] is None:
            counts['unmatched_owners'] = len(owners)
        if gate:
            from backoffice.tasks import TEACHING_JOB_KINDS, TEACHING_JOB_TIMEOUT
            from knowledge_builder.models import KnowledgeTreeBuild
            from quizzes.models import ContentPipelineTask, QuizExam

            now = timezone.now()
            active = AIUsageReservation.objects.filter(status='pending').filter(
                Q(conversation_id__isnull=False, updated_at__gte=now - CHAT_RESERVATION_TTL) |
                Q(conversation_id__isnull=True, updated_at__gte=now - AI_RESERVATION_TTL)).count()
            if active:
                counts['active_chat_requests'] = active
            active_teaching = list(ContentPipelineTask.objects.filter(
                status='running', started_at__gte=now - TEACHING_JOB_TIMEOUT, payload__kind__in=TEACHING_JOB_KINDS,
            ).filter(Q(payload__requires_ulr__isnull=True) | Q(payload__requires_ulr=False))
                .order_by('pk').values_list('pk', flat=True))
            if active_teaching:
                counts['active_unpinned_teaching_tasks'] = len(active_teaching)
                report['active_teaching_task_ids'] = active_teaching
            # The older ARC and bulk entry points mark a job running before queueing it and never set kind.
            question_pipelines = list(ContentPipelineTask.objects.filter(
                task_type='ai_generate', status='running', payload__kind__isnull=True,
            ).filter(Q(payload__bulk_mode=True) | Q(payload__has_keys=['kp_ids', 'questions_per_kp']))
                .filter(Q(payload__requires_ulr__isnull=True) | ~Q(payload__requires_ulr=True))
                .order_by('pk').values_list('pk', flat=True))
            if question_pipelines:
                counts['unsettled_legacy_question_pipelines'] = len(question_pipelines)
                report['unsettled_question_pipeline_ids'] = question_pipelines
            # A requeued exam has no start time. Keep old started attempts visible until recovery or settlement.
            unsettled_grading = list(QuizExam.objects.filter(status='grading', requires_ulr=False, started_at__isnull=False)
                .order_by('pk').values_list('pk', flat=True))
            if unsettled_grading:
                counts['unsettled_unpinned_exam_grading'] = len(unsettled_grading)
                report['unsettled_exam_ids'] = unsettled_grading
            if blocked_exams := blocked_queued_exam_ids():
                counts['queued_exam_grading_not_ready'] = len(blocked_exams)
                report['blocked_queued_exam_ids'] = blocked_exams
            running_builds = list(KnowledgeTreeBuild.objects.filter(
                status=KnowledgeTreeBuild.Status.RUNNING, requires_ulr=False,
            ).order_by('pk').values_list('pk', flat=True))
            if running_builds:
                counts['running_unpinned_knowledge_builds'] = len(running_builds)
                report['running_knowledge_build_ids'] = [str(pk) for pk in running_builds]
            preparations = list(ProjectLearningEvent.objects.filter(kind='block_prepare', content__status='running')
                .filter(Q(content__requires_ulr__isnull=True) | Q(content__requires_ulr=False))
                .order_by('pk').values_list('pk', flat=True))
            if preparations:
                counts['running_unpinned_block_assessments'] = len(preparations)
                report['unsettled_block_preparation_ids'] = preparations
        report.update(counts)
        if gate:
            blockers = {key: counts[key] for key in MIGRATION_BLOCKERS if counts[key]}
            report.update(migrated=not blockers, blockers=blockers)
        self.stdout.write(json.dumps(report, sort_keys=True))
        if gate and blockers:
            raise CommandError('DSH 退役盘点存在未完成的迁移项。')
