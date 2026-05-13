import { createBrowserRouter, RouterProvider, Navigate, useLocation } from 'react-router-dom';
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
import { InstitutionDashboard } from './pages/InstitutionDashboard';
import { InstitutionStudents } from './pages/InstitutionStudents';
import { InstitutionAdmin } from './pages/InstitutionAdmin';
import { InstitutionHome } from './pages/InstitutionHome';
import { InviteCodeAdmin } from './pages/InviteCodeAdmin';
import { Interviews } from './pages/Interviews';
import { PdfMockExam } from './pages/PdfMockExam';
import { WrongQuestionReviewPage } from './pages/WrongQuestionReviewPage';
import { useAuthStore } from './store/useAuthStore';
import { useSystemStore } from './store/useSystemStore';
import { Loader2 } from 'lucide-react';
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

  if (loading) return (
    <div className="h-screen w-screen flex items-center justify-center bg-background">
      <div className="flex flex-col items-center gap-4 text-center">
        <Loader2 className="h-10 w-10 animate-spin text-muted-foreground/40" />
        <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-[0.2em]">Synchronizing Secure Session...</p>
      </div>
    </div>
  );

  if (!token) return <Navigate to="/login" replace />;
  return children;
};

const RequireAdmin = ({ children }: { children: ReactNode }) => {
  const { user } = useAuthStore();
  if (!user) return <Navigate to="/login" replace />;
  if (user.role !== 'admin') return <Navigate to="/settings" replace />;
  return children;
};

import { Landing } from './pages/Landing';
import { CourseDetails } from './pages/CourseDetails';
import StartupMaterials from './pages/StartupMaterials';

// Root entry handler to manage landing vs app logic
const RootRedirect = () => {
  const { token, user, setAuth } = useAuthStore();
  const [loading, setLoading] = useState(!!token && !user);
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

  if (loading) return (
    <div className="h-screen w-screen flex items-center justify-center bg-background">
      <div className="flex flex-col items-center gap-4 text-center">
        <Loader2 className="h-10 w-10 animate-spin text-muted-foreground/40" />
        <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-[0.2em]">Authenticating Secure Session...</p>
      </div>
    </div>
  );

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
      { index: true, element: <RequireAuth><CourseCenter /></RequireAuth> },
      { path: "course-details", element: <CourseDetails /> },
      { path: "startup-materials", element: <StartupMaterials /> },
      { path: "articles", element: <RequireAuth><ArticleCenter /></RequireAuth> },
      { path: "qa", element: <RequireAuth><QASystem /></RequireAuth> },
      { path: "article/:id", element: <RequireAuth><ArticleDetail /></RequireAuth> },
      { path: "tests", element: <RequireAuth><TestLadder /></RequireAuth> },
      { path: "tests/session", element: <RequireAuth><TestSessionPage /></RequireAuth> },
      { path: "study", element: <RequireAuth><StudyRoom /></RequireAuth> },
      { path: "ai", element: <RequireAuth><AIAssistant /></RequireAuth> },
      { path: "knowledge-map", element: <RequireAuth><KnowledgeMap /></RequireAuth> },
      { path: "knowledge-map/node/:id", element: <RequireAuth><KnowledgeNodeDetail /></RequireAuth> },
      { path: "settings", element: <RequireAuth><Settings /></RequireAuth> },
      { path: "system-settings", element: <RequireAuth><RequireAdmin><SystemSettings /></RequireAdmin></RequireAuth> },
      { path: "management", element: <RequireAuth><RequireAdmin><Maintenance /></RequireAdmin></RequireAuth> },
      { path: "course/:id", element: <RequireAuth><VideoLesson /></RequireAuth> },
      { path: "tests/review", element: <RequireAuth><WrongQuestionReviewPage /></RequireAuth> },
      { path: "mock-exam", element: <RequireAuth><PdfMockExam /></RequireAuth> },
      { path: "interviews", element: <RequireAuth><Interviews /></RequireAuth> },
      { path: "institution", element: <RequireAuth><InstitutionDashboard /></RequireAuth> },
      { path: "institution/students", element: <RequireAuth><InstitutionStudents /></RequireAuth> },
      { path: "institution/admin", element: <RequireAuth><InstitutionAdmin /></RequireAuth> },
      { path: "invite-codes", element: <RequireAuth><RequireAdmin><InviteCodeAdmin /></RequireAdmin></RequireAuth> },
      { path: "intro", element: <InstitutionHome /> },
    ],
  },
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
