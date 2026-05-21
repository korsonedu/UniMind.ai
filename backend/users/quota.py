from django.utils import timezone
from django.db.models import F
from django.db import transaction

# ── 配额矩阵 ──

PLAN_QUOTA_LIMITS: dict[str, dict[str, int | None]] = {
    'free': {
        'course': 5, 'question': 200, 'knowledge_point': 300,
        'article': 5, 'ai_question': 30, 'ai_call_total': 200,
    },
    'solo': {
        'course': 30, 'question': 2000, 'knowledge_point': 1000,
        'article': 20, 'ai_question': None, 'ai_call_total': 1500,
    },
    'plus': {
        'course': 100, 'question': 10000, 'knowledge_point': 5000,
        'article': 100, 'ai_question': None, 'ai_call_total': 5000,
        'pdf_export': 100, 'interview': 50,
    },
    'pro': {
        'course': None, 'question': None, 'knowledge_point': None,
        'article': None, 'ai_question': None, 'ai_call_total': None,
        'pdf_export': None, 'interview': None,
    },
}

# 资源类型: total(总量型, COUNT) / monthly(月计型, UsageLog)
RESOURCE_TYPE: dict[str, str] = {
    'course': 'total', 'question': 'total',
    'knowledge_point': 'total', 'article': 'total',
    'ai_question': 'monthly', 'ai_call_total': 'monthly',
    'pdf_export': 'monthly', 'interview': 'monthly',
}

# 月计型资源 → UsageLog 字段名
MONTHLY_FIELD_MAP: dict[str, str] = {
    'ai_question': 'ai_question_count',
    'ai_call_total': 'ai_call_total_count',
    'pdf_export': 'pdf_export_count',
    'interview': 'interview_count',
}

# 总量型资源 → (model_cls_path, filter_field)
TOTAL_COUNT_SOURCES: dict[str, tuple[str, str]] = {
    'course': ('courses.models.Course', 'institution'),
    'question': ('quizzes.models.Question', 'institution'),
    'knowledge_point': ('quizzes.models.KnowledgePoint', 'institution'),
    'article': ('articles.models.Article', 'institution'),
}

# 资源标签（用于提示文案）
RESOURCE_LABELS: dict[str, str] = {
    'course': '课程数',
    'question': '题目总数',
    'knowledge_point': '知识图谱节点',
    'article': '文章数',
    'ai_question': 'AI 出题次数',
    'ai_call_total': 'AI 调用总次数',
    'pdf_export': '模拟考试 PDF',
    'interview': '面试场次',
}

# 升级路径
PLAN_ORDER = ['free', 'solo', 'plus', 'pro']
PLAN_LABELS = {'free': 'Free', 'solo': 'Solo', 'plus': 'Plus', 'pro': 'Pro'}


# ── helpers ──

def get_current_period_start():
    now = timezone.now()
    return now.replace(day=1).date()


def _get_limit(institution, resource_type) -> int | None:
    """返回该机构在该资源上的配额上限。None=无限制，0=已耗尽。"""
    if institution is None:
        return 0
    limits = PLAN_QUOTA_LIMITS.get(institution.plan, {})
    return limits.get(resource_type)


def _next_plan_and_limit(institution, resource_type) -> tuple[str | None, int | None]:
    """找到下一个有更高配额的 plan 和对应 limit。"""
    if institution is None:
        return None, None
    current = institution.plan
    try:
        idx = PLAN_ORDER.index(current)
    except ValueError:
        return None, None
    for next_plan in PLAN_ORDER[idx + 1:]:
        next_limits = PLAN_QUOTA_LIMITS.get(next_plan, {})
        if resource_type in next_limits:
            return next_plan, next_limits[resource_type]
    return None, None


def _count_total(institution, resource_type) -> int:
    """实时 COUNT 总量型资源。"""
    model_path, filter_field = TOTAL_COUNT_SOURCES[resource_type]
    module_path, model_name = model_path.rsplit('.', 1)
    import importlib
    mod = importlib.import_module(module_path)
    model_cls = getattr(mod, model_name)
    return model_cls.objects.filter(**{filter_field: institution}).count()


# ── 核心 API ──

