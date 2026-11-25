"""Smoke the shared task path; no separate block progress or client answer keys."""
from datetime import timedelta
from unittest.mock import patch

from django.db import connection
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from ai_assistant.models import ConversationProject, ProjectLearning, ProjectLearningEvent, ProjectLearningTask
from ai_assistant.services.learning_knowledge import knowledge_operation, knowledge_state
from ai_assistant.services.learning_resources import store_resource
from ai_assistant.services.project_learning import change_learning
from courses.models import Course
from knowledge_builder.models import KnowledgeTreeBuild, TreeModule, TreeAtomPoint, LearningBlock, BlockStep, BlockStepAtom, BlockEdge, BlockResource
from quizzes.ai_workflow import run_exam_grading
from users.models import CourseStudentStatus, User


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

    def generate(self, row, block, q_type, seen, source_context='', *, before_retry=None):
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

    def enqueue_assessment(self):
        with patch('knowledge_builder.tasks.prepare_block_assessment.delay') as dispatch, self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.url, {'project_id': self.project.pk}, format='json')
        self.assertEqual(response.data['preparation']['status'], 'pending')
        event = ProjectLearningEvent.objects.get(project=self.project, kind='block_prepare')
        dispatch.assert_called_once_with(event.pk)
        return event

    @override_settings(UNIMIND_LEARNING_RUNTIME='ulr')
    def test_duplicate_delivery_only_generates_one_assessment(self):
        from knowledge_builder.tasks import prepare_block_assessment

        with self.settings(UNIMIND_LEARNING_RUNTIME='legacy'):
            event = self.enqueue_assessment()
        self.assertFalse(event.content.get('requires_ulr', False))

        def generate(*args, **kwargs):
            item = self.generate(*args, **kwargs)
            if self.counter == 1:
                event.refresh_from_db()
                self.assertTrue(event.content.get('requires_ulr', False))
                prepare_block_assessment(event.pk)
                self.assertEqual(self.assessment(action='read').data['preparation']['status'], 'pending')
            return item

        with patch('knowledge_builder.block_assessments._generate_question', side_effect=generate):
            prepare_block_assessment(event.pk)
            prepare_block_assessment(event.pk)
        self.assertEqual(self.counter, 2)
        result = ProjectLearningEvent.objects.get(project=self.project, kind='block_assessment')
        event.refresh_from_db()
        self.assertEqual(event.content['assessment_id'], result.pk)
        self.assertEqual(event.content['status'], 'completed')
        self.assertEqual(ProjectLearningTask.objects.filter(project=self.project).count(), 2)

    @override_settings(UNIMIND_LEARNING_RUNTIME='ulr')
    def test_wrong_worker_can_be_retried_on_ulr_with_the_same_preparation(self):
        from knowledge_builder.tasks import prepare_block_assessment

        event = self.enqueue_assessment()
        self.assertTrue(event.content.get('requires_ulr', False))
        with self.settings(UNIMIND_LEARNING_RUNTIME='legacy'), \
                patch('knowledge_builder.block_assessments._generate_question') as model:
            prepare_block_assessment(event.pk)
            rejected = self.assessment()
            self.assertEqual(rejected.status_code, 400, rejected.data)
        model.assert_not_called()
        event.refresh_from_db()
        self.assertEqual(event.content['status'], 'failed')
        self.assertFalse(ProjectLearningTask.objects.filter(project=self.project).exists())

        restored = self.assessment()
        self.assertEqual(restored.data['preparation']['status'], 'completed')
        event.refresh_from_db()
        self.assertEqual(restored.data['assessment']['id'], event.content['assessment_id'])
        self.assertTrue(event.content['requires_ulr'])
        self.assertEqual(ProjectLearningEvent.objects.filter(project=self.project, kind='block_prepare').count(), 1)
        self.assertEqual(self.counter, 2)

    def test_lost_queue_message_reuses_preparation_and_original_settings(self):
        from ai_engine.observability import runtime_observation
        from knowledge_builder.tasks import prepare_block_assessment

        event = self.enqueue_assessment()
        past = timezone.now() - timedelta(minutes=13)
        ProjectLearningEvent.objects.filter(pk=event.pk).update(content={**event.content, 'queued_at': past.timestamp()})
        self.assertEqual(self.assessment(action='read').data['preparation']['status'], 'failed')
        payload = {'project_id': self.project.pk}
        with patch('knowledge_builder.tasks.prepare_block_assessment.delay', side_effect=RuntimeError('broker unavailable')) as dispatch, \
                self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.post(self.url, payload, format='json').status_code, 200)
        dispatch.assert_called_once_with(event.pk)
        self.assertEqual(self.assessment(action='read').data['preparation']['status'], 'failed')
        with patch('knowledge_builder.tasks.prepare_block_assessment.delay') as dispatch, self.captureOnCommitCallbacks(execute=True):
            for _ in range(2):
                response = self.client.post(self.url, payload, format='json')
                self.assertEqual(response.data['preparation']['status'], 'pending')
        dispatch.assert_called_once_with(event.pk)
        self.assertEqual(self.assessment(action='read').data['preparation']['status'], 'pending')

        observations = []

        def generate(*args, **kwargs):
            observations.append(runtime_observation.get())
            return self.generate(*args, **kwargs)

        with patch('knowledge_builder.block_assessments._generate_question', side_effect=generate):
            prepare_block_assessment(event.pk)
            prepare_block_assessment(event.pk)
        event.refresh_from_db()
        self.assertEqual((event.content['status'], event.content['mode'], event.content['retest']), ('completed', 'objective', False))
        self.assertEqual(ProjectLearningEvent.objects.filter(project=self.project, kind='block_prepare').count(), 1)
        self.assertEqual(ProjectLearningEvent.objects.filter(project=self.project, kind='block_assessment').count(), 1)
        self.assertEqual(self.counter, 2)
        self.assertEqual({row['request_id'] for row in observations}, {f'assessment:{event.pk}'})
        self.assertEqual(len({row['attempt_id'] for row in observations}), 1)

    def test_expired_assessment_drops_late_questions(self):
        from knowledge_builder.tasks import prepare_block_assessment

        event = self.enqueue_assessment()

        def generate(*args, **kwargs):
            item = self.generate(*args, **kwargs)
            with patch('django.utils.timezone.now', return_value=timezone.now() + timedelta(minutes=13)):
                self.assertEqual(self.assessment(action='read').data['preparation']['status'], 'failed')
            return item

        with patch('knowledge_builder.block_assessments._generate_question', side_effect=generate):
            prepare_block_assessment(event.pk)
        event.refresh_from_db()
        self.assertEqual((self.counter, event.content['status']), (1, 'failed'))
        self.assertFalse(ProjectLearningTask.objects.filter(project=self.project).exists())
        self.assertFalse(ProjectLearningEvent.objects.filter(project=self.project, kind='block_assessment').exists())

    def mount_course_excerpt(self):
        CourseStudentStatus.objects.create(user=self.user, is_course_student=True)
        course = Course.objects.create(title='折现率课程', is_published=True)
        resource = BlockResource.objects.create(build=self.build, block=self.block, source_kind='course',
            course_id=course.pk, title=course.title, url='/courses', excerpt='课程原摘录')
        response = self.client.post(self.url.replace('/quiz/', '/resources/'), {
            'action': 'attach_project', 'project_id': self.project.pk, 'resource_id': resource.pk,
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        return course

    def test_course_withdrawal_stops_preparation_after_the_first_question(self):
        from knowledge_builder.tasks import prepare_block_assessment

        course = self.mount_course_excerpt()
        event = self.enqueue_assessment()

        def generate(*args, **kwargs):
            self.assertIn('课程原摘录', args[-1])
            item = self.generate(*args, **kwargs)
            if self.counter == 1:
                Course.objects.filter(pk=course.pk).update(is_published=False)
            return item

        with patch('knowledge_builder.block_assessments._generate_question', side_effect=generate):
            prepare_block_assessment(event.pk)
        self.assertEqual((self.counter, self.assessment(action='read').data['preparation']['status']), (1, 'failed'))
        self.assertFalse(ProjectLearningTask.objects.filter(project=self.project).exists())
        self.assertFalse(ProjectLearningEvent.objects.filter(project=self.project, kind='block_assessment').exists())

    @override_settings(UNIMIND_LEARNING_RUNTIME='ulr')
    def test_course_withdrawal_stops_retry_of_invalid_question(self):
        from knowledge_builder.tasks import prepare_block_assessment

        course = self.mount_course_excerpt()
        event = self.enqueue_assessment()

        def invalid_question(**kwargs):
            self.assertIn('课程原摘录', kwargs['user_prompt'])
            Course.objects.filter(pk=course.pk).update(is_published=False)
            return None

        with patch('knowledge_builder.block_study.config._get_api_key', return_value='fixture'), \
                patch('knowledge_builder.block_study.AIService.structured_output', side_effect=invalid_question) as model:
            prepare_block_assessment(event.pk)
        model.assert_called_once()
        self.assertEqual(self.assessment(action='read').data['preparation']['status'], 'failed')
        self.assertFalse(ProjectLearningTask.objects.filter(project=self.project).exists())

    def test_changed_project_excerpt_drops_prepared_questions(self):
        from knowledge_builder.tasks import prepare_block_assessment

        resource = BlockResource.objects.create(build=self.build, block=self.block,
            title='折现率资料', url='https://example.org/discount', excerpt='项目原摘录')
        response = self.client.post(self.url.replace('/quiz/', '/resources/'), {
            'action': 'attach_project', 'project_id': self.project.pk, 'resource_id': resource.pk,
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        original = response.data['resource']
        event = self.enqueue_assessment()

        def generate(*args, **kwargs):
            self.assertIn('项目原摘录', args[-1])
            item = self.generate(*args, **kwargs)
            if self.counter == 2:
                revised = store_resource(self.project, {**original, 'excerpt': '新项目摘录', 'content_version': 'new'})
                self.assertEqual(revised['resource']['id'], original['id'])
            return item

        with patch('knowledge_builder.block_assessments._generate_question', side_effect=generate):
            prepare_block_assessment(event.pk)
        self.assertEqual((self.counter, self.assessment(action='read').data['preparation']['status']), (2, 'failed'))
        self.assertFalse(ProjectLearningTask.objects.filter(project=self.project).exists())
        self.assertFalse(ProjectLearningEvent.objects.filter(project=self.project, kind='block_assessment').exists())

    def test_postgresql_redelivery_recovers_the_original_preparation(self):
        if connection.vendor != 'postgresql':
            self.skipTest('PostgreSQL session lock required.')
        from knowledge_builder.tasks import prepare_block_assessment

        event = self.enqueue_assessment()
        with patch('knowledge_builder.block_assessments._generate_question', side_effect=SystemExit), self.assertRaises(SystemExit):
            prepare_block_assessment(event.pk)
        event.refresh_from_db()
        self.assertEqual(event.content['status'], 'running')
        prepare_block_assessment.push_request(delivery_info={'redelivered': True})
        try:
            with patch('knowledge_builder.block_assessments._generate_question', side_effect=self.generate):
                prepare_block_assessment.run(event.pk)
                prepare_block_assessment.run(event.pk)
        finally:
            prepare_block_assessment.pop_request()
        event.refresh_from_db()
        self.assertEqual((self.counter, event.content['status']), (2, 'completed'))
        self.assertEqual(ProjectLearningEvent.objects.filter(project=self.project, kind='block_prepare').count(), 1)
        self.assertEqual(ProjectLearningEvent.objects.filter(project=self.project, kind='block_assessment').count(), 1)

    @override_settings(UNIMIND_LEARNING_RUNTIME='ulr', UNIMIND_DSH_ENABLED=False)
    def test_postgresql_cutover_requeues_interrupted_legacy_assessment(self):
        if connection.vendor != 'postgresql':
            self.skipTest('PostgreSQL session lock required.')
        from io import StringIO
        import json
        from tempfile import TemporaryDirectory

        from django.core.management import call_command, CommandError
        from ai_assistant.models import Bot
        from knowledge_builder.tasks import prepare_block_assessment

        Bot.objects.create(is_xiaoyu=True, name='小宇')
        with self.settings(UNIMIND_LEARNING_RUNTIME='legacy'):
            event = self.enqueue_assessment()
            with patch('knowledge_builder.block_assessments._generate_question', side_effect=SystemExit), self.assertRaises(SystemExit):
                prepare_block_assessment(event.pk)
        event.refresh_from_db()
        self.assertEqual(event.content['status'], 'running')
        self.assertFalse(event.content['requires_ulr'])
        original = event.content.copy()
        self.assertFalse(ProjectLearningTask.objects.filter(project=self.project).exists())

        def gate(state, blocked=False):
            output = StringIO()
            options = {'state_dir': state, 'api_url': 'http://127.0.0.1:8000', 'require_migrated': True, 'stdout': output}
            if blocked:
                with self.assertRaisesRegex(CommandError, '未完成的迁移项'):
                    call_command('audit_dsh_sessions', **options)
            else:
                call_command('audit_dsh_sessions', **options)
            return json.loads(output.getvalue())

        def resume(**options):
            output = StringIO()
            with self.captureOnCommitCallbacks(execute=True):
                call_command('resume_block_assessment', event.pk, stdout=output, **options)
            return json.loads(output.getvalue())

        with TemporaryDirectory() as state:
            blocked = gate(state, blocked=True)
            self.assertEqual(blocked['blockers'], {'running_unpinned_block_assessments': 1})
            self.assertEqual(blocked['unsettled_block_preparation_ids'], [event.pk])
            with self.assertRaisesRegex(CommandError, '请停止旧工作进程'):
                resume()
            with patch('knowledge_builder.tasks.prepare_block_assessment.delay', side_effect=RuntimeError('broker unavailable')) as dispatch:
                resume(legacy_workers_stopped=True)
            dispatch.assert_called_once_with(event.pk)
            event.refresh_from_db()
            self.assertEqual(event.content['status'], 'failed')
            self.assertTrue(event.content['queue_retryable'])

            with patch('knowledge_builder.tasks.prepare_block_assessment.delay') as dispatch:
                self.assertTrue(resume(legacy_workers_stopped=True)['queued'])
                self.assertFalse(resume(legacy_workers_stopped=True)['queued'])
            dispatch.assert_called_once_with(event.pk)
            with patch('knowledge_builder.block_assessments._generate_question', side_effect=self.generate):
                prepare_block_assessment(event.pk)
                prepare_block_assessment(event.pk)
            self.assertTrue(gate(state)['migrated'])

        event.refresh_from_db()
        self.assertTrue(event.content['requires_ulr'])
        self.assertEqual(event.content['status'], 'completed')
        self.assertEqual({key: event.content[key] for key in ('block_id', 'version_id', 'mode', 'retest')},
                         {key: original[key] for key in ('block_id', 'version_id', 'mode', 'retest')})
        result = self.assessment(action='read').data
        self.assertEqual(result['assessment']['id'], event.content['assessment_id'])
        self.assertEqual(len(result['assessment']['items']), 2)
        self.assertEqual(ProjectLearningEvent.objects.filter(project=self.project, kind='block_prepare').count(), 1)
        self.assertEqual(ProjectLearningEvent.objects.filter(project=self.project, kind='block_assessment').count(), 1)
        self.assertEqual(ProjectLearningTask.objects.filter(project=self.project).count(), self.counter)
        self.assertEqual(self.counter, 2)

    @override_settings(UNIMIND_LEARNING_RUNTIME='ulr', UNIMIND_DSH_ENABLED=False)
    def test_postgresql_cutover_settles_assessment_for_replaced_version(self):
        if connection.vendor != 'postgresql':
            self.skipTest('PostgreSQL session lock required.')
        from io import StringIO
        import json
        from tempfile import TemporaryDirectory

        from django.core.management import call_command, CommandError
        from ai_assistant.models import Bot
        from knowledge_builder.tasks import prepare_block_assessment

        Bot.objects.create(is_xiaoyu=True, name='小宇')
        with self.settings(UNIMIND_LEARNING_RUNTIME='legacy'):
            event = self.enqueue_assessment()
            with patch('knowledge_builder.block_assessments._generate_question', side_effect=SystemExit), self.assertRaises(SystemExit):
                prepare_block_assessment(event.pk)
        event.refresh_from_db()
        original = event.content.copy()
        self.assertEqual(original['status'], 'running')

        self.block.short_title = '折现 · 新版'
        self.block.save(update_fields=['short_title'])
        knowledge_operation(self.project, {'action': 'from_build', 'build_id': str(self.build.pk),
            'block_ids': [self.block.pk], 'revision': self.state.revision})
        self.state.refresh_from_db()
        change_learning(self.project, {'action': 'accept', 'revision': self.state.revision})
        self.state.refresh_from_db()
        self.assertNotEqual(self.state.plan['knowledge_path']['version_id'], original['version_id'])

        with TemporaryDirectory() as state_dir:
            gate = {'state_dir': state_dir, 'api_url': 'http://127.0.0.1:8000', 'require_migrated': True}
            with self.assertRaises(CommandError):
                call_command('audit_dsh_sessions', **gate, stdout=StringIO())
            with patch.object(prepare_block_assessment, 'delay') as dispatch, \
                    patch('knowledge_builder.block_assessments._generate_question') as model:
                for _ in range(2):
                    receipt = StringIO()
                    call_command('resume_block_assessment', event.pk, legacy_workers_stopped=True, stdout=receipt)
                    self.assertEqual(json.loads(receipt.getvalue()), {'event_id': event.pk, 'status': 'failed',
                        'queued': False, 'error_code': 'superseded_learning_version'})
                prepare_block_assessment(event.pk)
                dispatch.assert_not_called()
                model.assert_not_called()
            inventory = StringIO()
            call_command('audit_dsh_sessions', **gate, stdout=inventory)
            self.assertTrue(json.loads(inventory.getvalue())['migrated'])
            unknown = ProjectLearningEvent.objects.create(project=self.project, kind='block_prepare',
                content={**original, 'version_id': self.state.plan['knowledge_path']['version_id'] + 1})
            with self.assertRaisesRegex(CommandError, '无法核对'):
                call_command('resume_block_assessment', unknown.pk, legacy_workers_stopped=True, stdout=StringIO())
            unknown.refresh_from_db()
            self.assertEqual(unknown.content['status'], 'running')

        event.refresh_from_db()
        self.assertEqual(event.content['version_id'], original['version_id'])
        self.assertFalse(event.content['queue_retryable'])
        self.assertFalse(ProjectLearningTask.objects.filter(project=self.project).exists())
        self.assertIsNone(self.assessment(action='read').data['preparation'])

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
