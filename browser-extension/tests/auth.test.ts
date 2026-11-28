import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { handleAuthCookieChange, login, loginByCode, sendVerificationCode, syncCookieToken } from '../src/lib/auth';
import { DEFAULT_SERVER_ORIGIN, LEGACY_ORIGINS, normalizeServerOrigin, readSession, saveSession, setServerOrigin } from '../src/lib/storage';

const cookieGet = vi.fn<(options: { url: string; name: string }) => Promise<{ value: string } | null>>();
let storage: Record<string, unknown>;

beforeEach(async () => {
  storage = {};
  cookieGet.mockReset().mockResolvedValue(null);
  vi.stubGlobal('chrome', {
    cookies: { get: cookieGet },
    storage: { local: {
      get: async (key: string) => ({ [key]: storage[key] }),
      set: async (patch: Record<string, unknown>) => { Object.assign(storage, patch); },
    } },
  });
  await setServerOrigin('http://localhost:5173/');
});

afterEach(() => vi.unstubAllGlobals());

describe('Token 双通道', () => {
  it('从指定的当前主站读取 Cookie 并在登出后清除同步会话', async () => {
    cookieGet.mockResolvedValueOnce({ value: 'cookie-fixture' });
    expect(await syncCookieToken('http://localhost:5173')).toBe('cookie-fixture');
    expect(cookieGet).toHaveBeenCalledWith({ url: 'http://localhost:5173', name: 'auth_token' });
    expect(await readSession()).toMatchObject({ token: 'cookie-fixture', tokenSource: 'cookie' });

    await handleAuthCookieChange({
      cookie: { name: 'auth_token', domain: 'localhost' }, removed: true, cause: 'explicit',
    } as chrome.cookies.CookieChangeInfo);
    expect(await readSession()).toMatchObject({ token: null, tokenSource: null });

    expect(await syncCookieToken('https://another.example')).toBeNull();
    expect(cookieGet).toHaveBeenCalledTimes(2);
  });

  it('内联登录发往 Vite 代理且不带过期 Token，无 Cookie 时仍能保留该独立会话', async () => {
    await saveSession({ token: 'stale-fixture', tokenSource: 'inline' });
    const fetch = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>()
      .mockResolvedValue(new Response(JSON.stringify({ token: 'inline-fixture', user: { id: 42 } })));
    vi.stubGlobal('fetch', fetch);
    await login('tester', 'fake-password');

    const request = fetch.mock.calls[0]?.[1];
    expect(fetch.mock.calls[0]?.[0]).toBe('http://localhost:5173/api/users/login/');
    expect(request?.credentials).toBe('omit');
    expect(new Headers(request?.headers).get('Authorization')).toBeNull();
    expect(new Headers(request?.headers).get('Accept-Language')).toBe('zh-CN');
    expect(JSON.parse(String(request?.body))).toMatchObject({ username: 'tester', password: 'fake-password' });
    expect(await syncCookieToken()).toBeNull();
    expect(await readSession()).toMatchObject({ token: 'inline-fixture', tokenSource: 'inline', user: { id: 42 } });
  });

  it.each(['https://unimind-ai.com', 'https://www.unimind-ai.com'])('在 %s 没有 Cookie 时从另一主站域同步', async origin => {
    await setServerOrigin(origin);
    cookieGet.mockResolvedValueOnce(null).mockResolvedValueOnce({ value: 'fallback-cookie' });

    expect(await syncCookieToken()).toBe('fallback-cookie');
    expect(cookieGet.mock.calls.map(([options]) => options.url)).toEqual([
      origin,
      origin === DEFAULT_SERVER_ORIGIN ? 'https://www.unimind-ai.com' : DEFAULT_SERVER_ORIGIN,
    ]);
    expect(await readSession()).toMatchObject({ serverOrigin: origin, token: 'fallback-cookie', tokenSource: 'cookie' });
  });

  it('优先使用当前主站域的 Cookie', async () => {
    await setServerOrigin(DEFAULT_SERVER_ORIGIN);
    cookieGet.mockResolvedValueOnce({ value: 'primary-cookie' });
    expect(await syncCookieToken()).toBe('primary-cookie');
    expect(cookieGet).toHaveBeenCalledTimes(1);
  });

  it('根域设置下响应 www 的 Cookie 变化，两个域都退出后清空会话', async () => {
    await setServerOrigin(DEFAULT_SERVER_ORIGIN);
    cookieGet.mockResolvedValueOnce(null).mockResolvedValueOnce({ value: 'www-cookie' });
    await handleAuthCookieChange({
      cookie: { name: 'auth_token', domain: 'www.unimind-ai.com' }, removed: false, cause: 'explicit',
    } as chrome.cookies.CookieChangeInfo);
    expect(await readSession()).toMatchObject({ token: 'www-cookie', tokenSource: 'cookie' });

    await handleAuthCookieChange({
      cookie: { name: 'auth_token', domain: 'www.unimind-ai.com' }, removed: true, cause: 'explicit',
    } as chrome.cookies.CookieChangeInfo);
    expect(await readSession()).toMatchObject({ token: null, tokenSource: null });
  });

  it('www 设置下响应根域的 Cookie 变化', async () => {
    await setServerOrigin('https://www.unimind-ai.com');
    cookieGet.mockResolvedValueOnce(null).mockResolvedValueOnce({ value: 'root-cookie' });
    await handleAuthCookieChange({
      cookie: { name: 'auth_token', domain: '.unimind-ai.com' }, removed: false, cause: 'explicit',
    } as chrome.cookies.CookieChangeInfo);
    expect(await readSession()).toMatchObject({ token: 'root-cookie' });
  });

  it('主站域之间发生 Cookie 覆盖时保留当前会话，并忽略无关域', async () => {
    await setServerOrigin(DEFAULT_SERVER_ORIGIN);
    await saveSession({ token: 'current-cookie', tokenSource: 'cookie' });
    for (const [domain, cause] of [['www.unimind-ai.com', 'overwrite'], ['unimind-ai.com.example', 'explicit']] as const) {
      await handleAuthCookieChange({
        cookie: { name: 'auth_token', domain }, removed: true, cause,
      } as chrome.cookies.CookieChangeInfo);
    }
    expect(cookieGet).not.toHaveBeenCalled();
    expect(await readSession()).toMatchObject({ token: 'current-cookie' });
  });

  it('查询 Cookie 期间切换服务器会丢弃旧域结果', async () => {
    await setServerOrigin(DEFAULT_SERVER_ORIGIN);
    cookieGet.mockImplementationOnce(async () => {
      await setServerOrigin('http://localhost:8000');
      return { value: 'old-domain-cookie' };
    });
    expect(await syncCookieToken()).toBeNull();
    expect(await readSession()).toMatchObject({ serverOrigin: 'http://localhost:8000', token: null });
  });
});

