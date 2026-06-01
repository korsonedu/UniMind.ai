import json
import logging
import os
import threading
from datetime import timedelta
from django.utils import timezone
from django.db.models import F
from ..models import AgentMemory

USE_MEM0 = os.getenv('USE_MEM0', 'false').lower() == 'true'

logger = logging.getLogger(__name__)

MEMORY_CHAR_LIMIT = 800


def get_memories_for_injection(user, limit=10):
    """检索用户最相关的记忆，用于注入 system prompt。"""
    now = timezone.now()
    memories = list(AgentMemory.objects.filter(
        user=user, is_active=True
    ).order_by('-confidence', '-use_count', '-updated_at')[:limit])

    if not memories:
        return ''

    lines = []
    total_len = 0
    used_pks = []
    for m in memories:
        line = f"- {m.key}：{m.value}（来源：{'历史对话' if m.source == 'auto' else '用户设置'}）"
        if total_len + len(line) > MEMORY_CHAR_LIMIT:
            break
        lines.append(line)
        total_len += len(line)
        used_pks.append(m.pk)

    if used_pks:
        AgentMemory.objects.filter(pk__in=used_pks).update(
            use_count=F('use_count') + 1, last_used_at=now
        )

    if not lines:
        return ''
    return "## 用户记忆\n以下是关于该用户的已知信息，请在回答中参考：\n" + "\n".join(lines)


def extract_memories_async(user, conversation_history):
    """后台线程：从对话中提取记忆。"""
    from ai_assistant.utils import _THREAD_POOL
    _THREAD_POOL.submit(_extract_memories_worker, user.id, conversation_history)


def _extract_memories_worker(user_id, conversation_history):
    """提取记忆的实际工作函数。"""
    from django.db import connections
    try:
        from users.models import User

        user = User.objects.filter(id=user_id).first()
        if not user:
            return

        prompt = _build_extraction_prompt(conversation_history)
        messages = [
            {'role': 'system', 'content': '你是一个记忆提取助手。从对话中提取关于用户的关键事实。'},
            {'role': 'user', 'content': prompt},
        ]

        from ai_engine.service import AIEngine
        res = AIEngine.call_ai(
            messages, temperature=0.3, max_tokens=1000, operation='memory.extract'
        )

        if not res or 'choices' not in res:
            return

        content = res['choices'][0]['message']['content']
        memories = _parse_extraction_result(content)

        for mem in memories:
            if not mem.get('key') or not mem.get('value'):
                continue
            # 去重：同用户同类型同 key 不重复
            existing = AgentMemory.objects.filter(
                user=user, memory_type=mem['type'], key=mem['key']
            ).first()
            if existing:
                # 更新置信度（取较高值）
                if mem.get('confidence', 0) > existing.confidence:
                    existing.value = mem['value']
                    existing.confidence = mem['confidence']
                    existing.save(update_fields=['value', 'confidence', 'updated_at'])
            else:
                AgentMemory.objects.create(
                    user=user,
                    memory_type=mem['type'],
                    key=mem['key'],
                    value=mem['value'],
                    source='auto',
                    confidence=mem.get('confidence', 0.5),
                )

        logger.info("Extracted %d memories for user %s", len(memories), user_id)

    except Exception as e:
        logger.exception("Memory extraction error: %s", e)
    finally:
        connections.close_all()


def _build_extraction_prompt(conversation_history):
    """构建提取 prompt。"""
    lines = []
    for msg in conversation_history[-10:]:  # 最近 10 条
        role = '用户' if msg.get('role') == 'user' else 'AI'
        lines.append(f"{role}: {msg.get('content', '')[:500]}")
    dialogue = "\n".join(lines)

    try:
        from core.prompt_manager import PromptManager
        template = PromptManager.get_prompt('ai_assistant', 'memory_extraction_prompt.txt')
        return template.replace('{dialogue}', dialogue)
    except Exception:
        return f"从以下对话中提取关键事实，返回 JSON 格式：\n\n{dialogue}"


def _parse_extraction_result(content):
    """解析 AI 返回的记忆提取结果。"""
    try:
        # 尝试从 markdown code block 中提取 JSON
        if '```json' in content:
            content = content.split('```json')[1].split('```')[0]
        elif '```' in content:
            content = content.split('```')[1].split('```')[0]
        data = json.loads(content.strip())
        if isinstance(data, dict) and 'memories' in data:
            return data['memories']
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, IndexError):
        pass
    return []


def extract_memories_with_mem0(user, conversation_history):
    """Use mem0 to extract and store memories from conversation."""
    if not USE_MEM0:
        return
    if not user.institution_id:
        return

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

    from ai_assistant.utils import _THREAD_POOL
    _THREAD_POOL.submit(_worker)


def build_memory_context(user, user_message: str = '', bot_type: str = 'planner'):
    """Build dual-layer memory context + adaptive directives for prompt injection.

    Returns (memory_context: str, adaptive_directives: str).
    Used by both polling (process_ai_chat) and streaming (AIChatStreamView) paths.
    """
    memory_context = ""
    adaptive_directives = ""

    try:
        structured = get_memories_for_injection(user)
        semantic = get_mem0_memories_for_injection(user, query=user_message)
        parts = [p for p in [structured, semantic] if p]
        memory_context = "\n\n".join(parts)

        if USE_MEM0 and user.institution_id:
            from ai_assistant.services.prompt_adapter import get_adaptive_directives_llm
            from ai_assistant.services.tenant_memory import TenantMemoryManager
            mgr = TenantMemoryManager(institution_id=user.institution_id)
            raw_memories = mgr.get_all(user_id=user.id)[:20]
            adaptive_directives = get_adaptive_directives_llm(raw_memories, bot_type=bot_type)
    except Exception:
        logger.exception("Failed to build memory context for user %s", user.id)

    return memory_context, adaptive_directives


def get_mem0_memories_for_injection(user, query: str = '', limit: int = 5) -> str:
    """Retrieve semantically relevant memories from mem0 for prompt injection."""
    if not USE_MEM0:
        return ''
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
