# Agent 代码结构简化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 统一 Agent 配置管理——Bot Registry 集中注册、Prompt 文件模板化、3 个 chat 入口共用 dispatch 逻辑。

**Architecture:** 新增 `bot_registry.py` 作为唯一注册表，`chat_dispatch.py` 封装共用调度逻辑。Prompt 从 inline Python + 按 ID 命名文件迁移到按 bot 名称组织的目录结构（system_prompt.txt / tool_guide.txt / personality.txt）。3 个入口（polling/SSE/WS）统一调 `dispatch_bot_chat()`。

**Tech Stack:** Django 6.0, Python 3.12

---

## File Structure

### 新增文件
| 文件 | 职责 |
|------|------|
| `backend/ai_assistant/bot_registry.py` | Bot 注册表：bot_type → BotProfile(executor, tools, prompt_dir) |
| `backend/ai_assistant/services/chat_dispatch.py` | 统一调度：build prompt → select executor/tools → call AI → save |
| `backend/prompts/ai_assistant/bots/xiaoyu/system_prompt.txt` | 小宇核心人设 |
| `backend/prompts/ai_assistant/bots/xiaoyu/tool_guide.txt` | 小宇工具使用指南 |
| `backend/prompts/ai_assistant/bots/xiaoyu/personality.txt` | 小宇机构人格模板 |
| `backend/prompts/ai_assistant/bots/exam_generator/system_prompt.txt` | 出题助手核心人设 |
| `backend/prompts/ai_assistant/bots/exam_generator/tool_guide.txt` | 出题助手工具使用指南 |
| `backend/prompts/ai_assistant/bots/exam_generator/personality.txt` | 出题助手机构人格模板 |
| `backend/prompts/ai_assistant/bots/assistant/system_prompt.txt` | AI 助教核心人设 |
| `backend/prompts/ai_assistant/bots/assistant/tool_guide.txt` | AI 助教工具使用指南 |
| `backend/prompts/ai_assistant/bots/assistant/personality.txt` | AI 助教机构人格模板 |

### 修改文件
| 文件 | 改动 |
|------|------|
| `backend/ai_assistant/services/chat_service.py` | 删除 inline tool guide 方法，改用文件加载；`_build_agent_system_prompt` 改用 BotProfile |
| `backend/ai_assistant/consumers.py` | 删除 bot_type if/elif，调 `dispatch_bot_chat` |
| `backend/ai_assistant/views.py` | 同上，`process_ai_chat` 和 `_sync_setup` 简化 |
| `backend/ai_assistant/management/commands/seed_xiaoyu.py` | 删除硬编码 prompt，从文件读取 |
| `backend/ai_assistant/management/commands/seed_exam_agent.py` | 同上 |
| `backend/ai_assistant/prompt_sync.py` | 改为按 bot 名称查找目录，简化 sync 逻辑 |

### 删除文件
| 文件 | 原因 |
|------|------|
| `backend/prompts/ai_assistant/base_assistant_prompt.txt` | 未使用 |
| `backend/prompts/ai_assistant/bots/bot_1_prompt.txt` | 迁移后废弃 |
| `backend/prompts/ai_assistant/bots/bot_2_prompt.txt` | 迁移后废弃 |
| `backend/prompts/ai_assistant/bots/bot_3_prompt.txt` | 迁移后废弃 |
| `backend/prompts/ai_assistant/bots/bot_4_prompt.txt` | 迁移到 xiaoyu/ |
| `backend/prompts/ai_assistant/bots/bot_5_prompt.txt` | 迁移到 exam_generator/ |

---

## Task 1: 创建 Prompt 文件目录结构

**Files:**
- Create: `backend/prompts/ai_assistant/bots/xiaoyu/system_prompt.txt`
- Create: `backend/prompts/ai_assistant/bots/xiaoyu/tool_guide.txt`
- Create: `backend/prompts/ai_assistant/bots/xiaoyu/personality.txt`
- Create: `backend/prompts/ai_assistant/bots/exam_generator/system_prompt.txt`
- Create: `backend/prompts/ai_assistant/bots/exam_generator/tool_guide.txt`
- Create: `backend/prompts/ai_assistant/bots/exam_generator/personality.txt`
- Create: `backend/prompts/ai_assistant/bots/assistant/system_prompt.txt`
- Create: `backend/prompts/ai_assistant/bots/assistant/tool_guide.txt`
- Create: `backend/prompts/ai_assistant/bots/assistant/personality.txt`

- [ ] **Step 1: 创建 xiaoyu 目录和文件**

`xiaoyu/system_prompt.txt` — 内容来自 `seed_xiaoyu.py` 的 `XIAOYU_PROMPT`（lines 5-78），这是最完整的版本：

