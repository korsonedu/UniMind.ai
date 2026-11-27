import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { SelectField, SelectOption } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { t } from '@/i18n';
import api from '@/lib/api';
import { activeWorkspace } from '@/lib/activeWorkspace';

type ToolSummary = {
  name: string;
  namespaced_name: string;
  description: string;
  read_only: boolean;
};

type ExternalMcpServer = {
  id: number;
  name: string;
  slug: string;
  url: string;
  auth_type: 'none' | 'bearer' | 'header';
  auth_header_name: string;
  has_secret: boolean;
  enabled: boolean;
  allow_write_tools: boolean;
  tool_count: number;
  tools: ToolSummary[];
  last_synced_at: string | null;
  last_error: string;
};

type McpPreset = {
  id: string;
  name: string;
  category: string;
  url: string;
  auth_type: 'none' | 'bearer' | 'header';
  description: string;
};

type ServersResponse = {
  servers: ExternalMcpServer[];
  presets: McpPreset[];
};

export function ExternalMcpServers() {
  const [busy, setBusy] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [authType, setAuthType] = useState<'none' | 'bearer' | 'header'>('bearer');
  const [authHeaderName, setAuthHeaderName] = useState('Authorization');
  const [authSecret, setAuthSecret] = useState('');
  const [allowWrite, setAllowWrite] = useState(false);
  const [selectedPreset, setSelectedPreset] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState('');

  const endpoint = '/ai/mcp-servers/';
  const query = useQuery({
    queryKey: ['external-mcp-servers', activeWorkspace()],
    queryFn: ({ signal }) => api.get<ServersResponse>(endpoint, { signal }).then(res => res.data),
  });

  function applyPreset(preset: McpPreset) {
    setSelectedPreset(preset.id);
    setName(preset.id === 'custom' ? '' : preset.name);
    setUrl(preset.url || '');
    setAuthType(preset.auth_type || 'bearer');
    setAuthHeaderName('Authorization');
    setErrorMessage('');
  }

  async function handleCreate(event: React.FormEvent) {
    event.preventDefault();
    if (busy || !name.trim() || !url.trim()) return;
    setBusy('create');
    setErrorMessage('');
    try {
      await api.post<ExternalMcpServer>(endpoint, {
        name: name.trim(),
        url: url.trim(),
        auth_type: authType,
        auth_header_name: authType === 'header' ? authHeaderName.trim() : 'Authorization',
        auth_secret: authType === 'none' ? '' : authSecret.trim(),
        allow_write_tools: allowWrite,
      });
      setName('');
      setUrl('');
      setAuthSecret('');
      setAllowWrite(false);
      await query.refetch();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string; url?: string[] } } })?.response?.data;
      setErrorMessage(detail?.detail || detail?.url?.[0] || t('外部工具连接保存失败，请检查地址与凭证。'));
    } finally {
      setBusy(null);
    }
  }

  async function handleSync(id: number) {
    setBusy(`sync-${id}`);
    setErrorMessage('');
    try {
      await api.post(`${endpoint}${id}/sync/`);
      await query.refetch();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setErrorMessage(detail || t('同步外部 MCP 工具失败，请检查服务是否可达。'));
      await query.refetch();
    } finally {
      setBusy(null);
    }
  }

  async function handleToggle(server: ExternalMcpServer, field: 'enabled' | 'allow_write_tools', value: boolean) {
    setBusy(`toggle-${server.id}`);
    setErrorMessage('');
    try {
      await api.patch(`${endpoint}${server.id}/`, { [field]: value });
      await query.refetch();
    } catch {
      setErrorMessage(t('连接操作未完成，请重试。'));
    } finally {
      setBusy(null);
    }
  }

  async function handleDelete(id: number) {
    setBusy(`delete-${id}`);
    setErrorMessage('');
    try {
      await api.delete(`${endpoint}${id}/`);
      await query.refetch();
    } catch {
      setErrorMessage(t('连接操作未完成，请重试。'));
    } finally {
      setBusy(null);
    }
  }

  const presets = query.data?.presets || [];
  const servers = query.data?.servers || [];

  return <>
    <h3 className="um-settings-group-title">{t('让小宇接入外部工具（MCP Client）')}</h3>
    <p className="um-settings-description">
      {t('添加符合 Streamable HTTP 规范的远程 MCP 服务后，小宇可在对话中按需检索 Notion、Obsidian、GitHub、网盘、Zotero、飞书或 Anki 等外部资料。默认仅开放只读工具。')}
    </p>
    <section className="um-settings-group">
      {presets.length > 0 && <div className="um-settings-row um-mcp-presets-row">
        <div>
          <span>{t('常用预设')}</span>
          <p>{t('点击填充推荐配置，再补充你的服务地址或令牌')}</p>
        </div>
        <div className="um-mcp-presets">
          {presets.map(preset => (
            <Button
              key={preset.id}
              type="button"
              variant={selectedPreset === preset.id ? 'default' : 'outline'}
              size="sm"
              onClick={() => applyPreset(preset)}
            >
              {preset.name}
            </Button>
          ))}
        </div>
      </div>}
      <form onSubmit={event => void handleCreate(event)}>
        <div className="um-settings-row">
          <div><label htmlFor="ext-mcp-name">{t('工具名称')}</label></div>
          <Input id="ext-mcp-name" required maxLength={80} placeholder="Notion / Obsidian / GitHub" value={name}
            onChange={event => { setName(event.target.value); setSelectedPreset(null); }} />
        </div>
        <div className="um-settings-row">
          <div><label htmlFor="ext-mcp-url">{t('远程 MCP 地址')}</label></div>
          <Input id="ext-mcp-url" required maxLength={500} placeholder="https://mcp.notion.com/mcp" value={url}
            onChange={event => setUrl(event.target.value)} />
        </div>
        <div className="um-settings-row">
          <div><label htmlFor="ext-mcp-auth-type">{t('认证方式')}</label></div>
          <SelectField className="um-mcp-select" id="ext-mcp-auth-type" value={authType} onValueChange={v => setAuthType(v as 'none' | 'bearer' | 'header')}>
            <SelectOption value="bearer">Bearer Token</SelectOption>
            <SelectOption value="header">{t('自定义请求头')}</SelectOption>
            <SelectOption value="none">{t('无认证')}</SelectOption>
          </SelectField>
        </div>
        {authType === 'header' && <div className="um-settings-row">
          <div><label htmlFor="ext-mcp-header-name">{t('请求头名称')}</label></div>
          <Input id="ext-mcp-header-name" maxLength={80} placeholder="X-API-Key" value={authHeaderName}
            onChange={event => setAuthHeaderName(event.target.value)} />
        </div>}
        {authType !== 'none' && <div className="um-settings-row">
          <div><label htmlFor="ext-mcp-secret">{t('访问令牌（加密存储）')}</label></div>
          <Input id="ext-mcp-secret" type="password" maxLength={2000} placeholder="secret_..." value={authSecret}
            onChange={event => setAuthSecret(event.target.value)} autoComplete="off" />
        </div>}
        <div className="um-settings-row">
          <div>
            <label htmlFor="ext-mcp-write">{t('允许调用外部写入工具')}</label>
            <p>{t('关闭时小宇只能调用外部服务的只读检索工具')}</p>
          </div>
          <Switch id="ext-mcp-write" checked={allowWrite} onCheckedChange={setAllowWrite} />
        </div>
        <div className="um-settings-row um-mcp-submit-row">
          <Button type="submit" disabled={!!busy || !name.trim() || !url.trim()}>{t('添加外部 MCP 工具')}</Button>
        </div>
      </form>
    </section>

    {errorMessage && <p className="um-desktop-error um-mcp-error" role="alert">{errorMessage}</p>}

    {servers.length > 0 && <>
      <h3 className="um-settings-group-title">{t('已连接的外部 MCP 工具')}</h3>
      <section className="um-settings-group">
        {servers.map(server => (
          <div className="um-settings-row um-mcp-server-row" key={server.id}>
            <div>
              <strong>{server.name}</strong>
              <p className="um-mcp-server-url">{server.url}</p>
              <p>
                {server.enabled ? t('已启用') : t('已停用')}
                {' · '}
                {server.allow_write_tools ? t('读写') : t('只读')}
                {' · '}
                {t('已同步工具：')}{server.tool_count}
                {server.last_error ? ` · ${server.last_error}` : ''}
              </p>
            </div>
            <div className="um-mcp-server-actions">
              <Switch
                aria-label={`${server.name} ${t('启用开关')}`}
                checked={server.enabled}
                disabled={!!busy}
                onCheckedChange={checked => void handleToggle(server, 'enabled', checked)}
              />
              <Button type="button" variant="outline" size="sm" disabled={!!busy} onClick={() => void handleSync(server.id)}>
                {busy === `sync-${server.id}` ? t('同步中…') : t('同步工具')}
              </Button>
              <Button type="button" variant="outline" size="sm" disabled={!!busy} onClick={() => void handleDelete(server.id)}>
                {t('移除')}
              </Button>
            </div>
          </div>
        ))}
      </section>
    </>}
  </>;
}
