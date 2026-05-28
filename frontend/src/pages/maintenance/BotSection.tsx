import React, { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Bot, Upload, Edit3, Trash2, Plus } from 'lucide-react';
import api from '@/lib/api';
import { toast } from 'sonner';
import { useAuthStore } from '@/store/useAuthStore';
import { useConfirm } from '@/components/useConfirm';
import { InstitutionBotSection } from './InstitutionBotSection';

export const BotSection: React.FC = () => {
  const { t } = useTranslation('maintenance');
  const { user } = useAuthStore();
  const { confirm, Dialog: ConfirmDialog } = useConfirm();

  // 机构管理员看到可见性开关 + 自定义 bot 管理
  if (user?.is_institution_admin && !user?.is_admin) {
    return <div className="max-w-5xl mx-auto space-y-6"><InstitutionBotSection /></div>;
  }
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [editingItem, setEditingItem] = useState<any | null>(null);
  const [form, setForm] = useState({ name: '', prompt: '', avatar: null as File | null, is_exclusive: false });

  const fetchItems = useCallback(async () => {
    try {
      const res = await api.get('/ai/bots/');
      setItems(res.data);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchItems(); }, [fetchItems]);

  const resetForm = () => setForm({ name: '', prompt: '', avatar: null, is_exclusive: false });

  const handleCreate = async () => {
    if (!form.name || !form.prompt) return toast.error(t('bot.infoIncomplete'));
    const fd = new FormData();
    fd.append('name', form.name);
    fd.append('system_prompt', form.prompt);
    fd.append('is_exclusive', String(form.is_exclusive));
    if (form.avatar) fd.append('avatar', form.avatar);
    try {
      const res = await api.post('/ai/bots/', fd);
      const templateName = res.data?.prompt_template_name;
      toast.success(templateName ? t('bot.assistantOnline') + '，Prompt: ' + templateName : t('bot.assistantOnline'));
      resetForm();
      setShowCreate(false);
      fetchItems();
    } catch { toast.error(t('bot.publishFailed')); }
  };

  const handleUpdate = async () => {
    if (!editingItem) return;
    const fd = new FormData();
    Object.keys(editingItem).forEach(key => {
      if (editingItem[key] instanceof File) fd.append(key, editingItem[key]);
      else if (editingItem[key] !== null && editingItem[key] !== undefined) {
        if (key === 'avatar' && typeof editingItem[key] === 'string') return;
        fd.append(key, String(editingItem[key]));
      }
    });
    try {
      await api.patch(`/ai/bots/${editingItem.id}/`, fd);
      toast.success('已更新');
      setEditingItem(null);
      fetchItems();
    } catch { toast.error('更新失败'); }
  };

  const handleDelete = async (id: number, name: string) => {
    if (!(await confirm(`删除机器人「${name}」？此操作不可撤销。`))) return;
    try {
      await api.delete(`/ai/bots/${id}/`);
      toast.success('已删除');
      fetchItems();
    } catch { toast.error('删除失败'); }
  };

  if (loading) return null;

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Bot className="h-5 w-5 text-[#6E6E73]" />
          <h3 className="text-lg font-semibold tracking-tight">{t('tabs.aiBot')}</h3>
          <Badge variant="secondary" className="text-[11px] rounded-full bg-[#F5F5F7] text-[#6E6E73] hover:bg-[#F5F5F7]">{items.length}</Badge>
        </div>
        <Button onClick={() => { resetForm(); setShowCreate(true); }} className="h-10 rounded-xl bg-[#0071E3] hover:bg-[#0077ED] text-white font-medium text-sm px-5 shadow-[0_1px_3px_rgba(0,113,227,0.3)] transition-[background-color,box-shadow] gap-2">
          <Plus className="w-4 h-4" />
          {t('bot.deployAssistant')}
        </Button>
      </div>

      {items.length === 0 ? (
        <Card className="p-16 bg-white rounded-2xl border border-black/[0.04] shadow-[0_1px_2px_rgba(0,0,0,0.02),0_4px_16px_rgba(0,0,0,0.03)] text-center">
          <Bot className="h-10 w-10 text-[#AEAEB2] mx-auto mb-4 opacity-30" />
          <p className="text-sm text-[#8E8E93] font-medium">{t('sectionList.noBots')}</p>
          <p className="text-xs text-[#AEAEB2] mt-1">{t('sectionList.noBotsHint')}</p>
        </Card>
      ) : (
        <Card className="bg-white rounded-2xl border border-black/[0.04] shadow-[0_1px_2px_rgba(0,0,0,0.02),0_4px_16px_rgba(0,0,0,0.03)] overflow-hidden">
          <ScrollArea className="h-[560px]">
            <div className="divide-y divide-black/[0.04]">
              {items.map((item: any) => (
                <div key={item.id} className="p-4 hover:bg-[#F5F5F7]/50 transition-colors group">
                  <div className="flex items-center gap-4">
                    <Avatar className="h-10 w-10 rounded-full shrink-0">
                      <AvatarImage src={item.avatar} />
                      <AvatarFallback className="text-xs font-medium bg-[#F5F5F7]">{item.name?.[0]}</AvatarFallback>
                    </Avatar>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-medium">{item.name}</p>
                        {item.is_exclusive && (
                          <Badge variant="secondary" className="text-[10px] rounded-full bg-amber-100 text-amber-700 font-medium hover:bg-amber-100">专属</Badge>
                        )}
                        {item.institution_name && (
                          <Badge variant="secondary" className="text-[10px] rounded-full bg-blue-100 text-blue-700 font-medium hover:bg-blue-100">{item.institution_name}</Badge>
                        )}
                      </div>
                      <p className="text-xs text-[#8E8E93] mt-0.5 truncate">
                        {item.prompt_template_name || 'bots/bot_id_prompt.txt'} · {item.prompt_file_exists ? 'FILE OK' : 'FILE MISSING'}
                      </p>
                      <p className="text-xs text-[#AEAEB2] mt-0.5 line-clamp-1">{item.system_prompt?.slice(0, 100)}</p>
                    </div>
                    <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                      <Button onClick={() => setEditingItem({ ...item })} variant="ghost" size="icon" className="h-8 w-8 text-[#6E6E73] hover:bg-[#F5F5F7] rounded-lg">
                        <Edit3 className="w-3.5 h-3.5" />
                      </Button>
                      <Button onClick={() => handleDelete(item.id, item.name)} variant="ghost" size="icon" className="h-8 w-8 text-[#6E6E73] hover:bg-red-50 hover:text-red-500 rounded-lg">
                        <Trash2 className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </ScrollArea>
        </Card>
      )}

      {/* Create Dialog */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent className="sm:max-w-[600px] rounded-3xl p-8 border-none shadow-[0_0_0_1px_rgba(0,0,0,0.04),0_4px_8px_rgba(0,0,0,0.04),0_16px_32px_rgba(0,0,0,0.08),0_32px_64px_rgba(0,0,0,0.04)] bg-white text-left">
          <DialogHeader>
            <DialogTitle className="text-lg font-semibold flex items-center gap-3">
              <Bot className="h-5 w-5 text-[#6E6E73]" /> {t('bot.deployAssistant')}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-5 pt-4">
            <div className="flex items-center gap-5">
              <div className="relative group shrink-0">
                <Avatar className="h-20 w-20 border-4 border-white shadow-[0_2px_8px_rgba(0,0,0,0.06)] rounded-full overflow-hidden">
                  {form.avatar ? <AvatarImage src={URL.createObjectURL(form.avatar)} /> : <AvatarFallback className="text-xs font-medium bg-[#F5F5F7]">INIT</AvatarFallback>}
                </Avatar>
                <div className="absolute inset-0 bg-black/30 opacity-0 group-hover:opacity-100 transition-opacity rounded-full flex items-center justify-center cursor-pointer">
                  <Upload className="w-4 h-4 text-white" />
                  <input type="file" onChange={e => setForm({ ...form, avatar: e.target.files?.[0] || null })} className="absolute inset-0 opacity-0 cursor-pointer" accept="image/*" />
                </div>
              </div>
              <div className="flex-1 space-y-2">
                <Label className="text-xs font-medium text-[#6E6E73] ml-1">{t('bot.nickname')}</Label>
                <Input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} className="bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 focus-visible:border-[#0071E3]/30 h-11 rounded-xl px-4 text-sm font-medium" />
              </div>
            </div>
            <textarea value={form.prompt} onChange={e => setForm({ ...form, prompt: e.target.value })} className="w-full bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 focus-visible:border-[#0071E3]/30 rounded-2xl p-5 min-h-[200px] font-medium text-sm resize-none outline-none" placeholder={t('bot.promptPlaceholder')} />
            <div className="flex items-center gap-2">
              <input type="checkbox" id="exclusive" checked={form.is_exclusive} onChange={e => setForm({ ...form, is_exclusive: e.target.checked })} />
              <Label htmlFor="exclusive" className="text-xs font-medium text-[#6E6E73]">{t('editDialog.exclusiveMentorPermission')}</Label>
            </div>
            <Button onClick={handleCreate} className="w-full h-11 rounded-xl bg-[#0071E3] hover:bg-[#0077ED] text-white font-medium text-sm shadow-[0_1px_3px_rgba(0,113,227,0.3)] transition-[background-color,box-shadow]">
              {t('bot.deployBot')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Edit Dialog */}
      <Dialog open={!!editingItem} onOpenChange={open => !open && setEditingItem(null)}>
        <DialogContent className="sm:max-w-[600px] rounded-3xl p-8 border-none shadow-[0_0_0_1px_rgba(0,0,0,0.04),0_4px_8px_rgba(0,0,0,0.04),0_16px_32px_rgba(0,0,0,0.08),0_32px_64px_rgba(0,0,0,0.04)] bg-white text-left">
          <DialogHeader>
            <DialogTitle className="text-lg font-semibold">{t('sectionList.editBot')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-5 pt-4">
            <div className="space-y-1.5">
              <Label className="text-xs font-medium text-[#6E6E73] ml-1">名称</Label>
              <div className="flex items-center gap-4">
                <Input value={editingItem?.name || ''} onChange={e => setEditingItem({ ...editingItem, name: e.target.value })} className="bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 focus-visible:border-[#0071E3]/30 h-11 rounded-xl px-4 text-sm font-medium flex-1" />
                <div className="flex items-center gap-2 shrink-0">
                  <input type="checkbox" id="edit-exclusive" checked={editingItem?.is_exclusive || false} onChange={e => setEditingItem({ ...editingItem, is_exclusive: e.target.checked })} />
                  <Label htmlFor="edit-exclusive" className="text-xs font-medium text-[#6E6E73]">{t('editDialog.exclusiveMentorPermission')}</Label>
                </div>
              </div>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-medium text-[#6E6E73] ml-1">Prompt 模板</Label>
              <Input value={editingItem?.prompt_template_name || ''} readOnly className="bg-[#F5F5F7] border-transparent h-11 rounded-xl px-4 text-sm font-medium text-[#8E8E93]" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-medium text-[#6E6E73] ml-1">System Prompt</Label>
              <textarea value={editingItem?.system_prompt || ''} onChange={e => setEditingItem({ ...editingItem, system_prompt: e.target.value })} className="w-full bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 focus-visible:border-[#0071E3]/30 rounded-2xl p-5 min-h-[200px] font-medium text-sm resize-none outline-none" />
            </div>
            <Button onClick={handleUpdate} className="w-full h-11 rounded-xl bg-[#0071E3] hover:bg-[#0077ED] text-white font-medium text-sm shadow-[0_1px_3px_rgba(0,113,227,0.3)] transition-[background-color,box-shadow]">
              {t('editDialog.updateAndSync')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
      {ConfirmDialog}
    </div>
  );
};
