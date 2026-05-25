# AI 系统参考手册

> 维护者索引：所有 AI 功能的分系统位置、Schema、Prompt 模板、模型路由的完整映射。
> 新增/修改 AI 功能时，先查此文档定位要改的文件。

## 架构总览

```
prompts/                          ← Prompt 模板（纯文本，业务可编辑）
    ↓ AIService.get_template()
quizzes/services/                 ← 判分逻辑、命题管线编排
interviews/services.py            ← 面试 AI
courses/services/ai_course_service.py ← 课程 AI
    ↓ AIService.structured_output() / simple_chat()
ai_engine/ai_service.py           ← AIService 门面（system_prompt+user_prompt → messages）
    ↓ AIEngine.structured_output() / call_ai()
ai_engine/service.py              ← AIEngine（HTTP 请求、tool calling、熔断、重试）
    ↓ HTTP POST → api.deepseek.com/v1/chat/completions
ai_engine/tools.py                ← JSON Schema 定义（约束模型输出格式）
ai_engine/config.py               ← 模型路由表（哪个任务用什么模型、是否思考）
```

**三个原则**：
1. Prompt 模板在 `prompts/`，不在代码里
2. JSON Schema 在 `tools.py`，每个 AI 函数的输出格式有唯一定义
3. 模型路由在 `config.py`，不散落在各调用点

---

## 一、功能索引

### 1. 判分

| 维度 | 值 |
|------|---|
| **入口** | `quizzes/views_exam.py` → `GradeSubjectiveView.post` |
| **服务** | `quizzes/services/ai_task_service.py` → `QuizAITaskService.grade_question` |
| **AI 方法** | `structured_output` |
| **Schema** | `GRADING_RESULT_SCHEMA` (tools.py:179) |
| **Prompt** | `prompts/quizzes/grading_prompt.txt` |
| **Operation** | `quizzes.grade_question` |
| **Model** | 默认 (deepseek-v4-pro)，无思考 |
| **请求参数** | temperature=0.2, max_tokens=2500 |

**输出格式**：
```json
{"score": 8.5, "feedback": "判分依据...", "analysis": "标准答案...", "memorix_rating": 3}
```

**逻辑**：
- 客观题：本地对比答案（normalize_objective_answer），AI 只做深度解析（为什么对/错 + 易错点）
- 主观题：AI 完整判分（score/feedback/analysis/memorix_rating），分数钳位到 [0, max_score]
- 失败时返回 zero-score 兜底

**客观题深度解析**（同文件 `_analyze_objective`）：

| 维度 | 值 |
|------|---|
| **Schema** | `OBJECTIVE_ANALYSIS_SCHEMA` (tools.py:193) |
| **Prompt** | `prompts/quizzes/objective_analysis_prompt.txt` |
| **Operation** | `quizzes.objective_analysis` |
| **输出** | `{"why_correct": "...", "why_wrong": "...", "pitfalls": "..."}` |

---

### 2. 命题

#### 2a. 批量智能命题（最常见）

| 维度 | 值 |
|------|---|
| **入口** | `quizzes/views_ai.py` → `AIPreviewGenerateView.post` |
| **服务** | `quizzes/services/single_generate_pipeline.py` → `run_single_generate_pipeline` |
| **Author** | `quizzes/services/question_generator.py` → `QuestionGenerator._request_bulk_generate_once` |
| **Reviewer** | `single_generate_pipeline.py` → `_review_by_model` |
| **AI 方法** | `structured_output` (Author + Reviewer 均用) |
| **Author Schema** | `QUESTION_LIST_SCHEMA` (tools.py:173) — 题目数组 |
| **Reviewer Schema** | `BATCH_REVIEW_SCHEMA` (tools.py:203) — 批量审查结果 |
| **Author Prompt** | `prompts/quizzes/bulk_generate_prompt.txt` |
| **Reviewer Prompt** | `prompts/pipeline/reviewer_single.txt` (PromptManager name: `AI_QUESTION_REVIEWER_BATCH`) |
| **Operation** | Author: `quizzes.bulk_generate`, Reviewer: `quizzes.single_pipeline.reviewer` |
| **Model** | 默认 (deepseek-v4-pro)，无思考 |
| **请求参数** | Author: temperature=0.35, max_tokens=动态(1200+count×1200); Reviewer: temperature=0.05, max_tokens=2200 |

