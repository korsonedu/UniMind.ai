import React, { useState } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

import { useTranslation } from 'react-i18next';

import api from '@/lib/api';

export const Register: React.FC = () => {
  const { t } = useTranslation('auth');
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [nickname, setNickname] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [sendingCode, setSendingCode] = useState(false);
  const [error, setError] = useState('');
  const [codeSent, setCodeSent] = useState(false);
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const getInstitutionSlug = (): string => {
    const fromParam = searchParams.get('institution');
    if (fromParam) return fromParam;
    const cookie = document.cookie.split('; ').find(r => r.startsWith('institution_invite='));
    if (cookie) return cookie.split('=')[1];
    return '';
  };
  const institutionSlug = getInstitutionSlug();

  const handleSendCode = async () => {
    if (!email.trim()) { setError(t('register.errors.enterEmail')); return; }
    setSendingCode(true);
    setError('');
    try {
      await api.post('/users/send-verification-code/', { email });
      setCodeSent(true);
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
      await api.post('/users/register/', { email, code, nickname, password });
      navigate(institutionSlug ? `/login?institution=${institutionSlug}` : '/login');
    } catch (err: any) {
      setError(err.response?.data?.error || Object.values(err.response?.data || {}).flat()[0] as string || t('register.errors.registerFailed'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-unimind-bg-secondary flex items-center justify-center p-4">
      <Card className="w-full max-w-md border-none shadow-2xl rounded-3xl bg-white/80 backdrop-blur-xl p-4">
        <CardHeader className="space-y-1 text-center">
          <CardTitle className="text-2xl font-bold tracking-tight">{t('register.title')}</CardTitle>
          <CardDescription>{t('register.subtitle')}</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleRegister} className="space-y-4">
            {error && <p className="text-red-500 text-xs text-center">{error}</p>}

            <div className="flex gap-2">
              <Input
                type="email"
                placeholder={t('register.email')}
                value={email}
                onChange={(e) => { setEmail(e.target.value); setCodeSent(false); }}
                className="bg-slate-50/50 border-none h-12 rounded-xl focus-visible:ring-black flex-1"
                required
              />
              <Button
                type="button"
                onClick={handleSendCode}
                disabled={sendingCode || !email.trim()}
                className="h-12 rounded-xl bg-black text-white font-medium shrink-0"
              >
                {sendingCode ? t('register.sending') : codeSent ? t('register.codeSent') : t('register.getCode')}
              </Button>
            </div>

            <div className="space-y-2">
              <Input
                placeholder={t('register.code')}
                value={code}
                onChange={(e) => setCode(e.target.value)}
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
                className="bg-slate-50/50 border-none h-12 rounded-xl focus-visible:ring-black"
                minLength={6}
                required
              />
            </div>

            <Button className="w-full h-12 bg-black text-white rounded-xl font-medium hover:bg-black/90 transition-all" disabled={loading}>
              {loading ? t('register.registering') : t('register.submit')}
            </Button>
          </form>
          <div className="mt-6 text-center text-sm text-muted-foreground">
            {t('register.hasAccount')}{" "}
            <Link to={institutionSlug ? `/login?institution=${institutionSlug}` : '/login'} className="text-black font-semibold hover:underline">
              {t('register.loginLink')}
            </Link>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};
