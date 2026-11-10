import uuid
from copy import deepcopy
from datetime import timedelta
from unittest.mock import patch
from django.test import override_settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from django.http import Http404
from rest_framework.test import APITestCase
from users.models import User
from ai_assistant.models import AIChatMessage, Bot, Conversation, ConversationProject, ProjectLearning, ProjectLearningEvent
from ai_assistant.services.project_learning import change_learning, completed_learning_turn, LearningConflict
from ai_assistant.services.learning_resources import find_resources
from ai_assistant.services.learning_library import resource_operation
from ai_assistant.services.learning_knowledge import knowledge_operation, knowledge_state
from ai_assistant.services.bayesian_evidence import belief
from ai_assistant.services.dsh_service import build_context, execute_tool, memory_snapshot


@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}, USE_MEM0=False,
                   UNIMIND_CONTENT_INSTITUTION_ID='global')
class LearningKnowledgeSmoke(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='knowledge_smoke', is_member=False)
        self.other = User.objects.create_user(username='knowledge_other')
        self.bot = Bot.objects.create(name='小宇', bot_type='planner')
        self.project = ConversationProject.objects.create(user=self.user, name='执行与分支')
        self.conversation = Conversation.objects.create(user=self.user, bot=self.bot, project=self.project, conversation_id=uuid.uuid4())
        with patch('ai_assistant.services.learning_resources.public_text', return_value=('https://example.org/flow', '<title>执行结构</title><p>程序按顺序执行指令。条件分支根据条件选择路径。</p>')):
            source = find_resources(self.project, {'url': 'https://example.org/flow'})['resource']
        self.resource = resource_operation(self.project, {'action': 'save', 'source_id': source['id']})['resource']
        self.nodes = [self.node('sequence', '顺序执行', [], '程序按顺序执行指令。'), self.node('branch', '条件分支', ['sequence'], '条件分支根据条件选择路径。')]
        self.version = knowledge_operation(self.project, {'action': 'save', 'title': '执行结构', 'nodes': self.nodes})
        self.turn('开始了解顺序与分支。')
        self.bind()
        self.client.force_authenticate(self.user)

    def node(self, key, title, parents, quote):
        return {'id': key, 'title': title, 'outcome': '能独立解释执行路径并给出理由', 'prerequisites': parents,
                'citation': {'resource_id': self.resource['id'], 'revision': 1, 'quote': quote}}

    def turn(self, text):
        self.message = AIChatMessage.objects.create(user=self.user, bot=self.bot, conversation_id=self.conversation.conversation_id, role='user', content=text)
        return self.message

    def bind(self, **overrides):
        prepared = knowledge_operation(self.project, {'action': 'prepare', 'version_id': self.version['version_id'], 'targets': ['branch'], 'depth': 'transfer'})
        plan = {'goal': '解释执行路径', 'weekly_minutes': 60, 'stages': [
            {'id': 'execution', 'title': '执行与条件', 'outcome': '独立解释路径', 'task': '解释一个程序', 'prerequisites': [],
             'sources': list(prepared['sources'].values()), 'knowledge_nodes': ['sequence', 'branch']}],
                'knowledge_path': prepared['knowledge_path']}
        plan.update(overrides)
        state = ProjectLearning.objects.get(project=self.project)
        return change_learning(self.project, {'action': 'plan', 'revision': state.revision, 'plan': plan}, message=self.message, model=True)

    def probe(self, node='sequence', question='执行 a=1 然后 a=a+2，请解释最后的 a 值。', mode='apply'):
        return knowledge_operation(self.project, {'action': 'probe', 'node_id': node, 'mode': mode,
            'question': question, 'rubric': '说明先赋值再增加二，结果为三，并解释顺序。'}, message=self.message)

    def present(self, probe, text=None, completed=True):
        AIChatMessage.objects.create(user=self.user, bot=self.bot, conversation_id=self.conversation.conversation_id, role='assistant',
            content=text or probe['question'], metadata={'learning_turn': completed_learning_turn(self.message.pk)} if completed else {})

    def progress(self, probe, outcome='success', assistance='independent', **overrides):
        state = ProjectLearning.objects.get(project=self.project)
        args = {'action': 'progress', 'revision': state.revision, 'observation': '解释了先后顺序', 'feedback': '已说明顺序，接下来换例子',
            'next_action': '解释另一个程序', 'assistance': assistance, 'strategy': '追踪变量',
            'knowledge_check': {'probe_id': probe['probe_id'], 'outcome': outcome, 'quote': self.message.content, 'reason': '对照先赋值再相加的标准，实际回答说明了先后顺序。'}}
        args.update(overrides)
        return change_learning(self.project, args, message=self.message, model=True)

    def test_bayes_directions_hint_staleness_and_separate_transfer(self):
        now = timezone.now()
        def result(outcome='success', help='independent', days=0):
            return belief([{'outcome': outcome, 'assistance': help, 'at': (now-timedelta(days=days)).isoformat()}], now)
        empty = belief([], now)
        self.assertAlmostEqual(empty['mean'], .5)
        self.assertGreater(result()['mean'], result(help='hint')['mean'])
        self.assertGreater(result(help='hint')['mean'], .5)
        self.assertLess(result('failure')['mean'], .5)
        self.assertEqual(result(help='guided')['effective_count'], 0)
        self.assertAlmostEqual(result(days=90)['mean']-.5, (result()['mean']-.5)/2)
        self.assertGreaterEqual(result()['information_gain'], 0)
        probe = self.probe(); self.present(probe)
        self.turn('先将 a 设为 1，再加 2，最后是 3。')
        data = self.progress(probe)['knowledge']
        self.assertGreater(data['nodes'][0]['beliefs']['apply']['mean'], .5)
        self.assertAlmostEqual(data['nodes'][0]['beliefs']['transfer']['mean'], .5)
        self.assertEqual(data['recommendations'][0]['node_id'], 'sequence')
        self.assertEqual(data['evidence'][0]['quote'], self.message.content)
        with self.assertRaises(ValidationError):
            self.progress(probe, outcome='failure')

    def test_map_cycles_quotes_ownership_and_immutable_versions(self):
        cycle = deepcopy(self.nodes); cycle[0]['prerequisites'] = ['branch']
        with self.assertRaises(ValidationError):
            knowledge_operation(self.project, {'action': 'save', 'title': '环', 'nodes': cycle})
        wrong = deepcopy(self.nodes); wrong[0]['citation']['quote'] = '这句没有在已读资料版本中出现。'
        with self.assertRaises(ValidationError):
            knowledge_operation(self.project, {'action': 'save', 'title': '伪引文', 'nodes': wrong})
        newer = knowledge_operation(self.project, {'action': 'save', 'title': '执行结构第二版', 'map_id': self.version['map_id'], 'revision': 1, 'nodes': self.nodes})
        self.assertEqual(knowledge_operation(self.project, {'action': 'read', 'version_id': self.version['version_id']})['title'], '执行结构')
        self.assertEqual(newer['revision'], 2)
        foreign = ConversationProject.objects.create(user=self.other, name='他人的项目')
        with self.assertRaises(Http404):
            knowledge_operation(foreign, {'action': 'read', 'version_id': self.version['version_id']})
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(f'/api/ai/projects/{self.project.pk}/learning/knowledge/').status_code, 404)

    def test_task_must_be_presented_in_completed_previous_turn(self):
        probe = self.probe()
        with self.assertRaises(ValidationError): self.progress(probe)
        self.present(probe, completed=False)
        self.turn('先赋值再加二，最后等于三。')
        with self.assertRaises(ValidationError): self.progress(probe)
        # A successful but unrelated answer also cannot unlock this task.
        AIChatMessage.objects.create(user=self.user, bot=self.bot, conversation_id=self.conversation.conversation_id,
            role='assistant', content='另一条回复', metadata={'learning_turn': completed_learning_turn(probe['probe_id'])})
        self.turn('我又独立检查了一次。')
        with self.assertRaises(ValidationError): self.progress(probe)
        self.assertFalse(ProjectLearningEvent.objects.filter(kind='progress').exists())

    def test_duplicate_question_answer_and_fabricated_quote_are_rejected(self):
        first = self.probe(); self.present(first)
        self.turn('先赋值为一，再加二，得到三。')
        self.progress(first)
        with self.assertRaises(ValidationError): self.probe()
        second = self.probe(question='执行 a=2 然后 a=a+3，请解释最后的 a 值。'); self.present(second)
        self.turn('先赋值为一，再加二，得到三。')
        with self.assertRaises(ValidationError): self.progress(second)
        self.turn('先赋值为二，再加三，得到五。')
        with self.assertRaises(ValidationError):
            self.progress(second, knowledge_check={'probe_id': second['probe_id'], 'outcome': 'success', 'quote': '不存在的原文', 'reason': '这里的原文没有实际用户回答依据。'})
        self.progress(second)

    def test_path_change_needs_confirmation_and_sources_stay_pinned(self):
        state = ProjectLearning.objects.get(project=self.project)
        old_source = next(row for row in state.resources if row.get('pinned'))
        with patch('ai_assistant.services.learning_resources.public_text', return_value=('https://example.org/flow', '<title>新版</title><p>重新读取的内容不覆盖旧版本。</p>')):
            find_resources(self.project, {'url': 'https://example.org/flow'})
        state.refresh_from_db()
        self.assertIn(old_source, state.resources)
        changed = self.bind(knowledge_path={'version_id': self.version['version_id'], 'targets': ['branch'], 'depth': 'apply'})
        self.assertEqual(changed['plan']['knowledge_path']['depth'], 'transfer')
        self.assertEqual(changed['pending_plan']['plan']['knowledge_path']['depth'], 'apply')
        accepted = change_learning(self.project, {'action': 'accept', 'revision': changed['revision']})
        self.assertEqual(accepted['plan']['knowledge_path']['depth'], 'apply')

    def test_tool_routing_budget_permission_and_late_write(self):
        context = {'message_id': self.message.pk, 'bot_id': self.bot.pk, 'conversation_id': str(self.message.conversation_id)}
        first = build_context(self.user, '请查看知识地图与贝叶斯证据路径', chat_context=context)
        self.assertLessEqual(len(first['tools']), 8)
        self.assertIn('manage_learning_knowledge', [item['function']['name'] for item in first['tools']])
        version = memory_snapshot(self.user)['version']
        response = execute_tool(self.user, 'manage_learning_knowledge', {'action': 'search'}, version, chat_context=context)
        self.assertNotIn('error', response)
        ProjectLearningEvent.objects.create(project=self.project, kind='turn')
        response = execute_tool(self.user, 'manage_learning_knowledge', {'action': 'probe', 'node_id': 'sequence', 'mode': 'apply', 'question': '解释一段实际程序的执行顺序。', 'rubric': '逐行说明变量的值与执行先后。'}, version, chat_context=context)
        self.assertIn('error', response)
        self.assertEqual(self.client.post(f'/api/ai/projects/{self.project.pk}/learning/knowledge/', {'action': 'probe'}, format='json').status_code, 400)

    def test_review_stages_use_first_learning_position(self):
        from ai_assistant.services.learning_knowledge import validate_path
        state = ProjectLearning.objects.get(project=self.project)
        plan = deepcopy(state.plan)
        base = plan['stages'][0]
        def stages(order):
            return [{**base, 'id': f's{index}', 'prerequisites': [], 'knowledge_nodes': [node]} for index, node in enumerate(order)]
        plan['stages'] = stages(['branch', 'sequence', 'branch'])
        with self.assertRaises(ValidationError): validate_path(self.project, state, plan)
        plan['stages'] = stages(['sequence', 'branch', 'sequence'])
        validate_path(self.project, state, plan)

    def test_removed_task_presentation_stops_contributing_to_estimate(self):
        probe = self.probe(); self.present(probe)
        self.turn('先赋值为二，再加三，得到五。')
        data = self.progress(probe)['knowledge']
        self.assertEqual(data['nodes'][0]['beliefs']['apply']['independent_count'], 1)
        AIChatMessage.objects.filter(role='assistant').delete()
        state = ProjectLearning.objects.get(project=self.project)
        data = knowledge_state(self.project, state)
        self.assertEqual(data['excluded_evidence_count'], 1)
        self.assertEqual(data['nodes'][0]['beliefs']['apply']['independent_count'], 0)
        self.assertAlmostEqual(data['nodes'][0]['beliefs']['apply']['mean'], .5)
