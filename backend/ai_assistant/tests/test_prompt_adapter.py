"""Tests for prompt_adapter — pattern detection and adaptive directive generation."""
from django.test import SimpleTestCase
from ai_assistant.services.prompt_adapter import detect_patterns, get_adaptive_directives


class TestDetectPatterns(SimpleTestCase):
    def test_empty_memories(self):
        self.assertEqual(detect_patterns([]), [])

    def test_none_input(self):
        self.assertEqual(detect_patterns(None), [])

    def test_formula_oriented(self):
        memories = [{"memory": "用户经常问公式推导和证明过程"}]
        labels = detect_patterns(memories)
        self.assertIn("formula_oriented", labels)

    def test_visual_learner(self):
        memories = [{"memory": "用户喜欢用图表和思维导图来理解概念"}]
        labels = detect_patterns(memories)
        self.assertIn("visual_learner", labels)

    def test_example_driven(self):
        memories = [{"memory": "用户偏好具体案例和实例讲解"}]
        labels = detect_patterns(memories)
        self.assertIn("example_driven", labels)

    def test_prefers_brief(self):
        memories = [{"memory": "用户要求回答简洁精简，不要太长"}]
        labels = detect_patterns(memories)
        self.assertIn("prefers_brief", labels)

    def test_prefers_detailed(self):
        memories = [{"memory": "用户希望回答详细展开，全面说明"}]
        labels = detect_patterns(memories)
        self.assertIn("prefers_detailed", labels)

    def test_deep_questioner(self):
        memories = [{"memory": "用户经常追问为什么，想知道本质和原理"}]
        labels = detect_patterns(memories)
        self.assertIn("deep_questioner", labels)

    def test_multiple_patterns(self):
        memories = [
            {"memory": "用户喜欢公式推导"},
            {"memory": "用户要求简洁回答"},
        ]
        labels = detect_patterns(memories)
        self.assertIn("formula_oriented", labels)
        self.assertIn("prefers_brief", labels)

    def test_agent_memory_format(self):
        """Should also work with AgentMemory key+value format."""
        memories = [{"key": "学习偏好", "value": "喜欢用具体例子理解概念"}]
        labels = detect_patterns(memories)
        self.assertIn("example_driven", labels)

    def test_no_match(self):
        memories = [{"memory": "今天天气不错"}]
        labels = detect_patterns(memories)
        self.assertEqual(labels, [])


class TestGetAdaptiveDirectives(SimpleTestCase):
    def test_empty_memories_returns_empty(self):
        self.assertEqual(get_adaptive_directives([]), "")

    def test_returns_formatted_string(self):
        memories = [{"memory": "用户经常问公式推导"}]
        result = get_adaptive_directives(memories)
        self.assertIn("## 自适应指令", result)
        self.assertIn("公式推导", result)

    def test_no_match_returns_empty(self):
        memories = [{"memory": "今天天气不错"}]
        self.assertEqual(get_adaptive_directives(memories), "")
