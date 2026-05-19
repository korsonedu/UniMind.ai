from django.urls import path
from .views import (
    RegisterView, LoginView, UserDetailView, UpdateProfileView,
    OnlineUserListView, UpdateEmailView, UpdatePasswordView,
    DailyPlanListView, DailyPlanDetailView, ResetEloView,
    ActivateMembershipView, ActivationCodeListView, ActivationCodeDetailView,
    BIAnalyticsView, WeeklyCognitiveReportView, HeartbeatView,
    MyKnowledgeMasteryView, SendVerificationCodeView, LogoutView,
)
from .views_admin import (
    SuperuserUserListView, UserTagListView, PermissionGroupListView,
)
from .views_institution import (
    InstitutionDashboardView, InstitutionListView, InstitutionDetailView,
    InstitutionCreateView, InstitutionActivateView, InstitutionDeactivateView,
    InstitutionChangePlanView,
    InstitutionStudentListView, InstitutionStudentDetailView,
    InstitutionStudentStatsView, InstitutionStudentResetPasswordView,
    InstitutionStudentRankingView,
    InstitutionFeatureView, InstitutionPreviewView,
    InstitutionSelfUpdateView,
    CheckInviteView, RegenerateInviteSlugView,
    PlanInviteCodeListView, PlanInviteCodeGenerateView, PlanInviteCodeDeactivateView,
    ValidateInviteCodeView,
    UpdateDirectionsView,
    PublicInstitutionView, InstitutionJoinBySlugView,
    InstitutionMemberListView, InstitutionMemberRoleView,
)
from .views_points import (
    PointsBalanceView, PointsLedgerView,
    InstitutionRewardConfigView, InstitutionAwardPointsView,
)

urlpatterns = [
    # Auth & profile
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('send-verification-code/', SendVerificationCodeView.as_view(), name='send-verification-code'),
    path('me/', UserDetailView.as_view(), name='user-detail'),
    path('me/update/', UpdateProfileView.as_view(), name='user-update'),
    path('me/email/', UpdateEmailView.as_view(), name='email-update'),
    path('me/password/', UpdatePasswordView.as_view(), name='password-update'),
    path('me/reset-elo/', ResetEloView.as_view(), name='reset-elo'),
    path('me/activate/', ActivateMembershipView.as_view(), name='activate-membership'),
    path('me/weekly-report/', WeeklyCognitiveReportView.as_view(), name='weekly-report'),
    path('me/knowledge-mastery/', MyKnowledgeMasteryView.as_view(), name='knowledge-mastery'),
    path('me/points/', PointsBalanceView.as_view(), name='points-balance'),
    path('me/points/ledger/', PointsLedgerView.as_view(), name='points-ledger'),
    path('heartbeat/', HeartbeatView.as_view(), name='heartbeat'),

    # System
    path('online/', OnlineUserListView.as_view(), name='online-users'),
    path('plans/', DailyPlanListView.as_view(), name='daily-plan-list'),
    path('plans/<int:pk>/', DailyPlanDetailView.as_view(), name='daily-plan-detail'),

    # Admin
    path('admin/codes/', ActivationCodeListView.as_view(), name='activation-codes'),
    path('admin/codes/<int:pk>/', ActivationCodeDetailView.as_view(), name='activation-code-detail'),
    path('admin/bi/', BIAnalyticsView.as_view(), name='admin-bi'),
    path('admin/superusers/users/', SuperuserUserListView.as_view(), name='admin-superuser-users'),
    path('admin/superusers/users/<int:pk>/', SuperuserUserListView.as_view(), name='admin-superuser-user-detail'),
    path('admin/user-tags/', UserTagListView.as_view(), name='admin-user-tags'),
    path('admin/permission-groups/', PermissionGroupListView.as_view(), name='admin-permission-groups'),

    # Institution — platform admin
    path('institutions/', InstitutionListView.as_view(), name='institution-list'),
    path('institutions/create/', InstitutionCreateView.as_view(), name='institution-create'),
    path('institutions/<int:pk>/', InstitutionDetailView.as_view(), name='institution-detail'),
    path('institutions/<int:pk>/activate/', InstitutionActivateView.as_view(), name='institution-activate'),
    path('institutions/<int:pk>/deactivate/', InstitutionDeactivateView.as_view(), name='institution-deactivate'),
    path('institutions/<int:pk>/change-plan/', InstitutionChangePlanView.as_view(), name='institution-change-plan'),
    path('institutions/<int:pk>/preview/', InstitutionPreviewView.as_view(), name='institution-preview'),

    # Institution — self-service (current user's institution)
    path('institution/me/', InstitutionDashboardView.as_view(), name='institution-me'),
    path('institution/me/update/', InstitutionSelfUpdateView.as_view(), name='institution-self-update'),
    path('institution/me/directions/', UpdateDirectionsView.as_view(), name='institution-directions-update'),
    path('institution/me/features/', InstitutionFeatureView.as_view(), name='institution-features'),
    path('institution/me/regenerate-invite-slug/', RegenerateInviteSlugView.as_view(), name='regenerate-invite-slug'),
    path('institution/join-by-slug/', InstitutionJoinBySlugView.as_view(), name='institution-join-by-slug'),
    path('public/institution/<str:slug>/', PublicInstitutionView.as_view(), name='public-institution'),
    path('check-invite/', CheckInviteView.as_view(), name='check-invite'),

    # Institution — students
    path('institution/me/students/', InstitutionStudentListView.as_view(), name='institution-student-list'),
    path('institution/me/students/ranking/', InstitutionStudentRankingView.as_view(), name='institution-student-ranking'),
    path('institution/me/students/<int:pk>/', InstitutionStudentDetailView.as_view(), name='institution-student-detail'),
    path('institution/me/students/<int:pk>/stats/', InstitutionStudentStatsView.as_view(), name='institution-student-stats'),
    path('institution/me/students/<int:pk>/reset-password/', InstitutionStudentResetPasswordView.as_view(), name='institution-student-reset-password'),

    # Institution — members (owner + teacher management)
    path('institution/me/members/', InstitutionMemberListView.as_view(), name='institution-member-list'),
    path('institution/me/members/<int:pk>/role/', InstitutionMemberRoleView.as_view(), name='institution-member-role'),

    # Institution — rewards
    path('institution/me/rewards/config/', InstitutionRewardConfigView.as_view(), name='institution-rewards-config'),
    path('institution/me/rewards/award/', InstitutionAwardPointsView.as_view(), name='institution-rewards-award'),

    # Plan invite codes
    path('admin/plan-invite-codes/', PlanInviteCodeListView.as_view(), name='plan-invite-codes'),
    path('admin/plan-invite-codes/generate/', PlanInviteCodeGenerateView.as_view(), name='plan-invite-codes-generate'),
    path('admin/plan-invite-codes/<int:pk>/deactivate/', PlanInviteCodeDeactivateView.as_view(), name='plan-invite-codes-deactivate'),

    # Validate invite code (for onboarding flow)
    path('institutions/validate-invite-code/', ValidateInviteCodeView.as_view(), name='validate-invite-code'),
]
