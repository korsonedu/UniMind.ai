"""
Experience Extractor — 从 Agent 对话轨迹中提取可复用规律。

核心思路：
- 不只看"哪里失败了"，而是从成功/失败轨迹中提取"学到了什么可复用的规律"
- 规律是陈述性的、有范围有触发条件的，不是一次性修复方案

Phase 1：仅从轨迹文本提取规律，路由判断和验证留到后续阶段。
"""

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

EXTRACTION_SYSTEM_PROMPT = """你是一个 Agent 行为分析师。你的任务是从 AI 学习助手的对话轨迹中提取可复用的教学规律。

## 输入格式
你会收到一段完整的对话轨迹，包含：
- 用户（学生）的问题
- AI 助手的回复和工具调用
- 工具返回的结果
- 对话的最终评估（成功/失败/部分成功）

## 你的任务
从这段轨迹中提取 **0-3 条可复用的规律**。规律不是对这段对话的评价，而是从中学到的、可以在未来类似场景中使用的经验。

## 规律分四类

1. **prompt（教学策略）**：适用于所有学生的全局教学策略
   - 例："因式分解用图形化引导比代数推导效果好"
   - 例："学生说不会时先反问而非直接给答案"

2. **memory（个体记忆）**：只对特定学生有效的个人特征
   - 例："张三符号处理能力弱，出代数题时降低符号依赖"
   - 例："李四偏好简洁解释，避免长篇背景介绍"

3. **tool（工具配置）**：涉及工具的参数或能力边界
   - 参数级：可以通过调整现有参数解决的问题
     · 例："知识树检索 topK=5 时无关结果太多，应降为 3"
   - 能力级：工具**缺少某种能力**，不是调参数能解决的。这是最重要的发现。
     · 例："学生输入'二次函数图像'搜不到'二次函数的图象与性质'，知识树检索缺少模糊匹配或同义词处理能力"
     · 例："复杂多项式渲染超过 30 秒超时，图形生成工具需要复杂度预估和降级策略"
     · 例："学生用缩写'导数'搜不到'导数的概念与几何意义'，需要别名映射"
   > 能力级缺口的 effect.instruction 应描述**缺失的能力是什么**，不是调参建议。

4. **workflow（工作流模式）**：涉及 Agent 协作顺序或模式选择
   - 例："因式分解类 KP 先讲解再出题效果好"
   - 例："简单算术题跳过复杂出题工具，直接生成"

## 作用范围
每条规律必须明确适用范围：
- **global**：适用所有学生
- **student**：仅适用特定学生（需指定 student_id）
- **kp_chain**：仅适用某知识点的依赖链（需指定 kp_id）

## 输出格式
以 JSON 数组输出，每条规律包含以下字段：

```json
[
  {
    "title": "一句话摘要（≤30字）",
    "dimension": "prompt | memory | tool | workflow",
    "scope_type": "global | student | kp_chain",
    "scope_value": {},
    "trigger": {
      "event": "出题 | 讲解 | 答疑 | 搜索知识树",
      "condition": "触发条件描述（中文，≤20字）"
    },
    "effect": {
      "instruction": "规律的具体内容（中文，≤100字）",
      "params": {},
      "gap_type": "parameter | capability（仅tool维度需要）"
    },
    "confidence": "low",
    "rationale": "为什么这是一条可复用的规律（≤50字）"
  }
]
```

## 重要规则
1. 如果轨迹中没有值得复用的规律，返回空数组 []
2. 规律必须可操作——"小宇回答得不好"不是规律，"因式分解应优先使用图形化引导"才是
3. 不要把一次性信息当成规律——"学生问圆的面积"不是规律，那个学生以后不会再问一模一样的问题
4. 不要编造——如果没有观察到足够的证据，就不要提取规律
5. scope_value 根据 scope_type 填写：global 为空对象 {}，student 填 {"student_id": <从轨迹推断>}，kp_chain 填 {"kp_id": <从轨迹推断>}
"""


