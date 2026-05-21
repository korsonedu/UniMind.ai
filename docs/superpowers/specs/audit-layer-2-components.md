# Layer 2 Audit: Shared Components (24 files)

Audited against the Web Interface Guidelines. Findings in `file:line` format.

---

## /Users/eular/Desktop/官网0215/frontend/src/components/ConfirmDialog.tsx
✓ pass

---

## /Users/eular/Desktop/官网0215/frontend/src/components/DirectionSelector.tsx
frontend/src/components/DirectionSelector.tsx:98 - Icon component decorative, missing `aria-hidden="true"`
frontend/src/components/DirectionSelector.tsx:136 - Check icon decorative, missing `aria-hidden="true"`
frontend/src/components/DirectionSelector.tsx:177 - Wrench icon decorative, missing `aria-hidden="true"`
frontend/src/components/DirectionSelector.tsx:119 - `transition-all` on button (anti-pattern: animate only transform/opacity)
frontend/src/components/DirectionSelector.tsx:130 - `transition-all` on checkbox indicator
frontend/src/components/DirectionSelector.tsx:164 - `transition-all` on custom option button

---

## /Users/eular/Desktop/官网0215/frontend/src/components/EloPopover.tsx
frontend/src/components/EloPopover.tsx:98 - Trigger button missing `aria-label` (icon-only with Sparkles + HelpCircle, no accessible text)
frontend/src/components/EloPopover.tsx:101 - `transition-all` on trigger button
frontend/src/components/EloPopover.tsx:106 - Sparkles icon decorative, missing `aria-hidden="true"`
frontend/src/components/EloPopover.tsx:108 - HelpCircle icon decorative, missing `aria-hidden="true"`
frontend/src/components/EloPopover.tsx:126 - Trophy icon decorative, missing `aria-hidden="true"`
frontend/src/components/EloPopover.tsx:136 - Coins icon decorative, missing `aria-hidden="true"`
frontend/src/components/EloPopover.tsx:151 - Sparkles icon decorative, missing `aria-hidden="true"`
frontend/src/components/EloPopover.tsx:168 - Building2 icon decorative, missing `aria-hidden="true"`
frontend/src/components/EloPopover.tsx:282 - HelpCircle icon decorative, missing `aria-hidden="true"`
frontend/src/components/EloPopover.tsx:306 - ArrowUpRight icon decorative, missing `aria-hidden="true"`
frontend/src/components/EloPopover.tsx:321 - History icon decorative, missing `aria-hidden="true"`
frontend/src/components/EloPopover.tsx:347 - ArrowUpRight/ArrowDownRight icons decorative, missing `aria-hidden="true"`
frontend/src/components/EloPopover.tsx:144 - Loading state has no `aria-live="polite"` for async content updates
frontend/src/components/EloPopover.tsx:180 - Loading spinner has no `aria-live="polite"` for async content updates
frontend/src/components/EloPopover.tsx:325 - Ledger loading spinner has no `aria-live="polite"`
frontend/src/components/EloPopover.tsx:194-224 - Ranking list has no virtualization (maps up to 15 items but pattern allows unbounded growth)

---

## /Users/eular/Desktop/官网0215/frontend/src/components/EmptyState.tsx
frontend/src/components/EmptyState.tsx:18 - Icon decorative, missing `aria-hidden="true"`

---

## /Users/eular/Desktop/官网0215/frontend/src/components/ErrorBoundary.tsx
frontend/src/components/ErrorBoundary.tsx:43 - AlertTriangle icon decorative, missing `aria-hidden="true"`
frontend/src/components/ErrorBoundary.tsx:56 - RefreshCw icon decorative, missing `aria-hidden="true"`

---

## /Users/eular/Desktop/官网0215/frontend/src/components/FeatureGuard.tsx
frontend/src/components/FeatureGuard.tsx:17 - Loader2 icon decorative, missing `aria-hidden="true"`

---

## /Users/eular/Desktop/官网0215/frontend/src/components/InlineError.tsx
frontend/src/components/InlineError.tsx:12 - AlertCircle icon decorative, missing `aria-hidden="true"`
frontend/src/components/InlineError.tsx:19 - RefreshCw icon decorative, missing `aria-hidden="true"`

---

