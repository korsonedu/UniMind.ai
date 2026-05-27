# UniMind.ai 更新日志 (Changelog)

所有项目的重要更新都将记录在此文件中，以确保开发进度的可追溯性。

---

## [v2.8.0-dev] - 2026-05-27

### 🧠 Multi-Tenant Agent Memory (mem0 + pgvector)

- **语义记忆**：集成 mem0 SDK + pgvector，Agent 从对话中自动提取语义记忆，下次对话语义检索注入 prompt。
- **租户隔离**：每个机构独立 pgvector collection（`inst_{id}`），用户级 `user_id` 过滤。
- **双层记忆**：结构化（AgentMemory KV）+ 语义（mem0）互补，结构化层存精确数据，语义层存模糊认知。
- **工具权限沙箱**：`PLAN_TOOL_ACCESS` 按 plan（free/starter/growth/enterprise）过滤 Agent 可用工具集。
- **机构人格**：Bot 模型新增 `institution_personality` JSONField，机构可配置教学风格、语气、知识领域。
- **Feature Flag**：`USE_MEM0=true` 启用，默认关闭，渐进式上线。
- **Embedding 配置**：`AI_EMBEDDING_MODEL` / `AI_EMBEDDING_BASE_URL` 环境变量可配置 embedding 模型。
- **语义记忆 API**：`/api/ai/memories/semantics/` — GET 列表、DELETE 单条、DELETE 清空。
- **测试**：6 单元测试 + 9 工具权限测试 + 3 集成测试（需 PG）。
- **技术文档**：`docs/tech/features/MULTI_TENANT_AGENT_MEMORY.md`

---

## [v2.8.0-dev] - 2026-05-26

### 🤖 多步可见 Agent（WebSocket 实时步骤 + 流式输出）

- **`call_ai_with_streaming_tools`** (`ai_engine/service.py`)：流式 Agent 循环，支持 `on_step` 回调实时推送每步 tool call/result。
- **WebSocket Consumer** (`ai_assistant/consumers.py`)：`AgentChatConsumer`，agent loop 在线程池中执行，每步通过 WS 推送。
- **Step Label 生成** (`tool_executor.py` → `generate_step_label`)：22 个 tool 的中文动态描述（如"检索「导数」相关知识点"）。
- **前端组件**：`useAgentChat` hook + `AgentStepCard` 折叠卡片组件，集成到 `AIAssistant.tsx`。
- **适用范围**：exam_generator（出题助手）和 planner（小宇）升级，assistant 保持原有 polling 模式。
- **技术文档**：`docs/tech/features/MULTI_STEP_AGENT.md`

---

## [v2.8.0-dev] - 2026-05-25

### 🧠 Agent 记忆系统

- **新增 `AgentMemory` 模型** (`ai_assistant/models.py`)：4 种记忆类型（preference/academic/interaction/teacher_context），支持 AI 自动提取和用户手动创建。
- **记忆服务** (`ai_assistant/services/memory_service.py`)：对话后后台线程自动提取关键事实，下次对话注入 system prompt（上限 800 字符）。
- **CRUD API**：`/api/ai/memories/` — 用户可查看、创建、编辑、删除自己的记忆。
- **Prompt 模板**：`prompts/ai_assistant/memory_extraction_prompt.txt` — 结构化 JSON 输出 schema。

### 🩺 学生诊断测试

- **诊断服务** (`quizzes/services/diagnostic_service.py`)：随机选取 10 个机构知识点生成诊断题，支持客观题精确匹配 + 主观题 AI 判分。
- **Memorix 初始化**：答对 KP → stability=5.0, next_review=+3天；答错 → stability=1.0, next_review=+1天。
- **路由守卫**：学生首次登录未完成诊断 → 强制跳转 `/diagnostic`。
- **前端页面** (`frontend/src/pages/DiagnosticTest.tsx`)：三阶段流程（欢迎→答题→结果分析）。

### 📋 出题模板预设系统

