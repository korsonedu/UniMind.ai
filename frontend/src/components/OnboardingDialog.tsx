import { useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { Dialog, DialogContent } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useAuthStore } from '@/store/useAuthStore';
import { useInstitutionStore } from '@/store/useInstitutionStore';
import api from '@/lib/api';
import { Check, Loader2 } from 'lucide-react';
import { DirectionSelector } from '@/components/DirectionSelector';

const TOTAL_STEPS = 5;

const SCALE_OPTIONS = ['1-50', '50-200', '200-500', '500+'] as const;

export function OnboardingDialog() {
  const { user, updateUser } = useAuthStore();
  const institution = useInstitutionStore(s => s.institution);
  const { t } = useTranslation('onboarding');

  const [dismissed, setDismissed] = useState(false);
  const [currentStep, setCurrentStep] = useState(1);
  const [animState, setAnimState] = useState<'visible' | 'exiting' | 'entering'>('visible');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);

  // Form state
  const [inviteCode, setInviteCode] = useState('');
  const [instName, setInstName] = useState('');
  const [studentScale, setStudentScale] = useState('');
  const [selectedSubjects, setSelectedSubjects] = useState<string[]>([]);
  const [description, setDescription] = useState('');

  // Direction data
  const [plan, setPlan] = useState('');
  const [subjects, setSubjects] = useState<any[]>([]);

  const PLAN_DIRECTION_LIMITS: Record<string, number> = { starter: 1, growth: 3, enterprise: 999999 };

  // Don't show if: no user / has institution / dismissed / platform admin
  if (!user || user.institution || user.institution_id || institution || dismissed) return null;
  if (user.is_admin) return null;

  const goToStep = useCallback((nextStep: number) => {
    setAnimState('exiting');
    setTimeout(() => {
      setCurrentStep(nextStep);
      setError('');
      setAnimState('entering');
      setTimeout(() => setAnimState('visible'), 300);
    }, 300);
  }, []);

  // Step 1: Validate invite code
  const handleValidateCode = async () => {
    if (!inviteCode.trim()) return setError(t('step1.error_empty'));
    setLoading(true); setError('');
    try {
      const { data } = await api.post('/users/institutions/validate-invite-code/', {
        invite_code: inviteCode.trim().toUpperCase(),
      });
      setPlan(data.plan);
      const subRes = await api.get('/quizzes/knowledge-points/subjects/');
      setSubjects(subRes.data.categories || []);
      goToStep(2);
    } catch (err: any) {
      setError(err.response?.data?.error || t('step1.error_invalid'));
    }
    setLoading(false);
  };

  // Step 2: Validate name
  const handleNameNext = () => {
    if (!instName.trim()) return setError(t('step2.error_empty'));
    goToStep(3);
  };

  // Step 3: Select scale → auto-advance
  const handleScaleSelect = (scale: string) => {
    setStudentScale(scale);
    goToStep(4);
  };

  // Step 4: Subjects → next
  const handleSubjectsNext = () => {
    goToStep(5);
  };

  // Step 5: Create institution
  const handleCreate = async () => {
    setLoading(true); setError('');
    try {
      const { data } = await api.post('/users/institutions/create/', {
        invite_code: inviteCode.trim().toUpperCase(),
        name: instName.trim(),
        description: description.trim(),
        student_scale: studentScale,
        subject_names: selectedSubjects.length > 0 ? selectedSubjects : ['custom'],
      });
      updateUser({ institution_id: data.institution.id, institution_role: 'owner' });
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

  return (
    <Dialog open={!dismissed} onOpenChange={(open) => { if (!open) setDismissed(true); }}>
      <DialogContent className="sm:max-w-lg rounded-2xl border-none shadow-2xl bg-card p-8 min-h-[400px]"
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
              {currentStep === 1 && (
                <div className="space-y-4">
                  <div className="space-y-1">
                    <h2 className="text-xl font-black">{t('step1.title')}</h2>
                    <p className="text-sm font-medium text-muted-foreground">{t('step1.subtitle')}</p>
                  </div>
                  <Input
                    placeholder={t('step1.placeholder')}
                    value={inviteCode}
                    onChange={e => setInviteCode(e.target.value.toUpperCase())}
                    spellCheck={false}
                    autoComplete="off"
                    className="h-12 rounded-xl font-mono text-center tracking-widest text-lg"
                    onKeyDown={e => e.key === 'Enter' && handleValidateCode()}
                  />
                </div>
              )}

              {currentStep === 2 && (
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

              {currentStep === 3 && (
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

              {currentStep === 4 && (
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

              {currentStep === 5 && (
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

            {/* Progress dots */}
            <div className="flex items-center justify-center gap-2">
              {Array.from({ length: TOTAL_STEPS }, (_, i) => (
                <div
                  key={i}
                  className={`h-2 w-2 rounded-full transition-all duration-300 ${
                    i + 1 === currentStep
                      ? 'bg-primary w-4'
                      : i + 1 < currentStep
                        ? 'bg-primary/60'
                        : 'bg-muted-foreground/20'
                  }`}
                />
              ))}
            </div>

            {/* Navigation buttons */}
            <div className="flex gap-2">
              {currentStep > 1 && currentStep < 5 && (
                <Button variant="outline" className="flex-1 h-11 rounded-xl"
                  onClick={() => goToStep(currentStep - 1)}>
                  {t('wizard.back')}
                </Button>
              )}
              {currentStep === 1 && (
                <Button variant="apple" className="flex-1 h-11 rounded-xl" onClick={handleValidateCode} disabled={loading}>
                  {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : t('wizard.next')}
                </Button>
              )}
              {currentStep === 2 && (
                <Button variant="apple" className="flex-1 h-11 rounded-xl" onClick={handleNameNext}>
                  {t('wizard.next')}
                </Button>
              )}
              {currentStep === 4 && (
                <Button variant="apple" className="flex-1 h-11 rounded-xl" onClick={handleSubjectsNext}>
                  {t('wizard.next')}
                </Button>
              )}
              {currentStep === 5 && (
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
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
