"""Natural follow-up -> semantic proposal -> reviewed replay -> scoped publication."""
import copy
import json
from unittest.mock import patch

import pytest
from rest_framework.exceptions import PermissionDenied, ValidationError

from ai_assistant.models import AIChatMessage, Bot, PrismEpisode, PrismMemory, PrismProposal
from ai_assistant.services import prism_memory as prism
from ai_assistant.services.prism_feedback import propose_relations, propose_shared, review_relation, review_shared
from users.models import User


def references(prefix, group=None):
    return [{'id': f'{prefix}-{value}', 'verified': True,
             'features': {'topic': 'discount', 'question_focus': value}, 'behavior': {'explain': value},
             **({'group': group} if group else {})} for value in ('principle', 'rate')]


@pytest.fixture
def learning(db, monkeypatch, settings):
    settings.UNIMIND_PRISM_MODE = 'shadow'
    user = User.objects.create_user(username='feedback-learner')
    other = User.objects.create_user(username='other-learner')
    admin = User.objects.create_user(username='feedback-reviewer')
    monkeypatch.setattr('ai_assistant.views._can_use_learning_context', lambda user: True)
    monkeypatch.setattr('users.permissions.is_platform_admin', lambda user: user.pk == admin.pk)
    bot = Bot.objects.create(name='小宇', bot_type='planner', system_prompt='smoke')
    question = AIChatMessage.objects.create(user=user, bot=bot, role='user', content='为什么要折现？')
    answer = AIChatMessage.objects.create(user=user, bot=bot, role='assistant',
        conversation_id=question.conversation_id, content='先看折现原理。')
    source = PrismEpisode.objects.create(question=question, answer=answer,
        observation={'features': {'topic': 'discount'}, 'behavior': {'explain': 'principle'}, 'verified': False})
    followup = AIChatMessage.objects.create(user=user, bot=bot, role='user',
        conversation_id=question.conversation_id, content='我问的是为什么用这个利率。')
    reply = AIChatMessage.objects.create(user=user, bot=bot, role='assistant',
        conversation_id=question.conversation_id, content='这里需要解释利率的选择条件。')
    observation = {'features': {'topic': 'discount'}, 'behavior': {'explain': 'rate'}, 'verified': False,
        'previous_episode_id': source.pk, 'feedback': {'kind': 'clarification', 'distinctions': [{
            'key': 'question_focus', 'description': '区分操作原理与参数选择条件。',
            'source_value': 'principle', 'followup_value': 'rate',
            'source_evidence': '为什么要折现', 'followup_evidence': '为什么用这个利率'}]}}
    spec = {'training': references('train'), 'validation': references('validation')}
    public = {'public_system_cases': True, 'fields': ['question_focus'],
              'definitions': {'question_focus': 'Distinguish an operation principle from parameter choice.'},
              'training': references('public-train', 'course-a'),
              'validation': references('public-val', 'course-b'), 'test': references('public-test', 'course-c')}
    return {'user': user, 'other': other, 'admin': admin, 'source': source, 'question': followup, 'answer': reply,
            'observation': observation, 'spec': spec, 'public': public}


def candidate(data):
    ids = propose_relations(data['question'], data['observation'])
    return PrismProposal.objects.get(pk=ids[0])


