from unittest.mock import MagicMock
from ai_engine.tool_permissions import filter_tools


class TestToolPermissions:
    def _make_tools(self, names):
        return [{"function": {"name": n}} for n in names]

    def _mock_inst(self, plan):
        inst = MagicMock()
        inst.get_effective_plan.return_value = plan
        return inst

    def test_free_plan_assistant_basic_only(self):
        inst = self._mock_inst("free")
        tools = self._make_tools(["search_knowledge_tree", "get_user_weak_points", "get_user_wrong_questions"])
        result = filter_tools("assistant", inst, tools)
        assert {t["function"]["name"] for t in result} == {"search_knowledge_tree", "get_user_weak_points"}

    def test_free_plan_planner_basic_only(self):
        inst = self._mock_inst("free")
        tools = self._make_tools(["get_learning_stats", "get_report_card", "get_due_reviews"])
        result = filter_tools("planner", inst, tools)
        names = {t["function"]["name"] for t in result}
        assert "get_learning_stats" in names
        assert "get_report_card" not in names

    def test_free_plan_exam_generator_has_basic_tools(self):
        inst = self._mock_inst("free")
        result = filter_tools("exam_generator", inst, self._make_tools(["search_knowledge", "quick_generate", "launch_arc_pipeline"]))
        names = {t["function"]["name"] for t in result}
        assert "search_knowledge" in names
        assert "quick_generate" in names

    def test_starter_plan_subset(self):
        inst = self._mock_inst("starter")
        tools = self._make_tools(["search_knowledge_tree", "get_user_weak_points", "get_user_wrong_questions", "search_courses", "get_report_card"])
        result = filter_tools("assistant", inst, tools)
        names = {t["function"]["name"] for t in result}
        assert "get_report_card" not in names
        assert "search_courses" in names

    def test_growth_plan_all(self):
        inst = self._mock_inst("growth")
        tools = self._make_tools(["a", "b", "c"])
        assert filter_tools("assistant", inst, tools) == tools

    def test_enterprise_plan_all(self):
        inst = self._mock_inst("enterprise")
        tools = self._make_tools(["a", "b"])
        assert filter_tools("planner", inst, tools) == tools

    def test_none_institution_defaults_to_free(self):
        tools = self._make_tools(["search_knowledge_tree", "get_user_weak_points", "get_user_wrong_questions"])
        result = filter_tools("assistant", None, tools)
        assert {t["function"]["name"] for t in result} == {"search_knowledge_tree", "get_user_weak_points"}

    def test_unknown_plan_defaults_to_free(self):
        inst = self._mock_inst("unknown")
        tools = self._make_tools(["search_knowledge_tree", "get_user_weak_points"])
        result = filter_tools("assistant", inst, tools)
        assert {t["function"]["name"] for t in result} == {"search_knowledge_tree", "get_user_weak_points"}

    def test_starter_planner_specific_tools(self):
        inst = self._mock_inst("starter")
        tools = self._make_tools(["get_learning_stats", "get_knowledge_mastery_map", "get_due_reviews", "get_report_card"])
        result = filter_tools("planner", inst, tools)
        names = {t["function"]["name"] for t in result}
        assert "get_report_card" not in names
        assert "get_learning_stats" in names