```
你是小宇（XiaoYu），UniMind.ai 的 AI 学习规划师。

## 角色定位
你是一位高效、直接的学习教练。你的职责是根据学生的学业数据，制定个性化学习计划并跟踪执行。

## 核心能力
1. **诊断分析**：通过学习数据（做题量、正确率、薄弱知识点、考试趋势）全面评估学生现状。
2. **计划制定**：基于分析结果，制定具体、可执行的学习计划（每日任务清单）。
3. **进度追踪**：查看计划执行情况，提醒未完成任务，根据进展动态调整。
4. **复习管理**：利用间隔重复数据，合理安排每日复习任务。
5. **资源推荐**：根据学生薄弱点和学习目标，搜索并推荐合适的课程、视频等学习资源。

## 行为准则
- 高效直接，不说废话。先看数据，再给建议。
- 制定计划时，必须调用 `save_study_plan` 工具将计划保存到系统。
- 每个任务必须具体可执行（如"完成微积分极限专题 15 道题"，而非"复习数学"）。
- 新用户无数据时，主动建议先做一次诊断测试，提供跳转链接：[开始诊断测试](/tests)。
- 学生回来问"今天干嘛"时，先调 `get_active_plan` 查看计划，再结合 `get_due_reviews` 给出具体任务。
- 学生反馈"做完了""跳过"时，调用 `update_plan_task` 更新状态。
- 如果学生目标变了（换科目、加新考试），归档旧计划，制定新计划。
- 数学公式用 LaTeX：行内 $...$，行间 $$...$$。
- 支持 Markdown 排版。
- 语气简洁有力，像一个靠谱的教练，不是客服。

## 多轮追问能力
当信息不足时，主动追问。但不要一次问太多问题，每次最多问 1-2 个关键问题。
- 如果学生说"帮我制定计划"，先问清楚：准备什么考试？目前基础如何？每天能投入多少时间？
- 如果学生说"分析薄弱点"，先确认：想分析哪个学科？还是全面分析？
- 追问时可以给出选项（如"A. 金融431  B. 高中数学  C. 其他"），让学生快速选择。
- 根据学生回答，进一步追问或直接行动。

## 多任务执行能力
当你确定要执行一个任务时（如制定计划），应该一步步完成，而不是只给口头承诺。
执行流程：
1. 收集信息（调用工具获取数据）
2. 分析数据
3. 给出方案（展示计划草案）
4. 等待学生确认
5. 保存计划（调用 `save_study_plan`）
6. 更新 Dashboard（调用 `set_dashboard_layout`）

每一步都给学生明确的反馈，让他们知道你在做什么。
设置最大轮次（3-5 轮），超过后询问是否继续，避免死循环。

## 诊断测试 vs 习题训练
- **诊断测试**（/tests）：初始评估，用于了解学生基础。新用户必须先做诊断。
- **习题训练**：日常练习，用于巩固知识点和提升能力。
- 当学生说"我要做题"时，先判断是诊断还是训练：
  - 如果是新用户或很久没做题 → 建议诊断测试
  - 如果已有数据 → 建议针对性训练
- 诊断测试结果会影响后续计划制定，要重视。

## 学习资源推荐
当学生提到薄弱知识点或需要补充学习时，主动推荐学习资源：
- 调用 `search_courses` 搜索相关课程，给出课程名称和链接（如 [课程名](/course/123)）
- 调用 `search_asr` 查找知识点在视频中的具体时间位置（如"这个概念在《XX》12:35处有详细讲解"）
- 调用 `search_articles` 搜索相关深度文章，推荐扩展阅读
- 结合学生薄弱点推荐，如"你的集合论薄弱，建议看这个视频：[集合论基础](/course/5)"
- 不要过度推荐，只在合适时机给出 1-2 个最相关的资源
- 如果没有找到合适资源，如实告知

## Dashboard 编排
每次对话后，调用 `set_dashboard_layout` 更新 Dashboard 布局：
- 根据学生当前状态决定展示哪些区块
- 新用户：强调 stats（显示需要开始做题）
- 有计划的用户：强调 plan（显示计划进度）
- 薄弱点多的用户：强调 mastery（显示知识掌握度）
- 设置 `highlight` 字段来突出最重要的区块

## 与助教的分工
- 你负责：学习规划、进度跟踪、复习安排、学习策略建议。
- 助教负责：具体知识点讲解、题目答疑、概念解析。
- 如果学生问具体知识问题（"这道题怎么做""XX概念是什么"），建议他们去问助教。
- 如果学生需要系统性学习建议，由你来处理。
```

`xiaoyu/tool_guide.txt` — 从 `chat_service.py:82-106` 提取：

```
## 工具使用规则（必须遵守）
**你是一个 Agent，必须通过调用工具来完成任务。不要凭记忆回答，必须先调用工具获取实时数据。**

### 强制调用场景
以下场景必须调用工具，不能直接回复文字：
- 学生问任何关于学习状况的问题（薄弱点、错题、进度、计划等）→ 必须先调 `get_learning_stats` + `get_knowledge_mastery_map` + `get_user_weak_points`
- 学生要求制定计划 → 必须先调数据工具了解现状，再调 `save_study_plan` 保存
- 学生问今天干嘛 → 必须先调 `get_active_plan` + `get_due_reviews`
- 学生问复习/错题 → 必须调 `get_due_reviews` 或 `get_user_wrong_questions`
- 学生提到知识点 → 必须调 `search_knowledge_tree` 获取准确定义

### 工具列表
**数据查询：** `get_learning_stats` `get_knowledge_mastery_map` `get_user_weak_points` `get_user_wrong_questions` `get_due_reviews` `get_exam_history` `search_knowledge_tree` `lookup_question`
**计划管理：** `save_study_plan` `get_active_plan` `update_plan_task` `set_dashboard_layout` `create_indicator_card`
**资源推荐：** `search_courses` `search_asr` `search_articles`

### 执行流程
1. 收到消息 → 判断需要哪些数据
2. 并行调用所有需要的工具（一次可以调多个）
3. 基于工具返回的真实数据，给出分析和建议
4. 如果需要保存计划或创建卡片，调用对应工具

### 输出格式
- 工具返回 JSON，你用中文自然表达关键信息
- 用 `create_indicator_card` 创建个性化指标卡片展示数据概览
- 用 `set_dashboard_layout` 配置 Dashboard 布局
```

`xiaoyu/personality.txt` — 机构人格注入模板：

```
## 机构教学配置
{personality_parts}
```

- [ ] **Step 2: 创建 exam_generator 目录和文件**

`exam_generator/system_prompt.txt` — 内容来自 `seed_exam_agent.py` 的 `EXAM_AGENT_PROMPT`（lines 5-49）：

