import json
import re
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from ai_service import AIService
from ai_engine.service import AICallError
from users.models import User
from .models import KnowledgePoint


class AIServiceBatchingTests(TestCase):
    def setUp(self):
        self.kp_1 = KnowledgePoint.objects.create(code="MB-1001", name="货币供给", level="kp")
        self.kp_2 = KnowledgePoint.objects.create(code="IF-2001", name="汇率决定", level="kp")

    @patch("ai_engine.service.AIEngine.call_ai")
    def test_grade_question_extracts_json_from_text(self, mock_call_ai):
        # 模型未调用工具、把 JSON 混在正文里：structured_output 的 regex fallback 应提取成功
        repaired = {
            "score": 8,
            "feedback": "要点较完整，公式应用基本正确。",
            "analysis": "核心机制阐述到位，但边界条件说明不足。",
            "memorix_rating": 3,
        }
        mock_call_ai.return_value = {
            "choices": [{"message": {"content": f"评分结果如下：{json.dumps(repaired, ensure_ascii=False)}（以上为评分）"}}]
        }

        result = AIService.grade_question(
            question_text="说明 IS 曲线右移的机制。",
            user_answer="投资增加导致总需求上升。",
            correct_answer="从投资函数、商品市场均衡推导 IS 右移。",
            q_type="subjective",
            max_score=10,
            grading_points="1. 原理 2. 机制 3. 结论",
            subjective_type="简答题",
        )

        self.assertEqual(result["score"], 8.0)
        self.assertEqual(result["memorix_rating"], 3)
        self.assertIn("要点较完整", result["feedback"])


class KnowledgeTreeImportMatchTests(TestCase):
    """导入匹配：同 code 必须同 parent 才算同一节点，否则跨分支错配（历史事故：重复长树）。"""

    def setUp(self):
        from users.models import Institution

        self.inst = Institution.objects.create(
            name="导入测试机构", slug="import-test", contact_name="T", contact_email="t@example.com",
        )

    @staticmethod
    def _tree(sub_name="模块A", kp_name="考点1"):
        return [{
            "code": "SUB-01", "name": sub_name, "level": "sub",
            "children": [{"code": "KP-01", "name": kp_name, "level": "kp", "children": []}],
        }]

    def test_reimport_updates_instead_of_creating(self):
        from .views_knowledge import _create_or_update_knowledge_tree

        created, updated = _create_or_update_knowledge_tree(self._tree(), institution=self.inst)
        self.assertEqual((created, updated), (2, 0))

        created2, updated2 = _create_or_update_knowledge_tree(
            self._tree(sub_name="模块A改名", kp_name="考点1改名"), institution=self.inst,
        )
        self.assertEqual((created2, updated2), (0, 2))
        self.assertEqual(KnowledgePoint.objects.filter(institution=self.inst).count(), 2)

    def test_same_code_under_different_parent_creates_separate_nodes(self):
        from .views_knowledge import _create_or_update_knowledge_tree

        tree = [{
            "code": "SUB-01", "name": "模块A", "level": "sub",
            "children": [
                {"code": "SEC-01", "name": "小节1", "level": "sec", "children": [
                    {"code": "KP-01", "name": "考点甲", "level": "kp", "children": []}]},
                {"code": "SEC-02", "name": "小节2", "level": "sec", "children": [
                    {"code": "KP-01", "name": "考点乙", "level": "kp", "children": []}]},
            ],
        }]
        created, updated = _create_or_update_knowledge_tree(tree, institution=self.inst)
        self.assertEqual((created, updated), (5, 0))

        kps = KnowledgePoint.objects.filter(code="KP-01", institution=self.inst)
        self.assertEqual(kps.count(), 2)
        self.assertEqual({k.name for k in kps}, {"考点甲", "考点乙"})

        created2, updated2 = _create_or_update_knowledge_tree(tree, institution=self.inst)
        self.assertEqual((created2, updated2), (0, 5))