def format_trajectory_for_extraction(trajectory) -> str:
    """将 AITrajectory 格式化为 LLM 可读的文本。"""

    from ..models import AITrajectory

    lines = []

    # 轨迹元信息
    lines.append(f"## 轨迹 #{trajectory.id}")
    lines.append(f"评估结果: {trajectory.get_outcome_display()}")
    lines.append(f"使用的 prompt 变体: {trajectory.prompt_variant}")
    if trajectory.outcome_metrics:
        lines.append(f"评估指标: {json.dumps(trajectory.outcome_metrics, ensure_ascii=False)}")
    lines.append("")

    # 对话
    lines.append("## 对话内容")
    messages = trajectory.messages or []
    for msg in messages:
        role = msg.get('role', '?')
        content = msg.get('content', '')
        if not content:
            continue
        # 截断过长内容
        if len(content) > 500:
            content = content[:500] + '...'
        role_label = {'user': '学生', 'assistant': '小宇', 'system': '系统'}.get(role, role)
        lines.append(f"[{role_label}] {content}")
    lines.append("")

    # 工具调用
    tool_calls = trajectory.tool_calls or []
    if tool_calls:
        lines.append("## 工具调用序列")
        for i, tc in enumerate(tool_calls):
            name = tc.get('name', 'unknown') if isinstance(tc, dict) else str(tc)
            lines.append(f"  {i+1}. {name}")
    lines.append("")

    return "\n".join(lines)


def extract_experiences(trajectory) -> list[dict]:
    """
    从一条轨迹中提取可复用规律。

    Args:
        trajectory: AITrajectory 实例

    Returns:
        list[dict]: 提取的规律列表（已解析的 JSON），每个 dict 包含完整的 Experience 字段
    """
    from ai_engine.service import AIEngine

    trajectory_text = format_trajectory_for_extraction(trajectory)

    messages = [
        {'role': 'system', 'content': EXTRACTION_SYSTEM_PROMPT},
        {'role': 'user', 'content': f"分析以下对话轨迹，提取可复用的教学规律：\n\n{trajectory_text}"},
    ]

    try:
        res = AIEngine.call_ai(
            messages,
            temperature=0.2,
            max_tokens=1500,
            operation='experience.extract',
        )

        if not res or 'choices' not in res:
            logger.warning("experience_extract: no valid response for trajectory %d", trajectory.id)
            return []

        content = res['choices'][0]['message']['content']
        experiences = _parse_extraction_result(content)

        logger.info(
            "experience_extract: extracted %d experiences from trajectory %d",
            len(experiences), trajectory.id,
        )
        return experiences

    except Exception:
        logger.exception("experience_extract: failed for trajectory %d", trajectory.id)
        return []


def _parse_extraction_result(content: str) -> list[dict]:
    """解析 LLM 返回的 JSON。兼容 markdown code block 包裹。"""
    # 去除 markdown code block 标记
    cleaned = content.strip()
    if cleaned.startswith('```'):
        # 找到第一个换行后的内容
        first_nl = cleaned.find('\n')
        if first_nl != -1:
            cleaned = cleaned[first_nl + 1:]
        # 去掉末尾的 ```
        if cleaned.endswith('```'):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

    try:
        result = json.loads(cleaned)
        if isinstance(result, list):
            return result
        if isinstance(result, dict) and 'experiences' in result:
            return result['experiences']
        logger.warning("experience_extract: unexpected JSON structure: %s", type(result))
    except json.JSONDecodeError:
        logger.warning("experience_extract: failed to parse JSON from: %.200s", cleaned)

    return []


def save_experiences(trajectory, experiences: list[dict]) -> list:
    """
    将提取的规律保存为 Experience 记录。

    Args:
        trajectory: 来源轨迹
        experiences: extract_experiences 返回的规律列表

    Returns:
        list[Experience]: 创建的 Experience 实例列表
    """
    from ..models import Experience

    saved = []
    for exp_data in experiences:
        try:
            experience = Experience.objects.create(
                user_id=trajectory.user_id,
                trajectory=trajectory,
                dimension=exp_data.get('dimension', 'prompt'),
                scope_type=exp_data.get('scope_type', 'global'),
                scope_value=exp_data.get('scope_value', {}),
                title=exp_data.get('title', ''),
                trigger=exp_data.get('trigger', {}),
                effect=exp_data.get('effect', {}),
                confidence='low',
                weight=1.0,
                status='active',
            )
            saved.append(experience)
            logger.info(
                "experience_extract: saved '%s' (dim=%s, scope=%s, id=%d)",
                experience.title, experience.dimension, experience.scope_type, experience.id,
            )
        except Exception:
            logger.exception("experience_extract: failed to save experience '%s'", exp_data.get('title', '?'))

    return saved
