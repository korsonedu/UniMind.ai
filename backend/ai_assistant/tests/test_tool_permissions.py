from unittest.mock import MagicMock
from ai_engine.tool_permissions import filter_tools


class TestToolPermissions:
    def _make_tools(self, names):
        return [{"function": {"name": n}} for n in names]

    def test_free_plan_assistant_basic_only(self):
        inst = MagicMock(plan="free")
        tools = self._make_tools(["search_knowledge_tree", "get_user_weak_points", "get_user_wrong_questions"])
        result = filter_tools("assistant", inst, tools)
        assert {t["function"]["name"] for t in result} == {"search_knowledge_tree", "get_user_weak_points"}

    def test_free_plan_planner_basic_only(self):
        inst = MagicMock(plan="free")
        tools = self._make_tools(["get_learning_stats", "save_study_plan", "get_due_reviews"])
        result = filter_tools("planner", inst, tools)
        names = {t["function"]["name"] for t in result}
        assert "get_learning_stats" in names
        assert "save_study_plan" not in names

    def test_free_plan_exam_generator_empty(self):
        inst = MagicMock(plan="free")
        result = filter_tools("exam_generator", inst, self._make_tools(["generate_questions"]))
        assert result == []

    def test_starter_plan_subset(self):
        inst = MagicMock(plan="starter")
        tools = self._make_tools(["search_knowledge_tree", "get_user_weak_points", "get_user_wrong_questions", "search_courses", "get_class_weak_points"])
        result = filter_tools("assistant", inst, tools)
        names = {t["function"]["name"] for t in result}
        assert "get_class_weak_points" not in names
        assert "search_courses" in names

    def test_growth_plan_all(self):
        inst = MagicMock(plan="growth")
        tools = self._make_tools(["a", "b", "c"])
        assert filter_tools("assistant", inst, tools) == tools

    def test_enterprise_plan_all(self):
        inst = MagicMock(plan="enterprise")
        tools = self._make_tools(["a", "b"])
        assert filter_tools("planner", inst, tools) == tools

    def test_none_institution_defaults_to_free(self):
        tools = self._make_tools(["search_knowledge_tree", "get_user_weak_points", "get_user_wrong_questions"])
        result = filter_tools("assistant", None, tools)
        assert {t["function"]["name"] for t in result} == {"search_knowledge_tree", "get_user_weak_points"}

    def test_unknown_plan_defaults_to_free(self):
        inst = MagicMock(plan="unknown")
        tools = self._make_tools(["search_knowledge_tree", "get_user_weak_points"])
        result = filter_tools("assistant", inst, tools)
        assert {t["function"]["name"] for t in result} == {"search_knowledge_tree", "get_user_weak_points"}

    def test_starter_planner_specific_tools(self):
        inst = MagicMock(plan="starter")
        tools = self._make_tools(["get_learning_stats", "get_knowledge_mastery_map", "get_due_reviews", "save_study_plan"])
        result = filter_tools("planner", inst, tools)
        names = {t["function"]["name"] for t in result}
        assert "save_study_plan" not in names
        assert "get_learning_stats" in names
