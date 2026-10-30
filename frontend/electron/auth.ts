import { session, shell } from 'electron';
import { createHash, randomBytes, timingSafeEqual } from 'node:crypto';

export type AuthState = { status: 'idle' | 'opening' | 'waiting' | 'completing' | 'authenticated' | 'error'; error?: string; expiresAt?: number };
type Attempt = { state: string; verifier: string; controller: AbortController; expiresAt: number; timer: ReturnType<typeof setTimeout>; browserUrl?: string; claimed: boolean; completion?: Promise<void> };
const token = /^[A-Za-z0-9_-]{43}$/;

export class DesktopAuth {
  state: AuthState = { status: 'idle' };
  private attempt: Attempt | undefined;
  private generation = 0;
  private cleanup: Promise<void> = Promise.resolve();
  constructor(private source: string, private changed: () => void, private authenticated: () => void) {}
  private publish(state: AuthState) { this.state = state; this.changed(); }
  private invalidate() {
    const old = this.attempt; this.attempt = undefined;
    if (old) { clearTimeout(old.timer); old.controller.abort(); }
    this.cleanup = this.cleanup.then(() => old?.completion).then(() => {});
    return this.cleanup;
  }
  private current(attempt: Attempt) { return this.attempt === attempt && !attempt.controller.signal.aborted && Date.now() < attempt.expiresAt; }
  private ensureCurrent(attempt: Attempt) { if (!this.current(attempt)) throw new Error('本次登录已取消或超时，请重新开始'); }
  private async request(route: string, attempt: Attempt, body?: unknown) {
    const response = await session.defaultSession.fetch(new URL(route, this.source).href, {
      method: body ? 'POST' : 'GET', credentials: 'include', redirect: 'error',
      signal: AbortSignal.any([attempt.controller.signal, AbortSignal.timeout(15000)]),
      headers: { 'Accept': 'application/json', ...(body ? { 'Content-Type': 'application/json' } : {}) },
      ...(body ? { body: JSON.stringify(body) } : {}),
    }).catch(() => { throw new Error('暂时无法连接登录服务，请检查网络后重试'); });
    if (!response.ok) throw new Error(response.status === 401 || response.status === 403 ? '登录确认已失效，请重新开始' : '登录服务暂时不可用，请稍后重试');
    return response.json().catch(() => { throw new Error('登录服务返回异常，请稍后重试'); });
  }
  async start() {
    const waiting = this.attempt;
    if (waiting && this.current(waiting) && !waiting.claimed && waiting.browserUrl && this.state.status === 'waiting') {
      try { await shell.openExternal(waiting.browserUrl); }
      catch { if (this.current(waiting)) this.publish({ status: 'waiting', expiresAt: waiting.expiresAt, error: '无法打开系统浏览器，请重试或取消后重新开始' }); }
      return;
    }
    const generation = ++this.generation;
    const cleanup = this.invalidate();
    this.publish({ status: 'opening' });
    await cleanup;
    if (generation !== this.generation) return;
    const verifier = randomBytes(32).toString('base64url');
    const attempt: Attempt = {
      state: randomBytes(32).toString('base64url'), verifier, controller: new AbortController(),
      expiresAt: Date.now() + 180000, claimed: false,
      timer: setTimeout(() => { if (this.attempt === attempt) { this.generation++; void this.invalidate().catch(() => this.publish({ status: 'error', error: '无法清理未完成的登录，请退出客户端后重试' })); this.publish({ status: 'error', error: '登录已超时，请重新开始' }); } }, 180000),
    };
    this.attempt = attempt;
    try {
      const result = await this.request('/api/users/desktop-auth/start/', attempt, { state: attempt.state, code_challenge: createHash('sha256').update(verifier).digest('base64url') });
      this.ensureCurrent(attempt);
      if (!result || typeof result.request_id !== 'string' || !token.test(result.request_id) || result.expires_in !== 180) throw new Error('登录服务返回了无效请求，请重试');
      const browser = new URL('/accounts/desktop/', this.source);
      browser.searchParams.set('request', result.request_id);
      attempt.browserUrl = browser.href;
      this.publish({ status: 'waiting', expiresAt: attempt.expiresAt });
      await shell.openExternal(browser.href).catch(() => { throw new Error('无法打开系统浏览器，请检查默认浏览器设置后重试'); });
    } catch (error) {
      if (this.attempt !== attempt || attempt.claimed) return;
      const generation = ++this.generation; await this.invalidate();
      if (generation === this.generation) this.publish({ status: 'error', error: error instanceof Error ? error.message : '无法打开系统浏览器，请重试' });
    }
  }
  async cancel() {
    const generation = ++this.generation;
    const cleanup = this.invalidate();
    this.publish({ status: 'idle' });
    await cleanup;
    if (generation === this.generation) this.publish({ status: 'idle' });
  }
  receive(value: string): boolean {
    if (!value.startsWith('unimind://auth/callback?') || value.length > 256 || value.includes('#') || /[\u0000-\u0020\\]/.test(value)) return false;
    let url: URL;
    try { url = new URL(value); } catch { return false; }
    if (url.protocol !== 'unimind:' || url.hostname !== 'auth' || url.port || url.username || url.password || url.pathname !== '/callback' || url.hash || url.search.slice(1).split('&').length !== 2) return false;
    const params = [...url.searchParams];
    if (params.length !== 2 || url.searchParams.getAll('code').length !== 1 || url.searchParams.getAll('state').length !== 1) return false;
    const code = url.searchParams.get('code')!, state = url.searchParams.get('state')!;
    const attempt = this.attempt;
    if (!attempt || this.state.status !== 'waiting' || !this.current(attempt) || attempt.claimed || !token.test(code) || !token.test(state) || !timingSafeEqual(Buffer.from(state), Buffer.from(attempt.state))) return false;
    attempt.claimed = true;
    this.publish({ status: 'completing', expiresAt: attempt.expiresAt });
    attempt.completion = this.complete(attempt, code);
    void attempt.completion.catch(() => this.publish({ status: 'error', error: '无法清理未完成的登录，请退出客户端后重试' }));
    return true;
  }
  private async complete(attempt: Attempt, code: string) {
    let before: Electron.Cookie[] = [], exchanged = false, committed = false;
    try {
      before = await session.defaultSession.cookies.get({ url: this.source, name: 'auth_token' });
      this.ensureCurrent(attempt);
      exchanged = true;
      const result = await this.request('/api/users/desktop-auth/exchange/', attempt, { code, code_verifier: attempt.verifier });
      this.ensureCurrent(attempt);
      if (result?.ok !== true) throw new Error('登录确认失败，请重新开始');
      const user = await this.request('/api/users/me/', attempt);
      this.ensureCurrent(attempt);
      if (!Number.isSafeInteger(user?.id) || user.id <= 0) throw new Error('无法确认登录账号，请重新开始');
      clearTimeout(attempt.timer); this.attempt = undefined; committed = true;
      this.publish({ status: 'authenticated' });
      this.authenticated();
    } catch (error) {
      if (this.attempt === attempt) this.publish({ status: 'error', error: error instanceof Error ? error.message : '登录确认失败，请重试' });
    } finally {
      if (!committed && exchanged) {
        // New starts wait for this cleanup, so a cancelled exchange cannot leave
        // its cookie behind or delete a later login's credential.
        const cookies = await session.defaultSession.cookies.get({ url: this.source, name: 'auth_token' });
        for (const cookie of cookies) if (!before.some(previous => previous.domain === cookie.domain && previous.path === cookie.path && previous.value === cookie.value)) {
          await session.defaultSession.cookies.remove(new URL(cookie.path || '/', this.source).href, cookie.name);
        }
      }
      if (this.attempt === attempt) { clearTimeout(attempt.timer); this.attempt = undefined; }
    }
  }
}
