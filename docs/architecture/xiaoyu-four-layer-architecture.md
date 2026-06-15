# 小宇四层架构设计 v3

> 状态：Phase 1/3/4 完成 | 日期：2026-06-10
> 用途：开发参考。定义四层边界、模块、接口、隔离性。

## 四层总览

```
┌──────────────────────────────────────┐
│   第四层：测评引擎                     │
│   评分 · 错因分析 · 变式题匹配          │
├──────────────────────────────────────┤
│   第三层：教育能力闭环                  │
│   教 · 练 · 测 · 评                   │
│   通过 MemorySystem 获取数据           │
├──────────────────────────────────────┤
│   第二层：记忆系统                     │
│   ┌────────────────────────────┐     │
│   │ 查询接口层 (v3)              │     │
│   ├────────────────────────────┤     │
│   │ 存储引擎 + Memorix 调度引擎  │     │
│   └────────────────────────────┘     │
├──────────────────────────────────────┤
│   第一层：基础框架                     │
│   对话引擎 · Bot 运行时 · 工具系统      │
└──────────────────────────────────────┘
```

**核心原则：Memorix 是闭环的节拍器。** 不做"立刻纠错"，错题按间隔重复节奏自然出现。测评引擎负责诊断，Memorix 负责调度。

---

## 第一层：基础框架

对话生命周期、Bot 运行时、工具系统基础设施。不包含教育业务逻辑。

| 模块 | 代码位置 |
|------|---------|
| 对话引擎 | `chat_dispatch.py` |
| Bot 运行时 | `bot_registry.py` |
| 工具基类 | `tool_executor.py::BaseToolExecutor` |
| 工具注册 + 权限 | `ai_engine/tools/` + `tool_permissions.py` |
| 意图路由 | BotProfile (`use_intent_router`) |
| 模型路由 | `ai_engine/config.py` |
| 传输层 | `consumers.py` (WS) + views (SSE/polling) |

**对外接口：** `dispatch(user, bot, message, history, institution) → (result, steps)`

**约束：** 不操作数据库。新增 Bot：写 prompt → 注册 BotProfile → 选填 ToolExecutor。

### 调度执行器

Memorix 计算了 `next_review_at`，但基础框架层需要一个组件在那个时间点执行动作——学生不来，时钟不能停。

**调度执行器**（基础框架层新增，Phase 4+）：
- 定时轮询 `MemorySystem.query.due_count(user)` → 如果到期题目超过阈值，通过飞书/邮件/小程序推送通知
- 只消费 `due_count`，不操作 stability/difficulty——不与 Memorix 耦合
- 通知内容："你有 5 道题到期了，三角函数正确率 60% → 现在复习"

**设计原则：** 调度执行器不决定"什么时间"——那是 Memorix 的事。它只负责"在那个时间点拉回学生"。

### 多 Agent 运行时

当前注册两个 Agent，共享同一四层基础设施：

| Agent | bot_type | 工具数 | 工具集 | 职责 |
|-------|----------|--------|--------|------|
| 小宇 | `planner` | 17 | `get_planner_tools()` | 学生端：学习规划 + 知识讲解 + 数据分析 + 教练式对话 |
| 命题官 | `exam_generator` | 5 专用 | `get_exam_generator_tools()` | 教师端：快速出题(Author单步) + ARC精修(异步管线) + 题库统计 |

**共享与隔离：**
- 共享：基础框架（对话引擎、Bot运行时、模型路由）+ 记忆系统（机构级数据隔离）
- 隔离：各自的 ToolExecutor 子类 + 独立的工具权限白名单 + 独立的 prompt 目录
- 协作：命题官出题写入题库 → 小宇从同一题库抽题 → 测评引擎评分 → 结果写入共享的 Memorix

新增 Agent 注册到 `BOT_REGISTRY` 后自动继承四层能力，通过 `tool_permissions.py` 控制工具访问边界。

---

## 第二层：记忆系统

教育闭环的数据中枢。所有数据查询和写入必须经过这里。

### Memorix 调度引擎

```
UserQuestionStatus:
  stability          → 决定下次间隔
  difficulty         → 影响稳定度增长
  reps / lapses      → 累积指标
  next_review_at     → 调度输出

Phase 1 新增:
  error_type         → concept_error / calculation_error / careless_mistake
  error_metadata     → {reasoning, suggested_focus}
```

