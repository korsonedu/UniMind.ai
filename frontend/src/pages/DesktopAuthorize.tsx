import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { AuthLayout } from '@/components/AuthLayout';
import { Button } from '@/components/ui/button';
import api from '@/lib/api';
import { formatApiErrorToast } from '@/lib/apiError';
import { getLoginPath } from '@/lib/routing';
import { useAuthStore } from '@/store/useAuthStore';

type Account = { id: number; nickname: string; email: string };

export function DesktopAuthorize() {
  const [params] = useSearchParams();
  const requestId = params.get('request') || '';
  const [user, setUser] = useState<Account | null>(null);
  const [callback, setCallback] = useState('');
  const [error, setError] = useState('');
  const [pending, setPending] = useState(false);
  const navigate = useNavigate();
  const returnTo = `/desktop-auth?${new URLSearchParams({ request: requestId })}`;

  useEffect(() => {
    const controller = new AbortController();
    void api.get('/users/desktop-auth/confirm/', { params: { request: requestId }, signal: controller.signal })
      .then(({ data }) => { if (!controller.signal.aborted) setUser(data.user); })
      .catch(err => { if (!controller.signal.aborted) setError(formatApiErrorToast(err, '无法确认登录请求，请返回 App 重新开始。')); });
    return () => controller.abort();
  }, [requestId]);

  const confirm = async () => {
    if (!user || pending) return;
    setPending(true); setError('');
    try {
      const { data } = await api.post('/users/desktop-auth/confirm/', { request: requestId, account_id: user.id });
      setCallback(data.callback);
      window.location.href = data.callback;
    } catch (err) { setError(formatApiErrorToast(err, '登录确认失败，请重试。')); }
    finally { setPending(false); }
  };

  const switchAccount = async () => {
    setPending(true); setError('');
    try {
      await api.post('/users/logout/');
      useAuthStore.getState().logout();
      navigate(getLoginPath(returnTo), { replace: true });
    } catch (err) { setError(formatApiErrorToast(err, '暂时无法切换账号，请重试。')); }
    finally { setPending(false); }
  };

  return <AuthLayout title={callback ? '登录已确认' : '登录 UniMind.ai App'} subtitle={callback ? '请返回 App 完成登录。' : undefined}>
    {error && <p role="alert" className="mb-5 text-sm text-red-600">{error}</p>}
    {callback ? <Button asChild className="w-full h-12 rounded-xl"><a href={callback}>打开 UniMind.ai</a></Button> : user ? <div className="space-y-4">
      <div className="rounded-xl border border-border p-4"><p className="font-medium">{user.nickname}</p><p className="text-sm text-muted-foreground">{user.email}</p></div>
      <Button className="w-full h-12 rounded-xl" disabled={pending} onClick={() => void confirm()}>{pending ? '请稍候…' : '确认登录 App'}</Button>
      <Button variant="ghost" className="w-full" disabled={pending} onClick={() => void switchAccount()}>使用其他账号</Button>
    </div> : !error && <p role="status" className="text-sm text-muted-foreground">正在确认账号…</p>}
  </AuthLayout>;
}
