from unittest.mock import patch
from uuid import uuid4

import pytest

from quizzes.models import KnowledgePoint, Question


@pytest.mark.django_db
def test_ulr_only_saves_completed_text_as_a_question_reference_answer(admin_client, admin_user, user, settings):
    settings.UNIMIND_LEARNING_RUNTIME = 'ulr'
    settings.UNIMIND_DSH_GENERATION_ENABLED = False
    settings.UNIMIND_CONTENT_INSTITUTION_ID = 'global'
    settings.UNIMIND_DIRECTUS_ADMIN_MAP = {str(uuid4()): admin_user.pk, str(uuid4()): user.pk}
    point = KnowledgePoint.objects.create(name='合成折现率考点', level='kp')
    answer = '把未来现金流折算到同一时点。'
    cases = [
        ({'message': {'content': '尚未生成完的参考答案'}}, ''),
        ({'finish_reason': 'stop', 'message': {'content': None, 'reasoning_content': '内部推算过程'}}, ''),
        ({'finish_reason': 'stop', 'message': {'content': '继续调用工具', 'tool_calls': [
            {'type': 'function', 'function': {'name': 'lookup_question', 'arguments': '{}'}},
        ]}}, ''),
        ({'finish_reason': 'length', 'message': {'content': '达输出上限的参考答案'}}, ''),
        ({'finish_reason': 'stop', 'message': {'content': answer}}, answer),
    ]
    with (
        patch('ai_engine.service.AIEngine.call_provider') as provider,
        patch('ai_assistant.services.dsh_generation.generate') as dsh,
    ):
        for index, (choice, expected) in enumerate(cases):
            provider.return_value = {'choices': [choice]}
            response = admin_client.post('/api/quizzes/questions/', {
                'knowledge_point': point.pk, 'text': f'合成参考答案题目 {index}', 'q_type': 'subjective',
            }, format='json')
            assert response.status_code == 201, response.data
            assert (Question.objects.get(pk=response.data['id']).ai_answer or '') == expected
        assert provider.call_count == len(cases)
        assert all(call.kwargs['max_retries'] == 0 for call in provider.call_args_list)
    dsh.assert_not_called()
