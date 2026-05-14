import { useState, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useAuthStore } from '@/store/useAuthStore';
import api from '@/lib/api';
import { GraduationCap, Building2, ArrowRight, Loader2, Check } from 'lucide-react';

export function OnboardingDialog() {
  const { user, updateUser } = useAuthStore();
  const location = useLocation();
  const [step, setStep] = useState<'role' | 'teacher' | 'student'>('role');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  // Teacher form
  const [teacherCode, setTeacherCode] = useState('');
  const [instName, setInstName] = useState('');
  const [instDesc, setInstDesc] = useState('');
  const [instPhone, setInstPhone] = useState('');

  // Student join
  const [joinCode, setJoinCode] = useState('');

  // 路由切换时重新弹出
  useEffect(() => {
    setDismissed(false);
  }, [location.pathname]);

  // 不弹
  if (!user || user.institution || user.institution_id || user.institution_role === 'admin' || user.is_admin || dismissed) return null;

  const handleCreateInstitution = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!teacherCode.trim()) return setError('请输入方案邀请码');
    if (!instName.trim()) return setError('请输入机构名称');
    setLoading(true); setError('');
    try {
      const { data } = await api.post('/users/institution/create/', {
        invite_code: teacherCode.trim().toUpperCase(),
        name: instName.trim(),
        description: instDesc.trim(),
        contact_phone: instPhone.trim(),
      });
      updateUser({ institution_id: data.institution.id, institution_role: 'admin' });
      setDone(true);
    } catch (err: any) {
      setError(err.response?.data?.error || '创建失败');
    }
    setLoading(false);
  };

  const handleJoinInstitution = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!joinCode.trim()) return setError('请输入邀请码');
    setLoading(true); setError('');
    try {
      const { data } = await api.post('/users/institution/join/', { invite_code: joinCode.trim() });
      updateUser({ institution_id: data.institution?.id, institution_role: 'student' });
      setDone(true);
    } catch (err: any) {
      setError(err.response?.data?.error || '加入失败，请检查邀请码');
    }
    setLoading(false);
  };

  const handleDone = () => {
    window.location.reload();
  };

  return (
    <Dialog open={!dismissed} onOpenChange={(open) => { if (!open) setDismissed(true); }} modal={true}>
      <DialogContent
        className="sm:max-w-[440px] rounded-2xl border-none shadow-2xl bg-card p-8"
        onInteractOutside={e => e.preventDefault()}
      >
        {done ? (
          <div className="text-center space-y-5 py-4">
            <div className="h-14 w-14 rounded-2xl bg-emerald-50 text-emerald-600 flex items-center justify-center mx-auto shadow-inner">
              <Check className="h-7 w-7" />
            </div>
            <div className="space-y-2">
              <DialogTitle className="text-xl font-black">设置完成！</DialogTitle>
              <DialogDescription className="font-medium text-muted-foreground">
                {step === 'teacher' ? '你的机构已创建，邀请码已在机构后台生成。' : '已成功加入机构，开始学习吧。'}
              </DialogDescription>
            </div>
            <Button onClick={handleDone} variant="apple" className="w-full">
              进入 UniMind
            </Button>
          </div>
        ) : step === 'role' ? (
          <>
            <DialogHeader className="space-y-1 mb-6">
              <DialogTitle className="text-xl font-black">设置你的身份</DialogTitle>
              <DialogDescription className="font-medium text-muted-foreground">
                选择你在 UniMind 中的角色，或点右上角 X 跳过稍后设置
              </DialogDescription>
            </DialogHeader>
            <div className="grid gap-3">
              <button
                onClick={() => setStep('teacher')}
                className="text-left p-5 rounded-xl border-2 border-border hover:border-[#0071E3] hover:bg-[#0071E3]/3 transition-all group"
              >
                <div className="flex items-start gap-3">
                  <div className="h-10 w-10 rounded-xl bg-[#0071E3]/8 flex items-center justify-center shrink-0 group-hover:bg-[#0071E3]/15">
                    <Building2 className="h-5 w-5 text-[#0071E3]" />
                  </div>
                  <div className="space-y-1">
                    <p className="text-sm font-extrabold text-[#1D1D1F] flex items-center gap-2">
                      我是老师/机构 <ArrowRight className="h-3.5 w-3.5 text-[#0071E3] opacity-0 group-hover:opacity-100 transition-opacity" />
                    </p>
                    <p className="text-xs text-[#8E8E93] font-medium">创建你的专属机构，管理学员和课程</p>
                  </div>
                </div>
              </button>

              <button
                onClick={() => setStep('student')}
                className="text-left p-5 rounded-xl border-2 border-border hover:border-[#34C759] hover:bg-[#34C759]/3 transition-all group"
              >
                <div className="flex items-start gap-3">
                  <div className="h-10 w-10 rounded-xl bg-[#34C759]/8 flex items-center justify-center shrink-0 group-hover:bg-[#34C759]/15">
                    <GraduationCap className="h-5 w-5 text-[#34C759]" />
                  </div>
                  <div className="space-y-1">
                    <p className="text-sm font-extrabold text-[#1D1D1F] flex items-center gap-2">
                      我是学生 <ArrowRight className="h-3.5 w-3.5 text-[#34C759] opacity-0 group-hover:opacity-100 transition-opacity" />
                    </p>
                    <p className="text-xs text-[#8E8E93] font-medium">通过老师给的邀请码加入机构</p>
                  </div>
                </div>
              </button>
            </div>
          </>
        ) : step === 'teacher' ? (
          <>
            <DialogHeader className="space-y-1 mb-5">
              <DialogTitle className="text-xl font-black">创建你的机构</DialogTitle>
              <DialogDescription className="font-medium text-muted-foreground">
                填写机构基本信息，之后可在仪表盘中修改
              </DialogDescription>
            </DialogHeader>
            <form onSubmit={handleCreateInstitution} className="space-y-3">
              <Input placeholder="方案邀请码 *（由 UniMind 提供）" required value={teacherCode}
                onChange={e => setTeacherCode(e.target.value.toUpperCase())}
                className="h-11 rounded-xl font-mono text-center tracking-widest" />
              <Input placeholder="机构名称 *" required value={instName}
                onChange={e => setInstName(e.target.value)}
                className="h-11 rounded-xl" />
              <Input placeholder="一句话简介（如：专注金融考研辅导）" value={instDesc}
                onChange={e => setInstDesc(e.target.value)}
                className="h-11 rounded-xl" />
              <Input placeholder="联系电话" value={instPhone}
                onChange={e => setInstPhone(e.target.value)}
                className="h-11 rounded-xl" />
              {error && <p className="text-xs text-red-500">{error}</p>}
              <div className="flex gap-2 pt-2">
                <Button type="button" variant="outline" className="flex-1 h-11 rounded-xl"
                  onClick={() => { setStep('role'); setError(''); }}>
                  返回
                </Button>
                <Button type="submit" variant="apple" className="flex-1 h-11 rounded-xl" disabled={loading}>
                  {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : '创建机构'}
                </Button>
              </div>
            </form>
          </>
        ) : (
          <>
            <DialogHeader className="space-y-1 mb-5">
              <DialogTitle className="text-xl font-black">加入机构</DialogTitle>
              <DialogDescription className="font-medium text-muted-foreground">
                输入老师提供的 8 位邀请码
              </DialogDescription>
            </DialogHeader>
            <form onSubmit={handleJoinInstitution} className="space-y-3">
              <Input placeholder="邀请码（如 T1TYFLBN）" required value={joinCode}
                onChange={e => setJoinCode(e.target.value.toUpperCase())}
                className="h-11 rounded-xl font-mono text-lg text-center tracking-widest" />
              {error && <p className="text-xs text-red-500">{error}</p>}
              <div className="flex gap-2 pt-2">
                <Button type="button" variant="outline" className="flex-1 h-11 rounded-xl"
                  onClick={() => { setStep('role'); setError(''); }}>
                  返回
                </Button>
                <Button type="submit" variant="apple" className="flex-1 h-11 rounded-xl" disabled={loading}>
                  {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : '加入'}
                </Button>
              </div>
            </form>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
