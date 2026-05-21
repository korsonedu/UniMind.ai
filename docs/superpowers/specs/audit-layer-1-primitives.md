# Audit: Layer 1 — UI Primitives

**Date:** 2026-05-20
**Scope:** 20 shadcn/ui-inspired primitives under `frontend/src/components/ui/`
**Standard:** Web Interface Guidelines (accessibility, focus, forms, animation, typography, content, images, performance, navigation, touch, safe areas, dark mode, locale, hydration, hover, copy, anti-patterns)

---

## /Users/eular/Desktop/官网0215/frontend/src/components/ui/alert-dialog.tsx

| Line | Rule | Finding |
|------|------|---------|
| 38 | Animation — prefers-reduced-motion | `duration-200` + animate-in/out classes with no `@media (prefers-reduced-motion: reduce)` override. Dialog will still animate for users who request reduced motion. |
| 19-26 | Touch — overscroll-behavior | Overlay and content do not set `overscroll-behavior: contain`. Scrolling behind the modal is possible on touch devices. |
| — | Touch — tap-highlight-color | No `-webkit-tap-highlight-color` set on interactive elements. |

---

## /Users/eular/Desktop/官网0215/frontend/src/components/ui/avatar.tsx

| Line | Rule | Finding |
|------|------|---------|
| 24-29 | Images — explicit width/height | `AvatarImage` renders `<img>` with `aspect-square` in className but no `width` / `height` attributes. Causes CLS during image load when container size is not yet established. |

---

## /Users/eular/Desktop/官网0215/frontend/src/components/ui/badge.tsx

| Line | Rule | Finding |
|------|------|---------|
| 7 | Focus — use `:focus-visible` | Uses `focus:outline-none focus:ring-2` instead of `focus-visible:`. Focus ring appears on click, not just keyboard focus. |

---

## /Users/eular/Desktop/官网0215/frontend/src/components/ui/button.tsx

| Line | Rule | Finding |
|------|------|---------|
| 8 | Touch — tap-highlight-color | No `-webkit-tap-highlight-color` set. Mobile Safari will show grey tap flash. |
| 8 | Touch — touch-action | No `touch-action: manipulation`. Double-tap zoom delay not suppressed. |

Note: `icon` size variant (line 32, `h-9 w-9`) correctly relies on consumer to provide `aria-label` — no violation in the primitive itself.

---

## /Users/eular/Desktop/官网0215/frontend/src/components/ui/card.tsx

| Line | Rule | Finding |
|------|------|---------|
| — | — | ✓ pass — presentational only, no interactive elements, no animations, no images. |

---

## /Users/eular/Desktop/官网0215/frontend/src/components/ui/checkbox.tsx

| Line | Rule | Finding |
|------|------|---------|
| 23 | Accessibility — aria-hidden on decorative icon | `<Check>` icon renders inside the button but has no `aria-hidden="true"`. State is already communicated via `aria-checked`, so the icon is decorative. |
| 10 | Touch — tap-highlight-color | No `-webkit-tap-highlight-color` set. |
| 10 | Touch — touch-action | No `touch-action: manipulation`. |

---

## /Users/eular/Desktop/官网0215/frontend/src/components/ui/dialog.tsx

| Line | Rule | Finding |
|------|------|---------|
| 48 | Accessibility — aria-hidden on decorative icon | Close button `<X>` icon missing `aria-hidden="true"`. `sr-only` text already provides accessible name. |
| 47 | Focus — use `:focus-visible` | Close button uses `focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2` — ring appears on click. Change to `focus-visible:` prefix. |
| 41 | Animation — prefers-reduced-motion | `duration-200` + animate-in/out with no reduced-motion fallback. |
| 41 | Touch — overscroll-behavior | Dialog content does not set `overscroll-behavior: contain`. Background scroll possible on touch devices. |

---

## /Users/eular/Desktop/官网0215/frontend/src/components/ui/dropdown-menu.tsx

| Line | Rule | Finding |
|------|------|---------|
| 37 | Accessibility — aria-hidden on decorative icon | `<ChevronRight>` icon in SubTrigger missing `aria-hidden="true"`. |
| 110 | Accessibility — aria-hidden on decorative icon | `<Check>` icon in CheckboxItem indicator missing `aria-hidden="true"`. |
| 133 | Accessibility — aria-hidden on decorative icon | `<Circle>` icon in RadioItem indicator missing `aria-hidden="true"`. |
| 50 | Animation — prefers-reduced-motion | Animations via data-state classes with no reduced-motion fallback. |

---

## /Users/eular/Desktop/官网0215/frontend/src/components/ui/hover-card.tsx

| Line | Rule | Finding |
|------|------|---------|
| 19 | Focus — outline-none without replacement | `outline-none` used with no `focus-visible:ring-*` fallback. If content becomes focusable, focus will be invisible. |
| 19 | Animation — prefers-reduced-motion | Animations via data-state classes with no reduced-motion fallback. |

---

## /Users/eular/Desktop/官网0215/frontend/src/components/ui/input.tsx

| Line | Rule | Finding |
|------|------|---------|
| 11 | Touch — tap-highlight-color | No `-webkit-tap-highlight-color` set. |
| 11 | Touch — touch-action | No `touch-action: manipulation`. |

