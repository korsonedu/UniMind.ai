"""Strict batched client for configured online embedding endpoints (e.g. SiliconFlow / llama-server)."""
import os
from time import monotonic

import httpx
import numpy as np

from ai_engine import config
from ai_engine.observability import log_ai_operation, model_token_counts, runtime_observation
from .exceptions import EmbeddingError

_DIMENSION_PARAM_MODELS = ("qwen3-embedding", "text-embedding-3")


def _embeddings_endpoint(base_url):
    base = (base_url or "").strip().rstrip("/")
    if not base:
        raise EmbeddingError("EMBEDDING_BASE_URL must be configured")
    return base if base.endswith("/embeddings") else f"{base}/embeddings"


def _supports_dimensions_param(model_name):
    normalized = (model_name or "").strip().casefold()
    return any(token in normalized for token in _DIMENSION_PARAM_MODELS)


def _should_send_dimensions(model_name, dimensions):
    if dimensions <= 0:
        return False
    mode = os.getenv("AI_EMBEDDING_SEND_DIMENSIONS", "auto").strip().casefold()
    if mode in {"1", "true", "yes", "on"}:
        return True
    if mode in {"0", "false", "no", "off"}:
        return False
    return _supports_dimensions_param(model_name)


def _default_batch_size():
    raw = os.getenv("AI_EMBEDDING_BATCH_SIZE", "32").strip()
    try:
        value = int(raw)
    except ValueError as error:
        raise EmbeddingError(f"AI_EMBEDDING_BATCH_SIZE must be a positive integer: {raw!r}") from error
    if value <= 0:
        raise EmbeddingError(f"AI_EMBEDDING_BATCH_SIZE must be a positive integer: {value}")
    return value


def _request_batch(texts):
    endpoint = _embeddings_endpoint(config.EMBEDDING_BASE_URL)
    expected_dim = int(config.EMBEDDING_DIMENSIONS or 0)
    body = {"model": config.EMBEDDING_MODEL, "input": texts}
    if _should_send_dimensions(config.EMBEDDING_MODEL, expected_dim):
        body["dimensions"] = expected_dim
    started = monotonic()
    payload = None
    try:
        response = httpx.post(
            endpoint,
            json=body,
            headers={"Authorization": f"Bearer {config.EMBEDDING_API_KEY}",
                     "Content-Type": "application/json"},
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPStatusError as error:
        detail = error.response.text.strip()[:300]
        suffix = f" | body={detail}" if detail else ""
        raise EmbeddingError(f"Embedding HTTP/JSON request failed: {error}{suffix}") from error
    except (httpx.HTTPError, ValueError) as error:
        raise EmbeddingError(f"Embedding HTTP/JSON request failed: {error}") from error
    finally:
        if runtime_observation.get():
            details = payload if isinstance(payload, dict) else {}
            reported = details.get('model')
            log_ai_operation('knowledge_tree.embedding', payload is not None, round((monotonic() - started) * 1000),
                'none' if payload is not None else 'upstream', metadata={
                    'kind': 'embedding', 'model': config.EMBEDDING_MODEL, 'input_count': len(texts),
                    'reported_model': reported if isinstance(reported, str) and len(reported) <= 160 else None,
                    **model_token_counts(details.get('usage')),
                })
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise EmbeddingError("Embedding response must contain a data array")
    rows = payload["data"]
    if len(rows) != len(texts) or any(not isinstance(row, dict) for row in rows):
        raise EmbeddingError("Embedding response count differs from input count")
    indices = [row.get("index") for row in rows]
    if any(type(index) is not int for index in indices) or sorted(indices) != list(range(len(texts))):
        raise EmbeddingError("Embedding indices must be a complete unique input permutation")
    vectors = [row.get("embedding") for row in sorted(rows, key=lambda row: row["index"])]
    if any(not isinstance(vector, list) or not vector for vector in vectors):
        raise EmbeddingError("Embedding vectors must be nonempty arrays")
    if any(any(type(value) not in (int, float) for value in vector) for vector in vectors):
        raise EmbeddingError("Embedding coordinates must be numbers")
    if len({len(vector) for vector in vectors}) != 1:
        raise EmbeddingError("Embedding dimensions are inconsistent")
    matrix = np.asarray(vectors, dtype=np.float64)
    if expected_dim > 0 and matrix.shape[1] != expected_dim:
        raise EmbeddingError(
            f"Embedding dimensions differ from configured dimensions (expected {expected_dim}, got {matrix.shape[1]})"
        )
    norms = np.linalg.norm(matrix, axis=1)
    if not np.isfinite(matrix).all() or not np.isfinite(norms).all() or np.any(norms <= 0):
        raise EmbeddingError("Embedding vectors must be finite and have nonzero L2 norms")
    return matrix / norms[:, None]


def embed_views(atoms, batch_size=None):
    resolved_batch_size = _default_batch_size() if batch_size is None else batch_size
    if not atoms or type(resolved_batch_size) is not int or resolved_batch_size <= 0:
        raise EmbeddingError("Embedding requires atoms and a positive batch size")
    texts = {
        "parent": [atom["parent_path"] for atom in atoms],
        "point": [f"{atom['name']}；要素：{'、'.join(atom['key_elements'])}" for atom in atoms],
        "namegoal": [f"{atom['name']}：{atom['goal_statement']}" for atom in atoms],
    }
    views = {}
    for view, items in texts.items():
        batches = [_request_batch(items[start:start + resolved_batch_size])
                   for start in range(0, len(items), resolved_batch_size)]
        if len({batch.shape[1] for batch in batches}) != 1:
            raise EmbeddingError("Embedding dimensions changed between batches")
        views[view] = np.concatenate(batches, axis=0)
    if len({matrix.shape for matrix in views.values()}) != 1:
        raise EmbeddingError("Embedding dimensions differ between views")
    return views
