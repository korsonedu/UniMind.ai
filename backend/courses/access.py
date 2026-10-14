from django.db.models import Q

from users.learning import active_grants, has_legacy_membership
from .models import Course


def visible_courses(request):
    user = request.user
    courses = Course.objects.select_related('module')
    if not user.is_authenticated or not user.is_active:
        return courses.none()
    module_ids = set()
    for grant in active_grants(user):
        module_ids.update(grant.snapshot.get('modules', []))
    access = Q(module__is_public=True) | Q(module_id__in=module_ids)
    if user.institution_id and has_legacy_membership(user):
        access |= Q(institution_id=user.institution_id)
    return courses.filter(access)
