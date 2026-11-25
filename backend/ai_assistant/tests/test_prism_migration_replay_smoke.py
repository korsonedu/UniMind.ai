"""Synthetic checks for migration review and formal-key replay; no real model."""
from io import StringIO
import json
from unittest.mock import patch

import pytest
from django.core.management import call_command, CommandError
from rest_framework.exceptions import PermissionDenied, ValidationError

from ai_assistant.models import AIChatMessage, AgentMemory, AITrajectory, Bot, Experience, PrismMemory, PrismProposal
from ai_assistant.services import prism_memory, prism_migration
from ai_assistant.services.prism_replay import replay
from quizzes.models import Question


@pytest.fixture
def legacy(user, settings, monkeypatch):
    settings.UNIMIND_PRISM_MODE = 'active'
    settings.UNIMIND_CONTENT_INSTITUTION_ID = 'global'
    monkeypatch.setattr('ai_assistant.views._can_use_learning_context', lambda user: True)
    monkeypatch.setattr('ai_assistant.services.prism_replay.has_learning_feature', lambda user, feature: True)
    bot = Bot.objects.create(name='小宇', bot_type='planner', is_active=True)
    question = AIChatMessage.objects.create(user=user, bot=bot, role='user', content='请解释时间和比例的区别')
    trajectory = AITrajectory.objects.create(user=user, bot=bot, conversation_id=question.conversation_id,
        messages=[{'role': 'user', 'content': question.content}])
    experience = Experience.objects.create(user=user, trajectory=trajectory, dimension='prompt', scope_type='global',
        title='区分两种关系后再解释', confidence='high', effect={'instruction': '先区分时间关系和比例关系。'})
    return user, bot, question, experience


def spec():
    def rows(group):
        return [{'id': f'{group}-{kind}', 'verified': True, 'group': group,
                 'features': {'topic': 'relations', 'relation': kind}, 'behavior': {'explain': kind}}
                for kind in ('time', 'ratio')]
    return {'reviewed_source_match': True, 'fields': ['topic'], 'definitions': {'relation': '区分时间与比例关系。'},
            'training': rows('training'), 'validation': rows('validation'), 'test': rows('heldout')}


def test_reviewed_migration_stays_private_and_invalidates_changed_source(legacy):
    user, _, _, experience = legacy
    proposal = prism_migration.stage(user, 'experience', experience.pk, user)
    assert prism_migration.stage(user, 'experience', experience.pk, user).pk == proposal.pk
    assert not proposal.memory.active and proposal.memory.scope == 'student'
    assert 'instruction' not in json.dumps(proposal.payload)
    report = prism_migration.review(proposal.pk, user, spec())
    assert report['passed'] and report['test']['correct'] == 2
    assert len(list(prism_memory.checked_memories(user))) == 1
    experience.effect = {'instruction': '原依据已变更'}
    experience.save()
    assert list(prism_memory.checked_memories(user)) == []
    with pytest.raises(ValidationError):
        prism_migration.validate_origin(PrismMemory.objects.get(pk=proposal.memory_id))


def test_migration_checks_owner_disjoint_sources_and_no_automatic_activation(legacy):
    user, _, question, experience = legacy
    other = type(user).objects.create_user(username='migration-other')
    with pytest.raises(PermissionDenied):
        prism_migration.stage(user, 'experience', experience.pk, other)
    proposal = prism_migration.stage(user, 'experience', experience.pk, user)
    bad = spec()
    bad['test'][0]['group'] = 'training'
    with pytest.raises(ValidationError):
        prism_migration.review(proposal.pk, user, bad)
    bad = spec()
    bad['reviewed_source_match'] = False
    with pytest.raises(ValidationError):
        prism_migration.review(proposal.pk, user, bad)
    question.delete()
    with pytest.raises(ValidationError):
        prism_migration.review(proposal.pk, user, spec())
    assert not PrismMemory.objects.get(pk=proposal.memory_id).active


def test_formal_key_never_enters_model_and_identical_contexts_are_not_fake_gain(legacy):
    user, _, _, experience = legacy
    experience.status = 'retired'
    experience.save()
    AgentMemory.objects.create(user=user, key='解释偏好', value='先说明条件', source='manual')
    question = Question.objects.create(text='这是合成冒烟题，哪一项符合条件？', q_type='objective',
        options=['A. 条件成立', 'B. 条件不成立'], correct_answer='A', ai_answer='隐藏参考解析')
    before = AIChatMessage.objects.count()
    def answer(system, material, schema, max_tokens):
        assert set(material) == {'question', 'options', 'facts', 'memory'}
        assert '隐藏参考解析' not in json.dumps(material, ensure_ascii=False)
        json.dumps(material)  # Datetime-valued DB fields must not reach the wire.
        return {'answer': 'A'}, {'usage': None, 'observed_model': 'synthetic-smoke'}
    with patch('ai_assistant.services.teaching_shadow._call_model', side_effect=answer) as model:
        prepared = replay(user, [question.pk], data_origin='synthetic')
        assert prepared['status'] == 'prepared_no_answers_or_scores' and 'totals' not in prepared
        model.assert_not_called()
        result = replay(user, [question.pk], live_model=True, data_origin='synthetic')
        model.assert_called_once()
    assert result['memory_contrast_cases'] == 0 and result['paired_differences']['prism_minus_legacy'] == 0
    assert all(value == 1 for value in result['answer_key_accuracy'].values())
    assert AIChatMessage.objects.count() == before and not PrismProposal.objects.exists()


def test_replay_rejects_out_of_scope_bank_and_private_output_cannot_be_overwritten(legacy, settings, tmp_path):
    user, _, _, _ = legacy
    question = Question.objects.create(text='合成私有回放题', q_type='objective', options=['A.甲', 'B.乙'], correct_answer='A')
    path = tmp_path / 'private-replay.json'
    call_command('prism_replay', student=user.pk, reviewer=user.username, questions=[question.pk], output=str(path), stdout=StringIO())
    assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(CommandError):
        call_command('prism_replay', student=user.pk, reviewer=user.username, questions=[question.pk], output=str(path))
    settings.UNIMIND_CONTENT_INSTITUTION_ID = '999999'
    with pytest.raises(ValidationError):
        replay(user, [question.pk])
