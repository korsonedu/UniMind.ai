from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from django.test import SimpleTestCase
from ai_assistant.services.learning_guidance import teaching_guidance


class TeachingGuidanceSmoke(SimpleTestCase):
    def test_same_teaching_episode_across_domains(self):
        for subject in ('函数定义域', '计算机缓存', '备考概念辨析'):
            with self.subTest(subject=subject):
                state = SimpleNamespace(status='active', current_stage='s', feedback='', next_action='了解起点', plan={'stages': [{'id': 's', 'title': subject}]})
                def task(key, prompt, score, assistance='independent', status='completed'):
                    return {'id': str(key), 'stage_id': 's', 'title': subject, 'status': status, 'purpose': 'practice',
                        'assistance': assistance, 'source_task_id': '1' if key in (2, 3) else '4' if key > 4 else None, 'created_at': (datetime(2026, 11, 11, tzinfo=timezone.utc) + timedelta(minutes=key)).isoformat(),
                        'summary': {'total_score': score, 'max_score': 10, 'label_source': 'model_rubric_grade'},
                        'payload': {'questions': [{'text': prompt}]}}
                first = task(1, '请解释第一个具体问题', 3)
                self.assertEqual(teaching_guidance(state, [first])['status'], 'remediate')
                again = task(2, '请解释另一个具体问题', 2)
                self.assertTrue(teaching_guidance(state, [first, again])['stalled'])
                helped = task(3, '获得提示后完成的任务', 9, 'hint')
                self.assertEqual(teaching_guidance(state, [first, again, helped])['status'], 'recheck')
                one = task(4, '独立完成的新任务一', 8)
                self.assertEqual(teaching_guidance(state, [one])['status'], 'recheck')
                repeated = task(5, '独立完成的新任务一', 9)
                self.assertEqual(teaching_guidance(state, [one, repeated])['status'], 'recheck')
                two = task(6, '独立完成的新任务二', 9)
                result = teaching_guidance(state, [one, two])
                self.assertEqual(result['status'], 'review')
                self.assertIn('尚未独立复核', result['feedback'])
                self.assertEqual(state.status, 'active')
                failed = task(7, '评价系统未完成', 0, status='failed')
                self.assertEqual(teaching_guidance(state, [one, failed])['status'], 'retry')
                state.status = 'paused'
                self.assertEqual(teaching_guidance(state, [one, failed])['status'], 'inactive')

    def test_new_observation_and_removed_stage_do_not_force_old_task_route(self):
        state = SimpleNamespace(status='active', current_stage='new', feedback='后续真实回答已澄清问题', next_action='沿新例子继续', plan={'stages': [{'id': 'new'}]})
        old = {'id':'old', 'stage_id':'removed', 'status':'ready'}
        self.assertEqual(teaching_guidance(state, [old])['status'], 'start')

    def test_latest_dialogue_and_distinct_nodes_keep_separate_evidence(self):
        at = datetime(2026, 11, 11, tzinfo=timezone.utc)
        state = SimpleNamespace(status='active', current_stage='s', feedback='新回答已经澄清，请换一个例子', next_action='继续新例子', plan={'stages': [{'id':'s'}]})
        def task(key, node, status='completed'):
            return {'id':str(key),'stage_id':'s','node_id':node,'mode':'apply','status':status,'assistance':'independent','title':'实际任务',
                'created_at':at.isoformat(),'summary':{'created_at':(at+timedelta(minutes=key)).isoformat(), 'completed_at':(at+timedelta(minutes=key)).isoformat() if status=='completed' else None,'total_score':9,'max_score':10},
                'payload':{'questions':[{'text':str(key)}]}}
        self.assertEqual(teaching_guidance(state,[task(1,'a'),task(2,'b')])['status'],'recheck')
        old = task(1, 'a', 'failed')
        self.assertEqual(teaching_guidance(state,[old],progress_at=at+timedelta(minutes=2))['next_action'], state.next_action)
        new_ready = {**task(3, 'a', 'ready'), 'summary': None, 'created_at': (at+timedelta(minutes=3)).isoformat()}
        self.assertEqual(teaching_guidance(state,[old,new_ready],progress_at=at+timedelta(minutes=2))['next_action'],state.next_action)
        new_submission = task(3, 'a', 'processing')
        self.assertEqual(teaching_guidance(state,[old,new_submission],progress_at=at+timedelta(minutes=2))['status'],'awaiting')
