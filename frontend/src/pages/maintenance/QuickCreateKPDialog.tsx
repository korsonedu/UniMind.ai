import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { BrainCircuit } from 'lucide-react';
import api from '@/lib/api';
import { toast } from 'sonner';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  kpList: any[];
  onCreated: (kpId: string) => void;
  onRefresh: () => void;
}

export const QuickCreateKPDialog: React.FC<Props> = ({ open, onOpenChange, kpList, onCreated, onRefresh }) => {
  const { t } = useTranslation('maintenance');
  const [form, setForm] = useState({ name: '', description: '', parent: '0' });

  const handleCreate = async () => {
    if (!form.name.trim()) return toast.error(t('quickCreate.nameRequired'));
    try {
      const res = await api.post('/quizzes/knowledge-points/', {
        ...form,
        parent: form.parent === '0' ? null : form.parent,
      });
      const newId = res.data.id.toString();
      await onRefresh();
      onCreated(newId);
      onOpenChange(false);
      setForm({ name: '', description: '', parent: '0' });
    } catch (e) {
      toast.error(t('quickCreate.createFailed'));
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px] rounded-3xl p-8 border-none shadow-[0_0_0_1px_rgba(0,0,0,0.04),0_4px_8px_rgba(0,0,0,0.04),0_16px_32px_rgba(0,0,0,0.08),0_32px_64px_rgba(0,0,0,0.04)] bg-white text-left">
        <DialogHeader>
          <DialogTitle className="text-lg font-semibold flex items-center gap-3">
            <BrainCircuit className="text-indigo-500 w-5 h-5" /> {t('quickCreate.newKnowledgePoint')}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-5 pt-4">
          <div className="space-y-1.5">
            <Label className="text-xs font-medium text-[#6E6E73]">{t('quickCreate.nodeName')}</Label>
            <Input
              value={form.name}
              onChange={e => setForm({ ...form, name: e.target.value })}
              placeholder={t('quickCreate.nodeNamePlaceholder')}
              className="bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 focus-visible:border-[#0071E3]/30 h-11 rounded-xl px-4 text-sm font-medium"
            />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs font-medium text-[#6E6E73]">{t('quickCreate.parent')}</Label>
            <Select value={form.parent} onValueChange={v => setForm({ ...form, parent: v })}>
              <SelectTrigger className="h-11 rounded-xl bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 focus-visible:border-[#0071E3]/30 font-medium text-xs px-4">
                <SelectValue placeholder={t('quickCreate.topLevel')} />
              </SelectTrigger>
              <SelectContent>
                {kpList.map((kp: any) => (
                  <SelectItem key={kp.id} value={kp.id.toString()} className="text-xs">{kp.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <textarea
            value={form.description}
            onChange={e => setForm({ ...form, description: e.target.value })}
            className="w-full bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 focus-visible:border-[#0071E3]/30 rounded-xl p-4 min-h-[100px] font-medium text-xs resize-none outline-none"
            placeholder={t('quickCreate.descPlaceholder')}
          />
          <div className="flex gap-3 pt-2">
            <Button variant="outline" onClick={() => onOpenChange(false)} className="flex-1 h-11 rounded-xl border-black/[0.06] bg-white hover:bg-[#F5F5F7] font-medium text-sm">
              {t('quickCreate.cancel')}
            </Button>
            <Button onClick={handleCreate} className="flex-[2] h-11 rounded-xl bg-[#0071E3] hover:bg-[#0077ED] text-white font-medium text-sm shadow-[0_1px_3px_rgba(0,113,227,0.3)] transition-[background-color,box-shadow]">
              {t('quickCreate.confirmSave')}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};
