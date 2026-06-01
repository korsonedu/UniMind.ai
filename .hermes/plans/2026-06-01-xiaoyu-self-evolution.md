# 小宇自进化优化实施计划

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** 将小宇的自适应指令从规则驱动升级为 LLM 驱动，并补齐 Memorix↔Agent 数据通路。

**Architecture:** 
- prompt_adapter.py 从关键词匹配升级为 LLM 分析，动态生成自适应指令
- Memorix 的难度衰减和知识嵌入信息反馈给小宇的工具函数
- 新增 trajectory 数据表，为后续 GEPA 自进化做数据储备

**Tech Stack:** Django ORM, OpenAI-compatible API, mem0, Memorix optimizer

---

## Phase 1: 自适应指令 LLM 化

### Task 1: 创建 LLM 分析服务

**Objective:** 创建 LLM 驱动的记忆分析服务，替代规则匹配

**Files:**
- Create: `backend/ai_assistant/services/memory_analyzer.py`

**Step 1: 实现 LLM 分析服务**

```python
"""
LLM-driven memory analyzer: analyze user memories to detect learning patterns,
preferences, and cognitive state. Replaces rule-based keyword matching.
"""

import json
import logging
from typing import List, Dict, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class UserProfile:
    """用户学习画像，由 LLM 分析记忆生成。"""
    learning_style: str  # formula_oriented, visual_learner, example_driven, memorization_oriented
    response_length: str  # prefers_brief, prefers_detailed, balanced
    interaction_style: str  # deep_questioner, critical_thinker, passive_learner
    cognitive_state: str  # focused, anxious, overwhelmed, motivated
    domain_expertise: str  # beginner, intermediate, advanced
    confidence: float  # 分析置信度 0-1
    raw_analysis: str  # LLM 原始分析


ANALYSIS_PROMPT = """你是一个学习行为分析专家。分析以下用户记忆，识别学习风格和当前状态。

用户记忆：
{memories}

请从以下维度分析用户：

1. **学习风格**（选一个）：
   - formula_oriented: 偏好公式推导和定量分析
   - visual_learner: 偏好图形化表达
   - example_driven: 偏好通过具体例子理解
   - memorization_oriented: 偏好记忆技巧

2. **回复长度偏好**（选一个）：
   - prefers_brief: 偏好简洁回答（200字以内）
   - prefers_detailed: 偏好详细解答
   - balanced: 根据问题复杂度自适应

3. **交互风格**（选一个）：
   - deep_questioner: 喜欢追问原理
   - critical_thinker: 会主动质疑
   - passive_learner: 主要接收信息

4. **当前认知状态**（选一个）：
   - focused: 专注高效
   - anxious: 焦虑紧迫（多次提到时间不够、来不及）
   - overwhelmed: 信息过载（同时处理多个知识点）
   - motivated: 积极主动

5. **领域专业度**（选一个）：
   - beginner: 初学者（基础概念问题多）
   - intermediate: 中级（能处理标准问题）
   - advanced: 高级（关注综合应用）

6. **置信度**：0-1，表示分析的确定程度

返回 JSON 格式：
{
  "learning_style": "...",
  "response_length": "...",
  "interaction_style": "...",
  "cognitive_state": "...",
  "domain_expertise": "...",
  "confidence": 0.0,
  "reasoning": "分析依据..."
}
"""


def analyze_user_profile(memories: List[Dict], bot_type: str = "planner") -> Optional[UserProfile]:
    """
    使用 LLM 分析用户记忆，生成学习画像。
    
    Args:
        memories: mem0 或 AgentMemory 格式的记忆列表
        bot_type: 'planner' 或 'exam_generator'
    
    Returns:
        UserProfile 或 None（如果分析失败）
    """
    if not memories:
        return None
    
    # 格式化记忆文本
    memory_texts = []
    for m in memories[:20]:  # 最多分析20条
        if isinstance(m, dict):
            if 'memory' in m:
                memory_texts.append(f"- {m['memory']}")
            elif 'key' in m and 'value' in m:
                memory_texts.append(f"- {m['key']}: {m['value']}")
    
    if not memory_texts:
        return None
    
    memories_str = "\n".join(memory_texts)
    prompt = ANALYSIS_PROMPT.format(memories=memories_str)
    
    try:
        from ai_engine.service import AIEngine
        
        messages = [
            {"role": "system", "content": "你是一个学习行为分析专家，只返回 JSON 格式分析结果。"},
            {"role": "user", "content": prompt}
        ]
        
        response = AIEngine.call_ai(
            messages,
            temperature=0.3,
            max_tokens=500,
            operation='memory.analyze_profile'
        )
        
        if not response or 'choices' not in response:
            return None
        
        content = response['choices'][0]['message']['content']
        
        # 解析 JSON
        try:
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0]
            elif '```' in content:
                content = content.split('```')[1].split('```')[0]
            
            data = json.loads(content.strip())
            
            return UserProfile(
                learning_style=data.get('learning_style', 'balanced'),
                response_length=data.get('response_length', 'balanced'),
                interaction_style=data.get('interaction_style', 'passive_learner'),
                cognitive_state=data.get('cognitive_state', 'focused'),
                domain_expertise=data.get('domain_expertise', 'intermediate'),
                confidence=float(data.get('confidence', 0.5)),
                raw_analysis=data.get('reasoning', '')
            )
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Failed to parse LLM analysis: %s", e)
            return None
    
    except Exception as e:
        logger.exception("LLM analysis failed: %s", e)
        return None


