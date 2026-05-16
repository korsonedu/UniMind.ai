import { createBrowserRouter, RouterProvider, Navigate, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { MainLayout } from './layouts/MainLayout';
import { CourseCenter } from './pages/CourseCenter';
import { TestLadder } from './pages/TestLadder';
import { StudyRoom } from './pages/StudyRoom';
import { Settings } from './pages/Settings';
import { Maintenance } from './pages/Maintenance';
import { Login } from './pages/Login';
import { Register } from './pages/Register';
import { VideoLesson } from './pages/VideoLesson';
import { ArticleDetail } from './pages/ArticleDetail';
import { ArticleCenter } from './pages/ArticleCenter';
import { AIAssistant } from './pages/AIAssistant';
import { SystemSettings } from './pages/SystemSettings';
import { KnowledgeMap } from './pages/KnowledgeMap';
import { KnowledgeNodeDetail } from './pages/KnowledgeNodeDetail';
import { QASystem } from './pages/QASystem';
import { TestSessionPage } from './pages/TestSessionPage';
import InstitutionDashboard from './pages/InstitutionDashboard';
import InstitutionStudents from './pages/InstitutionStudents';
import InstitutionAdmin from './pages/InstitutionAdmin';
import InstitutionHome from './pages/InstitutionHome';
import InviteCodeAdmin from './pages/InviteCodeAdmin';
import { PromptTemplatesAdmin } from './pages/PromptTemplatesAdmin';
import { Interviews } from './pages/Interviews';
import { PdfMockExam } from './pages/PdfMockExam';
import { WrongQuestionReviewPage } from './pages/WrongQuestionReviewPage';
import { LandingZh } from './pages/LandingZh';
import { LandingEn } from './pages/LandingEn';
import { useAuthStore } from './store/useAuthStore';
import { useSystemStore } from './store/useSystemStore';
import { useInstitutionStore } from './store/useInstitutionStore';
import { FeatureGuard } from './components/FeatureGuard';
import { FEATURES } from './store/useInstitutionStore';
import { Loading } from '@/components/Loading';
import { useState, useEffect, type ReactNode } from 'react';
import api from '@/lib/api';
import { Toaster } from 'sonner';
import { WeeklyReportDialog } from './components/WeeklyReportDialog';
import { Landing } from './pages/Landing';

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

  if (loading) return <Loading message="Synchronizing Secure Session..." fullScreen size="lg" />;

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
  if (institution?.plan === 'pro') return <InstitutionHome />;
  return <Navigate to="/courses" replace />;
};

// Root entry handler to manage landing vs app logic
const RootRedirect = () => {
  const { token, user, setAuth } = useAuthStore();
  const [loading, setLoading] = useState(!!token && !user);
  const [checkingInvite, setCheckingInvite] = useState(true);
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    if (token && !user) {
      api.get('/users/me/')
        .then(res => setAuth(res.data, token))
        .catch(() => {
          api.post('/users/logout/').catch(() => {});
        })
        .finally(() => setLoading(false));
    }
  }, [token, user, setAuth]);

  useEffect(() => {
    if (token || user) { setCheckingInvite(false); return; }
    api.get('/users/check-invite/')
      .then(res => {
        if (res.data?.has_invite) navigate('/register', { replace: true });
      })
      .catch(() => {})
      .finally(() => setCheckingInvite(false));
  }, [token, user]);

  if (loading || checkingInvite) return <Loading message="Authenticating Secure Session..." fullScreen size="lg" />;

  if (token && user) return <Outlet />;

  return <Landing />;
};

const router = createBrowserRouter([
  {
    path: "/",
    element: <RootRedirect />,
    children: [
      { index: true, element: <RequireAuth><HomeRedirect /></RequireAuth> },
      {
        element: <RequireAuth><MainLayout /></RequireAuth>,
        children: [
          { path: "courses", element: <CourseCenter /> },
          { path: "articles", element: <ArticleCenter /> },
          { path: "qa", element: <FeatureGuard feature={FEATURES.FAQ_SYSTEM}><QASystem /></FeatureGuard> },
          { path: "article/:id", element: <ArticleDetail /> },
          { path: "tests", element: <FeatureGuard feature={FEATURES.QUIZ_EXAM}><TestLadder /></FeatureGuard> },
          { path: "tests/session", element: <FeatureGuard feature={FEATURES.QUIZ_EXAM}><TestSessionPage /></FeatureGuard> },
          { path: "study", element: <FeatureGuard feature={FEATURES.STUDY_ROOM}><StudyRoom /></FeatureGuard> },
          { path: "ai", element: <FeatureGuard feature={FEATURES.AI_ASSISTANT}><AIAssistant /></FeatureGuard> },
          { path: "knowledge-map", element: <FeatureGuard feature={FEATURES.KNOWLEDGE_GRAPH}><KnowledgeMap /></FeatureGuard> },
          { path: "knowledge-map/node/:id", element: <FeatureGuard feature={FEATURES.KNOWLEDGE_GRAPH}><KnowledgeNodeDetail /></FeatureGuard> },
          { path: "settings", element: <Settings /> },
          { path: "system-settings", element: <RequireAdmin><SystemSettings /></RequireAdmin> },
          { path: "management", element: <RequireAdmin><Maintenance /></RequireAdmin> },
          { path: "course/:id", element: <FeatureGuard feature={FEATURES.COURSE_VIDEO}><VideoLesson /></FeatureGuard> },
          { path: "tests/review", element: <FeatureGuard feature={FEATURES.WRONG_REVIEW}><WrongQuestionReviewPage /></FeatureGuard> },
          { path: "mock-exam", element: <FeatureGuard feature={FEATURES.PDF_MOCK}><PdfMockExam /></FeatureGuard> },
          { path: "interviews", element: <FeatureGuard feature={FEATURES.INTERVIEW_MOCK}><Interviews /></FeatureGuard> },
          { path: "institution", element: <RequireInstitution><InstitutionDashboard /></RequireInstitution> },
          { path: "institution/students", element: <RequireInstitution><InstitutionStudents /></RequireInstitution> },
          { path: "institution/admin", element: <RequireAdmin><InstitutionAdmin /></RequireAdmin> },
          { path: "invite-codes", element: <RequirePlatformAdmin><InviteCodeAdmin /></RequirePlatformAdmin> },
          { path: "prompt-templates", element: <RequirePlatformAdmin><PromptTemplatesAdmin /></RequirePlatformAdmin> },
        ],
      },
    ],
  },
  { path: "/intro/:slug", element: <InstitutionHome /> },
  { path: "/intro", element: <Navigate to="/" replace /> },
  { path: "/en", element: <LandingEn /> },
  { path: "/zh", element: <LandingZh /> },
  { path: "/login", element: <Login /> },
  { path: "/register", element: <Register /> },
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
