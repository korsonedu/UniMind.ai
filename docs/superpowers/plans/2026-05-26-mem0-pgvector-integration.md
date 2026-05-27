# Phase 1: mem0 + pgvector Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat KV memory system with mem0 semantic memory backed by pgvector, enabling per-tenant isolated, semantically searchable agent memory.

**Architecture:** mem0 Python SDK (local mode) with pgvector backend. Each institution gets its own pgvector collection (`inst_{id}`). User isolation via mem0's built-in `user_id` filtering. The existing `AgentMemory` model stays for structured data; mem0 handles unstructured semantic memory.

**Tech Stack:** Python 3.12, Django 6.0, PostgreSQL + pgvector, mem0ai SDK, DeepSeek embedding API

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `backend/ai_assistant/services/tenant_memory.py` | TenantMemoryManager: mem0 wrapper with institution isolation |
| Modify | `backend/ai_assistant/services/memory_service.py` | Wire mem0 extraction + semantic retrieval |
| Modify | `backend/ai_assistant/views.py` | Use mem0 retrieval in chat flow, add semantic memory API |
| Modify | `backend/ai_assistant/urls.py` | Add semantic memory endpoints |
| Create | `backend/ai_assistant/services/test_tenant_memory.py` | Unit tests for TenantMemoryManager |
| Modify | `backend/requirements.txt` | Add mem0ai, pgvector packages |
| Modify | `backend/school_system/settings.py` | pgvector extension config |

---

### Task 1: Install Dependencies and Enable pgvector

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/school_system/settings.py`

- [ ] **Step 1: Add mem0ai and pgvector to requirements.txt**

Append to `backend/requirements.txt`:
```
mem0ai>=0.1.0
pgvector>=0.3.0
```

- [ ] **Step 2: Install packages**

Run:
```bash
cd backend && pip install mem0ai pgvector
```

- [ ] **Step 3: Enable pgvector extension in PostgreSQL**

Run:
```bash
psql -U unimind -d unimind -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

Verify:
```sql
SELECT * FROM pg_extension WHERE extname = 'vector';
```
Expected: 1 row showing the vector extension.

- [ ] **Step 4: Add pgvector to Django INSTALLED_APPS (if needed)**

Check if mem0 handles collection creation automatically. If Django needs pgvector awareness, add to `INSTALLED_APPS` in `backend/school_system/settings.py`:
```python
INSTALLED_APPS = [
    # ... existing ...
    'pgvector',  # only if needed for Django ORM integration
]
```

- [ ] **Step 5: Commit**

```bash
git add backend/requirements.txt backend/school_system/settings.py
git commit -m "deps: add mem0ai and pgvector for semantic memory"
```

---

### Task 2: Create TenantMemoryManager

**Files:**
- Create: `backend/ai_assistant/services/tenant_memory.py`
- Create: `backend/ai_assistant/services/test_tenant_memory.py`

- [ ] **Step 1: Write failing tests for TenantMemoryManager**

Create `backend/ai_assistant/services/test_tenant_memory.py`:

