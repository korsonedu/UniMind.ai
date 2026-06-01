# Agent 记忆系统

> 最后更新：2026-06-01

## 概述

Agent 记忆系统让 AI 助教能够跨会话记住用户的关键信息（偏好、学业状态、交互习惯），并在后续对话中自动注入上下文，实现"越用越懂你"的体验。

系统采用**双层记忆架构**：结构化记忆（AgentMemory KV）+ 语义记忆（mem0 + pgvector），并具备 Prompt 自适应和主动反思能力。

## 架构

```
用户对话 → AIChatView / AgentChatConsumer
    │
    ├── chat_dispatch（统一调度，BotRegistry 选择 Executor + tools）
    │
    ├── Prompt 组装（文件模板 + 运行时注入）
    │   ├── system_prompt.txt（核心人设，文件加载）
    │   ├── tool_guide.txt（工具指南，文件加载）
    │   ├── 机构人格（institution_personality JSONField）
    │   ├── 结构化记忆（AgentMemory KV）
    │   ├── 语义记忆（mem0 pgvector 语义检索）
    │   └── 自适应指令（prompt_adapter 模式检测）
    │
    └── Agent Loop（call_ai_with_tools，最多 5 轮）
            │
            ▼
        后台提取记忆
            ├── extract_memories_async（结构化）
            ├── extract_memories_with_mem0（语义）
            └── reflect_user_learning（每日元认知）
```

## 双层记忆

### Layer 1：结构化记忆（AgentMemory）

精确 KV 存储，PostgreSQL 原生。

| 字段 | 类型 | 说明 |
|------|------|------|
| user | FK → User | 记忆归属 |
| memory_type | CharField(20) | `preference` / `academic` / `interaction` / `teacher_context` |
| key | CharField(200) | 记忆键，如"偏好数学推导风格" |
| value | TextField | 记忆值，如"喜欢用具体例子先引入" |
| source | CharField(20) | `auto`（AI 提取）/ `manual`（用户设置） |
| confidence | Float | 置信度 0-1 |
| use_count | Integer | 被引用次数 |
| is_active | Boolean | 是否启用 |

**约束**：
- `UniqueConstraint(user, memory_type, key)` — 防止并发提取产生重复
- 索引：`(user, memory_type, is_active)` + `(user, is_active, confidence)`

**服务**：`ai_assistant/services/memory_service.py`

- `get_memories_for_injection(user)` — 按 confidence + use_count 排序，上限 800 字符
- `extract_memories_async(user, history)` — 后台线程 AI 提取，按 key 去重
- `build_memory_context(user, user_message)` — **统一入口**，返回 `(memory_context, adaptive_directives)`，polling 和 streaming 两条聊天路径共用

### Layer 2：语义记忆（mem0 + pgvector）

向量相似度检索，支持模糊语义匹配。

| 组件 | 文件 | 说明 |
|------|------|------|
| TenantMemoryManager | `ai_assistant/services/tenant_memory.py` | mem0 wrapper，pgvector 后端 |
| 租户隔离 | pgvector collection | 每个机构独立 `inst_{id}` collection |
| 用户隔离 | mem0 user_id | 同一机构内按 user_id 过滤 |
| Feature Flag | `USE_MEM0` 环境变量 | 默认 false，渐进式上线 |

**服务**：`ai_assistant/services/memory_service.py`

- `get_mem0_memories_for_injection(user, query)` — 语义检索相关记忆
- `extract_memories_with_mem0(user, history)` — 后台线程 mem0 提取

### Prompt 自适应

**双模式**：LLM 驱动分析（优先）+ 规则引擎（fallback）。

| 组件 | 文件 | 说明 |
|------|------|------|
| LLM 分析器 | `ai_assistant/services/memory_analyzer.py` | LLM 分析用户记忆生成 UserProfile |
| 规则引擎 | `ai_assistant/services/prompt_adapter.py` | 8 种模式检测（关键词匹配） |
| 注入位置 | `chat_service.py` → `_build_agent_system_prompt()` | system prompt 末尾 |

**LLM 分析模式（v2.10.0+）**：
- 用户登录时 Celery 异步预计算画像，缓存到 Redis（24h 过期）
- 对话时优先读取缓存，未命中时 fallback 到规则匹配
- 分析维度：learning_style、response_length、interaction_style、cognitive_state、domain_expertise
- 置信度阈值：>= 0.6 才使用 LLM 结果

**规则引擎模式（fallback）**：

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

### Memorix↔Agent 联动

Memorix 记忆调度算法与小宇 Agent 深度集成。

| 工具 | 功能 | Memorix 字段 |
|------|------|-------------|
| `get_due_reviews` | 获取待复习题目 | difficulty, reps, lapses, memorix_priority |
| `get_knowledge_difficulty_analysis` | 知识点难度分析 | avg_difficulty, avg_stability, mastery_level, memorix_insight |

**优先级计算**：
- `critical`: lapses >= 3（反复遗忘）
- `high`: difficulty >= 7 或 stability < 2
- `medium`: stability < 7
- `low`: 其他

