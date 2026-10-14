from django.db import transaction
from django.db.models import Count
from django.db.models.deletion import ProtectedError
from rest_framework import generics, serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from core.utils import apply_institution_filter
from users.permissions import IsAdmin, IsMember, is_platform_admin, is_institution_admin
from .models import Course, CourseModule
from .serializers import CourseModuleSerializer


class ModuleListCreateView(generics.ListCreateAPIView):
    serializer_class = CourseModuleSerializer
    pagination_class = None

    def get_permissions(self):
        return [IsAdmin()] if self.request.method == 'POST' else [IsMember()]

    def get_queryset(self):
        if is_platform_admin(self.request.user) or is_institution_admin(self.request.user):
            return apply_institution_filter(CourseModule.objects.annotate(course_count=Count('courses')), self.request.user, self.request)
        from .access import visible_courses
        ids = visible_courses(self.request).values_list('module_id', flat=True)
        return CourseModule.objects.filter(pk__in=ids).annotate(course_count=Count('courses'))

    def perform_create(self, serializer):
        serializer.save(institution=self.request.user.institution)


class ModuleDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = CourseModuleSerializer

    def get_permissions(self):
        return [IsMember()] if self.request.method == 'GET' else [IsAdmin()]

    def get_queryset(self):
        return apply_institution_filter(CourseModule.objects.annotate(course_count=Count('courses')), self.request.user, self.request)

    def destroy(self, request, *args, **kwargs):
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            return Response({'error': '请先将模块内的课程迁至其他模块。'}, status=400)


class ModuleAssignmentInput(serializers.Serializer):
    module = serializers.IntegerField(min_value=1)
    courses = serializers.ListField(child=serializers.IntegerField(min_value=1), allow_empty=False)


class ModuleAssignView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request):
        payload = ModuleAssignmentInput(data=request.data)
        payload.is_valid(raise_exception=True)
        ids = set(payload.validated_data['courses'])
        with transaction.atomic():
            module = apply_institution_filter(CourseModule.objects.select_for_update(), request.user, request).filter(pk=payload.validated_data['module']).first()
            if not module:
                return Response({'error': '模块不存在或无权限。'}, status=400)
            courses = apply_institution_filter(Course.objects.select_for_update(), request.user, request).filter(pk__in=ids)
            selected = list(courses)
            if len(selected) != len(ids) or any(course.institution_id != module.institution_id for course in selected):
                return Response({'error': '课程与模块须属于同一机构。'}, status=400)
            courses.update(module=module)
        return Response({'updated': len(ids)})
