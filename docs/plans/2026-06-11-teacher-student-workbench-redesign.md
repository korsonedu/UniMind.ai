# UniMind 教师端 & 学生端重设计方案

> 2026-06-12 | 对答论证结论

## 核心定位

UniMind = 教育机构基础设施。客户是机构和教师，不是学生。

## 设计原则

- Agent-native：Agent 是唯一界面，不是功能之一
- 事驱动：打开看到待处理的事，不是数据看板
- 套件化：Sidebar 是业务工具箱，不是功能导航
- 浏览和对话并存：内容资产的浏览视图（快）+ Agent 对话决策（深）
- 教师端 Agent 不拟人化，学生端保留"小宇"名字

---

## 一、整体架构

### 教师端 6 套件

```
┌─ Sidebar ─────┐  ┌─ 主区域 ────────────────────────────┐
│               │  │                                      │
│ 💬 AI         │  │ Agent 时间线（首页）                 │
│               │  │ 主动推送 + 对话 + 结构化卡片         │
│ 📚 课程       │  │ 列表 CRUD + AI 按钮                  │
│               │  │                                      │
│ 📝 题库       │  │ 列表 CRUD + 手动出题 + AI 出题       │
│               │  │                                      │
│ 📄 文章       │  │ 列表 CRUD + AI 按钮                  │
│               │  │                                      │
│ 💬 答疑       │  │ 待回答队列（保持现状），手动回复     │
│               │  │                                      │
│ 👥 学员       │  │ 花名册 + 侧拉详情 + AI 按钮          │
└───────────────┘  └──────────────────────────────────────┘
```

Agent 需覆盖的 5 件事：内容管理、作业布置、数据分析、行动执行、答疑。

### 学生端 6 套件

```
┌─ Sidebar ─────┐  ┌─ 主区域 ────────────────────────────┐
│               │  │                                      │
│ 💬 小宇       │  │ Agent 时间线（首页）                 │
│               │  │ 主动推送 + 对话 + 结构化卡片         │
│ 🏆 刷题       │  │ 统一练习入口                         │
│               │  │ 上半：教师/小宇推的题                │
│               │  │ 下半：自由练习（选知识点/难度/数量） │
│ 📚 课程       │  │ 视频卡片网格（保持现状）             │
│               │  │                                      │
│ 📄 文章       │  │ 文章列表（保持现状）                  │
│               │  │                                      │
│ 💬 答疑       │  │ 对老师的问答（保持现状）             │
│               │  │                                      │
│ 🎯 自习室     │  │ 番茄钟+在线同学（保持现状）          │
└───────────────┘  └──────────────────────────────────────┘
```

刷题套件 = 所有练习的唯一入口。小宇推荐 → 刷题套件打开；教师布置 → 刷题套件打开；自己主动练 → 刷题套件打开。统一界面。

### 两端对比

| 能力 | 教师端 | 学生端 |
|------|--------|--------|
| Agent 首页 | AI | 小宇 |
| 内容资产 | 课程、题库、文章 | 课程、文章 |
| 练习 | — | 刷题 |
| 沟通 | 答疑 | 答疑 |
| 管理 | 学员 | — |
| 学习 | — | 自习室 |

---

## 二、Agent 时间线 UI

当前 AgentChatLayout 是纯对话（用户说→AI回）。改为时间线模式。

### 核心理念

- **时间线式，不是聊天式。** Agent 可以不等用户说话就推消息。用户操作（点按钮、选卡片）作为消息节点出现在时间线里。
- **主动推送（重度）。** 打开时 Agent 已经推送待关注事项，之后持续推送新事件。
- **结构化卡片。** 三种类型：
  - **数据卡**：展示信息 + 操作按钮（作业进度、学生数据、班级趋势）
  - **决策卡**：两个按钮的选择（"要不要做X？"）
  - **内容卡**：可交互的富内容（题目列表可编辑、课程列表可搜索）
- **卡片上的按钮执行在时间线里展开结果。** 不跳页面、不弹对话框。
- **底部保留输入框。** 随时可以打字，也可以只点卡片交互。

### 示例（教师端）

