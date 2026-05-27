"""
Prompt self-adaptation: analyze semantic memories to detect user patterns,
then generate adaptive prompt directives for the Agent's system prompt.

Rule-based (no LLM calls) for speed and cost. Patterns are detected via
keyword matching on mem0 semantic memory text.
"""

import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

# Pattern rules: (keywords, directive)
# Keywords are checked against memory text (case-insensitive, Chinese)
_LEARNING_STYLE_RULES = [
    {
        "keywords": ["公式", "推导", "证明", "数学", "计算", "定量"],
        "label": "formula_oriented",
        "directive": "该学生偏好公式推导和定量分析。回答时优先展示推导过程和数学表达，再给出文字解释。",
    },
    {
        "keywords": ["图", "表", "可视化", "流程图", "思维导图", "示意"],
        "label": "visual_learner",
        "directive": "该学生偏好图形化表达。回答时多用表格、流程图、ASCII 图示来辅助说明。",
    },
    {
        "keywords": ["例子", "举例", "实例", "案例", "具体", "场景"],
        "label": "example_driven",
        "directive": "该学生偏好通过具体例子理解概念。回答时先给贴近生活的例子，再抽象总结。",
    },
    {
        "keywords": ["背", "记忆", "口诀", "速记", "技巧"],
        "label": "memorization_oriented",
        "directive": "该学生偏好记忆技巧和速记方法。回答时提供口诀、助记法、对比表格等记忆辅助。",
    },
]

_RESPONSE_LENGTH_RULES = [
    {
        "keywords": ["简短", "简洁", "精简", "别太长", "少说", "要点"],
        "label": "prefers_brief",
        "directive": "该学生偏好简洁回答。控制回答在 200 字以内，用要点列表代替长段落。",
    },
    {
        "keywords": ["详细", "展开", "深入", "完整", "全面", "具体说明"],
        "label": "prefers_detailed",
        "directive": "该学生偏好详细解答。回答时展开每个要点，给出完整的推导和解释。",
    },
]

_INTERACTION_STYLE_RULES = [
    {
        "keywords": ["为什么", "原理", "本质", "根本原因", "深层"],
        "label": "deep_questioner",
        "directive": "该学生喜欢追问原理和本质。回答时主动解释'为什么'，而非只说'是什么'。",
    },
    {
        "keywords": ["错了", "不对", "但是", "可是", "质疑", "反驳"],
        "label": "critical_thinker",
        "directive": "该学生会主动质疑和挑战。回答时注意逻辑严密性，主动说明边界条件和例外情况。",
    },
]


def detect_patterns(memories: List[Dict]) -> List[str]:
    """Analyze memory texts and return matched pattern labels.

    Args:
        memories: list of dicts with 'memory' key (mem0 format)
                  or list of dicts with 'key'+'value' keys (AgentMemory format)

    Returns:
        List of matched pattern labels (deduplicated)
    """
    if not memories:
        return []

    # Flatten all memory text into a single corpus
    texts = []
    for m in memories:
        if isinstance(m, dict):
            if 'memory' in m:
                texts.append(m['memory'])
            elif 'key' in m and 'value' in m:
                texts.append(f"{m['key']} {m['value']}")

    corpus = " ".join(texts).lower()
    if not corpus:
        return []

    matched = []
    all_rules = (
        _LEARNING_STYLE_RULES
        + _RESPONSE_LENGTH_RULES
        + _INTERACTION_STYLE_RULES
    )

    for rule in all_rules:
        for kw in rule["keywords"]:
            if kw in corpus:
                matched.append(rule["label"])
                break

    return list(set(matched))


def get_adaptive_directives(memories: List[Dict]) -> str:
    """Generate adaptive prompt directives from semantic memories.

    Returns a formatted string to inject into system prompt, or empty string
    if no patterns detected.
    """
    labels = detect_patterns(memories)
    if not labels:
        return ""

    label_to_directive = {}
    all_rules = (
        _LEARNING_STYLE_RULES
        + _RESPONSE_LENGTH_RULES
        + _INTERACTION_STYLE_RULES
    )
    for rule in all_rules:
        label_to_directive[rule["label"]] = rule["directive"]

    directives = []
    for label in labels:
        if label in label_to_directive:
            directives.append(f"- {label_to_directive[label]}")

    if not directives:
        return ""

    return "## 自适应指令（基于用户历史行为分析）\n" + "\n".join(directives)
