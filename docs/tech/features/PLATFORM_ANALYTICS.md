# 平台数据分析系统

## 概述

平台级数据截留与分析系统，用于验证产品有效性、VC 数据展示、数据资产沉淀。所有数据**仅超管可见**，严格隔离。

## 数据价值与用途

### 一、产品有效性证明

核心问题：**UniMind 到底有没有用？**

| 数据 | 证明什么 | 怎么用 |
|------|----------|--------|
| 诊断前后测对比 | 学生用了产品后是否提分 | case study：某机构 30 天平均提分 X 分 |
| 答题正确率趋势 | 学习效果是否在改善 | 折线图展示正确率随时间上升 |
| 知识点薄弱分布 | 产品是否精准定位了薄弱环节 | 热力图展示 Top N 薄弱知识点被攻克 |
| 课程完成率 | 内容质量和用户粘性 | 完成率 > 60% 说明内容有价值 |
| AI 对话量 | AI 助教是否被真正使用 | 不是摆设，是高频工具 |
| 诊断完成率 | 新用户是否完成冷启动 | 漏斗：注册 → 诊断 → 首次刷题 |

**关键指标：** 学生平均提分幅度 × 使用学生数 = 产品影响力（VC 最爱看的数字）

### 二、增长与留存（VC 数据室必备）

| 指标 | VC 怎么看 | 我们怎么算 |
|------|-----------|-----------|
| DAU / MAU | 产品粘性，>20% 算健康 | 每日去重登录用户 |
| 次日留存 | 新用户是否回来，>30% 及格 | 前天注册用户中昨天登录的比例 |
| 7 日留存 | 产品是否有中期价值，>15% 及格 | 7 天前注册用户中本周活跃的比例 |
| 机构增长率 | 市场需求验证 | 每周新增机构数 |
| 机构续用率 | 产品力的终极证明 | 试用期满后继续使用的比例 |
| NPS 净推荐值 | 用户愿不愿意推荐，>0 算正向 | (%推荐者 - %贬损者) × 100 |

**叙事逻辑：** "我们有 X 家机构在用，Y 名学生，平均提分 Z 分，NPS 为 W，次日留存 N%"

### 三、数据资产沉淀（长期护城河）

| 数据资产 | 护城河价值 | 积累方式 |
|----------|-----------|----------|
| 题库质量反馈 | 哪些题被采纳/修改/淘汰 → 出题模型微调数据 | 每次 ARC 管线运行记录 |
| 学习行为序列 | 错题→复习→掌握 的时间序列 → Memorix 算法优化 | UserQuestionStatus 时间戳 |
| 知识图谱覆盖度 | 各学科各机构的知识点覆盖 → 平台壁垒 | 知识点 × 机构矩阵 |
| 教师偏好数据 | 出题风格、难度偏好 → 个性化 Agent | 命题官对话 + 模板使用记录 |
| 机构运营模式 | 不同机构的使用模式 → 最佳实践提炼 | 事件分布聚类 |

**护城河逻辑：** 数据越多 → 模型越准 → 体验越好 → 用户越多 → 数据越多（飞轮效应）

### 四、数据对应关系

```
产品验证          VC 增长           数据资产
─────────        ─────────        ─────────
诊断提分    ←→   NPS/口碑    ←→   学习行为序列
正确率趋势  ←→   留存率      ←→   题库质量反馈
功能渗透率  ←→   DAU/MAU     ←→   教师偏好数据
课程完成率  ←→   机构增长    ←→   知识图谱覆盖
```

同一份数据，三个维度复用。采集一次，服务三个目标。

## 架构

```
事件记录层              聚合层                  API 层              展示层
AnalyticsEvent      →  Celery 每日聚合       →  Dashboard API    →  AnalyticsPanel
record_event()         DailyPlatformStats      IsPlatformAdmin      CSV 导出
                                                                         ↓
NPS 问卷              ←  should_show_nps()   ←  NPSStatusView    ←  NPSSurvey 弹窗
NPSSurvey
```

## 数据模型

### AnalyticsEvent（事件表）

轻量级业务事件，单条 INSERT，不影响主流程性能。

| 字段 | 类型 | 说明 |
|------|------|------|
| event_type | CharField(50) | 事件类型（见下方枚举） |
| user | FK → User | 关联用户（可空） |
| institution | FK → Institution | 关联机构（可空，自动从 user 继承） |
| properties | JSONField | 事件属性 |
| created_at | DateTimeField | 发生时间 |

**事件类型：**