```python
import pytest
from unittest.mock import patch, MagicMock
from ai_assistant.services.tenant_memory import TenantMemoryManager


class TestTenantMemoryManager:
    @patch('ai_assistant.services.tenant_memory.Memory')
    def test_init_creates_mem0_with_pgvector(self, mock_memory_cls):
        """Manager initializes mem0 with pgvector config for the institution."""
        manager = TenantMemoryManager(institution_id=42)
        assert manager.institution_id == 42
        mock_memory_cls.from_config.assert_called_once()
        config = mock_memory_cls.from_config.call_args[0][0]
        assert config["vector_store"]["provider"] == "pgvector"
        assert "inst_42" in str(config["vector_store"]["config"]["collection_name"])

    @patch('ai_assistant.services.tenant_memory.Memory')
    def test_add_calls_mem0_add(self, mock_memory_cls):
        """add() delegates to mem0 with correct user_id and metadata."""
        mock_mem = MagicMock()
        mock_memory_cls.from_config.return_value = mock_mem
        manager = TenantMemoryManager(institution_id=1)
        manager.add(user_id=100, message="学生喜欢图解法", metadata={"type": "preference"})
        mock_mem.add.assert_called_once()
        call_kwargs = mock_mem.add.call_args
        assert call_kwargs[1]["user_id"] == "100"
        assert call_kwargs[1]["metadata"]["institution_id"] == 1

    @patch('ai_assistant.services.tenant_memory.Memory')
    def test_search_returns_results(self, mock_memory_cls):
        """search() returns mem0 search results."""
        mock_mem = MagicMock()
        mock_mem.search.return_value = [
            {"memory": "三角函数弱", "score": 0.85},
        ]
        mock_memory_cls.from_config.return_value = mock_mem
        manager = TenantMemoryManager(institution_id=1)
        results = manager.search(user_id=100, query="数学怎么样", limit=5)
        assert len(results) == 1
        assert results[0]["memory"] == "三角函数弱"

    @patch('ai_assistant.services.tenant_memory.Memory')
    def test_get_all_returns_all_memories(self, mock_memory_cls):
        """get_all() delegates to mem0 get_all."""
        mock_mem = MagicMock()
        mock_mem.get_all.return_value = [
            {"id": "m1", "memory": "偏好图解法"},
            {"id": "m2", "memory": "三角函数弱"},
        ]
        mock_memory_cls.from_config.return_value = mock_mem
        manager = TenantMemoryManager(institution_id=1)
        results = manager.get_all(user_id=100)
        assert len(results) == 2

    @patch('ai_assistant.services.tenant_memory.Memory')
    def test_delete_removes_single_memory(self, mock_memory_cls):
        """delete() delegates to mem0 delete."""
        mock_mem = MagicMock()
        mock_memory_cls.from_config.return_value = mock_mem
        manager = TenantMemoryManager(institution_id=1)
        manager.delete(user_id=100, memory_id="m1")
        mock_mem.delete.assert_called_once_with("m1")

    @patch('ai_assistant.services.tenant_memory.Memory')
    def test_delete_all_clears_user_memories(self, mock_memory_cls):
        """delete_all() delegates to mem0 delete_all for the user."""
        mock_mem = MagicMock()
        mock_memory_cls.from_config.return_value = mock_mem
        manager = TenantMemoryManager(institution_id=1)
        manager.delete_all(user_id=100)
        mock_mem.delete_all.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd backend && python -m pytest ai_assistant/services/test_tenant_memory.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'ai_assistant.services.tenant_memory'`

- [ ] **Step 3: Implement TenantMemoryManager**

Create `backend/ai_assistant/services/tenant_memory.py`:

```python
import logging
import os
from django.conf import settings

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
                "model": get_embedding_model(),
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
        from mem0 import Memory
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd backend && python -m pytest ai_assistant/services/test_tenant_memory.py -v
```
Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/ai_assistant/services/tenant_memory.py backend/ai_assistant/services/test_tenant_memory.py
git commit -m "feat: add TenantMemoryManager with mem0 + pgvector isolation"
```

---

### Task 3: Wire mem0 Extraction into Chat Flow

**Files:**
- Modify: `backend/ai_assistant/services/memory_service.py`
- Modify: `backend/ai_assistant/views.py`

- [ ] **Step 1: Add mem0 extraction function to memory_service.py**

Add to `backend/ai_assistant/services/memory_service.py` after the existing functions:

```python
def extract_memories_with_mem0(user, conversation_history):
    """Use mem0 to extract and store memories from conversation.

    Replaces the manual LLM extraction with mem0's built-in
    extraction, deduplication, and confidence management.
    """
    if not user.institution_id:
        return  # No institution = no mem0 storage

    # Build conversation text for mem0
    lines = []
    for msg in conversation_history[-10:]:
        role = '用户' if msg.get('role') == 'user' else 'AI'
        content = str(msg.get('content', ''))[:500]
        if content and content != '[Thinking...]':
            lines.append(f"{role}: {content}")

    if not lines:
        return

    conversation_text = "\n".join(lines)

    def _worker():
        from django.db import connections
        try:
            from ai_assistant.services.tenant_memory import TenantMemoryManager
            manager = TenantMemoryManager(institution_id=user.institution_id)
            manager.add(
                user_id=user.id,
                message=conversation_text,
                metadata={"source": "auto_extract"},
            )
        except Exception:
            logger.exception("mem0 extraction failed for user %d", user.id)
        finally:
            connections.close_all()

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
```

- [ ] **Step 2: Add mem0 retrieval function to memory_service.py**

Add to `backend/ai_assistant/services/memory_service.py`:

```python
def get_mem0_memories_for_injection(user, query: str = '', limit: int = 5) -> str:
    """Retrieve semantically relevant memories from mem0 for prompt injection.

    Args:
        user: The user object.
        query: Current user message for semantic matching. Falls back to get_all if empty.
        limit: Max memories to retrieve.

    Returns:
        Formatted memory string for system prompt injection, or empty string.
    """
    if not user.institution_id:
        return ''

    try:
        from ai_assistant.services.tenant_memory import TenantMemoryManager
        manager = TenantMemoryManager(institution_id=user.institution_id)

        if query:
            memories = manager.search(user_id=user.id, query=query, limit=limit)
        else:
            memories = manager.get_all(user_id=user.id)[:limit]

        if not memories:
            return ''

        lines = []
        for m in memories:
            text = m.get('memory', '')
            if text:
                lines.append(f"- {text}")

        if not lines:
            return ''

        return "## 用户记忆（语义检索）\n以下是与当前问题相关的用户记忆：\n" + "\n".join(lines)

    except Exception:
        logger.exception("mem0 retrieval failed for user %d", user.id)
        return ''
