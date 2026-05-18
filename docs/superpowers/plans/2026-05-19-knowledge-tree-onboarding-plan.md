# Knowledge Tree Presets + Institution Onboarding — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** AI-batch-generate 17-subject knowledge trees, add business direction selection to institution onboarding with auto-import.

**Architecture:** Two-phase: (1) Add `subject` field to KnowledgePoint, modify import command for multi-subject global co-existence, build AI generation command, generate+import all 17 subjects. (2) Expose subjects API, add validate-invite-code endpoint, modify InstitutionCreateView to clone global KPs, add direction-selection step to OnboardingDialog.

**Tech Stack:** Django 6.0, DeepSeek V4 Pro (via AIService), React 19, TypeScript

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `backend/quizzes/models.py` | Modify | Add `subject` field to KnowledgePoint |
| `backend/quizzes/management/commands/import_knowledge_tree.py` | Modify | `--subject` flag, scoped clear, set subject on import |
| `backend/quizzes/management/commands/generate_knowledge_tree.py` | Create | AI generation via DeepSeek, output MD files |
| `backend/knowledge_trees/*.md` | Create | 16 generated subject files + 1 existing |
| `backend/finance_431.md` | Delete | Duplicate; `knowledge_tree.md` is canonical |
| `backend/quizzes/views_knowledge.py` | Modify | Add `KnowledgePointSubjectsView` |
| `backend/quizzes/urls.py` | Modify | Route for subjects endpoint |
| `backend/users/views_institution.py` | Modify | `ValidateInviteCodeView` + clone logic in `InstitutionCreateView` |
| `backend/users/urls.py` | Modify | Route for validate-invite-code |
| `frontend/src/components/OnboardingDialog.tsx` | Modify | Direction selection step |

---

### Task 1: Add `subject` field to KnowledgePoint model

**Files:**
- Modify: `backend/quizzes/models.py:4-19`

- [ ] **Step 1: Add the field to the model**

```python
# backend/quizzes/models.py — add after `institution` field (line 17)
subject = models.CharField(max_length=100, blank=True, null=True, verbose_name="学科名称", help_text="如 金融431、法学、IELTS 等")
```

- [ ] **Step 2: Make migration**

```bash
cd backend && python manage.py makemigrations quizzes
```

Expected: generates `quizzes/migrations/0031_knowledgepoint_subject.py` (or next available number)

- [ ] **Step 3: Run migration**

```bash
cd backend && python manage.py migrate
```

Expected: `Applying quizzes.0031... OK`

- [ ] **Step 4: Commit**

```bash
git add backend/quizzes/models.py backend/quizzes/migrations/0031_*.py
git commit -m "feat: add subject field to KnowledgePoint model"
```

---

### Task 2: Modify `import_knowledge_tree` for multi-subject support

**Files:**
- Modify: `backend/quizzes/management/commands/import_knowledge_tree.py`

**Context:** Currently `--global` clears ALL global KPs before import. With 17 subjects, each import must only affect its own subject's nodes.

- [ ] **Step 1: Add `--subject` argument**

In `add_arguments`, after `--global`:

```python
parser.add_argument('--subject', type=str, help='学科名称（如 金融431、法学），用于多学科全局共存')
```

- [ ] **Step 2: Change the clear logic to scope by subject**

Replace the existing scope filter + delete block (lines 47-62):

```python
# Determine scope for clearing existing nodes
if institution:
    scope_filter = {'institution': institution}
    scope_label = f'机构「{institution.name}」'
elif kwargs.get('global'):
    subject = kwargs.get('subject') or ''
    if subject:
        scope_filter = {'institution__isnull': True, 'subject': subject}
        scope_label = f'全局「{subject}」'
    else:
        scope_filter = {'institution__isnull': True}
        scope_label = '全局'
else:
    scope_filter = {'institution__isnull': True}
    scope_label = '全局'

existing = KnowledgePoint.objects.filter(**scope_filter).count()

if not kwargs.get('force'):
    if existing > 0:
        confirm = input(
            f'{scope_label} 当前有 {existing} 个节点。'
            f'清空并重新导入？[y/N] '
        )
        if confirm.strip().lower() != 'y':
            self.stdout.write('已取消。')
            return

KnowledgePoint.objects.filter(**scope_filter).delete()
self.stdout.write(f"清理了 {scope_label} 的旧知识树数据。")
```

