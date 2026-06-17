"""作业模块独立路由 — 挂载于 /api/assignments/"""
from django.urls import path
from .views_question import (
    AssignmentCreateView,
    StudentAssignmentListView,
    StudentAssignmentDetailView,
    StudentAssignmentSubmitView,
    AssignmentSubmissionListView,
    AssignmentGradeView,
    TeacherAssignmentListView,
)

urlpatterns = [
    # 教师端
    path('create/', AssignmentCreateView.as_view(), name='assignment-create'),  # POST
    path('teacher/', TeacherAssignmentListView.as_view(), name='teacher-assignment-list'),  # GET
    # 学生端
    path('my/', StudentAssignmentListView.as_view(), name='student-assignment-list'),
    path('<int:pk>/questions/', StudentAssignmentDetailView.as_view(), name='student-assignment-detail'),
    path('submit/', StudentAssignmentSubmitView.as_view(), name='student-assignment-submit'),
    # 提交 & 批改
    path('<int:pk>/submissions/', AssignmentSubmissionListView.as_view(), name='assignment-submissions'),
    path('submissions/<int:pk>/grade/', AssignmentGradeView.as_view(), name='assignment-grade'),
]