```

- [ ] **Step 3: Update process_ai_chat to use mem0**

In `backend/ai_assistant/views.py`, modify `process_ai_chat()`:

Replace the memory retrieval block (lines 37-42):
```python
    # 获取记忆上下文
    memory_context = ""
    try:
        from ai_assistant.services.memory_service import get_memories_for_injection
        memory_context = get_memories_for_injection(user)
    except Exception:
        pass
```

With:
```python
    # 获取记忆上下文 (dual-layer: structured + mem0 semantic)
    memory_context = ""
    try:
        from ai_assistant.services.memory_service import (
            get_memories_for_injection,
            get_mem0_memories_for_injection,
        )
        # Layer 1: structured KV memories
        structured = get_memories_for_injection(user)
        # Layer 2: mem0 semantic retrieval
        semantic = get_mem0_memories_for_injection(user, query=user_message)
        # Combine both layers
        parts = [p for p in [structured, semantic] if p]
        memory_context = "\n\n".join(parts)
    except Exception:
        pass
```

- [ ] **Step 4: Update memory extraction to use mem0**

In `backend/ai_assistant/views.py`, modify the extraction block (lines 107-112):

Replace:
```python
    finally:
        # 异步提取记忆（不阻塞响应）
        try:
            from ai_assistant.services.memory_service import extract_memories_async
            extract_memories_async(user, history_msgs + [{'role': 'user', 'content': user_message}])
        except Exception:
            pass
        connections.close_all()
```

With:
```python
    finally:
        # 异步提取记忆（不阻塞响应）
        try:
            from ai_assistant.services.memory_service import (
                extract_memories_async,
                extract_memories_with_mem0,
            )
            full_history = history_msgs + [{'role': 'user', 'content': user_message}]
            # Legacy extraction (structured KV — keep for backward compat)
            extract_memories_async(user, full_history)
            # mem0 semantic extraction
            extract_memories_with_mem0(user, full_history)
        except Exception:
            pass
        connections.close_all()
```

- [ ] **Step 5: Run existing tests to check for regressions**

Run:
```bash
cd backend && python manage.py test ai_assistant --verbosity=2
```
Expected: All existing tests pass. No regressions.

- [ ] **Step 6: Commit**

```bash
git add backend/ai_assistant/services/memory_service.py backend/ai_assistant/views.py
git commit -m "feat: wire mem0 extraction and semantic retrieval into chat flow"
```

---

### Task 4: Add Semantic Memory API Endpoints

**Files:**
- Modify: `backend/ai_assistant/views.py`
- Modify: `backend/ai_assistant/urls.py`

- [ ] **Step 1: Add SemanticMemoryListView and SemanticMemoryDeleteView**

Add to `backend/ai_assistant/views.py`:

```python
class SemanticMemoryListView(APIView):
    """List semantic memories for the current user from mem0."""
    permission_classes = [IsMember]

    def get(self, request):
        user = request.user
        if not user.institution_id:
            return Response({"memories": []})

        try:
            from ai_assistant.services.tenant_memory import TenantMemoryManager
            manager = TenantMemoryManager(institution_id=user.institution_id)
            memories = manager.get_all(user_id=user.id)
            return Response({"memories": memories})
        except Exception as e:
            logger.exception("Failed to list semantic memories")
            return Response({"error": str(e)}, status=500)


class SemanticMemoryDeleteView(APIView):
    """Delete a single semantic memory or clear all."""
    permission_classes = [IsMember]

    def delete(self, request, memory_id=None):
        user = request.user
        if not user.institution_id:
            return Response({"error": "No institution"}, status=400)

        try:
            from ai_assistant.services.tenant_memory import TenantMemoryManager
            manager = TenantMemoryManager(institution_id=user.institution_id)
            if memory_id:
                manager.delete(user_id=user.id, memory_id=memory_id)
            else:
                manager.delete_all(user_id=user.id)
            return Response({"status": "ok"})
        except Exception as e:
            logger.exception("Failed to delete semantic memory")
            return Response({"error": str(e)}, status=500)
