"""
Experience Router — Phase 1+2 集成测试。

测试：
1. 轨迹格式化
2. 提取结果解析
3. 路由验证
4. 去重合并
5. 触发匹配
6. Prompt 注入
7. 衰减逻辑
"""

import json
from datetime import timedelta
from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model

from ai_assistant.models import AITrajectory, Experience, Bot, AgentMemory
from ai_assistant.services.experience_extractor import (
    format_trajectory_for_extraction,
    _parse_extraction_result,
    save_experiences,
)
from ai_assistant.services.experience_router import (
    validate_routing,
    find_duplicates,
    merge_experiences,
    apply_decay,
    retire_experience,
    _title_similarity,
)
from ai_assistant.services.experience_applicator import (
    get_applicable_experiences,
    inject_experiences_into_prompt,
    apply_memory_experiences,
    record_trigger,
)


User = get_user_model()


class TrajectoryFormattingTest(TestCase):
    """测试轨迹文本格式化。"""

    def test_format_basic_trajectory(self):
        """基础轨迹格式化。"""
        user = User.objects.create_user(
            username='test_student_fmt', password='pass',
            email='fmt@test.com',
        )
        bot = Bot.objects.create(
            name='test-bot', bot_type='planner',
            system_prompt='test',
        )
        trajectory = AITrajectory.objects.create(
            user=user, bot=bot,
            conversation_id='00000000-0000-0000-0000-000000000001',
            messages=[
                {'role': 'user', 'content': '帮我讲解因式分解'},
                {'role': 'assistant', 'content': '我们从图形化的角度来理解因式分解...'},
            ],
            tool_calls=[
                {'name': 'search_knowledge_tree', 'args': {'query': '因式分解'}},
                {'name': 'render_visual', 'args': {'type': 'graph'}},
            ],
            tool_outputs=[
                json.dumps({'nodes': [{'id': 1, 'name': '因式分解'}]}),
                json.dumps({'url': '/vis/123.png'}),
            ],
            outcome='success',
            outcome_metrics={'auto_evaluated': True, 'auto_confidence': 0.75},
        )

        text = format_trajectory_for_extraction(trajectory)

        self.assertIn('因式分解', text)
        self.assertIn('search_knowledge_tree', text)
        self.assertIn('render_visual', text)
        self.assertIn('成功', text)  # get_outcome_display() 返回中文
        self.assertNotIn('password', text.lower())  # 不含敏感信息


class ExtractionParsingTest(TestCase):
    """测试 LLM 输出解析。"""

    def test_parse_bare_json_array(self):
        """解析裸 JSON 数组。"""
        content = '''
[
  {
    "title": "因式分解用图形化引导",
    "dimension": "prompt",
    "scope_type": "global",
    "scope_value": {},
    "trigger": {"event": "讲解", "condition": "涉及因式分解时触发"},
    "effect": {"instruction": "用面积模型或几何图形辅助讲解因式分解"},
    "confidence": "low",
    "rationale": "学生反馈图形化理解比代数推导直观"
  }
]
'''
        result = _parse_extraction_result(content)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['title'], '因式分解用图形化引导')
        self.assertEqual(result[0]['dimension'], 'prompt')

    def test_parse_markdown_codeblock(self):
        """解析 markdown ```json 包裹的 JSON。"""
        content = '''```json
[
  {"title": "test", "dimension": "memory", "scope_type": "student",
   "scope_value": {"student_id": 1}, "trigger": {"event": "出题"},
   "effect": {"instruction": "test memory"}, "confidence": "low",
   "rationale": "test"}
]
```'''
        result = _parse_extraction_result(content)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['dimension'], 'memory')
        self.assertEqual(result[0]['scope_value']['student_id'], 1)

    def test_parse_empty_array(self):
        """解析空数组。"""
        result = _parse_extraction_result('[]')
        self.assertEqual(result, [])

    def test_parse_invalid(self):
        """解析无效 JSON 返回空。"""
        result = _parse_extraction_result('not json')
        self.assertEqual(result, [])


