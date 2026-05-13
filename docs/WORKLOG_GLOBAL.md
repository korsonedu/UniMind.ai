# 全局开发工作记录：Phase 1 至 Phase 8 (Global Development Worklog)

> **文档目的**：本日志详尽记录了我们在本次对话中完成的从“基础设施建设”到“主观题 AI 阅卷”，以及后续“复试模块”、“熔断机制”等各蓝图设计的全部工作量和代码变更。供团队同事审阅整体开发进度和架构实施细节。

---

## Phase 1: 基础设施层建设 (Infrastructure & RBAC/Prompt Models)

**目标**：为后续复杂的 AI 和算法能力搭建安全、解耦的数据底座。

**核心工作量**：
1. **用户与权限扩展 (`backend/users`)**：
   - 采用 `OneToOneField` 为原有的 `User` 模型增加了 `UserProfile`，包含 `student_type`（跨考/本专业）和 `target_university`（目标院校）。
   - 复用了已有的 `UserTag` 体系。
   - 更新了 `admin.py` 进行后台注册。
2. **Prompt 管理系统 (`backend/core`)**：
   - 全新创建了 `core` app 并注册到 `INSTALLED_APPS`。
   - 设计了 `PromptTemplate` 模型表，支持动态从数据库加载、版本控制以及启用停用状态 (`is_active`)。
   - 更新了 `admin.py` 以便管理员在后台可视化配置 Prompt。
3. **安全与部署**：
   - 成功生成 `0016_userprofile` (users) 和 `0001_initial` (core) 迁移文件，并在不破坏原有业务表的情况下安全执行了 `migrate`。

---

## Phase 2: 核心算法与数据层 (FSRS Auto-tuning & Knowledge Graph)

**目标**：建立 FSRS 个性化自动调优算法和图谱状态同步机制。

**核心工作量**：
1. **第三方算法库集成**：
   - 在 `requirements.txt` 中引入了 `numpy` 和 `scipy`，为自动微分和函数最优化奠定基础。
2. **FSRS 离线调优引擎 (`backend/quizzes/fsrs_optimizer.py`)**：
   - 基于 `scipy.optimize.minimize` (L-BFGS-B 算法) 编写了 FSRS 参数自动调优脚本。
   - 编写了离线验证逻辑，成功使用 mock 数据将 RMSE 预测损失从 0.42 降低至 0.27。
3. **数据模型拓展 (`backend/quizzes/models.py`)**：
   - 新增 `FSRSProfile` 表，用于存储用户专属演化权重及 Loss 表现。
   - 新增 `ReviewLog` 表，保存历史复习日志以便离线计算。
   - 新增 `UserKnowledgeState` 表，用于图谱模块中的 `mastery_score` 记录。
4. **Celery 异步调度 (`backend/quizzes/tasks.py`)**：
   - 新建 `@shared_task: auto_tune_fsrs_for_all_users`，定时检索达到阈值的用户自动优化权重。
   - 新建 `@shared_task: calculate_mastery_scores`。
5. **部署**：完成数据库的表结构迁移。

---

## Phase 3: 多智能体 AI 业务流 (Multi-Agent Pipeline & Celery Chains)

**目标**：重构原有的单体“硬编码”AI 出题流，升级为多智能体对抗评估工作流。

**核心工作量**：
1. **Prompt 引擎连接 (`backend/core/prompt_manager.py`)**：
   - 封装 `PromptManager.get_prompt` 单例，支持当数据库未命中时安全 Fallback 到默认值。
2. **多智能体拆分与解耦 (`backend/quizzes/tasks.py`)**：
   - 开发了四个独立的 Celery 节点：
     - `agent_generate_draft`: 出题与正确答案起草。
     - `agent_add_distractors`: 干扰项生成。
     - `agent_review_and_loop`: 对抗性评估（如校验 LaTeX 和难度），如被“教研员”打回，则触发最高 3 次的内部循环重试。
     - `agent_taxonomy_and_save`: 落库前的标签清洗。
3. **流水线编排 (`backend/quizzes/services/multi_agent_builder.py`)**：
   - 使用 Celery 的 `chain` 原语，将上述 4 个任务串联为可重试、可观测的管线 `trigger_ai_question_generation`。

---

## Phase 4: 主观题 AI 阅卷引擎 (AI Essay Grading Engine)

**目标**：利用大模型对学生的名词解释、简答题、论述题进行带有采分点的结构化批改。

