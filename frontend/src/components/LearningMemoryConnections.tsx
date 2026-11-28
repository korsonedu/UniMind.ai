import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Check, Copy } from '@phosphor-icons/react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { ExternalMcpServers } from '@/components/ExternalMcpServers';
import { t } from '@/i18n';
import api from '@/lib/api';
import { activeWorkspace } from '@/lib/activeWorkspace';
import { getServerOrigin } from '@/lib/serverConfig';

type Connection = { id: number; name: string; can_write: boolean; share_notes: boolean; project_name: string | null };
type IssuedCredential = { name: string; token: string };

async function copyText(value: string): Promise<boolean> {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(value);
      return true;
    } catch {
      // Fallback below for restricted clipboard contexts.
    }
  }
  const textarea = document.createElement('textarea');
  textarea.value = value;
  textarea.setAttribute('readonly', '');
  textarea.style.position = 'fixed';
  textarea.style.opacity = '0';
  document.body.appendChild(textarea);
  textarea.select();
  const ok = document.execCommand('copy');
  document.body.removeChild(textarea);
  return ok;
}

export function LearningMemoryConnections() {
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState('');
  const [canWrite, setCanWrite] = useState(false);
  const [shareNotes, setShareNotes] = useState(false);
  const [issuedCredential, setIssuedCredential] = useState<IssuedCredential | null>(null);
  const [copiedField, setCopiedField] = useState<'token' | 'endpoint' | null>(null);
  const [error, setError] = useState(false);
  const url = '/ai/learning-memory/grants/';
  const connections = useQuery({
    queryKey: ['learning-memory-connections', activeWorkspace()],
    queryFn: ({ signal }) => api.get<Connection[]>(url, { signal }).then(response => response.data),
  });
  const server = getServerOrigin() || window.location.origin;
  const endpoint = new URL('/api/ai/learning-memory/mcp/', server).href;
  const stdioProxyCommand = `npx -y @unimind/mcp-proxy --url ${endpoint}`;

  async function handleCopy(field: 'token' | 'endpoint', value: string) {
    const ok = await copyText(value);
    if (ok) {
      setCopiedField(field);
      toast.success(field === 'token' ? t('已复制 Bearer 凭证') : t('已复制 MCP 地址'));
      window.setTimeout(() => {
        setCopiedField(current => (current === field ? null : current));
      }, 2000);
    } else {
      toast.error(t('复制失败，请手动选中复制。'));
    }
  }

  async function create() {
    setBusy(true);
    setError(false);
    const createdName = name.trim();
    try {
      const response = await api.post<{ token: string }>(url, { name: createdName, can_write: canWrite, share_notes: shareNotes });
      setIssuedCredential({ name: createdName, token: response.data.token });
      setCopiedField(null);
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
      void connections.refetch();
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  }

  return <>
    <h3 className="um-settings-group-title um-mcp-first-title">{t('向外部 Agent 开放学习记忆（MCP Server）')}</h3>
    <section className="um-settings-group">
      <form onSubmit={event => { event.preventDefault(); if (!busy && name.trim()) void create(); }}>
        <div className="um-settings-row">
          <div><label htmlFor="learning-memory-endpoint">{t('MCP 地址')}</label></div>
          <Input id="learning-memory-endpoint" readOnly value={endpoint} onFocus={event => event.currentTarget.select()} />
        </div>
        <div className="um-settings-row">
          <div>
            <label htmlFor="learning-memory-stdio-proxy">{t('本地 stdio 代理命令')}</label>
            <p>{t('供 Claude Desktop、Raycast、Obsidian 等仅支持 stdio 的桌面客户端使用')}</p>
          </div>
          <Input id="learning-memory-stdio-proxy" readOnly value={stdioProxyCommand} onFocus={event => event.currentTarget.select()} />
        </div>
        <div className="um-settings-row">
          <div><label htmlFor="learning-memory-connection-name">{t('连接名称')}</label></div>
          <Input id="learning-memory-connection-name" required maxLength={80} placeholder="Codex / Claude / Cursor / WorkBuddy" value={name}
            onChange={event => setName(event.target.value)} />
        </div>
        <div className="um-settings-row">
          <div><label htmlFor="learning-memory-notes">{t('共享学习笔记')}</label></div>
          <Switch id="learning-memory-notes" checked={shareNotes} onCheckedChange={setShareNotes} />
        </div>
        <div className="um-settings-row">
          <div><label htmlFor="learning-memory-write">{t('允许外部 Agent 写入学习记录')}</label></div>
          <Switch id="learning-memory-write" checked={canWrite} onCheckedChange={setCanWrite} />
        </div>
        <div className="um-settings-row um-mcp-submit-row">
          <Button type="submit" disabled={busy || !name.trim()}>{t('创建连接凭证')}</Button>
        </div>
      </form>
    </section>
    {(error || connections.isError) && <p className="um-desktop-error um-mcp-error" role="alert">{t('连接操作未完成，请重试。')}</p>}
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
    <ExternalMcpServers />

    <Dialog
      open={!!issuedCredential}
      onOpenChange={open => {
        if (!open) {
          setIssuedCredential(null);
          setCopiedField(null);
        }
      }}
    >
      <DialogContent
        className="um-settings-edit-dialog um-mcp-token-dialog"
        onInteractOutside={event => event.preventDefault()}
      >
        <DialogHeader>
          <DialogTitle>{t('连接凭证已创建')}</DialogTitle>
          <DialogDescription>
            {t('此 Bearer 凭证仅显示这一次，关闭后将无法再次查看，请先复制并妥善保存。')}
          </DialogDescription>
        </DialogHeader>
        {issuedCredential && <div className="um-mcp-token-body">
          <div className="um-mcp-token-field">
            <label htmlFor="learning-memory-token-modal">
              {t('Bearer 凭证')} · {issuedCredential.name}
            </label>
            <div className="um-mcp-copy-row">
              <Input
                id="learning-memory-token-modal"
                className="font-mono"
                readOnly
                value={issuedCredential.token}
                onFocus={event => event.currentTarget.select()}
              />
              <Button
                type="button"
                variant="outline"
                onClick={() => void handleCopy('token', issuedCredential.token)}
              >
                {copiedField === 'token' ? <Check size={16} aria-hidden="true" /> : <Copy size={16} aria-hidden="true" />}
                {copiedField === 'token' ? t('已复制') : t('复制')}
              </Button>
            </div>
          </div>
          <div className="um-mcp-token-field">
            <label htmlFor="learning-memory-endpoint-modal">{t('MCP 地址')}</label>
            <div className="um-mcp-copy-row">
              <Input
                id="learning-memory-endpoint-modal"
                className="font-mono"
                readOnly
                value={endpoint}
                onFocus={event => event.currentTarget.select()}
              />
              <Button
                type="button"
                variant="outline"
                onClick={() => void handleCopy('endpoint', endpoint)}
              >
                {copiedField === 'endpoint' ? <Check size={16} aria-hidden="true" /> : <Copy size={16} aria-hidden="true" />}
                {copiedField === 'endpoint' ? t('已复制') : t('复制')}
              </Button>
            </div>
          </div>
        </div>}
        <footer className="um-settings-footer">
          <Button
            type="button"
            onClick={() => {
              setIssuedCredential(null);
              setCopiedField(null);
            }}
          >
            {t('我已保存，关闭')}
          </Button>
        </footer>
      </DialogContent>
    </Dialog>
  </>;
}
