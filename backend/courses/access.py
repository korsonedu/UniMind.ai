from core.utils import get_user_content_institution_id
from rest_framework.permissions import BasePermission

from .models import Course


def has_full_course_access(user):
    from users.workspaces.access import membership_for, workspace_active, active_course_ids
    member = membership_for(user)
    if member:
        return workspace_active(member) and (member.role == 'admin' or active_course_ids(member).exists())
    return False


class HasFullCourseAccess(BasePermission):
    message = '该功能仅向课程学员开放。'

    def has_permission(self, request, view):
        return has_full_course_access(request.user)


def visible_courses(request):
    """课程仅在所属机构空间中按成员授权开放。"""
    from users.workspaces.access import membership_for, active_course_ids
    member = membership_for(request.user)
    if member:
        return Course.objects.filter(is_published=True, pk__in=active_course_ids(member))
    return Course.objects.none()


def course_list_queryset(queryset, request):
    from django.db.models import Count, Prefetch, Q
    from .models import CourseTagRelation, VideoProgress

    relations = CourseTagRelation.objects.filter(
        tag__institution_id=get_user_content_institution_id(request.user),
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
