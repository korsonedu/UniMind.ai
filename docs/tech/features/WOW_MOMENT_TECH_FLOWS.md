# UniMind 核心功能技术流程图

> 6 个主打 wow moment 的技术架构、数据流、消息协议。Mermaid 格式，可直接渲染。

---

## 一、多步可见 Agent（Multi-Step Visible Agent）

### 技术架构

出题助手（exam_generator）和小宇（planner）升级为多步可见 Agent——Agent 的每一步 tool call 实时推送到前端，文本回复逐 token 流式输出。

| Bot | 通信方式 | 端点 | 原因 |
|-----|----------|------|------|
| exam_generator | WebSocket | `ws/ai/chat/<bot_id>/` | 教师端，需持久连接 |
| planner (小宇) | SSE | `POST /api/ai/chat/stream/` | 学生端，复用 HTTP 基础设施 |
| assistant | HTTP Polling | `POST /api/ai/chat/` | 保持现有简单模式 |

### 消息协议

**客户端 → 服务端：**

```typescript
{ message: string; bot_id: number }
```

**服务端 → 客户端（4 种事件）：**

```typescript
// 步骤事件 — 同一个 call_id 发两次：calling → done
{
  type: "step";
  call_id: string;          // tool call 唯一 ID
  step: number;             // 第几轮（从 1 开始）
  status: "calling" | "done";
  name: string;             // tool 名称
  label: string;            // 中文描述，如 "检索「导数」相关知识点"
  args_summary?: string;    // 参数 JSON（可选，前端折叠显示）
  result_summary?: string;  // 结果摘要（仅 status=done）
}

// 文本 token — 逐字符流式
{ type: "text_delta"; delta: string }

// 完成事件 — 携带完整最终文本
{ type: "done"; full_content: string }

// 错误事件
{ type: "error"; message: string }
```

### 技术流程

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend (React)                         │
│                                                                 │
│  useAgentChat(botId) — WebSocket hook                           │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐           │
│  │  steps[] │ │ streaming│ │ isDone   │ │isConnected│          │
│  │          │ │ Text     │ │          │ │          │           │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘           │
│       │                          │                              │
│       ▼                          ▼                              │
│  AgentStepCard × N         <ChatMessage />                      │
│  ✓ 检索「导数」知识点        "首先，导数的定义是..."              │
│  ⟳ 生成 5 道题...                                              │
│  ○ 启动 ARC 审查                                               │
└────────────────────────┬────────────────────────────────────────┘
                         │ ws://host/ws/ai/chat/{bot_id}/
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Backend (Django Channels)                     │
│                                                                 │
│  AgentChatConsumer (AsyncWebsocketConsumer)                     │
│    │                                                            │
│    ├─ 1. 保存用户消息到 DB                                      │
│    ├─ 2. 加载最近 10 条历史                                     │
│    ├─ 3. 选择 ToolExecutor (planner / exam_gen)                 │
│    │                                                            │
│    ▼                                                            │
│  call_ai_with_streaming_tools(on_step=callback)                 │
│    for round in max(5):                                         │
│      ├─ 流式解析 LLM 响应                                       │
│      │                                                          │
│      ├─ if tool_call:                                           │
│      │    ├─ on_step(step_calling) → WS push step 事件          │
│      │    ├─ ToolExecutor.execute_tool()                        │
│      │    └─ on_step(step_done) → WS push step 事件             │
│      │                                                          │
│      └─ if text:                                                │
│           └─ on_step(text_delta) → WS push text_delta 事件      │
│                                                                 │
│    ├─ on_step(done) → WS push done 事件                         │
│    ├─ 保存最终消息到 DB                                         │
│    └─ 异步提取记忆（结构化 + mem0 语义）                        │
└─────────────────────────────────────────────────────────────────┘
```

### Step Label 映射（动态生成）

| tool_name | label |
|-----------|-------|
| `search_knowledge_tree` | 检索「{query}」相关知识点 |
| `get_user_wrong_questions` | 查看{subject}错题 |
| `generate_questions` | 基于 {n} 个知识点生成 {m} 道题 |
| `launch_arc_pipeline` | 启动题目审查（ARC 管线） |
| `get_learning_stats` | 获取学习统计数据 |
| `get_due_reviews` | 查询未来 7 天的复习任务 |
| `search_courses` | 搜索课程「{query}」 |
| `create_indicator_card` | 创建自定义指标卡片 |

### 一次完整请求的数据流

```
用户输入 "帮我出 5 道导数题"
  │
  ▼
