# Multi-Tenant Agent with mem0 Self-Evolving Memory

**日期**: 2026-05-26
**状态**: Draft
**作者**: eular + Claude

## 1. 动机

当前 Agent 记忆系统是扁平 KV（`AgentMemory`），无语义检索，无自动去重，记忆注入是固定 800 字符的静态列表。用户用久了 Agent 也不会"变聪明"——没有自我进化能力。

目标：构建一个**多租户隔离、语义记忆、自我进化**的 Agent 系统，让每个用户感受到"专属 AI 助教"。

## 2. 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                     Frontend (React 19)                      │
│         Agent Chat UI / Memory Dashboard / Settings          │
└─────────────────────┬───────────────────────────────────────┘
                      │ POST /api/ai/chat/
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                   AIChatView (Django)                        │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │ Tool Perms   │  │ Prompt       │  │ Memory Injection   │  │
│  │ Sandbox      │  │ Assembly     │  │ (dual-layer)       │  │
│  └─────────────┘  └──────────────┘  └───────────────────┘  │
└─────────────────────┬───────────────────────────────────────┘
                      │
         ┌────────────┼────────────┐
         ▼            ▼            ▼
   ┌──────────┐ ┌──────────┐ ┌──────────┐
   │Assistant │ │ Planner  │ │ ExamGen  │
   │ToolExec  │ │ToolExec  │ │ToolExec  │
   └──────────┘ └──────────┘ └──────────┘
                      │
┌─────────────────────────────────────────────────────────────┐
│                    Dual-Layer Memory                         │
│  ┌─────────────────────┐  ┌──────────────────────────────┐ │
│  │ Layer 1: Structured  │  │ Layer 2: mem0 (pgvector)     │ │
│  │ AgentMemory (KV)     │  │ - 语义检索                    │ │
│  │ - 知识点掌握度        │  │ - 自动提取                    │ │
│  │ - 学习计划状态        │  │ - 去重/衰减                   │ │
│  │ - ELO 分数           │  │ - 主动反思                    │ │
│  │ (PostgreSQL)         │  │ - Prompt 自适应               │ │
│  └─────────────────────┘  └──────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                      │
         ┌────────────┼────────────┐
         ▼                         ▼
┌─────────────────┐      ┌─────────────────┐
│  PostgreSQL     │      │  pgvector        │
│  (business)     │      │  (embeddings)    │
│  + pgvector ext │      │                  │
└─────────────────┘      └─────────────────┘
```

## 3. 双层记忆模型

### 3.1 Layer 1：结构化记忆（保留现有）

不变。关系型 DB 存储精确可查询的数据：

| 数据类型 | 模型 | 用途 |
|----------|------|------|
| 知识点掌握度 | `KnowledgeMastery` | Memorix 调度、薄弱点分析 |
| 学习计划 | `StudyPlan` + `StudyPlanTask` | 计划追踪、任务状态 |
| ELO 分数 | `UserELO` | 难度自适应 |
| 错题记录 | `QuestionRecord` | 错题重练 |
| 诊断结果 | `DiagnosticResult` | 初始化画像 |

这些数据需要精确查询（"掌握度 < 0.6 的知识点"），不适合向量检索。

### 3.2 Layer 2：mem0 语义记忆（新增）

用 mem0 Python SDK（local mode），底层接 pgvector：

```python
# backend/ai_assistant/services/tenant_memory.py

from mem0 import Memory

