import hashlib
import json
import logging
import os
import threading
from datetime import timedelta
from django.conf import settings
from django.utils import timezone
from django.db.models import F
from ai_engine.observability import observe_background
from ..models import AgentMemory, MemoryExtractionLog
from .ulr_config import standalone_ulr
from .memory_core import fact_prompt as get_memories_for_injection, fact_write_revision, merge_fact, prism_active, semantic_writes_allowed

USE_MEM0 = os.getenv('USE_MEM0', 'false').lower() == 'true'

logger = logging.getLogger(__name__)


def extract_memories_async(user, conversation_history, conversation_id=None, *, ulr=False,
                           source_message_id=None, answer_message_id=None):
    """Schedule background extraction for the completed turn."""
    from ai_assistant.utils import _THREAD_POOL
    if conversation_id:
        from notes.context import conversation_uses_notes
        if conversation_uses_notes(user, conversation_id):
            return
    if prism_active() and conversation_id:
        from ..models import AIChatMessage, PrismEpisode
        question = AIChatMessage.objects.filter(user=user, conversation_id=conversation_id, role='user',
            content=_latest_user_message(conversation_history)).order_by('-id').first()
        if question and question.metadata.get('prism_clarification'):
            return
        episode = PrismEpisode.objects.filter(question=question).first() if question else None
        from .fact_evidence import active
        if episode and episode.observation.get('collect_facts') and not active():
            return  # The bound completion owns both observations and personal facts.
    if ulr or standalone_ulr():
        if source_message_id and answer_message_id:
            from .ulr_memory import schedule_memory_extraction
            schedule_memory_extraction(source_message_id, answer_message_id)
        return
    write_revision = fact_write_revision(user)
    if not semantic_writes_allowed():
        from .fact_evidence import active
        if active():
            from ..models import AIChatMessage
            question = AIChatMessage.objects.filter(user=user, conversation_id=conversation_id, role='user',
                content=_latest_user_message(conversation_history)).order_by('-pk').first()
            if question:
                _THREAD_POOL.submit(_extract_memories_via_dsh, user.id, conversation_history,
                    conversation_id, write_revision, source_message_id=question.pk)
        else:
            _THREAD_POOL.submit(_extract_memories_via_dsh, user.id, conversation_history, conversation_id, write_revision,
                                source_message_id=source_message_id, answer_message_id=answer_message_id)
    else:
        _THREAD_POOL.submit(_extract_memories_worker, user.id, conversation_history, write_revision)


def _extract_memories_worker(user_id, conversation_history, write_revision=None):
    """提取记忆的实际工作函数。"""
    from django.db import connections
    try:
        from users.models import User

        user = User.objects.filter(id=user_id).first()
        if not user:
            return

        if write_revision is None:
            write_revision = fact_write_revision(user)
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
            merge_fact(user, memory_type=mem['type'], key=mem['key'], value=mem['value'],
                       confidence=mem.get('confidence', 0.5), source='auto', write_revision=write_revision)

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


def _build_dsh_extraction_prompt(conversation_history, *, known_facts=None, observed_at=None):
    lines = []
    for msg in (conversation_history or [])[-10:]:
        role = '用户' if msg.get('role') == 'user' else 'AI'
        lines.append(f"{role}: {str(msg.get('content') or '')[:500]}")
    from .fact_evidence import active
    temporal = ("\n当前启用时间与项目记忆。明确自述的项目限制也可保留：scope=project，跨项目稳定事实用global。"
        "更新同一事实时沿用其语义键；撤回明确事实用operation=retract，其他用set。"
        "有效起止只有原话明确支持时填写带时区ISO时间 valid_from/valid_until，否则null。"
        "撤回是从valid_from（默认本条时间）开始的取消事件，valid_until填null，不把被取消旧事实的结束时间填到这里。"
        "临时限制不提升为长期偏好；不根据问题、助手建议或自述能力推断客观掌握。"
        + '\nknown_facts=' + json.dumps(known_facts or [], ensure_ascii=False)
        + '\n沿用已有事实时填写其_existing_id，服务端核验归属。只有不同语义才新建key。'
        + '\n本条用户陈述的服务器时间=' + str(observed_at) + '\n'
        if active() else '')
    return (
        "从以下对话中提取用户长期记忆。只提取用户亲口明确陈述的稳定偏好、学业背景和交互习惯。\n"
        "不要提取助手建议、假设、未确认计划或临时情绪。每条必须附用户原话 evidence；找不到原话就不输出。\n"
        "单次提问、查资料、出题、人工答疑或准备草稿的请求，不代表长期偏好或学习背景；问某个概念不等于长期学习该领域。\n"
        "本次发布前需本人确认属于当前操作要求和平台规则，不应提取为个人记忆。只有明确自述的长期习惯、偏好或学业事实才可提取，不得自行推断。\n"
        "反例：‘我想请老师答疑，请准备草稿，为什么久期随利率变化？我会核对后确认发布’没有长期事实，应提交 memories=[]。\n"
        "正例：‘我习惯先看例子再看公式’可提取讲解习惯；‘我的专业是金融学’可提取明确学业事实。\n"
        "没有合格事实也必须调用提交工具，提交 {\"memories\":[]}，不能省略工具调用。\n"
        "返回 JSON：{\"memories\":[{\"memory_type\":\"preference|academic|interaction\",\"key\":\"10字以内\",\"value\":\"具体事实\",\"confidence\":0.0-1.0,\"evidence\":\"用户原话\"}]}\n\n"
        + temporal + "\n".join(lines)
    )


