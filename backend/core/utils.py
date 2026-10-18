from django.conf import settings
from rest_framework.exceptions import PermissionDenied


def get_content_institution_id():
    """单平台内容边界必须显式配置，不从操作者或历史机构猜测。"""
    value = getattr(settings, 'UNIMIND_CONTENT_INSTITUTION_ID', None)
    if value == 'global':
        return None
    try:
        if isinstance(value, bool) or int(value) < 1:
            raise ValueError
        return int(value)
    except (TypeError, ValueError):
        raise PermissionDenied('科晟内容范围尚未配置，请联系管理员。')


def get_content_institution():
    from users.models import Institution
    institution_id = get_content_institution_id()
    if institution_id is None:
        return None
    institution = Institution.objects.filter(pk=institution_id, is_active=True).first()
    if institution is None:
        raise PermissionDenied('科晟内容范围不可用，请联系管理员。')
    return institution


def apply_institution_filter(qs, user, request=None, institution_field='institution'):
    """机构字段暂作科晟内容归属；管理员也不能跨范围读取历史租户内容。"""
    institution_id = get_content_institution_id()
    if request:
        params = getattr(request, 'query_params', None)
        if params is None:
            params = request.GET
        preview_id = params.get('preview_institution')
        if preview_id and str(preview_id) != str(institution_id if institution_id is not None else 'global'):
            raise PermissionDenied('仅可访问科晟内容范围。')
    return qs.filter(**{f'{institution_field}_id': institution_id})
