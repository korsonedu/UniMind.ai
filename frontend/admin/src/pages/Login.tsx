import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '@/store/useAuthStore';
import api from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Layers, Loader2 } from 'lucide-react';

export default function Login() {
  const navigate = useNavigate();
  const { token } = useAuthStore();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Already logged in → redirect
  if (token) {
    navigate('/institutions', { replace: true });
    return null;
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      const res = await api.post('/users/login/', { username, password });
      localStorage.setItem('token', res.data.token);
      useAuthStore.getState().setAuth(res.data.user, res.data.token);
      navigate('/institutions', { replace: true });
    } catch (err: any) {
      const detail = err.response?.data?.detail || err.response?.data?.error;
      if (typeof detail === 'object') {
        setError(Object.values(detail).flat().join('; ') || '登录失败');
      } else {
        setError(detail || '登录失败，请检查用户名和密码');
      }
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#F5F5F7] flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="h-10 w-10 rounded-xl bg-[#0071E3] flex items-center justify-center mx-auto mb-3 shadow-md shadow-[#0071E3]/20">
            <Layers className="h-5 w-5 text-white" strokeWidth={2.5} />
          </div>
          <h1 className="text-xl font-extrabold text-[#1D1D1F] tracking-tight">UniMind</h1>
          <p className="text-sm text-[#8E8E93] mt-1 font-medium">机构管理后台</p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="bg-white rounded-2xl border border-[#E5E5EA]/60 p-6 space-y-4 shadow-sm">
          <div className="space-y-1.5">
            <label className="text-[10px] font-extrabold text-[#AEAEB2] uppercase tracking-wider ml-1">
              用户名
            </label>
            <Input
              type="text"
              placeholder="输入管理员账号"
              value={username}
              onChange={e => setUsername(e.target.value)}
              required
              autoFocus
              className="h-11 rounded-xl"
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-[10px] font-extrabold text-[#AEAEB2] uppercase tracking-wider ml-1">
              密码
            </label>
            <Input
              type="password"
              placeholder="输入密码"
              value={password}
              onChange={e => setPassword(e.target.value)}
              required
              className="h-11 rounded-xl"
            />
          </div>
          {error && (
            <p className="text-xs text-red-500 font-medium bg-red-50 px-3 py-2 rounded-lg">{error}</p>
          )}
          <Button
            type="submit"
            disabled={loading}
            className="w-full h-11 rounded-xl bg-[#0071E3] hover:bg-[#0071E3]/90 text-white font-extrabold text-sm shadow-md shadow-[#0071E3]/20"
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : '登录'}
          </Button>
        </form>

        <p className="text-center text-[10px] text-[#AEAEB2] mt-6 font-medium">
          仅限平台管理员登录
        </p>
      </div>
    </div>
  );
}
