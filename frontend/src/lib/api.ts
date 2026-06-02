import axios from 'axios';

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
    if (error.response?.status === 401) {
      localStorage.removeItem('auth-storage');
      window.dispatchEvent(new Event('auth:logout'));
      if (window.location.pathname !== '/login') {
        window.location.href = '/login';
      }
      return Promise.reject(error);
    }
    // 403 + 无机构 → 弹出 onboarding 引导创建/加入机构
    if (error.response?.status === 403) {
      try {
        const raw = localStorage.getItem('auth-storage');
        const stored = raw ? JSON.parse(raw) : null;
        const u = stored?.state?.user;
        if (u && !u.institution && !u.institution_id && !u.is_admin) {
          window.dispatchEvent(new Event('onboarding:required'));
        }
      } catch { /* ignore parse errors */ }
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
    return Promise.reject(error);
  }
);

export default api;
