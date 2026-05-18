# Knowledge Tree Presets + Institution Onboarding Design

**Date:** 2026-05-19 | **Status:** Draft

## Problem

Landing page claims 10+ pre-built knowledge frameworks. Reality: only Finance 431 exists. Institution creation has no direction selection or auto-import — every institution starts with an empty knowledge tree.

## Scope

Two independent workstreams:

| # | Workstream | Deliverable |
|---|-----------|-------------|
| 1 | AI batch-generate knowledge trees for 17 subjects | `backend/knowledge_trees/*.md` files + management command |
| 2 | Add business direction selection to institution onboarding | Frontend OnboardingDialog step + backend clone logic |

---

## Part 1: AI Batch Knowledge Tree Generation

### Subjects (17 total)

**中文 (8):** 金融431 (already exists), 法学, 计算机408, 教育学311, CPA, CFA, 法考, 教资
**English (9):** SAT, ACT, MCAT, LSAT, GRE, GMAT, USMLE, IELTS, TOEFL

### Format

Same as existing `backend/knowledge_tree.md`:

```
# SUB-01 货币银行学
## CH-01 货币与货币制度
### SEC-01 货币的起源与形态演变
- KP-01 实物货币与金属货币的历史
- KP-02 信用货币的产生
```

- 4-8 SUB per subject, 3-8 CH per SUB, 2-6 SEC per CH, 3-10 KP per SEC
- Code format: `SUB-01`, `CH-01`, `SEC-01`, `KP-01` (reset per chapter, e.g., `CH-02` → `SEC-01`, `KP-01`)
- Description in parentheses after name is allowed (e.g., `货币银行学（Monetary Banking）`)

### Generation Tool

New management command:

```bash
python manage.py generate_knowledge_tree --subject "法学"
python manage.py generate_knowledge_tree --subject "IELTS" --dry-run  # preview only
```

Implementation:
- `backend/quizzes/management/commands/generate_knowledge_tree.py`
- Calls DeepSeek v4-pro with a structured prompt (format template + subject syllabus constraints)
- Output to `backend/knowledge_trees/<subject>.md`
- Existing `finance_431.md` is deleted; `knowledge_tree.md` is the canonical Finance 431 source

### Import

After manual spot-check, each subject is imported as global (institution=NULL):

```bash
python manage.py import_knowledge_tree backend/knowledge_trees/法学.md --global --force
```

The `import_knowledge_tree` command is modified to support multi-subject global import — instead of deleting all global KPs, only clear and re-import nodes for the matching top-level SUB codes.

### MD files are not user-facing

MD files are import sources only. Users see imported knowledge trees in the frontend. After import, MD files can be archived or deleted — they serve no runtime purpose.

---

## Part 2: Institution Onboarding — Business Direction Selection

### Plan Constraints

Free users cannot create institutions (InstitutionCreateView requires PlanInviteCode). Only Solo, Plus, Pro are relevant.

| Plan | Max directions | Rationale |
|------|---------------|-----------|
| Solo | 1 | Single-teacher, single subject |
| Plus | 3 | Small team, multiple subjects |
| Pro | Unlimited | Self-hosted, institution manages own scope |

Plan is known when the user enters onboarding — invite code validation returns `(plan, duration_days)`.

### Flow Change

```
Before:
  Role select → Institution info → Done (empty tree)

After:
  Role select → Institution info → Direction select → Done (trees imported)
```

### New Step: Direction Selection (OnboardingDialog)

- Subject list fetched from global knowledge points: `GET /api/quizzes/knowledge-points/subjects/` returns top-level SUB nodes with `institution__isnull=True`, grouped by category
- Categories: 考研专业课 / 职业资格证 / 海外考试
- Search/filter bar at top
- Multi-select checkboxes (count gated by plan)
- "自定义：我自己搭知识树" option at bottom — selects nothing, imports nothing
- Selection stored to `business_type` field on Institution model

### Backend: Clone on Institution Create

`InstitutionCreateView` modified:

1. Accept new field `subject_codes: list[str]` in request body
2. After institution creation, for each selected SUB code:
   - Find the global SUB node + all its descendants (recursive FK traversal)
   - Clone them to the new institution (new IDs, `institution=inst`, parent relationships remapped)
3. If `subject_codes` is empty or contains "custom", skip clone — institution starts with empty tree

No markdown parsing at runtime — clone directly from DB global KnowledgePoint records.

### New API Endpoint

`GET /api/quizzes/knowledge-points/subjects/` — returns global top-level subjects:

```json
{
  "categories": [
    {
      "name": "考研专业课",
      "subjects": [
        {"code": "SUB-FIN-01", "name": "金融431", "description": "..."},
        {"code": "SUB-LAW-01", "name": "法学", "description": "..."}
      ]
    }
  ]
}
```

---

## Implementation Order

1. Modify `import_knowledge_tree` to support multi-subject global imports
2. Build `generate_knowledge_tree` management command
3. Generate + import all 16 new subjects (Finance 431 already done)
4. Clean up: delete `finance_431.md`, ensure `knowledge_tree.md` is the canonical Finance 431 source
5. Add `GET /api/quizzes/knowledge-points/subjects/` endpoint
6. Modify `InstitutionCreateView` to accept `subject_codes` and clone KPs
7. Add direction selection step to `OnboardingDialog`

---

## Files Affected

| File | Change |
|------|--------|
| `backend/knowledge_trees/*.md` | New — 17 subject markdown files |
| `backend/quizzes/management/commands/generate_knowledge_tree.py` | New — AI generation command |
| `backend/quizzes/management/commands/import_knowledge_tree.py` | Modify — multi-subject global import |
| `backend/quizzes/views_knowledge.py` | Modify — new subjects endpoint |
| `backend/quizzes/urls.py` | Modify — route for subjects endpoint |
| `backend/users/views_institution.py` | Modify — accept subject_codes, clone KPs |
| `backend/users/serializers_institution.py` | Modify — add subject_codes field |
| `frontend/src/components/OnboardingDialog.tsx` | Modify — add direction selection step |
| `backend/finance_431.md` | Delete |
