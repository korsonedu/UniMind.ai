import logging
from rest_framework import permissions

logger = logging.getLogger(__name__)

# Permission point constants
CAP_LEARNING_ACCESS = "learning.access"
CAP_MEMBER_ACCESS = "member.access"
CAP_ADMIN_PANEL = "admin.panel"
CAP_CONTENT_MANAGE = "content.manage"
CAP_USERS_MANAGE = "users.manage"
CAP_SYSTEM_MANAGE = "system.manage"

ADMIN_CAPABILITIES = [
    CAP_ADMIN_PANEL,
    CAP_CONTENT_MANAGE,
    CAP_USERS_MANAGE,
    CAP_SYSTEM_MANAGE,
]

# Frontend/backed can share this matrix payload as single source of truth.
ROLE_PERMISSION_MATRIX = {
    "student": [CAP_LEARNING_ACCESS],
    "member": [CAP_LEARNING_ACCESS, CAP_MEMBER_ACCESS],
    "admin": [CAP_LEARNING_ACCESS, CAP_MEMBER_ACCESS, *ADMIN_CAPABILITIES],
}


def is_platform_admin(user) -> bool:
    """超级管理员：is_superuser 即为平台管理员。"""
    return bool(
        user
        and user.is_authenticated
        and getattr(user, "is_superuser", False)
    )


def is_institution_admin(user) -> bool:
    """机构管理员：owner 或 teacher。"""
    return bool(
        user
        and user.is_authenticated
        and user.institution is not None
        and user.institution_role in ('owner', 'teacher')
    )


def is_member_or_admin(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    if is_platform_admin(user) or is_institution_admin(user):
        return True
    if not getattr(user, "is_member", False):
        return False
    from django.utils import timezone
    now = timezone.now()
    if getattr(user, 'membership_expires_at', None) and user.membership_expires_at < now:
        return False
    return True


def get_user_capabilities(user) -> list[str]:
    if not user or not user.is_authenticated:
        return []

    caps = [CAP_LEARNING_ACCESS]
    if getattr(user, "is_member", False) or is_platform_admin(user) or is_institution_admin(user):
        caps.append(CAP_MEMBER_ACCESS)
    if is_platform_admin(user):
        caps.extend(ADMIN_CAPABILITIES)

    # Superuser 人员管理扩展：读取用户访问档案中的权限组与自定义权限。
    profile = getattr(user, "access_profile", None)
    if profile:
        try:
            for group in profile.permission_groups.filter(is_active=True):
                for cap in (group.permissions or []):
                    cap_str = str(cap).strip()
                    if cap_str:
                        caps.append(cap_str)
        except Exception:
            logger.exception("加载权限组失败: user=%s", user.id)

        for cap in (profile.extra_permissions or []):
            cap_str = str(cap).strip()
            if cap_str:
                caps.append(cap_str)

        blocked = {str(cap).strip() for cap in (profile.blocked_permissions or []) if str(cap).strip()}
    else:
        blocked = set()

    seen = set()
    deduped = []
    for cap in caps:
        if cap not in seen:
            deduped.append(cap)
            seen.add(cap)
    if blocked:
        deduped = [cap for cap in deduped if cap not in blocked]
    return deduped


def has_capability(user, capability: str) -> bool:
    return capability in get_user_capabilities(user)


class IsPlatformAdmin(permissions.BasePermission):
    message = "需要管理员权限。"

    def has_permission(self, request, view):
        return is_platform_admin(request.user)


class IsAdmin(permissions.BasePermission):
    """超级管理员或机构管理员（owner / teacher）"""
    message = "需要管理员权限。"

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if is_platform_admin(user):
            return True
        return (user.institution is not None and user.institution_role in ('owner', 'teacher'))


class IsMember(permissions.BasePermission):
    message = "您需要先成为学员（激活会员）才能使用此功能。"

    def has_permission(self, request, view):
        return is_member_or_admin(request.user)


class IsMemberOrReadOnlyList(permissions.BasePermission):
    """非会员可读列表接口（逛逛模式），写操作需要会员权限。"""

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated
        return is_member_or_admin(request.user)


class IsAdminWriteMemberRead(permissions.BasePermission):
    """
    SAFE 方法：会员或管理员可读。
    写方法：平台管理员或机构管理员可写。
    """
    message = "权限不足。"

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return is_member_or_admin(request.user)
        return is_platform_admin(request.user) or is_institution_admin(request.user)


class IsInstitutionAdmin(permissions.BasePermission):
    """机构管理员权限（owner 或 teacher）"""
    message = "需要机构管理员权限。"

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        # 平台管理员预览模式：直接放行
        if request.query_params.get('preview_institution') and is_platform_admin(user):
            return True
        return (user.institution is not None
                and user.institution_role in ('owner', 'teacher'))


class IsInstitutionOwner(permissions.BasePermission):
    """机构所有者权限（仅 owner，teacher 不可）"""
    message = "仅机构所有者可执行此操作。"

    def has_permission(self, request, view):
        user = request.user
        return (user and user.is_authenticated
                and user.institution is not None
                and user.institution_role == 'owner')


class IsInstitutionActive(permissions.BasePermission):
    """所在机构有效（已启用 + 版本未到期）"""
    message = "机构服务已到期或已停用，请联系管理员。"

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if is_platform_admin(user):
            return True
        inst = user.institution
        if inst is None:
            return False
        return inst.is_active and inst.is_plan_active


class HasPlanFeature(permissions.BasePermission):
    """
    检查用户所在机构是否具备指定功能。
    用法: permission_classes = [HasPlanFeature]; required_feature = 'ai.generate'
    """
    message = "当前版本不支持此功能，请升级。"

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if is_platform_admin(user):
            return True
        required = getattr(view, 'required_feature', None)
        if required is None:
            return True
        from users.models import has_plan_feature
        return has_plan_feature(user.institution, required)


class IsInstitutionMember(permissions.BasePermission):
    """属于某个机构的成员"""
    message = "需要机构成员身份。"

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        # 平台管理员预览模式：直接放行
        if request.query_params.get('preview_institution') and is_platform_admin(user):
            return True
        return user.institution is not None


class HasQuota(permissions.BasePermission):
    """
    通用配额检查。
    usage: permission_classes = [HasQuota]
           quota_resource = 'course'
    """
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if is_platform_admin(user) or is_institution_admin(user):
            return True
        resource = getattr(view, 'quota_resource', None)
        if resource is None:
            return True
        from users.quota import check_quota, get_quota_message
        if not check_quota(user.institution, resource):
            self.message = get_quota_message(user.institution, resource)
            return False
        return True



