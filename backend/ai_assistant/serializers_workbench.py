import math
from pathlib import Path
from urllib.parse import urlsplit

from django.urls import reverse
from rest_framework import serializers

from .models import ProjectSource, ProjectSourceChunk
from .services.workbench_media import external_video_key
from .services.workbench_parsers import WorkbenchParseError


UPLOAD_FORMATS = {
    '.pdf': (ProjectSource.Type.PDF, 'application/pdf'),
    '.pptx': (ProjectSource.Type.PPTX, 'application/vnd.openxmlformats-officedocument.presentationml.presentation'),
    '.docx': (ProjectSource.Type.DOCX, 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'),
    '.md': (ProjectSource.Type.TEXT, 'text/markdown'),
    '.txt': (ProjectSource.Type.TEXT, 'text/plain'),
    '.mp4': (ProjectSource.Type.UPLOADED_MEDIA, 'video/mp4'),
    '.mov': (ProjectSource.Type.UPLOADED_MEDIA, 'video/quicktime'),
    '.webm': (ProjectSource.Type.UPLOADED_MEDIA, 'video/webm'),
    '.mp3': (ProjectSource.Type.UPLOADED_MEDIA, 'audio/mpeg'),
    '.m4a': (ProjectSource.Type.UPLOADED_MEDIA, 'audio/mp4'),
    '.wav': (ProjectSource.Type.UPLOADED_MEDIA, 'audio/wav'),
}


class ProjectSourceChunkSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectSourceChunk
        fields = (
            'id', 'chunk_index', 'anchor_type', 'locator_label', 'heading', 'content',
            'page_number', 'slide_number', 'start_seconds', 'end_seconds', 'token_estimate', 'metadata',
        )
        read_only_fields = fields


class ProjectSourceSummarySerializer(serializers.ModelSerializer):
    file_preview_url = serializers.SerializerMethodField()
    companion_play_url = serializers.SerializerMethodField()

    class Meta:
        model = ProjectSource
        fields = (
            'id', 'project_id', 'source_type', 'title', 'mime_type', 'file_size', 'source_url',
            'course_id', 'companion_course_id', 'external_key', 'status', 'error_message',
            'is_selected', 'summary', 'unit_count', 'word_count', 'duration_seconds', 'metadata',
            'file_preview_url', 'companion_play_url', 'created_at', 'updated_at',
        )
        read_only_fields = fields

    def get_file_preview_url(self, source):
        if source.file:
            return reverse('project-source-file', kwargs={'pk': source.project_id, 'source_id': source.pk})
        return None

    def get_companion_play_url(self, source):
        if source.source_type == ProjectSource.Type.EXTERNAL_VIDEO:
            return source.source_url or None
        course_id = source.companion_course_id or source.course_id
        if course_id:
            return f'/course/{course_id}?project={source.project_id}'
        return None


class ProjectSourceDetailSerializer(ProjectSourceSummarySerializer):
    chunks = ProjectSourceChunkSerializer(many=True, read_only=True)

    class Meta(ProjectSourceSummarySerializer.Meta):
        fields = (*ProjectSourceSummarySerializer.Meta.fields, 'chunks')
        read_only_fields = fields


class ProjectSourceUploadSerializer(serializers.Serializer):
    files = serializers.ListField(
        child=serializers.FileField(allow_empty_file=False, error_messages={
            'empty': '请上传非空文件。', 'invalid': '请上传有效文件。',
        }),
        allow_empty=False, error_messages={'empty': '请至少上传一个文件。'},
    )

    def validate_files(self, files):
        for file in files:
            format_info = UPLOAD_FORMATS.get(Path(file.name).suffix.lower())
            if format_info is None:
                raise serializers.ValidationError(f'文件「{file.name}」的格式不受支持。')
            source_type, _ = format_info
            limit_mb = 500 if source_type == ProjectSource.Type.UPLOADED_MEDIA else 50
            if file.size > limit_mb * 1024 * 1024:
                raise serializers.ValidationError(f'文件「{file.name}」不能超过 {limit_mb} MB。')
        return files


class SourceURLField(serializers.URLField):
    def run_validators(self, value):
        super().run_validators(value)
        parts = urlsplit(value)
        if parts.scheme not in ('http', 'https') or parts.username is not None or parts.password is not None:
            raise serializers.ValidationError('请输入不含账号密码的 HTTP 或 HTTPS 链接。')


class VideoSegmentSerializer(serializers.Serializer):
    start_time = serializers.FloatField(min_value=0, max_value=2_147_483_647)
    end_time = serializers.FloatField(min_value=0, max_value=2_147_483_647)
    text = serializers.CharField()

    def validate(self, attrs):
        if not 0 <= attrs['start_time'] <= attrs['end_time'] <= 2_147_483_647:
            raise serializers.ValidationError('字幕时间无效，请检查起止时间。')
        return attrs


class ProjectSourceImportSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=('web_url', 'course', 'external_video', 'text'))
    title = serializers.CharField(max_length=240, required=False)
    url = SourceURLField(max_length=3000, required=False)
    course_id = serializers.IntegerField(min_value=1, required=False)
    platform = serializers.ChoiceField(choices=('bilibili', 'youtube', 'generic'), required=False)
    external_id = serializers.CharField(max_length=200, required=False)
    part = serializers.IntegerField(min_value=1, max_value=999_999_999, required=False)
    duration_seconds = serializers.FloatField(min_value=0, max_value=2_147_483_647, required=False)
    segments = VideoSegmentSerializer(many=True, allow_empty=False, required=False)
    content = serializers.CharField(max_length=512_000, required=False)
    source_url = SourceURLField(max_length=3000, allow_blank=True, required=False)

    def validate(self, attrs):
        kind = attrs['kind']
        required = {
            'web_url': ('url',),
            'course': ('course_id',),
            'external_video': ('platform', 'external_id', 'url', 'title', 'segments'),
            'text': ('title', 'content'),
        }
        missing = {field: '此项为必填项。' for field in required[kind] if field not in attrs}
        if missing:
            raise serializers.ValidationError(missing)
        if kind == 'web_url' and urlsplit(attrs['url']).scheme != 'https':
            raise serializers.ValidationError({'url': '请输入公开的 HTTPS 网页链接。'})
        if kind == 'external_video':
            attrs.setdefault('part', 1)
            attrs.setdefault('duration_seconds', 0)
            if not math.isfinite(attrs['duration_seconds']):
                raise serializers.ValidationError({'duration_seconds': '视频时长无效。'})
            try:
                attrs['external_key'] = external_video_key(attrs['platform'], attrs['external_id'], attrs['part'])
            except WorkbenchParseError as exc:
                raise serializers.ValidationError({'external_id': str(exc)}) from exc
        return attrs


class ProjectSourcePatchSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=240, required=False)
    is_selected = serializers.BooleanField(required=False)
    action = serializers.ChoiceField(choices=('retry',), required=False)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError('请提供要修改的字段或重试操作。')
        return attrs


class ProjectSourceBatchSelectSerializer(serializers.Serializer):
    is_selected = serializers.BooleanField()
    source_ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=False, required=False)
    select_all = serializers.BooleanField(required=False)

    def validate(self, attrs):
        if 'select_all' in attrs and attrs['select_all'] == ('source_ids' in attrs):
            raise serializers.ValidationError('请选择全部来源或提供来源编号列表。')
        return attrs
