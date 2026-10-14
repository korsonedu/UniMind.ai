import { useState } from 'react';
import { PencilSimple, Plus, Trash } from '@phosphor-icons/react';
import { toast } from 'sonner';
import type { CourseModule } from '@/types/api';
import api from '@/lib/api';
import { formatApiErrorToast } from '@/lib/apiError';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { useConfirm } from '@/components/useConfirm';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  modules: CourseModule[];
  onRefresh: () => Promise<void>;
}

export function CourseModuleDialog({ open, onOpenChange, modules, onRefresh }: Props) {
  const [editing, setEditing] = useState<CourseModule | null>(null);
  const [form, setForm] = useState({ name: '', description: '', is_public: false, sort_order: 0 });
  const [saving, setSaving] = useState(false);
  const { confirm, Dialog: ConfirmDialog } = useConfirm();
  const reset = () => { setEditing(null); setForm({ name: '', description: '', is_public: false, sort_order: modules.length ? Math.max(...modules.map(module => module.sort_order)) + 1 : 0 }); };
  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!form.name.trim() || saving) return;
    setSaving(true);
    try {
      const payload = { ...form, name: form.name.trim() };
      if (editing) await api.patch(`/courses/modules/${editing.id}/`, payload);
      else await api.post('/courses/modules/', payload);
      await onRefresh();
      setEditing(null);
      setForm({ name: '', description: '', is_public: false, sort_order: Math.max(form.sort_order, ...modules.map(module => module.sort_order)) + 1 });
      toast.success(editing ? '模块已更新' : '模块已创建');
    } catch (error) { toast.error(formatApiErrorToast(error, '模块保存失败')); }
    finally { setSaving(false); }
  };
  const remove = async (module: CourseModule) => {
    if (!(await confirm(`删除模块「${module.name}」？`))) return;
    setSaving(true);
    try {
      await api.delete(`/courses/modules/${module.id}/`);
      if (editing?.id === module.id) reset();
      await onRefresh();
      toast.success('模块已删除');
    } catch (error) { toast.error(formatApiErrorToast(error, '模块删除失败')); }
    finally { setSaving(false); }
  };
  return <Dialog open={open} onOpenChange={value => { if (saving) return; onOpenChange(value); if (value) reset(); }}>
    <DialogContent className="sm:max-w-[640px] max-h-[90dvh] overflow-y-auto rounded-lg">
      <DialogHeader><DialogTitle>课程模块</DialogTitle></DialogHeader>
      <ul className="divide-y border-y max-h-64 overflow-y-auto">
        {modules.map(module => <li key={module.id} className="flex items-center gap-3 py-3">
          <div className="min-w-0 flex-1"><p className="text-sm font-medium break-words">{module.name}</p><p className="text-xs text-muted-foreground">{module.course_count} 门课程 · 顺序 {module.sort_order}</p></div>
          <Button type="button" variant="ghost" size="icon" title={`编辑${module.name}`} aria-label={`编辑${module.name}`} disabled={saving} onClick={() => { setEditing(module); setForm({ name: module.name, description: module.description, is_public: module.is_public, sort_order: module.sort_order }); }}><PencilSimple size={16} /></Button>
          <Button type="button" variant="ghost" size="icon" title={module.course_count ? '请先迁出模块内课程' : `删除${module.name}`} aria-label={`删除${module.name}`} disabled={saving || module.course_count > 0} onClick={() => { void remove(module); }}><Trash size={16} /></Button>
        </li>)}
        {!modules.length && <li className="py-5 text-sm text-muted-foreground">暂无模块</li>}
      </ul>
      <form onSubmit={save} className="space-y-4">
        <div className="flex items-center justify-between"><h3 className="text-sm font-medium">{editing ? '编辑模块' : '新建模块'}</h3>{editing && <Button type="button" variant="ghost" size="icon" aria-label="新建模块" title="新建模块" disabled={saving} onClick={reset}><Plus size={16} /></Button>}</div>
        <div className="space-y-2"><Label htmlFor="module-name">模块名称</Label><Input id="module-name" required maxLength={100} value={form.name} disabled={saving} onChange={event => setForm({ ...form, name: event.target.value })} /></div>
        <div className="space-y-2"><Label htmlFor="module-description">模块简介</Label><Textarea id="module-description" value={form.description} disabled={saving} onChange={event => setForm({ ...form, description: event.target.value })} /></div>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.is_public} disabled={saving} onChange={event => setForm({ ...form, is_public: event.target.checked })} />免费开放</label>
        <div className="space-y-2"><Label htmlFor="module-order">显示顺序</Label><Input id="module-order" type="number" min={0} step={1} required value={form.sort_order} disabled={saving} onChange={event => setForm({ ...form, sort_order: Number(event.target.value) })} /></div>
        <div className="flex justify-end"><Button type="submit" disabled={saving || !form.name.trim()}>{saving ? '保存中…' : '保存模块'}</Button></div>
      </form>
      {ConfirmDialog}
    </DialogContent>
  </Dialog>;
}