**核心工作量**：
1. **采分点模型支持 (`backend/quizzes/models.py`)**：
   - 在 `Question` 表新增 `rubric` 字段，存储标准 JSON 采分点标准。
   - 在 `ExamQuestionResult` 中新增 `details` 字段，用于展示批注回显。
2. **评分逻辑适配 (`backend/quizzes/services/ai_task_service.py`)**：
   - 深度改造了 `grade_question` 函数，使其能接受 `rubric` 并动态加载 `ESSAY_GRADER` 系统 Prompt。
   - 在返回结果中解析和包含采分明细（`details`）数组。如 JSON 输出损坏，会通过子代理的 `schema_repair` 函数修复结构。
3. **工作流透传 (`backend/quizzes/ai_workflow.py`)**：
   - 将 `details` 从评分底层穿透，保存至用户作答结果中。
4. **离线测试闭环 (`backend/test_essay_grader.py`)**：
   - 编写了测试用例，验证了 MM 定理“无税”相关的采分点匹配，打通从入参拼装到 JSON 提取解析的全链路，确保 Schema Validation 不出错。
5. **部署**：完成数据库字段追加迁移。

---

## Phase 5: 综合复试模块预研与设计 (Comprehensive Interview Planning)

**目标**：设计覆盖初试通过后，面试阶段的端到端陪练流。

**核心工作量 (已输出设计与蓝图)**：
1. 规划了简历调优、英语口语纠音、高压/专业场景模拟面试等功能。
2. **蓝图落地**：产出 `docs/COMPREHENSIVE_INTERVIEW_MODULE.md`，确立了通过 **Django Channels (WebSocket)** 搭配 STT/LLM/TTS 构建全双工低延迟对话链路的技术路径。
3. 确立了新 Django App (`interviews`) 与 `ResumeRecord`, `InterviewSession`, `InterviewTurn` 表结构。
4. 输出子模块工作日志到 `docs/PHASE_5_WORKLOG.md`，准备了待办的执行清单。

---

## Phase 6: AI 熔断降级与冗余机制 (AI Circuit Breaker & Fallback)

**目标**：保护大模型 API 的高可用性，在 API 故障、限流或超时的情况下，实现业务的优雅降级。

**核心工作量 (规划中)**：
1. **熔断器引入**：在 `backend/ai_engine/service.py` 封装请求入口，引入熔断逻辑（记录错误次数，超时熔断跳闸）。
2. **多模型路由**：实现从主模型到备用模型（如 `gpt-4o` 到 `claude-3.5-sonnet` 再到 `glm-4-flash`）的自动故障转移（Fallback Routing）。
3. **业务层优雅降级**：当底层大模型彻底断线时，各业务能够自动降级（如出题模块回退到本地题库抽题，主观题退回本地结构化答案自评模式）。

---

## Phase 7: 动态宏观学习计划调度器 (Macro-Level Study Planner)

**目标**：结合 FSRS 微观进度，为学生提供全局、动态的考研周期排期与每周计划。

**核心工作量 (规划中)**：
1. **数据模型搭建**：新建 `StudyPlan` 和 `WeeklyTask` 记录用户的宏观目标与学习周报。
2. **进度计算机制**：结合知识图谱的掌握度，实时计算剩余任务权重与实际完成速率，生成红绿灯状态。
3. **AI 周报调度器**：开发周日晚自动执行的 `Celery` 调度任务，根据进度状态通过 AI 智能生成下周详细的个性化学习清单。

---

## Phase 8: 考前个性化 PDF 试卷生成 (Personalized PDF Mock Exams)

**目标**：在冲刺阶段提供纸质化模考体验，将错题/薄弱知识点排版为 PDF 试卷。

**核心工作量 (规划中)**：
1. **组卷算法开发**：依据 431 真实题型比例（选择题、名词解释、计算题、论述题等），定向从 FSRS 遗忘节点与历史图谱红灯节点中抽题组卷。
2. **PDF 渲染引擎整合**：引入 `WeasyPrint` 或基于 Django Template 生成 HTML，再转换输出极高清晰度的实体试卷。
3. **异步生成工作流**：由于 PDF 生成较为耗时，剥离至 `Celery` 任务。后台异步生成双份文件（空白作答版、详尽解析版），并通过对象存储下发至考生。

---

## 2026-05-03 核查补充记录（仅记录“已落实且当前无明显问题”项）

本次按 `docs/` 逻辑对前后端落地情况进行代码核查，并执行基础检查（`scripts/check_backend.sh`）：

