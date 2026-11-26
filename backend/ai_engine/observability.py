import logging
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Dict, Optional
from uuid import uuid4

from django.core.cache import cache
from django.utils import timezone


logger = logging.getLogger(__name__)
runtime_observation = ContextVar('runtime_observation', default={})
_TRACE_ID_MAX_LEN = 128


def normalize_trace_id(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text or len(text) > _TRACE_ID_MAX_LEN:
        return None
    if any(ord(ch) <= 32 or ord(ch) >= 127 for ch in text):
        return None
    return text


def current_trace_id() -> Optional[str]:
    current = runtime_observation.get()
    if not isinstance(current, dict):
        return None
    return normalize_trace_id(current.get('trace_id'))


def resolve_trace_id(explicit: Any = None, *, fallback: Any = None) -> str:
    for candidate in (explicit, current_trace_id(), fallback):
        normalized = normalize_trace_id(candidate)
        if normalized:
            return normalized
    return str(uuid4())


@contextmanager
def observe_runtime(runtime, request_id, *, trace_id=None, attempt_id=None, **source):
    resolved_trace = resolve_trace_id(trace_id, fallback=request_id)
    token = runtime_observation.set({
        **source,
        'runtime': runtime,
        'request_id': request_id,
        'attempt_id': attempt_id or uuid4(),
        'trace_id': resolved_trace,
    })
    try:
        yield resolved_trace
    finally:
        runtime_observation.reset(token)


@contextmanager
def observe_background(runtime, request_id, *, trace_id=None, **source):
    resolved_trace = resolve_trace_id(trace_id, fallback=request_id)
    token = runtime_observation.set({
        **source,
        'runtime': runtime,
        'request_id': request_id,
        'attempt_id': uuid4(),
        'trace_id': resolved_trace,
    })
    try:
        yield
    finally:
        runtime_observation.reset(token)


def model_token_counts(usage, *, anthropic=False):
    """Express both DeepSeek protocols in total input and output tokens."""
    if not isinstance(usage, dict):
        return {}

    def count(key, values=usage):
        value = values.get(key)
        return value if type(value) is int and value >= 0 else None

    if anthropic:
        uncached, output_count = count('input_tokens'), count('output_tokens')
        cached = count('cache_read_input_tokens')
        created = count('cache_creation_input_tokens')
        misses = uncached + (created or 0) if uncached is not None else None
        input_count = misses + (cached or 0) if misses is not None else None
    else:
        input_count, output_count = count('prompt_tokens'), count('completion_tokens')
        cached, misses = count('prompt_cache_hit_tokens'), count('prompt_cache_miss_tokens')
        if cached is None and isinstance(details := usage.get('prompt_tokens_details'), dict):
            cached = count('cached_tokens', details)
    return {key: value for key, value in {
        'prompt_tokens': input_count, 'completion_tokens': output_count,
        'cached_tokens': cached, 'cache_miss_tokens': misses,
    }.items() if value is not None}


def _safe_incr(key: str, timeout_seconds: int = 48 * 3600) -> None:
    try:
        cache.incr(key)
    except Exception:
        try:
            cache.set(key, 1, timeout_seconds)
        except Exception:
            # 观测不能影响业务链路
            return


def _as_text_dict(payload: Optional[Dict[str, Any]]) -> Dict[str, str]:
    if not isinstance(payload, dict):
        return {}
    normalized: Dict[str, str] = {}
    for key, value in payload.items():
        if value is None:
            continue
        normalized[str(key)] = str(value)
    return normalized


def record_ai_operation(
    operation: str,
    success: bool,
    duration_ms: int,
    error_category: str = 'none',
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    op = str(operation or 'unknown').strip() or 'unknown'
    err = str(error_category or 'none').strip() or 'none'
    now = timezone.now()
    bucket = now.strftime('%Y%m%d%H')

    base = f'ai:ops:{op}:{bucket}'
    _safe_incr(f'{base}:total')
    _safe_incr(f'{base}:success' if success else f'{base}:fail')
    if not success:
        _safe_incr(f'{base}:err:{err}')

    log_ai_operation(op, success, duration_ms, err, metadata)


def log_ai_operation(operation, success, duration_ms, error_category='none', metadata=None):
    meta = {**_as_text_dict(runtime_observation.get()), **_as_text_dict(metadata)}
    logger.info(
        "ai.obs operation=%s success=%s duration_ms=%s error=%s meta=%s",
        operation,
        success,
        max(0, int(duration_ms or 0)),
        error_category,
        meta,
    )


def record_schema_event(
    operation: str,
    stage: str,
    success: bool,
    detail: str = '',
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    op = str(operation or 'unknown').strip() or 'unknown'
    stg = str(stage or 'validate').strip() or 'validate'
    bucket = timezone.now().strftime('%Y%m%d%H')

    base = f'ai:schema:{op}:{bucket}:{stg}'
    _safe_incr(f'{base}:total')
    _safe_incr(f'{base}:success' if success else f'{base}:fail')

    meta = {**_as_text_dict(runtime_observation.get()), **_as_text_dict(metadata)}
    if detail:
        meta['detail'] = str(detail)

    logger.info(
        "ai.schema operation=%s stage=%s success=%s meta=%s",
        op,
        stg,
        success,
        meta,
    )
