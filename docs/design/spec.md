# UniMind 产品与品牌设计规范

> v1.0 — 2026-06-17
> 本规范是 UniMind 前端实现的唯一设计来源。所有 PR/audit 以此为准。

---

## 1. 品牌标识

### 1.1 Logo

| 变体 | 文件 | 用途 |
|------|------|------|
| 标准横版 | `Unimind_logo.png` (50KB) | 侧边栏、顶部导航 |
| 宽版 | `Unimind_logo_wide.png` (96KB) | 登录页、Landing |
| 小图标 | `unimind_logo_small.png` (601KB) | 折叠侧边栏、favicon |
| Favicon | `favicon.svg` | 浏览器标签 |

Logo 使用时不添加阴影、边框或背景色。侧边栏中的 logo 使用 CSS class `brand-logo-invert` 处理暗色模式颜色反转。

### 1.2 品牌色

| Token | Hex | HSL | 用途 |
|-------|-----|-----|------|
| **UniMind Blue** | `#0071E3` | `211 100% 45%` | 主色调、链接、按钮、选中态 |
| UniMind Red | `#FF3B30` | `3 100% 59%` | 错误、危险操作、逾期标记 |
| UniMind Green | `#34C759` | `142 100% 42%` | 成功、已提交、已掌握 |

主色调 `--unimind-blue` 已映射至 shadcn/ui 的 `--primary`，全局一致性由 CSS 变量保证。

### 1.3 辅助调色板

| Token | Hex | HSL | 用途 |
|-------|-----|-----|------|
| Text Primary | `#1D1D1F` | `240 2% 11%` | 正文、标题 |
| Text Secondary | `#6E6E73` | `240 2% 45%` | 辅助文字 |
| Text Tertiary | `#8E8E93` | `240 2% 58%` | 占位符、禁用态 |
| Border | `#E5E5EA` | `240 4% 90%` | 分隔线、卡片边框 |
| Background Secondary | `#F5F5F7` | `240 7% 97%` | 次级背景、输入框填充 |

---

## 2. 设计系统

### 2.1 技术栈

| 层 | 选型 | 说明 |
|----|------|------|
| UI 框架 | **shadcn/ui** (Radix primitives) | 组件源码在 `frontend/src/components/ui/` |
| CSS 框架 | **Tailwind CSS v3** | `tailwind.config.js` 映射 CSS 变量 |
| 图标 | **@phosphor-icons/react** | 唯一图标库，禁止混用 Lucide |
| 字体 | **系统字体栈** + Playfair Display (display) | 见 §3 |
| 动画 | **CSS animate-in** (tailwindcss-animate) | 无外部动画库依赖 |

### 2.2 组件库纪律

- 所有 UI 组件从 `@/components/ui/` 导入，不手写 primitives
- shadcn/ui 组件可定制但不可重构其内部结构
- 新增组件用 `npx shadcn@latest add <name>`，保持源码可控
- Card 使用 `variant` 属性（`default` / `apple`），不直接覆写背景色

---

## 3. 字体排印

### 3.1 Font Stack

```css
font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI",
             Roboto, "Helvetica Neue", Arial, sans-serif;
```

- **正文**: 系统 sans-serif（Apple 平台使用 SF Pro）
- **Display**: Playfair Display（仅 Marketing/Landing 页面的大标题）

### 3.2 字重约定

| 用途 | Tailwind | 说明 |
|------|----------|------|
| 页面标题（H1） | `font-black` + `tracking-tight` | 仅 PageWrapper title / DialogTitle |
| 卡片标题 / 段落标题 | `font-bold` | 默认强调字重 |
| 标签 / Badge | `font-bold` | 小字号加粗 |
| 正文 | `font-medium` | 可读性优先 |
| 辅助文字 | `font-medium` 或 `font-normal` | 配合 `text-muted-foreground` |

`font-black` 不可用于正文、标签、按钮或辅助文字。每页的 `font-black` 使用点应不超过 3 处（标题 + 关键数字）。

### 3.3 字号阶梯

