import { createApiClient } from './api';
import { readSession, saveSession, normalizeServerOrigin, type AuthUser, type ExtensionSession } from './storage';
import { sendRuntimeMessage, UNIMIND_AUTH_SYNC } from '../shared/bridge';

interface LoginResponse {
  token: string;
  user: AuthUser;
}

async function authenticate(path: string, body: Record<string, string>): Promise<ExtensionSession> {
  const session = await readSession();
  // Login is public. A previous expired token must not prevent replacing it.
  const api = createApiClient({ ...session, token: null });
  const response = await api.request<LoginResponse>(path, {
    method: 'POST',
    body,
  });
  if (!response.token) throw new Error('登录响应中缺少 Token，请重新登录。');
  return saveSession({
    serverOrigin: session.serverOrigin,
    token: response.token,
    user: response.user ?? null,
    tokenSource: 'inline',
    botId: null,
  });
}

export function login(identifier: string, password: string): Promise<ExtensionSession> {
  return authenticate('/users/login/', { username: identifier.trim(), password });
}

export async function sendVerificationCode(email: string): Promise<void> {
  const session = await readSession();
  const api = createApiClient({ ...session, token: null });
  await api.request('/users/send-verification-code/', {
    method: 'POST',
    body: { email: email.trim(), purpose: 'login_by_code' },
  });
}

export function loginByCode(email: string, code: string): Promise<ExtensionSession> {
  return authenticate('/users/login-by-code/', { email: email.trim(), code: code.trim() });
}

export async function syncBrowserAuth(): Promise<ExtensionSession> {
  const session = await readSession();
  await sendRuntimeMessage(UNIMIND_AUTH_SYNC, { serverOrigin: session.serverOrigin });
  return readSession();
}

let cookieSyncQueue: Promise<unknown> = Promise.resolve();

function cookieOrigins(serverOrigin: string): string[] {
  if (serverOrigin === 'https://unimind-ai.com') return [serverOrigin, 'https://www.unimind-ai.com'];
  if (serverOrigin === 'https://www.unimind-ai.com') return [serverOrigin, 'https://unimind-ai.com'];
  return [serverOrigin];
}

export function syncCookieToken(serverOrigin?: string): Promise<string | null> {
  const sync = async () => {
    const session = await readSession();
    const origin = serverOrigin ? normalizeServerOrigin(serverOrigin) : session.serverOrigin;
    if (origin !== session.serverOrigin) return null;
    let cookie: chrome.cookies.Cookie | null = null;
    for (const cookieOrigin of cookieOrigins(origin)) {
      cookie = await chrome.cookies.get({ url: cookieOrigin, name: 'auth_token' });
      if (cookie?.value) break;
    }
    const latest = await readSession();
    if (latest.serverOrigin !== origin) return null;
    if (cookie?.value) {
      if (latest.token !== cookie.value || latest.tokenSource !== 'cookie') {
        const stored = await saveSession({
          serverOrigin: origin,
          token: cookie.value,
          tokenSource: 'cookie',
          user: latest.token === cookie.value ? latest.user : null,
          botId: latest.token === cookie.value ? latest.botId : null,
        }, latest);
        return stored.token;
      }
      return cookie.value;
    }
    // An inline login remains valid when the browser has no login cookie.
    if (latest.tokenSource === 'cookie') {
      await saveSession({ serverOrigin: origin, token: null, user: null, tokenSource: null, botId: null }, latest);
    }
    return null;
  };
  const result = cookieSyncQueue.then(sync, sync);
  cookieSyncQueue = result.catch(() => undefined);
  return result;
}

export async function handleAuthCookieChange(change: chrome.cookies.CookieChangeInfo): Promise<void> {
  if (change.cookie.name !== 'auth_token') return;
  const session = await readSession();
  const domain = change.cookie.domain.replace(/^\./, '');
  const matchesDomain = cookieOrigins(session.serverOrigin).some(origin => {
    const hostname = new URL(origin).hostname;
    return hostname === domain || hostname.endsWith(`.${domain}`);
  });
  if (!matchesDomain) return;
  // Chrome emits a removal before adding an overwritten cookie.
  if (change.removed && change.cause === 'overwrite') return;
  await syncCookieToken(session.serverOrigin);
}