| event_type | 触发位置 | 说明 |
|------------|----------|------|
| `user_login` | `users/views.py` LoginView | 登录成功 |
| `diagnostic_start` | `users/views.py` DiagnosticGenerateView | 开始诊断测试 |
| `diagnostic_complete` | `users/views.py` DiagnosticSubmitView | 完成诊断测试 |
| `quiz_attempt` | `quizzes/views_exam.py` SubmitExamView | 提交答卷 |
| `ai_chat_start` | `ai_assistant/views.py` AIChatView | 发起 AI 对话 |
| `course_view` | `courses/views.py` VideoProgressUpdateView | 首次浏览课程 |
| `course_complete` | `courses/views.py` VideoProgressUpdateView | 完成课程 |
| `pdf_export` | （待接入） | PDF 导出 |
| `invite_click` | （待接入） | 邀请链接点击 |

### DailyPlatformStats（每日快照）

由 Celery 任务每日凌晨聚合写入，一条/天。

| 分类 | 字段 | 来源 |
|------|------|------|
| 用户 | total_users, new_users, dau, wau, mau | User 表 + AnalyticsEvent |
| 机构 | total_institutions, new_institutions, active_institutions | Institution 表 + AnalyticsEvent |
| 学习 | quiz_attempts, quiz_correct_rate, diagnostic_completions | QuizExam + ExamQuestionResult + AnalyticsEvent |
| AI | ai_chat_sessions, ai_calls_total | AnalyticsEvent + InstitutionUsageLog |
| 课程 | course_views, course_completions, pdf_exports | AnalyticsEvent |
| 留存 | day1_retention, day7_retention, day30_retention | AnalyticsEvent 用户登录去重 |

### NPSSurvey（NPS 问卷）

| 字段 | 说明 |
|------|------|
| user | 关联用户 |
| score | 0-10 评分 |
| feedback | 可选文字反馈 |
| source | `auto`（系统弹出）/ `manual`（主动提交） |
| created_at | 提交时间 |

**NPS 分类：** 9-10 = Promoter, 7-8 = Passive, 0-6 = Detractor
**NPS 分数：** (%Promoter - %Detractor) × 100，范围 -100 ~ +100

## API

所有接口需 `IsPlatformAdmin`（`is_superuser`）权限。

### GET /api/users/admin/analytics/dashboard/?days=30

返回平台分析 Dashboard 数据。

```json
{
  "summary": {
    "total_users": 1234,
    "total_institutions": 15,
    "dau": 89,
    "mau": 456,
    "day7_retention": 0.35
  },
  "trends": [
    {
      "date": "2026-05-28",
      "dau": 89,
      "new_users": 12,
      "new_institutions": 2,
      "quiz_attempts": 234,
      "quiz_correct_rate": 0.7234,
      "ai_chat_sessions": 45,
      "course_views": 67,
      "day1_retention": 0.45
    }
  ],
  "feature_breakdown": {
    "quiz_attempt": 1234,
    "ai_chat_start": 567,
    "course_view": 890
  },
  "institution_top": [
    {"id": 1, "name": "示例机构", "student_count": 50, "created_at": "2026-05-01"}
  ],
  "nps": {
    "score": 42,
    "total": 100,
    "distribution": {"promoters": 60, "passives": 22, "detractors": 18},
    "recent_feedback": [
      {"username": "user1", "score": 9, "feedback": "很好用", "created_at": "2026-05-28T10:00:00"}
    ]
  }
}
```

### GET /api/users/admin/analytics/export/?type=trends&days=90

导出 CSV 文件，支持三种类型：

| type | 说明 | 内容 |
|------|------|------|
| `trends` | 趋势数据 | DailyPlatformStats 全部字段 |
| `events` | 原始事件 | 最近 10000 条 AnalyticsEvent |
| `nps` | NPS 问卷 | 全部 NPSSurvey 记录 |

### POST /api/users/nps/submit/

提交 NPS 问卷（需登录）。

```json
{"score": 9, "feedback": "很好用", "source": "auto"}
```

### GET /api/users/nps/status/

检查当前用户是否需要填写 NPS。

```json
{"should_show": true}
```

## NPS 弹出规则

`should_show_nps(user)` 三个条件同时满足：

1. **注册满 7 天** — `user.date_joined` 距今 ≥ 7 天
2. **本周 ≥ 3 天活跃** — 近 7 天有 ≥ 3 天的 `user_login` 事件
3. **冷却期 ≥ 30 天** — 距上次 NPSSurvey 提交 ≥ 30 天

前端行为：
- 每次页面加载调用 `GET /nps/status/`，`sessionStorage` 去重（每会话只检查一次）
- 满足条件后延迟 3 秒弹出
- 用户可关闭，关闭后本次会话不再弹出

## 聚合任务

### Celery Task: `core.tasks.aggregate_daily_platform_stats`

- **调度：** 每日 00:00（`CELERY_BEAT_SCHEDULE`，86400s 间隔）
- **逻辑：** 聚合昨日数据写入 `DailyPlatformStats`，`update_or_create` 幂等
- **留存计算：** N 日留存 = N 天前登录用户中昨日也登录的比例

手动触发：

