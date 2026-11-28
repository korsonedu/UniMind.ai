"""Transcribe a short external-video audio snippet on its original timeline."""
import logging
import math
import os
import tempfile
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.cache import cache
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from courses.asr import ASRProviderRegistry


logger = logging.getLogger(__name__)

MAX_AUDIO_BYTES = 4 * 1024 * 1024
CACHE_TIMEOUT = 86400
AUDIO_EXTENSIONS = {'.m4a', '.mp4', '.m4s', '.aac', '.webm', '.ogg', '.wav', '.mp3'}
OSS_SETTINGS = ('OSS_ACCESS_KEY_ID', 'OSS_ACCESS_KEY_SECRET', 'OSS_BUCKET_NAME', 'OSS_ENDPOINT')


def _validate_audio(audio):
    if audio is None or not getattr(audio, 'size', 0):
        raise ValidationError('请上传非空音频切片。')
    if audio.size > MAX_AUDIO_BYTES:
        raise ValidationError('音频切片不能超过 4 MiB。')
    extension = Path(audio.name or '').suffix.lower()
    content_type = (getattr(audio, 'content_type', '') or '').split(';', 1)[0].strip().lower()
    if (extension not in AUDIO_EXTENSIONS and not content_type.startswith('audio/')
            and content_type not in ('video/mp4', 'application/octet-stream')):
        raise ValidationError('请上传支持的音频切片格式。')
    return audio


class ExternalAudioSnippetInput(serializers.Serializer):
    audio = serializers.FileField(allow_empty_file=False)
    platform = serializers.CharField(default='generic')
    external_id = serializers.CharField(max_length=128)
    part = serializers.IntegerField(default=1, allow_null=True)
    clip_start_seconds = serializers.FloatField(default=0.0)

    def validate_audio(self, value):
        return _validate_audio(value)

    def validate_platform(self, value):
        value = value.lower()
        if value not in ('bilibili', 'youtube', 'generic'):
            raise ValidationError('不支持的视频平台。')
        return value

    def validate_part(self, value):
        return value if value is not None and value > 0 else 1

    def validate_clip_start_seconds(self, value):
        if not math.isfinite(value):
            raise ValidationError('音频起点必须是有限秒数。')
        return max(0.0, value)


def _oss_configured():
    return all(str(getattr(settings, key, '') or '').strip() for key in OSS_SETTINGS)


def _select_provider():
    configs = getattr(settings, 'ASR_PROVIDER_CONFIG', {})
    preferred = os.environ.get('EXTERNAL_SNIPPET_ASR_PROVIDER', '').strip()
    candidates = [preferred, 'mimo_asr', 'glm_asr', 'whisper_openai', 'qwen_filetrans']
    for name in dict.fromkeys(candidates):
        provider_class = ASRProviderRegistry._providers.get(name)
        if provider_class is None:
            continue
        config = configs.get(name, {})
        needs_key = getattr(provider_class, 'requires_api_key', name not in ('dummy', 'vosk'))
        if needs_key and not str(config.get('api_key', '') or '').strip():
            continue
        if name == 'qwen_filetrans' and not _oss_configured():
            continue
        return name, ASRProviderRegistry.get_provider(name, config)
    return None, None


def _transcribe_with_oss(provider, audio_path):
    import oss2

    endpoint = settings.OSS_ENDPOINT
    if not endpoint.startswith(('http://', 'https://')):
        endpoint = 'https://' + endpoint
    auth = oss2.Auth(settings.OSS_ACCESS_KEY_ID, settings.OSS_ACCESS_KEY_SECRET)
    bucket = oss2.Bucket(auth, endpoint, settings.OSS_BUCKET_NAME)
    object_key = f'tmp/ext-asr/{uuid4().hex}{Path(audio_path).suffix}'
    try:
        with open(audio_path, 'rb') as source:
            bucket.put_object(object_key, source)
        return provider.transcribe_url(bucket.sign_url('GET', object_key, 3600))
    finally:
        try:
            bucket.delete_object(object_key)
        except Exception:
            logger.warning('External snippet temporary OSS object cleanup failed.')


def transcribe_external_snippet(audio, *, platform, external_id, part=1, clip_start_seconds=0.0):
    """Return absolute transcript timestamps, or an available=False configuration fallback."""
    data = ExternalAudioSnippetInput(data={
        'audio': audio, 'platform': platform, 'external_id': external_id,
        'part': part, 'clip_start_seconds': clip_start_seconds,
    })
    data.is_valid(raise_exception=True)
    values = data.validated_data
    offset = values['clip_start_seconds']
    cache_key = (f"ext_asr:v1:{values['platform']}:{values['external_id']}:"
                 f"p{values['part']}:{int(offset // 15)}")
    try:
        cached = cache.get(cache_key)
    except Exception:
        cached = None
    if cached is not None:
        return {**cached, 'cached': True}

    name, provider = _select_provider()
    if provider is None:
        return {'available': False, 'provider': 'unconfigured', 'cached': False,
                'segments': [], 'full_text': ''}

    suffix = Path(audio.name or '').suffix.lower()
    if suffix not in AUDIO_EXTENSIONS or suffix == '.m4s':
        suffix = '.m4a'
    with tempfile.TemporaryDirectory(prefix='ext_asr_') as directory:
        audio_path = os.path.join(directory, 'snippet' + suffix)
        audio.seek(0)
        written = 0
        with open(audio_path, 'wb') as output:
            for chunk in audio.chunks():
                written += len(chunk)
                if written > MAX_AUDIO_BYTES:
                    raise ValidationError('音频切片不能超过 4 MiB。')
                output.write(chunk)
        if not written:
            raise ValidationError('请上传非空音频切片。')
        result = (_transcribe_with_oss(provider, audio_path) if name == 'qwen_filetrans'
                  else provider.transcribe(audio_path))

    response = {
        'available': True, 'provider': name, 'cached': False,
        'segments': [
            {'start_time': round(offset + float(segment.start), 2),
             'end_time': round(offset + float(segment.end), 2), 'text': segment.text}
            for segment in result.segments
        ],
        'full_text': result.full_text,
    }
    try:
        cache.set(cache_key, response, timeout=CACHE_TIMEOUT)
    except Exception:
        pass
    return response
