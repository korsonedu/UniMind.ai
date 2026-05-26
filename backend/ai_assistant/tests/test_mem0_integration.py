"""
Integration tests for mem0 + pgvector.
Requires: PostgreSQL with pgvector extension, test database.
Run with: pytest ai_assistant/tests/test_mem0_integration.py -v -m integration
"""
import os
import pytest


# Skip if no real DB available or USE_MEM0 is not enabled
pytestmark = pytest.mark.skipif(
    os.getenv('USE_MEM0', 'false').lower() != 'true',
    reason="Integration tests require USE_MEM0=true"
)


@pytest.mark.integration
class TestMem0Integration:
    """These tests hit a real pgvector instance."""

    def test_add_and_search(self):
        """End-to-end: add a memory and search for it."""
        from ai_assistant.services.tenant_memory import TenantMemoryManager

        manager = TenantMemoryManager(institution_id=999)

        # Add a memory
        manager.add(user_id=1, message="学生三角函数公式记不住，但图形理解能力很强")

        # Search
        results = manager.search(user_id=1, query="这个学生数学怎么样")
        assert len(results) > 0
        assert any("三角函数" in r.get("memory", "") for r in results)

        # Cleanup
        manager.delete_all(user_id=1)

    def test_user_isolation(self):
        """Users within same institution cannot see each other's memories."""
        from ai_assistant.services.tenant_memory import TenantMemoryManager

        manager = TenantMemoryManager(institution_id=999)

        # User 1 adds memory
        manager.add(user_id=1, message="我喜欢用图解法学习")
        # User 2 adds memory
        manager.add(user_id=2, message="我喜欢背公式")

        # User 1 should only see their own
        results_1 = manager.get_all(user_id=1)
        results_2 = manager.get_all(user_id=2)

        assert all("图解" not in r.get("memory", "") for r in results_2)
        assert all("背公式" not in r.get("memory", "") for r in results_1)

        # Cleanup
        manager.delete_all(user_id=1)
        manager.delete_all(user_id=2)

    def test_institution_isolation(self):
        """Different institutions have separate memory collections."""
        from ai_assistant.services.tenant_memory import TenantMemoryManager

        manager_a = TenantMemoryManager(institution_id=888)
        manager_b = TenantMemoryManager(institution_id=889)

        # Institution 888 user adds memory
        manager_a.add(user_id=1, message="机构A的学生记忆")
        # Institution 889 user adds memory
        manager_b.add(user_id=1, message="机构B的学生记忆")

        # Institution 888 should not see 889's memories
        results_a = manager_a.get_all(user_id=1)
        results_b = manager_b.get_all(user_id=1)

        assert all("机构B" not in r.get("memory", "") for r in results_a)
        assert all("机构A" not in r.get("memory", "") for r in results_b)

        # Cleanup
        manager_a.delete_all(user_id=1)
        manager_b.delete_all(user_id=1)
