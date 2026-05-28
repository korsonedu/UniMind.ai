# Institution Onboarding Wizard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the existing OnboardingDialog with a card-based wizard — role selection (student/teacher) as step 1, then 5 steps for institution creation (teacher path only).

**Architecture:** Keep the dialog form factor in MainLayout, rewrite internals as a multi-card wizard. Step 1 is role selection: students see guidance to get invite link, teachers proceed to institution creation. Backend adds `student_scale` field to Institution model, `join-by-invite-slug` endpoint for existing account binding, and passes it through the existing create API.

**Tech Stack:** React 19, shadcn/ui Dialog, CSS transitions, Django REST Framework

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `backend/users/models.py:146-167` | Modify | Add `student_scale` field to Institution |
| `backend/users/serializers_institution.py:5-20` | Modify | Add `student_scale` to InstitutionSerializer fields |
| `backend/users/views_institution.py:783-867` | Modify | Accept and save `student_scale` in InstitutionCreateView |
| `backend/users/migrations/XXXX_add_student_scale.py` | Create | Auto-generated migration |
| `frontend/src/components/OnboardingDialog.tsx` | Rewrite | Card-based wizard component |
| `frontend/src/locales/zh/onboarding.json` | Rewrite | Chinese translations for wizard |
| `frontend/src/locales/en/onboarding.json` | Rewrite | English translations for wizard |

---

### Task 1: Add `student_scale` to Institution model

**Files:**
- Modify: `backend/users/models.py:162` (after `business_type` field)

- [ ] **Step 1: Add the field**

Add after line 162 (`business_type = ...`):

```python
    student_scale = models.CharField(
        max_length=20,
        choices=[
            ('1-50', '1-50 人'),
            ('50-200', '50-200 人'),
            ('200-500', '200-500 人'),
            ('500+', '500+ 人'),
        ],
        blank=True,
        default='',
        verbose_name="学员规模",
    )
```

- [ ] **Step 2: Generate migration**

Run: `cd /Users/eular/Desktop/UniMind/UniMindCode/backend && python manage.py makemigrations users --name add_student_scale`

Expected: `Migrations for 'users': users/migrations/XXXX_add_student_scale.py - Add field student_scale to institution`

- [ ] **Step 3: Verify migration**

Run: `cd /Users/eular/Desktop/UniMind/UniMindCode/backend && python manage.py migrate --run-syncdb 2>&1 | tail -5`

Expected: No errors.

- [ ] **Step 4: Commit**

```bash
git add backend/users/models.py backend/users/migrations/
git commit -m "feat: add student_scale field to Institution model"
```

---

### Task 2: Update serializers and create view

**Files:**
- Modify: `backend/users/serializers_institution.py:13-19`
- Modify: `backend/users/views_institution.py:833-843`

- [ ] **Step 1: Add student_scale to InstitutionSerializer**

In `backend/users/serializers_institution.py`, add `'student_scale'` to the `fields` list in `InstitutionSerializer.Meta` (line 18, after `'business_type'`):

```python
            'custom_domain', 'logo', 'business_type', 'student_scale', 'description', 'notes',
```

- [ ] **Step 2: Accept student_scale in InstitutionCreateView**

In `backend/users/views_institution.py`, inside `InstitutionCreateView.post()`, add after line 816 (`description = ...`):

```python
        student_scale = (request.data.get('student_scale') or '').strip()
```

Then in the `Institution.objects.create(...)` call (line 833), add `student_scale=student_scale`:

```python
        inst = Institution.objects.create(
            name=name, slug=slug,
            contact_name=contact_name,
            contact_email=contact_email,
            contact_phone=contact_phone,
            description=description,
            student_scale=student_scale,
            plan=plan,
            plan_expires_at=compute_expiry(duration_days),
            created_by=user,
            is_active=True,
        )
```

- [ ] **Step 3: Verify backend still works**

Run: `cd /Users/eular/Desktop/UniMind/UniMindCode/backend && python manage.py check`

Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 4: Commit**

```bash
git add backend/users/serializers_institution.py backend/users/views_institution.py
git commit -m "feat: pass student_scale through serializer and create view"
```

---

### Task 3: Update i18n translations

**Files:**
- Rewrite: `frontend/src/locales/zh/onboarding.json`
- Rewrite: `frontend/src/locales/en/onboarding.json`

- [ ] **Step 1: Write Chinese translations**

Replace `frontend/src/locales/zh/onboarding.json` with:

