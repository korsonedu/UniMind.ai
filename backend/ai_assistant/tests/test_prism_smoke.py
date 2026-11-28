"""Focused smoke coverage for the SDTM mechanism and its DSH persistence seam."""
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.exceptions import ValidationError

from ai_assistant.models import (AIChatMessage, Bot, ConversationProject, LearningStrategy,
    LearningStrategyUse, ProjectLearningEvent, PrismApplication, PrismEpisode, PrismMemory)
from ai_assistant.services.prism_kernel import differentiate, induce, transfer
from ai_assistant.services import prism_memory as prism
from users.models import User


def reference(case_id, relation, surface='a'):
    return {'id': case_id, 'verified': True,
            'features': {'topic': 'arbitrary_rule', 'relation': relation, 'surface': surface},
            'behavior': {'explain': {'time': 'timeline', 'ratio': 'units'}[relation]}}


def test_differentiation_changes_representation_on_unseen_examples():
    train = [reference('a', 'time'), reference('b', 'ratio')]
    validation = [reference('v1', 'time', 'new'), reference('v2', 'ratio', 'new')]
    report = differentiate(train, validation, ['topic'])
    assert report['baseline']['unknown'] == 2
    assert report['selected']['fields'] == ['topic', 'relation']
    assert report['selected']['report']['correct'] == 2
    assert differentiate(train, validation, ['topic', 'relation'])['selected'] is None


def test_unseen_composition_and_missing_condition_abstention():
    fields = ['material', 'purpose', 'format']
    cases = []
    for i, changed in enumerate([None, *fields]):
        values = {key: 'changed' if key == changed else 'base' for key in fields}
        cases.append({'id': i, 'verified': True, 'features': values, 'behavior': values})
    result = transfer(cases, fields, dict.fromkeys(fields, 'changed'))
    assert result['status'] == 'matched'
    assert result['behavior'] == dict.fromkeys(fields, 'changed')
    assert len(result['operators']) == 2
    assert transfer(cases, fields, {'material': 'changed'})['reason'] == 'missing_conditions'


