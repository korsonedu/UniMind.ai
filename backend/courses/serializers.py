from rest_framework import serializers
from .models import Course, Album, StartupMaterial


class RelativeFileField(serializers.FileField):
    """返回根相对 URL（以 / 开头），确保跨设备访问时资源 URL 正确"""
    def to_representation(self, value):
        if not value:
            return None
        url = value.url
        return url if url.startswith('/') else '/' + url


class RelativeImageField(serializers.ImageField):
    def to_representation(self, value):
        if not value:
            return None
        url = value.url
        return url if url.startswith('/') else '/' + url


class AlbumSerializer(serializers.ModelSerializer):
    cover_image = RelativeImageField(required=False)

    class Meta:
        model = Album
        fields = ('id', 'name', 'description', 'cover_image', 'created_at')


class CourseSerializer(serializers.ModelSerializer):
    cover_image = RelativeImageField(required=False)
    video_file = RelativeFileField(required=False)
    courseware = RelativeFileField(required=False)
    reference_materials = RelativeFileField(required=False)

    class Meta:
        model = Course
        fields = ('id', 'title', 'album_obj', 'description', 'knowledge_point', 'cover_image', 'video_file', 'elo_reward', 'courseware', 'reference_materials', 'ai_outline_enabled', 'institution', 'created_at', 'updated_at', 'author')
        read_only_fields = ('author',)

class StartupMaterialSerializer(serializers.ModelSerializer):
    file = RelativeFileField(required=False)

    class Meta:
        model = StartupMaterial
        fields = ('id', 'name', 'description', 'file', 'created_at')
