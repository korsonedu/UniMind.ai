import { app, BrowserWindow, Menu, dialog, session, ipcMain, Notification, Tray, nativeImage, protocol, powerMonitor, type MenuItemConstructorOptions } from 'electron';
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
let sourceUrl = '';
let offline: OfflineLibrary;
let updater: DesktopUpdater;
let auth: DesktopAuth;
let offlineWindow: BrowserWindow | null = null;
let tray: Tray | null = null;
let quitting = false;
let preferences = { notifications: false, keepRunning: false };
const noticeTimes = new Map<string, number>();
protocol.registerSchemesAsPrivileged([{ scheme: 'unimind-offline', privileges: { standard: true, secure: true, supportFetchAPI: true, stream: true } }]);

function state() {
  return { version: app.getVersion(), platform: process.platform, preferences: { ...preferences }, downloads: offline?.list() || [], storage: offline?.storage() || { usedBytes: 0 }, learningSync: offline?.learningSync() || { pending: 0, rejected: 0 }, offlineSession: offline?.offlineSession() || null, update: updater?.state || { status: 'unconfigured' }, auth: auth?.state || { status: 'idle' } };
}
function changed() {
  if (mainWindow && sameOrigin(sourceUrl, mainWindow.webContents.getURL())) mainWindow.webContents.send('desktop:state', state());
}
function showMain() {
  if (!mainWindow) createMainWindow();
  if (mainWindow?.isMinimized()) mainWindow.restore();
  mainWindow?.show(); mainWindow?.focus();
}
function validRoute(value: unknown): value is string {
  return typeof value === 'string' && value.length <= 500 && /^\/(?:settings|xiaoyu|courses|notes)(?:[/?#]|$)/.test(value)
    && sameOrigin(sourceUrl, new URL(value, sourceUrl).href)
    && /^\/(?:settings|xiaoyu|courses|notes)(?:\/|$)/.test(new URL(value, sourceUrl).pathname) && !/[\\\r\n]/.test(value);
}
let pendingRoute = '';
function navigate(route: string) {
  if (!validRoute(route)) return;
  showMain();
  if (mainWindow?.webContents.isLoadingMainFrame()) pendingRoute = route;
  else mainWindow?.webContents.send('desktop:navigate', route);
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
    offlineWindow.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
    const guard = (event: Electron.Event, url: string) => { if (!url.startsWith('unimind-offline://library/')) event.preventDefault(); };
    offlineWindow.webContents.on('will-navigate', guard);
    offlineWindow.webContents.on('will-redirect', event => guard(event, event.url));
    offlineWindow.on('closed', () => { offlineWindow = null; });
  }
  void offlineWindow.loadURL(target); offlineWindow.show();
}
function updateTray() {
  if (!preferences.keepRunning) { tray?.destroy(); tray = null; return; }
  if (tray) return;
  tray = new Tray(nativeImage.createFromPath(path.join(app.getAppPath(), 'tray.png')));
  tray.setToolTip('UniMind');
  tray.setContextMenu(Menu.buildFromTemplate([{ label: '打开 UniMind', click: showMain }, { label: '离线课程库', click: () => openOffline() }, { type: 'separator' }, { label: '退出 UniMind', click: () => app.quit() }]));
  tray.on('click', showMain);
}
function notify(value: unknown) {
  if (!value || typeof value !== 'object') throw new Error('无效通知');
  const item = value as Record<string, unknown>;
  if (typeof item.title !== 'string' || typeof item.body !== 'string' || !validRoute(item.route)) throw new Error('无效通知');
  if (!preferences.notifications || mainWindow?.isFocused() || !Notification.isSupported()) return;
  const key = `${item.title}:${item.route}`;
  if (Date.now() - (noticeTimes.get(key) || 0) < 60000) return;
  noticeTimes.set(key, Date.now());
  if (noticeTimes.size > 100) noticeTimes.delete(noticeTimes.keys().next().value!);
  const notice = new Notification({ title: item.title.slice(0, 80), body: item.body.slice(0, 160), silent: true });
  notice.on('click', () => navigate(item.route as string)); notice.show();
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
      for (const [key, enabled] of Object.entries(value)) {
        if (!['notifications', 'keepRunning'].includes(key) || typeof enabled !== 'boolean') throw new Error('无效桌面设置');
        preferences[key as keyof typeof preferences] = enabled;
      }
      await writeFile(path.join(app.getPath('userData'), 'desktop-preferences.json'), JSON.stringify(preferences));
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
    if (!mainWindow || event.sender !== mainWindow.webContents || event.senderFrame !== mainWindow.webContents.mainFrame || !sameOrigin(sourceUrl, event.senderFrame.url)) throw new Error('不受信任的桌面请求');
    return handler(args[0]);
  });
}

function previewMode(): boolean {
  return app.getName().toLowerCase().includes('preview') || (!app.isPackaged && process.env.UNIMIND_DESKTOP_PREVIEW === '1');
}