describe('生产域名与旧设置迁移', () => {
  it.each([...LEGACY_ORIGINS])('自动回写旧域 %s 且不沿用旧域 Token', async legacy => {
    storage = {
      'unimind:settings': { serverOrigin: `${legacy}/login`, futureSetting: true },
      [`unimind:auth:${legacy}`]: { token: 'legacy-token', user: { id: 1 }, tokenSource: 'inline' },
    };
    expect(await readSession()).toMatchObject({ serverOrigin: DEFAULT_SERVER_ORIGIN, token: null, user: null });
    expect(storage['unimind:settings']).toEqual({ serverOrigin: DEFAULT_SERVER_ORIGIN, futureSetting: true });
    expect(await readSession()).toMatchObject({ serverOrigin: DEFAULT_SERVER_ORIGIN, token: null });
  });

  it('并发迁移与服务切换按顺序执行', async () => {
    storage = { 'unimind:settings': { serverOrigin: [...LEGACY_ORIGINS][0] } };
    const [migrated, switched] = await Promise.all([readSession(), setServerOrigin('http://localhost:8000')]);
    expect(migrated.serverOrigin).toBe(DEFAULT_SERVER_ORIGIN);
    expect(switched.serverOrigin).toBe('http://localhost:8000');
    expect(await readSession()).toMatchObject({ serverOrigin: 'http://localhost:8000', token: null });
  });

  it('迁移设置时保留已经独立存储的生产主站会话', async () => {
    storage = {
      'unimind:settings': { serverOrigin: [...LEGACY_ORIGINS][0] },
      [`unimind:auth:${DEFAULT_SERVER_ORIGIN}`]: { token: 'production-token', user: { id: 9 }, tokenSource: 'inline' },
    };
    expect(await readSession()).toMatchObject({ serverOrigin: DEFAULT_SERVER_ORIGIN, token: 'production-token', user: { id: 9 } });
  });

  it.each(['https://unimind-ai.com/login?next=/xiaoyu', 'unimind-ai.com', ' unimind-ai.com/login '])('友好归一化 %s', input => {
    expect(normalizeServerOrigin(input)).toBe(DEFAULT_SERVER_ORIGIN);
  });

  it.each(['', 'ftp://unimind-ai.com', 'https://user:password@unimind-ai.com'])('拒绝无效或含凭据的服务地址 %s', input => {
    expect(() => normalizeServerOrigin(input)).toThrow();
  });
});