def profile_to_directives(profile: UserProfile, bot_type: str = "planner") -> str:
    """
    将用户画像转换为自适应指令字符串。
    
    Returns:
        格式化的指令字符串，用于注入 system prompt
    """
    if not profile:
        return ""
    
    directives = []
    
    # 学习风格指令
    style_directives = {
        "formula_oriented": "该学生偏好公式推导和定量分析。回答时优先展示推导过程和数学表达，再给出文字解释。",
        "visual_learner": "该学生偏好图形化表达。回答时多用表格、流程图、ASCII 图示来辅助说明。",
        "example_driven": "该学生偏好通过具体例子理解概念。回答时先给贴近生活的例子，再抽象总结。",
        "memorization_oriented": "该学生偏好记忆技巧和速记方法。回答时提供口诀、助记法、对比表格等记忆辅助。",
    }
    if profile.learning_style in style_directives:
        directives.append(f"- {style_directives[profile.learning_style]}")
    
    # 回复长度指令
    length_directives = {
        "prefers_brief": "该学生偏好简洁回答。控制回答在 200 字以内，用要点列表代替长段落。",
        "prefers_detailed": "该学生偏好详细解答。回答时展开每个要点，给出完整的推导和解释。",
    }
    if profile.response_length in length_directives:
        directives.append(f"- {length_directives[profile.response_length]}")
    
    # 交互风格指令
    interaction_directives = {
        "deep_questioner": "该学生喜欢追问原理和本质。回答时主动解释'为什么'，而非只说'是什么'。",
        "critical_thinker": "该学生会主动质疑和挑战。回答时注意逻辑严密性，主动说明边界条件和例外情况。",
    }
    if profile.interaction_style in interaction_directives:
        directives.append(f"- {interaction_directives[profile.interaction_style]}")
    
    # 认知状态指令
    state_directives = {
        "anxious": "该学生当前处于焦虑状态。回答时先共情、稳定情绪，再给出可立即执行的小步骤。",
        "overwhelmed": "该学生当前信息过载。回答时精简内容，只聚焦最紧急的 1 个问题。",
        "motivated": "该学生当前积极主动。可以适当增加挑战性任务，引导深度学习。",
    }
    if profile.cognitive_state in state_directives:
        directives.append(f"- {state_directives[profile.cognitive_state]}")
    
    if not directives:
        return ""
    
    return "## 自适应指令（基于用户历史行为分析）\n" + "\n".join(directives)
