import { app, session, net, safeStorage } from 'electron';
import { createHash, randomUUID } from 'node:crypto';
import { createReadStream, type ReadStream } from 'node:fs';
import { mkdir, open, readFile, readdir, rename, rm, stat, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { Readable } from 'node:stream';
import { sameOrigin, validSource } from './security';
import { OfflineProgress, playerScript } from './offline-player';

export type Download = { courseId: number; title: string; status: 'downloading' | 'paused' | 'ready' | 'failed'; receivedBytes: number; totalBytes: number; expiresAt?: number; error?: string };
type Cached = Download & { version: string; grant?: string };
type DownloadJob = { controller: AbortController; done: Promise<void>; paused?: boolean; removing?: Promise<void> };
type Manifest = { grant?: string; user_id: number; course_id: number; title: string; expires_at: number; version: string; video: { url: string; filename: string; size: number } };
const escape = (value: string) => value.replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]!));
export const courseId = (value: unknown): number => {
  if (!Number.isSafeInteger(value) || Number(value) <= 0) throw new Error('无效课程');
  return value as number;
};

export class OfflineLibrary {
  private actor: number | null = null;
  private credential = '';
  private locked = false;
  private leaseExpiresAt = 0;
  private dataWrites: Promise<void> = Promise.resolve();
  private entries: Cached[] = [];
  private jobs = new Map<number, DownloadJob>();
  private pending = new Set<Promise<void>>();
  private cleanup: Promise<void> = Promise.resolve();
  private epoch = 0;
  private syncFlight: Promise<void> | null = null;
  private streams = new Map<number, Set<ReadStream>>();
  private writes: Promise<void> = Promise.resolve();
  private usedBytes = 0;
  private playerTokens = new Map<string, { actor: number; epoch: number; course: number; version: string; grant?: string }>();
  private learning = new OfflineProgress();
  private root = path.join(app.getPath('userData'), 'offline');
  constructor(private source: string, private changed: () => void, private identityChanged: () => void) {}
  private async fingerprint() {
    const cookies = await session.defaultSession.cookies.get({ url: this.source, name: 'auth_token' });
    return cookies.length ? createHash('sha256').update(cookies[0].value).digest('hex') : '';
  }
  private file(id: number) { return path.join(this.root, String(this.actor), `${id}.video`); }
  private persist() {
    const write = this.writes.catch(() => {}).then(async () => {
      await mkdir(this.root, { recursive: true, mode: 0o700 });
      const actor = this.actor;
      let usedBytes = 0;
      if (actor) for (const filename of await readdir(path.join(this.root, String(actor))).catch(() => [] as string[])) {
        if (/^[1-9]\d*\.video(?:\.part)?$/.test(filename)) usedBytes += (await stat(path.join(this.root, String(actor), filename)).catch(() => ({ size: 0 }))).size;
      }
      if (actor === this.actor) this.usedBytes = usedBytes;
      const file = path.join(this.root, 'active.json');
      await writeFile(`${file}.tmp`, JSON.stringify({ origin: new URL(this.source).origin, actor: this.actor, credential: this.credential, locked: this.locked, leaseExpiresAt: this.leaseExpiresAt, entries: this.entries, learning: this.learning.snapshot() }), { mode: 0o600 });
      await rename(`${file}.tmp`, file);
    });
    this.writes = write;
    return write;
  }
  storage() { return { usedBytes: this.usedBytes }; }
  learningSync() { return this.learning.state(); }
  offlineSession() {
    return this.actor && !this.locked && this.leaseExpiresAt > Date.now()
      ? { userId: this.actor, expiresAt: this.leaseExpiresAt }
      : null;
  }
  private offlineDataFile() {
    return this.actor ? path.join(this.root, String(this.actor), 'notes.bin') : null;
  }
  async readOfflineData(): Promise<unknown | null> {
    const file = this.offlineDataFile();
    if (!file || !this.offlineSession() || !safeStorage.isEncryptionAvailable()) return null;
    try {
      const text = safeStorage.decryptString(await readFile(file));
      return JSON.parse(text);
    } catch {
      return null;
    }
  }
  async writeOfflineData(value: unknown): Promise<void> {
    const file = this.offlineDataFile();
    if (!file || !this.offlineSession()) throw new Error('离线数据不可用，请先联网同步账号');
    if (!safeStorage.isEncryptionAvailable()) throw new Error('系统加密不可用，无法保存离线笔记');
    const text = JSON.stringify(value);
    if (Buffer.byteLength(text) > 8 * 1024 * 1024) throw new Error('离线数据超过 8 MB');
    const encrypted = safeStorage.encryptString(text);
    const write = this.dataWrites.catch(() => {}).then(async () => {
      await mkdir(path.dirname(file), { recursive: true, mode: 0o700 });
      await writeFile(`${file}.tmp`, encrypted, { mode: 0o600 });
      await rename(`${file}.tmp`, file);
    });
    this.dataWrites = write;
    return write;
  }
  async clearOfflineData(): Promise<void> {
    const file = this.offlineDataFile();
    if (file) await rm(file, { force: true });
  }
  async restore() {
    try {
      const stored = JSON.parse(await readFile(path.join(this.root, 'active.json'), 'utf8'));
      const credential = await this.fingerprint();
      if (stored.origin !== new URL(this.source).origin || !Number.isSafeInteger(stored.actor) || stored.actor <= 0) return;
      this.actor = stored.actor; this.credential = stored.credential; this.locked = stored.locked === true || !credential || credential !== this.credential;
      this.leaseExpiresAt = Number.isFinite(stored.leaseExpiresAt) ? stored.leaseExpiresAt : 0;
      this.entries = (Array.isArray(stored.entries) ? stored.entries : []).filter((e: Cached) => e && Number.isSafeInteger(e.courseId) && e.courseId > 0 && ['ready', 'downloading', 'paused', 'failed'].includes(e.status) && typeof e.version === 'string' && Number.isSafeInteger(e.totalBytes) && e.totalBytes > 0 && Number.isFinite(e.expiresAt) && e.expiresAt! > Date.now());
      this.learning.restore(stored.learning);
      for (const entry of this.entries) {
        if (entry.status === 'downloading') entry.status = 'paused';
        const info = await stat(`${this.file(entry.courseId)}${entry.status === 'ready' ? '' : '.part'}`).catch(() => null);
        if (!info || info.size > entry.totalBytes || (entry.status === 'ready' && info.size !== entry.totalBytes)) { entry.status = 'failed'; entry.receivedBytes = 0; }
        else entry.receivedBytes = info.size;
      }
      const directory = path.join(this.root, String(this.actor));
      const retained = new Set(this.entries.map(entry => entry.courseId));
      for (const filename of await readdir(directory).catch(() => [] as string[])) {
        const match = /^([1-9]\d*)\.video(\.part)?$/.exec(filename);
        if (match && Number.isSafeInteger(Number(match[1])) && (!retained.has(Number(match[1])) || (match[2] && this.entries.some(e => e.courseId === Number(match[1]) && e.status === 'ready')))) await rm(path.join(directory, filename), { force: true });
      }
      await this.persist();
    } catch { /* First launch has no offline library. */ }
  }
  list(): Download[] {
    return this.actor && !this.locked ? this.entries.filter(e => !e.expiresAt || e.expiresAt > Date.now()).map(entry => ({ courseId: entry.courseId, title: entry.title, status: entry.status, receivedBytes: entry.receivedBytes, totalBytes: entry.totalBytes, expiresAt: entry.expiresAt, error: entry.error })) : [];
  }
  async logout(waitForJobs = true, preserveSync = false) {
    if (!preserveSync) this.syncFlight = null;
    const oldDirectory = this.actor ? path.join(this.root, String(this.actor)) : null;
    const pending = [...this.pending];
    this.epoch++; for (const job of this.jobs.values()) job.controller.abort(); this.jobs.clear();
    for (const streams of this.streams.values()) for (const stream of streams) stream.destroy();
    this.streams.clear();
    this.actor = null; this.credential = ''; this.locked = false; this.leaseExpiresAt = 0; this.entries = []; this.usedBytes = 0; this.playerTokens.clear(); this.learning.clear(); this.identityChanged();
    const cleanup = this.cleanup.then(async () => {
      await Promise.allSettled(pending);
      if (oldDirectory) await rm(oldDirectory, { recursive: true, force: true });
    });
    this.cleanup = cleanup;
    await this.persist(); this.changed();
    if (waitForJobs) await cleanup; else void cleanup.catch(() => {});
  }
  async json(route: string, body?: unknown) {
    const cookies = await session.defaultSession.cookies.get({ url: this.source, name: 'csrftoken' });
    const response = await session.defaultSession.fetch(new URL(route, this.source).href, {
      method: body ? 'POST' : 'GET', credentials: 'include', redirect: 'error', signal: AbortSignal.timeout(10000),
      headers: { 'Content-Type': 'application/json', ...(cookies[0] ? { 'X-CSRFToken': cookies[0].value } : {}) },
      ...(body ? { body: JSON.stringify(body) } : {}),
    });
    if (response.status === 401 || (response.status === 403 && route === '/api/users/me/')) { await this.lock(); throw new Error('请重新登录后同步离线记录'); }
    if (!response.ok) throw Object.assign(new Error(`课程授权复核失败（${response.status}）`), { status: response.status });
    return response.json();
  }
  sync(): Promise<void> {
    if (this.syncFlight) return this.syncFlight;
    const flight = this.syncIdentity().finally(() => { if (this.syncFlight === flight) this.syncFlight = null; });
    this.syncFlight = flight;
    return flight;
  }
  private async syncIdentity() {
    let epoch = this.epoch;
    const user = await this.json('/api/users/me/');
    if (epoch !== this.epoch) throw new Error('账号已变更，请重试');
    if (!Number.isSafeInteger(user.id) || user.id <= 0) throw new Error('无法确认账号');
    const fingerprint = await this.fingerprint();
    if (epoch !== this.epoch) throw new Error('账号已变更，请重试');
    if (!fingerprint) throw new Error('请先登录');
    if (this.actor !== user.id) {
      await this.logout(true, true);
      epoch++;
      if (epoch !== this.epoch) throw new Error('账号已变更，请重试');
      this.actor = user.id;
    }
    this.credential = fingerprint; this.locked = false;
    this.leaseExpiresAt = Date.now() + 86400000;
    await this.persist();
    try { await this.review(); } catch (error) {
      // A course permission failure must not prevent authenticated events receiving a terminal result.
      if (epoch === this.epoch) await this.flushLearning();
      throw error;
    }
    if (epoch === this.epoch && this.learning.error === '请重新登录后同步离线记录') this.learning.error = undefined;
    if (epoch === this.epoch) await this.flushLearning();
    if (epoch !== this.epoch) throw new Error('账号已变更，请重试');
    await this.persist();
    if (epoch !== this.epoch) throw new Error('账号已变更，请重试');
    this.changed();
  }
  private async review() {
    if (!this.actor) return;
    for (const entry of [...this.entries]) if (!Number.isFinite(entry.expiresAt) || entry.expiresAt! <= Date.now()) await this.remove(entry.courseId);
    if (!this.entries.length) return;
    const actor = this.actor; const epoch = this.epoch;
    let result;
    try { result = await this.json('/api/courses/offline-access/', { course_ids: this.entries.map(e => e.courseId) }); } catch (error) {
      if ((error as { status?: number }).status === 403) for (const entry of [...this.entries]) {
        if (epoch !== this.epoch) break;
        await this.remove(entry.courseId);
      }
      throw error;
    }
    if (epoch !== this.epoch || result.user_id !== actor) { if (epoch === this.epoch) await this.logout(); throw new Error('账号已变更'); }
    const granted = new Map<number, Manifest>(result.courses.map((m: Manifest) => [m.course_id, m]));
    for (const entry of [...this.entries]) {
      const manifest = granted.get(entry.courseId);
      if ((entry.expiresAt || 0) <= Date.now() || !manifest || manifest.version !== entry.version || !Number.isFinite(manifest.expires_at) || manifest.expires_at * 1000 <= Date.now()) await this.remove(entry.courseId);
      else { entry.expiresAt = Math.min(entry.expiresAt || 0, manifest.expires_at * 1000); if (typeof manifest.grant === 'string') entry.grant = manifest.grant; }
    }
    await this.persist();
  }
  remove(id: number): Promise<void> {
    courseId(id);
    let job = this.jobs.get(id);
    if (job?.removing) return job.removing;
    if (!job) {
      job = { controller: new AbortController(), done: Promise.resolve() };
      this.jobs.set(id, job);
    }
    const current = job;
    const file = this.file(id);
    current.controller.abort();
    current.removing = (async () => {
      await current.done;
      for (const stream of this.streams.get(id) || []) stream.destroy();
      this.streams.delete(id);
      this.entries = this.entries.filter(e => e.courseId !== id);
      for (const [token, player] of this.playerTokens) if (player.course === id) this.playerTokens.delete(token);
      await Promise.all([rm(file, { force: true }), rm(`${file}.part`, { force: true })]);
      await this.persist(); this.changed();
    })().finally(() => {
      this.pending.delete(current.removing!);
      if (this.jobs.get(id) === current) this.jobs.delete(id);
    });
    this.pending.add(current.removing);
    return current.removing;
  }
  async pause(id: number) {
    courseId(id);
    const job = this.jobs.get(id);
    if (!job || job.removing) return;
    job.paused = true; job.controller.abort();
    await job.done;
  }
  suspend() {
    this.playerTokens.clear();
    for (const [id, job] of this.jobs) if (!job.removing) void this.pause(id).catch(() => {});
  }
  async download(id: number): Promise<void> {
    courseId(id); await this.sync();
    const startEpoch = this.epoch;
    const existing = this.jobs.get(id);
    if (existing) {
      if (existing.removing) { await existing.removing; return this.download(id); }
      return;
    }
    if (this.entries.length >= 100 && !this.entries.some(e => e.courseId === id)) throw new Error('请先移除部分离线课程（最多100节）');
    const controller = new AbortController();
    let finish!: () => void;
    const job: DownloadJob = { controller, done: new Promise<void>(resolve => { finish = resolve; }) };
    this.jobs.set(id, job); this.pending.add(job.done);
    void job.done.finally(() => this.pending.delete(job.done));
    let handle: Awaited<ReturnType<typeof open>> | undefined;
    let entry: Cached | undefined;
    try {
      const manifest: Manifest = await this.json(`/api/courses/${id}/offline-manifest/`);
      if (controller.signal.aborted) throw new Error('下载已暂停');
      if (startEpoch !== this.epoch) throw new Error('账号已变更，请重新下载');
      if (manifest.user_id !== this.actor || manifest.course_id !== id || typeof manifest.title !== 'string' || typeof manifest.version !== 'string' || !Number.isFinite(manifest.expires_at) || !Number.isSafeInteger(manifest.video?.size) || manifest.video.size <= 0 || !sameOrigin(this.source, new URL(manifest.video.url, this.source).href)) throw new Error('无效下载授权');
      const expiresAt = Math.min(Date.now() + 86400000, manifest.expires_at * 1000);
      if (expiresAt <= Date.now()) throw new Error('课程授权已到期');
      const file = this.file(id);
      const previous = this.entries.find(e => e.courseId === id);
      if (previous?.status === 'ready' && previous.version === manifest.version && previous.totalBytes === manifest.video.size && (await stat(file).catch(() => null))?.size === manifest.video.size) {
        if (this.jobs.get(id) === job) this.jobs.delete(id); finish(); return;
      }
      let offset = 0;
      if (previous && previous.version === manifest.version && previous.totalBytes === manifest.video.size) {
        offset = (await stat(`${file}.part`).catch(() => ({ size: 0 }))).size;
        if (offset > manifest.video.size) offset = 0;
      }
      entry = { courseId: id, title: manifest.title, status: 'downloading', receivedBytes: offset, totalBytes: manifest.video.size, expiresAt, version: manifest.version, grant: manifest.grant };
      this.entries = [...this.entries.filter(e => e.courseId !== id), entry];
      await mkdir(path.dirname(file), { recursive: true, mode: 0o700 });
      await this.persist(); this.changed();
      const activeEntry = entry;
      // Keep the per-course lock until the background transfer and all persistence finish.
      const task = (async () => {
        try {
          const fetchMedia = async (start: number) => {
            let url = new URL(manifest.video.url, this.source).href;
            for (let redirects = 0; redirects <= 5; redirects++) {
              if (!validSource(url, true) || (!sameOrigin(this.source, url) && new URL(url).protocol !== 'https:')) throw new Error('不安全的媒体地址');
              const response = await session.defaultSession.fetch(url, { redirect: 'manual', credentials: sameOrigin(this.source, url) ? 'include' : 'omit', signal: controller.signal, headers: start ? { Range: `bytes=${start}-` } : {} });
              if (![301, 302, 303, 307, 308].includes(response.status)) return response;
              const location = response.headers.get('location'); if (!location) throw new Error('媒体重定向无效');
              url = new URL(location, url).href;
            }
            throw new Error('媒体重定向过多');
          };
          if (offset < manifest.video.size) {
            let response = await fetchMedia(offset);
            if (offset && response.status === 206) {
              const range = /^bytes (\d+)-(\d+)\/(\d+)$/.exec(response.headers.get('content-range') || '');
              if (!range || Number(range[1]) !== offset || Number(range[2]) !== manifest.video.size - 1 || Number(range[3]) !== manifest.video.size) {
                await response.body?.cancel(); offset = 0; response = await fetchMedia(0);
              }
            } else if (offset) {
              // A server without Range support safely replaces the partial download.
              offset = 0;
              if (response.status !== 200) { await response.body?.cancel(); response = await fetchMedia(0); }
            }
            if (!response.ok || !response.body || (!offset && response.status !== 200)) throw new Error(`下载失败（${response.status}）`);
            activeEntry.receivedBytes = offset;
            handle = await open(`${file}.part`, offset ? 'a' : 'w', 0o600);
            const reader = response.body.getReader(); let lastProgress = 0;
            while (true) {
              const { done, value } = await reader.read(); if (done) break;
              if (controller.signal.aborted || startEpoch !== this.epoch) throw new Error('下载已暂停');
              if (activeEntry.receivedBytes + value.byteLength > activeEntry.totalBytes) { await reader.cancel(); throw new Error('媒体大小与授权不符'); }
              await handle.writeFile(value); activeEntry.receivedBytes += value.byteLength;
              if (Date.now() - lastProgress > 1000) { await this.persist(); this.changed(); lastProgress = Date.now(); }
            }
            await handle.close(); handle = undefined;
          }
          if (activeEntry.receivedBytes !== activeEntry.totalBytes) throw new Error('下载不完整，请重试');
          const confirmation: Manifest = await this.json(`/api/courses/${id}/offline-manifest/`);
          if (controller.signal.aborted || startEpoch !== this.epoch || confirmation.user_id !== this.actor || confirmation.course_id !== id || confirmation.version !== manifest.version || confirmation.video?.size !== manifest.video.size || confirmation.expires_at * 1000 <= Date.now()) throw new Error('下载授权已变更');
          activeEntry.expiresAt = Math.min(expiresAt, confirmation.expires_at * 1000);
          await rename(`${file}.part`, file); activeEntry.status = 'ready'; await this.persist(); this.changed();
        } catch (error) {
          await handle?.close(); handle = undefined;
          if (startEpoch === this.epoch && this.entries.includes(activeEntry)) {
            activeEntry.status = job.paused ? 'paused' : 'failed'; activeEntry.error = job.paused ? undefined : String(error instanceof Error ? error.message : error);
            await this.persist(); this.changed();
          }
        } finally {
          if (!job.removing && this.jobs.get(id) === job) this.jobs.delete(id);
          finish();
        }
      })();
      void task.catch(() => {});
    } catch (error) {
      if (job.paused && startEpoch === this.epoch) {
        const prior = this.entries.find(e => e.courseId === id && e.status !== 'ready');
        if (prior) { prior.status = 'paused'; await this.persist(); this.changed(); }
      }
      if (!job.removing && this.jobs.get(id) === job) this.jobs.delete(id);
      finish();
      if (!job.paused) throw error;
    }
  }
  async lock() {
    this.locked = true; this.epoch++; this.playerTokens.clear();
    for (const entry of this.entries) if (entry.status === 'downloading') entry.status = 'paused';
    for (const [id, job] of this.jobs) if (!job.removing) void this.pause(id).catch(() => {});
    for (const streams of this.streams.values()) for (const stream of streams) stream.destroy();
    this.streams.clear(); this.identityChanged();
    this.learning.error = '请重新登录后同步离线记录';
    await this.persist(); this.changed();
  }
  private async flushLearning() {
    if (!this.actor || this.locked || !net.isOnline()) return;
    const actor = this.actor; const epoch = this.epoch;
    await this.learning.flush(async event => {
      if (this.locked || this.actor !== actor || this.epoch !== epoch || this.credential !== await this.fingerprint()) throw new Error('请重新登录后同步离线记录');
      const cookies = await session.defaultSession.cookies.get({ url: this.source, name: 'csrftoken' });
      const response = await session.defaultSession.fetch(new URL(`/api/courses/${event.courseId}/offline-progress/`, this.source).href, {
        method: 'POST', credentials: 'include', redirect: 'error', signal: AbortSignal.timeout(10000),
        headers: { 'Content-Type': 'application/json', ...(cookies[0] ? { 'X-CSRFToken': cookies[0].value } : {}) },
        body: JSON.stringify(event.payload),
      });
      if (this.actor !== actor || this.epoch !== epoch) throw new Error('账号已变更');
      if (response.status === 401) { await this.lock(); throw new Error('请重新登录后同步离线记录'); }
      if (response.ok) return 'accepted';
      const result = await response.json().catch(() => ({}));
      if (response.status >= 400 && response.status < 500 && result.terminal === true) return 'rejected';
      throw new Error(`离线学习记录暂未同步（${response.status}）`);
    }, () => this.persist());
    this.changed();
  }
  private async authorize() {
    if (!this.actor || this.locked || this.credential !== await this.fingerprint()) { await this.lock(); throw new Error('请在线登录后再打开离线课程'); }
    if (!net.isOnline()) return;
    // A network transport failure permits an unexpired cached authorization.
    // HTTP failures and permission revocation never fall back to cached access.
    try { await this.sync(); } catch (error) {
      const message = String(error);
      if (!this.actor || !/ERR_(?:INTERNET_DISCONNECTED|NETWORK_CHANGED|NAME_NOT_RESOLVED|CONNECTION|TIMED_OUT)|fetch failed|TimeoutError/.test(message)) throw error;
    }
  }
  async respond(request: Request, trustedPrivateWindow = false): Promise<Response> {
    const url = new URL(request.url);
    if (url.protocol !== 'unimind-offline:' || url.host !== 'library' || !['GET', 'POST'].includes(request.method)) return new Response('Not found', { status: 404 });
    try {
      const parts = url.pathname.split('/').filter(Boolean);
      const statusRequest = request.method === 'GET' && parts[0] === 'learning-status';
      if (request.method === 'POST' || statusRequest) {
        const reject = (error: string, status = 403) => Response.json({ error }, { status, headers: { 'Cache-Control': 'no-store' } });
        if (parts.length !== 2 || parts[0] !== (statusRequest ? 'learning-status' : 'progress')) return reject('invalid_progress_route', 404);
        const token = this.playerTokens.get(request.headers.get('x-unimind-player') || '');
        if (!token) return reject('player_token_missing_or_expired');
        if (token.actor !== this.actor || token.epoch !== this.epoch || token.course !== Number(parts[1])) return reject('player_identity_changed');
        if (this.locked) return reject('login_required');
        if (this.credential !== await this.fingerprint()) return reject('login_credential_changed');
        const origin = request.headers.get('origin');
        // Electron may carry Chromium's Referer header without setting Request.referrer.
        const referrer = request.headers.get('referer') || request.referrer;
        const hasReferrer = !!referrer && referrer !== 'about:client';
        const privateOrigin = origin === 'unimind-offline://library';
        const privateReferrer = referrer === `unimind-offline://library/course/${token.course}`;
        if ((origin && !privateOrigin) || (hasReferrer && !privateReferrer) || (!origin && !hasReferrer && !trustedPrivateWindow)) {
          const originKind = !origin ? 'missing' : privateOrigin ? 'private' : origin === 'null' ? 'opaque' : 'other';
          const referrerKind = !hasReferrer ? 'missing' : privateReferrer ? 'private' : 'other';
          return reject(`player_origin_${originKind}_referrer_${referrerKind}`);
        }
        const entry = this.entries.find(e => e.courseId === token.course && e.status === 'ready' && (e.expiresAt || 0) > Date.now());
        if (!entry || entry.version !== token.version) return reject('course_unavailable_or_changed');
        if (statusRequest) return Response.json({ ...this.learning.state(), ...(!entry.grant ? { error: '本地续播位置会保存，联网确认课程后才能同步学习记录' } : {}) }, { headers: { 'Cache-Control': 'no-store' } });
        const body = await request.text();
        if (body.length > 4096) return reject('progress_payload_too_large', 413);
        try { this.learning.record(token.course, JSON.parse(body), token.version, token.grant); }
        catch { return reject('invalid_progress_payload', 400); }
        try { await this.persist(); }
        catch { return reject('local_checkpoint_write_failed', 500); }
        this.changed();
        void this.flushLearning().catch(() => {});
        return Response.json(this.learning.state(), { headers: { 'Cache-Control': 'no-store' } });
      }
      await this.authorize();
      if (url.pathname === '/player.js') return new Response(playerScript, { headers: { 'Content-Type': 'application/javascript; charset=utf-8', 'Cache-Control': 'no-store' } });
      if (parts[0] === 'video') {
        const id = courseId(Number(parts[1]));
        const entry = this.entries.find(e => e.courseId === id && e.status === 'ready' && (e.expiresAt || 0) > Date.now());
        if (!entry) throw new Error('离线授权已过期或已撤销，请联网重新下载');
        const file = this.file(id); const info = await stat(file);
        if (info.size !== entry.totalBytes) throw new Error('本地视频不完整，请重新下载');
        const range = request.headers.get('range');
        let start = 0; let end = info.size - 1;
        if (range) {
          const match = /^bytes=(\d*)-(\d*)$/.exec(range);
          if (!match || (!match[1] && !match[2])) return new Response(null, { status: 416, headers: { 'Content-Range': `bytes */${info.size}` } });
          if (!match[1]) start = Math.max(0, info.size - Number(match[2]));
          else { start = Number(match[1]); if (match[2]) end = Math.min(Number(match[2]), end); }
          if (!Number.isSafeInteger(start) || !Number.isSafeInteger(end) || start > end || start >= info.size) return new Response(null, { status: 416, headers: { 'Content-Range': `bytes */${info.size}` } });
        }
        const input = createReadStream(file, { start, end });
        const active = this.streams.get(id) || new Set<ReadStream>(); active.add(input); this.streams.set(id, active);
        const expires = setTimeout(() => input.destroy(), Math.max(1, entry.expiresAt! - Date.now()));
        input.once('close', () => { clearTimeout(expires); active.delete(input); if (!active.size) this.streams.delete(id); });
        const stream = Readable.toWeb(input) as ReadableStream<Uint8Array>;
        return new Response(stream, { status: range ? 206 : 200, headers: { 'Content-Type': 'video/mp4', 'Accept-Ranges': 'bytes', 'Content-Length': String(end - start + 1), 'Cache-Control': 'no-store', ...(range ? { 'Content-Range': `bytes ${start}-${end}/${info.size}` } : {}) } });
      }
      const entry = parts[0] === 'course' ? this.entries.find(e => e.courseId === Number(parts[1]) && e.status === 'ready' && (e.expiresAt || 0) > Date.now()) : null;
      if (parts.length && !entry) throw new Error('课程不可用，请联网重新下载');
      const token = entry ? randomUUID() : '';
      if (entry) { this.playerTokens.set(token, { actor: this.actor!, epoch: this.epoch, course: entry.courseId, version: entry.version, grant: entry.grant }); }
      // A single private player window is reused; retain a small allowance for an outgoing pagehide save.
      if (this.playerTokens.size > 20) this.playerTokens.delete(this.playerTokens.keys().next().value!);
      const sync = this.learning.state();
      const content = entry ? `<a href="/">← 离线课程库</a><h1>${escape(entry.title)}</h1><video controls src="/video/${entry.courseId}" data-course="${entry.courseId}" data-token="${token}" data-position="${this.learning.position(entry.courseId)}"></video><p id="sync-status">${escape(!entry.grant ? '本地续播位置会保存，联网确认课程后才能同步学习记录' : sync.error || (sync.pending ? `离线记录已保存，待同步（${sync.pending}）` : '播放位置会保存在本机，联网后同步真实观看记录'))}</p><p>离线授权到期：${escape(new Date(entry.expiresAt!).toLocaleString('zh-CN'))}</p><script src="/player.js" defer></script>` : `<h1>离线课程库</h1><p>当前账号已下载的课程。授权最多保留24小时，联网时会重新确认课程权限。</p>${this.list().filter(e => e.status === 'ready').map(e => `<article><a href="/course/${e.courseId}">${escape(e.title)}</a><p>有效至 ${escape(new Date(e.expiresAt!).toLocaleString('zh-CN'))}</p></article>`).join('') || '<p>暂无可用的离线课程，请联网登录并下载。</p>'}`;
      return this.page(content);
    } catch (error) { return this.page(`<h1>暂时无法播放</h1><p>${escape(error instanceof Error ? error.message : '请联网后重试')}</p><a href="/">返回课程库</a>`, 403); }
  }
  private page(content: string, status = 200) {
    return new Response(`<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>UniMind · 离线课程</title><style>body{font:16px/1.7 system-ui;background:#f5f4f0;color:#242424;margin:48px auto;padding:0 24px;max-width:1050px}h1{font-size:30px}a{color:#345a46}article{border-top:1px solid #d8d7d0;padding:20px 0}p{color:#666}video{width:100%;max-height:72vh;background:#111}</style>${content}</html>`, { status, headers: { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store', 'Content-Security-Policy': "default-src 'none'; script-src 'self'; connect-src 'self'; style-src 'unsafe-inline'; media-src 'self'; frame-ancestors 'none'" } });
  }
}