class RoutingValidationTest(TestCase):
    """测试路由验证。"""

    def setUp(self):
        self.bot = Bot.objects.create(
            name='test-bot', bot_type='planner',
            system_prompt='test',
        )

    def _make_exp(self, **kwargs):
        return Experience(
            title=kwargs.get('title', '测试规律'),
            dimension=kwargs.get('dimension', 'prompt'),
            scope_type=kwargs.get('scope_type', 'global'),
            scope_value=kwargs.get('scope_value', {}),
            trigger=kwargs.get('trigger', {}),
            effect=kwargs.get('effect', {'instruction': 'test'}),
        )

    def test_valid_global_prompt(self):
        exp = self._make_exp()
        self.assertTrue(validate_routing(exp))

    def test_invalid_dimension(self):
        exp = self._make_exp(dimension='invalid_dim')
        self.assertFalse(validate_routing(exp))

    def test_invalid_scope_type(self):
        exp = self._make_exp(scope_type='invalid_scope')
        self.assertFalse(validate_routing(exp))

    def test_student_scope_missing_id(self):
        exp = self._make_exp(scope_type='student', scope_value={})
        self.assertFalse(validate_routing(exp))

    def test_student_scope_with_id(self):
        exp = self._make_exp(scope_type='student', scope_value={'student_id': 123})
        self.assertTrue(validate_routing(exp))

    def test_kp_chain_scope_missing_id(self):
        exp = self._make_exp(scope_type='kp_chain', scope_value={})
        self.assertFalse(validate_routing(exp))

    def test_title_too_short(self):
        exp = self._make_exp(title='ab')
        self.assertFalse(validate_routing(exp))


class DedupTest(TestCase):
    """测试去重。"""

    def test_title_similarity_identical(self):
        self.assertGreater(_title_similarity('因式分解用图形化引导', '因式分解用图形化引导'), 0.9)

    def test_title_similarity_different(self):
        self.assertLess(_title_similarity('因式分解', '二次函数求根'), 0.5)

    def test_find_duplicates(self):
        e1 = Experience.objects.create(
            title='因式分解用图形化引导', dimension='prompt',
            scope_type='global', effect={'instruction': 'v1'},
        )
        e2 = Experience.objects.create(
            title='因式分解用图形化教学', dimension='prompt',
            scope_type='global', effect={'instruction': 'v2'},
        )

        dups = find_duplicates(e2)
        self.assertEqual(len(dups), 1)
        self.assertEqual(dups[0].id, e1.id)

    def test_merge(self):
        e1 = Experience.objects.create(
            title='test rule', dimension='prompt',
            scope_type='global', effect={'instruction': 'v1'},
            weight=1.0,
        )
        e2 = Experience.objects.create(
            title='test rule v2', dimension='prompt',
            scope_type='global', effect={'instruction': 'v2'},
            weight=1.0,
        )

        merge_experiences(e1, e2)

        e1.refresh_from_db()
        e2.refresh_from_db()
        self.assertEqual(e1.weight, 2.0)
        self.assertEqual(e2.status, 'retired')


class TriggerMatchingTest(TestCase):
    """测试触发条件匹配。"""

    def setUp(self):
        self.exp_global = Experience.objects.create(
            title='全局讲解策略', dimension='prompt',
            scope_type='global',
            trigger={'event': '讲解'},
            effect={'instruction': 'test'},
            confidence='medium',
        )
        self.exp_student = Experience.objects.create(
            title='张三个体策略', dimension='memory',
            scope_type='student',
            scope_value={'student_id': 123},
            trigger={'event': '出题'},
            effect={'instruction': 'test'},
            confidence='medium',
        )
        self.exp_kp = Experience.objects.create(
            title='因式分解策略', dimension='workflow',
            scope_type='kp_chain',
            scope_value={'kp_id': 45},
            trigger={},
            effect={'instruction': 'test'},
            confidence='medium',
        )

    def test_global_matches_any_context(self):
        result = get_applicable_experiences({'event': '讲解'})
        self.assertIn(self.exp_global.id, [e.id for e in result])

    def test_student_scope_match(self):
        result = get_applicable_experiences({'event': '出题', 'student_id': 123})
        self.assertIn(self.exp_student.id, [e.id for e in result])

    def test_student_scope_no_match(self):
        result = get_applicable_experiences({'event': '出题', 'student_id': 999})
        ids = [e.id for e in result]
        self.assertNotIn(self.exp_student.id, ids)

    def test_kp_scope_exact_match(self):
        result = get_applicable_experiences({'event': '讲解', 'kp_id': 45})
        self.assertIn(self.exp_kp.id, [e.id for e in result])

    def test_kp_scope_no_match(self):
        result = get_applicable_experiences({'event': '讲解', 'kp_id': 99})
        ids = [e.id for e in result]
        self.assertNotIn(self.exp_kp.id, ids)

    def test_event_filter_mismatch(self):
        result = get_applicable_experiences({'event': '答疑'})
        ids = [e.id for e in result]
        self.assertNotIn(self.exp_global.id, ids)  # 需要 "讲解" event


