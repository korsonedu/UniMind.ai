import axios from 'axios';
import { toast } from 'sonner';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api',
  withCredentials: true,
});

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
  return config;
});

api.interceptors.response.use(
  (response) => {
    const bonus = response.data?.daily_bonus;
    if (bonus > 0) {
      toast.success(`+${bonus} 积分 · 每日登录奖励`, { duration: 3000 });
    }
    return response;
  },
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('auth-storage');
      if (window.location.pathname !== '/login') {
        window.location.href = '/login';
      }
      return Promise.reject(error);
    }

    if (error.response?.status === 402) {
      const msg = error.response?.data?.error || '积分不足，刷几道题就能解锁此功能';
      toast.error(msg, {
        duration: 5000,
        action: {
          label: '去刷题',
          onClick: () => { window.location.href = '/tests'; },
        },
      });
    }
    return Promise.reject(error);
  }
);

export default api;