def test_followup_capture_and_review_activate_defined_relation(learning):
    data = learning
    data['source'].observation = {'status': 'pending', 'verified': False}
    data['source'].save(update_fields=['observation'])
    with patch('ai_assistant.utils._THREAD_POOL.submit') as queue:
        prism.schedule(data['question'], data['answer'])
        queue.assert_called_once()
    assert data['question'].prism_episode.observation['status'] == 'pending'
    with patch.object(prism, 'extract', return_value=data['observation']), patch('django.db.connections.close_all'):
        prism.observe_completion(data['question'].pk, data['answer'].pk)
    assert PrismEpisode.objects.get(question=data['question']).observation['verified'] is False
    proposal = PrismProposal.objects.get()
    assert not proposal.memory.active and proposal.status == 'pending'
    assert proposal.question.prism_application.result['proposal_ids'] == [proposal.pk]
    assert not proposal.memory.cases
    report = review_relation(proposal.pk, data['user'], data['spec'])
    proposal.refresh_from_db()
    memory = proposal.memory
    assert report['selected']['added'] == 'question_focus'
    assert proposal.status == 'accepted' and memory.active and memory.revision == 2
    assert memory.definitions['question_focus'] == '区分操作原理与参数选择条件。'
    assert memory.operators
    with pytest.raises(ValidationError):
        review_relation(proposal.pk, data['user'], data['spec'])
    with patch('ai_assistant.services.dsh_tasks.run_structured', return_value={'features': [], 'behavior': []}) as model:
        prism.extract(data['question'], data['answer'])
        prompt = json.loads(model.call_args.args[1])
        assert prompt['known_relations']['question_focus'] == memory.definitions['question_focus']
        assert prompt['known_values']['question_focus'] == ['principle', 'rate']
        assert prompt['previous']['question'] == data['source'].question.content
        prism.extract(data['question'])
        assert json.loads(model.call_args.args[1])['previous']['question'] == data['source'].question.content


def test_unrelated_ungrounded_and_foreign_followups_do_not_create_proposals(learning):
    data = learning
    unrelated = copy.deepcopy(data['observation'])
    unrelated['feedback']['kind'] = 'unrelated'
    assert propose_relations(data['question'], unrelated) == []
    wrong = copy.deepcopy(data['observation'])
    wrong['feedback']['distinctions'][0]['followup_evidence'] = '不存在的原话'
    assert propose_relations(data['question'], wrong) == []
    foreign = AIChatMessage.objects.create(user=data['other'], bot=data['question'].bot, role='user',
        conversation_id=data['question'].conversation_id, content=data['question'].content)
    assert propose_relations(foreign, data['observation']) == []
    assert not PrismProposal.objects.exists()


def test_course_context_can_ground_task_relations_but_requires_current_access(learning):
    data = learning
    data['question'].metadata['course_context'] = {'course_id': 123, 'video_seconds': 90,
        'segments': [{'text': '本节讨论折现率的选择条件。'}]}
    result = {'features': [{'key': 'question_focus', 'value': 'rate', 'evidence': '折现率的选择条件'}], 'behavior': []}
    with patch.object(prism, 'accessible', return_value=True), \
            patch('ai_assistant.services.dsh_tasks.run_structured', return_value=result) as model:
        observation = prism.extract(data['question'])
        assert observation['features']['question_focus'] == 'rate'
        assert observation['feature_sources']['question_focus'] == 'course'
        assert '折现率' in json.loads(model.call_args.args[1])['material']
    with patch.object(prism, 'accessible', return_value=False), \
            patch('ai_assistant.services.dsh_tasks.run_structured') as model:
        assert prism.extract(data['question'])['features'] == {}
        model.assert_not_called()


def test_relation_review_checks_owner_revision_and_source_deletion(learning):
    data = learning
    proposal = candidate(data)
    with pytest.raises(PermissionDenied):
        review_relation(proposal.pk, data['other'], data['spec'])
    PrismMemory.objects.filter(pk=proposal.memory_id).update(revision=2)
    with pytest.raises(ValidationError):
        review_relation(proposal.pk, data['user'], data['spec'])
    data['source'].question.delete()
    assert not PrismProposal.objects.exists()


def test_failed_relation_replay_keeps_memory_inactive(learning):
    data = learning
    proposal = candidate(data)
    spec = copy.deepcopy(data['spec'])
    for case in spec['training'] + spec['validation']:
        case['features']['question_focus'] = 'same'
    report = review_relation(proposal.pk, data['user'], spec)
    proposal.refresh_from_db()
    assert report['selected'] is None and proposal.status == 'rejected'
    assert not proposal.memory.active and proposal.memory.definitions == {}