```

**Step 2: 验证服务可用**

Run: `python -c "from ai_assistant.services.memory_analyzer import analyze_user_profile, UserProfile; print('Import OK')"`

---

### Task 2: 更新 prompt_adapter.py 使用 LLM 分析

**Objective:** 修改 prompt_adapter.py，优先使用 LLM 分析，规则匹配作为 fallback

**Files:**
- Modify: `backend/ai_assistant/services/prompt_adapter.py`

**Step 1: 添加 LLM 分析函数**

在 `prompt_adapter.py` 末尾添加：

```python
def get_adaptive_directives_llm(memories: List[Dict], bot_type: str = "planner") -> str:
    """
    使用 LLM 分析生成自适应指令。
    
    优先使用 LLM 分析，如果失败则 fallback 到规则匹配。
    """
    try:
        from ai_assistant.services.memory_analyzer import analyze_user_profile, profile_to_directives
        
        profile = analyze_user_profile(memories, bot_type=bot_type)
        if profile and profile.confidence >= 0.6:
            return profile_to_directives(profile, bot_type=bot_type)
    except Exception as e:
        logger.warning("LLM analysis failed, falling back to rules: %s", e)
    
    # Fallback to rule-based
    return get_adaptive_directives(memories, bot_type=bot_type)
```

**Step 2: 验证函数可用**

Run: `python -c "from ai_assistant.services.prompt_adapter import get_adaptive_directives_llm; print('Import OK')"`

---

### Task 3: 更新 memory_service.py 使用新的自适应指令

**Objective:** 修改 memory_service.py 的 build_memory_context 函数，使用 LLM 驱动的自适应指令

**Files:**
- Modify: `backend/ai_assistant/services/memory_service.py:184-208`

**Step 1: 修改 build_memory_context 函数**

将第 199-204 行：
```python
        if USE_MEM0 and user.institution_id:
            from ai_assistant.services.prompt_adapter import get_adaptive_directives
            from ai_assistant.services.tenant_memory import TenantMemoryManager
            mgr = TenantMemoryManager(institution_id=user.institution_id)
            raw_memories = mgr.get_all(user_id=user.id)[:20]
            adaptive_directives = get_adaptive_directives(raw_memories, bot_type=bot_type)
```

修改为：
```python
        if USE_MEM0 and user.institution_id:
            from ai_assistant.services.prompt_adapter import get_adaptive_directives_llm
            from ai_assistant.services.tenant_memory import TenantMemoryManager
            mgr = TenantMemoryManager(institution_id=user.institution_id)
            raw_memories = mgr.get_all(user_id=user.id)[:20]
            adaptive_directives = get_adaptive_directives_llm(raw_memories, bot_type=bot_type)
```

**Step 2: 验证修改**

Run: `cd backend && python -c "from ai_assistant.services.memory_service import build_memory_context; print('Import OK')"`

---

## Phase 2: Memorix↔Agent 联动

### Task 4: 扩展小宇的 get_due_reviews 工具

**Objective:** 让 get_due_reviews 工具返回 Memorix 的难度衰减和知识嵌入信息

**Files:**
- Modify: `backend/ai_engine/tools.py` (找到 get_due_reviews 工具函数)

**Step 1: 查看当前 get_due_reviews 实现**

Run: `grep -n "get_due_reviews" backend/ai_engine/tools.py | head -20`

**Step 2: 扩展返回字段**

在 get_due_reviews 函数中，增加 Memorix 的难度和稳定性字段：

```python
# 在返回的每个复习项中添加：
{
    "question_id": ...,
    "knowledge_point": ...,
    "due_date": ...,
    "retrievability": ...,
    # 新增 Memorix 字段
    "difficulty": card.difficulty,  # 难度衰减值（1-10）
    "stability": card.stability,  # 记忆稳定性（天数）
    "lapse_count": card.lapse_count,  # 遗忘次数
    "memorix_priority": _calculate_memorix_priority(card),  # 基于 Memorix 的优先级
}

def _calculate_memorix_priority(card) -> str:
    """基于 Memorix 数据计算复习优先级。"""
    if card.lapse_count >= 3:
        return "critical"  # 反复遗忘，需要重点关注
    if card.difficulty >= 7:
        return "high"  # 高难度
    if card.stability < 2:
        return "high"  # 稳定性低
    if card.stability < 7:
        return "medium"
    return "low"