function entryUrl(): string {
  if (app.isPackaged && !previewMode()) return new URL('/login', RELEASE_URL).href;
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
let recoveryNotice: 'resume' | 'renderer-recovered' | undefined;
function signalRecovery(reason: 'resume' | 'renderer-recovered') {
  if (mainWindow && sameOrigin(sourceUrl, mainWindow.webContents.getURL()) && !mainWindow.webContents.isLoadingMainFrame()) mainWindow.webContents.send('desktop:resume', { reason });
  else recoveryNotice = reason;
}
async function offerRecovery() {
  if (recovering || quitting || !mainWindow) return;
  recovering = true;
  try {
    const result = await dialog.showMessageBox(mainWindow, { type: 'warning', title: 'UniMind 需要重新连接', message: '页面暂时没有响应。可以重新连接，或先打开离线课程库。', detail: '重新连接后会恢复草稿并查询原任务；执行结果不明时，可先刷新历史，再决定是否手动重试。', buttons: ['重新连接', '离线课程库', '稍后处理'], defaultId: 0, cancelId: 2 });
    if (result.response === 0 && mainWindow) {
      const current = mainWindow.webContents.getURL();
      recoveryNotice = 'renderer-recovered';
      void mainWindow.loadURL(sameOrigin(sourceUrl, current) ? current : sourceUrl).catch(() => {});
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
  mainWindow = new BrowserWindow({
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
  mainWindow.once('ready-to-show', () => mainWindow?.show());
  mainWindow.webContents.on('will-navigate', (event, url) => {
    if (!sameOrigin(source, url)) event.preventDefault();
  });
  mainWindow.webContents.on('will-redirect', event => {
    if (event.isMainFrame && !sameOrigin(source, event.url)) event.preventDefault();
  });
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (validResource(source, url, development)) openResourceWindow(url, development);
    return { action: 'deny' };
  });
  mainWindow.webContents.on('did-finish-load', () => {
    changed();
    if (recoveryNotice) { const reason = recoveryNotice; recoveryNotice = undefined; signalRecovery(reason); }
    if (pendingRoute) { const route = pendingRoute; pendingRoute = ''; navigate(route); }
  });
  mainWindow.webContents.on('did-fail-load', (_event, code, _description, url, isMainFrame) => {
    if (code === -3 || !isMainFrame || url.startsWith('data:')) return;
    mainWindow?.show();
    if (app.isPackaged && !previewMode()) void mainWindow?.loadURL(fallbackUrl()).catch(() => {});
    openOffline();
  });
  mainWindow.webContents.on('render-process-gone', () => { void offerRecovery(); });
  mainWindow.on('unresponsive', () => { void offerRecovery(); });
  mainWindow.on('close', event => {
    if (preferences.keepRunning && !quitting) { event.preventDefault(); mainWindow?.hide(); }
  });
  mainWindow.on('closed', () => { mainWindow = null; });
  void mainWindow.loadURL(source).catch(() => {});
  if (!app.isPackaged) mainWindow.webContents.openDevTools({ mode: 'detach' });
}

function installMenu(): void {
  const template: MenuItemConstructorOptions[] = [];
  if (process.platform === 'darwin') template.push({ role: 'appMenu' });
  template.push({ label: '学习', submenu: [
    { label: '小宇', accelerator: 'CommandOrControl+1', click: () => navigate('/xiaoyu') },
    { label: '课程', accelerator: 'CommandOrControl+2', click: () => navigate('/courses') },
    { label: '笔记', accelerator: 'CommandOrControl+3', click: () => navigate('/notes') },
    { label: '桌面设置', accelerator: 'CommandOrControl+,', click: () => navigate('/settings?section=desktop') },
    { type: 'separator' }, { label: '离线课程库', accelerator: 'CommandOrControl+Shift+O', click: () => openOffline() },
    { label: '重新连接', click: () => { showMain(); void mainWindow?.loadURL(sourceUrl); } },
    { label: '退出 UniMind', accelerator: 'CommandOrControl+Q', click: () => app.quit() },
  ] }, { role: 'editMenu' }, { role: 'windowMenu' });
  if (!app.isPackaged) template.push({ role: 'viewMenu' });
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
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
  app.on('open-url', (event, url) => { event.preventDefault(); if (desktopReady) deepLink(url); else pendingDeepLink = url; });
  app.on('second-instance', (_event, argv) => {
    const link = argv.find(arg => arg.startsWith('unimind://'));
    if (!desktopReady) { if (link) pendingDeepLink = link; return; }
    showMain(); if (link) deepLink(link);
  });
  app.on('window-all-closed', () => {
    if (process.platform !== 'darwin' && !preferences.keepRunning) app.quit();
  });
  app.whenReady().then(async () => {
    sourceUrl = entryUrl();
    if (!validSource(sourceUrl, allowsDevelopment(sourceUrl))) throw new Error('桌面客户端只允许 HTTPS 站点或本机开发地址');
    try { const saved = JSON.parse(await readFile(path.join(app.getPath('userData'), 'desktop-preferences.json'), 'utf8')); preferences = { notifications: saved.notifications === true, keepRunning: saved.keepRunning === true }; } catch { /* Defaults require explicit opt-in. */ }
    offline = new OfflineLibrary(sourceUrl, changed, () => { offlineWindow?.close(); });
    await offline.restore();
    updater = new DesktopUpdater(previewMode(), changed);
    auth = new DesktopAuth(sourceUrl, changed, () => {
      showMain();
      void mainWindow?.loadURL(new URL('/account-callback?next=/xiaoyu', sourceUrl).href).catch(() => {});
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
      signalRecovery('resume');
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