```
┌─ Agent 时间线 ──────────────────────────────────────────┐
│  ── 今天 09:30 ──                                       │
│  ┌──────────────────────────────────────────────────┐   │
│  │ AI                                              │   │
│  │ 早上好。金融1班的货币政策练习还有5人没交，       │   │
│  │ 明天截止。                                       │   │
│  │                                                  │   │
│  │ ┌─ 作业进度卡 ──────────────────────────────┐   │   │
│  │ │ 货币政策练习 · 单选题 20道                  │   │   │
│  │ │ 已提交 19/24  待批改 3                      │   │   │
│  │ │ [查看详情] [催交]                          │   │   │
│  │ └──────────────────────────────────────────┘   │   │
│  └──────────────────────────────────────────────────┘   │
│                                                          │
│  ── 09:35 ──                                            │
│  ┌──────────────────────────────────────────────────┐   │
│  │ AI                                              │   │
│  │ 李四这周活跃掉了70%，货币政策正确率只有42%。     │   │
│  │ 要不要看一下？                                   │   │
│  │                                                  │   │
│  │ [看一下] [忽略]                                  │   │
│  └──────────────────────────────────────────────────┘   │
│                                                          │
│  ── 09:36 ──                                            │
│  ┌──────────────────────────────────────────────────┐   │
│  │ 你                                              │   │
│  │ [点击了"看一下"]                                 │   │
│  └──────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────┐   │
│  │ AI                                              │   │
│  │ ┌─ 李四 学习数据卡 ────────────────────────┐    │   │
│  │ │ 本周活跃 1天 │ ELO 980 │ 薄弱: 货币政策   │    │   │
│  │ │ 最近5次正确率: 42% 55% 38% 60% 45%       │    │   │
│  │ │ [生成针对性练习] [推送提醒] [查看详细]   │    │   │
│  │ └──────────────────────────────────────────┘    │   │
│  └──────────────────────────────────────────────────┘   │
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │ [输入框]                              [发送 ▶]  │   │
│  └──────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────┘
```

---

## 三、Sidebar 设计

### 改为纯图标套件

- 6 个平级图标，无文字标签，不可折叠
- 不需要层级导航——没有子菜单
- 默认选中第一个（教师端 AI / 学生端 小宇）
- 不再有功能门控——6 个套件永远完整可见
- 头像在 sidebar 底部，点击弹出菜单

### 顶栏

```
┌─ 顶栏 ──────────────────────────────────────────────────┐
│  [📢 广播(管理员可见)]  [🔔 通知]  [👤 头像 ▾]          │
└──────────────────────────────────────────────────────────┘
```

### 头像菜单

| 功能 | 说明 |
|------|------|
| 机构设置 | 名称、Logo、学科方向 |
| 方案与账单 | 当前方案、升级、支付历史 |
| 教师管理 | 邀请/移除/权限分配 |
| 邀请学生 | 复制邀请链接 |
| 切换到学生视角 | 预览学生端 |
| AI 设置 | Bot 参数、ARC 管线配置 |
| 偏好 | 主题色等 |
| 安全 | 审计日志（仅管理员） |
| 退出登录 | — |

不放头像菜单的：
- 站内广播 → 顶栏独立 icon（仅管理员可见）
- 数据/洞察 → 进 Agent 时间线卡片
- 标签管理 → 进各套件内编辑流

---

## 四、权限体系

### 原则

- **套件永远完整可见，不锁套件。**
- **限制在具体能力和用量。**

### 能力限制矩阵

| 限制维度 | Free | Starter | Growth | Enterprise |
|---------|------|---------|--------|------------|
| AI 出题/月 | 30 | 100 | 无限 | 无限 |
| ARC 精修 | ✗ | ✗ | ✓ | ✓ |
| 学员数上限 | 30 | 50 | 200 | 无限 |
| 课程数 | 5 | 30 | 100 | 无限 |
| 题目库存量 | 200 | 2,000 | 10,000 | 无限 |
| 文章数 | 5 | 20 | 100 | 无限 |
| 知识库 KB | 300 | 1,000 | 5,000 | 无限 |
| AI 主动推送 | ✗ | ✗ | ✓ | ✓ |
| 答疑（人工） | ✓ | ✓ | ✓ | ✓ |
| 数据看板（Agent内） | 基础 | 基础 | 完整 | 完整 |
| 班级数 | 1 | 3 | 10 | 无限 |
| 教师数 | 1 | 2 | 5 | 无限 |
| AI 对话/月 | 100 | 500 | 3,000 | 无限 |
| PDF 导出/月 | 0 | 10 | 100 | 无限 |
| 面试/月 | 0 | 10 | 50 | 无限 |
| 自定义 Bot | 0 | 3 | 10 | 无限 |
| 存储 | 500MB | 5GB | 50GB | 无限 |

### 超限行为

套件内操作按钮置灰 + tooltip："已达上限，升级方案获取更多"。
**不出现锁页面、锁套件、锁 sidebar 项。**

---

## 五、数据模型变更

### Class 模型（新增）

```python
class Class(models.Model):
    institution = FK(Institution, related_name='classes')
    name = CharField(max_length=200)
    created_at = DateTimeField(auto_now_add=True)
    students = ManyToManyField(User, related_name='classes')
```

### Assignment 模型（新增，替代 TeacherExam）

```python
class Assignment(models.Model):
    STATUS = (('draft','草稿'), ('published','已发布'), ('closed','已关闭'))
    title = CharField(max_length=500)
    description = TextField(blank=True)
    institution = FK(Institution)
    created_by = FK(User)
    target_classes = ManyToManyField(Class)
    due_date = DateTimeField(null=True)
    status = CharField(choices=STATUS, default='draft')
    created_at = DateTimeField(auto_now_add=True)

class AssignmentQuestion(models.Model):
    assignment = FK(Assignment, related_name='assignment_questions')
    question = FK(Question)
    order = IntegerField(default=0)
    points = IntegerField(default=1)

class AssignmentSubmission(models.Model):
    assignment = FK(Assignment)
    student = FK(User)
    submitted_at = DateTimeField(auto_now_add=True)
    answers = JSONField()
    score = FloatField(null=True)
    graded_by = FK(User, null=True)
    graded_at = DateTimeField(null=True)
```

