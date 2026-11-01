import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import axios from 'axios';
import { noteDraft, notesApi, type Note, type NoteDraft } from '@/lib/notes';
import { offlineCacheSupported, queueNoteSave, removeQueuedNote } from '@/lib/offlineData';
import { useAuthStore } from '@/store/useAuthStore';

export function useNoteSave(onSaved: (note: Note) => void) {
  const [documentKey, setDocumentKey] = useState(0);
  const [note, setNote] = useState<Note | null>(null);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');
  const current = useRef<Note | null>(null);
  const saved = useRef('');
  const [savedSignature, setSavedSignature] = useState('');
  const conflict = useRef(false);
  const pending = useRef<Promise<void> | null>(null);
  const onSavedRef = useRef(onSaved);
  useLayoutEffect(() => { onSavedRef.current = onSaved; }, [onSaved]);
  const dirty = saving || (!!note && JSON.stringify(noteDraft(note)) !== savedSignature);
  const load = useCallback((value: Note | null) => {
    current.current = value; saved.current = value ? JSON.stringify(noteDraft(value)) : '';
    setSavedSignature(saved.current);
    setDocumentKey(value => value + 1);
    conflict.current = false; setError(''); setStatus(value ? '已保存' : ''); setNote(value);
  }, []);
  const change = useCallback((patch: Partial<NoteDraft>) => {
    if (!current.current || current.current.deleted_at) return;
    const next = { ...current.current, ...patch };
    current.current = next; setNote(next); setStatus('未保存');
    if (!conflict.current) setError('');
  }, []);
  const flush = useCallback(async () => {
    if (pending.current) return pending.current;
    const work = async () => {
      if (conflict.current) throw new Error('版本冲突，请先保留本地内容，再重新加载。');
      const userId = useAuthStore.getState().user?.id;
      const queueLocally = async (snapshot: Note, signature: string) => {
        if (!userId || !offlineCacheSupported()) return false;
        await queueNoteSave(userId, snapshot.id, snapshot.version, noteDraft(snapshot));
        saved.current = signature; setSavedSignature(signature);
        setStatus('已保存到本地，等待同步'); setError('');
        onSavedRef.current({ ...snapshot, updated_at: new Date().toISOString() });
        return true;
      };
      while (current.current && !current.current.deleted_at && JSON.stringify(noteDraft(current.current)) !== saved.current) {
        const snapshot = current.current;
        const signature = JSON.stringify(noteDraft(snapshot));
        if (!navigator.onLine && await queueLocally(snapshot, signature)) return;
        setStatus('保存中…');
        try {
          const result = await notesApi.save(snapshot);
          if (current.current?.id !== snapshot.id) return;
          if (userId) await removeQueuedNote(userId, snapshot.id);
          saved.current = signature; setSavedSignature(signature);
          const next = { ...current.current, version: result.version, updated_at: result.updated_at, backlinks: result.backlinks };
          current.current = next; setNote(next); setError('');
          onSavedRef.current(result);
        } catch (cause) {
          const networkFailure = axios.isAxiosError(cause) && !cause.response;
          if (networkFailure && await queueLocally(snapshot, signature)) return;
          conflict.current = axios.isAxiosError(cause) && cause.response?.status === 409;
          const message = conflict.current ? '其他页面已更新这篇笔记。本地内容已保留，请复制或下载后重新加载，避免覆盖。' : '保存失败，本地内容已保留。请检查网络后重试。';
          setError(message); setStatus('保存失败'); throw new Error(message);
        }
      }
      setStatus('已保存');
    };
    setSaving(true);
    pending.current = work();
    try { await pending.current; } finally { pending.current = null; setSaving(false); }
  }, []);
  useEffect(() => {
    if (!dirty || error) return;
    const timer = window.setTimeout(() => { void flush().catch(() => {}); }, 700);
    return () => window.clearTimeout(timer);
  }, [note, dirty, error, flush]);
  useEffect(() => {
    const protect = (event: BeforeUnloadEvent) => {
      if (pending.current || (current.current && JSON.stringify(noteDraft(current.current)) !== saved.current)) { event.preventDefault(); event.returnValue = ''; }
    };
    window.addEventListener('beforeunload', protect);
    return () => window.removeEventListener('beforeunload', protect);
  }, []);
  return { note, documentKey, dirty, status, error, load, change, flush };
}
