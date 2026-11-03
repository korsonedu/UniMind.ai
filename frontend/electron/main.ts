import { app, BrowserWindow, Menu, clipboard, dialog, session, ipcMain, Notification, Tray, nativeImage, protocol, powerMonitor, globalShortcut, type MenuItemConstructorOptions } from 'electron';
import path from 'node:path';
import { readFile, writeFile } from 'node:fs/promises';
import { OfflineLibrary, courseId } from './offline';
import { DesktopUpdater } from './updater';
import { DesktopAuth } from './auth';
import { sameOrigin, validResource, validSource } from './security';

const RELEASE_URL = 'https://unimind-ai.com';
const DEV_URL = 'http://127.0.0.1:5173';
const PREVIEW_URL = 'http://127.0.0.1:5175/api/ai/dsh-preview/student-b/';

const SECURE_WEB_PREFERENCES: Electron.WebPreferences = {
  contextIsolation: true,
  nodeIntegration: false,
  sandbox: true,
  webSecurity: true,
  spellcheck: false,
  scrollBounce: process.platform === 'darwin',
  webviewTag: false,
};

let mainWindow: BrowserWindow | null = null;
const mainWindows = new Map<BrowserWindow, { pendingRoute?: string; recoveryNotice?: 'resume' | 'renderer-recovered' }>();
let sourceUrl = '';
let offline: OfflineLibrary;
let updater: DesktopUpdater;
let auth: DesktopAuth;
let offlineWindow: BrowserWindow | null = null;
let tray: Tray | null = null;
let trayMenu: Menu | null = null;
let quitting = false;
let preferences = { notifications: false, keepRunning: false, launchAtLogin: false, quickEntry: true, focusMinutes: 25, startupPage: '/xiaoyu', notifyChat: true, notifyQA: true, notifyLearning: true };
let focusDuration = preferences.focusMinutes * 60;
let focusStatus: 'idle' | 'running' | 'paused' = 'idle';
let focusRemaining = focusDuration;
let focusEndsAt = 0;
let focusInterval: ReturnType<typeof setInterval> | null = null;
const noticeTimes = new Map<string, number>();
protocol.registerSchemesAsPrivileged([{ scheme: 'unimind-offline', privileges: { standard: true, secure: true, supportFetchAPI: true, stream: true } }]);

function state() {
  return { version: app.getVersion(), platform: process.platform, preferences: { ...preferences }, focus: { status: focusStatus, remaining: focusRemaining, duration: focusDuration }, downloads: offline?.list() || [], storage: offline?.storage() || { usedBytes: 0 }, learningSync: offline?.learningSync() || { pending: 0, rejected: 0 }, offlineSession: offline?.offlineSession() || null, update: updater?.state || { status: 'unconfigured' }, auth: auth?.state || { status: 'idle' } };
}
function changed() {
  const next = state();
  for (const window of mainWindows.keys()) {
    if (sameOrigin(sourceUrl, window.webContents.getURL())) window.webContents.send('desktop:state', next);
  }
}