WS 发送 {message: "帮我出 5 道导数题", bot_id: 5}
  │
  ▼
AgentChatConsumer.receive()
  ├─ 保存用户消息 → AIChatMessage
  ├─ 加载最近 10 条历史 → messages[]
  ├─ 选择 ExamGeneratorToolExecutor
  │
  ▼
call_ai_with_streaming_tools(on_step=callback)
  │
  ├─ Round 1: LLM 流式返回 → tool_call: search_knowledge_tree
  │   ├─ WS: step(calling) "检索「导数」相关知识点"
  │   ├─ 执行 ORM 查询
  │   └─ WS: step(done) + result_summary
  │
  ├─ Round 2: LLM 流式返回 → tool_call: generate_questions
  │   ├─ WS: step(calling) "基于 3 个知识点生成 5 道题"
  │   ├─ 调用 AI 出题
  │   └─ WS: step(done) + result_summary
  │
  ├─ Round 3: LLM 流式返回 → text content
  │   ├─ WS: text_delta "好"
  │   ├─ WS: text_delta "的"
  │   ├─ WS: text_delta "，"
  │   └─ ... (逐 token)
  │
  └─ 无更多 tool_call
      ├─ WS: done(full_content)
      ├─ 保存最终消息 → AIChatMessage
      └─ 异步提取记忆
```

---

## 二、4-Agent ARC 对抗出题管线

### 技术架构

4 个 AI Agent 迭代博弈，单次 LLM 出题通过率约 60%，ARC 管线 85%+。

```
Author → Reviewer → AuthorRevise → Classifier
  ↑                       ↓              │
  └─── 最多 3 轮迭代 ──────┘              │
                                          ▼
                                    审核队列 → 批次多样性报告
