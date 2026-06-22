import React, { useState, useEffect, useRef } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';
import { AuthLayout } from '@/components/AuthLayout';
import { Warning } from '@phosphor-icons/react';

import api from '@/lib/api';
import { useAuthStore } from '@/store/useAuthStore';

export const Register: React.FC = () => {
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [nickname, setNickname] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [sendingCode, setSendingCode] = useState(false);
  const [error, setError] = useState('');
  const [agreedToTerms, setAgreedToTerms] = useState(false);
  const [codeSent, setCodeSent] = useState(false);
  const [countdown, setCountdown] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    const { user } = useAuthStore.getState();
    if (user) navigate('/', { replace: true });
  }, []);
  useEffect(() => {
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, []);

  const [searchParams] = useSearchParams();
  const getInstitutionSlug = (): string => {
    const fromParam = searchParams.get('institution');
    if (fromParam) return fromParam;
    const cookie = document.cookie.split('; ').find(r => r.startsWith('institution_invite='));
    if (cookie) return cookie.split('=')[1];
    return '';
  };
  const getInstitutionRole = (): string => {
    const cookie = document.cookie.split('; ').find(r => r.startsWith('institution_invite_role='));
    if (cookie) return cookie.split('=')[1];
    return 'student';
  };
  const institutionSlug = getInstitutionSlug();
  const institutionRole = getInstitutionRole();
  const refCode = searchParams.get('ref') || '';

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
    } catch (err: any) {
      setError(err.response?.data?.error || '发送失败');
    } finally {
      setSendingCode(false);
    }
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!code.trim()) { setError('请输入验证码'); return; }
    setLoading(true);
    setError('');
    try {
      await api.post('/users/register/', { email, code, nickname, password, agreed_to_terms: agreedToTerms, referral_code: refCode });
      navigate(institutionSlug ? `/login?institution=${institutionSlug}&role=${institutionRole}` : '/login');
    } catch (err: any) {
      setError(err.response?.data?.error || Object.values(err.response?.data || {}).flat()[0] as string || '注册失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout
      title="创建账号"
      subtitle="开启你的 UniMind 学习之旅"
      footer={
        <p className="text-sm text-[#6E6E73] dark:text-white/40">
          已有账号？
          <Link
            to={institutionSlug ? `/login?institution=${institutionSlug}&role=${institutionRole}` : '/login'}
            className="text-[#1D1D1F] dark:text-white font-medium hover:underline ml-1"
          >
            登录
          </Link>
        </p>
      }
    >
      {/* Referral banner */}
      {refCode && (
        <div className="rounded-xl bg-blue-50 dark:bg-blue-950/25 border border-blue-200 dark:border-blue-800/40 px-4 py-3 mb-5 text-sm text-blue-700 dark:text-blue-400">
          通过推荐链接注册，完成首次购买后你和推荐人都将获得奖励
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
            邮箱
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
              className="h-12 rounded-xl font-medium shrink-0"
            >
              {sendingCode ? '发送中' : countdown > 0 ? `${countdown}s` : '获取验证码'}
            </Button>
          </div>
        </div>

        <div className="space-y-1.5">
          <label htmlFor="reg-code" className="text-sm font-medium text-[#1D1D1F] dark:text-white/85">
            验证码
          </label>
          <Input
            id="reg-code"
            placeholder="输入 6 位验证码"
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
            昵称
          </label>
          <Input
            id="reg-nickname"
            placeholder="你的称呼"
            value={nickname}
            onChange={(e) => setNickname(e.target.value)}
            className="h-12 rounded-xl"
            required
          />
        </div>

        <div className="space-y-1.5">
          <label htmlFor="reg-password" className="text-sm font-medium text-[#1D1D1F] dark:text-white/85">
            密码
          </label>
          <Input
            id="reg-password"
            type="password"
            placeholder="至少 8 位"
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
            我已阅读并同意
            <Link to="/terms" className="text-[#1D1D1F] dark:text-white font-medium hover:underline mx-0.5">用户协议</Link>
            和
            <Link to="/privacy" className="text-[#1D1D1F] dark:text-white font-medium hover:underline ml-0.5">隐私政策</Link>
          </label>
        </div>

        <Button
          type="submit"
          className="w-full h-12 rounded-xl font-semibold tracking-tight text-[15px]"
          disabled={loading || !agreedToTerms}
        >
          {loading ? '注册中...' : '注册'}
        </Button>
      </form>
    </AuthLayout>
  );
};
