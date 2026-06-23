# MUTAR 自进化引擎 数据收集与自进化

## 概述

MUTAR（Measure→Umpire→Think→Adapt→Refine）是 UniMind Prompt 层的自进化引擎。通过采集对话轨迹、用户反馈、工具执行信号，驱动 AI 回答质量的持续优化。

**当前状态（2026-06-13）：** 数据采集→评估→分析→建议→变体路由 全链路已打通。优化执行层框架就绪，等待 trajectory 数据积累后开启 LLM 驱动的自动 prompt 优化。

## 架构

```
用户发消息
    ↓
Agent 执行（tool_call_log / tool_output_log 累积在 BaseToolExecutor）
    ↓
对话结束（SSE / Polling / WebSocket 三条路径的 finally 块）
    ↓
record_trajectory_async (Celery task)
    ↓
AITrajectory 表
├── messages: 完整对话
├── tool_calls: 工具调用序列
├── tool_outputs: 工具返回结果
├── outcome: success / partial / failure / unknown
├── outcome_metrics: 评估置信度、错误率、来源标记
├── prompt_variant: 使用的 variant 名称（非硬编码 baseline）
    ↓
┌─ 自动评估 ─────────────────────┐
│ _auto_evaluate_trajectory()     │
│ 启发式规则 → outcome + confidence│
└────────────────────────────────┘
    ↓
┌─ 用户反馈覆盖 ─────────────────┐
│ POST /api/ai/feedback/          │
│ 赞/踩 → outcome + feedback_source│
└────────────────────────────────┘
    ↓
每周日 2am: analyze_trajectory_task
    ↓
Redis mutar:suggestions
    ↓
每周一 3am: optimize_prompt_task（框架阶段仅 log）
```

## 数据模型

### AITrajectory（`ai_assistant/models.py:185`）

| 字段 | 类型 | 说明 |
|------|------|------|
| `user` | FK→User | 用户 |
| `bot` | FK→Bot | 使用的 AI 助教 |
| `conversation_id` | UUID | 会话 ID |
| `messages` | JSON | 完整对话记录 `[{role, content}, ...]` |
| `tool_calls` | JSON | 工具调用序列 `[{name, args}, ...]` |
| `tool_outputs` | JSON | 工具返回结果 `[json_str, ...]` |
| `outcome` | CharField | success / partial / failure / unknown |
| `outcome_metrics` | JSON | `{auto_evaluated, auto_confidence, tool_error_rate, feedback_source, ...}` |
| `prompt_variant` | CharField | 使用的 variant 名称（默认 `baseline`） |
| `evaluated_at` | DateTime | 评估时间（自动评估或用户反馈时更新） |

### AIChatMessage.feedback（`ai_assistant/models.py:12`）

| 字段 | 类型 | 说明 |
|------|------|------|
| `feedback` | BooleanField | true=赞, false=踩, null=未评价 |

用户反馈通过 `POST /api/ai/feedback/` 写入，并同步覆盖同 `conversation_id` 的最新 `AITrajectory.outcome`。

## 核心组件

### 轨迹记录（`trajectory_recorder.py`）

| 函数 | 说明 |
|------|------|
| `record_trajectory(user_id, bot_id, conversation_id, messages, tool_calls, tool_outputs, prompt_variant)` | 记录一条轨迹（默认异步 Celery） |
| `_auto_evaluate_trajectory(trajectory)` | 启发式自动评估：AI 报错→failure(0.95), 工具全成功→success(0.75), 部分失败→partial(0.65) |
| `evaluate_trajectory(trajectory_id, outcome, outcome_metrics)` | 外部评估入口（用户反馈 / LLM 评估调用） |
| `get_trajectory_stats(user_id, days)` | 用户轨迹统计（成功率、平均工具调用数、variant 分布） |
| `get_successful_trajectories(bot_type, min_mastery_delta, limit)` | 查询成功轨迹用于 prompt 优化 |

### 变体管理（`mutar_variants.py`）

