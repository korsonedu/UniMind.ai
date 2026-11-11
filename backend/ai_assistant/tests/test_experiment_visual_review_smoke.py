"""Visual gate smoke; no external model requests."""
import base64
import binascii
from copy import deepcopy
import hashlib
import json
import struct
from unittest.mock import MagicMock, patch
from uuid import uuid4
import zlib

import pytest
import requests

from ai_assistant.models import AIChatMessage, Bot
from ai_assistant.services import learning_experiments as experiments
from ai_assistant.services import learning_experiment_review as reviewer


def screenshots():
    def png(width, height):
        def chunk(tag, data):
            return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', binascii.crc32(tag + data) & 0xffffffff)
        pixels = (b'\0' + b'\xff' * width * 3) * height
        return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
                + chunk(b'IDAT', zlib.compress(pixels)) + chunk(b'IEND', b''))
    frames = []
    for phase, width, height in [('initial', 700, 360), ('initial', 360, 420), ('check-1', 700, 360), ('final', 360, 420)]:
        raw = png(width, height)
        frames.append({'id': f'{phase}-{width}', 'phase': phase, 'width': width, 'height': height,
            'sha256': hashlib.sha256(raw).hexdigest(), 'png': base64.b64encode(raw).decode()})
    return frames


def response(verdict):
    result = MagicMock()
    result.__enter__.return_value = result
    result.iter_content.return_value = [json.dumps({'choices': [{'message': {'content': json.dumps(verdict)}}],
        'usage': {'prompt_tokens': 100, 'completion_tokens': 20}}).encode()]
    return result


@pytest.fixture
def lecture(user, settings):
    settings.DEBUG = settings.UNIMIND_LEARNING_EXPERIMENTS_PROTOTYPE = True
    settings.UNIMIND_LEARNING_VISUAL_REVIEW_ENABLED = True
    user.is_member = True
    user.save(update_fields=['is_member'])
    bot = Bot.objects.create(name='小宇', bot_type='planner')
    message = AIChatMessage.objects.create(user=user, bot=bot, role='user', content='解释这个图形')
    claims = {'message_id': message.pk, 'bot_id': bot.pk, 'conversation_id': str(message.conversation_id)}
    args = {'title': '合成画布讲解', 'html': '<button id="go">观察</button><canvas></canvas><output id="out">1</output>',
        'checks': [{'selector': '#go', 'action': 'click', 'expect_selector': '#out', 'expect_text': '1'}]}
    return user, message, claims, args


@pytest.mark.django_db
def test_visual_rejection_blocks_mount_then_passes_without_storing_images(lecture):
    user, message, claims, args = lecture
    frames = screenshots()
    problem = {'frame_id': 'initial-700', 'category': 'overlap', 'description': 'canvas中图例遮挡了数值。', 'bbox': [10, 20, 80, 30]}
    session = MagicMock()
    session.__enter__.return_value = session
    session.post.side_effect = [response({'passed': False, 'issues': [problem]}), response({'passed': True, 'issues': []})]
    worker = {'ok': True, 'errors': [], 'checks': [{'ok': True}], 'screenshots': frames}
    with patch('ai_assistant.services.learning_worker.run', side_effect=lambda *a, **k: deepcopy(worker)), \
            patch.object(reviewer.requests, 'Session', return_value=session), \
            patch.object(reviewer, 'get_model_for_task', return_value={
                'api_key': 'synthetic-secret', 'base_url': 'https://api.deepseek.com/v1/chat/completions'}):
        failed = experiments.execute(user, 'build_learning_experiment', args, claims)
        assert 'visual' not in failed and failed['preview']['visual_review']['status'] == 'rejected'
        message.refresh_from_db()
        assert not message.metadata.get('learning_experiments')
        assert message.metadata['visual_review_attempts'] == 1
        good = experiments.execute(user, 'build_learning_experiment', args, claims)
        assert good['visual']['type'] == 'learning_experiment'
        exhausted = experiments.execute(user, 'build_learning_experiment', {
            **args, 'experiment_id': good['experiment_id'], 'base_revision': 1}, claims)
        assert exhausted['preview']['visual_review']['status'] == 'budget_exhausted'
        assert '无需修改源码' in exhausted['error']
        assert session.post.call_count == 2
        body = session.post.call_args.kwargs['json']
        assert body['model'] == 'deepseek-flash'
        assert len([part for part in body['messages'][1]['content'] if part['type'] == 'image_url']) == 4
        assert session.post.call_args.kwargs['allow_redirects'] is False
    message.refresh_from_db()
    saved = json.dumps(message.metadata)
    assert 'data:image' not in saved and frames[0]['png'] not in saved and 'synthetic-secret' not in saved
    assert message.metadata['learning_experiments'][good['experiment_id']]['revision'] == 1


@pytest.mark.django_db
def test_visual_approval_cannot_overwrite_parameters_changed_during_review(lecture):
    user, message, claims, args = lecture
    key = str(uuid4())
    message.metadata = {'learning_experiments': {key: {'experiment_id': key, 'title': '旧版',
        'html': args['html'], 'state': {}, 'state_version': 0, 'revision': 1}}}
    message.save(update_fields=['metadata'])
    def approve(_frames):
        message.refresh_from_db()
        message.metadata['learning_experiments'][key].update(state={'rate': 6}, state_version=1)
        message.save(update_fields=['metadata'])
        return {'status': 'passed', 'issues': []}
    with patch('ai_assistant.services.learning_worker.run', return_value={'ok': True, 'errors': [], 'screenshots': screenshots()}), \
            patch.object(reviewer, 'review_screenshots', side_effect=approve):
        with pytest.raises(experiments.ExperimentConflict):
            experiments.execute(user, 'build_learning_experiment', {**args, 'title': '未核验的新状态',
                'experiment_id': key, 'base_revision': 1}, claims)
    message.refresh_from_db()
    stored = message.metadata['learning_experiments'][key]
    assert stored['revision'] == 1 and stored['title'] == '旧版' and stored['state'] == {'rate': 6}


def test_invalid_or_unavailable_visual_review_never_passes():
    frames = screenshots()
    session = MagicMock()
    session.__enter__.return_value = session
    bad = {'passed': True, 'issues': [{'frame_id': 'initial-700', 'category': 'blank', 'description': '空白', 'bbox': [0, 0, 40, 40]}]}
    session.post.side_effect = [response(bad), requests.Timeout('synthetic timeout')]
    with patch.object(reviewer.requests, 'Session', return_value=session), \
            patch.object(reviewer, 'get_model_for_task', return_value={
                'api_key': 'synthetic', 'base_url': 'https://api.deepseek.com/v1/chat/completions'}):
        assert reviewer.review_screenshots(frames)['status'] == 'unavailable'
        assert reviewer.review_screenshots(frames)['status'] == 'unavailable'
    assert session.post.call_count == 2
