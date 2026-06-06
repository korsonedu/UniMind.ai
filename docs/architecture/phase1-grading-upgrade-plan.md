# Phase 1：测评引擎升级 — 实施计划

> 日期：2026-06-06
> 目标：让每次评分同时输出错因分析，错因持久化到 Memorix，复习时被引用

## 改动清单

| # | 类型 | 文件 | 说明 |
|---|------|------|------|
| 1 | Prompt | `prompts/grading/` (待确认确切路径) | grade_question 扩展：评分 + 错因 |
| 2 | Model | `quizzes/models.py` | UserQuestionStatus 加字段 |
| 3 | Migration | `quizzes/migrations/` | 新增字段的 migration |
| 4 | Handler | `ai_assistant/services/tool_executor.py` | grade 后写入错因 |
| 5 | Handler | `ai_assistant/services/tool_executor.py` | due_reviews 附带 error_type |

---

## 1. grade_question Prompt 扩展

### 现有输出

```json
{
  "score": 6.0,
  "max_score": 10.0,
  "feedback": "回答基本正确，但在公式应用上有误...",
  "analysis": "学生将 sin²x+cos²x=1 误记为..."
}
```

### 扩展后输出

```json
{
  "score": 6.0,
  "max_score": 10.0,
  "is_correct": false,
  "feedback": "...",
  "analysis": "...",
  "error_analysis": {
    "type": "concept_error",
    "reasoning": "将 sin²x+cos²x=1 误记为 sin²x-cos²x=1，属于公式记忆混淆",
    "suggested_focus": "复习三角函数基本恒等式，重点区分符号"
  }
}
```

### 错因类型

| type | 含义 | 判定条件 |
|------|------|---------|
| `concept_error` | 概念/公式错误 | 用错公式、混淆概念、理解偏差 |
| `calculation_error` | 计算失误 | 思路正确但计算步骤出错 |
| `careless_mistake` | 审题/粗心 | 漏看条件、抄错数字、单位错误 |

### Prompt 追加内容

```
## 错因分析

如果学生回答有误（score < max_score * 0.6），请追加 error_analysis 字段：
- type: "concept_error" | "calculation_error" | "careless_mistake"
- reasoning: 具体分析错因，引用学生的错误点和正确答案的对比
- suggested_focus: 一句话建议学生应该强化什么

如果回答完全正确或接近正确（score >= max_score * 0.6），error_analysis 为 null。

注意：不要为了分类而生搬硬套。如果无法明确判断，type 可以用 reasoning 描述，type 留空。
```

### 找到 grade_question 的位置

```bash
grep -r "grade_question" quizzes/services/ --include="*.py" -l
```

---

## 2. UserQuestionStatus 字段扩展

### Model 新增字段

```python
# quizzes/models.py

class UserQuestionStatus(models.Model):
    # ... 现有字段 ...

    # Phase 1 新增
    error_type = models.CharField(
        max_length=32,
        blank=True,
        default='',
        help_text='错因类型: concept_error / calculation_error / careless_mistake'
    )
    error_metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text='错因详情: {reasoning, suggested_focus, graded_at}'
    )
```

### Migration

```bash
python manage.py makemigrations quizzes --name add_error_analysis_to_userquestionstatus
```

### 注意事项

- `error_type` 用 CharField（不用 choice），方便后续扩展
- `error_metadata` 用 JSONField，存储 reasoning + suggested_focus + graded_at
- 两个字段都允许为空（老数据没有错因分析）

---

## 3. grade 后写入错因

### 位置

`ai_assistant/services/tool_executor.py` → `PlannerToolExecutor._handle_grade_student_answer`

### 当前代码逻辑

```python
def _handle_grade_student_answer(self, args):
    # ... grade_question 调用 ...
    result = QuizAITaskService.grade_question(...)
    return {
        "question_id": question_id,
        "score": result.get('score', 0),
        ...
    }
```

### 修改后

