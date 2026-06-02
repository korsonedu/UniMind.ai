# Action Cards Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `action_cards` visual type to XiaoYu's VisualCanvas — AI-driven masonry-layout cards with direct jump links for guiding next learning steps.

**Architecture:** New `ActionCardsRenderer.tsx` using CSS Grid (2-column, high-priority spans full width). Backend adds `'action_cards'` to valid render_visual types and updates prompt to guide AI on when/how to generate actionable cards.

**Tech Stack:** React 19, Tailwind CSS, CSS Grid, Lucide icons, Django (prompt + tool_executor)

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `frontend/src/pages/xiaoyu/visuals/ActionCardsRenderer.tsx` | Create | Masonry grid renderer for action cards |
| `frontend/src/pages/xiaoyu/visuals/index.ts` | Modify | Register `action_cards` in RENDERERS map |
| `backend/ai_assistant/services/tool_executor.py:728` | Modify | Add `'action_cards'` to `valid_types` set |
| `backend/prompts/ai_assistant/bots/xiaoyu/tool_guide.txt` | Modify | Add action_cards usage guide + data combination flow |

---

### Task 1: Create ActionCardsRenderer

**Files:**
- Create: `frontend/src/pages/xiaoyu/visuals/ActionCardsRenderer.tsx`

- [ ] **Step 1: Create the renderer component**

```tsx
// frontend/src/pages/xiaoyu/visuals/ActionCardsRenderer.tsx
import React, { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  PlayCircle, PenLine, RotateCcw, BookOpen, TrendingUp, Calendar, FileText,
  ArrowRight,
} from 'lucide-react';
import { cn } from '@/lib/utils';

// --- Types ---

type ActionType = 'video' | 'quiz' | 'review' | 'course' | 'article' | 'plan' | 'exam';
type Priority = 'high' | 'normal' | 'low';
type IconType = 'video' | 'quiz' | 'review' | 'course' | 'chart' | 'plan' | 'exam';

interface Action {
  type: ActionType;
  url: string;
  label: string;
}

interface ActionCard {
  title: string;
  description: string;
  priority: Priority;
  icon: IconType;
  action: Action;
}

interface ActionCardsPayload {
  title?: string;
  cards: ActionCard[];
}

// --- Icon & color mapping ---

const ICON_MAP: Record<IconType, React.FC<{ className?: string }>> = {
  video: PlayCircle,
  quiz: PenLine,
  review: RotateCcw,
  course: BookOpen,
  chart: TrendingUp,
  plan: Calendar,
  exam: FileText,
};

const COLOR_MAP: Record<IconType, { border: string; bg: string; text: string; icon: string }> = {
  video:  { border: 'border-l-blue-500',   bg: 'bg-blue-50',   text: 'text-blue-700',   icon: 'text-blue-500' },
  quiz:   { border: 'border-l-emerald-500', bg: 'bg-emerald-50', text: 'text-emerald-700', icon: 'text-emerald-500' },
  review: { border: 'border-l-amber-500',   bg: 'bg-amber-50',  text: 'text-amber-700',  icon: 'text-amber-500' },
  course: { border: 'border-l-indigo-500',  bg: 'bg-indigo-50', text: 'text-indigo-700', icon: 'text-indigo-500' },
  chart:  { border: 'border-l-emerald-500', bg: 'bg-emerald-50', text: 'text-emerald-700', icon: 'text-emerald-500' },
  plan:   { border: 'border-l-violet-500',  bg: 'bg-violet-50', text: 'text-violet-700', icon: 'text-violet-500' },
  exam:   { border: 'border-l-rose-500',    bg: 'bg-rose-50',   text: 'text-rose-700',   icon: 'text-rose-500' },
};

// --- Navigation hook ---

const useSafeNavigate = () => {
  const navigate = useNavigate();
  return useCallback((url: string) => {
    if (!url) return;
    if (url.startsWith('/')) navigate(url);
    else if (url.startsWith('http')) window.open(url, '_blank', 'noopener,noreferrer');
  }, [navigate]);
};

// --- Single card ---

const ActionCardItem: React.FC<{ card: ActionCard }> = ({ card }) => {
  const safeNavigate = useSafeNavigate();
  const colors = COLOR_MAP[card.icon] || COLOR_MAP.chart;
  const Icon = ICON_MAP[card.icon] || TrendingUp;

  return (
    <button
      onClick={() => safeNavigate(card.action.url)}
      className={cn(
        'w-full text-left rounded-lg border-l-4 p-4 transition-all duration-200',
        'hover:translate-y-[-2px] hover:shadow-md active:translate-y-0',
        'cursor-pointer group',
        colors.border, colors.bg,
      )}
    >
      <div className="flex items-start gap-3">
        <Icon className={cn('h-5 w-5 mt-0.5 shrink-0', colors.icon)} />
        <div className="flex-1 min-w-0">
          <h4 className={cn('text-sm font-semibold', colors.text)}>{card.title}</h4>
          <p className="text-xs text-muted-foreground mt-1 leading-relaxed">{card.description}</p>
          <div className={cn('flex items-center gap-1 mt-2 text-xs font-medium', colors.text)}>
            {card.action.label}
            <ArrowRight className="h-3 w-3 transition-transform group-hover:translate-x-0.5" />
          </div>
        </div>
      </div>
    </button>
  );
};

// --- Main renderer ---

export const ActionCardsRenderer: React.FC<{ payload: ActionCardsPayload }> = ({ payload }) => {
  if (!Array.isArray(payload.cards) || payload.cards.length === 0) return null;

  // Sort: high first, then normal, then low
  const priorityOrder: Record<Priority, number> = { high: 0, normal: 1, low: 2 };
  const sorted = [...payload.cards].sort((a, b) => priorityOrder[a.priority] - priorityOrder[b.priority]);

  return (
    <div className="p-4 space-y-3 animate-in fade-in duration-300">
      {payload.title && <h3 className="text-sm font-semibold">{payload.title}</h3>}
      <div className="grid grid-cols-2 gap-3">
        {sorted.map((card, i) => (
          <div key={i} className={card.priority === 'high' ? 'col-span-2' : 'col-span-1'}>
            <ActionCardItem card={card} />
          </div>
        ))}
      </div>
    </div>
  );
};
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit --pretty 2>&1 | head -30`
Expected: No errors related to ActionCardsRenderer

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/xiaoyu/visuals/ActionCardsRenderer.tsx
git commit -m "feat: add ActionCardsRenderer with masonry grid layout"
```

---

### Task 2: Register action_cards type

**Files:**
- Modify: `frontend/src/pages/xiaoyu/visuals/index.ts`

- [ ] **Step 1: Add import and register**

Add to imports (line 5):
```tsx
import { ActionCardsRenderer } from './ActionCardsRenderer';
```

Add to RENDERERS map (after line 16):
```tsx
  action_cards: ActionCardsRenderer,
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit --pretty 2>&1 | head -30`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/xiaoyu/visuals/index.ts
git commit -m "feat: register action_cards visual type"
```

