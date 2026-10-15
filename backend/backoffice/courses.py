from django.db.models import Count
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404
from rest_framework import serializers

from courses.models import Course, CourseModule, Album, LearningActivity
from courses.serializers import CourseModuleSerializer
from quizzes.models import KnowledgePoint
from .common import content_institution, managed, identity, paginate, delete_files_after_commit


class ModuleInput(CourseModuleSerializer):
    def validate(self, attrs):
        subject = attrs.get('subject', self.instance.subject if self.instance else '').strip()
        if not subject:
            raise serializers.ValidationError({'subject': '请填写所属学科。'})
        attrs['subject'] = subject
        name = attrs.get('name', self.instance.name if self.instance else '')
        queryset = managed(CourseModule.objects.filter(subject=subject, name=name))
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError({'name': '当前学科已存在同名模块。'})
        return attrs


class CourseInput(serializers.ModelSerializer):
    subject_name = serializers.CharField(source='module.subject', read_only=True, default='')
    module_name = serializers.CharField(source='module.name', read_only=True, default='')
    video_name = serializers.CharField(source='video_file.name', read_only=True, default='')
    cover_name = serializers.CharField(source='cover_image.name', read_only=True, default='')
    courseware_name = serializers.CharField(source='courseware.name', read_only=True, default='')
    reference_name = serializers.CharField(source='reference_materials.name', read_only=True, default='')

    class Meta:
        model = Course
        fields = ('id', 'title', 'module', 'module_name', 'subject_name', 'description', 'album_obj', 'knowledge_point',
                  'sort_order', 'elo_reward', 'ai_outline_enabled', 'updated_at',
                  'video_name', 'cover_name', 'courseware_name', 'reference_name')
        read_only_fields = ('updated_at',)

    def validate(self, attrs):
        module = attrs.get('module', self.instance.module if self.instance else None)
        if not module:
            raise serializers.ValidationError({'module': '请选择所属模块。'})
        scope = content_institution(required=True)
        if module.institution_id != (scope.pk if scope else None):
            raise serializers.ValidationError({'module': '模块不属于受管内容范围。'})
        if self.instance and self.instance.institution_id != module.institution_id:
            raise serializers.ValidationError({'module': '课程与模块须属于同一教学机构。'})
        for field in ('album_obj', 'knowledge_point'):
            value = attrs.get(field, getattr(self.instance, field, None))
            if value and value.institution_id != module.institution_id:
                raise serializers.ValidationError({field: '关联内容须属于同一教学机构。'})
        return attrs


def list_courses(request, data):
    queryset = managed(Course.objects.select_related('module')).order_by('sort_order', 'id')
    if data.get('search'):
        queryset = queryset.filter(title__icontains=str(data['search'])[:200])
    if data.get('module') == 'unassigned':
        queryset = queryset.filter(module__isnull=True)
    elif data.get('module'):
        queryset = queryset.filter(module_id=identity(data, 'module'))
    return paginate(queryset, data, lambda item: CourseInput(item).data)


def save_course(request, data):
    instance = get_object_or_404(managed(Course.objects.select_for_update()), pk=identity(data)) if data.get('id') else None
    serializer = CourseInput(instance, data=data, partial=bool(instance))
    serializer.is_valid(raise_exception=True)
    module = serializer.validated_data.get('module', instance.module if instance else None)
    if instance:
        course = serializer.save()
    else:
        from courses.views import _next_course_sort_order
        course = serializer.save(institution=module.institution, author=request.user,
                                 sort_order=serializer.validated_data.get('sort_order', _next_course_sort_order(module.institution)))
    return CourseInput(course).data


def delete_course(request, data):
    course = get_object_or_404(managed(Course.objects.select_for_update()), pk=identity(data))
    if course.progress_records.exists() or LearningActivity.objects.filter(course=course).exists():
        raise serializers.ValidationError('课程已有学习记录，不能直接删除。')
    try:
        # Bypass Course.delete(), which removes files before database protection checks.
        files = [course.video_file, course.cover_image, course.courseware, course.reference_materials]
        Course.objects.filter(pk=course.pk).delete()
        delete_files_after_commit(files)
    except ProtectedError:
        raise serializers.ValidationError('课程仍有业务引用，暂不能删除。')
    return {'id': data['id'], 'deleted': True}


def list_modules(request, data):
    queryset = managed(CourseModule.objects.annotate(course_count=Count('courses'))).order_by('sort_order', 'id')
    return {'items': CourseModuleSerializer(queryset, many=True).data}


def save_module(request, data):
    scope = content_institution(required=True)
    instance = get_object_or_404(managed(CourseModule.objects.select_for_update()), pk=identity(data)) if data.get('id') else None
    serializer = ModuleInput(instance, data=data, partial=bool(instance))
    serializer.is_valid(raise_exception=True)
    module = serializer.save(institution=scope)
    return CourseModuleSerializer(module).data


def delete_module(request, data):
    module = get_object_or_404(managed(CourseModule.objects.select_for_update()), pk=identity(data))
    if module.learning_products.exists():
        raise serializers.ValidationError('模块仍被学习服务引用，请先调整服务配置。')
    try:
        module.delete()
    except ProtectedError:
        raise serializers.ValidationError('请先将模块内课程迁至其他模块。')
    return {'id': data['id'], 'deleted': True}


def assign_courses(request, data):
    module = get_object_or_404(managed(CourseModule.objects.select_for_update()), pk=identity(data, 'module'))
    ids = set(serializers.ListField(child=serializers.IntegerField(min_value=1), allow_empty=False, max_length=500).run_validation(data.get('courses')))
    queryset = managed(Course.objects.select_for_update()).filter(pk__in=ids)
    selected = list(queryset)
    if len(selected) != len(ids) or any(item.institution_id != module.institution_id for item in selected):
        raise serializers.ValidationError('全部课程与目标模块须属于同一教学机构。')
    queryset.update(module=module)
    return {'id': module.pk, 'updated': len(ids)}


def options(request, data):
    def rows(model):
        return list(managed(model.objects.all()).order_by('id').values('id', 'name'))
    return {'albums': rows(Album), 'knowledge_points': rows(KnowledgePoint)}
