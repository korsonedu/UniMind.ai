import React, { useState } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

import api from '@/lib/api';

export const Register: React.FC = () => {
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
    if (!email.trim()) { setError('请先输入邮箱'); return; }
    setSendingCode(true);
    setError('');
    try {
      await api.post('/users/send-verification-code/', { email });
      setCodeSent(true);
    } catch (err: any) {
      setError(err.response?.data?.error || '发送验证码失败');
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
      await api.post('/users/register/', { email, code, nickname, password });
      navigate(institutionSlug ? `/login?institution=${institutionSlug}` : '/login');
    } catch (err: any) {
      setError(err.response?.data?.error || Object.values(err.response?.data || {}).flat()[0] as string || '注册失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#F5F5F7] flex items-center justify-center p-4">
      <Card className="w-full max-w-md border-none shadow-2xl rounded-3xl bg-white/80 backdrop-blur-xl p-4">
        <CardHeader className="space-y-1 text-center">
          <CardTitle className="text-2xl font-bold tracking-tight">创建账号</CardTitle>
          <CardDescription>开启你的 UniMind 学术之旅</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleRegister} className="space-y-4">
            {error && <p className="text-red-500 text-xs text-center">{error}</p>}

            <div className="flex gap-2">
              <Input
                type="email"
                placeholder="邮箱"
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
                {sendingCode ? '发送中' : codeSent ? '已发送' : '获取验证码'}
              </Button>
            </div>

            <div className="space-y-2">
              <Input
                placeholder="验证码"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                className="bg-slate-50/50 border-none h-12 rounded-xl focus-visible:ring-black text-lg tracking-widest font-mono"
                maxLength={6}
                required
              />
            </div>

            <div className="space-y-2">
              <Input
                placeholder="昵称（选填）"
                value={nickname}
                onChange={(e) => setNickname(e.target.value)}
                className="bg-slate-50/50 border-none h-12 rounded-xl focus-visible:ring-black"
              />
            </div>

            <div className="space-y-2">
              <Input
                type="password"
                placeholder="设置密码（至少 6 位）"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="bg-slate-50/50 border-none h-12 rounded-xl focus-visible:ring-black"
                minLength={6}
                required
              />
            </div>

            <Button className="w-full h-12 bg-black text-white rounded-xl font-medium hover:bg-black/90 transition-all" disabled={loading}>
              {loading ? "注册中..." : "立即注册 · 免费试用"}
            </Button>
          </form>
          <div className="mt-6 text-center text-sm text-muted-foreground">
            已有账号？{" "}
            <Link to={institutionSlug ? `/login?institution=${institutionSlug}` : '/login'} className="text-black font-semibold hover:underline">
              去登录
            </Link>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};
