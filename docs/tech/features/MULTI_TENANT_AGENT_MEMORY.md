# Multi-Tenant Agent Memory System

> 多租户 Agent 记忆系统：语义记忆（mem0 + pgvector）+ 工具权限沙箱 + 机构人格

## 概述

为每个用户提供"专属 AI 助教"体验。Agent 通过 mem0 自动从对话中提取语义记忆，下次对话时语义检索相关记忆注入 prompt，形成"越用越懂你"的正循环。

### 核心能力

| 能力 | 说明 |
|------|------|
| 语义记忆 | mem0 + pgvector，基于向量相似度检索，非关键词匹配 |
| 租户隔离 | 每个机构独立 pgvector collection，用户级 user_id 过滤 |
| 工具权限沙箱 | 按 plan（free/starter/growth/enterprise）过滤可用工具集 |
| 机构人格 | 机构管理员可配置 Agent 教学风格、语气、知识领域 |
| 双层记忆 | 结构化（AgentMemory KV）+ 语义（mem0）互补 |
| Feature Flag | `USE_MEM0=true` 启用，默认关闭，渐进式上线 |

## 架构

```
用户对话
    │
    ▼
AIChatView
    │
    ├── Tool Permission Sandbox (filter_tools by plan)
    │
    ├── Prompt Assembly
    │   ├── base system prompt
    │   ├── institution personality (机构人格)
    │   ├── structured memory (AgentMemory KV)
    │   └── semantic memory (mem0 pgvector)
    │
    └── Agent Loop (call_ai_with_tools)
            │
            ▼
        后台提取记忆
            ├── extract_memories_async (结构化)
            └── extract_memories_with_mem0 (语义)
```

## 文件结构

```
backend/
├── ai_engine/
│   ├── config.py              # EMBEDDING_MODEL, EMBEDDING_BASE_URL
│   └── tool_permissions.py    # PLAN_TOOL_ACCESS, filter_tools()
├── ai_assistant/
│   ├── models.py              # Bot.institution_personality
│   ├── migrations/
│   │   └── 0008_add_institution_personality.py
│   ├── services/
│   │   ├── tenant_memory.py   # TenantMemoryManager (mem0 wrapper)
│   │   ├── memory_service.py  # extract_memories_with_mem0, get_mem0_memories_for_injection
│   │   ├── chat_service.py    # 人格注入 + 工具过滤
│   │   └── tool_executor.py   # self.institution
│   └── tests/
│       ├── test_tenant_memory.py      # 6 unit tests
│       ├── test_tool_permissions.py   # 9 unit tests
│       └── test_mem0_integration.py   # 3 integration tests (需 PG)
```

## 配置

### 环境变量

```bash
# 启用 mem0 语义记忆（默认 false）
USE_MEM0=true

# Embedding 模型配置（可选，有默认值）
AI_EMBEDDING_MODEL=deepseek-embedding
AI_EMBEDDING_BASE_URL=https://api.deepseek.com/v1
```

### 数据库要求

```sql
-- PostgreSQL 需要 pgvector 扩展
CREATE EXTENSION IF NOT EXISTS vector;
```

### 安装依赖

```bash
pip install mem0ai pgvector
```

## API 端点

### 语义记忆

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/ai/memories/semantics/` | 获取语义记忆列表 |
| GET | `/api/ai/memories/semantics/?limit=10` | 限制返回数量 |
| DELETE | `/api/ai/memories/semantics/<memory_id>/` | 删除单条记忆 |
| DELETE | `/api/ai/memories/semantics/clear/` | 清空全部记忆 |

### 工具权限（按 plan）

| Plan | assistant 工具 | planner 工具 | exam_generator 工具 |
|------|---------------|-------------|-------------------|
| free | 2 个基础 | 不可用 | 不可用 |
| starter | 4 个 | 3 个 | 2 个 |
| growth | 全部 | 全部 | 全部 |
| enterprise | 全部 | 全部 | 全部 |

### 机构人格配置

Bot 模型的 `institution_personality` JSONField：

```json
{
    "teaching_style": "严格",
    "knowledge_domain": "金融431",
    "tone": "专业",
    "custom_instructions": "不要用太多类比，直接讲公式推导"
}
```

## Prompt 自适应（Phase 3）

Agent 根据用户历史行为模式自动调整回复风格。

| 组件 | 文件 | 说明 |
|------|------|------|
| Pattern Detector | `ai_assistant/services/prompt_adapter.py` | 规则引擎，关键词匹配 8 种模式 |
| Integration | `ai_assistant/views.py` | 两条聊天路径（polling + streaming）均注入自适应指令 |
| Chat Service | `ai_assistant/services/chat_service.py` | `_build_agent_system_prompt` 接受 `adaptive_directives` 参数 |

**支持的模式**：

| 类别 | 模式 | 触发关键词 | 生成指令 |
|------|------|-----------|---------|
| 学习风格 | formula_oriented | 公式/推导/证明/计算 | 优先展示推导过程 |
| 学习风格 | visual_learner | 图/表/可视化/思维导图 | 多用表格和图示 |
| 学习风格 | example_driven | 例子/举例/实例/案例 | 先给例子再抽象 |
| 学习风格 | memorization_oriented | 背/记忆/口诀/速记 | 提供记忆技巧 |
| 回复长度 | prefers_brief | 简短/简洁/精简 | 控制 200 字以内 |
| 回复长度 | prefers_detailed | 详细/展开/深入 | 完整推导和解释 |
| 交互风格 | deep_questioner | 为什么/原理/本质 | 主动解释"为什么" |
| 交互风格 | critical_thinker | 错了/不对/质疑 | 注意逻辑严密性 |

**注入位置**：system prompt 末尾，格式为 `## 自适应指令（基于用户历史行为分析）`

## 主动反思与元认知（Phase 4）

Celery 定时任务，每日分析用户学习数据并生成高阶语义记忆。

| 组件 | 文件 | 说明 |
|------|------|------|
| Celery Task | `ai_assistant/tasks.py` → `reflect_user_learning` | 每日任务，分析活跃用户 |
| Beat Schedule | `school_system/settings.py` | 86400s 间隔 |

**分析维度**：

| 维度 | 数据源 | 生成洞察 |
|------|--------|---------|
| 做题错误率 | QuizExam.results | >60% → "掌握度低，加强基础"；<20% → "可尝试更高难度" |
| 使用频率 | AIChatMessage 计数 | ≥20 次/周 → "积极性高"；≤2 次/周 → "需要激励" |
| 学习时段 | AIChatMessage 小时分布 | 深夜 → "注意休息"；上午 → "高效学习者" |

**存储方式**：通过 mem0 存为语义记忆，metadata 标记 `source=meta_cognition`，下次对话自动注入。

## 测试

```bash
# 单元测试（33 个）
cd backend && python3 -m pytest ai_assistant/tests/ -v

# 集成测试（需 PG + pgvector + USE_MEM0=true）
USE_MEM0=true python3 -m pytest ai_assistant/tests/test_mem0_integration.py -v -m integration
```