```

- [ ] **Step 2: Add URLs**

Add to `backend/ai_assistant/urls.py` (after existing memory URLs):

```python
    path('memories/semantics/', SemanticMemoryListView.as_view(), name='semantic-memory-list'),
    path('memories/semantics/<str:memory_id>/', SemanticMemoryDeleteView.as_view(), name='semantic-memory-detail'),
    path('memories/semantics/clear/', SemanticMemoryDeleteView.as_view(), name='semantic-memory-clear'),
```

- [ ] **Step 3: Add imports**

At the top of `backend/ai_assistant/urls.py`, add `SemanticMemoryListView, SemanticMemoryDeleteView` to the import from views.

- [ ] **Step 4: Test the endpoints manually**

Run the dev server and test:
```bash
cd backend && python manage.py runserver
# In another terminal:
# GET /api/ai/memories/semantics/ — should return {"memories": [...]} or {"memories": []}
# DELETE /api/ai/memories/semantics/<id>/ — should return {"status": "ok"}
# DELETE /api/ai/memories/semantics/clear/ — should return {"status": "ok"}
```

- [ ] **Step 5: Commit**

```bash
git add backend/ai_assistant/views.py backend/ai_assistant/urls.py
git commit -m "feat: add semantic memory API endpoints (list, delete, clear)"
```

---

### Task 5: Add Embedding Configuration

**Files:**
- Modify: `backend/ai_engine/config.py`
- Modify: `backend/ai_assistant/services/tenant_memory.py`

- [ ] **Step 1: Add embedding model config to ai_engine/config.py**

Add to `backend/ai_engine/config.py` after the model routing table:

```python
# ── Embedding model config (for mem0 semantic memory) ──
EMBEDDING_MODEL = os.getenv('AI_EMBEDDING_MODEL', 'deepseek-embedding')
EMBEDDING_BASE_URL = os.getenv('AI_EMBEDDING_BASE_URL', DEFAULT_BASE_URL.replace('/chat/completions', ''))
```

- [ ] **Step 2: Update TenantMemoryManager to use config**

Modify `backend/ai_assistant/services/tenant_memory.py`, function `_get_mem0_config`:

Replace the embedder section:
```python
        "embedder": {
            "provider": "openai",
            "config": {
                "api_key": settings.LLM_API_KEY,
                "base_url": getattr(settings, 'LLM_BASE_URL', 'https://api.deepseek.com/v1'),
                "model": "deepseek-embedding",
            },
        },
```

With:
```python
        "embedder": {
            "provider": "openai",
            "config": {
                "api_key": LLM_API_KEY,
                "base_url": LLM_BASE_URL,
                "model": get_embedding_model(),
            },
        },
```

Add imports at the top of the file:
```python
from ai_engine.config import EMBEDDING_MODEL, EMBEDDING_BASE_URL


def get_embedding_model() -> str:
    return EMBEDDING_MODEL


def get_embedding_base_url() -> str:
    return EMBEDDING_BASE_URL
```

- [ ] **Step 3: Run tests**

Run:
```bash
cd backend && python -m pytest ai_assistant/services/test_tenant_memory.py -v
```
Expected: All tests PASS (mocked, so config changes don't break them).

- [ ] **Step 4: Commit**

```bash
git add backend/ai_engine/config.py backend/ai_assistant/services/tenant_memory.py
git commit -m "feat: add embedding model config for mem0"
```

---

### Task 6: Integration Smoke Test

**Files:**
- Create: `backend/ai_assistant/services/test_mem0_integration.py`

- [ ] **Step 1: Write integration test (requires running PG with pgvector)**

Create `backend/ai_assistant/services/test_mem0_integration.py`:

```python
"""
Integration tests for mem0 + pgvector.
Requires: PostgreSQL with pgvector extension, test database.
Run with: pytest ai_assistant/services/test_mem0_integration.py -v -m integration
"""
import pytest
from unittest.mock import patch