```bash
cd backend && python manage.py shell -c "from core.tasks import aggregate_daily_platform_stats; aggregate_daily_platform_stats()"
```

## 前端组件

### AnalyticsPanel（数据分析 Tab）

位置：`frontend/src/pages/maintenance/AnalyticsPanel.tsx`

- 汇总卡片：总用户、总机构、DAU、MAU、7日留存
- 趋势图：DAU、新增用户、学习活动、次日留存率（recharts）
- 功能分布：饼图 + 事件计数
- 机构 Top 10：按学生数排序
- NPS 卡片：NPS 分数 + 分布 + 近期反馈
- 导出按钮：趋势 / 事件 / NPS 三个 CSV 下载

### NPSSurvey（NPS 弹窗）

位置：`frontend/src/components/NPSSurvey.tsx`

- 全局挂载在 `App.tsx`
- 0-10 评分条 + 可选文字输入
- 提交后 2 秒自动关闭

## 文件清单

| 文件 | 说明 |
|------|------|
| `backend/core/models.py` | AnalyticsEvent, DailyPlatformStats, NPSSurvey |
| `backend/core/analytics.py` | record_event(), should_show_nps() |
| `backend/core/tasks.py` | aggregate_daily_platform_stats |
| `backend/core/migrations/0005_*.py` | 数据库迁移 |
| `backend/school_system/settings.py` | Celery beat schedule |
| `backend/users/views.py` | AnalyticsDashboardView, AnalyticsExportView, NPSSubmitView, NPSStatusView |
| `backend/users/urls.py` | URL 注册 |
| `backend/users/views.py` | 埋点：登录/诊断 |
| `backend/quizzes/views_exam.py` | 埋点：答题 |
| `backend/ai_assistant/views.py` | 埋点：AI 对话 |
| `backend/courses/views.py` | 埋点：课程 |
| `frontend/src/pages/maintenance/AnalyticsPanel.tsx` | Dashboard 组件 |
| `frontend/src/components/NPSSurvey.tsx` | NPS 弹窗 |
| `frontend/src/pages/Maintenance.tsx` | 新增 Tab |
| `frontend/src/App.tsx` | 全局挂载 NPS |

## 扩展

### 新增事件类型

1. 在 `AnalyticsEvent.EVENT_TYPES` 加新选项
2. 在对应 view 中调用 `record_event('new_event', user=user)`
3. 聚合任务中加对应计数逻辑（可选）

### 新增统计指标

1. 在 `DailyPlatformStats` 加字段
2. `python manage.py makemigrations core && python manage.py migrate`
3. 在 `aggregate_daily_platform_stats` 中加聚合逻辑
4. 在 `AnalyticsDashboardView.get` 中返回新字段

## VC 叙事模板

从 Dashboard 导出数据后，可直接套用以下结构：

### 一页纸数据摘要

```
UniMind 产品数据 — 截至 YYYY-MM-DD

┌─ 规模 ─────────────────────────────────────┐
│  总用户: X 人    总机构: Y 家    DAU: Z     │
│  月活(MAU): W    7日留存: N%                │
└────────────────────────────────────────────┘

┌─ 产品有效性 ───────────────────────────────┐
│  诊断后平均提分: +X.X 分 (样本: Y 人)      │
│  答题正确率趋势: 58% → 72% (30天)          │
│  AI 助教使用率: 85% 学生至少用过 1 次      │
│  课程完成率: 62%                           │
└────────────────────────────────────────────┘

┌─ 用户满意度 ───────────────────────────────┐
│  NPS: +42 (推荐 60% / 中立 22% / 贬损 18%) │
│  "诊断测试很准，帮我找到了薄弱环节"        │
│  "AI 出题省了我很多时间" — 某机构教师       │
└────────────────────────────────────────────┘

┌─ 增长 ─────────────────────────────────────┐
│  本周新增机构: X 家  (环比 +Y%)            │
│  机构续用率: Z%                            │
│  学生周活跃增长: +N%                       │
└────────────────────────────────────────────┘
```

### 讲故事的顺序

1. **痛点** → 传统教育机构缺乏数据驱动的学情分析
2. **解法** → UniMind = AI 诊断 + 自适应刷题 + 智能出题
3. **证据** → 数据摘要（上述四个模块）
4. **飞轮** → 数据越多模型越准 → 体验越好 → 用户越多
5. **下一步** → 扩大机构覆盖，打磨核心指标，准备下一轮

## 数据合规

- 学生数据**仅用于聚合统计**，不暴露个人行为给机构以外的任何人
- NPS 反馈在 Dashboard 展示时**脱敏显示用户名**
- CSV 导出**仅超管可操作**，导出内容不含密码/Token 等敏感字段
- `AnalyticsEvent` 中 `user` 字段为 `SET_NULL`，用户注销后事件保留但不关联个人
- 建议在用户协议中加入"平台数据用于产品改进"条款
