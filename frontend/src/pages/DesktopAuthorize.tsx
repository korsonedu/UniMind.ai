import { t, useLocale } from '@/i18n';
import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { AuthLayout } from '@/components/AuthLayout';
import { Button } from '@/components/ui/button';
import api from '@/lib/api';
import { formatApiErrorToast } from '@/lib/apiError';
import { getLoginPath } from '@/lib/routing';
import { useAuthStore } from '@/store/useAuthStore';

type Account = { id: number; nickname: string; email: string };

export function DesktopAuthorize() {
  useLocale();
  const [params] = useSearchParams();
  const requestId = params.get('request') || '';
  const [user, setUser] = useState<Account | null>(null);
  const [callback, setCallback] = useState('');
  const [error, setError] = useState('');
  const [pending, setPending] = useState(false);
  const navigate = useNavigate();
  const returnTo = `/desktop-auth?${new URLSearchParams({ request: requestId })}`;

  const confirm = useCallback(async (account: Account, signal?: AbortSignal) => {
    setPending(true); setError('');
    try {
      const { data } = await api.post('/users/desktop-auth/confirm/', { request: requestId, account_id: account.id }, { signal });
      if (signal?.aborted) return;
      setCallback(data.callback);
      window.location.href = data.callback;
    } catch (err) { if (!signal?.aborted) setError(formatApiErrorToast(err, t('登录确认失败，请重试。'))); }
    finally { if (!signal?.aborted) setPending(false); }
  }, [requestId, setPending, setError, setCallback]);

  useEffect(() => {
    const controller = new AbortController();
    void api.get('/users/desktop-auth/confirm/', { params: { request: requestId }, signal: controller.signal })
      .then(({ data }) => {
        if (controller.signal.aborted) return;
        setUser(data.user);
        void confirm(data.user, controller.signal);
      })
      .catch(err => { if (!controller.signal.aborted) setError(formatApiErrorToast(err, t('无法确认登录请求，请返回 App 重新开始。'))); });
    return () => controller.abort();
  }, [requestId, confirm]);

  const switchAccount = async () => {
    setPending(true); setError('');
    try {
      await api.post('/users/logout/');
      useAuthStore.getState().logout();
      navigate(getLoginPath(returnTo), { replace: true });
    } catch (err) { setError(formatApiErrorToast(err, t('暂时无法切换账号，请重试。'))); }
    finally { setPending(false); }
  };

  return <AuthLayout title={callback ? t('登录已确认') : t('登录 UniMind.ai App')} subtitle={callback ? t('请返回 App 完成登录。') : undefined}>
    {error && <p role="alert" className="mb-5 text-sm text-red-600">{error}</p>}
    {callback ? <Button asChild className="um-auth-submit"><a href={callback}>{t('打开 UniMind.ai')}</a></Button> : user ? <div className="space-y-4">
      <div className="um-auth-account"><span className="um-auth-avatar" aria-hidden="true">{user.nickname.slice(0, 1)}</span><div><p className="um-auth-account-name">{user.nickname}</p><p className="um-auth-account-email">{user.email}</p></div></div>
      <Button className="um-auth-submit" disabled={pending} onClick={() => void confirm(user)}>{pending ? t('正在确认登录…') : t('重试登录 App')}</Button>
      <Button variant="ghost" className="um-auth-secondary" disabled={pending} onClick={() => void switchAccount()}>{t('使用其他账号')}</Button>
    </div> : !error && <p role="status" className="text-sm text-muted-foreground">{t('正在确认账号…')}</p>}
  </AuthLayout>;
}
