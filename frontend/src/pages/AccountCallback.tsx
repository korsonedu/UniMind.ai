import { useNavigate, useSearchParams } from 'react-router-dom';
import { queryKeys } from '@/lib/queryKeys';
import { AuthLayout } from '@/components/AuthLayout';
import { Button } from '@/components/ui/button';
import { t, useLocale } from '@/i18n';
import { useEffect, useState } from 'react';
import axios from 'axios';
import { queryClient } from '@/lib/queryClient';
import { useAuthStore } from '@/store/useAuthStore';
import { useInstitutionStore } from '@/store/useInstitutionStore';
import { getReturnTo, getLoginPath } from '@/lib/routing';

export function AccountCallback() {
  useLocale();
  const [error, setError] = useState(false);
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const returnTo = getReturnTo(params.get('next'));
  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    const load = async () => {
      try {
        // Discard previous-account caches before the authoritative identity request.
        await queryClient.cancelQueries();
        if (cancelled) return;
        queryClient.clear();
        useAuthStore.getState().logout({ preserveDesktop: true });
        const { data: user } = await axios.get(`${import.meta.env.VITE_API_URL || '/api'}/users/me/`, {
          withCredentials: true, timeout: 30000, signal: controller.signal,
        });
        if (cancelled) return;
        queryClient.setQueryData(queryKeys.user.me, user);
        useAuthStore.getState().setAuth(user, null);
        await useInstitutionStore.getState().fetchFeatures();
        if (!cancelled) navigate(returnTo, { replace: true });
      } catch {
        if (!cancelled) setError(true);
      }
    };
    void load();
    return () => { cancelled = true; controller.abort(); };
  }, [navigate, returnTo]);
  return <AuthLayout title={error ? t('暂时无法进入 UniMind') : t('正在确认你的账号')}>
    {error ? <div className="space-y-3">
      <Button className="um-auth-submit" onClick={() => window.location.reload()}>{t('重试')}</Button>
      <Button asChild variant="ghost" className="um-auth-secondary"><a href={getLoginPath(returnTo)}>{t('重新登录')}</a></Button>
    </div> : <p role="status" className="um-auth-status">{t('确认后将进入 UniMind。')}</p>}
  </AuthLayout>;
}