**管线流程**：
```
Author: 知识点分批 → ThreadPoolExecutor 并发 → structured_output(QUESTION_LIST_SCHEMA)
  ↓
本地校验: 去重 → LaTeX 括号配对 → 客观题选项完整性
  ↓
Reviewer: 批量打包 → structured_output(BATCH_REVIEW_SCHEMA) → 不通过的丢弃
  ↓
Classifier: 本地匹配知识点 code → kp_id（不调 AI）
```

#### 2b. 对抗性出题管线（高质量，每道题独立迭代）

| 维度 | 值 |
|------|---|
| **入口** | `quizzes/views_ai.py` → `AdversarialPipelineView.post` |
| **服务** | `quizzes/services/adversarial_pipeline.py` → `_execute_pipeline` (Celery 异步) |
| **Agent 数** | 4 个（Author / Reviewer / AuthorRevise / Classifier） |

| Agent | Schema | AI 方法 | Prompt | Operation | Model | Thinking | temperature |
|-------|--------|---------|--------|-----------|-------|----------|-------------|
| Author | `AUTHOR_OUTPUT_SCHEMA` | `structured_output` | `pipeline/author_generate.txt` | `pipeline.author` | deepseek-v4-pro | 关 | 0.7 |
| Reviewer | `REVIEWER_OUTPUT_SCHEMA` | **`agentic_structured_output`** | `pipeline/reviewer_adversarial.txt` | `pipeline.reviewer` | deepseek-v4-pro | **开(high)** | 0.2 |
| Revise | `AUTHOR_REVISE_OUTPUT_SCHEMA` | `structured_output` | inline（system_prompt 在代码中） | `pipeline.author_revise` | deepseek-v4-pro | **medium** | 0.6 |
| Classifier | `CLASSIFIER_OUTPUT_SCHEMA` | `structured_output` | `pipeline/classifier.txt` | `pipeline.classifier` | deepseek-v4-**flash** | 关 | 0.1 |

**Reviewer 知识库 Agent**：Reviewer 是唯一使用 `agentic_structured_output` 的管线 Agent。评审前可通过两个研究工具自主查询：
- `lookup_knowledge_point_definition(code)`：查询目标知识点的标准定义、范围和核心内容，验证 coverage 维度
- `search_similar_questions(kp_code, limit)`：搜索同知识点下已有题目，检查是否雷同或重复

研究结果通过 `reasoning_content` 贯穿多轮工具调用，最后由 `submit_review` 工具提交结构化评审结果。

**迭代逻辑**：每道题最多 3 轮 Reviewer→Revise。score >= 0.7 通过，3 轮不通过标记 `quality_warning=True` 仍保留。

**三维度评分**（Reviewer）：discrimination(区分度), clarity(表述清晰度), coverage(知识覆盖度)。每项 0.0-1.0。任一维度 < 0.4 则总分 ≤ 0.5。

#### 2c. 从文本出题

| 维度 | 值 |
|------|---|
| **入口** | `quizzes/views_ai.py` → `GenerateFromTextView.post` |
| **服务** | `ai_task_service.py` → `QuizAITaskService.generate_questions_from_text` |
| **Schema** | `QUESTION_LIST_SCHEMA` |
| **Prompt** | `prompts/quizzes/generate_from_text_prompt.txt` |
| **Operation** | `quizzes.generate_from_text` |
| **请求参数** | temperature=0.35, max_tokens=7000 |