- **新增 `ExamTemplate` 模型** (`quizzes/models.py`)：支持难度、题型比例、题量、预选知识点等配置。
- **3 个系统预设**（数据迁移 `0036_seed_system_presets.py`）：期末模拟卷（hard/30题）、周测（normal/15题）、知识点专练（mixed/10题）。
- **CRUD API**：`/api/quizzes/templates/` — 系统预设不可删改，机构可创建自定义模板。
- **前端组件**：工作台左侧栏模板选择器（随 Feature 5 一起交付）。

### 🔄 闭环反馈

- **班级分析端点**：`/api/users/institution/me/analytics/class-performance/` — 按 KP 聚合全班正确率 + 周趋势。
- **薄弱知识点建议**：`/api/users/institution/me/analytics/suggested-topics/` — Top 5 最弱 KP + 针对性建议。
- **绩效告警**：`notifications` 新增 `performance_alert` 类型，Celery 每日检测正确率下降 >15% 自动通知。
- **Agent 工具扩展**：`get_class_weak_points` + `get_class_performance_summary`（仅 teacher/owner 可用）。
- **前端面板** (`ClassPerformancePanel.tsx`)：div 柱状图 + 趋势箭头 + "针对出题"按钮（跳转工作台预选 KP）。

### 🎨 AI 出题工作台

- **教师首页**：`/workbench` — teacher/owner 登录后自动跳转，侧边栏首位入口。
- **ARC 管线集成**：复用现有 4-agent 对抗管线（Author→Reviewer→AuthorRevise→Classifier），前端直接调用 `/api/quizzes/admin/adversarial-pipeline/`。
- **后端端点**：`WorkbenchTaskListView`（教师任务列表）+ `WorkbenchTaskStatusView`（轻量轮询）。
- **三栏布局**：左侧模板+任务列表 / 中间白板（配置→进度 stepper→结果审核）/ 右侧 AI 助手占位。
- **子组件**：`TemplateSidebar`、`LaunchConfig`（KP 搜索+难度/题型配置）、`PipelineProgress`（4 阶段 stepper）、`QuestionResults`、`QuestionReviewCard`（ARC 元数据展示）。
- **审核入库**：逐题选择 + 批量批准/拒绝，复用 `PipelineReviewActionView`。

## [v2.7.0-dev] - 2026-05-23

### 🔌 AI 引擎：模型供应商热插拔

- **从 DeepSeek V4 全量切换至 Xiaomi MiMo V2.5**
    - `FALLBACK_FAST = 'mimo-v2.5'` / `FALLBACK_PRO = 'mimo-v2.5-pro'`，供应商切换只改 config.py 顶部。
    - MiMo thinking + tool_choice 不冲突，移除 DeepSeek 特有的 `elif tool_choice → thinking=disabled` 互斥逻辑。
- **分级路由替代硬编码模型名**
    - `_TASK_MODEL_MAP` 从 `(env_key, model_name)` 改为 `(env_key, tier)`，tier ∈ {fast, pro}。
    - 分辨率链：单任务 env → `AI_MODEL_FAST`/`AI_MODEL_PRO` env → `FALLBACK_FAST`/`FALLBACK_PRO`。
- **env 变量名供应商无关化**
    - `DEEPSEEK_API_KEY` → `LLM_API_KEY`（单一变量，不再有多级 fallback 链）。
    - env 文件不重复 config.py 默认值，纯覆盖层。
- **协议适配**
    - `max_tokens` → `max_completion_tokens`（MiMo API 格式）。
    - `reasoning_effort` → `thinking: {type: "enabled"}`（MiMo 思考模式控制）。
- **死代码清理**
    - 移除 `settings.py` 中零引用的 `DEEPSEEK_API_KEY` / `LLM_MODEL` / `LLM_BASE_URL`。
    - 移除 `config.py` 中零引用的 `get_llm_config()` 和无调用方的 operation 前缀（`essay`/`grading`/`grade`）。