- [ ] **Step 3: Set subject on each created KnowledgePoint**

In the creation block (line 104), add `subject`:

```python
kp = KnowledgePoint.objects.create(
    code=code.strip(),
    name=clean_name,
    description=raw_name,
    level=level_str,
    parent=parent,
    order=order_counter[order_key],
    institution=institution,
    subject=kwargs.get('subject') or '',
)
```

- [ ] **Step 4: Commit**

```bash
git add backend/quizzes/management/commands/import_knowledge_tree.py
git commit -m "feat: add --subject flag to import_knowledge_tree for multi-subject global imports"
```

---

### Task 3: Build `generate_knowledge_tree` management command

**Files:**
- Create: `backend/quizzes/management/commands/generate_knowledge_tree.py`

- [ ] **Step 1: Create the command file**

```python
import os
from django.core.management.base import BaseCommand
from ai_engine.ai_service import AIService


PROMPT_TEMPLATE = """你是一位教育课程设计专家。请为「{subject}」生成一份完整的知识点树（知识图谱），用于 AI 出题系统的知识体系基础。

## 输出格式要求

严格使用以下 Markdown 层级格式，不得偏离：

```
# [SUB-01] 科目模块名称（英文名）
## [CH-01] 章名称
### [SEC-01] 节名称
- [KP-01] 知识点名称
```

## 规模要求

- 4-8 个 SUB（一级模块）
- 每个 SUB 下 3-8 个 CH（章）
- 每个 CH 下 2-6 个 SEC（节）
- 每个 SEC 下 3-10 个 KP（知识点）
- 每个知识点的 code 格式：KP-序号，每节内从 01 开始重新编号

## 内容要求

1. 覆盖该学科的核心知识体系，基于公开考纲和主流教材
2. 知识点颗粒度适中：既不能太粗（一个 KP 涵盖过大范围），也不能太细（拆分到无意义的细节）
3. 名称后可加括号备注英文，如 `[SUB-01] 货币银行学（Monetary Banking）`
4. 知识点名称简洁明确，一句话说清是什么

## 学科背景

{subject_context}

请直接输出 Markdown，不要加任何前言后语。"""

SUBJECT_CONTEXTS = {
    '法学': '法学硕士（法律硕士）全国联考核心知识体系，涵盖法理学、宪法学、法制史、民法学、刑法学、行政法学、诉讼法学等核心科目。',
    '计算机408': '全国硕士研究生招生考试计算机学科专业基础综合（408），涵盖数据结构、计算机组成原理、操作系统、计算机网络四大核心科目。',
    '教育学311': '全国硕士研究生招生考试教育学专业基础综合（311），涵盖教育学原理、中外教育史、教育心理学、教育研究方法等核心科目。',
    'CPA': '中国注册会计师（CPA）全国统一考试专业阶段，涵盖会计、审计、财务成本管理、经济法、税法、公司战略与风险管理六科。',
    'CFA': 'CFA（特许金融分析师）考试知识体系，涵盖道德与职业标准、定量方法、经济学、财务报表分析、公司金融、权益投资、固定收益、衍生品、另类投资、投资组合管理。',
    '法考': '国家统一法律职业资格考试，涵盖中国特色社会主义法治理论、法理学、宪法、刑法、刑事诉讼法、民法、民事诉讼法、行政法与行政诉讼法、商经法、国际法等。',
    '教资': '教师资格证考试（中学段）核心知识体系，涵盖教育学、心理学、教育心理学、教育法律法规、教师职业道德、新课程改革等。',
    'SAT': 'SAT (Scholastic Assessment Test) — covers Reading, Writing and Language, Math (with and without calculator), and optional Essay sections aligned with College Board standards.',
    'ACT': 'ACT (American College Testing) — covers English, Mathematics, Reading, Science Reasoning, and optional Writing sections.',
    'MCAT': 'MCAT (Medical College Admission Test) — covers Biological and Biochemical Foundations, Chemical and Physical Foundations, Psychological/Social/Biological Foundations, and Critical Analysis and Reasoning Skills (CARS).',
    'LSAT': 'LSAT (Law School Admission Test) — covers Logical Reasoning, Analytical Reasoning (Logic Games), Reading Comprehension, and Writing Sample sections.',
    'GRE': 'GRE (Graduate Record Examination) General Test — covers Verbal Reasoning, Quantitative Reasoning, and Analytical Writing sections.',
    'GMAT': 'GMAT (Graduate Management Admission Test) — covers Quantitative Reasoning, Verbal Reasoning, Integrated Reasoning, and Analytical Writing Assessment.',
    'USMLE': 'USMLE (United States Medical Licensing Examination) — Step 1 (basic sciences), Step 2 CK (clinical knowledge), Step 3 (clinical management), covering foundational and clinical medical sciences.',
    'IELTS': 'IELTS (International English Language Testing System) — Academic and General Training modules covering Listening, Reading, Writing, and Speaking sections.',
    'TOEFL': 'TOEFL iBT (Test of English as a Foreign Language) — covers Reading, Listening, Speaking, and Writing sections aligned with ETS standards.',
}


class Command(BaseCommand):
    help = '使用 AI 批量生成学科知识树 Markdown 文件'

    def add_arguments(self, parser):
        parser.add_argument('--subject', type=str, required=True, help='学科名称，如 法学、IELTS')
        parser.add_argument('--dry-run', action='store_true', help='仅预览 AI 输出，不写入文件')
        parser.add_argument('--output-dir', type=str, default=None, help='输出目录，默认 backend/knowledge_trees/')

    def handle(self, *args, **kwargs):
        subject = kwargs['subject']
        dry_run = kwargs['dry_run']
        output_dir = kwargs['output_dir']

        if output_dir is None:
            output_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
                'knowledge_trees'
            )

        context = SUBJECT_CONTEXTS.get(subject, f'{subject} 的核心知识体系。')
        prompt = PROMPT_TEMPLATE.format(subject=subject, subject_context=context)

        self.stdout.write(f'正在为「{subject}」生成知识树...')

        result = AIService.simple_chat_text(
            system_prompt='你是一位资深教育课程设计师，精通知识体系构建。请严格按照指定格式生成内容，不添加任何额外说明。',
            user_prompt=prompt,
            temperature=0.3,
            max_tokens=16384,
            operation='generate_knowledge_tree',
        )

        if not result:
            self.stdout.write(self.style.ERROR('AI 返回为空，请重试。'))
            return

        if dry_run:
            self.stdout.write('─── 预览（dry-run）───')
            self.stdout.write(result)
            self.stdout.write('─── 结束 ───')
            return

        os.makedirs(output_dir, exist_ok=True)
        filename = f'{subject}.md'
        filepath = os.path.join(output_dir, filename)

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(result)

        self.stdout.write(self.style.SUCCESS(f'知识树已保存到: {filepath}'))
```