## /Users/eular/Desktop/官网0215/frontend/src/components/LanguageSwitcher.tsx
frontend/src/components/LanguageSwitcher.tsx:27 - Globe icon decorative in compact variant, missing `aria-hidden="true"`
frontend/src/components/LanguageSwitcher.tsx:41 - Globe icon decorative in full variant, missing `aria-hidden="true"`

---

## /Users/eular/Desktop/官网0215/frontend/src/components/Loading.tsx
frontend/src/components/Loading.tsx:14 - Default message uses `...` (three dots) instead of typographic ellipsis `...`
frontend/src/components/Loading.tsx:27 - Loader2 icon decorative, missing `aria-hidden="true"`
frontend/src/components/Loading.tsx:20 - Container missing `role="status"` and `aria-live="polite"` for screen reader announcement

---

## /Users/eular/Desktop/官网0215/frontend/src/components/MarkdownEditor.tsx
frontend/src/components/MarkdownEditor.tsx:19 - ToolbarButton component: icon-only buttons with no `aria-label` or accessible text
frontend/src/components/MarkdownEditor.tsx:111 - Bold toolbar button icon-only, missing `aria-label`
frontend/src/components/MarkdownEditor.tsx:117 - Italic toolbar button icon-only, missing `aria-label`
frontend/src/components/MarkdownEditor.tsx:123 - Underline toolbar button icon-only, missing `aria-label`
frontend/src/components/MarkdownEditor.tsx:133 - Heading1 toolbar button icon-only, missing `aria-label`
frontend/src/components/MarkdownEditor.tsx:138 - Heading2 toolbar button icon-only, missing `aria-label`
frontend/src/components/MarkdownEditor.tsx:148 - Bullet list toolbar button icon-only, missing `aria-label`
frontend/src/components/MarkdownEditor.tsx:153 - Ordered list toolbar button icon-only, missing `aria-label`
frontend/src/components/MarkdownEditor.tsx:159 - Blockquote toolbar button icon-only, missing `aria-label`
frontend/src/components/MarkdownEditor.tsx:165 - Code block toolbar button icon-only, missing `aria-label`
frontend/src/components/MarkdownEditor.tsx:174 - Undo toolbar button icon-only, missing `aria-label`
frontend/src/components/MarkdownEditor.tsx:177 - Redo toolbar button icon-only, missing `aria-label`
frontend/src/components/MarkdownEditor.tsx:25 - ToolbarButton uses `transition-all` (anti-pattern)
frontend/src/components/MarkdownEditor.tsx:77 - Editor container uses `transition-all` (anti-pattern)
frontend/src/components/MarkdownEditor.tsx:79 - `.ProseMirror` has `outline: none !important` without visible focus ring replacement
frontend/src/components/MarkdownEditor.tsx:19-28 - ToolbarButton missing `focus-visible:ring-*` visible focus indicator

---

## /Users/eular/Desktop/官网0215/frontend/src/components/NotificationBell.tsx
frontend/src/components/NotificationBell.tsx:68 - Bell icon button (size="icon") missing `aria-label`
frontend/src/components/NotificationBell.tsx:69 - Bell icon decorative, missing `aria-hidden="true"`
frontend/src/components/NotificationBell.tsx:71 - Unread dot indicator is visual-only, no screen reader text
frontend/src/components/NotificationBell.tsx:109 - Notification item is a `<div>` with `onClick` (should be `<button>` with correct role)
frontend/src/components/NotificationBell.tsx:109 - Notification item missing `tabIndex`, `role="button"`, and keyboard handler (`onKeyDown`)
frontend/src/components/NotificationBell.tsx:124 - `toLocaleString` should use `Intl.DateTimeFormat` with explicit locale for consistency
frontend/src/components/NotificationBell.tsx:51 - Inline navigation via `navigate()` and `window.open()` inside onClick (minor: should use `<a>`/`<Link>` for nav-only items)

---