class TenantMemoryManager:
    """两级隔离的 mem0 管理器"""

    def __init__(self, institution_id: int):
        self.config = {
            "vector_store": {
                "provider": "pgvector",
                "config": {
                    "host": settings.DB_HOST,
                    "port": settings.DB_PORT,
                    "dbname": settings.DB_NAME,
                    "user": settings.DB_USER,
                    "password": settings.DB_PASSWORD,
                    "collection_name": f"inst_{institution_id}",
                }
            },
            "embedder": {
                "provider": "openai",
                "config": {
                    "api_key": settings.LLM_API_KEY,
                    "base_url": settings.LLM_BASE_URL,
                    "model": "text-embedding-3-small",
                }
            },
            "version": "v1.1",
        }
        self.memory = Memory.from_config(self.config)

    def add(self, user_id: int, message: str, metadata: dict = None):
        """对话后自动提取记忆"""
        self.memory.add(
            message,
            user_id=str(user_id),
            metadata={**(metadata or {}), "institution_id": self.institution_id},
        )

    def search(self, user_id: int, query: str, limit: int = 5) -> list:
        """语义检索相关记忆"""
        return self.memory.search(query, user_id=str(user_id), limit=limit)

    def get_all(self, user_id: int) -> list:
        """获取用户全部记忆"""
        return self.memory.get_all(user_id=str(user_id))

    def delete(self, user_id: int, memory_id: str):
        """删除单条记忆"""
        self.memory.delete(memory_id)

    def delete_all(self, user_id: int):
        """清空用户全部记忆"""
        self.memory.delete_all(user_id=str(user_id))
```

### 3.3 两层协作模式

```
用户问："我三角函数怎么样？"
    │
    ├── Layer 2 (mem0 语义检索) → "该生三角函数公式记忆弱，但图形理解强"
    │                               (语义匹配，非精确查询)
    │
    └── Layer 1 (结构化查询) → KnowledgeMastery(trig, 0.42)
                                 (精确数值，Memorix 调度依据)
    │
    ▼
Agent 回复："你三角函数掌握度 42%，主要弱在公式推导。
            不过你图形理解能力很强，我建议用单位圆来辅助记忆公式。"
```

两层互补：mem0 提供"理解"，结构化层提供"数据"。

## 4. 租户隔离策略

### 4.1 数据隔离（pgvector collection）

每个机构一个 pgvector collection，物理隔离向量数据：

```
pgvector collections:
├── inst_1      ← 机构 A 所有用户的记忆
├── inst_2      ← 机构 B 所有用户的记忆
├── inst_3      ← 机构 C 所有用户的记忆
└── global      ← 平台级共享记忆（所有机构可读）
```

- 机构间：collection 级隔离，查询天然不跨 collection
- 机构内：mem0 内置 `user_id` 过滤
- 全局共享：`global` collection 存储平台通用知识

### 4.2 工具权限沙箱

扩展现有 `HasPlanFeature` 到 Agent 工具层：

```python
# backend/ai_engine/tool_permissions.py

PLAN_TOOL_ACCESS = {
    "free": {
        "assistant": ["search_knowledge_tree", "get_user_weak_points"],
        "planner": [],
        "exam_generator": [],
    },
    "starter": {
        "assistant": [
            "search_knowledge_tree", "get_user_weak_points",
            "get_user_wrong_questions", "search_courses",
        ],
        "planner": [
            "get_learning_stats", "get_knowledge_mastery_map",
            "get_due_reviews",
        ],
        "exam_generator": ["search_knowledge_points", "generate_questions"],
    },
    "growth": {
        "assistant": "all",
        "planner": "all",
        "exam_generator": "all",
    },
    "enterprise": {
        "assistant": "all",
        "planner": "all",
        "exam_generator": "all",
    },
}


def filter_tools(bot_type: str, institution, all_tools: list) -> list:
    """按 plan 过滤可用工具"""
    plan = institution.plan if institution else "free"
    allowed = PLAN_TOOL_ACCESS.get(plan, PLAN_TOOL_ACCESS["free"]).get(bot_type, [])
    if allowed == "all":
        return all_tools
    return [t for t in all_tools if t["function"]["name"] in allowed]
```

在 `AIChatView` 构建工具列表时调用 `filter_tools()`。

### 4.3 机构级 Agent 人格

Bot 模型扩展：

```python
class Bot(models.Model):
    # ... existing fields ...
    institution_personality = models.JSONField(
        default=dict, blank=True,
        help_text="机构自定义人格配置",
    )
    # 示例：
    # {
    #   "teaching_style": "严格",
    #   "knowledge_domain": "金融431",
    #   "tone": "专业",
    #   "custom_instructions": "不要用太多类比，直接讲公式推导"
    # }
