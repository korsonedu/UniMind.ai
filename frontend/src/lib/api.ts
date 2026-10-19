import axios from 'axios';
import { toast } from 'sonner';
import { getLoginPath } from './routing';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api',
  withCredentials: true,
  timeout: 30000,
});

// Preview mode: platform admin previews another institution
let _previewInstitutionId: number | null = null;
export function setPreviewInstitutionId(id: number | null) { _previewInstitutionId = id; }
export function getPreviewInstitutionId() { return _previewInstitutionId; }

api.interceptors.request.use((config) => {
  // Auth via httpOnly cookie (CookieTokenAuthentication) — no Authorization header needed
  // Attach preview institution ID for backend filtering
  if (_previewInstitutionId) {
    config.params = { ...config.params, preview_institution: _previewInstitutionId };
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401 && error.config?.url !== '/users/login/' && error.config?.url !== '/users/login-by-code/') {
      localStorage.removeItem('auth-storage');
      window.dispatchEvent(new Event('auth:logout'));
      // The root identity check renders Landing or the login redirect itself.
      if (error.config?.url !== '/users/me/'
        && !['/', '/login', '/register', '/verify-code', '/account-callback'].includes(window.location.pathname)) {
        window.location.replace(getLoginPath(window.location.pathname + window.location.search + window.location.hash));
      }
      return Promise.reject(error);
    }
    // Retry on 429 (rate limit) and network errors, max 2 retries
    const config = error.config;
    const retryCount = config.__retryCount || 0;
    const isRetryable = error.response?.status === 429 || !error.response;
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
    if (axios.isAxiosError(error) && error.code === 'ERR_NETWORK') {
      toast.error('网络连接失败', {
        id: 'network-connection-error',
        description: '再试一次，反正时间是一种幻觉。——《银河搭车客指南》',
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
 *   const { url, init } = streamFetch('/ai/chat/stream/', { message: 'hi' }, controller.signal);
 *   const res = await fetch(url, init);
 */
export function streamFetch(
  path: string,
  body?: Record<string, unknown>,
  signal?: AbortSignal,
  extraHeaders?: Record<string, string>,
): { url: string; init: RequestInit } {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...extraHeaders,
  };

  let urlPath = path.startsWith('/') ? path : `/${path}`;
  if (_previewInstitutionId) {
    const sep = urlPath.includes('?') ? '&' : '?';
    urlPath = `${urlPath}${sep}preview_institution=${_previewInstitutionId}`;
  }

  return {
    url: urlPath,
    init: {
      method: 'POST',
      headers,
      credentials: 'include',
      body: body ? JSON.stringify(body) : undefined,
      signal,
    },
  };
}

export default api;