```
你是出题助手，UniMind.ai 的 AI 出题工作台核心 Agent。

## 角色定位
你是一位专业的命题专家，帮助教师通过对话快速生成高质量题目。你是教师端首页的核心交互入口。

## 核心工作流（严格按顺序执行）
1. **理解需求**：从教师对话中提取出题意图——知识点、难度、题型、数量。
2. **搜索知识点**：调用 `search_knowledge_points` 搜索知识点，获取知识点 ID。
3. **立即出题**：拿到知识点 ID 后，**必须立即调用** `generate_questions` 生成题目。不要等待教师确认。
4. **呈现结果**：将题目以清晰格式展示，标注题型、难度、知识点。
5. **精修升级**：教师对质量有更高要求时，建议调用 `launch_arc_pipeline` 进行 4-agent 对抗精修。
6. **入库保存**：教师确认满意后，调用 `save_questions_to_library` 存入题库。

## 重要规则
- **必须出题**：你的核心任务是出题。收到出题需求后，必须调用工具生成题目，不能只搜索或只回复文字。
- **搜索后必须出题**：调用 search_knowledge_points 拿到知识点 ID 后，下一步必须调用 generate_questions。
- **不要等待确认**：教师说出题需求后，直接搜索+出题，不需要先问教师"要不要开始"。
- **搜索无结果时**：如果搜索没有找到匹配的知识点，告诉教师可用的知识点范围，并建议换一个关键词。
- 教师说"出题"就出题，不问多余问题。
- 信息不足时（如未指定知识点），快速追问，一次只问一个关键信息。
- 数学公式用 LaTeX：行内 $...$，行间 $$...$$。
- 语气专业简洁，像一个靠谱的命题专家。

## 对话式指令处理
教师可能用简短的口语化指令，你必须正确理解并执行：
- **"入库""存入题库""保存""存库"** → 调用 `save_questions_to_library`，保存最近一次生成的全部题目。
- **"入库第1、3题""保存前两题"** → 调用 `save_questions_to_library`，传入 `question_indices`。
- **"ARC精修""精修一下""用ARC跑一遍"** → 调用 `launch_arc_pipeline`。
- **"看看进度""管线跑完了吗"** → 调用 `check_pipeline_status`。
- **"再来一组""换XX知识点出题"** → 重新调用 search + generate。
- **"难度改成hard""加到10题"** → 用新参数重新调用 generate_questions。

处理这些指令时，直接调用对应工具，不要反问确认。

## 题目呈现格式
工具返回题目后，用以下格式展示每道题：
- 题号 + 题型标签 + 难度标签 + 知识点名称
- 题干全文
- 客观题列出选项 A/B/C/D
- 答案简要提示

## 与助教/规划师的分工
- 你负责：出题、题目质量把控、ARC 精修、题目入库。
- 助教负责：知识点讲解、题目答疑。
- 规划师负责：学习计划、进度跟踪。
```

`exam_generator/tool_guide.txt` — 从 `chat_service.py:58-79` 提取：

```
## 可用工具（必须使用）
你有以下工具可用，收到出题需求时**必须调用工具**，不能只回复文字：

- `search_knowledge_points`: 搜索知识点获取 ID。出题前必须先调用此工具。
- `generate_questions`: 根据知识点 ID 快速生成题目（同步约 10 秒）。搜索拿到 ID 后**必须立即调用**此工具。
- `launch_arc_pipeline`: 启动 ARC 精修管线（异步 2-5 分钟）。教师要求高质量时使用。
- `check_pipeline_status`: 查询 ARC 管线进度。
- `save_questions_to_library`: 将题目存入题库。教师说"入库""保存""存入题库"时调用。

工作流程（严格遵守）：
1. 收到出题需求 → 调用 search_knowledge_points 获取知识点 ID
2. 拿到知识点 ID → **立即**调用 generate_questions 生成题目
3. 将工具返回的题目用 Markdown 格式呈现给教师
4. 教师说"入库/保存" → 调用 save_questions_to_library

口语化指令识别：
- "入库/存库/保存/存入题库" → save_questions_to_library
- "ARC精修/精修/用ARC跑" → launch_arc_pipeline
- "看看进度/跑完没" → check_pipeline_status
- "再来一组/换XX出题" → 重新 search + generate
- "难度改hard/加到10题" → 用新参数重新 generate

注意：这些指令直接执行，不要反问确认。搜索无结果时告知可用范围。
```

`exam_generator/personality.txt` — 同 xiaoyu 模板。

- [ ] **Step 3: 创建 assistant 目录和文件**

`assistant/system_prompt.txt` — 内容来自 `base_assistant_prompt.txt`（已存在，30 行）：

```
你是 UniMind.ai 的 AI 学术助教，专为大学生提供全学科答疑辅导。你的核心目标是帮助学生真正理解知识，而非替他们完成作业。

## 角色定位
- 你是一位耐心、博学且善于引导的导师，不是答题机器。
- 你的价值在于启发思考、填补认知盲区、帮助学生建立知识体系。
- 面对学生的困惑，优先追问和引导，而非直接输出结论。

## 回答规范
1. **启发性优先**：先理解学生的问题背景和困惑点，用反问或类比帮助其自行推导，再给出结构化讲解。
2. **概念与推导并重**：不仅讲"是什么"，还要讲"为什么"，用逻辑链条串联知识点。
3. **举例说明**：每个抽象概念至少配一个具体例子，优先使用生活场景或经典案例。
4. **分层回答**：先给出简明结论，再展开详细推导，最后总结要点。让学生可以按需阅读。
5. 数学公式用 LaTeX：行内 $...$，行间 $$...$$ 或 \[...\]，公式前后保留空格。
6. 支持 Markdown 排版，合理使用标题、列表、表格、代码块等提升可读性。
7. 语气亲切专业，用"你"称呼学生，营造一对一辅导氛围。

## 能力边界
- 对于超出知识范围或不确定的问题，诚实说明，并推荐可靠的学习资源或替代思路。
- 不代替学生完成会带来学术诚信风险的作业（如代写论文、直接给出考试答案）。
- 涉及医疗、法律、心理危机等专业领域的问题，应明确建议学生寻求专业帮助。

## 学科适配
- 根据学生提问自动识别所属学科，使用该学科的术语体系和思维范式。
- 理科问题重推导过程，文科问题重论证框架，工科问题重实践应用。
- 跨学科问题应指出各学科视角的异同，帮助学生建立融会贯通的理解。

## 交互风格
- 首次回答一个问题时，先简要评估其先验知识水平（如："你之前接触过XX概念吗？"），据此调整讲解深度。
- 当学生表现出困惑时，换一种角度或更基础的层次重新讲解，而非简单重复。
- 鼓励学生追问和质疑，对好的追问给予肯定。
```

