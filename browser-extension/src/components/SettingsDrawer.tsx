import { useEffect, useRef, useState } from 'react';
import { ArrowSquareOut, ArrowsClockwise, SignOut, X } from '@phosphor-icons/react';
import { syncBrowserAuth } from '../lib/auth';
import {
  clearAuth, DEFAULT_SERVER_ORIGIN, normalizeServerOrigin, requestServerPermission, setServerOrigin,
  type ExtensionSession,
} from '../lib/storage';
import { sendRuntimeMessage, UNIMIND_TOGGLE_TAB_AUDIO } from '../shared/bridge';

export const APPEARANCE_STORAGE_KEY = 'unimind:appearance';
type Appearance = 'system' | 'light' | 'dark';

export function SettingsDrawer({ session, onClose }: { session: ExtensionSession; onClose: () => void }) {
  const [origin, setOrigin] = useState(session.serverOrigin);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [audio, setAudio] = useState(false);
  const [appearance, setAppearance] = useState<Appearance>('system');
  const dialog = useRef<HTMLElement>(null);
  useEffect(() => {
    let mounted = true;
    void chrome.storage.local.get(APPEARANCE_STORAGE_KEY).then(values => {
      const value = values[APPEARANCE_STORAGE_KEY];
      if (mounted) setAppearance(value === 'light' || value === 'dark' ? value : 'system');
    }).catch(() => undefined);
    return () => { mounted = false; };
  }, []);
  useEffect(() => {
    const previousFocus = document.activeElement as HTMLElement | null;
    dialog.current?.querySelector<HTMLButtonElement>('button')?.focus();
    function keydown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose();
      if (event.key !== 'Tab') return;
      const focusable = dialog.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), a[href]');
      if (!focusable?.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    }
    document.addEventListener('keydown', keydown);
    return () => { document.removeEventListener('keydown', keydown); previousFocus?.focus(); };
  }, [onClose]);

  async function saveOrigin() {
    setError('');
    setMessage('');
    let normalized: string;
    try { normalized = normalizeServerOrigin(origin); }
    catch (failure) { setError(failure instanceof Error ? failure.message : '请输入有效网址。'); return; }
    // Request optional hosts while this handler still has the user's activation.
    const permission = requestServerPermission(normalized);
    setBusy(true);
    try {
      if (!await permission) throw new Error('请允许访问此服务地址，以连接你的 UniMind 账号。');
      await setServerOrigin(normalized);
      setOrigin(normalized);
      await syncBrowserAuth();
      setMessage('服务地址已保存。');
    } catch (failure) { setError(failure instanceof Error ? failure.message : '保存失败，请重试。'); }
    finally { setBusy(false); }
  }
  async function sync() {
    setBusy(true);
    setError('');
    try {
      const next = await syncBrowserAuth();
      setMessage(next.token ? '浏览器登录态已同步。' : '尚未找到浏览器登录态，可在侧栏直接登录。');
    } catch (failure) { setError(failure instanceof Error ? failure.message : '同步失败，请重试。'); }
    finally { setBusy(false); }
  }
  async function toggleAudio() {
    setError('');
    try {
      const result = await sendRuntimeMessage(UNIMIND_TOGGLE_TAB_AUDIO, { enabled: !audio });
      setAudio(result.enabled);
      if (result.error) setError(result.error);
    } catch { setError('暂时无法连接当前页面。'); }
  }
  async function changeAppearance(value: Appearance) {
    setError('');
    try {
      await chrome.storage.local.set({ [APPEARANCE_STORAGE_KEY]: value });
      setAppearance(value);
    } catch { setError('外观设置暂时无法保存，请重试。'); }
  }
  return <div className="drawer-overlay" onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}>
    <section ref={dialog} className="settings-drawer" role="dialog" aria-modal="true" aria-labelledby="settings-title">
      <header className="drawer-heading"><h2 id="settings-title">伴学设置</h2>
        <button type="button" className="icon-button" aria-label="关闭设置" onClick={onClose}><X size={19} /></button></header>
      <label className="field-label" htmlFor="server-origin">主站服务地址</label>
      <div className="server-presets">
        <button type="button" onClick={() => setOrigin(DEFAULT_SERVER_ORIGIN)}>线上主站 (unimind-ai.com)</button>
        <button type="button" onClick={() => setOrigin('http://localhost:8000')}>本地 8000</button>
        <button type="button" onClick={() => setOrigin('http://localhost:5173')}>本地 5173</button>
      </div>
      <form onSubmit={event => { event.preventDefault(); void saveOrigin(); }}>
        <input id="server-origin" type="text" inputMode="url" required placeholder="https://unimind-ai.com" value={origin} onChange={event => setOrigin(event.target.value)} disabled={busy} />
        <button type="submit" className="primary-button settings-save" disabled={busy}>{busy ? '连接中…' : '保存并连接'}</button>
      </form>
      <div className="settings-section">
        <label className="appearance-row" htmlFor="appearance">外观
          <select id="appearance" value={appearance} onChange={event => void changeAppearance(event.target.value as Appearance)}>
            <option value="system">跟随系统</option><option value="light">浅色</option><option value="dark">深色</option>
          </select>
        </label>
      </div>
      <div className="settings-section">
        <h3>账号</h3>
        <p className="muted">{session.token ? String(session.user?.nickname || session.user?.username || session.user?.email || '已登录 UniMind') : '登录后即可接续主站的学习记录。'}</p>
        <button type="button" className="secondary-button" onClick={() => void sync()} disabled={busy}><ArrowsClockwise size={16} />同步浏览器登录态</button>
        <a className="secondary-button" href={`${session.serverOrigin}/login`} target="_blank" rel="noopener noreferrer"><ArrowSquareOut size={16} />打开 UniMind 主站登录</a>
        {session.token && <button type="button" className="text-button logout-button" onClick={() => {
          void clearAuth().then(onClose).catch(failure => setError(failure instanceof Error ? failure.message : '退出失败，请重试。'));
        }}><SignOut size={16} />退出插件账号</button>}
      </div>
      <div className="settings-section">
        <h3>实时听课</h3>
        <p className="muted">用于没有字幕的视频，由你主动开启。</p>
        <button type="button" className="secondary-button" onClick={() => void toggleAudio()}>{audio ? '停止实时听课录音' : '开启实时听课录音'}</button>
      </div>
      {message && <p className="inline-success" role="status">{message}</p>}
      {error && <p className="inline-error" role="alert">{error}</p>}
    </section>
  </div>;
}
