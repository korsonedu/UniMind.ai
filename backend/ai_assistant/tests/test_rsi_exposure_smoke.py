"""Presentation receipts for synthetic learning turns and frozen evidence."""
from uuid import uuid4

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from ai_assistant.models import (
    AIChatMessage, Bot, Conversation, ConversationProject, LearningStrategyOutcome, LearningStrategyUse,
    ProjectLearning, ProjectLearningEvent, TaskMemoryObject, TeachingDecisionLog,
)
from ai_assistant.services import method_adoption, task_memory_store, teaching_sidecar
from ai_assistant.services.learning_library import strategy_operation
from ai_assistant.services.learning_tasks import create_task, sync_task_result
from ai_assistant.services.project_learning import completed_learning_turn
from ai_assistant.services.public_methods import publish_method
from ai_assistant.services.state.rsi.rsi_evidence import project_method_evidence
from quizzes.models import ExamQuestionResult, QuizExam
from users.login_sessions import LoginSession
from users.models import CourseStudentStatus, User, UserAccessProfile


@override_settings(UNIMIND_CONTENT_INSTITUTION_ID='global', UNIMIND_LEARNING_RUNTIME='ulr',
    UNIMIND_PRISM_MODE='off', UNIMIND_SDTM_TASK_MEMORY_MODE='active', USE_MEM0=False)
