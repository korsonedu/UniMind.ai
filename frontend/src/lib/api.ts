import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api',
  withCredentials: true,
});

// Preview mode: platform admin previews another institution
let _previewInstitutionId: number | null = null;
export function setPreviewInstitutionId(id: number | null) { _previewInstitutionId = id; }
export function getPreviewInstitutionId() { return _previewInstitutionId; }

api.interceptors.request.use((config) => {
  const stored = localStorage.getItem('auth-storage');
  if (stored) {
    try {
      const parsed = JSON.parse(stored);
      const token = parsed?.state?.token;
      if (token) {
        config.headers.Authorization = `Token ${token}`;
      }
    } catch {
      // ignore parse errors
    }
  }
  // Attach preview institution ID for backend filtering
  if (_previewInstitutionId) {
    config.params = { ...config.params, preview_institution: _previewInstitutionId };
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('auth-storage');
      window.dispatchEvent(new Event('auth:logout'));
      if (window.location.pathname !== '/login') {
        window.location.href = '/login';
      }
      return Promise.reject(error);
    }
    return Promise.reject(error);
  }
);

export default api;
