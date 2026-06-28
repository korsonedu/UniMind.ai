import { createBrowserRouter, RouterProvider, Navigate, Outlet, useNavigate } from 'react-router-dom';
import { lazy, Suspense, useEffect, type ReactNode } from 'react';
import { QueryClientProvider } from '@tanstack/react-query';
import { useQuery } from '@tanstack/react-query';
import { queryClient } from '@/lib/queryClient';
import { queryKeys } from '@/lib/queryKeys';
import { useStudyRoomWs } from '@/hooks/useStudyRoomWs';
import { useXiaoYuEngine } from '@/hooks/useXiaoYuEngine';
import { FEATURES } from './store/useInstitutionStore';
const MainLayout = lazy(() => import('./layouts/MainLayout').then(m => ({ default: m.MainLayout })));
import { useAuthStore } from './store/useAuthStore';
import { useSystemStore } from './store/useSystemStore';
import { useInstitutionStore } from './store/useInstitutionStore';
import { FeatureGuard } from './components/FeatureGuard';
import { Loading } from '@/components/Loading';
import api from '@/lib/api';
import { Toaster } from 'sonner';
import i18n from '@/lib/i18n';
import { ErrorBoundary } from '@/components/ErrorBoundary';

const NPSSurvey = lazy(() => import('./components/NPSSurvey').then(m => ({ default: m.NPSSurvey })));
import { FeedbackButton } from './components/FeedbackButton';
import { OnboardingDialog } from '@/components/OnboardingDialog';

// Lazy-loaded pages — named exports need .then() wrapper
const lazyNamed = <T extends Record<string, React.ComponentType<any>>>(loader: () => Promise<T>, name: keyof T) =>
  lazy(() => loader().then(m => ({ default: m[name] })));

const Landing = lazyNamed(() => import('./pages/Landing'), 'Landing');
const CourseCenter = lazyNamed(() => import('./pages/CourseCenter'), 'CourseCenter');
const TestLadder = lazyNamed(() => import('./pages/TestLadder'), 'TestLadder');
const StudyRoom = lazyNamed(() => import('./pages/StudyRoom'), 'StudyRoom');
const Settings = lazyNamed(() => import('./pages/Settings'), 'Settings');
const Maintenance = lazyNamed(() => import('./pages/Maintenance'), 'Maintenance');
const Login = lazyNamed(() => import('./pages/Login'), 'Login');
const Register = lazyNamed(() => import('./pages/Register'), 'Register');
const VerifyCode = lazyNamed(() => import('./pages/VerifyCode'), 'VerifyCode');
const VideoLesson = lazyNamed(() => import('./pages/VideoLesson'), 'VideoLesson');
const ArticleDetail = lazyNamed(() => import('./pages/ArticleDetail'), 'ArticleDetail');
const ArticleCenter = lazyNamed(() => import('./pages/ArticleCenter'), 'ArticleCenter');
const SystemSettings = lazyNamed(() => import('./pages/SystemSettings'), 'SystemSettings');
const KnowledgeMap = lazyNamed(() => import('./pages/KnowledgeMap'), 'KnowledgeMap');
const KnowledgeNodeDetail = lazyNamed(() => import('./pages/KnowledgeNodeDetail'), 'KnowledgeNodeDetail');
const QASystem = lazyNamed(() => import('./pages/QASystem'), 'QASystem');
const TestSessionPage = lazyNamed(() => import('./pages/TestSessionPage'), 'TestSessionPage');
const PromptTemplatesAdmin = lazyNamed(() => import('./pages/PromptTemplatesAdmin'), 'PromptTemplatesAdmin');

const PdfMockExam = lazyNamed(() => import('./pages/PdfMockExam'), 'PdfMockExam');
const WrongQuestionReviewPage = lazyNamed(() => import('./pages/WrongQuestionReviewPage'), 'WrongQuestionReviewPage');
const ReportCard = lazyNamed(() => import('./pages/ReportCard'), 'ReportCard');
const Achievements = lazyNamed(() => import('./pages/Achievements'), 'Achievements');

