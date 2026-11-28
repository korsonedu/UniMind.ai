import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { t } from '@/i18n';
import api from '@/lib/api';

type Kind = 'course' | 'note';
type Source = { id: number; title: string | null };
type Sources = { attached: (Source & { kind: Kind })[]; available: Source[] };

export function LearningMemorySources({ projectId }: { projectId: number }) {
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<Kind>('course');
  const [draft, setDraft] = useState('');
  const [search, setSearch] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  const url = `/ai/projects/${projectId}/learning-memory/sources/`;
  const sources = useQuery({
    queryKey: ['learning-memory-sources', projectId, kind, search],
    queryFn: ({ signal }) => api.get<Sources>(url, { params: { kind, q: search }, signal }).then(response => response.data),
    enabled: open,
  });

  async function change(id: number, removing: boolean) {
    setBusy(true);
    setError(false);
    try {
      if (removing) await api.delete(`${url}${id}/`);
      else await api.post(url, { kind, source_id: id });
      await sources.refetch();
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  }

  return <details className="um-path-block" onToggle={event => setOpen(event.currentTarget.open)}>
    <summary>{t('关联学习记录')}</summary>
    <p>{t('关联后，小宇可以在新对话中找回这门课的进度或这篇笔记。')}</p>
    {sources.data?.attached.map(source => <p key={source.id}>
      {source.title ?? t('来源已不可访问')}{' '}
      <button type="button" className="um-learning-text-button" disabled={busy}
        onClick={() => void change(source.id, true)}>{t('解除关联')}</button>
    </p>)}
    <form onSubmit={event => { event.preventDefault(); setSearch(draft.trim()); }}>
      <label>{t('来源类型')}<select value={kind} disabled={busy}
        onChange={event => setKind(event.target.value === 'note' ? 'note' : 'course')}>
        <option value="course">{t('课程')}</option>
        <option value="note">{t('笔记')}</option>
      </select></label>
      <label>{t('按标题查找')}<input maxLength={120} value={draft} onChange={event => setDraft(event.target.value)} /></label>{' '}
      <button type="submit" className="um-agent-button" disabled={busy}>{t('搜索')}</button>
    </form>
    {open && sources.isPending && <p role="status">{t('正在读取学习来源…')}</p>}
    {(error || sources.isError) && <p role="alert">{t('学习记录关联操作失败，请重试。')}</p>}
    {sources.data?.available.length === 0 && <p>{t('没有找到可关联的来源。')}</p>}
    {sources.data?.available.map(source => <p key={source.id}>
      {source.title || t('无标题')}{' '}
      <button type="button" className="um-learning-text-button" disabled={busy}
        onClick={() => void change(source.id, false)}>{t('关联到项目')}</button>
    </p>)}
  </details>;
}
