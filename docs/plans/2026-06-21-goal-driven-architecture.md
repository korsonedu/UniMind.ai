# 目标→规划→执行 架构方案

## 现状问题

当前三个系统各自独立，没有统一的目标驱动链路：

```
StudyPlan (学生端)         — per-user, Memorix 生成任务清单
TeachingPlan (教师端)      — per-class, 周计划 JSON
Memorix Field             — 识别现状（薄弱点/前驱链/遗忘风险）
```

问题：
- StudyPlan 我刚错加了 goal/deadline（学生不该定目标）
- TeachingPlan 没有目标字段，只有周计划结构，教师手动填
- Memorix Field 知道现状但不知道该往哪走
- 三者之间没有数据流动

## 正确架构

```
教师设定目标 ──→ TeachingPlan ──→ 拆解为周计划（覆盖哪些 KP）
                                       ↓
Memorix Field 识别现状 ──→ Agent 计算 gap ──→ StudyPlan
  （薄弱点/掌握度/遗忘）     （目标-现状）      （每日任务）
```

**职责边界：**

| 层 | 谁操作 | 数据 |
|----|--------|------|
| 目标 | 教师在工作台/教案页 | goal, deadline, target_score, subject |
| 规划 | Agent（工作台对话） | 根据目标 + 知识树大小计算每周推进节奏 |
| 进度追踪 | TeachingPlan | milestones, 当前周/总周, 领先/落后 |
| 现状识别 | Memorix Field | 薄弱点、前驱链、遗忘风险、掌握度分布 |
| 每日执行 | StudyPlan | Memorix 到期复习 + 本周新学 KP 练习 |

## 数据流

```
教师: "火箭班，1年内高考数学130分"
  → TeachingPlan.goal = "1年内高考数学130分"
  → TeachingPlan.deadline = "2027-06-01"
  → Agent 计算: 52周 / 120个KP = 每周2-3个KP
  → TeachingPlan.weekly_plans = [Week1→..., Week2→...]

教师说 "生成火箭班本周学习计划"
  → Agent 读取 TeachingPlan.weekly_plans[当前周].kp_ids
  → Agent 读 Memorix Field: 该班学生在这些 KP 上的掌握度分布
  → Agent 为每个学生生成 StudyPlan:
     tasks = [
       当前周新学KP练习（来自 TeachingPlan）,
       Memorix 到期复习（来自 Memorix Field）
     ]

学生打开小宇:
  → 看到 StudyPlan 每日任务
  → 完成/跳过/调顺序
  → 不改目标
```

## 模型改动

### StudyPlan — 回退

移除我刚加的 6 个字段（这些不该在这里）：
- ~~goal, deadline, target_score, subject, current_level, milestones~~

新加 1 个 FK：
- `teaching_plan = FK(TeachingPlan, null=True)` — 可选，有班级的学生关联

### TeachingPlan — 接手目标

新加 5 个字段：
- `goal = TextField` — "1年内达到高考数学130分"
- `deadline = DateField(null=True)` — 目标截止日
- `target_score = PositiveIntegerField(null=True)` — 目标分数
- `current_level = CharField` — "已掌握基础代数，薄弱在函数和解析几何"
- `milestones = JSONField(null=True)` — [{week:4, target:"函数章节掌握80%", achieved:false}]

已有字段继续使用：
- `weekly_plans` — 保留现有结构，加 `kp_ids` 用于 Agent 规划
- `subject, semester, week_count` — 保留

## 实施步骤

### Step 1: StudyPlan 回退（1 个 migration）

1. 删除刚加的 6 个字段
2. 生成回退 migration
3. 加 `teaching_plan` FK

### Step 2: TeachingPlan 加目标字段（1 个 migration）

1. 加 goal, deadline, target_score, current_level, milestones
2. 生成 migration

### Step 3: 后端数据流（3 个改动）

1. **工作台 Agent 工具**：加 `create_teaching_plan` 工具，教师对话设定目标
2. **Dashboard**：`XiaoYuDashboardView._get_plan` 关联 TeachingPlan
3. **小宇 Agent 工具**：`get_active_plan` 返回 teaching_plan 关联数据

### Step 4: 前端（2 个改动）

1. **教案页 LessonPlans.tsx**：加目标设定面板（goal/deadline）+ 进度条
2. **XiaoYu 计划卡片**：显示 "来自火箭班教学计划 · 第3周函数" 来源信息

### Step 5: Agent prompt 更新

1. 工作台 tool_guide：加 create_teaching_plan 使用说明
2. 小宇 tool_guide：更新 save_study_plan，说明混合 TeachingPlan + Memorix

## 不改的东西

- Memorix Field 的 analytics_service — 已有正确率/前驱链/遗忘风险分析，够用
- StudyPlan 的前端任务编辑 — 保留完成/跳过/调顺序/增删任务
- LessonPlan 模型 — 保留，但暂不改动（后续迭代）

## 改动量估算

| 步骤 | 文件 | 量级 |
|------|------|------|
| Step 1 | models.py + migration | ~20 行 |
| Step 2 | models.py + migration | ~10 行 |
| Step 3 | tool_executor.py + views_dashboard.py + tools.py | ~80 行 |
| Step 4 | LessonPlans.tsx + XiaoYu.tsx | ~60 行 |
| Step 5 | tool_guide.txt × 2 | ~20 行 |

总计 ~200 行，2 个 migration。