```

### 四角色定义

| 角色 | 模型分级 | 调用模式 | 职责 |
|------|----------|----------|------|
| Author | FALLBACK_FAST | structured_output | 根据知识点+目标难度+题型生成候选题 |
| Reviewer | FALLBACK_PRO | simple_chat_text + thinking(high) | 三维质量评分（唯一开 thinking 的 Agent） |
| AuthorRevise | FALLBACK_FAST | structured_output | 根据 Reviewer 反馈逐条修正，不改难度 |
| Classifier | FALLBACK_FAST | structured_output | 三层审计：答案正确性+难度合规+知识标签 |

### Reviewer 三维评分

| 维度 | 说明 | 门禁 |
|------|------|------|
| discrimination | 区分度：能否区分掌握者和未掌握者 | — |
| clarity | 表述清晰度：题干无歧义，选项互斥 | — |
| coverage | 知识覆盖度：命中目标知识点核心内容 | — |
| **综合 score** | (d + c + cv) / 3 | **< 0.7 → 退回** |
| **任一维度** | — | **< 0.4 → 硬性不通过** |

### 难度外生控制

难度由人工在前端选择，贯穿全管线，AI 不得自行修改：

| 难度 | 定义 |
|------|------|
| entry | 概念识记，纯记忆型，单步结论 |
| easy | 基础理解 + 1-2 步直接推理 |
| normal | 概念+情境结合，2-3 步推理 |
| hard | 跨章节或多模型联动，≥3 步严谨推理 |
| extreme | 高压综合题，模型选择/条件变化/现实约束 |

### 技术流程

```
┌──────────────────────────────────────────────────────────────────┐
│                    ARC 对抗出题管线                                │
│                                                                  │
│  输入: {knowledge_points, difficulty, question_type, count}       │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ Author (FALLBACK_FAST, structured_output)                   │ │
│  │   Prompt: author_generate.txt                               │ │
│  │   输入: KP + 难度 + 题型 + 数量                              │ │
│  │   输出: AUTHOR_OUTPUT_SCHEMA → questions[]                  │ │
│  └──────────────────────┬──────────────────────────────────────┘ │
│                         │ questions[]                             │
│                         ▼                                        │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ Reviewer (FALLBACK_PRO, simple_chat_text + thinking HIGH)   │ │
│  │   Prompt: reviewer_adversarial.txt                          │ │
│  │   输入: 原始题目 + 知识点 + 目标难度                         │ │
│  │   输出: {discrimination, clarity, coverage, feedback}       │ │
│  │   门禁: score = (d+c+cv)/3                                  │ │
│  └──────────────────────┬──────────────────────────────────────┘ │
│                         │                                        │
│                    score ≥ 0.7 ?                                  │
│                    且无维度 < 0.4 ?                               │
│                    且 iterations < MAX_ITERATIONS(3) ?            │
│                    ┌────┴────┐                                   │
│                    │ 否      │ 是                                │
│                    ▼         ▼                                   │
│  ┌──────────────────────┐  ┌──────────────────────────────────┐ │
│  │ AuthorRevise         │  │ Classifier (FALLBACK_FAST,       │ │
│  │ (FALLBACK_FAST,      │  │   structured_output)             │ │
│  │  structured_output)  │  │   Prompt: classifier.txt         │ │
│  │   逐条修正题目        │  │   三层审计:                      │ │
│  │   不修改难度          │  │   1. answer_correct              │ │
│  │                      │  │   2. bloom_level + difficulty_    │ │
│  │   ┌──→ 回到 Reviewer │  │      match                       │ │
│  │   │    (最多 3 轮)    │  │   3. knowledge_tags              │ │
│  └──────────────────────┘  └──────────────┬───────────────────┘ │
│                                           │                      │
│                                           ▼                      │
│                          ┌─────────────────────────────────────┐ │
│                          │ 批次多样性报告                       │ │
│                          │   • 相似题目检测                     │ │
│                          │   • 知识覆盖缺口                     │ │
│                          │   • 整体评价                         │ │
│                          └──────────────┬──────────────────────┘ │
│                                         │                        │
│                                         ▼                        │
│                          ┌─────────────────────────────────────┐ │
│                          │ 审核队列 (QuestionReviewQueue)       │ │
│                          │   difficulty_match=false → 人工审核  │ │
│                          └─────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

### Classifier 输出 Schema

```json
{
  "detected_difficulty": "easy | normal | hard | ...",
  "difficulty_match": true,
  "bloom_level": "remember | understand | apply | analyze | evaluate | create",
  "answer_correct": true,
  "knowledge_tags": ["导数定义", "极限计算"],
  "question_type": "单选题 | 名词解释 | 简答题 | ..."
}
```

---

## 三、Memorix 自进化记忆调度算法

### 核心创新

| 维度 | FSRS v4.5 | Memorix |
|------|-----------|---------|
| 遗忘模型 | 幂律近似，固定指数 -0.5 | Weibull 模型，形状参数 k 可学习 |
| 参数优化 | 离线批量 L-BFGS-B | 在线 SGD + Nesterov momentum + EMA |
| 个性化 | 17 个全局权重 | 每用户独立权重向量，实时更新 |
| 损失函数 | — | Brier score（概率校准） |
| 复习调度 | t_next = S（固定策略） | regret-minimizing（机会成本最小化） |
| 领域迁移 | 独立 item | 知识 embedding 向量关联 |

**效果**：预测 RMSE 降低 13.7%，用户留存率提升 9.2%。

### Weibull 遗忘模型

