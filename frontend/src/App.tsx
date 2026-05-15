import { createBrowserRouter, RouterProvider, Navigate, useLocation, useNavigate } from 'react-router-dom';
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
          localStorage.removeItem('token');
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
  // 仅机构管理员可访问管理类页面
  if (user.institution_role !== 'admin' && !user.is_institution_admin && !user.is_admin) {
    return <Navigate to="/" replace />;
  }
  return children;
};

// 超管默认跳转到机构管理
const HomeRedirect = () => {
  const { user } = useAuthStore();
  const institution = useInstitutionStore(s => s.institution);
  if (user?.role === 'admin' && !institution && !user?.institution) return <Navigate to="/institution/admin" replace />;
  return <CourseCenter />;
};

import { Landing } from './pages/Landing';
import { CourseDetails } from './pages/CourseDetails';
import StartupMaterials from './pages/StartupMaterials';

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
          localStorage.removeItem('token');
        })
        .finally(() => setLoading(false));
    }
  }, [token, user, setAuth]);

  useEffect(() => {
    if (token || user) { setCheckingInvite(false); return; }
    api.get('/users/check-invite/')
      .then(res => {
        if (res.data?.has_invite) navigate('/login', { replace: true });
      })
      .catch(() => {})
      .finally(() => setCheckingInvite(false));
  }, [token, user]);

  if (loading || checkingInvite) return <Loading message="Authenticating Secure Session..." fullScreen size="lg" />;

  // Allow access to startup materials even if not logged in (using MainLayout)
  if (location.pathname === '/startup-materials') return <MainLayout />;

  // If logged in, wrap the app content in MainLayout
  if (token && user) return <MainLayout />;

  // Otherwise, return the landing page (outside layout)
  return <Landing />;
};

const router = createBrowserRouter([
  {
    path: "/",
    element: <RootRedirect />,
    children: [
      { index: true, element: <RequireAuth><HomeRedirect /></RequireAuth> },
      { path: "course-details", element: <CourseDetails /> },
      { path: "startup-materials", element: <StartupMaterials /> },
      { path: "articles", element: <RequireAuth><ArticleCenter /></RequireAuth> },
      { path: "qa", element: <RequireAuth><FeatureGuard feature={FEATURES.FAQ_SYSTEM}><QASystem /></FeatureGuard></RequireAuth> },
      { path: "article/:id", element: <RequireAuth><ArticleDetail /></RequireAuth> },
      { path: "tests", element: <RequireAuth><FeatureGuard feature={FEATURES.QUIZ_EXAM}><TestLadder /></FeatureGuard></RequireAuth> },
      { path: "tests/session", element: <RequireAuth><FeatureGuard feature={FEATURES.QUIZ_EXAM}><TestSessionPage /></FeatureGuard></RequireAuth> },
      { path: "study", element: <RequireAuth><FeatureGuard feature={FEATURES.STUDY_ROOM}><StudyRoom /></FeatureGuard></RequireAuth> },
      { path: "ai", element: <RequireAuth><FeatureGuard feature={FEATURES.AI_ASSISTANT}><AIAssistant /></FeatureGuard></RequireAuth> },
      { path: "knowledge-map", element: <RequireAuth><FeatureGuard feature={FEATURES.KNOWLEDGE_GRAPH}><KnowledgeMap /></FeatureGuard></RequireAuth> },
      { path: "knowledge-map/node/:id", element: <RequireAuth><FeatureGuard feature={FEATURES.KNOWLEDGE_GRAPH}><KnowledgeNodeDetail /></FeatureGuard></RequireAuth> },
      { path: "settings", element: <RequireAuth><Settings /></RequireAuth> },
      { path: "system-settings", element: <RequireAuth><RequireAdmin><SystemSettings /></RequireAdmin></RequireAuth> },
      { path: "management", element: <RequireAuth><RequireAdmin><Maintenance /></RequireAdmin></RequireAuth> },
      { path: "course/:id", element: <RequireAuth><FeatureGuard feature={FEATURES.COURSE_VIDEO}><VideoLesson /></FeatureGuard></RequireAuth> },
      { path: "tests/review", element: <RequireAuth><FeatureGuard feature={FEATURES.WRONG_REVIEW}><WrongQuestionReviewPage /></FeatureGuard></RequireAuth> },
      { path: "mock-exam", element: <RequireAuth><FeatureGuard feature={FEATURES.PDF_MOCK}><PdfMockExam /></FeatureGuard></RequireAuth> },
      { path: "interviews", element: <RequireAuth><FeatureGuard feature={FEATURES.AI_GENERATE}><Interviews /></FeatureGuard></RequireAuth> },
      { path: "institution", element: <RequireAuth><RequireInstitution><InstitutionDashboard /></RequireInstitution></RequireAuth> },
      { path: "institution/students", element: <RequireAuth><RequireInstitution><InstitutionStudents /></RequireInstitution></RequireAuth> },
      { path: "institution/admin", element: <RequireAuth><RequireAdmin><InstitutionAdmin /></RequireAdmin></RequireAuth> },
      { path: "invite-codes", element: <RequireAuth><RequirePlatformAdmin><InviteCodeAdmin /></RequirePlatformAdmin></RequireAuth> },
      { path: "intro", element: <InstitutionHome /> },
    ],
  },
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