@pytest.mark.integration
class TestMem0Integration:
    """These tests hit a real pgvector instance. Mark as integration."""

    @patch('ai_assistant.services.tenant_memory.settings')
    def test_add_and_search(self, mock_settings):
        """End-to-end: add a memory and search for it."""
        from ai_assistant.services.tenant_memory import TenantMemoryManager

        # Use test DB settings
        mock_settings.DATABASES = {
            'default': {
                'HOST': 'localhost',
                'PORT': '5432',
                'NAME': 'unimind_test',
                'USER': 'unimind',
                'PASSWORD': 'test',
            }
        }

        manager = TenantMemoryManager(institution_id=999)

        # Add a memory
        manager.add(user_id=1, message="学生三角函数公式记不住，但图形理解能力很强")

        # Search
        results = manager.search(user_id=1, query="这个学生数学怎么样")
        assert len(results) > 0
        assert any("三角函数" in r.get("memory", "") for r in results)

        # Cleanup
        manager.delete_all(user_id=1)

    @patch('ai_assistant.services.tenant_memory.settings')
    def test_user_isolation(self, mock_settings):
        """Users within same institution cannot see each other's memories."""
        from ai_assistant.services.tenant_memory import TenantMemoryManager

        mock_settings.DATABASES = {
            'default': {
                'HOST': 'localhost',
                'PORT': '5432',
                'NAME': 'unimind_test',
                'USER': 'unimind',
                'PASSWORD': 'test',
            }
        }

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
```

- [ ] **Step 2: Run integration tests (manual — requires PG)**

Run:
```bash
cd backend && python -m pytest ai_assistant/services/test_mem0_integration.py -v -m integration
```
Expected: Tests pass if PG has pgvector and test DB exists. Skip if no test DB.

- [ ] **Step 3: Commit**

```bash
git add backend/ai_assistant/services/test_mem0_integration.py
git commit -m "test: add mem0 integration tests (pgvector)"
```

---

### Task 7: Backward Compatibility and Migration Path

**Files:**
- Modify: `backend/ai_assistant/services/memory_service.py`

- [ ] **Step 1: Add feature flag for mem0**

Add to the top of `backend/ai_assistant/services/memory_service.py`:

```python
import os

USE_MEM0 = os.getenv('USE_MEM0', 'false').lower() == 'true'
```

- [ ] **Step 2: Gate mem0 calls behind the flag**

Update `get_mem0_memories_for_injection`:
```python
def get_mem0_memories_for_injection(user, query: str = '', limit: int = 5) -> str:
    """Retrieve semantically relevant memories from mem0."""
    if not USE_MEM0:
        return ''
    # ... rest of function unchanged
```

Update `extract_memories_with_mem0`:
```python
def extract_memories_with_mem0(user, conversation_history):
    """Use mem0 to extract and store memories from conversation."""
    if not USE_MEM0:
        return
    # ... rest of function unchanged
```

- [ ] **Step 3: Update views.py to respect the flag**

In `backend/ai_assistant/views.py`, the dual-layer retrieval block already handles exceptions gracefully, so no changes needed — if mem0 functions return empty strings, the behavior falls back to structured-only.

- [ ] **Step 4: Verify backward compatibility**

Run:
```bash
cd backend && USE_MEM0=false python manage.py test ai_assistant --verbosity=2
```
Expected: All existing tests pass. mem0 code paths are skipped.

- [ ] **Step 5: Commit**

```bash
git add backend/ai_assistant/services/memory_service.py
git commit -m "feat: add USE_MEM0 feature flag for gradual rollout"
```

---

### Task 8: End-to-End Verification

- [ ] **Step 1: Start dev server with mem0 enabled**

```bash
cd backend && USE_MEM0=true python manage.py runserver
```

- [ ] **Step 2: Test chat flow**

Send a chat message via API or UI:
1. Send a message that reveals user preferences: "我不太会三角函数，但我几何很好"
2. Wait for response
3. Check logs for mem0 extraction
4. Send another message: "我之前说的数学问题还记得吗"
5. Verify the agent references the previous memory

- [ ] **Step 3: Test semantic memory API**

```bash
# List memories
curl -b cookies.txt http://localhost:8000/api/ai/memories/semantics/

# Verify memories were extracted
# Should see entries about 三角函数 and 几何
```

- [ ] **Step 4: Test tenant isolation**

Create two test users in different institutions. Have conversations with each. Verify that memories from one user/institution are not visible to the other.

- [ ] **Step 5: Run full check**

```bash
make full-check
```
Expected: All checks pass.

- [ ] **Step 6: Commit final state**

```bash
git add -A
git commit -m "feat: Phase 1 complete — mem0 + pgvector semantic memory integration"
```

---

## Verification Checklist

- [ ] pgvector extension installed in PostgreSQL
- [ ] `TenantMemoryManager` can add, search, delete memories
- [ ] Chat flow uses dual-layer memory (structured + mem0)
- [ ] mem0 extraction runs asynchronously after each chat
- [ ] Semantic memory API endpoints work (list, delete, clear)
- [ ] `USE_MEM0=false` falls back to existing behavior
- [ ] No regressions in existing tests
- [ ] User isolation verified (same institution, different users)
- [ ] Institution isolation verified (different institutions)
