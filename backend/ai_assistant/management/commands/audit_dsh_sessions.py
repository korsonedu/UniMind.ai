"""Inventory the histories that must survive retirement of the DSH worker."""
from collections import Counter, defaultdict
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
from uuid import UUID

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from ai_assistant.models import AIChatMessage, Bot, Conversation
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
    'active_unpinned_teaching_tasks', 'running_unpinned_knowledge_builds',
})


def valid_id(value):
    return isinstance(value, str) and SESSION_ID.fullmatch(value) is not None


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


def prompt_id(answer):
    turn = answer.metadata.get('learning_turn')
    return turn.get('message_id') if isinstance(turn, dict) else None


def site_histories(user_id, answers, counts):
    prompts = AIChatMessage.objects.filter(user_id=user_id, role='user').in_bulk([
        value for answer in answers if type(value := prompt_id(answer)) is int
    ])
    conversations = {row.conversation_id: row.bot_id for row in Conversation.objects.filter(user_id=user_id,
        conversation_id__in={answer.conversation_id for answer in answers})}
    histories, sessions, previous_answers, invalid = defaultdict(list), {}, {}, set()
    product_prompts = {}
    for answer in answers:
        session_id = answer.metadata.get('dsh_session_id')
        if not valid_id(session_id):
            counts['invalid_site_link'] += 1
            continue
        message_id = prompt_id(answer)
        prompt = prompts.get(message_id) if type(message_id) is int else None
        source = (answer.conversation_id, answer.bot_id)
        cards = answer.metadata.get('dsh_cards', [])
        if (not prompt or (prompt.conversation_id, prompt.bot_id) != source or not previous_answers.get(session_id, 0) < prompt.pk < answer.pk
                or conversations.get(answer.conversation_id) != answer.bot_id or not answer.bot_id
                or sessions.setdefault(session_id, source) != source or not isinstance(cards, list)):
            invalid.add(session_id)
        else:
            previous_answers[session_id] = answer.pk
            histories[session_id].extend([('user', prompt.content, []), ('assistant', answer.content, cards)])
            product_prompts[answer.pk] = prompt
    return histories, invalid, product_prompts


def valid_site_receipt(answer, original_prompt, request_id, conversation_id, fingerprint, reply):
    metadata = reply.get('metadata')
    original_request_id = original_prompt.metadata.get('runtime_request_id')
    return (reply.get('done') is True and not reply.get('is_error')
            and HEX_DIGEST.fullmatch(fingerprint) is not None
            and (conversation_id is None or conversation_id == answer.conversation_id)
            and reply.get('conversation_id', str(answer.conversation_id)) == str(answer.conversation_id)
            and (original_request_id is None or original_request_id == str(request_id))
            and isinstance(metadata, dict) and metadata.get('engine') == 'dsh'
            and metadata.get('dsh_session_id') == reply['session_id']
            and metadata.get('dsh_cards', []) == answer.metadata.get('dsh_cards', []))


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