class PromptInjectionTest(TestCase):
    """测试 Prompt 注入。"""

    def test_inject_empty(self):
        result = inject_experiences_into_prompt('你是学习助手', [])
        self.assertEqual(result, '你是学习助手')

    def test_inject_single(self):
        exp = Experience(
            title='图形化引导', dimension='prompt',
            effect={'instruction': '用图形化方法讲解因式分解'},
        )
        result = inject_experiences_into_prompt('你是学习助手', [exp])
        self.assertIn('教学经验指引', result)
        self.assertIn('图形化方法讲解因式分解', result)
        self.assertIn('Prompt 策略', result)

    def test_inject_respects_max_chars(self):
        exp = Experience(
            title='长规律', dimension='prompt',
            effect={'instruction': 'x' * 900},
        )
        result = inject_experiences_into_prompt('你是学习助手', [exp], max_chars=100)
        # 注入部分不应超过 max_chars
        injected = result[len('你是学习助手'):]
        self.assertLess(len(injected), 150)


class MemoryApplicationTest(TestCase):
    """测试 Memory 维度写入。"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='test_student', password='pass',
            email='student@test.com',
        )

    def test_apply_memory_experiences(self):
        exp = Experience.objects.create(
            title='张三符号弱', dimension='memory',
            scope_type='student', scope_value={'student_id': self.user.id},
            effect={'instruction': '降低符号依赖题型比例'},
            confidence='medium',
        )

        saved = apply_memory_experiences(self.user, [exp])
        self.assertEqual(saved, 1)

        memory = AgentMemory.objects.get(key=f'experience:{exp.id}')
        self.assertIn('符号', memory.value)

    def test_no_duplicate_memory(self):
        exp = Experience.objects.create(
            title='张三符号弱', dimension='memory',
            scope_type='student', scope_value={'student_id': self.user.id},
            effect={'instruction': '降低符号依赖题型比例'},
            confidence='medium',
        )

        # 第一次写入
        apply_memory_experiences(self.user, [exp])
        # 第二次不应重复写入
        saved = apply_memory_experiences(self.user, [exp])
        self.assertEqual(saved, 0)


class DecayTest(TestCase):
    """测试衰减逻辑。"""

    def setUp(self):
        self.bot = Bot.objects.create(
            name='test-bot', bot_type='planner',
            system_prompt='test',
        )

    def test_decay_30days(self):
        now = timezone.now()
        exp = Experience.objects.create(
            title='old rule', dimension='prompt',
            scope_type='global', effect={'instruction': 'test'},
            weight=10.0, last_triggered_at=now - timedelta(days=35),
        )

        affected = apply_decay()
        self.assertGreaterEqual(affected, 1)

        exp.refresh_from_db()
        self.assertLess(exp.weight, 10.0)  # 衰减了

    def test_dormant_60days(self):
        now = timezone.now()
        exp = Experience.objects.create(
            title='very old rule', dimension='prompt',
            scope_type='global', effect={'instruction': 'test'},
            last_triggered_at=now - timedelta(days=65),
            status='active',
        )

        apply_decay()

        exp.refresh_from_db()
        self.assertEqual(exp.status, 'dormant')

    def test_archived_90days(self):
        now = timezone.now()
        exp = Experience.objects.create(
            title='ancient rule', dimension='prompt',
            scope_type='global', effect={'instruction': 'test'},
            last_triggered_at=now - timedelta(days=95),
            status='dormant',
        )

        apply_decay()

        exp.refresh_from_db()
        self.assertEqual(exp.status, 'archived')

    def test_retire_on_failure(self):
        exp = Experience.objects.create(
            title='bad rule', dimension='prompt',
            scope_type='global', effect={'instruction': 'test'},
            verify_fail_count=2,
        )

        retire_experience(exp, '验证连续失败')

        exp.refresh_from_db()
        self.assertEqual(exp.status, 'retired')
        self.assertEqual(exp.verify_fail_count, 3)


class RecordTriggerTest(TestCase):
    """测试触发时间记录。"""

    def test_record_trigger_updates_timestamp(self):
        exp = Experience.objects.create(
            title='test', dimension='prompt',
            scope_type='global', effect={'instruction': 'test'},
        )

        count = record_trigger([exp])
        self.assertEqual(count, 1)

        exp.refresh_from_db()
        self.assertIsNotNone(exp.last_triggered_at)