const BillingPage = lazyNamed(() => import('./pages/Billing'), 'BillingPage');
const PaymentResult = lazyNamed(() => import('./pages/PaymentResult'), 'PaymentResult');
const Checkout = lazyNamed(() => import('./pages/Checkout'), 'Checkout');
const DiagnosticTest = lazyNamed(() => import('./pages/DiagnosticTest'), 'DiagnosticTest');
const StudyPlan = lazyNamed(() => import('./pages/StudyPlan'), 'StudyPlan');
const XiaoYu = lazyNamed(() => import('./pages/XiaoYu'), 'XiaoYu');
const PracticeSession = lazy(() => import('./pages/xiaoyu/PracticeSession'));

// Default exports — plain lazy() works
const Workbench = lazy(() => import('./pages/Workbench'));
const TeacherQuestions = lazy(() => import('./pages/TeacherQuestions'));
const AssetHub = lazy(() => import('./pages/AssetHub'));
const TeacherKnowledgeTree = lazy(() => import('./pages/TeacherKnowledgeTree'));
const InstitutionDashboard = lazy(() => import('./pages/InstitutionDashboard'));
const InstitutionStudents = lazy(() => import('./pages/InstitutionStudents'));
const InstitutionAdmin = lazy(() => import('./pages/InstitutionAdmin'));
const InstitutionHome = lazy(() => import('./pages/InstitutionHome'));
const MemorixPage = lazy(() => import('./pages/Memorix'));
const InviteCodeAdmin = lazy(() => import('./pages/InviteCodeAdmin'));
const PlatformAdmin = lazy(() => import('./pages/PlatformAdmin'));
const JoinPage = lazyNamed(() => import('./pages/JoinPage'), 'JoinPage');
const NotFound = lazy(() => import('./pages/NotFound'));
const OnlineExam = lazyNamed(() => import('./pages/OnlineExam'), 'OnlineExam');
const Gradebook = lazyNamed(() => import('./pages/Gradebook'), 'Gradebook');
const TeacherAssignments = lazyNamed(() => import('./pages/TeacherAssignments'), 'TeacherAssignments');
const Marketplace = lazyNamed(() => import('./pages/Marketplace'), 'Marketplace');
const APIPlatform = lazyNamed(() => import('./pages/APIPlatform'), 'APIPlatform');
const MyAssignments = lazy(() => import('./pages/MyAssignments'));
const CourseManage = lazy(() => import('./pages/CourseManage'));
const ArticleManage = lazy(() => import('./pages/ArticleManage'));
const AuditLogs = lazy(() => import('./pages/AuditLogs'));
const Legal = lazy(() => import('./pages/Legal'));
const PricingPage = lazy(() => import('./pages/Pricing'));
const PromoPlus = lazy(() => import('./pages/PromoPlus'));
const LessonPlans = lazy(() => import('./pages/LessonPlans'));

import { Skeleton } from '@/components/ui/skeleton';

const PageLoader = () => (
  <div className="min-h-dvh w-full flex items-center justify-center bg-background">
    <div className="w-full max-w-6xl mx-auto px-6 md:px-8 py-12 space-y-8">
      {/* Header skeleton */}
      <div className="space-y-3 max-w-lg">
        <Skeleton className="h-8 w-64 rounded-lg" />
        <Skeleton className="h-4 w-96 rounded-md" />
      </div>
      {/* Card grid skeleton */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="space-y-3 rounded-xl border border-border/50 p-5">
            <Skeleton className="h-36 w-full rounded-lg" />
            <Skeleton className="h-5 w-3/4 rounded-md" />
            <Skeleton className="h-4 w-1/2 rounded-md" />
          </div>
        ))}
      </div>
    </div>
  </div>
);

// Language redirect helper
const LanguageRedirect = ({ lang }: { lang: string }) => {
  useEffect(() => {
    i18n.changeLanguage(lang);
  }, [lang]);
  return <Navigate to="/" replace />;
};

// Auth Guard — RootRedirect already handles auth validation; here we just gate.
const RequireAuth = ({ children }: { children: ReactNode }) => {
  const user = useAuthStore(s => s.user);
  const { theme, setTheme } = useSystemStore();

  useEffect(() => {
    if (user?.role === 'admin') {
      if (theme === 'dark') setTheme('dark');
    } else if (user && theme !== 'light') {
      setTheme('light');
    }
    // PWA push subscription — deferred to avoid blocking render
    if (user) {
      const timer = setTimeout(() => {
        import('@/lib/pushSubscription').then(m => m.subscribeToPush()).catch(() => {});
      }, 3000);
      return () => clearTimeout(timer);
    }
  }, [user?.role, user, theme, setTheme]);

  if (!user) return <Navigate to="/login" replace />;
  return children;
};