describe('验证码登录', () => {
  it('发送登录验证码并用验证码替换过期会话，两次公共请求均省略 Cookie 和 Authorization', async () => {
    await setServerOrigin(DEFAULT_SERVER_ORIGIN);
    await saveSession({ token: 'stale-token', tokenSource: 'inline' });
    const fetch = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>()
      .mockResolvedValueOnce(new Response(JSON.stringify({ message: '验证码已发送' })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ token: 'code-token', user: { id: 7, email: 'learner@example.com' } })));
    vi.stubGlobal('fetch', fetch);

    await sendVerificationCode(' learner@example.com ');
    expect(await readSession()).toMatchObject({ token: 'stale-token' });
    const session = await loginByCode(' learner@example.com ', ' 123456 ');
    expect(session).toMatchObject({ token: 'code-token', tokenSource: 'inline', user: { id: 7 } });
    expect(fetch.mock.calls.map(([url]) => url)).toEqual([
      `${DEFAULT_SERVER_ORIGIN}/api/users/send-verification-code/`,
      `${DEFAULT_SERVER_ORIGIN}/api/users/login-by-code/`,
    ]);
    expect(fetch.mock.calls.map(([, request]) => JSON.parse(String(request?.body)))).toEqual([
      { email: 'learner@example.com', purpose: 'login_by_code' },
      { email: 'learner@example.com', code: '123456' },
    ]);
    for (const [, request] of fetch.mock.calls) {
      expect(request?.method).toBe('POST');
      expect(request?.credentials).toBe('omit');
      expect(new Headers(request?.headers).get('Authorization')).toBeNull();
    }
  });

  it('展示服务端验证码错误并保留当前会话', async () => {
    await saveSession({ token: 'current-token', tokenSource: 'inline' });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: '验证码已过期' }), { status: 400 })));
    await expect(loginByCode('learner@example.com', '000000')).rejects.toThrow('验证码已过期');
    expect(await readSession()).toMatchObject({ token: 'current-token' });
  });

  it('缺少 Token 的登录响应不会覆盖会话', async () => {
    await saveSession({ token: 'current-token', tokenSource: 'inline' });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ user: { id: 7 } }))));
    await expect(loginByCode('learner@example.com', '123456')).rejects.toThrow('登录响应中缺少 Token');
    expect(await readSession()).toMatchObject({ token: 'current-token' });
  });

  it('验证码请求期间切换服务地址时拒绝保存旧服务返回的 Token', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => {
      await setServerOrigin('http://localhost:8000');
      return new Response(JSON.stringify({ token: 'old-server-token', user: { id: 7 } }));
    }));
    await expect(loginByCode('learner@example.com', '123456')).rejects.toThrow('服务地址已经切换');
    expect(await readSession()).toMatchObject({ serverOrigin: 'http://localhost:8000', token: null });
  });
});