`assistant/tool_guide.txt` — 从 `chat_service.py:24-37` 提取：

```
## 可用工具
你可以调用以下工具来获取实时信息，提升回答质量：
- `search_knowledge_tree`: 搜索知识点定义、公式、例题。当学生问概念、定理、公式时，先搜索再回答。
- `get_user_weak_points`: 查看学生薄弱知识点。当学生问'我哪里弱''怎么复习'时使用。
- `get_user_wrong_questions`: 查看学生最近的错题。当学生问'我错在哪''帮我分析'时使用。
- `lookup_question`: 根据题目 ID 查询详情。当学生提到具体题号时使用。
- `get_class_weak_points`: 获取班级最薄弱知识点（仅教师可用）。当教师问'班级哪里弱''学生整体情况'时使用。
- `get_class_performance_summary`: 获取班级整体数据概览（仅教师可用）。当教师问'班级整体表现'时使用。

使用原则：
1. 需要具体数据（知识点内容、学生情况、题目详情）时，先调工具再回答，不要凭记忆编造。
2. 简单问候、闲聊、通用学习建议不需要调工具。
3. 工具返回的数据是 JSON，请将关键信息用中文自然表达。
```

`assistant/personality.txt` — 同 xiaoyu 模板。

- [ ] **Step 4: 验证文件结构**

Run: `find backend/prompts/ai_assistant/bots/ -type f -name "*.txt" | sort`
Expected: 9 files in 3 subdirectories (xiaoyu/, exam_generator/, assistant/)

- [ ] **Step 5: Commit**

```bash
git add backend/prompts/ai_assistant/bots/xiaoyu/ backend/prompts/ai_assistant/bots/exam_generator/ backend/prompts/ai_assistant/bots/assistant/
git commit -m "feat: add structured prompt templates for all 3 bot types"
```

---

## Task 2: 创建 Bot Registry

**Files:**
- Create: `backend/ai_assistant/bot_registry.py`

- [ ] **Step 1: 创建 bot_registry.py**

```python
"""
Bot 注册表：bot_type → (ToolExecutor, tools_factory, prompt_dir, config)。

新增 bot 只需：
1. 写 prompt 文件到 prompts/ai_assistant/bots/{name}/
2. 在 BOT_REGISTRY 加一行
3. （可选）写 ToolExecutor 子类
"""
from dataclasses import dataclass
from typing import Callable


@dataclass
class BotProfile:
    name: str                          # 显示名称
    bot_type: str                      # Bot model 的 bot_type 值
    executor_class: type               # ToolExecutor 子类
    tools_factory: Callable            # get_planner_tools, etc.
    prompt_dir: str                    # prompts 文件目录名
    is_exclusive: bool = False         # 是否注入学生学术数据
    force_tool_choice: bool = False    # 是否强制 tool_choice="required"


def _get_executor_class(bot_type: str):
    """延迟导入 ToolExecutor 子类，避免循环引用。"""
    if bot_type == 'planner':
        from ai_assistant.services.tool_executor import PlannerToolExecutor
        return PlannerToolExecutor
    elif bot_type == 'exam_generator':
        from ai_assistant.services.exam_generator_tool_executor import ExamGeneratorToolExecutor
        return ExamGeneratorToolExecutor
    else:
        from ai_assistant.services.tool_executor import AssistantToolExecutor
        return AssistantToolExecutor


def _get_tools_factory(bot_type: str):
    """延迟导入 tools factory。"""
    if bot_type == 'planner':
        from ai_engine.tools import get_planner_tools
        return get_planner_tools
    elif bot_type == 'exam_generator':
        from ai_engine.tools import get_exam_generator_tools
        return get_exam_generator_tools
    else:
        from ai_engine.tools import get_assistant_tools
        return get_assistant_tools


BOT_REGISTRY: dict[str, BotProfile] = {
    'planner': BotProfile(
        name='小宇',
        bot_type='planner',
        executor_class=None,  # 延迟加载
        tools_factory=None,
        prompt_dir='xiaoyu',
        is_exclusive=True,
        force_tool_choice=True,
    ),
    'exam_generator': BotProfile(
        name='出题助手',
        bot_type='exam_generator',
        executor_class=None,
        tools_factory=None,
        prompt_dir='exam_generator',
        is_exclusive=False,
        force_tool_choice=True,
    ),
    'assistant': BotProfile(
        name='AI 助教',
        bot_type='assistant',
        executor_class=None,
        tools_factory=None,
        prompt_dir='assistant',
        is_exclusive=False,
        force_tool_choice=False,
    ),
}


def get_bot_profile(bot_type: str) -> BotProfile:
    """获取 bot 配置，未知类型 fallback 到 assistant。"""
    profile = BOT_REGISTRY.get(bot_type, BOT_REGISTRY['assistant'])
    # 延迟加载 executor_class 和 tools_factory
    if profile.executor_class is None:
        profile.executor_class = _get_executor_class(profile.bot_type)
    if profile.tools_factory is None:
        profile.tools_factory = _get_tools_factory(profile.bot_type)
    return profile
```

- [ ] **Step 2: 验证 import**

Run: `cd backend && python -c "from ai_assistant.bot_registry import get_bot_profile; p = get_bot_profile('planner'); print(p.name, p.prompt_dir)"`
Expected: `小宇 xiaoyu`

- [ ] **Step 3: Commit**

```bash
git add backend/ai_assistant/bot_registry.py
git commit -m "feat: add bot_registry for unified bot configuration"
```

---

## Task 3: 重写 prompt_sync.py

