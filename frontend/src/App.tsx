import { activeWorkspace } from '@/lib/activeWorkspace';
import { useXiaoYuChat } from '@/pages/xiaoyu/xiaoYuChatContext';
import { OfflineTrialPage } from '@/components/OfflineTrialPage';
import { getLocale, t, useLocale } from '@/i18n';
import { saveLanguagePreference } from '@/lib/languagePreference';
import { createBrowserRouter, RouterProvider, Navigate, Outlet, useLocation, useParams, useSearchParams } from 'react-router-dom';
import { lazy, Suspense, useCallback, useEffect, useState, type ReactNode } from 'react';
import { registerSW } from 'virtual:pwa-register';
import axios from 'axios';
import { QueryClientProvider } from '@tanstack/react-query';
import { useQuery } from '@tanstack/react-query';
import { queryClient } from '@/lib/queryClient';
import { queryKeys } from '@/lib/queryKeys';
import { HOME_PATH, getLoginPath } from '@/lib/routing';
import { FEATURES } from './store/useInstitutionStore';
const MainLayout = lazy(() => import('./layouts/MainLayout').then(m => ({ default: m.MainLayout })));
import { useAuthStore } from './store/useAuthStore';
import { useInstitutionStore } from './store/useInstitutionStore';
import { FeatureGuard } from './components/FeatureGuard';
import { Loading } from '@/components/Loading';
import { PageLoader } from '@/components/PageLoader';
import api from '@/lib/api';
import { Toaster, toast } from 'sonner';
import { App as NativeApp } from '@capacitor/app';
import { keepNativeSession } from '@/lib/offlineSession';
import { isNativePlatform } from '@/lib/serverConfig';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { XiaoYuChatHost } from './pages/xiaoyu/XiaoYuChatProvider';
import { useWorkspace } from '@/lib/workspace';

let serviceWorkerRegistered = false;

// Lazy-loaded pages — named exports need .then() wrapper
const Landing = lazy(() => import('./pages/Landing').then(module => ({ default: module.Landing })));
const CourseCenter = lazy(() => import('./pages/CourseCenter').then(module => ({ default: module.CourseCenter })));
const VideoLesson = lazy(() => import('./pages/VideoLesson').then(module => ({ default: module.VideoLesson })));
const TestLadder = lazy(() => import('./pages/TestLadder').then(module => ({ default: module.TestLadder })));
const InstitutionManagement = lazy(() => import('./pages/InstitutionManagement'));
const Settings = lazy(() => import('./pages/Settings').then(module => ({ default: module.Settings })));
const Login = lazy(() => import('./pages/Login').then(module => ({ default: module.Login })));
const DesktopAuthorize = lazy(() => import('./pages/DesktopAuthorize').then(module => ({ default: module.DesktopAuthorize })));
const AccountCallback = lazy(() => import('./pages/AccountCallback').then(module => ({ default: module.AccountCallback })));
const Register = lazy(() => import('./pages/Register').then(module => ({ default: module.Register })));
const VerifyCode = lazy(() => import('./pages/VerifyCode').then(module => ({ default: module.VerifyCode })));
const TestSessionPage = lazy(() => import('./pages/TestSessionPage').then(module => ({ default: module.TestSessionPage })));
const ExamResultPage = lazy(() => import('./pages/ExamResultPage').then(module => ({ default: module.ExamResultPage })));
const ExamHistoryPage = lazy(() => import('./pages/ExamHistoryPage').then(module => ({ default: module.ExamHistoryPage })));

const WrongQuestionReviewPage = lazy(() => import('./pages/WrongQuestionReviewPage').then(module => ({ default: module.WrongQuestionReviewPage })));

const BillingPage = lazy(() => import('./pages/Billing').then(module => ({ default: module.BillingPage })));
const PaymentResult = lazy(() => import('./pages/PaymentResult').then(module => ({ default: module.PaymentResult })));
const Checkout = lazy(() => import('./pages/Checkout').then(module => ({ default: module.Checkout })));
const DiagnosticTest = lazy(() => import('./pages/DiagnosticTest').then(module => ({ default: module.DiagnosticTest })));
const KnowledgeBuilder = lazy(() => import('./pages/KnowledgeBuilder'));
const NotesPage = lazy(() => import('./pages/notes/NotesPage'));
const PracticeSession = lazy(() => import('./pages/xiaoyu/PracticeSession'));
const ProjectKnowledge = lazy(() => import('./pages/ProjectKnowledge'));
const XiaoYu = lazy(() => import('./pages/XiaoYu').then(module => ({ default: module.XiaoYu })));