### Trajectory 数据收集

为 GEPA（Genetic-Pareto）自进化优化做数据储备。

| 组件 | 文件 | 说明 |
|------|------|------|
| AITrajectory 模型 | `ai_assistant/models.py` | 记录对话轨迹 |
| 记录服务 | `ai_assistant/services/trajectory_recorder.py` | Celery 异步记录 |
| Celery Tasks | `ai_assistant/tasks.py` | `record_trajectory_async`, `precompute_user_profile` |

**记录字段**：messages、tool_calls、tool_outputs、outcome、outcome_metrics、prompt_variant

### 主动反思（元认知）

Celery 定时任务，每日分析用户学习数据生成高阶语义记忆。

| 组件 | 文件 | 说明 |
|------|------|------|
| Celery Task | `ai_assistant/tasks.py` → `reflect_user_learning` | 每日任务 |
| Beat Schedule | `school_system/settings.py` | 86400s 间隔 |

**分析维度**：做题错误率、使用频率、学习时段。洞察通过 mem0 存储，metadata 标记 `source=meta_cognition`。

### 记忆清理

Celery 周任务 `cleanup_stale_memories`（每周执行）：

| 规则 | 条件 | 动作 |
|------|------|------|
| 结构化 — 未使用 | `use_count=0` 且 `updated_at > 30天` | `is_active=False` |
| 结构化 — 低置信 | `confidence < 0.3` 且 `updated_at > 60天` | `is_active=False` |
| 语义 — 不活跃用户 | 用户 90 天无对话 | `delete_all(user_id)` |

## 工具权限沙箱

按机构方案（plan）过滤 Agent 可用工具集。

| 组件 | 文件 | 说明 |
|------|------|------|
| PLAN_TOOL_ACCESS | `ai_engine/tool_permissions.py` | free/starter/growth/enterprise 四级配置 |
| filter_tools() | 同上 | 过滤函数，chat_service 调用 |

| Plan | assistant | planner | exam_generator |
|------|-----------|---------|----------------|
| free | 2 基础 | 4 基础 | 不可用 |
| starter | 4 | 3 | 2 |
| growth | 全部 | 全部 | 全部 |
| enterprise | 全部 | 全部 | 全部 |

## 机构人格

Bot 模型的 `institution_personality` JSONField，机构管理员可配置 Agent 教学风格。

```json
{
    "teaching_style": "严格",
    "knowledge_domain": "金融431",
    "tone": "专业",
    "custom_instructions": "不要用太多类比，直接讲公式推导"
}
```

注入位置：`chat_service.py` → `_build_agent_system_prompt()` 的 `## 机构教学配置` 段。

## API

### 结构化记忆

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/ai/memories/` | 列表（支持 `?type=preference` 过滤） |
| POST | `/api/ai/memories/` | 创建手动记忆 |
| PATCH | `/api/ai/memories/<id>/` | 更新 |
| DELETE | `/api/ai/memories/<id>/` | 删除 |

### 语义记忆

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/ai/memories/semantics/` | 语义记忆列表（`?limit=N`，上限 200） |
| DELETE | `/api/ai/memories/semantics/<memory_id>/` | 删除单条（含所有权验证） |
| DELETE | `/api/ai/memories/semantics/clear/` | 清空当前用户全部语义记忆 |

## 记忆注入流程

`ai_assistant/services/chat_service.py` → `_build_agent_system_prompt()`

system prompt 按以下顺序组装：

1. base prompt（Bot.system_prompt）
2. 用户记忆（结构化 + 语义检索结果）
3. 工具使用指引（按 bot_type 分支）
4. 机构教学配置（institution_personality）
5. 自适应指令（prompt_adapter 模式检测结果）

## 配置

```bash
# 启用 mem0 语义记忆（默认 false）
USE_MEM0=true

# Embedding 模型配置
AI_EMBEDDING_MODEL=deepseek-embedding
AI_EMBEDDING_BASE_URL=https://api.deepseek.com/v1

# PostgreSQL 需要 pgvector 扩展
# CREATE EXTENSION IF NOT EXISTS vector;

# 依赖
# pip install mem0ai pgvector
```

## 测试

```bash
# 单元测试（33 个）
cd backend && python3 -m pytest ai_assistant/tests/ -v

# 集成测试（需 PG + pgvector + USE_MEM0=true）
USE_MEM0=true python3 -m pytest ai_assistant/tests/test_mem0_integration.py -v -m integration
```

## 迁移

- `ai_assistant/0006_agentmemory.py` — AgentMemory schema
- `ai_assistant/0008_add_institution_personality.py` — Bot.institution_personality
- `ai_assistant/0012/0013` — AgentMemory UniqueConstraint + 索引

## 详细文档

| 文档 | 内容 |
|------|------|
| `docs/tech/features/MULTI_TENANT_AGENT_MEMORY.md` | 多租户记忆系统完整设计（mem0+pgvector、工具权限沙箱、机构人格） |
