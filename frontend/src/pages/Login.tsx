import { queryClient } from '@/lib/queryClient';
import { queryKeys } from '@/lib/queryKeys';
import { t, useLocale } from '@/i18n';
import { formatApiErrorToast } from '@/lib/apiError';
import React, { useState, useEffect } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { AuthLayout } from '@/components/AuthLayout';
import { useAuthStore } from '@/store/useAuthStore';
import { Warning, Spinner } from '@phosphor-icons/react';

import api from '@/lib/api';
import { useInstitutionStore } from '@/store/useInstitutionStore';
import { getReturnTo } from '@/lib/routing';
import { DesktopLogin } from './DesktopLogin';

type LoginTab = 'password' | 'code';

export const Login: React.FC = () => window.unimindDesktop ? <DesktopLogin /> : <WebLogin />;

const WebLogin: React.FC = () => {
  useLocale();
  const [tab, setTab] = useState<LoginTab>('password');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [sendingCode, setSendingCode] = useState(false);
  const setAuth = useAuthStore(s => s.setAuth);
  const { fetchFeatures } = useInstitutionStore();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const returnTo = getReturnTo(searchParams.get('next'));

  useEffect(() => {
    const { user } = useAuthStore.getState();
    if (user) navigate(returnTo, { replace: true });
  }, [navigate, returnTo]);

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
  const registerParams = new URLSearchParams({ next: returnTo });
  if (institutionSlug) {
    registerParams.set('institution', institutionSlug);
    registerParams.set('role', institutionRole);
  }

  const handlePasswordLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim() || !password) return;
    setLoading(true);
    setError('');
    try {
      const response = await api.post('/users/login/', { username: email, password });
      const user = response.data.user;
      const token = response.data.token;
      await queryClient.cancelQueries({ queryKey: queryKeys.user.me });
      queryClient.setQueryData(queryKeys.user.me, user);
      setAuth(user, token);
      await fetchFeatures();
      navigate(returnTo, { replace: true });
    } catch (err: unknown) {
      setError(formatApiErrorToast(err, t('登录失败')));
    } finally {
      setLoading(false);
    }
  };

  const isValidEmail = (e: string) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e);

  const handleSendCode = async () => {
    if (!email.trim()) return;
    if (!isValidEmail(email)) {
      setError(t('请输入有效的邮箱地址'));
      return;
    }
    setSendingCode(true);
    setError('');
    try {
      await api.post('/users/send-verification-code/', { email, purpose: 'login_by_code' });
      const params = new URLSearchParams(registerParams);
      params.set('email', email);
      params.set('purpose', 'login_by_code');
      navigate(`/verify-code?${params}`);
    } catch (err: unknown) {
      setError(formatApiErrorToast(err, t('发送失败，请稍后重试')));
      setSendingCode(false);
    }
  };

  return (
    <AuthLayout
      title={t('欢迎回来')}
      footer={
        tab === 'password' ? (
          <p className="text-sm text-[#6E6E73] dark:text-white/40">
            {t('没有账号？')}
            <Link
              to={`/register?${registerParams}`}
              className="text-[#1D1D1F] dark:text-white font-medium hover:underline ml-1"
            >
              {t('注册')}
            </Link>
          </p>
        ) : undefined
      }
    >
      <div className="um-auth-tabs" aria-label={t('登录方式')}>
        <button type="button" aria-pressed={tab === 'password'} onClick={() => { setTab('password'); setError(''); }}>{t('密码登录')}</button>
        <button type="button" aria-pressed={tab === 'code'} onClick={() => { setTab('code'); setError(''); }}>{t('验证码登录 / 注册')}</button>
      </div>

      {/* Error banner */}
      {error && (
        <div className="flex items-start gap-2.5 rounded-xl bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800/40 px-4 py-3 mb-5 text-sm text-red-700 dark:text-red-400">
          <Warning className="h-4 w-4 mt-0.5 shrink-0" weight="fill" />
          <span>{error}</span>
        </div>
      )}

      {/* Shared email field */}
      <div className="space-y-1.5 mb-4">
        <label htmlFor="login-email" className="text-sm font-medium text-[#1D1D1F] dark:text-white/85">
          {t('邮箱')}
        </label>
        <Input
          id="login-email"
          type="email"
          placeholder="name@example.com"
          value={email}
          onChange={(e) => { setEmail(e.target.value); setError(''); }}
          autoComplete="username"
          spellCheck={false}
          className="h-12 rounded-xl"
          required
        />
      </div>

      {/* Password tab */}
      {tab === 'password' && (
        <form onSubmit={handlePasswordLogin} className="space-y-4">
          <div className="space-y-1.5">
            <label htmlFor="login-password" className="text-sm font-medium text-[#1D1D1F] dark:text-white/85">
              {t('密码')}
            </label>
            <Input
              id="login-password"
              type="password"
              placeholder={t('输入密码')}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              spellCheck={false}
              className="h-12 rounded-xl"
              required
            />
          </div>

          <Button
            type="submit"
            className="um-auth-submit"
            disabled={loading}
          >
            {loading ? t('登录中...') : t('登录')}
          </Button>
        </form>
      )}

      {/* Code tab */}
      {tab === 'code' && (
        <div className="space-y-1.5">
          <Button
            type="button"
            className="um-auth-submit"
            disabled={sendingCode || !email.trim()}
            onClick={handleSendCode}
          >
            {sendingCode ? <Spinner className="h-4 w-4 animate-spin" /> : t('发送验证码')}
          </Button>
        </div>
      )}
    </AuthLayout>
  );
};
