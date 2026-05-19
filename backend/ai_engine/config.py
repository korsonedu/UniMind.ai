import os
from django.conf import settings

# ── DeepSeek V4 native API defaults ──
DEFAULT_MODEL = 'deepseek-v4-pro'
DEFAULT_BASE_URL = 'https://api.deepseek.com/v1/chat/completions'

# Per-task model routing table — mirrors README model strategy matrix
_TASK_MODEL_MAP = {
    # ── Chat / interview (fast response) ──
    'chat':     ('AI_MODEL_CHAT',              'deepseek-v4-flash'),
    'interviews': ('AI_MODEL_CHAT',            'deepseek-v4-flash'),
    # ── Question generation pipeline ──
    'pipeline.author':    ('AI_MODEL_GENERATE_AUTHOR',    'deepseek-v4-pro'),
    'pipeline.reviewer':  ('AI_MODEL_GENERATE_REVIEWER',  'deepseek-v4-pro'),
    'pipeline.author_revise': ('AI_MODEL_GENERATE_AUTHOR', 'deepseek-v4-pro'),
    'pipeline.classifier':('AI_MODEL_GENERATE_CLASSIFIER', 'deepseek-v4-flash'),
    # ── Knowledge tree generation ──
    'generate_knowledge_tree': ('AI_MODEL_GENERATE_KNOWLEDGE_TREE', 'deepseek-v4-pro'),
    # ── Grading (thinking enabled) ──
    'grading':  ('AI_MODEL_GRADE_SUBJECTIVE',   'deepseek-v4-pro'),
    'grade':    ('AI_MODEL_GRADE_SUBJECTIVE',   'deepseek-v4-pro'),
    'essay':    ('AI_MODEL_ESSAY_GRADE',        'deepseek-v4-pro'),
    # ── Light tasks ──
    'answer':   ('AI_MODEL_GENERATE_ANSWER',    'deepseek-v4-flash'),
    'parse':    ('AI_MODEL_PARSE_TEXT',         'deepseek-v4-flash'),
    'text_parse': ('AI_MODEL_PARSE_TEXT',       'deepseek-v4-flash'),
    'schema':   ('AI_MODEL_SCHEMA_REPAIR',       'deepseek-v4-flash'),
    'repair':   ('AI_MODEL_SCHEMA_REPAIR',       'deepseek-v4-flash'),
}

# Thinking effort per task prefix (only applies to pro-class models)
_TASK_THINKING = {
    'pipeline.reviewer':       'high',
    'pipeline.author_revise':  'medium',
    'grading':                 'high',
    'grade':                   'high',
    'essay':                   'max',
}


def get_llm_config():
    """Return the default (global) LLM config."""
    return {
        "api_key": _get_api_key(),
        "base_url": _get_base_url(),
        "model": _get_global_model(),
    }


def get_model_for_task(operation: str = 'general'):
    """Select model + optional thinking effort based on operation tag.

    Resolution order: env-var override → task map → global default.
    """
    model = _get_global_model()
    thinking = None

    if operation:
        op_lower = operation.lower()
        for prefix, (env_key, fallback) in _TASK_MODEL_MAP.items():
            if op_lower.startswith(prefix):
                model = os.getenv(env_key, fallback)
                thinking = _TASK_THINKING.get(prefix)
                break

    return {
        "api_key": _get_api_key(),
        "base_url": _get_base_url(),
        "model": model,
        "thinking": thinking,
    }


def _get_api_key():
    return os.getenv('DEEPSEEK_API_KEY') or os.getenv('LLM_API_KEY', '')


def _get_base_url():
    return os.getenv('LLM_BASE_URL', DEFAULT_BASE_URL)


def _get_global_model():
    return os.getenv('LLM_MODEL', DEFAULT_MODEL)
