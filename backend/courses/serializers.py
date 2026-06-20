from rest_framework import serializers
from .models import Course, Album, StartupMaterial, CourseTag, CourseTagRelation


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


class AlbumCourseBriefSerializer(serializers.ModelSerializer):
    cover_image = RelativeImageField(required=False)

    class Meta:
        model = Course
        fields = ('id', 'title', 'cover_image')


class AlbumSerializer(serializers.ModelSerializer):
    cover_image = RelativeImageField(required=False)
    course_count = serializers.IntegerField(read_only=True, required=False)
    courses = AlbumCourseBriefSerializer(many=True, read_only=True)

    class Meta:
        model = Album
        fields = ('id', 'name', 'description', 'cover_image', 'created_at', 'course_count', 'courses')


class CourseSerializer(serializers.ModelSerializer):
    cover_image = RelativeImageField(required=False)
    video_file = RelativeFileField(required=False)
    courseware = RelativeFileField(required=False)
    reference_materials = RelativeFileField(required=False)

    album = AlbumSerializer(source='album_obj', read_only=True)
    album_obj = serializers.PrimaryKeyRelatedField(
        queryset=Album.objects.all(), required=False, allow_null=True, write_only=True
    )
    tags = serializers.SerializerMethodField()

    def get_tags(self, obj):
        relations = obj.tag_relations.select_related('tag').all()
        return CourseTagSerializer([r.tag for r in relations], many=True).data

    class Meta:
        model = Course
        fields = ('id', 'title', 'album', 'album_obj', 'description', 'knowledge_point', 'cover_image', 'video_file', 'elo_reward', 'courseware', 'reference_materials', 'ai_outline_enabled', 'sort_order', 'institution', 'tags', 'created_at', 'updated_at', 'author')
        read_only_fields = ('author', 'institution')

class StartupMaterialSerializer(serializers.ModelSerializer):
    file = RelativeFileField(required=False)

    class Meta:
        model = StartupMaterial
        fields = ('id', 'name', 'description', 'file', 'created_at')


class CourseTagSerializer(serializers.ModelSerializer):
    course_count = serializers.SerializerMethodField()
    courses = serializers.SerializerMethodField()

    class Meta:
        model = CourseTag
        fields = ('id', 'name', 'slug', 'course_count', 'courses', 'created_at')
        read_only_fields = ('slug', 'created_at')

    def get_course_count(self, obj):
        return getattr(obj, 'course_count', obj.course_relations.count())

    def get_courses(self, obj):
        course_ids = obj.course_relations.values_list('course_id', flat=True)
        courses = Course.objects.filter(id__in=course_ids).only('id', 'title', 'cover_image')
        return AlbumCourseBriefSerializer(courses, many=True).data


# ── Teaching Plan & Lesson Plan ──

from courses.models import TeachingPlan, LessonPlan


class LessonPlanSerializer(serializers.ModelSerializer):
    knowledge_point_names = serializers.SerializerMethodField()

    class Meta:
        model = LessonPlan
        fields = [
            'id', 'teaching_plan', 'title', 'objectives', 'knowledge_points',
            'knowledge_point_names', 'activities', 'materials', 'ai_generated',
            'duration_minutes', 'week_number', 'order', 'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at', 'institution', 'created_by']

    def get_knowledge_point_names(self, obj):
        return list(obj.knowledge_points.values_list('name', flat=True))


class TeachingPlanSerializer(serializers.ModelSerializer):
    lesson_plans = LessonPlanSerializer(many=True, read_only=True)
    class_name = serializers.SerializerMethodField()

    class Meta:
        model = TeachingPlan
        fields = [
            'id', 'institution', 'class_obj', 'class_name', 'title', 'description',
            'subject', 'semester', 'week_count', 'weekly_plans', 'lesson_plans',
            'created_by', 'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at', 'institution', 'created_by']

    def get_class_name(self, obj):
        return obj.class_obj.name
