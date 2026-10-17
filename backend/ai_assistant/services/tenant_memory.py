import logging
from pathlib import Path
from django.conf import settings
from ai_engine.config import (
    EMBEDDING_MODEL, EMBEDDING_BASE_URL, EMBEDDING_API_KEY, EMBEDDING_DIMENSIONS,
    get_model_for_task,
)

try:
    from mem0 import Memory
except ImportError:
    Memory = None

logger = logging.getLogger(__name__)


def _get_mem0_config(institution_id: int) -> dict:
    """Build mem0 config with pgvector backend for the given institution."""
    db = settings.DATABASES['default']
    llm = get_model_for_task('memory.extract')
    base_url = llm['base_url'].rstrip('/').removesuffix('/chat/completions')
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
                "embedding_model_dims": EMBEDDING_DIMENSIONS,
            },
        },
        "embedder": {
            "provider": "openai",
            "config": {
                "api_key": EMBEDDING_API_KEY,
                "openai_base_url": EMBEDDING_BASE_URL,
                "model": EMBEDDING_MODEL,
                "embedding_dims": EMBEDDING_DIMENSIONS,
            },
        },
        "llm": {
            "provider": "openai",
            "config": {
                "api_key": llm['api_key'],
                "openai_base_url": base_url,
                "model": llm['model'],
                "temperature": 0,
                "max_tokens": 2000,
            },
        },
        "history_db_path": str(Path(settings.BASE_DIR) / '.cache' / 'mem0' / f'history_inst_{int(institution_id)}.db'),
        "custom_instructions": "只提取用户明确陈述或确认的长期目标、偏好和学习事实。助手建议、示例和推测不能视作用户事实；临时问题和未确认的方案不要保存。",
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
        if self._config.get('history_db_path'):
            Path(self._config['history_db_path']).parent.mkdir(parents=True, exist_ok=True)
        self.memory = Memory.from_config(self._config)

    def add(self, user_id: int, message: str | list[dict], metadata: dict = None):
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
            result = self.memory.search(query, filters={'user_id': str(user_id)}, top_k=limit)
            return result.get('results', []) if isinstance(result, dict) else result
        except Exception:
            logger.exception("mem0 search failed for user %d", user_id)
            return []

    def get_all(self, user_id: int) -> list:
        """Get all memories for a user."""
        try:
            result = self.memory.get_all(filters={'user_id': str(user_id)})
            return result.get('results', []) if isinstance(result, dict) else result
        except Exception:
            logger.exception("mem0 get_all failed for user %d", user_id)
            return []

    def delete(self, memory_id: str):
        """Delete a single memory by ID.

        Note: mem0 deletes by memory_id directly. Caller must verify
        the memory belongs to the authenticated user before calling.
        """
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