TeacherExam 标记为 deprecated，数据迁移到 Assignment。PDF 作业作为特殊题型处理。

---

## 六、Agent 工具变更

### 教师端 Agent 工具 5→12

**保留：**
- `search_knowledge` — 搜索知识树
- `quick_generate` — 快速出题
- `launch_arc_pipeline` — ARC 精修管线
- `check_pipeline_status` — 查管线状态
- `get_workbench_stats` — 工作台统计

**新增数据类：**
- `get_student_detail` — 个体统计（正确率、活跃度、薄弱点、ELO 趋势）
- `get_class_performance` — 班级薄弱点、正确率趋势
- `get_assignment_progress` — 作业提交/批改进度

**新增行动类：**
- `assign_practice` — 推练习给学生（创建 Assignment）
- `send_notification` — 发提醒通知
- `generate_study_plan` — 生成学习计划

**新增内容类：**
- `list_courses` — 浏览课程库
- `list_articles` — 浏览文章库
- `list_questions` — 浏览题库

### 学生端小宇

保持现有 17 工具不变。新增和教师端 Agent 的互通能力。

---

## 七、Agent 互通机制

通过通知系统 + Agent 事件回调：

| 场景 | 方向 | 内容 |
|------|------|------|
| 答疑升级 | 小宇→教师Agent | 学生问题 + 上下文 + 初步判断 |
| 教师布置作业 | 教师Agent→小宇 | 新作业通知 → 小宇推给学生 |
| 学生完成作业 | 小宇→教师Agent | 提交结果 → 推送教师审批阅 |
| 薄弱点变化 | 小宇→教师Agent | 教师可在学员套件查看更新 |

基础设施：通知系统现有功能 + Agent 事件回调，不需要新的中间件。

---

## 八、改造范围

### 新建

无。在现有路由和组件上重构。

### 删除

- `/management` (Maintenance.tsx)
- `/institution` (InstitutionDashboard.tsx)
- `/home` (StudentHome.tsx)
- `/knowledge-map` + `/node/:id`
- `/plan` (StudyPlan.tsx)
- `/mock-exam` (PdfMockExam.tsx)
- `/tests/review` (WrongQuestionReviewPage.tsx)

### 重写

- `/workbench` — 聊天 UI → Agent 时间线
- `/xiaoyu` — 聊天 UI → Agent 时间线
- `/tests` — 刷题套件（推题+自由练+错题本）
- `/institution/students` — 学员套件
- `MainLayout.tsx` — Sidebar 套件图标
- `AgentChatLayout.tsx` — Agent 时间线组件
- 后端 Agent 工具定义 — 5→12

### 保留

- `/courses` `/course/:id` `/articles` `/article/:id` `/qa` `/study`
- `/tests/session` (统一练习界面)
- `/settings` `/billing` `/system-settings` (进头像菜单)
- `/institution/admin` `/invite-codes` `/platform-analytics` (超级管理员)

### 新增数据模型

- `Class` — Institution 下分组
- `Assignment` + `AssignmentQuestion` + `AssignmentSubmission` — 作业系统
- 通知触发器 — 作业布置/批改→自动通知

---

## 九、改造优先级

### Phase 1：模型 + 基础设施（后端，不影响前端）
1. 新增 Class 模型 → migration
2. 新增 Assignment 模型（替代 TeacherExam）→ migration
3. 教师端 Agent 工具扩展 5→12
4. 通知触发器（作业布置/批改→自动通知）
5. Agent 互通（小宇↔教师 Agent 事件回调）

### Phase 2：教师端重写（客户侧优先）
1. Sidebar 重构（MainLayout 套件图标）
2. Agent 时间线（重写 /workbench）
3. 课程/题库/文章/答疑/学员套件
4. 头像菜单收容低频功能
5. Agent 主动推送逻辑
6. 跑通完整教师流程：出题→布置→看提交→批改→看数据

### Phase 3：学生端重写
1. Agent 时间线（重写 /xiaoyu）
2. 刷题套件统一入口
3. 合并待办+错题本+模拟考
4. 删除旧页面（StudentHome、KnowledgeMap 等）
5. Agent 互通联调

---

## 十、产品叙事

- 教师打开 UniMind → 全屏 Agent 时间线 → AI 已经在推送今天要关注的事
- 学生打开 UniMind → 全屏 Agent 时间线 → 小宇已经在推送今天该做的任务
- Sidebar = 工具箱，只在需要浏览/管理内容资产时使用
- 教师端 Agent 不拟人化，学生端保留小宇的名字和温度
