import type { StudySession } from '@/store/useStudyRoomStore';

// Only imported by the development fixture module. Vite's HMR socket stays real.
const RealWebSocket = window.WebSocket;
let session: StudySession | null = null;
class LocalStudySocket extends EventTarget {
  static readonly OPEN = 1;
  static readonly CLOSED = 3;
  readonly url: string;
  readyState = 0;
  onopen: ((event: Event) => void) | null = null;
  onclose: ((event: Event) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  private interval: ReturnType<typeof setInterval>;
  constructor(url: string | URL) {
    super();
    this.url = String(url);
    setTimeout(() => {
      if (this.readyState === 3) return;
      this.readyState = 1;
      this.onopen?.(new Event('open'));
      this.emit({ type: 'session.sync', session });
    }, 0);
    this.interval = setInterval(() => {
      if (session?.status !== 'active' || this.readyState !== 1) return;
      session.time_left = Math.max(0, Math.ceil((session.timer_end_ts! - Date.now() / 1000)));
      session.total_focus++;
      this.emit({ type: 'timer.tick', time_left: session.time_left });
      if (!session.time_left) { session.status = 'ended'; this.emit({ type: 'timer.expired', ...session }); }
    }, 1000);
  }
  private emit(data: object) { this.onmessage?.(new MessageEvent('message', { data: JSON.stringify(data) })); }
  send(text: string) {
    const message = JSON.parse(text);
    if (message.type === 'ping') { this.emit({ type: 'pong' }); return; }
    if (message.type === 'session.start') session = { status: 'active', task_name: message.task_name, duration: message.duration, time_left: message.duration * 60, timer_end_ts: Date.now() / 1000 + message.duration * 60, total_focus: 0 };
    if (message.type === 'session.pause' && session) { session.status = 'paused'; session.timer_end_ts = null; }
    if (message.type === 'session.resume' && session) { session.status = 'active'; session.timer_end_ts = Date.now() / 1000 + session.time_left; }
    if (message.type === 'session.end' && session) {
      this.emit({ type: 'session.ended', summary: { task_name: session.task_name, duration: session.duration, total_focus_seconds: session.total_focus } }); session = null;
    }
    this.emit({ type: 'session.sync', session });
  }
  close() { this.readyState = 3; clearInterval(this.interval); this.onclose?.(new Event('close')); }
}

window.WebSocket = new Proxy(RealWebSocket, {
  construct(target, args) {
    return new URL(String(args[0]), location.href).pathname === '/ws/study-room/'
      ? new LocalStudySocket(args[0]) : Reflect.construct(target, args);
  },
});
