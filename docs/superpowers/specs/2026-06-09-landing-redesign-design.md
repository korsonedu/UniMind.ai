# Landing Page Redesign Design

**Date:** 2026-06-09
**Status:** Approved
**Scope:** `frontend/src/pages/Landing.tsx` — 视觉风格重写，不改组件结构

## 设计决策

| 决策项 | 选择 | 原因 |
|--------|------|------|
| 主题 | 亮白底 #FAFAFA | 差异化——8/10 AI 站用暗色 |
| 强调色 | 深靛蓝纯色 #2D2B6B | 去蓝紫渐变，纯色更沉稳 |
| 字体 | DM Sans（标题+正文） | 比 Inter 圆润，适合教育产品 |
| Hero 背景 | 去掉知识图谱 canvas | 简化首屏，突出文案 |
| Hero 布局 | 优化现有居中布局 | 改动最小，内容逻辑已验证 |
| 页面结构 | 保留 9 section | 不合并，只统一视觉风格 |
| 蓝紫渐变 | 全部删除 | 用户明确反感 AI 行业视觉俗套 |

## Hero 区层级（从上到下）

1. **🎉 Memorix-Field 通知**（文字直出，单行，深色）
   - 文案：`🎉 Memorix-Field 图扩散记忆调度发布 — 遗忘率相比 SOTA 降低 19.9%，现已全面支持 Agent 个性化学习路径 →`
   - 链接到 `/memorix`
   - 样式：无胶囊，纯文字，`text-[12px] text-[#2d2b6b]`，strong 标记产品名

2. **标题**
   - `让每个学生拥有` / `专属 AI 学习引擎`（第二行深靛蓝高亮）
   - DM Sans, `text-[38px] md:text-[52px] lg:text-[64px] font-extrabold tracking-[-0.03em]`

3. **副标题 + 主 CTA**
   - 副标题：`个性化记忆调度 × 知识图谱 × 小宇 Agent`
   - CTA：深靛蓝实心按钮 `免费开始 →`

4. **Promo 胶囊**（深靛蓝边框+淡底色）
   - 文案：`首批机构专享 · Growth 方案免费开放`
   - 链接到 `/promo/plus`

5. **Trust 标记**
   - `已服务 10+ 机构 · 50,000+ 题目生成`

## FinalCTA 区

- 标题：`准备好，进入智能教育新时代`
- 副标题：`首批机构免费获得 Growth 方案。AI 出题、自适应复习、学情分析——开箱即用。`
- 双 CTA：`免费开始`（主按钮）+ `查看方案对比 →`（文字链接）
- 深色底 #111 不变

## 全局视觉变更

### 颜色替换

| 旧值 | 新值 | 位置 |
|------|------|------|
| `linear-gradient(135deg, #6366f1, #8b5cf6, #06b6d4)` | `#2d2b6b` | Hero 标题高亮、Stats 数字、标签 |
| `text-[#5b5fef]` | `text-[#2d2b6b]` | section label |
| `bg-gray-900 hover:bg-gray-800` (CTA) | `bg-[#2d2b6b] hover:bg-[#232260]` | 主 CTA 按钮 |
| `#5b5fef` (FinalCTA 按钮) | `#2d2b6b` | FinalCTA 按钮 |
| `text-indigo-500/600` | `text-[#2d2b6b]` | 标签、链接 |
| `bg-indigo-50` | `bg-[#f0efff]` | Promo 胶囊底色 |
| `border-indigo-300` | `border-[#d4d0f5]` | Promo 胶囊边框 |

### 字体替换

| 旧值 | 新值 |
|------|------|
| `"Playfair Display", serif` | `"DM Sans", sans-serif` |
| `"DM Mono", monospace`（Stats 数字） | 保留不变 |

### 移除项

- `KnowledgeGraphCanvas` 组件引用和 import
- Hero 区 canvas 背景
- 所有蓝紫渐变（`linear-gradient(135deg, #6366f1, #8b5cf6, ...)`）

### 不变项

- 9 section 结构
- Scroll reveal 动效逻辑
- 鼠标视差 hook（`useMouseParallax`）
- 动画计数器 hook（`useCountUp`）
- Nav 逻辑（scrolled 状态、mobile menu）
- i18n 翻译 key（只改视觉，不改文案 key）
- Testimonials 滚动动画
- Subjects 标签云

## 验证标准

- [ ] 无蓝紫渐变残留（grep `#6366f1` `#8b5cf6` `#06b6d4` 无结果）
- [ ] `KnowledgeGraphCanvas` import 已移除
- [ ] Hero 区无 canvas 元素
- [ ] Memorix 通知在 Hero 标题上方，单行显示
- [ ] Promo 胶囊在 CTA 下方
- [ ] FinalCTA 双 CTA 布局
- [ ] 所有 CTA 按钮颜色统一为 #2d2b6b
- [ ] DM Sans 字体正确加载（Google Fonts）
- [ ] `make frontend-check` 通过
