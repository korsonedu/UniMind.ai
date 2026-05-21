# Frontend Audit & Redesign — UniMind.ai

## Goal

对 `frontend/src/` 下全部 ~100 个 TypeScript/TSX 文件进行：
1. Web Interface Guidelines 规范审核（全量 `file:line` 输出）
2. 去 AI 味：打破 shadcn 模板感（B 优先）、剔除过度装饰（A）、文案瘦身（C）
3. 全面修复 a11y/performance/i18n/form 等非设计问题

## Scope

| 层 | 文件范围 | 数量 |
|---|---------|------|
| UI 基元 | `components/ui/*.tsx` | 20 |
| 通用业务组件 | `components/*.tsx` + 子目录 | ~15 |
| 页面 | `pages/*.tsx` + 子目录 | ~40 |
| lib/store | `lib/*.ts` `store/*.ts` | ~15 |

## No-Go 区域

- **Landing / LandingZh / LandingEn** — 不动任何文案（C），不动整体结构设计
- **机构公开首页 (intro/:slug)** — 不在此次审核范围
- **不删除已有死代码** — 除非是改动造成的 orphan

## Phases

### Phase 1 — Audit（审核）

三层并发，每层按 Web Interface Guidelines 逐条检查，输出 `file:line` 格式。

**检查维度：**
- Accessibility：aria-label / label / keyboard / semantic HTML / alt
- Focus：focus-visible 替代 outline-none / :focus-within
- Forms：autocomplete / type / inputmode / label 可点击 / spellcheck / submit 状态
- Animation：prefers-reduced-motion / transform+opacity 限定 / 禁止 transition:all
- Typography：… vs ... / 正确引号 / tabular-nums / text-wrap balance
- Content：truncate / min-w-0 / empty state / 长内容处理
- Images：width+height / lazy loading / fetchpriority
- Performance：虚拟化 / 无 layout-read-in-render / uncontrolled inputs
- Navigation：URL 状态同步 / 正确 Link 标签 / destructive action 确认
- Touch：touch-action / tap-highlight / overscroll-behavior / drag
- Safe Areas：safe-area-inset / overflow 控制
- Dark Mode：color-scheme / meta theme-color
- i18n：Intl.DateTimeFormat / Intl.NumberFormat / translate="no"
- Hydration：value+onChange / 时间渲染一致性
- Hover：hover 状态 / 对比度递增
- Content：主动语态 / Title Case / 数字用阿拉伯 / 按钮明确 / 错误含下一步
- Anti-patterns：user-scalable=no / onPaste+preventDefault / transition:all / outline-none 无替代

### Phase 2 — De-shadcn Template（去 AI 味 B）

**核心矛盾：** shadcn/ui 的默认主题 = rounded-xl + shadow-sm + border-border + blue-purple gradient + Inter = 一眼 AI。

**策略：**
1. **重设计 UI 基元** — 用 `frontend-design` skill 为 button/card/input/dialog/select/tabs/badge 注入 UniMind 品牌特征
2. **建立 design tokens** — 通过 CSS 变量 + Tailwind config 统合，消除 `Landing.tsx` 中硬编码的 `#0071E3` / `#1D1D1F` / `#6E6E73` 等 Apple 色值
3. **页面差异化** — tool-like pages（TestSession/KnowledgeMap）≠ marketing-like pages（Landing），不同定位不同视觉密度

**成功标准：** 截一张页面截图，没人能说"这是 shadcn 做的"。

### Phase 3 — Remove Over-decoration（去 AI 味 A）

剔除无功能目的的：
- 无意义渐变背景（bg-gradient-to-r 仅用于装饰）
- 过度阴影层次（shadow-2xl + shadow-blue-100/50 + ring 叠加）
- emoji 纯装饰用法
- 五颜六色的彩色卡片矩阵
- 动画仅为炫技（应简化或去除）

### Phase 4 — Copy Slimming（去 AI 味 C）

排除 Landing/Intro 页面后，找：
- "智能xxx" "一键xxx" "高效xxx" → 改具体动作
- 空泛 marketing speak → 改写或删除
- 按钮标签 "开始" "确认" "提交" → 具体动词 "添加知识点" "保存配置"
- 错误提示只描述问题 → 加上下一步："请检查网络后重试"

### Phase 5 — Fix Everything Else

逐文件修复 Phase 1 审核发现的全部非设计问题：
- a11y：缺 label、缺 aria、缺 keyboard handler、semantic 错误
- performance：长列表未虚拟化、layout read in render
- forms：缺 autocomplete、错误 type、paste 被阻止
- i18n：硬编码日期/数字格式 → Intl.*
- hydration：value 无 onChange、时间渲染不一致
- content：text truncation 缺失、empty state 缺失
- focus：outline-none 无 focus-visible 替代
- animation：transition:all → 属性列表

## Deliverables

- `docs/superpowers/specs/2026-05-20-frontend-audit-report.md` — 全量审核报告
- 重新设计的 UI 基元组件（20 个文件）
- 更新后的 Tailwind config（新增 design tokens）
- 各页面/组件修复
- 文案改动清单（Phase 4）

## Out of Scope

- 后端代码
- Landing/Intro 页面文案和结构
- 添加新功能
- 数据库迁移
- 测试用例编写