错题处理：lapse → stability 减半 → 间隔重置为 1 天。已在现有代码中运行，Phase 1 只加字段。

### 查询接口层（Phase 4 实现）

```
MemorySystem
├── query.user_profile(user)           → UserProfile
├── query.weak_points(user, limit=5)   → [WeakPoint]
├── query.mastery_map(user, subject?)  → MasteryMap
├── query.due_reviews(user, limit=20)  → [DueReview]
├── query.learning_stats(user)         → LearningStats
├── query.difficulty_analysis(user)    → [KPDifficulty]
├── write.error_analysis(user, qid, a) → void
├── write.memorix_update(user, qid, r) → void
└── build_context(user, message)       → MemoryContext
```

Phase 1 中 handler 可直接操作 model（最小改动），Phase 4 切换为接口调用。

### 自适应 Prompt 系统

记忆系统不只是存储，它还动态影响 Agent 的行为。每次对话前，系统构建双层上下文注入 system prompt：

**记忆注入：**
```
build_context(user, message) → {
    memory_context:      结构化记忆（key-value，按 confidence 排序，800 字符上限）
                       + 语义记忆（mem0 向量检索，与当前消息相关的记忆）
    adaptive_directives: LLM 分析用户画像后生成的自适应指令
}
```

**用户画像分析（memory_analyzer.py）：**
- LLM 从记忆中提取 6 维画像：学习风格（formula/visual/example/memorization/balanced）、回复长度偏好、交互风格（deep_questioner/critical/passive）、认知状态（focused/anxious/overwhelmed/motivated）、领域专业度（beginner/intermediate/advanced）、置信度
- 置信度 ≥ 0.6 的画像写入 Redis 缓存（24h TTL），减少重复 LLM 调用
- 画像分析失败时 fallback 到规则匹配（关键词检测）

**自适应指令生成（prompt_adapter.py）：**
- 将画像转换为自然语言指令注入 system prompt
- 例："该学生偏好公式推导。回答时优先展示数学表达。"
- 例："该学生当前处于焦虑状态。先共情，再给可立即执行的小步骤。"

**调用链：** `chat_dispatch` → `build_memory_context()` → `get_adaptive_directives_llm()`（LLM 分析 + 规则 fallback）→ 注入 system prompt。

---

## 第三层：教育能力闭环

教→练→测→评。练包含 Memorix 到期复习，"纠"由间隔重复消解。

| 环节 | 工具 | 数据来源 |
|------|------|---------|
| 教 | 知识树搜索、课程推荐、ASR 定位、文章搜索 | 应用库 |
| 练 | 主动抽题、Memorix 到期复习、错题回顾 | MemorySystem.query |
| 测 | 考试记录、诊断测试（`run_diagnostic`） | quizzes app |
| 评 | 学习统计、掌握图谱、薄弱点、Memorix 分析 | MemorySystem.query |
| 计划 | StudyPlan CRUD | StudyPlan 表 |
| 可视化 | render_visual | LLM 输出 |

### 闭环

```
练(抽题或到期复习) → 答题
  → 测评引擎: 评分 + 错因分析
    → 记忆系统: write.error_analysis + write.memorix_update
      → Memorix 调度 next_review_at
        → [到期] query.due_reviews → 错题 + 标签
          → 学生复习 → 循环
```

### 对话自适应

小宇不使用模式切换按钮。Agent 根据学生的提问自然调整行为：

- 学生问"这道题怎么做" → 简短解答，必要时调 `lookup_question`
- 学生说"帮我系统讲一下三角函数" → 展开推导，调知识树，出 `render_visual`
- 学生说"来一场模拟考试" → 进入全屏做题页（`/xiaoyu/practice/:sessionId`），计时+统一提交

全屏做题不是"模式"，是学生明确触发的一个动作——和点击练习卡片进入全屏做题是同一逻辑。小宇的 system prompt 不需要模式指令块。

### 自进化（Phase 7）

Trajectory 记录每轮对话的工具调用序列、用户反馈和任务完成度，Celery 异步写入 `AITrajectory` 表。MUTAR 自进化管线（Generate → Evaluate → Polish → Adapt）目前处于数据收集阶段，目标是通过分析 Trajectory 数据自动优化 prompt 模板和 Memorix 参数。Phase 7 前标记为数据收集。

### 教师端闭环（命题官）