#### 2d. 文本解析（OCR/批量导入）

| 维度 | 值 |
|------|---|
| **入口** | `quizzes/views_ai.py` → `AIPreviewParseView.post` (Celery 异步分段) |
| **服务** | `ai_task_service.py` → `QuizAITaskService.parse_questions_from_text` |
| **Schema** | `QUESTION_LIST_SCHEMA` |
| **Prompt** | `prompts/quizzes/preview_parse_prompt.txt` |
| **Operation** | `quizzes.preview_parse` |
| **请求参数** | temperature=0.2, max_tokens=3200 |

#### 2e. 模拟考试命题（基于错题）

| 维度 | 值 |
|------|---|
| **入口** | `quizzes/views_memorix.py` → `PersonalizedMockExamView.post` (Celery → PDF) |
| **服务** | `quizzes/services/mock_exam_generator.py` → `MockExamGeneratorService` |
| **Schema** | `QUESTION_LIST_SCHEMA` |
| **Prompt** | inline（SYSTEM_PROMPT + QUESTION_SCHEMA 常量） |
| **Operation** | `quizzes.mock_exam_generate` |
| **请求参数** | temperature=0.4, max_tokens=8000 |
| **特点** | 分两批并行：客观题+名词解释 / 计算题+论述题 |

---

### 3. 面试

#### 3a. 简历调优

| 维度 | 值 |
|------|---|
| **入口** | `interviews/views.py` → `ResumeTuneView.post` |
| **服务** | `interviews/services.py` → `InterviewAIService.tune_resume` |
| **Schema** | `RESUME_TUNE_SCHEMA` (tools.py:224) |
| **Prompt** | `prompts/interviews/resume_tuner.txt` (PromptManager: `AI_RESUME_TUNER`) |
| **Operation** | `interviews.tune_resume` |
| **Model** | deepseek-v4-flash |
| **输出** | `{"score": 85, "diagnostics": "...", "optimized_content": {...}, "predicted_questions": [...]}` |

#### 3b. 面试复盘雷达

| 维度 | 值 |
|------|---|
| **入口** | `interviews/views.py` → `InterviewFinishView.post` |
| **服务** | `interviews/services.py` → `InterviewAIService.generate_post_interview_radar` |
| **Schema** | `INTERVIEW_RADAR_SCHEMA` (tools.py:245) |
| **Prompt** | `prompts/interviews/interview_analyzer.txt` (PromptManager: `AI_INTERVIEW_ANALYZER`) |
| **Operation** | `interviews.radar_analysis` |
| **Model** | deepseek-v4-flash |
| **输出** | `{"radar_scores": {theory, logic, stress, fluency, english}, "overall_feedback": "..."}` |

#### 3c. 模拟面试追问（流式对话）

| 维度 | 值 |
|------|---|
| **入口** | `interviews/views.py` → `InterviewReplyStreamView.post` (SSE) |
| **服务** | `interviews/services.py` → `InterviewAIService.generate_interview_reply_stream` |
| **AI 方法** | `AIEngine.call_ai_stream`（**非** structured_output，自由文本） |
| **Operation** | `interviews.mock_reply` |
| **Model** | deepseek-v4-flash |
| **Prompt** | inline (`_build_prompt()` 根据 session_type/ style 动态构建) |

#### 3d. 逐句点评

| 维度 | 值 |
|------|---|
| **入口** | `interviews/views.py` → (面试 WebSocket 内触发) |
| **服务** | `InterviewAIService.annotate_candidate_turn` |
| **AI 方法** | `simple_chat_text`（纯文本） |
| **Operation** | `interviews.turn_feedback` |
| **Prompt** | `prompts/interviews/turn_feedback.txt` (PromptManager: `AI_INTERVIEW_TURN_FEEDBACK`) |

---

### 4. 课程

#### 4a. 视频大纲生成

