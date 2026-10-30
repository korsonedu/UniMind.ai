import { contextBridge, ipcRenderer } from 'electron';

const invoke = (method: string, ...args: unknown[]) => ipcRenderer.invoke(`desktop:${method}`, ...args);
const subscribe = (channel: string, callback: (value: any) => void) => {
  const listener = (_event: Electron.IpcRendererEvent, value: unknown) => callback(value);
  ipcRenderer.on(channel, listener);
  return () => ipcRenderer.removeListener(channel, listener);
};
let pendingRoute: string | undefined;
const navigationListeners = new Set<(route: string) => void>();
ipcRenderer.on('desktop:navigate', (_event, route: string) => {
  if (!navigationListeners.size) pendingRoute = route;
  else for (const callback of navigationListeners) callback(route);
});
let pendingResume: { reason: 'resume' | 'renderer-recovered' } | undefined;
const resumeListeners = new Set<(event: { reason: 'resume' | 'renderer-recovered' }) => void>();
ipcRenderer.on('desktop:resume', (_event, value: { reason: 'resume' | 'renderer-recovered' }) => {
  if (!resumeListeners.size) pendingResume = value;
  else for (const callback of resumeListeners) callback(value);
});
contextBridge.exposeInMainWorld('unimindDesktop', {
  getState: () => invoke('getState'),
  syncIdentity: () => invoke('syncIdentity'),
  logout: () => invoke('logout'),
  updatePreferences: (value: unknown) => invoke('updatePreferences', value),
  notify: (value: unknown) => invoke('notify', value),
  downloadCourse: (courseId: number) => invoke('downloadCourse', courseId),
  pauseDownload: (courseId: number) => invoke('pauseDownload', courseId),
  removeDownload: (courseId: number) => invoke('removeDownload', courseId),
  openOfflineLibrary: () => invoke('openOfflineLibrary'),
  openOfflineCourse: (courseId: number) => invoke('openOfflineCourse', courseId),
  checkForUpdates: () => invoke('checkForUpdates'),
  installUpdate: () => invoke('installUpdate'),
  onNavigate: (callback: (route: string) => void) => {
    navigationListeners.add(callback);
    if (pendingRoute) { const route = pendingRoute; pendingRoute = undefined; callback(route); }
    return () => navigationListeners.delete(callback);
  },
  onResume: (callback: (event: { reason: 'resume' | 'renderer-recovered' }) => void) => {
    resumeListeners.add(callback);
    if (pendingResume) { const value = pendingResume; pendingResume = undefined; callback(value); }
    return () => resumeListeners.delete(callback);
  },
  onStateChanged: (callback: (state: unknown) => void) => subscribe('desktop:state', callback),
});
