from django.urls import path
from .views import (
    RegisterView, LoginView, UserDetailView, UpdateProfileView,
    SystemConfigView, OnlineUserListView, UpdateEmailView, UpdatePasswordView,
    DailyPlanListView, DailyPlanDetailView, ResetEloView,
    ActivateMembershipView, ActivationCodeListView, ActivationCodeDetailView,
    BIAnalyticsView, WeeklyCognitiveReportView, HeartbeatView,
    MyKnowledgeMasteryView, SendVerificationCodeView,
)
from .views_institution import (
    InstitutionDashboardView, InstitutionListView, InstitutionDetailView,
    InstitutionCreateView, InstitutionActivateView, InstitutionDeactivateView,
    InstitutionChangePlanView, InstitutionStatsView,
    InstitutionStudentListView, InstitutionStudentDetailView,
    InstitutionStudentStatsView, InstitutionStudentResetPasswordView,
    InstitutionStudentRankingView,
    InstitutionFeatureView, InstitutionPreviewView,
    JoinInstitutionView, InstitutionSelfUpdateView, InstitutionJoinView,
    InstitutionInviteLookupView, CheckInviteView, RegenerateInviteSlugView,
    PlanInviteCodeListView, PlanInviteCodeGenerateView, PlanInviteCodeDeactivateView,
)

urlpatterns = [
    # Auth & profile
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path('send-verification-code/', SendVerificationCodeView.as_view(), name='send-verification-code'),
    path('me/', UserDetailView.as_view(), name='user-detail'),
    path('me/update/', UpdateProfileView.as_view(), name='user-update'),
    path('me/email/', UpdateEmailView.as_view(), name='email-update'),
    path('me/password/', UpdatePasswordView.as_view(), name='password-update'),
    path('me/reset-elo/', ResetEloView.as_view(), name='reset-elo'),
    path('me/activate/', ActivateMembershipView.as_view(), name='activate-membership'),
    path('me/weekly-report/', WeeklyCognitiveReportView.as_view(), name='weekly-report'),
    path('me/knowledge-mastery/', MyKnowledgeMasteryView.as_view(), name='knowledge-mastery'),
    path('heartbeat/', HeartbeatView.as_view(), name='heartbeat'),

    # System
    path('config/', SystemConfigView.as_view(), name='system-config'),
    path('online/', OnlineUserListView.as_view(), name='online-users'),
    path('plans/', DailyPlanListView.as_view(), name='daily-plan-list'),
    path('plans/<int:pk>/', DailyPlanDetailView.as_view(), name='daily-plan-detail'),

    # Admin
    path('admin/codes/', ActivationCodeListView.as_view(), name='activation-codes'),
    path('admin/codes/<int:pk>/', ActivationCodeDetailView.as_view(), name='activation-code-detail'),
    path('admin/bi/', BIAnalyticsView.as_view(), name='admin-bi'),

    # Institution — platform admin
    path('institutions/', InstitutionListView.as_view(), name='institution-list'),
    path('institutions/create/', InstitutionCreateView.as_view(), name='institution-create'),
    path('institutions/<int:pk>/', InstitutionDetailView.as_view(), name='institution-detail'),
    path('institutions/<int:pk>/activate/', InstitutionActivateView.as_view(), name='institution-activate'),
    path('institutions/<int:pk>/deactivate/', InstitutionDeactivateView.as_view(), name='institution-deactivate'),
    path('institutions/<int:pk>/change-plan/', InstitutionChangePlanView.as_view(), name='institution-change-plan'),
    path('institutions/<int:pk>/stats/', InstitutionStatsView.as_view(), name='institution-stats'),
    path('institutions/<int:pk>/preview/', InstitutionPreviewView.as_view(), name='institution-preview'),

    # Institution — self-service (current user's institution)
    path('institution/me/', InstitutionDashboardView.as_view(), name='institution-me'),
    path('institution/me/update/', InstitutionSelfUpdateView.as_view(), name='institution-self-update'),
    path('institution/me/features/', InstitutionFeatureView.as_view(), name='institution-features'),
    path('institution/me/preview/', InstitutionPreviewView.as_view(), name='institution-preview'),
    path('institution/join/', InstitutionJoinView.as_view(), name='institution-join'),
    path('institution/me/regenerate-invite-slug/', RegenerateInviteSlugView.as_view(), name='regenerate-invite-slug'),
    path('join/<str:invite_slug>/', JoinInstitutionView.as_view(), name='join-by-invite'),
    path('check-invite/', CheckInviteView.as_view(), name='check-invite'),
    path('institution/invite-lookup/', InstitutionInviteLookupView.as_view(), name='institution-invite-lookup'),

    # Institution — students
    path('institution/me/students/', InstitutionStudentListView.as_view(), name='institution-student-list'),
    path('institution/me/students/ranking/', InstitutionStudentRankingView.as_view(), name='institution-student-ranking'),
    path('institution/me/students/<int:pk>/', InstitutionStudentDetailView.as_view(), name='institution-student-detail'),
    path('institution/me/students/<int:pk>/stats/', InstitutionStudentStatsView.as_view(), name='institution-student-stats'),
    path('institution/me/students/<int:pk>/reset-password/', InstitutionStudentResetPasswordView.as_view(), name='institution-student-reset-password'),

    # Plan invite codes
    path('admin/plan-invite-codes/', PlanInviteCodeListView.as_view(), name='plan-invite-codes'),
    path('admin/plan-invite-codes/generate/', PlanInviteCodeGenerateView.as_view(), name='plan-invite-codes-generate'),
    path('admin/plan-invite-codes/<int:pk>/deactivate/', PlanInviteCodeDeactivateView.as_view(), name='plan-invite-codes-deactivate'),
]
