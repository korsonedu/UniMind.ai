from core.utils import apply_institution_filter, get_content_institution_id, get_user_content_institution_id
from django.db.models import Exists, OuterRef
from rest_framework.permissions import BasePermission
from users.permissions import IsMember

from .models import Course


def has_full_course_access(user):
    from users.learning import is_course_student
    from users.workspaces.access import membership_for, workspace_active, active_course_ids
    member = membership_for(user)
    if member:
        return workspace_active(member) and (member.role == 'admin' or active_course_ids(member).exists())
    from users.permissions import is_platform_admin
    return bool(user and user.is_authenticated and user.is_active and
                (is_platform_admin(user) or is_course_student(user)))


class HasFullCourseAccess(BasePermission):
    message = '该功能仅向课程学员开放。'

    def has_permission(self, request, view):
        return has_full_course_access(request.user)


def visible_courses(request):
    return visible_courses_for(request.user, request)


def visible_courses_for(user, request=None):
    """课程学员可读本平台全课，注册学生仅可读明确开放的模块。"""
    from users.workspaces.access import membership_for, active_course_ids
    member = membership_for(user)
    if member:
        return Course.objects.filter(is_published=True, pk__in=active_course_ids(member))
    courses = apply_institution_filter(Course.objects.filter(is_published=True), user, request).filter(
        workspace_content__isnull=True, institution__learning_workspace__isnull=True)
    if not has_full_course_access(user):
        courses = courses.filter(module__is_public=True, module__institution_id=get_content_institution_id())
    return courses


def private_companion_courses(user, project_id=None):
    if not user.is_authenticated or not user.is_active:
        return Course.objects.none()
    from ai_assistant.models import ProjectSource
    sources = ProjectSource.objects.filter(
        companion_course_id=OuterRef('pk'), file=OuterRef('video_file'),
        user=user, project__user=user, source_type=ProjectSource.Type.UPLOADED_MEDIA,
    )
    if project_id is not None:
        sources = sources.filter(project_id=project_id)
    return Course.objects.filter(is_workbench_companion=True, is_published=False, author=user).filter(Exists(sources))


def project_station_courses(request, project_id, course_id):
    from ai_assistant.models import ProjectSource
    if not ProjectSource.objects.filter(
        project_id=project_id, project__user=request.user, user=request.user,
        source_type=ProjectSource.Type.COURSE, course_id=course_id,
    ).exists():
        return Course.objects.none()
    return visible_courses(request).filter(pk=course_id)


class CanReadCourse(IsMember):
    def has_permission(self, request, view):
        return super().has_permission(request, view) or (
            request.method in ('GET', 'HEAD')
            and private_companion_courses(request.user).filter(pk=view.kwargs['pk']).exists()
        )


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
