import { createBrowserRouter, RouterProvider, Navigate, Outlet, useNavigate, useLocation } from 'react-router-dom';
import { lazy, Suspense, useEffect, type ReactNode } from 'react';
import { QueryClientProvider } from '@tanstack/react-query';
import { useQuery } from '@tanstack/react-query';
import { queryClient } from '@/lib/queryClient';
import { queryKeys } from '@/lib/queryKeys';
import { HOME_PATH, getLoginPath } from '@/lib/routing';
import { useStudyRoomWs } from '@/hooks/useStudyRoomWs';
import { useXiaoYuEngine } from '@/hooks/useXiaoYuEngine';
import { FEATURES } from './store/useInstitutionStore';
const MainLayout = lazy(() => import('./layouts/MainLayout').then(m => ({ default: m.MainLayout })));
const CommunityLayout = lazy(() => import('./layouts/CommunityLayout').then(m => ({ default: m.CommunityLayout })));
const CommunityEntry = lazy(() => import('./layouts/CommunityLayout').then(m => ({ default: m.CommunityEntry })));
import { useAuthStore } from './store/useAuthStore';
import { useSystemStore } from './store/useSystemStore';
import { useInstitutionStore } from './store/useInstitutionStore';
import { FeatureGuard } from './components/FeatureGuard';
import { Loading } from '@/components/Loading';
import api from '@/lib/api';
import { Toaster } from 'sonner';
import { ErrorBoundary } from '@/components/ErrorBoundary';

const NPSSurvey = lazy(() => import('./components/NPSSurvey').then(m => ({ default: m.NPSSurvey })));
import { FeedbackButton } from './components/FeedbackButton';


// Lazy-loaded pages — named exports need .then() wrapper
const Landing = lazy(() => import('./pages/Landing').then(module => ({ default: module.Landing })));
const CourseCenter = lazy(() => import('./pages/CourseCenter').then(module => ({ default: module.CourseCenter })));
const TestLadder = lazy(() => import('./pages/TestLadder').then(module => ({ default: module.TestLadder })));
const StudyRoom = lazy(() => import('./pages/StudyRoom').then(module => ({ default: module.StudyRoom })));
const Settings = lazy(() => import('./pages/Settings').then(module => ({ default: module.Settings })));
const Login = lazy(() => import('./pages/Login').then(module => ({ default: module.Login })));
const AccountCallback = lazy(() => import('./pages/AccountCallback').then(module => ({ default: module.AccountCallback })));
const Register = lazy(() => import('./pages/Register').then(module => ({ default: module.Register })));
const VerifyCode = lazy(() => import('./pages/VerifyCode').then(module => ({ default: module.VerifyCode })));
const QASystem = lazy(() => import('./pages/QASystem').then(module => ({ default: module.QASystem })));
const QuestionDetail = lazy(() => import('./pages/QASystem').then(module => ({ default: module.QuestionDetail })));
const TestSessionPage = lazy(() => import('./pages/TestSessionPage').then(module => ({ default: module.TestSessionPage })));
const ExamResultPage = lazy(() => import('./pages/ExamResultPage').then(module => ({ default: module.ExamResultPage })));
const ExamHistoryPage = lazy(() => import('./pages/ExamHistoryPage').then(module => ({ default: module.ExamHistoryPage })));

const WrongQuestionReviewPage = lazy(() => import('./pages/WrongQuestionReviewPage').then(module => ({ default: module.WrongQuestionReviewPage })));
const ReportCard = lazy(() => import('./pages/ReportCard').then(module => ({ default: module.ReportCard })));
const Achievements = lazy(() => import('./pages/Achievements').then(module => ({ default: module.Achievements })));