```

## 5. 自我进化机制

### 5.1 维度 1：对话驱动记忆积累

mem0 核心能力，替换现有 `extract_memories_async()`：

```python
# 在 process_ai_chat 完成后调用
def post_chat_memory_extraction(user, bot, conversation_text):
    tenant_memory = TenantMemoryManager(user.institution_id)
    tenant_memory.add(
        user_id=user.id,
        message=conversation_text,
        metadata={
            "bot_type": bot.bot_type,
            "timestamp": now().isoformat(),
        },
    )
```

**对比现有 memory_service.py**：
- 提取更智能：mem0 内置多种提取策略，不是单次 LLM 调用
- 自动去重合并：相似记忆合并更新，不会出现重复条目
- 语义检索：基于当前对话上下文检索相关记忆，而非全量注入

### 5.2 维度 2：主动反思与元认知

Agent 主动分析用户数据，生成高阶认知记忆：

```python
# backend/ai_assistant/services/meta_cognition.py

class MetaCognitionEngine:
    """定期分析用户学习数据，生成元认知记忆"""

    def reflect(self, user_id: int):
        """由 Celery 定时任务触发，每周一次"""

        # 1. 从结构化层拉数据
        mastery = self._get_mastery_distribution(user_id)
        wrong_qs = self._get_recent_wrong_questions(user_id, days=30)
        study_time = self._get_study_time_distribution(user_id)

        # 2. LLM 生成元认知分析
        analysis = AIEngine.call_ai(
            system_prompt="你是学习分析专家，分析学生数据并给出教学策略建议。",
            user_prompt=f"""
            分析该学生近30天学习数据：
            - 知识点掌握度分布：{mastery}
            - 近期错题分布：{wrong_qs}
            - 学习时长分布：{study_time}

            输出 JSON:
            {{
                "strengths": ["强项领域"],
                "weaknesses": ["薄弱领域"],
                "learning_pattern": "学习模式描述",
                "teaching_strategy": "给 Agent 的教学策略建议"
            }}
            """,
        )

        # 3. 存入 mem0
        tenant_memory = TenantMemoryManager(user.institution_id)
        tenant_memory.add(
            user_id=user_id,
            message=f"[元认知分析] 强项：{analysis['strengths']}，"
                    f"薄弱：{analysis['weaknesses']}，"
                    f"学习模式：{analysis['learning_pattern']}，"
                    f"教学策略：{analysis['teaching_strategy']}",
            metadata={
                "type": "meta_cognition",
                "confidence": 0.8,
                "generated_at": now().isoformat(),
            },
        )
```

**Celery 定时任务**：

```python
# backend/ai_assistant/tasks.py

@celery_app.task
def run_weekly_meta_cognition():
    """每周日凌晨 3 点跑"""
    from users.models import User
    active_users = User.objects.filter(
        last_login__gte=now() - timedelta(days=30),
        institution__isnull=False,
    )
    engine = MetaCognitionEngine()
    for user in active_users:
        try:
            engine.reflect(user.id)
        except Exception as e:
            logger.error(f"Meta-cognition failed for user {user.id}: {e}")
```

### 5.3 维度 3：Prompt 自适应

system prompt 根据记忆动态调整：

```python
# backend/ai_assistant/services/adaptive_prompt.py

class AdaptivePromptBuilder:
    """基于记忆自适应构建 system prompt"""

    def build(self, base_prompt: str, user, institution) -> str:
        sections = [base_prompt]

        # 1. 机构人格注入
        if institution and institution.bot_personality:
            sections.append(
                f"## 机构教学风格\n{institution.bot_personality}"
            )

        # 2. mem0 语义检索相关记忆
        tenant_memory = TenantMemoryManager(user.institution_id)
        memories = tenant_memory.get_all(user.id)

        if memories:
            preferences = [m for m in memories
                          if m.get("metadata", {}).get("type") == "preference"]
            meta_cognition = [m for m in memories
                             if m.get("metadata", {}).get("type") == "meta_cognition"]
            other = [m for m in memories
                    if m.get("metadata", {}).get("type") not in ("preference", "meta_cognition")]

            if preferences:
                sections.append("## 学习偏好\n" +
                    "\n".join(f"- {m['memory']}" for m in preferences[:5]))

            if meta_cognition:
                sections.append(f"## 教学策略建议\n{meta_cognition[0]['memory']}")

            if other:
                sections.append("## 用户记忆\n" +
                    "\n".join(f"- {m['memory']}" for m in other[:5]))

        # 3. 工具指南（按 plan 过滤后的）
        sections.append(self._get_tool_guide(user, institution))

        return "\n\n".join(sections)