| 维度 | 值 |
|------|---|
| **入口** | `courses/views.py` → `CourseOutlineView.post` |
| **服务** | `courses/services/ai_course_service.py` → `AICourseService._request_outline_items` |
| **Schema** | `OUTLINE_ITEMS_SCHEMA` (tools.py:265) |
| **Prompt** | `prompts/courses/transcript_outline_prompt.txt` |
| **Operation** | `courses.generate_outline` |
| **AI 方法** | `structured_output` |
| **输出** | `[{"title": "...", "timestamp_seconds": 0, "description": "..."}]` |

**流程**：视频上传 → ASR 转录 → 转录完成自动触发大纲生成 → 大纲完成自动触发出题。

#### 4b. 课程视频出题

| 维度 | 值 |
|------|---|
| **入口** | 大纲完成自动触发 → `_schedule_question_generation` |
| **服务** | `AICourseService.generate_questions_from_transcript` |
| **Schema** | `QUESTION_LIST_SCHEMA` |
| **Prompt** | inline（system_prompt + 拼接 prompt） |
| **Operation** | `courses.generate_questions` |
| **结果** | 写入 `CourseVideoQuestion` 表（不入主题库） |

---

### 5. 辅助

#### 5a. AI 答案生成

| 维度 | 值 |
|------|---|
| **触发** | 管理员创建题目时自动触发（`QuestionListCreateView.perform_create`） |
| **服务** | `ai_task_service.py` → `QuizAITaskService.generate_ai_answer` |
| **AI 方法** | `simple_chat_text`（纯文本） |
| **Prompt** | `prompts/quizzes/ai_answer_prompt.txt` |
| **Operation** | `quizzes.generate_ai_answer` |

#### 5b. 知识树生成

| 维度 | 值 |
|------|---|
| **入口** | `python manage.py generate_knowledge_tree --subject <name>` |
| **命令** | `quizzes/management/commands/generate_knowledge_tree.py` |
| **AI 方法** | `simple_chat_text`（纯文本） |
| **Operation** | `generate_knowledge_tree` |
| **Model** | deepseek-v4-pro |
| **请求参数** | temperature=0.3, max_tokens=16384 |

#### 5c. AI 助教对话（Agent 多轮工具调用）

| 维度 | 值 |
|------|---|
| **入口** | `ai_assistant/views.py` → `AIChatView.post` → 后台线程 `process_ai_chat` |
| **服务** | `ai_assistant/services/chat_service.py` → `AssistantChatService.chat_with_assistant_agent` |
| **AI 方法** | **`call_ai_with_tools`**（多轮 Agent 循环，非流式） |
| **Prompt** | `prompts/ai_assistant/base_assistant_prompt.txt` + `prompts/ai_assistant/bots/*.txt` |
| **Model** | deepseek-v4-flash |
| **工具** | 4 个：`search_knowledge_tree` / `get_user_weak_points` / `get_user_wrong_questions` / `lookup_question` |
| **工具执行器** | `ai_assistant/services/tool_executor.py` → `AssistantToolExecutor` |

**Agent 行为**：助教在回复前可自主调用工具查询知识库和用户数据，而非仅凭模型参数记忆回答。工具查询结果注入上下文后，模型基于准确数据进行回复。

**工具说明**：
- `search_knowledge_tree(query, subject?)`：按名称查找知识点（模糊匹配）
- `get_user_weak_points()`：获取当前用户错题最多的知识点排行
- `get_user_wrong_questions(limit?)`：获取最近错题列表（题干+答案）
- `lookup_question(question_id)`：查询具体题目详情

---

## 二、Schema 目录

所有 Schema 定义在 `backend/ai_engine/tools.py`。

### 管线专用

