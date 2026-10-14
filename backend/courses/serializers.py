from rest_framework import serializers
from .models import Course, CourseModule, Album, StartupMaterial, CourseTag, CourseTagRelation, VideoProgress


class CourseModuleSerializer(serializers.ModelSerializer):
    course_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = CourseModule
        fields = ('id', 'name', 'description', 'is_public', 'sort_order', 'course_count')
        validators = []

    def validate_name(self, value):
        institution_id = self.instance.institution_id if self.instance else self.context['request'].user.institution_id
        duplicates = CourseModule.objects.filter(institution_id=institution_id, name=value)
        if self.instance:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise serializers.ValidationError('当前机构已存在同名模块。')
        return value


class RelativeFileField(serializers.FileField):
    """文件先经过访问校验，再由媒体服务返回本地文件或 OSS 签名地址。"""
    def to_representation(self, value):
        if not value:
            return None
        from urllib.parse import quote
        return '/media/' + quote(value.name, safe='/')


class RelativeImageField(serializers.ImageField):
    def to_representation(self, value):
        if not value:
            return None
        url = value.url
        if url.startswith('http://') or url.startswith('https://'):
            return url
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
    module_name = serializers.CharField(source='module.name', read_only=True, default='')
    module_sort_order = serializers.IntegerField(source='module.sort_order', read_only=True, default=0)
    cover_image = RelativeImageField(required=False)
    video_file = RelativeFileField(required=False)
    courseware = RelativeFileField(required=False)
    reference_materials = RelativeFileField(required=False)

    album = AlbumSerializer(source='album_obj', read_only=True)
    album_obj = serializers.PrimaryKeyRelatedField(
        queryset=Album.objects.all(), required=False, allow_null=True, write_only=True
    )
    tags = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()

    def validate(self, attrs):
        module = attrs.get('module')
        if not self.instance and not module:
            raise serializers.ValidationError({'module': '请选择所属模块。'})
        if 'module' in attrs:
            if module is None:
                raise serializers.ValidationError({'module': '请选择所属模块。'})
            institution_id = self.instance.institution_id if self.instance else self.context['request'].user.institution_id
            if module.institution_id != institution_id:
                raise serializers.ValidationError({'module': '模块不属于当前课程所在机构。'})
        return attrs

    def get_tags(self, obj):
        relations = obj.tag_relations.select_related('tag').all()
        return CourseTagSerializer([r.tag for r in relations], many=True).data

    def get_progress(self, obj):
        """当前用户的观看进度；匿名或无记录返回 None"""
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None
        return VideoProgress.objects.filter(user=request.user, course_id=obj.id) \
            .values('last_position', 'is_finished').first()

    class Meta:
        model = Course
        fields = ('id', 'title', 'module', 'module_name', 'module_sort_order', 'album', 'album_obj', 'description', 'knowledge_point', 'cover_image', 'video_file', 'elo_reward', 'courseware', 'reference_materials', 'ai_outline_enabled', 'sort_order', 'institution', 'tags', 'progress', 'created_at', 'updated_at', 'author')
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
