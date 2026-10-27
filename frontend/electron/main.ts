import { app, BrowserWindow, Menu, dialog, session, type MenuItemConstructorOptions } from 'electron';
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
  webviewTag: false,
};

let mainWindow: BrowserWindow | null = null;
let sourceUrl = '';

function previewMode(): boolean {
  return process.env.UNIMIND_DESKTOP_PREVIEW === '1' || app.getName().toLowerCase().includes('preview');
}

function entryUrl(): string {
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
  window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  void window.loadURL(target);
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
    webPreferences: SECURE_WEB_PREFERENCES,
  });
  mainWindow.once('ready-to-show', () => mainWindow?.show());
  mainWindow.webContents.on('will-navigate', (event, url) => {
    if (!sameOrigin(source, url)) event.preventDefault();
  });
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (validResource(source, url, development)) openResourceWindow(url, development);
    return { action: 'deny' };
  });
  mainWindow.webContents.on('did-fail-load', (_event, code, description) => {
    if (code === -3) return;
    dialog.showErrorBox('UniMind 无法连接', `加载失败：${description || code}`);
  });
  mainWindow.on('closed', () => { mainWindow = null; });
  void mainWindow.loadURL(source);
  if (!app.isPackaged) mainWindow.webContents.openDevTools({ mode: 'detach' });
}

function installMenu(): void {
  const template: MenuItemConstructorOptions[] = [];
  if (process.platform === 'darwin') template.push({ role: 'appMenu' });
  template.push({ role: 'editMenu' }, { role: 'windowMenu' });
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
  app.on('second-instance', () => {
    if (!mainWindow) return;
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.focus();
  });
  app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') app.quit();
  });
  app.whenReady().then(() => {
    installMenu();
    installSecurity();
    app.setAboutPanelOptions({ applicationName: 'UniMind', applicationVersion: app.getVersion() });
    createMainWindow();
    app.on('activate', () => {
      if (BrowserWindow.getAllWindows().length === 0) createMainWindow();
    });
  }).catch(error => {
    dialog.showErrorBox('UniMind 无法启动', String(error));
    app.quit();
  });
}