@override_settings(UNIMIND_PRISM_MODE='active')
class PrismSmoke(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='prism-student')
        self.other = User.objects.create_user(username='prism-other')
        self.bot = Bot.objects.create(name='小宇', bot_type='planner', system_prompt='smoke')
        self.question = AIChatMessage.objects.create(user=self.user, bot=self.bot, role='user', content='这里为什么这样算？')
        self.answer = AIChatMessage.objects.create(user=self.user, bot=self.bot, role='assistant',
            conversation_id=self.question.conversation_id, content='先检查时间单位。')
        check = patch('ai_assistant.views._can_use_learning_context', return_value=True)
        check.start()
        self.addCleanup(check.stop)
        self.train = [reference('a', 'time'), reference('b', 'ratio')]

    def memory(self, key='public', owner=None, cases=None, fields=None):
        cases, fields = cases or self.train, fields or ['topic', 'relation']
        return PrismMemory.objects.create(key=key, owner=owner, scope='student' if owner else 'system',
            fields=fields, cases=cases, operators=induce(cases, fields))

    def test_dual_scope_isolation_and_frozen_version(self):
        shared = self.memory()
        self.memory('private-other', owner=self.other)
        own = self.memory('private-self', owner=self.user)
        with patch.object(prism, 'extract', return_value={'features': self.train[0]['features']}):
            prism.prepare(self.question)
            prism.prepare(self.question)
        self.assertEqual(PrismApplication.objects.count(), 1)
        packet = prism.context(self.question)
        self.assertEqual({row['key'] for row in packet['memories']}, {shared.key, own.key})
        shared.revision += 1
        shared.save()
        self.assertEqual([row['key'] for row in prism.context(self.question)['memories']], [own.key])

    def test_growth_filters_relevance_and_invalid_sources_before_search_budget(self):
        for index in range(12):
            self.memory(f'a-{index}', cases=[{**row, 'features': {**row['features'], 'topic': f'other-{index}'}} for row in self.train])
            self.memory(f'bad-{index}', owner=self.user,
                cases=[{**row, 'source_message_id': 999999} for row in self.train])
        target = self.memory('z-target')
        packet = prism.packet_for(self.question, self.train[0]['features'])
        self.assertEqual([row['key'] for row in packet['memories']], [target.key])
        self.assertEqual(packet['decision']['behavior'], {'explain': 'timeline'})
        self.question.content = 'other-11'
        with patch('ai_assistant.services.dsh_tasks.run_structured', return_value={'features': [], 'behavior': []}) as model:
            prism.extract(self.question)
            import json
            self.assertEqual(json.loads(model.call_args.args[1])['known_values']['topic'][0], 'other-11')

    def test_behavior_plan_resolves_scope_and_rechecks_revoked_sources(self):
        self.memory('a-public')
        private = self.memory('own', owner=self.user, cases=[{**row, 'source_message_id': self.question.pk,
            'behavior': {'explain': 'personal'}} for row in self.train])
        following = AIChatMessage.objects.create(user=self.user, bot=self.bot, role='user', content='继续')
        with patch.object(prism, 'extract', return_value={'features': self.train[0]['features']}):
            prism.prepare(following)
        self.assertEqual(prism.context(following)['decision']['behavior'], {'explain': 'personal'})
        self.memory('b-conflicting', cases=[{**row, 'behavior': {'explain': 'conflict'}} for row in self.train])
        packet = prism.packet_for(following, self.train[0]['features'])
        self.assertEqual(packet['decision']['behavior'], {'explain': 'personal'})
        self.question.delete()
        self.assertEqual(prism.context(following)['decision']['behavior'], {'explain': 'timeline'})
        packet = prism.packet_for(following, self.train[0]['features'])
        self.assertEqual(packet['decision']['behavior'], {})
        self.assertEqual(set(packet['decision']['conflicts']['explain']), {'timeline', 'conflict'})

    def test_private_evidence_not_promoted_and_deleted_sources_not_recalled(self):
        cases = [{**row, 'source_message_id': self.question.pk} for row in self.train]
        self.memory(cases=cases)
        self.memory('personal', owner=self.user, cases=cases)
        next_question = AIChatMessage.objects.create(user=self.user, bot=self.bot, role='user', content='继续')
        self.assertEqual([row['key'] for row in prism.packet_for(next_question, cases[0]['features'])['memories']], ['personal'])
        self.question.delete()
        self.assertEqual(prism.packet_for(next_question, cases[0]['features'])['memories'], [])
        with patch('ai_assistant.services.dsh_tasks.run_structured', return_value={'features': [], 'behavior': []}) as model:
            prism.extract(next_question)
            import json
            self.assertEqual(json.loads(model.call_args.args[1])['known_values'], {})

    def test_existing_methods_are_scoped_candidates_with_revocable_frozen_sources(self):
        project = ConversationProject.objects.create(user=self.user, name='合成任务')
        event = ProjectLearningEvent.objects.create(project=project, message=self.question,
            kind='progress', content={'strategy': '先统一时间单位，再代入公式'})
        method = LearningStrategy.objects.create(user=self.user, source_event=event, topic='时间')
        other_project = ConversationProject.objects.create(user=self.other, name='他人任务')
        other_source = AIChatMessage.objects.create(user=self.other, bot=self.bot, role='user', content='时间')
        other_event = ProjectLearningEvent.objects.create(project=other_project, message=other_source,
            kind='progress', content={'strategy': '他人方法'})
        LearningStrategy.objects.create(user=self.other, source_event=other_event, topic='时间')
        next_question = AIChatMessage.objects.create(user=self.user, bot=self.bot, role='user', content='时间为什么要换算？')
        with patch.object(prism, 'extract', return_value={'features': {}}):
            prism.prepare(next_question)
        packet = prism.context(next_question)
        self.assertEqual([row['id'] for row in packet['methods']], [method.pk])
        self.assertEqual(packet['methods'][0]['status'], 'candidate_not_verified')
        self.assertEqual(packet['memories'], [])
        self.assertFalse(LearningStrategyUse.objects.exists())
        event.content = {'strategy': '已更改的方法'}
        event.save()
        self.assertEqual(prism.context(next_question)['methods'], [])
        self.assertEqual(prism.packet_for(next_question, {})['methods'][0]['method'], '已更改的方法')
        method.is_retired = True
        method.save()
        self.assertEqual(prism.packet_for(next_question, {})['methods'], [])
        method.is_retired = False
        method.save()
        self.question.metadata = {'notes_context_used': True}
        self.question.save()
        self.assertEqual(prism.packet_for(next_question, {})['methods'], [])
        self.question.delete()
        self.assertEqual(prism.packet_for(next_question, {})['methods'], [])

    def test_account_deletion_clears_private_core_even_without_message_sources(self):
        from rest_framework.test import APIClient
        self.user.set_password('PrismSmoke123!')
        self.user.save()
        own = self.memory('delete-own', owner=self.user)
        shared = self.memory('retain-shared')
        other = self.memory('retain-other', owner=self.other)
        PrismEpisode.objects.create(question=self.question, answer=self.answer, observation={})
        PrismApplication.objects.create(question=self.question, packet={})
        client = APIClient()
        client.force_authenticate(self.user)
        self.assertEqual(client.post('/api/users/me/delete/', {'password': 'PrismSmoke123!'}, format='json').status_code, 200)
        self.assertFalse(PrismMemory.objects.filter(pk=own.pk).exists())
        self.assertEqual(set(PrismMemory.objects.values_list('pk', flat=True)), {shared.pk, other.pk})
        self.assertFalse(PrismEpisode.objects.exists())
        self.assertFalse(PrismApplication.objects.exists())

    def test_refinement_is_revision_checked_and_materializes_new_operators(self):
        memory = self.memory(owner=self.user, fields=['topic'])
        validation = [reference('v1', 'time'), reference('v2', 'ratio')]
        prism.refine(memory.pk, 1, self.train, validation)
        memory.refresh_from_db()
        self.assertEqual(memory.fields, ['topic', 'relation'])
        self.assertTrue(memory.operators)
        self.assertEqual(memory.revisions.count(), 1)
        with self.assertRaises(ValidationError):
            prism.refine(memory.pk, 1, self.train, validation)
        with self.assertRaises(ValueError):
            prism.refine(memory.pk, 2, [{**row, 'verified': False} for row in self.train], validation)

    @override_settings(UNIMIND_PRISM_MODE='shadow')
    def test_shadow_observes_once_without_injection_or_self_certification(self):
        observation = {'features': self.train[0]['features'], 'behavior': {'explain': 'timeline'}, 'verified': False}
        with patch.object(prism, 'extract', return_value=observation) as extract, patch('django.db.connections.close_all'):
            prism.prepare(self.question)
            prism.observe_completion(self.question.pk, self.answer.pk)
            prism.observe_completion(self.question.pk, self.answer.pk)
            extract.assert_called_once()
        self.assertEqual(PrismEpisode.objects.count(), 1)
        self.assertFalse(PrismMemory.objects.exists())
        self.assertEqual(prism.context(self.question), {})
        self.assertIn('shadow_packet', PrismApplication.objects.get().result)
        self.question.delete()
        self.assertFalse(PrismEpisode.objects.exists())
        self.assertFalse(PrismApplication.objects.exists())

    def test_observation_evidence_must_quote_the_corresponding_source(self):
        rows = [{'key': 'goal', 'value': 'explain', 'evidence': self.question.content},
                {'key': 'trait', 'value': 'weak', 'evidence': 'not in the source'}]
        self.assertEqual(prism.grounded(rows, self.question.content), {'goal': 'explain'})
        self.memory(cases=[{**row, 'verified': False} for row in self.train])
        self.assertEqual(prism.packet_for(self.question, self.train[0]['features'])['memories'], [])

    def test_notes_context_is_excluded_and_off_mode_has_no_model_calls(self):
        self.question.metadata = {'notes_context_used': True}
        self.question.save(update_fields=['metadata'])
        with patch.object(prism, 'extract') as extract:
            prism.prepare(self.question)
            extract.assert_not_called()
        with override_settings(UNIMIND_PRISM_MODE='off'), patch.object(prism, 'extract') as extract:
            prism.prepare(self.question)
            self.assertEqual(prism.context(self.question), {})
            extract.assert_not_called()
            from ai_assistant.services.dsh_xiaoyu import task_context
            claims = {'message_id': self.question.pk, 'conversation_id': str(self.question.conversation_id),
                      'bot_id': self.bot.pk}
            with patch('ai_assistant.services.dsh_xiaoyu.prepare_note_context', return_value=('', [])):
                self.assertNotIn('"prism"', task_context(self.user, claims, self.question.content))
