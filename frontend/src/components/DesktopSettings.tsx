import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { useDesktopStore, type DesktopState } from '@/lib/desktop';

export function DesktopSettings() {
  const { state, error } = useDesktopStore();
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState('');
  const desktop = window.unimindDesktop;
  if (!desktop) return null;
  const run = async (key: string, action: () => Promise<DesktopState | void>) => {
    if (busy) return;
    setBusy(key); setActionError('');
    try { const next = await action(); if (next) useDesktopStore.setState({ state: next, error: null }); }
    catch (failure) { setActionError(String(failure instanceof Error ? failure.message : failure)); }
    finally { setBusy(null); }
  };
  if (!state) return <div className="um-settings-empty"><p role="status">{error || '正在读取桌面设置…'}</p>{error && <Button variant="outline" disabled={!!busy} onClick={() => void run('sync', desktop.syncIdentity)}>重试</Button>}</div>;
  const updateLabels = { unconfigured: '发布源未配置', idle: '可以检查更新', checking: '正在检查更新…', available: '发现新版本', downloading: '正在下载更新…', downloaded: '更新已准备好', error: '更新检查失败' };
  const usedBytes = state.storage?.usedBytes ?? 0;
  const storageLabel = usedBytes >= 1024 ** 3 ? `${(usedBytes / 1024 ** 3).toFixed(1)} GB` : `${(usedBytes / 1024 ** 2).toFixed(1)} MB`;
  const focusLabel = state.focus ? `${Math.floor(state.focus.remaining / 60)}:${String(state.focus.remaining % 60).padStart(2, '0')}` : '';
  return <>
    {(actionError || error) && <p className="um-desktop-error" role="alert">{actionError || error}</p>}
    <h3 className="um-settings-group-title">桌面体验</h3>
    <section className="um-settings-group">
      <div className="um-settings-row"><div><label htmlFor="desktop-notifications">系统通知</label><p>在后台收到新消息或小宇完成回复时提醒你。需允许系统通知。</p></div><Switch id="desktop-notifications" checked={state.preferences.notifications} disabled={!!busy} onCheckedChange={notifications => void run('notifications', () => desktop.updatePreferences({ notifications }))} /></div>
      <div className="um-settings-row"><div><label htmlFor="desktop-background">关闭窗口后继续运行</label><p>在菜单栏或托盘保留 UniMind，继续下载课程并接收提醒。退出应用可使用菜单中的“退出”。</p></div><Switch id="desktop-background" checked={state.preferences.keepRunning} disabled={!!busy} onCheckedChange={keepRunning => void run('background', () => desktop.updatePreferences({ keepRunning }))} /></div>
      {state.preferences.launchAtLogin !== undefined && <div className="um-settings-row"><div><label htmlFor="desktop-launch-at-login">开机自启</label><p>登录系统后自动启动 UniMind，保持下载和提醒可用。</p></div><Switch id="desktop-launch-at-login" checked={state.preferences.launchAtLogin} disabled={!!busy} onCheckedChange={launchAtLogin => void run('launch-at-login', () => desktop.updatePreferences({ launchAtLogin }))} /></div>}
      {state.preferences.quickEntry !== undefined && <div className="um-settings-row"><div><label htmlFor="desktop-quick-entry">全局快捷键</label><p>{state.platform === 'darwin' ? '⌘⇧U 打开 UniMind；⌘⇧N 新建笔记。' : 'Ctrl+Shift+U 打开 UniMind；Ctrl+Shift+N 新建笔记。'}关闭后不再注册。</p></div><Switch id="desktop-quick-entry" checked={state.preferences.quickEntry} disabled={!!busy} onCheckedChange={quickEntry => void run('quick-entry', () => desktop.updatePreferences({ quickEntry }))} /></div>}
      <div className="um-settings-row"><div><span>键盘快捷键</span><p>{state.platform === 'darwin' ? '⌘' : 'Ctrl'}+, 打开设置；{state.platform === 'darwin' ? '⌘' : 'Ctrl'}+1 小宇；+2 课程；+3 笔记。完整快捷键见应用菜单。</p></div></div>
      {state.focus && <div className="um-settings-row"><div><span>菜单栏专注</span><p>{state.focus.status === 'running' ? `专注中 ${focusLabel}` : state.focus.status === 'paused' ? `已暂停 ${focusLabel}` : '未开始'}。可在菜单栏或应用菜单开始 25 分钟专注。</p></div></div>}
    </section>
    <h3 className="um-settings-group-title">离线课程</h3>
    <section className="um-settings-group">
      <div className="um-settings-row"><div><span>已下载的课程</span><p>离线授权最多保留 24 小时，播放位置保存在本机，联网后同步学习记录。退出账号会清除缓存和未同步记录，请先联网同步。</p></div><Button variant="outline" disabled={!!busy} onClick={() => void run('library', desktop.openOfflineLibrary)}>打开离线课程库</Button></div>
      {state.storage && <div className="um-settings-row"><div><span>本机课程缓存</span><p>已占用 {storageLabel}，包含已完成的视频和可继续下载的分片。移除课程可释放空间。</p></div></div>}
      {state.learningSync && <div className="um-settings-row"><div><span>学习记录同步</span><p role="status">{state.learningSync.pending ? `${state.learningSync.pending} 条记录等待同步，联网后会继续。` : '暂无待同步记录。'}{state.learningSync.rejected > 0 && ` ${state.learningSync.rejected} 条记录因课程权限或授权变化未计入账户。`}</p>{state.learningSync.error && <p>{state.learningSync.error}</p>}</div><Button variant="outline" disabled={!!busy} onClick={() => void run('sync-learning', desktop.syncIdentity)}>重新同步</Button></div>}
      {!state.downloads.length && <div className="um-settings-row"><p>暂无下载。前往课程中心选择要离线观看的课程。</p></div>}
      {state.downloads.map(course => <div className="um-settings-row um-desktop-download" key={course.courseId}>
        <div><strong>{course.title}</strong><p>{course.status === 'downloading' || course.status === 'paused' ? `${course.status === 'paused' ? '已暂停，可继续下载' : '正在下载'} · ${Math.min(100, Math.floor(course.receivedBytes / Math.max(1, course.totalBytes) * 100))}%` : course.status === 'failed' ? course.error || '下载失败，请重试' : `可离线观看${course.expiresAt ? ` · 有效至 ${new Date(course.expiresAt).toLocaleString()}` : ''}`}</p>{course.status === 'downloading' && <progress aria-label={`${course.title}下载进度`} max={course.totalBytes || 1} value={course.receivedBytes} />}</div>
        <div className="um-desktop-actions">
          {course.status === 'ready' && <Button variant="outline" disabled={!!busy} onClick={() => void run(`play-${course.courseId}`, () => desktop.openOfflineCourse(course.courseId))}>播放</Button>}
          {course.status === 'downloading' && desktop.pauseDownload && <Button variant="outline" disabled={!!busy} onClick={() => void run(`pause-${course.courseId}`, () => desktop.pauseDownload!(course.courseId))}>暂停</Button>}
          {(course.status === 'failed' || course.status === 'paused') && <Button variant="outline" disabled={!!busy} onClick={() => void run(`retry-${course.courseId}`, () => desktop.downloadCourse(course.courseId))}>{course.status === 'paused' ? '继续下载' : '重试'}</Button>}
          <Button variant="ghost" disabled={!!busy} onClick={() => void run(`remove-${course.courseId}`, () => desktop.removeDownload(course.courseId))}>{course.status === 'downloading' ? '取消并移除' : '移除'}</Button>
        </div>
      </div>)}
    </section>
    <h3 className="um-settings-group-title">版本与更新</h3>
    <section className="um-settings-group"><div className="um-settings-row"><div><span>UniMind {state.version}</span><p>{updateLabels[state.update.status]}{state.update.version ? ` · ${state.update.version}` : ''}</p>{state.update.error && <p>{state.update.error}</p>}</div>{state.update.status === 'downloaded' ? <Button disabled={!!busy} onClick={() => void run('install', desktop.installUpdate)}>重启并更新</Button> : <Button variant="outline" disabled={!!busy || ['unconfigured', 'checking', 'available', 'downloading'].includes(state.update.status)} onClick={() => void run('update', desktop.checkForUpdates)}>检查更新</Button>}</div></section>
  </>;
}