| 用途 | 字号 | Tailwind |
|------|------|----------|
| 页面 H1 | 28px | `text-2xl` |
| 区块标题 | 20px | `text-xl` |
| 卡片标题 | 16px | `text-base` / `text-sm font-bold` |
| 正文 | 14px | `text-sm` |
| 辅助 / 标签 | 12px | `text-xs` |
| 微型 | 10-11px | `text-[10px]` / `text-[11px]` |

---

## 4. 颜色系统

### 4.1 Semantic Token Map

产品界面**必须**使用 Tailwind semantic tokens。以下为唯一合法的颜色 class：

| 语义 | Light | Dark | 用法 |
|------|-------|------|------|
| `bg-background` | `#FFFFFF` | `hsl(240 10% 3.9%)` | 页面底色 |
| `bg-card` | `#FFFFFF` | `hsl(240 10% 3.9%)` | 卡片、面板 |
| `bg-muted` | `hsl(240 4.8% 95.9%)` | — | 次级背景、输入框填充 |
| `text-foreground` | `#1D1D1F` | `hsl(0 0% 98%)` | 正文 |
| `text-muted-foreground` | `hsl(240 3.8% 46.1%)` | — | 辅助文字 |
| `border-border` | `hsl(240 5.9% 90%)` | — | 边框、分隔线 |
| `text-primary` | `#0071E3` | — | 链接、强调 |
| `bg-primary` | `#0071E3` | — | 主按钮、选中态 |
| `text-primary-foreground` | `#FFFFFF` | — | 主按钮文字 |

### 4.2 禁止使用的颜色

- **禁止** hex 色值（`#xxxxxx`）——除数据可视化（图表色板）和品牌资产（logo 背景色）外
- **禁止** `bg-white` / `text-black` ——使用 `bg-card` / `text-foreground`
- **禁止** `border-gray-*` / `border-stone-*` / `border-slate-*` ——使用 `border-border`
- **禁止** `bg-gray-50` / `bg-stone-50` / `bg-slate-50` ——使用 `bg-muted`
- **禁止** `text-stone-*` / `text-gray-*` ——使用 `text-foreground` / `text-muted-foreground`

### 4.3 例外：状态色

以下函数式颜色可在 light mode 直接使用，但**必须**配 dark mode variant：

```
bg-amber-50 dark:bg-amber-950/30
text-amber-600 dark:text-amber-400
border-amber-200 dark:border-amber-800/40

bg-emerald-50 dark:bg-emerald-950/30
text-emerald-600 dark:text-emerald-400
border-emerald-200 dark:border-emerald-800/40

bg-red-50 dark:bg-red-950/30
text-red-600 dark:text-red-400
border-red-200 dark:border-red-800/40
```

### 4.4 独立设计语言页面

以下页面不适用 §4.1-4.3 的颜色限制，各自维护其内部一致的色板：

- `Landing.tsx` — 公开着陆页，白色底 + UniMind Blue 品牌色
- `Memorix.tsx` — 研究论文页，暗色主题 `#0a0a14`
- `InstitutionHome.tsx` — 机构公开首页，自定义品牌色
- `PromoPlus.tsx` — 推广页
- `Pricing.tsx` — 定价页

---

## 5. 形状系统

### 5.1 圆角

```
Component        | Tailwind        | 值
─────────────────|─────────────────|──────
Card / Panel     | rounded-xl      | 12px
Dialog           | rounded-xl      | 12px
Input / Select   | rounded-lg      | 8px
Button           | rounded-lg      | 8px
Badge / Pill     | rounded-full    | 9999px
Avatar           | rounded-full    | 9999px
```

**禁止** `rounded-2xl` / `rounded-3xl` 在标准产品卡片上使用。特例：Settings 页面的 profile 卡片、Sheet 面板可使用 `rounded-2xl` / `rounded-3xl`。

**禁止** `rounded-apple`（非标准）。替换为 `rounded-xl`。

### 5.2 Shadow

默认不使用投影。仅在需要表示浮层层次时使用：
- Dialog/Popover: `shadow-lg`（Dialog 组件自带）
- 卡片 Hover: `hover:shadow-sm`（可选）

---

## 6. 间距与布局

### 6.1 页面内容宽度

