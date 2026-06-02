# Agent 软进化：从 Self-Refine 到 GEPA 的行动指南

> 来源：《从 Self-Refine 到 GEPA：Agent 软进化，到底在进化什么？》
> 整理日期：2026-06-01
> 用途：指导 UniMind Agent 系统后续演进方向

## 核心定义

**软进化** = 不改模型权重，不改 Agent 源码，而是把失败轨迹、环境反馈、反思结论、可复用技能和任务策略写回运行时上下文。它优化的是"下一次模型看到的工作现场"。

```
执行轨迹 τ → 反馈 f → 经验 e → 上下文状态 C' → 下一次执行
```

## 三层学习的区分

| 层级 | 本质 | 成本 | 例子 |
|------|------|------|------|
| **权重学习** | 改模型参数 | 最高 | 预训练、SFT、RLHF、GRPO |
| **上下文学习（软进化）** | 改运行时状态 | 中等 | 记忆、反思、技能库、prompt 演化 |
| **程序学习（硬进化）** | 改 Agent 源码/工作流 | 最高风险 | 生成工具代码、修改 agent program |

UniMind 当前主要在**上下文学习**层，部分涉及程序学习（ToolExecutor 子类）。

## 七篇论文的关键机制

### 1. Self-Refine — 最小闭环

- **机制**：生成 → 反馈 → 精炼，同一模型循环修正
- **价值**：把"修正过程"显式展开，第一遍输出不是终点
- **限制**：无长期记忆，反馈可能不可靠，可能把正确答案改坏
- **UniMind 对应**：`call_ai_with_tools` 的 5 轮工具调用循环（部分覆盖）

### 2. Reflexion — 失败写入长期记忆

- **机制**：Actor + Evaluator + Self-Reflection，失败反思写入 memory
- **价值**：解决 credit assignment — 标量 reward 说不清错在哪，语言反思可以
- **公式**：`π(ai|si), θ = {Ma, mem}` — 模型不变，mem 变了，策略就变了
- **限制**：memory 可能越来越长、越来越噪，不验证反思是否因果有效
- **UniMind 对应**：`AgentMemory` 结构化记忆 + `mem0` 语义记忆（已有基础）

### 3. Generative Agents — 记忆是行为状态

- **机制**：memory stream + retrieval（relevance/recency/importance）+ reflection + planning
- **价值**：memory ≠ 聊天记录，而是可检索、可压缩、可参与决策的状态
- **关键**：retrieval 三信号缺一不可 — 只看 relevance 会忽略状态变化，只看 recency 会被琐事淹没
- **UniMind 对应**：`mem0` 语义检索（relevance），但缺少 recency 和 importance 加权

### 4. Voyager — 经验变成可执行技能

- **机制**：automatic curriculum + skill library（代码技能）+ iterative prompting
- **价值**：技能是 temporally extended（完成子目标的程序）和 compositional（可组合）
- **关键区分**：Reflexion 存"下次注意什么"（语言规则），Voyager 存"下次调用什么"（可执行过程）
- **限制**：技能库是外部工具资产，不是 Agent 自身的递归自改造
- **UniMind 对应**：`ToolExecutor` 子类 + 工具注册表（部分覆盖，但技能不是自动生成的）

### 5. Re-ReST — 反思推进到训练样本

- **机制**：Agent 自生成轨迹 + 反思增强 → self-training 数据
- **价值**：把高质量经验从 inference memory 内化到模型行为
- **风险**：confirmation bias — 错误轨迹被当监督，下一轮更稳定犯同样错误
- **UniMind 对应**：暂无（当前不训练模型，但未来可考虑将 Agent 交互数据用于 fine-tuning）

### 6. ACE — Context 是会演化的 Playbook

- **机制**：Generator + Reflector + Curator 三角色分工，结构化增量更新 context
- **价值**：避免两个陷阱 — brevity bias（总结过度丢失细节）和 context collapse（反复重写后信息塌缩）
- **关键**：context 有结构、版本、合并、废弃和审计，不是无限追加也不是整体重写
- **UniMind 对应**：`system_prompt.txt` + `tool_guide.txt` 静态文件 + `prompt_adapter` 自适应（部分覆盖）

### 7. GEPA — 自然语言反思挑战 RL

- **机制**：Genetic-Pareto prompt optimization — 采样轨迹、自然语言反思、Pareto frontier 保留互补经验
- **数据**：比 GRPO 平均高 6%，最高高 20%，少用 35× rollouts
- **关键区分**：GRPO 看 reward（标量），GEPA 看轨迹解释（自然语言）。前者适合答案可验证、样本充足的场景；后者适合失败可解释、rollout 预算有限的场景
- **UniMind 对应**：暂无（prompt 是静态文件，不做自动演化）

## 系统状态更新总览

