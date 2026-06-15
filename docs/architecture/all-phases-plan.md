# UniMind 全部 Phase 实施计划

> 日期：2026-06-06
> 架构基础：四层架构设计 v3

---

## Phase 0：架构文档 ✅
- 内容：四层架构定义 + 隔离性审查 + 多Agent + 多租户 + 安全 + 商业化
- 状态：已完成

---

## Phase 1：测评引擎 — 错因分析 + Memorix 字段扩展 🔜

**目标：** 评分同时输出错因，错因持久化到 Memorix，复习时引用。

| # | 改动 | 文件 |
|---|------|------|
| 1 | grade_question prompt 扩展（追加 error_analysis 输出） | `prompts/grading/` |
| 2 | UserQuestionStatus 加 `error_type` + `error_metadata` | `quizzes/models.py` + migration |
| 3 | _handle_grade_student_answer 写入错因 | `tool_executor.py` |
| 4 | _handle_get_due_reviews 附带 error_type | `tool_executor.py` |

**不改：** Memorix 调度逻辑（lapse 已自动缩短间隔），不新建 service。

**详见：** `docs/architecture/phase1-grading-upgrade-plan.md`

---

## Phase 2：测评引擎独立化 + 评分记录

**目标：** 测评引擎从 tool_executor 中抽离为独立 GradingEngine，建立评分记录表。

| # | 改动 | 说明 |
|---|------|------|
| 1 | 新建 `GradingEngine` service | 封装 grade_question + ErrorClassifier，独立于 PlannerToolExecutor |
| 2 | 新建 `GradingRecord` 模型 | 记录每次评分的 score / error_analysis / kp_breakdown / graded_at |
| 3 | _handle_grade_student_answer 改为调 GradingEngine | tool_executor 只做路由，不做评分逻辑 |
| 4 | GradingRecord 写入 Celery 异步 | 评分记录不阻塞对话主路径 |
| 5 | 加分阶段摘要 API | `GET /api/grading/history/?user=...&kp=...`，供 Dashboard 和数据分析使用 |

**验证：** 评分结果写入 GradingRecord 表；现有 grade_student_answer 行为不变。

---

## Phase 3：记忆系统 — mem0 默认开启 + 画像持久化

**目标：** 语义记忆默认运行，用户画像持久化存储。

| # | 改动 | 说明 |
|---|------|------|
| 1 | `USE_MEM0=true` 设为默认 | 环境变量 + 文档更新 |
| 2 | `UserProfile` 模型持久化 | 新建表存储画像（learning_style / response_length / interaction_style / cognitive_state / domain_expertise / confidence），替代纯 Redis 缓存 |
| 3 | 画像更新策略 | 每次记忆更新后 Celery 异步重算画像；confidence < 0.6 时保留旧画像不覆盖 |
| 4 | memory_context 注入优化 | 语义记忆检索从"按当前消息 query"改为"按用户画像 + 当前消息"双路检索 |
| 5 | 画像数据回填 | 为现有活跃用户跑一次全量画像生成 |

**风险：** mem0 需要 pgvector 扩展，确认生产 PostgreSQL 版本支持。

---

## Phase 4：MemorySystem 查询接口层

**目标：** 教育闭环 handler 不再直接 import `quizzes.models`，通过 MemorySystem 接口访问数据。

| # | 改动 | 说明 |
|---|------|------|
| 1 | 实现 `MemorySystem` 查询接口 | `query.user_profile()` / `query.weak_points()` / `query.mastery_map()` / `query.due_reviews()` / `query.learning_stats()` / `query.difficulty_analysis()` |
| 2 | 实现 `MemorySystem` 写入接口 | `write.error_analysis()` / `write.memorix_update()` |
| 3 | 重构 PlannerToolExecutor handler | `get_learning_stats` / `get_knowledge_mastery_map` / `get_user_weak_points` / `get_due_reviews` / `get_knowledge_difficulty` → 全部改为调 MemorySystem.query |
| 4 | 重构 ExamGeneratorToolExecutor handler | `get_workbench_stats` / `get_class_weak_points` → 调 MemorySystem.query |
| 5 | 重构 _handle_grade_student_answer | 错因写入改为 `MemorySystem.write.error_analysis()` |
| 6 | 移除 handler 中的 model import | 除 MemorySystem 内部实现外，禁止 `from quizzes.models import ...` |

