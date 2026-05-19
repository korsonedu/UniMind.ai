import os
from django.conf import settings

# ── DeepSeek V4 native API defaults ──
DEFAULT_MODEL = 'deepseek-v4-pro'
DEFAULT_BASE_URL = 'https://api.deepseek.com/v1/chat/completions'

# Per-task model routing — matched against dot-separated segments of the operation name.
# First match wins (order matters). Each entry maps a segment prefix to a model name.
# flash: lightweight / latency-sensitive.  pro: quality-critical or domain expertise.
_TASK_MODEL_MAP = {
    # ── Flash ──
    'chat':              'deepseek-v4-flash',
    'interviews':        'deepseek-v4-flash',
    'classifier':        'deepseek-v4-flash',
    'objective_analysis':'deepseek-v4-flash',
    'preview_parse':     'deepseek-v4-flash',
    'generate_ai_answer':'deepseek-v4-flash',
    'schema_repair':     'deepseek-v4-flash',

    # ── Pro ──
    'author_revise':     'deepseek-v4-pro',
    'author':            'deepseek-v4-pro',
    'bulk_generate':     'deepseek-v4-pro',
    'mock_exam_generate':'deepseek-v4-pro',
    'generate_from_text':'deepseek-v4-pro',
    'generate_knowledge_tree':'deepseek-v4-pro',
    'generate_outline':  'deepseek-v4-pro',
    'generate_questions':'deepseek-v4-pro',
    'grade':             'deepseek-v4-pro',

    # ── Pro + thinking ──
    'reviewer':          'deepseek-v4-pro',
    'essay':             'deepseek-v4-pro',
}

# Thinking effort — only for tasks that genuinely need chain-of-thought reasoning.
# Thinking adds latency + cost + format instability; don't enable unless the benefit is clear.
_TASK_THINKING = {
    'author_revise': 'medium',  # Revise: incorporate reviewer feedback into updated question
    'reviewer':      'high',    # Adversarial review: deep logic + consistency check
    'essay':         'max',     # Essay grading: multi-dimensional rubric evaluation
}


def _match_operation(op_lower: str, prefix: str) -> bool:
    """Match if *op* starts with *prefix* OR any dot-separated segment starts with *prefix*."""
    if op_lower.startswith(prefix):
        return True
    for segment in op_lower.split('.'):
        if segment.startswith(prefix):
            return True
    return False


def get_llm_config():
    """Return the default (global) LLM config."""
    return {
        "api_key": _get_api_key(),
        "base_url": _get_base_url(),
        "model": _get_global_model(),
    }


def get_model_for_task(operation: str = 'general'):
    """Select model + optional thinking effort based on operation tag.

    Resolution order: per-task map → global ``LLM_MODEL`` env var → ``deepseek-v4-pro``.
    Matches against dot-separated segments (e.g. ``quizzes.grade_question``
    matches the ``grade`` prefix via its ``grade_question`` segment).
    """
    model = _get_global_model()
    thinking = None

    if operation:
        op_lower = operation.lower()
        for prefix, task_model in _TASK_MODEL_MAP.items():
            if _match_operation(op_lower, prefix):
                model = task_model
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
