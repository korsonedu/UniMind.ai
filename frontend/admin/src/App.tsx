import { createBrowserRouter, RouterProvider, Navigate } from 'react-router-dom';
import { Suspense, lazy, useState, useEffect, type ReactNode } from 'react';
import { useAuthStore } from '@/store/useAuthStore';
import api from '@/lib/api';
import { isAdminUser } from '@/lib/authz';
import { Toaster } from 'sonner';
import { Loader2 } from 'lucide-react';

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
  const { token, user, setAuth } = useAuthStore();
  const [loading, setLoading] = useState(!user && !!token);

  useEffect(() => {
    if (!user && token) {
      api.get('/users/me/')
        .then(res => setAuth(res.data, token))
        .catch(() => localStorage.removeItem('token'))
        .finally(() => setLoading(false));
    }
  }, []);

  if (loading) return <RouteLoading />;
  if (!token) return <Navigate to="/login" replace />;
  return children;
};

const RequireAdmin = ({ children }: { children: ReactNode }) => {
  const { user } = useAuthStore();
  if (!user) return <Navigate to="/login" replace />;
  if (!isAdminUser(user)) {
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