- [ ] **Step 2: Add task model routing for the new operation**

In `backend/ai_engine/config.py`, add to `_TASK_MODEL_MAP`:

```python
# In the Pro section, add:
'generate_knowledge_tree': 'deepseek-v4-pro',
```

- [ ] **Step 3: Test with a single subject (dry-run)**

```bash
cd backend && python manage.py generate_knowledge_tree --subject "法学" --dry-run
```

Expected: prints the generated markdown tree to stdout.

- [ ] **Step 4: Commit**

```bash
git add backend/quizzes/management/commands/generate_knowledge_tree.py backend/ai_engine/config.py
git commit -m "feat: add generate_knowledge_tree management command"
```

---

### Task 4: Import Finance 431 with subject tagging, delete duplicate

**Files:**
- Modify: `backend/knowledge_tree.md` (re-import with `--subject`)
- Delete: `backend/finance_431.md`

- [ ] **Step 1: Import Finance 431 as global with subject tag**

```bash
cd backend && python manage.py import_knowledge_tree backend/knowledge_tree.md --global --subject "金融431" --force
```

Expected: imports all Finance 431 nodes with `subject='金融431'`, `institution=NULL`.

- [ ] **Step 2: Delete the duplicate file**

```bash
rm backend/finance_431.md
```

- [ ] **Step 3: Commit**