def check_quota(institution, resource_type: str) -> bool:
    """
    检查机构是否还有指定资源的配额。
    无 institution 或资源未配置 → False。
    limit=None → 无限制，永远 True。
    """
    if institution is None:
        return False
    limit = _get_limit(institution, resource_type)
    if limit is None:
        return True
    if RESOURCE_TYPE.get(resource_type) == 'total':
        used = _count_total(institution, resource_type)
        return used < limit
    else:
        from users.models_commercial import InstitutionUsageLog
        field = MONTHLY_FIELD_MAP.get(resource_type, 'ai_question_count')
        usage, _ = InstitutionUsageLog.objects.get_or_create(
            institution=institution,
            period_start=get_current_period_start(),
        )
        return getattr(usage, field) < limit


def increment_quota(institution, resource_type: str):
    """
    原子递增月计型资源计数。总量型资源无需递增（直接 COUNT）。
    超限时不递增。
    """
    if institution is None:
        return
    if RESOURCE_TYPE.get(resource_type) != 'monthly':
        return
    limit = _get_limit(institution, resource_type)
    if limit is None:
        return
    field = MONTHLY_FIELD_MAP.get(resource_type, 'ai_question_count')
    from users.models_commercial import InstitutionUsageLog
    with transaction.atomic():
        usage = InstitutionUsageLog.objects.select_for_update().get_or_create(
            institution=institution,
            period_start=get_current_period_start(),
        )[0]
        current = getattr(usage, field)
        if current < limit:
            setattr(usage, field, F(field) + 1)
            usage.save(update_fields=[field])
            # 兼容旧代码：ai_question 同步递增 ai_generation_count
            if resource_type == 'ai_question' and field != 'ai_generation_count':
                usage.ai_generation_count = F('ai_generation_count') + 1
                usage.save(update_fields=['ai_generation_count'])


def get_all_quota_info(institution) -> dict:
    """
    返回所有资源的配额信息。
    {resource: {used, limit, pct, status}}
    """
    if institution is None:
        return {}

    plan = institution.plan
    plan_limits = PLAN_QUOTA_LIMITS.get(plan, {})

    # 月计型：一次查出当月 UsageLog
    from users.models_commercial import InstitutionUsageLog
    monthly_usage, _ = InstitutionUsageLog.objects.get_or_create(
        institution=institution,
        period_start=get_current_period_start(),
    )

    result = {}
    for resource_type, limit in plan_limits.items():
        rtype = RESOURCE_TYPE.get(resource_type, 'total')
        if rtype == 'total':
            used = _count_total(institution, resource_type)
        else:
            field = MONTHLY_FIELD_MAP.get(resource_type, 'ai_question_count')
            used = getattr(monthly_usage, field)

        actual_limit = limit  # None = 无限制
        if actual_limit is not None and actual_limit > 0:
            pct = min(round(used / actual_limit * 100), 100)
        else:
            pct = 0

        if actual_limit is None:
            status = 'normal'
        elif used >= actual_limit:
            status = 'exhausted'
        elif pct >= 80:
            status = 'warning'
        else:
            status = 'normal'

        result[resource_type] = {
            'used': used,
            'limit': actual_limit,
            'pct': pct,
            'status': status,
        }

    return result


def get_quota_message(institution, resource_type: str) -> str:
    """生成配额耗尽时的升级提示文案。"""
    limit = _get_limit(institution, resource_type)
    label = RESOURCE_LABELS.get(resource_type, resource_type)
    next_plan, next_limit = _next_plan_and_limit(institution, resource_type)

    if next_plan and next_limit is not None:
        next_label = PLAN_LABELS.get(next_plan, next_plan)
        return f'{label}已达上限（{limit}）。升级到 {next_label} 解锁 {next_limit}。'
    elif next_plan and next_limit is None:
        next_label = PLAN_LABELS.get(next_plan, next_plan)
        return f'{label}已达上限（{limit}）。升级到 {next_label} 解锁无限制。'
    else:
        return f'{label}已达上限，请联系管理员升级方案。'


# ── 向后兼容 wrapper ──

FREE_AI_QUOTA_LIMIT = 30  # 已从 20 调整为 30


def check_ai_quota(institution) -> bool:
    return check_quota(institution, 'ai_question')


def increment_ai_quota(institution):
    increment_quota(institution, 'ai_question')
    increment_quota(institution, 'ai_call_total')


def get_ai_quota_info(institution):
    """兼容旧接口：返回 {used, limit} 指向 ai_question。"""
    if institution is None:
        return {'used': 0, 'limit': 0}
    info = get_all_quota_info(institution)
    ai_q = info.get('ai_question', {'used': 0, 'limit': 0})
    return {'used': ai_q['used'], 'limit': ai_q['limit']}