```

---

### Task 5: 添加知识点难度分析工具

**Objective:** 新增工具，让小宇可以查询知识点的 Memorix 难度分布

**Files:**
- Modify: `backend/ai_engine/tools.py`
- Modify: `backend/prompts/ai_assistant/bots/xiaoyu/tool_guide.txt`

**Step 1: 添加新工具函数**

```python
def get_knowledge_difficulty_analysis(user_id: int, subject: str = None) -> Dict:
    """
    获取知识点的 Memorix 难度分析。
    
    Returns:
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
    """
    from quizzes.models import ReviewCard, KnowledgePoint
    
    # 获取用户的复习卡片
    cards = ReviewCard.objects.filter(
        user_id=user_id,
        is_active=True
    ).select_related('knowledge_point')
    
    if subject:
        cards = cards.filter(knowledge_point__subject=subject)
    
    # 按知识点聚合
    kp_stats = {}
    for card in cards:
        kp_name = card.knowledge_point.name
        if kp_name not in kp_stats:
            kp_stats[kp_name] = {
                "difficulties": [],
                "stabilities": [],
                "total_reviews": 0,
                "lapse_counts": []
            }
        kp_stats[kp_name]["difficulties"].append(card.difficulty)
        kp_stats[kp_name]["stabilities"].append(card.stability)
        kp_stats[kp_name]["total_reviews"] += card.review_count
        kp_stats[kp_name]["lapse_counts"].append(card.lapse_count)
    
    # 计算统计
    knowledge_points = []
    for kp_name, stats in kp_stats.items():
        avg_diff = sum(stats["difficulties"]) / len(stats["difficulties"])
        avg_stab = sum(stats["stabilities"]) / len(stats["stabilities"])
        total_lapses = sum(stats["lapse_counts"])
        
        # 判断掌握程度
        if avg_diff >= 7 or avg_stab < 2:
            mastery = "weak"
        elif avg_diff >= 5 or avg_stab < 5:
            mastery = "developing"
        else:
            mastery = "strong"
        
        # 生成 Memorix 洞察
        insight_parts = []
        if avg_diff >= 7:
            insight_parts.append(f"平均难度较高（{avg_diff:.1f}）")
        if avg_stab < 3:
            insight_parts.append(f"记忆稳定性低（{avg_stab:.1f}天）")
        if total_lapses >= 5:
            insight_parts.append(f"累计遗忘 {total_lapses} 次")
        
        if insight_parts:
            insight = f"该知识点{', '.join(insight_parts)}，建议增加复习频率并使用间隔重复策略"
        else:
            insight = "该知识点掌握情况良好"
        
        knowledge_points.append({
            "name": kp_name,
            "avg_difficulty": round(avg_diff, 1),
            "avg_stability": round(avg_stab, 1),
            "total_reviews": stats["total_reviews"],
            "mastery_level": mastery,
            "memorix_insight": insight
        })
    
    # 按难度排序
    knowledge_points.sort(key=lambda x: x["avg_difficulty"], reverse=True)
    
    weak_count = sum(1 for kp in knowledge_points if kp["mastery_level"] == "weak")
    
    return {
        "knowledge_points": knowledge_points,
        "summary": f"共 {len(knowledge_points)} 个知识点，其中 {weak_count} 个需要重点关注"
    }
```

**Step 2: 更新 tool_guide.txt**

在 `backend/prompts/ai_assistant/bots/xiaoyu/tool_guide.txt` 末尾添加：

```
**get_knowledge_difficulty_analysis**：
- 用途：获取知识点的 Memorix 难度分析
- 参数：
  - subject (可选): 学科名称
- 返回：
  - knowledge_points: 知识点列表，包含 avg_difficulty、avg_stability、mastery_level、memorix_insight
  - summary: 汇总信息
