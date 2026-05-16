from rest_framework import serializers
from .models import Course, Album, StartupMaterial

class AlbumSerializer(serializers.ModelSerializer):
    class Meta:
        model = Album
        fields = ('id', 'name', 'description', 'cover_image', 'created_at')

class CourseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Course
        fields = ('id', 'title', 'album_obj', 'description', 'knowledge_point', 'cover_image', 'video_file', 'elo_reward', 'courseware', 'reference_materials', 'ai_outline_enabled', 'institution', 'created_at', 'updated_at', 'author')
        read_only_fields = ('author',)

class StartupMaterialSerializer(serializers.ModelSerializer):
    class Meta:
        model = StartupMaterial
        fields = ('id', 'name', 'description', 'file', 'created_at')
