import { useState } from 'react';
import { Link } from 'react-router-dom';
import api from '@/lib/api';

interface NoteSource {
  source_id: string;
  note_id: number;
  title: string;
  version: number;
  excerpt: string;
}

function isSource(value: unknown): value is NoteSource {
  if (!value || typeof value !== 'object') return false;
  const source = value as Partial<NoteSource>;
  return typeof source.source_id === 'string' && /^N[1-9]\d*$/.test(source.source_id)
    && Number.isInteger(source.note_id) && typeof source.title === 'string'
    && Number.isInteger(source.version) && typeof source.excerpt === 'string';
}

function SourceItem({ source, cited }: { source: NoteSource; cited: boolean }) {
  const [status, setStatus] = useState<'idle' | 'loading' | 'available' | 'unavailable' | 'error'>('idle');
  const [version, setVersion] = useState(source.version);
  const check = async (open: boolean) => {
    if (!open || status === 'loading') return;
    setStatus('loading');
    try {
      const { data } = await api.get(`/notes/items/${source.note_id}/`);
      setVersion(data.version);
      setStatus(data.deleted_at ? 'unavailable' : 'available');
    } catch (error) {
      const code = (error as { response?: { status?: number } }).response?.status;
      setStatus(code === 404 || code === 403 ? 'unavailable' : 'error');
    }
  };
  return <details className="py-1" onToggle={event => void check(event.currentTarget.open)}>
    <summary className="cursor-pointer text-xs text-muted-foreground">
      [{source.source_id}] {source.title || '无标题'} · {cited ? '回答引用' : '本次参考'}
    </summary>
    <div className="mt-2 space-y-2 rounded-md bg-muted/40 p-3 text-xs text-muted-foreground">
      <p>回答使用版本 {source.version} 的历史片段。</p>
      <p className="whitespace-pre-wrap max-h-48 overflow-auto leading-relaxed">{source.excerpt}</p>
      {status === 'loading' && <p role="status">正在检查原笔记…</p>}
      {status === 'available' && <p>
        {version !== source.version && <span>原笔记现为版本 {version}，正文已更新。 </span>}
        <Link className="underline underline-offset-2 text-foreground" to={`/notes/${source.note_id}`}>打开原笔记</Link>
      </p>}
      {status === 'unavailable' && <p>原笔记已删除或当前不可访问。</p>}
      {status === 'error' && <button className="underline" onClick={() => void check(true)}>原笔记状态读取失败，重试</button>}
    </div>
  </details>;
}

export function NoteSources({ sources, content }: { sources: unknown; content: string }) {
  if (!Array.isArray(sources)) return null;
  const valid = sources.filter(isSource);
  if (!valid.length) return null;
  return <div className="mt-2 w-full" aria-label="笔记来源">
    {valid.map(source => <SourceItem key={source.source_id} source={source} cited={content.includes(`[${source.source_id}]`)} />)}
  </div>;
}
