from __future__ import annotations

from typing import Dict, List

from core.models import PromptTemplate
from quizzes.models import PromptTemplateVersion


PIPELINE_NAMESPACE = "pipeline_prompts"
REQUIRED_PIPELINE_PROMPTS = [
    (
        "AI_QUESTION_GENERATOR",
        "GENERATOR",
        "你是一个学科命题专家。根据给定的知识点，生成一道符合学科标准的题目草稿，包含题干(question)和正确答案(correct_answer)。返回JSON。",
    ),
    (
        "AI_DISTRACTOR_EXPERT",
        "GENERATOR",
        "你是一个干扰项专家。根据给定的题干和正确答案，生成极具迷惑性的错误选项。返回包含完整 A,B,C,D 选项的JSON，以及对应的陷阱解析(explanation)。",
    ),
    (
        "AI_QUESTION_REVIEWER",
        "REVIEWER",
        "你是一个严苛的审核教研员。检查题目事实、LaTeX公式、大纲契合度。返回JSON: {'passed': true/false, 'reason': '...', 'suggested_fix': '...'}",
    ),
    (
        "AI_TAXONOMIST",
        "TAGGER",
        "你是一个题目标签员。根据传入的完整题目评估难度(entry/easy/normal/hard/extreme)。返回JSON: {'difficulty_level': '...'}。",
    ),
]


def _safe_version_num(raw_version: str | None) -> int:
    text = str(raw_version or "").strip().lower()
    if text.startswith("v"):
        text = text[1:]
    text = text.split(".", 1)[0]
    try:
        val = int(text)
        return max(1, val)
    except Exception:
        return 1


def _history_qs(template_name: str):
    return PromptTemplateVersion.objects.filter(
        namespace=PIPELINE_NAMESPACE,
        template_name=template_name,
    )


def _ensure_required_prompts():
    for name, agent_role, content in REQUIRED_PIPELINE_PROMPTS:
        PromptTemplate.objects.get_or_create(
            name=name,
            defaults={
                "version": "v1.0",
                "agent_role": agent_role,
                "content": content,
            },
        )


def _ensure_baseline_snapshot(prompt: PromptTemplate):
    if _history_qs(prompt.name).exists():
        return
    base_version = _safe_version_num(prompt.version)
    PromptTemplateVersion.objects.create(
        namespace=PIPELINE_NAMESPACE,
        template_name=prompt.name,
        version=base_version,
        content=prompt.content or "",
        change_note="baseline_snapshot",
        created_by=None,
    )


def list_pipeline_prompts() -> List[Dict]:
    _ensure_required_prompts()
    rows = PromptTemplate.objects.all().order_by("name")
    items: List[Dict] = []
    for row in rows:
        latest = _history_qs(row.name).order_by("-version").values_list("version", flat=True).first()
        items.append(
            {
                "namespace": PIPELINE_NAMESPACE,
                "template_name": row.name,
                "latest_version": int(latest or _safe_version_num(row.version)),
                "updated_at": row.created_at,
                "agent_role": row.agent_role,
                "model_provider": row.model_provider,
                "is_active": bool(row.is_active),
            }
        )
    return items


def read_pipeline_prompt(template_name: str) -> Dict:
    _ensure_required_prompts()
    prompt = PromptTemplate.objects.filter(name=template_name).first()
    if not prompt:
        raise FileNotFoundError("pipeline_prompt_not_found")
    _ensure_baseline_snapshot(prompt)

    history_rows = _history_qs(template_name).select_related("created_by").order_by("-version", "-id")[:30]
    history = [
        {
            "id": row.id,
            "version": row.version,
            "change_note": row.change_note,
            "created_by_username": getattr(row.created_by, "username", ""),
            "created_at": row.created_at,
        }
        for row in history_rows
    ]

    latest_version = history[0]["version"] if history else _safe_version_num(prompt.version)
    return {
        "namespace": PIPELINE_NAMESPACE,
        "template_name": prompt.name,
        "content": prompt.content or "",
        "latest_version": latest_version,
        "history": history,
        "agent_role": prompt.agent_role,
        "model_provider": prompt.model_provider,
        "temperature": prompt.temperature,
        "is_active": bool(prompt.is_active),
        "version_text": prompt.version,
    }


def _next_version(template_name: str, fallback_version: int) -> int:
    current = _history_qs(template_name).order_by("-version").values_list("version", flat=True).first()
    return int(current or fallback_version) + 1


def save_pipeline_prompt(
    template_name: str,
    content: str,
    change_note: str = "",
    operator=None,
    agent_role: str | None = None,
    model_provider: str | None = None,
    temperature: float | None = None,
    is_active: bool | None = None,
) -> Dict:
    _ensure_required_prompts()
    prompt = PromptTemplate.objects.filter(name=template_name).first()
    if not prompt:
        raise FileNotFoundError("pipeline_prompt_not_found")
    _ensure_baseline_snapshot(prompt)

    fallback_version = _safe_version_num(prompt.version)
    version = _next_version(template_name, fallback_version=fallback_version)

    if agent_role in {"GENERATOR", "REVIEWER", "TAGGER"}:
        prompt.agent_role = agent_role
    if model_provider is not None:
        prompt.model_provider = str(model_provider).strip() or prompt.model_provider
    if temperature is not None:
        prompt.temperature = max(0.0, min(2.0, float(temperature)))
    if is_active is not None:
        prompt.is_active = bool(is_active)

    prompt.content = str(content or "")
    prompt.version = f"v{version}"
    prompt.save()

    row = PromptTemplateVersion.objects.create(
        namespace=PIPELINE_NAMESPACE,
        template_name=template_name,
        version=version,
        content=prompt.content,
        change_note=str(change_note or "").strip(),
        created_by=operator if getattr(operator, "is_authenticated", False) else None,
    )
    return {
        "id": row.id,
        "namespace": row.namespace,
        "template_name": row.template_name,
        "version": row.version,
        "change_note": row.change_note,
        "created_at": row.created_at,
    }


def rollback_pipeline_prompt(template_name: str, version_id: int, operator=None) -> Dict:
    _ensure_required_prompts()
    prompt = PromptTemplate.objects.filter(name=template_name).first()
    if not prompt:
        raise FileNotFoundError("pipeline_prompt_not_found")
    _ensure_baseline_snapshot(prompt)

    target = _history_qs(template_name).filter(id=int(version_id)).first()
    if not target:
        raise FileNotFoundError("target_version_not_found")

    rolled = save_pipeline_prompt(
        template_name=template_name,
        content=target.content,
        change_note=f"rollback_from_v{target.version}",
        operator=operator,
        agent_role=prompt.agent_role,
        model_provider=prompt.model_provider,
        temperature=prompt.temperature,
        is_active=prompt.is_active,
    )
    rolled["rollback_source_version"] = target.version
    return rolled
