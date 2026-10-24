import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Switch } from '@/components/ui/switch';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { notesApi, type NoteAISetting } from '@/lib/notes';
import { useInstitutionStore } from '@/store/useInstitutionStore';

export default function NoteAISettings({ onboarding = false }: { onboarding?: boolean }) {
  const hasAI = useInstitutionStore(state => state.hasFeature('ai.assistant'));
  const [settings, setSettings] = useState<NoteAISetting | null>(null);
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const load = () => { setFailed(false); void notesApi.aiSettings().then(setSettings).catch(() => setFailed(true)); };
  useEffect(() => { if (hasAI || !onboarding) load(); }, [hasAI, onboarding]);
  const save = async (enabled: boolean) => {
    if (busy) return;
    setBusy(true);
    try { setSettings(await notesApi.updateAISettings(enabled)); setDismissed(true); }
    catch { toast.error('设置保存失败，请重试。'); }
    finally { setBusy(false); }
  };
  if (onboarding && !hasAI) return null;
  if (onboarding) return <Dialog open={!!settings && !settings.acknowledged && !dismissed} onOpenChange={open => { if (!open) { setDismissed(true); void save(false); } }}>
    <DialogContent className="max-w-md"><DialogHeader><DialogTitle>让小宇了解你的笔记</DialogTitle><DialogDescription>开启后，小宇会在后台阅读你保存的笔记，在对话时了解你正在学什么。笔记仅用于你和小宇的交流，小宇不会修改笔记。你可以随时在个人设置中关闭。</DialogDescription></DialogHeader>
      <DialogFooter><Button variant="outline" disabled={busy} onClick={() => { setDismissed(true); void save(false); }}>直接书写</Button><Button disabled={busy} onClick={() => void save(true)}>启用</Button></DialogFooter>
    </DialogContent>
  </Dialog>;
  return <Card className="border-none shadow-sm rounded-3xl bg-card p-8"><div className="flex items-center justify-between gap-5"><label htmlFor="note-ai-awareness" className="font-medium text-sm">让小宇了解我的笔记</label>{failed ? <Button variant="outline" onClick={load}>重试</Button> : <Switch id="note-ai-awareness" checked={settings?.enabled ?? false} disabled={!settings || busy || !hasAI && !settings.enabled} onCheckedChange={value => void save(value)} />}</div></Card>;
}
