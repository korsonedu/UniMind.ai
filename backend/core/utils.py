from django.conf import settings
from rest_framework.exceptions import PermissionDenied


def get_content_institution_id(*, required=True):
    """单平台内容边界必须显式配置，不从操作者或历史机构猜测。"""
    value = getattr(settings, 'UNIMIND_CONTENT_INSTITUTION_ID', None)
    if value in (None, '') and not required:
        return None
    if value == 'global':
        return None
    try:
        if isinstance(value, bool) or int(value) < 1:
            raise ValueError
        return int(value)
    except (TypeError, ValueError):
        raise PermissionDenied('内容访问范围尚未配置，请联系管理员。')


def get_content_institution():
    from users.models import Institution
    institution_id = get_content_institution_id()
    if institution_id is None:
        return None
    institution = Institution.objects.filter(pk=institution_id, is_active=True).first()
    if institution is None:
        raise PermissionDenied('内容访问范围不可用，请联系管理员。')
    return institution


def apply_institution_filter(qs, user, request=None, institution_field='institution'):
    """机构字段暂作科晟内容归属；管理员也不能跨范围读取历史租户内容。"""
    from users.workspaces.access import membership_for, workspace_active, active_course_ids
    member = membership_for(user)
    if member:
        if not workspace_active(member):
            return qs.none()
        institution_id = member.workspace.institution_id
        if qs.model._meta.label_lower == 'courses.course':
            qs = qs.filter(pk__in=active_course_ids(member), is_published=True)
    else:
        institution_id = get_content_institution_id()
    if request:
        params = getattr(request, 'query_params', None)
        if params is None:
            params = request.GET
        preview_id = params.get('preview_institution')
        if preview_id and str(preview_id) != str(institution_id if institution_id is not None else 'global'):
            raise PermissionDenied('仅可访问已授权的内容范围。')
    return qs.filter(**{f'{institution_field}_id': institution_id})


def get_user_content_institution_id(user):
    from users.workspaces.access import membership_for
    member = membership_for(user)
    return member.workspace.institution_id if member else get_content_institution_id()
