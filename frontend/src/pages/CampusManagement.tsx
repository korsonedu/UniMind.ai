/**
 * 机构管理员 — 子校区/分校管理
 */
import { useState, useEffect, useCallback } from 'react';
import {
  Plus, Buildings, Users, Trash, Pencil, CheckCircle,
  ArrowsLeftRight, X, Spinner, Info,
} from '@phosphor-icons/react';
import api from '@/lib/api';
import { cn } from '@/lib/utils';
import { PageWrapper } from '@/components/PageWrapper';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { toast } from 'sonner';
import { useInstitutionStore } from '@/store/useInstitutionStore';

interface Campus {
  id: number;
  name: string;
  slug: string;
  plan: string;
  inherit_plan: boolean;
  is_active: boolean;
  is_plan_active: boolean;
  student_count: number;
  staff_count: number;
  business_type: string;
  created_at: string;
}

const PLAN_LABELS: Record<string, string> = {
  free: 'Free', starter: 'Starter', growth: 'Growth', enterprise: 'Enterprise',
};

export function CampusManagement() {
  const [campuses, setCampuses] = useState<Campus[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [editCampus, setEditCampus] = useState<Campus | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const store = useInstitutionStore();

  const fetchCampuses = useCallback(async () => {
    try {
      const { data } = await api.get('/users/institution/me/children/');
      setCampuses(Array.isArray(data) ? data : []);
    } catch {
      toast.error('无法加载校区列表');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchCampuses(); }, [fetchCampuses]);

  async function handleCreate(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSubmitting(true);
    const form = new FormData(e.currentTarget);
    const payload: Record<string, unknown> = {
      name: (form.get('name') as string).trim(),
      slug: (form.get('slug') as string).trim(),
      inherit_plan: form.get('inherit_plan') !== 'false',
    };
    if (payload.inherit_plan === false) {
      payload.plan = form.get('plan') || 'free';
    }
    try {
      const { data } = await api.post('/users/institution/me/children/', payload);
      await fetchCampuses();
      setShowCreate(false);
      toast.success(`校区「${data.name}」已创建`);
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error || '创建失败';
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleEdit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!editCampus) return;
    setSubmitting(true);
    const form = new FormData(e.currentTarget);
    const payload: Record<string, unknown> = {
      name: (form.get('name') as string).trim(),
      contact_name: (form.get('contact_name') as string).trim(),
      contact_email: (form.get('contact_email') as string).trim(),
      business_type: (form.get('business_type') as string).trim(),
      inherit_plan: form.get('inherit_plan') !== 'false',
    };
    if (payload.inherit_plan === false) {
      payload.plan = form.get('plan') || 'free';
    }
    try {
      await api.put(`/users/institution/me/children/${editCampus.id}/`, payload);
      setEditCampus(null);
      await fetchCampuses();
      toast.success('校区信息已更新');
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error || '更新失败';
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDeactivate(campus: Campus) {
    if (!confirm(`确定停用校区「${campus.name}」？停用后该校区学员无法登录。`)) return;
    try {
      await api.delete(`/users/institution/me/children/${campus.id}/`);
      await fetchCampuses();
      toast.success(`「${campus.name}」已停用`);
    } catch {
      toast.error('操作失败');
    }
  }

  async function handleSwitch(campus: Campus) {
    try {
      await api.post(`/users/institution/me/children/${campus.id}/context/`);
      store.switchCampus(campus.id);
      toast.success(`已切换到「${campus.name}」`);
    } catch {
      toast.error('切换失败');
    }
  }

  async function handleResetContext() {
    store.switchCampus(null);
    toast.success('已切换回总校聚合视图');
  }

  if (loading) {
    return (
      <PageWrapper title="校区管理">
        <div className="flex items-center justify-center py-20"><Spinner className="animate-spin h-8 w-8 text-muted-foreground" /></div>
      </PageWrapper>
    );
  }

  return (
    <PageWrapper title="校区管理">
      {/* header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <p className="text-muted-foreground text-sm">
            管理总校下属的所有校区 / 分校
          </p>
        </div>
        <div className="flex items-center gap-2">
          {store.currentCampusId && (
            <Button variant="outline" size="sm" onClick={handleResetContext}>
              <ArrowsLeftRight className="mr-1 h-4 w-4" />
              回到总校视图
            </Button>
          )}
          <Button size="sm" onClick={() => setShowCreate(true)}>
            <Plus className="mr-1 h-4 w-4" />
            新建校区
          </Button>
        </div>
      </div>

      {/* campus list */}
      {campuses.length === 0 ? (
        <Card className="p-12 text-center">
          <Buildings className="mx-auto h-12 w-12 mb-4 text-muted-foreground/40" />
          <p className="text-muted-foreground mb-4">暂无子校区</p>
          <Button onClick={() => setShowCreate(true)}>
            <Plus className="mr-1 h-4 w-4" />
            创建第一个校区
          </Button>
        </Card>
      ) : (
        <div className="grid gap-4">
          {campuses.map((c) => (
            <Card key={c.id} className={cn('p-5', !c.is_active && 'opacity-50')}>
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <Buildings className="h-5 w-5 text-primary" />
                    <h3 className="font-semibold text-lg">{c.name}</h3>
                    <Badge variant={c.is_plan_active ? 'default' : 'destructive'}>
                      {PLAN_LABELS[c.plan] || c.plan}
                    </Badge>
                    {c.inherit_plan && (
                      <Badge variant="outline" className="text-xs">
                        <Info className="mr-1 h-3 w-3" />
                        继承总校方案
                      </Badge>
                    )}
                    {!c.is_active && <Badge variant="destructive">已停用</Badge>}
                  </div>
                  <p className="text-sm text-muted-foreground">slug: {c.slug}</p>
                  <div className="flex items-center gap-4 mt-2 text-sm text-muted-foreground">
                    <span className="flex items-center gap-1">
                      <Users className="h-4 w-4" /> {c.student_count} 学员
                    </span>
                    <span className="flex items-center gap-1">
                      <Buildings className="h-4 w-4" /> {c.staff_count} 教职工
                    </span>
                    <span>创建于 {new Date(c.created_at).toLocaleDateString('zh-CN')}</span>
                  </div>
                </div>
                <div className="flex items-center gap-2 ml-4">
                  <Button variant="ghost" size="sm" onClick={() => handleSwitch(c)}>
                    <ArrowsLeftRight className="mr-1 h-4 w-4" />
                    切换
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => setEditCampus(c)}>
                    <Pencil className="h-4 w-4" />
                  </Button>
                  {c.is_active && (
                    <Button variant="ghost" size="sm" onClick={() => handleDeactivate(c)}>
                      <Trash className="h-4 w-4 text-destructive" />
                    </Button>
                  )}
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* create dialog */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>新建校区</DialogTitle>
            <DialogDescription>创建总校下属的分校区，默认继承总校版本方案。</DialogDescription>
          </DialogHeader>
          <form onSubmit={handleCreate} className="space-y-4 mt-2">
            <div>
              <Label htmlFor="c-name">校区名称 *</Label>
              <Input id="c-name" name="name" required placeholder="如：海淀校区" />
            </div>
            <div>
              <Label htmlFor="c-slug">标识符（留空自动生成）</Label>
              <Input id="c-slug" name="slug" placeholder="如：haidian" />
            </div>
            <div className="flex items-center justify-between">
              <Label htmlFor="c-inherit">继承总校版本方案</Label>
              <Switch id="c-inherit" name="inherit_plan" defaultChecked />
            </div>
            <Button type="submit" className="w-full" disabled={submitting}>
              {submitting ? <Spinner className="animate-spin mr-1 h-4 w-4" /> : <Plus className="mr-1 h-4 w-4" />}
              创建校区
            </Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* edit dialog */}
      <Dialog open={!!editCampus} onOpenChange={(v) => { if (!v) setEditCampus(null); }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>编辑校区</DialogTitle>
          </DialogHeader>
          {editCampus && (
            <form onSubmit={handleEdit} className="space-y-4 mt-2">
              <div>
                <Label htmlFor="e-name">校区名称</Label>
                <Input id="e-name" name="name" defaultValue={editCampus.name} required />
              </div>
              <div>
                <Label htmlFor="e-contact">联系人</Label>
                <Input id="e-contact" name="contact_name" />
              </div>
              <div>
                <Label htmlFor="e-email">联系邮箱</Label>
                <Input id="e-email" name="contact_email" type="email" />
              </div>
              <div>
                <Label htmlFor="e-biz">主营业务</Label>
                <Input id="e-biz" name="business_type" />
              </div>
              <div className="flex items-center justify-between">
                <Label htmlFor="e-inherit">继承总校版本方案</Label>
                <Switch id="e-inherit" name="inherit_plan" defaultChecked={editCampus.inherit_plan} />
              </div>
              {!editCampus.inherit_plan && (
                <div>
                  <Label htmlFor="e-plan">独立版本</Label>
                  <select id="e-plan" name="plan" defaultValue={editCampus.plan} className="w-full border rounded px-3 py-2 mt-1">
                    <option value="free">Free</option>
                    <option value="starter">Starter</option>
                    <option value="growth">Growth</option>
                    <option value="enterprise">Enterprise</option>
                  </select>
                </div>
              )}
              <Button type="submit" className="w-full" disabled={submitting}>
                {submitting ? <Spinner className="animate-spin mr-1 h-4 w-4" /> : <CheckCircle className="mr-1 h-4 w-4" />}
                保存
              </Button>
            </form>
          )}
        </DialogContent>
      </Dialog>
    </PageWrapper>
  );
}