```

### 5.4 进化闭环

```
用户对话
    │
    ▼
mem0 自动提取记忆 (每次对话后)
    │
    ▼
定期反思生成元认知 (每周)
    │
    ▼
Prompt 自适应 (每次对话前)
    │
    ▼
Agent 回复更精准
    │
    ▼
用户更愿意对话 → 更多记忆 → (循环)
```

## 6. 前端：记忆管理 UI

用户可查看、编辑、删除自己的记忆：

### 6.1 API 端点

```
GET    /api/ai/memories/semantics/          # 获取语义记忆列表
DELETE /api/ai/memories/semantics/<id>/     # 删除单条
DELETE /api/ai/memories/semantics/clear/    # 清空全部
GET    /api/ai/memories/insights/           # 获取元认知洞察
```

### 6.2 UI 组件

在 Settings 页面新增"AI 记忆"tab：
- 记忆列表（分类展示：偏好、学术、互动）
- 每条可查看、可删除
- "清空所有记忆"按钮（二次确认）
- 元认知洞察展示（强项/薄弱/学习模式）

## 7. 实施分阶段

### Phase 1：mem0 + pgvector 基础集成
- 安装 pgvector 扩展
- 集成 mem0 Python SDK
- 实现 `TenantMemoryManager`
- 替换 `memory_service.py` 的提取逻辑
- 语义检索替换固定 800 字符注入
- **验证**: Agent 能从 mem0 检索到相关记忆并注入 prompt

### Phase 2：工具权限沙箱 + 机构人格
- 实现 `PLAN_TOOL_ACCESS` 配置
- 实现 `filter_tools()` 过滤
- Bot 模型扩展 `institution_personality` 字段
- 前端机构人格配置 UI
- **验证**: free plan 用户无法使用 growth 工具

### Phase 3：Prompt 自适应
- 实现 `AdaptivePromptBuilder`
- 替换现有 `_build_agent_system_prompt()` 逻辑
- **验证**: Agent 回复风格随用户记忆变化

### Phase 4：主动反思与元认知
- 实现 `MetaCognitionEngine`
- 配置 Celery 定时任务
- 前端记忆管理 UI
- **验证**: 元认知记忆在对话中被正确使用

## 8. 技术选型

| 组件 | 选择 | 理由 |
|------|------|------|
| 向量数据库 | pgvector | 现有 PG 加扩展，零新增基础设施 |
| 记忆框架 | mem0 (Python SDK, local mode) | 官方支持 pgvector，内置去重/衰减 |
| Embedding | DeepSeek embedding / text-embedding-3-small | 与现有 LLM 供应商一致 |
| 定时任务 | Celery (existing) | 已有 Celery infrastructure |

## 9. 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| mem0 版本不稳定 | API 变动 | 锁定版本，封装 TenantMemoryManager 隔离变化 |
| pgvector 性能 | >100万向量时检索慢 | 当前规模够用；未来可迁移 Qdrant（mem0 抽象层支持） |
| Embedding 成本 | 每次对话都调 embedding | 用 DeepSeek embedding（便宜）；控制提取频率 |
| 元认知 LLM 成本 | 每周 N 个用户 × 1 次 LLM 调用 | 只对活跃用户（30天内有对话）跑；用 fast 模型 |
| 记忆噪音 | mem0 提取到无关信息 | confidence 阈值过滤；用户可手动删除 |

## 10. 成功标准

- [ ] Agent 能基于语义检索到的记忆回答"这个学生怎么样"类问题
- [ ] 不同机构的 Agent 数据完全隔离（collection 级）
- [ ] free plan 用户无法使用 growth 工具
- [ ] Agent 回复风格随用户记忆积累而变化
- [ ] 元认知分析每周自动生成
- [ ] 用户可在设置中查看和管理自己的记忆
