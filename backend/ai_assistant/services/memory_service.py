import hashlib
import json
import logging
import os
import threading
from datetime import timedelta
from django.conf import settings
from django.utils import timezone
from django.db.models import F
from ..models import AgentMemory, MemoryExtractionLog

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
        source_label = '用户设置' if m.source == 'manual' else '历史对话'
        line = f"- {m.key}：{m.value}（来源：{source_label}）"
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


def extract_memories_async(user, conversation_history, conversation_id=None):
    """后台线程：从对话中提取记忆。"""
    from ai_assistant.utils import _THREAD_POOL
    if getattr(settings, 'UNIMIND_DSH_MEMORY_ENABLED', False) or getattr(settings, 'UNIMIND_DSH_GENERATION_ENABLED', False):
        _THREAD_POOL.submit(_extract_memories_via_dsh, user.id, conversation_history, conversation_id)
    else:
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


def _latest_user_message(conversation_history):
    for msg in reversed(conversation_history or []):
        if msg.get('role') == 'user' and str(msg.get('content') or '').strip():
            return str(msg['content'])
    return ''


def _memory_message_hash(text):
    normalized = ' '.join(str(text or '').split())
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()


def _build_dsh_extraction_prompt(conversation_history):
    lines = []
    for msg in (conversation_history or [])[-10:]:
        role = '用户' if msg.get('role') == 'user' else 'AI'
        lines.append(f"{role}: {str(msg.get('content') or '')[:500]}")
    return (
        "从以下对话中提取用户长期记忆。只提取用户亲口明确陈述的稳定偏好、学业背景和交互习惯。\n"
        "不要提取助手建议、假设、未确认计划或临时情绪。每条必须附用户原话 evidence；找不到原话就不输出。\n"
        "单次提问、查资料、出题、人工答疑或准备草稿的请求，不代表长期偏好或学习背景；问某个概念不等于长期学习该领域。\n"
        "本次发布前需本人确认属于当前操作要求和平台规则，不应提取为个人记忆。只有明确自述的长期习惯、偏好或学业事实才可提取，不得自行推断。\n"
        "反例：‘我想请老师答疑，请准备草稿，为什么久期随利率变化？我会核对后确认发布’没有长期事实，应提交 memories=[]。\n"
        "正例：‘我习惯先看例子再看公式’可提取讲解习惯；‘我的专业是金融学’可提取明确学业事实。\n"
        "没有合格事实也必须调用提交工具，提交 {\"memories\":[]}，不能省略工具调用。\n"
        "返回 JSON：{\"memories\":[{\"memory_type\":\"preference|academic|interaction\",\"key\":\"10字以内\",\"value\":\"具体事实\",\"confidence\":0.0-1.0,\"evidence\":\"用户原话\"}]}\n\n"
        + "\n".join(lines)
    )


def _merge_memory_candidates(user, candidates, user_message, conversation_id):
    """Only merge candidates backed by the current user message; manual or disabled entries win."""
    normalized_user = ' '.join(str(user_message or '').split())
    saved = 0
    for mem in candidates or []:
        if not isinstance(mem, dict):
            continue
        memory_type = str(mem.get('memory_type') or '').strip()
        if memory_type not in {choice[0] for choice in AgentMemory.MEMORY_TYPES}:
            continue
        key = str(mem.get('key') or '').strip()[:200]
        value = str(mem.get('value') or '').strip()
        evidence = ' '.join(str(mem.get('evidence') or '').split())
        if not key or not value or not evidence or evidence not in normalized_user:
            continue
        try:
            confidence = float(mem.get('confidence') or 0)
        except (TypeError, ValueError):
            continue
        confidence = max(0.0, min(1.0, confidence))
        if confidence < 0.6:
            continue
        existing = AgentMemory.objects.filter(user=user, memory_type=memory_type, key=key).first()
        if existing:
            if existing.source == 'manual' or not existing.is_active:
                continue
            if confidence > existing.confidence:
                existing.value = value
                existing.confidence = confidence
                existing.evidence = evidence
                existing.source = 'dsh'
                existing.source_conversation_id = conversation_id
                existing.save(update_fields=['value', 'confidence', 'evidence', 'source', 'source_conversation_id', 'updated_at'])
                saved += 1
        else:
            AgentMemory.objects.create(user=user, memory_type=memory_type, key=key, value=value,
                source='dsh', evidence=evidence, source_conversation_id=conversation_id, confidence=confidence)
            saved += 1
    return saved


def _extract_memories_via_dsh(user_id, conversation_history, conversation_id):
    """Extract reviewed candidates through the server harness; one turn is processed once."""
    from django.db import connections
    try:
        from users.models import User
        from ai_assistant.services.dsh_tasks import run_structured

        user = User.objects.filter(id=user_id).first()
        user_message = _latest_user_message(conversation_history)
        if not user or not user_message or not conversation_id:
            return
        conversation_key = str(conversation_id)
        message_hash = _memory_message_hash(user_message)
        if MemoryExtractionLog.objects.filter(user=user, conversation_id=conversation_key, message_hash=message_hash).exists():
            return
        result = run_structured('assistant.memory_extract', _build_dsh_extraction_prompt(conversation_history))
        candidates = result.get('memories') if isinstance(result, dict) else []
        if not isinstance(candidates, list):
            candidates = []
        from django.db import transaction
        from ..models import Conversation, AIChatMessage
        with transaction.atomic():
            conversation = Conversation.objects.select_for_update().filter(user=user, conversation_id=conversation_key).first()
            if not conversation or not AIChatMessage.objects.filter(user=user, conversation_id=conversation_key,
                    role='user', content=user_message).exists():
                return  # Deleting the source while the model runs must also discard late candidates.
            log, created = MemoryExtractionLog.objects.get_or_create(user=user, conversation_id=conversation_key,
                message_hash=message_hash, defaults={'candidate_count': len(candidates)})
            if not created:
                return
            saved = _merge_memory_candidates(user, candidates, user_message, conversation_key)
            log.saved_count = saved
            log.save(update_fields=['saved_count'])
        logger.info("Extracted %d DSH memories for user %s", saved, user_id)
    except Exception:
        logger.exception("DSH memory extraction error for user %s", user_id)
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
    if getattr(settings, 'UNIMIND_DSH_MEMORY_ENABLED', False) or getattr(settings, 'UNIMIND_DSH_GENERATION_ENABLED', False):
        return
    if not USE_MEM0:
        return
    if not user.institution_id:
        return

    messages = []
    for msg in conversation_history[-10:]:
        role = msg.get('role')
        content = str(msg.get('content', ''))[:500]
        if role in ('user', 'assistant') and content and content != '[Thinking...]':
            messages.append({'role': role, 'content': content})

    if not messages:
        return

    def _worker():
        from django.db import connections
        try:
            from ai_assistant.services.tenant_memory import TenantMemoryManager
            manager = TenantMemoryManager(institution_id=user.institution_id)
            manager.add(
                user_id=user.id,
                message=messages,
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
            adaptive_directives = get_adaptive_directives_llm(raw_memories, bot_type=bot_type, user_id=user.id)
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