def test_stale_relation_can_only_rebase_with_current_revision_and_retained_references(learning):
    data = learning
    first = candidate(data)
    observation = copy.deepcopy(data['observation'])
    observation['feedback']['distinctions'][0]['key'] = 'answer_style'
    second = PrismProposal.objects.get(pk=propose_relations(data['question'], observation)[0])
    review_relation(first.pk, data['user'], data['spec'])
    def joint(prefix):
        return [{'id': f'{prefix}-{focus}-{style}', 'verified': True,
            'features': {'topic': 'discount', 'question_focus': focus, 'answer_style': style},
            'behavior': {'explain': focus if style == 'brief' else focus + '_expanded'}}
            for focus in ('principle', 'rate') for style in ('brief', 'detailed')]
    spec = {'expected_revision': 2, 'training': joint('joint-train'), 'validation': joint('joint-val'),
        'regression': [{**case, 'features': {**case['features'], 'answer_style': 'brief'}} for case in data['spec']['training']]}
    with pytest.raises(ValidationError):
        review_relation(second.pk, data['user'], {**spec, 'expected_revision': 1})
    broken = copy.deepcopy(spec)
    broken['regression'][0]['behavior'] = {'explain': 'overwritten'}
    with pytest.raises(ValidationError):
        review_relation(second.pk, data['user'], broken)
    report = review_relation(second.pk, data['user'], spec)
    assert report['regression']['correct'] == 2 and report['reviewed_revision'] == 2
    memory = PrismMemory.objects.get(pk=first.memory_id)
    assert memory.fields == ['question_focus', 'answer_style'] and memory.revision == 3


def test_shared_publication_uses_public_references_only(learning):
    data = learning
    relation = candidate(data)
    review_relation(relation.pk, data['user'], data['spec'])
    memory = PrismMemory.objects.get(pk=relation.memory_id)
    memory.definitions['private'] = 'PRIVATE-SENTINEL'
    memory.save(update_fields=['definitions'])
    with pytest.raises(PermissionDenied):
        propose_shared(memory.pk, 'system:focus', data['user'])
    proposal = propose_shared(memory.pk, 'system:focus', data['admin'])
    report = review_shared(proposal.pk, data['admin'], data['public'])
    shared = PrismMemory.objects.get(key='system:focus')
    assert report['passed'] and shared.scope == 'system' and shared.owner_id is None
    assert shared.cases == data['public']['training']
    assert 'PRIVATE-SENTINEL' not in json.dumps([shared.cases, shared.definitions, shared.operators])
    assert shared.definitions == data['public']['definitions']


def test_shared_validation_rejects_leakage_and_failed_holdout(learning):
    data = learning
    relation = candidate(data)
    review_relation(relation.pk, data['user'], data['spec'])
    proposal = propose_shared(relation.memory_id, 'system:blocked', data['admin'])
    leaked = copy.deepcopy(data['public'])
    leaked['training'][0]['source_message_id'] = data['source'].question_id
    with pytest.raises(ValidationError):
        review_shared(proposal.pk, data['admin'], leaked)
    overlap = copy.deepcopy(data['public'])
    overlap['test'][0]['group'] = 'course-a'
    with pytest.raises(ValidationError):
        review_shared(proposal.pk, data['admin'], overlap)
    reused = copy.deepcopy(data['public'])
    reused['training'][0]['id'] = data['spec']['training'][0]['id']
    with pytest.raises(ValidationError):
        review_shared(proposal.pk, data['admin'], reused)
    failed = copy.deepcopy(data['public'])
    failed['test'][0]['behavior']['explain'] = 'wrong'
    report = review_shared(proposal.pk, data['admin'], failed)
    assert not report['passed'] and not PrismMemory.objects.filter(key='system:blocked').exists()
