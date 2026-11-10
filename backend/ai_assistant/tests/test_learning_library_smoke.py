import uuid
from unittest.mock import patch
from django.test import override_settings
from rest_framework.test import APITestCase
from rest_framework.exceptions import ValidationError
from users.models import User
from ai_assistant.models import (AIChatMessage, Bot, Conversation, ConversationProject, ProjectLearning,
    ProjectLearningEvent, LearningResource, LearningStrategy, LearningStrategyReview)
from ai_assistant.views_projects import save_new_conversation_project
from ai_assistant.services.project_learning import change_learning, turn_project_context, LearningConflict
from ai_assistant.services.learning_resources import find_resources
from ai_assistant.services.learning_library import resource_operation, strategy_operation, library_data
from ai_assistant.services.dsh_service import build_context, execute_tool, memory_snapshot
from types import SimpleNamespace


@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}, USE_MEM0=False,
                   UNIMIND_CONTENT_INSTITUTION_ID='global')
class LearningLibrarySmoke(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='library_personal', is_member=False)
        self.other = User.objects.create_user(username='library_other')
        self.bot = Bot.objects.create(name='小宇', bot_type='planner')
        self.project = ConversationProject.objects.create(user=self.user, name='函数概念')
        self.target = ConversationProject.objects.create(user=self.user, name='换个场景学习')
        self.plan = {'goal': '解释函数的单值对应', 'weekly_minutes': 120, 'deadline': None, 'stages': [
            {'id': 'concept', 'title': '函数概念', 'outcome': '独立判断一个新例子', 'task': '解释一个关系', 'prerequisites': [], 'sources': []}]}
        self.message = self.turn(self.project, '每个输入只能对应一个输出。')
        self.prepare(self.project, self.message)
        self.event = self.progress(self.project, self.message)
        self.client.force_authenticate(self.user)
        self.url = f'/api/ai/projects/{self.project.pk}/learning/library/'
        with patch('ai_assistant.services.learning_resources.public_text', return_value=('https://example.org/functions', '<title>函数教材</title><p>函数表示单值对应关系。</p>')):
            self.resource = find_resources(self.project, {'url': 'https://example.org/functions'})['resource']

    def turn(self, project, text):
        conversation = Conversation.objects.filter(project=project).first()
        if conversation is None:
            conversation = Conversation.objects.create(user=self.user, bot=self.bot, project=project, conversation_id=uuid.uuid4())
        save_new_conversation_project(SimpleNamespace(user=self.user, data={'project_id': project.pk}), self.bot, conversation.conversation_id)
        return AIChatMessage.objects.create(user=self.user, bot=self.bot, conversation_id=conversation.conversation_id, role='user', content=text)

    def prepare(self, project, message):
        revision = ProjectLearning.objects.get(project=project).revision
        return change_learning(project, {'action': 'plan', 'revision': revision, 'plan': self.plan}, message=message)

    def progress(self, project, message, assistance='independent'):
        state = ProjectLearning.objects.get(project=project)
        change_learning(project, {'action': 'progress', 'revision': state.revision, 'observation': '能解释单值条件，迁移例子仍需检验',
            'feedback': '已解释条件，下一步看新例子。', 'assistance': assistance, 'strategy': '先解释再判断变式例子',
            'next_action': '判断一个新关系'}, message=message, model=True)
        return ProjectLearningEvent.objects.filter(project=project, message=message, kind='progress').first()

    def save_strategy(self):
        return strategy_operation(self.project, {'action': 'save', 'event_id': self.event.pk, 'domain': '数学'})['strategy_id']

    def test_owned_resource_reuse_keeps_traceable_project_snapshot(self):
        saved = self.client.post(self.url, {'kind': 'resource', 'action': 'save', 'source_id': self.resource['id'], 'domain': '数学'}, format='json')
        self.assertEqual(saved.status_code, 200)
        row = saved.data['resource']
        self.assertFalse(self.client.post(self.url, {'kind': 'resource', 'action': 'save', 'source_id': self.resource['id']}, format='json').data['created'])
        attached = resource_operation(self.target, {'action': 'attach', 'resource_id': row['id']})['resource']
        self.assertNotEqual(attached['id'], self.resource['id'])
        self.assertEqual(attached['read_at'], self.resource['read_at'])
        self.assertEqual(attached['library_revision'], 1)
        message = self.turn(self.target, '在另一个例子里继续。')
        plan = {**self.plan, 'stages': [{**self.plan['stages'][0], 'sources': [attached['id']]}]}
        result = change_learning(self.target, {'action': 'plan', 'revision': 0, 'plan': plan}, message=message)
        self.assertEqual(result['plan']['stages'][0]['sources'], [attached['id']])

    def test_archive_privacy_revision_and_old_snapshot_do_not_overwrite(self):
        row = resource_operation(self.project, {'action': 'save', 'source_id': self.resource['id']})['resource']
        attached = resource_operation(self.target, {'action': 'attach', 'resource_id': row['id']})['resource']
        resource_operation(self.project, {'action': 'archive', 'resource_id': row['id'], 'revision': 1})
        with self.assertRaises(ValidationError):
            resource_operation(self.target, {'action': 'attach', 'resource_id': row['id']})
        with self.assertRaises(LearningConflict):
            resource_operation(self.project, {'action': 'restore', 'resource_id': row['id'], 'revision': 1})
        resource_operation(self.project, {'action': 'restore', 'resource_id': row['id'], 'revision': 2})
        with patch('ai_assistant.services.learning_resources.public_text', return_value=('https://example.org/functions', '<title>新版教材</title><p>新读取的内容。</p>')):
            newer = find_resources(self.project, {'url': self.resource['url']})['resource']
        resource_operation(self.project, {'action': 'save', 'source_id': newer['id'], 'revision': 3})
        self.assertEqual(ProjectLearning.objects.get(project=self.target).resources[0]['excerpt'], attached['excerpt'])
        with self.assertRaises(LearningConflict):
            resource_operation(self.target, {'action': 'save', 'source_id': attached['id'], 'revision': 4})
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        foreign = ConversationProject.objects.create(user=self.other, name='私有目标')
        self.assertEqual(self.client.post(f'/api/ai/projects/{foreign.pk}/learning/library/', {'kind': 'resource', 'action': 'attach', 'resource_id': row['id']}, format='json').status_code, 404)

    def test_method_review_needs_later_actual_independent_evidence(self):
        strategy_id = self.save_strategy()
        trigger = self.turn(self.target, '请在这个项目试用以前的方法。')
        self.prepare(self.target, trigger)
        use_id = strategy_operation(self.target, {'action': 'apply', 'strategy_id': strategy_id, 'reason': '同样需要区分定义和例子'}, message=trigger)['use_id']
        same_turn = self.progress(self.target, trigger)
        with self.assertRaises(ValidationError):
            strategy_operation(self.target, {'action': 'review', 'use_id': use_id, 'event_id': same_turn.pk, 'judgement': 'support', 'reason': '不能用本轮冒充后续'}, message=trigger)
        AIChatMessage.objects.create(user=self.user, bot=self.bot, conversation_id=trigger.conversation_id, role='assistant', content='请先说清定义，再判断这个新例子。')
        later = self.turn(self.target, '有提示后我才知道怎么判断。')
        hinted = self.progress(self.target, later, 'hint')
        args = {'action': 'review', 'use_id': use_id, 'event_id': hinted.pk, 'judgement': 'support', 'reason': '仍有提示'}
        with self.assertRaises(ValidationError):
            strategy_operation(self.target, args, message=later)
        args['judgement'] = 'uncertain'
        self.assertTrue(strategy_operation(self.target, args, message=later)['created'])
        self.assertFalse(strategy_operation(self.target, args, message=later)['created'])
        duplicate = self.progress(self.target, later, 'hint')
        self.assertFalse(strategy_operation(self.target, {**args, 'event_id': duplicate.pk}, message=later)['created'])
        independent = self.turn(self.target, '我独立判断了新的对应关系，并给出了理由。')
        evidence = self.progress(self.target, independent)
        strategy_operation(self.target, {'action': 'review', 'use_id': use_id, 'event_id': evidence.pk, 'judgement': 'support', 'reason': '在新例子中独立解释条件'}, message=independent)
        result = library_data(self.user)['strategies'][0]
        self.assertEqual(result['counts'], {'support': 1, 'against': 0, 'uncertain': 1})
        self.assertEqual(result['context']['goal'], self.plan['goal'])
        self.assertEqual(LearningStrategyReview.objects.count(), 2)

    def test_retirement_and_removed_source_stop_new_recommendation(self):
        strategy_id = self.save_strategy()
        strategy_operation(self.project, {'action': 'retire', 'strategy_id': strategy_id, 'revision': 1})
        trigger = self.turn(self.project, '再试一次。')
        with self.assertRaises(ValidationError):
            strategy_operation(self.project, {'action': 'apply', 'strategy_id': strategy_id, 'reason': '不应采用停用方法'}, message=trigger)
        self.assertFalse(library_data(self.user, compact=True)['strategies'])
        strategy_operation(self.project, {'action': 'restore', 'strategy_id': strategy_id, 'revision': 2})
        self.message.delete()
        self.assertFalse(library_data(self.user, compact=True)['strategies'])
        self.assertFalse(library_data(self.user)['strategies'][0]['available'])

    def test_new_library_tool_contract_stable_context_and_superseded_write(self):
        context = {'message_id': self.message.pk, 'bot_id': self.bot.pk, 'conversation_id': str(self.message.conversation_id)}
        first = build_context(self.user, '继续目标学习', chat_context=context)
        self.assertLessEqual(len(first['tools']), 8)
        version = memory_snapshot(self.user)['version']
        result = execute_tool(self.user, 'manage_learning_resources', {'action': 'save', 'source_id': self.resource['id']}, version, chat_context=context)
        self.assertNotIn('error', result)
        second = build_context(self.user, '继续目标学习', chat_context=context)
        self.assertEqual(first['student'], second['student'])
        self.assertEqual(first['system_prompt'], second['system_prompt'])
        self.turn(self.project, '先改用其他材料。')
        result = execute_tool(self.user, 'manage_learning_strategies', {'action': 'save', 'event_id': self.event.pk}, version, chat_context=context)
        self.assertIn('error', result)
        self.assertEqual(LearningStrategy.objects.count(), 0)

    def test_api_cannot_fabricate_method_trial_or_review(self):
        strategy_id = self.save_strategy()
        result = self.client.post(self.url, {'kind': 'strategy', 'action': 'apply', 'strategy_id': strategy_id, 'reason': '伪造试用'}, format='json')
        self.assertEqual(result.status_code, 400)
        self.assertEqual(self.client.post(self.url, {'kind': 'strategy', 'action': 'save', 'event_id': 999999}, format='json').status_code, 404)
        self.assertEqual(LearningResource.objects.count(), 0)
