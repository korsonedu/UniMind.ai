from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied
from users.models_workspace import WorkspaceMembership


def membership_for(user):
    if not user or not user.is_authenticated or not user.is_active:
        return None
    if not isinstance(user, get_user_model()) or not user.pk:
        return None
    return WorkspaceMembership.objects.select_related('workspace__institution').filter(user=user, is_current=True).first()


def workspace_active(member):
    return bool(member and member.is_active and member.workspace.is_active
                and member.workspace.institution.is_active
                and member.workspace.service_ends_on >= timezone.localdate())


def active_course_ids(member):
    from courses.models import Course
    if not workspace_active(member):
        return Course.objects.none().values_list('pk', flat=True)
    courses = Course.objects.filter(workspace_content__workspace=member.workspace)
    if member.role != 'admin':
        courses = courses.filter(workspace_enrollments__membership=member,
                                 workspace_enrollments__service_ends_on__gte=timezone.localdate())
    return courses.values_list('pk', flat=True).distinct()


def require_admin(user):
    member = membership_for(user)
    if not workspace_active(member) or member.role != 'admin':
        raise PermissionDenied('仅机构 workspace 管理员可以执行此操作。')
    return member