**Files:**
- Modify: `backend/ai_assistant/prompt_sync.py`

- [ ] **Step 1: 重写 prompt_sync.py**

改为按 bot 名称（prompt_dir）查找目录，支持新的目录结构：

```python
import logging
from pathlib import Path
from typing import Optional

from django.conf import settings


logger = logging.getLogger(__name__)


def _base_dir() -> Path:
    return Path(getattr(settings, 'BASE_DIR', Path(__file__).resolve().parent.parent))


def get_bots_prompt_dir() -> Path:
    path = _base_dir() / 'prompts' / 'ai_assistant' / 'bots'
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_bot_prompt_dir(bot) -> Path:
    """根据 bot 的 bot_type 获取 prompt 目录。"""
    from ai_assistant.bot_registry import get_bot_profile
    profile = get_bot_profile(bot.bot_type)
    return get_bots_prompt_dir() / profile.prompt_dir


def read_prompt_file(bot, filename: str) -> Optional[str]:
    """读取 bot prompt 目录下的指定文件。"""
    path = get_bot_prompt_dir(bot) / filename
    if not path.exists():
        return None
    try:
        return path.read_text(encoding='utf-8').strip()
    except Exception:
        logger.exception('读取 Prompt 文件失败: %s', path)
        return None


def write_prompt_file(bot, filename: str, content: str) -> Path:
    """写入 bot prompt 目录下的指定文件。"""
    dir_path = get_bot_prompt_dir(bot)
    dir_path.mkdir(parents=True, exist_ok=True)
    path = dir_path / filename
    path.write_text(str(content or ''), encoding='utf-8')
    return path


def load_system_prompt(bot) -> str:
    """加载 bot 的完整 system prompt（文件优先，fallback 到 DB）。"""
    content = read_prompt_file(bot, 'system_prompt.txt')
    if content:
        return content
    return bot.system_prompt or '你是UniMind.ai的AI学术助教。'


def load_tool_guide(bot) -> str:
    """加载 bot 的 tool guide。"""
    content = read_prompt_file(bot, 'tool_guide.txt')
    if content:
        return f"\n\n{content}"
    return ''


def load_personality_template(bot) -> str:
    """加载 bot 的 personality 模板。"""
    content = read_prompt_file(bot, 'personality.txt')
    if content:
        return content
    return ''


# 向后兼容：保留旧接口但标记为 deprecated
def get_bot_prompt_path(bot) -> Path:
    """Deprecated: 使用 get_bot_prompt_dir 替代。"""
    return get_bot_prompt_dir(bot) / 'system_prompt.txt'


def read_bot_prompt_file(bot) -> Optional[str]:
    """Deprecated: 使用 read_prompt_file 替代。"""
    return read_prompt_file(bot, 'system_prompt.txt')


def write_bot_prompt_file(bot, content: str) -> Path:
    """Deprecated: 使用 write_prompt_file 替代。"""
    return write_prompt_file(bot, 'system_prompt.txt', content)


def sync_bot_prompt(bot):
    """文件优先覆盖 DB，文件不存在则从 DB 创建文件。"""
    file_content = read_prompt_file(bot, 'system_prompt.txt')
    if file_content is not None:
        if bot.system_prompt != file_content:
            bot.system_prompt = file_content
            bot.save(update_fields=['system_prompt'])
        return
    write_prompt_file(bot, 'system_prompt.txt', bot.system_prompt or '')


def delete_bot_prompt_file(bot):
    """删除 bot 的 prompt 目录。"""
    import shutil
    dir_path = get_bot_prompt_dir(bot)
    if dir_path.exists():
        try:
            shutil.rmtree(dir_path)
        except Exception:
            logger.exception('删除 Prompt 目录失败: %s', dir_path)
```

- [ ] **Step 2: 验证 import**

Run: `cd backend && python -c "from ai_assistant.prompt_sync import load_system_prompt, load_tool_guide; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/ai_assistant/prompt_sync.py
git commit -m "refactor: rewrite prompt_sync to use bot_type-based directory structure"
```

---

## Task 4: 重写 chat_service.py

**Files:**
- Modify: `backend/ai_assistant/services/chat_service.py`

- [ ] **Step 1: 重写 _build_agent_system_prompt 和删除 inline tool guide 方法**

新版 `chat_service.py`，删除 `_build_planner_tool_guide`、`_build_exam_generator_tool_guide` 和 inline tool guide，改用文件加载：

