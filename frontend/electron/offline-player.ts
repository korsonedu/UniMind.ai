import { randomUUID } from 'node:crypto';

type Checkpoint = { position: number; duration: number; ended_at: string };
type Payload = Checkpoint & { event_id: string; grant: string; version: string; watched_seconds: number; focused_seconds: number; started_at: string; is_finished: boolean };
type Queued = { courseId: number; payload: Payload };

export class OfflineProgress {
  private positions: Record<string, Checkpoint> = {};
  private queue: Queued[] = [];
  private rejected = 0;
  private generation = 0;
  private flight: Promise<void> | null = null;
  error: string | undefined;
  snapshot() { return { positions: this.positions, queue: this.queue, rejected: this.rejected, error: this.error }; }
  state() { return { pending: this.queue.length, rejected: this.rejected, ...(this.error ? { error: this.error } : {}) }; }
  position(id: number) { return this.positions[String(id)]?.position || 0; }
  clear() { this.generation++; this.positions = {}; this.queue = []; this.rejected = 0; this.error = undefined; this.flight = null; }
  restore(value: unknown) {
    this.clear();
    if (!value || typeof value !== 'object') return;
    const restored = value as Partial<ReturnType<OfflineProgress['snapshot']>>;
    if (restored.positions && typeof restored.positions === 'object') for (const [id, point] of Object.entries(restored.positions) as [string, Checkpoint][]) {
      if (/^[1-9]\d*$/.test(id) && point && Number.isFinite(point.position) && point.position >= 0 && Number.isFinite(point.duration) && Number.isFinite(Date.parse(point.ended_at))) this.positions[id] = point;
    }
    this.queue = Array.isArray(restored.queue) ? restored.queue.filter((event: Queued) => event && Number.isSafeInteger(event.courseId) && event.courseId > 0 && typeof event.payload?.event_id === 'string' && typeof event.payload.grant === 'string' && typeof event.payload.version === 'string') : [];
    this.rejected = typeof restored.rejected === 'number' && Number.isSafeInteger(restored.rejected) && restored.rejected >= 0 ? restored.rejected : 0;
    this.error = typeof restored.error === 'string' ? restored.error : undefined;
  }
  record(id: number, value: unknown, version: string, grant?: string) {
    const body = value as Record<string, unknown>;
    if (!body || typeof body !== 'object' || !Number.isFinite(body.position) || !Number.isFinite(body.duration) || !Number.isInteger(body.watched_seconds)
      || Number(body.duration) <= 0 || Number(body.position) < 0 || Number(body.position) > Number(body.duration) + 1 || Number(body.watched_seconds) < 0 || Number(body.watched_seconds) > Math.min(120, Number(body.duration))
      || !Number.isInteger(body.focused_seconds) || Number(body.focused_seconds) < 0 || Number(body.focused_seconds) > Number(body.watched_seconds)
      || typeof body.started_at !== 'string' || typeof body.ended_at !== 'string' || !Number.isFinite(Date.parse(body.started_at)) || !Number.isFinite(Date.parse(body.ended_at))
      || Date.parse(body.started_at) > Date.parse(body.ended_at) || Date.parse(body.ended_at) > Date.now() + 30000 || Number(body.watched_seconds) > (Date.parse(body.ended_at) - Date.parse(body.started_at)) / 1000 + 1
      || typeof body.is_finished !== 'boolean') throw new Error('无效学习记录');
    const checkpoint = { position: Number(body.position), duration: Number(body.duration), ended_at: body.ended_at };
    if (!this.positions[String(id)] || Date.parse(checkpoint.ended_at) >= Date.parse(this.positions[String(id)].ended_at)) this.positions[String(id)] = checkpoint;
    if (!grant) { this.error = '本地续播位置已保存，联网确认课程后才能同步学习记录'; return; }
    this.queue.push({ courseId: id, payload: { ...checkpoint, event_id: randomUUID(), version, grant, watched_seconds: Number(body.watched_seconds), focused_seconds: Number(body.focused_seconds), started_at: body.started_at, is_finished: body.is_finished } });
  }
  flush(send: (event: Queued) => Promise<'accepted' | 'rejected'>, persist: () => Promise<void>) {
    if (this.flight) return this.flight;
    const generation = this.generation;
    const flight = (async () => {
      while (this.queue.length && generation === this.generation) {
        const event = this.queue[0];
        try {
          const result = await send(event);
          if (generation !== this.generation) return;
          this.queue.shift();
          if (result === 'rejected') { this.rejected++; this.error = '部分离线记录未被服务器接收，本地续播位置已保留'; }
          else if (!this.rejected) this.error = undefined;
          await persist();
        } catch (error) {
          if (generation === this.generation) { this.error = error instanceof Error ? error.message : '离线记录暂未同步'; await persist(); }
          return;
        }
      }
    })().finally(() => { if (this.flight === flight) this.flight = null; });
    this.flight = flight;
    return flight;
  }
}