```
Self-Refine    → 更新当前输出 y（临时）
Reflexion      → 更新经验记忆 mem（跨 episode）
Generative Agents → 更新长期行为状态（memory stream + retrieval）
Voyager        → 更新技能库 S（可执行代码）
Re-ReST        → 更新训练样本分布（自训练数据）
ACE            → 更新结构化 context playbook C（增量）
GEPA           → 更新 prompt population P（演化）
```

通用公式：`state_{t+1} = Update(state_t, trajectory_t, feedback_t, verifier_t)`

## 软进化解决了什么

1. **重复犯错** — 无记忆 Agent 每次都是第一次；有记忆后失败原因、成功策略可跨轮次
2. **样本效率** — GEPA 比 GRPO 少用大量 rollouts，因为自然语言反思信息带宽更高
3. **能力外部化** — Agent 的一部分能力可以放在外部状态（技能库、playbook、memory stream）

## 软进化没解决什么

1. **经验是否因果有效** — 可能把偶然成功总结成规则，或把失败归因错；需要反事实测试和 verifier
2. **上下文是否被稳定遵守** — 经验写进 prompt ≠ 行为被强制约束；模型可能忽略、误读、长上下文丢失重点
3. **系统结构是否足够** — 很多失败需要新工具、新控制流、新测试器，不是"下次注意"能解决的

## 五个演进趋势

| # | 趋势 | UniMind 落地建议 |
|---|------|-----------------|
| 1 | memory 从"存历史"走向"存可执行经验" | AgentMemory 当前存 KV，应增加：任务规则、失败模式、用户偏好、工具约束 |
| 2 | reflection 从漂亮总结走向可验证归因 | 反思需绑定具体轨迹、失败证据、适用范围；不能只是"我应该更小心" |
| 3 | context update 工程化 | prompt 文件应有版本、合并、废弃机制；避免无限追加和整体重写 |
| 4 | 软进化与 RL 合流 | 语言经验更新 context + verifier reward 筛选候选，两者互补 |
| 5 | 评测看长期复用而非单题分数 | 关键指标：做过一批任务后是否少犯重复错误、能否迁移经验、memory 噪声是否可控 |

## 对 UniMind 的直接行动建议

### 近期（可立即做）

1. **AgentMemory 增加 recency + importance 加权** — 当前 mem0 只做语义相似度检索，缺少时间衰减和重要性评分。参考 Generative Agents 的 retrieval score。
2. **对话后反思机制** — Agent 完成任务后，自动生成结构化反思（成功/失败原因、关键决策点），写入记忆。当前只有 `extract_memories_async` 提取事实，没有反思。
3. **Prompt 版本管理** — `system_prompt.txt` 和 `tool_guide.txt` 当前是静态文件，应支持 A/B 测试和基于反馈的迭代（不需要 GEPA 级别的自动演化，先做到可追踪版本和效果对比）。

### 中期（需要基础设施）

4. **技能库机制** — 将高频工具调用序列沉淀为可复用的复合技能（类似 Voyager 的 skill library）。当前 17 个工具是扁平列表，没有技能组合。
5. **Context 结构化更新** — 参考 ACE 的 Curator 角色，让 prompt 上下文做增量更新而非每次重写。避免 context collapse。
6. **Verifier 集成** — 对 Agent 输出增加自动验证（如：生成的题目是否符合知识树、代码是否可执行），将验证结果作为反馈信号。

### 长期（架构演进）

7. **自训练数据管线** — 参考 Re-ReST，将高质量 Agent 交互轨迹转为训练数据，用于 fine-tuning 或 prompt 优化。
8. **Prompt 自动演化** — 参考 GEPA，对 system_prompt 做基于反思的自动优化，用 Pareto frontier 保留多样化策略。

## 与 UniMind 现有架构的映射

| 软进化机制 | UniMind 现状 | 差距 |
|-----------|-------------|------|
| Self-Refine（输出修正） | `call_ai_with_tools` 5 轮循环 | 部分覆盖，但无显式 feedback→refine 步骤 |
| Reflexion（失败记忆） | `AgentMemory` + `mem0` | 有基础，但缺少反思生成和因果验证 |
| Generative Agents（行为状态） | `mem0` 语义检索 | 缺 recency/importance 加权，缺少 reflection 层 |
| Voyager（技能库） | `BotRegistry` + `ToolExecutor` | 工具是预定义的，不是从经验中自动生成 |
| ACE（context playbook） | `prompt_adapter` 自适应 | 简单模式检测，非结构化增量更新 |
| GEPA（prompt 演化） | 静态 prompt 文件 | 完全缺失 |

## 一句话总结

> Agent 软进化不是"模型自己变强"，而是"系统把过去的任务经验组织成下一次可用的上下文资产"。UniMind 已有记忆基础设施，下一步是让记忆从"存事实"升级为"存可验证的可执行经验"，并让 prompt 从静态文件进化为可追踪、可迭代的 playbook。
