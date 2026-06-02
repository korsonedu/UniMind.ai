from django.db.models import Q
from rest_framework.exceptions import PermissionDenied

from users.permissions import is_platform_admin


def apply_institution_filter(qs, user, request=None, institution_field='institution'):
    """按机构过滤查询集。平台管理员可通过 preview_institution 预览任意机构数据。"""
    preview_inst_id = None
    if request:
        preview_inst_id = request.query_params.get('preview_institution')
    if preview_inst_id:
        if not is_platform_admin(user):
            raise PermissionDenied("仅平台管理员可预览其他机构数据")
        return qs.filter(**{f'{institution_field}_id': preview_inst_id})
    if is_platform_admin(user):
        return qs
    inst = getattr(user, 'institution', None)
    if inst:
        return qs.filter(Q(**{institution_field: inst}) | Q(**{f'{institution_field}__isnull': True}))
    return qs.filter(**{f'{institution_field}__isnull': True})


