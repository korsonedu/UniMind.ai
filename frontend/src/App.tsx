import { createBrowserRouter, RouterProvider, Navigate, Outlet, useLocation, useNavigate } from 'react-router-dom';
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
import { WeeklyReportDialog } from './components/WeeklyReportDialog';
import { Landing } from './pages/Landing';
import i18n from '@/lib/i18n';

// Lazy-loaded pages — named exports need .then() wrapper
const lazyNamed = <T extends Record<string, React.ComponentType<any>>>(loader: () => Promise<T>, name: keyof T) =>
  lazy(() => loader().then(m => ({ default: m[name] })));

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
const AIAssistant = lazyNamed(() => import('./pages/AIAssistant'), 'AIAssistant');
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

// Default exports — plain lazy() works
const InstitutionDashboard = lazy(() => import('./pages/InstitutionDashboard'));
const InstitutionStudents = lazy(() => import('./pages/InstitutionStudents'));
const InstitutionAdmin = lazy(() => import('./pages/InstitutionAdmin'));
const InstitutionHome = lazy(() => import('./pages/InstitutionHome'));
const InviteCodeAdmin = lazy(() => import('./pages/InviteCodeAdmin'));
const NotFound = lazy(() => import('./pages/NotFound'));
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

// Auth Guard with Persistence
const RequireAuth = ({ children }: { children: ReactNode }) => {
  const { token, user, setAuth } = useAuthStore();
  const { theme, setTheme } = useSystemStore();
  const [loading, setLoading] = useState(!user && !!token);

  useEffect(() => {
    // Theme policy: dark mode beta is only for admins.
    if (user?.role === 'admin') {
      if (theme === 'dark') setTheme('dark');
    } else if (user && theme !== 'light') {
      setTheme('light');
    }

    if (!user && token) {
      api.get('/users/me/')
        .then(res => setAuth(res.data, token))
        .catch(() => {
          api.post('/users/logout/').catch(() => {});
          window.location.href = '/login';
        })
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, [user, token, theme, setTheme]);

  if (loading) return <Loading message="Synchronizing Secure Session…" fullScreen size="lg" />;

  if (!token) return <Navigate to="/login" replace />;
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
  if (!user) return <Navigate to="/login" replace />;
  if (isPlatformAdmin) return children;
  if (!institution?.id) return <Navigate to="/" replace />;
  // 机构管理员（owner / teacher）可访问管理类页面
  if (user.institution_role !== 'owner' && user.institution_role !== 'teacher' && !user.is_institution_admin && !user.is_admin) {
    return <Navigate to="/" replace />;
  }
  return children;
};

// 超管默认跳转到机构管理；Pro 机构有主页 → 主页，否则 → 课程中心
const HomeRedirect = () => {
  const { user } = useAuthStore();
  const institution = useInstitutionStore(s => s.institution);
  if (user?.role === 'admin' && !institution && !user?.institution) return <Navigate to="/institution/admin" replace />;
  if (institution?.plan === 'enterprise') return <Suspense fallback={<PageLoader />}><InstitutionHome /></Suspense>;
  return <Navigate to="/courses" replace />;
};

// Root entry handler to manage landing vs app logic
const RootRedirect = () => {
  const { token, user } = useAuthStore();
  const hasHydrated = useAuthStore.persist.hasHydrated();
  const [checkingInvite, setCheckingInvite] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    if (!hasHydrated) return;
    if (token || user) { setCheckingInvite(false); return; }
    const controller = new AbortController();
    api.get('/users/check-invite/', { signal: controller.signal })
      .then(res => {
        if (res.data?.has_invite) navigate('/register', { replace: true });
      })
      .catch(() => {})
      .finally(() => setCheckingInvite(false));
    return () => controller.abort();
  }, [token, user, hasHydrated]);

  if (!hasHydrated || checkingInvite) return <Loading message="Authenticating Secure Session…" fullScreen size="lg" />;

  // Token exists → let RequireAuth handle user fetching, render page immediately
  if (token) return <Outlet />;

  return <Landing />;
};

const lazyPage = (Component: React.ComponentType) => (
  <Suspense fallback={<PageLoader />}><Component /></Suspense>
);

