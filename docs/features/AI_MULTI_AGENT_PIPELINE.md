# AI 出题多智能体管线设计 (AI Multi-Agent Pipeline)

## 1. 背景与动机
目前系统的 AI 出题功能（`backend/quizzes/ai_workflow.py`）依赖于单个 LLM（如单一 Prompt）一次性完成题目生成、格式化和审核。
这存在明显的缺陷：
1. **幻觉与错误**：容易生成逻辑漏洞、LaTeX 语法错误（如公式未闭合）。
2. **难度失控**：单模型难以兼顾“知识点准确性”和“干扰项的迷惑性”。
3. **超纲风险**：生成的题目可能偏离 431 考研大纲。

为了提升题库质量，我们将管线升级为**多智能体对抗评估系统 (Multi-Agent Adversarial System)**。

## 2. 智能体角色定义 (Agent Roles)

我们将出题过程拆解为 4 个协作的 AI 专家：

### Agent 1: 出题专家 (Generator)
- **职责**：根据给定的 `KnowledgePoint` 和知识点上下文，起草题干 (Stem) 和正确答案。
- **要求**：富有创造力，紧贴 431 大纲。
- **推荐模型**：成本较低的高吞吐模型（如 GPT-3.5, GLM-4-Flash, DeepSeek-V2）。

### Agent 2: 干扰项专家 (Distractor Expert)
- **职责**：专门针对选择题，根据正确答案和常见考研陷阱（如偷换概念、符号错误），生成极具迷惑性的错误选项。
- **输入**：Agent 1 生成的题干和正确答案。
- **输出**：完整的 A, B, C, D 选项及其陷阱解析。

### Agent 3: 审核教研员 (Reviewer / Critic)
- **职责**：作为系统的守门员，执行对抗性评估。它拥有“一票否决权”。
- **检查清单**：
  1. 逻辑与事实是否绝对正确？
  2. LaTeX 公式是否规范（必须使用 `$公式$` 或 `$$公式$$`，不能出现语法解析错误）？
  3. 是否偏离 431 大纲？
  4. 难度是否适合研究生入学考试？
- **输出**：`{"passed": true/false, "reason": "...", "suggested_fix": "..."}`。
- **推荐模型**：强推理模型（如 GPT-4o, Claude 3.5 Sonnet）。

### Agent 4: 归类与标签员 (Taxonomist)
- **职责**：当题目被 Agent 3 通过后，对其进行入库前的最后加工。
- **工作内容**：
  1. 评估初始 ELO 难度（如 1200）。
  2. 标注认知层级（记忆 / 理解 / 应用 / 分析）。
  3. 输出最终符合系统要求的严格 JSON 格式。

## 3. 工作流与状态机 (Workflow & State Machine)

系统将采用类似 LangGraph 形式的循环状态机：

1. **[Start]** 用户/定时任务发起出题请求，指定知识点。
2. **[Node: Generate]** Agent 1 生成草稿。
3. **[Node: Add Distractors]** Agent 2 补充干扰项。
4. **[Node: Review]** Agent 3 进行对抗审查。
   - 如果审查 `passed == true`，进入 **[Node: Taxonomy]**。
   - 如果审查 `passed == false`，携带 `reason` 返回 **[Node: Generate]** 重写。
   - **循环限制**：设定最大重试次数（如 3 次），超过则抛出异常，防止死循环消耗 Token。
5. **[Node: Taxonomy]** Agent 4 整理格式。
6. **[End]** 将最终 JSON 存入 `Question` 数据库。

## 4. 架构落地与代码结构

由于 Django 已经集成了 Celery，多智能体管线可以作为一个串行的 Celery Task Chain 来实现：

```python
# backend/quizzes/services/multi_agent_builder.py
from celery import chain

def trigger_ai_question_generation(knowledge_point_id):
    """触发多智能体出题管线"""
    workflow = chain(
        agent_generate_draft.s(knowledge_point_id),
        agent_add_distractors.s(),
        agent_review_and_loop.s(max_retries=3), # 内部包含重试逻辑
        agent_taxonomy_and_save.s()
    )
    workflow.apply_async()
```

## 5. 带来的业务价值
1. **题库零人工审核**：通过强力 Reviewer 模型，实现生成的题目直接进入生产环境（至少是试运行环境）。
2. **丰富解析**：Distractor Expert 可以自动为每个错误选项生成“为什么你选了这个会错”的解释，完美契合前面提到的 RAG 个性化解析。