function focusText(seconds: number) {
  return `${Math.floor(seconds / 60).toString().padStart(2, '0')}:${(seconds % 60).toString().padStart(2, '0')}`;
}
const trayImages = new Map<string, Electron.NativeImage>();
function trayIcon(paused = false) {
  const file = process.platform === 'darwin' ? (paused ? 'trayPausedTemplate.png' : 'trayTemplate.png') : 'tray.png';
  if (!trayImages.has(file)) {
    const image = nativeImage.createFromPath(path.join(app.getAppPath(), file));
    if (process.platform === 'darwin') image.setTemplateImage(true);
    trayImages.set(file, image);
  }
  return trayImages.get(file)!;
}
function trayLabel(seconds: number) {
  return seconds >= 60 ? `${Math.ceil(seconds / 60)}m` : `${seconds}s`;
}
let trayPaused = false;
function updateTrayTitle() {
  if (!tray) return;
  const active = focusStatus !== 'idle';
  const paused = focusStatus === 'paused';
  if (process.platform === 'darwin') {
    if (paused !== trayPaused) {
      tray.setImage(trayIcon(paused));
      trayPaused = paused;
    }
    tray.setTitle(active ? trayLabel(focusRemaining) : '', { fontType: 'monospacedDigit' });
  }
  tray.setToolTip(active ? `UniMind · ${paused ? '已暂停' : '专注中'} ${focusText(focusRemaining)}` : 'UniMind');
}
function maybeQuit() {
  if (process.platform !== 'darwin' && !preferences.keepRunning && focusStatus === 'idle' && !mainWindows.size && !offlineWindow) app.quit();
}
function stopFocusInterval() {
  if (focusInterval) clearInterval(focusInterval);
  focusInterval = null;
}
function ensureFocusInterval() {
  if (focusInterval) return;
  focusInterval = setInterval(focusTick, 1000);
  focusInterval.unref?.();
}
function startFocus() {
  if (focusStatus === 'running') return;
  if (focusStatus === 'paused' && focusRemaining > 0) {
    focusStatus = 'running';
    focusEndsAt = Date.now() + focusRemaining * 1000;
  } else {
    focusDuration = preferences.focusMinutes * 60;
    focusRemaining = focusDuration;
    focusEndsAt = Date.now() + focusDuration * 1000;
    focusStatus = 'running';
  }
  ensureFocusInterval();
  updateTray();
  changed();
}
function pauseFocus() {
  if (focusStatus !== 'running') return;
  focusRemaining = Math.max(0, Math.ceil((focusEndsAt - Date.now()) / 1000));
  focusStatus = 'paused';
  stopFocusInterval();
  updateTray();
  changed();
}
function resetFocus() {
  focusStatus = 'idle';
  focusDuration = preferences.focusMinutes * 60;
  focusRemaining = focusDuration;
  focusEndsAt = 0;
  stopFocusInterval();
  updateTray();
  changed();
  maybeQuit();
}
function toggleFocus() {
  if (focusStatus === 'running') pauseFocus(); else startFocus();
}
function focusTick() {
  if (focusStatus !== 'running') return;
  focusRemaining = Math.max(0, Math.ceil((focusEndsAt - Date.now()) / 1000));
  updateTray();
  if (focusRemaining <= 0) finishFocus();
}
function finishFocus() {
  const completedMinutes = focusDuration / 60;
  stopFocusInterval();
  focusDuration = preferences.focusMinutes * 60;
  focusStatus = 'idle';
  focusRemaining = focusDuration;
  focusEndsAt = 0;
  updateTray();
  changed();
  if (Notification.isSupported()) {
    const notice = new Notification({ title: '专注结束', body: `完成了 ${completedMinutes} 分钟专注，休息一下。` });
    notice.on('click', showMain);
    notice.show();
  }
  maybeQuit();
}
function applyLaunchAtLogin() {
  if (!app.isPackaged || !['darwin', 'win32'].includes(process.platform)) return;
  app.setLoginItemSettings({ openAtLogin: preferences.launchAtLogin });
}
function registerGlobalShortcuts() {
  globalShortcut.unregisterAll();
  if (!preferences.quickEntry) return;
  if (!globalShortcut.register('CommandOrControl+Shift+U', showMain)) console.warn('无法注册全局快捷键 CommandOrControl+Shift+U');
  if (!globalShortcut.register('CommandOrControl+Shift+N', () => { showMain(); navigate('/notes?new=1'); })) console.warn('无法注册全局快捷键 CommandOrControl+Shift+N');
}
function showMain() {
  const focused = BrowserWindow.getFocusedWindow();
  if (focused && mainWindows.has(focused)) mainWindow = focused;
  if (!mainWindow) createMainWindow();
  if (mainWindow?.isMinimized()) mainWindow.restore();
  mainWindow?.show(); mainWindow?.focus();
}
function validRoute(value: unknown): value is string {
  return typeof value === 'string' && value.length <= 500 && /^\/(?:settings|xiaoyu|courses|notes|qa|tests)(?:[/?#]|$)/.test(value)
    && sameOrigin(sourceUrl, new URL(value, sourceUrl).href)
    && /^\/(?:settings|xiaoyu|courses|notes|qa|tests)(?:\/|$)/.test(new URL(value, sourceUrl).pathname) && !/[\\\r\n]/.test(value);
}
function navigate(route: string) {
  if (!validRoute(route)) return;
  showMain();
  if (!mainWindow) return;
  if (mainWindow.webContents.isLoadingMainFrame()) mainWindows.get(mainWindow)!.pendingRoute = route;
  else mainWindow.webContents.send('desktop:navigate', route);
}
function deepLink(value: string) {
  if (auth?.receive(value)) { showMain(); return; }
  try {
    const url = new URL(value);
    if (url.protocol !== 'unimind:' || url.username || url.password || url.port) return;
    if (!['settings', 'xiaoyu', 'courses', 'notes'].includes(url.hostname)) return;
    const route = `/${url.hostname}${url.pathname}${url.search}${url.hash}`;
    if (validRoute(route)) navigate(route);
  } catch { /* Ignore malformed external links. */ }
}
function openOffline(id?: number) {
  const target = `unimind-offline://library/${id ? `course/${courseId(id)}` : ''}`;
  if (!offlineWindow) {
    offlineWindow = new BrowserWindow({ width: 1100, height: 760, title: 'UniMind · 离线课程', webPreferences: { ...SECURE_WEB_PREFERENCES, partition: 'unimind-offline' } });
    installContextMenu(offlineWindow);
    offlineWindow.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
    const guard = (event: Electron.Event, url: string) => { if (!url.startsWith('unimind-offline://library/')) event.preventDefault(); };
    offlineWindow.webContents.on('will-navigate', guard);
    offlineWindow.webContents.on('will-redirect', event => guard(event, event.url));
    offlineWindow.on('closed', () => { offlineWindow = null; });
  }
  void offlineWindow.loadURL(target); offlineWindow.show();
}
function updateMenu() {
  const menu = Menu.getApplicationMenu();
  const toggle = menu?.getMenuItemById('focus-toggle');
  if (toggle) toggle.label = focusStatus === 'running' ? '暂停专注' : focusStatus === 'paused' ? '继续专注' : '开始专注';
  const reset = menu?.getMenuItemById('focus-reset');
  if (reset) reset.enabled = focusStatus !== 'idle';
}
function updateTray() {
  updateMenu();
  const shouldShow = preferences.keepRunning || focusStatus !== 'idle';
  if (!shouldShow) { tray?.destroy(); tray = null; trayMenu = null; trayPaused = false; return; }
  if (!tray) {
    tray = new Tray(trayIcon());
    trayPaused = false;
    if (process.platform !== 'darwin') tray.on('click', showMain);
    trayMenu = Menu.buildFromTemplate([
      { label: '打开 UniMind', icon: trayIcon().resize({ width: 16, height: 16 }), click: showMain },
      { label: '离线课程库', click: () => openOffline() },
      { type: 'separator' },
      { id: 'focus-time', label: '', enabled: false },
      { id: 'focus-action', label: '', click: toggleFocus },
      { id: 'focus-reset', label: '重置计时', click: resetFocus },
      { type: 'separator' },
      { label: '退出 UniMind', click: () => app.quit() },
    ]);
    tray.setContextMenu(trayMenu);
  }
  trayMenu!.getMenuItemById('focus-time')!.label = `${focusStatus === 'running' ? '专注中' : focusStatus === 'paused' ? '已暂停' : '专注'} · ${focusText(focusRemaining)}`;
  trayMenu!.getMenuItemById('focus-action')!.label = focusStatus === 'running' ? '暂停专注' : focusStatus === 'paused' ? '继续专注' : `开始 ${preferences.focusMinutes} 分钟专注`;
  trayMenu!.getMenuItemById('focus-reset')!.enabled = focusStatus !== 'idle';
  updateTrayTitle();
}
function notify(value: unknown) {
  if (!value || typeof value !== 'object') throw new Error('无效通知');
  const item = value as Record<string, unknown>;
  if (typeof item.title !== 'string' || typeof item.body !== 'string' || !validRoute(item.route)) throw new Error('无效通知');
  const kind = item.kind ?? 'learning';
  if (!['chat', 'qa', 'learning'].includes(kind as string)) throw new Error('无效通知类别');
  const enabled = kind === 'chat' ? preferences.notifyChat : kind === 'qa' ? preferences.notifyQA : preferences.notifyLearning;
  if (!preferences.notifications || !enabled || mainWindow?.isFocused() || !Notification.isSupported()) return;
  const key = `${item.title}:${item.route}`;
  if (Date.now() - (noticeTimes.get(key) || 0) < 60000) return;
  noticeTimes.set(key, Date.now());
  if (noticeTimes.size > 100) noticeTimes.delete(noticeTimes.keys().next().value!);
  const notice = new Notification({ title: item.title.slice(0, 80), body: item.body.slice(0, 160), silent: true });
  notice.on('click', () => navigate(item.route as string)); notice.show();
}
function validPreference(key: string, value: unknown) {
  if (['notifications', 'keepRunning', 'launchAtLogin', 'quickEntry', 'notifyChat', 'notifyQA', 'notifyLearning'].includes(key)) return typeof value === 'boolean';
  if (key === 'focusMinutes') return typeof value === 'number' && [15, 25, 45, 60].includes(value);
  if (key === 'startupPage') return ['/xiaoyu', '/courses', '/notes'].includes(value as string);
  return false;
}
function installIPC() {
  const handlers: Record<string, (value: unknown) => unknown> = {
    getState: () => state(),
    syncIdentity: async () => { await offline.sync(); return state(); },
    startLogin: async () => { await auth.start(); return state(); },
    cancelLogin: async () => { await auth.cancel(); return state(); },
    logout: async () => { await auth.cancel(); await offline.logout(); return state(); },
    updatePreferences: async (value: unknown) => {
      if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('无效桌面设置');
      if (!Object.entries(value).every(([key, setting]) => validPreference(key, setting))) throw new Error('无效桌面设置');
      const next = { ...preferences, ...value };
      await writeFile(path.join(app.getPath('userData'), 'desktop-preferences.json'), JSON.stringify(next));
      preferences = next;
      if (focusStatus === 'idle') focusRemaining = focusDuration = preferences.focusMinutes * 60;
      applyLaunchAtLogin();
      registerGlobalShortcuts();
      updateTray(); changed(); return state();
    },
    notify,
    downloadCourse: async (id: unknown) => { await offline.download(courseId(id)); return state(); },
    pauseDownload: async (id: unknown) => { await offline.pause(courseId(id)); return state(); },
    removeDownload: async (id: unknown) => { await offline.remove(courseId(id)); return state(); },
    openOfflineLibrary: () => openOffline(),
    openOfflineCourse: (id: unknown) => openOffline(courseId(id)),
    readOfflineData: () => offline.readOfflineData(),
    writeOfflineData: async (value: unknown) => { await offline.writeOfflineData(value); return state(); },
    clearOfflineData: async () => { await offline.clearOfflineData(); return state(); },
    checkForUpdates: async () => { await updater.check(); return state(); },
    installUpdate: () => updater.install(() => { quitting = true; }),
  };
  for (const [name, handler] of Object.entries(handlers)) ipcMain.handle(`desktop:${name}`, (event, ...args) => {
    const window = BrowserWindow.fromWebContents(event.sender);
    if (!window || !mainWindows.has(window) || event.senderFrame !== window.webContents.mainFrame || !sameOrigin(sourceUrl, event.senderFrame.url)) throw new Error('不受信任的桌面请求');
    return handler(args[0]);
  });
}

function previewMode(): boolean {
  return app.getName().toLowerCase().includes('preview') || (!app.isPackaged && process.env.UNIMIND_DESKTOP_PREVIEW === '1');
}

function entryUrl(): string {
  if (app.isPackaged && !previewMode()) {
    const target = new URL('/login', RELEASE_URL);
    target.searchParams.set('next', preferences.startupPage);
    return target.href;
  }
  if (process.env.UNIMIND_DESKTOP_URL) return process.env.UNIMIND_DESKTOP_URL;
  if (previewMode()) return PREVIEW_URL;
  return app.isPackaged ? RELEASE_URL : DEV_URL;
}

function allowsDevelopment(source: string): boolean {
  return !app.isPackaged || previewMode() || source.startsWith('http://127.0.0.1')
    || source.startsWith('http://localhost') || source.startsWith('http://[::1]');
}

function openResourceWindow(target: string, development: boolean): void {
  const window = new BrowserWindow({
    width: 900,
    height: 650,
    minWidth: 640,
    minHeight: 480,
    title: 'UniMind · 课程与附件',
    parent: mainWindow ?? undefined,
    webPreferences: SECURE_WEB_PREFERENCES,
  });
  installContextMenu(window);
  window.webContents.on('will-navigate', (event, url) => {
    if (!validResource(sourceUrl, url, development)) event.preventDefault();
  });
  window.webContents.on('will-redirect', event => {
    if (!validResource(sourceUrl, event.url, development)) event.preventDefault();
  });
  window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  void window.loadURL(target).catch(() => {});
}

let recovering = false;
function signalRecovery(reason: 'resume' | 'renderer-recovered', window: BrowserWindow) {
  if (sameOrigin(sourceUrl, window.webContents.getURL()) && !window.webContents.isLoadingMainFrame()) window.webContents.send('desktop:resume', { reason });
  else mainWindows.get(window)!.recoveryNotice = reason;
}
async function offerRecovery(window: BrowserWindow) {
  if (recovering || quitting || window.isDestroyed()) return;
  recovering = true;
  try {
    const result = await dialog.showMessageBox(window, { type: 'warning', title: 'UniMind 需要重新连接', message: '页面暂时没有响应。可以重新连接，或先打开离线课程库。', detail: '重新连接后会恢复草稿并查询原任务；执行结果不明时，可先刷新历史，再决定是否手动重试。', buttons: ['重新连接', '离线课程库', '稍后处理'], defaultId: 0, cancelId: 2 });
    if (result.response === 0 && !window.isDestroyed()) {
      const current = window.webContents.getURL();
      mainWindows.get(window)!.recoveryNotice = 'renderer-recovered';
      void window.loadURL(sameOrigin(sourceUrl, current) ? current : sourceUrl).catch(() => {});
    } else if (result.response === 1) openOffline();
  } finally { recovering = false; }
}

function fallbackUrl(): string {
  const target = sourceUrl.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
  const html = `<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>UniMind · 网络不可用</title>
<style>
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;padding:32px;background:#f4f2ed;color:#202226;font:15px/1.7 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
main{width:min(440px,100%);padding:28px;border:1px solid #e2e5e9;border-radius:16px;background:#fff;box-shadow:0 8px 24px rgb(20 25 30 / 6%)}
h1{margin:0 0 8px;font-size:20px}p{margin:0 0 12px;color:#60656c}a{display:inline-block;margin-top:8px;color:#202226;font-weight:600;text-decoration:underline;text-underline-offset:3px}
small{display:block;margin-top:16px;color:#8a8f96}
</style>
</head>
<body><main>
<h1>网络暂时不可用</h1>
<p>无法连接 UniMind。请检查网络后重试。</p>
<p>离线课程库已打开，可继续观看已下载的课程。</p>
<a href="${target}">重新连接</a>
<small>UniMind ${app.getVersion()}</small>
</main></body></html>`;
  return `data:text/html;charset=utf-8,${encodeURIComponent(html)}`;
}

function createMainWindow(): void {
  const source = entryUrl();
  const development = allowsDevelopment(source);
  if (!validSource(source, development)) {
    dialog.showErrorBox('UniMind 无法启动', '桌面客户端只允许 HTTPS 站点或本机开发地址。');
    app.quit();
    return;
  }
  sourceUrl = source;
  const window = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 900,
    minHeight: 600,
    center: true,
    resizable: true,
    fullscreen: false,
    show: false,
    title: previewMode() ? 'UniMind Preview · 合成数据' : 'UniMind',
    titleBarStyle: 'hidden',
    ...(process.platform === 'darwin' ? { trafficLightPosition: { x: 12, y: 18 } } : { titleBarOverlay: true }),
    webPreferences: { ...SECURE_WEB_PREFERENCES, preload: path.join(__dirname, 'preload.cjs') },
  });
  mainWindows.set(window, {});
  mainWindow = window;
  const windowState = mainWindows.get(window)!;
  installContextMenu(window);
  window.on('focus', () => { mainWindow = window; });
  window.once('ready-to-show', () => window.show());
  window.webContents.on('will-navigate', (event, url) => {
    if (!sameOrigin(source, url)) event.preventDefault();
  });
  window.webContents.on('will-redirect', event => {
    if (event.isMainFrame && !sameOrigin(source, event.url)) event.preventDefault();
  });
  window.webContents.setWindowOpenHandler(({ url }) => {
    if (validResource(source, url, development)) openResourceWindow(url, development);
    return { action: 'deny' };
  });
  window.webContents.on('did-finish-load', () => {
    changed();
    if (windowState.recoveryNotice) { const reason = windowState.recoveryNotice; windowState.recoveryNotice = undefined; signalRecovery(reason, window); }
    if (windowState.pendingRoute) { const route = windowState.pendingRoute; windowState.pendingRoute = undefined; window.webContents.send('desktop:navigate', route); }
  });
  window.webContents.on('did-fail-load', (_event, code, _description, url, isMainFrame) => {
    if (code === -3 || !isMainFrame || url.startsWith('data:')) return;
    window.show();
    if (app.isPackaged && !previewMode()) void window.loadURL(fallbackUrl()).catch(() => {});
    openOffline();
  });
  window.webContents.on('render-process-gone', () => { void offerRecovery(window); });
  window.on('unresponsive', () => { void offerRecovery(window); });
  window.on('close', event => {
    if (preferences.keepRunning && !quitting) { event.preventDefault(); window.hide(); }
  });
  window.on('closed', () => {
    mainWindows.delete(window);
    if (mainWindow === window) mainWindow = [...mainWindows.keys()].pop() ?? null;
  });
  void window.loadURL(source).catch(() => {});
  if (!app.isPackaged) window.webContents.openDevTools({ mode: 'detach' });
}