// 超级管理员：is_superuser 且无机构绑定
const RequirePlatformAdmin = ({ children }: { children: ReactNode }) => {
  const { user } = useAuthStore();
  if (!user) return <Navigate to="/login" replace />;
  if (!user.is_admin) return <Navigate to="/settings" replace />;
  return children;
};

// 机构管理员或超级管理员：可访问管理类功能
const RequireAdmin = ({ children }: { children: ReactNode }) => {
  const { user } = useAuthStore();
  if (!user) return <Navigate to="/login" replace />;
  if (!user.is_admin && !user.is_institution_admin)
    return <Navigate to="/settings" replace />;
  return children;
};

// 机构成员（管理员 + 学员）+ 超级管理员预览
const RequireInstitution = ({ children }: { children: ReactNode }) => {
  const { user } = useAuthStore();
  const institution = useInstitutionStore(s => s.institution);
  const isPlatformAdmin = useInstitutionStore(s => s.isPlatformAdmin);
  const featuresLoading = useInstitutionStore(s => s.loading);
  const fetchFeatures = useInstitutionStore(s => s.fetchFeatures);

  useEffect(() => {
    if (user && !institution && !featuresLoading) {
      fetchFeatures();
    }
  }, [user, institution, featuresLoading, fetchFeatures]);

  if (!user) return <Navigate to="/login" replace />;
  if (featuresLoading) return <Loading message="Loading institution…" fullScreen size="lg" />;
  if (!institution && !isPlatformAdmin) return <Navigate to="/" replace />;
  if (isPlatformAdmin) return children;
  if (!institution?.id) return <Navigate to="/" replace />;
  // 机构管理员（owner / teacher）可访问管理类页面
  if (user.institution_role !== 'owner' && user.institution_role !== 'teacher' && !user.is_institution_admin && !user.is_admin) {
    return <Navigate to="/" replace />;
  }
  return children;
};

// 超管默认跳转到机构管理；Pro 机构 → 机构主页；未完成诊断的学生 → 诊断；否则 → 学生主页
const HomeRedirect = () => {
  const { user } = useAuthStore();
  const institution = useInstitutionStore(s => s.institution);
  if (user?.role === 'admin' && !institution && !user?.institution) return <Navigate to="/institution/admin" replace />;
  if (institution?.plan === 'enterprise') {
    if (user?.institution_role === 'owner' || user?.institution_role === 'teacher' || user?.is_institution_admin) {
      return <Navigate to="/workbench" replace />;
    }
    return <Navigate to="/institution" replace />;
  }
  // 教师/机构主 → 工作台
  if (user?.institution_role === 'owner' || user?.institution_role === 'teacher' || user?.is_institution_admin) {
    return <Navigate to="/workbench" replace />;
  }
  // 学生 → 小宇（Agent 为入口，诊断由小宇引导）
  if (user?.institution_role === 'student') {
    return <Navigate to="/xiaoyu" replace />;
  }

  return <Navigate to="/xiaoyu" replace />;
};

// Root entry handler to manage landing vs app logic
// korsonedu.com → 机构主页；unimind-ai.com → 正常 Landing/App
const isKorsonedu = typeof window !== 'undefined' &&
  /korsonedu\.com/.test(window.location.hostname);

const RootRedirect = () => {
  const user = useAuthStore(s => s.user);
  const setAuth = useAuthStore(s => s.setAuth);
  const logout = useAuthStore(s => s.logout);
  const hasHydrated = useAuthStore.persist.hasHydrated();
  const navigate = useNavigate();

  const { data: userData, isLoading, isError } = useQuery({
    queryKey: queryKeys.user.me,
    queryFn: () => api.get('/users/me/').then(r => r.data),
    enabled: hasHydrated,
    retry: false,
  });

  // Sync auth store with query result
  useEffect(() => {
    if (userData) setAuth(userData, null);
  }, [userData, setAuth]);

  // On auth failure, log out and check invite status
  useEffect(() => {
    if (!isError) return;
    logout();
    api.get('/users/check-invite/')
      .then(res => {
        if (res.data?.has_invite) navigate('/register', { replace: true });
      })
      .catch(() => {});
  }, [isError, logout, navigate]);

  if (!hasHydrated || isLoading) return <Loading message="Authenticating Secure Session…" fullScreen size="lg" />;

  if (userData) return <Outlet />;

  // korsonedu.com → 直接展示机构主页
  if (isKorsonedu) return <Suspense fallback={<PageLoader />}><InstitutionHome slug="korsonedu" /></Suspense>;

  return <Suspense fallback={<PageLoader />}><Landing /></Suspense>;
};

