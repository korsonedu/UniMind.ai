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


class AIPreviewGenerateViewTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="admin_user",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_authenticate(user=self.admin)
        self.kp = KnowledgePoint.objects.create(
            code="MB-1001",
            name="货币供给机制",
            level="kp",
        )

    @patch("quizzes.views_ai.AIService.preview_generate_questions")
    def test_preview_timeout_returns_504(self, mock_preview):
        mock_preview.side_effect = AICallError(
            "AI 服务响应超时（>120s），请稍后重试。",
            status_code=504,
            retryable=True,
        )

        resp = self.client.post(
            "/api/quizzes/ai-smart-generate-preview/",
            {
                "kp_ids": [self.kp.id],
                "count": 2,
                "types": ["单项选择题"],
                "difficulty_level": "normal",
            },
            format="json",
        )

        self.assertEqual(resp.status_code, status.HTTP_504_GATEWAY_TIMEOUT)
        self.assertIn("超时", resp.data.get("error", ""))


class AIServiceBatchingTests(TestCase):
    def setUp(self):
        self.kp_1 = KnowledgePoint.objects.create(code="MB-1001", name="货币供给", level="kp")
        self.kp_2 = KnowledgePoint.objects.create(code="IF-2001", name="汇率决定", level="kp")

    @override_settings(AI_BULK_GENERATE_MAX_PER_REQUEST=3, AI_BULK_GENERATE_CONCURRENCY=2)
    @patch("ai_service.AIService.simple_chat")
    def test_preview_generate_split_by_kp_and_batch(self, mock_simple_chat):
        def _fake_response(*args, **kwargs):
            user_prompt = kwargs.get("user_prompt", "")
            code_match = re.search(r'"code":\s*"([^"]+)"', user_prompt)
            count_match = re.search(r'每个知识点生成题目数量：\s*(\d+)', user_prompt)
            kp_code = code_match.group(1) if code_match else "MB-1001"
            q_count = int(count_match.group(1)) if count_match else 1

            payload = []
            for i in range(q_count):
                payload.append(
                    {
                        "q_type": "objective",
                        "subjective_type": "",
                        "question": f"{kp_code} 第{i + 1}题：中央银行操作与货币乘数变化。",
                        "options": {
                            "A": "存款准备金率上调会提高货币乘数",
                            "B": "公开市场买入通常会投放基础货币",
                            "C": "法定准备金与超额准备金都不影响M2",
                            "D": "再贴现率下降必然抑制信贷扩张",
                        },
                        "answer": "B",
                        "grading_points": "无",
                        "difficulty_level": "normal",
                        "related_knowledge_id": kp_code,
                    }
                )

            return {"choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}}]}

        mock_simple_chat.side_effect = _fake_response

        generated = AIService.preview_generate_questions(
            kp_ids=[self.kp_1.id, self.kp_2.id],
            count_per_kp=5,
            target_types=["单项选择题"],
            target_difficulty="mixed",
        )

        # 2 个考点 * 每考点 (3 + 2) 分批 => 4 次模型请求
        self.assertEqual(mock_simple_chat.call_count, 4)
        self.assertEqual(len(generated), 10)
        self.assertTrue(all(item["kp_id"] in {self.kp_1.id, self.kp_2.id} for item in generated))

    @override_settings(AI_BULK_GENERATE_MAX_PER_REQUEST=3, AI_BULK_GENERATE_CONCURRENCY=1)
    @patch("ai_service.AIService.simple_chat")
    def test_preview_generate_repairs_invalid_json_payload(self, mock_simple_chat):
        def _fake_response(*args, **kwargs):
            operation = kwargs.get("operation", "")
            if operation.endswith("schema_repair"):
                repaired = [
                    {
                        "q_type": "objective",
                        "subjective_type": "",
                        "question": "MB-1001 第1题：公开市场业务对基础货币的影响。",
                        "options": {"A": "收缩基础货币", "B": "增加基础货币", "C": "不影响", "D": "必然通缩"},
                        "answer": "B",
                        "grading_points": "无",
                        "difficulty_level": "normal",
                        "related_knowledge_id": "MB-1001",
                    }
                ]
                return {"choices": [{"message": {"content": json.dumps(repaired, ensure_ascii=False)}}]}

            # 初次返回非 JSON，触发 schema repair
            return {"choices": [{"message": {"content": "以下是题目：1) ...（格式损坏）"}}]}

        mock_simple_chat.side_effect = _fake_response

        generated = AIService.preview_generate_questions(
            kp_ids=[self.kp_1.id],
            count_per_kp=1,
            target_types=["单项选择题"],
            target_difficulty="normal",
        )

        self.assertEqual(len(generated), 1)
        self.assertEqual(generated[0]["q_type"], "objective")
        self.assertGreaterEqual(mock_simple_chat.call_count, 2)

    @patch("ai_service.AIService.simple_chat")
    def test_grade_question_repairs_invalid_json_payload(self, mock_simple_chat):
        def _fake_response(*args, **kwargs):
            operation = kwargs.get("operation", "")
            if operation.endswith("schema_repair"):
                repaired = {
                    "score": 8,
                    "feedback": "要点较完整，公式应用基本正确。",
                    "analysis": "核心机制阐述到位，但边界条件说明不足。",
                    "fsrs_rating": 3,
                }
                return {"choices": [{"message": {"content": json.dumps(repaired, ensure_ascii=False)}}]}

            return {"choices": [{"message": {"content": "评分：8分，反馈如下（非JSON）"}}]}

        mock_simple_chat.side_effect = _fake_response

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
        self.assertEqual(result["fsrs_rating"], 3)
        self.assertIn("要点较完整", result["feedback"])