```json
{
  "wizard": {
    "next": "下一步",
    "finish": "完成",
    "skip": "跳过",
    "back": "返回",
    "creating": "创建中…"
  },
  "step1": {
    "title": "欢迎使用 UniMind！",
    "subtitle": "请输入您的邀请码开始创建机构",
    "placeholder": "请输入邀请码",
    "error_empty": "请输入邀请码",
    "error_invalid": "邀请码无效"
  },
  "step2": {
    "title": "给你的机构起个名字吧",
    "subtitle": "这将展示在学员端和邀请链接中",
    "placeholder": "例如：宇艺教育",
    "error_empty": "请输入机构名称"
  },
  "step3": {
    "title": "你的机构目前有多少学生？",
    "subtitle": "帮助我们为你推荐合适的方案",
    "options": {
      "1-50": "1-50 人",
      "50-200": "50-200 人",
      "200-500": "200-500 人",
      "500+": "500+ 人"
    }
  },
  "step4": {
    "title": "你主要教哪些科目？",
    "subtitle_plan": "{{plan}} 方案最多选择 {{count}} 个学科方向",
    "subtitle_default": "选择你机构的学科方向"
  },
  "step5": {
    "title": "简单介绍一下你的机构",
    "subtitle": "让学员快速了解你（可选）",
    "placeholder": "例如：专注金融考研辅导 10 年，累计培训 5000+ 学员"
  },
  "done": {
    "title": "设置完成！",
    "subtitle": "你的机构已创建成功，现在可以邀请学员、生成题目了。",
    "enter": "进入 UniMind"
  }
}
```

- [ ] **Step 2: Write English translations**

Replace `frontend/src/locales/en/onboarding.json` with:

```json
{
  "wizard": {
    "next": "Next",
    "finish": "Finish",
    "skip": "Skip",
    "back": "Back",
    "creating": "Creating…"
  },
  "step1": {
    "title": "Welcome to UniMind!",
    "subtitle": "Enter your invite code to create your institution",
    "placeholder": "Enter invite code",
    "error_empty": "Please enter an invite code",
    "error_invalid": "Invalid invite code"
  },
  "step2": {
    "title": "Name your institution",
    "subtitle": "This will be shown to students and in invite links",
    "placeholder": "e.g., Bright Future Education",
    "error_empty": "Please enter an institution name"
  },
  "step3": {
    "title": "How many students do you have?",
    "subtitle": "Helps us recommend the right plan for you",
    "options": {
      "1-50": "1-50",
      "50-200": "50-200",
      "200-500": "200-500",
      "500+": "500+"
    }
  },
  "step4": {
    "title": "What subjects do you teach?",
    "subtitle_plan": "{{plan}} plan — up to {{count}} subject directions",
    "subtitle_default": "Select your subject directions"
  },
  "step5": {
    "title": "Tell us about your institution",
    "subtitle": "Help students understand what you offer (optional)",
    "placeholder": "e.g., 10 years of CFA exam prep, 5000+ students trained"
  },
  "done": {
    "title": "All Set!",
    "subtitle": "Your institution has been created. You can now invite students and generate questions.",
    "enter": "Enter UniMind"
  }
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/locales/zh/onboarding.json frontend/src/locales/en/onboarding.json
git commit -m "feat: update i18n translations for onboarding wizard"
```

---

### Task 4: Rewrite OnboardingDialog as card-based wizard

**Files:**
- Rewrite: `frontend/src/components/OnboardingDialog.tsx`

- [ ] **Step 1: Rewrite the component**

Replace the entire `frontend/src/components/OnboardingDialog.tsx` with:

```tsx
import { useState, useEffect, useCallback } from 'react';
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
        // Hide close button — onboarding should not be easily dismissed
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
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd /Users/eular/Desktop/UniMind/UniMindCode/frontend && npx tsc --noEmit 2>&1 | grep -i OnboardingDialog || echo "No errors in OnboardingDialog"`

Expected: No errors.

- [ ] **Step 3: Verify frontend builds**

Run: `cd /Users/eular/Desktop/UniMind/UniMindCode/frontend && npx vite build 2>&1 | tail -5`

Expected: Build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/OnboardingDialog.tsx
git commit -m "feat: rewrite OnboardingDialog as card-based onboarding wizard"
```

---

### Task 5: Verify integration

- [ ] **Step 1: Run backend checks**

Run: `cd /Users/eular/Desktop/UniMind/UniMindCode && make backend-check`

Expected: No errors.

- [ ] **Step 2: Run frontend checks**

Run: `cd /Users/eular/Desktop/UniMind/UniMindCode && make frontend-check`

Expected: No errors.

- [ ] **Step 3: Final commit if needed**

If any fixes were needed, commit them.
