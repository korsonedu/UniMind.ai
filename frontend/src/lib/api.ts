import { getLocale, t } from '@/i18n';
import axios, { type AxiosRequestConfig } from 'axios';
import { Preferences } from '@capacitor/preferences';
import { DEMO_USER, isOfflineDemo, isNativeOffline, setNativeOffline, OFFLINE_MESSAGE } from './offlineSession';
import { getServerOrigin } from './serverConfig';
import { toast } from 'sonner';
import { getLoginPath } from './routing';
import { getApiBaseUrl, getRegisteredAuthToken, isNativePlatform } from './serverConfig';
import { activeWorkspace, setActiveWorkspace, spaceStorageKey } from './activeWorkspace';

const api = axios.create({
  baseURL: getApiBaseUrl(),
  withCredentials: !isNativePlatform(),
  timeout: 30000,
});

export const backgroundRequest: AxiosRequestConfig & { background: true } = { background: true };

let csrfRequest: Promise<string> | null = null;
export function getCsrfToken(background = false): Promise<string> {
  const cookie = document.cookie.split('; ').find(item => item.startsWith('csrftoken='));
  if (cookie) return Promise.resolve(decodeURIComponent(cookie.slice('csrftoken='.length)));
  if (!csrfRequest) {
    csrfRequest = api.get('/csrf/', background ? backgroundRequest : undefined)
      .then(response => response.data.csrf_token as string)
      .finally(() => { csrfRequest = null; });
  }
  return csrfRequest;
}

// Preview mode: platform admin previews another institution
let _previewInstitutionId: number | null = null;
export function setPreviewInstitutionId(id: number | null) { _previewInstitutionId = id; }
export function getPreviewInstitutionId() { return _previewInstitutionId; }

api.interceptors.request.use(async (config) => {
  config.headers.set('X-UniMind-Workspace', activeWorkspace());
  if (!config.headers.has('Accept-Language')) config.headers.set('Accept-Language', getLocale());
  const native = isNativePlatform();
  const background = 'background' in config && config.background === true;
  if (background && native && (isOfflineDemo() || isNativeOffline())) throw new axios.CanceledError();
  if (native && isOfflineDemo()) {
    config.adapter = async request => {
      const path = (request.url || '').replace(/^\/api/, '').split('?')[0];
      const method = request.method?.toUpperCase() || 'GET';
      let data: unknown;
      if (path === '/users/me/' && method === 'GET') data = { ...DEMO_USER, nickname: t(DEMO_USER.nickname), bio: t(DEMO_USER.bio) };
      else if (path === '/users/institution/me/features/') data = { features: ['ai.assistant','quiz.exam','knowledge.graph','full.report'], is_platform_admin: false, institution: null };
      else if (path === '/users/learning/access/') data = { is_course_student: false, ai_usage: { used: 0, limit: 0, remaining: 0, base_remaining: 0, addon_remaining: 0, configured: true, unlimited: false }, addons: [] };
      else if (path === '/notifications/unread-count/') data = { count: 0 };
      else if (path === '/notifications/') data = [];
      else {
        try { data = await (await import('./offlineDemoApi')).demoRequest(method, path, typeof request.data === 'string' ? JSON.parse(request.data) : request.data, request.params); } catch (error) { if (error instanceof Error && error.message === t(OFFLINE_MESSAGE)) toast.info(t(OFFLINE_MESSAGE), { id: 'offline-action' }); throw error; }
      }
      return { data, status: 200, statusText: 'OK', headers: {}, config: request };
    };
    config.headers.delete('Authorization');
    return config;
  }
  if (native && isNativeOffline() && !['get','head','options'].includes(config.method || 'get')) { toast.info(t(OFFLINE_MESSAGE), { id: 'offline-action' }); throw new Error(t(OFFLINE_MESSAGE)); }
  if (native && (config.method || 'get') === 'get' && /^\/(users\/me\/|users\/institution\/me\/features\/|notes\/)/.test(config.url || '')) config.timeout = Math.min(config.timeout || 5000, 5000);
  config.baseURL = getApiBaseUrl();
  config.withCredentials = !native;

  if (native) {
    config.withXSRFToken = false;
    config.headers.delete('X-CSRFToken');
    // Native Capacitor builds authenticate via Authorization Token without cookies to skip CSRF enforcement.
    const token = getRegisteredAuthToken();
    if (token) {
      config.headers.set('Authorization', `Token ${token}`);
    } else {
      config.headers.delete('Authorization');
    }
  } else if (!['get', 'head', 'options'].includes(config.method?.toLowerCase() || 'get')) {
    // Web/Electron authenticate via httpOnly cookie (CookieTokenAuthentication) + CSRF.
    config.headers.set('X-CSRFToken', await getCsrfToken(background));
  }
  // Attach preview institution ID for backend filtering
  if (_previewInstitutionId) {
    config.params = { ...config.params, preview_institution: _previewInstitutionId };
  }
  return config;
});