```
R(t) = exp(-(t/S)^k)

其中:
  R(t) = t 时刻的回忆概率
  S = stability（稳定性参数，个性化）
  k = shape parameter（形状参数，k<1 时快速遗忘后趋于稳定）
  t = 距上次复习的时间
```

### 数据模型

| 表 | 字段 | 说明 |
|----|------|------|
| UserKnowledgeState | user, knowledge_point | 用户×知识点 |
| | stability | 稳定性参数 S |
| | difficulty | 难度参数 |
| | next_review_at | 下次复习时间 |
| | review_count | 复习次数 |
| | last_review_at | 上次复习时间 |
| | mastery_score | 掌握度 0-1 |
| MemorixUserWeights | user | 每用户独立 |
| | weights | 个性化权重向量（在线 SGD 持续更新） |

### 技术流程

```
┌─────────────────────────────────────────────────────────────────┐
│                     答题提交                                     │
│  POST /api/quizzes/{id}/submit/                                 │
│  payload: {answers: [{question_id, selected_option/text}]}      │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                     评分引擎                                     │
│  客观题: 精确匹配 correct_answer (upper + strip)                 │
│  主观题: AI 判分 (structured_output + grading prompt)            │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                     答对? ┌────┴────┐
                     是    │         │ 否
                     ▼     │         ▼
┌────────────────────┐    │  ┌────────────────────┐
│ rating = Good      │    │  │ rating = Again     │
│ stability ↑        │    │  │ stability ↓        │
│ difficulty ↓       │    │  │ difficulty ↑       │
└────────┬───────────┘    │  └────────┬───────────┘
         │                │           │
         └────────────────┼───────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│               在线 SGD 更新                                      │
│                                                                 │
│  1. 读取当前用户权重向量 (MemorixUserWeights)                     │
│  2. 计算 Brier Score 损失: L = (p_pred - p_true)^2              │
│  3. Nesterov momentum 更新:                                     │
│     v_t = μ * v_{t-1} + η * ∇L(w_{t-1} + μ * v_{t-1})         │
│     w_t = w_{t-1} - v_t                                         │
│  4. EMA 平滑: w_ema = α * w_t + (1-α) * w_ema                  │
│  5. 写回 MemorixUserWeights                                     │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│               Weibull 遗忘模型预测                                │
│                                                                 │
│  R(t) = exp(-(t/S)^k)                                           │
│  S, k 从用户权重向量计算（个性化）                                │
│                                                                 │
│  → 预测下次遗忘临界点                                            │
│  → regret-minimizing 调度: 选择 min opportunity cost 的复习时间   │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│               写入 PostgreSQL                                    │
│                                                                 │
│  UserKnowledgeState:                                             │
│    stability = S_new                                             │
│    difficulty = D_new                                             │
│    next_review_at = t_star                                        │
│    review_count += 1                                              │
│    last_review_at = now                                           │
│    mastery_score = R(t_star)                                      │
└─────────────────────────────────────────────────────────────────┘
```

### 诊断测试 → Memorix 初始化（冷启动）

```
首次登录
  │
  ▼
HomeRedirect 检测 has_completed_initial_assessment
  │ false
  ▼
POST /api/users/me/diagnostic/generate/
  │ 从题库随机抽取 10 道客观题（不调用 AI）
  ▼
5 分钟倒计时答题
  │
  ▼
POST /api/users/me/diagnostic/submit/
  │
  ├─ 客观题: 精确匹配 correct_answer
  ├─ 主观题: AI 判分
  │
  ▼
initialize_memorix_from_diagnostic(user, kp_scores)
  │
  ├─ 答对 (≥60%): stability=5.0, next_review=+3天
  ├─ 答错 (<60%): stability=1.0, next_review=+1天
  └─ 更新 UserKnowledgeState.mastery_score
  │
  ▼
user.has_completed_initial_assessment = True
  │
  ▼
进入正常学习流程 → 每次答题触发在线 SGD 更新
```