## [v2.6.0-dev] - 2026-05-22

### 🧠 AI 引擎：Prompt 系统升级为 Agent 系统

- **结构化输出替代正则 JSON 提取**
    - `AIEngine.structured_output()` 使用 OpenAI 兼容的 `tool_choice="required"` 强制模型输出符合 JSON Schema 的结构化数据，取代依赖正则匹配的 `extract_json()`。
    - 保留 `extract_json()` 作为 fallback，向后兼容所有现有调用。
- **出题管线 4 个 Agent 工具定义**
    - 新增 `backend/ai_engine/tools.py`，为 Author/Reviewer/AuthorRevise/Classifier 四个 Agent 定义精确的 JSON Schema（题型、评分维度、分类标签）。
    - 每个 Schema 包含 `type`、`enum`、`minimum`/`maximum` 约束，从 API 层面杜绝输出格式偏差。
- **多轮 Agent 循环就绪**
    - `AIEngine.call_ai_with_tools()` 支持模型多次调用工具、结果回传后继续推理的标准 Agent loop。
    - 首轮 `tool_choice` 可强制，后续自动切换为 `auto` 让模型自主决策。最多 5 轮，超出时记录 warning。
- **防御性修复（Code Review 11 findings）**
    - 修复 `_author_generate` 中变量名错误 `parsed`→`q_list`，该 bug 导致管线静默产出 0 题。
    - `json.loads(None)` 引发 `TypeError` 未被捕获 → except 子句补齐 `TypeError`。
    - `_extract_content` 空字符串遮蔽 `reasoning_content` → `if content is None` 改为 `if not content`。
    - `simple_chat` 对 `content: null` 调用 `.strip()` 引发 `AttributeError` → 安全处理。
    - `if tools:` 空列表 falsy → 改为 `if tools is not None:`。
    - `_QUESTION_SCHEMA` 在 Author/Revise 之间共享可变引用 → `deepcopy` 隔离。
    - `_extract_tool_calls` / `_extract_content` 异常块补充日志。
    - 管线 4 个 Agent 函数补充 `result is None` 警告日志，避免 AI 故障静默吞没。
    - Reviewer/Classifier user prompt 与 tool schema 指令统一。
    - AUTHOR_SYSTEM_PROMPT 去掉旧的"输出纯 JSON 数组"格式指令。
- **0 新依赖，~300 LOC**，仅使用 `requests` + `json` + `copy.deepcopy`。

### 🧩 全站结构化输出推广（6 文件，7 Schema）

- **判分链路** (`ai_task_service.py`)：`grade_question` / `_analyze_objective` / `generate_questions_from_text` / `parse_questions_from_text` 全部切换为 `structured_output` 主路径。
- **批量命题** (`question_generator.py`)：`_request_bulk_generate_once` 切换为 `structured_output`。
- **单管线审核** (`single_generate_pipeline.py`)：`_review_by_model` 切换为 `structured_output`。
- **模拟考试命题** (`mock_exam_generator.py`)：`_call_ai_and_parse` 切换为 `structured_output`。
- **面试模块** (`interviews/services.py`)：`tune_resume` / `generate_post_interview_radar` 切换为 `structured_output`。
- **课程模块** (`courses/services/ai_course_service.py`)：`_request_outline_items` / `generate_questions_from_transcript` 切换为 `structured_output`。
- **新增 7 个通用 Schema** 到 `backend/ai_engine/tools.py`：`QUESTION_LIST_SCHEMA`、`GRADING_RESULT_SCHEMA`、`OBJECTIVE_ANALYSIS_SCHEMA`、`BATCH_REVIEW_SCHEMA`、`RESUME_TUNE_SCHEMA`、`INTERVIEW_RADAR_SCHEMA`、`OUTLINE_ITEMS_SCHEMA`。
- **降级策略**：所有调用点均保留旧的 `simple_chat` → `extract_json` + `_repair_json_payload` 作为 fallback，`structured_output` 返回 `None` 时自动回退。
- **流式对话/自由文本不参与**：面试官追问、AI 助教聊天、`generate_ai_answer` 等不需要结构化输出的场景保持原样。

