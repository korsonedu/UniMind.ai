import { Outlet, useNavigate } from 'react-router-dom';
import { useAuthStore } from '@/store/useAuthStore';
import { Button } from '@/components/ui/button';
import { Layers, LogOut, Building2 } from 'lucide-react';

export default function AdminLayout() {
  const navigate = useNavigate();
  const { user, logout } = useAuthStore();

  return (
    <div className="min-h-screen bg-[#F5F5F7]">
      {/* Header */}
      <header className="bg-white border-b border-[#E5E5EA]/60">
        <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <Layers className="h-4 w-4 text-[#0071E3]" strokeWidth={2.5} />
              <span className="font-extrabold text-sm text-[#1D1D1F] tracking-tight">UniMind</span>
              <span className="text-[11px] font-bold text-[#8E8E93]">机构管理后台</span>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 text-xs text-[#AEAEB2]">
              <Building2 className="h-3.5 w-3.5" />
              <span>{user?.nickname || user?.username}</span>
              {user?.is_admin && (
                <span className="px-1.5 py-0.5 rounded bg-[#0071E3]/8 text-[#0071E3] text-[10px] font-bold">Admin</span>
              )}
            </div>
            <Button
              variant="ghost"
              size="sm"
              className="h-8 text-xs text-[#8E8E93]"
              onClick={() => { logout(); navigate('/login'); }}
            >
              <LogOut className="h-3.5 w-3.5 mr-1" /> 退出
            </Button>
          </div>
        </div>
      </header>

      {/* Content */}
      <div className="max-w-6xl mx-auto px-6 py-8">
        <Outlet />
      </div>
    </div>
  );
}
