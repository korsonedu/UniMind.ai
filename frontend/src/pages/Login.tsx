import React, { useState, useEffect } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { AuthLayout } from '@/components/AuthLayout';
import { useAuthStore } from '@/store/useAuthStore';
import { Warning, Spinner } from '@phosphor-icons/react';

import api from '@/lib/api';
import { useInstitutionStore } from '@/store/useInstitutionStore';

type LoginTab = 'password' | 'code';

export const Login: React.FC = () => {
  const [tab, setTab] = useState<LoginTab>('password');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [sendingCode, setSendingCode] = useState(false);
  const { setAuth, updateUser } = useAuthStore();
  const { fetchFeatures } = useInstitutionStore();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  useEffect(() => {
    const { user } = useAuthStore.getState();
    if (user) navigate('/', { replace: true });
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

  const handlePasswordLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim() || !password) return;
    setLoading(true);
    setError('');
    try {
      const response = await api.post('/users/login/', { username: email, password });
      const user = response.data.user;
      const token = response.data.token;
      setAuth(user, token);
      if (institutionSlug) {
        try {
          await api.post('/users/institution/join-by-slug/', { slug: institutionSlug, role: institutionRole });
          const meRes = await api.get('/users/me/');
          updateUser(meRes.data);
        } catch (_err) {}
      }
      await fetchFeatures();
      navigate('/');
    } catch (err: any) {
      const errorData = err.response?.data;
      setError(errorData?.error || errorData?.non_field_errors?.[0] || errorData?.detail || '登录失败');
    } finally {
      setLoading(false);
    }
  };

  const handleSendCode = async () => {
    if (!email.trim()) return;
    setSendingCode(true);
    setError('');
    try {
      await api.post('/users/send-verification-code/', { email, purpose: 'login_by_code' });
      navigate(`/verify-code?email=${encodeURIComponent(email)}&purpose=login_by_code${institutionSlug ? `&institution=${institutionSlug}&role=${institutionRole}` : ''}`);
    } catch (err: any) {
      setError(err.response?.data?.error || '发送失败，请稍后重试');
      setSendingCode(false);
    }
  };

  return (
    <AuthLayout
      title="欢迎回来"
      subtitle={tab === 'password' ? '登录你的 UniMind 账号' : '新用户将自动创建账号'}
      footer={
        tab === 'password' ? (
          <p className="text-sm text-[#6E6E73] dark:text-white/40">
            没有账号？
            <Link
              to={institutionSlug ? `/register?institution=${institutionSlug}` : '/register'}
              className="text-[#1D1D1F] dark:text-white font-medium hover:underline ml-1"
            >
              注册
            </Link>
          </p>
        ) : undefined
      }
    >
      {/* Tab switcher */}
      <div className="flex rounded-xl bg-[#F5F5F7] dark:bg-white/[0.06] p-1 mb-6">
        <button
          type="button"
          onClick={() => { setTab('password'); setError(''); }}
          className={`
            flex-1 py-2.5 text-sm font-medium rounded-lg transition-all duration-200
            ${tab === 'password'
              ? 'bg-white dark:bg-white/[0.12] text-[#1D1D1F] dark:text-white shadow-sm'
              : 'text-[#8E8E93] dark:text-white/30 hover:text-[#6E6E73] dark:hover:text-white/50'
            }
          `}
        >
          密码登录
        </button>
        <button
          type="button"
          onClick={() => { setTab('code'); setError(''); }}
          className={`
            flex-1 py-2.5 text-sm font-medium rounded-lg transition-all duration-200
            ${tab === 'code'
              ? 'bg-white dark:bg-white/[0.12] text-[#1D1D1F] dark:text-white shadow-sm'
              : 'text-[#8E8E93] dark:text-white/30 hover:text-[#6E6E73] dark:hover:text-white/50'
            }
          `}
        >
          验证码登录
        </button>
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
          邮箱
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
              密码
            </label>
            <Input
              id="login-password"
              type="password"
              placeholder="输入密码"
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
            className="w-full h-12 rounded-xl font-semibold tracking-tight text-[15px]"
            disabled={loading}
          >
            {loading ? '登录中...' : '登录'}
          </Button>
        </form>
      )}

      {/* Code tab */}
      {tab === 'code' && (
        <div className="space-y-1.5">
          <Button
            type="button"
            variant="outline"
            className="w-full h-12 rounded-xl font-medium"
            disabled={sendingCode || !email.trim()}
            onClick={handleSendCode}
          >
            {sendingCode ? <Spinner className="h-4 w-4 animate-spin" /> : '发送验证码'}
          </Button>
          <p className="text-xs text-[#AEAEB2] dark:text-white/25 text-center pt-1">
            未注册邮箱自动创建账号，验证码 10 分钟内有效
          </p>
        </div>
      )}
    </AuthLayout>
  );
};
