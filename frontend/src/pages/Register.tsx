import React, { useState, useEffect, useRef } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';

import { useTranslation } from 'react-i18next';

import api from '@/lib/api';
import { useAuthStore } from '@/store/useAuthStore';

export const Register: React.FC = () => {
  const { t } = useTranslation('auth');
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

  // 已登录则跳转首页
  useEffect(() => {
    const { token } = useAuthStore.getState();
    if (token) {
      navigate('/', { replace: true });
    }
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
          if (prev <= 1) {
            clearInterval(timerRef.current!);
            timerRef.current = null;
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
    } catch (err: any) {
      setError(err.response?.data?.error || t('register.errors.sendCodeFailed'));
    } finally {
      setSendingCode(false);
    }
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!code.trim()) { setError(t('register.errors.enterCode')); return; }
    setLoading(true);
    setError('');
    try {
      await api.post('/users/register/', { email, code, nickname, password, agreed_to_terms: agreedToTerms });
      navigate(institutionSlug ? `/login?institution=${institutionSlug}&role=${institutionRole}` : '/login');
    } catch (err: any) {
      setError(err.response?.data?.error || Object.values(err.response?.data || {}).flat()[0] as string || t('register.errors.registerFailed'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-unimind-bg-secondary flex items-center justify-center p-4">
      <Card className="w-full max-w-md border-none shadow-lg rounded-3xl bg-white/80 backdrop-blur-xl">
        <CardHeader className="p-6 space-y-1 text-center">
          <CardTitle className="text-2xl font-bold tracking-tight">{t('register.title')}</CardTitle>
          <CardDescription>{t('register.subtitle')}</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleRegister} className="space-y-4">
            {error && <p className="text-sm text-center bg-red-50 text-red-600 rounded-xl py-2.5 px-3">{error}</p>}

            <div className="flex gap-2">
              <Input
                type="email"
                placeholder={t('register.email')}
                value={email}
                onChange={(e) => { setEmail(e.target.value); setCodeSent(false); }}
                autoComplete="email"
                spellCheck={false}
                className="bg-slate-50/50 border-none h-12 rounded-xl focus-visible:ring-black flex-1"
                required
              />
              <Button
                type="button"
                onClick={handleSendCode}
                disabled={sendingCode || !email.trim() || countdown > 0}
                className="h-12 rounded-xl bg-black text-white font-medium shrink-0"
              >
                {sendingCode ? t('register.sending') : countdown > 0 ? `${countdown}s` : t('register.getCode')}
              </Button>
            </div>

            <div className="space-y-2">
              <Input
                placeholder={t('register.code')}
                value={code}
                onChange={(e) => setCode(e.target.value)}
                autoComplete="one-time-code"
                spellCheck={false}
                className="bg-slate-50/50 border-none h-12 rounded-xl focus-visible:ring-black text-lg tracking-widest font-mono"
                maxLength={6}
                required
              />
            </div>

            <div className="space-y-2">
              <Input
                placeholder={t('register.nickname')}
                value={nickname}
                onChange={(e) => setNickname(e.target.value)}
                className="bg-slate-50/50 border-none h-12 rounded-xl focus-visible:ring-black"
              />
            </div>

            <div className="space-y-2">
              <Input
                type="password"
                placeholder={t('register.password')}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
                spellCheck={false}
                className="bg-slate-50/50 border-none h-12 rounded-xl focus-visible:ring-black"
                minLength={6}
                required
              />
            </div>

            <div className="flex items-start gap-2">
              <Checkbox
                id="agree-terms"
                checked={agreedToTerms}
                onCheckedChange={(checked) => setAgreedToTerms(checked === true)}
                className="mt-0.5"
              />
              <label htmlFor="agree-terms" className="text-xs text-muted-foreground leading-relaxed cursor-pointer">
                我已阅读并同意{' '}
                <Link to="/terms" className="text-black font-medium hover:underline">用户协议</Link>
                {' '}和{' '}
                <Link to="/privacy" className="text-black font-medium hover:underline">隐私政策</Link>
              </label>
            </div>

            <Button className="w-full h-12 bg-black text-white rounded-xl font-medium hover:bg-black/90 transition-all" disabled={loading || !agreedToTerms}>
              {loading ? t('register.registering') : t('register.submit')}
            </Button>
          </form>
          <div className="mt-6 text-center text-sm text-muted-foreground">
            {t('register.hasAccount')}{" "}
            <Link to={institutionSlug ? `/login?institution=${institutionSlug}&role=${institutionRole}` : '/login'} className="text-black font-semibold hover:underline">
              {t('register.loginLink')}
            </Link>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};
