# Frontend Audit & Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Audit ~100 frontend files against Web Interface Guidelines, then de-shadcn the UI, remove over-decoration, slim copy, and fix all issues.

**Architecture:** 5-phase sequential pipeline. Phase 1 spawns 3 parallel audit agents. Phase 2 replaces the shadcn template look by introducing UniMind design tokens and redesigning 8 core UI primitives. Phase 3 strips decorative clutter. Phase 4 rewrites AI-tainted copy. Phase 5 fixes all audit findings. Landing/Intro pages are protected from copy changes.

**Tech Stack:** Tailwind CSS 4, shadcn/ui (Radix primitives), React 19, TypeScript, class-variance-authority, lucide-react

---

### Task 1: Phase 1 — Parallel Audit (3 layers)

**Description:** Dispatch 3 Explore subagents concurrently to audit all frontend files against Web Interface Guidelines. Each agent gets a specific file list and the full guidelines. Output: `file:line` format findings per layer.

#### Task 1a: Audit UI Primitives (20 files)

**Files:** `frontend/src/components/ui/{alert-dialog,avatar,badge,button,card,checkbox,dialog,dropdown-menu,hover-card,input,label,popover,scroll-area,select,separator,sheet,slider,switch,tabs,tooltip}.tsx`

- [ ] **Step 1: Read every UI primitive file**

Read all 20 files in `components/ui/` to understand current implementation.

- [ ] **Step 2: Audit against all guideline categories**

Check every rule from the Web Interface Guidelines against each file:
- Focus states: `focus-visible:ring-*` present on all interactives? No bare `outline-none`?
- Animation: `transition: all` → list properties? `prefers-reduced-motion` honored?
- Forms: inputs have `autocomplete`/`name`? Correct `type`/`inputmode`?
- Accessibility: Icon buttons have `aria-label`? Semantic HTML before ARIA?
- Content handling: truncation with `min-w-0`? Empty state handling?
- Touch: `touch-action: manipulation` on interactive elements?
- Hydration: `value` + `onChange` paired?

- [ ] **Step 3: Output findings**

Output in `file:line` format, grouped by file. Use `✓ pass` for clean files.

Expected output saved to `docs/superpowers/specs/audit-layer-1-primitives.md`

#### Task 1b: Audit Shared Components (~18 files)

**Files:** `frontend/src/components/{ConfirmDialog,EmptyState,ErrorBoundary,FeatureGuard,InlineError,LanguageSwitcher,Loading,MarkdownEditor,NotificationBell,OnboardingDialog,PageWrapper,PersistentUploadToast,PointsConfirmDialog,UpgradeModal,WeeklyReportDialog,DirectionSelector,EloPopover}.tsx` + `components/course/{OutlinePanel,SubtitlesOverlay}.tsx` + `components/interviews/{InterviewLobby,RadarChart,ResumeTuner,SessionChat,SessionList}.tsx`

- [ ] **Step 1: Read all shared component files**
- [ ] **Step 2: Audit against guidelines (same categories as 1a)**
- [ ] **Step 3: Output findings to `docs/superpowers/specs/audit-layer-2-components.md`**

#### Task 1c: Audit Pages & Sub-pages (~45 files)

**Files:** All `frontend/src/pages/*.tsx` + `pages/*/**.tsx` + `layouts/MainLayout.tsx`

- [ ] **Step 1: Read all page files**
- [ ] **Step 2: Audit against guidelines plus page-specific checks:**
  - Performance: Lists >50 items virtualized? Layout reads in render?
  - Navigation: URL state sync for filters/tabs/pagination? Links use `<a>`/`<Link>`?
  - Content: Long text handling? Empty states for all data-dependent views?
  - Copy: Active voice? Title Case headings? Numerals? Specific button labels?
  - Dark mode: `color-scheme: dark`? `<meta name="theme-color">`?

- [ ] **Step 3: Output findings to `docs/superpowers/specs/audit-layer-3-pages.md`**
- [ ] **Step 4: Commit audit reports**

```bash
git add docs/superpowers/specs/audit-layer-*.md
git commit -m "docs: add frontend audit reports for all 3 layers"
```

---

### Task 2: Phase 2 — Design Tokens & CSS Foundation

**Goal:** Replace the standard shadcn HSL theme with UniMind-branded tokens that bridge the Apple design direction seen in Landing.tsx.