命题官是教师/机构主的专属 Agent，闭环与学生端不同：产出不是练习，是题目。

| 环节 | 工具 | 说明 |
|------|------|------|
| **出题** | `quick_generate`（Author 单步） | 按知识点+题型+难度一键生成 |
| **精修** | `launch_arc_pipeline` → `check_pipeline_status`（异步） | ARC 对抗出题管线：多模型互审→校准→差分 |
| **发布** | 对话中嵌入题目预览卡片 → 教师确认 → 写入题库 | 发布后小宇可抽取 |
| **分析** | `get_workbench_stats` + `get_class_weak_points` + `get_class_performance_summary` | 班级表现概览、薄弱点分布 |

命题官的工具权限与学生端隔离：教师不能调用 `grade_student_answer`（那是学生端的），学生不能调用 `quick_generate`（那是教师端的）。权限由 `tool_permissions.py` 按 `bot_type` 强制执行。

命题官与学生端共享同一个题库、同一个 Memorix 调度（教师可以看到班级的薄弱点分布，但无法直接修改学生的 `next_review_at`——只能通过出题影响"可用的题目池"）。

---

## 第四层：测评引擎

评分 + 错因分析 + 变式题匹配。一次调用完成诊断链。

```
grade(question, student_answer) → {
    score, max_score, is_correct, feedback, analysis

    error_analysis: {
        type: "concept_error" | "calculation_error" | "careless_mistake",
        reasoning, suggested_focus, confidence
    }

    remediation_questions: [...]    // Phase 1.5
    kp_breakdown: [...]              // Phase 2
}
```

测评演进路径：CTT（评分）→ 错因分类（Phase 1）→ IRT 知识建模（Phase 2+）→ CDM 认知诊断（Phase 5+）。当前在 Level 1→2。

---

## 隔离性审查

```
层 → 层              调用点                        当前    目标
═══════════════════════════════════════════════════════════
基础框架 → 记忆系统    build_memory_context()        ✅     —
基础框架 → 教育闭环    create_tool_executor()        ✅     —
基础框架 → 测评引擎    (不直接调用)                   ✅     —

教育闭环 → 记忆系统    get_learning_stats            ✅     MemorySystem.query
                       get_knowledge_mastery_map     ✅     MemorySystem.query
                       get_user_weak_points          ✅     MemorySystem.query
                       get_due_reviews               ✅     MemorySystem.query
                       get_knowledge_difficulty      ✅     MemorySystem.query

教育闭环 → 测评引擎    grade_student_answer           ✅     GradingEngine.grade()
测评引擎 → 记忆系统    (handler 直接写 model)         ✅     MemorySystem.write
═══════════════════════════════════════════════════════════
```

**现状：** Phase 4 已完成——所有 handler 通过 MemorySystem 接口层调用，零直接 quizzes.models import。

---

## 多租户与机构隔离

UniMind 按机构（institution）进行数据隔离。机构模型贯穿四层：

**记忆系统层：** 所有数据查询以 `institution` 参数过滤。`UserQuestionStatus`、`KnowledgePoint`、`ReviewLog` 等模型通过 `Q(institution=X) | Q(institution__isnull=True)` 实现机构隔离——机构用户只能看到本机构或公共数据。mem0 语义记忆按 `institution_id` 分租户（`TenantMemoryManager`），每个机构独立的向量索引。

**教育闭环层：** 工具执行器构造时注入 `self.institution`，所有查询自动带机构过滤。班级分析工具（`get_class_weak_points`、`get_class_performance_summary`）额外校验用户角色——仅 `teacher` 和 `owner` 可调用。

**测评引擎层：** 评分不依赖机构上下文（题目和答案是机构无关的），但评分结果写入时自动关联用户所属机构。

**基础框架层：** 机构信息从用户 session 中提取，注入 dispatch 调用链。新增 Bot 时可设为 `is_exclusive`——独占型 Bot（如小宇）注入学生学术数据，非独占型 Bot（如命题官）不注入。

**机构管理：** 机构创建、成员邀请（`/join/:invite_slug`）、角色分配（owner/teacher/student）由 `users` app 处理。机构主可自定义 Bot 人格（`institution_personality`），覆盖默认 system prompt。

---

## 异步任务系统

Celery 异步任务编排贯穿四层，处理非实时计算：

