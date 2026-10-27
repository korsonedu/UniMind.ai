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