### 🧹 死代码清理

- **删除 `_repair_json_payload`**（60 行）：AI 二次修复 JSON 的兜底逻辑。Agent 化后 `tool_choice="required"` 合规率 >99%，此路径不再触发。
- **删除 `parse_question_list_with_repair` / `parse_grading_payload_with_repair`**（各 30 行）：extract_json + validate + repair 的旧三层链路。
- **删除 `validate_grading_payload`**（30 行，`ai_schema_guard.py`）：仅被上述死代码引用。
- **简化 5 处 fallback**：从 20 行 try/except/simple_chat/extract_json/repair 简化为 `logger.warning(...) + return fallback_default`。
- **保留 `validate_question_list_payload`**：被 `views_ai.py` 独立使用（前端输入校验，非 AI 输出校验）。
- **净减少 ~220 LOC**。

### 📚 文档

- 新增 `docs/tech/AI_SYSTEM_REFERENCE.md`：完整的功能索引、Schema 目录、Prompt 模板目录、模型路由表、修改指南。

### 🔧 API 兼容性

- `AIEngine.call_ai()` 新增可选参数 `tools`/`tool_choice`，默认 `None`，所有现有调用方不受影响。
- `AIService.call_ai()` 同步透传。
- `AIService.simple_chat()` / `simple_chat_text()` / `extract_json()` 签名与行为完全不变。

---

## [v2.5.8-stable] - 2026-05-17

### ✨ 新增

- **按任务智能模型路由**
    - `ai_engine/config.py` 成为模型路由单一来源，21 个 operation 按任务难度显式分配 v4-pro / v4-flash / 思考模式。
    - 路由匹配算法从 `startswith` 升级为逐段匹配，`quizzes.grade_question` 等命名空间操作不再漏过路由。
    - 此前 9 个 `AI_MODEL_*` 逐任务环境变量收敛为单一全局入口 `LLM_MODEL`。
- **JSON 解析三重兜底**
    - 模型输出格式偶有变异时，不再直接返回零分兜底。
    - 新增 markdown fence 任意位置提取 → 括号匹配定位 → 字符串感知截取三级递进解析，覆盖模型常见输出变异。
- **轻量任务自动降级**
    - AI 助教对话、文本解析、答案生成、周计划、Schema 修复等 8 个轻量任务从 v4-pro 切换至 v4-flash，降低推理成本且不影响输出质量。

### 🔧 优化

- **判分去链式推理**：主观题判分为结构化 JSON 输出任务，不依赖 CoT。去掉 thinking 后判分延迟降低约 60%，且从根本上减少模型输出格式不稳定的风险。
- **Schema 修复链路修正**：此前未命中路由表，实际使用与判分相同的重型模型，修复耗时 107s+。修正后路由至 v4-flash 轻量模型，延迟降至正常水平。
- **CoT 策略收紧**：链式推理仅保留于 3 个真正需要深度推理的场景——出题审核(high)、作文评分(max)、出题修订(medium)。
- **AI 响应提取逻辑修正**：思考模式下 `content` 为空时不再错误回退到思维链文本，避免判分误判。

---

## [v2.5.7-stable] - 2026-03-01

### 📝 Prompt 可维护性增强
- **quizzes 模板顶部职责注释**
    - 为 `backend/quizzes/templates` 下全部 `.txt` prompt 增加顶部“文件职责”说明。
    - 覆盖主模板、system 模板、共享规则块三类文件。
    - 注释内容明确了每个 prompt 的用途、调用入口或被引用关系，便于团队协作与后续治理。

---

## [v2.5.6-stable] - 2026-03-01

### 🧩 quizzes Prompt 结构化收敛
- **抽取共享规则块，减少重复维护**
    - 新增 `shared_answer_requirements.txt`、`shared_question_shape_constraints.txt`、`shared_output_schema.txt`。
    - `bulk_generate_prompt.txt` 与 `generate_from_text_prompt.txt` 改为引用共享块，避免同一规则多处拷贝。
