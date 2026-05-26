import logging
import os
from django.conf import settings

try:
    from mem0 import Memory
except ImportError:
    Memory = None

logger = logging.getLogger(__name__)

LLM_API_KEY = os.getenv('LLM_API_KEY', '')
LLM_BASE_URL = os.getenv('LLM_BASE_URL', 'https://api.deepseek.com/v1')


def _get_mem0_config(institution_id: int) -> dict:
    """Build mem0 config with pgvector backend for the given institution."""
    db = settings.DATABASES['default']
    return {
        "vector_store": {
            "provider": "pgvector",
            "config": {
                "host": db['HOST'],
                "port": db['PORT'] or '5432',
                "dbname": db['NAME'],
                "user": db['USER'],
                "password": db['PASSWORD'],
                "collection_name": f"inst_{institution_id}",
            },
        },
        "embedder": {
            "provider": "openai",
            "config": {
                "api_key": LLM_API_KEY,
                "base_url": LLM_BASE_URL,
                "model": "deepseek-embedding",
            },
        },
        "version": "v1.1",
    }


class TenantMemoryManager:
    """Per-institution isolated memory manager backed by mem0 + pgvector.

    Usage:
        manager = TenantMemoryManager(institution_id=42)
        manager.add(user_id=100, message="学生偏好图解法")
        results = manager.search(user_id=100, query="这个学生怎么样")
    """

    def __init__(self, institution_id: int):
        if Memory is None:
            raise ImportError("mem0ai is required: pip install mem0ai")
        self.institution_id = institution_id
        self._config = _get_mem0_config(institution_id)
        self.memory = Memory.from_config(self._config)

    def add(self, user_id: int, message: str, metadata: dict = None):
        """Add a memory. mem0 auto-extracts and deduplicates."""
        meta = metadata or {}
        meta["institution_id"] = self.institution_id
        try:
            self.memory.add(
                message,
                user_id=str(user_id),
                metadata=meta,
            )
        except Exception:
            logger.exception("mem0 add failed for user %d", user_id)

    def search(self, user_id: int, query: str, limit: int = 5) -> list:
        """Semantic search for relevant memories."""
        try:
            return self.memory.search(query, user_id=str(user_id), limit=limit)
        except Exception:
            logger.exception("mem0 search failed for user %d", user_id)
            return []

    def get_all(self, user_id: int) -> list:
        """Get all memories for a user."""
        try:
            return self.memory.get_all(user_id=str(user_id))
        except Exception:
            logger.exception("mem0 get_all failed for user %d", user_id)
            return []

    def delete(self, user_id: int, memory_id: str):
        """Delete a single memory by ID."""
        try:
            self.memory.delete(memory_id)
        except Exception:
            logger.exception("mem0 delete failed for memory %s", memory_id)

    def delete_all(self, user_id: int):
        """Delete all memories for a user."""
        try:
            self.memory.delete_all(user_id=str(user_id))
        except Exception:
            logger.exception("mem0 delete_all failed for user %d", user_id)
