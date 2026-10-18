from rest_framework import serializers
from core.utils import apply_institution_filter, get_content_institution, get_content_institution_id
from .models import Course, CourseModule, Album, StartupMaterial, CourseTag, CourseTagRelation, VideoProgress


class CourseModuleSerializer(serializers.ModelSerializer):
    course_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = CourseModule
        fields = ('id', 'name', 'subject', 'description', 'is_public', 'sort_order', 'course_count')
        validators = []

    def validate(self, attrs):
        institution = get_content_institution()
        institution_id = institution.pk if institution else None
        subject = attrs.get('subject', self.instance.subject if self.instance else '').strip()
        name = attrs.get('name', self.instance.name if self.instance else '')
        if not subject:
            raise serializers.ValidationError({'subject': '请填写所属学科。'})
        attrs['subject'] = subject
        duplicates = CourseModule.objects.filter(institution_id=institution_id, subject=subject, name=name)
        if self.instance:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise serializers.ValidationError({'name': '当前学科已存在同名模块。'})
        return attrs


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
    courses = serializers.SerializerMethodField()

    def get_courses(self, obj):
        if self.context.get('course_list_summary'):
            return []
        institution_id = get_content_institution_id()
        courses = [course for course in obj.courses.all() if course.institution_id == institution_id]
        return AlbumCourseBriefSerializer(courses, many=True, context=self.context).data

    class Meta:
        model = Album
        fields = ('id', 'name', 'description', 'cover_image', 'created_at', 'course_count', 'courses')


class CourseSerializer(serializers.ModelSerializer):
    subject_name = serializers.SerializerMethodField()
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

    def get_subject_name(self, obj):
        if obj.module_id and obj.module.subject:
            return obj.module.subject
        if not obj.knowledge_point_id:
            return ''
        from quizzes.models import KnowledgePoint
        from .classification import legacy_subject
        if '_legacy_subject_points' not in self.context:
            self.context['_legacy_subject_points'] = {point['id']: point for point in KnowledgePoint.objects.values('id', 'name', 'subject', 'parent_id')}
        return legacy_subject(self.context['_legacy_subject_points'], obj.knowledge_point_id)

    def validate(self, attrs):
        institution = get_content_institution()
        institution_id = institution.pk if institution else None
        module = attrs.get('module')
        if not self.instance and not module:
            raise serializers.ValidationError({'module': '请选择所属模块。'})
        if 'module' in attrs:
            if module is None:
                raise serializers.ValidationError({'module': '请选择所属模块。'})
            if module.institution_id != institution_id:
                raise serializers.ValidationError({'module': '模块不属于当前课程所在机构。'})
        for field in ('album_obj', 'knowledge_point'):
            value = attrs.get(field)
            if value and value.institution_id != institution_id:
                raise serializers.ValidationError({field: '所选内容不属于当前内容范围。'})
        return attrs

    def get_tags(self, obj):
        relations = getattr(obj, 'serialized_tag_relations', None)
        if relations is None:
            relations = obj.tag_relations.filter(tag__institution_id=get_content_institution_id()).select_related('tag')
        tags = []
        for relation in relations:
            if hasattr(relation, 'tag_course_count'):
                relation.tag.course_count = relation.tag_course_count
            tags.append(relation.tag)
        return CourseTagSerializer(tags, many=True, context=self.context).data

    def get_progress(self, obj):
        """当前用户的观看进度；匿名或无记录返回 None"""
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None
        if hasattr(obj, 'serialized_progress'):
            progress = obj.serialized_progress
            return {'last_position': progress[0].last_position, 'is_finished': progress[0].is_finished} if progress else None
        return VideoProgress.objects.filter(user=request.user, course_id=obj.id) \
            .values('last_position', 'is_finished').first()

    class Meta:
        model = Course
        fields = ('id', 'title', 'module', 'module_name', 'module_sort_order', 'subject_name', 'album', 'album_obj', 'description', 'knowledge_point', 'cover_image', 'video_file', 'elo_reward', 'courseware', 'reference_materials', 'ai_outline_enabled', 'sort_order', 'institution', 'tags', 'progress', 'created_at', 'updated_at', 'author')
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
        count = getattr(obj, 'course_count', None)
        return count if count is not None else obj.course_relations.filter(course__institution_id=get_content_institution_id()).count()

    def get_courses(self, obj):
        if self.context.get('course_list_summary'):
            return []
        course_ids = obj.course_relations.values_list('course_id', flat=True)
        courses = apply_institution_filter(Course.objects.filter(id__in=course_ids), None).only('id', 'title', 'cover_image')
        return AlbumCourseBriefSerializer(courses, many=True).data