| Schema | 行号 | 用途 | 输出类型 |
|--------|------|------|---------|
| `_QUESTION_SCHEMA` | 12 | 单题结构（公共基础） | object |
| `_REVIEW_DIMENSIONS_SCHEMA` | 43 | 审查三维度（公共基础） | object |
| `AUTHOR_OUTPUT_SCHEMA` | 68 | 对抗管线 Author | `{questions: [...]}` |
| `REVIEWER_OUTPUT_SCHEMA` | 80 | 对抗管线 Reviewer | `{score, feedback, dimensions}` |
| `AUTHOR_REVISE_OUTPUT_SCHEMA` | 96 | 对抗管线 Revise | `{revised_question: {...}}` |
| `CLASSIFIER_OUTPUT_SCHEMA` | 104 | 对抗管线 Classifier | `{difficulty_level, knowledge_tags, ...}` |
| `BATCH_DIVERSITY_REPORT_SCHEMA` | 146 | 批量多样性审查 | `{similar_pairs, coverage_gaps, overall_assessment}` |

### 通用输出

| Schema | 行号 | 用途 | 输出类型 |
|--------|------|------|---------|
| `QUESTION_LIST_SCHEMA` | 230 | 批量命题输出 | array of questions |
| `GRADING_RESULT_SCHEMA` | 236 | 主观题判分 | `{score, feedback, analysis, memorix_rating}` |
| `OBJECTIVE_ANALYSIS_SCHEMA` | 250 | 客观题解析 | `{why_correct, why_wrong, pitfalls}` |
| `BATCH_REVIEW_SCHEMA` | 260 | 单管线批量审核 | array of `{index, pass, issues, severity}` |
| `RESUME_TUNE_SCHEMA` | 281 | 简历调优 | `{score, diagnostics, optimized_content, predicted_questions}` |
| `INTERVIEW_RADAR_SCHEMA` | 302 | 面试复盘 | `{radar_scores: {5维}, overall_feedback}` |
| `OUTLINE_ITEMS_SCHEMA` | 322 | 课程大纲 | array of `{title, timestamp_seconds, description}` |

### Agent 工具（研究/查询）

| Schema | 行号 | 用途 | 使用者 |
|--------|------|------|--------|
| `SEARCH_KNOWLEDGE_TREE_SCHEMA` | 338 | 按名称搜索知识点 | AI 助教 |
| `GET_USER_WEAK_POINTS_SCHEMA` | 353 | 获取用户薄弱知识点 | AI 助教 |
| `GET_USER_WRONG_QUESTIONS_SCHEMA` | 359 | 获取用户错题列表 | AI 助教 |
| `LOOKUP_QUESTION_SCHEMA` | 371 | 按 ID 查询题目详情 | AI 助教 |
| `LOOKUP_KNOWLEDGE_POINT_SCHEMA` | 384 | 按 code 查询知识点定义 | Reviewer |
| `SEARCH_SIMILAR_QUESTIONS_SCHEMA` | 395 | 搜索同知识点已有题目 | Reviewer |

---

## 三、Prompt 模板目录

所有模板在 `backend/prompts/`。

```
prompts/
├── quizzes/
│   ├── grading_prompt.txt              ← 主观题判分
│   ├── objective_analysis_prompt.txt   ← 客观题深度解析
│   ├── bulk_generate_prompt.txt        ← 批量命题 (Author)
│   ├── generate_from_text_prompt.txt   ← 从文本出题
│   ├── preview_parse_prompt.txt        ← 文本解析 (OCR/导入)
│   └── ai_answer_prompt.txt            ← AI 答案生成
├── pipeline/
│   ├── author_generate.txt             ← 对抗管线 Author
│   ├── reviewer_adversarial.txt        ← 对抗管线 Reviewer
│   ├── reviewer_single.txt             ← 单管线 Reviewer
│   └── classifier.txt                  ← 对抗管线 Classifier
├── interviews/
│   ├── resume_tuner.txt                ← 简历调优
│   ├── interview_analyzer.txt          ← 面试复盘雷达
│   └── turn_feedback.txt               ← 逐句点评
├── courses/
│   └── transcript_outline_prompt.txt   ← 视频大纲生成
└── ai_assistant/
    ├── base_assistant_prompt.txt       ← AI 助教基础
    └── bots/
        ├── bot_1_prompt.txt            ← 助教角色 1
        ├── bot_2_prompt.txt            ← 助教角色 2
        └── bot_3_prompt.txt            ← 助教角色 3
```