```bash
git add backend/finance_431.md
git commit -m "chore: remove duplicate finance_431.md, canonical source is knowledge_tree.md"
```

---

### Task 5: Generate + import remaining 16 subjects

**Note:** This task is run manually by the developer. Each subject takes ~30-60s of AI generation time.

- [ ] **Step 1: Generate all 16 subjects**

```bash
cd backend
for subject in "法学" "计算机408" "教育学311" "CPA" "CFA" "法考" "教资" "SAT" "ACT" "MCAT" "LSAT" "GRE" "GMAT" "USMLE" "IELTS" "TOEFL"; do
  echo "=== 正在生成: $subject ==="
  python manage.py generate_knowledge_tree --subject "$subject"
done
```

- [ ] **Step 2: Spot-check 2-3 generated files for quality**

Read and verify format correctness, content relevance. Fix obvious issues (e.g., duplicate codes, missing levels).

- [ ] **Step 3: Import all as global**

```bash
cd backend
for file in backend/knowledge_trees/*.md; do
  subject=$(basename "$file" .md)
  echo "=== 正在导入: $subject ==="
  python manage.py import_knowledge_tree "$file" --global --subject "$subject" --force
done
```

- [ ] **Step 4: Verify global knowledge points count**

```bash
cd backend && python manage.py shell -c "
from quizzes.models import KnowledgePoint
from django.db.models import Count
for s in KnowledgePoint.objects.filter(institution__isnull=True).values('subject').annotate(n=Count('id')).order_by('subject'):
    print(f\"{s['subject']}: {s['n']} nodes\")
"
```

Expected: 17 subjects each with hundreds of nodes.

- [ ] **Step 5: Commit (MD files are not committed per docs policy)**

No commit needed — `backend/knowledge_trees/` is gitignored or not committed per project policy. The trees live in the database.

---

### Task 6: Add subjects API endpoint

**Files:**
- Modify: `backend/quizzes/views_knowledge.py`
- Modify: `backend/quizzes/urls.py`

- [ ] **Step 1: Add the view**

In `backend/quizzes/views_knowledge.py`, add:

```python
from rest_framework.views import APIView
from rest_framework.response import Response
from quizzes.models import KnowledgePoint

# Category → subject name mapping
SUBJECT_CATEGORIES = {
    '考研专业课': ['金融431', '法学', '计算机408', '教育学311'],
    '职业资格证': ['CPA', 'CFA', '法考', '教资'],
    '海外考试': ['SAT', 'ACT', 'MCAT', 'LSAT', 'GRE', 'GMAT', 'USMLE', 'IELTS', 'TOEFL'],
}

class KnowledgePointSubjectsView(APIView):
    """Return global top-level subjects grouped by category, for institution onboarding."""
    permission_classes = []  # public endpoint

    def get(self, request):
        subjects_qs = KnowledgePoint.objects.filter(
            level='sub',
            institution__isnull=True,
        ).values('subject', 'code', 'name').order_by('subject', 'order')

        # group by subject name
        subject_map = {}
        for row in subjects_qs:
            s = row['subject']
            if s not in subject_map:
                subject_map[s] = {'subject': s, 'label': s, 'topics': []}
            subject_map[s]['topics'].append({
                'code': row['code'],
                'name': row['name'],
            })

        categories = []
        for cat_name, subjects in SUBJECT_CATEGORIES.items():
            cat_subjects = []
            for s in subjects:
                if s in subject_map:
                    cat_subjects.append(subject_map[s])
            if cat_subjects:
                categories.append({'name': cat_name, 'subjects': cat_subjects})

        return Response({'categories': categories})
```

