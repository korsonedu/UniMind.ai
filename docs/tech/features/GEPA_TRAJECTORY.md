# GEPA Trajectory 数据收集

## 概述

为后续 GEPA（Genetic-Pareto）自进化优化做数据储备，记录小宇的对话轨迹、工具调用序列和结果评估。

## 架构

```
小宇对话
        ↓
trajectory_recorder.py
        ↓
AITrajectory 数据表
├── messages: 完整对话记录
├── tool_calls: 工具调用序列
├── tool_outputs: 工具返回结果
├── outcome: 结果评估
├── outcome_metrics: 结果指标
└── prompt_variant: Prompt 变体标识
        ↓
GEPA 自进化（后续阶段）
```

## 核心组件

### 1. AITrajectory 模型

**字段说明：**
- `user`: 用户外键
- `bot`: Bot 外键
- `conversation_id`: 会话 ID（UUID）
- `messages`: 完整对话记录（JSON）
- `tool_calls`: 工具调用序列（JSON）
- `tool_outputs`: 工具返回结果（JSON）
- `outcome`: 结果类型（success/partial/failure/unknown）
- `outcome_metrics`: 结果指标（JSON，如掌握率变化、任务完成度）
- `prompt_variant`: 使用的 prompt 变体标识（用于 A/B 测试）

### 2. trajectory_recorder.py

**关键函数：**
- `record_trajectory(...)`: 记录一条对话轨迹
- `evaluate_trajectory(trajectory_id, outcome, outcome_metrics)`: 评估轨迹结果
- `get_trajectory_stats(user_id, days)`: 获取用户轨迹统计
- `get_successful_trajectories(...)`: 获取成功轨迹用于 prompt 优化

### 3. 记录时机

在以下时机记录 trajectory：
- 用户发起对话时：创建 trajectory 记录
- 每次工具调用时：追加到 tool_calls 和 tool_outputs
- 对话结束时：更新 trajectory 的完整数据
- 用户下次登录时：评估上次对话的 outcome

### 4. 结果评估

**评估指标：**
- `knowledge_mastery_delta`: 对话后知识点掌握率变化
- `task_completion_rate`: 任务完成率
- `user_satisfaction`: 用户满意度（基于续聊率、主动提问深度）
- `tool_efficiency`: 有效工具调用 / 总工具调用

**评估时机：**
- 对话后 1 天：评估短期效果（任务完成率）
- 对话后 7 天：评估中期效果（掌握率变化）
- 对话后 30 天：评估长期效果（知识保持率）

## GEPA 自进化流程（后续实现）

```
1. 数据收集（当前阶段）
   └── 收集 trajectory + outcome + metrics

2. Prompt 变体生成
   └── 基于反思生成 prompt 变体

3. Pareto 优化
   └── 多目标优化：学习效果 + 用户满意度 + 工具效率

4. 变体选择
   └── 根据用户画像选择最优变体

5. 持续迭代
   └── 收集新数据 → 生成新变体 → 优化
```

## 查询示例

### 查询用户最近 30 天的轨迹统计

```python
from ai_assistant.services.trajectory_recorder import get_trajectory_stats

stats = get_trajectory_stats(user_id=123, days=30)
# {
#     "total": 45,
#     "success_rate": 0.78,
#     "avg_tool_calls": 3.2,
#     "prompt_variants": {"baseline": 40, "v1": 5}
# }
```

### 查询成功的轨迹用于 prompt 优化

```python
from ai_assistant.services.trajectory_recorder import get_successful_trajectories

trajectories = get_successful_trajectories(
    bot_type='planner',
    min_mastery_delta=0.2,
    limit=100
)
```

## 配置

无需额外配置。当 `USE_MEM0=true` 时自动启用 trajectory 记录。

## 后续优化

- 自动评估：使用 LLM 自动评估对话质量
- Prompt 变体库：管理多个 prompt 变体
- GEPA 集成：对接 DSPy GEPA optimizer
- A/B 测试框架：自动分配变体并收集对比数据
