export const DEFAULT_SERVER_ORIGIN = 'https://unimind-ai.com';
export const LEGACY_ORIGINS = new Set(['https://unimind.korsonedu.com', 'http://unimind.korsonedu.com']);
const SETTINGS_KEY = 'unimind:settings';
const AUTH_PREFIX = 'unimind:auth:';

export interface AuthUser {
  id: number | string;
  username?: string;
  email?: string;
  nickname?: string;
  [field: string]: unknown;
}

export interface ExtensionSettings {
  serverOrigin: string;
}

export interface ExtensionSession extends ExtensionSettings {
  token: string | null;
  user: AuthUser | null;
  tokenSource: 'cookie' | 'inline' | null;
  botId?: number | null;
}

type AuthRecord = Omit<ExtensionSession, 'serverOrigin'>;
const EMPTY_AUTH: AuthRecord = { token: null, user: null, tokenSource: null, botId: null };
let pendingWrite: Promise<unknown> = Promise.resolve();

export function normalizeServerOrigin(value: string): string {
  const candidate = value.trim();
  if (!candidate) throw new Error('请输入 http 或 https 服务地址。');
  const url = new URL(candidate.includes('://') ? candidate : `https://${candidate}`);
  if (!['http:', 'https:'].includes(url.protocol)) throw new Error('请输入 http 或 https 服务地址。');
  if (url.username || url.password) throw new Error('服务地址中不能包含用户名或密码。');
  return url.origin;
}

export function serverPermissionPattern(value: string): string {
  const url = new URL(normalizeServerOrigin(value));
  return `${url.protocol}//${url.hostname}/*`;
}

// Call directly from a click handler so Chrome retains the user's activation.
export function requestServerPermission(origin: string): Promise<boolean> {
  return chrome.permissions.request({ origins: [serverPermissionPattern(origin)] });
}

async function readSessionUnlocked(): Promise<ExtensionSession> {
  const settings = await chrome.storage.local.get(SETTINGS_KEY);
  const storedSettings = settings[SETTINGS_KEY] as Partial<ExtensionSettings> | undefined;
  let serverOrigin = normalizeServerOrigin(storedSettings?.serverOrigin || DEFAULT_SERVER_ORIGIN);
  if (LEGACY_ORIGINS.has(serverOrigin)) {
    serverOrigin = DEFAULT_SERVER_ORIGIN;
    await chrome.storage.local.set({ [SETTINGS_KEY]: { ...storedSettings, serverOrigin } });
  }
  const values = await chrome.storage.local.get(AUTH_PREFIX + serverOrigin);
  const auth = values[AUTH_PREFIX + serverOrigin] as Partial<AuthRecord> | undefined;
  return { serverOrigin, ...EMPTY_AUTH, ...auth };
}

export function readSession(): Promise<ExtensionSession> {
  return serializeWrite(readSessionUnlocked);
}

function serializeWrite<T>(write: () => Promise<T>): Promise<T> {
  const run = async (): Promise<T> => {
    if (typeof navigator !== 'undefined' && navigator.locks) {
      return await navigator.locks.request('unimind:session-write', write);
    }
    return write();
  };
  const result = pendingWrite.then(run, run);
  pendingWrite = result.catch(() => undefined);
  return result;
}

export function saveSession(
  patch: Partial<ExtensionSession>,
  expected?: Pick<ExtensionSession, 'token' | 'tokenSource'>,
): Promise<ExtensionSession> {
  return serializeWrite(async () => {
    const current = await readSessionUnlocked();
    if (patch.serverOrigin && normalizeServerOrigin(patch.serverOrigin) !== current.serverOrigin) {
      throw new Error('服务地址已经切换，请重新操作。');
    }
    if (expected && (current.token !== expected.token || current.tokenSource !== expected.tokenSource)) return current;
    const next = { ...current, ...patch, serverOrigin: current.serverOrigin };
    const { serverOrigin, ...auth } = next;
    await chrome.storage.local.set({ [AUTH_PREFIX + serverOrigin]: auth });
    return next;
  });
}

export function setServerOrigin(value: string): Promise<ExtensionSession> {
  const serverOrigin = normalizeServerOrigin(value);
  return serializeWrite(async () => {
    const current = await readSessionUnlocked();
    if (current.serverOrigin === serverOrigin) return current;
    await chrome.storage.local.set({
      [AUTH_PREFIX + serverOrigin]: { ...EMPTY_AUTH },
      [SETTINGS_KEY]: { serverOrigin },
    });
    return { serverOrigin, ...EMPTY_AUTH };
  });
}

export function clearAuth(): Promise<ExtensionSession> {
  return saveSession({ ...EMPTY_AUTH });
}

export function subscribeSession(listener: (session: ExtensionSession) => void): () => void {
  let sequence = 0;
  const changed = (changes: Record<string, chrome.storage.StorageChange>, area: string) => {
    if (area !== 'local' || !Object.keys(changes).some(key => key === SETTINGS_KEY || key.startsWith(AUTH_PREFIX))) return;
    const revision = ++sequence;
    void readSession().then(session => {
      if (revision === sequence) listener(session);
    }).catch(() => undefined);
  };
  chrome.storage.onChanged.addListener(changed);
  return () => {
    sequence++;
    chrome.storage.onChanged.removeListener(changed);
  };
}
