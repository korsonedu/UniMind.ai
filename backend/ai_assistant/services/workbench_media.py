"""Ingest time-based sources using the course access rules and ASR providers."""

import math
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

from django.conf import settings
from rest_framework.exceptions import PermissionDenied

from ai_assistant.models import WORKBENCH_SOURCE_PREFIX
from courses.access import visible_courses_for
from courses.asr import (
    ASRProviderRegistry, DummyASRProvider, GLMChunkedASRProvider, MiMoASRProvider,
    OpenAIWhisperProvider, QwenFileTransASRProvider, VoskASRProvider,
)
from courses.models import Course, TranscriptSegment, VideoTranscript
from users.feature_access import has_learning_feature

from .workbench_parsers import (
    WorkbenchParseError, parse_docx_file, parse_pdf_file, parse_pptx_file, parse_text_content,
)

VIDEO_EXTENSIONS = {'.mp4', '.mov', '.webm'}
MEDIA_FORMATS = {
    '.mp4': 'mov', '.mov': 'mov', '.webm': 'matroska',
    '.mp3': 'mp3', '.m4a': 'mov', '.wav': 'wav',
}
COURSEWARE_PARSERS = {'.pdf': parse_pdf_file, '.pptx': parse_pptx_file, '.docx': parse_docx_file}
SENTENCE_END = re.compile(r'[。！？.!?；;][”’」』"\']*$')
CJK_ADJACENT = re.compile(r'(?<=[\u3400-\u9fff。！？；，、]) (?=[\u3400-\u9fff。！？；，、])')


@dataclass
class MediaIngest:
    chunks: list
    updates: dict = field(default_factory=dict)
    segments: list = field(default_factory=list)
    language: str = ''
    provider_name: str = ''


def _normalize_segments(segments):
    normalized = []
    for segment in segments:
        try:
            start, end = float(segment['start_time']), float(segment['end_time'])
            text = segment['text'].strip()
        except (KeyError, TypeError, ValueError, AttributeError, OverflowError) as exc:
            raise WorkbenchParseError('字幕格式无效，请检查时间和文本。') from exc
        if not math.isfinite(start) or not math.isfinite(end) or not 0 <= start <= end <= 2_147_483_647:
            raise WorkbenchParseError('字幕时间无效，请检查起止时间。')
        if text:
            normalized.append({'start_time': start, 'end_time': end, 'text': text})
    return sorted(normalized, key=lambda item: item['start_time'])