function installContextMenu(window: BrowserWindow): void {
  window.webContents.on('context-menu', (_event, params) => {
    const { editFlags: flags, isEditable, selectionText, linkURL } = params;
    const items: MenuItemConstructorOptions[] = [];
    if (isEditable) {
      items.push(
        { label: '撤销', role: 'undo', enabled: flags.canUndo },
        { label: '重做', role: 'redo', enabled: flags.canRedo },
        { type: 'separator' },
        { label: '剪切', role: 'cut', enabled: flags.canCut },
        { label: '复制', role: 'copy', enabled: flags.canCopy },
        { label: '粘贴', role: 'paste', enabled: flags.canPaste },
        { label: '全选', role: 'selectAll', enabled: flags.canSelectAll },
      );
    } else if (selectionText.trim()) {
      items.push({ label: '复制', role: 'copy', enabled: flags.canCopy });
    }
    if (linkURL && validResource(sourceUrl, linkURL, allowsDevelopment(sourceUrl))) {
      if (items.length) items.push({ type: 'separator' });
      items.push(
        { label: '打开链接', click: () => openResourceWindow(linkURL, allowsDevelopment(sourceUrl)) },
        { label: '复制链接地址', click: () => clipboard.writeText(linkURL) },
      );
    }
    if (items.length) Menu.buildFromTemplate(items).popup({ window });
  });
}