---

### Task 3: Backend — accept action_cards type

**Files:**
- Modify: `backend/ai_assistant/services/tool_executor.py:728`

- [ ] **Step 1: Add 'action_cards' to valid_types**

At line 728, change:
```python
        valid_types = {'data_card', 'latex_derivation', 'step_solution', 'knowledge_map'}
```
to:
```python
        valid_types = {'data_card', 'latex_derivation', 'step_solution', 'knowledge_map', 'action_cards'}
```

- [ ] **Step 2: Verify backend check passes**

Run: `cd backend && python manage.py check`
Expected: System check identified no issues

- [ ] **Step 3: Commit**

```bash
git add backend/ai_assistant/services/tool_executor.py
git commit -m "feat: accept action_cards type in render_visual handler"
```

---

### Task 4: Update prompt — guide AI on action cards

**Files:**
- Modify: `backend/prompts/ai_assistant/bots/xiaoyu/tool_guide.txt`

- [ ] **Step 1: Add action_cards section to tool_guide.txt**

Append after the `knowledge_map` section (after line 81), before the "必须渲染的场景" section:

```
**action_cards** — 行动引导卡片（AI 决策布局）
适用场景：用户询问"今天学什么""有什么建议""薄弱点分析""学习建议"等需要引导下一步行动时。
数据组合流程：
1. 调用 get_user_weak_points 获取薄弱知识点（按错误次数排序）
2. 对 Top 3 薄弱点调用 search_asr 搜索匹配的视频课程片段
3. 调用 get_due_reviews 获取到期复习任务数量
4. 可选：调用 search_courses 推荐相关课程
优先级规则：mastery_score < 0.5 或错误率 > 50% → high；50%-70% → normal；辅助信息 → low
每张卡片必须有可跳转的 action。视频类 url 格式：/courses/{id}?t={seconds}
```json
{"type": "action_cards", "payload": {
  "title": "今日学习建议",
  "cards": [
    {
      "title": "函数单调性薄弱",
      "description": "正确率 45%，建议先看视频巩固导数应用",
      "priority": "high",
      "icon": "video",
      "action": {"type": "video", "url": "/courses/3?t=120", "label": "观看视频"}
    },
    {
      "title": "12 道复习题待完成",
      "description": "间隔重复到期，今日不复习记忆衰减约 30%",
      "priority": "normal",
      "icon": "review",
      "action": {"type": "review", "url": "/review", "label": "开始复习"}
    }
  ]
}}
```
```

- [ ] **Step 2: Update "必须渲染的场景" section**

Add a new bullet to the "必须渲染的场景" list (after line 87):
```
- **行动建议**：用户询问学习建议、今日任务、下一步该做什么 → `action_cards`
```

- [ ] **Step 3: Commit**

```bash
git add backend/prompts/ai_assistant/bots/xiaoyu/tool_guide.txt
git commit -m "feat: add action_cards prompt guide for XiaoYu"
```

---

### Task 5: Seed bot and verify end-to-end

- [ ] **Step 1: Re-seed XiaoYu bot to sync updated prompts**

Run: `cd backend && python manage.py seed_xiaoyu`
Expected: Bot '小宇' updated successfully

- [ ] **Step 2: Run backend check**

Run: `make backend-check`
Expected: All checks pass

- [ ] **Step 3: Run frontend check**

Run: `make frontend-check`
Expected: TypeScript compiles, Vite build succeeds

- [ ] **Step 4: Commit any fixes if needed**

```bash
git add -A
git commit -m "fix: address check failures for action_cards"
```