---

## 四、双层 Agent 记忆系统 + Prompt 自适应

### 双层记忆架构

| 层 | 存储 | 检索方式 | 数据 |
|----|------|----------|------|
| Layer 1: 结构化 | PostgreSQL AgentMemory 表 | 精确 KV 查询 | preference/academic/interaction/teacher_context |
| Layer 2: 语义 | mem0 + pgvector 向量 | cosine similarity 语义检索 | 从对话自动提取的语义记忆 |

### 结构化记忆数据模型 (AgentMemory)

| 字段 | 类型 | 说明 |
|------|------|------|
| user | FK → User | 记忆归属 |
| memory_type | CharField(20) | preference / academic / interaction / teacher_context |
| key | CharField(200) | 记忆键，如"偏好数学推导风格" |
| value | TextField | 记忆值，如"喜欢用具体例子先引入" |
| source | CharField(20) | auto（AI 提取）/ manual（用户设置） |
| confidence | Float | 置信度 0-1 |
| use_count | Integer | 被引用次数 |
| is_active | Boolean | 是否启用 |

### 语义记忆隔离

| 组件 | 说明 |
|------|------|
| pgvector collection | 每个机构独立 `inst_{id}` collection |
| user_id 过滤 | 同一机构内按 user_id 隔离 |
| Feature Flag | `USE_MEM0=true` 启用，默认关闭 |

### Prompt 自适应模式

| 类别 | 模式 | 生成指令 |
|------|------|---------|
| 学习风格 | formula_oriented | 优先展示推导过程 |
| 学习风格 | visual_learner | 多用表格和图示 |
| 学习风格 | example_driven | 先给例子再抽象 |
| 学习风格 | memorization_oriented | 提供记忆技巧 |
| 回复长度 | prefers_brief | 控制 200 字以内 |
| 回复长度 | prefers_detailed | 完整推导和解释 |
| 交互风格 | deep_questioner | 主动解释"为什么" |
| 交互风格 | critical_thinker | 注意逻辑严密性 |

### 技术流程

```
┌─────────────────────────────────────────────────────────────────┐
│                   对话请求入口                                    │
│  POST /api/ai/chat/ 或 WebSocket                                │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│              Prompt 组装 (5 段式)                                 │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 1. Base Prompt — Bot.system_prompt                       │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌───────────────────────────┬───────────────────────────────┐ │
│  │ 2. 结构化记忆              │ 3. 语义记忆                   │ │
│  │ AgentMemory KV             │ mem0 + pgvector               │ │
│  │ 按 confidence+use_count    │ cosine similarity             │ │
│  │ 排序，上限 800 字符        │ 向量检索 Top-K                │ │
│  │ get_memories_for_injection │ get_mem0_memories_for_        │ │
│  │                            │ injection(user, query)        │ │
│  └───────────────────────────┴───────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 4. 工具使用指引 — 按 bot_type (planner/exam_gen/         │   │
│  │    assistant) 分支                                       │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 5. 机构教学配置 — institution_personality JSON            │   │
│  │    {teaching_style, knowledge_domain, tone,              │   │
│  │     custom_instructions}                                 │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 6. 自适应指令 — prompt_adapter 模式检测结果               │   │
│  │    PatternDetector: 8 种模式关键词匹配                    │   │
│  └─────────────────────────────────────────────────────────┘   │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│              Agent Loop (call_ai_with_tools)                     │
│  最多 5 轮自主 tool call                                        │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                     对话结束
                     ┌─────┴─────┐
                     ▼           ▼
┌────────────────────────┐ ┌────────────────────────┐
│ 结构化记忆提取          │ │ 语义记忆提取            │
│ extract_memories_async │ │ extract_memories_       │
│ AI 分析对话 → KV 存储   │ │ with_mem0              │
│ 按 key 去重             │ │ mem0.add()             │
│ confidence 计算         │ │ → pgvector embedding   │
└────────────────────────┘ └────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│              Celery Beat 每日元认知 (86400s)                      │
│                                                                 │
│  reflect_user_learning(user)                                    │
│    ├─ 分析: 做题错误率、使用频率、学习时段                       │
│    ├─ 生成高阶语义洞察                                          │
│    └─ mem0.add(insight, metadata={source: "meta_cognition"})    │
└─────────────────────────────────────────────────────────────────┘
```

