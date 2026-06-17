from django.urls import path
from .views import (
    RegisterView, LoginView, UserDetailView, UpdateProfileView,
    OnlineUserListView, UpdateEmailView, UpdatePasswordView,
    DailyPlanListView, DailyPlanDetailView,
    ActivateMembershipView,
    BIAnalyticsView, WeeklyCognitiveReportView, HeartbeatView,
    MyKnowledgeMasteryView, SendVerificationCodeView, LogoutView,
    DiagnosticGenerateView, DiagnosticSubmitView,
    AnalyticsDashboardView, AnalyticsExportView, NPSSubmitView, NPSStatusView,
    AccountDeleteView, DataExportView, FeedbackSubmitView,
    AvatarProxyView,
    UserCheckInView, AchievementListView, UserAchievementView,
    UserClassListView,
    StudentReportCardView, StudentReportCardPDFView,
)
from .views_admin import (
    SuperuserUserListView, UserTagListView, PermissionGroupListView,
)
from .views_institution import (
    InstitutionDashboardView, PlatformAdminInstitutionOverviewView,
    InstitutionListView, InstitutionDetailView,
    InstitutionCreateView, InstitutionActivateView, InstitutionDeactivateView,
    InstitutionChangePlanView,
    InstitutionStudentListView, InstitutionStudentDetailView,
    InstitutionStudentStatsView, InstitutionStudentResetPasswordView,
    InstitutionStudentRankingView,
    InstitutionFeatureView, InstitutionPreviewView,
    InstitutionSelfUpdateView,
    CheckInviteView, RegenerateInviteSlugView,
    PlanInviteCodeListView, PlanInviteCodeGenerateView, PlanInviteCodeDeactivateView,
    InstitutionPaymentConfigView,
    ValidateInviteCodeView,
    UpdateDirectionsView,
    PublicInstitutionView, InstitutionJoinBySlugView, InstitutionJoinByInviteSlugView,
    InstitutionMemberListView, InstitutionMemberRoleView,
    InstitutionClassPerformanceView, InstitutionSuggestedTopicsView,
    InstitutionAuditLogView, InstitutionNotificationConfigView,
    ClassListCreateView, ClassDetailView, ClassStudentView,
    InstitutionBulkInitView,
    ClassCourseManageView, StudentClassCourseView, ClassGradebookView,
    InstitutionBusinessDashboardView, InstitutionDataExportView,
    InstitutionStudentReportCardView,
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
    path('me/activate/', ActivateMembershipView.as_view(), name='activate-membership'),
    path('me/weekly-report/', WeeklyCognitiveReportView.as_view(), name='weekly-report'),
    path('me/knowledge-mastery/', MyKnowledgeMasteryView.as_view(), name='knowledge-mastery'),
    path('me/diagnostic/generate/', DiagnosticGenerateView.as_view(), name='diagnostic-generate'),
    path('me/diagnostic/submit/', DiagnosticSubmitView.as_view(), name='diagnostic-submit'),
    path('heartbeat/', HeartbeatView.as_view(), name='heartbeat'),
    path('nps/submit/', NPSSubmitView.as_view(), name='nps-submit'),
    path('nps/status/', NPSStatusView.as_view(), name='nps-status'),

    # System
    path('online/', OnlineUserListView.as_view(), name='online-users'),
    path('plans/', DailyPlanListView.as_view(), name='daily-plan-list'),
    path('plans/<int:pk>/', DailyPlanDetailView.as_view(), name='daily-plan-detail'),

    # Admin
    path('admin/bi/', BIAnalyticsView.as_view(), name='admin-bi'),
    path('admin/analytics/dashboard/', AnalyticsDashboardView.as_view(), name='admin-analytics-dashboard'),
    path('admin/analytics/export/', AnalyticsExportView.as_view(), name='admin-analytics-export'),
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

    path('institutions/overview/', PlatformAdminInstitutionOverviewView.as_view(), name='institution-overview'),

    # Institution — self-service (current user's institution)
    path('institution/me/', InstitutionDashboardView.as_view(), name='institution-me'),
    path('institution/me/update/', InstitutionSelfUpdateView.as_view(), name='institution-self-update'),
    path('institution/me/directions/', UpdateDirectionsView.as_view(), name='institution-directions-update'),
    path('institution/me/features/', InstitutionFeatureView.as_view(), name='institution-features'),
    path('institution/me/regenerate-invite-slug/', RegenerateInviteSlugView.as_view(), name='regenerate-invite-slug'),
    path('institution/me/bulk-init/', InstitutionBulkInitView.as_view(), name='institution-bulk-init'),
    path('institution/join-by-slug/', InstitutionJoinBySlugView.as_view(), name='institution-join-by-slug'),
    path('institution/join-by-invite-slug/', InstitutionJoinByInviteSlugView.as_view(), name='institution-join-by-invite-slug'),
    path('public/institution/<str:slug>/', PublicInstitutionView.as_view(), name='public-institution'),
    path('check-invite/', CheckInviteView.as_view(), name='check-invite'),

    # Institution — students
    path('institution/me/students/', InstitutionStudentListView.as_view(), name='institution-student-list'),
    path('institution/me/students/ranking/', InstitutionStudentRankingView.as_view(), name='institution-student-ranking'),
    path('institution/me/students/<int:pk>/', InstitutionStudentDetailView.as_view(), name='institution-student-detail'),
    path('institution/me/students/<int:pk>/stats/', InstitutionStudentStatsView.as_view(), name='institution-student-stats'),
    path('institution/me/students/<int:pk>/reset-password/', InstitutionStudentResetPasswordView.as_view(), name='institution-student-reset-password'),
    path('institution/me/students/<int:pk>/report-card/', InstitutionStudentReportCardView.as_view(), name='institution-student-report-card'),

    # Institution — members (owner + teacher management)
    path('institution/me/members/', InstitutionMemberListView.as_view(), name='institution-member-list'),
    path('institution/me/members/<int:pk>/role/', InstitutionMemberRoleView.as_view(), name='institution-member-role'),

    # Institution — analytics
    path('institution/me/analytics/class-performance/', InstitutionClassPerformanceView.as_view(), name='institution-class-performance'),
    path('institution/me/analytics/suggested-topics/', InstitutionSuggestedTopicsView.as_view(), name='institution-suggested-topics'),

    # Institution — audit log
    path('institution/me/audit-logs/', InstitutionAuditLogView.as_view(), name='institution-audit-logs'),

    # Institution — notification config
    path('institution/me/notification-config/', InstitutionNotificationConfigView.as_view(), name='institution-notification-config'),
    path('institution/me/classes/', ClassListCreateView.as_view(), name='institution-class-list'),
    path('institution/me/classes/<int:pk>/', ClassDetailView.as_view(), name='institution-class-detail'),
    path('institution/me/classes/<int:pk>/students/', ClassStudentView.as_view(), name='institution-class-students'),
    path('institution/me/class-courses/', ClassCourseManageView.as_view(), name='institution-class-course-manage'),
    path('institution/me/class-courses/<int:pk>/', ClassCourseManageView.as_view(), name='institution-class-course-delete'),
    path('me/class-courses/', StudentClassCourseView.as_view(), name='student-class-courses'),
    path('institution/me/gradebook/', ClassGradebookView.as_view(), name='institution-gradebook'),
    path('institution/me/business-dashboard/', InstitutionBusinessDashboardView.as_view(), name='institution-business-dashboard'),
    path('institution/me/data-export/', InstitutionDataExportView.as_view(), name='institution-data-export'),

    # Institution — payment config (Pro)
    path('institution/me/payment-config/', InstitutionPaymentConfigView.as_view(), name='institution-payment-config'),

    # Plan invite codes
    path('admin/plan-invite-codes/', PlanInviteCodeListView.as_view(), name='plan-invite-codes'),
    path('admin/plan-invite-codes/generate/', PlanInviteCodeGenerateView.as_view(), name='plan-invite-codes-generate'),
    path('admin/plan-invite-codes/<int:pk>/deactivate/', PlanInviteCodeDeactivateView.as_view(), name='plan-invite-codes-deactivate'),

    # Validate invite code (for onboarding flow)
    path('institutions/validate-invite-code/', ValidateInviteCodeView.as_view(), name='validate-invite-code'),

    # Account management (P0: 个保法合规)
    path('me/delete/', AccountDeleteView.as_view(), name='account-delete'),
    path('me/data-export/', DataExportView.as_view(), name='data-export'),
    path('feedback/', FeedbackSubmitView.as_view(), name='feedback-submit'),

    # Avatar proxy
    path('avatar/<str:style>/<str:seed>/', AvatarProxyView.as_view(), name='avatar-proxy'),

    # Check-in & achievements
    path('me/checkin/', UserCheckInView.as_view(), name='user-checkin'),
    path('achievements/', AchievementListView.as_view(), name='achievement-list'),
    path('me/achievements/', UserAchievementView.as_view(), name='user-achievements'),
    path('me/classes/', UserClassListView.as_view(), name='user-classes'),

    # Report card
    path('me/report-card/', StudentReportCardView.as_view(), name='student-report-card'),
    path('me/report-card/pdf/', StudentReportCardPDFView.as_view(), name='student-report-card-pdf'),
]