**模板语法**：Python `str.format_map()`，占位符用 `{key_name}`。缺少 key 时返回 `{key_name}` 原样（`_SafeDict` 兜底），不会抛异常。

**模板加载**：`AIService.get_template(namespace, template_name)` → 从 `prompts/<namespace>/<template_name>` 读取。

**PromptManager 兼容**：部分旧代码用 `PromptManager.get_prompt("AI_QUESTION_AUTHOR", default)` 加载。PromptManager 内部映射到 `prompts/pipeline/author_generate.txt`。

---

## 四、模型路由

文件：`backend/ai_engine/config.py`

### 路由表

| 前缀匹配 | 模型 | 思考 | 场景 |
|---------|------|------|------|
| `pipeline.author` | deepseek-v4-pro | 关 | 对抗管线出题 |
| `pipeline.reviewer` | deepseek-v4-pro | **high** | 对抗管线深度审查 |
| `pipeline.author_revise` | deepseek-v4-pro | **medium** | 基于反馈修订 |
| `pipeline.classifier` | deepseek-v4-**flash** | 关 | 题目分类（轻量） |
| `chat` | deepseek-v4-flash | 关 | AI 助教对话 |
| `interviews` | deepseek-v4-flash | 关 | 面试追问/简历/复盘 |
| `generate_knowledge_tree` | deepseek-v4-pro | 关 | 知识树生成 |
| `grading` / `grade` | deepseek-v4-pro | **high** | 主观题判分 |
| `essay` | deepseek-v4-pro | **max** | 作文评分 |
| `answer` | deepseek-v4-flash | 关 | 答案生成 |
| `parse` / `text_parse` | deepseek-v4-flash | 关 | 文本解析 |
| `schema` / `repair` | deepseek-v4-flash | 关 | JSON 修复 |
| *（未匹配）* | `LLM_MODEL` 或 deepseek-v4-pro | 关 | 通用默认 |

### 路由机制

```python
def get_model_for_task(operation: str):
    for prefix, (env_key, fallback) in _TASK_MODEL_MAP.items():
        if operation.lower().startswith(prefix):
            model = os.getenv(env_key, fallback)  # env var 优先
            thinking = _TASK_THINKING.get(prefix)
            break
    return {"api_key": ..., "base_url": ..., "model": model, "thinking": thinking}
```

**注意**：`quizzes.grade_question` 不以 `grade` 开头（它以 `quizzes` 开头），所以**不匹配路由表**，使用全局默认模型。判分的 thinking=high 实际上未生效（由于 v2.5.8 的去 CoT 优化，operation 命名避开了路由表的 `grade` 前缀）。

### 环境变量覆盖

每个路由都有对应的环境变量。例如设置 `AI_MODEL_GENERATE_AUTHOR=deepseek-v4-flash` 可以让 Author 使用轻量模型。

全局覆盖：`LLM_MODEL=deepseek-v4-flash` 会让所有未匹配路由表的 operation 使用 flash。

---

## 五、如何修改

### 改 Prompt 模板

1. 找到对应模板文件（见第三节）
2. 直接编辑 `.txt` 文件
3. 重启服务即生效（无需改代码）
4. 模板中的 `{variable}` 是占位符，查看对应服务的 `ai.format_template(...)` 调用了解有哪些变量

### 改输出格式

1. 在 `tools.py` 修改对应的 Schema（见第二节）
2. 同步修改对应 Prompt 模板中的指令（让模型知道新的输出格式）
3. 同步修改服务代码中读取 `result['field']` 的地方

