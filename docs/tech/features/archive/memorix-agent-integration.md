# Memorix↔Agent 联动

## 概述

打通 Memorix 记忆调度算法和小宇学习教练之间的数据通路，让小宇能够基于 Memorix 的难度衰减和知识嵌入信息提供更精准的学习建议。

## 架构

```
Memorix（刷题调度）
├── 难度衰减（difficulty）
├── 记忆稳定性（stability）
├── 遗忘次数（lapse_count）
└── 知识嵌入（knowledge_embedding）
        ↓
小宇工具函数
├── get_due_reviews（扩展返回 Memorix 字段）
└── get_knowledge_difficulty_analysis（新增工具）
        ↓
学习建议（基于 Memorix 数据）
```

## 核心改进

### 1. get_due_reviews 工具扩展

**新增返回字段：**
- `difficulty`: 难度衰减值（1-10），越高越难
- `stability`: 记忆稳定性（天数），越低越容易遗忘
- `reps`: 总复习次数
- `lapses`: 遗忘次数
- `memorix_priority`: 基于 Memorix 的优先级（critical/high/medium/low）

**优先级计算逻辑：**
```python
if lapses >= 3:
    return "critical"  # 反复遗忘
if difficulty >= 7:
    return "high"  # 高难度
if stability < 2:
    return "high"  # 稳定性低
if stability < 7:
    return "medium"
return "low"
```

### 2. get_knowledge_difficulty_analysis 工具（新增）

**用途：** 获取知识点的 Memorix 难度分析

**参数：**
- `subject` (可选): 学科名称

**返回：**
```json
{
    "knowledge_points": [
        {
            "name": "极限",
            "avg_difficulty": 6.5,
            "avg_stability": 3.2,
            "total_reviews": 45,
            "mastery_level": "weak",
            "memorix_insight": "该知识点平均难度较高（6.5），且记忆稳定性低（3.2天），建议增加复习频率"
        }
    ],
    "summary": "共 12 个知识点，其中 3 个需要重点关注"
}
```

**掌握程度判断：**
- `weak`: avg_difficulty >= 7 或 avg_stability < 2
- `developing`: avg_difficulty >= 5 或 avg_stability < 5
- `strong`: 其他

## 使用场景

### 场景 1：学生问"为什么我总是记不住极限"

小宇调用 `get_knowledge_difficulty_analysis(subject="高数")`，发现：
- 极限的 avg_difficulty = 6.5（较高）
- avg_stability = 3.2（较低）
- lapse_count = 8（反复遗忘）

小宇回复："从你的学习数据看，极限这个知识点确实是一个难点。Memorix 记忆系统显示，你在这个知识点上的平均难度是 6.5（满分 10），记忆稳定性只有 3.2 天，意味着你平均 3 天就会遗忘一次。这说明不是你不努力，而是这个知识点本身就需要更频繁的复习。我建议你使用间隔重复策略：今天复习一次，2 天后再复习一次，5 天后再复习一次，这样可以逐步提高记忆稳定性。"

### 场景 2：学生问"我今天该复习什么"

小宇调用 `get_due_reviews()`，发现：
- 题目 A: difficulty=8, stability=1.5, memorix_priority="critical"
- 题目 B: difficulty=5, stability=6, memorix_priority="medium"
- 题目 C: difficulty=3, stability=10, memorix_priority="low"

小宇回复："根据你的记忆数据，我建议优先复习题目 A。这道题难度较高（8/10），而且记忆稳定性只有 1.5 天，说明你最近刚遗忘过。题目 B 可以放在明天，题目 C 可以放到下周。"

## 配置

无需额外配置。Memorix 数据已在数据库中，工具函数自动读取。

## 后续优化

- 知识嵌入向量：利用 Memorix 的 knowledge_embedding 计算知识点关联性
- 个性化遗忘曲线：为每个用户定制 Weibull 参数
- 预测性干预：在学生即将遗忘前主动提醒复习
