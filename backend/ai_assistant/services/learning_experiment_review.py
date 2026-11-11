"""Independent image review; only the trusted backend receives model credentials."""
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import struct
from time import monotonic
from urllib.parse import urlsplit

import requests
from django.conf import settings
from django.db import transaction
from jsonschema import Draft202012Validator

from ai_engine.config import get_model_for_task
from ai_engine.observability import record_ai_operation
from ai_assistant.models import AIChatMessage


def reserve_review(current):
    if current is None:
        return False
    with transaction.atomic():
        message = AIChatMessage.objects.select_for_update().get(pk=current.pk, user_id=current.user_id, role='user')
        attempts = message.metadata.get('visual_review_attempts', 0)
        if attempts >= 2:
            return False
        AIChatMessage.objects.filter(pk=message.pk).update(
            metadata={**message.metadata, 'visual_review_attempts': attempts + 1})
    return True


def review_screenshots(frames):
    model = os.getenv('AI_MODEL_EXPERIMENT_REVIEW') or 'deepseek-flash'
    result = {'status': 'unavailable', 'model': model, 'frames': [], 'issues': []}
    started = monotonic()
    try:
        result['frames'] = [{k: frame[k] for k in ('id', 'width', 'height', 'phase', 'sha256')} for frame in frames]
        ids = [frame['id'] for frame in frames]
        if not 4 <= len(frames) <= 8 or len(set(ids)) != len(ids):
            raise ValueError('Incomplete screenshot set')
        if not {'initial-700', 'initial-360', 'final-360'} <= set(ids):
            raise ValueError('Missing viewport evidence')
        total_bytes, content = 0, []
        for frame in frames:
            if len(frame['png']) > 700000:
                raise ValueError('Screenshot too large')
            raw = base64.b64decode(frame['png'], validate=True)
            total_bytes += len(raw)
            if (not raw.startswith(b'\x89PNG\r\n\x1a\n') or len(raw) < 24
                    or struct.unpack('>II', raw[16:24]) != (frame['width'], frame['height'])
                    or hashlib.sha256(raw).hexdigest() != frame['sha256']
                    or len(raw) > 512 * 1024 or total_bytes > 2 * 1024 * 1024):
                raise ValueError('Invalid screenshot evidence')
            content.extend([{'type': 'text', 'text': f"frame_id={frame['id']}; {frame['width']}x{frame['height']} CSS px"},
                {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + frame['png'], 'detail': 'original'}}])
        config = get_model_for_task('assistant.chat.planner')
        endpoint = urlsplit(config['base_url'])
        if not config['api_key'] or endpoint.scheme != 'https' or endpoint.username or endpoint.query or endpoint.fragment:
            raise ValueError('Visual reviewer is not configured')
        prompt = (Path(settings.BASE_DIR) / 'prompts/ai_assistant/bots/xiaoyu/experiment_visual_review.txt').read_text()
        with requests.Session() as session:
            session.trust_env = False
            with session.post(config['base_url'], headers={'Authorization': 'Bearer ' + config['api_key']},
                    json={'model': model, 'messages': [{'role': 'system', 'content': prompt},
                        {'role': 'user', 'content': content}], 'thinking': {'type': 'disabled'},
                        'response_format': {'type': 'json_object'}, 'temperature': 0, 'max_tokens': 1600,
                        'stream': False}, timeout=(3, 15), allow_redirects=False, stream=True) as response:
                response.raise_for_status()
                raw = bytearray()
                for chunk in response.iter_content(4096):
                    raw.extend(chunk)
                    if len(raw) > 65536:
                        raise ValueError('Review response too large')
        reply = json.loads(raw)
        verdict = json.loads(reply['choices'][0]['message']['content'])
        schema = {'type': 'object', 'additionalProperties': False, 'required': ['passed', 'issues'], 'properties': {
            'passed': {'type': 'boolean'}, 'issues': {'type': 'array', 'maxItems': 6, 'items': {
                'type': 'object', 'additionalProperties': False, 'required': ['frame_id', 'category', 'description', 'bbox'],
                'properties': {'frame_id': {'enum': ids}, 'category': {'enum': [
                    'overlap', 'cropped', 'unreadable', 'blank', 'misleading', 'other']},
                    'description': {'type': 'string', 'minLength': 1, 'maxLength': 240},
                    'bbox': {'type': 'array', 'minItems': 4, 'maxItems': 4,
                        'items': {'type': 'number', 'minimum': 0}}}}}}}
        if not Draft202012Validator(schema).is_valid(verdict) or verdict['passed'] == bool(verdict['issues']):
            raise ValueError('Invalid review verdict')
        by_id = {frame['id']: frame for frame in frames}
        for issue in verdict['issues']:
            x, y, w, h = issue['bbox']
            frame = by_id[issue['frame_id']]
            if (not all(math.isfinite(value) for value in (x, y, w, h))
                    or w <= 0 or h <= 0 or x + w > frame['width'] or y + h > frame['height']):
                raise ValueError('Review coordinates outside screenshot')
        usage = reply.get('usage') or {}
        result.update(status='passed' if verdict['passed'] else 'rejected', issues=verdict['issues'],
            usage={key: usage[key] for key in ('prompt_tokens', 'completion_tokens') if isinstance(usage.get(key), int)})
    except (requests.RequestException, ValueError, KeyError, TypeError, IndexError) as error:
        result['error'] = '独立视觉审查无法完成，本次未挂载；请稍后重试。'
        result['failure_kind'] = type(error).__name__
        if isinstance(error, requests.HTTPError) and error.response is not None:
            result['http_status'] = error.response.status_code
    record_ai_operation('assistant.experiment.visual_review', result['status'] != 'unavailable',
        int((monotonic() - started) * 1000), error_category=result.get('failure_kind', 'none'),
        metadata={'model': model, 'frames': len(frames), 'decision': result['status'], **result.get('usage', {})})
    return result