const BillingPage = lazy(() => import('./pages/Billing').then(module => ({ default: module.BillingPage })));
const PaymentResult = lazy(() => import('./pages/PaymentResult').then(module => ({ default: module.PaymentResult })));
const Checkout = lazy(() => import('./pages/Checkout').then(module => ({ default: module.Checkout })));
const DiagnosticTest = lazy(() => import('./pages/DiagnosticTest').then(module => ({ default: module.DiagnosticTest })));
const XiaoYu = lazy(() => import('./pages/XiaoYu').then(module => ({ default: module.XiaoYu })));
const NotesPage = lazy(() => import('./pages/notes/NotesPage'));
const PracticeSession = lazy(() => import('./pages/xiaoyu/PracticeSession'));

// Default exports — plain lazy() works
const MemorixPage = lazy(() => import('./pages/Memorix'));
const JoinPage = lazy(() => import('./pages/JoinPage').then(module => ({ default: module.JoinPage })));
const NotFound = lazy(() => import('./pages/NotFound'));

const Legal = lazy(() => import('./pages/Legal'));
const PricingPage = lazy(() => import('./pages/Pricing'));


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

// Auth Guard — RootRedirect already handles auth validation; here we just gate.
const RequireAuth = ({ children }: { children: ReactNode }) => {
  const user = useAuthStore(s => s.user);
  const location = useLocation();
  const { theme, setTheme } = useSystemStore();

  useEffect(() => {
    if (user && theme !== 'light') {
      setTheme('light');
    }
    // PWA push subscription — deferred to avoid blocking render
    if (user) {
      const timer = setTimeout(() => {
        import('@/lib/pushSubscription').then(m => m.subscribeToPush()).catch(() => {});
      }, 3000);
      return () => clearTimeout(timer);
    }
  }, [user, theme, setTheme]);

  if (!user) return <Navigate to={getLoginPath(location.pathname + location.search + location.hash)} replace />;
  return children;
};

const HomeRedirect = () => <Navigate to={HOME_PATH} replace />;

const LegacyRedirect = ({ to }: { to: string }) => {
  const { search, hash } = useLocation();
  return <Navigate to={{ pathname: to, search, hash }} replace />;
};

const legacyRoutes = [
  ['workbench/*', HOME_PATH],
  ['assets/*', HOME_PATH],
  ['knowledge-tree/*', HOME_PATH],
  ['knowledge-map/*', HOME_PATH],
  ['learning-products/*', HOME_PATH],
  ['articles/*', HOME_PATH],
  ['article/*', HOME_PATH],
  ['management/*', HOME_PATH],
  ['institution/*', HOME_PATH],
  ['api-platform/*', HOME_PATH],
  ['invite-codes/*', HOME_PATH],
  ['prompt-templates/*', HOME_PATH],
  ['platform/*', HOME_PATH],
  ['platform-analytics/*', HOME_PATH],
  ['questions/*', '/tests'],
  ['courses/manage/*', '/courses'],
  ['marketplace/*', '/courses'],
  ['system-settings/*', '/settings'],
];

const RootRedirect = () => {

  const setAuth = useAuthStore(s => s.setAuth);
  const logout = useAuthStore(s => s.logout);
  const hasHydrated = useAuthStore.persist.hasHydrated();
  const navigate = useNavigate();
  const location = useLocation();

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
    if (location.pathname !== '/') return;
    api.get('/users/check-invite/')
      .then(res => {
        if (res.data?.has_invite) navigate('/register', { replace: true });
      })
      .catch(() => {});
  }, [isError, logout, navigate, location.pathname]);

  if (!hasHydrated || isLoading) return <Loading message="Authenticating Secure Session…" fullScreen size="lg" />;

  if (userData) return <Outlet />;

  if (location.pathname !== '/') return <Navigate to={getLoginPath(location.pathname + location.search + location.hash)} replace />;

  return <Suspense fallback={<div className="min-h-dvh bg-[#080b0f]" aria-hidden="true" />}><Landing /></Suspense>;
};

const lazyPage = (Component: React.ComponentType) => (
  <ErrorBoundary>
    <Suspense fallback={<PageLoader />}><Component /></Suspense>
  </ErrorBoundary>
);

