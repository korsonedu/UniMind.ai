"""Focused parser routing and canonical-schema checks, no model provider."""
import json
import sys
from unittest.mock import patch

import pytest
from ai_engine.ai_service import AIService
from ai_engine.tools import QUESTION_LIST_SCHEMA
from ai_assistant.services.dsh_runtime import DshUnavailable


def test_parser_opt_in_is_independent_and_never_falls_back(settings):
    body = dict(system_prompt='', user_prompt='合成题目资料', schema=QUESTION_LIST_SCHEMA,
                operation='quizzes.preview_parse')
    with patch('ai_engine.ai_service.AIEngine.structured_output', return_value=[]) as legacy:
        assert AIService.structured_output(**body) == []
        settings.UNIMIND_DSH_TEACHING_ENABLED = True
        with patch('ai_assistant.services.dsh_tasks.run_structured', return_value=[]) as task:
            assert AIService.structured_output(**body) == []
            task.assert_called_once()
        legacy.reset_mock()
        with patch('ai_assistant.services.dsh_tasks.run_structured', side_effect=DshUnavailable()):
            with pytest.raises(DshUnavailable):
                AIService.structured_output(**body)
        legacy.assert_not_called()


def test_parser_array_envelope_and_fixed_budget(settings, tmp_path, monkeypatch):
    from ai_assistant.services.dsh_tasks import run_structured
    settings.DEBUG = True
    settings.UNIMIND_DSH_PYTHON = sys.executable
    settings.UNIMIND_DSH_STATE_DIR = str(tmp_path)
    settings.UNIMIND_DSH_FIXTURE_URL = 'http://127.0.0.1:8912/v1/messages'
    monkeypatch.setenv('AI_MODEL_FAST', 'parse-fast-model')
    question = dict(question='合成题目', q_type='subjective', subjective_type='short',
                    options=None, answer='合成答案', grading_points=['合成评分点'], difficulty_level='normal')
    with patch('ai_assistant.services.dsh_tasks.subprocess.Popen') as popen:
        process = popen.return_value.__enter__.return_value
        process.returncode = 0
        process.communicate.return_value = (json.dumps({'status': 200, 'result': {'questions': [question]}}).encode(), b'')
        assert run_structured('quizzes.preview_parse', '合成材料') == [question]
        payload = json.loads(process.communicate.call_args.args[0])
        policy = payload['context']['model_policy']
        assert (policy['tier'], policy['model'], policy['max_requests'], policy['max_tokens']) == ('fast', 'parse-fast-model', 1, 3200)
        wire = payload['context']['tools'][0]['function']['parameters']
        assert wire['type'] == 'object'
        assert wire['properties']['questions']['items']['properties']['options']['oneOf'][-1]['type'] == 'null'
        assert '解析' in payload['context']['task_instruction']
        for bad in ({'questions': [{}]}, {'questions': [{**question, 'difficulty_level': 'invalid'}]}, {'questions': 'bad'}):
            process.communicate.return_value = (json.dumps({'status': 200, 'result': bad}).encode(), b'')
            with pytest.raises(DshUnavailable):
                run_structured('quizzes.preview_parse', '合成材料')


def test_existing_parser_sends_material_when_template_is_absent():
    from quizzes.services.ai_task_service import QuizAITaskService
    with patch.object(AIService, 'get_template', return_value=None), patch.object(AIService, 'structured_output', return_value=[]) as model:
        assert QuizAITaskService.parse_questions_from_text(AIService, raw_text='SYNTHETIC_SOURCE_314') == []
        assert 'SYNTHETIC_SOURCE_314' in model.call_args.kwargs['user_prompt']


def test_parser_preserves_missing_fields_and_raw_options():
    from quizzes.services.ai_task_service import QuizAITaskService

    class FakeAI:
        @staticmethod
        def get_template(*_args):
            return None

        @staticmethod
        def format_template(template, **kwargs):
            return template.format(**kwargs)

        @staticmethod
        def structured_output(**_kwargs):
            return [
                {'question': '主观题', 'q_type': 'subjective', 'subjective_type': 'short',
                 'answer': '', 'grading_points': None, 'difficulty_level': 'normal'},
                {'question': '客观题', 'q_type': 'objective', 'options': {'A': '一'}, 'answer': 'A'},
            ]

    result = QuizAITaskService.parse_questions_from_text(FakeAI(), '合成材料')
    assert result[0]['grading_points'] == '' and result[0]['correct_answer'] == ''
    assert result[1]['options'] == {'A': '一'}
