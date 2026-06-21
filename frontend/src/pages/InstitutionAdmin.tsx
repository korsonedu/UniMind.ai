import { useCallback, useEffect, useState } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { useAuthStore } from '@/store/useAuthStore';
import { useInstitutionStore } from '@/store/useInstitutionStore';
import { useTranslation } from 'react-i18next';
import api from '@/lib/api';
import { Buildings, Plus, MagnifyingGlass, Spinner, Pencil, Power, Users, Calendar, ArrowLeft, Stack, Eye, Upload, ShieldCheck, Ticket, Key, Copy } from '@phosphor-icons/react';
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
  const { t } = useTranslation('common');
  const enterPreview = useInstitutionStore(s => s.enterPreview);
  const [institutions, setInstitutions] = useState<Institution[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const debouncedSearch = useDebouncedValue(search, 300);
  const [planFilter, setPlanFilter] = useState('');
  const [createOpen, setCreateOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<Institution | null>(null);
  const { confirm, Dialog: ConfirmDialog } = useConfirm();

  // Coupon management
  const [coupons, setCoupons] = useState<any[]>([]);
  const [couponsLoading, setCouponsLoading] = useState(false);
  const [couponCreateOpen, setCouponCreateOpen] = useState(false);

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

  const fetchCoupons = useCallback(async () => {
    setCouponsLoading(true);
    try {
      const { data } = await api.get('/payments/coupons/');
      setCoupons(Array.isArray(data) ? data : data.results || []);
    } catch { console.error('[CouponAdmin] fetch failed'); }
    setCouponsLoading(false);
  }, []);

  useEffect(() => { fetchCoupons(); }, [fetchCoupons]);

  const handleToggleCoupon = async (id: number, isActive: boolean) => {
    try {
      await api.put(`/payments/coupons/${id}/`, { is_active: !isActive });
      fetchCoupons();
    } catch { toast.error(t('updateFailed')); }
  };

  const handleDeleteCoupon = async (id: number, code: string) => {
    if (!(await confirm(t('deleteCouponConfirm', { code })))) return;
    try {
      await api.delete(`/payments/coupons/${id}/`);
      fetchCoupons();
    } catch { toast.error(t('deleteFailed')); }
  };

  const handleActivate = async (id: number) => {
    try {
      await api.post(`/users/institutions/${id}/activate/`);
      fetchInstitutions();
    } catch { toast.error(t('activateFailed')); }
  };
  const handleDeactivate = async (id: number) => {
    try {
      await api.post(`/users/institutions/${id}/deactivate/`);
      fetchInstitutions();
    } catch { toast.error(t('deactivateFailed')); }
  };
  const handleDelete = async (id: number, name: string) => {
    if (!(await confirm(t('deleteInstitutionConfirm', { name })))) return;
    try {
      await api.delete(`/users/institutions/${id}/`);
      fetchInstitutions();
    } catch { toast.error(t('deleteFailed')); }
  };

  // Institution owner → own settings
  if (user?.is_institution_owner) {
    return <InstitutionSelfSettings />;
  }

  // Teacher → no access
  if (user?.is_institution_admin) {
    return (
      <div className="min-h-screen bg-muted flex items-center justify-center text-muted-foreground text-sm">
        {t('institutionOwnerOnly')}
      </div>
    );
  }

  // Super admin → institution CRUD
  if (!user?.is_admin) {
    return (
      <div className="min-h-screen bg-muted flex items-center justify-center text-muted-foreground text-sm">
        {t('platformAdminOnly')}
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-muted">
      <header className="bg-card border-b border-border/60">
        <div className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Button variant="ghost" size="sm" className="h-8 text-xs" onClick={() => navigate('/')}>
              <ArrowLeft className="h-4 w-4 mr-1" /> {t('backToUnimind')}
            </Button>
            <span className="text-muted-foreground/40">|</span>
            <div className="flex items-center gap-2">
              <Stack className="h-4 w-4 text-primary" strokeWidth={2.5} />
              <span className="font-extrabold text-sm text-foreground tracking-tight">{t('institutionAdminPanel')}</span>
            </div>
          </div>
          <span className="text-xs text-muted-foreground">{user.nickname || user.username}</span>
        </div>
      </header>

      <div className="max-w-6xl mx-auto px-4 py-8 space-y-6">
        {/* Page header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-extrabold text-foreground tracking-tight">
              {t('institutionCount', { count: institutions.length })}
            </h1>
            <p className="text-sm text-muted-foreground/60 mt-1">{t('institutionManageDesc')}</p>
          </div>
          <Button variant="apple" size="sm" onClick={() => setCreateOpen(true)}>
            <Plus className="h-4 w-4" /> {t('createInstitution')}
          </Button>
        </div>

        {/* Filters */}
      <div className="flex gap-3">
        <div className="relative flex-1 max-w-xs">
          <MagnifyingGlass className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder={t('searchInstitution')}
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
              {p === '' ? t('all') : p.charAt(0).toUpperCase() + p.slice(1)}
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
          <p className="text-sm font-medium">{t('noInstitutions')}</p>
          <p className="text-xs mt-1">{t('noInstitutionsHint')}</p>
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
                        <Badge variant="outline" className="text-[10px] text-red-500 dark:text-red-400 border-red-200 dark:border-red-800/40">{t('institutionDisabled')}</Badge>
                      )}
                      {inst.is_active && !inst.is_plan_active && (
                        <Badge variant="outline" className="text-[10px] text-amber-500 dark:text-amber-400 border-amber-200 dark:border-amber-800/40">{t('institutionExpired')}</Badge>
                      )}
                    </div>
                    <div className="flex items-center gap-4 mt-1 text-xs text-muted-foreground">
                      <span className="flex items-center gap-1"><Users className="h-3 w-3" />{t('studentCount', { current: inst.student_count, max: inst.max_students })}</span>
                      <span className="flex items-center gap-1"><Calendar className="h-3 w-3" />{inst.plan_expires_at ? inst.plan_expires_at.slice(0, 10) : t('permanent')}</span>
                      <span>{inst.contact_name} · {inst.contact_email}</span>
                    </div>
                  </div>
                </div>

                {/* Right: actions */}
                <div className="flex items-center gap-1.5 shrink-0">
                  <Button variant="ghost" size="sm" className="h-8 text-xs text-primary"
                    onClick={() => enterPreview(inst.id)}>
                    <Eye className="h-3.5 w-3.5 mr-1" />{t('preview')}
                  </Button>
                  <Button variant="ghost" size="sm" className="h-8 text-xs" onClick={() => setEditTarget(inst)}>
                    <Pencil className="h-3.5 w-3.5 mr-1" />{t('edit')}
                  </Button>
                  {inst.is_active ? (
                    <Button variant="ghost" size="sm" className="h-8 text-xs text-amber-600" onClick={() => handleDeactivate(inst.id)}>
                      <Power className="h-3.5 w-3.5 mr-1" />{t('deactivateInstitution')}
                    </Button>
                  ) : (
                    <Button variant="ghost" size="sm" className="h-8 text-xs text-emerald-600" onClick={() => handleActivate(inst.id)}>
                      <Power className="h-3.5 w-3.5 mr-1" />{t('activateInstitution')}
                    </Button>
                  )}
                  <Button variant="ghost" size="sm" className="h-8 text-xs text-red-500" onClick={() => handleDelete(inst.id, inst.name)}>
                    {t('delete')}
                  </Button>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Coupon Management */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-extrabold text-foreground tracking-tight">{t('couponManagement')}</h2>
            <p className="text-sm text-muted-foreground/60 mt-1">{t('couponManagementDesc')}</p>
          </div>
          <Button variant="apple" size="sm" onClick={() => setCouponCreateOpen(true)}>
            <Plus className="h-4 w-4" /> {t('createCoupon')}
          </Button>
        </div>

        {couponsLoading ? (
          <div className="flex justify-center py-8">
            <Spinner className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : coupons.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <Ticket className="h-10 w-10 mx-auto mb-2 opacity-20" />
            <p className="text-sm font-medium">{t('noCoupons')}</p>
            <p className="text-xs mt-1">{t('noCouponsHint')}</p>
          </div>
        ) : (
          <div className="space-y-2">
            {coupons.map((c: any) => {
              const discountText = c.discount_type === 'percentage' ? t('couponPctDiscount', { value: c.discount_value }) : t('couponFixedDiscount', { value: (c.discount_value / 100).toFixed(0) });
              return (
              <Card key={c.id} variant="apple" className="p-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3 min-w-0">
                    <div className={cn('h-9 w-9 rounded-lg flex items-center justify-center shrink-0',
                      c.is_active ? 'bg-emerald-50 dark:bg-emerald-900/20' : 'bg-muted-foreground/10')}>
                      <Ticket className={cn('h-4 w-4',
                        c.is_active ? 'text-emerald-600' : 'text-muted-foreground')} />
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-extrabold text-foreground font-mono">{c.code}</span>
                        {c.is_active ? (
                          <Badge className="text-[10px] font-bold bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400">{t('couponActive')}</Badge>
                        ) : (
                          <Badge variant="outline" className="text-[10px] text-muted-foreground">{t('disabled')}</Badge>
                        )}
                      </div>
                      <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground">
                        <span>{discountText}</span>
                        {c.min_order_cents > 0 && <span>{t('couponMinOrder', { amount: (c.min_order_cents / 100).toFixed(0) })}</span>}
                        <span>{c.current_uses || 0}/{c.max_uses || '∞'} {t('couponTimes')}</span>
                        {c.expires_at && <span>{t('couponExpires', { date: c.expires_at.slice(0, 10) })}</span>}
                        {c.plan_restriction && (
                          <span className="text-[10px] bg-muted px-1.5 py-0.5 rounded">{c.plan_restriction}</span>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <Switch
                      checked={c.is_active}
                      onCheckedChange={() => handleToggleCoupon(c.id, c.is_active)}
                    />
                    <Button variant="ghost" size="sm" className="h-8 text-xs text-red-500" onClick={() => handleDeleteCoupon(c.id, c.code)}>
                      {t('delete')}
                    </Button>
                  </div>
                </div>
              </Card>
            )})}
          </div>
        )}
      </section>

      {/* Create Coupon Dialog */}
      <CreateCouponDialog
        open={couponCreateOpen}
        onClose={() => setCouponCreateOpen(false)}
        onCreated={() => { setCouponCreateOpen(false); fetchCoupons(); }}
      />

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
  const { t } = useTranslation('common');
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
      setError(err.response?.data?.detail || err.response?.data?.error || t('createInstitutionFailed'));
    }
    setSaving(false);
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-md">
        <DialogHeader><DialogTitle>{t('createInstitution')}</DialogTitle></DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3">
          <Input placeholder={t('institutionName') + ' *'} required
            value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} />
          <div className="grid grid-cols-2 gap-2">
            <Input placeholder={t('contactName') + ' *'} required
              value={form.contact_name} onChange={e => setForm({ ...form, contact_name: e.target.value })} />
            <Input placeholder={t('contactEmail') + ' *'} type="email" required
              value={form.contact_email} onChange={e => setForm({ ...form, contact_email: e.target.value })} />
          </div>
          <Input placeholder={t('contactPhone')}
            value={form.contact_phone} onChange={e => setForm({ ...form, contact_phone: e.target.value })} />
          <Input placeholder={t('businessTypePlaceholder')}
            value={form.business_type} onChange={e => setForm({ ...form, business_type: e.target.value })} />
          <p className="text-[11px] text-muted-foreground -mt-1">{t('businessTypeHint')}</p>
          <div className="grid grid-cols-2 gap-2">
            <select
              value={form.plan}
              onChange={e => setForm({ ...form, plan: e.target.value })}
              className="h-10 rounded-xl border border-border bg-background px-3 text-sm font-medium"
            >
              <option value="free">{t('planFree')}</option>
              <option value="starter">{t('planStarter')}</option>
              <option value="growth">{t('planGrowth')}</option>
              <option value="enterprise">{t('planEnterprise')}</option>
            </select>
            <Input type="date"
              value={form.plan_expires_at} onChange={e => setForm({ ...form, plan_expires_at: e.target.value })} />
          </div>
          {error && <p className="text-xs text-red-500">{error}</p>}
          <DialogFooter>
            <Button type="button" variant="outline" size="sm" onClick={onClose}>{t('cancel')}</Button>
            <Button type="submit" variant="apple" size="sm" disabled={saving}>
              {saving ? t('creating') : t('create')}
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
  const { t } = useTranslation('common');
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
      if (form.plan !== institution.plan) {
        await api.post(`/users/institutions/${institution.id}/change-plan/`, {
          plan: form.plan,
          plan_expires_at: payload.plan_expires_at || null,
        });
      }
      onUpdated();
    } catch (err: any) {
      setError(err.response?.data?.detail || t('saveInstitutionFailed'));
    }
    setSaving(false);
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-md">
        <DialogHeader><DialogTitle>{t('editInstitution')}</DialogTitle></DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3">
          <Input placeholder={t('institutionName')}
            value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} />
          <Input placeholder={t('contactName')}
            value={form.contact_name} onChange={e => setForm({ ...form, contact_name: e.target.value })} />
          <Input placeholder={t('contactEmail')} type="email"
            value={form.contact_email} onChange={e => setForm({ ...form, contact_email: e.target.value })} />
          <Input placeholder={t('contactPhone')}
            value={form.contact_phone} onChange={e => setForm({ ...form, contact_phone: e.target.value })} />
          <Input placeholder={t('businessTypePlaceholder')}
            value={form.business_type} onChange={e => setForm({ ...form, business_type: e.target.value })} />
          <p className="text-[11px] text-muted-foreground -mt-1">{t('businessTypeHint')}</p>
          <div className="grid grid-cols-2 gap-2">
            <select
              value={form.plan}
              onChange={e => setForm({ ...form, plan: e.target.value })}
              className="h-10 rounded-xl border border-border bg-background px-3 text-sm font-medium"
            >
              <option value="free">{t('planFree')}</option>
              <option value="starter">{t('planStarter')}</option>
              <option value="growth">{t('planGrowth')}</option>
              <option value="enterprise">{t('planEnterprise')}</option>
            </select>
            <Input type="date"
              value={form.plan_expires_at} onChange={e => setForm({ ...form, plan_expires_at: e.target.value })} />
          </div>
          <Input placeholder={t('institutionNotes')}
            value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} />
          {error && <p className="text-xs text-red-500">{error}</p>}
          <DialogFooter>
            <Button type="button" variant="outline" size="sm" onClick={onClose}>{t('cancel')}</Button>
            <Button type="submit" variant="apple" size="sm" disabled={saving}>
              {saving ? t('saving') : t('save')}
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
  const { t } = useTranslation('common');
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
  const [slug, setSlug] = useState('');
  const [ssoConfig, setSsoConfig] = useState({
    provider: 'feishu', enabled: false, client_id: '', client_secret: '',
    redirect_uri: '', domain_whitelist: '', auto_join: false, default_role: 'student',
  });
  const [ssoLoading, setSsoLoading] = useState(false);
  const [ssoSaving, setSsoSaving] = useState(false);
  const [apiKeysCount, setApiKeysCount] = useState(0);
  const [apiKeysLoading, setApiKeysLoading] = useState(false);

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
      setSlug(data.slug || '');
    }).catch((e) => {
      console.error('[InstitutionSelfSettings] fetch failed:', e);
      toast.error(t('loadInstitutionFailed'));
    });
  }, []);

  // Fetch SSO config & API keys (enterprise only)
  useEffect(() => {
    if (plan !== 'enterprise') return;
    setSsoLoading(true);
    api.get('/users/institution/me/sso-config/')
      .then(({ data }) => setSsoConfig({
        provider: data.provider || 'feishu',
        enabled: data.enabled || false,
        client_id: data.client_id || '',
        client_secret: data.client_secret || '',
        redirect_uri: data.redirect_uri || '',
        domain_whitelist: (data.domain_whitelist || []).join(', '),
        auto_join: data.auto_join || false,
        default_role: data.default_role || 'student',
      }))
      .catch((e) => { console.error('[InstitutionSelfSettings] SSO config fetch failed:', e); })
      .finally(() => setSsoLoading(false));
    setApiKeysLoading(true);
    api.get('/users/institution/me/api-keys/')
      .then(({ data }) => {
        const keys = Array.isArray(data) ? data : data.results || [];
        setApiKeysCount(keys.filter((k: any) => k.is_active).length);
      })
      .catch(() => setApiKeysCount(0))
      .finally(() => setApiKeysLoading(false));
  }, [plan]);

  const handleSsoSave = async () => {
    setSsoSaving(true);
    try {
      const payload = {
        ...ssoConfig,
        domain_whitelist: ssoConfig.domain_whitelist
          .split(',').map((s: string) => s.trim()).filter(Boolean),
      };
      await api.put('/users/institution/me/sso-config/', payload);
      toast.success(t('ssoSaved'));
    } catch (e: any) {
      toast.error(e.response?.data?.error || t('ssoSaveFailed'));
    } finally {
      setSsoSaving(false);
    }
  };

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
      toast.success(t('institutionUpdated'));
    } catch (e: any) {
      toast.error(e.response?.data?.error || t('saveSettingsFailed'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="min-h-screen bg-muted">
      <header className="bg-card border-b border-border/60">
        <div className="max-w-3xl mx-auto px-4 h-14 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Button variant="ghost" size="sm" className="h-8 text-xs" onClick={() => navigate('/')}>
              <ArrowLeft className="h-4 w-4 mr-1" /> {t('back')}
            </Button>
            <span className="text-muted-foreground/40">|</span>
            <div className="flex items-center gap-2">
              <Buildings className="h-4 w-4 text-primary" />
              <span className="font-extrabold text-sm text-foreground">{t('institutionSettingsTitle')}</span>
            </div>
          </div>
          <Badge className={cn('text-[10px] font-bold', planActive ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700')}>
            {planActive ? t('activePlan', { plan: planLabel }) : t('expiredPlan', { plan: planLabel })}
          </Badge>
        </div>
      </header>

      <div className="max-w-3xl mx-auto px-4 py-8 space-y-6">
        <Card className="p-6 rounded-2xl border-none shadow-sm bg-card">
          <div className="grid grid-cols-3 gap-4 text-center">
            <div>
              <p className="text-[10px] font-bold uppercase text-muted-foreground">{t('currentPlan')}</p>
              <p className="text-sm font-bold mt-1">{planLabel}</p>
            </div>
            <div>
              <p className="text-[10px] font-bold uppercase text-muted-foreground">{t('expiresAt')}</p>
              <p className="text-sm font-bold mt-1">{expiresAt ? new Date(expiresAt).toLocaleDateString(navigator.language || 'zh-CN') : t('permanent')}</p>
            </div>
            <div>
              <p className="text-[10px] font-bold uppercase text-muted-foreground">{t('studentCountLabel')}</p>
              <p className="text-sm font-bold mt-1">{studentCount} / {maxStudents}</p>
            </div>
          </div>
        </Card>

        <Card className="p-8 rounded-2xl border-none shadow-sm bg-card space-y-6">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label className="text-[10px] font-bold uppercase text-muted-foreground">{t('institutionName')}</Label>
              <Input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} autoComplete="organization" className="h-10 rounded-xl bg-muted/50 border-none font-bold text-sm" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-[10px] font-bold uppercase text-muted-foreground">{t('contactName')}</Label>
              <Input value={form.contact_name} onChange={e => setForm({ ...form, contact_name: e.target.value })} autoComplete="name" className="h-10 rounded-xl bg-muted/50 border-none font-bold text-sm" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-[10px] font-bold uppercase text-muted-foreground">{t('contactEmail')}</Label>
              <Input value={form.contact_email} onChange={e => setForm({ ...form, contact_email: e.target.value })} autoComplete="email" spellCheck={false} className="h-10 rounded-xl bg-muted/50 border-none font-bold text-sm" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-[10px] font-bold uppercase text-muted-foreground">{t('contactPhone')}</Label>
              <Input value={form.contact_phone} onChange={e => setForm({ ...form, contact_phone: e.target.value })} type="tel" autoComplete="tel" className="h-10 rounded-xl bg-muted/50 border-none font-bold text-sm" />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label className="text-[10px] font-bold uppercase text-muted-foreground">{t('businessType')}</Label>
            <div className="flex items-center gap-2 flex-wrap">
              {currentDirections.length > 0 ? (
                currentDirections.map((dir: string) => (
                  <Badge key={dir} variant="outline" className="text-xs font-bold h-7 px-3 rounded-lg border-primary/30 bg-primary/5 text-primary">
                    {dir}
                  </Badge>
                ))
              ) : (
                <span className="text-sm text-muted-foreground">{t('directionNotSet')}</span>
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
                <Pencil className="h-3 w-3 mr-1" />{t('editDirection')}
              </Button>
            </div>
            <p className="text-[11px] text-muted-foreground">{t('directionWarning')}</p>
          </div>

          <div className="space-y-1.5">
            <Label className="text-[10px] font-bold uppercase text-muted-foreground">{t('institutionNotes')}</Label>
            <Input value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} className="h-10 rounded-xl bg-muted/50 border-none font-bold text-sm" placeholder={t('institutionNotesPlaceholder')} />
          </div>

          <div className="space-y-1.5">
            <Label className="text-[10px] font-bold uppercase text-muted-foreground">{t('institutionLogo')}</Label>
            <div className="flex items-center gap-4">
              {logoPreview && (
                <img src={logoPreview} alt="Logo" className="h-16 w-16 rounded-2xl object-cover border border-border" />
              )}
              <div className="relative flex-1">
                <Button variant="outline" className="w-full h-12 rounded-xl border-dashed border-2 font-bold text-xs">
                  <Upload className="w-4 h-4 mr-2 opacity-40" />
                  {logo ? logo.name : logoPreview ? t('changeLogo') : t('uploadLogo')}
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
            {t('saveInstitutionSettings')}
          </Button>
        </Card>

        {/* SSO config (enterprise) */}
        {plan === 'enterprise' && (
          <Card className="p-8 rounded-2xl border-none shadow-sm bg-card space-y-6">
            <div className="flex items-center gap-2">
              <ShieldCheck className="h-5 w-5 text-primary" />
              <h2 className="text-base font-extrabold text-foreground">{t('ssoTitle')}</h2>
            </div>

            {ssoLoading ? (
              <div className="flex justify-center py-8">
                <Spinner className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <Label className="text-[10px] font-bold uppercase text-muted-foreground">{t('ssoProvider')}</Label>
                  <select
                    value={ssoConfig.provider}
                    onChange={e => setSsoConfig({ ...ssoConfig, provider: e.target.value })}
                    className="h-10 rounded-xl border border-border bg-muted/50 px-3 text-sm font-medium w-full"
                  >
                    <option value="feishu">{'feishu'}</option>
                    <option value="dingtalk">{'dingtalk'}</option>
                    <option value="wecom">{'wecom'}</option>
                    <option value="oidc">{'oidc'}</option>
                  </select>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-[10px] font-bold uppercase text-muted-foreground">{t('ssoEnabled')}</Label>
                  <Switch
                    checked={ssoConfig.enabled}
                    onCheckedChange={v => setSsoConfig({ ...ssoConfig, enabled: v })}
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <Label className="text-[10px] font-bold uppercase text-muted-foreground">{t('ssoClientId')}</Label>
                  <Input
                    value={ssoConfig.client_id}
                    onChange={e => setSsoConfig({ ...ssoConfig, client_id: e.target.value })}
                    className="h-10 rounded-xl bg-muted/50 border-none text-sm"
                    spellCheck={false}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-[10px] font-bold uppercase text-muted-foreground">{t('ssoClientSecret')}</Label>
                  <Input
                    type="password"
                    value={ssoConfig.client_secret}
                    onChange={e => setSsoConfig({ ...ssoConfig, client_secret: e.target.value })}
                    className="h-10 rounded-xl bg-muted/50 border-none text-sm"
                    spellCheck={false}
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <Label className="text-[10px] font-bold uppercase text-muted-foreground">{t('ssoRedirectUri')}</Label>
                <Input
                  value={ssoConfig.redirect_uri}
                  onChange={e => setSsoConfig({ ...ssoConfig, redirect_uri: e.target.value })}
                  className="h-10 rounded-xl bg-muted/50 border-none text-sm"
                  spellCheck={false}
                />
              </div>

              <div className="space-y-1.5">
                <Label className="text-[10px] font-bold uppercase text-muted-foreground">{t('ssoDomainWhitelist')}</Label>
                <Input
                  value={ssoConfig.domain_whitelist}
                  onChange={e => setSsoConfig({ ...ssoConfig, domain_whitelist: e.target.value })}
                  placeholder="example.com, corp.example.com"
                  className="h-10 rounded-xl bg-muted/50 border-none text-sm"
                  spellCheck={false}
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <Label className="text-[10px] font-bold uppercase text-muted-foreground">{t('ssoAutoJoin')}</Label>
                  <Switch
                    checked={ssoConfig.auto_join}
                    onCheckedChange={v => setSsoConfig({ ...ssoConfig, auto_join: v })}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-[10px] font-bold uppercase text-muted-foreground">{t('ssoDefaultRole')}</Label>
                  <select
                    value={ssoConfig.default_role}
                    onChange={e => setSsoConfig({ ...ssoConfig, default_role: e.target.value })}
                    className="h-10 rounded-xl border border-border bg-muted/50 px-3 text-sm font-medium w-full"
                  >
                    <option value="student">{t('ssoRoleStudent')}</option>
                    <option value="teacher">{t('ssoRoleTeacher')}</option>
                  </select>
                </div>
              </div>

              {slug && (
                <div className="flex items-center gap-2 p-3 rounded-xl bg-muted/50 text-xs">
                  <span className="text-muted-foreground shrink-0">{t('ssoLoginLink')}</span>
                  <code className="text-primary font-mono truncate">https://unimind-ai.com/api/users/sso/authorize/?institution_slug={slug}</code>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 text-xs shrink-0"
                    onClick={() => {
                      navigator.clipboard.writeText(`https://unimind-ai.com/api/users/sso/authorize/?institution_slug=${slug}`);
                      toast.success(t('copiedLoginLink'));
                    }}
                  >
                    <Copy className="h-3 w-3 mr-1" />{t('copyText')}
                  </Button>
                </div>
              )}

              <Button
                onClick={handleSsoSave}
                disabled={ssoSaving}
                className="w-full h-12 rounded-xl bg-black text-white font-bold text-xs uppercase tracking-widest"
              >
                {ssoSaving ? <Spinner className="h-4 w-4 animate-spin mr-2" /> : <ShieldCheck className="h-4 w-4 mr-2" />}
                {t('saveSsoConfig')}
              </Button>
            </div>
            )}
          </Card>
        )}

        {/* API platform summary (enterprise) */}
        {plan === 'enterprise' && (
          <Card className="p-8 rounded-2xl border-none shadow-sm bg-card space-y-4">
            <div className="flex items-center gap-2">
              <Key className="h-5 w-5 text-primary" />
              <h2 className="text-base font-extrabold text-foreground">{t('apiPlatformTitle')}</h2>
            </div>

            {apiKeysLoading ? (
              <div className="flex justify-center py-4">
                <Spinner className="h-5 w-5 animate-spin text-muted-foreground" />
              </div>
            ) : (
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="h-10 w-10 rounded-xl bg-primary/8 flex items-center justify-center">
                    <Key className="h-5 w-5 text-primary" />
                  </div>
                  <div>
                    <p className="text-sm font-bold text-foreground">{t('apiKeyCount', { count: apiKeysCount })}</p>
                    <p className="text-xs text-muted-foreground">{t('apiManagement')}</p>
                  </div>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  className="h-9 rounded-xl text-xs font-medium"
                  onClick={() => navigate('/api-platform')}
                >
                  {t('goToApiPlatform')}
                </Button>
              </div>
            )}
          </Card>
        )}

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
              toast.success(t('directionsUpdated', { deleted: data.deleted, imported: data.imported_nodes }));
              setDirectionOpen(false);
            } catch (err: any) {
              setDirectionError(err.response?.data?.error || t('directionsUpdateFailed'));
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
  const { t } = useTranslation('common');
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

  const planHint = plan === 'starter' ? t('directionPlanStarter') : plan === 'growth' ? t('directionPlanGrowth') : t('directionPlanDefault');

  return (
    <>
      <Dialog open={open} onOpenChange={onClose}>
        <DialogContent className="sm:max-w-[500px] rounded-2xl border-none shadow-2xl bg-card p-6">
          <DialogHeader className="space-y-1 mb-4">
            <DialogTitle className="text-lg font-black">{t('editDirectionsTitle')}</DialogTitle>
            <DialogDescription className="font-medium text-muted-foreground text-sm">
              {planHint}
              <span className="block text-red-500 mt-1">{t('directionDangerWarning')}</span>
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
              {t('cancel')}
            </Button>
            <Button type="button" variant="apple" className="h-10 rounded-xl text-sm"
              onClick={handleConfirmSave} disabled={saving}>
              {saving ? <Spinner className="h-4 w-4 animate-spin mr-1" /> : null}
              {t('saveDirection')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Confirm dialog */}
      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent className="sm:max-w-[380px] rounded-2xl border-none shadow-2xl bg-card p-6">
          <DialogHeader className="space-y-2 mb-4">
            <DialogTitle className="text-base font-black">{t('confirmDirectionChange')}</DialogTitle>
            <DialogDescription className="text-sm text-muted-foreground">
              <span dangerouslySetInnerHTML={{ __html: t('confirmDirectionDesc') }} />
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" className="h-10 rounded-xl text-sm" onClick={() => setConfirmOpen(false)}>
              {t('cancel')}
            </Button>
            <Button variant="destructive" className="h-10 rounded-xl text-sm" onClick={handleConfirmed}>
              {t('confirmChange')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

/* ── Create Coupon Dialog ── */

function CreateCouponDialog({
  open, onClose, onCreated,
}: {
  open: boolean; onClose: () => void; onCreated: () => void;
}) {
  const { t } = useTranslation('common');
  const [form, setForm] = useState({
    code: '',
    discount_type: 'fixed',
    discount_value: '',
    min_order_cents: '',
    max_uses: '0',
    max_uses_per_user: '1',
    expires_at: '',
    plan_restriction: '',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true); setError('');
    try {
      const payload: any = {
        code: form.code.trim(),
        discount_type: form.discount_type,
        discount_value: parseInt(form.discount_value, 10),
        min_order_cents: parseInt(form.min_order_cents, 10) || 0,
        max_uses: parseInt(form.max_uses, 10) || 0,
        max_uses_per_user: parseInt(form.max_uses_per_user, 10) || 1,
      };
      if (form.expires_at) payload.expires_at = form.expires_at;
      if (form.plan_restriction.trim()) {
        payload.plan_restriction = form.plan_restriction
          .split(',')
          .map((s: string) => s.trim())
          .filter(Boolean)
          .join(',');
      }
      await api.post('/payments/coupons/', payload);
      onCreated();
    } catch (err: any) {
      setError(err.response?.data?.error || Object.values(err.response?.data || {}).flat().join('; ') || t('couponCreateFailed'));
    }
    setSaving(false);
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{t('createCouponTitle')}</DialogTitle>
          <DialogDescription>{t('createCouponDesc')}</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3">
          <Input placeholder={t('couponCodeLabel')} required
            value={form.code} onChange={e => setForm({ ...form, code: e.target.value })} />

          <div className="grid grid-cols-2 gap-2">
            <Select
              value={form.discount_type}
              onValueChange={v => setForm({ ...form, discount_type: v })}
            >
              <SelectTrigger className="h-10 rounded-xl">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="percentage">{t('couponPctOption')}</SelectItem>
                <SelectItem value="fixed">{t('couponFixedOption')}</SelectItem>
              </SelectContent>
            </Select>
            <Input
              placeholder={form.discount_type === 'percentage' ? t('couponPctPlaceholder') : t('couponFixedPlaceholder')}
              type="number" required
              value={form.discount_value}
              onChange={e => setForm({ ...form, discount_value: e.target.value })}
            />
          </div>

          <div className="grid grid-cols-2 gap-2">
            <Input
              placeholder={t('couponMinOrderPlaceholder')} type="number"
              value={form.min_order_cents}
              onChange={e => setForm({ ...form, min_order_cents: e.target.value })}
            />
            <Input
              placeholder={t('couponMaxUsesPlaceholder')} type="number"
              value={form.max_uses}
              onChange={e => setForm({ ...form, max_uses: e.target.value })}
            />
          </div>

          <div className="grid grid-cols-2 gap-2">
            <Input
              placeholder={t('couponMaxPerUserPlaceholder')} type="number"
              value={form.max_uses_per_user}
              onChange={e => setForm({ ...form, max_uses_per_user: e.target.value })}
            />
            <Input
              type="date"
              value={form.expires_at}
              onChange={e => setForm({ ...form, expires_at: e.target.value })}
            />
          </div>

          <Input
            placeholder={t('couponPlanRestrictPlaceholder')}
            value={form.plan_restriction}
            onChange={e => setForm({ ...form, plan_restriction: e.target.value })}
          />

          {error && <p className="text-xs text-red-500">{error}</p>}
          <DialogFooter>
            <Button type="button" variant="outline" size="sm" onClick={onClose}>{t('cancel')}</Button>
            <Button type="submit" variant="apple" size="sm" disabled={saving}>
              {saving ? t('creating') : t('create')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
