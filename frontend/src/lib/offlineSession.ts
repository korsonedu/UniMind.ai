export const DEMO_USER_ID = -1;
export const DEMO_USER = {
  id: DEMO_USER_ID, username: 'offline-demo', nickname: '离线体验者', role: 'student' as const,
  elo_score: 1000, avatar_url: '', avatar_style: 'bottts', avatar_seed: 'offline-demo', bio: '离线试用数据仅保存在本机',
  allow_broadcast: false, show_others_broadcast: false, is_member: false,
  has_completed_initial_assessment: true, tour_dismissed_at: '2026-01-01', tour_panel_dismissed_at: '2026-01-01',
};
let demo = false;
let offline = false;
const listeners = new Set<() => void>();
export const isOfflineDemo = () => demo;
export const isNativeOffline = () => offline;
export const subscribeOffline = (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; };
export function setOfflineDemo(value: boolean) { demo = value; offline = value; listeners.forEach(listener => listener()); }
export function setNativeOffline(value: boolean) { if (demo) return; offline = value; listeners.forEach(listener => listener()); }
export function keepNativeSession(native: boolean, demoActive: boolean, hasUser: boolean, hasToken: boolean, status?: number): boolean {
  return native && (demoActive || (hasUser && hasToken && status !== 401 && status !== 403));
}
export const OFFLINE_MESSAGE = '当前处于离线状态，连接服务器后可用';