| 任务 | 所属层 | 触发时机 | 实现 |
|------|--------|---------|------|
| 记忆提取 | 记忆系统 | 对话结束后 | `_extract_memories_worker`（后台线程 + LLM） |
| 用户画像预计算 | 记忆系统 | 记忆更新后 | `precompute_user_profile`（Celery task） |
| Trajectory 记录 | 记忆系统 | 每次对话完成 | `record_trajectory_async`（Celery task，为 MUTAR 自进化准备数据） |
| ARC 出题管线 | 教育闭环(教师端) | 教师确认后 | `launch_arc_pipeline` → 多模型互审 → 校准 → 差分（多步 Celery chain） |
| Phase 1 错题预批改 | 测评引擎 | 每道题完成后 | Celery task 异步批改，结果写 Redis，提交时聚合 |

**设计原则：** 所有耗时超过 2 秒的操作必须走 Celery。对话主路径（dispatch → LLM → tool calls → response）保持同步，但工具内部的副作用（记忆提取、轨迹记录、预批改）异步化。

---

## 安全模型

**工具权限白名单：** `BaseToolExecutor.__call__` 在执行任何工具前校验 `tool_name` 是否在 `_allowed_tool_names` 白名单中。白名单由 `tool_permissions.py::filter_tools()` 根据 `bot_type` 和 `institution` 动态生成。LLM 即使被 prompt injection 诱导调用越权工具，也会在 executor 层被拦截。

**API 认证：** REST API 使用 `CookieTokenAuthentication`（httpOnly cookie 优先，fallback Authorization header）。WebSocket 在 connect 时验证，未认证立即 close（code 4001）。前端不存储 token 到 localStorage。

**敏感字段加密：** 支付密钥等使用 `EncryptedCharField` / `EncryptedTextField`（Fernet AES 对称加密）。加密密钥通过 `ENCRYPTION_KEY` 环境变量注入。

**跨层数据保护：** MemorySystem 查询接口层（Phase 4）是核心安全边界——上层无法绕过接口直接操作数据库，杜绝 handler 越权修改 Memorix 调度参数。

**机构间数据隔离：** 所有数据查询在 ORM 层强制机构过滤（见"多租户"章节），不存在跨机构数据泄露路径。

---

## 架构中的学习阶段

Memorix 的核心能力——按 stability 计算最优间隔——依赖使用过程中积累的数据。新用户没有 UserQuestionStatus，stability 和 difficulty 均为 null。这不是架构失效，是学习过程的自然起点。

新用户前几天的学习由诊断测试提供初始方向，由固定间隔（1-3-7-14-30 天）驱动题目调度。随着答题数据积累，stability 开始收敛，Memorix 的自适应调度自然激活。同一学生在固定间隔阶段的 stability 增长斜率与 Memorix 激活后的斜率对比，就是 Memorix 增量价值的 within-subject 数据来源。

架构不需要为"新用户没数据"定义特殊的 Warming 状态——因为从没有数据到有数据就是 Memorix 设计的一部分。第一天不精准，第 30 天精准，这是正常的。

---

## 能力层级与商业化边界

四层架构定义的是能力全集。商业化需要按能力层级分层，而非按使用次数：

| 层级 | 调度 | 测评 | 记忆 | 目标用户 |
|------|------|------|------|---------|
| **免费** | 固定间隔 (1-3-7-14-30) | CTT 评分 + 反馈 | 单 session 上下文 | 个人学习者 |
| **付费** | Memorix 自适应 stability | + 错因分类 + IRT 知识建模 | + 跨 session 长期记忆 + 用户画像 | 机构 / 重度用户 |

分层的技术实现：`MemorySystem` 接口不区分层级（`query.due_reviews(user)` 对所有人一样），但接口内部根据 `user.membership_tier` 选择调度算法实现（固定间隔 vs Memorix 自适应）。测评引擎的 `grade()` 同理——免费版只返回 `{score, feedback}`，付费版追加 `{error_analysis, kp_breakdown}`。

**设计原则：** 分层不是"砍免费版的功能"，是"付费版在数据积累后解锁更精准的能力"。免费用户的学习体验不因分层而受损——固定间隔本身就是新用户前几天的调度方式。

---

## 落地 Roadmap