```
类别           | max-w           | 适用页面
───────────────|─────────────────|─────────────────────────────────
专注阅读       | max-w-2xl 672px | MyAssignments, StudyPlan, StudentHome
标准列表       | max-w-4xl 896px | CourseCenter, ArticleCenter, PdfMockExam, AssetHub
数据密集       | max-w-6xl 1152px| TestLadder, WrongQuestionReview, Gradebook, InstitutionDashboard, InstitutionAdmin, TeacherQuestions
全画布         | w-full          | KnowledgeMap, Workbench
```

所有使用 `PageWrapper` 的页面应在其内容区包裹上述 `max-w` 容器。

### 6.2 页面容器

学生端和教师端的产品页面**必须**使用 `PageWrapper`，传 `title` 和 `subtitle`。不传 title 会导致顶部栏空白。

独立页面（Login, Register, Landing, Pricing, Checkout 等）不使用 `PageWrapper`。

### 6.3 Section 间距

- 页面级 section 间距: `space-y-5` 或 `space-y-6`
- 卡片内间距: `space-y-3` 或 `space-y-4`
- 表单字段间距: `space-y-2.5`（label + input）

### 6.4 输入框高度

```
用途           | Tailwind  | px
───────────────|───────────|─────
标准输入框     | h-9       | 36px
大号输入框     | h-10      | 40px
紧凑输入框     | h-8       | 32px（仅内联表单/工具栏搜索）
```

---

## 7. 组件模式

### 7.1 页面标题

使用 `PageWrapper` 组件：
```tsx
<PageWrapper title="我的作业" subtitle="">
  <div className="max-w-2xl mx-auto">
    {/* page content */}
  </div>
</PageWrapper>
```

### 7.2 卡片

```tsx
// 标准产品卡片
<div className="rounded-xl border border-border bg-card p-4">

// 无边框卡片（浮层感）
<Card className="border-none shadow-sm rounded-xl">

// 展开面板
<div className="rounded-xl border border-border bg-card overflow-hidden">
```

### 7.3 空状态

```tsx
<div className="flex flex-col items-center justify-center py-20 text-muted-foreground">
  <div className="h-16 w-16 rounded-2xl bg-muted/40 flex items-center justify-center mb-4">
    <Icon className="h-8 w-8 text-muted-foreground/30" />
  </div>
  <p className="text-sm font-bold">暂无内容</p>
  <p className="text-xs mt-1 text-muted-foreground/60">说明文字</p>
</div>
```

### 7.4 加载态

使用 Skeleton 组件匹配最终布局形状，不使用裸 Spinner：

```tsx
// 列表加载
<div className="space-y-2">
  {Array.from({ length: 4 }).map((_, i) => (
    <div key={i} className="rounded-xl border border-border bg-card p-4 flex items-center gap-3">
      <Skeleton className="h-9 w-9 rounded-lg shrink-0" />
      <div className="flex-1 space-y-1.5">
        <Skeleton className="h-4 w-48" />
        <Skeleton className="h-3 w-32" />
      </div>
    </div>
  ))}
</div>
```

### 7.5 Badge 状态色

```tsx
// Warning
<Badge variant="outline" className="border-amber-200 dark:border-amber-800/40 text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/30">

// Success
<Badge variant="outline" className="border-emerald-200 dark:border-emerald-800/40 text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/30">

// Danger
<Badge variant="outline" className="border-red-200 dark:border-red-800/40 text-red-500 dark:text-red-400">
```

### 7.6 微交互

所有可点击元素应包含：
- `transition-colors duration-150` 或 `duration-200`
- `active:scale-[0.99]` 或 `active:scale-[0.98]`（按钮按压反馈）
- `hover:border-primary/20`（卡片 hover 边框微亮）

页面入场动画（通过 PageWrapper 或内容区 wrapper）：
- `animate-in fade-in slide-in-from-bottom-2 duration-300`

---

## 8. 页面类型与路由

### 8.1 产品页面（适用本规范全部条款）

