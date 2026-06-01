# 自适应指令 LLM 化

## 概述

小宇的自适应指令系统从规则驱动升级为 LLM 驱动，能够更准确地识别用户的学习风格、认知状态和交互偏好。

## 架构

```
用户记忆（mem0/AgentMemory）
        ↓
LLM 分析服务（memory_analyzer.py）
        ↓
用户画像（UserProfile）
        ↓
自适应指令生成（profile_to_directives）
        ↓
注入 system prompt
```

## 核心组件

### 1. memory_analyzer.py

LLM 驱动的记忆分析服务，替代原有的规则匹配。

**关键函数：**
- `analyze_user_profile(memories, bot_type)`: 分析用户记忆，返回 UserProfile
- `profile_to_directives(profile, bot_type)`: 将画像转换为指令字符串

**分析维度：**
- `learning_style`: 学习风格（formula_oriented, visual_learner, example_driven, memorization_oriented, balanced）
- `response_length`: 回复长度偏好（prefers_brief, prefers_detailed, balanced）
- `interaction_style`: 交互风格（deep_questioner, critical_thinker, passive_learner）
- `cognitive_state`: 认知状态（focused, anxious, overwhelmed, motivated）
- `domain_expertise`: 领域专业度（beginner, intermediate, advanced）

### 2. prompt_adapter.py

更新为使用 LLM 分析，规则匹配作为 fallback。

**关键函数：**
- `get_adaptive_directives_llm(memories, bot_type)`: 优先使用 LLM，失败时 fallback 到规则

### 3. memory_service.py

`build_memory_context` 函数使用新的自适应指令生成方式。

## 配置

无需额外配置。当 `USE_MEM0=true` 且用户有机构时，自动启用 LLM 分析。

## 性能考虑

- **缓存策略**：用户画像预计算后缓存到 Redis（24 小时过期）
- **异步预计算**：用户登录时触发 Celery 异步任务预计算画像
- **缓存命中**：对话时直接读取缓存，0ms 延迟
- **缓存未命中**：fallback 到规则匹配（同步，<10ms）
- **置信度阈值**：>= 0.6 才会缓存，低于此值使用规则匹配

## Fallback 机制

```
用户登录 → Celery 异步预计算画像 → 缓存到 Redis
                                        ↓
对话时 → 读取缓存 → 命中 → 使用缓存画像
                      ↓ (未命中)
                      规则匹配 → 使用规则结果
```

## 后续优化

- GEPA 自进化：收集 trajectory 数据，自动优化分析 prompt
- 画像更新触发器：对话结束、记忆更新时自动触发重新计算
- A/B 测试：对比 LLM 分析 vs 规则匹配的效果
