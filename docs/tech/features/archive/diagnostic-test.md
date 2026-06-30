# 学生诊断测试

## 概述

学生诊断测试是新学生首次登录时的强制流程：通过 10 道题快速评估学生的知识掌握水平，初始化 Memorix 记忆调度参数，生成个性化学习建议。

## 流程

```
学生首次登录 → HomeRedirect 检测 has_completed_initial_assessment
  → 未完成 → /diagnostic（全屏，无 sidebar）
    → 点击开始 → 从题库随机抽取 10 道客观题（POST /api/users/me/diagnostic/generate/）
    → 答题（5 分钟倒计时）
    → 提交（POST /api/users/me/diagnostic/submit/）
    → 结果页（强弱项分析 + 学习计划建议）
    → "回到首页" / "开始练习"
```

## 后端

### 诊断服务

`quizzes/services/diagnostic_service.py`

#### 生成题目

```python
generate_diagnostic_questions(institution) -> list[dict]
```

从数据库现有题库随机抽取，**不调用 AI 生成**（避免超时）：
1. 优先从机构题库取 `q_type='objective'` 且有 `correct_answer` 的题目
2. 不够则从全局题库补
3. 返回前端格式的 dict 列表（`question_text`, `options`, `answer`, `knowledge_point_id`）

#### 评分

```python
grade_diagnostic_answers(user, answers: list[dict]) -> (results, kp_scores)
```

- 客观题：精确匹配 `correct_answer`（upper + strip）
- 主观题：调用 AI 判分（`AIEngine.call_ai()` + grading prompt）
- 返回 `(results_list, kp_scores_dict)`

#### Memorix 初始化

```python
initialize_memorix_from_diagnostic(user, kp_scores)
```

| 答题结果 | stability | next_review_at |
|----------|-----------|----------------|
| 答对（≥60%） | 5.0 | now + 3 天 |
| 答错（<60%） | 1.0 | now + 1 天 |

同时更新 `UserKnowledgeState.mastery_score`。

#### 学习计划

```python
build_study_plan(kp_scores) -> dict
```

返回 `{weak_kps: [...], strong_kps: [...], recommendation: "..."}`

### API 端点

| Method | Path | 说明 |
|--------|------|------|
| POST | `/api/users/me/diagnostic/generate/` | 从题库抽取诊断题（已评估则 400，需 `IsMember`） |
| POST | `/api/users/me/diagnostic/submit/` | 提交答案 + 评分 + 初始化 Memorix |

`submit` 完成后设置 `user.has_completed_initial_assessment = True`，前端同步更新 auth store。

### 路由守卫

`frontend/src/App.tsx` — `HomeRedirect`

```typescript
if (user?.institution_role === 'student' && !user?.has_completed_initial_assessment)
  return <Navigate to="/diagnostic" replace />;
```

诊断完成后前端调用 `updateUser({ has_completed_initial_assessment: true })` 同步状态，避免死循环。

## 前端

`frontend/src/pages/DiagnosticTest.tsx`

三阶段全屏页面（ Lovart 风格布局，无 sidebar）：
1. **欢迎页**：居中图标 + 统计数据 + 开始按钮
2. **答题页**：逐题作答，5 分钟倒计时，细进度条，圆角选项卡片
3. **结果页**：居中大号百分比 + 强弱项分类卡片 + "回到首页"/"开始练习"双按钮

## 权限

端点需要 `IsMember` 权限（付费会员或管理员）。新用户需由机构授予会员身份后才能访问。

## 迁移

依赖 `users` app 的 `has_completed_initial_assessment` 字段（已存在于 User 模型）。