api.interceptors.response.use(
  async (response) => {
    if (isNativePlatform() && !isOfflineDemo()) {
      setNativeOffline(false);
      const id = JSON.parse(localStorage.getItem(spaceStorageKey('auth-storage')) || '{}').state?.user?.id;
      if (id > 0 && ['/users/me/','/users/institution/me/features/'].includes(response.config.url || '')) {
        await Preferences.set({ key: `unimind:identity:${getServerOrigin()}:${id}:${response.config.url}`, value: JSON.stringify(response.data) }).catch(() => { toast.info(t('本地缓存保存失败，当前在线会话仍可使用'), { id: 'offline-cache-write' }); });
      }
    }
    return response;
  },
  async (error) => {
    if (error.config?.background) return Promise.reject(error);
    if (error.response?.status === 403 && error.response?.data?.code === 'workspace_unavailable') {
      setActiveWorkspace(null);
      window.location.replace('/xiaoyu');
      return Promise.reject(error);
    }
    if (isNativePlatform() && !isOfflineDemo() && !error.response && !axios.isCancel(error)) {
      setNativeOffline(true);
      const id = JSON.parse(localStorage.getItem(spaceStorageKey('auth-storage')) || '{}').state?.user?.id;
      if (id > 0 && ['/users/me/','/users/institution/me/features/'].includes(error.config?.url || '')) {
        const { value } = await Preferences.get({ key: `unimind:identity:${getServerOrigin()}:${id}:${error.config.url}` });
        if (value && error.config.url !== '/users/me/') return { data: JSON.parse(value), status: 200, statusText: 'Offline cache', headers: {}, config: error.config };
      }
      return Promise.reject(error);
    }
    if (!isOfflineDemo() && error.response?.status === 401 && error.config?.url !== '/users/login/' && error.config?.url !== '/users/login-by-code/') {
      localStorage.removeItem(spaceStorageKey('auth-storage'));
      window.dispatchEvent(new Event('auth:logout'));
      if (isNativePlatform()) {
        // Let the queued Preferences removal finish before a full-page redirect.
        const { flushNativeToken } = await import('@/store/useAuthStore');
        await flushNativeToken().catch(() => {});
      }
      // The root identity check renders Landing or the login redirect itself.
      if (error.config?.url !== '/users/me/'
        && !['/', '/login', '/register', '/verify-code', '/account-callback'].includes(window.location.pathname)) {
        window.location.replace(getLoginPath(window.location.pathname + window.location.search + window.location.hash));
      }
      return Promise.reject(error);
    }
    // Only reads may be replayed after a lost response.
    const config = error.config;
    const retryCount = config?.__retryCount || 0;
    const isRetryable = config && ['get', 'head', 'options'].includes(config.method?.toLowerCase() || 'get')
      && !axios.isCancel(error) && (error.response?.status === 429 || !error.response);
    if (isRetryable && retryCount < 2) {
      config.__retryCount = retryCount + 1;
      // Respect Retry-After header if present, otherwise exponential backoff
      const retryAfter = error.response?.headers?.['retry-after'];
      const delay = retryAfter
        ? Math.min(parseInt(retryAfter, 10) * 1000, 30000)
        : 1000 * Math.pow(2, retryCount);
      await new Promise(r => setTimeout(r, delay));
      return api(config);
    }
    if (!isOfflineDemo() && !isNativeOffline() && navigator.onLine && axios.isAxiosError(error) && error.code === 'ERR_NETWORK') {
      toast.error(t('网络连接失败'), {
        id: 'network-connection-error',
        description: t('再试一次，反正时间是一种幻觉。——《银河搭车客指南》'),
        classNames: { description: 'italic text-muted-foreground' },
      });
    }
    return Promise.reject(error);
  }
);

/**
 * Build fetch RequestInit for SSE streaming requests.
 * Injects the same context that axios interceptors provide:
 *   - credentials: 'include' (Cookie auth)
 *   - preview_institution query param (platform admin preview)
 *
 * Usage:
 *   const { url, init } = await streamFetch('/api/ai/chat/stream/', { message: 'hi' }, controller.signal);
 *   const res = await fetch(url, init);
 */
export async function streamFetch(
  path: string,
  body?: Record<string, unknown>,
  signal?: AbortSignal,
  extraHeaders?: Record<string, string>,
): Promise<{ url: string; init: RequestInit }> {
  if (isOfflineDemo() || isNativeOffline()) { toast.info(t(OFFLINE_MESSAGE)); throw new Error(t(OFFLINE_MESSAGE)); }
  const native = isNativePlatform();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'X-UniMind-Workspace': activeWorkspace(),
    'Accept-Language': getLocale(),
  };

  if (native) {
    const token = getRegisteredAuthToken();
    if (token) {
      headers['Authorization'] = `Token ${token}`;
    }
  } else {
    headers['X-CSRFToken'] = await getCsrfToken();
  }
  Object.assign(headers, extraHeaders);

  let urlPath = /^https?:\/\//i.test(path) ? path : path.startsWith('/') ? path : `/${path}`;
  if (native && /^https?:\/\//i.test(path) && new URL(path).origin !== getServerOrigin()) {
    throw new Error('Streaming requests must use the configured server origin');
  }
  if (!/^https?:\/\//i.test(path)) {
    const apiBase = getApiBaseUrl().replace(/\/$/, '');
    const relativePath = urlPath === '/api' || urlPath.startsWith('/api/')
      ? urlPath.replace(/^\/api(?=\/|$)/, '')
      : urlPath;
    urlPath = `${apiBase}${relativePath}`;
  }
  if (_previewInstitutionId) {
    const sep = urlPath.includes('?') ? '&' : '?';
    urlPath = `${urlPath}${sep}preview_institution=${_previewInstitutionId}`;
  }

  return {
    url: urlPath,
    init: {
      method: 'POST',
      headers,
      credentials: native ? 'omit' : 'include',
      body: body ? JSON.stringify(body) : undefined,
      signal,
    },
  };
}

export default api;
