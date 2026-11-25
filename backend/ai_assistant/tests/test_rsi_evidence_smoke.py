"""Synthetic method assignments and grades through both evidence ledgers."""
import json
from unittest.mock import patch
from uuid import uuid4

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from ai_assistant.models import (AIChatMessage, Bot, Conversation, ConversationProject, LearningStrategy,
    LearningStrategyOutcome, LearningStrategyUse, ProjectLearning, ProjectLearningEvent, TaskMemoryObject)
from ai_assistant.services import learning_diagnostics, method_adoption, task_memory_store, teaching_sidecar
from ai_assistant.services.learning_library import strategy_operation
from ai_assistant.services.learning_tasks import create_task, sync_task_result
from ai_assistant.services.project_learning import completed_learning_turn
from ai_assistant.services.public_methods import publish_method
from ai_assistant.services.rsi_evidence import project_method_evidence, summarize_method_evidence
from quizzes.models import ExamQuestionResult, QuizExam
from users.models import CourseStudentStatus, User


@override_settings(UNIMIND_CONTENT_INSTITUTION_ID='global', UNIMIND_LEARNING_RUNTIME='ulr',
    UNIMIND_PRISM_MODE='off', UNIMIND_SDTM_TASK_MEMORY_MODE='active', UNIMIND_SDTM_STRUCTURED_DIAGNOSTICS=True,
    UNIMIND_SDTM_DIAGNOSTIC_PROJECTS=frozenset(), USE_MEM0=False)
