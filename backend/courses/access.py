from core.utils import apply_institution_filter, get_content_institution_id
from rest_framework.permissions import BasePermission

from .models import Course


def has_full_course_access(user):
    from users.learning import is_course_student
    from users.permissions import is_platform_admin
    return bool(user and user.is_authenticated and user.is_active and
                (is_platform_admin(user) or is_course_student(user)))


class HasFullCourseAccess(BasePermission):
    message = '该功能仅向课程学员开放。'

    def has_permission(self, request, view):
        return has_full_course_access(request.user)


def visible_courses(request):
    """课程学员可读本平台全课，注册学生仅可读明确开放的模块。"""
    courses = apply_institution_filter(Course.objects.all(), request.user, request)
    if not has_full_course_access(request.user):
        courses = courses.filter(module__is_public=True, module__institution_id=get_content_institution_id())
    return courses


def course_list_queryset(queryset, request):
    from django.db.models import Count, Prefetch, Q
    from .models import CourseTagRelation, VideoProgress

    relations = CourseTagRelation.objects.filter(
        tag__institution_id=get_content_institution_id(),
    ).select_related('tag').annotate(
        tag_course_count=Count('tag__course_relations', filter=Q(
            tag__course_relations__course__in=visible_courses(request),
        )),
    )
    return queryset.select_related('module', 'album_obj').prefetch_related(
        Prefetch('tag_relations', queryset=relations, to_attr='serialized_tag_relations'),
        Prefetch('progress_records', queryset=VideoProgress.objects.filter(user=request.user),
                 to_attr='serialized_progress'),
    )
