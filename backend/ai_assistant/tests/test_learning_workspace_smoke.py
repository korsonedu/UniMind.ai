"""Workspace smoke: persistent focus, side-activity isolation and owned context."""
from types import SimpleNamespace
from uuid import uuid4
from datetime import timedelta
from django.utils import timezone
from django.test import override_settings
from rest_framework.test import APITestCase
from django.http import Http404
from users.models import User, CourseStudentStatus
from ai_assistant.models import ConversationProject, ProjectLearning, Bot, Conversation, AIChatMessage
from ai_assistant.services.project_learning import activity_snapshot, change_learning
from ai_assistant.services.learning_tasks import create_task, task_data
from ai_assistant.services.learning_guidance import teaching_guidance


@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
                   UNIMIND_CONTENT_INSTITUTION_ID='global', USE_MEM0=False)
class LearningWorkspaceSmoke(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='workspace_smoke')
        CourseStudentStatus.objects.create(user=self.user, is_course_student=True)
        self.project = ConversationProject.objects.create(user=self.user, name='学习主线')
        self.state = ProjectLearning.objects.create(project=self.project, planning_enabled=True, status='active', current_stage='concept',
            plan={'goal': '解释函数', 'stages': [{'id': 'concept', 'title': '函数概念', 'outcome': '说明对应关系'}, {'id': 'value', 'title': '函数值', 'outcome': '正确代入'}]})
        def task(stage):
            return create_task(self.project, {'stage_id': stage, 'title': stage, 'instructions': '说明依据',
                'definition': {'prompt': '请说明这个概念的含义及理由。', 'response_type': 'explanation', 'criteria': ['准确说明含义']}})
        self.first, self.other = task('concept'), task('value')
        self.client.force_authenticate(self.user)

    def test_owned_focus_changes_stage_and_rejects_retired_or_foreign_tasks(self):
        url = f'/api/ai/projects/{self.project.pk}/learning/'
        response = self.client.patch(url, {'action': 'focus', 'task_id': str(self.other.pk), 'revision': 0}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['current_stage'], 'value')
        self.assertEqual(response.data['focus_task_id'], str(self.other.pk))
        self.assertEqual(response.data['teaching_guidance']['task_id'], str(self.other.pk))
        self.state.refresh_from_db()
        self.state.plan['stages'] = [{'id': 'value', 'title': '函数值', 'outcome': '正确代入'}]
        self.state.save()
        self.assertFalse(task_data(self.first)['is_current'])
        rejected = self.client.patch(url, {'action': 'focus', 'task_id': str(self.first.pk), 'revision': 1}, format='json')
        self.assertEqual(rejected.status_code, 400)
        other_user = User.objects.create_user(username='workspace_foreign')
        foreign = ConversationProject.objects.create(user=other_user, name='其他人')
        with self.assertRaises(Http404):
            activity_snapshot(foreign, {'task_id': str(self.first.pk)})

    def test_side_activity_supplies_context_without_moving_mainline(self):
        self.state.reminders_enabled = True
        self.state.followup_at = timezone.now() + timedelta(days=3)
        self.state.followup_text = '继续当前主线'
        self.state.save()
        reminder = self.state.followup_at
        viewed = activity_snapshot(self.project, {'task_id': str(self.other.pk)})
        self.assertFalse(viewed['mainline'])
        self.assertEqual(viewed['task']['id'], str(self.other.pk))
        bot = Bot.objects.create(name='小宇', bot_type='planner')
        conversation = Conversation.objects.create(user=self.user, project=self.project, bot=bot, conversation_id=uuid4())
        message = AIChatMessage.objects.create(user=self.user, bot=bot, conversation_id=conversation.conversation_id,
            role='user', content='我想复盘这道题。', metadata={'learning_activity': viewed})
        result = change_learning(self.project, {'action': 'progress', 'revision': 0, 'observation': '解释了函数值',
            'feedback': '旁支任务完成', 'next_action': '继续函数值', 'assistance': 'independent', 'current_stage': 'value'},
            message=message, model=True)
        self.assertEqual(result['current_stage'], 'concept')
        self.assertNotEqual(result['feedback'], '旁支任务完成')
        self.assertEqual(result['followup_at'], reminder)
        self.assertEqual(result['followup_text'], '继续当前主线')
        self.assertEqual(result['teaching_guidance']['task_id'], str(self.first.pk))
        self.assertFalse(self.project.learning_events.get(kind='progress').content['mainline'])
        self.state.refresh_from_db()
        self.state.plan['knowledge_path'] = {'version_id': 999}
        self.state.save()
        self.assertFalse(activity_snapshot(self.project, {'task_id': str(self.first.pk)})['mainline'])

    def test_later_side_stage_success_does_not_replace_unresolved_mainline(self):
        state = SimpleNamespace(status='active', current_stage='concept', feedback='', next_action='继续检查',
            plan={'stages': [{'id': 'concept'}, {'id': 'value'}]})
        def task(key, stage, score):
            return {'id': key, 'stage_id': stage, 'node_id': stage, 'mode': 'apply', 'title': stage,
                'status': 'completed', 'purpose': 'practice', 'assistance': 'independent',
                'created_at': '2026-11-14T00:00:00+00:00', 'summary': {'total_score': score, 'max_score': 10,
                'completed_at': f'2026-11-14T00:0{1 if stage == "concept" else 2}:00+00:00'},
                'payload': {'questions': [{'text': key}]}}
        result = teaching_guidance(state, [task('first', 'concept', 0), task('later', 'value', 10)])
        self.assertEqual(result['status'], 'remediate')
        self.assertEqual(result['stage_id'], 'concept')
        self.assertEqual(result['task_id'], 'first')
