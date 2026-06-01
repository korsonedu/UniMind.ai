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

- LLM 分析会增加约 200-500ms 延迟
- 分析结果会随记忆一起缓存
- 置信度阈值设为 0.6，低于此值使用规则匹配

## Fallback 机制

```
LLM 分析 → 置信度 >= 0.6 → 使用 LLM 结果
         ↓ (失败或置信度低)
         规则匹配 → 使用规则结果
```

## 后续优化

- GEPA 自进化：收集 trajectory 数据，自动优化分析 prompt
- 缓存策略：对频繁访问的用户画像进行缓存
- A/B 测试：对比 LLM 分析 vs 规则匹配的效果
