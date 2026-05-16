import React, { useState } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useAuthStore } from '@/store/useAuthStore';
import { toast } from 'sonner';

import api from '@/lib/api';

export const Login: React.FC = () => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const { setAuth, updateUser } = useAuthStore();
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

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      const response = await api.post('/users/login/', { username, password });
      const user = response.data.user;
      const token = response.data.token;
      setAuth(user, token);

      // Auto-join institution from invite link or registration flow
      if (institutionSlug) {
        try {
          await api.post('/users/institution/join-by-slug/', { slug: institutionSlug });
          const meRes = await api.get('/users/me/');
          updateUser(meRes.data);
        } catch (err: any) {
          toast.error(err.response?.data?.error || '加入机构失败，可稍后在设置中重试');
        }
      }

      navigate('/');
    } catch (err: any) {
      const errorData = err.response?.data;
      setError(errorData?.error || errorData?.non_field_errors?.[0] || errorData?.detail || '登录失败，请检查用户名或密码');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#F5F5F7] flex items-center justify-center p-4">
      <Card className="w-full max-w-md border-none shadow-2xl rounded-3xl bg-white/80 backdrop-blur-xl p-4">
        <CardHeader className="space-y-1 text-center">
          <CardTitle className="text-2xl font-bold tracking-tight">欢迎回来</CardTitle>
          <CardDescription>登录你的网校账号，继续你的学习之旅</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleLogin} className="space-y-4">
            {error && <p className="text-red-500 text-xs text-center">{error}</p>}
            <div className="space-y-2">
              <Input 
                placeholder="邮箱或用户名" 
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="bg-slate-50/50 border-none h-12 rounded-xl focus-visible:ring-black"
                required
              />
            </div>
            <div className="space-y-2">
              <Input 
                type="password" 
                placeholder="密码" 
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="bg-slate-50/50 border-none h-12 rounded-xl focus-visible:ring-black"
                required
              />
            </div>
            <Button className="w-full h-12 bg-black text-white rounded-xl font-medium hover:bg-black/90 transition-all" disabled={loading}>
              {loading ? "登录中..." : "立即登录"}
            </Button>
          </form>
          <div className="mt-6 text-center text-sm text-muted-foreground">
            还没有账号？{" "}
            <Link to={institutionSlug ? `/register?institution=${institutionSlug}` : '/register'} className="text-black font-semibold hover:underline">
              立即注册
            </Link>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};