| 页面 | 路由 | PageWrapper | 内容宽度 |
|------|------|-------------|---------|
| 我的作业 | `/my-assignments` | ✅ | `max-w-2xl` |
| 学习计划 | `/plan` | ✅ | `max-w-2xl` |
| 学生首页 | `/` (学生) | ✅ | `max-w-2xl` |
| 课程中心 | `/courses` | ✅ | `max-w-4xl` |
| 文章中心 | `/articles` | ✅ | `max-w-4xl` |
| 模拟考试 | `/mock-exam` | ✅ | `max-w-4xl` |
| 资产中心 | `/asset-hub` | ❌ | `max-w-4xl` |
| 刷题天梯 | `/tests` | ✅ | `max-w-6xl` |
| 错题本 | `/wrong-review` | ✅ | `max-w-6xl` |
| 成绩册 | `/gradebook` | ✅ | `max-w-6xl` |
| 机构管理 | `/institution/admin` | ❌ | `max-w-6xl` |
| 机构看板 | `/institution` | ❌ | `max-w-6xl` |
| 教师题库 | `/questions` | ❌ | `max-w-6xl` |
| 教师作业 | `/assignments` | ❌ | `max-w-4xl` |
| 知识地图 | `/knowledge-map` | ✅ | `w-full` |
| 工作台 | `/workbench` | ❌ | `w-full` |
| 答疑系统 | `/qa` | ✅ | `max-w-5xl` |
| 自习室 | `/study` | — | 专用布局 |
| 诊断测试 | `/diagnostic` | ❌ | 专用布局 |

### 8.2 独立页面（适用 §1-3，不适用 §4-7 产品条款）

- Landing `/`（未登录）
- Login `/login`
- Register `/register`
- Pricing `/pricing`
- Checkout `/checkout`
- PaymentResult `/payment-result`
- Memorix `/memorix`
- InstitutionHome `/intro/:slug`
- PromoPlus `/promo-plus`

### 8.3 管理页面（适用 §1-6，宽松执行 §7）

- Maintenance `/management`
- PlatformAnalytics `/platform-analytics`
- SystemSettings `/system-settings`
- AuditLogs `/audit-logs`
- InviteCodeAdmin `/invite-codes`
- PromptTemplatesAdmin `/prompt-templates`

---

## 9. 审计标准

### 9.1 合规检查清单

进行全量设计审计时，按以下清单逐页检查：

- [ ] **颜色**：无 `#xxxxxx` hex 色值（数据可视化除外）？无 `bg-white` / `text-black`？无 `border-gray-*` / `border-stone-*` / `border-slate-*`？
- [ ] **Dark Mode**：所有状态色（amber/emerald/red/green）有 `dark:` variant？
- [ ] **宽度**：内容区 `max-w` 与 §6.1 一致？
- [ ] **圆角**：卡片 `rounded-xl`？输入框 `rounded-lg`？标签 `rounded-full`？无 `rounded-apple`？
- [ ] **字重**：`font-black` 仅用于页面/弹窗标题（≤3 处/页）？
- [ ] **PageWrapper**：产品页面使用 PageWrapper 并传 title？
- [ ] **输入框**：高度为 `h-9`（标准）/ `h-10`（大号）/ `h-8`（紧凑）？
- [ ] **图标**：仅使用 `@phosphor-icons/react`？无 hand-rolled SVG paths？
- [ ] **空状态**：使用图标 + 圆角容器 + 分层文字？非裸 Spinner？
- [ ] **加载态**：使用 Skeleton 匹配布局形状？非裸 Spinner？
- [ ] **交互态**：可点击元素有 `transition-colors` + `active:scale-[0.99]`？
- [ ] **动画**：使用 `animate-in fade-in` 入场？无 `window.addEventListener('scroll')`？

### 9.2 违规分级

| 级别 | 定义 | 示例 |
|------|------|------|
| **P0 必须修复** | 颜色/宽度/圆角违规 | `bg-white`, `border-stone-100`, `max-w` 错误 |
| **P1 应该修复** | 组件模式不一致 | 缺 dark variant, 缺空状态, Skeleton→Spinner |
| **P2 可以优化** | 微交互/动画缺失 | 缺 `transition-colors`, 缺入场动画 |

---

## 10. 变更流程

1. 本规范修改需 PR 审批
2. 新增页面需在 §8.1-8.3 注册
3. 新增颜色 token 需在 §1 or §4 注册并同步 `index.css`
4. 全量审计每年至少一次，重大版本发布前强制执行
