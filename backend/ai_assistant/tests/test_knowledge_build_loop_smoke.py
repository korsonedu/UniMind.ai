from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from ai_assistant.models import ConversationProject, LearningKnowledgeVersion, ProjectLearning
from ai_assistant.services.learning_knowledge import knowledge_state, knowledge_operation
from ai_assistant.services.learning_tasks import create_task
from ai_assistant.services.dsh_cards import build_tool_card, INTERNAL_PATH
from ai_assistant.services.project_learning import change_learning
from knowledge_builder.models import KnowledgeTreeBuild, LearningBlock, BlockEdge
from quizzes.ai_workflow import run_exam_grading
from quizzes.models import Question
from users.models import User


@override_settings(UNIMIND_CONTENT_INSTITUTION_ID='global', USE_MEM0=False,
                   CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class KnowledgeBuildLoopSmoke(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='graph_loop')
        self.project = ConversationProject.objects.create(user=self.user, name='折现学习')
        self.state = ProjectLearning.objects.create(project=self.project, planning_enabled=True)
        self.build = KnowledgeTreeBuild.objects.create(subject='公司理财', created_by=self.user,
            status='COMPLETED', completed_at=timezone.now())
        self.first = LearningBlock.objects.create(build=self.build, code='B1', short_title='折现', narrative_summary='解释未来现金流如何折算为现值。')
        self.second = LearningBlock.objects.create(build=self.build, code='B2', short_title='净现值', narrative_summary='比较现金流入现值和初始投入。')
        BlockEdge.objects.create(build=self.build, from_block=self.first, to_block=self.second, edge_kind='unidirectional')
        self.url = f'/api/ai/projects/{self.project.pk}/learning/knowledge/'
        self.client.force_authenticate(self.user)
        for target in ('users.feature_access.has_learning_feature', 'quizzes.ai_workflow.has_learning_feature',
                       'ai_assistant.services.learning_tasks.has_learning_feature',
                       'ai_assistant.services.learning_task_evidence.has_learning_feature'):
            mock = patch(target, return_value=True)
            mock.start()
            self.addCleanup(mock.stop)

    def propose(self):
        self.state.refresh_from_db()
        return self.client.post(self.url, {'action': 'from_build', 'build_id': str(self.build.pk),
            'block_ids': [self.second.pk], 'revision': self.state.revision}, format='json')

    def test_confirm_task_answer_evidence_and_next_node(self):
        builds = knowledge_operation(self.project, {'action': 'builds'})
        self.assertTrue(INTERNAL_PATH.fullmatch(builds['builds'][0]['href']))
        self.assertEqual(build_tool_card('manage_learning_knowledge', builds)['type'], 'data_card')
        response = self.propose()
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(INTERNAL_PATH.fullmatch(response.data['href']))
        self.assertEqual(build_tool_card('manage_learning_knowledge', response.data)['payload']['cta']['link'], response.data['href'])
        self.state.refresh_from_db()
        self.assertEqual(self.state.plan, {})
        self.assertEqual(self.state.status, 'preparing')
        plan = self.state.pending_plan['plan']
        self.assertEqual(len(plan['stages']), 2)
        change_learning(self.project, {'action': 'accept', 'revision': self.state.revision})
        self.state.refresh_from_db()
        version_id = plan['knowledge_path']['version_id']
        first_id, second_id = f'kb_{self.first.pk}', f'kb_{self.second.pk}'
        self.assertEqual(knowledge_state(self.project, self.state)['recommendations'][0]['node_id'], first_id)
        for index, answer in enumerate(('A', 'A', 'B', 'A', 'A')):
            question = Question.objects.create(text=f'第 {index} 个不同情境：折现的方向是什么？',
                q_type='objective', options=['未来现金流折成现值', '现值大于未来现金流'], correct_answer='A')
            task = create_task(self.project, {'version_id': version_id, 'node_id': first_id,
                'stage_id': plan['stages'][0]['id'], 'title': '折现检查', 'instructions': '独立作答。',
                'question_ids': [question.pk]})
            with patch('quizzes.views_exam.dispatch_exam_grading'), self.captureOnCommitCallbacks(execute=True):
                submitted = self.client.post('/api/quizzes/submit-exam/', {'submission_id': str(task.pk),
                    'learning_task_id': str(task.pk), 'assistance': 'independent',
                    'answers': [{'question_id': question.pk, 'answer': answer}]}, format='json')
            self.assertEqual(submitted.status_code, 202, submitted.data)
            with patch('quizzes.ai_workflow._queue_experience_verification'), self.captureOnCommitCallbacks(execute=True):
                run_exam_grading(self.user.pk, submitted.data['exam_id'])
            current = knowledge_state(self.project, self.state)
            self.assertEqual(current['evidence'][0]['task_id'], str(task.pk))
            node = next(node for node in current['nodes'] if node['id'] == first_id)
            self.assertEqual(node['learning_status'], ('recheck', 'supported', 'review', 'recheck', 'supported')[index])
            self.assertEqual(current['recommendations'][0]['node_id'], second_id if index in (1, 4) else first_id)
        self.assertEqual(current['builder']['build_id'], str(self.build.pk))
        self.assertEqual(node['citation']['source_kind'], 'generated_graph')

    def test_scope_free_chat_conflict_and_reuse(self):
        self.assertEqual(self.propose().status_code, 200)
        first_version = LearningKnowledgeVersion.objects.get()
        self.assertEqual(self.propose().status_code, 200)
        self.assertEqual(LearningKnowledgeVersion.objects.count(), 1)
        self.assertEqual(LearningKnowledgeVersion.objects.get().pk, first_version.pk)
        self.assertEqual(self.client.post(self.url, {'action': 'from_build', 'build_id': str(self.build.pk),
            'block_ids': [self.first.pk], 'revision': 0}, format='json').status_code, 409)
        other = User.objects.create_user(username='private_graph_owner')
        self.build.created_by = other
        self.build.save(update_fields=['created_by'])
        self.assertEqual(self.propose().status_code, 404)
        self.build.created_by = self.user
        self.build.save(update_fields=['created_by'])
        self.state.refresh_from_db()
        self.state.planning_enabled = False
        self.state.save(update_fields=['planning_enabled'])
        self.assertEqual(self.propose().status_code, 400)

    def test_bidirectional_blocks_remain_one_unit(self):
        BlockEdge.objects.filter(build=self.build).update(edge_kind='bidirectional')
        response = self.propose()
        self.assertEqual(response.status_code, 200, response.data)
        self.state.refresh_from_db()
        version = LearningKnowledgeVersion.objects.get()
        self.assertEqual(len(version.snapshot['nodes']), 1)
        self.assertEqual(set(version.snapshot['nodes'][0]['builder_block_ids']), {self.first.pk, self.second.pk})
        self.assertEqual(len(self.state.pending_plan['plan']['stages']), 1)
