"""
Experience Applicator — 运行时规律匹配与注入。

在每次对话/工具调用前，检查当前上下文是否匹配已有经验的触发条件，
命中则注入到 prompt 上下文（低置信度）或写入持久层（高置信度）。

Phase 2 职责：
- 触发条件匹配
- Prompt 维度：临时注入 context 或生成 variant
- Memory 维度：写入 AgentMemory
- 记录触发时间（用于衰减计算）

Phase 3 扩展：
- Tool 维度参数调整
- Workflow 维度模式选择
"""

import logging
from typing import Optional
from django.utils import timezone

logger = logging.getLogger(__name__)


def get_applicable_experiences(context: dict, limit: int = 5) -> list:
    """
    根据当前上下文匹配适用的经验规律。

    Args:
        context: 当前对话上下文
            {
                'event': '出题' | '讲解' | '答疑' | '搜索知识树',
                'student_id': 123,  # optional
                'kp_id': 45,  # optional
                'institution_id': 7,  # optional
            }
        limit: 最大返回数量（跨维度各取 top N，总共不超过 limit）

    Returns:
        list[Experience]: 按权重降序排列的适用经验
    """
    from ..models import Experience

    event = context.get('event', '')
    student_id = context.get('student_id')
    kp_id = context.get('kp_id')

    # 候选：所有 active 经验
    candidates = Experience.objects.filter(
        status='active',
        confidence__in=['medium', 'high'],
    ).order_by('-weight')

    # 如果 medium/high 经验不足，加入 low 经验作为建议
    if candidates.count() < limit:
        low_candidates = Experience.objects.filter(
            status='active',
            confidence='low',
        ).order_by('-weight')
        candidates = list(candidates) + list(low_candidates)

    matched = []
    for exp in candidates:
        if _trigger_matches(exp, event, student_id, kp_id):
            matched.append(exp)
            if len(matched) >= limit:
                break

    # 按维度分组排序：prompt > workflow > memory > tool（影响范围从大到小）
    dim_order = {'prompt': 0, 'workflow': 1, 'memory': 2, 'tool': 3}
    matched.sort(key=lambda e: (dim_order.get(e.dimension, 99), -e.weight))

    return matched[:limit]


def _trigger_matches(experience, event: str, student_id: Optional[int], kp_id: Optional[int]) -> bool:
    """
    检查一条经验的触发条件是否匹配当前上下文。

    匹配逻辑：
    1. scope 过滤（global 始终通过，student 匹配 student_id，kp_chain 匹配 kp_id）
    2. event 过滤（trigger.event 匹配当前 event）
    """
    trigger = experience.trigger or {}
    scope_type = experience.scope_type
    scope_value = experience.scope_value or {}

    # 1. scope 过滤
    if scope_type == 'global':
        pass  # 始终匹配
    elif scope_type == 'student':
        if not student_id or scope_value.get('student_id') != student_id:
            return False
    elif scope_type == 'kp_chain':
        if not kp_id or scope_value.get('kp_id') != kp_id:
            # Phase 3: 也检查 downstream KP（is_downstream_of）
            return False
    elif scope_type == 'institution':
        # Phase 2 暂不实现机构 scope
        return False

    # 2. event 过滤（如果 trigger 有 event 要求）
    trigger_event = trigger.get('event', '')
    if trigger_event and event and trigger_event != event:
        return False

    return True


def inject_experiences_into_prompt(
    system_prompt: str,
    experiences: list,
    max_chars: int = 800,
) -> str:
    """
    将适用的经验注入 system_prompt。

    注入格式（追加在 system_prompt 末尾）：
    ```
    ## 教学经验指引
    - [Prompt策略] 因式分解优先用图形化引导
    - [个体建议] 张三符号处理弱，降低符号依赖题型比例
    ```

    Args:
        system_prompt: 原始 system_prompt
        experiences: 适用的经验列表
        max_chars: 注入内容的最大字符数

    Returns:
        注入后的 system_prompt
    """
    from ..models import Experience

    if not experiences:
        return system_prompt

    dim_labels = dict(Experience.DIMENSION_CHOICES)

    lines = ['', '## 教学经验指引']

    total = 0
    for exp in experiences:
        dim_label = dim_labels.get(exp.dimension, exp.dimension)
        instruction = (exp.effect or {}).get('instruction', exp.title)
        line = f"- [{dim_label}] {instruction}"
        if total + len(line) > max_chars:
            break
        lines.append(line)
        total += len(line)

    if len(lines) == 2:
        # 没有实际注入内容
        return system_prompt

    return system_prompt + '\n' + '\n'.join(lines)