const router = createBrowserRouter([
  {
    path: "/",
    element: <RootRedirect />,
    children: [
      { index: true, element: <RequireAuth><HomeRedirect /></RequireAuth> },
      {
        element: <RequireAuth><MainLayout /></RequireAuth>,
        children: [
          { path: "courses", element: lazyPage(CourseCenter) },
          { path: "articles", element: lazyPage(ArticleCenter) },
          { path: "qa", element: <FeatureGuard feature={FEATURES.FAQ_SYSTEM}>{lazyPage(QASystem)}</FeatureGuard> },
          { path: "article/:id", element: lazyPage(ArticleDetail) },
          { path: "tests", element: <FeatureGuard feature={FEATURES.QUIZ_EXAM}>{lazyPage(TestLadder)}</FeatureGuard> },
          { path: "tests/session", element: <FeatureGuard feature={FEATURES.QUIZ_EXAM}>{lazyPage(TestSessionPage)}</FeatureGuard> },
          { path: "study", element: <FeatureGuard feature={FEATURES.STUDY_ROOM}>{lazyPage(StudyRoom)}</FeatureGuard> },
          { path: "ai", element: <FeatureGuard feature={FEATURES.AI_ASSISTANT}>{lazyPage(AIAssistant)}</FeatureGuard> },
          { path: "knowledge-map", element: <FeatureGuard feature={FEATURES.KNOWLEDGE_GRAPH}>{lazyPage(KnowledgeMap)}</FeatureGuard> },
          { path: "knowledge-map/node/:id", element: <FeatureGuard feature={FEATURES.KNOWLEDGE_GRAPH}>{lazyPage(KnowledgeNodeDetail)}</FeatureGuard> },
          { path: "settings", element: lazyPage(Settings) },
          { path: "billing", element: lazyPage(BillingPage) },
          { path: "system-settings", element: <RequireAdmin>{lazyPage(SystemSettings)}</RequireAdmin> },
          { path: "management", element: <RequireAdmin>{lazyPage(Maintenance)}</RequireAdmin> },
          { path: "course/:id", element: <FeatureGuard feature={FEATURES.COURSE_VIDEO}>{lazyPage(VideoLesson)}</FeatureGuard> },
          { path: "tests/review", element: <FeatureGuard feature={FEATURES.WRONG_REVIEW}>{lazyPage(WrongQuestionReviewPage)}</FeatureGuard> },
          { path: "mock-exam", element: <FeatureGuard feature={FEATURES.PDF_MOCK}>{lazyPage(PdfMockExam)}</FeatureGuard> },

          { path: "institution", element: <RequireInstitution>{lazyPage(InstitutionDashboard)}</RequireInstitution> },
          { path: "institution/students", element: <RequireInstitution>{lazyPage(InstitutionStudents)}</RequireInstitution> },
          { path: "institution/admin", element: <RequireAdmin>{lazyPage(InstitutionAdmin)}</RequireAdmin> },
          { path: "invite-codes", element: <RequirePlatformAdmin>{lazyPage(InviteCodeAdmin)}</RequirePlatformAdmin> },
          { path: "prompt-templates", element: <RequirePlatformAdmin>{lazyPage(PromptTemplatesAdmin)}</RequirePlatformAdmin> },
          { path: "*", element: lazyPage(NotFound) },
        ],
      },
    ],
  },
  { path: "/intro/:slug", element: lazyPage(InstitutionHome) },
  { path: "/intro", element: <Navigate to="/" replace /> },
  { path: "/en", element: <LanguageRedirect lang="en" /> },
  { path: "/zh", element: <LanguageRedirect lang="zh" /> },
  { path: "/pricing", element: lazyPage(PricingPage) },
  { path: "/promo/plus", element: lazyPage(PromoPlus) },
  { path: "/login", element: lazyPage(Login) },
  { path: "/register", element: lazyPage(Register) },
  { path: "/checkout", element: <RequireAuth>{lazyPage(Checkout)}</RequireAuth> },
  { path: "/payments/result", element: <RequireAuth>{lazyPage(PaymentResult)}</RequireAuth> },
  { path: "*", element: lazyPage(NotFound) },
]);

function App() {
  return (
    <>
      <Toaster position="top-center" richColors />
      <WeeklyReportDialog />
      <RouterProvider router={router} />
    </>
  );
}

export default App;
