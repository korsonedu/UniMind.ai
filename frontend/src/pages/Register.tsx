import { t, useLocale } from '@/i18n';
import { formatApiErrorToast } from '@/lib/apiError';
import React, { useState, useEffect, useRef } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';
import { AuthLayout } from '@/components/AuthLayout';
import { Warning } from '@phosphor-icons/react';
import { useQuery } from '@tanstack/react-query';

import api from '@/lib/api';
import { isNativePlatform } from '@/lib/serverConfig';
import { ServerConfigControl } from '@/components/ServerConfigControl';
import { useAuthStore } from '@/store/useAuthStore';
import { getReturnTo } from '@/lib/routing';

export const Register: React.FC = () => {
  useLocale();
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [nickname, setNickname] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [sendingCode, setSendingCode] = useState(false);
  const [error, setError] = useState('');
  const [agreedToTerms, setAgreedToTerms] = useState(false);
  const [, setCodeSent] = useState(false);
  const [countdown, setCountdown] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const returnTo = getReturnTo(searchParams.get('next'));
  const nativePlatform = isNativePlatform();

  useEffect(() => {
    const { user } = useAuthStore.getState();
    if (user && (!nativePlatform || useAuthStore.getState().token)) navigate(returnTo, { replace: true });
  }, [navigate, returnTo, nativePlatform]);
  useEffect(() => {
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
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
  const refCode = searchParams.get('ref') || '';
  const referral = useQuery({
    queryKey: ['referral-validity', refCode],
    enabled: !!refCode,
    retry: false,
    queryFn: ({ signal }) => api.get<{ valid: boolean }>('/payments/referral/validate/', { params: { code: refCode }, signal }).then(({ data }) => data.valid),
  });
  const loginParams = new URLSearchParams({ next: returnTo });
  if (institutionSlug) {
    loginParams.set('institution', institutionSlug);
    loginParams.set('role', institutionRole);
  }

  const handleSendCode = async () => {
    if (!email.trim() || countdown > 0) return;
    setSendingCode(true);
    setError('');
    try {
      await api.post('/users/send-verification-code/', { email });
      setCodeSent(true);
      setCountdown(60);
      timerRef.current = setInterval(() => {
        setCountdown(prev => {
          if (prev <= 1) { if (timerRef.current) clearInterval(timerRef.current); timerRef.current = null; return 0; }
          return prev - 1;
        });
      }, 1000);
    } catch (err: unknown) {
      setError(formatApiErrorToast(err, t('发送失败')));
    } finally {
      setSendingCode(false);
    }
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!code.trim()) { setError(t('请输入验证码')); return; }
    setLoading(true);
    setError('');
    try {
      await api.post('/users/register/', { email, code, nickname, password, agreed_to_terms: agreedToTerms, referral_code: refCode });
      navigate(`/login?${loginParams}`);
    } catch (err: unknown) {
      setError(formatApiErrorToast(err, t('注册失败')));
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout
      title={t('创建账号')}
      footer={
        <p className="text-sm text-[#6E6E73] dark:text-white/40">
          {t('已有账号？')}
          <Link
            to={`/login?${loginParams}`}
            className="text-[#1D1D1F] dark:text-white font-medium hover:underline ml-1"
          >
            {t('登录')}
          </Link>
        </p>
      }
    >
      {nativePlatform && <div className="um-auth-server"><ServerConfigControl variant="pill" onOriginChanged={() => setError('')} /></div>}
      {/* Referral banner */}
      {referral.isSuccess && (
        <div className="rounded-xl bg-blue-50 dark:bg-blue-950/25 border border-blue-200 dark:border-blue-800/40 px-4 py-3 mb-5 text-sm text-blue-700 dark:text-blue-400">
          {referral.data ? t('你收到了 UniMind.ai 好友邀请。完成注册后，你和好友各获 3 天免费会员。') : t('邀请链接已失效，可以继续注册。')}
        </div>
      )}

      {/* Error banner */}
      {error && (
        <div className="flex items-start gap-2.5 rounded-xl bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800/40 px-4 py-3 mb-5 text-sm text-red-700 dark:text-red-400">
          <Warning className="h-4 w-4 mt-0.5 shrink-0" weight="fill" />
          <span>{error}</span>
        </div>
      )}

      <form onSubmit={handleRegister} className="space-y-4">
        <div className="space-y-1.5">
          <label htmlFor="reg-email" className="text-sm font-medium text-[#1D1D1F] dark:text-white/85">
            {t('邮箱')}
          </label>
          <div className="flex gap-2">
            <Input
              id="reg-email"
              type="email"
              placeholder="name@example.com"
              value={email}
              onChange={(e) => { setEmail(e.target.value); setCodeSent(false); }}
              autoComplete="email"
              spellCheck={false}
              className="h-12 rounded-xl flex-1"
              required
            />
            <Button
              type="button"
              onClick={handleSendCode}
              disabled={sendingCode || !email.trim() || countdown > 0}
              variant="outline"
              className="um-auth-code-button"
            >
              {sendingCode ? t('发送中') : countdown > 0 ? `${countdown}s` : t('获取验证码')}
            </Button>
          </div>
        </div>

        <div className="space-y-1.5">
          <label htmlFor="reg-code" className="text-sm font-medium text-[#1D1D1F] dark:text-white/85">
            {t('验证码')}
          </label>
          <Input
            id="reg-code"
            placeholder={t('输入 6 位验证码')}
            value={code}
            onChange={(e) => setCode(e.target.value)}
            autoComplete="one-time-code"
            spellCheck={false}
            className="h-12 rounded-xl text-lg tracking-[0.3em] font-mono text-center"
            maxLength={6}
            required
          />
        </div>

        <div className="space-y-1.5">
          <label htmlFor="reg-nickname" className="text-sm font-medium text-[#1D1D1F] dark:text-white/85">
            {t('昵称')}
          </label>
          <Input
            id="reg-nickname"
            placeholder={t('你的称呼')}
            value={nickname}
            onChange={(e) => setNickname(e.target.value)}
            className="h-12 rounded-xl"
            required
          />
        </div>

        <div className="space-y-1.5">
          <label htmlFor="reg-password" className="text-sm font-medium text-[#1D1D1F] dark:text-white/85">
            {t('密码')}
          </label>
          <Input
            id="reg-password"
            type="password"
            placeholder={t('至少 8 位，含大写字母和数字')}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
            spellCheck={false}
            className="h-12 rounded-xl"
            minLength={8}
            required
          />
        </div>

        <div className="flex items-start gap-2 pt-1">
          <Checkbox
            id="agree-terms"
            checked={agreedToTerms}
            onCheckedChange={(checked) => setAgreedToTerms(checked === true)}
            className="mt-0.5"
          />
          <label htmlFor="agree-terms" className="text-xs text-[#6E6E73] dark:text-white/40 leading-relaxed cursor-pointer">
            {t('我已阅读并同意')}
            <Link to="/terms" className="text-[#1D1D1F] dark:text-white font-medium hover:underline mx-0.5">{t('用户协议')}</Link>
            {t('和')}
            <Link to="/privacy" className="text-[#1D1D1F] dark:text-white font-medium hover:underline ml-0.5">{t('隐私政策')}</Link>
          </label>
        </div>

        <Button
          type="submit"
          className="um-auth-submit"
          disabled={loading || !agreedToTerms}
        >
          {loading ? t('注册中...') : t('注册')}
        </Button>
      </form>
    </AuthLayout>
  );
};