#### Task 2a: Extend CSS Variables

**Files:**
- Modify: `frontend/src/index.css` (the `:root` and `.dark` blocks)
- Create: (inline in index.css) new semantic token layer

- [ ] **Step 1: Add UniMind brand tokens to index.css `:root` block**

Add after existing shadcn variables, before the `*` reset:

```css
:root {
  /* Existing shadcn tokens remain... */

  /* ── UniMind Brand Tokens ── */
  --unimind-blue: 211 100% 45%;        /* #0071E3 */
  --unimind-blue-foreground: 0 0% 100%;
  --unimind-red: 3 100% 59%;            /* #FF3B30 */
  --unimind-green: 142 100% 42%;        /* #34C759 */
  --unimind-text: 240 2% 11%;           /* #1D1D1F */
  --unimind-text-secondary: 240 2% 45%; /* #6E6E73 */
  --unimind-text-tertiary: 240 2% 58%;  /* #8E8E93 */
  --unimind-text-quaternary: 240 2% 68%; /* #AEAEB2 */
  --unimind-border: 240 4% 90%;         /* #E5E5EA */
  --unimind-bg-secondary: 240 7% 97%;   /* #F5F5F7 */

  /* Map primary to UniMind blue */
  --primary: var(--unimind-blue);
  --primary-foreground: var(--unimind-blue-foreground);
}

.dark {
  /* Existing dark tokens remain... */

  --unimind-blue: 211 100% 55%;
  --unimind-text: 0 0% 98%;
  --unimind-text-secondary: 240 5% 65%;
  --unimind-text-tertiary: 240 5% 55%;
  --unimind-border: 240 4% 20%;
  --unimind-bg-secondary: 240 4% 12%;
}
```

- [ ] **Step 2: Replace hardcoded hex in index.css dark mode overrides**

Replace all `[#1D1D1F]` → use `--unimind-text`, `[#F5F5F7]` → use `--unimind-bg-secondary`, etc. Remove the massive block of hardcoded color overrides (lines 59-137) and replace with semantic rules pointing to the new tokens.

- [ ] **Step 3: Remove `--primary-override` hack**

Delete `--primary-override` variable and all selectors using it (`.bg-primary`, `.border-primary`, `.ring-black` overrides). The new `--primary` mapping handles this properly.

- [ ] **Step 4: Remove Vite boilerplate from App.css**

Delete unused `.logo`/`.card`/`.read-the-docs` rules and the `#root` centering layout that conflicts with the app's actual layout.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/index.css frontend/src/App.css
git commit -m "refactor: add UniMind brand tokens, clean dark mode overrides, remove Vite boilerplate"
```

#### Task 2b: Replace Hardcoded Colors in All Components

**Files:** All files using hardcoded hex values — priority List:
1. `frontend/src/pages/Landing.tsx` — most hardcoded colors
2. `frontend/src/components/OnboardingDialog.tsx`
3. All other files from Phase 1 audit that use `#` colors directly

- [ ] **Step 1: grep for all hardcoded hex colors**

```bash
grep -rn '#[0-9A-Fa-f]\{6\}\|#[0-9A-Fa-f]\{3\}' frontend/src --include='*.tsx' --include='*.ts' | grep -v node_modules | grep -v dist | grep -v '//\|/\*'
```

- [ ] **Step 2: Replace Landing.tsx hardcoded colors with Tailwind semantic classes**

Map:
- `#0071E3` / `#0071E3`-based → `text-primary`, `bg-primary`, `border-primary`
- `#1D1D1F` → `text-foreground`
- `#6E6E73` → `text-muted-foreground`
- `#8E8E93` → keep as `text-unimind-text-tertiary` (Tailwind custom)
- `#AEAEB2` → `text-unimind-text-quaternary`
- `#E5E5EA` → `border-border`
- `#F5F5F7` → `bg-unimind-bg-secondary`
- `#FF3B30` → `text-destructive`
- `#34C759` → `text-unimind-green`

- [ ] **Step 3: Register custom tokens in tailwind.config.js**

