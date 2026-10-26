"""Small adapter/policy checks; actual SDK and submission are tested in the isolated fixture."""
import json
import signal
import subprocess
import sys
from unittest.mock import patch

import pytest
from ai_engine.ai_service import AIService
from ai_engine.tools import GRADING_RESULT_SCHEMA
from ai_assistant.services.dsh_runtime import DshUnavailable


def test_grading_opt_in_and_no_model_fallback(settings, monkeypatch):
    from ai_engine.config import get_model_for_task
    monkeypatch.setenv('LLM_MODEL', 'legacy-custom-model')
    monkeypatch.setenv('AI_MODEL_FAST', 'fast-model')
    assert get_model_for_task('quizzes.objective_analysis')['model'] == 'legacy-custom-model' 
    body = dict(system_prompt='', user_prompt='合成评分', schema=GRADING_RESULT_SCHEMA,
                tool_name='submit_grading_result', operation='quizzes.grade_question')
    with patch('ai_engine.ai_service.AIEngine.structured_output', return_value={'legacy': True}) as legacy:
        assert AIService.structured_output(**body) == {'legacy': True}
        settings.UNIMIND_DSH_GRADING_ENABLED = True
        with patch('ai_assistant.services.dsh_tasks.run_structured', return_value={'score': 8}) as task:
            assert AIService.structured_output(**body) == {'score': 8}
            assert task.call_args.args[0] == 'quizzes.grade_question'
        legacy.reset_mock()
        with patch('ai_assistant.services.dsh_tasks.run_structured', side_effect=DshUnavailable()):
            with pytest.raises(DshUnavailable):
                AIService.structured_output(**body)
            assert AIService.structured_output(**{**body, 'operation': 'quizzes.objective_analysis'}) is None
        legacy.assert_not_called()


def test_structured_result_validation_private_config_and_timeout(settings, tmp_path):
    from ai_assistant.services.dsh_tasks import run_structured
    settings.DEBUG = True
    settings.UNIMIND_DSH_PYTHON = sys.executable
    settings.UNIMIND_DSH_STATE_DIR = str(tmp_path / 'tasks')
    settings.UNIMIND_DSH_FIXTURE_URL = 'http://127.0.0.1:8912/v1/messages'
    with patch('ai_assistant.services.dsh_tasks.Path.mkdir', side_effect=PermissionError()):
        with pytest.raises(DshUnavailable):
            run_structured('quizzes.objective_analysis', '合成目录故障')
    valid = {'score': 8, 'feedback': '合成评分', 'analysis': '合成答案', 'memorix_rating': 3, 'error_analysis': None}
    with patch('ai_assistant.services.dsh_tasks.subprocess.Popen') as popen:
        process = popen.return_value.__enter__.return_value
        process.returncode = 0
        process.communicate.return_value = (json.dumps({'status': 200, 'result': valid}).encode(), b'')
        assert run_structured('quizzes.grade_question', 'PRIVATE_SYNTHETIC_ANSWER') == valid
        payload = json.loads(process.communicate.call_args.args[0])
        assert payload['context']['model_policy']['tier'] == 'pro'
        assert payload['context']['model_policy']['max_tokens'] == 2500
        assert payload['context']['model_policy']['max_requests'] == 1
        wire = payload['context']['tools'][0]['function']['parameters']
        assert wire['properties']['memorix_rating']['enum'] == [1, 2, 3, 4]
        assert wire['properties']['error_analysis']['oneOf'][-1] == {'type': 'null'}
        assert 'SECRET_KEY' not in popen.call_args.kwargs['env']
        assert 'PRIVATE_SYNTHETIC_ANSWER' not in str(popen.call_args.args)
        for bad in ({**valid, 'score': float('nan')}, {**valid, 'memorix_rating': 8}, {'score': 8}):
            process.communicate.return_value = (json.dumps({'status': 200, 'result': bad}).encode(), b'')
            with pytest.raises(DshUnavailable):
                run_structured('quizzes.grade_question', '合成作答')
        process.pid = 123456789
        process.communicate.side_effect = [subprocess.TimeoutExpired('task', 120), (b'', b'')]
        with patch('ai_assistant.services.dsh_tasks.os.killpg') as kill:
            with pytest.raises(DshUnavailable):
                run_structured('quizzes.grade_question', '合成超时')
            kill.assert_called_once_with(process.pid, signal.SIGKILL)
        process.poll.return_value = None
        process.communicate.side_effect = [KeyboardInterrupt(), (b'', b'')]
        with patch('ai_assistant.services.dsh_tasks.os.killpg') as kill:
            with pytest.raises(KeyboardInterrupt):
                run_structured('quizzes.grade_question', '合成任务中断')
            kill.assert_called_once_with(process.pid, signal.SIGKILL)
    assert not list((tmp_path / 'tasks' / '.tasks').glob('*'))


@pytest.mark.django_db
def test_practice_reads_the_owned_session_and_saved_result(auth_client, user, settings):
    from django.core.cache import cache
    from rest_framework.test import APIClient
    from quizzes.models import Question, PracticeSubmission
    from users.models import CourseStudentStatus
    from uuid import uuid4
    CourseStudentStatus.objects.create(user=user, is_course_student=True)
    question = Question.objects.create(text='合成原会话题目')
    sid = uuid4().hex
    url = f'/api/ai/practice/session/{sid}/'
    cache.set(f'practice:session:{sid}', {'user_id': user.pk, 'questions': [{'id': question.pk, 'text': question.text}]})
    response = auth_client.get(url)
    assert response.status_code == 200
    assert response.json()['questions'] == [{'id': question.pk, 'text': question.text}]
    assert cache.get(f'practice:session:{sid}') is not None
    assert APIClient().get(url).status_code == 401
    other = type(user).objects.create_user(username='other-practice-owner')
    CourseStudentStatus.objects.create(user=other, is_course_student=True)
    client = APIClient(); client.force_authenticate(user=other)
    assert client.get(url).status_code == 403
    question.delete()
    assert auth_client.get(url).status_code == 403
    wrong_id = uuid4().hex
    PracticeSubmission.objects.create(user=user, session_id=wrong_id, answers_hash='synthetic-exam', response={'exam_id': 1})
    assert auth_client.get(f'/api/ai/practice/session/{wrong_id}/').status_code == 404
    PracticeSubmission.objects.create(user=user, session_id=sid, answers_hash='synthetic', response={'total_score': 8, 'results': []})
    cache.delete(f'practice:session:{sid}')
    assert auth_client.get(url).json()['result'] == {'total_score': 8, 'results': []}
