"""
LLM-driven memory analyzer: analyze user memories to detect learning patterns,
preferences, and cognitive state. Replaces rule-based keyword matching.

Part of xiaoyu self-evolution optimization.
"""

import json
import logging
from typing import List, Dict, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class UserProfile:
    """用户学习画像，由 LLM 分析记忆生成。"""
    learning_style: str  # formula_oriented, visual_learner, example_driven, memorization_oriented, balanced
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
   - balanced: 无明显偏好

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
{{
  "learning_style": "...",
  "response_length": "...",
  "interaction_style": "...",
  "cognitive_state": "...",
  "domain_expertise": "...",
  "confidence": 0.0,
  "reasoning": "分析依据..."
}}

注意：
- 只返回 JSON，不要有其他文字
- 如果记忆信息不足，使用 balanced 作为默认值
- confidence 根据记忆数量和质量判断
"""


def analyze_user_profile(
    memories: List[Dict],
    bot_type: str = "planner"
) -> Optional[UserProfile]:
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
            logger.warning("Empty response from LLM for profile analysis")
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
            logger.warning("Failed to parse LLM analysis JSON: %s", e)
            return None

    except Exception as e:
        logger.exception("LLM profile analysis failed: %s", e)
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
