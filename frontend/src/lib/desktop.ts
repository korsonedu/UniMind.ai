import { create } from 'zustand';

export interface DesktopState {
  version: string;
  platform: string;
  preferences: { notifications: boolean; keepRunning: boolean };
  downloads: { courseId: number; title: string; status: 'downloading' | 'paused' | 'ready' | 'failed'; receivedBytes: number; totalBytes: number; expiresAt?: number; error?: string }[];
  storage?: { usedBytes: number };
  learningSync?: { pending: number; rejected: number; error?: string };
  update: { status: 'unconfigured' | 'idle' | 'checking' | 'available' | 'downloading' | 'downloaded' | 'error'; version?: string; error?: string };
}
interface DesktopBridge {
  getState(): Promise<DesktopState>;
  syncIdentity(): Promise<DesktopState>;
  logout(): Promise<DesktopState>;
  updatePreferences(value: Partial<DesktopState['preferences']>): Promise<DesktopState>;
  notify(value: { title: string; body: string; route: string }): Promise<void>;
  downloadCourse(courseId: number): Promise<DesktopState>;
  pauseDownload?(courseId: number): Promise<DesktopState>;
  removeDownload(courseId: number): Promise<DesktopState>;
  openOfflineLibrary(): Promise<void>;
  openOfflineCourse(courseId: number): Promise<void>;
  checkForUpdates(): Promise<DesktopState>;
  installUpdate(): Promise<void>;
  onNavigate(callback: (route: string) => void): () => void;
  onStateChanged(callback: (state: DesktopState) => void): () => void;
  onResume?(callback: (event: { reason: 'resume' | 'renderer-recovered' }) => void): () => void;
}
declare global { interface Window { unimindDesktop?: DesktopBridge } }
export const useDesktopStore = create<{ state: DesktopState | null; error: string | null }>(() => ({ state: null, error: null }));
export function notifyDesktop(value: { title: string; body: string; route: string }) {
  void window.unimindDesktop?.notify(value).catch(() => { /* System notifications are best effort. */ });
}
