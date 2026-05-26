import pytest
from unittest.mock import patch, MagicMock


def _fake_config(institution_id: int) -> dict:
    """Return a realistic config for testing init behavior."""
    return {
        "vector_store": {
            "provider": "pgvector",
            "config": {
                "host": "localhost",
                "port": "5432",
                "dbname": "testdb",
                "user": "testuser",
                "password": "testpass",
                "collection_name": f"inst_{institution_id}",
            },
        },
        "embedder": {
            "provider": "openai",
            "config": {
                "api_key": "",
                "base_url": "https://api.deepseek.com/v1",
                "model": "deepseek-embedding",
            },
        },
        "version": "v1.1",
    }


class TestTenantMemoryManager:
    @patch("ai_assistant.services.tenant_memory.Memory")
    @patch("ai_assistant.services.tenant_memory._get_mem0_config", side_effect=_fake_config)
    def test_init_creates_mem0_with_pgvector(self, mock_config_fn, mock_memory_cls):
        """Manager initializes mem0 with pgvector config for the institution."""
        from ai_assistant.services.tenant_memory import TenantMemoryManager

        manager = TenantMemoryManager(institution_id=42)
        assert manager.institution_id == 42
        mock_config_fn.assert_called_once_with(42)
        mock_memory_cls.from_config.assert_called_once()
        config = mock_memory_cls.from_config.call_args[0][0]
        assert config["vector_store"]["provider"] == "pgvector"
        assert "inst_42" in str(config["vector_store"]["config"]["collection_name"])

    @patch("ai_assistant.services.tenant_memory.Memory")
    @patch("ai_assistant.services.tenant_memory._get_mem0_config", return_value={})
    def test_add_calls_mem0_add(self, mock_config_fn, mock_memory_cls):
        """add() delegates to mem0 with correct user_id and metadata."""
        mock_mem = MagicMock()
        mock_memory_cls.from_config.return_value = mock_mem
        from ai_assistant.services.tenant_memory import TenantMemoryManager

        manager = TenantMemoryManager(institution_id=1)
        manager.add(user_id=100, message="学生喜欢图解法", metadata={"type": "preference"})
        mock_mem.add.assert_called_once()
        call_args = mock_mem.add.call_args
        # mem0.add() is called as: add(message, user_id=str, metadata=dict)
        assert call_args[0][0] == "学生喜欢图解法"
        assert call_args[1]["user_id"] == "100"
        assert call_args[1]["metadata"]["institution_id"] == 1

    @patch("ai_assistant.services.tenant_memory.Memory")
    @patch("ai_assistant.services.tenant_memory._get_mem0_config", return_value={})
    def test_search_returns_results(self, mock_config_fn, mock_memory_cls):
        """search() returns mem0 search results."""
        mock_mem = MagicMock()
        mock_mem.search.return_value = [
            {"memory": "三角函数弱", "score": 0.85},
        ]
        mock_memory_cls.from_config.return_value = mock_mem
        from ai_assistant.services.tenant_memory import TenantMemoryManager

        manager = TenantMemoryManager(institution_id=1)
        results = manager.search(user_id=100, query="数学怎么样", limit=5)
        assert len(results) == 1
        assert results[0]["memory"] == "三角函数弱"

    @patch("ai_assistant.services.tenant_memory.Memory")
    @patch("ai_assistant.services.tenant_memory._get_mem0_config", return_value={})
    def test_get_all_returns_all_memories(self, mock_config_fn, mock_memory_cls):
        """get_all() delegates to mem0 get_all."""
        mock_mem = MagicMock()
        mock_mem.get_all.return_value = [
            {"id": "m1", "memory": "偏好图解法"},
            {"id": "m2", "memory": "三角函数弱"},
        ]
        mock_memory_cls.from_config.return_value = mock_mem
        from ai_assistant.services.tenant_memory import TenantMemoryManager

        manager = TenantMemoryManager(institution_id=1)
        results = manager.get_all(user_id=100)
        assert len(results) == 2

    @patch("ai_assistant.services.tenant_memory.Memory")
    @patch("ai_assistant.services.tenant_memory._get_mem0_config", return_value={})
    def test_delete_removes_single_memory(self, mock_config_fn, mock_memory_cls):
        """delete() delegates to mem0 delete."""
        mock_mem = MagicMock()
        mock_memory_cls.from_config.return_value = mock_mem
        from ai_assistant.services.tenant_memory import TenantMemoryManager

        manager = TenantMemoryManager(institution_id=1)
        manager.delete(memory_id="m1")
        mock_mem.delete.assert_called_once_with("m1")

    @patch("ai_assistant.services.tenant_memory.Memory")
    @patch("ai_assistant.services.tenant_memory._get_mem0_config", return_value={})
    def test_delete_all_clears_user_memories(self, mock_config_fn, mock_memory_cls):
        """delete_all() delegates to mem0 delete_all for the user."""
        mock_mem = MagicMock()
        mock_memory_cls.from_config.return_value = mock_mem
        from ai_assistant.services.tenant_memory import TenantMemoryManager

        manager = TenantMemoryManager(institution_id=1)
        manager.delete_all(user_id=100)
        mock_mem.delete_all.assert_called_once_with(user_id="100")