- **system prompt 去“一行化”**
    - 将 5 个 `system_*` 模板改为多行强约束版本，明确输出边界、字段要求与失败返回策略。
- **统一口径**
    - `generate_from_text` 场景下的论述题答案要求与智能命题场景保持一致（原理 -> 分论点 -> 定量/公式分析）。

---

## [v2.5.5-stable] - 2026-03-01

### 🧹 Prompt 治理：去重与单源化
- **quizzes Prompt 读取改为单源**
    - `AIService.get_template` 对 `namespace=quizzes` 不再回退 `core/prompts`，固定从 `backend/quizzes/templates` 读取。
    - 消除“同名文件双目录”导致的隐性覆盖与维护歧义。
- **删除重复模板**
    - 移除 `backend/core/prompts` 下与 `quizzes/templates` 完全重复的 5 个文件：
      `ai_answer_prompt.txt`、`bulk_generate_prompt.txt`、`generate_from_text_prompt.txt`、`grading_prompt.txt`、`preview_parse_prompt.txt`。
- **目录职责明确**
    - `backend/quizzes/templates`：题库与命题相关 Prompt 唯一来源。
    - `backend/core/prompts`：AI 助手与跨模块通用 Prompt（如 `system_prompt`、`base_assistant_prompt`、`exclusive_mentor_prompt`、`bots/*`）。

---

## [v2.5.4-stable] - 2026-03-01

### ⚡ AI 命题吞吐优化
- **分批基础上的并发队列**
    - 在“按考点分批生成”基础上，新增受控并发队列，支持多批次并行请求。
    - 新增 `AI_BULK_GENERATE_CONCURRENCY`（默认 2），可在稳定性与速度之间按环境调优。
    - 保持失败即中止策略，避免错误批次继续放大资源消耗。
- **调度日志增强**
    - 输出批次调度日志（总任务数、单批上限、并发上限），便于压测与线上观测。

---

## [v2.5.3-stable] - 2026-03-01

### 🛠️ 根因修复：AI 命题 500/超时
- **智能命题调用链重构（非兜底）**
    - 将 `ai-smart-generate-preview` 从“多考点一次性大请求”改为“按考点 + 分批请求”模式。
    - 新增 `AI_BULK_GENERATE_MAX_PER_REQUEST`（默认 3），显著降低单次 Prompt/响应体积与单请求耗时。
    - 生成 token 预算按批次题量动态计算，避免高并发下超大响应阻塞。
- **可观测性增强**
    - 新增命题请求日志（考点数、每批题量、Prompt 字符数），便于定位慢请求根因。

### 🎯 论述题答案协议升级（贴教材、重定量）
- **论述题标准答案强制三段式**
    - 先解释核心原理（概念 + 关键公式/恒等式 + 变量含义）。
    - 至少 3 个分论点。
    - 每个分论点都要包含“理论机制 -> 公式/数量关系 -> 结论”。
- **表达风格约束**
    - 明确禁止“研究报告/政策评论式空泛表达”，要求贴近课本与 431 理论框架。
- **判分点模板同步**
    - 论述题默认 `grading_points` 更新为“原理与公式、分论点定量分析、教材术语归纳”三维度。

### ✅ 测试
- 新增 `AIService` 分批生成测试，验证“2 考点 × 每考点 5 题 × 每批 3 题”会触发 4 次模型调用。

---

## [v2.5.2-stable] - 2026-03-01

### 🚀 业务体验修复
- **知识地图做题弹窗可滚动**
    - 修复「知识地图 -> 点击做题」弹窗在长内容场景下无法上下滚动的问题，特训流程可完整浏览与作答。
- **智能命题题型默认全未选**
    - 「目标命题题型」改为初始全部未选，需教师主动勾选后才能开始命题。
    - 开始命题按钮增加题型必选约束，避免误触发默认全选策略。
