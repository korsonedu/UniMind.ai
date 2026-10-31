from django.contrib.auth import get_user_model
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import serializers

from courses.models import CourseModule
from users.models import LearningProduct, LearningGrant, UserAccessProfile, StudentCohort
from users.feature_access import FEATURE_AREAS
from users.permissions import get_user_capabilities
from users.learning import grant_product, usage_info
from users.views_learning import LearningProductSerializer, LearningGrantSerializer
from .common import identity, paginate, managed


def person(user):
    from users.learning import is_course_student, cohort_info
    from users.permissions import is_platform_admin
    enabled = is_course_student(user)
    status = getattr(user, 'course_student_status', None)
    return {'id': user.pk, 'username': user.username, 'email': user.email, 'nickname': user.nickname,
            'is_active': user.is_active, 'email_verified': user.email_verified,
            'is_course_student': enabled, 'is_admin': is_platform_admin(user),
            'course_student_enabled': status.is_course_student if status else enabled,
            'cohort': cohort_info(user)}


def list_students(request, data):
    query = str(data.get('search', '')).strip()[:200]
    queryset = get_user_model().objects.order_by('-date_joined', '-id')
    if query:
        queryset = queryset.filter(Q(email__icontains=query) | Q(username__icontains=query) | Q(nickname__icontains=query))
    if data.get('cohort_id'):
        queryset = queryset.filter(course_student_status__cohort_id=serializers.IntegerField(min_value=1).run_validation(data['cohort_id']))
    return paginate(queryset, data, person)


def student_detail(request, data):
    user = get_object_or_404(get_user_model(), pk=identity(data))
    return {**person(user), 'ai_usage': usage_info(user),
            'feature_options': FEATURE_AREAS,
            'enabled_features': [area['key'] for area in FEATURE_AREAS if area['key'] in get_user_capabilities(user)],
            'grants': LearningGrantSerializer(user.learning_grants.select_related('user')[:100], many=True).data}


def save_access(request, data):
    user = get_object_or_404(get_user_model().objects.select_for_update(), pk=identity(data))
    keys = {area['key'] for area in FEATURE_AREAS}
    enabled = set(serializers.ListField(child=serializers.ChoiceField(choices=sorted(keys))).run_validation(data.get('enabled_features')))
    profile, _ = UserAccessProfile.objects.get_or_create(user=user)
    unrelated = set(profile.blocked_permissions or []) - keys
    profile.blocked_permissions = sorted(unrelated | (keys - enabled))
    profile.save(update_fields=['blocked_permissions'])
    return {'id': user.pk, 'enabled_features': sorted(enabled)}


def save_student_status(request, data):
    from django.core.cache import cache
    from users.learning import set_course_student_status, is_course_student, cohort_info
    user = get_object_or_404(get_user_model().objects.select_for_update(), pk=identity(data))
    if user.is_superuser:
        raise serializers.ValidationError('管理员身份不通过学员状态调整。')
    value = serializers.BooleanField().run_validation(data.get('is_course_student'))
    existing = getattr(user, 'course_student_status', None)
    changes = {}
    if 'cohort_id' in data:
        cohort = serializers.PrimaryKeyRelatedField(queryset=StudentCohort.objects.all(), allow_null=True).run_validation(data['cohort_id'])
        changes['cohort_id'] = cohort.pk if cohort else None
    if existing is not None and existing.is_course_student == value and (
            'cohort_id' not in changes or existing.cohort_id == changes['cohort_id']):
        request.backoffice_no_change = True
    else:
        set_course_student_status(user, value, actor=request.user, **changes)
    cache.delete(f'effective_plan:{user.pk}')
    cohort = cohort_info(user)
    return {'id': user.pk, 'is_course_student': is_course_student(user), 'course_student_enabled': value,
            'cohort': cohort, 'cohort_id': cohort['id'] if cohort else None}


class CohortInput(serializers.ModelSerializer):
    state = serializers.CharField(read_only=True)

    class Meta:
        model = StudentCohort
        fields = ('id', 'name', 'target_year', 'exam_date', 'starts_on', 'ends_on', 'is_active', 'state', 'updated_at')
        read_only_fields = ('id', 'state', 'updated_at')

    def validate(self, data):
        start = data.get('starts_on', getattr(self.instance, 'starts_on', None))
        end = data.get('ends_on', getattr(self.instance, 'ends_on', None))
        if start and end and end < start:
            raise serializers.ValidationError({'ends_on': '结束日期不能早于开始日期。'})
        return data


def list_cohorts(request, data):
    return {'items': CohortInput(StudentCohort.objects.all(), many=True).data}


def save_cohort(request, data):
    instance = get_object_or_404(StudentCohort.objects.select_for_update(), pk=identity(data)) if data.get('id') else None
    serializer = CohortInput(instance, data=data, partial=bool(instance))
    serializer.is_valid(raise_exception=True)
    return CohortInput(serializer.save()).data


class ProductInput(LearningProductSerializer):
    def validate_modules(self, value):
        allowed = set(managed(CourseModule.objects.all()).values_list('pk', flat=True))
        if any(module.pk not in allowed for module in value):
            raise serializers.ValidationError('包含受管范围以外的模块。')
        return value


def list_products(request, data):
    return {'items': LearningProductSerializer(LearningProduct.objects.prefetch_related('modules'), many=True).data}


def save_product(request, data):
    instance = get_object_or_404(LearningProduct.objects.select_for_update(), pk=identity(data)) if data.get('id') else None
    serializer = ProductInput(instance, data=data, partial=bool(instance))
    serializer.is_valid(raise_exception=True)
    return LearningProductSerializer(serializer.save()).data


def create_grant(request, data):
    class Input(serializers.Serializer):
        user = serializers.IntegerField(min_value=1)
        product = serializers.PrimaryKeyRelatedField(queryset=LearningProduct.objects.all())
        source = serializers.ChoiceField(choices=['course', 'admin'])
        request_id = serializers.UUIDField()
    payload = Input(data=data)
    payload.is_valid(raise_exception=True)
    values = payload.validated_data
    user = get_object_or_404(get_user_model().objects.select_for_update(), pk=values['user'], is_active=True, email_verified=True)
    existing = LearningGrant.objects.filter(request_id=values['request_id']).first()
    if existing:
        if (existing.user_id, existing.product_id, existing.source) != (user.pk, values['product'].pk, values['source']):
            raise serializers.ValidationError('该请求编号已用于其他发放操作。')
        request.backoffice_no_change = True
        return LearningGrantSerializer(existing).data
    grant = grant_product(user, values['product'], source=values['source'])
    grant.request_id = values['request_id']
    grant.save(update_fields=['request_id'])
    return LearningGrantSerializer(grant).data


def revoke_grant(request, data):
    grant = get_object_or_404(LearningGrant.objects.select_for_update().select_related('user'), pk=identity(data))
    if grant.revoked:
        request.backoffice_no_change = True
    else:
        grant.revoked = True
        grant.save(update_fields=['revoked'])
    return LearningGrantSerializer(grant).data
