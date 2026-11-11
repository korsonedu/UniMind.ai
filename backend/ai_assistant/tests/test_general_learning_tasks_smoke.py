"""Small cross-domain checks for owned open tasks and formal grading recovery."""
from unittest.mock import patch

from django.test import override_settings
from rest_framework.exceptions import ValidationError
from rest_framework.test import APITestCase

from ai_assistant.models import ConversationProject, ProjectLearning, ProjectLearningEvent, ProjectLearningTask
from ai_assistant.services.learning_tasks import create_task, task_data, task_result_snapshot
from quizzes.ai_workflow import run_exam_grading
from quizzes.models import Question, KnowledgePoint, QuizExam, UserQuestionStatus
from quizzes.services.practice_results import exam_result_payload
from users.models import User, CourseStudentStatus


@override_settings(UNIMIND_CONTENT_INSTITUTION_ID='global', USE_MEM0=False,
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class GeneralLearningTasksSmoke(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='general_tasks_synthetic')
        CourseStudentStatus.objects.create(user=self.user, is_course_student=True)
        self.project = ConversationProject.objects.create(user=self.user, name='通用学习')
        self.state = ProjectLearning.objects.create(project=self.project, status='active',
            plan={'goal': '说明原理', 'stages': [{'id': 'start', 'title': '起点', 'knowledge_nodes': []}]})
        self.client.force_authenticate(self.user)
        self.arguments = {'stage_id': 'start', 'title': '说明原因', 'instructions': '先独立说明，再根据反馈调整。',
            'purpose': 'diagnostic', 'definition': {'prompt': '请解释一个输入为什么只能有一个输出。',
                'response_type': 'reasoning', 'criteria': ['说明输入输出关系', '给出能支持判断的理由'],
                'reference_answer': '内部参考：固定输入应有唯一输出。'}}

    def submit(self, task, answer='我先固定输入，再检查它是否唯一对应输出。'):
        with patch('quizzes.views_exam.dispatch_exam_grading'), self.captureOnCommitCallbacks(execute=True):
            return self.client.post('/api/quizzes/submit-exam/', {'learning_task_id': str(task.pk),
                'submission_id': str(task.pk), 'assistance': 'independent',
                'answers': [{'question_id': 0, 'answer': answer}]}, format='json')

    def grade(self, exam_id, failure=False):
        returned = {'score': 8, 'feedback': '说明了主要条件，还可补充反例。', 'analysis': '按给出的标准逐项检查。', 'memorix_rating': 4}
        with patch('quizzes.ai_workflow.AIService.grade_question', side_effect=ValueError('synthetic temporary failure') if failure else None, return_value=returned), self.captureOnCommitCallbacks(execute=True):
            run_exam_grading(self.user.pk, exam_id)

    def test_cross_domain_private_tasks_have_one_owned_recoverable_grade_without_bank_side_effects(self):
        elo = self.user.elo_score
        for response_type, prompt in [('calculation', '请写出一次函数值代入的计算过程。'),
                ('explanation', '请解释计算机缓存为什么能减少访存时间。'),
                ('case', '请说明备考案例中这个判断成立的条件。')]:
            with self.subTest(response_type=response_type):
                task = create_task(self.project, {**self.arguments, 'definition': {
                    **self.arguments['definition'], 'prompt': prompt, 'response_type': response_type}})
                public = task_data(task)
                self.assertIsNone(public['version_id'])
                self.assertEqual(public['payload']['questions'][0]['id'], 0)
                self.assertNotIn('内部参考', str(public))
                response = self.submit(task)
                self.assertEqual(response.status_code, 202, response.data)
                exam_id = response.data['exam_id']
                self.assertEqual(self.submit(task).data['exam_id'], exam_id)
                pending = exam_result_payload(QuizExam.objects.get(pk=exam_id))
                self.assertEqual(pending['results'][0]['correct_answer'], '')
                self.assertEqual(pending['results'][0]['analysis'], '')
                self.grade(exam_id); self.grade(exam_id)
                task.refresh_from_db()
                self.assertEqual(task_data(task)['status'], 'completed')
                self.assertEqual(task_data(task)['summary']['label_source'], 'model_rubric_grade')
                self.assertIn('尚未独立复核', task_data(task)['summary']['summary_text'])
                result = task.exam.results.get()
                self.assertIsNone(result.question_id)
                self.assertEqual(task_result_snapshot(task, result)['criteria'], task.definition['criteria'])
                recovered = self.client.get(f'/api/quizzes/submissions/{task.pk}/').data
                self.assertEqual(recovered['answers'][0]['answer'], result.user_answer)
                self.assertEqual(recovered['assistance'], 'independent')
        self.assertEqual(ProjectLearningEvent.objects.filter(kind='assessment').count(), 3)
        self.assertEqual(Question.objects.count(), 0)
        self.assertEqual(KnowledgePoint.objects.count(), 0)
        self.assertEqual(UserQuestionStatus.objects.count(), 0)
        self.user.refresh_from_db(); self.assertEqual(self.user.elo_score, elo)

    def test_failed_private_grading_retries_original_submission_and_snapshot_changes_are_rejected(self):
        task = create_task(self.project, self.arguments)
        response = self.submit(task); self.assertEqual(response.status_code, 202)
        self.grade(response.data['exam_id'], failure=True)
        task.refresh_from_db(); self.assertEqual(task_data(task)['status'], 'failed')
        self.assertEqual(ProjectLearningEvent.objects.filter(kind='assessment').count(), 0)
        with patch('quizzes.views_exam.dispatch_exam_grading'), self.captureOnCommitCallbacks(execute=True):
            retried = self.client.post(f'/api/quizzes/exams/{task.exam_id}/retry/', {'question_id': 0}, format='json')
        self.assertEqual(retried.status_code, 202)
        self.grade(task.exam_id)
        task.refresh_from_db(); self.assertEqual(task_data(task)['status'], 'completed')
        self.assertEqual(ProjectLearningEvent.objects.filter(kind='assessment').count(), 1)
        changed = create_task(self.project, self.arguments)
        changed.definition['criteria'] = ['被事后替换的标准']
        changed.save(update_fields=['definition'])
        self.assertEqual(self.submit(changed).status_code, 400)
        foreign = User.objects.create_user(username='general_task_other')
        CourseStudentStatus.objects.create(user=foreign, is_course_student=True)
        self.client.force_authenticate(foreign)
        self.assertEqual(self.submit(task).status_code, 404)

    def test_recheck_requires_different_content_and_owned_parent_and_actual_sources(self):
        source = create_task(self.project, self.arguments)
        with self.assertRaises(ValidationError):
            create_task(self.project, {**self.arguments, 'purpose': 'recheck', 'source_task_id': str(source.pk)})
        next_arguments = {**self.arguments, 'purpose': 'recheck', 'source_task_id': str(source.pk), 'definition': {
            **self.arguments['definition'], 'prompt': '请用另一种情境说明输入和输出的对应关系。'}}
        next_task = create_task(self.project, next_arguments)
        self.assertEqual(next_task.source_task_id, source.pk)
        with self.assertRaises(ValidationError):
            create_task(self.project, {**self.arguments, 'definition': {**self.arguments['definition'], 'sources': ['invented-source']}})
        other = ConversationProject.objects.create(user=self.user, name='另一个项目')
        ProjectLearning.objects.create(project=other, status='active', plan=self.state.plan)
        self.assertEqual(self.client.post(f'/api/ai/projects/{other.pk}/learning/tasks/', next_arguments, format='json').status_code, 404)

    def test_bank_subjective_reuses_existing_memorix_and_rejects_missing_rubric(self):
        question = Question.objects.create(text='说明一种缓存命中过程。', q_type='subjective', subjective_type='short',
            grading_points='说明先查缓存再访存', correct_answer='先查缓存，未命中再访问主存。')
        task = create_task(self.project, {key: value for key, value in self.arguments.items() if key != 'definition'} |
            {'question_ids': [question.pk]})
        with patch('quizzes.views_exam.dispatch_exam_grading'), self.captureOnCommitCallbacks(execute=True):
            response = self.client.post('/api/quizzes/submit-exam/', {'learning_task_id': str(task.pk),
                'submission_id': str(task.pk), 'assistance': 'hint', 'answers': [{'question_id': question.pk, 'answer': '先查缓存。'}]}, format='json')
        self.assertEqual(response.status_code, 202, response.data)
        with patch('quizzes.ai_workflow._queue_experience_verification'):
            self.grade(response.data['exam_id'])
        task.refresh_from_db()
        self.assertEqual(task_data(task)['summary']['label_source'], 'model_rubric_grade')
        self.assertEqual(UserQuestionStatus.objects.get(user=self.user, question=question).reps, 1)
        question.grading_points = ''; question.save(update_fields=['grading_points'])
        with self.assertRaises(ValidationError):
            create_task(self.project, {key: value for key, value in self.arguments.items() if key != 'definition'} |
                {'question_ids': [question.pk]})

    def test_permission_revoked_during_model_call_stops_result_commit(self):
        from users.models import UserAccessProfile
        UserAccessProfile.objects.create(user=self.user)
        task = create_task(self.project, self.arguments)
        response = self.submit(task)
        def revoke(**arguments):
            UserAccessProfile.objects.filter(user=self.user).update(blocked_permissions=['quiz.exam'])
            return {'score': 9, 'feedback': '模型完成评价', 'analysis': '结果不得在撤权后写回', 'memorix_rating': 4}
        with patch('quizzes.ai_workflow.AIService.grade_question', side_effect=revoke), self.captureOnCommitCallbacks(execute=True):
            run_exam_grading(self.user.pk, response.data['exam_id'])
        task.refresh_from_db()
        self.assertNotEqual(task.exam.results.get().status, 'graded')
        self.assertFalse(ProjectLearningEvent.objects.filter(project=self.project,kind='assessment').exists())

    def test_cross_source_recheck_cannot_copy_original_prompt(self):
        bank = Question.objects.create(text='解释机会成本的含义。', q_type='subjective',grading_points='指出最佳替代用途。')
        original = create_task(self.project, {key:value for key,value in self.arguments.items() if key!='definition'} | {'question_ids':[bank.pk]})
        with self.assertRaises(ValidationError):
            create_task(self.project, {**self.arguments,'purpose':'recheck','source_task_id':str(original.pk),'definition':{**self.arguments['definition'],'prompt':bank.text}})

    def test_same_prompt_across_bank_and_personal_tasks_is_one_knowledge_observation(self):
        from django.utils import timezone
        from ai_assistant.models import LearningKnowledgeMap, LearningKnowledgeVersion
        from ai_assistant.services.learning_tasks import sync_task_result
        from ai_assistant.services.learning_task_evidence import formal_observations
        from quizzes.models import ExamQuestionResult
        mapping = LearningKnowledgeMap.objects.create(user=self.user,title='合成知识')
        version = LearningKnowledgeVersion.objects.create(knowledge_map=mapping,revision=1,snapshot={'nodes':[{'id':'n'}]})
        self.state.plan = {'knowledge_path':{'version_id':version.pk},'stages':[{'id':'start','knowledge_nodes':['n']}]}
        self.state.save(update_fields=['plan'])
        bank = Question.objects.create(text='请解释一个输入为什么只能有一个输出。',q_type='subjective',grading_points='说明唯一性。')
        args = {**self.arguments,'version_id':version.pk,'node_id':'n'}
        first = create_task(self.project,{key:value for key,value in args.items() if key!='definition'} | {'question_ids':[bank.pk]})
        second = create_task(self.project,args)
        for task in (first, second):
            exam=QuizExam.objects.create(user=self.user,status='completed',total_questions=1)
            task.exam=exam;task.assistance='independent';task.save(update_fields=['exam','assistance'])
            snapshot=task.question_snapshot['0' if task.definition else str(bank.pk)]
            result=ExamQuestionResult.objects.create(exam=exam,question=None if task.definition else bank,position=1,user_answer='每个输入唯一输出。',score=9,max_score=10,is_correct=True,status='graded',graded_at=timezone.now(),question_snapshot=snapshot)
            sync_task_result(result)
        observations, provenance=formal_observations(self.project,version.pk)
        self.assertEqual(len(observations),1)
        self.assertEqual(provenance['repeated_questions'],1)
        self.assertEqual(observations[0]['label_source'],'model_rubric_grade')

    def test_remediation_can_use_another_planned_stage_without_combining_results(self):
        source = create_task(self.project,self.arguments)
        self.state.plan['stages'].append({'id':'smaller','title':'补前置','knowledge_nodes':[]})
        self.state.save(update_fields=['plan'])
        child=create_task(self.project,{**self.arguments,'stage_id':'smaller','source_task_id':str(source.pk),'definition':{**self.arguments['definition'],'prompt':'请先说明什么是一个确定的输入。'}})
        self.assertEqual(child.source_task_id,source.pk)
        self.assertEqual(child.stage_id,'smaller')
