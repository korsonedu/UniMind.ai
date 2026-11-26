import { getLocale, t, useLocale } from '@/i18n';
import { SelectField, SelectOption } from '@/components/ui/select';
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { useDesktopStore, type DesktopState } from '@/lib/desktop';
import { getApiBaseUrl } from '@/lib/serverConfig';

type WebsiteUpdate = { version: string; prerelease: boolean; url?: string };

export function DesktopSettings({ section = 'all' }: { section?: 'all' | 'general' | 'notifications' | 'storage' | 'updates' | 'shortcuts' }) {
  useLocale();
  const { state, error } = useDesktopStore();
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState('');
  const [websiteResult, setWebsiteResult] = useState<WebsiteUpdate | 'current' | null>(null);
  const desktop = window.unimindDesktop;
  if (!desktop) return null;
  const run = async (key: string, action: () => Promise<DesktopState | void>) => {
    if (busy) return;
    setBusy(key); setActionError('');
    try { const next = await action(); if (next) useDesktopStore.setState({ state: next, error: null }); }
    catch (failure) { setActionError(String(failure instanceof Error ? failure.message : failure)); }
    finally { setBusy(null); }
  };
  if (!state) return <div className="um-settings-empty"><p role="status">{error ? t(error) : t('正在读取桌面设置…')}</p>{error && <Button variant="outline" disabled={!!busy} onClick={() => void run('sync', desktop.syncIdentity)}>{t('重试')}</Button>}</div>;
  const updateLabels = { unconfigured: t('发布源未配置'), idle: t('可以检查更新'), checking: t('正在检查更新…'), available: t('发现新版本'), downloading: t('正在下载更新…'), downloaded: t('更新已准备好'), error: t('更新检查失败') };
  const checkWebsite = state.update.status === 'unconfigured';
  const websiteUpdate = checkWebsite && typeof websiteResult === 'object' ? websiteResult : null;
  const checkForUpdates = async () => {
    if (!checkWebsite) return desktop.checkForUpdates();
    setWebsiteResult(null);
    try {
      const response = await fetch(`${getApiBaseUrl()}/desktop-release/`, { cache: 'no-store' });
      if (!response.ok) throw new Error();
      const release: { version: string; prerelease: boolean; packages: { mac?: string; windows?: string } } = await response.json();
      const installed = state.version.match(/^(\d+\.\d+\.\d+)(-[\w.-]+)?(?:\+[\w.-]+)?$/);
      if (!installed || !/^\d+\.\d+\.\d+$/.test(release.version)) throw new Error();
      const order = release.version.localeCompare(installed[1], 'en', { numeric: true });
      if (order < 0 || (order === 0 && !installed[2])) {
        setWebsiteResult('current');
        return;
      }
      const url = state.platform === 'darwin' ? release.packages.mac : state.platform === 'win32' ? release.packages.windows : undefined;
      setWebsiteResult({ version: release.version, prerelease: release.prerelease, url });
    } catch {
      throw new Error('更新检查失败');
    }
  };
  const usedBytes = state.storage?.usedBytes ?? 0;
  const storageLabel = usedBytes >= 1024 ** 3 ? `${(usedBytes / 1024 ** 3).toFixed(1)} GB` : `${(usedBytes / 1024 ** 2).toFixed(1)} MB`;
  const focusLabel = state.focus ? `${Math.floor(state.focus.remaining / 60)}:${String(state.focus.remaining % 60).padStart(2, '0')}` : '';
  return <>
    {(actionError || error) && <p className="um-desktop-error" role="alert">{t(actionError || error || '')}</p>}
    {(section === 'all' || section === 'notifications') && <>
    <h3 className="um-settings-group-title">{t('通知')}</h3>
    <section className="um-settings-group">
      <div className="um-settings-row"><div><label htmlFor="desktop-notifications">{t('接收系统通知')}</label></div><Switch id="desktop-notifications" aria-controls="desktop-notification-types" checked={state.preferences.notifications} disabled={!!busy} onCheckedChange={notifications => void run('notifications', () => desktop.updatePreferences({ notifications }))} /></div>
      <fieldset id="desktop-notification-types" aria-label={t('通知内容')} className="um-desktop-notification-types" hidden={!state.preferences.notifications} disabled={!!busy || !state.preferences.notifications}>
        {state.preferences.notifyChat !== undefined && <div className="um-settings-row"><div><label htmlFor="desktop-notify-chat">{t('小宇回复完成')}</label></div><Switch id="desktop-notify-chat" checked={state.preferences.notifyChat} disabled={!!busy || !state.preferences.notifications} onCheckedChange={notifyChat => void run('notify-chat', () => desktop.updatePreferences({ notifyChat }))} /></div>}
        {state.preferences.notifyQA !== undefined && <div className="um-settings-row"><div><label htmlFor="desktop-notify-qa">{t('答疑回复')}</label></div><Switch id="desktop-notify-qa" checked={state.preferences.notifyQA} disabled={!!busy || !state.preferences.notifications} onCheckedChange={notifyQA => void run('notify-qa', () => desktop.updatePreferences({ notifyQA }))} /></div>}
        {state.preferences.notifyLearning !== undefined && <div className="um-settings-row"><div><label htmlFor="desktop-notify-learning">{t('学习与系统消息')}</label></div><Switch id="desktop-notify-learning" checked={state.preferences.notifyLearning} disabled={!!busy || !state.preferences.notifications} onCheckedChange={notifyLearning => void run('notify-learning', () => desktop.updatePreferences({ notifyLearning }))} /></div>}
      </fieldset>
    </section>
    </>}
    {(section === 'all' || section === 'general') && <>
    <h3 className="um-settings-group-title">{t('启动与后台运行')}</h3>
    <section className="um-settings-group">
      {state.preferences.startupPage !== undefined && <div className="um-settings-row"><div><label htmlFor="desktop-startup-page">{t('启动时打开')}</label></div><SelectField id="desktop-startup-page" value={state.preferences.startupPage} disabled={!!busy} onValueChange={value => void run('startup-page', () => desktop.updatePreferences({ startupPage: value as DesktopState['preferences']['startupPage'] }))}><SelectOption value="/xiaoyu">{t('小宇')}</SelectOption><SelectOption value="/courses">{t('课程中心')}</SelectOption><SelectOption value="/notes">{t('笔记')}</SelectOption></SelectField></div>}
      <div className="um-settings-row"><div><label htmlFor="desktop-background">{t('关闭窗口后继续运行')}</label></div><Switch id="desktop-background" checked={state.preferences.keepRunning} disabled={!!busy} onCheckedChange={keepRunning => void run('background', () => desktop.updatePreferences({ keepRunning }))} /></div>
      {state.preferences.launchAtLogin !== undefined && <div className="um-settings-row"><div><label htmlFor="desktop-launch-at-login">{t('开机自启')}</label></div><Switch id="desktop-launch-at-login" checked={state.preferences.launchAtLogin} disabled={!!busy} onCheckedChange={launchAtLogin => void run('launch-at-login', () => desktop.updatePreferences({ launchAtLogin }))} /></div>}
    </section>
    <h3 className="um-settings-group-title">{t('专注计时')}</h3>
    <section className="um-settings-group">
      {state.preferences.focusMinutes !== undefined && <div className="um-settings-row"><div><label htmlFor="desktop-focus-minutes">{t('每轮专注时长')}</label></div><SelectField id="desktop-focus-minutes" value={state.preferences.focusMinutes} disabled={!!busy} onValueChange={value => void run('focus-minutes', () => desktop.updatePreferences({ focusMinutes: Number(value) }))}>{[15, 25, 45, 60].map(minutes => <SelectOption key={minutes} value={minutes}>{minutes} {t('分钟')}</SelectOption>)}</SelectField></div>}
      {state.focus && <div className="um-settings-row"><div><span>{t('菜单栏专注')}</span><p>{state.focus.status === 'running' ? t('专注中 {0}', { 0: focusLabel }) : state.focus.status === 'paused' ? t('已暂停 {0}', { 0: focusLabel }) : t('未开始')}</p></div></div>}
    </section>
    </>}
    {(section === 'all' || section === 'shortcuts') && <>
    <h3 className="um-settings-group-title">{t('全局快捷键')}</h3><section className="um-settings-group">
      {state.preferences.quickEntry !== undefined && <div className="um-settings-row"><div><label htmlFor="desktop-quick-entry">{t('全局快捷键')}</label></div><Switch id="desktop-quick-entry" checked={state.preferences.quickEntry} disabled={!!busy} onCheckedChange={quickEntry => void run('quick-entry', () => desktop.updatePreferences({ quickEntry }))} /></div>}
      <div className="um-settings-row"><span>{t('唤起 UniMind.ai')}</span><kbd>{state.platform === 'darwin' ? '⌘' : 'Ctrl'} ⇧ U</kbd></div>
      <div className="um-settings-row"><span>{t('快速新建笔记')}</span><kbd>{state.platform === 'darwin' ? '⌘' : 'Ctrl'} ⇧ N</kbd></div>
    </section>
    <h3 className="um-settings-group-title">{t('应用内快捷键')}</h3><section className="um-settings-group">
      {[['打开设置', ','], ['打开课程中心', '2'], ['新聊天', 'T'], ['离线课程库', '⇧ O']].map(([label, key]) => <div className="um-settings-row" key={label}><span>{t(label)}</span><kbd>{state.platform === 'darwin' ? '⌘' : 'Ctrl'} {key}</kbd></div>)}
    </section></>}
    {(section === 'all' || section === 'storage') && <>
    <h3 className="um-settings-group-title">{t('离线课程')}</h3>
    <section className="um-settings-group">
      <div className="um-settings-row"><div><span>{t('已下载的课程')}</span></div><Button variant="outline" disabled={!!busy} onClick={() => void run('library', desktop.openOfflineLibrary)}>{t('打开离线课程库')}</Button></div>
      {state.storage && <div className="um-settings-row"><div><span>{t('本机课程缓存')}</span><p>{t('已占用')} {storageLabel}</p></div></div>}
      {state.learningSync && <div className="um-settings-row"><div><span>{t('学习记录同步')}</span><p role="status">{state.learningSync.pending ? t('{0} 条记录等待同步，联网后会继续。', { 0: state.learningSync.pending }) : t('暂无待同步记录。')}{state.learningSync.rejected > 0 && t(' {0} 条记录因课程权限或授权变化未计入账户。', { 0: state.learningSync.rejected })}</p>{state.learningSync.error && <p>{state.learningSync.error}</p>}</div><Button variant="outline" disabled={!!busy} onClick={() => void run('sync-learning', desktop.syncIdentity)}>{t('重新同步')}</Button></div>}
      {!state.downloads.length && <div className="um-settings-row"><p>{t('暂无下载。')}</p></div>}
      {state.downloads.map(course => <div className="um-settings-row um-desktop-download" key={course.courseId}>
        <div><strong>{course.title}</strong><p>{course.status === 'downloading' || course.status === 'paused' ? `${course.status === 'paused' ? t('已暂停，可继续下载') : t('正在下载')} · ${Math.min(100, Math.floor(course.receivedBytes / Math.max(1, course.totalBytes) * 100))}%` : course.status === 'failed' ? t(course.error || '下载失败，请重试') : t('可离线观看{0}', { 0: course.expiresAt ? t(' · 有效至 {0}', { 0: new Date(course.expiresAt).toLocaleString(getLocale()) }) : '' })}</p>{course.status === 'downloading' && <progress aria-label={t('{0}下载进度', { 0: course.title })} max={course.totalBytes || 1} value={course.receivedBytes} />}</div>
        <div className="um-desktop-actions">
          {course.status === 'ready' && <Button variant="outline" disabled={!!busy} onClick={() => void run(`play-${course.courseId}`, () => desktop.openOfflineCourse(course.courseId))}>{t('播放')}</Button>}
          {course.status === 'downloading' && desktop.pauseDownload && <Button variant="outline" disabled={!!busy} onClick={() => void run(`pause-${course.courseId}`, () => desktop.pauseDownload!(course.courseId))}>{t('暂停')}</Button>}
          {(course.status === 'failed' || course.status === 'paused') && <Button variant="outline" disabled={!!busy} onClick={() => void run(`retry-${course.courseId}`, () => desktop.downloadCourse(course.courseId))}>{course.status === 'paused' ? t('继续下载') : t('重试')}</Button>}
          <Button variant="ghost" disabled={!!busy} onClick={() => void run(`remove-${course.courseId}`, () => desktop.removeDownload(course.courseId))}>{course.status === 'downloading' ? t('取消并移除') : t('移除')}</Button>
        </div>
      </div>)}
    </section>
    </>}
    {(section === 'all' || section === 'updates') && <>
    <h3 className="um-settings-group-title">{t('版本与更新')}</h3>
    <section className="um-settings-group">
      <div className="um-settings-row">
        <div>
          <span>{t('客户端版本')} {state.version}</span>
          {!['unconfigured', 'idle'].includes(state.update.status) && <p role="status">{updateLabels[state.update.status]}{state.update.version ? ` · ${state.update.version}` : ''}</p>}
          {state.update.status === 'error' && state.update.error && <p>{t(state.update.error)}</p>}
          {checkWebsite && busy === 'update' && <p role="status">{t('正在检查更新…')}</p>}
          {checkWebsite && websiteResult === 'current' && <p role="status">{t('当前已是最新版')}</p>}
          {websiteUpdate && <>
            <p role="status">{t('发现新版本')} · {websiteUpdate.version}{websiteUpdate.prerelease && t(' · 预发布版')}</p>
            <p>{websiteUpdate.url ? t('下载后请退出 App 并手动安装。') : t('暂无对应安装包')}</p>
          </>}
        </div>
        <div className="um-desktop-actions">
          {websiteUpdate?.url && <Button asChild><a href={websiteUpdate.url} download>{t('下载新版')}</a></Button>}
          {state.update.status === 'downloaded'
            ? <Button disabled={!!busy} onClick={() => void run('install', desktop.installUpdate)}>{t('重启并更新')}</Button>
            : <Button variant="outline" disabled={!!busy || ['checking', 'available', 'downloading'].includes(state.update.status)} onClick={() => void run('update', checkForUpdates)}>{t('检查更新')}</Button>}
        </div>
      </div>
    </section>
    </>}
  </>;
}
