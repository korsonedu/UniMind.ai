import React, { useState, useEffect, useCallback } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Bot, Upload, Edit3, Trash2, Plus, Eye } from 'lucide-react';
import api from '@/lib/api';
import { toast } from 'sonner';
import { useInstitutionStore, FEATURES } from '@/store/useInstitutionStore';
import { useConfirm } from '@/components/useConfirm';

interface GlobalBotVis {
  bot_id: number;
  name: string;
  avatar: string | null;
  is_visible: boolean;
}

export const InstitutionBotSection: React.FC = () => {
  const { hasFeature, usage } = useInstitutionStore();
  const { confirm, Dialog: ConfirmDialog } = useConfirm();
  const canCreateCustom = hasFeature(FEATURES.AI_BOT_CUSTOM);
  const customBotQuota = usage?.custom_bot;

  // Global bot visibility
  const [globalBots, setGlobalBots] = useState<GlobalBotVis[]>([]);
  const [globalLoading, setGlobalLoading] = useState(true);

  // Custom bots
  const [customBots, setCustomBots] = useState<any[]>([]);
  const [customLoading, setCustomLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [editingItem, setEditingItem] = useState<any | null>(null);
  const [form, setForm] = useState({ name: '', prompt: '', avatar: null as File | null, is_exclusive: false });

  const fetchGlobalBots = useCallback(async () => {
    try {
      const { data } = await api.get('/ai/bots/visibility/');
      setGlobalBots(data);
    } catch (e) { console.debug('[InstitutionBotSection] fetch failed:', e); }
    finally { setGlobalLoading(false); }
  }, []);

  const fetchCustomBots = useCallback(async () => {
    try {
      const { data } = await api.get('/ai/bots/');
      setCustomBots(data.filter((b: any) => b.institution !== null));
    } catch (e) { console.debug('[InstitutionBotSection] fetch failed:', e); }
    finally { setCustomLoading(false); }
  }, []);

  useEffect(() => { fetchGlobalBots(); fetchCustomBots(); }, [fetchGlobalBots, fetchCustomBots]);

  const toggleVisibility = async (botId: number, visible: boolean) => {
    try {
      await api.patch('/ai/bots/visibility/', { bot_id: botId, is_visible: visible });
      setGlobalBots(prev => prev.map(b => b.bot_id === botId ? { ...b, is_visible: visible } : b));
      toast.success(visible ? '已启用' : '已隐藏');
    } catch { toast.error('操作失败'); }
  };

  const resetForm = () => setForm({ name: '', prompt: '', avatar: null, is_exclusive: false });

  const handleCreate = async () => {
    if (!form.name || !form.prompt) return toast.error('请填写名称和 Prompt');
    const fd = new FormData();
    fd.append('name', form.name);
    fd.append('system_prompt', form.prompt);
    fd.append('is_exclusive', String(form.is_exclusive));
    if (form.avatar) fd.append('avatar', form.avatar);
    try {
      await api.post('/ai/bots/', fd);
      toast.success('自定义机器人已创建');
      resetForm();
      setShowCreate(false);
      fetchCustomBots();
    } catch (e: any) {
      toast.error(e.response?.data?.detail || e.response?.data?.error || '创建失败');
    }
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
      fetchCustomBots();
    } catch { toast.error('更新失败'); }
  };

  const handleDelete = async (id: number, name: string) => {
    if (!(await confirm(`删除机器人「${name}」？此操作不可撤销。`))) return;
    try {
      await api.delete(`/ai/bots/${id}/`);
      toast.success('已删除');
      fetchCustomBots();
    } catch { toast.error('删除失败'); }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {/* Left: Global Bot Visibility */}
      <div className="space-y-4">
        <div className="flex items-center gap-3">
          <Eye className="h-5 w-5 text-[#6E6E73]" />
          <h3 className="text-lg font-semibold tracking-tight">平台机器人</h3>
          <Badge variant="secondary" className="text-[11px] rounded-full bg-[#F5F5F7] text-[#6E6E73]">{globalBots.length}</Badge>
        </div>
        <p className="text-xs text-[#8E8E93] -mt-2">开关控制学生是否可见</p>

        {globalLoading ? null : globalBots.length === 0 ? (
          <Card className="p-8 bg-white rounded-2xl border border-black/[0.04] text-center">
            <p className="text-sm text-[#8E8E93]">暂无平台机器人</p>
          </Card>
        ) : (
          <Card className="bg-white rounded-2xl border border-black/[0.04] overflow-hidden">
            <ScrollArea className="max-h-[500px]">
              <div className="divide-y divide-black/[0.04]">
                {globalBots.map(bot => (
                  <div key={bot.bot_id} className="p-4 flex items-center gap-4 hover:bg-[#F5F5F7]/50 transition-colors">
                    <Avatar className="h-10 w-10 rounded-full shrink-0">
                      <AvatarImage src={bot.avatar || undefined} />
                      <AvatarFallback className="text-xs font-medium bg-[#F5F5F7]">{bot.name?.[0]}</AvatarFallback>
                    </Avatar>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium">{bot.name}</p>
                    </div>
                    <button
                      onClick={() => toggleVisibility(bot.bot_id, !bot.is_visible)}
                      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors shrink-0 ${
                        bot.is_visible ? 'bg-[#0071E3]' : 'bg-[#E5E5EA]'
                      }`}
                    >
                      <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                        bot.is_visible ? 'translate-x-6' : 'translate-x-1'
                      }`} />
                    </button>
                  </div>
                ))}
              </div>
            </ScrollArea>
          </Card>
        )}
      </div>

      {/* Right: Custom Bots */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Bot className="h-5 w-5 text-[#6E6E73]" />
            <h3 className="text-lg font-semibold tracking-tight">自定义机器人</h3>
            <Badge variant="secondary" className="text-[11px] rounded-full bg-[#F5F5F7] text-[#6E6E73]">{customBots.length}</Badge>
            {customBotQuota && customBotQuota.limit !== null && (
              <span className="text-xs text-[#8E8E93]">{customBotQuota.used}/{customBotQuota.limit}</span>
            )}
          </div>
          {canCreateCustom && (
            <Button
              onClick={() => { resetForm(); setShowCreate(true); }}
              disabled={customBotQuota?.status === 'exhausted'}
              className="h-9 rounded-xl bg-[#0071E3] hover:bg-[#0077ED] text-white font-medium text-xs px-4 shadow-[0_1px_3px_rgba(0,113,227,0.3)] gap-1.5"
            >
              <Plus className="w-3.5 h-3.5" />
              创建
            </Button>
          )}
        </div>

        {!canCreateCustom ? (
          <Card className="p-8 bg-white rounded-2xl border border-black/[0.04] text-center">
            <p className="text-sm text-[#8E8E93]">当前方案不支持自定义机器人，请升级到 Solo 或以上方案</p>
          </Card>
        ) : customLoading ? null : customBots.length === 0 ? (
          <Card className="p-12 bg-white rounded-2xl border border-black/[0.04] text-center">
            <Bot className="h-10 w-10 text-[#AEAEB2] mx-auto mb-4 opacity-30" />
            <p className="text-sm text-[#8E8E93] font-medium">还没有自定义机器人</p>
            <p className="text-xs text-[#AEAEB2] mt-1">创建专属你机构的 AI 助教</p>
          </Card>
        ) : (
          <Card className="bg-white rounded-2xl border border-black/[0.04] overflow-hidden">
            <ScrollArea className="max-h-[500px]">
              <div className="divide-y divide-black/[0.04]">
                {customBots.map((item: any) => (
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
                        </div>
                        <p className="text-xs text-[#AEAEB2] mt-0.5 line-clamp-1">{item.system_prompt?.slice(0, 80)}</p>
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
      </div>

      {/* Create Dialog */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent className="sm:max-w-[600px] rounded-3xl p-8 border-none shadow-2xl bg-white">
          <DialogHeader>
            <DialogTitle className="text-lg font-semibold flex items-center gap-3">
              <Bot className="h-5 w-5 text-[#6E6E73]" /> 创建自定义机器人
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-5 pt-4">
            <div className="flex items-center gap-5">
              <div className="relative group shrink-0">
                <Avatar className="h-20 w-20 border-4 border-white shadow-[0_2px_8px_rgba(0,0,0,0.06)] rounded-full overflow-hidden">
                  {form.avatar ? <AvatarImage src={URL.createObjectURL(form.avatar)} /> : <AvatarFallback className="text-xs font-medium bg-[#F5F5F7]">BOT</AvatarFallback>}
                </Avatar>
                <div className="absolute inset-0 bg-black/30 opacity-0 group-hover:opacity-100 transition-opacity rounded-full flex items-center justify-center cursor-pointer">
                  <Upload className="w-4 h-4 text-white" />
                  <input type="file" onChange={e => setForm({ ...form, avatar: e.target.files?.[0] || null })} className="absolute inset-0 opacity-0 cursor-pointer" accept="image/*" />
                </div>
              </div>
              <div className="flex-1 space-y-2">
                <Label className="text-xs font-medium text-[#6E6E73] ml-1">机器人名称</Label>
                <Input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} className="bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 h-11 rounded-xl px-4 text-sm font-medium" />
              </div>
            </div>
            <textarea value={form.prompt} onChange={e => setForm({ ...form, prompt: e.target.value })} className="w-full bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 rounded-2xl p-5 min-h-[200px] font-medium text-sm resize-none outline-none" placeholder="输入机器人的 System Prompt..." />
            <div className="flex items-center gap-2">
              <input type="checkbox" id="inst-exclusive" checked={form.is_exclusive} onChange={e => setForm({ ...form, is_exclusive: e.target.checked })} />
              <Label htmlFor="inst-exclusive" className="text-xs font-medium text-[#6E6E73]">专属导师（注入学生学情上下文）</Label>
            </div>
            <Button onClick={handleCreate} className="w-full h-11 rounded-xl bg-[#0071E3] hover:bg-[#0077ED] text-white font-medium text-sm shadow-[0_1px_3px_rgba(0,113,227,0.3)]">
              创建
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Edit Dialog */}
      <Dialog open={!!editingItem} onOpenChange={open => !open && setEditingItem(null)}>
        <DialogContent className="sm:max-w-[600px] rounded-3xl p-8 border-none shadow-2xl bg-white">
          <DialogHeader>
            <DialogTitle className="text-lg font-semibold">编辑机器人</DialogTitle>
          </DialogHeader>
          <div className="space-y-5 pt-4">
            <div className="space-y-1.5">
              <Label className="text-xs font-medium text-[#6E6E73] ml-1">名称</Label>
              <div className="flex items-center gap-4">
                <Input value={editingItem?.name || ''} onChange={e => setEditingItem({ ...editingItem, name: e.target.value })} className="bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 h-11 rounded-xl px-4 text-sm font-medium flex-1" />
                <div className="flex items-center gap-2 shrink-0">
                  <input type="checkbox" id="edit-inst-exclusive" checked={editingItem?.is_exclusive || false} onChange={e => setEditingItem({ ...editingItem, is_exclusive: e.target.checked })} />
                  <Label htmlFor="edit-inst-exclusive" className="text-xs font-medium text-[#6E6E73]">专属导师</Label>
                </div>
              </div>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-medium text-[#6E6E73] ml-1">System Prompt</Label>
              <textarea value={editingItem?.system_prompt || ''} onChange={e => setEditingItem({ ...editingItem, system_prompt: e.target.value })} className="w-full bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 rounded-2xl p-5 min-h-[200px] font-medium text-sm resize-none outline-none" />
            </div>
            <Button onClick={handleUpdate} className="w-full h-11 rounded-xl bg-[#0071E3] hover:bg-[#0077ED] text-white font-medium text-sm shadow-[0_1px_3px_rgba(0,113,227,0.3)]">
              更新
            </Button>
          </div>
        </DialogContent>
      </Dialog>
      {ConfirmDialog}
    </div>
  );
};
