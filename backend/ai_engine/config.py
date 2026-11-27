import os

# ── Model provider defaults ──
FALLBACK_FAST = 'deepseek-v4-flash'     # 轻量任务：对话、分类、解析、schema修复（原生支持多模态视觉）
FALLBACK_PRO  = 'deepseek-v4-pro'       # 重量任务：评审、判分、知识树生成（纯文本，不读图）
FALLBACK_VISION = FALLBACK_FAST         # 多模态视觉默认走 deepseek-v4-flash，可通过 AI_MODEL_VISION 热切换（如 Qwen3-VL-Plus）
DEFAULT_MODEL = FALLBACK_FAST
DEFAULT_BASE_URL = 'https://api.deepseek.com/v1/chat/completions'

# Per-task model routing table.
# Each task → (per_task_env_key, tier) where tier ∈ {'fast', 'pro'}.
_TASK_MODEL_MAP = {
    'knowledge_tree_dispatch': ('AI_MODEL_KNOWLEDGE_TREE_DISPATCH', 'fast'),
    'knowledge_tree_decompose': ('AI_MODEL_GENERATE_KNOWLEDGE_TREE', 'fast'),
    'knowledge_tree_edges': ('AI_MODEL_GENERATE_KNOWLEDGE_TREE', 'fast'),
    'knowledge_tree_repair': ('AI_MODEL_SCHEMA_REPAIR', 'fast'),
    'knowledge_tree_block': ('AI_MODEL_GENERATE_KNOWLEDGE_TREE', 'fast'),
    'knowledge_builder_source_align': ('AI_MODEL_PARSE_TEXT', 'fast'),
    'knowledge_builder_micro_lesson': ('AI_MODEL_CHAT', 'fast'),
    # ── Chat ──
    # 前缀匹配规则：'assistant.chat.planner' 精确匹配小宇，其他 agent 操作 fallback 到默认 flash
    'assistant.chat.planner': ('AI_MODEL_CHAT', 'fast'),
    'assistant.chat.planner.learning': ('AI_MODEL_CHAT', 'fast'),
    'assistant.learning.probe_assessment': ('AI_MODEL_FAST', 'fast'),
    'assistant.title': ('AI_MODEL_FAST', 'fast'),
    'assistant.memory_extract': ('AI_MODEL_FAST', 'fast'),
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
    'ulr.quizzes.objective_analysis': ('AI_MODEL_OBJECTIVE_ANALYSIS', 'fast'),
    'ulr.quizzes.preview_parse': ('AI_MODEL_FAST', 'fast'),
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
EMBEDDING_MODEL = os.getenv('AI_EMBEDDING_MODEL', 'Qwen/Qwen3-Embedding-0.6B')
EMBEDDING_BASE_URL = os.getenv('AI_EMBEDDING_BASE_URL', 'http://127.0.0.1:8012/v1').rstrip('/')
EMBEDDING_API_KEY = os.getenv('AI_EMBEDDING_API_KEY', 'local')
EMBEDDING_DIMENSIONS = int(os.getenv('AI_EMBEDDING_DIMENSIONS') or '1024')

# Thinking effort per task prefix.
# When thinking is enabled with tool calls, reasoning_content MUST be
# passed back in subsequent requests (see service.py call_ai_with_tools).
_TASK_THINKING = {
    'pipeline.reviewer':       'high',
}


def get_model_tier_for_operation(operation: str = 'general') -> str | None:
    """根据 operation 返回模型等级（'fast' / 'pro' / None）。"""
    if not operation:
        return None
    op_lower = operation.lower()
    for prefix, (_, tier) in _TASK_MODEL_MAP.items():
        if op_lower.startswith(prefix):
            return tier
    return None


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


def messages_contain_images(messages) -> bool:
    """Return True if any OpenAI-format chat message carries an image_url content block."""
    for msg in messages or ():
        content = msg.get('content') if isinstance(msg, dict) else None
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get('type') == 'image_url':
                    return True
    return False


def get_vision_model_for_task(operation: str = 'general'):
    """Select a verified vision-capable model (defaults to deepseek-v4-flash, hot-swappable via AI_MODEL_VISION).

    Avoids routing image payloads to text-only pro models (e.g. deepseek-v4-pro).
    Supports dedicated AI_VISION_BASE_URL / AI_VISION_API_KEY for optional Qwen-VL / GLM-V routing.
    """
    base_cfg = get_model_for_task(operation)
    vision_model = os.getenv('AI_MODEL_VISION') or FALLBACK_VISION
    vision_base_url = os.getenv('AI_VISION_BASE_URL') or base_cfg['base_url']
    vision_api_key = os.getenv('AI_VISION_API_KEY') or base_cfg['api_key']
    return {
        "api_key": vision_api_key,
        "base_url": vision_base_url,
        "model": vision_model,
        "thinking": None,
    }


def _get_api_key():
    return os.getenv('LLM_API_KEY', '')


def _get_base_url():
    return os.getenv('LLM_BASE_URL', DEFAULT_BASE_URL)


def _get_global_model():
    return os.getenv('LLM_MODEL', DEFAULT_MODEL)