- 使用场景：当学生问"我哪些知识点最薄弱"或"为什么我总是记不住"时调用
```

---

## Phase 3: Trajectory 数据收集（为 GEPA 准备）

### Task 6: 创建 Trajectory 数据表

**Objective:** 创建存储对话 trajectory 的数据表，为后续 GEPA 自进化做数据储备

**Files:**
- Create: `backend/ai_assistant/migrations/0014_add_trajectory.py`（自动生成）

**Step 1: 更新 models.py**

在 `backend/ai_assistant/models.py` 末尾添加：

```python
class AITrajectory(models.Model):
    """Agent 对话轨迹，用于后续 GEPA 自进化优化。"""
    
    OUTCOME_CHOICES = (
        ('success', '成功'),
        ('partial', '部分成功'),
        ('failure', '失败'),
        ('unknown', '未知'),
    )
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='trajectories')
    bot = models.ForeignKey('Bot', on_delete=models.CASCADE, related_name='trajectories')
    conversation_id = models.UUIDField(db_index=True)
    
    # Trajectory 数据
    messages = models.JSONField(help_text="完整对话记录")
    tool_calls = models.JSONField(default=list, help_text="工具调用序列")
    tool_outputs = models.JSONField(default=list, help_text="工具返回结果")
    
    # 结果评估
    outcome = models.CharField(max_length=20, choices=OUTCOME_CHOICES, default='unknown')
    outcome_metrics = models.JSONField(default=dict, help_text="结果指标：掌握率变化、任务完成度等")
    
    # Prompt 变体（用于 A/B 测试）
    prompt_variant = models.CharField(max_length=50, default='baseline', help_text="使用的 prompt 变体标识")
    
    # 元数据
    created_at = models.DateTimeField(auto_now_add=True)
    evaluated_at = models.DateTimeField(null=True, blank=True, help_text="结果评估时间")
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'bot', 'created_at']),
            models.Index(fields=['conversation_id']),
            models.Index(fields=['outcome', 'created_at']),
        ]
        verbose_name = '对话轨迹'
        verbose_name_plural = '对话轨迹'
    
    def __str__(self):
        return f"{self.user} - {self.bot.name} - {self.conversation_id}"
```

**Step 2: 生成迁移文件**

Run: `cd backend && python manage.py makemigrations ai_assistant`

**Step 3: 验证迁移文件**

Run: `cat backend/ai_assistant/migrations/0014_add_trajectory.py | head -30`

---

### Task 7: 添加 Trajectory 记录服务

**Objective:** 创建记录对话 trajectory 的服务函数

**Files:**
- Create: `backend/ai_assistant/services/trajectory_recorder.py`

**Step 1: 实现记录服务**

```python
"""
Trajectory recorder: capture agent conversations for GEPA self-evolution.
"""

import logging
from typing import Dict, List, Optional
from django.utils import timezone
from ..models import AITrajectory

logger = logging.getLogger(__name__)


def record_trajectory(
    user_id: int,
    bot_id: int,
    conversation_id: str,
    messages: List[Dict],
    tool_calls: List[Dict],
    tool_outputs: List[Dict],
    prompt_variant: str = 'baseline'
) -> AITrajectory:
    """
    记录一条对话轨迹。
    
    Args:
        user_id: 用户 ID
        bot_id: Bot ID
        conversation_id: 会话 ID
        messages: 对话消息列表
        tool_calls: 工具调用序列
        tool_outputs: 工具返回结果
        prompt_variant: 使用的 prompt 变体标识
    
    Returns:
        创建的 AITrajectory 实例
    """
    try:
        trajectory = AITrajectory.objects.create(
            user_id=user_id,
            bot_id=bot_id,
            conversation_id=conversation_id,
            messages=messages,
            tool_calls=tool_calls,
            tool_outputs=tool_outputs,
            prompt_variant=prompt_variant,
        )
        
        logger.info("Recorded trajectory %d for user %d, conversation %s", 
                    trajectory.id, user_id, conversation_id)
        return trajectory
    
    except Exception as e:
        logger.exception("Failed to record trajectory: %s", e)
        return None


def evaluate_trajectory(
    trajectory_id: int,
    outcome: str,
    outcome_metrics: Dict
) -> bool:
    """
    评估一条轨迹的结果。
    
    Args:
        trajectory_id: 轨迹 ID
        outcome: 结果类型 ('success', 'partial', 'failure')
        outcome_metrics: 结果指标
    
    Returns:
        是否成功更新
    """
    try:
        trajectory = AITrajectory.objects.get(id=trajectory_id)
        trajectory.outcome = outcome
        trajectory.outcome_metrics = outcome_metrics
        trajectory.evaluated_at = timezone.now()
        trajectory.save(update_fields=['outcome', 'outcome_metrics', 'evaluated_at'])
        
        logger.info("Evaluated trajectory %d: %s", trajectory_id, outcome)
        return True
    
    except AITrajectory.DoesNotExist:
        logger.warning("Trajectory %d not found", trajectory_id)
        return False
    except Exception as e:
        logger.exception("Failed to evaluate trajectory: %s", e)
        return False


