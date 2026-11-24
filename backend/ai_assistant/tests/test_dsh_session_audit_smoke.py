import hashlib
from datetime import timedelta
from io import StringIO
import json
from uuid import UUID, uuid4

from django.core.management import call_command, CommandError
from django.utils import timezone
import pytest

from ai_assistant.models import AIChatMessage, Bot, Conversation, ConversationProject
from users.models import AIUsageReservation


@pytest.mark.django_db
def test_dsh_inventory_separates_recoverable_unverified_and_deleted_histories(user, tmp_path, settings):
    api_url = 'http://127.0.0.1:8000'
    digest = hashlib.sha256(json.dumps([api_url, user.pk]).encode()).hexdigest()
    owner = tmp_path / digest
    owner.mkdir()
    (tmp_path / ('0' * 64)).mkdir()
    messages = [{'role': 'user', 'content': 'PRIVATE_SYNTHETIC_QUESTION'}, {'role': 'assistant', 'content': 'Synthetic reply'}]

    def write(session_id, rows):
        directory = owner / session_id
        directory.mkdir()
        (directory / 'transcript.json').write_text(json.dumps({'id': session_id, 'messages': rows}))

    def reserve(session_id, **data):
        AIUsageReservation.objects.create(user=user, request_id=uuid4(), attempt_id=uuid4(), week=timezone.now().date(),
            fingerprint='a' * 64, status='succeeded', response={'engine': 'dsh', 'session_id': session_id, **data})

    bot = Bot.objects.create(is_xiaoyu=True, name='小宇', bot_type='planner')
    for file_matches in (True, False, None):
        session_id, conversation_id = uuid4().hex, uuid4()
        Conversation.objects.create(user=user, bot=bot, conversation_id=conversation_id)
        prompt = AIChatMessage.objects.create(user=user, bot=bot, role='user', conversation_id=conversation_id, content=messages[0]['content'])
        answer = AIChatMessage.objects.create(user=user, bot=bot, role='assistant', conversation_id=conversation_id, content=messages[1]['content'],
            metadata={'engine': 'dsh', 'dsh_session_id': session_id, 'learning_turn': {'message_id': prompt.pk}})
        reserve(session_id, done=True, message_id=answer.pk, user_message={'message_id': prompt.pk},
                full_content=answer.content, metadata=answer.metadata)
        if file_matches is not None:
            write(session_id, messages if file_matches else [messages[0], {**messages[1], 'content': 'Different reply'}])
        if file_matches:
            legacy_conversation_id = conversation_id

    import_ids = []
    for has_file in (True, False):
        session_id = uuid4().hex
        import_ids.append(UUID(hex=session_id))
        extended = messages * 2
        for history in (extended, messages):
            reserve(session_id, finish_reason='completed', session={'id': session_id, 'messages': history}, content=messages[-1]['content'])
        if has_file:
            write(session_id, extended)

    write(uuid4().hex, messages)
    write(uuid4().hex, [])
    deleted = uuid4().hex
    write(deleted, messages)
    reserve(deleted, deleted=True)
    invalid = owner / uuid4().hex
    invalid.mkdir()
    (invalid / 'transcript.json').write_text('malformed')
    files = {p: p.read_bytes() for p in owner.glob('*/transcript.json')}
    before = list(AIUsageReservation.objects.filter(user=user).values_list('response', flat=True))
    output = StringIO()
    call_command('audit_dsh_sessions', state_dir=str(tmp_path), api_url=api_url, stdout=output)
    assert json.loads(output.getvalue()) == {'site_matched': 1, 'site_history_only': 1, 'conflict': 1, 'native_matched': 1,
        'native_ledger_only': 1, 'native_file_only': 1, 'empty_native_session': 1, 'deleted_with_file': 1,
        'unreadable_file': 1, 'unmatched_owners': 1}
    assert 'PRIVATE_SYNTHETIC_QUESTION' not in output.getvalue()
    assert all(path.read_bytes() == data for path, data in files.items())
    assert list(AIUsageReservation.objects.filter(user=user).values_list('response', flat=True)) == before

    args = {'state_dir': str(tmp_path), 'api_url': api_url, 'import_verified': True}
    settings.UNIMIND_DSH_ENABLED = True
    with pytest.raises(CommandError):
        call_command('audit_dsh_sessions', **args)
    settings.UNIMIND_DSH_ENABLED = False
    for pass_name in ('imported', 'already_imported'):
        output = StringIO()
        call_command('audit_dsh_sessions', stdout=output, **args)
        assert json.loads(output.getvalue())[pass_name] == 2
        assert Conversation.objects.count() == 5
    for conversation_id in import_ids:
        assert list(AIChatMessage.objects.filter(user=user, conversation_id=conversation_id)
                    .values('role', 'content')) == messages * 2
    assert all(path.read_bytes() == data for path, data in files.items())

    project = ConversationProject.objects.create(user=user, name='迁移验证项目')
    deleted_conversations = Conversation.objects.filter(conversation_id__in=[import_ids[0], legacy_conversation_id])
    deleted_conversations.update(project=project)
    continuation = AIChatMessage.objects.create(user=user, bot=bot, conversation_id=import_ids[0], role='assistant',
        content='继续讨论。', metadata={'engine': 'ulr'})
    request = AIUsageReservation.objects.create(user=user, request_id=uuid4(), attempt_id=uuid4(), week=timezone.now().date(),
        status='succeeded', response={'engine': 'ulr', 'message_id': continuation.pk})
    project.delete()
    request.refresh_from_db()
    assert request.response == {'engine': 'ulr', 'deleted': True}
    output = StringIO()
    call_command('audit_dsh_sessions', stdout=output, **args)
    after_delete = json.loads(output.getvalue())
    assert after_delete['deleted_with_file'] == 3 and after_delete['already_imported'] == 1
    assert 'imported' not in after_delete
    assert not deleted_conversations.exists()