Add to `theme.extend.colors`:
```js
unimind: {
  blue: 'hsl(var(--unimind-blue))',
  red: 'hsl(var(--unimind-red))',
  green: 'hsl(var(--unimind-green))',
  text: 'hsl(var(--unimind-text))',
  'text-secondary': 'hsl(var(--unimind-text-secondary))',
  'text-tertiary': 'hsl(var(--unimind-text-tertiary))',
  'text-quaternary': 'hsl(var(--unimind-text-quaternary))',
  border: 'hsl(var(--unimind-border))',
  'bg-secondary': 'hsl(var(--unimind-bg-secondary))',
}
```

- [ ] **Step 4: Replace hex in OnboardingDialog and other components**

Same mapping strategy. Each file gets its hardcoded hex replaced with semantic Tailwind classes.

- [ ] **Step 5: Verify dark mode still works**

Check that the new token-based approach handles dark mode through CSS variables without `!important` hacks.

- [ ] **Step 6: Commit**

```bash
git add frontend/tailwind.config.js frontend/src/pages/Landing.tsx frontend/src/components/OnboardingDialog.tsx
git commit -m "refactor: replace hardcoded hex colors with UniMind design tokens"
```

---

### Task 3: Phase 2 — Redesign Core UI Primitives

**Goal:** Break the shadcn template look. 8 components get redesign treatment.

**Approach:** Use `frontend-design` skill to redesign each primitive with the UniMind brand language — clean, functional, minimal Apple-inspired aesthetic but NOT shadcn-generic. No rounded-full everywhere, no bg-gradient-to-r for decoration, no shadow-sm + border-border combo.

#### Task 3a: Redesign Button

**File:** `frontend/src/components/ui/button.tsx`

- [ ] **Step 1: Current state analysis**

Current issues:
- `rounded-xl` + `shadow-sm` + `font-semibold` = shadcn template signature
- `apple` variant uses `bg-gradient-to-r from-blue-500 to-indigo-600` — over-decoration
- `pill: "rounded-full"` — combined with gradient = AI stereotype

- [ ] **Step 2: Redesign**

```tsx
const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-40 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default:
          "bg-foreground text-background hover:bg-foreground/90 rounded-lg",
        destructive:
          "bg-destructive text-destructive-foreground hover:bg-destructive/90 rounded-lg",
        outline:
          "border border-border bg-transparent hover:bg-accent rounded-lg",
        secondary:
          "bg-secondary text-secondary-foreground hover:bg-secondary/70 rounded-lg",
        ghost: "hover:bg-accent rounded-lg",
        link: "text-primary underline-offset-4 hover:underline p-0 h-auto",
        apple:
          "bg-primary text-primary-foreground hover:bg-primary/90 rounded-lg font-semibold",
        "apple-outline":
          "border border-primary text-primary bg-transparent hover:bg-primary/5 rounded-lg font-medium",
      },
      size: {
        default: "h-9 px-4 py-2",
        sm: "h-8 px-3 text-xs rounded-md",
        lg: "h-11 px-6 text-sm rounded-lg",
        icon: "h-9 w-9 rounded-lg",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)
```