// Served only by the private offline protocol. This window has no preload or desktop IPC.
export const playerScript = String.raw`(() => {
  const video = document.querySelector('video');
  if (!video) return;
  const message = document.getElementById('sync-status');
  let previous = null, watched = 0, focused = 0, started = Date.now(), lastSave = Date.now(), chain = Promise.resolve();
  let statusTimer, statusAttempts = 0, closed = false;
  const showStatus = state => {
    clearTimeout(statusTimer);
    if (closed) return;
    message.textContent = state.error || (state.pending ? '离线记录已保存，待联网同步（' + state.pending + '）' : '学习记录已同步');
    if (state.pending) statusTimer = setTimeout(refreshStatus, statusAttempts++ < 60 ? (navigator.onLine ? 2000 : 5000) : 30000);
  };
  const refreshStatus = async () => {
    if (closed) return;
    try {
      const response = await fetch('/learning-status/' + video.dataset.course, { headers: { 'X-UniMind-Player': video.dataset.token } });
      if (response.ok) showStatus(await response.json());
    } catch { /* The saved checkpoint remains available; a later online event retries status. */ }
  };
  window.addEventListener('online', () => { statusAttempts = 0; void refreshStatus(); });
  const baseline = () => { previous = { position: video.currentTime, wall: Date.now() }; };
  const sample = () => {
    const now = Date.now();
    if (previous && !video.paused && !video.seeking) {
      const wall = (now - previous.wall) / 1000, media = video.currentTime - previous.position;
      // Large wall gaps include suspend/background throttling; seeking never counts as viewing.
      if (wall > 0 && wall <= 5 && media > 0 && media <= wall * video.playbackRate + 0.5) {
        const seconds = Math.min(wall, media / video.playbackRate);
        watched += seconds;
        if (!document.hidden && document.hasFocus()) focused += seconds;
      }
    }
    baseline();
  };
  const save = (finished = false) => {
    if (!Number.isFinite(video.duration) || video.duration <= 0) return;
    const now = Date.now(), seconds = Math.floor(watched), focusedSeconds = Math.min(seconds, Math.floor(focused));
    watched -= seconds; focused -= focusedSeconds;
    const body = JSON.stringify({ position: video.currentTime, duration: video.duration, watched_seconds: Math.min(120, seconds), focused_seconds: Math.min(120, focusedSeconds), started_at: new Date(started).toISOString(), ended_at: new Date(now).toISOString(), is_finished: finished });
    started = now - watched * 1000; lastSave = now; statusAttempts = 0;
    chain = chain.catch(() => {}).then(async () => {
      const response = await fetch('/progress/' + video.dataset.course, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-UniMind-Player': video.dataset.token }, body, keepalive: true });
      const state = await response.json().catch(() => ({ error: 'invalid_local_response' }));
      if (!response.ok) {
        const failure = new Error('local_request_rejected');
        failure.code = typeof state.error === 'string' && /^[a-z_]+$/.test(state.error) ? state.error : 'local_request_rejected';
        failure.status = response.status;
        throw failure;
      }
      if (state.error === 'invalid_local_response') throw new Error(state.error);
      showStatus(state);
    }).catch(error => {
      const code = typeof error?.code === 'string' && /^[a-z_]+$/.test(error.code) ? error.code : 'local_fetch_failed';
      console.warn('[UniMind offline checkpoint]', code, typeof error?.status === 'number' ? error.status : '');
      if (['login_required', 'login_credential_changed', 'player_identity_changed'].includes(code)) message.textContent = '登录状态已失效，请重新登录后再打开课程。';
      else if (code === 'course_unavailable_or_changed') message.textContent = '课程授权或视频已变更，请联网重新下载后播放。';
      else if (code === 'local_checkpoint_write_failed') message.textContent = '本地记录未保存，请检查磁盘剩余空间后重试。';
      else message.textContent = '本地记录未保存，请重新打开课程后重试。';
    });
  };
  const resumePosition = () => { const position = Number(video.dataset.position); if (position > 0 && position < video.duration) video.currentTime = position; baseline(); };
  video.addEventListener('loadedmetadata', resumePosition);
  if (video.readyState >= 1) resumePosition();
  video.addEventListener('play', baseline);
  video.addEventListener('timeupdate', () => { sample(); if (Date.now() - lastSave >= 15000) save(); });
  video.addEventListener('seeking', () => { previous = null; });
  video.addEventListener('seeked', () => { baseline(); save(); });
  video.addEventListener('pause', () => { sample(); save(video.ended); previous = null; });
  video.addEventListener('ended', () => { save(true); previous = null; });
  window.addEventListener('pagehide', () => { closed = true; clearTimeout(statusTimer); sample(); save(video.ended); });
})();`;
