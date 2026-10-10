import { useState, useRef, useEffect } from 'react';
import { MagnifyingGlass, Plus, Trash, CaretLeft, CaretRight } from '@phosphor-icons/react';
import type { SessionSidebarProps } from './SessionSidebar';

export default function NativeSessionSidebar({ sessions, activeSessionId, onSelect, onDelete, onNew }: SessionSidebarProps) {
  const [query, setQuery] = useState('');
  const [width, setWidth] = useState(208);
  const cleanup = useRef<(() => void) | null>(null);
  useEffect(() => () => cleanup.current?.(), []);
  const collapsed = width === 48;
  const filtered = [...sessions].reverse().filter(session => [session.title, session.label, ...session.messages.map(message => message.content)].join(' ').toLowerCase().includes(query.trim().toLowerCase()));
  return <aside className="um-agent-sessions" style={{ width }} aria-label="历史对话">
    <header><h2>{collapsed ? '' : '历史对话'}</h2><button aria-label={collapsed ? '展开历史对话' : '收起历史对话'} onClick={() => setWidth(collapsed ? 208 : 48)}>{collapsed ? <CaretRight size={16} /> : <CaretLeft size={16} />}</button></header>
    <button className="um-agent-button um-agent-new" data-session-new onClick={onNew} aria-label="开始新对话"><Plus size={16} />{!collapsed && '新对话'}</button>
    {!collapsed && <label className="um-agent-search"><MagnifyingGlass size={16} /><input value={query} onChange={event => setQuery(event.target.value)} placeholder="搜索对话" aria-label="搜索对话" /></label>}
    <nav aria-label="会话列表"><ul>{filtered.map(session => <li key={session.id} data-active={session.id === activeSessionId}>
      <button data-session-select aria-current={session.id === activeSessionId ? 'page' : undefined} onClick={() => onSelect(session)} title={session.title || session.label}>
        {collapsed ? <span className="um-agent-session-dot" /> : <><span>{session.title || session.label}</span><span className="um-agent-session-meta">{session.messages.length} 条 · {session.lastTime ? new Date(session.lastTime).toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' }) : ''}</span></>}
      </button>
      {!collapsed && onDelete && <button className="um-agent-delete" onClick={() => onDelete(session)} aria-label={`删除对话：${session.title || session.label}`}><Trash size={15} /></button>}
    </li>)}</ul>{!filtered.length && !collapsed && <p className="um-agent-empty">{query ? '没有匹配的对话' : '暂无历史对话'}</p>}</nav>
    <div className="um-agent-resize" role="separator" aria-label="调整历史对话宽度" aria-orientation="vertical" aria-valuemin={48} aria-valuemax={320} aria-valuenow={width} tabIndex={0}
      onKeyDown={event => { if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') { event.preventDefault(); setWidth(value => Math.max(48, Math.min(320, value + (event.key === 'ArrowLeft' ? -16 : 16)))); } }}
      onPointerDown={event => {
        if (event.button !== 0) return;
        event.preventDefault(); cleanup.current?.();
        const start = event.clientX;
        const move = (pointer: PointerEvent) => setWidth(Math.max(48, Math.min(320, width + pointer.clientX - start)));
        const finish = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', finish); window.removeEventListener('pointercancel', finish); cleanup.current = null; };
        cleanup.current = finish; window.addEventListener('pointermove', move); window.addEventListener('pointerup', finish); window.addEventListener('pointercancel', finish);
      }} />
  </aside>;
}