---

## /Users/eular/Desktop/官网0215/frontend/src/components/ui/label.tsx

| Line | Rule | Finding |
|------|------|---------|
| — | — | ✓ pass — thin wrapper around Radix label, no interactive/animated surface area. |

---

## /Users/eular/Desktop/官网0215/frontend/src/components/ui/popover.tsx

| Line | Rule | Finding |
|------|------|---------|
| 24 | Focus — outline-none without replacement | `outline-none` used with no `focus-visible:ring-*` fallback. |
| 24 | Animation — prefers-reduced-motion | Animations with no reduced-motion fallback. |
| 24 | Animation — transform-origin | Zoom animation (`zoom-in-95` / `zoom-out-95`) present but no explicit `transform-origin` set (contrast with hover-card.tsx line 19 which uses `origin-[--radix-hover-card-content-transform-origin]`). |

---

## /Users/eular/Desktop/官网0215/frontend/src/components/ui/scroll-area.tsx

| Line | Rule | Finding |
|------|------|---------|
| — | — | ✓ pass — no interactive elements, no animations beyond native scrollbar. |

---

## /Users/eular/Desktop/官网0215/frontend/src/components/ui/select.tsx

| Line | Rule | Finding |
|------|------|---------|
| 27 | Accessibility — aria-hidden on decorative icon | `<ChevronDown>` in SelectTrigger missing `aria-hidden="true"`. |
| 45 | Accessibility — aria-hidden on decorative icon | `<ChevronUp>` in ScrollUpButton missing `aria-hidden="true"`. |
| 62 | Accessibility — aria-hidden on decorative icon | `<ChevronDown>` in ScrollDownButton missing `aria-hidden="true"`. |
| 126 | Accessibility — aria-hidden on decorative icon | `<Check>` in ItemIndicator missing `aria-hidden="true"`. |
| 20 | Focus — use `:focus-visible` | SelectTrigger uses `focus:outline-none focus:ring-1 focus:ring-ring` — focus ring appears on click. |
| 76 | Animation — prefers-reduced-motion | Animations with no reduced-motion fallback. |

---

## /Users/eular/Desktop/官网0215/frontend/src/components/ui/separator.tsx

| Line | Rule | Finding |
|------|------|---------|
| — | — | ✓ pass — decorative-only element, `decorative={true}` by default, no interactive surface. |

---

## /Users/eular/Desktop/官网0215/frontend/src/components/ui/sheet.tsx

| Line | Rule | Finding |
|------|------|---------|
| 68 | Accessibility — aria-hidden on decorative icon | Close button `<X>` icon missing `aria-hidden="true"`. `sr-only` text already provides accessible name. |
| 67 | Focus — use `:focus-visible` | Close button uses `focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2` — ring on click. |
| 34 | Animation — prefers-reduced-motion | `duration-300` / `duration-500` + slide animations with no reduced-motion fallback. |
| 63 | Touch — overscroll-behavior | Sheet content does not set `overscroll-behavior: contain`. Background scroll possible on touch devices. |

---

## /Users/eular/Desktop/官网0215/frontend/src/components/ui/slider.tsx

| Line | Rule | Finding |
|------|------|---------|
| — | — | ✓ pass — correct `focus-visible:` usage, no decorative icon issues, no animations beyond native. |

---

## /Users/eular/Desktop/官网0215/frontend/src/components/ui/switch.tsx

| Line | Rule | Finding |
|------|------|---------|
| — | — | ✓ pass — correct `focus-visible:` usage, proper thumb transform, no decorative icons. |

---

## /Users/eular/Desktop/官网0215/frontend/src/components/ui/tabs.tsx

| Line | Rule | Finding |
|------|------|---------|
| — | — | ✓ pass — correct `focus-visible:` on both TabsTrigger and TabsContent, no animations beyond transitions. |

---

## /Users/eular/Desktop/官网0215/frontend/src/components/ui/tooltip.tsx

| Line | Rule | Finding |
|------|------|---------|
| 22 | Animation — prefers-reduced-motion | `animate-in fade-in-0 zoom-in-95` with no reduced-motion fallback. |

---

## Summary

| Category | Violations |
|----------|------------|
| **Accessibility — aria-hidden** | 11 icons missing `aria-hidden="true"` across checkbox, dialog, dropdown-menu, select, sheet |
| **Animation — prefers-reduced-motion** | 8 files animate without respecting reduced motion (alert-dialog, dialog, dropdown-menu, hover-card, popover, select, sheet, tooltip) |
| **Focus — `:focus` vs `:focus-visible`** | 4 files use `focus:` ring (badge, dialog close, sheet close, select trigger) |
| **Focus — outline-none w/o replacement** | 2 files (hover-card, popover) |
| **Touch — tap-highlight-color** | 3 interactive files missing (button, checkbox, input) |
| **Touch — touch-action: manipulation** | 3 files missing (button, checkbox, input) |
| **Touch — overscroll-behavior: contain** | 3 modal-type files missing (alert-dialog, dialog, sheet) |
| **Images — explicit width/height** | 1 file (avatar) |
| **Clean (✓ pass)** | card, label, scroll-area, separator, slider, switch, tabs |

**Total unique issues across 20 files: 10 categories, affecting 17 of 20 files.**