Key changes:
- Drop `shadow-sm` from base — shadows are decorative
- Drop `pill: "rounded-full"` variant — unnecessary
- Drop `rounded-xl` → `rounded-lg` — less "friendly AI" look
- Grouped focus ring into base (each variant doesn't need its own)
- Apple variant: flat color, no gradient → single solid brand blue
- `disabled:opacity-50` → `40` — less faded

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ui/button.tsx
git commit -m "refactor: redesign button — drop gradients, shadows, rounded-xl for cleaner look"
```

#### Task 3b: Redesign Card

**File:** `frontend/src/components/ui/card.tsx`

Current issues: `rounded-xl border bg-card shadow` = shadcn template. `apple` variant adds `shadow-lg shadow-blue-100/50`.

- [ ] **Step 1: Redesign**

```tsx
const cardVariants = cva(
  "rounded-lg border bg-card text-card-foreground",
  {
    variants: {
      variant: {
        default: "",
        elevated: "shadow-sm",
        apple: "border-primary/20",
        ghost: "border-transparent bg-transparent",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)
```

Key changes:
- Drop default `shadow` — shadow is opt-in via `elevated` variant
- `rounded-xl` → `rounded-lg`
- `apple` variant: subtle border tint only, no shadow
- Add `ghost` variant for borderless cards

- [ ] **Step 2: Commit**

#### Task 3c: Redesign Input

**File:** `frontend/src/components/ui/input.tsx`

Current issues: `rounded-md` is fine but `shadow-sm` + `focus-visible:ring-1` are weak.

- [ ] **Step 1: Redesign**

```tsx
<input
  type={type}
  className={cn(
    "flex h-10 w-full rounded-lg border bg-transparent px-3 py-2 text-sm file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-50",
    className
  )}
  ref={ref}
  {...props}
/>
```

Key changes:
- `h-9` → `h-10` — larger hit target
- `rounded-md` → `rounded-lg` — consistent with buttons
- `ring-1` → `ring-2` — visible focus ring
- `shadow-sm` removed
- `focus-visible:ring-offset-1` added for breathing room

- [ ] **Step 2: Commit**

#### Task 3d: Redesign Dialog

**File:** `frontend/src/components/ui/dialog.tsx`

Current issues: `sm:rounded-[2.5rem]` is unnecessarily extreme. `backdrop-blur-sm` on overlay = decorative blur. Close button has `hover:bg-slate-100` — hardcoded color.

- [ ] **Step 1: Redesign DialogOverlay and DialogContent**

```tsx
// Overlay — drop backdrop-blur
className={cn(
  "fixed inset-0 z-50 bg-black/50 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
  className
)}

// Content — reasonable border-radius
className={cn(
  "fixed left-[50%] top-[50%] z-50 grid w-full max-w-lg translate-x-[-50%] translate-y-[-50%] gap-4 border bg-background p-6 shadow-lg duration-200 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 data-[state=closed]:slide-out-to-left-1/2 data-[state=closed]:slide-out-to-top-[48%] data-[state=open]:slide-in-from-left-1/2 data-[state=open]:slide-in-from-top-[48%] sm:rounded-xl",
  className
)}
// Close button — use semantic color
<DialogPrimitive.Close className="absolute right-4 top-4 rounded-lg p-1.5 opacity-70 ring-offset-background transition-opacity hover:opacity-100 hover:bg-accent focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:pointer-events-none">
  <X className="h-4 w-4" />
  <span className="sr-only">Close</span>
</DialogPrimitive.Close>
```

- [ ] **Step 2: Commit**

#### Task 3e: Redesign Badge

**File:** `frontend/src/components/ui/badge.tsx`

- [ ] **Step 1: Check and fix if needed**

Read the current badge, check for:
- `rounded-full` in default variant → change to `rounded-md`
- Extraneous variants that add decoration → strip

#### Task 3f: Redesign Tabs

**File:** `frontend/src/components/ui/tabs.tsx`

- [ ] **Step 1: Redesign trigger for less AI feel**

```tsx
// tabs-trigger — underline style instead of pill
className={cn(
  "inline-flex items-center justify-center whitespace-nowrap px-3 py-2 text-sm font-medium ring-offset-background transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 data-[state=active]:text-foreground data-[state=active]:border-b-2 data-[state=active]:border-foreground text-muted-foreground hover:text-foreground/80",
  className
)}
```

Key change: Active tab gets an underline border instead of a background pill.

- [ ] **Step 2: Commit**

#### Task 3g: Redesign Select, DropdownMenu

**Files:** `frontend/src/components/ui/select.tsx`, `frontend/src/components/ui/dropdown-menu.tsx`

- [ ] **Step 1: Select trigger — less generic**

Add more defined border, proper focus ring:
```tsx
className={cn(
  "flex h-10 w-full items-center justify-between rounded-lg border bg-transparent px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-50 [&>span]:line-clamp-1",
  className
)}
```

- [ ] **Step 2: Dropdown — check animation and content**

Ensure dropdown-content doesn't use shadow-2xl decoration. Use a clean, subtle shadow.

- [ ] **Step 3: Commit all remaining UI primitive changes**

```bash
git add frontend/src/components/ui/
git commit -m "refactor: redesign core UI primitives — remove shadcn template aesthetics"
```

---

### Task 4: Phase 3 — Remove Over-decoration

**Goal:** Strip decorative elements that add no functional value.

- [ ] **Step 1: Scan for decorative gradients**

```bash
grep -rn 'bg-gradient-to-r\|bg-gradient-to-b\|bg-gradient-to-l\|bg-gradient-to-t' frontend/src --include='*.tsx' | grep -v node_modules
```

Remove gradients from non-brand contexts (buttons, decorative headings, card backgrounds). Keep ONLY if it serves a clear functional purpose (e.g., progress bar fill).

- [ ] **Step 2: Scan for excessive shadows**

```bash
grep -rn 'shadow-2xl\|shadow-xl\|shadow-lg' frontend/src --include='*.tsx' | grep -v node_modules
```

Reduce: `shadow-2xl` → `shadow-lg`, `shadow-xl` → `shadow`, `shadow-lg` → `shadow-sm`. Remove colored shadows (`shadow-blue-*`, `shadow-red-*`).

- [ ] **Step 3: Scan for decorative blur**

```bash
grep -rn 'backdrop-blur' frontend/src --include='*.tsx' | grep -v node_modules
```

Remove from non-navigation contexts. Keep only for nav glass effect and modals if needed.

- [ ] **Step 4: Scan for emoji in JSX**

```bash
grep -rn '✨\|🔥\|🚀\|💡\|🎯\|⭐\|🏆\|💪\|👆\|✅\|❌\|🎉\|💥\|🧠' frontend/src --include='*.tsx' | grep -v node_modules
```

Remove decorative emoji from UI. Exception: onboarding/tutorial content where emotional tone is appropriate.

- [ ] **Step 5: Dial down color density**

Cards should not be colorful just for variety. Each colored element must justify its color semantically (destructive=red, success=green, brand=blue, neutral=gray).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/
git commit -m "refactor: remove over-decoration — gradients, excessive shadows, emoji, color density"
```

---

### Task 5: Phase 4 — Copy Slimming

**Goal:** Replace AI-tainted microcopy with specific, actionable language. Exclude Landing/Intro pages.

- [ ] **Step 1: Scan for generic verbs**

```bash
grep -rn '开始\|智能\|一键\|高效\|全新\|强大\|卓越\|极致' frontend/src --include='*.tsx' | grep -v Landing | grep -v LandingZh | grep -v LandingEn | grep -v Intro
```

- [ ] **Step 2: Fix button labels**

Pattern: generic → specific
- "确认" → "保存配置" / "删除账号" / "添加到题库"
- "提交" → "生成题目" / "发送反馈"
- "开始" → "进入练习" / "创建机构"

- [ ] **Step 3: Fix error messages**

Pattern: problem-only → problem + solution
- "加载失败" → "加载失败，请检查网络后重试"
- "输入无效" → "请输入有效的邮箱地址，如 name@example.com"

- [ ] **Step 4: Fix headings and labels**

- Title Case for English headings
- Active voice
- Numerals: "8 道题目" not "八道题目"
- `…` not `...` in loading states

- [ ] **Step 5: Commit**

```bash
git add frontend/src/
git commit -m "refactor: slim AI-tainted copy — specific labels, actionable errors"
```

---

### Task 6: Phase 5 — Fix All Audit Findings

**Goal:** Fix every actionable issue from Phase 1 audit reports, organized by category.

#### Task 6a: Fix Accessibility Issues

- [ ] **Step 1: Add missing `aria-label` to all icon-only buttons**

```bash
grep -rn 'aria-label' frontend/src/components --include='*.tsx' | wc -l
```

For each icon-only button found in audit, add descriptive `aria-label`.

- [ ] **Step 2: Add missing `<label>` or `aria-label` to form inputs**

Ensure every `<Input>` without visible label has `aria-label`. Check all forms in: OnboardingDialog, Settings, Login, Register.

- [ ] **Step 3: Add keyboard handlers to interactive elements**

Any `<div onClick>` → `<button onClick>`. Any custom interactive element needs `onKeyDown`.

- [ ] **Step 4: Add `alt` to all images, `aria-hidden="true"` to decorative icons**

- [ ] **Step 5: Add `aria-live="polite"` to async update regions**

Toasts already have this via Sonner. Check: loading spinners, validation messages, search results counts.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/
git commit -m "fix(a11y): add aria-labels, keyboard handlers, alt text, live regions"
```

#### Task 6b: Fix Focus & Animation Issues

- [ ] **Step 1: Replace all `outline-none` without `focus-visible` replacement**

```bash
grep -rn 'outline-none' frontend/src/components --include='*.tsx'
```

Every `outline-none` must be paired with `focus-visible:ring-*` or `focus-visible:outline-*`.

- [ ] **Step 2: Replace `transition: all` with property list**

```bash
grep -rn 'transition-all' frontend/src --include='*.tsx'
```

Change to `transition-colors` or `transition-[transform,opacity]` as appropriate.

- [ ] **Step 3: Add `prefers-reduced-motion` checks**

In `tailwind.config.js`: already handled by `tailwindcss-animate`. Verify it works.

- [ ] **Step 4: Commit**

#### Task 6c: Fix Forms & Content Issues

- [ ] **Step 1: Add `autocomplete` attributes to all form inputs**

Email inputs: `autocomplete="email"`. Name inputs: `autocomplete="name"`. Password: `autocomplete="new-password"` or `current-password`.

- [ ] **Step 2: Add `spellCheck={false}` on emails, codes, usernames**
- [ ] **Step 3: Ensure labels are clickable (`htmlFor` on Label component)**
- [ ] **Step 4: Add `autocomplete="off"` on non-auth fields triggering password managers**
- [ ] **Step 5: Add text truncation to content containers**

Add `truncate` or `line-clamp-*` + `min-w-0` on flex children where needed.

- [ ] **Step 6: Handle empty states**

Check all `.map()` calls — ensure empty array doesn't render broken UI. Add `EmptyState` component where missing.

- [ ] **Step 7: Commit**

#### Task 6d: Fix Performance Issues

- [ ] **Step 1: Add virtualization to long lists**

Check for arrays rendered without virtualization. Likely candidates: QuestionBankPanel, KnowledgeSystemPanel, Leaderboard.

Add `react-window` or `@tanstack/react-virtual` for lists >50 items.

- [ ] **Step 2: Fix layout reads in render**

```bash
grep -rn 'getBoundingClientRect\|offsetHeight\|offsetWidth\|scrollTop' frontend/src --include='*.tsx'
```

Move layout reads to `useEffect` or `useLayoutEffect`.

- [ ] **Step 3: Add `<link rel="preconnect">` for external domains**

In `index.html`, add preconnect for API domain, CDN.

- [ ] **Step 4: Commit**

#### Task 6e: Fix Navigation, Touch, i18n Issues

- [ ] **Step 1: Fix URL state sync**

Filters, tabs, pagination that use `useState` should sync to URL search params. Use `nuqs` or manual `useSearchParams`.

- [ ] **Step 2: Replace inline `onClick` navigation with `<Link>`**

```bash
grep -rn 'onClick=.*navigate' frontend/src --include='*.tsx'
```

- [ ] **Step 3: Add confirmation modals to destructive actions**

Delete buttons, remove actions must confirm before executing.

- [ ] **Step 4: Add `touch-action: manipulation` to interactive elements**
- [ ] **Step 5: Add `overscroll-behavior: contain` to modals/sheets**
- [ ] **Step 6: Replace hardcoded date/number formats with `Intl.*`**
- [ ] **Step 7: Add `translate="no"` to brand names, code tokens**

- [ ] **Step 8: Commit**

#### Task 6f: Fix Hydration & Hover Issues

- [ ] **Step 1: Ensure all inputs with `value` have `onChange`**

```bash
grep -rn 'value=' frontend/src --include='*.tsx' | grep -v 'defaultValue\|onChange'
```

- [ ] **Step 2: Guard date/time rendering against hydration mismatch**

Use `useEffect` for client-only date formatting, or `suppressHydrationWarning` where appropriate.

- [ ] **Step 3: Add hover states to all buttons/links**
- [ ] **Step 4: Commit**

---

### Task 7: Final Verification

- [ ] **Step 1: Build check**

```bash
cd frontend && npm run build
```

Ensure no build errors from the token migration, component redesign, or fix changes.

- [ ] **Step 2: Visual review**

Launch dev server, check 5 key pages:
1. Landing — colors migrated to tokens, visual identical
2. TestSessionPage — redesigned primitives in use
3. KnowledgeMap — no over-decoration
4. InstitutionAdmin — forms/copy fixed
5. Settings — a11y/focus working

- [ ] **Step 3: Dark mode toggle**

Verify dark mode works across all pages with new token system.

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "chore: final verification pass — build check, visual review, dark mode"
```
