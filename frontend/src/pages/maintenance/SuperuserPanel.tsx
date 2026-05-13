import React, { useEffect, useMemo, useState } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { Loader2, RefreshCw, Save } from 'lucide-react';
import api from '@/lib/api';
import { formatApiErrorToast } from '@/lib/apiError';
import { toast } from 'sonner';

type UserTag = {
  id: number;
  name: string;
  color: string;
  description: string;
  is_active: boolean;
};

type PermissionGroup = {
  id: number;
  key: string;
  name: string;
  description: string;
  permissions: string[];
  is_active: boolean;
};

type ManagedUser = {
  id: number;
  username: string;
  nickname: string;
  role: 'student' | 'admin';
  is_member: boolean;
  is_staff: boolean;
  is_superuser: boolean;
  tag_names: string[];
  permission_group_keys: string[];
  tag_ids: number[];
  permission_group_ids: number[];
  extra_permissions: string[];
  blocked_permissions: string[];
  profile_note: string;
  capabilities: string[];
};

const EMPTY_EDITOR = {
  role: 'student' as 'student' | 'admin',
  is_member: false,
  is_staff: false,
  is_superuser: false,
  tag_ids: [] as number[],
  permission_group_ids: [] as number[],
  extra_permissions_text: '',
  blocked_permissions_text: '',
  note: '',
};