def get_trajectory_stats(user_id: int, days: int = 30) -> Dict:
    """
    获取用户的轨迹统计。
    
    Returns:
        {
            "total": 45,
            "success_rate": 0.78,
            "avg_tool_calls": 3.2,
            "prompt_variants": {"baseline": 40, "v1": 5}
        }
    """
    from django.utils import timezone
    from django.db.models import Count, Avg
    from datetime import timedelta
    
    start_date = timezone.now() - timedelta(days=days)
    
    trajectories = AITrajectory.objects.filter(
        user_id=user_id,
        created_at__gte=start_date
    )
    
    total = trajectories.count()
    if total == 0:
        return {"total": 0, "success_rate": 0, "avg_tool_calls": 0, "prompt_variants": {}}
    
    success_count = trajectories.filter(outcome='success').count()
    
    # 计算平均工具调用数（需要从 JSON 字段计算）
    total_tool_calls = sum(len(t.tool_calls) for t in trajectories.only('tool_calls'))
    
    # 统计 prompt 变体分布
    variant_counts = trajectories.values_list('prompt_variant').annotate(
        count=Count('id')
    )
    variants = {v[0]: v[1] for v in variant_counts}
    
    return {
        "total": total,
        "success_rate": round(success_count / total, 2),
        "avg_tool_calls": round(total_tool_calls / total, 1),
        "prompt_variants": variants
    }
```

**Step 2: 验证服务可用**

Run: `python -c "from ai_assistant.services.trajectory_recorder import record_trajectory; print('Import OK')"`

---

### Task 8: 更新文档

**Objective:** 更新所有相关文档，记录本次优化

**Files:**
- Create: `docs/tech/features/ADAPTIVE_PROMPT_LLM.md`
- Create: `docs/tech/features/MEMORIX_AGENT_INTEGRATION.md`
- Create: `docs/tech/features/GEPA_TRAJECTORY.md`
- Modify: `docs/tech/AI_SYSTEM_REFERENCE.md`（如果存在）

**Step 1: 创建自适应指令 LLM 文档**

Create `docs/tech/features/ADAPTIVE_PROMPT_LLM.md`:

```markdown
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
- learning_style: 学习风格（formula_oriented, visual_learner, example_driven, memorization_oriented）
- response_length: 回复长度偏好（prefers_brief, prefers_detailed, balanced）
- interaction_style: 交互风格（deep_questioner, critical_thinker, passive_learner）
- cognitive_state: 认知状态（focused, anxious, overwhelmed, motivated）
- domain_expertise: 领域专业度（beginner, intermediate, advanced）

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
```

**Step 2: 创建 Memorix↔Agent 联动文档**

Create `docs/tech/features/MEMORIX_AGENT_INTEGRATION.md`:

```markdown
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
- `lapse_count`: 遗忘次数，反复遗忘需要重点关注
- `memorix_priority`: 基于 Memorix 的优先级（critical/high/medium/low）

**优先级计算逻辑：**
```python
if lapse_count >= 3:
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
```

**Step 3: 创建 Trajectory 数据收集文档**

Create `docs/tech/features/GEPA_TRAJECTORY.md`:

```markdown
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
from ai_assistant.models import AITrajectory

successful_trajectories = AITrajectory.objects.filter(
    outcome='success',
    outcome_metrics__knowledge_mastery_delta__gte=0.2
).order_by('-created_at')[:100]
```

## 配置

无需额外配置。当 `USE_MEM0=true` 时自动启用 trajectory 记录。

## 后续优化

- 自动评估：使用 LLM 自动评估对话质量
- Prompt 变体库：管理多个 prompt 变体
- GEPA 集成：对接 DSPy GEPA optimizer
- A/B 测试框架：自动分配变体并收集对比数据
```

---

## 执行顺序

1. Task 1-3: 自适应指令 LLM 化（最快见效）
2. Task 4-5: Memorix↔Agent 联动（补齐数据通路）
3. Task 6-7: Trajectory 数据收集（为 GEPA 准备）
4. Task 8: 文档更新

## 验证清单

- [ ] 自适应指令 LLM 分析可用
- [ ] 规则匹配作为 fallback 正常工作
- [ ] get_due_reviews 返回 Memorix 字段
- [ ] get_knowledge_difficulty_analysis 工具可用
- [ ] AITrajectory 迁移文件生成
- [ ] trajectory_recorder 服务可用
- [ ] 所有文档创建完成
- [ ] `make backend-check` 通过
- [ ] `make frontend-check` 通过
