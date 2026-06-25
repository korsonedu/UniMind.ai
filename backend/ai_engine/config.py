import os

# ── Model provider defaults ──
FALLBACK_FAST = 'deepseek-v4-flash'     # 轻量任务：对话、分类、解析、schema修复
FALLBACK_PRO  = 'deepseek-v4-pro'       # 重量任务：评审、判分、知识树生成
DEFAULT_MODEL = FALLBACK_FAST
DEFAULT_BASE_URL = 'https://api.deepseek.com/v1/chat/completions'

# Per-task model routing table.
# Each task → (per_task_env_key, tier) where tier ∈ {'fast', 'pro'}.
_TASK_MODEL_MAP = {
    # ── Chat / interview ──
    # 前缀匹配规则：'assistant.chat.planner' 精确匹配小宇，其他 agent 操作 fallback 到默认 flash
    'assistant.chat.planner': ('AI_MODEL_CHAT', 'pro'),
    'interviews': ('AI_MODEL_CHAT',            'fast'),
    # ── Question generation pipeline ──
    'pipeline.author':    ('AI_MODEL_GENERATE_AUTHOR',    'fast'),
    'quizzes.bulk_generate': ('AI_MODEL_GENERATE_AUTHOR', 'fast'),
    'pipeline.reviewer':  ('AI_MODEL_GENERATE_REVIEWER',  'pro'),
    'pipeline.author_revise': ('AI_MODEL_GENERATE_AUTHOR', 'fast'),
    'pipeline.classifier':('AI_MODEL_GENERATE_CLASSIFIER', 'fast'),
    # ── Knowledge tree generation ──
    'generate_knowledge_tree': ('AI_MODEL_GENERATE_KNOWLEDGE_TREE', 'pro'),
    # ── Knowledge edge analysis ──
    'knowledge_edge_analyze': ('AI_MODEL_GENERATE_KNOWLEDGE_TREE', 'pro'),
    # ── Grading ──
    'quizzes.grade':  ('AI_MODEL_GRADE_SUBJECTIVE',   'pro'),
    'quizzes.mock_exam_generate': ('AI_MODEL_GENERATE_AUTHOR', 'pro'),
    # ── Single pipeline reviewer ──
    'quizzes.single_pipeline.reviewer': ('AI_MODEL_GENERATE_REVIEWER', 'pro'),
    # ── Light tasks ──
    'answer':   ('AI_MODEL_GENERATE_ANSWER',    'fast'),
    'parse':    ('AI_MODEL_PARSE_TEXT',         'fast'),
    'text_parse': ('AI_MODEL_PARSE_TEXT',       'fast'),
    'schema':   ('AI_MODEL_SCHEMA_REPAIR',       'fast'),
    'repair':   ('AI_MODEL_SCHEMA_REPAIR',       'fast'),
}

# ── Embedding model config (for mem0 semantic memory) ──
EMBEDDING_MODEL = os.getenv('AI_EMBEDDING_MODEL', 'deepseek-embedding')
EMBEDDING_BASE_URL = os.getenv('AI_EMBEDDING_BASE_URL', DEFAULT_BASE_URL.replace('/chat/completions', ''))

# Thinking effort per task prefix.
# When thinking is enabled with tool calls, reasoning_content MUST be
# passed back in subsequent requests (see service.py call_ai_with_tools).
_TASK_THINKING = {
    'assistant.chat.planner':  'high',
    'pipeline.reviewer':       'high',
}


def get_model_for_task(operation: str = 'general'):
    """Select model + optional thinking effort based on operation tag.

    Resolution order (per task):
      1. per-task env var (e.g. AI_MODEL_CHAT)
      2. tier env var (AI_MODEL_FAST / AI_MODEL_PRO)
      3. hardcoded fallback (FALLBACK_FAST / FALLBACK_PRO)
      4. global LLM_MODEL env var (if no task prefix matches)
    """
    model = _get_global_model()
    thinking = None

    if operation:
        op_lower = operation.lower()
        for prefix, (env_key, tier) in _TASK_MODEL_MAP.items():
            if op_lower.startswith(prefix):
                tier_env = 'AI_MODEL_PRO' if tier == 'pro' else 'AI_MODEL_FAST'
                tier_fallback = FALLBACK_PRO if tier == 'pro' else FALLBACK_FAST
                model = os.getenv(env_key) or os.getenv(tier_env) or tier_fallback
                thinking = _TASK_THINKING.get(prefix)
                break

    return {
        "api_key": _get_api_key(),
        "base_url": _get_base_url(),
        "model": model,
        "thinking": thinking,
    }


def _get_api_key():
    return os.getenv('LLM_API_KEY', '')


def _get_base_url():
    return os.getenv('LLM_BASE_URL', DEFAULT_BASE_URL)


def _get_global_model():
    return os.getenv('LLM_MODEL', DEFAULT_MODEL)
