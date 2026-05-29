import React, { useState, useEffect } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useAuthStore } from '@/store/useAuthStore';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';

import api from '@/lib/api';
import { useInstitutionStore } from '@/store/useInstitutionStore';

export const Login: React.FC = () => {
  const { t } = useTranslation('auth');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const { setAuth, updateUser } = useAuthStore();
  const { fetchFeatures } = useInstitutionStore();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  // 已登录则跳转首页
  useEffect(() => {
    const { token } = useAuthStore.getState();
    if (token) {
      navigate('/', { replace: true });
    }
  }, []);

  const getInstitutionSlug = (): string => {
    const fromParam = searchParams.get('institution');
    if (fromParam) return fromParam;
    const cookie = document.cookie.split('; ').find(r => r.startsWith('institution_invite='));
    if (cookie) return cookie.split('=')[1];
    return '';
  };
  const getInstitutionRole = (): string => {
    const fromParam = searchParams.get('role');
    if (fromParam) return fromParam;
    const cookie = document.cookie.split('; ').find(r => r.startsWith('institution_invite_role='));
    if (cookie) return cookie.split('=')[1];
    return 'student';
  };
  const institutionSlug = getInstitutionSlug();
  const institutionRole = getInstitutionRole();

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      const response = await api.post('/users/login/', { username, password });
      const user = response.data.user;
      const token = response.data.token;
      setAuth(user, token);

      // Auto-join institution from invite link or registration flow
      if (institutionSlug) {
        try {
          await api.post('/users/institution/join-by-slug/', { slug: institutionSlug, role: institutionRole });
          const meRes = await api.get('/users/me/');
          updateUser(meRes.data);
        } catch (err: any) {
          // Only show error if user still has no institution after login
          if (!user.institution && !user.institution_id) {
            toast.error(err.response?.data?.error || t('login.joinInstitutionError'));
          }
        }
      }

      // Fetch institution features/plan so permissions are correct immediately
      await fetchFeatures();

      navigate('/');
    } catch (err: any) {
      const errorData = err.response?.data;
      setError(errorData?.error || errorData?.non_field_errors?.[0] || errorData?.detail || t('login.error'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-unimind-bg-secondary flex items-center justify-center p-4">
      <Card className="w-full max-w-md border-none shadow-lg rounded-3xl bg-white/80 backdrop-blur-xl">
        <CardHeader className="p-6 space-y-1 text-center">
          <CardTitle className="text-2xl font-bold tracking-tight">{t('login.title')}</CardTitle>
          <CardDescription>{t('login.subtitle')}</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleLogin} className="space-y-4">
            {error && <p className="text-sm text-center bg-red-50 text-red-600 rounded-xl py-2.5 px-3">{error}</p>}
            <div className="space-y-2">
              <Input
                placeholder={t('login.usernamePlaceholder')}
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                spellCheck={false}
                className="bg-slate-50/50 border-none h-12 rounded-xl focus-visible:ring-black"
                required
              />
            </div>
            <div className="space-y-2">
              <Input
                type="password"
                placeholder={t('login.passwordPlaceholder')}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                spellCheck={false}
                className="bg-slate-50/50 border-none h-12 rounded-xl focus-visible:ring-black"
                required
              />
            </div>
            <Button className="w-full h-12 bg-black text-white rounded-xl font-medium hover:bg-black/90 transition-all" disabled={loading}>
              {loading ? t('login.loggingIn') : t('login.submit')}
            </Button>
          </form>
          <div className="mt-6 text-center text-sm text-muted-foreground">
            {t('login.noAccount')}{" "}
            <Link to={institutionSlug ? `/register?institution=${institutionSlug}` : '/register'} className="text-black font-semibold hover:underline">
              {t('login.registerLink')}
            </Link>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};