- [ ] **Step 2: Add URL route**

In `backend/quizzes/urls.py`, add the import and route:

```python
from .views_knowledge import (
    KnowledgePointListView, KnowledgePointDetailView,
    KnowledgePointImportMDView, KnowledgePointExportMDView,
    KnowledgePointSubjectsView,  # NEW
)
```

Add route before `knowledge-points/`:

```python
path('knowledge-points/subjects/', KnowledgePointSubjectsView.as_view(), name='knowledge-point-subjects'),
```

- [ ] **Step 3: Test the endpoint**

```bash
cd backend && python manage.py runserver &
curl -s http://localhost:8000/api/quizzes/knowledge-points/subjects/ | python -m json.tool | head -40
```

Expected: JSON with categories and subjects.

- [ ] **Step 4: Commit**

```bash
git add backend/quizzes/views_knowledge.py backend/quizzes/urls.py
git commit -m "feat: add knowledge point subjects endpoint for onboarding"
```

---

### Task 7: Add validate-invite-code endpoint

**Files:**
- Modify: `backend/users/views_institution.py`
- Modify: `backend/users/urls.py`

**Context:** OnboardingDialog needs to know the plan BEFORE creating the institution, so it can enforce direction selection limits.

- [ ] **Step 1: Add the view**

In `backend/users/views_institution.py`, add after `InstitutionCreateView`:

```python
class ValidateInviteCodeView(APIView):
    """Validate a PlanInviteCode without consuming it — returns plan info for UI gating."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        invite_code = (request.data.get('invite_code') or '').strip().upper()
        if not invite_code:
            return Response({'error': '请输入方案邀请码'}, status=400)

        try:
            code_obj = PlanInviteCode.objects.get(code=invite_code, is_active=True)
        except PlanInviteCode.DoesNotExist:
            return Response({'error': '无效的方案邀请码'}, status=400)

        if code_obj.max_uses > 0 and code_obj.used_count >= code_obj.max_uses:
            return Response({'error': '该邀请码已达使用上限'}, status=400)

        return Response({
            'plan': code_obj.plan,
            'plan_label': code_obj.get_plan_display(),
            'duration_days': code_obj.duration_days,
        })
```

- [ ] **Step 2: Add URL route**

In `backend/users/urls.py`, find the institution routes section and add:

```python
path('institutions/validate-invite-code/', ValidateInviteCodeView.as_view(), name='validate-invite-code'),
```

Also update the import to include `ValidateInviteCodeView`.

- [ ] **Step 3: Commit**

```bash
git add backend/users/views_institution.py backend/users/urls.py
git commit -m "feat: add validate-invite-code endpoint for onboarding direction gating"
```

---

### Task 8: Add clone logic to InstitutionCreateView

**Files:**
- Modify: `backend/users/views_institution.py:716-775`

- [ ] **Step 1: Add the clone helper function**

At module level in `views_institution.py`, add:

```python
def _clone_knowledge_tree(subject_name, institution):
    """Clone all global KnowledgePoints for a subject into an institution scope."""
    global_kps = list(
        KnowledgePoint.objects.filter(
            subject=subject_name,
            institution__isnull=True,
        ).order_by('level', 'order')
    )
    if not global_kps:
        return 0

    old_to_new = {}
    for kp in global_kps:
        new_kp = KnowledgePoint(
            code=kp.code,
            name=kp.name,
            level=kp.level,
            prefix_category=kp.prefix_category,
            description=kp.description,
            parent=None,
            institution=institution,
            order=kp.order,
            subject=kp.subject,
        )
        new_kp.save()
        old_to_new[kp.id] = new_kp

    # Remap parent FK relationships
    for kp in global_kps:
        if kp.parent_id and kp.parent_id in old_to_new:
            new_kp = old_to_new[kp.id]
            new_kp.parent_id = old_to_new[kp.parent_id].id
            new_kp.save(update_fields=['parent'])

    return len(old_to_new)
```

Requires adding import at top of file:
```python
from quizzes.models import KnowledgePoint
```

- [ ] **Step 2: Modify InstitutionCreateView to accept and process subject_names**

After the institution is created (line 761) and before setting user fields, add:

```python
# Clone knowledge trees for selected subjects
subject_names = (request.data.get('subject_names') or [])
if isinstance(subject_names, str):
    subject_names = [s.strip() for s in subject_names.split(',') if s.strip()]

# Filter out "custom" — it means user wants empty tree
subject_names = [s for s in subject_names if s and s != 'custom']

DIRECTION_LIMITS = {'solo': 1, 'plus': 3, 'pro': 999999}
max_dirs = DIRECTION_LIMITS.get(plan, 1)
if len(subject_names) > max_dirs:
    return Response(
        {'error': f'{plan.upper()} 方案最多选择 {max_dirs} 个学科方向'},
        status=400,
    )

imported_count = 0
for s in subject_names:
    imported_count += _clone_knowledge_tree(s, inst)

# Also store business_type
inst.business_type = ', '.join(subject_names) if subject_names else '自定义'
inst.save(update_fields=['business_type'])
```

- [ ] **Step 3: Update response to include import info**

Add to the response dict:
```python
'imported_nodes': imported_count,
'subjects_imported': subject_names,
```

- [ ] **Step 4: Commit**

```bash
git add backend/users/views_institution.py
git commit -m "feat: clone global knowledge trees on institution creation with subject_names"
```

---

### Task 9: Add direction selection step to OnboardingDialog

**Files:**
- Modify: `frontend/src/components/OnboardingDialog.tsx`

- [ ] **Step 1: Add state variables and step type**

Add after existing state declarations (line 25):

```typescript
// Direction selection
const [plan, setPlan] = useState<string>('');
const [subjects, setSubjects] = useState<any[]>([]);
const [selectedSubjects, setSelectedSubjects] = useState<string[]>([]);
const [directionError, setDirectionError] = useState('');
```

- [ ] **Step 2: Modify the teacher form submit to first validate**

Replace the `handleCreateInstitution` function (lines 37-55) with a two-phase flow:

```typescript
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
    // Fetch subjects
    const subRes = await api.get('/quizzes/knowledge-points/subjects/');
    setSubjects(subRes.data.categories || []);
    setStep('directions');
  } catch (err: any) {
    setError(err.response?.data?.error || t('teacher.errors.invalidCode'));
  }
  setLoading(false);
};

const handleCreateWithDirections = async () => {
  setLoading(true); setDirectionError('');
  const limits: Record<string, number> = { solo: 1, plus: 3, pro: 999999 };
  const maxDirs = limits[plan] || 1;

  if (selectedSubjects.length === 0) {
    // OK — will be treated as "custom" (empty tree)
  } else if (selectedSubjects.length > maxDirs) {
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
```

- [ ] **Step 3: Add the direction selection UI step**

Add a new conditional branch before the closing `)` of the ternary chain, after the `step === 'teacher'` block:

```tsx
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

    <div className="space-y-3 max-h-[360px] overflow-y-auto pr-1">
      {subjects.map((cat: any) => (
        <div key={cat.name}>
          <p className="text-xs font-bold text-muted-foreground mb-2 uppercase tracking-wide">
            {cat.name}
          </p>
          <div className="grid grid-cols-2 gap-2">
            {cat.subjects.map((sub: any) => {
              const isSelected = selectedSubjects.includes(sub.subject);
              const limit = plan === 'solo' ? 1 : plan === 'plus' ? 3 : 999999;
              const atLimit = selectedSubjects.length >= limit && !isSelected;
              return (
                <button
                  key={sub.subject}
                  type="button"
                  disabled={atLimit}
                  onClick={() => {
                    if (isSelected) {
                      setSelectedSubjects(prev => prev.filter(s => s !== sub.subject));
                    } else if (!atLimit) {
                      setSelectedSubjects(prev => [...prev, sub.subject]);
                    }
                  }}
                  className={`text-left p-3 rounded-xl border-2 text-sm font-semibold transition-all ${
                    isSelected
                      ? 'border-[#0071E3] bg-[#0071E3]/8 text-[#0071E3]'
                      : atLimit
                        ? 'border-border bg-muted/30 text-muted-foreground cursor-not-allowed'
                        : 'border-border hover:border-[#0071E3]/40 hover:bg-[#0071E3]/3'
                  }`}
                >
                  {sub.label}
                </button>
              );
            })}
          </div>
        </div>
      ))}

      {/* Custom option */}
      <button
        type="button"
        onClick={() => {
          if (selectedSubjects.includes('custom')) {
            setSelectedSubjects([]);
          } else {
            setSelectedSubjects(['custom']);
          }
        }}
        className={`w-full p-3 rounded-xl border-2 text-sm font-semibold transition-all ${
          selectedSubjects.includes('custom')
            ? 'border-[#34C759] bg-[#34C759]/8 text-[#34C759]'
            : 'border-dashed border-muted-foreground/30 hover:border-[#34C759]/40 hover:bg-[#34C759]/3 text-muted-foreground'
        }`}
      >
        自定义：我自己搭建知识树
      </button>
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
)
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/OnboardingDialog.tsx
git commit -m "feat: add business direction selection to institution onboarding"
```

---

### Task 10: Integration test — end-to-end walkthrough

- [ ] **Step 1: Start backend and frontend**

```bash
cd backend && python manage.py runserver &
cd frontend && npm run dev &
```

- [ ] **Step 2: Create a Solo invite code for testing**

```bash
cd backend && python manage.py shell -c "
from users.models import PlanInviteCode
code = PlanInviteCode.generate(plan='solo', duration_days=365, max_uses=5)
print(f'Solo code: {code}')
"
```

- [ ] **Step 3: Register a new user and verify flow**

1. Register with email + code
2. Onboarding dialog appears → select teacher
3. Enter invite code + institution name → click create
4. Direction selection step appears with Solo limit (1)
5. Select "金融431" → create institution
6. Verify: institution created with knowledge tree populated
7. Check `business_type` field = "金融431"

- [ ] **Step 4: Verify clone correctness**

```bash
cd backend && python manage.py shell -c "
from quizzes.models import KnowledgePoint
inst_kps = KnowledgePoint.objects.filter(institution__isnull=False)
print(f'Institution KPs: {inst_kps.count()}')
for kp in inst_kps.filter(level='sub'):
    print(f'  [{kp.code}] {kp.name} (children: {kp.children.count()})')
"
```

Expected: institution has complete tree matching global Finance 431 structure.

---

## Self-Review Checklist

1. **Spec coverage:** All 7 items from Implementation Order are covered by tasks → Task 2 (import mod), Task 3+5 (generate), Task 4 (cleanup), Task 6 (subjects API), Task 8 (clone), Task 9 (frontend). Task 7 (validate endpoint) is a dependency for Task 9.
2. **Placeholder scan:** No TBD, TODO, or vague "add error handling" steps. All code is concrete.
3. **Type consistency:** `subject_names` used consistently between frontend and backend. `subject` field on model matches everywhere.
