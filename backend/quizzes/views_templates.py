from rest_framework import generics, permissions, status
from rest_framework.response import Response
from django.db import models
from users.permissions import IsMember, IsAdmin
from .models import ExamTemplate
from .serializers import ExamTemplateSerializer


class ExamTemplateListCreateView(generics.ListCreateAPIView):
    serializer_class = ExamTemplateSerializer
    permission_classes = [IsMember]

    def get_queryset(self):
        user = self.request.user
        # 系统预设 + 本机构模板
        qs = ExamTemplate.objects.filter(
            models.Q(is_system=True) | models.Q(institution=user.institution)
        )
        subject = self.request.query_params.get('subject')
        if subject:
            qs = qs.filter(subject=subject)
        return qs

    def perform_create(self, serializer):
        user = self.request.user
        if not user.institution:
            from rest_framework.exceptions import ValidationError
            raise ValidationError("请先加入机构")
        serializer.save(
            created_by=user,
            institution=user.institution,
            is_system=False,
        )


class ExamTemplateDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ExamTemplateSerializer
    permission_classes = [IsMember]

    def get_queryset(self):
        user = self.request.user
        return ExamTemplate.objects.filter(
            models.Q(is_system=True) | models.Q(institution=user.institution)
        )

    def perform_update(self, serializer):
        if serializer.instance.is_system:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("系统预设不可修改")
        serializer.save()

    def perform_destroy(self, instance):
        if instance.is_system:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("系统预设不可删除")
        instance.delete()