class RSIExposureSmoke(TestCase):
    url = '/api/ai/learning/exposure/present/'

    def setUp(self):
        self.user = User.objects.create_user(username='rsi_exposure_owner')
        CourseStudentStatus.objects.create(user=self.user, is_course_student=True)
        self.bot = Bot.objects.create(name='小宇', bot_type='planner')
        self.project = ConversationProject.objects.create(user=self.user, name='缓存原理')
        self.room = Conversation.objects.create(user=self.user, bot=self.bot, project=self.project, conversation_id=uuid4())
        ProjectLearning.objects.create(project=self.project, status='active', current_stage='start',
            plan={'goal': '解释缓存', 'stages': [{'id': 'start', 'title': '起点', 'knowledge_nodes': []}]})
        source = self.message('我比较了缓存命中与未命中。')
        event = ProjectLearningEvent.objects.create(project=self.project, message=source, kind='progress',
            content={'strategy': '按是否命中划分情境。'})
        strategy = strategy_operation(self.project, {'action': 'save', 'event_id': event.pk})['strategy_id']
        self.trigger = self.message('请用原来的方法解释。')
        teaching_sidecar.freeze_turn(self.project, self.trigger, {})
        use = strategy_operation(self.project, {'action': 'apply', 'strategy_id': strategy,
            'reason': '比较缓存命中与未命中。'}, message=self.trigger)
        self.use = LearningStrategyUse.objects.get(pk=use['use_id'])
        self.reply = self.completed_reply(self.trigger)
        self.decision = TeachingDecisionLog.objects.create(owner=self.user, project=self.project, message=self.trigger,
            answer=self.reply, decision_point='method_ranking', policy_version='test', selection_mode='deterministic',
            selected_action='compare', exposure={'status': 'assigned', 'adherence': 'unverified'})
        self.client = APIClient(enforce_csrf_checks=True)
        self.login(self.user)

    def login(self, user):
        self.client.cookies['auth_token'] = LoginSession.issue(user).key

    def message(self, content, *, role='user', metadata=None):
        return AIChatMessage.objects.create(user=self.user, bot=self.bot, conversation_id=self.room.conversation_id,
            role=role, content=content, metadata=metadata or {})

    def completed_reply(self, trigger):
        return self.message('未命中时需要访问主存。', role='assistant', metadata={
            'learning_turn': completed_learning_turn(trigger.pk),
            'ulr_teaching': {'action': 'offer_recheck', 'presentation': 'unknown'},
            'dsh_cards': [{'type': 'data_card', 'payload': {'title': '复查'}}]})

    def present(self, reply=None, **details):
        csrf = self.client.cookies.get('csrftoken')
        if csrf is None:
            self.client.get('/api/csrf/')
            csrf = self.client.cookies['csrftoken']
        return self.client.post(self.url, {'message_id': (reply or self.reply).pk, **details}, format='json',
            HTTP_X_CSRFTOKEN=csrf.value)

    def task(self, prompt, use=None):
        return create_task(self.project, {'stage_id': 'start', 'title': '缓存边界', 'instructions': '独立解释。',
            'purpose': 'recheck', 'strategy_use_id': use.pk if use else None,
            'definition': {'prompt': prompt, 'response_type': 'explanation', 'criteria': ['说明访问过程']}})

    def assess(self, task):
        question = task.question_snapshot['0']
        exam = QuizExam.objects.create(user=self.user, status='completed')
        task.exam, task.assistance = exam, 'independent'
        task.save(update_fields=['exam', 'assistance'])
        result = ExamQuestionResult.objects.create(exam=exam, score=question['max_score'], max_score=question['max_score'],
            user_answer='自己的解释', status='graded', graded_at=timezone.now(), question_snapshot=question)
        sync_task_result(result)
        return result

    def test_owner_receipt_and_duplicate_keep_first_presentation(self):
        teaching_sidecar.record_turn_completion(self.reply)
        rows = [self.decision, self.use]
        for row in rows:
            row.refresh_from_db()
        before = [row.exposure for row in rows]
        response = self.present(surface='recheck_card', card_type='manage_learning_tasks')
        self.assertEqual(response.status_code, 200)
        presented_at = response.data['presented_at']
        self.assertEqual(response.data, {'message_id': self.reply.pk, 'status': 'presented', 'presented_at': presented_at,
            'created': True, 'updated_decisions': 1, 'updated_strategy_uses': 1})
        duplicate = self.present(surface='hint_reply')
        self.assertEqual(duplicate.status_code, 200)
        self.assertEqual(duplicate.data, {**response.data, 'created': False, 'updated_decisions': 0, 'updated_strategy_uses': 0})
        self.reply.refresh_from_db()
        self.assertEqual(self.reply.metadata['rsi_presentation'], {'status': 'presented', 'presented_at': presented_at,
            'surface': 'recheck_card', 'card_type': 'manage_learning_tasks'})
        self.assertEqual(self.reply.metadata['ulr_teaching'], {'action': 'offer_recheck', 'presentation': 'presented',
            'presented_at': presented_at})
        for row, previous in zip(rows, before):
            row.refresh_from_db()
            self.assertEqual({key: row.exposure[key] for key in previous if key not in ('status', 'presentation')},
                {key: value for key, value in previous.items() if key not in ('status', 'presentation')})
            self.assertEqual(row.exposure['status'], 'presented')
            self.assertEqual(row.exposure['presentation'], 'presented')
            self.assertEqual(row.exposure['presented_at'], presented_at)
            self.assertEqual(row.exposure['presentation_surface'], 'recheck_card')
        self.assertEqual(self.decision.exposure['presentation_card_type'], 'manage_learning_tasks')

    def test_authorization_and_input_validation(self):
        self.assertEqual(APIClient().post(self.url, {'message_id': self.reply.pk}, format='json').status_code, 401)
        self.assertEqual(self.client.post(self.url, {'message_id': self.reply.pk}, format='json').status_code, 403)
        incomplete = self.message('未完成', role='assistant')
        self.assertEqual(self.present(incomplete).status_code, 404)
        self.assertEqual(self.present(self.trigger).status_code, 404)
        self.assertEqual(self.present(surface='unknown').status_code, 400)
        self.assertEqual(self.present(card_type=123).status_code, 400)
        self.assertEqual(self.present(card_type='x' * 65).status_code, 400)
        other = User.objects.create_user(username='rsi_exposure_other')
        profile = UserAccessProfile.objects.create(user=other, blocked_permissions=['ai.assistant'])
        self.login(other)
        self.assertEqual(self.present().status_code, 403)
        profile.delete()
        self.assertEqual(self.present().status_code, 404)
        self.login(self.user)
        self.room.user = other
        self.room.save(update_fields=['user'])
        self.assertEqual(self.present().status_code, 404)

    def test_presentation_before_completion_observer(self):
        response = self.present()
        self.assertEqual(response.status_code, 200)
        teaching_sidecar.record_turn_completion(self.reply)
        self.decision.refresh_from_db()
        self.use.refresh_from_db()
        self.assertEqual(teaching_sidecar.verified_strategy_reply(self.use)[0], self.reply)
        for row in (self.decision, self.use):
            self.assertEqual(row.exposure['status'], 'presented')
            self.assertEqual(row.exposure['presented_at'], response.data['presented_at'])
            self.assertEqual(row.exposure['reply_hash'], teaching_sidecar.canonical_hash(self.reply.content))

    def test_both_evidence_ledgers_and_frozen_frame_after_presentation(self):
        teaching_sidecar.record_turn_completion(self.reply)
        private_receipt = self.present().data
        private_result = self.assess(self.task('解释一次缓存未命中。', self.use))
        outcome = LearningStrategyOutcome.objects.get(result=private_result)
        self.assertTrue(outcome.snapshot['timing_verified'])
        self.assertEqual(outcome.snapshot['exposure']['status'], 'presented')
        self.assertFalse(outcome.snapshot['causal_claim'])

        task = self.task('解释一次缓存命中。')
        method = publish_method({'key': 'compare', 'instruction': '比较两个情境。',
            'requires': {'purpose': 'recheck'}, 'source': '合成测试'}, request_key='rsi-exposure')
        trigger = self.message('请说明另一种方法。')
        adoption = method_adoption.apply_public(self.project, {'task_id': task.pk, 'public_method_id': method.pk,
            'method_digest': method.digest, 'reason': '比较两种条件。'}, trigger)
        reply = self.completed_reply(trigger)
        method_adoption.record_completion(reply)
        frame = task_memory_store.prepare(self.project, self.user)
        self.assertEqual(len(frame['packet']['method_history']), 1)
        objects = list(TaskMemoryObject.objects.order_by('pk').values())
        public_response = self.present(reply, surface='practice_card', card_type='practice_quiz')
        self.assertEqual(public_response.status_code, 200)
        self.assertEqual(list(TaskMemoryObject.objects.order_by('pk').values()), objects)
        reply.refresh_from_db()
        self.assertEqual(reply.metadata['learning_turn']['message_id'], trigger.pk)

        self.assess(task)
        self.assertEqual(task_memory_store.restore(frame['frame_id'], self.user), frame['packet'])
        expected = {f'private:{self.use.pk}': private_receipt['presented_at'],
                    f"public:{adoption['use_id']}": public_response.data['presented_at']}
        evidence = project_method_evidence(self.project)
        self.assertEqual({row['use_id'] for row in evidence}, set(expected))
        for row in evidence:
            self.assertEqual(row['exposure'], {'status': 'presented', 'presentation': 'presented',
                'presented_at': expected[row['use_id']], 'adherence': 'unverified'})
            self.assertTrue(row['eligible_for_eval'])
            self.assertFalse(row['causal_claim'])