| 函数 | 说明 |
|------|------|
| `get_variant_for_request(bot)` | 按 traffic_split 加权随机选择 variant，返回 `(name, overrides)` 或 None |
| `apply_variant_prompt(system_prompt, overrides)` | 将 variant suffix 追加到 system_prompt 末尾 |
| `create_variant(bot_type, name, overrides, traffic_split)` | 创建/更新 variant（写入 JSON 文件） |
| `retire_variant(bot_type, name)` | 退役 variant：status→retired, traffic→0 |
| `update_traffic(bot_type, name, traffic_split)` | 调整 variant 流量比例 |
| `list_variants(bot_type)` | 列出所有 variant |

Variant 存储在 `backend/prompts/ai_assistant/variants/{bot_type}.json`，JSON 格式：

```json
{
  "variants": [
    {
      "name": "v1_conciseness",
      "status": "active",
      "traffic_split": 0.1,
      "overrides": {"suffix": "## 实验指令\n回复简洁，每段不超过3句。"},
      "created_at": "2026-06-13T00:00:00Z",
      "source_suggestion_id": null
    }
  ]
}
```

### 分析管道（`tasks.py`）

| Celery Task | 调度 | 说明 |
|-------------|------|------|
| `analyze_trajectory_task` | 每周日 2am | 聚合过去 7 天轨迹，生成优化建议写入 Redis |
| `optimize_prompt_task` | 每周一 3am | 读取建议，分派到 memorix/prompt/bot handler（框架阶段仅 log） |

`mutar:suggestions` Redis 格式：

```json
{
  "generated_at": "2026-06-15T02:00:00+00:00",
  "suggestions": [
    {
      "target": "memorix",
      "param": "alpha",
      "direction": "decrease",
      "current": 0.60, "suggested": 0.45,
      "reason": "Trajectory 成功率 45% < 60%",
      "confidence": 0.75
    }
  ]
}
```

## Outcome 评估来源（优先级从高到低）

| 来源 | 触发时机 | confidence | 标记 |
|------|---------|-----------|------|
| **用户反馈** | 用户点击 赞/踩 | 最高（人工标注） | `feedback_source: user` |
| **启发式评估** | 轨迹创建后自动运行 | 0.6-0.95 | `auto_evaluated: true` |
| **默认 unknown** | 轨迹创建时 | — | — |

用户反馈始终覆盖自动评估结果。

## 记录触发

三条聊天路径在对话结束时均调用 `record_trajectory(async_mode=True)`：

| 路径 | 文件 | 位置 |
|------|------|------|
| SSE 流式 | `views.py` `AIChatStreamView.generate()` | `finally` 块 |
| Polling 非流式 | `views.py` `process_ai_chat()` | `finally` 块 |
| WebSocket | `consumers.py` `AgentChatConsumer._run_agent()` | `try` 块末尾 |

`BaseToolExecutor.__call__` 在每次工具调用时累积 `tool_call_log` / `tool_output_log`。

## 查询示例

### 用户统计

```python
from ai_assistant.services.trajectory_recorder import get_trajectory_stats
stats = get_trajectory_stats(user_id=123, days=30)
# {"total": 45, "success_rate": 0.78, "avg_tool_calls": 3.2, "prompt_variants": {"baseline": 40, "v1": 5}}
```

### 创建实验 variant

```python
from ai_assistant.services.mutar_variants import create_variant, update_traffic
create_variant('planner', 'v1_conciseness', {'suffix': '## 实验指令\n回复简洁，每段不超过3句。'})
update_traffic('planner', 'v1_conciseness', 0.1)  # 10% 流量
```

### 查看 Variant 表现

```sql
SELECT prompt_variant, outcome, COUNT(*)
FROM ai_assistant_aitrajectory
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY prompt_variant, outcome;
```

## Memorix-Field 参数自进化

**与 Prompt 层自进化不同，Field 参数自进化不依赖 LLM 评估，而是基于 ReviewLog 的统计信号（Brier score）进行直接优化。**

