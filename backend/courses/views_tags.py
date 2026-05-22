from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Count
from django.utils.text import slugify

from .models import Course, CourseTag, CourseTagRelation
from .serializers import CourseTagSerializer
from users.permissions import IsAdmin


class TagListCreateView(generics.ListCreateAPIView):
    serializer_class = CourseTagSerializer

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAdmin()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        inst = self.request.user.institution
        if not inst:
            return CourseTag.objects.none()
        return CourseTag.objects.filter(institution=inst).annotate(course_count=Count('course_relations'))

    def perform_create(self, serializer):
        inst = self.request.user.institution
        name = serializer.validated_data.get('name', '')
        slug = slugify(name)
        base = slug
        n = 1
        while CourseTag.objects.filter(institution=inst, slug=slug).exists():
            slug = f"{base}-{n}"
            n += 1
        serializer.save(institution=inst, slug=slug)


class TagDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = CourseTagSerializer
    permission_classes = [IsAdmin]

    def get_queryset(self):
        return CourseTag.objects.filter(institution=self.request.user.institution)


class BatchAssignTagsView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request):
        course_id = request.data.get('course_id')
        tag_names = request.data.get('tags', [])

        if not course_id:
            return Response({"error": "course_id is required"}, status=400)
        try:
            course = Course.objects.get(pk=course_id)
        except Course.DoesNotExist:
            return Response({"error": "Course not found"}, status=404)

        inst = request.user.institution
        tag_ids = []
        for name in tag_names:
            name = name.strip()
            if not name:
                continue
            slug = slugify(name)
            tag, _ = CourseTag.objects.get_or_create(
                institution=inst, slug=slug,
                defaults={'name': name}
            )
            relation, _ = CourseTagRelation.objects.get_or_create(
                course=course, tag=tag
            )
            tag_ids.append(tag.id)

        # Remove relations for tags not in the new list
        course.tag_relations.exclude(tag_id__in=tag_ids).delete()

        relations = course.tag_relations.select_related('tag').all()
        return Response(CourseTagSerializer([r.tag for r in relations], many=True).data)