1. **Phase 1 基建与权限底座（通过）**  
   - 后端：`UserProfile` / `UserTag` / `PermissionGroup` / `UserAccessProfile` 与 `PromptTemplate` 模型及迁移均已存在并可正常加载。  
   - 前端：管理端已接入权限管理与用户权限编辑面板（`SuperuserPanel`、`authz` 能力判定链路）。

2. **Phase 2 算法与数据层（通过项）**  
   - `FSRSProfile`、`ReviewLog`、`UserKnowledgeState` 模型及迁移已落地。  
   - `quizzes/fsrs_optimizer.py`（`scipy`/`numpy`）可用，依赖已写入 `backend/requirements.txt`。  
   - `auto_tune_fsrs_for_all_users` / `calculate_mastery_scores` 任务函数已实现。

3. **Phase 3 多智能体管线（通过）**  
   - `agent_generate_draft`、`agent_add_distractors`、`agent_review_and_loop`、`agent_taxonomy_and_save` 与 `chain` 编排均已落地。  
   - Prompt 读取已通过 `PromptManager.get_prompt` 接入，满足“非硬编码直读”的主路径要求。

4. **Phase 4 主观题阅卷（通过）**  
   - `Question.rubric`、`ExamQuestionResult.details` 字段与迁移已落实。  
   - 阅卷链路已透传 `details`，并包含 schema repair/fallback 逻辑。  
   - `backend/test_essay_grader.py` 已存在用于闭环验证。

5. **Phase 5 复试模块（通过项）**  
   - `interviews` app 已创建并注册，`ResumeRecord` / `InterviewSession` / `InterviewTurn` 模型、Admin、迁移已落实。  
   - WebSocket 路由与 `InterviewConsumer` 基础骨架已存在。

6. **Phase 6 熔断机制（通过）**  
   - `ai_engine/circuit_breaker.py` 与 `ai_engine/service.py` 的熔断、重试、fallback 路由与可观测埋点已接入主调用链。

7. **Phase 8 个性化 PDF 模考（通过项）**  
   - `generate_personalized_pdf_mock_exam` 异步任务与 `PDFMockExamGenerator`（含双 PDF 输出）已实现。

---

## 2026-05-03 核查问题修复闭环（全部修复）

1. **前端构建阻断修复**  
   - 已修复 `frontend/src/pages/TestLadder.tsx` 末尾重复 JSX 片段导致的 TS 编译错误。  
   - 前端构建校验已通过（`npm run build`）。

2. **复试模块前后端闭环补齐**  
   - 新增 `backend/interviews/urls.py` 并挂载到主路由：`/api/interviews/`。  
   - 完成 `interviews/views.py` 的会话创建/列表/详情、文本轮次对话、会话结束复盘、简历调优接口。  
   - 前端 `frontend/src/pages/Interviews.tsx` 已接入真实 API（创建会话 + 历史记录拉取）。  
   - WebSocket `InterviewConsumer` 已从占位升级为鉴权、会话归属校验、落库与 AI 追问回复。

3. **定时调度落地修复（Phase 2 / Phase 7）**  
   - 在 `backend/school_system/settings.py` 增加 `CELERY_BEAT_SCHEDULE`：  
     - `auto_tune_fsrs_for_all_users`（每日）  
     - `calculate_mastery_scores`（每 6 小时）  
     - `generate_weekly_study_plan_for_all`（每周日晚）

4. **测试脚本问题修复**  
   - 重构 `backend/test_qa_bug.py`，去除模块导入期写库副作用，改为标准 `APITestCase`。  
   - 全量后端测试已通过（`python manage.py test`）。

5. **知识图谱热力接口补齐**  
   - 新增 `backend/quizzes/graph_views.py` 的 `UserHeatmapView`。  
   - 提供 `/api/graph/user_heatmap/`，返回节点掌握度、颜色、状态与汇总统计。

---

## 2026-05-04 功能可用性补齐（FSRS 曲线 + 多 AI Prompt 可视化）

1. **FSRS 拟合曲线正式可见**  
   - 新增后端接口：`GET /api/quizzes/fsrs/curve/`（`backend/quizzes/views.py::FSRSCurveView`，路由见 `backend/quizzes/urls.py`）。  
   - 输出内容包含：  
     - `time_series`：按日聚合的预测召回率 vs 实际召回率曲线；  
     - `fit_curve`：分桶校准拟合点（预测区间与实际表现）；  
     - `metrics`：`review_count` / `rmse` / `mae` / `avg_predicted` / `avg_actual`；  
     - `profile`：`last_optimized_at` / `current_loss` / `total_reviews_used` / `weights_preview`。  
   - 前端 `frontend/src/pages/TestLadder.tsx` 已接入并展示“FSRS 拟合曲线”卡片与指标，支持手动刷新。