@pytest.mark.django_db
def test_dsh_migration_gate_checks_import_content_and_ledger(user, tmp_path, settings):
    settings.UNIMIND_DSH_ENABLED = False
    api_url = 'http://127.0.0.1:8000'
    bot = Bot.objects.create(is_xiaoyu=True, name='小宇', bot_type='planner')
    conversation_id = uuid4()
    session_id = conversation_id.hex
    cards = [{'type': 'data_card', 'payload': {'title': 'SYNTHETIC_SOURCE'}}]
    rows = [{'role': 'user', 'content': 'SYNTHETIC_PROMPT'},
            {'role': 'assistant', 'content': 'SYNTHETIC_ANSWER', 'cards': cards}]
    reservation = AIUsageReservation.objects.create(user=user, request_id=uuid4(), attempt_id=uuid4(),
        week=timezone.now().date(), status='succeeded', response={
            'engine': 'dsh', 'session_id': session_id, 'finish_reason': 'completed',
            'session': {'id': session_id, 'messages': rows}, 'content': rows[1]['content'],
        })
    options = {'state_dir': str(tmp_path), 'api_url': api_url}

    def audit(blockers):
        output = StringIO()
        if blockers:
            with pytest.raises(CommandError, match='未完成的迁移项'):
                call_command('audit_dsh_sessions', **options, require_migrated=True, stdout=output)
        else:
            call_command('audit_dsh_sessions', **options, require_migrated=True, stdout=output)
        report = json.loads(output.getvalue())
        assert report['migrated'] is (not blockers) and report['blockers'] == blockers
        assert 'SYNTHETIC_' not in output.getvalue()

    audit({'pending_import': 1})
    assert not Conversation.objects.exists()
    call_command('audit_dsh_sessions', **options, import_verified=True, stdout=StringIO())
    messages = AIChatMessage.objects.filter(user=user, bot=bot, conversation_id=conversation_id)
    AIChatMessage.objects.create(user=user, bot=bot, conversation_id=conversation_id, role='assistant',
                                 content='原会话已经续聊。', metadata={'engine': 'ulr'})
    audit({})
    answer_id, metadata = messages.filter(metadata__engine='dsh_import').values_list('pk', 'metadata').get()
    messages.filter(pk=answer_id).update(metadata={**metadata, 'dsh_cards': []})
    audit({'import_conflict': 1})
    retry = StringIO()
    call_command('audit_dsh_sessions', **options, import_verified=True, stdout=retry)
    assert json.loads(retry.getvalue())['import_conflict'] == 1
    assert messages.count() == 3 and messages.get(pk=answer_id).metadata['dsh_cards'] == []
    messages.filter(pk=answer_id).update(metadata=metadata)
    receipt = reservation.response
    reservation.response = {'engine': 'dsh', 'session_id': session_id, 'deleted': True}
    reservation.save(update_fields=['response'])
    audit({'deleted_with_imported_history': 1})
    reservation.response = receipt
    reservation.save(update_fields=['response'])
    reservation.delete()
    audit({'import_without_source': 1})


