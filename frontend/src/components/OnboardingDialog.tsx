import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useAuthStore } from '@/store/useAuthStore';
import { useInstitutionStore } from '@/store/useInstitutionStore';
import api from '@/lib/api';
import { GraduationCap, Building2, ArrowRight, Loader2 } from 'lucide-react';
import { DirectionSelector } from '@/components/DirectionSelector';

export function OnboardingDialog() {
  const { user, updateUser } = useAuthStore();
  const institution = useInstitutionStore(s => s.institution);
  const { t } = useTranslation(['onboarding', 'common']);
  const [step, setStep] = useState<'role' | 'teacher' | 'directions' | 'student'>(user?.institution_role === 'owner' ? 'teacher' : 'role');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  // Teacher form
  const [teacherCode, setTeacherCode] = useState('');
  const [instName, setInstName] = useState('');
  const [instDesc, setInstDesc] = useState('');
  const [instPhone, setInstPhone] = useState('');

  // Direction selection
  const [plan, setPlan] = useState<string>('');
  const [subjects, setSubjects] = useState<any[]>([]);
  const [selectedSubjects, setSelectedSubjects] = useState<string[]>([]);
  const [directionError, setDirectionError] = useState('');

  const PLAN_DIRECTION_LIMITS: Record<string, number> = { solo: 1, plus: 3, pro: 999999 };

  // 不弹：无用户 / 已有机构（auth store 或 institution store）/ 已关闭 / 平台超管
  if (!user || user.institution || user.institution_id || institution || dismissed) return null;
  if (user.is_admin) return null;

  // Phase 1: validate invite code, then show direction selector
  const handleValidateAndNext = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!teacherCode.trim()) return setError(t('teacher.errors.enterInviteCode'));
    if (!instName.trim()) return setError(t('teacher.errors.enterName'));
    setLoading(true); setError('');
    try {
      const { data } = await api.post('/users/institutions/validate-invite-code/', {
        invite_code: teacherCode.trim().toUpperCase(),
      });
      setPlan(data.plan);
      // Fetch available subjects
      const subRes = await api.get('/quizzes/knowledge-points/subjects/');
      setSubjects(subRes.data.categories || []);
      setStep('directions');
    } catch (err: any) {
      setError(err.response?.data?.error || t('teacher.errors.invalidCode'));
    }
    setLoading(false);
  };

  // Phase 2: create institution with selected directions
  const handleCreateWithDirections = async () => {
    setLoading(true); setDirectionError('');
    const maxDirs = PLAN_DIRECTION_LIMITS[plan] || 1;

    if (selectedSubjects.length > 0 && selectedSubjects.length > maxDirs) {
      setDirectionError(`${plan.toUpperCase()} 方案最多选择 ${maxDirs} 个学科方向`);
      setLoading(false);
      return;
    }

    try {
      const { data } = await api.post('/users/institutions/create/', {
        invite_code: teacherCode.trim().toUpperCase(),
        name: instName.trim(),
        description: instDesc.trim(),
        contact_phone: instPhone.trim(),
        subject_names: selectedSubjects.length > 0 ? selectedSubjects : ['custom'],
      });
      updateUser({ institution_id: data.institution.id, institution_role: 'owner' });
      setDone(true);
    } catch (err: any) {
      setDirectionError(err.response?.data?.error || t('teacher.errors.createFailed'));
    }
    setLoading(false);
  };

  const handleDone = () => {
    window.location.reload();
  };

  return (
    <Dialog open={!dismissed} onOpenChange={(open) => { if (!open) setDismissed(true); }} >
      <DialogContent
        className="sm:max-w-[440px] rounded-2xl border-none shadow-2xl bg-card p-8"
      >
        {done ? (
          <div className="text-center space-y-5 py-4">
            <div className="h-14 w-14 rounded-2xl bg-emerald-50 text-emerald-600 flex items-center justify-center mx-auto shadow-inner">
              <Check className="h-7 w-7" />
            </div>
            <div className="space-y-2">
              <DialogTitle className="text-xl font-black">{t('done.title')}</DialogTitle>
              <DialogDescription className="font-medium text-muted-foreground">
                {step === 'teacher' ? t('done.teacherDesc') : t('done.studentDesc')}
              </DialogDescription>
            </div>
            <Button onClick={handleDone} variant="apple" className="w-full">
              {t('done.enter')}
            </Button>
          </div>
        ) : step === 'role' ? (
          <>
            <DialogHeader className="space-y-1 mb-6">
              <DialogTitle className="text-xl font-black">{t('role.title')}</DialogTitle>
              <DialogDescription className="font-medium text-muted-foreground">
                {t('role.subtitle')}
              </DialogDescription>
            </DialogHeader>
            <div className="grid gap-3">
              <button
                onClick={() => setStep('teacher')}
                className="text-left p-5 rounded-xl border-2 border-border hover:border-primary hover:bg-primary/3 transition-all group"
              >
                <div className="flex items-start gap-3">
                  <div className="h-10 w-10 rounded-xl bg-primary/8 flex items-center justify-center shrink-0 group-hover:bg-primary/15">
                    <Building2 className="h-5 w-5 text-primary" />
                  </div>
                  <div className="space-y-1">
                    <p className="text-sm font-extrabold text-foreground flex items-center gap-2">
                      {t('role.teacherLabel')} <ArrowRight className="h-3.5 w-3.5 text-primary opacity-0 group-hover:opacity-100 transition-opacity" />
                    </p>
                    <p className="text-xs text-unimind-text-tertiary font-medium">{t('role.teacherDesc')}</p>
                  </div>
                </div>
              </button>

              <button
                onClick={() => setStep('student')}
                className="text-left p-5 rounded-xl border-2 border-border hover:border-unimind-green hover:bg-unimind-green/3 transition-all group"
              >
                <div className="flex items-start gap-3">
                  <div className="h-10 w-10 rounded-xl bg-unimind-green/8 flex items-center justify-center shrink-0 group-hover:bg-unimind-green/15">
                    <GraduationCap className="h-5 w-5 text-unimind-green" />
                  </div>
                  <div className="space-y-1">
                    <p className="text-sm font-extrabold text-foreground flex items-center gap-2">
                      {t('role.studentLabel')} <ArrowRight className="h-3.5 w-3.5 text-unimind-green opacity-0 group-hover:opacity-100 transition-opacity" />
                    </p>
                    <p className="text-xs text-unimind-text-tertiary font-medium">{t('role.studentDesc')}</p>
                  </div>
                </div>
              </button>
            </div>
          </>
        ) : step === 'teacher' ? (
          <>
            <DialogHeader className="space-y-1 mb-5">
              <DialogTitle className="text-xl font-black">{t('teacher.title')}</DialogTitle>
              <DialogDescription className="font-medium text-muted-foreground">
                {t('teacher.subtitle')}
              </DialogDescription>
            </DialogHeader>
            <form onSubmit={handleValidateAndNext} className="space-y-3">
              <Input placeholder={t('teacher.inviteCodeLabel')} required value={teacherCode}
                onChange={e => setTeacherCode(e.target.value.toUpperCase())}
                className="h-11 rounded-xl font-mono text-center tracking-widest" />
              <Input placeholder={t('teacher.nameLabel')} required value={instName}
                onChange={e => setInstName(e.target.value)}
                className="h-11 rounded-xl" />
              <Input placeholder={t('teacher.descPlaceholder')} value={instDesc}
                onChange={e => setInstDesc(e.target.value)}
                className="h-11 rounded-xl" />
              <Input placeholder={t('teacher.phoneLabel')} value={instPhone}
                onChange={e => setInstPhone(e.target.value)}
                className="h-11 rounded-xl" />
              {error && <p className="text-xs text-red-500">{error}</p>}
              <div className="flex gap-2 pt-2">
                <Button type="button" variant="outline" className="flex-1 h-11 rounded-xl"
                  onClick={() => { setStep('role'); setError(''); }}>
                  {t('common:back')}
                </Button>
                <Button type="submit" variant="apple" className="flex-1 h-11 rounded-xl" disabled={loading}>
                  {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : '下一步'}
                </Button>
              </div>
            </form>
          </>
        ) : step === 'directions' ? (
          <>
            <DialogHeader className="space-y-1 mb-4">
              <DialogTitle className="text-xl font-black">选择业务方向</DialogTitle>
              <DialogDescription className="font-medium text-muted-foreground">
                {plan === 'solo'
                  ? 'Solo 方案可选择 1 个学科方向'
                  : plan === 'plus'
                    ? 'Plus 方案最多选择 3 个学科方向'
                    : '选择你机构的业务方向'}
              </DialogDescription>
            </DialogHeader>

            <div className="max-h-[360px] overflow-y-auto pr-1 -mx-1 px-1">
              <DirectionSelector
                categories={subjects}
                selected={selectedSubjects}
                onSelectionChange={setSelectedSubjects}
                maxSelections={PLAN_DIRECTION_LIMITS[plan] || 1}
              />
            </div>

            {directionError && <p className="text-xs text-red-500 mt-2">{directionError}</p>}

            <div className="flex gap-2 pt-3">
              <Button type="button" variant="outline" className="flex-1 h-11 rounded-xl"
                onClick={() => { setStep('teacher'); setDirectionError(''); }}>
                {t('common:back')}
              </Button>
              <Button type="button" variant="apple" className="flex-1 h-11 rounded-xl"
                onClick={handleCreateWithDirections} disabled={loading}>
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : t('teacher.create')}
              </Button>
            </div>
          </>
        ) : (
          <>
            <DialogHeader className="space-y-1 mb-5">
              <DialogTitle className="text-xl font-black">{t('student.title')}</DialogTitle>
              <DialogDescription className="font-medium text-muted-foreground">
                {t('student.subtitle')}
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-3">
              <p className="text-xs text-muted-foreground font-medium">
                {t('student.instruction')}
              </p>
              <Button variant="apple" className="w-full h-11 rounded-xl"
                onClick={() => setDismissed(true)}>
                {t('common:ok')}
              </Button>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
