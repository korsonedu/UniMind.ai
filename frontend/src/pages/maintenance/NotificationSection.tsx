import React, { useState, useCallback, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { Bell, Plus, PaperPlaneTilt, Spinner } from '@phosphor-icons/react';
import api from '@/lib/api';
import { toast } from 'sonner';

export const NotificationSection: React.FC = () => {
  const { t } = useTranslation('maintenance');
  const [showCompose, setShowCompose] = useState(false);
  const [form, setForm] = useState({ title: '', content: '', link: '' });
  const [isSending, setIsSending] = useState(false);
  const [history, setHistory] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchHistory = useCallback(async () => {
    try {
      const res = await api.get('/notifications/');
      setHistory(Array.isArray(res.data) ? res.data : res.data?.results || []);
    } catch (e) { console.debug('[NotificationSection] endpoint not available:', e); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchHistory(); }, [fetchHistory]);

  const handleSend = async () => {
    if (!form.title || !form.content) return toast.error(t('notification.contentRequired'));
    setIsSending(true);
    try {
      await api.post('/notifications/broadcast/', form);
      toast.success(t('notification.notificationSent'));
      setForm({ title: '', content: '', link: '' });
      setShowCompose(false);
      fetchHistory();
    } catch { toast.error(t('notification.sendFailed')); }
    finally { setIsSending(false); }
  };

  if (loading) return null;

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Bell className="h-5 w-5 text-[#6E6E73]" />
          <h3 className="text-lg font-semibold tracking-tight">{t('notification.siteBroadcast')}</h3>
          <Badge variant="secondary" className="text-[11px] rounded-full bg-[#F5F5F7] text-[#6E6E73] hover:bg-[#F5F5F7]">{history.length}</Badge>
        </div>
        <Button onClick={() => setShowCompose(true)} className="h-10 rounded-xl bg-[#0071E3] hover:bg-[#0077ED] text-white font-medium text-sm px-5 shadow-[0_1px_3px_rgba(0,113,227,0.3)] transition-[background-color,box-shadow] gap-2">
          <Plus className="w-4 h-4" />
          {t('sectionList.composeBroadcast')}
        </Button>
      </div>

      {/* List */}
      {history.length === 0 ? (
        <Card className="p-16 bg-white rounded-2xl border border-black/[0.04] shadow-[0_1px_2px_rgba(0,0,0,0.02),0_4px_16px_rgba(0,0,0,0.03)] text-center">
          <Bell className="h-10 w-10 text-[#AEAEB2] mx-auto mb-4 opacity-30" />
          <p className="text-sm text-[#8E8E93] font-medium">{t('sectionList.noBroadcasts')}</p>
          <p className="text-xs text-[#AEAEB2] mt-1">{t('sectionList.noBroadcastsHint')}</p>
        </Card>
      ) : (
        <Card className="bg-white rounded-2xl border border-black/[0.04] shadow-[0_1px_2px_rgba(0,0,0,0.02),0_4px_16px_rgba(0,0,0,0.03)] overflow-hidden">
          <ScrollArea className="h-[560px]">
            <div className="divide-y divide-black/[0.04]">
              {history.map((item: any, i: number) => (
                <div key={item.id || i} className="p-4 hover:bg-[#F5F5F7]/50 transition-colors">
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-semibold">{item.title || item.content?.slice(0, 40)}</p>
                      <p className="text-xs text-[#8E8E93] mt-0.5 line-clamp-1">{item.content}</p>
                      {item.link && (
                        <a href={item.link} className="text-xs text-[#0071E3] mt-0.5 inline-block truncate" target="_blank" rel="noopener noreferrer">
                          {item.link}
                        </a>
                      )}
                    </div>
                    <div className="shrink-0 text-right">
                      <span className="text-[11px] text-[#AEAEB2] font-medium">
                        {item.created_at ? new Date(item.created_at).toLocaleDateString() : ''}
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </ScrollArea>
        </Card>
      )}

      {/* Compose Dialog */}
      <Dialog open={showCompose} onOpenChange={setShowCompose}>
        <DialogContent className="sm:max-w-[600px] rounded-3xl p-8 border-none shadow-[0_0_0_1px_rgba(0,0,0,0.04),0_4px_8px_rgba(0,0,0,0.04),0_16px_32px_rgba(0,0,0,0.08),0_32px_64px_rgba(0,0,0,0.04)] bg-white text-left">
          <DialogHeader>
            <DialogTitle className="text-lg font-semibold flex items-center gap-3">
              <Bell className="h-5 w-5 text-[#6E6E73]" /> {t('notification.siteBroadcast')}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-5 pt-4">
            <div className="space-y-1.5">
              <Label className="text-xs font-medium text-[#6E6E73] ml-1">标题</Label>
              <Input
                value={form.title}
                onChange={e => setForm({ ...form, title: e.target.value })}
                placeholder={t('notification.titlePlaceholder')}
                className="bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 focus-visible:border-[#0071E3]/30 h-11 rounded-xl px-4 text-sm font-medium"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-medium text-[#6E6E73] ml-1">内容</Label>
              <textarea
                value={form.content}
                onChange={e => setForm({ ...form, content: e.target.value })}
                placeholder={t('notification.contentPlaceholder')}
                maxLength={50}
                className="w-full bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 focus-visible:border-[#0071E3]/30 rounded-2xl p-5 min-h-[120px] font-medium text-sm resize-none outline-none"
              />
              <p className="text-[11px] text-[#AEAEB2] text-right">{form.content.length}/50</p>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-medium text-[#6E6E73] ml-1">链接（选填）</Label>
              <Input
                value={form.link}
                onChange={e => setForm({ ...form, link: e.target.value })}
                placeholder="https://..."
                className="bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 focus-visible:border-[#0071E3]/30 h-11 rounded-xl px-4 text-sm font-medium"
              />
            </div>
            <Button
              onClick={handleSend}
              disabled={isSending}
              className="w-full h-11 rounded-xl bg-[#0071E3] hover:bg-[#0077ED] text-white font-medium text-sm shadow-[0_1px_3px_rgba(0,113,227,0.3)] transition-[background-color,box-shadow] gap-2"
            >
              {isSending ? <Spinner className="h-4 w-4 animate-spin" /> : <PaperPlaneTilt className="h-4 w-4" />}
              {t('notification.sendBroadcast')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};