| Phase | 内容 | 状态 |
|-------|------|------|
| Phase 0 | 架构文档 v3 | ✅ |
| Phase 1 | 测评引擎：错因分析 + Memorix 字段扩展 | ✅ 2026-06-10 |
| Phase 2 | 测评引擎独立化 + 评分记录 | 📋 |
| Phase 3 | 记忆系统：mem0 + 画像持久化 | ✅ 2026-06-10 |
| Phase 4 | MemorySystem 查询接口层 | ✅ 2026-06-10 |
| Phase 5 | API 化 | 📋 |
| Phase 6 | IRT / CDM 认知诊断升级 | 📋 |

## 新增 Agent 规则

1. 写 prompt 到 `prompts/ai_assistant/bots/{name}/`
2. 在 `bot_registry.py` 注册
3. 继承 `PlannerToolExecutor` 复用全部教育工具
4. 自动继承四层能力

---

## Agent 为入口的 SaaS

四层架构支撑 Agent 运行。前端采用"Agent 为入口，SaaS 为画布"的定位：

**学生端：** 登录默认进入小宇对话页（`/xiaoyu`）。对话流为主界面，内联卡片承载练习推送、批改结果、数据可视化。Dashboard 不是独立页面——它是 Agent 对话中的数据可视化能力。学生问"我的学习情况"→ 小宇调用 `render_visual(data_card, knowledge_map)` 在对话流中展示。

**新用户路由：** 新学生首次登录进入 `/xiaoyu`，小宇主动问候并引导诊断测试。诊断面板在对话流中自动展开（不跳转独立页面），确保 Agent 是第一个接触点。侧边栏收纳的功能模块（刷题、错题本、知识图谱、课程、模拟考试、数据分析）是同一能力的快捷入口，通过 Agent 对话唤起。

**侧边栏：** 可手动唤起/收起，不绑定模式。功能模块通过侧边栏快捷入口触发 → Agent 对话唤起 → 内联渲染。

### SaaS 模块：Agent 工具的 UI 快捷入口

侧边栏中的功能模块（刷题、错题本、知识图谱、课程、模拟考试、数据分析）不引入新架构层。它们是教育闭环层已有工具的 UI 快捷方式——点击按钮等同于对小宇说出对应指令：

| 模块 | 等同于对小宇说 | 实际工具调用 | 渲染方式 |
|------|-------------|------------|---------|
| 刷题 | "帮我抽题" | `get_practice_questions` | 对话流中题目卡片 → 点击进入全屏做题 |
| 错题本 | "看看错题" | `get_user_wrong_questions` | 对话流中错题列表面板 |
| 知识图谱 | "知识图谱" | `get_knowledge_mastery_map` | `render_visual(knowledge_map)` 对话流内联 |
| 课程 | "推荐课程" | `search_courses` | 对话流中课程卡片 → 点击进入全屏播放 |
| 模拟考试 | "模拟考试" | 全屏做题 + 计时 + `grade` | `/xiaoyu/practice/:sessionId` 独立路由 |
| 数据分析 | "分析数据" | `get_learning_stats` | `render_visual(data_card)` 对话流内联 |

**默认走 Agent 对话唤起，内联渲染。** 课程视频（需全屏播放器）和模拟考试（需全屏专注+计时）例外——卡片点击后进入独立路由，完成后回到对话流。

**教师端：** 登录默认进入命题官对话页（`/workbench`）。出题预览卡片嵌入对话流，班级数据看板按需唤起。

### 落地页：Agent 主动开口

小宇的落地页不是空白输入框——学生登录后，小宇已经在说话了。落地页的默认状态是一段基于记忆系统生成的个性化开场白：

- **有历史数据的学生：** "上次三角函数正确率从 40% 升到 65%，今天继续？你有 3 道到期复习题。"——引用记忆系统的学习统计和 Memorix 到期计数。
- **新学生：** "你好，我是小宇。先做个诊断测试？5 分钟，帮我了解你的强项和薄弱点。"——引导冷启动流程。

落地页不展示历史对话列表。历史对话收纳在侧边栏或底部链接中，主区域只保留小宇的开场白和输入框。视觉重心在小宇的话上，不是在"我该输入什么"上。

### 移动端适配

四层架构的前端形态天然适配移动端。单栏对话流不需要重新布局——全屏做题页独立路由、对话流卡片内联、无 split-view 无拖拽面板。移动端的差异仅在交互层面：左右滑动手势切题（桌面端：键盘快捷键 + 按钮），卡片全屏展开使用原生转场动画。

**详见：** `docs/architecture/xiaoyu-frontend-form.md`
