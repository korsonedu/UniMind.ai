import React, { useEffect, useState } from 'react';
import api from '@/lib/api';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Link, Plus, Copy, Trash } from '@phosphor-icons/react';

interface Invite {
  id: number;
  slug: string;
  assigned_role: string;
  max_uses: number | null;
  used_count: number;
  expires_at: string | null;
  requires_approval: boolean;
  is_active: boolean;
  created_at: string;
}

const ROLE_LABEL: Record<string, string> = {
  owner: '机构所有者',
  teacher: '教师',
  student: '学员',
};

export const InstitutionInviteSection: React.FC = () => {
  const [invites, setInvites] = useState<Invite[]>([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [assignedRole, setAssignedRole] = useState('student');
  const [requireApproval, setRequireApproval] = useState(true);
  const [maxUses, setMaxUses] = useState('');
  const [creating, setCreating] = useState(false);

  const fetchInvites = () => {
    api.get('/users/institution/me/invites/')
      .then(res => { setInvites(res.data); })
      .catch(() => toast.error('加载邀请链接失败'))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchInvites(); }, []);

  const copyLink = (slug: string) => {
    navigator.clipboard.writeText(`${window.location.origin}/join/${slug}`)
      .then(() => toast.success('已复制邀请链接'))
      .catch(() => toast.error('复制失败'));
  };

  const toggleActive = (invite: Invite) => {
    api.patch(`/users/institution/me/invites/${invite.id}/`, { is_active: !invite.is_active })
      .then(() => fetchInvites())
      .catch(() => toast.error('操作失败'));
  };

  const deleteInvite = (invite: Invite) => {
    if (!window.confirm(`确定删除此邀请链接？`)) return;
    api.delete(`/users/institution/me/invites/${invite.id}/`)
      .then(() => { fetchInvites(); toast.success('已删除'); })
      .catch(() => toast.error('删除失败'));
  };

  const createInvite = () => {
    setCreating(true);
    const payload: any = { assigned_role: assignedRole, requires_approval: requireApproval };
    const m = parseInt(maxUses, 10);
    if (m > 0) payload.max_uses = m;
    api.post('/users/institution/me/invites/', payload)
      .then(() => { fetchInvites(); setCreateOpen(false); toast.success('邀请链接已创建'); })
      .catch(() => toast.error('创建失败'))
      .finally(() => setCreating(false));
  };

  if (loading) return <div className="space-y-3">{Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-20 rounded-2xl" />)}</div>;

  return (
    <Card variant="apple" className="rounded-2xl">
      <CardHeader className="pb-3 flex flex-row items-center justify-between">
        <CardTitle className="text-sm font-extrabold">邀请链接管理</CardTitle>
        <Dialog open={createOpen} onOpenChange={setCreateOpen}>
          <DialogTrigger asChild>
            <Button size="sm" className="rounded-xl gap-1.5 h-8 text-xs"><Plus className="w-3.5 h-3.5" />新建邀请</Button>
          </DialogTrigger>
          <DialogContent className="rounded-2xl max-w-sm">
            <DialogHeader><DialogTitle className="text-sm">创建邀请链接</DialogTitle></DialogHeader>
            <div className="space-y-4 py-2">
              <div className="space-y-1.5">
                <Label className="text-[11px]">分配角色</Label>
                <Select value={assignedRole} onValueChange={setAssignedRole}>
                  <SelectTrigger className="h-9 rounded-xl text-xs"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {['student', 'teacher'].map(r => (
                      <SelectItem key={r} value={r} className="text-xs">{ROLE_LABEL[r]}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex items-center justify-between">
                <Label className="text-[11px]">需要审批</Label>
                <Switch checked={requireApproval} onCheckedChange={setRequireApproval} />
              </div>
              <div className="space-y-1.5">
                <Label className="text-[11px]">最大使用次数（留空不限）</Label>
                <Input className="h-9 rounded-xl text-xs" placeholder="例如 50" value={maxUses} onChange={e => setMaxUses(e.target.value)} />
              </div>
            </div>
            <DialogFooter>
              <Button onClick={createInvite} disabled={creating} className="rounded-xl text-xs w-full">{creating ? '创建中...' : '创建'}</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </CardHeader>
      <CardContent className="space-y-2">
        {invites.length === 0 && <p className="text-xs text-muted-foreground py-4 text-center">暂无邀请链接</p>}
        {invites.map(inv => (
          <div key={inv.id} className="flex items-center gap-3 p-3 rounded-xl bg-muted/30 border border-border/30">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-xs font-bold text-foreground/80 truncate">{inv.slug}</span>
                <Badge variant={inv.is_active ? 'apple-green' : 'secondary'} className="text-[10px] h-5">{inv.is_active ? '启用' : '停用'}</Badge>
                {inv.requires_approval && <Badge variant="outline" className="text-[10px] h-5">需审批</Badge>}
              </div>
              <div className="flex gap-3 text-[10px] text-muted-foreground">
                <span>{ROLE_LABEL[inv.assigned_role] || inv.assigned_role}</span>
                <span>{inv.used_count}{inv.max_uses ? `/${inv.max_uses}` : ''} 次使用</span>
              </div>
            </div>
            <div className="flex items-center gap-1 shrink-0">
              <Button variant="ghost" size="icon" className="h-7 w-7 rounded-lg" onClick={() => copyLink(inv.slug)}><Copy className="w-3 h-3" /></Button>
              <Button variant="ghost" size="icon" className="h-7 w-7 rounded-lg" onClick={() => toggleActive(inv)}><Switch className="w-3 h-3" /></Button>
              <Button variant="ghost" size="icon" className="h-7 w-7 rounded-lg text-destructive" onClick={() => deleteInvite(inv)}><Trash className="w-3 h-3" /></Button>
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
};