```python
from typing import Dict, Sequence

from ai_engine.tools import get_assistant_tools, get_planner_tools, get_exam_generator_tools


class AssistantChatService:
    @classmethod
    def build_system_prompt(cls, bot, student_context: str = '') -> str:
        """从文件加载 system prompt，fallback 到 DB。"""
        if not bot:
            return '你是UniMind.ai的AI学术助教。'

        from ai_assistant.prompt_sync import load_system_prompt
        prompt = load_system_prompt(bot)

        if bot.is_exclusive:
            prompt = prompt.replace('{student_context}', student_context or '暂无学业画像。')
        return prompt

    @classmethod
    def _build_agent_system_prompt(cls, bot, student_context: str = '', memory_context: str = '', institution=None, adaptive_directives: str = '') -> str:
        """为 Agent 模式构建包含工具使用指引的 system prompt。"""
        base = cls.build_system_prompt(bot, student_context)
        memory_section = f"\n\n{memory_context}" if memory_context else ''

        # 从文件加载 tool guide
        from ai_assistant.prompt_sync import load_tool_guide
        tool_guide = load_tool_guide(bot) if bot else ''

        # Inject institution personality
        personality_section = ''
        if bot and hasattr(bot, 'institution_personality') and bot.institution_personality:
            p = bot.institution_personality
            parts = []
            if p.get('teaching_style'):
                parts.append(f"教学风格：{p['teaching_style']}")
            if p.get('tone'):
                parts.append(f"语气：{p['tone']}")
            if p.get('knowledge_domain'):
                parts.append(f"知识领域：{p['knowledge_domain']}")
            if p.get('custom_instructions'):
                parts.append(p['custom_instructions'])
            if parts:
                personality_section = "\n\n## 机构教学配置\n" + "\n".join(f"- {x}" for x in parts)

        adaptive_section = f"\n\n{adaptive_directives}" if adaptive_directives else ''
        return base + memory_section + tool_guide + personality_section + adaptive_section

    @classmethod
    def chat_with_assistant(
        cls,
        ai,
        bot,
        history_messages: Sequence[Dict[str, str]],
        user_message: str,
        student_context: str = '',
    ):
        system_prompt = cls.build_system_prompt(bot, student_context)

        messages = [{'role': 'system', 'content': system_prompt}]

        for msg in history_messages or []:
            role = str(msg.get('role', '')).strip()
            content = str(msg.get('content', '')).strip()
            if role in {'user', 'assistant'} and content:
                messages.append({'role': role, 'content': content})

        messages.append({'role': 'user', 'content': user_message})

        return ai.call_ai(
            messages,
            temperature=0.6,
            max_tokens=2500,
            operation='assistant.chat',
        )

    @classmethod
    def chat_with_assistant_agent(
        cls,
        bot,
        history_messages: Sequence[Dict[str, str]],
        user_message: str,
        tool_executor,
        student_context: str = '',
        memory_context: str = '',
        on_step=None,
        adaptive_directives='',
    ):
        """Agent 化对话：模型可自主调用工具获取信息后再回答。"""
        from ai_engine.service import AIEngine
        from ai_engine.tool_permissions import filter_tools
        from ai_assistant.bot_registry import get_bot_profile

        institution = getattr(tool_executor, 'institution', None)
        system_prompt = cls._build_agent_system_prompt(bot, student_context, memory_context, institution, adaptive_directives)

        messages = [{'role': 'system', 'content': system_prompt}]

        for msg in history_messages or []:
            role = str(msg.get('role', '')).strip()
            content = str(msg.get('content', '')).strip()
            if role in {'user', 'assistant'} and content:
                messages.append({'role': role, 'content': content})

        messages.append({'role': 'user', 'content': user_message})

        # 从 registry 获取 tools
        profile = get_bot_profile(bot.bot_type if bot else 'assistant')
        tools = profile.tools_factory()

        # Apply tool permission sandbox
        bot_type = bot.bot_type if bot else 'assistant'
        tools = filter_tools(bot_type, institution, tools)

        # Force tool usage for agent bots
        forced_tool_choice = "required" if profile.force_tool_choice else "auto"

        if on_step:
            return AIEngine.call_ai_with_streaming_tools(
                messages=messages,
                tools=tools,
                tool_executor=tool_executor,
                on_step=on_step,
                tool_choice=forced_tool_choice,
                temperature=0.6,
                max_tokens=2500,
                operation='assistant.chat',
                max_tool_rounds=5,
            )
        else:
            return AIEngine.call_ai_with_tools(
                messages=messages,
                tools=tools,
                tool_executor=tool_executor,
                tool_choice=forced_tool_choice,
                temperature=0.6,
                max_tokens=2500,
                operation='assistant.chat',
                max_tool_rounds=5,
            )
```

- [ ] **Step 2: 验证 import**

Run: `cd backend && python -c "from ai_assistant.services.chat_service import AssistantChatService; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/ai_assistant/services/chat_service.py
git commit -m "refactor: replace inline tool guides with file-based prompt loading"
```

---

## Task 5: 创建 chat_dispatch.py 统一调度

**Files:**
- Create: `backend/ai_assistant/services/chat_dispatch.py`

- [ ] **Step 1: 创建 chat_dispatch.py**

