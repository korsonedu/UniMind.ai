import { createBrowserRouter, RouterProvider, Navigate } from 'react-router-dom';
import { Suspense, lazy, useState, useEffect, type ReactNode } from 'react';
import { useAuthStore } from '@/store/useAuthStore';
import api from '@/lib/api';
import { Toaster } from 'sonner';
import { Spinner as Loader2 } from '@phosphor-icons/react';

const AdminLayout = lazy(() => import('./layouts/AdminLayout'));
const Login = lazy(() => import('./pages/Login'));
const Institutions = lazy(() => import('./pages/Institutions'));

const RouteLoading = () => (
  <div className="h-screen w-screen flex items-center justify-center bg-[#F5F5F7]">
    <Loader2 className="h-8 w-8 animate-spin text-[#AEAEB2]" />
  </div>
);

const withSuspense = (node: ReactNode) => <Suspense fallback={<RouteLoading />}>{node}</Suspense>;

const RequireAuth = ({ children }: { children: ReactNode }) => {
  const { user, setAuth, logout } = useAuthStore();
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    api.get('/users/me/')
      .then(res => { if (active) setAuth(res.data, null); })
      .catch(() => { if (active) logout(); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [setAuth, logout]);

  if (loading) return <RouteLoading />;
  if (!user) return <Navigate to="/login" replace />;
  return children;
};

const RequireAdmin = ({ children }: { children: ReactNode }) => {
  const { user } = useAuthStore();
  if (!user) return <Navigate to="/login" replace />;
  if (!user.is_admin) {
    return (
      <div className="h-screen flex items-center justify-center bg-[#F5F5F7] text-sm text-[#AEAEB2]">
        仅平台管理员可访问此面板
      </div>
    );
  }
  return children;
};

const router = createBrowserRouter([
  { path: "/login", element: withSuspense(<Login />) },
  {
    path: "/",
    element: withSuspense(<RequireAuth><RequireAdmin><AdminLayout /></RequireAdmin></RequireAuth>),
    children: [
      { index: true, element: <Navigate to="/institutions" replace /> },
      { path: "institutions", element: withSuspense(<Institutions />) },
    ],
  },
]);

export default function App() {
  return (
    <>
      <Toaster position="top-center" richColors />
      <RouterProvider router={router} />
    </>
  );
}
