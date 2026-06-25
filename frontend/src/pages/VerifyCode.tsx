import React, { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { InputOTP, InputOTPGroup, InputOTPSlot } from '@/components/ui/input-otp';
import { AuthLayout } from '@/components/AuthLayout';
import { useAuthStore } from '@/store/useAuthStore';
import { useInstitutionStore } from '@/store/useInstitutionStore';
import { Warning, Spinner } from '@phosphor-icons/react';

import api from '@/lib/api';

export const VerifyCode: React.FC = () => {
  const [searchParams] = useSearchParams();
  const email = searchParams.get('email') || '';
  const institutionSlug = searchParams.get('institution') || '';
  const institutionRole = searchParams.get('role') || 'student';

  const [code, setCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [countdown, setCountdown] = useState(60);
  const [resending, setResending] = useState(false);

  const setAuth = useAuthStore(s => s.setAuth);
  const updateUser = useAuthStore(s => s.updateUser);
  const { fetchFeatures } = useInstitutionStore();
  const navigate = useNavigate();

  useEffect(() => {
    if (countdown <= 0) return;
    const timer = setInterval(() => setCountdown(prev => prev - 1), 1000);
    return () => clearInterval(timer);
  }, [countdown]);

  useEffect(() => {
    if (code.length === 6) handleLogin(code);
  }, [code]);

  useEffect(() => {
    if (!email) navigate('/login', { replace: true });
  }, [email]);

  const handleLogin = async (otp: string) => {
    setLoading(true);
    setError('');
    try {
      const response = await api.post('/users/login-by-code/', { email, code: otp });
      const user = response.data.user;
      const token = response.data.token;
      setAuth(user, token);
      if (institutionSlug) {
        try {
          await api.post('/users/institution/join-by-slug/', { slug: institutionSlug, role: institutionRole });
          const meRes = await api.get('/users/me/');
          updateUser(meRes.data);
        } catch (err) { console.error('Join institution after code login failed:', err); }
      }
      await fetchFeatures();
      navigate('/');
    } catch (err: any) {
      setCode('');
      setError(err.response?.data?.error || '验证码错误，请重试');
    } finally {
      setLoading(false);
    }
  };

  const handleResend = async () => {
    setResending(true);
    setError('');
    try {
      await api.post('/users/send-verification-code/', { email, purpose: 'login_by_code' });
      setCountdown(60);
    } catch (err: any) {
      setError(err.response?.data?.error || '重发失败');
    } finally {
      setResending(false);
    }
  };

  if (!email) return null;

  return (
    <AuthLayout
      title="验证邮箱"
      subtitle={
        <>
          验证码已发送至{' '}
          <span className="text-[#1D1D1F] dark:text-white font-medium">{email}</span>
        </>
      }
    >
      {/* Back button */}
      <button
        type="button"
        onClick={() => navigate(-1)}
        className="flex items-center gap-1 text-sm text-[#6E6E73] dark:text-white/40 hover:text-[#1D1D1F] dark:hover:text-white/70 transition-colors -mt-2 mb-5"
      >
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg" className="shrink-0">
          <path d="M10 3L5 8L10 13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
        返回
      </button>

      {/* Error banner */}
      {error && (
        <div className="flex items-start gap-2.5 rounded-xl bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800/40 px-4 py-3 mb-6 text-sm text-red-700 dark:text-red-400">
          <Warning className="h-4 w-4 mt-0.5 shrink-0" weight="fill" />
          <span>{error}</span>
        </div>
      )}

      {/* OTP Input */}
      <div className="flex justify-center mb-6">
        <InputOTP maxLength={6} value={code} onChange={setCode} disabled={loading}>
          <InputOTPGroup>
            <InputOTPSlot index={0} />
            <InputOTPSlot index={1} />
            <InputOTPSlot index={2} />
            <InputOTPSlot index={3} />
            <InputOTPSlot index={4} />
            <InputOTPSlot index={5} />
          </InputOTPGroup>
        </InputOTP>
      </div>

      {/* Loading indicator */}
      {loading && (
        <div className="flex items-center justify-center gap-2 text-sm text-[#AEAEB2] dark:text-white/25 mb-4">
          <Spinner className="h-4 w-4 animate-spin" />
          验证中...
        </div>
      )}

      {/* Resend */}
      <div className="text-center">
        <Button
          variant="link"
          size="sm"
          className="text-[#6E6E73] dark:text-white/40 text-xs font-normal"
          disabled={countdown > 0 || resending}
          onClick={handleResend}
        >
          {countdown > 0 ? `${countdown}s 后重新发送` : '重新发送验证码'}
        </Button>
      </div>
    </AuthLayout>
  );
};