- **自习室输入框自适应高度**
    - 消息输入框支持随内容自动增高（上限控制），多行输入体验更接近编辑器。

### 🛡️ 稳定性增强
- **AI 命题超时容错升级**
    - AI 调用新增可配置超时与重试（`LLM_REQUEST_TIMEOUT_SECONDS` / `LLM_REQUEST_MAX_RETRIES`）。
    - 对上游超时场景返回明确 `504` 与可读错误文案，不再直接暴露为通用 500。
    - 前端命题失败提示改为展示后端具体错误信息。
- **新增回归测试**
    - 补充 `AIPreviewGenerateView` 超时返回 504 的测试，防止回归。

---

## [v2.5.1-stable] - 2026-03-01

### 🚀 核心体验优化
- **自习室消息换行渲染修复**
    - 聊天输入框 `Shift+Enter` 产生的软换行现在会在消息区按行展示，不再被合并成单行。
    - Markdown 渲染链路新增软换行转义处理，兼容文本、公式和图片混排场景。
- **讨论区撤回规则强化**
    - 明确支持撤回「本人最后一条普通消息」与「本人最后一条任务状态系统气泡」两类内容。
    - 避免误撤回历史消息，保证讨论区上下文可追踪。

### 🎯 品牌统一 (UniMind.ai / 宇艺)
- **系统默认品牌配置更新**
    - `SystemConfig` 默认值统一更新为：`宇艺（UniMind.ai） / 宇艺 / UNIMIND.AI`。
    - 默认邀请码更新为 `UNIMIND2026`。
- **前后端展示文案统一**
    - 前端站点标题、主布局默认品牌名、落地页文案、文章页作者兜底名同步更新为“宇艺（UniMind.ai）”。
    - AI 系统提示词中的旧品牌名已替换，避免对外输出混用历史名称。

### 🛠️ 数据迁移
- **新增 `users` 迁移 `0014_systemconfig_unimind_defaults`**
    - 自动将历史默认品牌值（如“科晟智慧/KORSON ACADEMY/KORSON2025”）迁移为 UniMind.ai 新品牌默认值。

---

## [v2.5.0-stable] - 2026-03-01

### 🚀 核心特性 (Core Features)
- **智能出题难度控制上线**
    - 维护中心「智能题目工坊」新增目标难度选择：`入门 / 简单 / 适中 / 困难 / 极限 / 混合`。
    - 前后端打通 `difficulty_level` 参数，支持在生成预览阶段按目标难度稳定出题。
    - 当目标难度非混合时，系统会强制统一生成结果难度等级，避免题目难度漂移。
- **AI 命题 Prompt 难度协议升级**
    - 为 `entry/easy/normal/hard/extreme` 提供明确命题标准，重点强化“适中题/困难题”的判定边界。
    - 增加“目标难度一致性”硬约束，显著提升 AI 出题可控性与可复核性。
- **自习室在线心跳机制**
    - 新增 `POST /api/users/heartbeat/` 在线心跳接口，支持实时更新在线状态与当前任务。
    - 在线用户判定升级为可配置时间窗机制（`ONLINE_USER_ACTIVE_WINDOW_SECONDS`），解决“必须刷新才在线”的体验问题。
    - 前端自习室接入定时心跳与离场状态清理，在线状态稳定性大幅提升。

### 🛡️ 安全与部署能力增强
- **Django 配置分层与环境化**
    - 完成开发/生产安全分层，新增生产环境强校验（`SECRET_KEY`、`DEBUG`、`ALLOWED_HOSTS`）。
    - `CORS / CSRF / ALLOWED_HOSTS` 全量环境变量化，支持多环境统一部署。
- **Celery 配置补全**
    - 补齐 Broker/Result、任务超时、连接重试、Prefetch、ACK 策略、Beat 调度等关键参数。
    - 增加 `celery` 依赖声明，异步任务链路更完善、可运维性更强。