## /Users/eular/Desktop/官网0215/frontend/src/components/OnboardingDialog.tsx
frontend/src/components/OnboardingDialog.tsx:165 - Input (invite code) missing associated `<label>` or `aria-label`
frontend/src/components/OnboardingDialog.tsx:165 - Input missing `autocomplete` attribute
frontend/src/components/OnboardingDialog.tsx:167 - Invite code input should have `spellcheck="false"` and `autocomplete="off"`
frontend/src/components/OnboardingDialog.tsx:168 - Input (institution name) missing associated `<label>` or `aria-label`
frontend/src/components/OnboardingDialog.tsx:168 - Input missing `autocomplete="organization"`
frontend/src/components/OnboardingDialog.tsx:171 - Input (description) missing associated `<label>` or `aria-label`
frontend/src/components/OnboardingDialog.tsx:174 - Input (phone) missing associated `<label>` or `aria-label`
frontend/src/components/OnboardingDialog.tsx:174 - Input should use `type="tel"`, `inputmode="tel"`, and `autocomplete="tel"`
frontend/src/components/OnboardingDialog.tsx:177 - Error text is a standalone `<p>` not linked to inputs via `aria-describedby`
frontend/src/components/OnboardingDialog.tsx:99 - Check icon decorative, missing `aria-hidden="true"`
frontend/src/components/OnboardingDialog.tsx:131 - ArrowRight icon decorative, missing `aria-hidden="true"`
frontend/src/components/OnboardingDialog.tsx:148 - ArrowRight icon decorative, missing `aria-hidden="true"`

---

## /Users/eular/Desktop/官网0215/frontend/src/components/PageWrapper.tsx
frontend/src/components/PageWrapper.tsx:13 - `animate-in` does not honor `prefers-reduced-motion` (no conditional)

---

## /Users/eular/Desktop/官网0215/frontend/src/components/PersistentUploadToast.tsx
frontend/src/components/PersistentUploadToast.tsx:34 - Fixed position toast does not account for `env(safe-area-inset-bottom)`
frontend/src/components/PersistentUploadToast.tsx:67 - Cancel button uses `title` instead of `aria-label`
frontend/src/components/PersistentUploadToast.tsx:70 - X icon in cancel button decorative, missing `aria-hidden="true"`
frontend/src/components/PersistentUploadToast.tsx:76 - Close button uses `title` instead of `aria-label`
frontend/src/components/PersistentUploadToast.tsx:79 - X icon in close button decorative, missing `aria-hidden="true"`
frontend/src/components/PersistentUploadToast.tsx:6-14 - Status icons (Upload, Loader2, CheckCircle2, XCircle, FileWarning) missing `aria-hidden="true"`

---

## /Users/eular/Desktop/官网0215/frontend/src/components/PointsConfirmDialog.tsx
frontend/src/components/PointsConfirmDialog.tsx:35 - Coins icon decorative, missing `aria-hidden="true"`
frontend/src/components/PointsConfirmDialog.tsx:47 - Balance display uses `→` text character instead of accessible arrow icon or semantic element

---

## /Users/eular/Desktop/官网0215/frontend/src/components/UpgradeModal.tsx
frontend/src/components/UpgradeModal.tsx:93 - Check icons in feature list decorative, missing `aria-hidden="true"`
frontend/src/components/UpgradeModal.tsx:114 - Button triggers `navigate()` and `scrollIntoView` side effects (acceptable for CTA button, but navigation should prefer `<Link>`)

---

## /Users/eular/Desktop/官网0215/frontend/src/components/WeeklyReportDialog.tsx
frontend/src/components/WeeklyReportDialog.tsx:240 - Uses `window.alert()` instead of app's toast/modal system
frontend/src/components/WeeklyReportDialog.tsx:261 - Hardcoded `bg-white` breaks dark mode (no dark variant)
frontend/src/components/WeeklyReportDialog.tsx:283 - Calendar icon decorative, missing `aria-hidden="true"`
frontend/src/components/WeeklyReportDialog.tsx:306 - Download icon in button (button has text, icon decorative) missing `aria-hidden="true"`
frontend/src/components/WeeklyReportDialog.tsx:437 - TrendingUp icon decorative, missing `aria-hidden="true"`
frontend/src/components/WeeklyReportDialog.tsx:445 - BrainCircuit icon decorative, missing `aria-hidden="true"`
frontend/src/components/WeeklyReportDialog.tsx:453 - Calendar icon decorative, missing `aria-hidden="true"`
frontend/src/components/WeeklyReportDialog.tsx:463 - Award icon decorative, missing `aria-hidden="true"`
frontend/src/components/WeeklyReportDialog.tsx:88-92 - `formatMetricValue` returns hardcoded format strings, should use `Intl.NumberFormat`
frontend/src/components/WeeklyReportDialog.tsx:390 - Tooltip-less `<circle>` elements in SVG chart (low severity, chart is decorative)