function installMenu(): void {
  const template: MenuItemConstructorOptions[] = [];
  const appName = previewMode() ? 'UniMind Preview' : 'UniMind';
  const settings: MenuItemConstructorOptions = { label: '设置…', accelerator: 'CommandOrControl+,', click: () => navigate('/settings?section=desktop') };
  const update: MenuItemConstructorOptions = { label: '检查更新…', click: () => { navigate('/settings?section=desktop'); void updater.check(); } };
  const quit: MenuItemConstructorOptions = { role: 'quit', label: `退出 ${appName}` };
  const offlineLibrary: MenuItemConstructorOptions = { label: '离线课程库', accelerator: 'CommandOrControl+Shift+O', click: () => openOffline() };
  const reconnect: MenuItemConstructorOptions = { label: '重新连接', click: () => { showMain(); void mainWindow?.loadURL(sourceUrl); } };
  const file: MenuItemConstructorOptions[] = [
    { label: '新建窗口', accelerator: 'CommandOrControl+N', click: () => createMainWindow() },
    { label: '新聊天', accelerator: 'CommandOrControl+T', click: () => navigate('/xiaoyu?new=chat') },
    { label: '新项目…', click: () => navigate('/xiaoyu?new=project') },
    { type: 'separator' },
    offlineLibrary,
    reconnect,
    { type: 'separator' },
    { role: 'close', label: '关闭窗口' },
  ];
  const study: MenuItemConstructorOptions[] = [
    { label: '课程', accelerator: 'CommandOrControl+2', click: () => navigate('/courses') },
    { type: 'separator' },
    { id: 'focus-toggle', label: '开始专注', click: toggleFocus },
    { id: 'focus-reset', label: '重置专注', click: resetFocus },
  ];
  if (process.platform === 'darwin') {
    template.push({ label: appName, submenu: [
      { role: 'about', label: `关于 ${appName}` },
      { type: 'separator' },
      settings,
      update,
      { type: 'separator' },
      { role: 'services', label: '服务' },
      { type: 'separator' },
      { role: 'hide', label: `隐藏 ${appName}` },
      { role: 'hideOthers', label: '隐藏其他' },
      { role: 'unhide', label: '全部显示' },
      { type: 'separator' },
      quit,
    ] });
  } else {
    file.push({ type: 'separator' }, settings, update, quit);
  }
  template.push({ label: '文件', submenu: file }, { label: '学习', submenu: study }, { role: 'editMenu', label: '编辑' });
  if (process.platform === 'darwin') template.push({ label: '显示', submenu: [
    ...(!app.isPackaged ? [{ role: 'forceReload' as const, label: '强制重新载入' }, { role: 'toggleDevTools' as const, label: '切换开发者工具' }, { type: 'separator' as const }] : []),
    { role: 'resetZoom', label: '实际大小' },
    { role: 'zoomIn', label: '放大' },
    { role: 'zoomOut', label: '缩小' },
    { type: 'separator' },
    { role: 'togglefullscreen', label: '切换全屏' },
  ] });
  template.push({ role: 'windowMenu', label: '窗口' });
  if (process.platform !== 'darwin' && !app.isPackaged) template.push({ role: 'viewMenu' });
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
  updateMenu();
}

