# 系统架构整合与 AI 辅助开发蓝图 (Architecture Integration Roadmap)

## 1. 宏观愿景
本蓝图旨在将先前提出的 5 个优化方向整合为一个有机的、自适应的智能教育 SaaS 平台架构。这 5 个模块不是孤立的，而是通过数据流和业务流相互咬合的齿轮。

## 2. 模块间的内部逻辑关系 (Internal Logic & Synergy)

我们从一个**“学生做错了一道题”**的场景来看这 5 个模块的联动：

1. **触发点**：学生 (Student) 答错了一道由 **AI多智能体管线 (模块3)** 生成的题目。
2. **数据流向 A (FSRS - 模块1)**：答错记录进入 `ReviewLog`。当该学生的记录达到阈值，后台触发 **FSRS自动调优**，该学生未来的复习间隔被缩短。
3. **数据流向 B (知识图谱 - 模块2)**：该错题所属的知识点节点，在 **知识图谱热力图** 上颜色变红。系统启动“阻塞回溯”，发现其前置知识点薄弱，调整后续的推题路径。
4. **数据流向 C (用户画像 - 模块5)**：系统自动为该学生打上 `[该知识点薄弱]` 的 **动态标签 (RBAC与用户标签)**。
5. **数据流向 D (AI 管线反馈 - 模块3 & 4)**：如果某道 AI 生成的题被所有带 `[优秀学生]` 标签的用户做错，系统怀疑该题“超纲”或“有歧义”。**教研员 (Content Reviewer, 模块5)** 收到报警并介入。如果确认是题目质量问题，**Prompt 管理系统 (模块4)** 会收集此反例（Bad Case），并在下一次迭代时补充到 `Agent 3 (Reviewer)` 的 Prompt 模板中进行规避。

## 3. AI 辅助开发的正确打开方式 (Guidelines for AI Coding Agents)

当后续使用 AI 助手（如 Cursor, Claude, Gemini CLI 等）进行代码落地时，请遵循以下分步原则：

### Phase 1: 基础设施层 (Infrastructure)
**不要急于写 AI 逻辑，先搭好数据库和权限。**
- **任务 1.1**：要求 AI 读取 `docs/RBAC_USER_MANAGEMENT.md`，并在 `backend/users/models.py` 中建立 `UserProfile` 和 `UserTag`。
- **任务 1.2**：要求 AI 读取 `docs/PROMPT_MANAGEMENT_SYSTEM.md`，并在 `backend/core/models.py` 中建立 `PromptTemplate` 表，并提供基础的 CRUD 接口。

### Phase 2: 核心算法与数据层 (Algorithms & Data)
**建立状态机和数学模型，先离线跑通。**
- **任务 2.1**：要求 AI 读取 `docs/FSRS_AUTO_TUNING_ALGORITHM.md`，在 `quizzes/fsrs.py` 或独立脚本中编写 `scipy.optimize` 逻辑，使用假数据跑通 RMSE 最小化。
- **任务 2.2**：要求 AI 读取 `docs/KNOWLEDGE_GRAPH_PERSONALIZATION.md`，在 `quizzes/models.py` 中补充 `UserKnowledgeState`，并编写 Celery 任务定时从 ReviewLogs 计算 Mastery Score。

### Phase 3: AI 业务流 (AI Workflows)
**最后组装最复杂的生成与对抗管线。**
- **任务 3.1**：要求 AI 读取 `docs/AI_MULTI_AGENT_PIPELINE.md`，重构 `backend/quizzes/ai_workflow.py`。
- **强制要求**：AI 写这部分代码时，必须**从 Phase 1 的 `PromptTemplate` 数据库中读取 Prompt**，不能硬编码。
- **强制要求**：使用 Celery 的 `chain` 将生成、审核、打标签解耦为不同的 Tasks。

## 4. 防坑指南 (Pitfalls to Avoid)
1. **不要一揽子要求 AI 写全套**：将上述 Task 拆分成独立的 Prompt 交给 AI。
2. **注意数据库迁移依赖**：确保 Phase 1 的 `makemigrations` 和 `migrate` 成功后再进行 Phase 2。
3. **隔离 AI 与主线程**：所有涉及大模型调用（模块3）和高计算量（模块1）的代码，必须要求 AI 使用 `@shared_task` 包装，决不能阻塞 Web 请求。
