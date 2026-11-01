import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowUpRight, Spinner } from '@phosphor-icons/react';
import axios from 'axios';
import { useAuthStore } from '@/store/useAuthStore';
import { getReturnTo } from '@/lib/routing';
import type { DesktopLoginState } from '@/lib/desktop';
import '@/styles/desktop-login.css';

export function DesktopLogin() {
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
      if (active) setError('暂时无法连接客户端，请重新打开 UniMind。');
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
    }).catch(() => { /* An expired session stays on the desktop sign-in screen. */ });
    return () => controller.abort();
  }, [navigate, returnTo]);

  const start = async () => {
    if (!desktop?.startLogin || busy) return;
    setActionPending(true); setError('');
    try {
      const state = await desktop.startLogin();
      if (state.auth) setAuth(state.auth);
    } catch { setError('暂时无法打开登录页面，请稍后重试。'); }
    finally { setActionPending(false); }
  };
  const cancel = async () => {
    if (!desktop?.cancelLogin || actionPending) return;
    setActionPending(true); setError('');
    try {
      const state = await desktop.cancelLogin();
      setAuth(state.auth || { status: 'idle' });
    } catch { setError('暂时无法取消，请重新打开 UniMind。'); }
    finally { setActionPending(false); }
  };
  const status = error || auth.error || (!supported ? '请安装最新客户端，以使用浏览器登录。'
    : auth.status === 'completing' || auth.status === 'authenticated' ? '正在确认账号，即将进入学习空间。'
      : waiting ? '浏览器已打开。登录完成后，会自动回到这里。'
        : '使用你的科晟账号，在浏览器中安全登录。');

  return <main className="um-desktop-login">
    <div className="um-desktop-login-titlebar" aria-hidden="true" />
    <section className="um-desktop-login-content" aria-labelledby="desktop-login-title">
      <div className="um-desktop-login-mark"><img src="/unimind_logo_small.png" alt="" width="68" height="68" /></div>
      <h1 id="desktop-login-title">欢迎使用 UniMind</h1>
      <p className="um-desktop-login-subtitle">和小宇一起，把问题弄清楚。</p>
      <div className="um-desktop-login-actions">
        <button className="um-desktop-login-primary" disabled={!supported || busy} onClick={() => void start()}>
          {busy ? <><Spinner size={18} className="animate-spin" aria-hidden="true" />{auth.status === 'completing' || auth.status === 'authenticated' ? '正在进入 UniMind' : '正在打开浏览器'}</>
            : <>{waiting ? '重新打开浏览器' : '通过浏览器登录'}<ArrowUpRight size={18} aria-hidden="true" /></>}
        </button>
        <p className="um-desktop-login-status" role={error || auth.error ? 'alert' : 'status'}>{status}</p>
        {(waiting || auth.status === 'error') && <button className="um-desktop-login-cancel" disabled={actionPending} onClick={() => void cancel()}>{waiting ? '取消登录' : '返回登录'}</button>}
      </div>
    </section>
    <footer className="um-desktop-login-footer">
      <p><a href="/terms" target="_blank" rel="noreferrer">用户协议</a><span aria-hidden="true"> · </span><a href="/privacy" target="_blank" rel="noreferrer">隐私政策</a></p>
      <span>UniMind · 科晟智慧</span>
    </footer>
  </main>;
}
