"""Focused internal-generation routing checks; no model provider or real data."""
from unittest.mock import patch

import pytest

from ai_engine.service import AIEngine
from ai_assistant.services.dsh_runtime import DshUnavailable


def test_internal_generation_uses_dsh_without_legacy_fallback(settings):
    settings.UNIMIND_DSH_GENERATION_ENABLED = True
    schema = {'type': 'object', 'properties': {'ok': {'type': 'boolean'}}, 'required': ['ok']}
    messages = [{'role': 'user', 'content': '合成材料'}]
    with patch('ai_assistant.services.dsh_generation.generate', return_value={'ok': True}) as generate:
        assert AIEngine.structured_output(messages, schema, operation='courses.generate_outline') == {'ok': True}
        assert generate.call_args.kwargs['schema'] == schema
    with patch('ai_assistant.services.dsh_generation.generate', return_value={'text': '合成说明'}):
        result = AIEngine.call_ai(messages, operation='notes.understanding')
        assert result['choices'][0]['message']['content'] == '合成说明'
    with patch('ai_assistant.services.dsh_generation.generate', side_effect=DshUnavailable()), patch('ai_engine.service._session.post') as legacy:
        with pytest.raises(DshUnavailable):
            AIEngine.call_ai(messages, operation='memory.analyze_profile')
        legacy.assert_not_called()
    with patch('ai_engine.service._session.post') as legacy:
        with pytest.raises(DshUnavailable):
            AIEngine.call_ai_with_streaming_tools(messages, [], None, operation='assistant.chat.planner')
        legacy.assert_not_called()


def test_teaching_switch_routes_research_and_preserves_executor(settings):
    settings.UNIMIND_DSH_TEACHING_ENABLED = True
    executor = lambda name, arguments: '{}'
    schema = {'type': 'object'}
    with patch('ai_assistant.services.dsh_generation.generate', return_value={'score': .8}) as generate:
        result = AIEngine.agentic_structured_output([], schema, 'submit_review', '评阅', [], executor, operation='pipeline.reviewer')
        assert result == {'score': .8}
        assert generate.call_args.kwargs['executor'] is executor
    with patch('ai_assistant.services.dsh_generation.generate', return_value={'text': '候选已准备'}) as generate:
        result = AIEngine.call_ai_with_tools([], [], executor, operation='assistant.chat.exam_generator')
        assert result['choices'][0]['message']['content'] == '候选已准备'


def test_generation_budget_and_schema_are_server_owned(settings, tmp_path):
    from ai_assistant.services.dsh_generation import generate
    with patch('ai_assistant.services.dsh_generation.run_structured', return_value={'text': '合成'} ) as run:
        assert generate([], 'pipeline.reviewer', max_tokens=20000) == {'text': '合成'}
        spec = run.call_args.kwargs['internal']
        assert spec['tokens'] == 8192 and spec['max_requests'] == 1
        assert spec['tier'] == 'pro' and spec['thinking'] == 'high'
        assert spec['operation'] == 'pipeline.reviewer'
    with patch('ai_assistant.services.dsh_generation.run_structured', return_value={'text': '合成'}) as run:
        generate([], 'notes.understanding', temperature=0)
        assert run.call_args.kwargs['internal']['temperature'] == 0


def test_maintenance_command_and_mem0_cannot_bypass_generation(settings):
    from unittest.mock import Mock
    from quizzes.management.commands.backfill_question_kp import Command
    from ai_assistant.services.tenant_memory import TenantMemoryManager
    settings.UNIMIND_DSH_GENERATION_ENABLED = True
    with patch('ai_engine.ai_service.AIService.simple_chat_text', return_value='{"kp_id": 1}') as text, patch('httpx.post', side_effect=AssertionError('direct model request')):
        assert Command()._call_llm('合成系统', '合成题目') == {'kp_id': 1}
        assert text.call_args.kwargs['max_tokens'] == 256
    manager = object.__new__(TenantMemoryManager)
    manager.memory, manager.institution_id = Mock(), 1
    manager.add(1, '单次请求')
    manager.memory.add.assert_not_called()


@pytest.mark.django_db(transaction=True)
def test_teaching_job_revocation_reaches_reviewer_and_drops_candidates(settings):
    from uuid import uuid4
    from users.models import User
    from quizzes.models import ContentPipelineTask, KnowledgePoint
    from backoffice.tasks import run_teaching_task
    from ai_assistant.services.dsh_generation import generate
    admins = [User.objects.create_superuser(username=f'dsh-job-admin-{i}') for i in range(2)]
    settings.UNIMIND_DIRECTUS_ADMIN_MAP = dict(zip([str(uuid4()), str(uuid4())], [user.pk for user in admins]))
    settings.UNIMIND_CONTENT_INSTITUTION_ID = 'global'
    settings.UNIMIND_DSH_TEACHING_ENABLED = True
    kp = KnowledgePoint.objects.create(name='合成考点', level='kp')
    task = ContentPipelineTask.objects.create(created_by=admins[0], title='合成候选', payload={'kind': 'quick', 'kp_ids': [kp.pk], 'count': 1})
    def revoke(*args, **kwargs):
        User.objects.filter(pk=admins[0].pk).update(is_active=False)
        # Reviewer uses a plain closure, rather than TeachingExecutor.
        with patch('ai_assistant.services.dsh_generation.run_structured') as run:
            with pytest.raises(DshUnavailable):
                generate([], 'pipeline.reviewer', tools=[{'function': {'name': 'lookup_knowledge_point_definition', 'parameters': {'type': 'object'}}}], executor=lambda *_: '{}')
            run.assert_not_called()
        return [{'kp_id': kp.pk, 'question': '不应保存的候选'}]
    with patch('quizzes.services.adversarial_pipeline._author_generate', side_effect=revoke):
        run_teaching_task(task.pk)
    task.refresh_from_db()
    assert task.status == 'failed' and not task.result.get('questions')