// Default exports — plain lazy() works
const MemorixPage = lazy(() => import('./pages/Memorix'));
const NotFound = lazy(() => import('./pages/NotFound'));

const Legal = lazy(() => import('./pages/Legal'));
const PricingPage = lazy(() => import('./pages/Pricing'));

// Auth Guard — RootRedirect already handles auth validation; here we just gate.
const RequireAuth = ({ children }: { children: ReactNode }) => {
  const user = useAuthStore(s => s.user);
  const location = useLocation();
  useEffect(() => {
    // PWA push subscription — deferred to avoid blocking render
    if (user && !isNativePlatform()) {
      if (!serviceWorkerRegistered) {
        serviceWorkerRegistered = true;
        registerSW({ immediate: true });
      }
      const timer = setTimeout(() => {
        import('@/lib/pushSubscription').then(m => m.subscribeToPush()).catch(() => {});
      }, 3000);
      return () => clearTimeout(timer);
    }
  }, [user]);

  if (!user) return <Navigate to={getLoginPath(location.pathname + location.search + location.hash)} replace />;
  return children;
};

const HomeRedirect = () => <Navigate to={HOME_PATH} replace />;

const LegacyRedirect = ({ to }: { to: string }) => {
  const { search, hash } = useLocation();
  return <Navigate to={{ pathname: to, search, hash }} replace />;
};

const KnowledgeBuilderRedirect = () => {
  const { pathname, search, hash } = useLocation();
  return <Navigate to={{ pathname: `/xiaoyu${pathname}`, search, hash }} replace />;
};

const legacyRoutes = [
  ['workbench/*', HOME_PATH],
  ['assets/*', HOME_PATH],
  ['community/*', HOME_PATH],
  ['study/*', HOME_PATH],
  ['qa/*', HOME_PATH],
  ['achievements', HOME_PATH],
  ['report-card', HOME_PATH],
  ['knowledge-map/*', '/knowledge-tree'],
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
  useLocale();

  const storeUser = useAuthStore(s => s.user);
  const setAuth = useAuthStore(s => s.setAuth);
  const logout = useAuthStore(s => s.logout);
  const tokenHydrated = useAuthStore(s => s.tokenHydrated);
  const nativeToken = useAuthStore(s => s.token);
  const demoActive = useAuthStore(s => s.demoActive);
  const hasHydrated = useAuthStore.persist.hasHydrated() && tokenHydrated;
  const location = useLocation();
  const [offlineAccess, setOfflineAccess] = useState<{ userId: number; error: unknown } | null>(null);

  const { data: userData, isLoading, isError, error } = useQuery({
    queryKey: queryKeys.user.me,
    queryFn: ({ signal }) => api.get('/users/me/', { signal }).then(r => r.data),
    enabled: hasHydrated && !demoActive && (!isNativePlatform() || !!nativeToken),
    retry: false,
  });

  // Sync auth store with query result
  useEffect(() => {
    if (userData && !isError && !demoActive) {
      setAuth(userData);
      if (userData.preferred_language === '') {
        const language = getLocale();
        void saveLanguagePreference(language, userData.id).catch(() => {});
      }
    }
  }, [userData, isError, setAuth, demoActive]);

  // A network failure may keep the desktop offline session; only a 401 logs out.
  useEffect(() => {
    if (!isError || demoActive) return;
    if (keepNativeSession(isNativePlatform(), false, !!storeUser, !!nativeToken, axios.isAxiosError(error) ? error.response?.status : undefined)) return;
    const status = axios.isAxiosError(error) ? error.response?.status : undefined;
    const desktop = window.unimindDesktop;
    if (status === 401 || !desktop || !storeUser) {
      logout({ preserveDesktop: true });
      return;
    }
    let active = true;
    void desktop.getState().then(state => {
      if (!active) return;
      const session = state.offlineSession;
      if (session && session.userId === storeUser.id && session.expiresAt > Date.now()) setOfflineAccess({ userId: storeUser.id, error });
      else logout({ preserveDesktop: true });
    }).catch(() => { if (active) logout({ preserveDesktop: true }); });
    return () => { active = false; };
  }, [isError, error, logout, storeUser, nativeToken, demoActive]);

  // Anonymous visitors see the landing immediately; /users/me/ keeps validating in the background.
  const anonymousLanding = hasHydrated && !storeUser && location.pathname === '/' && !window.unimindDesktop && !isNativePlatform();

  if (hasHydrated && demoActive) return <Outlet />;
  if (hasHydrated && isError && keepNativeSession(isNativePlatform(), demoActive, !!storeUser, !!nativeToken, axios.isAxiosError(error) ? error.response?.status : undefined)) return <Outlet />;
  if (hasHydrated && isNativePlatform() && !nativeToken) return <Navigate to={getLoginPath(location.pathname + location.search + location.hash)} replace />;

  if (!hasHydrated || (isLoading && !anonymousLanding)) return <Loading message={t('正在验证登录状态…')} fullScreen size="lg" />;

  if (userData && !isError) {
    if (storeUser?.id !== userData.id) return <Loading message={t('正在验证登录状态…')} fullScreen size="lg" />;
    return <Outlet />;
  }

  if (isError && window.unimindDesktop && storeUser && !(axios.isAxiosError(error) && error.response?.status === 401)) {
    if (offlineAccess?.userId === storeUser.id && offlineAccess.error === error) return <Outlet />;
    return <Loading message={t('正在确认离线访问权限…')} fullScreen size="lg" />;
  }

  if (location.pathname !== '/') return <Navigate to={getLoginPath(location.pathname + location.search + location.hash)} replace />;
  if (window.unimindDesktop || isNativePlatform()) return <Navigate to="/login" replace />;

  return <Suspense fallback={<div className="min-h-dvh bg-[#080b0f]" aria-hidden="true" />}><Landing /></Suspense>;
};

