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
    "student": [CAP_MEMBER_ACCESS, "ai.assistant"],
    "member": [CAP_LEARNING_ACCESS, CAP_MEMBER_ACCESS],
    "admin": [CAP_LEARNING_ACCESS, CAP_MEMBER_ACCESS, *ADMIN_CAPABILITIES],
}


def is_platform_admin(user) -> bool:
    """仅两名桥接映射操作者可使用既有平台超管权限。"""
    if not (user and user.is_authenticated and user.is_active
            and getattr(user, 'is_staff', False) and getattr(user, 'is_superuser', False)
            and getattr(user, 'institution_id', None) is None):
        return False
    from django.conf import settings
    import json
    from uuid import UUID
    mapping = getattr(settings, 'UNIMIND_DIRECTUS_ADMIN_MAP', {})
    try:
        mapping = json.loads(mapping) if isinstance(mapping, str) else mapping
        if not isinstance(mapping, dict) or len(mapping) != 2:
            return False
        for actor in mapping:
            UUID(actor)
        return (len(mapping) == 2
                and len(set(mapping.values())) == 2
                and all(isinstance(pk, int) and not isinstance(pk, bool) and pk > 0
                        for pk in mapping.values())
                and user.pk in mapping.values())
    except (ValueError, TypeError, AttributeError):
        return False


def is_institution_admin(user) -> bool:
    """兼容旧调用；历史机构角色不再授予后台权限。"""
    return is_platform_admin(user)


def is_institution_owner(user) -> bool:
    return is_platform_admin(user)


def is_institution_teacher(user) -> bool:
    return is_platform_admin(user)


def is_member_or_admin(user) -> bool:
    return bool(user and user.is_authenticated and user.is_active)


def get_user_capabilities(user) -> list[str]:
    if not user or not user.is_authenticated or not user.is_active:
        return []

    from .learning import LEARNING_FEATURES, is_course_student
    caps = [CAP_MEMBER_ACCESS, 'ai.assistant', 'course.video']
    if is_platform_admin(user) or is_course_student(user):
        caps = [CAP_LEARNING_ACCESS, CAP_MEMBER_ACCESS, *LEARNING_FEATURES]
    if is_platform_admin(user):
        caps.extend(ADMIN_CAPABILITIES)
    allowed_caps = set(caps)

    # Superuser 人员管理扩展：读取用户访问档案中的权限组与自定义权限。
    profile = getattr(user, "access_profile", None)
    if profile:
        try:
            for group in profile.permission_groups.filter(is_active=True):
                for cap in (group.permissions or []):
                    cap_str = str(cap).strip()
                    if cap_str in allowed_caps:
                        caps.append(cap_str)
        except Exception:
            logger.exception("加载权限组失败: user=%s", user.id)

        for cap in (profile.extra_permissions or []):
            cap_str = str(cap).strip()
            if cap_str in allowed_caps:
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


class IsAdmin(IsPlatformAdmin):
    """仅既有平台管理员可进入管理端。"""


class IsMember(permissions.BasePermission):
    message = "请登录后使用学习功能。"

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated and request.user.is_active):
            return False
        self.message = HasStudentFeature.message
        return HasStudentFeature().has_permission(request, view)


class HasStudentFeature(permissions.BasePermission):
    message = '该功能尚未向你的账号开放，请联系管理员。'

    def has_permission(self, request, view):
        from .feature_access import has_learning_feature, request_feature
        feature = request_feature(request)
        if not request.user or not request.user.is_authenticated or not request.user.is_active:
            return False
        return not feature or has_learning_feature(request.user, feature)


class IsMemberOrReadOnlyList(permissions.BasePermission):
    """非会员可读列表接口（逛逛模式），写操作需要会员权限。"""

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return IsMember().has_permission(request, view)
        return is_member_or_admin(request.user) and HasStudentFeature().has_permission(request, view)


class IsAdminWriteMemberRead(permissions.BasePermission):
    """
    SAFE 方法：会员或管理员可读。
    写方法：平台管理员或机构管理员可写。
    """
    message = "权限不足。"

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return IsMember().has_permission(request, view)
        return is_platform_admin(request.user)


class IsInstitutionAdmin(IsPlatformAdmin):
    """旧权限名兼容，权限仅授予平台管理员。"""


class IsInstitutionTeacher(IsPlatformAdmin):
    pass


class IsInstitutionOwner(IsPlatformAdmin):
    pass


class IsInstitutionActive(permissions.BasePermission):
    """内部教学机构处于启用状态。"""
    message = "教学机构已停用，请联系管理员。"

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if is_platform_admin(user):
            return True
        inst = user.institution
        if inst is None:
            return False
        return inst.is_active


class HasPlanFeature(permissions.BasePermission):
    """
    检查用户是否具备指定功能（基于生效方案）。
    用法: permission_classes = [HasPlanFeature]; required_feature = 'ai.generate'

    方案来源：超管 → enterprise；有机构 → institution.get_effective_plan()；
    无机构 → personal_plan（默认 free）。
    """
    message = "当前账号未开放此功能，请联系管理员。"

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        required = getattr(view, 'required_feature', None)
        if required is None:
            return True
        from users.learning import LEARNING_FEATURES
        if required in LEARNING_FEATURES:
            from .feature_access import has_learning_feature
            return has_learning_feature(user, required)
        return is_platform_admin(user)


class IsInstitutionMember(IsPlatformAdmin):
    """旧机构管理接口仅保留管理员访问。"""


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
        if resource == 'ai_call_total':
            # 问答预留负责余额与重放校验；此处不能拦截已成功请求的幂等重试。
            return True
        from users.quota import check_quota, get_quota_message
        if not check_quota(user.institution, resource):
            self.message = get_quota_message(user.institution, resource)
            return False
        return True
