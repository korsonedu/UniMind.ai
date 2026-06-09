import { useState, useCallback, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Dialog, DialogContent } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useAuthStore } from '@/store/useAuthStore';
import { useInstitutionStore } from '@/store/useInstitutionStore';
import api from '@/lib/api';
import { Check, Loader2, GraduationCap, School } from 'lucide-react';
import { DirectionSelector } from '@/components/DirectionSelector';

// Teacher flow: steps 2-6 (role selected at step 1)
const TEACHER_STEPS = 5;

const SCALE_OPTIONS = ['1-50', '50-200', '200-500', '500+'] as const;

export function OnboardingDialog({ mandatory = false }: { mandatory?: boolean }) {
  const { user, updateUser } = useAuthStore();
  const institution = useInstitutionStore(s => s.institution);
  const fetchFeatures = useInstitutionStore(s => s.fetchFeatures);
  const { t } = useTranslation('onboarding');

  const [dismissed, setDismissed] = useState(false);
  const [currentStep, setCurrentStep] = useState(1);
  const [animState, setAnimState] = useState<'visible' | 'exiting' | 'entering'>('visible');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);

  // Listen for 403-triggered onboarding requirement
  useEffect(() => {
    const handler = () => setDismissed(false);
    window.addEventListener('onboarding:required', handler);
    return () => window.removeEventListener('onboarding:required', handler);
  }, []);

  // Role selection
  const [role, setRole] = useState<'student' | 'teacher' | null>(null);

  // Form state
  const [activationCode, setActivationCode] = useState('');
  const [codeActivated, setCodeActivated] = useState(false);
  const [instName, setInstName] = useState('');
  const [studentScale, setStudentScale] = useState('');
  const [selectedSubjects, setSelectedSubjects] = useState<string[]>([]);
  const [description, setDescription] = useState('');

  // Direction data
  const [plan, setPlan] = useState('');
  const [subjects, setSubjects] = useState<any[]>([]);

  const goToStep = useCallback((nextStep: number) => {
    setAnimState('exiting');
    setTimeout(() => {
      setCurrentStep(nextStep);
      setError('');
      setAnimState('entering');
      setTimeout(() => setAnimState('visible'), 300);
    }, 300);
  }, []);

  const PLAN_DIRECTION_LIMITS: Record<string, number> = { starter: 1, growth: 3, enterprise: 999999 };

  // Don't show if: no user / has institution / platform admin
  if (!user || user.institution || user.institution_id || institution) return null;
  if (!mandatory && dismissed) return null;
  if (user.is_admin) return null;

  // Step 1: Role selection
  const handleRoleSelect = (selected: 'student' | 'teacher') => {
    setRole(selected);
    if (selected === 'teacher') {
      goToStep(2); // activation code step
    }
    // student: stay on step 1, show guidance message
  };

  // Step 2: Activate membership code (optional)
  const handleActivateCode = async () => {
    if (!activationCode.trim()) return;
    setLoading(true); setError('');
    try {
      const { data } = await api.post('/users/me/activate/', { code: activationCode.trim() });
      setCodeActivated(true);
      updateUser(data.user);
      setPlan(data.plan);
      const subRes = await api.get('/quizzes/knowledge-points/subjects/');
      setSubjects(subRes.data.categories || []);
      goToStep(3);
    } catch (err: any) {
      setError(err.response?.data?.error || '激活码无效');
    }
    setLoading(false);
  };

  // Step 3: Validate name
  const handleNameNext = () => {
    if (!instName.trim()) return setError(t('step2.error_empty'));
    goToStep(4);
  };

  // Step 4: Select scale → auto-advance
  const handleScaleSelect = (scale: string) => {
    setStudentScale(scale);
    goToStep(5);
  };

  // Step 5: Subjects → next
  const handleSubjectsNext = () => {
    goToStep(6);
  };

  // Step 6: Create institution
  const handleCreate = async () => {
    setLoading(true); setError('');
    try {
      const { data } = await api.post('/users/institutions/create/', {
        invite_code: activationCode.trim().toUpperCase(),
        name: instName.trim(),
        description: description.trim(),
        student_scale: studentScale,
        subject_names: selectedSubjects.length > 0 ? selectedSubjects : ['custom'],
      });
      updateUser({ institution_id: data.institution.id, institution_role: 'owner' });
      await fetchFeatures();
      setDone(true);
    } catch (err: any) {
      setError(err.response?.data?.error || '创建失败');
    }
    setLoading(false);
  };

  const handleDone = () => window.location.reload();

  const animClass = animState === 'exiting'
    ? 'opacity-0 -translate-y-5'
    : animState === 'entering'
      ? 'opacity-0 translate-y-5'
      : 'opacity-100 translate-y-0';

  const showTeacherProgress = role === 'teacher' && currentStep >= 2;
  const teacherCurrentStep = currentStep - 1; // map step 2-6 to 1-5 for dots

  const shouldShow = user && !user.institution && !user.institution_id && !institution && !user.is_admin;

  return (
    <Dialog open={shouldShow} onOpenChange={mandatory ? undefined : (open: boolean) => { if (!open) setDismissed(true); }}>
      <DialogContent className="sm:max-w-lg rounded-2xl border-none shadow-2xl bg-card p-8 h-[480px]"
        showClose={false}
      >
        {done ? (
          <div className="text-center space-y-5 py-4">
            <div className="h-14 w-14 rounded-2xl bg-emerald-50 text-emerald-600 flex items-center justify-center mx-auto shadow-inner">
              <Check className="h-7 w-7" />
            </div>
            <div className="space-y-2">
              <h2 className="text-xl font-black">{t('done.title')}</h2>
              <p className="font-medium text-muted-foreground">{t('done.subtitle')}</p>
            </div>
            <Button onClick={handleDone} variant="apple" className="w-full">
              {t('done.enter')}
            </Button>
          </div>
        ) : (
          <div className="space-y-6">
            {/* Card content with animation */}
            <div className={`transition-all duration-300 ease-in-out ${animClass}`}>
              {/* Step 1: Role selection */}
              {currentStep === 1 && role === null && (
                <div className="space-y-4">
                  <div className="space-y-1">
                    <h2 className="text-xl font-black">你的身份是？</h2>
                    <p className="text-sm font-medium text-muted-foreground">选择后我们将为你提供对应的引导</p>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <button
                      type="button"
                      onClick={() => handleRoleSelect('student')}
                      className="group p-5 rounded-xl border-2 border-border hover:border-primary hover:bg-primary/5 transition-all text-center space-y-2"
                    >
                      <GraduationCap className="h-8 w-8 mx-auto text-muted-foreground group-hover:text-primary transition-colors" />
                      <div className="font-bold text-sm">我是学生</div>
                      <div className="text-xs text-muted-foreground">通过邀请链接加入机构</div>
                    </button>
                    <button
                      type="button"
                      onClick={() => handleRoleSelect('teacher')}
                      className="group p-5 rounded-xl border-2 border-border hover:border-primary hover:bg-primary/5 transition-all text-center space-y-2"
                    >
                      <School className="h-8 w-8 mx-auto text-muted-foreground group-hover:text-primary transition-colors" />
                      <div className="font-bold text-sm">我是教师 / 机构主</div>
                      <div className="text-xs text-muted-foreground">创建或管理教学机构</div>
                    </button>
                  </div>
                </div>
              )}

              {/* Step 1 (student): Guidance message */}
              {currentStep === 1 && role === 'student' && (
                <div className="space-y-4 text-center py-4">
                  <GraduationCap className="h-12 w-12 mx-auto text-primary" />
                  <div className="space-y-2">
                    <h2 className="text-xl font-black">请联系你的老师</h2>
                    <p className="text-sm font-medium text-muted-foreground">
                      请向你的老师或机构负责人索取邀请链接，<br />
                      点击链接后即可自动加入机构。
                    </p>
                  </div>
                  <Button variant="outline" className="w-full h-11 rounded-xl" onClick={() => setRole(null)}>
                    返回重新选择
                  </Button>
                </div>
              )}

              {/* Step 2: Activation code (optional, teacher path) */}
              {currentStep === 2 && (
                <div className="space-y-4">
                  <div className="space-y-1">
                    <h2 className="text-xl font-black">输入激活码</h2>
                    <p className="text-sm font-medium text-muted-foreground">
                      如果您有激活码，可以在此输入以解锁会员功能
                    </p>
                  </div>
                  <Input
                    placeholder="请输入激活码"
                    value={activationCode}
                    onChange={e => setActivationCode(e.target.value.toUpperCase())}
                    spellCheck={false}
                    autoComplete="off"
                    className="h-12 rounded-xl font-mono text-center tracking-widest text-lg"
                    onKeyDown={e => e.key === 'Enter' && handleActivateCode()}
                  />
                  {codeActivated && (
                    <p className="text-xs text-emerald-600 font-bold text-center">激活码已使用，会员已开通！</p>
                  )}
                </div>
              )}

              {/* Step 3: Institution name */}
              {currentStep === 3 && (
                <div className="space-y-4">
                  <div className="space-y-1">
                    <h2 className="text-xl font-black">{t('step2.title')}</h2>
                    <p className="text-sm font-medium text-muted-foreground">{t('step2.subtitle')}</p>
                  </div>
                  <Input
                    placeholder={t('step2.placeholder')}
                    value={instName}
                    onChange={e => setInstName(e.target.value)}
                    autoComplete="organization"
                    className="h-12 rounded-xl text-lg"
                    autoFocus
                    onKeyDown={e => e.key === 'Enter' && handleNameNext()}
                  />
                </div>
              )}

              {/* Step 4: Student scale */}
              {currentStep === 4 && (
                <div className="space-y-4">
                  <div className="space-y-1">
                    <h2 className="text-xl font-black">{t('step3.title')}</h2>
                    <p className="text-sm font-medium text-muted-foreground">{t('step3.subtitle')}</p>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    {SCALE_OPTIONS.map(scale => (
                      <button
                        key={scale}
                        type="button"
                        onClick={() => handleScaleSelect(scale)}
                        className="p-4 rounded-xl border-2 border-border hover:border-primary hover:bg-primary/5 transition-all text-center font-bold text-sm"
                      >
                        {t(`step3.options.${scale}`)}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Step 5: Subject selection */}
              {currentStep === 5 && (
                <div className="space-y-4">
                  <div className="space-y-1">
                    <h2 className="text-xl font-black">{t('step4.title')}</h2>
                    <p className="text-sm font-medium text-muted-foreground">
                      {plan
                        ? t('step4.subtitle_plan', { plan: plan.toUpperCase(), count: PLAN_DIRECTION_LIMITS[plan] || 1 })
                        : t('step4.subtitle_default')}
                    </p>
                  </div>
                  <div className="max-h-[280px] overflow-y-auto pr-1 -mx-1 px-1">
                    <DirectionSelector
                      categories={subjects}
                      selected={selectedSubjects}
                      onSelectionChange={setSelectedSubjects}
                      maxSelections={PLAN_DIRECTION_LIMITS[plan] || 1}
                    />
                  </div>
                </div>
              )}

              {/* Step 6: Description */}
              {currentStep === 6 && (
                <div className="space-y-4">
                  <div className="space-y-1">
                    <h2 className="text-xl font-black">{t('step5.title')}</h2>
                    <p className="text-sm font-medium text-muted-foreground">{t('step5.subtitle')}</p>
                  </div>
                  <textarea
                    placeholder={t('step5.placeholder')}
                    value={description}
                    onChange={e => setDescription(e.target.value)}
                    rows={3}
                    className="w-full rounded-xl border border-input bg-background px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-ring"
                  />
                </div>
              )}
            </div>

            {/* Error */}
            {error && <p className="text-xs text-red-500" role="alert">{error}</p>}

            {/* Progress dots (teacher path only) */}
            {showTeacherProgress && (
              <div className="flex items-center justify-center gap-2">
                {Array.from({ length: TEACHER_STEPS }, (_, i) => (
                  <div
                    key={i}
                    className={`h-2 w-2 rounded-full transition-all duration-300 ${
                      i + 1 === teacherCurrentStep
                        ? 'bg-primary w-4'
                        : i + 1 < teacherCurrentStep
                          ? 'bg-primary/60'
                          : 'bg-muted-foreground/20'
                    }`}
                  />
                ))}
              </div>
            )}

            {/* Navigation buttons */}
            {role === 'teacher' && currentStep >= 2 && (
              <div className="flex gap-2">
                {currentStep > 2 && currentStep < 6 && (
                  <Button variant="outline" className="flex-1 h-11 rounded-xl"
                    onClick={() => goToStep(currentStep - 1)}>
                    {t('wizard.back')}
                  </Button>
                )}
                {currentStep === 2 && (
                  <>
                    <Button variant="outline" className="flex-1 h-11 rounded-xl" onClick={() => goToStep(3)}>
                      跳过
                    </Button>
                    <Button variant="apple" className="flex-1 h-11 rounded-xl" onClick={handleActivateCode} disabled={loading || !activationCode.trim()}>
                      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : '激活'}
                    </Button>
                  </>
                )}
                {currentStep === 3 && (
                  <Button variant="apple" className="flex-1 h-11 rounded-xl" onClick={handleNameNext}>
                    {t('wizard.next')}
                  </Button>
                )}
                {currentStep === 5 && (
                  <Button variant="apple" className="flex-1 h-11 rounded-xl" onClick={handleSubjectsNext}>
                    {t('wizard.next')}
                  </Button>
                )}
                {currentStep === 6 && (
                  <>
                    <Button variant="outline" className="flex-1 h-11 rounded-xl" onClick={handleCreate} disabled={loading}>
                      {t('wizard.skip')}
                    </Button>
                    <Button variant="apple" className="flex-1 h-11 rounded-xl" onClick={handleCreate} disabled={loading}>
                      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : t('wizard.finish')}
                    </Button>
                  </>
                )}
              </div>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
