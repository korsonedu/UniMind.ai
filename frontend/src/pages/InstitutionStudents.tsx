import { useEffect, useState } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { useInstitutionStore } from '@/store/useInstitutionStore';
import { useAuthStore } from '@/store/useAuthStore';
import api from '@/lib/api';
import { toast } from 'sonner';
import {
  Users, UserPlus, Upload, Search, Loader2, Trash2, GraduationCap,
  Download, RefreshCw, TrendingUp, Hash, Clock, Save, Plus, Key,
  Shield,
} from 'lucide-react';
import { cn } from '@/lib/utils';

/* ── Page router: pick view based on role ── */

export default function InstitutionStudents() {
  const { isPlatformAdmin, institution } = useInstitutionStore();
  const [showGlobal, setShowGlobal] = useState(false);

  // 平台管理员 + 有机构 → 默认显示机构花名册，可切换到全局
  if (isPlatformAdmin && institution) {
    return (
      <div>
        <div className="flex items-center gap-3 mb-6">
          <h1 className="text-2xl font-extrabold text-foreground tracking-tight">学员管理</h1>
          <div className="flex items-center gap-1.5 ml-auto">
            <button onClick={() => setShowGlobal(false)}
              className={cn('text-xs font-bold px-3 py-1.5 rounded-lg transition-colors',
                !showGlobal ? 'bg-primary text-white' : 'bg-muted text-muted-foreground/60')}>
              本机构
            </button>
            <button onClick={() => setShowGlobal(true)}
              className={cn('text-xs font-bold px-3 py-1.5 rounded-lg transition-colors',
                showGlobal ? 'bg-primary text-white' : 'bg-muted text-muted-foreground/60')}>
              全局用户
            </button>
          </div>
        </div>
        {showGlobal ? <PlatformUserManagement /> : <InstitutionRosterManagement institution={institution} />}
      </div>
    );
  }

  // 仅平台管理员（无机构）→ 全局用户管理
  if (isPlatformAdmin) return <PlatformUserManagement />;

  // 仅机构管理员 → 本机构学员管理
  if (institution) return <InstitutionRosterManagement institution={institution} />;

  return (
    <div className="flex items-center justify-center h-64 text-sm text-muted-foreground">
      你没有机构管理权限
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   Platform Admin: Global User Management
   ═══════════════════════════════════════════════════════════ */

type UserTag = { id: number; name: string; color: string };
type PermGroup = { id: number; key: string; name: string; permissions: string[] };
type PlatformUser = {
  id: number; username: string; nickname: string; email?: string;
  role: 'student' | 'admin'; is_member: boolean; is_staff: boolean; is_superuser: boolean;
  tag_ids: number[]; tag_names: string[];
  permission_group_ids: number[]; permission_group_keys: string[];
  extra_permissions: string[]; blocked_permissions: string[]; profile_note: string;
  elo_score?: number;
};

const ALL_CAPS = [
  'learning.access', 'member.access', 'admin.panel', 'content.manage', 'users.manage', 'system.manage',
  'ai.generate', 'quiz.manual', 'quiz.exam', 'memorix.review', 'wrong.review',
  'basic.stats', 'full.report', 'class.compare', 'data.export',
  'course.video', 'video.outline', 'knowledge.graph', 'faq.system',
  'multi.teacher', 'study.room', 'ai.assistant', 'pdf.mock', 'brand.custom', 'api.access',
];

function PlatformUserManagement() {
  const [users, setUsers] = useState<PlatformUser[]>([]);
  const [tags, setTags] = useState<UserTag[]>([]);
  const [groups, setGroups] = useState<PermGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<PlatformUser | null>(null);

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [uRes, tRes, gRes] = await Promise.all([
        api.get('/users/admin/superusers/users/', { params: { page_size: 200, search } }),
        api.get('/users/admin/user-tags/'),
        api.get('/users/admin/permission-groups/'),
      ]);
      setUsers(uRes.data.results || uRes.data || []);
      setTags((tRes.data || []).filter((t: any) => t.is_active));
      setGroups((gRes.data || []).filter((g: any) => g.is_active));
    } catch { /* */ }
    setLoading(false);
  };

  useEffect(() => { fetchAll(); }, [search]);

  return (
    <div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        {[
          { label: '用户总数', value: users.length, icon: Users, color: 'text-primary', bg: 'bg-primary/6' },
          { label: '管理员', value: users.filter(u => u.role === 'admin').length, icon: Shield, color: 'text-[#FF9500]', bg: 'bg-[#FF9500]/6' },
          { label: '超级用户', value: users.filter(u => u.is_superuser).length, icon: Shield, color: 'text-purple-500', bg: 'bg-purple-50' },
          { label: '学员', value: users.filter(u => u.role === 'student').length, icon: GraduationCap, color: 'text-[#34C759]', bg: 'bg-[#34C759]/6' },
        ].map(s => (
          <Card key={s.label} variant="apple" className="p-4 space-y-1">
            <div className={cn('h-8 w-8 rounded-lg flex items-center justify-center', s.bg)}>
              <s.icon className={cn('h-4 w-4', s.color)} />
            </div>
            <p className="text-2xl font-extrabold text-foreground tracking-tightest">{s.value}</p>
            <p className="text-[11px] font-bold text-muted-foreground">{s.label}</p>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* User List */}
        <div className="lg:col-span-1 space-y-3">
          <div className="flex gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input placeholder="搜索用户..." className="pl-9" value={search} onChange={e => setSearch(e.target.value)} />
            </div>
            <Button variant="ghost" size="icon" onClick={fetchAll}><RefreshCw className="h-4 w-4" /></Button>
          </div>

          {loading ? (
            <div className="flex justify-center py-12"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
          ) : (
            <ScrollArea className="h-[520px]">
              <div className="space-y-1 pr-2">
                {users.map(u => (
                  <button key={u.id} onClick={() => setSelected(u)}
                    className={cn('w-full text-left p-3 rounded-xl border transition-colors',
                      selected?.id === u.id ? 'border-[#0071E3] bg-primary/4' : 'border-transparent hover:bg-muted')}>
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-bold text-foreground">{u.nickname || u.username}</span>
                      <span className={cn('text-[10px] font-bold px-1.5 py-0.5 rounded',
                        u.is_superuser ? 'bg-purple-100 text-purple-700' :
                        u.role === 'admin' ? 'bg-blue-100 text-blue-700' : 'bg-muted text-muted-foreground/60')}>
                        {u.is_superuser ? '超管' : u.role === 'admin' ? '管理员' : '学员'}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5">{u.email || u.username}</p>
                    {u.tag_names.length > 0 && (
                      <div className="flex gap-1 mt-1 flex-wrap">
                        {u.tag_names.slice(0, 4).map(t => (
                          <span key={t} className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground/60">{t}</span>
                        ))}
                      </div>
                    )}
                  </button>
                ))}
              </div>
            </ScrollArea>
          )}
        </div>

        {/* Permission Editor */}
        <div className="lg:col-span-2">
          {selected ? (
            <PlatformPermissionEditor key={selected.id}
              user={selected} tags={tags} groups={groups}
              onSaved={fetchAll} onCancel={() => setSelected(null)}
              onTagsChanged={fetchAll} onGroupsChanged={fetchAll} />
          ) : (
            <div className="flex items-center justify-center h-full text-sm text-muted-foreground pt-20">
              选择左侧用户以编辑权限
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function PlatformPermissionEditor({
  user, tags, groups, onSaved, onCancel, onTagsChanged, onGroupsChanged,
}: {
  user: PlatformUser; tags: UserTag[]; groups: PermGroup[];
  onSaved: () => void; onCancel: () => void;
  onTagsChanged: () => void; onGroupsChanged: () => void;
}) {
  const [e, setE] = useState({
    role: user.role, is_member: user.is_member, is_staff: user.is_staff, is_superuser: user.is_superuser,
    tag_ids: [...user.tag_ids], group_ids: [...user.permission_group_ids],
    extra: [...(user.extra_permissions || [])], blocked: [...(user.blocked_permissions || [])],
    note: user.profile_note || '',
  });
  const [saving, setSaving] = useState(false);
  const [newTag, setNewTag] = useState('');
  const [newGroupKey, setNewGroupKey] = useState('');
  const [newGroupName, setNewGroupName] = useState('');

  const toggle = (setter: any, field: string, val: any) => setter((prev: any) => ({
    ...prev, [field]: prev[field].includes(val) ? prev[field].filter((v: any) => v !== val) : [...prev[field], val],
  }));

  const addTag = async () => {
    if (!newTag.trim()) return;
    await api.post('/users/admin/user-tags/', { name: newTag.trim() });
    setNewTag(''); onTagsChanged(); toast.success('标签已添加');
  };
  const addGroup = async () => {
    if (!newGroupKey.trim() || !newGroupName.trim()) return;
    await api.post('/users/admin/permission-groups/', { key: newGroupKey.trim(), name: newGroupName.trim() });
    setNewGroupKey(''); setNewGroupName(''); onGroupsChanged(); toast.success('权限组已添加');
  };

  const save = async () => {
    setSaving(true);
    await api.patch(`/users/admin/superusers/users/${user.id}/`, {
      role: e.role, is_member: e.is_member, is_staff: e.is_staff, is_superuser: e.is_superuser,
      tag_ids: e.tag_ids, permission_group_ids: e.group_ids,
      extra_permissions: e.extra, blocked_permissions: e.blocked, note: e.note,
    });
    toast.success('已保存'); onSaved();
    setSaving(false);
  };

  return (
    <Card variant="apple" className="p-5 space-y-4 h-[520px] flex flex-col">
      <div className="flex items-center justify-between">
        <h3 className="font-extrabold text-sm">{user.nickname || user.username}</h3>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={onCancel}>取消</Button>
          <Button variant="apple" size="sm" onClick={save} disabled={saving}><Save className="h-3.5 w-3.5 mr-1" />保存</Button>
        </div>
      </div>

      <ScrollArea className="flex-1">
        <div className="space-y-4 pr-2">
          {/* Role + Checkboxes */}
          <div className="flex items-center gap-4 flex-wrap">
            <select value={e.role} onChange={ev => setE({ ...e, role: ev.target.value as any })}
              className="h-9 rounded-lg border px-3 text-sm font-medium">
              <option value="student">student</option><option value="admin">admin</option>
            </select>
            {(['is_member', 'is_staff', 'is_superuser'] as const).map(f => (
              <label key={f} className="flex items-center gap-1.5 text-sm font-medium cursor-pointer">
                <input type="checkbox" checked={!!e[f]} onChange={ev => setE({ ...e, [f]: ev.target.checked })} />
                {{ is_member: '会员', is_staff: '员工', is_superuser: '超管' }[f]}
              </label>
            ))}
          </div>

          {/* Tags */}
          <Section label="标签">
            <div className="flex flex-wrap gap-1.5">
              {tags.map(t => (
                <button key={t.id} onClick={() => toggle(setE, 'tag_ids', t.id)}
                  className={cn('text-[11px] font-bold px-2.5 py-1 rounded-lg border', e.tag_ids.includes(t.id) ? 'bg-amber-100 border-amber-300 text-amber-800' : 'bg-white border-border text-muted-foreground/60')}>{t.name}</button>
              ))}
            </div>
            <div className="flex gap-1.5 mt-1.5">
              <Input placeholder="新标签名" className="h-7 text-xs" value={newTag}
                onChange={ev => setNewTag(ev.target.value)} onKeyDown={ev => { if (ev.key === 'Enter') addTag(); }} />
              <Button variant="outline" size="sm" className="h-7 text-xs" onClick={addTag}><Plus className="h-3 w-3" /></Button>
            </div>
          </Section>

          {/* Permission Groups */}
          <Section label="权限组">
            <div className="flex flex-wrap gap-1.5">
              {groups.map(g => (
                <button key={g.id} onClick={() => toggle(setE, 'group_ids', g.id)}
                  className={cn('text-[11px] font-bold px-2.5 py-1 rounded-lg border', e.group_ids.includes(g.id) ? 'bg-indigo-100 border-indigo-300 text-indigo-800' : 'bg-white border-border text-muted-foreground/60')}>{g.name}</button>
              ))}
            </div>
            <div className="flex gap-1.5 mt-1.5">
              <Input placeholder="key" className="h-7 text-xs w-20" value={newGroupKey} onChange={ev => setNewGroupKey(ev.target.value)} />
              <Input placeholder="名称" className="h-7 text-xs flex-1" value={newGroupName} onChange={ev => setNewGroupName(ev.target.value)} onKeyDown={ev => { if (ev.key === 'Enter') addGroup(); }} />
              <Button variant="outline" size="sm" className="h-7 text-xs" onClick={addGroup}><Plus className="h-3 w-3" /></Button>
            </div>
          </Section>

          {/* Extra Permissions */}
          <Section label="额外授权（绿色 = 已授权）">
            <div className="flex flex-wrap gap-1">
              {ALL_CAPS.map(c => (
                <button key={c} onClick={() => toggle(setE, 'extra', c)}
                  className={cn('text-[10px] font-mono font-bold px-2 py-0.5 rounded border', e.extra.includes(c) ? 'bg-emerald-100 border-emerald-300 text-emerald-800' : 'bg-white border-border text-muted-foreground/40 hover:border-muted-foreground/40')}>{c}</button>
              ))}
            </div>
          </Section>

          {/* Blocked Permissions */}
          <Section label="禁用权限（红色 = 已禁用）">
            <div className="flex flex-wrap gap-1">
              {ALL_CAPS.map(c => (
                <button key={c} onClick={() => toggle(setE, 'blocked', c)}
                  className={cn('text-[10px] font-mono font-bold px-2 py-0.5 rounded border', e.blocked.includes(c) ? 'bg-red-100 border-red-300 text-red-800' : 'bg-white border-border text-muted-foreground/40 hover:border-muted-foreground/40')}>{c}</button>
              ))}
            </div>
          </Section>

          {/* Note */}
          <Section label="备注">
            <Input value={e.note} maxLength={200} onChange={ev => setE({ ...e, note: ev.target.value })} />
          </Section>
        </div>
      </ScrollArea>
    </Card>
  );
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label className="text-[11px] font-extrabold text-muted-foreground uppercase tracking-wider">{label}</Label>
      {children}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   Institution Admin: Roster Management
   ═══════════════════════════════════════════════════════════ */

type RosterStudent = {
  id: number; username: string; email: string; nickname: string;
  elo_score: number; institution_role: string; date_joined: string;
};

function InstitutionRosterManagement({ institution }: { institution: any }) {
  const [students, setStudents] = useState<RosterStudent[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const fetch = async () => {
    try { const { data } = await api.get('/users/institution/students/'); setStudents(data); } catch { /* */ }
    setLoading(false);
  };
  useEffect(() => { fetch(); }, []);

  const filtered = students.filter(s =>
    !search || s.nickname.includes(search) || s.email.includes(search) || s.username.includes(search)
  );

  const avgElo = students.length ? Math.round(students.reduce((a, s) => a + s.elo_score, 0) / students.length) : 0;

  return (
    <div>
      <h1 className="text-2xl font-extrabold text-foreground tracking-tight mb-1">学员管理</h1>
      <p className="text-sm text-muted-foreground/60 mb-6">
        {institution.name} · {institution.plan_label} · {students.length} / {institution.max_students} 名学员
      </p>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        {[
          { label: '学员总数', value: students.length, icon: Users, color: 'text-primary', bg: 'bg-primary/6' },
          { label: '版本上限', value: institution.max_students, icon: Hash, color: 'text-[#FF9500]', bg: 'bg-[#FF9500]/6' },
          { label: '平均 ELO', value: avgElo, icon: TrendingUp, color: 'text-[#34C759]', bg: 'bg-[#34C759]/6' },
          { label: '版本', value: institution.plan_label, icon: Clock, color: 'text-muted-foreground/60', bg: 'bg-muted-foreground/10' },
        ].map(s => (
          <Card key={s.label} variant="apple" className="p-4 space-y-1">
            <div className={cn('h-8 w-8 rounded-lg flex items-center justify-center', s.bg)}>
              <s.icon className={cn('h-4 w-4', s.color)} />
            </div>
            <p className="text-2xl font-extrabold text-foreground tracking-tightest">{s.value}</p>
            <p className="text-[11px] font-bold text-muted-foreground">{s.label}</p>
          </Card>
        ))}
      </div>

      {/* Toolbar */}
      <div className="flex items-center gap-3 flex-wrap mb-4">
        <div className="relative flex-1 min-w-[200px] max-w-xs">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input placeholder="搜索学员..." className="pl-9" value={search} onChange={e => setSearch(e.target.value)} />
        </div>
        <AddStudentDialog onAdded={fetch} disabled={students.length >= institution.max_students} />
        <BatchImportDialog onImported={fetch} />
        <Button variant="outline" size="sm" onClick={() => {
          const csv = '昵称,用户名,邮箱,ELO\n' + filtered.map(s => `${s.nickname},${s.username},${s.email},${s.elo_score}`).join('\n');
          const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([csv])); a.download = '学员列表.csv'; a.click();
        }} disabled={students.length === 0}><Download className="h-4 w-4" /> 导出</Button>
        <Button variant="ghost" size="icon" onClick={fetch}><RefreshCw className="h-4 w-4" /></Button>
      </div>

      {/* List */}
      {loading ? (
        <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-16 text-muted-foreground">
          <GraduationCap className="h-12 w-12 mx-auto mb-3 opacity-20" />
          <p className="text-sm font-medium">{search ? '没有匹配的学员' : '还没有学员'}</p>
        </div>
      ) : (
        <>
        <div className="space-y-2">
          {filtered.map(s => (
            <Card key={s.id} variant="apple"
              className={cn('p-4 cursor-pointer transition-all',
                selectedId === s.id ? 'ring-2 ring-[#0071E3]' : 'hover:shadow-apple')}
              onClick={() => setSelectedId(selectedId === s.id ? null : s.id)}>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3 min-w-0">
                  <div className="h-9 w-9 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                    <GraduationCap className="h-4 w-4 text-primary" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-bold text-foreground truncate">{s.nickname || s.username}</p>
                    <p className="text-xs text-muted-foreground">{s.email}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0" onClick={e => e.stopPropagation()}>
                  <Badge variant="outline" className="text-[10px]">ELO {s.elo_score}</Badge>
                  <ResetPasswordDialog userId={s.id} username={s.nickname || s.username} />
                  <Button variant="ghost" size="icon" className="h-8 w-8"
                    onClick={async () => {
                      if (!confirm(`确认移除「${s.nickname || s.username}」？`)) return;
                      await api.delete(`/users/institution/students/${s.id}/`);
                      fetch();
                    }}>
                    <Trash2 className="h-3.5 w-3.5 text-muted-foreground hover:text-red-500" />
                  </Button>
                </div>
              </div>
            </Card>
          ))}
        </div>

      <Dialog open={!!selectedId} onOpenChange={() => setSelectedId(null)}>
        <DialogContent className="max-w-lg">
          {selectedId && <StudentDetailPanel studentId={selectedId} />}
        </DialogContent>
      </Dialog>
      </>
      )}
    </div>
  );
}

/* ── Add Student Dialog ── */

function AddStudentDialog({ onAdded, disabled }: { onAdded: () => void; disabled: boolean }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ username: '', email: '', nickname: '', password: '' });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setSaving(true); setError('');
    try {
      await api.post('/users/institution/students/', form);
      setForm({ username: '', email: '', nickname: '', password: '' });
      onAdded(); setOpen(false);
    } catch (err: any) { setError(err.response?.data?.error || '创建失败'); }
    setSaving(false);
  };

  return (
    <>
      <Button variant="apple" size="sm" onClick={() => setOpen(true)} disabled={disabled}>
        <UserPlus className="h-4 w-4" /> 添加学员
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>添加学员</DialogTitle></DialogHeader>
          <form onSubmit={submit} className="space-y-3">
            <Input placeholder="用户名 *" required value={form.username} onChange={e => setForm({ ...form, username: e.target.value })} />
            <Input placeholder="邮箱 *" type="email" required value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} />
            <Input placeholder="昵称" value={form.nickname} onChange={e => setForm({ ...form, nickname: e.target.value })} />
            <Input placeholder="密码 *" type="password" required value={form.password} onChange={e => setForm({ ...form, password: e.target.value })} />
            {error && <p className="text-xs text-red-500">{error}</p>}
            <DialogFooter>
              <Button type="button" variant="outline" size="sm" onClick={() => setOpen(false)}>取消</Button>
              <Button type="submit" variant="apple" size="sm" disabled={saving}>创建</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}

/* ── Student Detail Panel ── */

type StudentStats = {
  student: { id: number; username: string; nickname: string; email: string; elo_score: number; last_active: string };
  questions: { total_answered: number; total_correct: number; total_wrong: number; correct_rate: number; mastered: number; total: number; due_review: number };
  activity: { reviews_this_week: number; exams_this_week: number };
  mastery: { mastered: number; stable: number; learning: number; weak: number; unknown: number };
  recent_scores: { total_score: number; max_score: number; created_at: string }[];
  daily_reviews: { day: string; count: number }[];
};

function StudentDetailPanel({ studentId }: { studentId: number }) {
  const [stats, setStats] = useState<StudentStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.get(`/users/institution/students/${studentId}/stats/`)
      .then(res => setStats(res.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [studentId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!stats) {
    return <p className="text-center text-sm text-muted-foreground py-8">无法加载学员数据</p>;
  }

  const { student, questions, activity, mastery, recent_scores } = stats;
  const total_mastery = Object.values(mastery).reduce((a, b) => a + b, 0) || 1;

  return (
    <div className="space-y-5">
      <DialogHeader>
        <DialogTitle>{student.nickname || student.username}</DialogTitle>
        <p className="text-xs text-muted-foreground">{student.email} · ELO {student.elo_score}</p>
      </DialogHeader>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: '总答题', value: questions.total_answered, sub: `${questions.correct_rate}% 正确` },
          { label: '已掌握', value: questions.mastered, sub: `共 ${questions.total} 题` },
          { label: '待复习', value: questions.due_review, sub: '记忆临界' },
          { label: '本周学习', value: activity.reviews_this_week, sub: `${activity.exams_this_week} 次模考` },
        ].map(s => (
          <div key={s.label} className="bg-muted rounded-xl p-3 text-center space-y-0.5">
            <p className="text-2xl font-extrabold text-foreground tracking-tightest">{s.value}</p>
            <p className="text-[11px] font-bold text-muted-foreground">{s.label}</p>
            <p className="text-[10px] text-muted-foreground/40">{s.sub}</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {/* Knowledge Mastery Bar */}
        <div className="space-y-2">
          <h4 className="text-xs font-extrabold text-muted-foreground uppercase tracking-wider">知识点掌握分布</h4>
          <div className="flex h-5 rounded-full overflow-hidden bg-muted">
            {[
              { key: 'mastered', label: '掌握', color: 'bg-[#34C759]', count: mastery.mastered },
              { key: 'stable', label: '稳定', color: 'bg-primary', count: mastery.stable },
              { key: 'learning', label: '学习中', color: 'bg-[#FF9500]', count: mastery.learning },
              { key: 'weak', label: '薄弱', color: 'bg-[#FF3B30]', count: mastery.weak },
              { key: 'unknown', label: '未知', color: 'bg-muted-foreground/40', count: mastery.unknown },
            ].map(m => (
              <div key={m.key} className={cn(m.color, 'transition-all')}
                style={{ width: `${(m.count / total_mastery) * 100}%` }}
                title={`${m.label}: ${m.count}`} />
            ))}
          </div>
          <div className="flex gap-3 text-[10px] font-bold text-muted-foreground">
            {[
              { key: 'mastered', label: '掌握', color: '#34C759', count: mastery.mastered },
              { key: 'stable', label: '稳定', color: '#0071E3', count: mastery.stable },
              { key: 'learning', label: '学习', color: '#FF9500', count: mastery.learning },
              { key: 'weak', label: '薄弱', color: '#FF3B30', count: mastery.weak },
            ].map(m => (
              <span key={m.key} className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full" style={{ backgroundColor: m.color }} />{m.label} {m.count}
              </span>
            ))}
          </div>
        </div>

        {/* Recent Scores */}
        <div className="space-y-2">
          <h4 className="text-xs font-extrabold text-muted-foreground uppercase tracking-wider">最近模考成绩</h4>
          {recent_scores.length === 0 ? (
            <p className="text-xs text-muted-foreground/40">暂无模考记录</p>
          ) : (
            <div className="space-y-1.5">
              {recent_scores.map((s, i) => (
                <div key={i} className="flex items-center justify-between text-xs">
                  <span className="text-muted-foreground">{s.created_at ? new Date(s.created_at).toLocaleDateString('zh-CN') : ''}</span>
                  <span className="font-bold text-foreground">{s.total_score}/{s.max_score}</span>
                  <span className={cn('font-bold', (s.total_score / s.max_score) >= 0.7 ? 'text-[#34C759]' : 'text-[#FF9500]')}>
                    {Math.round(s.total_score / s.max_score * 100)}%
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ── Batch Import Dialog ── */

function BatchImportDialog({ onImported }: { onImported: () => void }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState('');
  const [importing, setImporting] = useState(false);
  const [result, setResult] = useState<{ ok: number; fail: number; errors: string[] } | null>(null);

  const run = async () => {
    setImporting(true); setResult(null);
    const lines = text.trim().split('\n').filter(Boolean);
    const students = lines.map(line => {
      const p = line.split(',').map(s => s.trim());
      return { username: p[0] || '', email: p[1] || '', password: p[2] || '', nickname: p[3] || '' };
    }).filter(s => s.username && s.email && s.password);
    if (students.length === 0) { setResult({ ok: 0, fail: lines.length, errors: ['无有效数据'] }); setImporting(false); return; }
    try {
      const { data } = await api.post('/users/institution/students/', { students });
      const fail = (data.failed || []).length;
      const errors = (data.failed || []).map((f: any) => `${f.username}: ${f.error}`);
      setResult({ ok: data.created_count || 0, fail, errors }); setImporting(false);
      if (data.created_count > 0) onImported();
    } catch (err: any) {
      setResult({ ok: 0, fail: students.length, errors: [err.response?.data?.error || '导入失败'] });
      setImporting(false);
    }
  };

  return (
    <>
      <Button variant="outline" size="sm" onClick={() => setOpen(true)}><Upload className="h-4 w-4" /> 批量导入</Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader><DialogTitle>批量导入学员</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <p className="text-xs text-muted-foreground/60">每行一个：<code className="bg-muted px-1 rounded">用户名,邮箱,密码,昵称</code></p>
            <textarea className="w-full h-40 rounded-xl border p-3 text-sm font-mono resize-none"
              placeholder="zhangsan,zhang@ex.com,123456,张三" value={text} onChange={e => setText(e.target.value)} />
            {result && (
              <div className={cn('p-3 rounded-xl text-xs space-y-1', result.fail > 0 ? 'bg-amber-50 border border-amber-200' : 'bg-emerald-50 border border-emerald-200')}>
                <p className="font-bold">成功 {result.ok}，失败 {result.fail}</p>
                {result.errors.slice(0, 5).map((e, i) => <p key={i} className="text-red-500">{e}</p>)}
              </div>
            )}
            <DialogFooter>
              <Button variant="outline" size="sm" onClick={() => setOpen(false)}>关闭</Button>
              <Button variant="apple" size="sm" onClick={run} disabled={importing || !text.trim()}>开始导入</Button>
            </DialogFooter>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

/* ── Reset Password Dialog ── */

function ResetPasswordDialog({ userId, username }: { userId: number; username: string }) {
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState('');
  const [saving, setSaving] = useState(false);

  const reset = async () => {
    if (!password || password.length < 6) { toast.error('密码至少 6 位'); return; }
    setSaving(true);
    try {
      // Try institution-level reset first, fall back to superuser endpoint
      try {
        await api.post(`/users/institution/students/${userId}/reset-password/`, { password });
      } catch {
        await api.patch(`/users/admin/superusers/users/${userId}/`, { password });
      }
      toast.success(`已重置 ${username} 的密码`);
      setOpen(false); setPassword('');
    } catch (err: any) {
      toast.error(err.response?.data?.detail || '重置失败，可能需要平台管理员权限');
    }
    setSaving(false);
  };

  return (
    <>
      <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => setOpen(true)} title="重置密码">
        <Key className="h-3.5 w-3.5 text-muted-foreground" />
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>重置密码 — {username}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <Input placeholder="新密码（至少 6 位）" type="password" value={password} onChange={e => setPassword(e.target.value)} />
            <DialogFooter>
              <Button variant="outline" size="sm" onClick={() => setOpen(false)}>取消</Button>
              <Button variant="apple" size="sm" onClick={reset} disabled={saving}>确认重置</Button>
            </DialogFooter>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