class RSIEvidenceSmoke(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='rsi_evidence_synthetic')
        self.student = CourseStudentStatus.objects.create(user=self.user, is_course_student=True)
        self.bot = Bot.objects.create(name='小宇', bot_type='planner')
        self.project = ConversationProject.objects.create(user=self.user, name='计算机原理')
        self.room = Conversation.objects.create(user=self.user, bot=self.bot, project=self.project, conversation_id=uuid4())
        ProjectLearning.objects.create(project=self.project, status='active', current_stage='start',
            plan={'goal': '解释缓存', 'stages': [{'id': 'start', 'title': '起点', 'knowledge_nodes': []}]})
        self.source = self.message('我比较了缓存命中和未命中。')
        self.event = ProjectLearningEvent.objects.create(project=self.project, message=self.source, kind='progress',
            content={'strategy': '按是否命中划分情境。'})
        self.strategy = strategy_operation(self.project, {'action': 'save', 'event_id': self.event.pk})['strategy_id']
        self.method = publish_method({'key': 'compare', 'instruction': '比较两个情境。',
            'requires': {'purpose': 'recheck'}, 'source': '合成测试'}, request_key='rsi-evidence')

    def message(self, content, *, role='user', metadata=None):
        return AIChatMessage.objects.create(user=self.user, bot=self.bot, conversation_id=self.room.conversation_id,
            role=role, content=content, metadata=metadata or {})

    def task(self, prompt, use=None):
        return create_task(self.project, {'stage_id': 'start', 'title': '缓存边界', 'instructions': '自己解释。',
            'purpose': 'recheck', 'strategy_use_id': use.pk if use else None,
            'definition': {'prompt': prompt, 'response_type': 'explanation', 'criteria': ['说明访问过程']}})

    def private_use(self):
        message = self.message('请用原来的方法解释。')
        teaching_sidecar.freeze_turn(self.project, message, {})
        result = strategy_operation(self.project, {'action': 'apply', 'strategy_id': self.strategy,
            'reason': '比较缓存命中与未命中。'}, message=message)
        use = LearningStrategyUse.objects.get(pk=result['use_id'])
        teaching_sidecar.record_turn_completion(self.reply(message))
        return use

    def public_use(self, task, *, frozen=True):
        message = self.message('请说明另一种方法。')
        sidecar = teaching_sidecar.freeze_turn(self.project, message, {}) if frozen else None
        args = {'task_id': task.pk, 'public_method_id': self.method.pk, 'method_digest': self.method.digest,
                'reason': '比较两种条件。'}
        adopted = method_adoption.apply_public(self.project, args, message)
        self.assertTrue(adopted['created'])
        self.assertFalse(method_adoption.apply_public(self.project, args, message)['created'])
        use = TaskMemoryObject.objects.get(digest=adopted['use_id'])
        if sidecar:
            self.assertEqual(use.value['rsi_bundle_digest'], teaching_sidecar.canonical_hash(sidecar['bundle']))
            self.assertEqual(use.value['mechanisms_status'], 'observed')
        else:
            self.assertNotIn('rsi_bundle_digest', use.value)
            self.assertEqual(use.value['mechanisms_status'], 'unobserved_turn')
        method_adoption.record_completion(self.reply(message))
        return use

    def reply(self, message):
        return self.message('未命中时需要再访问主存。', role='assistant',
            metadata={'learning_turn': completed_learning_turn(message.pk)})

    def assessment(self, task, score):
        maximum = task.question_snapshot['0']['max_score']
        exam = QuizExam.objects.create(user=self.user, status='completed', total_questions=1, graded_count=1,
            total_score=score, max_score=maximum)
        task.exam, task.assistance = exam, 'independent'
        task.save(update_fields=['exam', 'assistance'])
        result = ExamQuestionResult.objects.create(exam=exam, score=score, max_score=maximum, user_answer='自己的解释',
            status='graded', graded_at=timezone.now(), question_snapshot=task.question_snapshot['0'])
        sync_task_result(result)
        return result

    def disclose(self, task):
        learning_diagnostics.certify_task(task, schema='cache-v1', bindings={'instance': str(task.pk)}, decisions=['miss'])
        question = self.message('未命中会访问哪里？')
        reply = self.reply(question)
        def certify():
            return learning_diagnostics.certify_text_delivery(task, question, reply,
                span=(0, len(reply.content)), quote=reply.content, decisions=['miss'])
        return certify

    def test_cross_ledger_outcomes_and_summary(self):
        first = self.private_use()
        task = self.task('请解释缓存未命中的过程。', first)
        self.assessment(task, task.question_snapshot['0']['max_score'])
        repeated = self.task(task.definition['prompt'], self.private_use())
        self.assessment(repeated, 0)
        shared = self.task('请按顺序说明一次内存读取。', self.private_use())
        public = self.public_use(shared)
        self.disclose(shared)()
        result = self.assessment(shared, 0)
        saved = LearningStrategyOutcome.objects.get(result=result).snapshot
        self.assertEqual(saved['reasons'], ['overlapping_methods', 'same_instance_solution_disclosed'])
        self.assertTrue(saved['overlapping_methods'] and saved['disclosed'])
        self.assertEqual(saved['status'], 'uncertain')
        separate = self.task('请解释缓存命中的代价。')
        other = self.public_use(separate, frozen=False)
        self.assessment(separate, 0)

        records = project_method_evidence(self.project)
        self.assertEqual(records, project_method_evidence(self.project))
        json.dumps(records, allow_nan=False)
        private, published = (project_method_evidence(self.project, **flags) for flags in (
            {'include_public': False}, {'include_private': False}))
        self.assertEqual(len(records), len(private) + len(published))
        self.assertEqual({row['use_id'] for row in published}, {f'public:{public.digest}', f'public:{other.digest}'})
        self.assertEqual(set(private[0]), {'ledger', 'use_id', 'project_id', 'task_id', 'method_ref', 'question_id',
            'reply_id', 'assigned_at', 'completed_at', 'mechanisms', 'selection', 'exposure', 'source_available',
            'outcomes', 'eligible_for_eval', 'causal_claim'})
        self.assertEqual(set(private[0]['outcomes'][0]), {'result_id', 'event_id', 'task_id', 'node_id', 'mode', 'purpose',
            'score', 'max_score', 'outcome', 'assistance', 'label_source', 'status', 'reasons', 'timing_verified',
            'repeated', 'overlapping_methods', 'disclosed', 'graded_at'})
        for row in records:
            self.assertEqual(set(row), set(private[0]))
            self.assertEqual(set(row['outcomes'][0]), set(private[0]['outcomes'][0]))
            self.assertFalse(row['causal_claim'])
            self.assertIsNone(row['selection']['propensity'])
        self.assertIsNotNone(published[0]['mechanisms'])
        self.assertIsNone(published[1]['mechanisms'])
        self.assertEqual(summarize_method_evidence(records), {
            ('private_strategy', self.strategy, first.method_version.digest): {
                'assigned_count': 3, 'reply_completed_count': 3, 'outcome_count': 3, 'eligible_outcome_count': 1,
                'uncertain_outcome_count': 2, 'independent_success_count': 1, 'independent_failure_count': 0,
                'excluded_disclosure_count': 1, 'excluded_repeated_count': 1, 'excluded_overlap_count': 1},
            ('public_method', 'compare', self.method.digest): {
                'assigned_count': 2, 'reply_completed_count': 2, 'outcome_count': 2, 'eligible_outcome_count': 1,
                'uncertain_outcome_count': 1, 'independent_success_count': 0, 'independent_failure_count': 1,
                'excluded_disclosure_count': 1, 'excluded_repeated_count': 0, 'excluded_overlap_count': 0},
        })

    def test_live_disclosure_source_permissions_and_unconfirmed_uses(self):
        use = self.private_use()
        task = self.task('请说明缓存未命中的数据来源。', use)
        certify = self.disclose(task)
        result = self.assessment(task, 0)
        public_task = self.task('请说明缓存命中的数据来源。')
        public = self.public_use(public_task)
        certify_public = self.disclose(public_task)
        self.assessment(public_task, 0)
        staged = self.message('试用尚未确认。', metadata={'runtime_request_id': str(uuid4())})
        LearningStrategyUse.objects.create(project=self.project, strategy_id=self.strategy, message=staged, reason='待确认')
        pending_source = ProjectLearningEvent.objects.create(project=self.project, message=staged, kind='progress',
            content={'strategy': '尚未确认的观察。'}, request_key='pending-ulr-source')
        pending_strategy = LearningStrategy.objects.create(user=self.user, source_event=pending_source)
        LearningStrategyUse.objects.create(project=self.project, strategy=pending_strategy, message=use.message, reason='待确认')
        rows = project_method_evidence(self.project)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row['eligible_for_eval'] for row in rows))
        receipt = certify()
        public_receipt = certify_public()
        for row in project_method_evidence(self.project):
            self.assertFalse(row['eligible_for_eval'])
            self.assertTrue(row['outcomes'][0]['disclosed'])
        self.assertFalse(LearningStrategyOutcome.objects.get(result=result).snapshot['disclosed'])
        learning_diagnostics.retract_text_delivery(receipt)
        learning_diagnostics.retract_text_delivery(public_receipt)
        self.assertTrue(all(row['eligible_for_eval'] for row in project_method_evidence(self.project)))

        for question in (self.source, public.question):
            question.metadata['course_context'] = {'course_id': 999999}
            question.save(update_fields=['metadata'])
        for row in project_method_evidence(self.project):
            self.assertFalse(row['source_available'] or row['eligible_for_eval'])
            self.assertIsNone(row['mechanisms'])
            self.assertIn('source_unavailable', row['outcomes'][0]['reasons'])
        self.student.is_course_student = False
        self.student.save(update_fields=['is_course_student'])
        self.assertEqual(project_method_evidence(self.project), [])
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            project_method_evidence(self.project)

    def test_compatible_bootstrap_preserves_old_and_new_frame_replay(self):
        previous_code = '672d763b69b0de63d13aad0fe3baab9514565620aca67a241bc24dcb6676ef06'
        task = self.task('请解释缓存命中的执行过程。')
        with patch.object(task_memory_store, 'CODE', previous_code):
            previous = task_memory_store.publish_policy(.61, request_key='old-evidence-frame-program')
            use = self.public_use(task)
            use.value.pop('rsi_bundle_digest')
            use.value.pop('mechanisms_status')
            use.save(update_fields=['value'])
            self.assessment(task, 0)
            now = timezone.now()
            old_frame = task_memory_store.prepare(self.project, self.user, now=now)
        self.assertNotEqual(task_memory_store.CODE, previous_code)
        self.assertEqual(old_frame['program_id'], previous.pk)
        self.assertEqual(len(old_frame['packet']['method_history']), 1)
        self.assertEqual(task_memory_store.restore(old_frame['frame_id'], self.user), old_frame['packet'])

        new_frame = task_memory_store.prepare(self.project, self.user, now=now)
        self.assertNotEqual(new_frame['program_id'], previous.pk)
        self.assertEqual(task_memory_store._bootstrap().definition['threshold'], .61)
        self.assertEqual(new_frame['packet'], old_frame['packet'])
        self.assertEqual(task_memory_store.prepare(self.project, self.user, now=now), new_frame)
        self.assertEqual(task_memory_store.restore(new_frame['frame_id'], self.user), new_frame['packet'])
        self.public_use(self.task('请解释另一个缓存场景。'))
        modern = task_memory_store.prepare(self.project, self.user, now=timezone.now())
        self.assertEqual(len(modern['packet']['method_history']), 2)
        self.assertEqual(task_memory_store.restore(modern['frame_id'], self.user), modern['packet'])
        self.assertEqual(task_memory_store.restore(old_frame['frame_id'], self.user), old_frame['packet'])