### 架构

```
学生答题 → ReviewLog 写入（predicted_retrievability + grade）
    ↓
每天 3:00: evaluate_field_brier_daily (Celery)
    ↓
按机构聚合 7 天 ReviewLog
    Brier = mean[(predicted_R - actual_binary)²]
    ↓
MemorixFieldConfig.brier_score（每机构）
    ↓
每周日 3:30: perturb_field_params_weekly (Celery)
    ↓
┌─ 评估进行中的扰动 ────────────────┐
│ brier_now vs brier_before          │
│ 改善 → 保留  劣化 → 回退           │
└────────────────────────────────────┘
    ↓
┌─ 发起新扰动 ──────────────────────┐
│ 轮询：decay → beta_e → beta_a → eta│
│ 方向：+10% / -10%                  │
│ 8 周完整周期，收敛后幅度减半         │
└────────────────────────────────────┘
```

### 与 Prompt 层 MUTAR 的区别

| 维度 | Prompt 层 MUTAR | Field 参数自进化 |
|------|----------------|-----------------|
| 数据源 | AITrajectory (对话轨迹 + 用户反馈) | ReviewLog (答题记录) |
| 评估方式 | 启发式规则 + 用户赞踩 + LLM 评估 | Brier score（严格真分数） |
| 优化对象 | system prompt 措辞 | 扩散方程参数 (α, βe, βa, η) |
| 隔离粒度 | bot 级别 | 机构级别 (per-institution) |
| 调度 | 每周日 analyze + 周一 optimize | 每天 Brier + 每周日扰动 |
| 优化策略 | LLM 生成 variant → A/B 测试 → 胜出 | 有限差分爬山 ±10% → Brier 对比 → 接受/回退 |
| 安全机制 | traffic_split 渐进放量 | SAFE_BOUNDS 硬边界 + 每次只动一个参数 |

### 数据模型

`MemorixFieldConfig`（`quizzes/models.py`）
- 参数值: `decay, beta_e, beta_a, eta`
- 评估状态: `brier_score, reviews_evaluated, last_evaluated_at`
- 扰动状态: `perturbation_param, perturbation_multiplier, perturbation_brier_before, perturbation_original_value`
- 历史: `perturbation_history` (JSON，完整调参轨迹)

### 参数安全边界

```python
SAFE_BOUNDS = {
    'decay':  (0.005, 0.10),   # 不至于忘太快或完全不衰减
    'beta_e': (0.0005, 0.02),  # 扩散不够或过度
    'beta_a': (0.1, 2.0),      # 评分放大失控
    'eta':    (0.005, 0.08),   # 转移太弱或太强
}
```

### Redis 缓存架构

```
memorix:field:params:{inst_id}  → JSON {decay, beta_e, beta_a, eta}
    热缓存 5min TTL，命中即返回
    miss → MemorixFieldConfig DB → settings 全局默认 → 写回 Redis
```

### Celery 任务

| 任务 | 调度 | 说明 |
|------|------|------|
| `evaluate_field_brier_daily` | 每天 3:00 | 按机构算 Brier（最少 50 样本） |
| `perturb_field_params_weekly` | 每周日 3:30 | 评估上轮扰动 + 发起新扰动 |

---

## 后续优化（等待数据积累）

- **自动 variant 生成**：`optimize_prompt_task` handler 调 LLM 根据建议生成 variant 措辞
- **LLM 评估**：用 LLM 替代启发式规则评估对话质量
- **自动部署**：胜出 variant 自动提升流量 → 失败 variant 自动退役

## 相关文档

- `docs/tech/AI_SYSTEM_REFERENCE.md` — AI 系统完整参考（含 MUTAR 章节）
- `docs/architecture/all-phases-plan.md` — Phase 7 路线图
- `docs/tech/reference/SOFT_EVOLUTION_GUIDE.md` — 理论基础（7 篇论文映射）
- `docs/tech/features/ADAPTIVE_PROMPT_LLM.md` — LLM 驱动的自适应指令
