import { useCallback, useEffect, useState } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { useAuthStore } from '@/store/useAuthStore';
import { useInstitutionStore } from '@/store/useInstitutionStore';
import api from '@/lib/api';
import { Buildings, Plus, MagnifyingGlass, Spinner, Pencil, Power,Users, Calendar, ArrowLeft, Stack, Eye, Upload, ShieldCheck } from '@phosphor-icons/react';
import { Label } from '@/components/ui/label';
import { DirectionSelector } from '@/components/DirectionSelector';

import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import { useNavigate } from 'react-router-dom';
import { useConfirm } from '@/components/useConfirm';
import { useDebouncedValue } from '@/lib/useDebouncedValue';

interface Institution {
  id: number;
  name: string;
  slug: string;
  contact_name: string;
  contact_email: string;
  contact_phone: string;
  plan: string;
  plan_label: string;
  plan_expires_at: string | null;
  is_active: boolean;
  is_plan_active: boolean;
  student_count: number;
  max_students: number;
  created_at: string;
  notes: string;
  business_type: string;
}

const PLAN_COLORS: Record<string, string> = {
  free: 'bg-muted-foreground', starter: 'bg-primary', growth: 'bg-unimind-green', enterprise: 'bg-amber-500',
};

export default function InstitutionAdmin() {
  const navigate = useNavigate();
  const { user } = useAuthStore();
  const enterPreview = useInstitutionStore(s => s.enterPreview);
  const [institutions, setInstitutions] = useState<Institution[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const debouncedSearch = useDebouncedValue(search, 300);
  const [planFilter, setPlanFilter] = useState('');
  const [createOpen, setCreateOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<Institution | null>(null);
  const { confirm, Dialog: ConfirmDialog } = useConfirm();

  const fetchInstitutions = useCallback(async () => {
    try {
      const params: Record<string, string> = {};
      if (debouncedSearch) params.search = debouncedSearch;
      if (planFilter) params.plan = planFilter;
      const { data } = await api.get('/users/institutions/', { params });
      setInstitutions(data);
    } catch (e) { console.error('[InstitutionAdmin] fetch failed:', e); }
    setLoading(false);
  }, [debouncedSearch, planFilter]);

  useEffect(() => { fetchInstitutions(); }, [fetchInstitutions]);

  const handleActivate = async (id: number) => {
    try {
      await api.post(`/users/institutions/${id}/activate/`);
      fetchInstitutions();
    } catch { toast.error('激活失败'); }
  };
  const handleDeactivate = async (id: number) => {
    try {
      await api.post(`/users/institutions/${id}/deactivate/`);
      fetchInstitutions();
    } catch { toast.error('停用失败'); }
  };
  const handleDelete = async (id: number, name: string) => {
    if (!(await confirm(`确认删除机构「${name}」？该操作不可撤销。`))) return;
    try {
      await api.delete(`/users/institutions/${id}/`);
      fetchInstitutions();
    } catch { toast.error('删除失败'); }
  };

  // 机构所有者 → 自己的机构设置
  if (user?.is_institution_owner) {
    return <InstitutionSelfSettings />;
  }

  // 教师 → 无权限访问机构设置
  if (user?.is_institution_admin) {
    return (
      <div className="min-h-screen bg-muted flex items-center justify-center text-muted-foreground text-sm">
        仅机构所有者可访问机构设置
      </div>
    );
  }

  // 超级管理员 → 机构 CRUD
  if (!user?.is_admin) {
    return (
      <div className="min-h-screen bg-muted flex items-center justify-center text-muted-foreground text-sm">
        仅平台管理员可访问
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-muted">
      {/* Standalone admin header — no MainLayout dependency */}
      <header className="bg-white border-b border-border/60">
        <div className="max-w-5xl mx-auto px-4 h-14 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Button variant="ghost" size="sm" className="h-8 text-xs" onClick={() => navigate('/')}>
              <ArrowLeft className="h-4 w-4 mr-1" /> 返回 UniMind
            </Button>
            <span className="text-muted-foreground/40">|</span>
            <div className="flex items-center gap-2">
              <Stack className="h-4 w-4 text-primary" strokeWidth={2.5} />
              <span className="font-extrabold text-sm text-foreground tracking-tight">机构管理后台</span>
            </div>
          </div>
          <span className="text-xs text-muted-foreground">{user.nickname || user.username}</span>
        </div>
      </header>

      <div className="max-w-5xl mx-auto px-4 py-8 space-y-6">
        {/* Page header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-extrabold text-foreground tracking-tight">
              {institutions.length} 个机构
            </h1>
            <p className="text-sm text-muted-foreground/60 mt-1">管理购买方、版本和服务状态</p>
          </div>
          <Button variant="apple" size="sm" onClick={() => setCreateOpen(true)}>
            <Plus className="h-4 w-4" /> 新建机构
          </Button>
        </div>

        {/* Filters */}
      <div className="flex gap-3">
        <div className="relative flex-1 max-w-xs">
          <MagnifyingGlass className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="搜索机构名称…"
            className="pl-9"
            value={search} onChange={e => setSearch(e.target.value)}
          />
        </div>
        <div className="flex gap-1.5">
          {['', 'free', 'starter', 'growth', 'enterprise'].map(p => (
            <button
              key={p}
              onClick={() => setPlanFilter(p)}
              className={cn(
                'px-3 py-1.5 rounded-lg text-xs font-bold transition-colors',
                planFilter === p
                  ? 'bg-primary text-white'
                  : 'bg-muted text-muted-foreground/60 hover:bg-muted-foreground/15'
              )}
            >
              {p === '' ? '全部' : p.charAt(0).toUpperCase() + p.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {/* List */}
      {loading ? (
        <div className="flex justify-center py-16">
          <Spinner className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : institutions.length === 0 ? (
        <div className="text-center py-16 text-muted-foreground">
          <Buildings className="h-12 w-12 mx-auto mb-3 opacity-20" />
          <p className="text-sm font-medium">暂无机构</p>
          <p className="text-xs mt-1">点击右上角「新建机构」创建第一个购买方</p>
        </div>
      ) : (
        <div className="space-y-2">
          {institutions.map(inst => (
            <Card key={inst.id} variant="apple" className="p-5">
              <div className="flex items-center justify-between">
                {/* Left: info */}
                <div className="flex items-center gap-4 min-w-0">
                  <div className={cn('h-10 w-10 rounded-xl flex items-center justify-center shrink-0',
                    inst.is_active ? 'bg-primary/8' : 'bg-muted-foreground/10')}>
                    <Buildings className={cn('h-5 w-5',
                      inst.is_active ? 'text-primary' : 'text-muted-foreground')} />
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <h3 className="text-sm font-extrabold text-foreground truncate">{inst.name}</h3>
                      <Badge className={cn('text-[10px] font-bold text-white', PLAN_COLORS[inst.plan] || 'bg-muted-foreground')}>
                        {inst.plan_label}
                      </Badge>
                      {!inst.is_active && (
                        <Badge variant="outline" className="text-[10px] text-red-500 border-red-200">已停用</Badge>
                      )}
                      {inst.is_active && !inst.is_plan_active && (
                        <Badge variant="outline" className="text-[10px] text-amber-500 border-amber-200">已到期</Badge>
                      )}
                    </div>
                    <div className="flex items-center gap-4 mt-1 text-xs text-muted-foreground">
                      <span className="flex items-center gap-1"><Users className="h-3 w-3" />{inst.student_count}/{inst.max_students} 学员</span>
                      <span className="flex items-center gap-1"><Calendar className="h-3 w-3" />{inst.plan_expires_at ? inst.plan_expires_at.slice(0, 10) : '永久有效'}</span>
                      <span>{inst.contact_name} · {inst.contact_email}</span>
                    </div>
                  </div>
                </div>

                {/* Right: actions */}
                <div className="flex items-center gap-1.5 shrink-0">
                  <Button variant="ghost" size="sm" className="h-8 text-xs text-primary"
                    onClick={() => enterPreview(inst.id)}>
                    <Eye className="h-3.5 w-3.5 mr-1" />预览
                  </Button>
                  <Button variant="ghost" size="sm" className="h-8 text-xs" onClick={() => setEditTarget(inst)}>
                    <Pencil className="h-3.5 w-3.5 mr-1" />编辑
                  </Button>
                  {inst.is_active ? (
                    <Button variant="ghost" size="sm" className="h-8 text-xs text-amber-600" onClick={() => handleDeactivate(inst.id)}>
                      <Power className="h-3.5 w-3.5 mr-1" />停用
                    </Button>
                  ) : (
                    <Button variant="ghost" size="sm" className="h-8 text-xs text-emerald-600" onClick={() => handleActivate(inst.id)}>
                      <Power className="h-3.5 w-3.5 mr-1" />启用
                    </Button>
                  )}
                  <Button variant="ghost" size="sm" className="h-8 text-xs text-red-500" onClick={() => handleDelete(inst.id, inst.name)}>
                    删除
                  </Button>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Create Dialog */}
      <CreateInstitutionDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={() => { setCreateOpen(false); fetchInstitutions(); }}
      />

      {/* Edit Dialog */}
      {editTarget && (
        <EditInstitutionDialog
          institution={editTarget}
          open={!!editTarget}
          onClose={() => setEditTarget(null)}
          onUpdated={() => { setEditTarget(null); fetchInstitutions(); }}
        />
      )}
      {ConfirmDialog}
    </div>
  </div>
  );
}

/* ── Create Dialog ── */

function CreateInstitutionDialog({
  open, onClose, onCreated,
}: {
  open: boolean; onClose: () => void; onCreated: () => void;
}) {
  const [form, setForm] = useState({
    name: '', slug: '', contact_name: '', contact_email: '', contact_phone: '',
    plan: 'free', plan_expires_at: '', notes: '', business_type: '',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true); setError('');
    try {
      const payload: any = { ...form };
      if (!payload.plan_expires_at) delete payload.plan_expires_at;
      if (!payload.contact_phone) payload.contact_phone = '';
      if (!payload.slug) payload.slug = payload.name.toLowerCase().replace(/\s+/g, '-');
      await api.post('/users/institutions/', payload);
      onCreated();
    } catch (err: any) {
      setError(err.response?.data?.detail || err.response?.data?.error || '创建机构失败，请检查信息后重试');
    }
    setSaving(false);
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-md">
        <DialogHeader><DialogTitle>新建机构</DialogTitle></DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3">
          <Input placeholder="机构名称 *" required
            value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} />
          <div className="grid grid-cols-2 gap-2">
            <Input placeholder="联系人 *" required
              value={form.contact_name} onChange={e => setForm({ ...form, contact_name: e.target.value })} />
            <Input placeholder="联系邮箱 *" type="email" required
              value={form.contact_email} onChange={e => setForm({ ...form, contact_email: e.target.value })} />
          </div>
          <Input placeholder="联系电话"
            value={form.contact_phone} onChange={e => setForm({ ...form, contact_phone: e.target.value })} />
          <Input placeholder="主营业务，如：金融431、CPA、法考、教资等"
            value={form.business_type} onChange={e => setForm({ ...form, business_type: e.target.value })} />
          <p className="text-[11px] text-muted-foreground -mt-1">此项与模拟面试、AI 助教等多个功能关联，请务必正确填写。</p>
          <div className="grid grid-cols-2 gap-2">
            <select
              value={form.plan}
              onChange={e => setForm({ ...form, plan: e.target.value })}
              className="h-10 rounded-xl border border-border bg-background px-3 text-sm font-medium"
            >
              <option value="free">Free</option>
              <option value="starter">Starter</option>
              <option value="growth">Growth</option>
              <option value="enterprise">Enterprise</option>
            </select>
            <Input type="date"
              value={form.plan_expires_at} onChange={e => setForm({ ...form, plan_expires_at: e.target.value })} />
          </div>
          {error && <p className="text-xs text-red-500">{error}</p>}
          <DialogFooter>
            <Button type="button" variant="outline" size="sm" onClick={onClose}>取消</Button>
            <Button type="submit" variant="apple" size="sm" disabled={saving}>
              {saving ? '创建中…' : '创建'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/* ── Edit Dialog ── */

function EditInstitutionDialog({
  institution, open, onClose, onUpdated,
}: {
  institution: Institution; open: boolean; onClose: () => void; onUpdated: () => void;
}) {
  const [form, setForm] = useState({
    name: institution.name,
    contact_name: institution.contact_name,
    contact_email: institution.contact_email,
    contact_phone: institution.contact_phone || '',
    plan: institution.plan,
    plan_expires_at: institution.plan_expires_at?.slice(0, 10) || '',
    notes: institution.notes || '',
    business_type: institution.business_type || '',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true); setError('');
    try {
      const payload: any = { ...form };
      if (!payload.plan_expires_at) delete payload.plan_expires_at;
      await api.put(`/users/institutions/${institution.id}/`, payload);
      // Also change plan via dedicated endpoint if changed
      if (form.plan !== institution.plan) {
        await api.post(`/users/institutions/${institution.id}/change-plan/`, {
          plan: form.plan,
          plan_expires_at: payload.plan_expires_at || null,
        });
      }
      onUpdated();
    } catch (err: any) {
      setError(err.response?.data?.detail || '保存机构信息失败，请重试');
    }
    setSaving(false);
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-md">
        <DialogHeader><DialogTitle>编辑机构</DialogTitle></DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3">
          <Input placeholder="机构名称"
            value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} />
          <Input placeholder="联系人"
            value={form.contact_name} onChange={e => setForm({ ...form, contact_name: e.target.value })} />
          <Input placeholder="联系邮箱" type="email"
            value={form.contact_email} onChange={e => setForm({ ...form, contact_email: e.target.value })} />
          <Input placeholder="联系电话"
            value={form.contact_phone} onChange={e => setForm({ ...form, contact_phone: e.target.value })} />
          <Input placeholder="主营业务，如：金融431、CPA、法考、教资等"
            value={form.business_type} onChange={e => setForm({ ...form, business_type: e.target.value })} />
          <p className="text-[11px] text-muted-foreground -mt-1">此项与模拟面试、AI 助教等多个功能关联，请务必正确填写。</p>
          <div className="grid grid-cols-2 gap-2">
            <select
              value={form.plan}
              onChange={e => setForm({ ...form, plan: e.target.value })}
              className="h-10 rounded-xl border border-border bg-background px-3 text-sm font-medium"
            >
              <option value="free">Free</option>
              <option value="starter">Starter</option>
              <option value="growth">Growth</option>
              <option value="enterprise">Enterprise</option>
            </select>
            <Input type="date"
              value={form.plan_expires_at} onChange={e => setForm({ ...form, plan_expires_at: e.target.value })} />
          </div>
          <Input placeholder="备注"
            value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} />
          {error && <p className="text-xs text-red-500">{error}</p>}
          <DialogFooter>
            <Button type="button" variant="outline" size="sm" onClick={onClose}>取消</Button>
            <Button type="submit" variant="apple" size="sm" disabled={saving}>
              {saving ? '保存中…' : '保存'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/* ── Institution Self-Settings (for institution admins) ── */

function InstitutionSelfSettings() {
  const navigate = useNavigate();
  const [form, setForm] = useState({
    name: '', contact_name: '', contact_email: '', contact_phone: '', notes: '', business_type: '',
  });
  const [logo, setLogo] = useState<File | null>(null);
  const [logoPreview, setLogoPreview] = useState('');
  const [plan, setPlan] = useState('');
  const [planLabel, setPlanLabel] = useState('');
  const [expiresAt, setExpiresAt] = useState('');
  const [studentCount, setStudentCount] = useState(0);
  const [maxStudents, setMaxStudents] = useState(0);
  const [planActive, setPlanActive] = useState(false);
  const [saving, setSaving] = useState(false);

  // Direction editing
  const [directionOpen, setDirectionOpen] = useState(false);
  const [directionSubjects, setDirectionSubjects] = useState<any[]>([]);
  const [directionSelected, setDirectionSelected] = useState<string[]>([]);
  const [directionSaving, setDirectionSaving] = useState(false);
  const [directionError, setDirectionError] = useState('');

  const currentDirections = (form.business_type || '')
    .split(',').map((s: string) => s.trim()).filter(Boolean);

  useEffect(() => {
    api.get('/users/institution/me/update/').then(({ data }) => {
      setForm({
        name: data.name || '',
        contact_name: data.contact_name || '',
        contact_email: data.contact_email || '',
        contact_phone: data.contact_phone || '',
        notes: data.notes || '',
        business_type: data.business_type || '',
      });
      setLogoPreview(data.logo_url || '');
      setPlanLabel(data.plan_label || '');
      setPlan(data.plan || '');
      setExpiresAt(data.plan_expires_at || '');
      setStudentCount(data.student_count || 0);
      setMaxStudents(data.max_students || 0);
      setPlanActive(data.is_plan_active);
    }).catch((e) => {
      console.error('[InstitutionSelfSettings] fetch failed:', e);
      toast.error('加载机构信息失败');
    });
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      const fd = new FormData();
      fd.append('name', form.name);
      fd.append('contact_name', form.contact_name);
      fd.append('contact_email', form.contact_email);
      fd.append('contact_phone', form.contact_phone);
      fd.append('notes', form.notes);
      fd.append('business_type', form.business_type);
      if (logo) fd.append('logo', logo);
      const { data } = await api.put('/users/institution/me/update/', fd);
      if (data.logo_url) setLogoPreview(data.logo_url);
      setLogo(null);
      toast.success('机构信息已更新');
    } catch (e: any) {
      toast.error(e.response?.data?.error || '保存机构设置失败，请重试');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="min-h-screen bg-muted">
      <header className="bg-white border-b border-border/60">
        <div className="max-w-3xl mx-auto px-4 h-14 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Button variant="ghost" size="sm" className="h-8 text-xs" onClick={() => navigate('/')}>
              <ArrowLeft className="h-4 w-4 mr-1" /> 返回
            </Button>
            <span className="text-muted-foreground/40">|</span>
            <div className="flex items-center gap-2">
              <Buildings className="h-4 w-4 text-primary" />
              <span className="font-extrabold text-sm text-foreground">机构设置</span>
            </div>
          </div>
          <Badge className={cn('text-[10px] font-bold', planActive ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700')}>
            {planLabel} {planActive ? '· 生效中' : '· 已到期'}
          </Badge>
        </div>
      </header>

      <div className="max-w-3xl mx-auto px-4 py-8 space-y-6">
        <Card className="p-6 rounded-2xl border-none shadow-sm bg-white">
          <div className="grid grid-cols-3 gap-4 text-center">
            <div>
              <p className="text-[10px] font-bold uppercase text-muted-foreground">当前方案</p>
              <p className="text-sm font-bold mt-1">{planLabel}</p>
            </div>
            <div>
              <p className="text-[10px] font-bold uppercase text-muted-foreground">到期时间</p>
              <p className="text-sm font-bold mt-1">{expiresAt ? new Date(expiresAt).toLocaleDateString(navigator.language || 'zh-CN') : '永久'}</p>
            </div>
            <div>
              <p className="text-[10px] font-bold uppercase text-muted-foreground">学员数</p>
              <p className="text-sm font-bold mt-1">{studentCount} / {maxStudents}</p>
            </div>
          </div>
        </Card>

        <Card className="p-8 rounded-2xl border-none shadow-sm bg-white space-y-6">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label className="text-[10px] font-bold uppercase text-muted-foreground">机构名称</Label>
              <Input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} autoComplete="organization" className="h-10 rounded-xl bg-muted/50 border-none font-bold text-sm" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-[10px] font-bold uppercase text-muted-foreground">联系人</Label>
              <Input value={form.contact_name} onChange={e => setForm({ ...form, contact_name: e.target.value })} autoComplete="name" className="h-10 rounded-xl bg-muted/50 border-none font-bold text-sm" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-[10px] font-bold uppercase text-muted-foreground">联系邮箱</Label>
              <Input value={form.contact_email} onChange={e => setForm({ ...form, contact_email: e.target.value })} autoComplete="email" spellCheck={false} className="h-10 rounded-xl bg-muted/50 border-none font-bold text-sm" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-[10px] font-bold uppercase text-muted-foreground">联系电话</Label>
              <Input value={form.contact_phone} onChange={e => setForm({ ...form, contact_phone: e.target.value })} type="tel" autoComplete="tel" className="h-10 rounded-xl bg-muted/50 border-none font-bold text-sm" />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label className="text-[10px] font-bold uppercase text-muted-foreground">业务方向</Label>
            <div className="flex items-center gap-2 flex-wrap">
              {currentDirections.length > 0 ? (
                currentDirections.map((dir: string) => (
                  <Badge key={dir} variant="outline" className="text-xs font-bold h-7 px-3 rounded-lg border-primary/30 bg-primary/5 text-primary">
                    {dir}
                  </Badge>
                ))
              ) : (
                <span className="text-sm text-muted-foreground">未设置方向</span>
              )}
              <Button
                variant="outline"
                size="sm"
                className="h-7 text-xs font-bold rounded-lg"
                onClick={async () => {
                  try {
                    const { data } = await api.get('/quizzes/knowledge-points/subjects/');
                    setDirectionSubjects(data.categories || []);
                    setDirectionSelected(currentDirections);
                    setDirectionError('');
                    setDirectionOpen(true);
                  } catch { console.error('Failed to load direction subjects'); }
                }}
              >
                <Pencil className="h-3 w-3 mr-1" />编辑方向
              </Button>
            </div>
            <p className="text-[11px] text-muted-foreground">业务方向决定机构的知识树结构，修改将删除旧知识点并导入新方向。</p>
          </div>

          <div className="space-y-1.5">
            <Label className="text-[10px] font-bold uppercase text-muted-foreground">机构简介</Label>
            <Input value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} className="h-10 rounded-xl bg-muted/50 border-none font-bold text-sm" placeholder="简短介绍你的机构…" />
          </div>

          <div className="space-y-1.5">
            <Label className="text-[10px] font-bold uppercase text-muted-foreground">机构 Logo</Label>
            <div className="flex items-center gap-4">
              {logoPreview && (
                <img src={logoPreview} alt="Logo" className="h-16 w-16 rounded-2xl object-cover border border-border" />
              )}
              <div className="relative flex-1">
                <Button variant="outline" className="w-full h-12 rounded-xl border-dashed border-2 font-bold text-xs">
                  <Upload className="w-4 h-4 mr-2 opacity-40" />
                  {logo ? logo.name : logoPreview ? '更换 Logo' : '上传 Logo'}
                </Button>
                <input type="file" accept="image/*" onChange={e => {
                  const f = e.target.files?.[0];
                  if (f) { setLogo(f); setLogoPreview(URL.createObjectURL(f)); }
                }} className="absolute inset-0 opacity-0 cursor-pointer" />
              </div>
            </div>
          </div>

          <Button onClick={handleSave} disabled={saving} className="w-full h-12 rounded-xl bg-black text-white font-bold text-xs uppercase tracking-widest">
            {saving ? <Spinner className="h-4 w-4 animate-spin mr-2" /> : <ShieldCheck className="h-4 w-4 mr-2" />}
            保存机构设置
          </Button>
        </Card>

        <DirectionEditDialog
          open={directionOpen}
          onClose={() => setDirectionOpen(false)}
          plan={plan}
          subjects={directionSubjects}
          selected={directionSelected}
          onSelectedChange={setDirectionSelected}
          onSave={async (names) => {
            setDirectionSaving(true);
            setDirectionError('');
            try {
              const { data } = await api.put('/users/institution/me/directions/', {
                subject_names: names,
              });
              setForm(f => ({ ...f, business_type: data.business_type }));
              toast.success(`已更新：删除 ${data.deleted} 个旧知识点，导入 ${data.imported_nodes} 个新知识点`);
              setDirectionOpen(false);
            } catch (err: any) {
              setDirectionError(err.response?.data?.error || '更新失败');
            } finally {
              setDirectionSaving(false);
            }
          }}
          saving={directionSaving}
          error={directionError}
        />
      </div>
    </div>
  );
}

/* ── Direction Edit Dialog ── */

const PLAN_DIRECTION_LIMITS: Record<string, number> = { starter: 1, growth: 3, enterprise: 999999, free: 0 };

function DirectionEditDialog({
  open, onClose, plan, subjects, selected, onSelectedChange, onSave, saving, error,
}: {
  open: boolean;
  onClose: () => void;
  plan: string;
  subjects: any[];
  selected: string[];
  onSelectedChange: (s: string[]) => void;
  onSave: (names: string[]) => void;
  saving: boolean;
  error: string;
}) {
  const maxDirs = PLAN_DIRECTION_LIMITS[plan] || 1;
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [pendingNames, setPendingNames] = useState<string[]>([]);

  const handleConfirmSave = () => {
    const names = selected.length > 0 ? selected : ['custom'];
    setPendingNames(names);
    setConfirmOpen(true);
  };

  const handleConfirmed = () => {
    setConfirmOpen(false);
    onSave(pendingNames);
  };

  return (
    <>
      <Dialog open={open} onOpenChange={onClose}>
        <DialogContent className="sm:max-w-[500px] rounded-2xl border-none shadow-2xl bg-card p-6">
          <DialogHeader className="space-y-1 mb-4">
            <DialogTitle className="text-lg font-black">编辑业务方向</DialogTitle>
            <DialogDescription className="font-medium text-muted-foreground text-sm">
              {plan === 'starter'
                ? 'Starter 方案可选择 1 个学科方向'
                : plan === 'growth'
                  ? 'Growth 方案最多选择 3 个学科方向'
                  : '选择你机构的业务方向'}
              <span className="block text-red-500 mt-1">修改方向将删除现有知识点并重新导入，请谨慎操作。</span>
            </DialogDescription>
          </DialogHeader>

          <div className="max-h-[380px] overflow-y-auto pr-1 -mx-1 px-1">
            <DirectionSelector
              categories={subjects}
              selected={selected}
              onSelectionChange={onSelectedChange}
              maxSelections={maxDirs}
            />
          </div>

          {error && <p className="text-xs text-red-500 mt-2">{error}</p>}

          <DialogFooter className="mt-4">
            <Button type="button" variant="outline" className="h-10 rounded-xl text-sm" onClick={onClose}>
              取消
            </Button>
            <Button type="button" variant="apple" className="h-10 rounded-xl text-sm"
              onClick={handleConfirmSave} disabled={saving}>
              {saving ? <Spinner className="h-4 w-4 animate-spin mr-1" /> : null}
              保存方向
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Confirm dialog */}
      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent className="sm:max-w-[380px] rounded-2xl border-none shadow-2xl bg-card p-6">
          <DialogHeader className="space-y-2 mb-4">
            <DialogTitle className="text-base font-black">确认修改业务方向</DialogTitle>
            <DialogDescription className="text-sm text-muted-foreground">
              此操作将<b>删除</b>机构现有的所有知识点，并重新导入所选方向的知识树。此操作不可撤销，确定继续？
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" className="h-10 rounded-xl text-sm" onClick={() => setConfirmOpen(false)}>
              取消
            </Button>
            <Button variant="destructive" className="h-10 rounded-xl text-sm" onClick={handleConfirmed}>
              确认修改
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
