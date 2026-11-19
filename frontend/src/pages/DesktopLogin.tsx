import { queryClient } from '@/lib/queryClient';
import { queryKeys } from '@/lib/queryKeys';
import { t, useLocale } from '@/i18n';
import { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowUpRight, Spinner } from '@phosphor-icons/react';
import axios from 'axios';
import { useAuthStore } from '@/store/useAuthStore';
import { getReturnTo } from '@/lib/routing';
import type { DesktopLoginState } from '@/lib/desktop';
import { AuthLayout } from '@/components/AuthLayout';
import { PageLoader } from '@/components/PageLoader';
import { Button } from '@/components/ui/button';

export function DesktopLogin() {
  useLocale();
  const desktop = window.unimindDesktop;
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const returnTo = getReturnTo(params.get('next'));
  const [auth, setAuth] = useState<DesktopLoginState>({ status: 'idle' });
  const [actionPending, setActionPending] = useState(false);
  const [error, setError] = useState('');
  const sessionCheck = useRef<AbortController | null>(null);
  const supported = !!desktop?.startLogin && !!desktop.cancelLogin;
  const waiting = auth.status === 'waiting';
  const completing = auth.status === 'completing' || auth.status === 'authenticated';
  const busy = actionPending || auth.status === 'opening' || completing;

  useEffect(() => {
    if (!desktop) return;
    let active = true;
    const unsubscribe = desktop.onStateChanged(state => { if (active && state.auth) setAuth(state.auth); });
    void desktop.getState().then(state => { if (active && state.auth) setAuth(state.auth); }).catch(() => {
      if (active) setError(t('暂时无法连接客户端，请重新打开 UniMind。'));
    });
    return () => { active = false; unsubscribe(); };
  }, [desktop]);

  useEffect(() => {
    const controller = new AbortController();
    sessionCheck.current = controller;
    void axios.get(`${import.meta.env.VITE_API_URL || '/api'}/users/me/`, {
      withCredentials: true, signal: controller.signal, timeout: 15000,
    }).then(({ data }) => {
      if (controller.signal.aborted) return;
      queryClient.setQueryData(queryKeys.user.me, data);
      useAuthStore.getState().setAuth(data, null);
      navigate(returnTo, { replace: true });
    }).catch(async error => {
      if (controller.signal.aborted || !desktop || (axios.isAxiosError(error) && error.response?.status === 401)) return;
      try {
        const { offlineSession } = await desktop.getState();
        const user = useAuthStore.getState().user;
        if (!controller.signal.aborted && user && offlineSession?.userId === user.id && offlineSession.expiresAt > Date.now()) {
          navigate(returnTo, { replace: true });
        }
      } catch { /* No valid offline session: keep the sign-in screen. */ }
    });
    return () => controller.abort();
  }, [desktop, navigate, returnTo]);

  const start = async () => {
    if (!desktop?.startLogin || busy) return;
    // Browser sign-in owns navigation once it starts.
    sessionCheck.current?.abort();
    setActionPending(true); setError('');
    try {
      const state = await desktop.startLogin();
      if (state.auth) setAuth(state.auth);
    } catch { setError(t('暂时无法打开登录页面，请稍后重试。')); }
    finally { setActionPending(false); }
  };
  const cancel = async () => {
    if (!desktop?.cancelLogin || actionPending) return;
    setActionPending(true); setError('');
    try {
      const state = await desktop.cancelLogin();
      setAuth(state.auth || { status: 'idle' });
    } catch { setError(t('暂时无法取消，请重新打开 UniMind。')); }
    finally { setActionPending(false); }
  };
  if (completing) return <PageLoader />;

  const status = error || auth.error || (!supported ? t('请安装最新客户端，以使用浏览器登录。')
    : waiting ? t('浏览器已打开。登录完成后，会自动回到这里。') : '');

  return <AuthLayout title={t('登录 UniMind.ai')}>
    <Button className="um-auth-submit" disabled={!supported || busy} onClick={() => void start()}>
      {busy ? <><Spinner size={18} className="animate-spin" aria-hidden="true" />{t('正在打开浏览器')}</>
        : <>{waiting ? t('重新打开浏览器') : t('通过浏览器登录')}<ArrowUpRight size={18} aria-hidden="true" /></>}
    </Button>
    {status && <p className="mt-4 text-sm text-center text-muted-foreground" role={error || auth.error ? 'alert' : 'status'}>{status}</p>}
    {(waiting || auth.status === 'error') && <Button variant="ghost" className="w-full mt-3" disabled={actionPending} onClick={() => void cancel()}>{waiting ? t('取消登录') : t('返回登录')}</Button>}
  </AuthLayout>;
}
