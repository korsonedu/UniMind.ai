import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { useAuthStore } from '@/store/useAuthStore';
import api from '@/lib/api';
import {
  Building2, Plus, Search, Loader2, Pencil, Power, PowerOff,
  Users, Calendar,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { formatApiErrorToast } from '@/lib/apiError';

const apiErr = (err: any, fallback: string): string => {
  const d = err?.response?.data;
  return d?.error || d?.details?.detail || d?.detail || fallback;
};

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
}

const PLAN_COLORS: Record<string, string> = {
  free: 'bg-[#AEAEB2]', solo: 'bg-[#0071E3]', plus: 'bg-[#34C759]', pro: 'bg-[#FF9500]',
};

export default function Institutions() {
  const { user } = useAuthStore();
  const [institutions, setInstitutions] = useState<Institution[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [planFilter, setPlanFilter] = useState('');
  const [createOpen, setCreateOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<Institution | null>(null);

  const fetchInstitutions = async () => {
    try {
      const params: Record<string, string> = {};
      if (search) params.search = search;
      if (planFilter) params.plan = planFilter;
      const { data } = await api.get('/users/admin/institutions/', { params });
      setInstitutions(data);
    } catch (err: any) {
      console.warn('[Institutions] fetch failed:', apiErr(err, 'unknown'));
    }
    setLoading(false);
  };

  useEffect(() => { fetchInstitutions(); }, [search, planFilter]);

  const handleActivate = async (id: number) => {
    await api.post(`/users/admin/institutions/${id}/activate/`);
    fetchInstitutions();
  };
  const handleDeactivate = async (id: number) => {
    await api.post(`/users/admin/institutions/${id}/deactivate/`);
    fetchInstitutions();
  };
  const handleDelete = async (id: number, name: string) => {
    if (!confirm(`确认删除机构「${name}」？该操作不可撤销。`)) return;
    await api.delete(`/users/admin/institutions/${id}/`);
    fetchInstitutions();
  };

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-extrabold text-[#1D1D1F] tracking-tight">
            {institutions.length} 个机构
          </h1>
          <p className="text-sm text-[#8E8E93] mt-1">管理购买方、版本和服务状态</p>
        </div>
        <Button className="h-9 rounded-xl text-xs font-extrabold bg-[#0071E3] hover:bg-[#0071E3]/90 shadow-sm" onClick={() => setCreateOpen(true)}>
          <Plus className="h-4 w-4" /> 新建机构
        </Button>
      </div>

      {/* Filters */}
      <div className="flex gap-3">
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[#AEAEB2]" />
          <Input
            placeholder="搜索机构名称..."
            className="pl-9"
            value={search} onChange={e => setSearch(e.target.value)}
          />
        </div>
        <div className="flex gap-1.5">
          {['', 'free', 'solo', 'plus', 'pro'].map(p => (
            <button
              key={p}
              onClick={() => setPlanFilter(p)}
              className={cn(
                'px-3 py-1.5 rounded-lg text-xs font-bold transition-colors',
                planFilter === p
                  ? 'bg-[#0071E3] text-white'
                  : 'bg-[#F5F5F7] text-[#8E8E93] hover:bg-[#E8E8ED]'
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
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : institutions.length === 0 ? (
        <div className="text-center py-16 text-[#AEAEB2]">
          <Building2 className="h-12 w-12 mx-auto mb-3 opacity-20" />
          <p className="text-sm font-medium">暂无机构</p>
          <p className="text-xs mt-1">点击右上角「新建机构」创建第一个购买方</p>
        </div>
      ) : (
        <div className="space-y-2">
          {institutions.map(inst => (
            <div key={inst.id} className="bg-white border border-[#E5E5EA]/60 rounded-2xl p-5">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-4 min-w-0">
                  <div className={cn('h-10 w-10 rounded-xl flex items-center justify-center shrink-0',
                    inst.is_active ? 'bg-[#0071E3]/8' : 'bg-[#AEAEB2]/10')}>
                    <Building2 className={cn('h-5 w-5',
                      inst.is_active ? 'text-[#0071E3]' : 'text-[#AEAEB2]')} />
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <h3 className="text-sm font-extrabold text-[#1D1D1F] truncate">{inst.name}</h3>
                      <Badge className={cn('text-[10px] font-bold text-white', PLAN_COLORS[inst.plan] || 'bg-[#AEAEB2]')}>
                        {inst.plan_label}
                      </Badge>
                      {!inst.is_active && (
                        <Badge variant="outline" className="text-[10px] text-red-500 border-red-200">已停用</Badge>
                      )}
                      {inst.is_active && !inst.is_plan_active && (
                        <Badge variant="outline" className="text-[10px] text-amber-500 border-amber-200">已到期</Badge>
                      )}
                    </div>
                    <div className="flex items-center gap-4 mt-1 text-xs text-[#AEAEB2]">
                      <span className="flex items-center gap-1"><Users className="h-3 w-3" />{inst.student_count}/{inst.max_students} 学员</span>
                      <span className="flex items-center gap-1"><Calendar className="h-3 w-3" />{inst.plan_expires_at ? inst.plan_expires_at.slice(0, 10) : '永久有效'}</span>
                      <span>{inst.contact_name} · {inst.contact_email}</span>
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-1.5 shrink-0">
                  <Button variant="ghost" size="sm" className="h-8 text-xs" onClick={() => setEditTarget(inst)}>
                    <Pencil className="h-3.5 w-3.5 mr-1" />编辑
                  </Button>
                  {inst.is_active ? (
                    <Button variant="ghost" size="sm" className="h-8 text-xs text-amber-600" onClick={() => handleDeactivate(inst.id)}>
                      <PowerOff className="h-3.5 w-3.5 mr-1" />停用
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
            </div>
          ))}
        </div>
      )}

      {/* Create Dialog */}
      <CreateDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={() => { setCreateOpen(false); fetchInstitutions(); }}
      />

      {/* Edit Dialog */}
      {editTarget && (
        <EditDialog
          institution={editTarget}
          open={!!editTarget}
          onClose={() => setEditTarget(null)}
          onUpdated={() => { setEditTarget(null); fetchInstitutions(); }}
        />
      )}
    </div>
  );
}

/* ── Create Dialog ── */

function CreateDialog({
  open, onClose, onCreated,
}: {
  open: boolean; onClose: () => void; onCreated: () => void;
}) {
  const [form, setForm] = useState({
    name: '', slug: '', contact_name: '', contact_email: '', contact_phone: '',
    plan: 'free', plan_expires_at: '', notes: '',
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
      await api.post('/users/admin/institutions/', payload);
      onCreated();
    } catch (err: any) {
      setError(apiErr(err, '创建失败'));
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
          <div className="grid grid-cols-2 gap-2">
            <select
              value={form.plan}
              onChange={e => setForm({ ...form, plan: e.target.value })}
              className="h-10 rounded-xl border border-border bg-background px-3 text-sm font-medium"
            >
              <option value="free">Free</option>
              <option value="solo">Solo</option>
              <option value="plus">Plus</option>
              <option value="pro">Pro</option>
            </select>
            <Input type="date"
              value={form.plan_expires_at} onChange={e => setForm({ ...form, plan_expires_at: e.target.value })} />
          </div>
          {error && <p className="text-xs text-red-500">{error}</p>}
          <DialogFooter>
            <Button type="button" variant="outline" size="sm" onClick={onClose}>取消</Button>
            <Button type="submit" size="sm" disabled={saving} className="bg-[#0071E3] text-white hover:bg-[#0071E3]/90 font-bold">
              {saving ? '创建中...' : '创建'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/* ── Edit Dialog ── */

function EditDialog({
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
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true); setError('');
    try {
      const payload: any = { ...form };
      if (!payload.plan_expires_at) delete payload.plan_expires_at;
      await api.put(`/users/admin/institutions/${institution.id}/`, payload);
      if (form.plan !== institution.plan) {
        await api.post(`/users/admin/institutions/${institution.id}/change-plan/`, {
          plan: form.plan,
          plan_expires_at: payload.plan_expires_at || null,
        });
      }
      onUpdated();
    } catch (err: any) {
      setError(apiErr(err, '保存失败'));
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
          <div className="grid grid-cols-2 gap-2">
            <select
              value={form.plan}
              onChange={e => setForm({ ...form, plan: e.target.value })}
              className="h-10 rounded-xl border border-border bg-background px-3 text-sm font-medium"
            >
              <option value="free">Free</option>
              <option value="solo">Solo</option>
              <option value="plus">Plus</option>
              <option value="pro">Pro</option>
            </select>
            <Input type="date"
              value={form.plan_expires_at} onChange={e => setForm({ ...form, plan_expires_at: e.target.value })} />
          </div>
          <Input placeholder="备注"
            value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} />
          {error && <p className="text-xs text-red-500">{error}</p>}
          <DialogFooter>
            <Button type="button" variant="outline" size="sm" onClick={onClose}>取消</Button>
            <Button type="submit" size="sm" disabled={saving} className="bg-[#0071E3] text-white hover:bg-[#0071E3]/90 font-bold">
              {saving ? '保存中...' : '保存'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
