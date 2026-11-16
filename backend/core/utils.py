from django.conf import settings
from rest_framework.exceptions import PermissionDenied


def get_content_institution_id(user=None):
    """Resolve the selected learning identity, otherwise the public partition."""
    if user is not None:
        from users.workspaces.access import membership_for
        member = membership_for(user)
        if member:
            return member.workspace.institution_id

    value = getattr(settings, 'UNIMIND_CONTENT_INSTITUTION_ID', None)
    if value == 'global':
        return None
    try:
        if isinstance(value, bool) or int(value) < 1:
            raise ValueError
        institution_id = int(value)
        if user is not None:
            from users.models_workspace import Workspace
            if Workspace.objects.filter(institution_id=institution_id).exists():
                return None
        return institution_id
    except (TypeError, ValueError):
        raise PermissionDenied('内容访问范围尚未配置，请联系管理员。')


def get_content_institution(user=None):
    from users.models import Institution
    institution_id = get_content_institution_id(user)
    if institution_id is None:
        return None
    institution = Institution.objects.filter(pk=institution_id, is_active=True).first()
    if institution is None:
        raise PermissionDenied('内容访问范围不可用，请联系管理员。')
    return institution


def apply_institution_filter(qs, user, request=None, institution_field='institution'):
    """Shared content follows the current space, including for administrators."""
    from users.workspaces.access import membership_for, workspace_active, active_course_ids
    member = membership_for(user)
    if member:
        if not workspace_active(member):
            return qs.none()
        institution_id = member.workspace.institution_id
        if qs.model._meta.label_lower == 'courses.course':
            qs = qs.filter(pk__in=active_course_ids(member), is_published=True)
    else:
        institution_id = get_content_institution_id(user)
    if request:
        params = getattr(request, 'query_params', None)
        if params is None:
            params = request.GET
        preview_id = params.get('preview_institution')
        if preview_id and str(preview_id) != str(institution_id if institution_id is not None else 'global'):
            raise PermissionDenied('仅可访问已授权的内容范围。')
    if qs.model._meta.label_lower == 'users.user':
        return qs.filter(workspace_learner__workspace=member.workspace) if member else qs.filter(workspace_learner__isnull=True)
    return qs.filter(**{f'{institution_field}_id': institution_id})


def get_user_content_institution_id(user):
    from users.workspaces.access import membership_for
    member = membership_for(user)
    return member.workspace.institution_id if member else get_content_institution_id(user)