const lazyPage = (Component: React.ComponentType) => (
  <ErrorBoundary>
    <Suspense fallback={<PageLoader />}><Component /></Suspense>
  </ErrorBoundary>
);

const router = createBrowserRouter([
  {
    path: "/",
    element: <RootRedirect />,
    children: [
      { index: true, element: <HomeRedirect /> },
      {
        element: <RequireAuth><Suspense fallback={<PageLoader />}><MainLayout /></Suspense></RequireAuth>,
        children: [
          { path: "courses", element: lazyPage(CourseCenter) },
          { path: "courses/manage", element: <RequireInstitution>{lazyPage(CourseManage)}</RequireInstitution> },
          { path: "articles", element: lazyPage(ArticleCenter) },
          { path: "articles/manage", element: <RequireInstitution>{lazyPage(ArticleManage)}</RequireInstitution> },
          { path: "qa", element: <FeatureGuard feature={FEATURES.FAQ_SYSTEM}>{lazyPage(QASystem)}</FeatureGuard> },
          { path: "article/:id", element: lazyPage(ArticleDetail) },
          { path: "tests", element: <FeatureGuard feature={FEATURES.QUIZ_EXAM}>{lazyPage(TestLadder)}</FeatureGuard> },
          { path: "tests/session", element: <FeatureGuard feature={FEATURES.QUIZ_EXAM}>{lazyPage(TestSessionPage)}</FeatureGuard> },
          { path: "study", element: <FeatureGuard feature={FEATURES.STUDY_ROOM}>{lazyPage(StudyRoom)}</FeatureGuard> },
          { path: "xiaoyu", element: lazyPage(XiaoYu) },
          { path: "xiaoyu/practice/:sessionId", element: lazyPage(PracticeSession) },
          { path: "plan", element: <FeatureGuard feature={FEATURES.AI_ASSISTANT}>{lazyPage(StudyPlan)}</FeatureGuard> },
          { path: "knowledge-map", element: <FeatureGuard feature={FEATURES.KNOWLEDGE_GRAPH}>{lazyPage(KnowledgeMap)}</FeatureGuard> },
          { path: "knowledge-map/node/:id", element: <FeatureGuard feature={FEATURES.KNOWLEDGE_GRAPH}>{lazyPage(KnowledgeNodeDetail)}</FeatureGuard> },
          { path: "settings", element: lazyPage(Settings) },
          { path: "billing", element: lazyPage(BillingPage) },
          { path: "system-settings", element: <RequireAdmin>{lazyPage(SystemSettings)}</RequireAdmin> },
          { path: "management", element: <RequireAdmin>{lazyPage(Maintenance)}</RequireAdmin> },
          { path: "course/:id", element: <FeatureGuard feature={FEATURES.COURSE_VIDEO}>{lazyPage(VideoLesson)}</FeatureGuard> },
          { path: "tests/review", element: <FeatureGuard feature={FEATURES.WRONG_REVIEW}>{lazyPage(WrongQuestionReviewPage)}</FeatureGuard> },
          { path: "my-assignments", element: lazyPage(MyAssignments) },
          { path: "achievements", element: lazyPage(Achievements) },

          { path: "report-card", element: lazyPage(ReportCard) },
          { path: "mock-exam", element: <FeatureGuard feature={FEATURES.PDF_MOCK}>{lazyPage(PdfMockExam)}</FeatureGuard> },
          { path: "exam/:examId", element: lazyPage(OnlineExam) },

          { path: "workbench", element: <RequireInstitution>{lazyPage(Workbench)}</RequireInstitution> },
          { path: "assets", element: <RequireInstitution>{lazyPage(AssetHub)}</RequireInstitution> },
          { path: "knowledge-tree", element: <RequireInstitution>{lazyPage(TeacherKnowledgeTree)}</RequireInstitution> },
          { path: "questions", element: <RequireInstitution>{lazyPage(TeacherQuestions)}</RequireInstitution> },
          { path: "institution", element: <RequireInstitution>{lazyPage(InstitutionDashboard)}</RequireInstitution> },
          { path: "institution/students", element: <RequireInstitution>{lazyPage(InstitutionStudents)}</RequireInstitution> },
          { path: "gradebook", element: <RequireInstitution>{lazyPage(Gradebook)}</RequireInstitution> },
          { path: "teacher-assignments", element: <RequireInstitution>{lazyPage(TeacherAssignments)}</RequireInstitution> },
          { path: "lesson-plans", element: <RequireInstitution><FeatureGuard feature={FEATURES.TEACHING_PLANS}>{lazyPage(LessonPlans)}</FeatureGuard></RequireInstitution> },
          { path: "marketplace", element: <RequireInstitution>{lazyPage(Marketplace)}</RequireInstitution> },
          { path: "api-platform", element: <RequireInstitution><FeatureGuard feature={FEATURES.API_ACCESS}>{lazyPage(APIPlatform)}</FeatureGuard></RequireInstitution> },
          { path: "institution/admin", element: <RequireAdmin>{lazyPage(InstitutionAdmin)}</RequireAdmin> },
          { path: "institution/audit-logs", element: <RequireAdmin>{lazyPage(AuditLogs)}</RequireAdmin> },
          { path: "invite-codes", element: <RequirePlatformAdmin>{lazyPage(InviteCodeAdmin)}</RequirePlatformAdmin> },
          { path: "prompt-templates", element: <RequirePlatformAdmin>{lazyPage(PromptTemplatesAdmin)}</RequirePlatformAdmin> },
          { path: "platform", element: <RequirePlatformAdmin>{lazyPage(PlatformAdmin)}</RequirePlatformAdmin> },
          { path: "*", element: lazyPage(NotFound) },
        ],
      },
    ],
  },
  { path: "/join/:invite_slug", element: lazyPage(JoinPage) },
  { path: "/intro/:slug", element: lazyPage(InstitutionHome) },
  { path: "/intro", element: <Navigate to="/" replace /> },
  { path: "/en", element: <LanguageRedirect lang="en" /> },
  { path: "/zh", element: <LanguageRedirect lang="zh" /> },
  { path: "/pricing", element: lazyPage(PricingPage) },
  { path: "/promo/plus", element: lazyPage(PromoPlus) },
  { path: "/memorix", element: lazyPage(MemorixPage) },
  { path: "/login", element: lazyPage(Login) },
  { path: "/register", element: lazyPage(Register) },
  { path: "/verify-code", element: lazyPage(VerifyCode) },
  { path: "/privacy", element: lazyPage(Legal) },
  { path: "/terms", element: lazyPage(Legal) },
  { path: "/diagnostic", element: <RequireAuth>{lazyPage(DiagnosticTest)}</RequireAuth> },
  { path: "/checkout", element: <RequireAuth>{lazyPage(Checkout)}</RequireAuth> },
  { path: "/payments/result", element: <RequireAuth>{lazyPage(PaymentResult)}</RequireAuth> },
  { path: "*", element: lazyPage(NotFound) },
]);

function StudyRoomWsBridge() {
  const user = useAuthStore(s => s.user);
  const features = useInstitutionStore(s => s.features);
  const isPlatformAdmin = useInstitutionStore(s => s.isPlatformAdmin);
  const enabled = !!user && (
    isPlatformAdmin || features.includes(FEATURES.STUDY_ROOM)
  );
  useStudyRoomWs(enabled);
  return null;
}

function XiaoYuEngineBridge() {
  const user = useAuthStore(s => s.user);
  const enabled = !!user;
  useXiaoYuEngine({ enabled });
  return null;
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ErrorBoundary>
        <Toaster position="top-center" richColors />
        <Suspense fallback={null}>
          <NPSSurvey />
        </Suspense>
        <OnboardingOverlay />
        <XiaoYuEngineBridge />
        <StudyRoomWsBridge />
        <RouterProvider router={router} />
        <FeedbackButton />
      </ErrorBoundary>
    </QueryClientProvider>
  );
}

function OnboardingOverlay() {
  const hasHydrated = useAuthStore.persist.hasHydrated();
  if (!hasHydrated) return null;
  return <OnboardingDialog mandatory />;
}

export default App;