def _merge_memory_candidates(user, candidates, user_message, conversation_id, *, ulr=False, write_revision=None, question=None):
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
        if mem.get('_existing_id') is not None:
            bound = AgentMemory.objects.select_for_update().filter(user=user, pk=mem['_existing_id']).first()
            if not bound:
                continue
            memory_type, key = bound.memory_type, bound.key
        value = str(mem.get('value') or '').strip()
        evidence = ' '.join(str(mem.get('evidence') or '').split())
        if not key or not value or not evidence or evidence not in normalized_user:
            continue
        if ulr:
            value = evidence
        try:
            confidence = float(mem.get('confidence') or 0)
        except (TypeError, ValueError):
            continue
        confidence = max(0.0, min(1.0, confidence))
        if confidence < 0.6:
            continue
        from . import fact_evidence
        if fact_evidence.active() and question is not None:
            saved += fact_evidence.append(user, {**mem, 'memory_type': memory_type, 'key': key,
                'value': value, 'confidence': confidence, 'evidence': evidence}, question)
        else:
            saved += merge_fact(user, memory_type=memory_type, key=key, value=value,
                                confidence=confidence, source='auto' if ulr else 'dsh', evidence=evidence,
                                conversation_id=conversation_id, write_revision=write_revision)
    return saved


def _extract_memories_via_dsh(user_id, conversation_history, conversation_id, write_revision=None, *, source_message_id=None, answer_message_id=None):
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
        if write_revision is None:
            write_revision = fact_write_revision(user)
        from ..models import AIChatMessage
        questions = AIChatMessage.objects.filter(user=user, conversation_id=conversation_id,
            role='user', content=user_message)
        question = (questions.filter(pk=source_message_id) if source_message_id is not None else questions).order_by('-pk').first()
        if question is None:
            return
        message_hash = _extraction_hash(user_message, question.pk)
        if MemoryExtractionLog.objects.filter(user=user, conversation_id=conversation_key, message_hash=message_hash).exists():
            return
        known = list(AgentMemory.objects.filter(user=user).values('id', 'memory_type', 'key'))
        with observe_background('legacy', f'memory:{conversation_key}',
                                source_message_id=question.pk, answer_message_id=answer_message_id):
            result = run_structured('assistant.memory_extract', _build_dsh_extraction_prompt(
                conversation_history, known_facts=known, observed_at=question.timestamp.isoformat()))
        candidates = result.get('memories') if isinstance(result, dict) else []
        if not isinstance(candidates, list):
            candidates = []
        saved = store_extracted_facts(user, candidates, user_message, conversation_key, write_revision,
            source_message_id=question.pk)
        logger.info("Extracted %d DSH memories for user %s", saved, user_id)
    except Exception:
        logger.exception("Server memory extraction error for user %s", user_id)
    finally:
        connections.close_all()


def _extraction_hash(text, message_id):
    from .fact_evidence import active
    return _memory_message_hash(str(message_id) + ':' + text if active() else text)


def store_extracted_facts(user, candidates, user_message, conversation_id, write_revision, *, source_message_id=None):
    from django.db import transaction
    from ..models import Conversation, AIChatMessage
    with transaction.atomic():
        conversation = Conversation.objects.select_for_update().filter(user=user, conversation_id=conversation_id).first()
        questions = AIChatMessage.objects.filter(user=user, conversation_id=conversation_id,
                role='user', content=user_message)
        question = (questions.filter(pk=source_message_id) if source_message_id is not None else questions).order_by('-pk').first()
        if not conversation or not question:
            return 0
        log, created = MemoryExtractionLog.objects.get_or_create(user=user, conversation_id=conversation_id,
            message_hash=_extraction_hash(user_message, question.pk), defaults={'candidate_count': len(candidates)})
        if not created:
            return 0
        from ..models import MemoryWriteState
        state = MemoryWriteState.objects.select_for_update().get(user=user) if write_revision is not None else None
        saved = (0 if state and state.revision != write_revision else
            _merge_memory_candidates(user, candidates, user_message, conversation_id,
                write_revision=write_revision, question=question))
        log.saved_count = saved
        log.save(update_fields=['saved_count'])
        return saved


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
    if standalone_ulr() or not semantic_writes_allowed():
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


def build_memory_context(user, user_message: str = '', bot_type: str = 'planner', *, chat_context=None):
    """Build dual-layer memory context + adaptive directives for prompt injection.

    Returns (memory_context: str, adaptive_directives: str).
    Used by both polling (process_ai_chat) and streaming (AIChatStreamView) paths.
    """
    memory_context = ""
    adaptive_directives = ""

    try:
        from .fact_evidence import active
        if active():
            return get_memories_for_injection(user, chat_context=chat_context), ''
        structured = get_memories_for_injection(user)
        semantic = get_mem0_memories_for_injection(user, query=user_message)
        parts = [p for p in [structured, semantic] if p]
        memory_context = "\n\n".join(parts)

        if USE_MEM0 and user.institution_id and not prism_active():
            from ai_assistant.services.prompt_adapter import get_adaptive_directives_llm
            raw_memories = []
            if not standalone_ulr():
                from ai_assistant.services.tenant_memory import TenantMemoryManager
                mgr = TenantMemoryManager(institution_id=user.institution_id)
                raw_memories = mgr.get_all(user_id=user.id)[:20]
            adaptive_directives = get_adaptive_directives_llm(raw_memories, bot_type=bot_type, user_id=user.id)
    except Exception:
        logger.exception("Failed to build memory context for user %s", user.id)

    return memory_context, adaptive_directives


def get_mem0_memories_for_injection(user, query: str = '', limit: int = 5) -> str:
    """Retrieve semantically relevant memories from mem0 for prompt injection."""
    from .fact_evidence import active
    if not USE_MEM0 or prism_active() or active():
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
