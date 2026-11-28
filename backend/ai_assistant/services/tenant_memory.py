import logging
from pathlib import Path
from uuid import UUID
from django.conf import settings
from psycopg2.extensions import make_dsn
from ai_engine.config import (
    EMBEDDING_MODEL, EMBEDDING_BASE_URL, EMBEDDING_API_KEY, EMBEDDING_DIMENSIONS,
    get_model_for_task,
)
from .ulr_config import standalone_ulr

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
                "connection_string": make_dsn(host=db['HOST'], port=db['PORT'] or '5432', dbname=db['NAME'],
                                              user=db['USER'], password=db['PASSWORD'],
                                              sslmode=db.get('OPTIONS', {}).get('sslmode')),
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

    def close(self):
        try:
            self.memory.close()
        finally:
            # The SDK's close() releases SQLite history. pgvector owns separate pools.
            for name in ('vector_store', '_entity_store', '_telemetry_vector_store'):
                pool = getattr(getattr(self.memory, name, None), 'connection_pool', None)
                if pool is not None:
                    (getattr(pool, 'closeall', None) or pool.close)()

    def add(self, user_id: int, message: str | list[dict], metadata: dict = None):
        """Add a memory. mem0 auto-extracts and deduplicates."""
        from .memory_core import semantic_writes_allowed
        if standalone_ulr() or not semantic_writes_allowed():
            return
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

    def get_all(self, user_id: int, *, limit: int = 20) -> list:
        """List at most the requested number of memories in the user's scope."""
        if limit <= 0:
            return []
        result = self.memory.get_all(filters={'user_id': str(user_id)}, top_k=limit)
        return result['results'] if isinstance(result, dict) else result

    def delete(self, memory_id: str, *, user_id: int) -> bool:
        """Verify ownership directly and confirm the memory has left active storage."""
        try:
            memory_id = str(UUID(memory_id))
        except ValueError:
            return False
        record = self.memory.get(memory_id)
        if not record or str(record.get('user_id')) != str(user_id):
            return False
        self.memory.delete(memory_id)
        if self.memory.get(memory_id) is not None:
            raise RuntimeError('Semantic memory is still present after deletion.')
        return True

    def delete_all(self, user_id: int):
        """The SDK's pgvector bulk delete processes one batch per call."""
        filters = {'user_id': str(user_id)}
        while batch := self.memory.vector_store.list(filters=filters, top_k=100)[0]:
            for record in batch:
                self.memory.delete(record.id)
            if self.memory.get(batch[0].id) is not None:
                raise RuntimeError('Semantic memory clear made no progress.')