// Keep the initial workspace hidden until its configuration and chat are ready.
const WorkspaceEntry = () => {
  const { pathname } = useLocation();
  const { chat, activate } = useXiaoYuChat();
  const { loading, hasFeature, fetchFeatures } = useInstitutionStore();
  const [entered, setEntered] = useState(false);
  const needsChat = pathname === '/xiaoyu' && hasFeature('ai.assistant');
  const waiting = loading || (needsChat && !chat.initialized);

  useEffect(() => {
    if (useInstitutionStore.getState().loading) void fetchFeatures();
  }, [fetchFeatures]);
  useEffect(() => {
    if (!loading && needsChat) activate();
  }, [loading, needsChat, activate]);
  const reveal = useCallback((node: HTMLDivElement | null) => {
    if (node) setEntered(true);
  }, []);

  return <RequireAuth>
    {!entered && <PageLoader />}
    <Suspense fallback={entered ? <PageLoader /> : null}>
      {(entered || !waiting) && <div className="contents" ref={reveal}><MainLayout /></div>}
    </Suspense>
  </RequireAuth>;
};

const workspacePage = (Component: React.ComponentType) => <ErrorBoundary><Component /></ErrorBoundary>;
const PersonalCourseRedirect = () => {
  const { data, isPending } = useWorkspace();
  const { pathname, key } = useLocation();
  const hasCourseSpace = data?.workspaces?.some(space => space.service_active);
  useEffect(() => {
    if (isPending) return;
    const message = hasCourseSpace
      ? pathname === '/courses'
        ? '请从左上角切换到课程空间，打开课程中心。'
        : '课程视频位于课程空间，请从左上角切换到对应课程空间查看。'
      : '请先加入可用的课程空间。';
    toast.info(t(message), { id: `course-space-${key}` });
  }, [hasCourseSpace, isPending, key, pathname]);
  return isPending ? <PageLoader /> : <Navigate to="/xiaoyu" replace />;
};
function InstitutionCourses() {
  const { id } = useParams();
  const [params] = useSearchParams();
  const project = Number(params.get('project'));
  if (activeWorkspace() !== 'personal') {
    return <FeatureGuard feature={FEATURES.COURSE_VIDEO}>{workspacePage(CourseCenter)}</FeatureGuard>;
  }
  if (id && Number.isSafeInteger(project) && project > 0) {
    return <ErrorBoundary><VideoLesson key={id} workbenchVideo missingCourse={<PersonalCourseRedirect />} /></ErrorBoundary>;
  }
  return <PersonalCourseRedirect />;
}

const lazyPage = (Component: React.ComponentType) => (
  <ErrorBoundary>
    <Suspense fallback={<PageLoader />}><Component /></Suspense>
  </ErrorBoundary>
);