def test_nested_generation_shares_deadline_and_stops_after_callback_closes():
    from ai_assistant.services.dsh_generation import generate, callbacks
    from ai_assistant.services.dsh_scope import generation_scope, current_execution
    with generation_scope():
        execution = current_execution()
        with patch('ai_assistant.services.dsh_generation.run_structured', return_value={'text': '合成'}) as run:
            generate([], 'pipeline.author')
            assert run.call_args.kwargs['internal']['deadline'] == execution['deadline']
            execution['cancelled'].set()
            with pytest.raises(DshUnavailable):
                generate([], 'pipeline.author')
            assert run.call_count == 1


def test_closing_bridge_stops_later_nested_requests_and_joins_handler():
    import json
    from threading import Event, Thread
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError
    from ai_assistant.services.dsh_generation import generate, callbacks
    from ai_assistant.services.dsh_scope import generation_scope, current_execution
    started, results = Event(), []
    tool = {'function': {'name': 'lookup_knowledge_point_definition', 'parameters': {'type': 'object'}}}
    def slow_result(*args, **kwargs):
        started.set()
        assert current_execution()['cancelled'].wait(2)
        return {'text': '晚到候选'}
    def executor(*args):
        for _ in range(3):
            generate([], 'pipeline.author')
        return {}
    with generation_scope(), patch('ai_assistant.services.dsh_generation.run_structured', side_effect=slow_result) as run:
        with callbacks([tool], executor, current_execution()) as bridge:
            def request():
                req = Request(bridge['url'] + '/lookup_knowledge_point_definition', json.dumps({}).encode(),
                              headers={'Authorization': 'Bearer ' + bridge['token']})
                try:
                    with urlopen(req, timeout=5) as response:
                        results.append(response.status)
                except HTTPError as error:
                    results.append(error.code)
            thread = Thread(target=request)
            thread.start()
            assert started.wait(2)
        thread.join(2)
        assert not thread.is_alive() and results == [403]
        assert run.call_count == 1


def test_callback_auth_schema_and_revoked_scope():
    import json
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError
    from ai_assistant.services.dsh_generation import callbacks
    schema = {'type': 'object', 'properties': {'limit': {'type': 'integer', 'minimum': 1, 'maximum': 2}},
              'required': ['limit'], 'additionalProperties': False}
    tools = [{'function': {'name': 'lookup_knowledge_point_definition', 'parameters': schema}}]
    class Executor:
        allowed = True
        calls = 0
        def check_dsh_scope(self):
            if not self.allowed:
                raise PermissionError()
        def __call__(self, name, args):
            self.calls += 1
            return {'found': True}
    executor = Executor()
    with callbacks(tools, executor) as bridge:
        def request(name, args, token=None):
            req = Request(bridge['url'] + '/' + name, json.dumps(args).encode(),
                          headers={'Authorization': 'Bearer ' + (token or bridge['token'])})
            try:
                with urlopen(req, timeout=5) as response:
                    return response.status
            except HTTPError as error:
                return error.code
        assert request('lookup_knowledge_point_definition', {'limit': 1}, 'wrong') == 403
        assert request('send_notification', {'limit': 1}) == 403
        assert request('lookup_knowledge_point_definition', {'limit': 3}) == 403
        assert executor.calls == 0
        assert request('lookup_knowledge_point_definition', {'limit': 1}) == 200
        executor.allowed = False
        assert request('lookup_knowledge_point_definition', {'limit': 1}) == 403
        assert executor.calls == 1


@pytest.mark.django_db
def test_teaching_executor_rechecks_current_admin_and_content(settings):
    from uuid import uuid4
    from users.models import User, Institution
    from backoffice.teaching_executor import TeachingExecutor
    admins = [User.objects.create_superuser(username=f'dsh-teacher-{i}') for i in range(2)]
    settings.UNIMIND_DIRECTUS_ADMIN_MAP = dict(zip([str(uuid4()), str(uuid4())], [user.pk for user in admins]))
    settings.UNIMIND_CONTENT_INSTITUTION_ID = 'global'
    executor = TeachingExecutor(admins[0])
    executor.check_dsh_scope()
    User.objects.filter(pk=admins[0].pk).update(is_active=False)
    with pytest.raises(PermissionError):
        executor.check_dsh_scope()
    User.objects.filter(pk=admins[0].pk).update(is_active=True)
    scope = Institution.objects.create(name='Another scope', slug='dsh-another-scope')
    settings.UNIMIND_CONTENT_INSTITUTION_ID = str(scope.pk)
    with pytest.raises(PermissionError):
        executor.check_dsh_scope()