function installSecurity(): void {
  session.defaultSession.setPermissionRequestHandler((_contents, _permission, callback) => callback(false));
  session.defaultSession.setPermissionCheckHandler(() => false);
  app.on('web-contents-created', (_event, contents) => {
    contents.on('will-attach-webview', event => event.preventDefault());
  });
}

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  let desktopReady = false;
  let pendingDeepLink = process.argv.find(arg => arg.startsWith('unimind://')) || '';
  app.on('before-quit', () => { quitting = true; });
  app.on('will-quit', () => { globalShortcut.unregisterAll(); stopFocusInterval(); });
  app.on('open-url', (event, url) => { event.preventDefault(); if (desktopReady) deepLink(url); else pendingDeepLink = url; });
  app.on('second-instance', (_event, argv) => {
    const link = argv.find(arg => arg.startsWith('unimind://'));
    if (!desktopReady) { if (link) pendingDeepLink = link; return; }
    showMain(); if (link) deepLink(link);
  });
  app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') maybeQuit();
  });
  app.whenReady().then(async () => {
    sourceUrl = entryUrl();
    if (!validSource(sourceUrl, allowsDevelopment(sourceUrl))) throw new Error('桌面客户端只允许 HTTPS 站点或本机开发地址');
    try {
      const saved = JSON.parse(await readFile(path.join(app.getPath('userData'), 'desktop-preferences.json'), 'utf8'));
      if (saved && typeof saved === 'object' && !Array.isArray(saved)) {
        preferences = { ...preferences, ...Object.fromEntries(Object.entries(saved).filter(([key, value]) => validPreference(key, value))) };
      }
    } catch { /* Defaults require explicit opt-in. */ }
    focusRemaining = focusDuration = preferences.focusMinutes * 60;
    sourceUrl = entryUrl();
    offline = new OfflineLibrary(sourceUrl, changed, () => { offlineWindow?.close(); });
    await offline.restore();
    updater = new DesktopUpdater(previewMode(), changed);
    auth = new DesktopAuth(sourceUrl, changed, () => {
      showMain();
      void mainWindow?.loadURL(new URL(`/account-callback?next=${encodeURIComponent(preferences.startupPage)}`, sourceUrl).href).catch(() => {});
    });
    const privateSession = session.fromPartition('unimind-offline');
    privateSession.setPermissionRequestHandler((_contents, _permission, callback) => callback(false));
    privateSession.setPermissionCheckHandler(() => false);
    privateSession.protocol.handle('unimind-offline', request => {
      const contents = offlineWindow?.webContents;
      const trustedPrivateWindow = !!contents && !contents.isDestroyed() && contents.session === privateSession
        && contents.getURL().startsWith('unimind-offline://library/');
      return offline.respond(request, trustedPrivateWindow);
    });
    setInterval(() => { if (offlineWindow) void offline.sync().catch(() => {}); }, 60000).unref();
    installIPC(); updateTray();
    powerMonitor.on('suspend', () => offline.suspend());
    powerMonitor.on('resume', () => {
      for (const window of mainWindows.keys()) signalRecovery('resume', window);
      if (offlineWindow) offlineWindow.webContents.reload();
    });
    if (app.isPackaged && !previewMode()) app.setAsDefaultProtocolClient('unimind');
    session.defaultSession.cookies.on('changed', (_event, cookie) => {
      const domain = cookie.domain?.replace(/^\./, '');
      if (cookie.name === 'auth_token' && domain && (new URL(sourceUrl).hostname === domain || new URL(sourceUrl).hostname.endsWith(`.${domain}`))) void offline.lock().catch(() => {});
    });
    installMenu();
    installSecurity();
    app.setAboutPanelOptions({ applicationName: 'UniMind', applicationVersion: app.getVersion() });
    createMainWindow();
    desktopReady = true;
    applyLaunchAtLogin();
    registerGlobalShortcuts();
    if (app.isPackaged && !previewMode()) {
      setTimeout(() => { void updater.check(); }, 8000).unref();
    }
    if (pendingDeepLink) { deepLink(pendingDeepLink); pendingDeepLink = ''; }
    app.on('activate', () => {
      showMain();
    });
  }).catch(error => {
    dialog.showErrorBox('UniMind 无法启动', String(error));
    app.quit();
  });
}
