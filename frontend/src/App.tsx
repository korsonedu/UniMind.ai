import { createBrowserRouter, RouterProvider, Navigate, Outlet, useNavigate } from 'react-router-dom';
import { lazy, Suspense, useState, useEffect, type ReactNode } from 'react';
import { MainLayout } from './layouts/MainLayout';
import { useAuthStore } from './store/useAuthStore';
import { useSystemStore } from './store/useSystemStore';
import { useInstitutionStore } from './store/useInstitutionStore';
import { FeatureGuard } from './components/FeatureGuard';
import { FEATURES } from './store/useInstitutionStore';
import { Loading } from '@/components/Loading';
import api from '@/lib/api';
import { Toaster } from 'sonner';
import i18n from '@/lib/i18n';
import { ErrorBoundary } from '@/components/ErrorBoundary';

const WeeklyReportDialog = lazy(() => import('./components/WeeklyReportDialog').then(m => ({ default: m.WeeklyReportDialog })));
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
const BillingPage = lazyNamed(() => import('./pages/Billing'), 'BillingPage');
const PaymentResult = lazyNamed(() => import('./pages/PaymentResult'), 'PaymentResult');
const Checkout = lazyNamed(() => import('./pages/Checkout'), 'Checkout');
const DiagnosticTest = lazyNamed(() => import('./pages/DiagnosticTest'), 'DiagnosticTest');
const StudyPlan = lazyNamed(() => import('./pages/StudyPlan'), 'StudyPlan');
const StudentHome = lazyNamed(() => import('./pages/StudentHome'), 'StudentHome');
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
const PlatformAnalytics = lazyNamed(() => import('./pages/PlatformAnalytics'), 'PlatformAnalytics');
const JoinPage = lazyNamed(() => import('./pages/JoinPage'), 'JoinPage');
const NotFound = lazy(() => import('./pages/NotFound'));
const MyAssignments = lazy(() => import('./pages/MyAssignments'));
const CourseManage = lazy(() => import('./pages/CourseManage'));
const ArticleManage = lazy(() => import('./pages/ArticleManage'));
const AuditLogs = lazy(() => import('./pages/AuditLogs'));
const Legal = lazy(() => import('./pages/Legal'));
const PricingPage = lazy(() => import('./pages/Pricing'));
const PromoPlus = lazy(() => import('./pages/PromoPlus'));

const PageLoader = () => <Loading fullScreen size="lg" />;

// Language redirect helper
const LanguageRedirect = ({ lang }: { lang: string }) => {
  useEffect(() => {
    i18n.changeLanguage(lang);
  }, [lang]);
  return <Navigate to="/" replace />;
};

// Auth Guard — RootRedirect already handles auth validation; here we just gate.
const RequireAuth = ({ children }: { children: ReactNode }) => {
  const { user } = useAuthStore();
  const { theme, setTheme } = useSystemStore();

  useEffect(() => {
    if (user?.role === 'admin') {
      if (theme === 'dark') setTheme('dark');
    } else if (user && theme !== 'light') {
      setTheme('light');
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
  const { user, setAuth, logout } = useAuthStore();
  const hasHydrated = useAuthStore.persist.hasHydrated();
  const [checking, setChecking] = useState(true);
  const [validUser, setValidUser] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    if (!hasHydrated) return;
    api.get('/users/me/')
      .then(res => {
        setAuth(res.data, null);
        setValidUser(true);
      })
      .catch(() => {
        logout();
        setValidUser(false);
        api.get('/users/check-invite/')
          .then(res => {
            if (res.data?.has_invite) navigate('/register', { replace: true });
          })
          .catch(() => {});
      })
      .finally(() => setChecking(false));
  }, [hasHydrated, setAuth, logout, navigate]);

  if (!hasHydrated || checking) return <Loading message="Authenticating Secure Session…" fullScreen size="lg" />;

  if (validUser) return <Outlet />;

  // korsonedu.com → 直接展示机构主页
  if (isKorsonedu) return <Suspense fallback={<PageLoader />}><InstitutionHome slug="korsonedu" /></Suspense>;

  return <Suspense fallback={<PageLoader />}><Landing /></Suspense>;
};

const lazyPage = (Component: React.ComponentType) => (
  <Suspense fallback={<PageLoader />}><Component /></Suspense>
);

const router = createBrowserRouter([
  {
    path: "/",
    element: <RootRedirect />,
    children: [
      { index: true, element: <HomeRedirect /> },
      {
        element: <RequireAuth><MainLayout /></RequireAuth>,
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
          { path: "home", element: lazyPage(StudentHome) },
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
          { path: "mock-exam", element: <FeatureGuard feature={FEATURES.PDF_MOCK}>{lazyPage(PdfMockExam)}</FeatureGuard> },

          { path: "workbench", element: <RequireInstitution>{lazyPage(Workbench)}</RequireInstitution> },
          { path: "assets", element: <RequireInstitution>{lazyPage(AssetHub)}</RequireInstitution> },
          { path: "knowledge-tree", element: <RequireInstitution>{lazyPage(TeacherKnowledgeTree)}</RequireInstitution> },
          { path: "questions", element: <RequireInstitution>{lazyPage(TeacherQuestions)}</RequireInstitution> },
          { path: "institution", element: <RequireInstitution>{lazyPage(InstitutionDashboard)}</RequireInstitution> },
          { path: "institution/students", element: <RequireInstitution>{lazyPage(InstitutionStudents)}</RequireInstitution> },
          { path: "institution/admin", element: <RequireAdmin>{lazyPage(InstitutionAdmin)}</RequireAdmin> },
          { path: "institution/audit-logs", element: <RequireAdmin>{lazyPage(AuditLogs)}</RequireAdmin> },
          { path: "invite-codes", element: <RequirePlatformAdmin>{lazyPage(InviteCodeAdmin)}</RequirePlatformAdmin> },
          { path: "prompt-templates", element: <RequirePlatformAdmin>{lazyPage(PromptTemplatesAdmin)}</RequirePlatformAdmin> },
          { path: "platform-analytics", element: <RequirePlatformAdmin>{lazyPage(PlatformAnalytics)}</RequirePlatformAdmin> },
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
  { path: "/privacy", element: lazyPage(Legal) },
  { path: "/terms", element: lazyPage(Legal) },
  { path: "/diagnostic", element: <RequireAuth>{lazyPage(DiagnosticTest)}</RequireAuth> },
  { path: "/checkout", element: <RequireAuth>{lazyPage(Checkout)}</RequireAuth> },
  { path: "/payments/result", element: <RequireAuth>{lazyPage(PaymentResult)}</RequireAuth> },
  { path: "*", element: lazyPage(NotFound) },
]);

function App() {
  return (
    <ErrorBoundary>
      <Toaster position="top-center" richColors />
      <Suspense fallback={null}>
        <WeeklyReportDialog />
        <NPSSurvey />
      </Suspense>
      <OnboardingOverlay />
      <RouterProvider router={router} />
      <FeedbackButton />
    </ErrorBoundary>
  );
}

function OnboardingOverlay() {
  const hasHydrated = useAuthStore.persist.hasHydrated();
  if (!hasHydrated) return null;
  return <OnboardingDialog mandatory />;
}

export default App;
