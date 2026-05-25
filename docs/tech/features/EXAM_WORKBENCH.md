# AI 出题工作台

## 概述

AI 出题工作台是老师/机构主的核心工作界面，集成 ARC 4-Agent 对抗出题管线（Author→Reviewer→AuthorRevise→Classifier）。采用三栏布局：左侧模板选择、中间题目白板（配置→进度→结果三态切换）、右侧 Agent 对话（v2）。

## 页面布局

```
┌──────────────┬────────────────────────────────┬──────────────────┐
│ 左侧栏 w-64  │ 中间白板 flex-1                │ 右侧 w-72        │
│              │                                │                  │
│ 模板列表     │ 空闲: 出题配置表单              │ v2: AI 助手对话  │
│ 最近任务     │ 运行: ARC 进度 stepper          │ 当前: 占位符     │
│              │ 完成: 题目审核卡片列表           │                  │
└──────────────┴────────────────────────────────┴──────────────────┘
```

## 核心流程

### 启动 ARC 管线

```
POST /api/quizzes/admin/adversarial-pipeline/
```

请求参数：
```json
{
  "kp_ids": [1, 2, 3],
  "questions_per_kp": 3,
  "difficulty": "normal",
  "types": ["objective", "subjective:short"],
  "title": "期中模拟卷 - 微积分"
}
```

返回：`{"task_id": 42, "status": "running"}`

### 轮询进度

```
GET /api/quizzes/workbench/tasks/{task_id}/status/
```

轻量端点，不含 result 大字段。返回：
```json
{
  "id": 42,
  "status": "running",
  "progress": 70,
  "title": "期中模拟卷 - 微积分",
  "current_stage": "review_done",
  "status_text": "Reviewer 完成，8 道题通过 (1-2 轮分布)",
  "stages": [
    {"stage": "author_generated", "count": 10},
    {"stage": "review_completed", "count": 8}
  ]
}
```

### 进度阶段映射

| current_stage | progress | 前端显示 |
|---------------|----------|---------|
| `author_start` | 5% | Author 正在生成候选题目... |
| `author_done` | 30% | Author 生成了 N 道候选题目 |
| `review_start` | 40% | Reviewer 正在逐题评审... |
| `review_done` | 70% | Reviewer 完成评审 |
| `classify_start` | 75% | Classifier 正在审计... |
| `classify_batch` | 85% | Classifier 正在生成多样性报告... |
| `classify_done` | 95% | 审计完成 |
| `completed` | 100% | 展示结果 |

### 审核入库

管线完成后自动创建 `status='review'` 的审核任务（`payload.source_task_id` = 生成任务 ID）。

```
GET /api/quizzes/admin/pipeline-review/     → 查找审核任务
POST /api/quizzes/admin/pipeline-review/{id}/  → 批准/拒绝
```

批准请求：
```json
{
  "action": "approve",
  "question_indices": [0, 2, 3]
}
```

`save_confirmed_questions()` 自动绑定 `institution=request.user.institution`，题目入库。

## 教师任务列表

```
GET /api/quizzes/workbench/tasks/
```

返回当前教师的最近 20 个出题任务（`created_by=request.user, task_type='ai_generate'`）。

## 前端组件

| 组件 | 文件 | 说明 |
|------|------|------|
| Workbench | `pages/Workbench.tsx` | 主页面，三栏布局 + 三态切换 |
| TemplateSidebar | `pages/workbench/TemplateSidebar.tsx` | 模板卡片列表 + 最近任务 |
| LaunchConfig | `pages/workbench/LaunchConfig.tsx` | KP 搜索 + 难度/题型/数量 + 启动按钮 |
| PipelineProgress | `pages/workbench/PipelineProgress.tsx` | 4 阶段 stepper + 实时进度条 |
| QuestionResults | `pages/workbench/QuestionResults.tsx` | 题目网格 + 批量操作栏 |
| QuestionReviewCard | `pages/workbench/QuestionReviewCard.tsx` | 单题展示（ARC 元数据 + 详情展开） |

## 路由

- 路径：`/workbench`
- 权限：`RequireInstitution`（teacher/owner/admin）
- HomeRedirect：teacher/owner → `/workbench`（所有方案级别）
- 侧边栏：institution admin 首位入口

## 集成：ClassPerformancePanel → 工作台

班级分析面板的"针对出题"按钮跳转 `/workbench?kp={id}`，工作台自动预选该知识点。

## 相关模型

- `ExamTemplate` — 出题模板（见模板预设系统）
- `ContentPipelineTask` — 异步任务跟踪
- `AgentMemory` — 教师记忆（注入 Agent 上下文）
- `Question` — 生成的题目

## ARC 管线详情

见 [AI_MULTI_AGENT_PIPELINE.md](./AI_MULTI_AGENT_PIPELINE.md)