**验证：** 所有现有测试通过；handler 中 grep `from quizzes.models` 返回零结果。handler 测试可 mock MemorySystem 接口。

---

## Phase 5：API 化

**目标：** 测评引擎和记忆系统对外输出 API。

| # | 改动 | 说明 |
|---|------|------|
| 1 | `POST /api/grading/grade/` | 接收 {question_id, student_answer} → 返回 grade() 结果（含 error_analysis） |
| 2 | `GET /api/memory/profile/?user_id=...` | 返回用户画像 |
| 3 | `GET /api/memory/due/?user_id=...` | 返回到期题目列表 |
| 4 | `GET /api/memory/stats/?user_id=...` | 返回学习统计 |
| 5 | API 认证 | 复用 CookieTokenAuthentication，+ API Key 支持（机构级密钥） |
| 6 | 速率限制 | 每 API Key 每分钟 60 次，超过返回 429 |

**验证：** API 可被外部系统调用（如机构自有的 LMS 系统集成）。

---

## Phase 6：IRT / CDM 认知诊断升级

**目标：** 从 CTT 评分升级到 IRT 知识建模，为 CDM 准备数据。

| # | 改动 | 说明 |
|---|------|------|
| 1 | Item 参数表 | 新建 `ItemParameter` 模型：discrimination / difficulty / guessing / last_estimated_at |
| 2 | IRT 参数估计 | Celery 定时任务（每周），对 responses ≥ 500 的题目跑 MML-EM 参数估计 |
| 3 | θ 能力估计 | 新建 `UserAbility` 模型，按知识点存 θ 值 |
| 4 | 升级 grade() 输出 | 追加 `kp_breakdown: [{kp_name, theta, mastery_probability}]` |
| 5 | Q-matrix 数据模型 | 新建 `QMatrix` + `QMatrixEntry` 模型（知识点 × 题目的映射表），为 CDM 准备数据结构 |
| 6 | 专家标注工具 | 飞书多维表格形式的 Q-matrix 标注界面（Phase 6.5） |

**前提条件：** 每道题 ≥ 500 次 responses。新题目在数据不足时 fallback 到 CTT。

---

## Phase 7：MUTAR 自进化

**目标：** 利用 Trajectory 数据自动优化 prompt 模板和 Memorix 参数。

| # | 改动 | 说明 |
|---|------|------|
| 1 | Trajectory 分析管线 | Celery 定时任务分析 AITrajectory 表，提取工具调用成功率 / 用户反馈 / 对话完成度 |
| 2 | Prompt 优化 (Generate→Evaluate→Polish) | 对低成功率场景自动生成 prompt 变体 → A/B 测试评估 → 采纳或回滚 |
| 3 | Memorix 参数自适应 | 分析 lapse_rate 和 stability 增长斜率 → 调整 γ（增长因子）和 α（lapse 惩罚） |
| 4 | 用户画像反馈闭环 | 用户对自适应指令的隐式反馈（是否忽略、是否追问）→ 调整画像分析权重 |
| 5 | 安全护栏 | 所有自动变更需人工审核后才能上线；A/B 测试期间保留原始版本作为 control |

**前提条件：** Trajectory 数据积累 ≥ 10,000 条，Phase 1-6 完成。

---

## 总览

```
Phase 0  ✅  架构文档
Phase 1  🔜  错因分析 + Memorix 字段
Phase 2  📋  测评引擎独立化 + GradingRecord
Phase 3  📋  mem0 默认 + 画像持久化
Phase 4  📋  MemorySystem 接口层（重构所有 handler）
Phase 5  📋  API 化（Grading + Memory 对外输出）
Phase 6  📋  IRT 参数估计 + Q-matrix
Phase 7  📋  MUTAR 自进化
```

**依赖关系：**
- Phase 2 依赖 Phase 1（测评引擎先有错因分析再独立化）
- Phase 4 依赖 Phase 2（MemorySystem 接口需要 GradingEngine 已独立）
- Phase 5 依赖 Phase 4（API 需要接口层）
- Phase 6 依赖 Phase 2（IRT 需要评分记录数据）
- Phase 7 依赖 Phase 4+6（自进化需要接口层 + IRT 参数）
