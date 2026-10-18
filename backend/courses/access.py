from core.utils import apply_institution_filter, get_content_institution_id

from .models import Course


def visible_courses(request):
    """当前用户可见的课程集合。

    模块仅作分类打标，学习权益暂不参与可见性判断；权限模型确定后再在此处实现。
    """
    return apply_institution_filter(Course.objects.all(), request.user, request)


def course_list_queryset(queryset, request):
    from django.db.models import Count, Prefetch, Q
    from .models import CourseTagRelation, VideoProgress

    relations = CourseTagRelation.objects.filter(
        tag__institution_id=get_content_institution_id(),
    ).select_related('tag').annotate(
        tag_course_count=Count('tag__course_relations', filter=Q(
            tag__course_relations__course__institution_id=get_content_institution_id(),
        )),
    )
    return queryset.select_related('module', 'album_obj').prefetch_related(
        Prefetch('tag_relations', queryset=relations, to_attr='serialized_tag_relations'),
        Prefetch('progress_records', queryset=VideoProgress.objects.filter(user=request.user),
                 to_attr='serialized_progress'),
    )