@pytest.mark.django_db
def test_dsh_migration_gate_requires_a_recoverable_receipt_for_each_product_turn(user, tmp_path, settings):
    settings.UNIMIND_DSH_ENABLED = False
    bot = Bot.objects.create(is_xiaoyu=True, name='小宇', bot_type='planner')
    conversation_id, request_id = uuid4(), uuid4()
    session_id = uuid4().hex
    Conversation.objects.create(user=user, bot=bot, conversation_id=conversation_id)
    source = {'user': user, 'bot': bot, 'conversation_id': conversation_id}
    prompt = AIChatMessage.objects.create(**source, role='user', content='合成迁移问题',
        metadata={'runtime_request_id': str(request_id)})
    cards = [{'type': 'data_card', 'payload': {'title': 'SYNTHETIC_RECOVERY_CARD'}}]
    metadata = {'engine': 'dsh', 'dsh_session_id': session_id, 'dsh_cards': cards,
        'learning_turn': {'message_id': prompt.pk}}
    answer = AIChatMessage.objects.create(**source, role='assistant', content='合成迁移答复', metadata=metadata)
    payload = {'engine': 'dsh', 'done': True, 'session_id': session_id, 'full_content': answer.content,
        'message_id': answer.pk, 'user_message': {'message_id': prompt.pk}, 'metadata': metadata}
    options = {'state_dir': str(tmp_path), 'api_url': 'http://127.0.0.1:8000', 'require_migrated': True}

    def audit(expected):
        output = StringIO()
        if expected:
            with pytest.raises(CommandError, match='未完成的迁移项'):
                call_command('audit_dsh_sessions', stdout=output, **options)
        else:
            call_command('audit_dsh_sessions', stdout=output, **options)
        assert json.loads(output.getvalue())['blockers'] == expected
        assert 'SYNTHETIC_RECOVERY_CARD' not in output.getvalue()

    audit({'missing_site_receipt': 1})
    receipt = AIUsageReservation.objects.create(user=user, request_id=request_id, conversation_id=conversation_id,
        attempt_id=uuid4(), week=timezone.now().date(), fingerprint='a' * 64, status='succeeded', response=payload)
    audit({})
    AIUsageReservation.objects.filter(pk=receipt.pk).update(response={**payload, 'metadata': {**metadata, 'dsh_cards': []}})
    audit({'invalid_site_receipt': 1})
    AIUsageReservation.objects.filter(pk=receipt.pk).update(response=payload, request_id=uuid4())
    audit({'invalid_site_receipt': 1})
    AIUsageReservation.objects.filter(pk=receipt.pk).update(request_id=request_id, fingerprint='')
    audit({'invalid_site_receipt': 1})
    AIUsageReservation.objects.filter(pk=receipt.pk).update(fingerprint='a' * 64)
    duplicate = AIUsageReservation.objects.create(user=user, request_id=uuid4(), attempt_id=uuid4(),
        week=timezone.now().date(), fingerprint='a' * 64, status='succeeded', response=payload)
    audit({'invalid_site_receipt': 1, 'duplicate_site_receipt': 1})
    duplicate.delete()
    audit({})
    from users.learning import AI_RESERVATION_TTL, CHAT_RESERVATION_TTL
    for conversation, ttl in ((conversation_id, CHAT_RESERVATION_TTL), (None, AI_RESERVATION_TTL)):
        pending = AIUsageReservation.objects.create(user=user, request_id=uuid4(), attempt_id=uuid4(),
            conversation_id=conversation, week=timezone.now().date(), status='pending')
        audit({'active_chat_requests': 1})
        AIUsageReservation.objects.filter(pk=pending.pk).update(updated_at=timezone.now() - ttl - timedelta(seconds=1))
        audit({})
        pending.refresh_from_db()
        assert pending.status == 'pending'
    from backoffice.tasks import TEACHING_JOB_TIMEOUT
    from quizzes.models import ContentPipelineTask

    job = ContentPipelineTask.objects.create(created_by=user, title='合成教研任务', task_type='other',
        status='pending', payload={'kind': 'chat'})
    audit({})
    ContentPipelineTask.objects.filter(pk=job.pk).update(status='running', started_at=timezone.now())
    audit({'active_unpinned_teaching_tasks': 1})
    ContentPipelineTask.objects.filter(pk=job.pk).update(payload={'kind': 'chat', 'requires_ulr': True})
    audit({})
    ContentPipelineTask.objects.filter(pk=job.pk).update(
        payload={'kind': 'chat'}, started_at=timezone.now() - TEACHING_JOB_TIMEOUT - timedelta(seconds=1))
    audit({})
    job.refresh_from_db()
    assert job.status == 'running'

    from knowledge_builder.models import KnowledgeTreeBuild

    KnowledgeTreeBuild.objects.create(subject='合成待处理旧构建', status='PENDING')
    KnowledgeTreeBuild.objects.create(subject='合成运行中构建', status='RUNNING', requires_ulr=True)
    audit({})
    build = KnowledgeTreeBuild.objects.create(subject='合成旧执行进程', status='RUNNING')
    KnowledgeTreeBuild.objects.filter(pk=build.pk).update(updated_at=timezone.now() - timedelta(days=1))
    audit({'running_unpinned_knowledge_builds': 1})
    build.refresh_from_db()
    assert build.status == 'RUNNING' and not build.requires_ulr
    KnowledgeTreeBuild.objects.filter(pk=build.pk).update(status='COMPLETED')
    audit({})
    owner = hashlib.sha256(json.dumps([options['api_url'], user.pk]).encode()).hexdigest()
    (tmp_path / owner).write_text('SYNTHETIC_RECOVERY_CARD')
    audit({'unreadable_owner': 1})