def apply_memory_experiences(user, experiences: list) -> int:
    """
    将 memory 维度的经验写入 AgentMemory。

    跳过已存在的同 title 记忆（去重）。

    Returns:
        写入的记忆数量
    """
    from ..models import AgentMemory

    saved = 0
    for exp in experiences:
        if exp.dimension != 'memory':
            continue

        # 去重：检查是否已有同 title 记忆
        existing = AgentMemory.objects.filter(
            user=user,
            key=f'experience:{exp.id}',
            is_active=True,
        ).exists()
        if existing:
            continue

        instruction = (exp.effect or {}).get('instruction', exp.title)
        AgentMemory.objects.create(
            user=user,
            key=f'experience:{exp.id}',
            value=instruction,
            source='auto',
            memory_type='interaction',
        )
        saved += 1
        logger.info(
            "experience_applicator: wrote memory for exp %d to user %d",
            exp.id, user.id,
        )

    return saved


def record_trigger(experiences: list) -> int:
    """
    记录经验被触发的时间（用于权重衰减计算）。

    Returns:
        更新的记录数
    """
    from ..models import Experience

    if not experiences:
        return 0

    now = timezone.now()
    ids = [e.id for e in experiences if e.id]
    count = Experience.objects.filter(id__in=ids).update(last_triggered_at=now)
    return count


def apply_tool_experiences(experiences: list) -> dict:
    """
    应用 tool 维度的经验：调整工具参数。

    当前支持的参数：
    - memorix.alpha: 遗忘曲线 α 值
    - knowledge_tree.topK: 知识树检索上限
    - 未知参数: 记录建议日志，待配置接口完善后生效

    Returns:
        {'applied': int, 'pending': int, 'changes': [dict]}
    """
    changes = []
    applied = 0
    pending = 0

    for exp in experiences:
        if exp.dimension != 'tool':
            continue

        params = (exp.effect or {}).get('params', {})
        if not params:
            continue

        for param_name, param_value in params.items():
            change = _apply_tool_param(exp, param_name, param_value)
            changes.append(change)
            if change['status'] == 'applied':
                applied += 1
            else:
                pending += 1

    return {'applied': applied, 'pending': pending, 'changes': changes}


def _apply_tool_param(experience, param_name: str, param_value) -> dict:
    """应用单个工具参数。已知参数直接改，未知参数记录待实现。"""
    change = {
        'exp_id': experience.id,
        'param': param_name,
        'value': param_value,
        'status': 'pending',
    }

    # 已知参数：Memorix α
    if param_name == 'memorix.alpha':
        try:
            val = float(param_value)
            val = max(0.1, min(1.0, val))
            # 写入环境变量或配置（Memorix 从 settings 读取）
            from django.conf import settings
            current = getattr(settings, 'MEMORIX_ALPHA', 0.60)
            # 安全写 Redis 缓存（Memorix scheduler 读取）
            try:
                from django_redis import get_redis_connection
                redis_conn = get_redis_connection("default")
                redis_conn.set('memorix:alpha', val)
                redis_conn.expire('memorix:alpha', 86400 * 30)
            except Exception:
                pass
            change['status'] = 'applied'
            change['old_value'] = current
            logger.info(
                "experience_applicator: tool param %s %s→%s (exp %d)",
                param_name, current, val, experience.id,
            )
        except (ValueError, TypeError):
            logger.warning("experience_applicator: invalid alpha value %s", param_value)

    # 已知参数：知识树 topK
    elif param_name == 'knowledge_tree.topK':
        try:
            val = int(param_value)
            val = max(1, min(20, val))
            try:
                from django_redis import get_redis_connection
                redis_conn = get_redis_connection("default")
                redis_conn.set('knowledge_tree:topK', val)
                redis_conn.expire('knowledge_tree:topK', 86400 * 30)
            except Exception:
                pass
            change['status'] = 'applied'
            logger.info(
                "experience_applicator: tool param %s → %s (exp %d)",
                param_name, val, experience.id,
            )
        except (ValueError, TypeError):
            logger.warning("experience_applicator: invalid topK value %s", param_value)

    else:
        # 未知参数：记录待实现
        logger.info(
            "experience_applicator: tool param %s=%s not yet auto-applied (exp %s, needs config interface)",
            param_name, param_value, experience.id,
        )

    return change


def apply_workflow_experiences(experiences: list) -> list[dict]:
    """
    应用 workflow 维度的经验：写入工作流模式提示。

    当前阶段：将 workflow 经验转为 prompt 注入格式（追加到 system prompt）。
    长期阶段：驱动 mode_selector 的条件判断。

    Returns:
        list[dict]: 注入的 workflow 提示
    """
    hints = []
    for exp in experiences:
        if exp.dimension != 'workflow':
            continue

        instruction = (exp.effect or {}).get('instruction', exp.title)
        trigger_cond = (exp.trigger or {}).get('condition', '')
        hint = {
            'instruction': instruction,
            'condition': trigger_cond,
            'exp_id': exp.id,
        }
        hints.append(hint)
        logger.info("experience_applicator: workflow hint '%s' (exp %s)", instruction, exp.id)

    return hints