---

## /Users/eular/Desktop/官网0215/frontend/src/components/course/OutlinePanel.tsx
frontend/src/components/course/OutlinePanel.tsx:43 - Loader2 icon decorative, missing `aria-hidden="true"`
frontend/src/components/course/OutlinePanel.tsx:59 - Sparkles icon decorative, missing `aria-hidden="true"`
frontend/src/components/course/OutlinePanel.tsx:61 - ChevronUp/ChevronDown icons decorative, missing `aria-hidden="true"`

---

## /Users/eular/Desktop/官网0215/frontend/src/components/course/SubtitlesOverlay.tsx
✓ pass

---

## /Users/eular/Desktop/官网0215/frontend/src/components/interviews/InterviewLobby.tsx
frontend/src/components/interviews/InterviewLobby.tsx:106 - Sparkles icon decorative, missing `aria-hidden="true"`
frontend/src/components/interviews/InterviewLobby.tsx:126 - Dynamic type.icon (FileText/Globe/GraduationCap) decorative, missing `aria-hidden="true"`
frontend/src/components/interviews/InterviewLobby.tsx:127 - type.icon component instance missing `aria-hidden="true"`

---

## /Users/eular/Desktop/官网0215/frontend/src/components/interviews/RadarChart.tsx
✓ pass

---

## /Users/eular/Desktop/官网0215/frontend/src/components/interviews/ResumeTuner.tsx
frontend/src/components/interviews/ResumeTuner.tsx:154 - Sparkles icon decorative, missing `aria-hidden="true"`
frontend/src/components/interviews/ResumeTuner.tsx:169 - File drop zone `<div>` with `onClick` should be a `<button>` or `<label>` for accessibility
frontend/src/components/interviews/ResumeTuner.tsx:176 - Drop zone click handler on `<div>` missing keyboard accessibility (`onKeyDown`)
frontend/src/components/interviews/ResumeTuner.tsx:185 - File size uses hardcoded `KB` and `toFixed(1)` - should use `Intl.NumberFormat`
frontend/src/components/interviews/ResumeTuner.tsx:219 - Textarea missing associated `<label>` or `aria-label`
frontend/src/components/interviews/ResumeTuner.tsx:226 - Clear text button icon-only (X icon), missing `aria-label`
frontend/src/components/interviews/ResumeTuner.tsx:229 - X icon decorative, missing `aria-hidden="true"`
frontend/src/components/interviews/ResumeTuner.tsx:253 - Loader2 icon decorative, missing `aria-hidden="true"`
frontend/src/components/interviews/ResumeTuner.tsx:261 - FileText icon decorative, missing `aria-hidden="true"`

---

## /Users/eular/Desktop/官网0215/frontend/src/components/interviews/SessionChat.tsx
frontend/src/components/interviews/SessionChat.tsx:243 - Textarea missing associated `<label>` or `aria-label`
frontend/src/components/interviews/SessionChat.tsx:252 - Send button icon-only (Send icon), missing `aria-label`
frontend/src/components/interviews/SessionChat.tsx:257 - Send icon decorative, missing `aria-hidden="true"`
frontend/src/components/interviews/SessionChat.tsx:122 - `onKeyDown` prevents default browser behavior for Enter key (acceptable for chat but should document pattern)
frontend/src/components/interviews/SessionChat.tsx:246 - Textarea has `onKeyDown` for Enter-to-submit, but no Escape handling for blur/mobile keyboard dismiss

---

## /Users/eular/Desktop/官网0215/frontend/src/components/interviews/SessionList.tsx
frontend/src/components/interviews/SessionList.tsx:49 - CheckCircle2 icon decorative, missing `aria-hidden="true"`
frontend/src/components/interviews/SessionList.tsx:51 - Clock icon decorative, missing `aria-hidden="true"`
frontend/src/components/interviews/SessionList.tsx:53 - Circle icon decorative, missing `aria-hidden="true"`