def audit_owner(user_id, owner, answers, replies, counts, target_bot, *, write=False):
    site, invalid, product_prompts = site_histories(user_id, answers, counts)
    by_id = {answer.pk: answer for answer in answers}
    native, completed_at, deleted, links = {}, {}, set(), set()
    seen_receipts = set()
    for request_id, conversation_id, fingerprint, reply, timestamp in replies:
        session_id = reply.get('session_id')
        if not valid_id(session_id):
            counts['invalid_ledger_link'] += 1
            continue
        if reply.get('deleted') is True:
            deleted.add(session_id)
        elif 'message_id' in reply:
            links.add(session_id)
            message_id = reply['message_id']
            answer = by_id.get(message_id) if type(message_id) is int else None
            prompt = reply.get('user_message')
            if (not answer or answer.metadata.get('dsh_session_id') != session_id
                    or answer.content != reply.get('full_content') or not isinstance(prompt, dict)
                    or type(prompt.get('message_id')) is not int
                    or prompt.get('message_id') != prompt_id(answer)):
                invalid.add(session_id)
            elif original_prompt := product_prompts.get(message_id):
                if message_id in seen_receipts:
                    counts['duplicate_site_receipt'] += 1
                seen_receipts.add(message_id)
                if not valid_site_receipt(answer, original_prompt, request_id, conversation_id, fingerprint, reply):
                    counts['invalid_site_receipt'] += 1
        else:
            try:
                if reply.get('finish_reason') != 'completed':
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

    imported_ids = AIChatMessage.objects.filter(user_id=user_id, role='assistant', metadata__engine='dsh_import')
    for session_id in imported_ids.order_by().values_list('metadata__dsh_imported_session_id', flat=True).distinct():
        if not valid_id(session_id):
            counts['invalid_imported_link'] += 1
        elif session_id not in native and session_id not in deleted and session_id not in invalid:
            counts['import_without_source'] += 1

    try:
        if owner and owner.is_symlink():
            raise ValueError()
        files = {item.name: item for item in owner.iterdir() if valid_id(item.name)} if owner else {}
    except (OSError, ValueError):
        counts['unreadable_owner'] += 1
        return
    for session_id in site.keys() | native.keys() | files.keys() | deleted | invalid | links:
        path = files.get(session_id)
        if session_id in deleted:
            counts['deleted_with_file' if path else 'deleted'] += 1
            if session_id in site:
                counts['deleted_with_site_history'] += 1
            if session_id in native or session_id in links:
                counts['deleted_with_active_ledger'] += 1
            if AIChatMessage.objects.filter(user_id=user_id, conversation_id=UUID(hex=session_id),
                    metadata__dsh_imported_session_id=session_id).exists():
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

    def handle(self, *args, **options):
        root = Path(options['state_dir'])
        api_url = options['api_url']
        parsed = urlsplit(api_url)
        if not root.is_absolute() or not root.is_dir() or parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost', '::1'):
            raise CommandError('需要绝对路径的 DSH 状态目录和该目录原先使用的本机 API 地址。')
        write, gate = options['import_verified'], options['require_migrated']
        if gate and (write or options['user_id'] is not None):
            raise CommandError('迁移验收须对完整快照执行只读盘点。')
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
        # Handoff replies live entirely in product history and have no legacy transcript to migrate.
        answers = AIChatMessage.objects.filter(role='assistant', metadata__engine='dsh',
                                               metadata__dsh_handoff__isnull=True)
        replies = AIUsageReservation.objects.filter(status='succeeded', response__engine='dsh',
                                                    response__metadata__dsh_handoff__isnull=True)
        linked_users = set(answers.order_by().values_list('user_id', flat=True).distinct())
        linked_users.update(replies.order_by().values_list('user_id', flat=True).distinct())
        linked_users.update(AIChatMessage.objects.filter(role='assistant', metadata__engine='dsh_import')
                            .order_by().values_list('user_id', flat=True).distinct())
        counts = Counter()
        for user_id in users.values_list('pk', flat=True).iterator():
            digest = hashlib.sha256(json.dumps([api_url, user_id]).encode()).hexdigest()
            owner = owners.pop(digest, None)
            if owner or user_id in linked_users:
                owned_answers = list(answers.filter(user_id=user_id).order_by('pk'))
                owned_replies = replies.filter(user_id=user_id).order_by('pk').values_list(
                    'request_id', 'conversation_id', 'fingerprint', 'response', 'updated_at')
                if write:
                    with transaction.atomic():
                        audit_owner(user_id, owner, owned_answers, owned_replies.select_for_update(), counts, target_bot, write=True)
                else:
                    audit_owner(user_id, owner, owned_answers, owned_replies.iterator(), counts, target_bot)
        if options['user_id'] is None:
            counts['unmatched_owners'] = len(owners)
        if gate:
            from backoffice.tasks import TEACHING_JOB_KINDS, TEACHING_JOB_TIMEOUT
            from knowledge_builder.models import KnowledgeTreeBuild
            from quizzes.models import ContentPipelineTask

            now = timezone.now()
            active = AIUsageReservation.objects.filter(status='pending').filter(
                Q(conversation_id__isnull=False, updated_at__gte=now - CHAT_RESERVATION_TTL) |
                Q(conversation_id__isnull=True, updated_at__gte=now - AI_RESERVATION_TTL)).count()
            if active:
                counts['active_chat_requests'] = active
            active_teaching = ContentPipelineTask.objects.filter(
                status='running', started_at__gte=now - TEACHING_JOB_TIMEOUT, payload__kind__in=TEACHING_JOB_KINDS,
            ).filter(Q(payload__requires_ulr__isnull=True) | Q(payload__requires_ulr=False)).count()
            if active_teaching:
                counts['active_unpinned_teaching_tasks'] = active_teaching
            running_builds = KnowledgeTreeBuild.objects.filter(
                status=KnowledgeTreeBuild.Status.RUNNING, requires_ulr=False,
            ).count()
            if running_builds:
                counts['running_unpinned_knowledge_builds'] = running_builds
        report = dict(counts)
        if gate:
            blockers = {key: counts[key] for key in MIGRATION_BLOCKERS if counts[key]}
            report.update(migrated=not blockers, blockers=blockers)
        self.stdout.write(json.dumps(report, sort_keys=True))
        if gate and blockers:
            raise CommandError('DSH 退役盘点存在未完成的迁移项。')