export const SuperuserPanel: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [search, setSearch] = useState('');
  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [tags, setTags] = useState<UserTag[]>([]);
  const [groups, setGroups] = useState<PermissionGroup[]>([]);
  const [selectedUserId, setSelectedUserId] = useState<number | null>(null);
  const [editor, setEditor] = useState(EMPTY_EDITOR);

  const selectedUser = useMemo(
    () => users.find((u) => u.id === selectedUserId) || null,
    [users, selectedUserId],
  );

  const applyUserToEditor = (user: ManagedUser | null) => {
    if (!user) {
      setEditor(EMPTY_EDITOR);
      return;
    }
    setEditor({
      role: user.role,
      is_member: !!user.is_member,
      is_staff: !!user.is_staff,
      is_superuser: !!user.is_superuser,
      tag_ids: [...(user.tag_ids || [])],
      permission_group_ids: [...(user.permission_group_ids || [])],
      extra_permissions_text: (user.extra_permissions || []).join('\n'),
      blocked_permissions_text: (user.blocked_permissions || []).join('\n'),
      note: user.profile_note || '',
    });
  };

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [userRes, tagRes, groupRes] = await Promise.all([
        api.get('/users/admin/superusers/users/', { params: { page: 1, page_size: 80, search: search.trim() || undefined } }),
        api.get('/users/admin/user-tags/'),
        api.get('/users/admin/permission-groups/'),
      ]);
      const userRows = (userRes.data?.results || []) as ManagedUser[];
      const tagRows = (tagRes.data || []) as UserTag[];
      const groupRows = (groupRes.data || []) as PermissionGroup[];
      setUsers(userRows);
      setTags(tagRows.filter((x) => x.is_active));
      setGroups(groupRows.filter((x) => x.is_active));

      if (!selectedUserId || !userRows.find((u) => u.id === selectedUserId)) {
        const next = userRows[0]?.id ?? null;
        setSelectedUserId(next);
        applyUserToEditor(userRows[0] || null);
      } else {
        const current = userRows.find((u) => u.id === selectedUserId) || null;
        applyUserToEditor(current);
      }
    } catch (e) {
      toast.error(formatApiErrorToast(e, 'Superuser 列表加载失败'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAll();
  }, []);

  useEffect(() => {
    if (!selectedUser) return;
    applyUserToEditor(selectedUser);
  }, [selectedUserId]);

  const toggleId = (ids: number[], id: number) => {
    return ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id];
  };

  const handleSave = async () => {
    if (!selectedUserId) return;
    setSaving(true);
    try {
      await api.patch(`/users/admin/superusers/users/${selectedUserId}/`, {
        role: editor.role,
        is_member: editor.is_member,
        is_staff: editor.is_staff,
        is_superuser: editor.is_superuser,
        tag_ids: editor.tag_ids,
        permission_group_ids: editor.permission_group_ids,
        extra_permissions: editor.extra_permissions_text.split('\n').map((x) => x.trim()).filter(Boolean),
        blocked_permissions: editor.blocked_permissions_text.split('\n').map((x) => x.trim()).filter(Boolean),
        note: editor.note,
      });
      toast.success('用户权限档案已更新');
      await fetchAll();
    } catch (e) {
      toast.error(formatApiErrorToast(e, '保存失败'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="grid grid-cols-1 xl:grid-cols-12 gap-6 text-left">
      <Card className="xl:col-span-4 p-6 rounded-3xl bg-white border border-black/[0.04] shadow-sm space-y-4">
        <div className="flex items-center justify-between gap-3">
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="搜索用户名/昵称"
            className="h-10 rounded-xl bg-slate-50 border-none font-bold text-xs"
          />
          <Button onClick={fetchAll} variant="ghost" size="icon" className="h-9 w-9 rounded-xl">
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4 opacity-50" />}
          </Button>
        </div>
        <ScrollArea className="h-[640px] pr-2">
          <div className="space-y-2">
            {users.map((u) => (
              <button
                key={u.id}
                onClick={() => setSelectedUserId(u.id)}
                className={`w-full text-left rounded-2xl px-3 py-3 border transition ${
                  selectedUserId === u.id
                    ? 'bg-indigo-50 border-indigo-200'
                    : 'bg-slate-50 border-transparent hover:border-black/10'
                }`}
              >
                <div className="flex items-center justify-between">
                  <p className="text-xs font-black text-slate-800">{u.nickname || u.username}</p>
                  <Badge className={u.role === 'admin' ? 'bg-emerald-100 text-emerald-700 border-none text-[10px]' : 'bg-slate-200 text-slate-700 border-none text-[10px]'}>
                    {u.role}
                  </Badge>
                </div>
                <p className="text-[11px] font-bold text-slate-400 mt-1">{u.username}</p>
                <div className="flex flex-wrap gap-1 mt-2">
                  {(u.tag_names || []).slice(0, 3).map((name) => (
                    <Badge key={name} className="bg-amber-100 text-amber-700 border-none text-[10px]">{name}</Badge>
                  ))}
                </div>
              </button>
            ))}
          </div>
        </ScrollArea>
      </Card>

      <Card className="xl:col-span-8 p-6 rounded-3xl bg-white border border-black/[0.04] shadow-sm space-y-5">
        {!selectedUser ? (
          <p className="text-sm font-bold text-slate-400">请选择左侧人员进行编辑</p>
        ) : (
          <>
            <div className="flex items-center justify-between">
              <div>
                <p className="label-apple text-black/40">Superuser 人员编辑</p>
                <h3 className="text-lg font-black text-slate-900 mt-1">{selectedUser.nickname || selectedUser.username}</h3>
                <p className="text-xs font-bold text-slate-400">{selectedUser.username}</p>
              </div>
              <Button onClick={handleSave} className="rounded-xl bg-black text-white text-xs font-bold" disabled={saving}>
                {saving ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <Save className="w-4 h-4 mr-2" />}
                保存变更
              </Button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <Label className="label-muted">角色</Label>
                <select
                  value={editor.role}
                  onChange={(e) => setEditor((prev) => ({ ...prev, role: e.target.value as 'student' | 'admin' }))}
                  className="mt-1 w-full h-10 rounded-xl bg-slate-50 border-none px-3 text-xs font-bold"
                >
                  <option value="student">student</option>
                  <option value="admin">admin</option>
                </select>
              </div>
              <label className="flex items-center gap-2 text-xs font-bold mt-6">
                <input type="checkbox" checked={editor.is_member} onChange={(e) => setEditor((prev) => ({ ...prev, is_member: e.target.checked }))} />
                会员权限
              </label>
              <label className="flex items-center gap-2 text-xs font-bold mt-6">
                <input type="checkbox" checked={editor.is_staff} onChange={(e) => setEditor((prev) => ({ ...prev, is_staff: e.target.checked }))} />
                管理员后台权限
              </label>
            </div>

            <div>
              <Label className="label-muted">标签</Label>
              <div className="mt-2 grid grid-cols-2 md:grid-cols-4 gap-2">
                {tags.map((tag) => (
                  <button
                    key={tag.id}
                    onClick={() => setEditor((prev) => ({ ...prev, tag_ids: toggleId(prev.tag_ids, tag.id) }))}
                    className={`rounded-xl border px-3 py-2 text-[11px] font-bold ${
                      editor.tag_ids.includes(tag.id)
                        ? 'bg-amber-100 border-amber-200 text-amber-700'
                        : 'bg-slate-50 border-transparent text-slate-500'
                    }`}
                  >
                    {tag.name}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <Label className="label-muted">权限组</Label>
              <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2">
                {groups.map((group) => (
                  <button
                    key={group.id}
                    onClick={() => setEditor((prev) => ({ ...prev, permission_group_ids: toggleId(prev.permission_group_ids, group.id) }))}
                    className={`rounded-xl border px-3 py-2 text-left ${
                      editor.permission_group_ids.includes(group.id)
                        ? 'bg-indigo-100 border-indigo-200'
                        : 'bg-slate-50 border-transparent'
                    }`}
                  >
                    <p className="text-xs font-black text-slate-800">{group.name}</p>
                    <p className="text-[10px] font-bold text-slate-500 mt-1">{group.key}</p>
                  </button>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <Label className="label-muted">附加权限（每行一项）</Label>
                <textarea
                  value={editor.extra_permissions_text}
                  onChange={(e) => setEditor((prev) => ({ ...prev, extra_permissions_text: e.target.value }))}
                  className="mt-1 w-full min-h-[110px] rounded-xl bg-slate-50 border-none p-3 text-xs font-mono"
                />
              </div>
              <div>
                <Label className="label-muted">屏蔽权限（每行一项）</Label>
                <textarea
                  value={editor.blocked_permissions_text}
                  onChange={(e) => setEditor((prev) => ({ ...prev, blocked_permissions_text: e.target.value }))}
                  className="mt-1 w-full min-h-[110px] rounded-xl bg-slate-50 border-none p-3 text-xs font-mono"
                />
              </div>
            </div>

            <div>
              <Label className="label-muted">管理备注</Label>
              <Input
                value={editor.note}
                onChange={(e) => setEditor((prev) => ({ ...prev, note: e.target.value }))}
                className="mt-1 h-10 rounded-xl bg-slate-50 border-none font-bold text-xs"
              />
            </div>
          </>
        )}
      </Card>
    </div>
  );
};