### 改模型/添加思考

1. 编辑 `config.py` 的 `_TASK_MODEL_MAP` 或 `_TASK_THINKING`
2. thinking 仅对 pro 类模型有效，可选值：`high` / `medium` / `max`

### 新增一个结构化 AI 功能（单轮）

适用场景：不需要研究工具，单次提交结果即可。如判分、分类、文本解析。

1. **定义 Schema**：在 `tools.py` 加一个 `XXX_SCHEMA`
2. **写 Prompt**：在 `prompts/<namespace>/` 创建模板文件
3. **写调用**：
   ```python
   result = AIService.structured_output(
       system_prompt="...",
       user_prompt=prompt,
       schema=XXX_SCHEMA,
       tool_name="submit_xxx",
       tool_description="提交XXX结果",
       temperature=0.3,
       max_tokens=4096,
       operation='your_namespace.your_task',
   )
   if result is None:
       logger.warning("...")
       return fallback
   ```
4. **加路由**（可选）：在 `config.py` 的 `_TASK_MODEL_MAP` 添加

### 新增一个多轮 Agent 功能（研究+输出）

适用场景：模型在输出前需要查数据库/外部资源。如 Reviewer（查知识点+已有题目）、AI 助教（查知识树+错题）。

核心方法：`agentic_structured_output` — 多轮研究工具调用 + 最后一轮结构化提交。

**步骤**：

1. **定义研究工具 Schema**：在 `tools.py` 添加工具参数 Schema（如 `LOOKUP_KNOWLEDGE_POINT_SCHEMA`）
2. **实现工具执行器**：一个 `def execute(tool_name, args) -> str` 函数，根据 tool_name dispatch
3. **定义输出 Schema**：最终提交结果的 Schema
4. **写 Prompt**：在 Prompt 中明确告知模型有哪些研究工具可用、何时使用
5. **写调用**：
   ```python
   result = AIService.agentic_structured_output(
       system_prompt="...",
       user_prompt="...",
       schema=OUTPUT_SCHEMA,
       tool_name="submit_result",           # 最终提交工具名
       tool_description="提交XXX结果",
       research_tools=get_my_research_tools(),  # 研究工具列表
       tool_executor=my_tool_executor,          # callable(name, args) -> str
       temperature=0.2,
       max_tokens=4096,
       operation='pipeline.my_task',
       max_tool_rounds=5,                   # 最多几轮工具调用
   )
   ```
6. **处理 None**：`agentic_structured_output` 不会兜底——模型未调用提交工具时返回 None，调用方需自行处理

**与单轮 `structured_output` 的区别**：
- `structured_output`：tool_choice="required"，模型必须第一轮就调用提交工具
- `agentic_structured_output`：不传 tool_choice，模型自主决定何时研究、何时提交。thinking 开启时自动生效（tool_choice 从请求体中整条移除）

### 新增一个多 Agent 管线

参考 `adversarial_pipeline.py` 的模式：
1. 每个 Agent 有独立的 Schema + system_prompt + tool_name
2. Agent 之间通过返回值传递数据
3. 单轮 Agent 用 `structured_output`，需研究能力的 Agent 用 `agentic_structured_output`
4. 管线进度写入 `ContentPipelineTask`

---

## 六、如何查找

**我想改判分的 Prompt** → `prompts/quizzes/grading_prompt.txt`

**我想改判分的输出格式** → `ai_engine/tools.py` 的 `GRADING_RESULT_SCHEMA`

**我想知道判分用什么模型** → `ai_engine/config.py`，operation=`quizzes.grade_question`（未匹配路由，用默认）

**我想让对抗管线 Author 用 flash** → 设置环境变量 `AI_MODEL_GENERATE_AUTHOR=deepseek-v4-flash`

**我想知道某个功能调了哪个服务函数** → 查第一节的功能索引表
