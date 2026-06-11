import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Stack } from '@phosphor-icons/react';
import api from '@/lib/api';
import { toast } from 'sonner';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (albumId: string) => void;
  onRefresh: () => void;
}

export const QuickCreateAlbumDialog: React.FC<Props> = ({ open, onOpenChange, onCreated, onRefresh }) => {
  const { t } = useTranslation('maintenance');
  const [name, setName] = useState('');
  const [desc, setDesc] = useState('');

  const handleCreate = async () => {
    if (!name.trim()) return toast.error(t('quickCreate.nameRequired'));
    try {
      const res = await api.post('/courses/albums/', { name: name.trim(), description: desc.trim() });
      const newId = res.data.id.toString();
      await onRefresh();
      onCreated(newId);
      onOpenChange(false);
      setName('');
      setDesc('');
      toast.success(t('album.albumCreated'));
    } catch (e) {
      toast.error(t('quickCreate.createFailed'));
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[420px] rounded-3xl p-8 border-none shadow-[0_0_0_1px_rgba(0,0,0,0.04),0_4px_8px_rgba(0,0,0,0.04),0_16px_32px_rgba(0,0,0,0.08),0_32px_64px_rgba(0,0,0,0.04)] bg-white text-left">
        <DialogHeader>
          <DialogTitle className="text-lg font-semibold flex items-center gap-3">
            <Stack className="text-emerald-500 w-5 h-5" /> {t('quickCreate.newAlbum')}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-5 pt-4">
          <div className="space-y-1.5">
            <Label className="text-xs font-medium text-[#6E6E73]">{t('quickCreate.albumName')}</Label>
            <Input
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder={t('quickCreate.albumNamePlaceholder')}
              className="bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 focus-visible:border-[#0071E3]/30 h-11 rounded-xl px-4 text-sm font-medium"
            />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs font-medium text-[#6E6E73]">{t('quickCreate.albumDesc')}</Label>
            <textarea
              value={desc}
              onChange={e => setDesc(e.target.value)}
              className="w-full bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 focus-visible:border-[#0071E3]/30 rounded-xl p-4 min-h-[80px] font-medium text-xs resize-none outline-none"
              placeholder={t('quickCreate.albumDescPlaceholder')}
            />
          </div>
          <div className="flex gap-3 pt-2">
            <Button variant="outline" onClick={() => onOpenChange(false)} className="flex-1 h-11 rounded-xl border-black/[0.06] bg-white hover:bg-[#F5F5F7] font-medium text-sm">
              {t('quickCreate.cancel')}
            </Button>
            <Button onClick={handleCreate} className="flex-[2] h-11 rounded-xl bg-[#0071E3] hover:bg-[#0077ED] text-white font-medium text-sm shadow-[0_1px_3px_rgba(0,113,227,0.3)] transition-[background-color,box-shadow]">
              {t('quickCreate.confirmCreate')}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};