```python
def _handle_grade_student_answer(self, args):
    # ... grade_question 调用 ...
    result = QuizAITaskService.grade_question(...)

    # Phase 1: 写入错因到 UserQuestionStatus
    error_analysis = result.get('error_analysis')
    if error_analysis and error_analysis.get('type'):
        try:
            from quizzes.models import UserQuestionStatus
            uqs = UserQuestionStatus.objects.filter(
                user=self.user, question_id=question_id
            ).first()
            if uqs:
                uqs.error_type = error_analysis['type']
                uqs.error_metadata = {
                    'reasoning': error_analysis.get('reasoning', ''),
                    'suggested_focus': error_analysis.get('suggested_focus', ''),
                    'graded_at': timezone.now().isoformat(),
                }
                uqs.save(update_fields=['error_type', 'error_metadata'])
        except Exception:
            pass  # 不影响评分主流程

    return {
        "question_id": question_id,
        "score": result.get('score', 0),
        "error_analysis": error_analysis,  # 传给 LLM 做自然语言分析
        ...
    }
```

### 设计决策

- 错因写入在 `_handle_grade_student_answer` 内部完成，不新建独立工具
- 写入失败不影响评分返回（try/except + pass）
- `error_analysis` 同时返回给 LLM，让小宇在回复中引用

---

## 4. due_reviews 附带 error_type

### 位置

`ai_assistant/services/tool_executor.py` → `PlannerToolExecutor._handle_get_due_reviews`

### 当前返回

```python
{
    "question_id": d.question_id,
    "question_text": ...,
    "kp_name": ...,
    "memorix_priority": ...,
    ...
}
```

### 修改后

在 reviews 字典中追加：

```python
{
    "question_id": d.question_id,
    "question_text": ...,
    "kp_name": ...,
    "memorix_priority": ...,
    # Phase 1 新增
    "error_type": d.error_type or '',      # 空字符串 = 无错因
    "error_metadata": d.error_metadata or {},
    ...
}
```

### LLM 行为预期

小宇在 tool_guide 中已有引用记忆上下文的规则。加上 error_type 后，小宇看到错因标签自然会引用：

> "这道题你上次做错了，原因是符号混淆（公式符号记反），这次注意区分。"

不需要改 system_prompt——现有的「记忆串联」和「深度分析」原则已覆盖。

---

## 验证方式

### 1. 本地测试

```bash
# 跑单元测试
python manage.py test quizzes.tests -k grade
python manage.py test ai_assistant.tests

# 手动测试
# 1. 找一道有正确答案的题
# 2. 用 grade_student_answer 工具提交一个错误答案
# 3. 检查返回值是否包含 error_analysis
# 4. 检查 UserQuestionStatus 表是否写入了 error_type
```

### 2. 回归检查

- 正常评分功能不受影响
- error_analysis 为 null 时（正确答题）不写任何东西
- 旧数据（无 error_type 字段）的 due_reviews 正常返回
- migration 可逆

### 3. 前端

- 无改动。`error_analysis` 由 LLM 消费，前端不直接渲染。

---

## 风险点

| 风险 | 缓解 |
|------|------|
| LLM 错因分类不准 | 3 种粗分类 + reasoning 字段兜底 |
| grade_question prompt 变长导致延迟 | 仅在 score < 60% 时追加 error_analysis，正确时不额外消耗 |
| migration 锁表 | JSONField default=dict + blank=True，字段允许为空，对现有数据无影响 |
| error_metadata 过大 | 限制 reasoning 200 字，suggested_focus 50 字 |

---

## 不做的事

- ❌ 不新建 service 文件（改动全部在现有文件中）
- ❌ 不改前端
- ❌ 不改 Memorix 调度逻辑（lapse 已自动缩短间隔）
- ❌ 不做变式题匹配（Phase 1.5）
- ❌ 不建新的 LLM 调用（错因分析和评分是同一个调用）
