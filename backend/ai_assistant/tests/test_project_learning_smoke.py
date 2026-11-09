import uuid
from datetime import timedelta
from unittest.mock import patch
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework.exceptions import ValidationError
from ai_assistant.models import AIChatMessage, Bot, Conversation, ConversationProject, ProjectLearning, ProjectLearningEvent
from ai_assistant.services.project_learning import change_learning, current_project, turn_project_context
from ai_assistant.services.dsh_service import build_context, execute_tool, memory_snapshot
from ai_assistant.services.learning_resources import find_resources, public_text
from ai_assistant.tasks_learning import send_project_learning_followups
from notifications.models import Notification
from users.models import User


@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
                   USE_MEM0=False, UNIMIND_CONTENT_INSTITUTION_ID='global')
class ProjectLearningSmoke(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='goal_learner', is_member=False)
        self.other = User.objects.create_user(username='other_goal_learner', is_member=False)
        self.bot = Bot.objects.create(name='小宇', bot_type='planner')
        self.project = ConversationProject.objects.create(user=self.user, name='高中数学', instructions='学会函数概念')
        self.conversation = Conversation.objects.create(user=self.user, bot=self.bot, project=self.project, conversation_id=uuid.uuid4())
        self.message = AIChatMessage.objects.create(user=self.user, bot=self.bot, conversation_id=self.conversation.conversation_id,
            role='user', content='我认为每个输入应该对应唯一的输出。')
        self.state = ProjectLearning.objects.create(project=self.project, last_conversation=self.conversation)
        self.context = {'message_id': self.message.pk, 'conversation_id': str(self.conversation.conversation_id), 'bot_id': self.bot.pk}
        self.plan = {'goal': '理解函数', 'deadline': None, 'weekly_minutes': 120, 'stages': [
            {'id': 'function', 'title': '函数概念', 'outcome': '解释输入与输出的关系', 'task': '解释一个具体例子', 'prerequisites': [], 'sources': []},
            {'id': 'graph', 'title': '函数图像', 'outcome': '从图像解释函数', 'task': '读一张图', 'prerequisites': ['function'], 'sources': []}]}
        self.client.force_authenticate(self.user)
        self.url = f'/api/ai/projects/{self.project.pk}/learning/'

    def make_plan(self):
        return change_learning(self.project, {'action': 'plan', 'revision': 0, 'plan': self.plan, 'next_action': '解释一个具体例子'}, message=self.message)

    def test_personal_access_project_privacy_and_revision(self):
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.make_plan()
        self.assertEqual(self.client.patch(self.url, {'action': 'pause', 'revision': 0}, format='json').status_code, 409)
        foreign = ConversationProject.objects.create(user=self.other, name='私人目标')
        self.assertEqual(self.client.get(f'/api/ai/projects/{foreign.pk}/learning/').status_code, 404)
        with self.assertRaises(Exception):
            current_project(self.other, self.context)
        self.assertEqual(self.client.patch(self.url, {'action': 'pause', 'revision': 1}, format='json').data['status'], 'paused')

    def test_real_dsh_tool_contract_records_bound_evidence_and_replay(self):
        context = build_context(self.user, '继续这个学习目标', chat_context=self.context)
        self.assertEqual(context['routing']['initial_group'], 'project')
        version = memory_snapshot(self.user)['version']
        result = execute_tool(self.user, 'plan_learning_project', {'revision': 0, 'plan': self.plan,
            'next_action': '解释一个具体例子', 'reason': '先从概念开始', 'major_change': False}, version, chat_context=self.context)
        self.assertNotIn('error', result)
        arguments = {'revision': 1, 'observation': '能说出单值对应关系，还需用新例子检验', 'feedback': '已经说清基本条件，下一步看新例子。',
            'assistance': 'independent', 'strategy': '让用户先解释再给变式', 'next_action': '判断另一个关系是否构成函数'}
        result = execute_tool(self.user, 'record_learning_progress', arguments, version, chat_context=self.context)
        self.assertNotIn('error', result)
        again = execute_tool(self.user, 'record_learning_progress', arguments, version, chat_context=self.context)
        self.assertEqual(result['revision'], again['revision'])
        event = ProjectLearningEvent.objects.get(project=self.project, kind='progress')
        self.assertEqual(event.message_id, self.message.pk)
        self.assertEqual(result['events'][0]['source']['text'], self.message.content)

    def test_major_change_needs_actual_user_acceptance(self):
        self.make_plan()
        revised = {**self.plan, 'goal': '系统学习高中数学', 'weekly_minutes': 300}
        result = change_learning(self.project, {'action': 'plan', 'revision': 1, 'plan': revised, 'reason': '扩大目标'}, message=self.message)
        self.assertEqual(result['plan']['goal'], self.plan['goal'])
        self.assertTrue(result['pending_plan'])
        accepted = self.client.patch(self.url, {'action': 'accept', 'revision': 2}, format='json')
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.data['plan']['goal'], revised['goal'])

    def test_followup_without_frontend_is_idempotent_and_pause_cancels(self):
        self.make_plan()
        ProjectLearning.objects.filter(pk=self.state.pk).update(followup_at=timezone.now() - timedelta(seconds=1), followup_text='上次的函数条件已经说清楚，今天换个例子试试。')
        self.assertEqual(send_project_learning_followups()['sent'], 1)
        self.assertEqual(send_project_learning_followups()['sent'], 0)
        notification = Notification.objects.get(recipient=self.user)
        self.assertIn(f'project={self.project.pk}', notification.link)
        self.assertTrue(AIChatMessage.objects.filter(metadata__learning_followup__project_id=self.project.pk).exists())
        state = self.client.get(self.url).data
        self.client.patch(self.url, {'action': 'pause', 'revision': state['revision']}, format='json')
        self.assertIsNone(ProjectLearning.objects.get(pk=self.state.pk).followup_at)
        self.assertEqual(send_project_learning_followups()['sent'], 0)

    def test_sources_must_be_read_and_private_hosts_are_blocked(self):
        bad = {**self.plan, 'stages': [{**self.plan['stages'][0], 'sources': ['invented']}]}
        with self.assertRaises(ValidationError):
            change_learning(self.project, {'action': 'plan', 'revision': 0, 'plan': bad}, message=self.message)
        with patch('ai_assistant.services.learning_resources.public_text', return_value=('https://example.org/lesson', '<html><title>函数教材</title><p>函数表示对应关系。</p></html>')):
            resource = find_resources(self.project, {'url': 'https://example.org/lesson'})['resource']
        self.assertIn('对应关系', resource['excerpt'])
        with patch('socket.getaddrinfo', return_value=[(2, 1, 6, '', ('127.0.0.1', 443))]):
            with self.assertRaises(ValidationError):
                public_text('https://localhost/private')

    def test_user_reply_invalidates_old_followup_and_project_course_history_remains_visible(self):
        self.make_plan()
        self.message.metadata = {'course_context': {'course_id': 999}}
        self.message.save()
        from ai_assistant.views_projects import save_new_conversation_project
        from types import SimpleNamespace
        save_new_conversation_project(SimpleNamespace(user=self.user, data={'project_id': self.project.pk}), self.bot, self.conversation.conversation_id)
        self.assertIsNone(ProjectLearning.objects.get(pk=self.state.pk).followup_at)
        history = self.client.get('/api/ai/history/', {'bot_id': self.bot.pk})
        self.assertEqual(history.status_code, 200)
        self.assertIn(self.message.pk, [row['id'] for row in history.data])
        self.project.delete()
        self.assertEqual(send_project_learning_followups()['sent'], 0)

    def test_turn_snapshot_stays_stable_after_own_tools_and_rejects_project_move(self):
        from ai_assistant.services.dsh_xiaoyu import task_context
        from rest_framework.exceptions import PermissionDenied
        first = build_context(self.user, self.message.content, chat_context=self.context)
        first['system_prompt'] += task_context(self.user, self.context, self.message.content)
        self.make_plan()
        second = build_context(self.user, self.message.content, chat_context=self.context)
        second['system_prompt'] += task_context(self.user, self.context, self.message.content)
        self.assertEqual(first['student'], second['student'])
        self.assertEqual(first['system_prompt'], second['system_prompt'])
        self.assertEqual(first['permissions_version'], second['permissions_version'])
        new_project = ConversationProject.objects.create(user=self.user, name='另一个目标')
        self.conversation.project = new_project
        self.conversation.save(update_fields=['project'])
        with self.assertRaises(PermissionDenied):
            current_project(self.user, self.context)
        with self.assertRaises(PermissionDenied):
            turn_project_context(self.user, self.context)

    def test_context_does_not_repeat_historical_plans(self):
        from ai_assistant.services.project_learning import project_context
        self.make_plan()
        ProjectLearningEvent.objects.create(project=self.project, kind='plan', content={'previous_plan': {'goal': 'HISTORICAL_ONLY' * 2000}})
        context = project_context(self.user, self.conversation.conversation_id)
        self.assertNotIn('HISTORICAL_ONLY', context)
        self.assertLess(len(context.encode()), 10000)

    def test_project_course_turn_can_switch_visible_course_and_return(self):
        from types import SimpleNamespace
        from courses.models import Course, CourseModule, VideoTranscript, TranscriptSegment
        from ai_assistant.services.course_context import prepare_course_context
        from rest_framework.exceptions import NotFound
        module = CourseModule.objects.create(name='公开数学', is_public=True)
        public = Course.objects.create(title='函数课程', module=module, is_published=True)
        private = Course.objects.create(title='未授权课程', is_published=True)
        transcript = VideoTranscript.objects.create(course=public, asr_status='completed')
        TranscriptSegment.objects.create(transcript=transcript, index=0, start_time=0, end_time=60, text='函数的条件')
        request = SimpleNamespace(user=self.user, query_params={}, data={'course_context': {'course_id': public.pk, 'video_seconds': 20}})
        result = prepare_course_context(request, self.bot, self.conversation.conversation_id)
        self.assertEqual(result['video_seconds'], 20)
        self.message.metadata = {'course_context': result}
        self.message.save(update_fields=['metadata'])
        request.data = {}
        self.assertIsNone(prepare_course_context(request, self.bot, self.conversation.conversation_id))
        request.data = {'course_context': {'course_id': private.pk, 'video_seconds': 20}}
        with self.assertRaises(NotFound):
            prepare_course_context(request, self.bot, self.conversation.conversation_id)

    def test_followup_read_response_and_timed_resume_are_separate(self):
        from types import SimpleNamespace
        from ai_assistant.views_projects import save_new_conversation_project
        self.make_plan()
        ProjectLearning.objects.filter(pk=self.state.pk).update(followup_at=timezone.now() - timedelta(seconds=1))
        send_project_learning_followups()
        delivered = self.client.get(self.url).data['events'][0]
        self.assertEqual(delivered['delivery'], {'saved': True, 'read': False, 'responded': False})
        notification = Notification.objects.get(pk=delivered['content']['notification_id'])
        notification.is_read = True
        notification.save(update_fields=['is_read'])
        reply = AIChatMessage.objects.create(user=self.user, bot=self.bot, conversation_id=self.conversation.conversation_id, role='user', content='我还需要一个提示。')
        turn_project_context(self.user, {**self.context, 'message_id': reply.pk})
        self.assertTrue(self.client.get(self.url).data['events'][0]['delivery']['responded'])
        revision = self.client.get(self.url).data['revision']
        future = (timezone.now() + timedelta(days=7)).isoformat()
        change_learning(self.project, {'action': 'pause', 'revision': revision, 'resume_at': future})
        save_new_conversation_project(SimpleNamespace(user=self.user, data={'project_id': self.project.pk}), self.bot, self.conversation.conversation_id)
        self.assertIsNotNone(ProjectLearning.objects.get(pk=self.state.pk).followup_at)