2. **多 AI 出题管线 Prompt 现在可在维护台直接查看与编辑**  
   - 新增服务：`backend/quizzes/services/pipeline_prompt_service.py`。  
   - 在现有模板管理 API 增加命名空间：`pipeline_prompts`，并支持：  
     - 列表、详情、保存新版本、回滚；  
     - `agent_role` / `model_provider` / `temperature` / `is_active` 元信息同步更新。  
   - 为避免“看不到 Prompt”的空白状态，已内置确保四个核心管线 Prompt 自动存在：  
     - `AI_QUESTION_GENERATOR`  
     - `AI_DISTRACTOR_EXPERT`  
     - `AI_QUESTION_REVIEWER`  
     - `AI_TAXONOMIST`
   - 前端 `frontend/src/pages/maintenance/PromptTemplatesPanel.tsx` 已增加“多AI出题管线”命名空间，并显示/编辑上述参数与版本。

3. **测试与校验结果**  
   - 后端守护检查：`scripts/check_backend.sh` 通过。  
   - 前端构建检查：`scripts/check_frontend.sh` 通过。  
   - 新增回归测试通过：  
     - `PromptTemplateAdminAPITests.test_pipeline_prompt_list_detail_save`  
     - `FSRSCurveAPITests.test_fsrs_curve_returns_metrics_and_series`

---

## 2026-05-04 二次全链路补齐（仅记录已落实且可用）

1. **宏观学习计划（后端 API + 前端入口）已落地可用**  
   - 新增后端接口：  
     - `GET/PUT /api/study/macro-plan/`（目标考试日期/目标分数/日学习时长）  
     - `GET/POST /api/study/weekly-planner/`（周任务读取与重生成）  
     - `PATCH /api/study/weekly-tasks/{id}/`（任务状态流转）  
   - 落地文件：`backend/study_room/views.py`、`backend/study_room/urls.py`、`backend/study_room/planner.py`、`backend/study_room/tasks.py`。  
   - 前端新增真实入口页：`/macro-plan`（`frontend/src/pages/MacroPlanner.tsx`），包含加载态/空态/失败态、真实数据联动、状态更新。

2. **FSRS 与知识图谱“去占位”实现已落地可用**  
   - `calculate_mastery_scores` 从 mock 常量改为真实聚合：  
     - `Mastery = 0.4 * Retrievability + 0.4 * WinRate + 0.2 * Normalize(ELO)`。  
   - 新增 `FSRSOptimizationLog`（用户参数调优日志），并在自动调优任务中写入“是否采纳/改善比例/样本数”。  
   - 新增接口：`GET /api/quizzes/fsrs/optimization-history/`。  
   - 前端 `TestLadder` 已显示最近调优记录，支持与拟合曲线联动查看。  
   - 知识图谱热力接口 `GET /api/graph/user_heatmap/` 增补 `bottlenecks`（阻塞链路）输出，前端 `KnowledgeMap` 已接入展示。

3. **个性化 PDF 模考闭环已落地可用（含可追溯记录）**  
   - 新增 `PersonalizedMockExam` 持久化模型（状态、题量、薄弱点覆盖、错误信息、双 PDF 路径）。  
   - 新增接口：`GET/POST /api/quizzes/personalized-mock-exams/`。  
   - 生成任务完成后会写入记录并通知可访问下载页。  
   - 前端新增入口页：`/mock-exams`（`frontend/src/pages/PdfMockExam.tsx`），支持历史记录和试卷版/解析版下载按钮。

4. **复试模块可追溯能力补齐（逐轮反馈 + 记录落库）**  
   - `InterviewTextTurnView` 增加：  
     - 考生逐句反馈 `feedback_for_turn`；  
     - 面试官轮次 `latency_ms` 记录。  
   - `ResumeTuneView` 增加文件上传解析（PDF/DOCX/TXT）与 `ResumeRecord` 落库。  
   - 前端 `Interviews` 页面改为真实会话交互：会话创建、详情拉取、文本追问、结束复盘、简历调优上传。

5. **管理与可维护性补齐**  
   - `StudyPlan`/`WeeklyTask`、`FSRSOptimizationLog`/`PersonalizedMockExam` 已注册到 Django Admin。  
   - 新增后端测试覆盖上述新增 API 与核心链路（`study_room/tests.py`、`interviews/tests.py`、`quizzes/tests.py` 对应新增用例）。
