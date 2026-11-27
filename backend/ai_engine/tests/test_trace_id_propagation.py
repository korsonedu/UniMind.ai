"""End-to-end tests for unified trace_id propagation across L4 -> L3 -> ULR -> L1 -> L2."""
import logging
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from ai_assistant.models import (
    AIChatMessage, Bot, Conversation, ConversationProject,
    LearningStrategy, LearningStrategyUse, ProjectLearningEvent,
)
from ai_assistant.services import teaching_sidecar
from ai_assistant.services.dsh_xiaoyu import complete_turn
from ai_assistant.services.title_generator import sync_generate_title
from ai_assistant.services.ulr_memory import extract_answer_memory
from ai_engine.observability import (
    current_trace_id, log_ai_operation, normalize_trace_id, observe_background,
    observe_runtime, record_schema_event, resolve_trace_id, runtime_observation,
)
from users.models import AIUsageReservation


def test_observability_trace_helpers_and_context_reset(caplog):
    assert normalize_trace_id('  trace-abc-123  ') == 'trace-abc-123'
    assert normalize_trace_id('bad trace with space') is None
    assert normalize_trace_id('bad\nnewline') is None
    assert normalize_trace_id('x' * 200) is None
    assert current_trace_id() is None

    with caplog.at_level(logging.INFO, logger='ai_engine.observability'):
        with observe_runtime('ulr', 'req-1', trace_id='trace-root-001') as trace_id:
            assert trace_id == 'trace-root-001'
            assert current_trace_id() == 'trace-root-001'
            log_ai_operation('assistant.chat.test', True, 12)
            record_schema_event('assistant.chat.test', 'validate', True)
            with observe_background('ulr', 'bg-1'):
                # Nested background scope inherits active trace_id unless overridden.
                assert runtime_observation.get()['trace_id'] == 'trace-root-001'
            with observe_background('ulr', 'bg-2', trace_id='trace-override-002'):
                assert runtime_observation.get()['trace_id'] == 'trace-override-002'
        assert current_trace_id() is None
        assert not runtime_observation.get()

    assert "'trace_id': 'trace-root-001'" in caplog.text
    assert 'ai.schema operation=assistant.chat.test' in caplog.text
    assert resolve_trace_id(None, fallback='fallback-id') == 'fallback-id'