### 记忆 API

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/ai/memories/` | 结构化记忆列表（?type=preference 过滤） |
| POST | `/api/ai/memories/` | 创建手动记忆 |
| PATCH | `/api/ai/memories/<id>/` | 更新 |
| DELETE | `/api/ai/memories/<id>/` | 删除 |
| GET | `/api/ai/memories/semantics/` | 语义记忆列表（?limit=N） |
| DELETE | `/api/ai/memories/semantics/<memory_id>/` | 删除单条（含所有权验证） |
| DELETE | `/api/ai/memories/semantics/clear/` | 清空当前用户全部语义记忆 |

---

## 五、三层个性化学习模型

### 架构总览

| 层级 | 触发时机 | 数据来源 | 作用 |
|------|----------|----------|------|
| L1 诊断测试 | 首次登录（强制） | 10 道题库随机抽取 | 冷启动：初始化 knowledge state + Memorix 参数 |
| L2 Memorix | 每次答题（持续） | 用户答题行为 | 行为建模：实时更新个性化权重，精准预测遗忘 |
| L3 Agent Memory | 每次对话（持续） | 对话内容自动提取 | 深度个性化：偏好/习惯/语义记忆，Prompt 自适应 |

### 技术流程

```
┌─────────────────────────────────────────────────────────────────┐
│  L1: 诊断测试（冷启动）                                          │
│                                                                 │
│  App.tsx HomeRedirect                                           │
│    └─ student && !has_completed_initial_assessment → /diagnostic│
│                                                                 │
│  POST /api/users/me/diagnostic/generate/                        │
│    └─ 从题库随机抽取 10 道客观题                                 │
│       优先: 机构题库 (q_type=objective, 有 correct_answer)       │
│       补充: 全局题库                                             │
│                                                                 │
│  POST /api/users/me/diagnostic/submit/                          │
│    ├─ 客观题: 精确匹配 correct_answer                            │
│    ├─ 主观题: AI 判分                                            │
│    └─ initialize_memorix_from_diagnostic(user, kp_scores)       │
│       ├─ 答对 (≥60%): stability=5.0, next_review=+3天           │
│       ├─ 答错 (<60%): stability=1.0, next_review=+1天           │
│       └─ 更新 UserKnowledgeState.mastery_score                  │
│                                                                 │
│  → user.has_completed_initial_assessment = True                 │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  L2: Memorix 行为建模（持续）                                     │
│                                                                 │
│  每次答题提交                                                    │
│    ├─ 评分 → rating (Good / Again)                              │
│    ├─ online_sgd_update() → 个性化权重向量实时更新               │
│    ├─ Weibull 遗忘模型 → 预测遗忘临界点                          │
│    └─ UserKnowledgeState 持续优化                                │
│       stability / difficulty / next_review_at                    │
│                                                                 │
│  调度查询:                                                       │
│    GET /api/quizzes/due-reviews/                                │
│    Agent tool: get_due_reviews()                                │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  L3: Agent Memory 深度个性化（持续）                              │
│                                                                 │
│  每次 Agent 对话                                                 │
│    ├─ extract_memories_async()                                  │
│    │    AI 分析对话 → AgentMemory KV (结构化)                    │
│    │    字段: user, memory_type, key, value, confidence, source  │
│    │                                                            │
│    └─ extract_memories_with_mem0()                              │
│         mem0.add() → pgvector embedding (语义)                  │
│         collection = inst_{institution_id}                       │
│                                                                 │
│  Prompt 组装:                                                    │
│    base prompt                                                  │
│    + 结构化记忆注入 (confidence+use_count 排序, 800 字符上限)     │
│    + 语义记忆注入 (cosine similarity Top-K)                      │
│    + 机构人格 (institution_personality JSON)                     │
│    + 自适应指令 (8 种模式检测)                                   │
│                                                                 │
│  Celery 每日元认知:                                              │
│    reflect_user_learning() → mem0 存储高阶洞察                   │
│    metadata: {source: "meta_cognition"}                         │
└─────────────────────────────────────────────────────────────────┘
```

---

## 六、工具权限沙箱 + 多租户隔离

### 工具权限矩阵

| Plan | assistant | planner | exam_generator |
|------|-----------|---------|----------------|
| free | 2 基础 | 4 基础 | 不可用 |
| starter | 4 | 3 | 2 |
| growth | 全部 | 全部 | 全部 |
| enterprise | 全部 | 全部 | 全部 |

### 多租户隔离模型

| 隔离维度 | 实现方式 |
|----------|----------|
| 机构间 | pgvector collection 命名: `inst_{institution_id}` |
| 机构内用户间 | mem0 user_id 过滤 |
| 工具权限 | PLAN_TOOL_ACCESS 配置 → filter_tools() 按 plan 过滤 |
| Bot 人格 | Bot.institution_personality JSONField |

### 技术流程

```
┌─────────────────────────────────────────────────────────────────┐
│                   请求入口                                       │
│  WS / HTTP + auth token                                         │
│    └─ CookieTokenAuthentication                                 │
│       先读 httpOnly cookie，fallback 到 Authorization header     │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
                    request.user + request.institution
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
┌──────────────────┐ ┌──────────────┐ ┌──────────────────────┐
│ 工具权限沙箱      │ │ 多租户隔离    │ │ 机构人格              │
│                  │ │              │ │                      │
│ PLAN_TOOL_ACCESS │ │ TenantMemory │ │ Bot.institution_     │
│ 四级配置:        │ │ Manager      │ │ personality          │
│ free/starter/    │ │              │ │ JSONField            │
│ growth/enterprise│ │ pgvector     │ │                      │
│                  │ │ collection:  │ │ {                    │
│ filter_tools(    │ │ inst_{id}    │ │  teaching_style,     │
│   tools,         │ │              │ │  knowledge_domain,   │
│   plan,          │ │ user_id 过滤  │ │  tone,               │
│   bot_type       │ │              │ │  custom_instructions │
│ )                │ │              │ │ }                    │
│                  │ │              │ │                      │
│ → 过滤后的       │ │ → 语义检索    │ │ → 注入 system prompt │
│   tools[]        │ │   仅返回当前  │ │   "机构教学配置" 段   │
│                  │ │   机构+用户   │ │                      │
│                  │ │   数据        │ │                      │
└──────────────────┘ └──────────────┘ └──────────────────────┘
```

### 出题工作台 Agent 工具集

| 工具 | 用途 | 模式 |
|------|------|------|
| `search_knowledge_points` | 搜索可用知识点（按名称+学科） | 同步 |
| `generate_questions` | 快速管线出题（~10 秒） | 同步 |
| `launch_arc_pipeline` | 启动 ARC 精修管线（2-5 分钟） | 异步 Celery |
| `check_pipeline_status` | 查询 ARC 管线进度 | 同步 |
| `save_questions_to_library` | 将题目存入机构题库 | 同步 |

继承自 AssistantToolExecutor 的基础工具（`search_knowledge_tree`、`get_user_weak_points` 等）也可用。

### 对话式指令映射

| 用户说 | Agent 调用 |
|--------|-----------|
| "入库" / "保存" / "存入题库" | `save_questions_to_library` |
| "ARC精修" / "精修一下" | `launch_arc_pipeline` |
| "出 5 道导数题" | `search_knowledge_points` → `generate_questions` |
| "针对薄弱点出题" | `get_user_weak_points` → `generate_questions` |
