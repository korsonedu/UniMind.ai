import { LanguageSelect } from '@/components/LanguageSelect';
import { t, useLocale } from '@/i18n';
import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowUpRight, Spinner } from '@phosphor-icons/react';
import axios from 'axios';
import { useAuthStore } from '@/store/useAuthStore';
import { getReturnTo } from '@/lib/routing';
import type { DesktopLoginState } from '@/lib/desktop';
import '@/styles/desktop-login.css';

export function DesktopLogin() {
  useLocale();
  const desktop = window.unimindDesktop;
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const returnTo = getReturnTo(params.get('next'));
  const [auth, setAuth] = useState<DesktopLoginState>({ status: 'idle' });
  const [actionPending, setActionPending] = useState(false);
  const [error, setError] = useState('');
  const supported = !!desktop?.startLogin && !!desktop.cancelLogin;
  const waiting = auth.status === 'waiting';
  const busy = actionPending || ['opening', 'completing', 'authenticated'].includes(auth.status);

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
    void axios.get(`${import.meta.env.VITE_API_URL || '/api'}/users/me/`, {
      withCredentials: true, signal: controller.signal, timeout: 15000,
    }).then(({ data }) => {
      if (controller.signal.aborted) return;
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
  const status = error || auth.error || (!supported ? t('请安装最新客户端，以使用浏览器登录。')
    : auth.status === 'completing' || auth.status === 'authenticated' ? t('正在确认账号，即将进入学习空间。')
      : waiting ? t('浏览器已打开。登录完成后，会自动回到这里。')
        : t('使用你的科晟账号，在浏览器中安全登录。'));

  return <main className="um-desktop-login">
    <div className="um-desktop-login-titlebar" aria-hidden="true" />
    <section className="um-desktop-login-content" aria-labelledby="desktop-login-title">
      <div className="um-desktop-login-mark"><img src="/unimind_logo_small.png" alt="" width="68" height="68" /></div>
      <div className="mb-4"><LanguageSelect /></div>
      <h1 id="desktop-login-title">{t('欢迎使用 UniMind')}</h1>
      <p className="um-desktop-login-subtitle">{t('和小宇一起，把问题弄清楚。')}</p>
      <div className="um-desktop-login-actions">
        <button className="um-desktop-login-primary" disabled={!supported || busy} onClick={() => void start()}>
          {busy ? <><Spinner size={18} className="animate-spin" aria-hidden="true" />{auth.status === 'completing' || auth.status === 'authenticated' ? t('正在进入 UniMind') : t('正在打开浏览器')}</>
            : <>{waiting ? t('重新打开浏览器') : t('通过浏览器登录')}<ArrowUpRight size={18} aria-hidden="true" /></>}
        </button>
        <p className="um-desktop-login-status" role={error || auth.error ? 'alert' : 'status'}>{t(status)}</p>
        {(waiting || auth.status === 'error') && <button className="um-desktop-login-cancel" disabled={actionPending} onClick={() => void cancel()}>{waiting ? t('取消登录') : t('返回登录')}</button>}
      </div>
    </section>
    <footer className="um-desktop-login-footer">
      <p><a href="/terms" target="_blank" rel="noreferrer">{t('用户协议')}</a><span aria-hidden="true"> · </span><a href="/privacy" target="_blank" rel="noreferrer">{t('隐私政策')}</a></p>
      <span>{t('UniMind · 科晟智慧')}</span>
    </footer>
  </main>;
}