@pytest.mark.django_db
def test_xiaoyu_turn_propagates_trace_id_to_receipt_recovery_and_background_jobs(user, caplog, settings):
    settings.UNIMIND_ULR_MODE = 'native'
    settings.UNIMIND_DSH_MEMORY_ENABLED = False
    settings.UNIMIND_DSH_TITLE_ENABLED = False
    bot = Bot.objects.create(name='小宇', bot_type='planner', is_xiaoyu=True, is_active=True)
    conv_id = uuid4()
    Conversation.objects.create(user=user, bot=bot, conversation_id=conv_id, title='')
    req_id = uuid4()
    custom_trace = 'trace-xiaoyu-e2e-001'
    request = SimpleNamespace(
        user=user,
        data={'message': '帮我复习现金流折现', 'conversation_id': str(conv_id), 'request_id': str(req_id)},
        headers={'X-Trace-Id': custom_trace},
        ui_language='zh',
    )

    observed_in_runtime = []

    def fake_run_turn(u, message, chat_context, emit, source, check_active, *, workbench=None):
        observed_in_runtime.append(dict(runtime_observation.get()))
        log_ai_operation('assistant.chat.ulr_turn', True, 5)
        return '这是现金流折现的讲解。', [], None, None, None, {
            'courses': [], 'notes': [], 'selection': False, 'question_answers': [], 'transcripts': [],
        }

    with caplog.at_level(logging.INFO, logger='ai_engine.observability'), \
            patch('ai_assistant.services.ulr_runtime.run_turn', side_effect=fake_run_turn), \
            patch('ai_assistant.services.dsh_xiaoyu.schedule_conversation_title'), \
            patch('ai_assistant.services.dsh_xiaoyu.extract_memories_async'):
        payload = complete_turn(request, bot, conv_id, '帮我复习现金流折现', lambda _e: None, ulr=True)

    assert observed_in_runtime and observed_in_runtime[0]['trace_id'] == custom_trace
    assert payload['trace_id'] == custom_trace
    assert payload['metadata']['trace_id'] == custom_trace

    question = AIChatMessage.objects.get(pk=payload['user_message']['message_id'])
    answer = AIChatMessage.objects.get(pk=payload['message_id'])
    assert question.metadata['trace_id'] == custom_trace
    assert answer.metadata['trace_id'] == custom_trace

    reservation = AIUsageReservation.objects.get(user=user, request_id=req_id)
    assert reservation.response['trace_id'] == custom_trace

    # Verify recovery endpoint surfaces trace_id in both body and X-Trace-Id header.
    client = APIClient()
    client.force_authenticate(user=user)
    recovery = client.get(f'/api/ai/chat-requests/{req_id}/')
    assert recovery.status_code == 200
    assert recovery.data['trace_id'] == custom_trace
    assert recovery['X-Trace-Id'] == custom_trace

    # Verify background memory extraction inherits the exact same trace_id from persisted L1 message.
    memory_obs = []

    def fake_memory_collector(*args, **kwargs):
        memory_obs.append(dict(runtime_observation.get()))
        log_ai_operation('assistant.memory_extract', True, 3)
        return {'memories': []}

    with caplog.at_level(logging.INFO, logger='ai_engine.observability'), \
            patch('ai_assistant.services.ulr_memory.has_learning_feature', return_value=True), \
            patch('ai_assistant.services.ulr_memory.conversation_uses_notes', return_value=False), \
            patch('ai_assistant.services.ulr_memory.run_collector', side_effect=fake_memory_collector):
        extract_answer_memory(question.pk, answer.pk)

    assert memory_obs and memory_obs[0]['trace_id'] == custom_trace

    # Verify background title generation inherits the exact same trace_id.
    title_obs = []

    def fake_title_collector(*args, **kwargs):
        title_obs.append(dict(runtime_observation.get()))
        log_ai_operation('assistant.title', True, 2)
        return {'title': '现金流折现复习'}

    conv = Conversation.objects.get(user=user, conversation_id=conv_id)
    with caplog.at_level(logging.INFO, logger='ai_engine.observability'), \
            patch('ai_assistant.services.title_generator._authorized_title_inputs', return_value=([], [], [], [], [])), \
            patch('ai_assistant.services.ulr_structured.run_collector', side_effect=fake_title_collector):
        generated = sync_generate_title(
            str(conv_id), user.pk, bot.pk, expected_title=conv.title, ulr=True, answer_message_id=answer.pk,
        )

    assert generated == '现金流折现复习'
    assert title_obs and title_obs[0]['trace_id'] == custom_trace


@pytest.mark.django_db
def test_teaching_sidecar_records_trace_id_across_freeze_decision_and_exposure(user):
    bot = Bot.objects.create(name='小宇', bot_type='planner', is_xiaoyu=True, is_active=True)
    project = ConversationProject.objects.create(user=user, name='财务估值')
    conv_id = uuid4()
    Conversation.objects.create(user=user, bot=bot, conversation_id=conv_id, project=project, title='估值')
    trace_id = 'trace-sidecar-001'
    question = AIChatMessage.objects.create(
        user=user, bot=bot, conversation_id=conv_id, role='user', content='如何算自由现金流？',
        metadata={'trace_id': trace_id},
    )
    frozen = teaching_sidecar.freeze_turn(project, question, {'stage': 's1'})
    assert frozen['trace_id'] == trace_id

    source_event = ProjectLearningEvent.objects.create(
        project=project, message=question, kind='strategy',
        content={'strategy': '先画时间轴再折现', 'context': {'topic': 'DCF'}},
    )
    strategy = LearningStrategy.objects.create(
        user=user, source_event=source_event, domain='finance', topic='DCF',
    )
    use = LearningStrategyUse.objects.create(project=project, strategy=strategy, message=question)
    teaching_sidecar.record_strategy_use(use, created=True)
    use.refresh_from_db()
    assert use.decision['trace_id'] == trace_id

    reply = AIChatMessage.objects.create(
        user=user, bot=bot, conversation_id=conv_id, role='assistant', content='先画现金流时间轴。',
        metadata={
            'trace_id': trace_id,
            'learning_turn': {'message_id': question.pk, 'completed': True, 'completed_at': timezone.now().isoformat()},
        },
    )
    teaching_sidecar.record_turn_completion(reply)
    use.refresh_from_db()
    assert use.exposure['trace_id'] == trace_id

