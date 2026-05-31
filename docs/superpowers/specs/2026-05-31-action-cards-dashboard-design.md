# Action Cards Dashboard — AI 驱动的行动引导卡片

**日期**: 2026-05-31
**状态**: 已批准
**范围**: 小宇 VisualCanvas 新增 `action_cards` 视觉类型

## 背景

当前小宇的 VisualCanvas 支持 4 种视觉类型（`data_card`、`latex_derivation`、`step_solution`、`knowledge_map`），都是纯展示型。用户需要一个**行动引导**层：AI 分析学习数据后，生成可跳转的卡片，引导下一步学习（薄弱点 → 推荐视频、复习到期 → 刷题页等）。

## 设计目标

1. **AI 决策布局**：卡片不等宽，AI 通过 `priority` 字段决定每张卡片的占宽
2. **行动导向**：每张卡片必须有可跳转的 action，不是纯数据展示
3. **数据组合**：AI 自由组合 `get_user_weak_points` + `search_asr` + `get_due_reviews` + `search_courses` 等工具生成建议
4. **零新增依赖**：纯 CSS Grid 实现 masonry 效果

## 数据模型

### `action_cards` 视觉类型

```typescript
interface ActionCardsPayload {
  title?: string;                    // 卡片组标题，如"今日学习建议"
  cards: ActionCard[];
}

interface ActionCard {
  title: string;                     // 卡片标题，如"函数单调性薄弱"
  description: string;               // 描述，如"正确率 45%，建议先看视频巩固"
  priority: 'high' | 'normal' | 'low';  // 决定占宽
  icon: 'video' | 'quiz' | 'review' | 'course' | 'chart' | 'plan' | 'exam';
  action: {
    type: 'video' | 'quiz' | 'review' | 'course' | 'article' | 'plan' | 'exam';
    url: string;                     // 跳转 URL
    label: string;                   // 按钮文案，如"观看视频"
  };
}
```

### priority → 布局映射

| priority | 占宽 | 适用场景 |
|----------|------|---------|
| `high` | 2 列（全宽） | 正确率 < 50% 的薄弱点，需要重点突破 |
| `normal` | 1 列 | 正确率 50-70%，或复习到期、考试记录等 |
| `low` | 1 列（紧凑） | 连续学习天数、积分等辅助信息 |

### icon → 视觉映射

| icon | 颜色 | 图标 |
|------|------|------|
| `video` | blue | PlayCircle |
| `quiz` | green | PenLine |
| `review` | amber | RotateCcw |
| `course` | indigo | BookOpen |
| `chart` | emerald | TrendingUp |
| `plan` | purple | Calendar |
| `exam` | red | FileText |

## 前端实现

### 新增文件

**`frontend/src/pages/xiaoyu/visuals/ActionCardsRenderer.tsx`**

- CSS Grid 布局：`grid-template-columns: repeat(2, 1fr)` + `grid-auto-rows: auto`
- `high` 卡片：`grid-column: span 2`
- 每张卡片结构：左侧彩色指示条（4px，颜色由 icon 决定）+ 标题 + 描述 + 底部跳转按钮
- hover 效果：`translate-y(-1px)` + `shadow-md`，暗示可点击
- 使用 `useNavigate` 处理内部路由跳转，外部链接用 `window.open`

### 修改文件

**`frontend/src/pages/xiaoyu/visuals/index.ts`**

- 注册 `action_cards: ActionCardsRenderer`

### 布局示例

```
┌─────────────────────────────────┐
│  high: 函数单调性薄弱            │
│  正确率 45%，推荐观看导数应用视频  │
│  [观看视频 →]                    │
└─────────────────────────────────┘
┌───────────────┐ ┌───────────────┐
│ normal:       │ │ normal:       │
│ 12道复习题到期 │ │ 上次考试 85分  │
│ [开始复习 →]  │ │ [查看记录 →]  │
└───────────────┘ └───────────────┘
┌──────┐ ┌──────┐ ┌───────────────┐
│ low: │ │ low: │ │ normal:       │
│ 连续 │ │ 积分 │ │ 推荐课程      │
│ 7天  │ │ 320  │ │ [查看 →]     │
└──────┘ └──────┘ └───────────────┘
```

## 后端实现

### Prompt 变更

**`backend/prompts/ai_assistant/bots/xiaoyu/tool_guide.txt`**

新增行动卡片使用指南：

```
## render_visual — action_cards 行动引导卡片

适用场景：用户询问"今天学什么""有什么建议""薄弱点分析""学习建议"等意图时。

数据组合流程：
1. 调用 get_user_weak_points 获取薄弱知识点（按 mastery_score 升序）
2. 对 Top 3 薄弱点调用 search_asr 搜索匹配的视频课程片段
3. 调用 get_due_reviews 获取到期复习任务
4. 可选：调用 search_courses 推荐相关课程

优先级规则：
- mastery_score < 0.5 → priority: 'high'
- mastery_score 0.5-0.7 → priority: 'normal'
- 辅助信息（连续天数、积分等）→ priority: 'low'

每张卡片必须有可跳转的 action。视频类 action 的 url 格式：/courses/{id}?t={seconds}
```

### 工具校验

**`backend/ai_assistant/services/tool_executor.py`**

`_handle_render_visual` 方法的 `VALID_TYPES` 集合新增 `'action_cards'`。

## 改动范围

| 文件 | 改动类型 | 预估行数 |
|------|---------|---------|
| `frontend/src/pages/xiaoyu/visuals/ActionCardsRenderer.tsx` | 新增 | ~120 行 |
| `frontend/src/pages/xiaoyu/visuals/index.ts` | 修改 | +2 行 |
| `backend/prompts/ai_assistant/bots/xiaoyu/tool_guide.txt` | 修改 | +30 行 |
| `backend/ai_assistant/services/tool_executor.py` | 修改 | +1 行 |

总计 ~150 行改动。

## 验证方式

1. 前端：在 XiaoYu 对话中输入"分析我的薄弱点并推荐视频"，确认 AI 调用 `render_visual` 输出 `action_cards` 类型，VisualCanvas 正确渲染 masonry 布局
2. 点击卡片跳转：确认视频卡片跳转到 `/courses/{id}?t={seconds}`，复习卡片跳转到 `/review`
3. 布局：确认 high 卡片全宽，normal/low 卡片半宽，不同屏幕宽度下自适应