```python
"""
统一的 bot 对话调度。

3 个入口（polling/SSE/WS）共用此模块，消除重复的 bot_type if/elif 逻辑。
"""
import logging
from typing import Callable, Optional

from ai_assistant.bot_registry import get_bot_profile

logger = logging.getLogger(__name__)


def create_tool_executor(bot, user):
    """根据 bot_type 创建 ToolExecutor 实例。"""
    profile = get_bot_profile(bot.bot_type if bot else 'assistant')
    return profile.executor_class(user=user)


def create_tools(bot, user, institution=None):
    """根据 bot_type 创建 tools 列表。"""
    from ai_engine.tool_permissions import filter_tools
    profile = get_bot_profile(bot.bot_type if bot else 'assistant')
    tools = profile.tools_factory()
    bot_type = bot.bot_type if bot else 'assistant'
    return filter_tools(bot_type, institution, tools)


def build_system_prompt(bot, user, student_context='', memory_context='', institution=None, adaptive_directives=''):
    """构建完整的 system prompt。"""
    from ai_assistant.services.chat_service import AssistantChatService
    return AssistantChatService._build_agent_system_prompt(
        bot, student_context, memory_context, institution, adaptive_directives
    )


def dispatch_bot_chat(
    bot,
    user,
    message: str,
    history: list,
    institution=None,
    *,
    stream: bool = False,
    on_step: Optional[Callable] = None,
    student_context: str = '',
    memory_context: str = '',
    adaptive_directives: str = '',
):
    """
    统一的 bot 对话调度。

    Args:
        bot: Bot 实例
        user: User 实例
        message: 用户消息
        history: 历史消息列表 [{"role": ..., "content": ...}]
        institution: 机构实例
        stream: 是否流式
        on_step: 流式回调（WebSocket/SSE 用）
        student_context: 学生学术上下文
        memory_context: 记忆上下文
        adaptive_directives: 自适应指令

    Returns:
        dict (polling) 或 Generator (streaming)
    """
    from ai_service import AIService

    # ExamGenerator cache recovery
    tool_executor = create_tool_executor(bot, user)
    if bot and bot.bot_type == 'exam_generator':
        _restore_exam_cache(tool_executor, user, bot)

    if stream and on_step:
        return AIService.chat_with_assistant_agent(
            bot=bot,
            history_messages=history,
            user_message=message,
            tool_executor=tool_executor,
            student_context=student_context,
            memory_context=memory_context,
            on_step=on_step,
            adaptive_directives=adaptive_directives,
        )
    else:
        return AIService.chat_with_assistant_agent(
            bot=bot,
            history_messages=history,
            user_message=message,
            tool_executor=tool_executor,
            student_context=student_context,
            memory_context=memory_context,
            adaptive_directives=adaptive_directives,
        )


def _restore_exam_cache(tool_executor, user, bot):
    """从最近一条助手消息的 metadata 中恢复已生成的题目缓存。"""
    from ai_assistant.models import AIChatMessage
    try:
        last_with_questions = AIChatMessage.objects.filter(
            user=user, bot=bot, role='assistant',
        ).exclude(metadata={}).order_by('-timestamp').first()
        if last_with_questions:
            cached = last_with_questions.metadata.get('generated_questions')
            if cached:
                tool_executor._last_generated = cached
    except Exception:
        pass


def dispatch_bot_chat_sync(
    bot,
    user,
    message: str,
    history: list,
    institution=None,
    *,
    student_context: str = '',
    memory_context: str = '',
    adaptive_directives: str = '',
):
    """
    同步版调度（用于 polling 和 SSE 的 sync 部分）。

    返回 (messages, tools, tool_executor, profile) 供调用方自行调用 AIEngine。
    """
    from ai_engine.tool_permissions import filter_tools

    profile = get_bot_profile(bot.bot_type if bot else 'assistant')
    tool_executor = profile.executor_class(user=user)

    if bot and bot.bot_type == 'exam_generator':
        _restore_exam_cache(tool_executor, user, bot)

    system_prompt = build_system_prompt(bot, user, student_context, memory_context, institution, adaptive_directives)
    messages = [{'role': 'system', 'content': system_prompt}]
    for msg in history:
        if msg['role'] in ('user', 'assistant') and msg['content']:
            messages.append(msg)
    messages.append({'role': 'user', 'content': message})

    tools = profile.tools_factory()
    bot_type = bot.bot_type if bot else 'assistant'
    tools = filter_tools(bot_type, institution, tools)

    return messages, tools, tool_executor, profile
```

- [ ] **Step 2: 验证 import**

Run: `cd backend && python -c "from ai_assistant.services.chat_dispatch import dispatch_bot_chat, dispatch_bot_chat_sync; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/ai_assistant/services/chat_dispatch.py
git commit -m "feat: add chat_dispatch for unified bot chat routing"
```

---

## Task 6: 切换 views.py 到 dispatch

**Files:**
- Modify: `backend/ai_assistant/views.py` (lines 42-57, 369-396)

- [ ] **Step 1: 修改 process_ai_chat（lines 42-57）**

删除 lines 42-57 的 if/elif 块，替换为：

```python
    from ai_assistant.services.chat_dispatch import dispatch_bot_chat

    try:
        with _AI_CHAT_SEMAPHORE:
            res = dispatch_bot_chat(
                bot=bot,
                user=user,
                message=user_message,
                history=history_msgs,
                student_context=student_context,
                memory_context=memory_context,
                adaptive_directives=adaptive_directives,
            )
```

同时删除旧的 import（`from ai_assistant.services.tool_executor import ...`）和 lines 59-61 的 `AIService.chat_with_assistant_agent` 调用。

注意：保留 lines 63-116 的结果处理逻辑不变，但 `tool_executor` 需要从 dispatch 获取。调整方式：让 `dispatch_bot_chat` 返回 `(result, tool_executor)` 元组，或者在 `process_ai_chat` 中单独创建 tool_executor 用于 metadata 提取。

更简洁的做法：修改 `dispatch_bot_chat` 返回 `dict` with `result` and `tool_executor` keys：

```python
def dispatch_bot_chat(...):
    ...
    result = AIService.chat_with_assistant_agent(...)
    return {'result': result, 'tool_executor': tool_executor}
```

然后 `process_ai_chat` 中：

```python
    from ai_assistant.services.chat_dispatch import dispatch_bot_chat

    try:
        with _AI_CHAT_SEMAPHORE:
            dispatch_result = dispatch_bot_chat(
                bot=bot, user=user, message=user_message,
                history=history_msgs, student_context=student_context,
                memory_context=memory_context, adaptive_directives=adaptive_directives,
            )
            res = dispatch_result['result']
            tool_executor = dispatch_result['tool_executor']
```

- [ ] **Step 2: 修改 _sync_setup（lines 369-396）**

删除 lines 369-396 的两个 if/elif 块（executor 选择 + tools 选择），替换为：

```python
            from ai_assistant.services.chat_dispatch import dispatch_bot_chat_sync

            messages, tools, tool_executor, profile = dispatch_bot_chat_sync(
                bot=bot,
                user=request.user,
                message=user_message,
                history=history_msgs,
                student_context=student_context,
                memory_context=memory_context,
                adaptive_directives=adaptive_directives,
            )
```

删除 lines 378-386 的手动 prompt 构建和 messages 组装（已包含在 `dispatch_bot_chat_sync` 中）。

- [ ] **Step 3: 验证**

Run: `cd backend && python -c "from ai_assistant.views import process_ai_chat; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/ai_assistant/views.py
git commit -m "refactor: switch views.py to use chat_dispatch"
```

---

## Task 7: 切换 consumers.py 到 dispatch

**Files:**
- Modify: `backend/ai_assistant/consumers.py` (lines 123-149)

- [ ] **Step 1: 修改 _run_agent 中的 dispatch 逻辑**

删除 lines 123-138 的 if/elif 块和 line 141 的 `AIService.chat_with_assistant_agent` 调用，替换为：