def _timestamp(seconds):
    hours, remainder = divmod(int(seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f'{hours:02}:{minutes:02}:{seconds:02}' if hours else f'{minutes:02}:{seconds:02}'


def _timestamp_chunks(segments):
    chunks = []
    window = []
    end = length = 0

    def flush():
        start = window[0]['start_time']
        chunks.append({
            'anchor_type': 'timestamp', 'locator_label': _timestamp(start),
            'start_seconds': start, 'end_seconds': end,
            'content': CJK_ADJACENT.sub('', ' '.join(line['text'] for line in window)),
            'metadata': {'segments': window.copy()},
        })
        window.clear()

    for segment in segments:
        start, finish, text = segment['start_time'], segment['end_time'], segment['text']
        if window and (start - end >= 8 or finish - window[0]['start_time'] > 50 or length + len(text) > 600):
            flush()
        if not window:
            end = length = 0
        window.append(segment)
        end = max(end, finish)
        length += len(text) + 1
        if (end - window[0]['start_time'] >= 25 or length >= 250) and SENTENCE_END.search(text):
            flush()
    if window:
        flush()
    return chunks


def segments_to_timestamp_chunks(segments):
    return _timestamp_chunks(_normalize_segments(segments))


def ingest_station_course(source):
    if not source.course_id or not has_learning_feature(source.user, 'course.video'):
        raise WorkbenchParseError('该课程不存在或当前账号无权访问。')
    try:
        course = visible_courses_for(source.user).filter(pk=source.course_id).first()
    except PermissionDenied as exc:
        raise WorkbenchParseError(str(exc.detail)) from exc
    if course is None:
        raise WorkbenchParseError('该课程不存在或当前账号无权访问。')

    outline = getattr(course, 'outline', None)
    items = list(outline.items.values('title', 'timestamp', 'description')) if outline and outline.status == 'completed' else []
    updates = {'metadata': {**source.metadata, 'outline': items}}
    transcript = getattr(course, 'transcript', None)
    if transcript and transcript.asr_status == 'completed':
        chunks = segments_to_timestamp_chunks(transcript.segments.values('start_time', 'end_time', 'text'))
        if chunks:
            return MediaIngest(chunks, updates)

    blocks = [course.description, *(f"## {item['title']}\n{item['description']}" for item in items)]
    if transcript and transcript.asr_status == 'completed':
        blocks.append(transcript.full_text)
    content = '\n\n'.join(block.strip() for block in blocks if block and block.strip())
    chunks = parse_text_content(content) if content else []
    if course.courseware and (parser := COURSEWARE_PARSERS.get(Path(course.courseware.name).suffix.lower())):
        try:
            with course.courseware.open('rb') as file:
                chunks.extend(parser(file))
        except WorkbenchParseError:
            if not chunks:
                raise
    if not chunks:
        raise WorkbenchParseError('课程暂无可读取的字幕、课件、大纲或简介。')
    return MediaIngest(chunks, updates)


def ingest_external_video(source):
    data = source.metadata
    platform = data.get('platform', '')
    external_id = data.get('external_id', '')
    if (not isinstance(platform, str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,23}', platform)
            or not isinstance(external_id, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+', external_id)):
        raise WorkbenchParseError('外部视频缺少有效的平台或视频编号。')

    key = f'{platform}:{external_id}'
    if platform == 'bilibili':
        part = data.get('part', 1)
        if isinstance(part, bool) or not re.fullmatch(r'[1-9][0-9]{0,8}', str(part)):
            raise WorkbenchParseError('B 站视频分 P 编号必须是正整数。')
        key += f':p{part}'
    if len(key) > 200:
        raise WorkbenchParseError('外部视频编号过长。')

    url = data.get('url') or source.source_url
    try:
        parsed = urlsplit(url)
        if (len(url) > 3000 or parsed.scheme not in ('http', 'https') or not parsed.hostname
                or parsed.username is not None or parsed.password is not None):
            raise ValueError
        duration = float(data.get('duration_seconds', source.duration_seconds))
        if not math.isfinite(duration) or not 0 <= duration <= 2_147_483_647:
            raise ValueError
    except (TypeError, ValueError, OverflowError, AttributeError) as exc:
        raise WorkbenchParseError('外部视频链接或时长无效。') from exc

    raw_segments = data.get('segments', [])
    if not isinstance(raw_segments, list):
        raise WorkbenchParseError('外部视频字幕须为分段列表。')
    chunks = segments_to_timestamp_chunks(raw_segments)
    if not chunks:
        raise WorkbenchParseError('该外部视频暂无可用字幕，请提供带时间戳的字幕。')
    title = data.get('title') or source.title
    if not isinstance(title, str):
        raise WorkbenchParseError('外部视频标题须为文本。')
    return MediaIngest(chunks, {
        'external_key': key, 'source_url': url, 'title': title[:240], 'duration_seconds': math.ceil(duration),
    })


def uploaded_media_suffix(source):
    if not source.file or not source.file.name.startswith(f'{WORKBENCH_SOURCE_PREFIX}{source.user_id}/'):
        raise WorkbenchParseError('未找到当前账号上传的音视频文件。')
    suffix = Path(source.file.name).suffix.lower()
    if suffix not in MEDIA_FORMATS:
        raise WorkbenchParseError('请上传 MP4、MOV、WEBM、MP3、M4A 或 WAV 文件。')
    return suffix


def prepare_companion_course(source):
    """Link the private video before ASR. The source owns its storage object."""
    if uploaded_media_suffix(source) not in VIDEO_EXTENSIONS:
        return
    course = source.companion_course
    if course is not None and (not course.is_workbench_companion or course.author_id != source.user_id):
        raise WorkbenchParseError('视频关联的私有课程无效。')
    if course is None:
        course = Course(author_id=source.user_id, is_workbench_companion=True,
                        ai_outline_enabled=False, elo_reward=0)
    elif course.video_file.name != source.file.name:
        VideoTranscript.objects.filter(course=course).delete()
    course.title = source.title[:200]
    course.video_file = source.file.name
    course.save()
    source.companion_course = course
    source.metadata = {**source.metadata, 'is_private_companion': True}
    source.save(update_fields=['companion_course', 'metadata'])
    VideoTranscript.objects.update_or_create(
        course=course, defaults={'asr_status': 'processing', 'error_message': ''},
    )


def _transcribe_local(provider, file, suffix):
    with TemporaryDirectory(prefix='workbench_asr_') as directory:
        try:
            path = file.path
        except NotImplementedError:
            path = str(Path(directory) / f'input{suffix}')
            with file.open('rb') as original, open(path, 'wb') as local:
                shutil.copyfileobj(original, local)

        if isinstance(provider, (GLMChunkedASRProvider, VoskASRProvider)) or (
            suffix in VIDEO_EXTENSIONS and isinstance(provider, (MiMoASRProvider, OpenAIWhisperProvider))
        ):
            audio = str(Path(directory) / 'audio.wav')
            try:
                subprocess.run(
                    ['ffmpeg', '-nostdin', '-v', 'error', '-protocol_whitelist', 'file,pipe',
                     '-f', MEDIA_FORMATS[suffix], '-i', path, '-map', '0:a:0',
                     '-vn', '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1', audio],
                    check=True, timeout=300, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            except FileNotFoundError as exc:
                raise WorkbenchParseError('语音转录需要在处理服务上安装 ffmpeg。') from exc
            except subprocess.TimeoutExpired as exc:
                raise WorkbenchParseError('提取音轨超时，请缩短视频后重试。') from exc
            except subprocess.CalledProcessError as exc:
                raise WorkbenchParseError('无法提取音轨，请检查文件格式和音轨。') from exc
            path = audio
        return provider.transcribe(path)


def ingest_uploaded_media(source, *, asr_provider=None):
    suffix = uploaded_media_suffix(source)
    provider_name = type(asr_provider).__name__ if asr_provider is not None else settings.ASR_DEFAULT_PROVIDER
    try:
        provider = asr_provider if asr_provider is not None else ASRProviderRegistry.get_default_provider()
        if isinstance(provider, DummyASRProvider):
            raise WorkbenchParseError('语音转录服务尚未配置，请配置有效的 ASR 提供者后重试。')
        if asr_provider is None and isinstance(provider, (
            QwenFileTransASRProvider, GLMChunkedASRProvider, MiMoASRProvider, OpenAIWhisperProvider,
        )):
            key = provider.config.get('api_key', '').strip().lower()
            if key in {'', 'dummy', 'test', 'sk-xxx', 'your-api-key'}:
                raise WorkbenchParseError('语音转录服务缺少有效的 API 密钥，请配置后重试。')
        if getattr(provider, 'supports_url', False) is True:
            url = source.file.url
            if not url.startswith('https://'):
                raise WorkbenchParseError('当前 ASR 需要可访问的私有存储签名链接，请配置 OSS 或使用本地文件 ASR。')
            result = provider.transcribe_url(url)
        else:
            result = _transcribe_local(provider, source.file, suffix)
    except WorkbenchParseError:
        raise
    except Exception as exc:
        raise WorkbenchParseError('语音转录失败，请检查服务配置和文件后重试。') from exc

    segments = _normalize_segments([
        {'start_time': segment.start, 'end_time': segment.end, 'text': segment.text}
        for segment in result.segments
    ])
    if not segments:
        raise WorkbenchParseError('未识别到可用字幕，请检查音轨是否包含清晰语音。')
    return MediaIngest(_timestamp_chunks(segments), segments=segments,
                       language=result.language[:10], provider_name=provider_name[:50])


def save_companion_subtitles(source, result):
    if not source.companion_course_id or source.companion_course.video_file.name != source.file.name:
        return
    transcript, _ = VideoTranscript.objects.select_for_update().get_or_create(course_id=source.companion_course_id)
    transcript.language = result.language
    transcript.full_text = '\n'.join(segment['text'] for segment in result.segments)
    transcript.asr_provider = result.provider_name
    transcript.asr_status = 'completed'
    transcript.error_message = ''
    transcript.revision += 1
    transcript.save()
    transcript.segments.all().delete()
    TranscriptSegment.objects.bulk_create(
        [TranscriptSegment(transcript=transcript, index=index, **segment)
         for index, segment in enumerate(result.segments)],
        batch_size=1000,
    )
