import React, { useEffect, useState } from 'react';
import api from '@/lib/api';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Check, X } from '@phosphor-icons/react';

interface JoinReq {
  id: number;
  user: number;
  user_name: string;
  user_nickname: string;
  invite_slug_used: string | null;
  status: string;
  message: string;
  created_at: string;
  reviewed_at: string | null;
}

export const JoinRequestSection: React.FC = () => {
  const [requests, setRequests] = useState<JoinReq[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('pending');

  const fetchRequests = () => {
    setLoading(true);
    api.get(`/users/institution/me/join-requests/?status=${statusFilter}`)
      .then(res => { setRequests(res.data); })
      .catch(() => toast.error('加载申请列表失败'))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchRequests(); }, [statusFilter]);

  const review = (id: number, action: 'approved' | 'rejected') => {
    api.patch(`/users/institution/me/join-requests/${id}/review/`, { status: action })
      .then(() => {
        toast.success(action === 'approved' ? '已通过' : '已拒绝');
        fetchRequests();
      })
      .catch(() => toast.error('操作失败'));
  };

  const statusBadge = (s: string) => {
    if (s === 'pending') return <Badge variant="outline" className="text-[10px] h-5">待审批</Badge>;
    if (s === 'approved') return <Badge variant="apple-green" className="text-[10px] h-5">已通过</Badge>;
    return <Badge variant="secondary" className="text-[10px] h-5">已拒绝</Badge>;
  };

  if (loading) return <div className="space-y-3">{Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-16 rounded-2xl" />)}</div>;

  return (
    <Card variant="apple" className="rounded-2xl">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-extrabold">加入申请</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <Tabs value={statusFilter} onValueChange={setStatusFilter}>
          <TabsList className="bg-muted/50 p-0.5 rounded-xl h-auto gap-0.5">
            {['pending', 'approved', 'rejected'].map(s => (
              <TabsTrigger key={s} value={s} className="rounded-lg px-3 py-1 text-[11px] data-[state=active]:bg-background">
                {s === 'pending' ? '待审批' : s === 'approved' ? '已通过' : '已拒绝'}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>

        {requests.length === 0 && <p className="text-xs text-muted-foreground py-6 text-center">暂无{statusFilter === 'pending' ? '待审批' : statusFilter === 'approved' ? '已通过' : '已拒绝'}的申请</p>}

        {requests.map(r => (
          <div key={r.id} className="flex items-center gap-3 p-3 rounded-xl bg-muted/30 border border-border/30">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-xs font-bold text-foreground/80">{r.user_nickname || r.user_name}</span>
                {statusBadge(r.status)}
              </div>
              <div className="flex gap-3 text-[10px] text-muted-foreground">
                <span>{new Date(r.created_at).toLocaleDateString('zh-CN')}</span>
                {r.invite_slug_used && <span>通过 {r.invite_slug_used.slice(0, 8)}…</span>}
                {r.message && <span className="truncate max-w-[120px]">{r.message}</span>}
              </div>
            </div>
            {r.status === 'pending' && (
              <div className="flex items-center gap-1.5 shrink-0">
                <Button size="sm" variant="outline" className="h-7 rounded-lg text-xs gap-1 text-emerald-600" onClick={() => review(r.id, 'approved')}><Check className="w-3 h-3" />通过</Button>
                <Button size="sm" variant="outline" className="h-7 rounded-lg text-xs gap-1 text-destructive" onClick={() => review(r.id, 'rejected')}><X className="w-3 h-3" />拒绝</Button>
              </div>
            )}
          </div>
        ))}
      </CardContent>
    </Card>
  );
};