### 🧩 工程质量与稳定性
- **前端 TypeScript 构建恢复**
    - 修复关键类型错误，恢复 `npm run build` 可通过状态。
    - 优化编译配置，降低历史遗留未使用变量导致的构建阻塞风险。
- **关键接口回归测试补齐**
    - 新增在线心跳与在线用户判定相关测试用例，保障实时在线能力可持续迭代。

---

## [v2.4.0-stable] - 2026-02-24

### 🚀 核心特性 (Core Features)
- **AI 判卷协议 2.0 (Tag-based)**
    - 彻底弃用脆弱的 JSON 协议，改用 **语义标签 (Tag-based)** 通讯格式。
    - 实现了 LaTeX 数学公式的 100% 原生源码保护，解决了 `\frac` 等公式导致的解析截断与乱码问题。
    - 单次判分 `max_tokens` 提升至 8192，确保数千字的深度学术推导不再受物理限制。
- **语义化题目难度体系**
    - 引入感官难度分级：入门 (Entry)、简单 (Easy)、适当 (Normal)、困难 (Hard)、极限 (Extreme)。
    - 建立 ELO 自动映射机制（800 - 1600 基准分），管理员录题不再需要手动填写数字。
    - `seed_questions.json` 种子数据已全量迁移至新难度标准。
- **“拿捏 (Mastered)” 题目管理系统**
    - 新增“拿捏”交互功能，允许学生将已完全掌握的题目从个人题库中永久封存。
    - **逻辑闭环**：点击拿捏后，该题即时禁用、清空草稿，且不再进入本次测验的判分流程。
- **文章中心分页功能**
    - 上线文章列表分页加载（每页 20 条），支持流畅的页面跳转与状态同步。

### 🎨 交互与 UI/UX 优化
- **测试报告页重构 (High Efficiency)**
    - 布局升级为 **左右分栏矩阵模式**，大幅提升复盘时的“屏效比”。
    - 右侧引入**题号状态矩阵**，红色/绿色直观展示正误，支持秒级切换查看。
    - 优化了高度适配（90vh）与内边距，显著提升了深度解析内容的可读性。
- **自习室顶部标题集成**
    - 为自习室页面增加了全局 Header 标题展示，增强页面功能归属感。
- **通知中心视觉升级**
    - 显著放大了通知中心的内容字号（正文 12px / 标题 13px font-black），解决了文字看不清的问题。
- **消除前端抖动**
    - 将 `Select` 组件替换为 `DropdownMenu`，解决了 Radix UI 隐藏滚动条导致的页面宽度瞬间抖动。
- **页面屏效比优化**
    - 显著缩减了系统主展示区域的内边距（从 `px-10 py-10` 优化为 `px-8 py-6`），提升了核心内容的视觉承载力。

### 🛠️ 工程化与系统稳定性
- **数据库瘦身与模型优化**
    - 物理删除了 `User` 模型中的冗余字段 `avatar_url` 与 `is_online`，改为动态属性判定。
    - 修复了管理员账号在特定情况下被拦截、要求输入激活码的权限逻辑 Bug。
- **AI 模块深度解耦**
    - 新建 `backend/ai_service.py` 统筹全站 AI 调用。
    - 实现了判卷逻辑、助教对话、通用生成逻辑的完全解耦，支持场景化的 `tokens` 与 `temperature` 配置。
- **即时状态同步**
    - 提交试卷时，主线程立即更新 `last_review` 标记，确保异步判分期间不会抽到重复题。
- **版本标识更新**
    - 正式启用 **`SMART ACADEMIC ENGINE`** 作为系统标识语。

---

## [v2.3.0] - 2026-02-23

### 🛠️ 历史重构回顾
- 废弃基于 Cache 的临时报告方案，上线 `QuizExam` 持久化模型。
- 实现提交试卷后的异步判分流程，引入后台线程处理 AI 深度分析。
- 修复 AI 助教消息重复与乐观更新冲突问题。