const router = createBrowserRouter([
  {
    element: <XiaoYuChatHost />,
    children: [
  ...(import.meta.env.DEV ? [{ path: '/dev/dsh', element: lazyPage(lazy(() => import('./pages/DshM0'))) }] : []),
  { path: "/knowledge-builder/*", element: <KnowledgeBuilderRedirect /> },
  ...legacyRoutes.map(([path, to]) => ({ path, element: <LegacyRedirect to={to} /> })),
  {
    path: "/",
    element: <RootRedirect />,
    children: [
      { index: true, element: <HomeRedirect /> },
      {
        element: <WorkspaceEntry />,
        children: [
          { path: "courses", element: <InstitutionCourses /> },
          { path: "tests", element: <FeatureGuard feature={FEATURES.QUIZ_EXAM}>{workspacePage(TestLadder)}</FeatureGuard> },
          { path: "tests/session", element: <FeatureGuard feature={FEATURES.QUIZ_EXAM}>{workspacePage(TestSessionPage)}</FeatureGuard> },
          { path: "tests/results/:examId", element: <FeatureGuard feature={FEATURES.QUIZ_EXAM}>{workspacePage(ExamResultPage)}</FeatureGuard> },
          { path: "tests/history", element: <FeatureGuard feature={FEATURES.QUIZ_EXAM}>{workspacePage(ExamHistoryPage)}</FeatureGuard> },
          { path: "notes", element: workspacePage(NotesPage) },
          { path: "notes/:id", element: workspacePage(NotesPage) },
          { path: "practice", element: <RequireAuth><OfflineTrialPage /></RequireAuth> },
          { path: "calendar", element: <RequireAuth><OfflineTrialPage calendar /></RequireAuth> },
          { path: "knowledge-tree", element: <FeatureGuard feature="ai.assistant">{workspacePage(ProjectKnowledge)}</FeatureGuard> },
          { path: "xiaoyu/knowledge-builder", element: <FeatureGuard feature="ai.assistant">{workspacePage(KnowledgeBuilder)}</FeatureGuard> },
          { path: "xiaoyu/knowledge-builder/:buildId", element: <FeatureGuard feature="ai.assistant">{workspacePage(KnowledgeBuilder)}</FeatureGuard> },
          { path: "xiaoyu", element: <FeatureGuard feature="ai.assistant">{workspacePage(XiaoYu)}</FeatureGuard> },
          { path: "xiaoyu/practice/:sessionId", element: <FeatureGuard feature="ai.assistant">{workspacePage(PracticeSession)}</FeatureGuard> },
          { path: "settings", element: workspacePage(Settings) },
          { path: "settings/institution", element: workspacePage(InstitutionManagement) },
          { path: "billing", element: workspacePage(BillingPage) },
          { path: "course/:id", element: <InstitutionCourses /> },
          { path: "tests/review", element: <FeatureGuard feature={FEATURES.WRONG_REVIEW}>{workspacePage(WrongQuestionReviewPage)}</FeatureGuard> },
          { path: "*", element: workspacePage(NotFound) },
        ],
      },
    ],
  },
  { path: "/intro/:slug", element: <Navigate to="/" replace /> },
  { path: "/intro", element: <Navigate to="/" replace /> },
  { path: "/pricing", element: lazyPage(PricingPage) },
  { path: "/promo/plus", element: <Navigate to="/pricing" replace /> },
  { path: "/memorix", element: lazyPage(MemorixPage) },
  { path: "/desktop-auth", element: lazyPage(DesktopAuthorize) },
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
    ],
  },
]);

function App() {
  const hydrated = useAuthStore(state => state.tokenHydrated);
  useLocale();
  useEffect(() => {
    if (!isNativePlatform()) return;
    let lastBack = 0;
    const listener = NativeApp.addListener('backButton', () => {
      if (document.fullscreenElement) { void document.exitFullscreen(); return; }
      const active = document.activeElement;
      const keyboardOpen = document.querySelector('.um-app-shell[data-keyboard-open="true"]')
        || (window.visualViewport && window.innerHeight - window.visualViewport.height > 140);
      if (keyboardOpen && active instanceof HTMLElement && active.matches('input, textarea, [contenteditable="true"]')) { active.blur(); return; }
      const dialog = [...document.querySelectorAll<HTMLElement>('[role="dialog"][data-state="open"], [role="alertdialog"][data-state="open"]')].at(-1);
      if (dialog) {
        dialog.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }));
        return;
      }
      const close = document.querySelector<HTMLButtonElement>('[data-native-back-close]');
      if (close) { close.click(); return; }
      const route = router.state.location.pathname;
      if (route !== HOME_PATH && route !== '/login' && window.history.state?.idx > 0) { void router.navigate(-1); return; }
      if (Date.now() - lastBack < 2000) { void NativeApp.exitApp(); return; }
      lastBack = Date.now();
      toast(t('再按一次返回键退出 UniMind'), { id: 'android-back-exit', duration: 2000 });
    });
    return () => { void listener.then(handle => handle.remove()); };
  }, []);
  if (!hydrated) return <Loading message={t('正在恢复登录状态…')} fullScreen />;
  return (
    <QueryClientProvider client={queryClient}>
      <ErrorBoundary>
        <Toaster position="top-center" richColors />
        <RouterProvider router={router} />
      </ErrorBoundary>
    </QueryClientProvider>
  );
}

export default App;