const router = createBrowserRouter([
  ...legacyRoutes.map(([path, to]) => ({ path, element: <LegacyRedirect to={to} /> })),
  {
    path: "/",
    element: <RootRedirect />,
    children: [
      { index: true, element: <HomeRedirect /> },
      {
        element: <RequireAuth><Suspense fallback={<PageLoader />}><MainLayout /></Suspense></RequireAuth>,
        children: [
          { path: "courses", element: <FeatureGuard feature={FEATURES.COURSE_VIDEO}>{lazyPage(CourseCenter)}</FeatureGuard> },
          {
            element: lazyPage(CommunityLayout),
            children: [
              { path: "community", element: lazyPage(CommunityEntry) },
              { path: "qa", element: <FeatureGuard feature={FEATURES.FAQ_SYSTEM}>{lazyPage(QASystem)}</FeatureGuard> },
              { path: "qa/:id", element: <FeatureGuard feature={FEATURES.FAQ_SYSTEM}>{lazyPage(QuestionDetail)}</FeatureGuard> },
              { path: "study", element: <FeatureGuard feature={FEATURES.STUDY_ROOM}>{lazyPage(StudyRoom)}</FeatureGuard> },
            ],
          },
          { path: "tests", element: <FeatureGuard feature={FEATURES.QUIZ_EXAM}>{lazyPage(TestLadder)}</FeatureGuard> },
          { path: "tests/session", element: <FeatureGuard feature={FEATURES.QUIZ_EXAM}>{lazyPage(TestSessionPage)}</FeatureGuard> },
          { path: "tests/results/:examId", element: <FeatureGuard feature={FEATURES.QUIZ_EXAM}>{lazyPage(ExamResultPage)}</FeatureGuard> },
          { path: "tests/history", element: <FeatureGuard feature={FEATURES.QUIZ_EXAM}>{lazyPage(ExamHistoryPage)}</FeatureGuard> },
          { path: "notes", element: lazyPage(NotesPage) },
          { path: "notes/:id", element: lazyPage(NotesPage) },
          { path: "xiaoyu", element: <FeatureGuard feature="ai.assistant">{lazyPage(XiaoYu)}</FeatureGuard> },
          { path: "xiaoyu/practice/:sessionId", element: <FeatureGuard feature="ai.assistant">{lazyPage(PracticeSession)}</FeatureGuard> },
          { path: "settings", element: lazyPage(Settings) },
          { path: "billing", element: lazyPage(BillingPage) },
          { path: "course/:id", element: <FeatureGuard feature={FEATURES.COURSE_VIDEO}>{lazyPage(CourseCenter)}</FeatureGuard> },
          { path: "tests/review", element: <FeatureGuard feature={FEATURES.WRONG_REVIEW}>{lazyPage(WrongQuestionReviewPage)}</FeatureGuard> },
          { path: "achievements", element: lazyPage(Achievements) },

          { path: "report-card", element: <FeatureGuard feature={FEATURES.FULL_REPORT}>{lazyPage(ReportCard)}</FeatureGuard> },

          { path: "*", element: lazyPage(NotFound) },
        ],
      },
    ],
  },
  { path: "/join/:invite_slug", element: lazyPage(JoinPage) },
  { path: "/intro/:slug", element: <Navigate to="/" replace /> },
  { path: "/intro", element: <Navigate to="/" replace /> },
  { path: "/pricing", element: lazyPage(PricingPage) },
  { path: "/promo/plus", element: <Navigate to="/pricing" replace /> },
  { path: "/memorix", element: lazyPage(MemorixPage) },
  { path: "/login", element: lazyPage(Login) },
  { path: "/account-callback", element: lazyPage(AccountCallback) },
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
        <XiaoYuEngineBridge />
        <StudyRoomWsBridge />
        <RouterProvider router={router} />
        <FeedbackButton />
      </ErrorBoundary>
    </QueryClientProvider>
  );
}

export default App;
