import axios from 'axios';
import { toast } from 'sonner';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000/api',
  withCredentials: true,
});

api.interceptors.response.use(
  (response) => {
    // 积分获取提示：heartbeat 返回 daily_bonus
    const bonus = response.data?.daily_bonus;
    if (bonus > 0) {
      toast.success(`+${bonus} 积分 · 每日登录奖励`, { duration: 3000 });
    }
    return response;
  },
  (error) => {
    // 积分不足
    if (error.response?.status === 402) {
      const msg = error.response?.data?.error || '积分不足，刷几道题就能解锁此功能';
      toast.error(msg, {
        duration: 5000,
        action: {
          label: '去刷题',
          onClick: () => { window.location.href = '/test-ladder'; },
        },
      });
    }
    return Promise.reject(error);
  }
);

export default api;