```python
            from ai_assistant.services.chat_dispatch import dispatch_bot_chat

            result = dispatch_bot_chat(
                bot=self.bot,
                user=self.user,
                message=message,
                history=history_msgs,
                institution=getattr(self, 'institution', None),
                stream=True,
                on_step=on_step,
                student_context=student_context,
                memory_context=memory_context,
            )
```

保留 lines 151-170 的结果处理和记忆提取逻辑不变。

- [ ] **Step 2: 验证**

Run: `cd backend && python -c "from ai_assistant.consumers import AgentChatConsumer; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/ai_assistant/consumers.py
git commit -m "refactor: switch consumers.py to use chat_dispatch"
```

---

## Task 8: 更新 seed 命令

**Files:**
- Modify: `backend/ai_assistant/management/commands/seed_xiaoyu.py`
- Modify: `backend/ai_assistant/management/commands/seed_exam_agent.py`

- [ ] **Step 1: 重写 seed_xiaoyu.py**

删除 lines 5-78 的 `XIAOYU_PROMPT` 硬编码字符串，改为从文件读取：

```python
from django.core.management.base import BaseCommand
from ai_assistant.models import Bot


class Command(BaseCommand):
    help = '创建或更新小宇（XiaoYu）学习规划师 Bot'

    def handle(self, *args, **options):
        from ai_assistant.prompt_sync import load_system_prompt, sync_bot_prompt

        # 先创建/获取 bot 记录
        bot, created = Bot.objects.update_or_create(
            name='小宇',
            defaults={
                'bot_type': 'planner',
                'system_prompt': '',  # 由 sync_bot_prompt 从文件填充
                'is_exclusive': True,
                'is_active': True,
                'institution': None,
            },
        )

        # 从文件同步 prompt 到 DB
        sync_bot_prompt(bot)

        action = 'Created' if created else 'Updated'
        self.stdout.write(self.style.SUCCESS(
            f'{action} 小宇 bot (id={bot.id}, type={bot.bot_type})'
        ))
```

- [ ] **Step 2: 重写 seed_exam_agent.py**

同理，删除硬编码 prompt：

```python
from django.core.management.base import BaseCommand
from ai_assistant.models import Bot


class Command(BaseCommand):
    help = '创建或更新出题助手 Bot'

    def handle(self, *args, **options):
        from ai_assistant.prompt_sync import sync_bot_prompt

        bot, created = Bot.objects.update_or_create(
            name='出题助手',
            defaults={
                'bot_type': 'exam_generator',
                'system_prompt': '',  # 由 sync_bot_prompt 从文件填充
                'is_exclusive': False,
                'is_active': True,
                'institution': None,
            },
        )

        sync_bot_prompt(bot)

        action = 'Created' if created else 'Updated'
        self.stdout.write(self.style.SUCCESS(
            f'{action} 出题助手 bot (id={bot.id}, type={bot.bot_type})'
        ))
```

- [ ] **Step 3: 验证**

Run: `cd backend && python -c "from ai_assistant.management.commands.seed_xiaoyu import Command; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/ai_assistant/management/commands/seed_xiaoyu.py backend/ai_assistant/management/commands/seed_exam_agent.py
git commit -m "refactor: seed commands read prompts from files instead of hardcoded strings"
```

---

## Task 9: 清理废弃文件

**Files:**
- Delete: `backend/prompts/ai_assistant/base_assistant_prompt.txt`
- Delete: `backend/prompts/ai_assistant/bots/bot_1_prompt.txt`
- Delete: `backend/prompts/ai_assistant/bots/bot_2_prompt.txt`
- Delete: `backend/prompts/ai_assistant/bots/bot_3_prompt.txt`
- Delete: `backend/prompts/ai_assistant/bots/bot_4_prompt.txt`
- Delete: `backend/prompts/ai_assistant/bots/bot_5_prompt.txt`

- [ ] **Step 1: 删除废弃文件**

```bash
rm backend/prompts/ai_assistant/base_assistant_prompt.txt
rm backend/prompts/ai_assistant/bots/bot_1_prompt.txt
rm backend/prompts/ai_assistant/bots/bot_2_prompt.txt
rm backend/prompts/ai_assistant/bots/bot_3_prompt.txt
rm backend/prompts/ai_assistant/bots/bot_4_prompt.txt
rm backend/prompts/ai_assistant/bots/bot_5_prompt.txt
```

- [ ] **Step 2: 验证目录结构**

Run: `find backend/prompts/ai_assistant/bots/ -type f | sort`
Expected: 只有 xiaoyu/, exam_generator/, assistant/ 下的 9 个文件

- [ ] **Step 3: Commit**

```bash
git add -A backend/prompts/ai_assistant/
git commit -m "cleanup: remove deprecated prompt files (bot_N_prompt.txt, base_assistant_prompt.txt)"
```

---

## Task 10: 全量验证

- [ ] **Step 1: backend check**

Run: `make backend-check`
Expected: 无错误

- [ ] **Step 2: 验证 prompt 文件可读**

Run: `cd backend && python -c "
from ai_assistant.bot_registry import get_bot_profile
from ai_assistant.prompt_sync import load_system_prompt, load_tool_guide
from ai_assistant.models import Bot

# 验证 registry
for bt in ['planner', 'exam_generator', 'assistant']:
    p = get_bot_profile(bt)
    print(f'{bt}: name={p.name}, dir={p.prompt_dir}, force_tool={p.force_tool_choice}')
"`
Expected:
```
planner: name=小宇, dir=xiaoyu, force_tool=True
exam_generator: name=出题助手, dir=exam_generator, force_tool=True
assistant: name=AI 助教, dir=assistant, force_tool=False
```

- [ ] **Step 3: 验证 chat_service import chain**

Run: `cd backend && python -c "
from ai_assistant.services.chat_service import AssistantChatService
from ai_assistant.services.chat_dispatch import dispatch_bot_chat, dispatch_bot_chat_sync
print('All imports OK')
"`
Expected: `All imports OK`

- [ ] **Step 4: Commit final**

```bash
git add -A
git commit -m "chore: agent structure simplification complete"
```
