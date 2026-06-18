import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { useAuthStore } from '@/store/useAuthStore';
import { toast } from 'sonner';
import api from '@/lib/api';

type Status = 'loading' | 'joining' | 'success' | 'conflict' | 'unauthenticated';

export const JoinPage: React.FC = () => {
  const { invite_slug } = useParams<{ invite_slug: string }>();
  const navigate = useNavigate();
  const { user, updateUser } = useAuthStore();
  const [status, setStatus] = useState<Status>('loading');
  const [instName, setInstName] = useState('');

  useEffect(() => {
    if (!invite_slug) {
      navigate('/');
      return;
    }

    // 未登录 → 跳注册页，带上 invite_slug 作为 institution 参数
    if (!user) {
      setStatus('unauthenticated');
      return;
    }

    // 已有所属机构 → 冲突提示
    if (user.institution || user.institution_id) {
      setStatus('conflict');
      return;
    }

    // 已登录 + 无机构 → 自动加入
    setStatus('joining');
    api.post('/users/institution/join-by-invite-slug/', { invite_slug })
      .then(async (res) => {
        setInstName(res.data.institution?.name || '');
        const meRes = await api.get('/users/me/');
        updateUser(meRes.data);
        setStatus('success');
        toast.success('已成功加入机构');
      })
      .catch((err) => {
        const msg = err.response?.data?.error || '加入失败';
        toast.error(msg);
        navigate('/');
      });
  }, [invite_slug, user, navigate, updateUser]);

  // 未登录 → 引导注册
  if (status === 'unauthenticated') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background p-4">
        <Card className="w-full max-w-md text-center">
          <CardHeader>
            <CardTitle>邀请加入</CardTitle>
            <CardDescription>请先登录或注册，然后将自动加入机构</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Button className="w-full" onClick={() => navigate(`/register?institution=${invite_slug}`)}>
              注册新账号
            </Button>
            <Button variant="outline" className="w-full" onClick={() => navigate(`/login?institution=${invite_slug}`)}>
              已有账号，去登录
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  // 已有机构 → 冲突
  if (status === 'conflict') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background p-4">
        <Card className="w-full max-w-md text-center">
          <CardHeader>
            <CardTitle>无法加入</CardTitle>
            <CardDescription>你已有所属机构，不能重复加入。如需更换，请先退出当前机构。</CardDescription>
          </CardHeader>
          <CardContent>
            <Button className="w-full" onClick={() => navigate('/')}>
              返回首页
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  // 加入中
  if (status === 'joining' || status === 'loading') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background p-4">
        <Card className="w-full max-w-md text-center">
          <CardHeader>
            <CardTitle>正在加入机构...</CardTitle>
            <CardDescription>请稍候</CardDescription>
          </CardHeader>
        </Card>
      </div>
    );
  }

  // 成功
  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-4">
      <Card className="w-full max-w-md text-center">
        <CardHeader>
          <CardTitle>加入成功</CardTitle>
          <CardDescription>你已成功加入{instName ? `「${instName}」` : '机构'}</CardDescription>
        </CardHeader>
        <CardContent>
          <Button className="w-full" onClick={() => navigate('/')}>
            进入首页
          </Button>
        </CardContent>
      </Card>
    </div>
  );
};
