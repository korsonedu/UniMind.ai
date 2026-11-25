import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { t } from '@/i18n';
import api from '@/lib/api';
import { activeWorkspace } from '@/lib/activeWorkspace';
import { getServerOrigin } from '@/lib/serverConfig';

type Connection = { id: number; name: string; can_write: boolean; share_notes: boolean; project_name: string | null };

export function LearningMemoryConnections() {
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState('');
  const [canWrite, setCanWrite] = useState(false);
  const [shareNotes, setShareNotes] = useState(false);
  const [token, setToken] = useState('');
  const [error, setError] = useState(false);
  const url = '/ai/learning-memory/grants/';
  const connections = useQuery({
    queryKey: ['learning-memory-connections', activeWorkspace()],
    queryFn: ({ signal }) => api.get<Connection[]>(url, { signal }).then(response => response.data),
  });
  const server = getServerOrigin() || window.location.origin;
  const endpoint = new URL('/api/ai/learning-memory/mcp/', server).href;

  async function create() {
    setBusy(true);
    setError(false);
    setToken('');
    try {
      const response = await api.post<{ token: string }>(url, { name, can_write: canWrite, share_notes: shareNotes });
      setToken(response.data.token);
      setName('');
      setCanWrite(false);
      setShareNotes(false);
      void connections.refetch();
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  }

  async function revoke(id: number) {
    setBusy(true);
    setError(false);
    try {
      await api.delete(`${url}${id}/`);
      setToken('');
      void connections.refetch();
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  }

  return <>
    <section className="um-settings-group">
      <form onSubmit={event => { event.preventDefault(); if (!busy && name.trim()) void create(); }}>
        <div className="um-settings-row">
          <label htmlFor="learning-memory-endpoint">{t('MCP 地址')}</label>
          <Input id="learning-memory-endpoint" readOnly value={endpoint} onFocus={event => event.currentTarget.select()} />
        </div>
        <div className="um-settings-row">
          <label htmlFor="learning-memory-connection-name">{t('连接名称')}</label>
          <Input id="learning-memory-connection-name" required maxLength={80} placeholder="Codex / WorkBuddy" value={name}
            onChange={event => setName(event.target.value)} />
        </div>
        <div className="um-settings-row">
          <label htmlFor="learning-memory-notes">{t('共享学习笔记')}</label>
          <Switch id="learning-memory-notes" checked={shareNotes} onCheckedChange={setShareNotes} />
        </div>
        <div className="um-settings-row">
          <label htmlFor="learning-memory-write">{t('允许外部 Agent 写入学习记录')}</label>
          <Switch id="learning-memory-write" checked={canWrite} onCheckedChange={setCanWrite} />
        </div>
        <div className="um-settings-row">
          <Button type="submit" disabled={busy || !name.trim()}>{t('创建连接凭证')}</Button>
        </div>
      </form>
      {token && <div className="um-settings-row border-t">
        <label htmlFor="learning-memory-token">{t('Bearer 凭证，只显示一次')}</label>
        <Input id="learning-memory-token" readOnly value={token} onFocus={event => event.currentTarget.select()} />
      </div>}
    </section>
    {(error || connections.isError) && <p role="alert">{t('连接操作未完成，请重试。')}</p>}
    {!!connections.data?.length && <>
      <h3 className="um-settings-group-title">{t('已授权连接')}</h3>
      <section className="um-settings-group">
        {connections.data.map(connection => <div className="um-settings-row" key={connection.id}>
          <div><strong>{connection.name}</strong><p>{connection.can_write ? t('读写') : t('只读')}
            {connection.share_notes ? ` · ${t('含笔记')}` : ''}
            {connection.project_name ? ` · ${connection.project_name}` : ''}</p></div>
          <Button type="button" variant="outline" disabled={busy} onClick={() => void revoke(connection.id)}>{t('断开连接')}</Button>
        </div>)}
      </section>
    </>}
  </>;
}
