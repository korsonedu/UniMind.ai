"""Smoke the shared task path; no separate block progress or client answer keys."""
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from ai_assistant.models import ConversationProject, ProjectLearning, ProjectLearningTask
from ai_assistant.services.learning_knowledge import knowledge_operation, knowledge_state
from ai_assistant.services.project_learning import change_learning
from knowledge_builder.models import KnowledgeTreeBuild, TreeModule, TreeAtomPoint, LearningBlock, BlockStep, BlockStepAtom, BlockEdge, BlockResource
from quizzes.ai_workflow import run_exam_grading
from users.models import User


@override_settings(UNIMIND_CONTENT_INSTITUTION_ID='global', USE_MEM0=False,
                   CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class BlockLearningSmoke(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='block_learning')
        self.project = ConversationProject.objects.create(user=self.user, name='折现')
        self.state = ProjectLearning.objects.create(project=self.project, planning_enabled=True)
        self.build = KnowledgeTreeBuild.objects.create(subject='公司理财', created_by=self.user, status='COMPLETED', completed_at=timezone.now())
        self.block = LearningBlock.objects.create(build=self.build, code='B1', short_title='折现', narrative_summary='理解折现')
        following = LearningBlock.objects.create(build=self.build, code='B2', short_title='净现值', narrative_summary='计算净现值')
        BlockEdge.objects.create(build=self.build, from_block=self.block, to_block=following, edge_kind='unidirectional')
        module = TreeModule.objects.create(build=self.build, code='M1', title='估值')
        step = BlockStep.objects.create(block=self.block, step_index=1, step_title='基础')
        for index, name in enumerate(('现金流', '折现率')):
            atom = TreeAtomPoint.objects.create(build=self.build, module=module, code=f'A{index}', name=name,
                goal_statement=f'解释{name}如何影响现值', cognitive_level='理解', goal_type='机制', granularity_minutes=5)
            BlockStepAtom.objects.create(step=step, atom=atom, membership_type='core', position=index)
        self.client.force_authenticate(self.user)
        for target in ('users.feature_access.has_learning_feature', 'quizzes.ai_workflow.has_learning_feature',
                       'ai_assistant.services.learning_tasks.has_learning_feature', 'ai_assistant.services.learning_task_evidence.has_learning_feature'):
            mock = patch(target, return_value=True)
            mock.start()
            self.addCleanup(mock.stop)
        knowledge_operation(self.project, {'action': 'from_build', 'build_id': str(self.build.pk), 'block_ids': [following.pk], 'revision': 0})
        self.state.refresh_from_db()
        change_learning(self.project, {'action': 'accept', 'revision': self.state.revision})
        self.state.refresh_from_db()
        self.url = f'/api/knowledge-builder/{self.build.pk}/blocks/{self.block.pk}/quiz/'
        from knowledge_builder.tasks import prepare_block_assessment
        queue = patch('knowledge_builder.tasks.prepare_block_assessment.delay', side_effect=prepare_block_assessment)
        queue.start()
        self.addCleanup(queue.stop)
        self.counter = 0

    def generate(self, row, block, q_type, seen, source_context=''):
        self.counter += 1
        return dict(stem=f'{row.atom.name}情境{self.counter}：解释现值变化的正确方向？', q_type=q_type,
            options={'A': '折为现值', 'B': '忽略时间'}, correct_answer='A', grading_points='解释现值与未来值',
            subjective_type='short', question_id=None)

    def assessment(self, **changes):
        with patch('knowledge_builder.block_assessments._generate_question', side_effect=self.generate), self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.url, {'project_id': self.project.pk, **changes}, format='json')
        if response.status_code == 200:
            return self.client.post(self.url, {'project_id': self.project.pk, 'action': 'read'}, format='json')
        return response

    def finish(self, assessment, assistance='independent'):
        for item in assessment['items']:
            task = item['task']
            with patch('quizzes.views_exam.dispatch_exam_grading'), self.captureOnCommitCallbacks(execute=True):
                response = self.client.post('/api/quizzes/submit-exam/', {'learning_task_id': task['id'], 'submission_id': task['id'],
                    'assistance': assistance, 'answers': [{'question_id': 0, 'answer': 'A'}]}, format='json')
            self.assertEqual(response.status_code, 202, response.data)
            with patch('quizzes.ai_workflow._queue_experience_verification'), self.captureOnCommitCallbacks(execute=True):
                run_exam_grading(self.user.pk, response.data['exam_id'])

    def test_tasks_answers_recovery_and_next_recommendation(self):
        for index in range(2):
            response = self.assessment(retest=bool(index))
            self.assertEqual(response.status_code, 200, response.data)
            assessment = response.data['assessment']
            self.assertEqual(len(assessment['items']), 2)
            self.assertNotIn('correct_answer', str(assessment))
            self.assertNotIn('signed_payload', str(assessment))
            self.assertEqual(self.assessment().data['assessment']['id'], assessment['id'])
            with patch('quizzes.ai_workflow.AIService.grade_question', side_effect=AssertionError('Objective tasks must use answer keys')):
                self.finish(assessment)
            restored = self.assessment(action='read').data['assessment']
            self.assertTrue(restored['passed'])
            state = knowledge_state(self.project, self.state)
            first = next(node for node in state['nodes'] if node['id'] == f'kb_{self.block.pk}')
            self.assertEqual(first['learning_status'], 'recheck' if index == 0 else 'supported')
            self.assertEqual(len(state['evidence']), index + 1)
        self.assertEqual(ProjectLearningTask.objects.filter(project=self.project).count(), 4)
        self.assertNotEqual(state['recommendations'][0]['node_id'], f'kb_{self.block.pk}')

    def test_generation_failure_and_project_resource_snapshot(self):
        from rest_framework.exceptions import ValidationError
        with patch('knowledge_builder.block_assessments._generate_question', side_effect=ValidationError('暂时无法出题')), self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.url, {'project_id': self.project.pk}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.assessment(action='read').data['preparation']['status'], 'failed')
        self.assertFalse(ProjectLearningTask.objects.filter(project=self.project).exists())
        resource = BlockResource.objects.create(build=self.build, block=self.block, title='公开视频', url='https://example.org/lecture', excerpt='仅有摘要')
        resource_url = self.url.replace('/quiz/', '/resources/')
        data = {'action': 'attach_project', 'project_id': self.project.pk, 'resource_id': resource.pk}
        response = self.client.post(resource_url, data, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data['resource']['not_web_read'])
        self.assertEqual(response.data['resource']['source_kind'], 'block_resource_excerpt')
        self.assertEqual(self.client.post(resource_url, data, format='json').data['resource']['id'], response.data['resource']['id'])
        other = User.objects.create_user(username='block_other')
        self.client.force_authenticate(other)
        self.assertEqual(self.assessment(action='read').status_code, 404)

    def test_failed_grading_is_pending_evidence_and_can_be_recovered(self):
        assessment = self.assessment(mode='challenge').data['assessment']
        with patch('quizzes.ai_workflow.AIService.grade_question', side_effect=RuntimeError('Model unavailable')):
            self.finish(assessment)
        restored = self.assessment(action='read').data['assessment']
        self.assertFalse(restored['complete'])
        self.assertFalse(restored['passed'])
        self.assertEqual(restored['items'][-1]['task']['status'], 'failed')
        self.assertEqual(knowledge_state(self.project, self.state)['evidence'], [])
        self.assertEqual(self.assessment(retest=True).status_code, 400)
