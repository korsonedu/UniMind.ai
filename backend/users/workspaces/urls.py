from django.urls import path
from .views import WorkspaceView, SelectWorkspaceView, InvitePreviewView, JoinView, SwitchView, LeaveView, InvitesView, InviteDetailView, MemberDetailView, CoursesView, CourseDetailView

urlpatterns = [
    path('select/', SelectWorkspaceView.as_view()),
    path('', WorkspaceView.as_view()),
    path('invite-preview/', InvitePreviewView.as_view()),
    path('join/', JoinView.as_view()),
    path('switch/', SwitchView.as_view()),
    path('leave/', LeaveView.as_view()),
    path('invites/', InvitesView.as_view()),
    path('invites/<int:pk>/', InviteDetailView.as_view()),
    path('members/<int:pk>/', MemberDetailView.as_view()),
    path('courses/', CoursesView.as_view()),
    path('courses/<int:pk>/', CourseDetailView.as_view()),
]
