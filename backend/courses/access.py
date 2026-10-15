from core.utils import apply_institution_filter

from .models import Course


def visible_courses(request):
    """当前用户可见的课程集合。

    模块仅作分类打标，学习权益暂不参与可见性判断；权限模型确定后再在此处实现。
    """
    return apply_institution_filter(Course.objects.all(), request.user, request)
