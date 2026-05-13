from pathlib import Path
from typing import Dict, List, Optional

from django.conf import settings
from django.db.models import Max

from quizzes.models import PromptTemplateVersion


ALLOWED_EXTENSIONS = {".txt", ".json"}
SUPPORTED_NAMESPACES = {"quizzes", "ai_assistant"}


def _base_dir() -> Path:
    return Path(getattr(settings, "BASE_DIR"))


def _namespace_dir(namespace: str) -> Path:
    ns = str(namespace or "").strip()
    if ns == "quizzes":
        return _base_dir() / "quizzes" / "templates"
    if ns == "ai_assistant":
        return _base_dir() / "core" / "prompts"
    raise ValueError("unsupported_namespace")


def _validate_template_name(template_name: str) -> str:
    name = Path(str(template_name or "")).name
    if name != template_name:
        raise ValueError("invalid_template_name")
    if Path(name).suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ValueError("unsupported_template_extension")
    if not name:
        raise ValueError("empty_template_name")
    return name


def list_templates(namespace: str) -> List[Dict]:
    ns = str(namespace or "quizzes").strip()
    if ns not in SUPPORTED_NAMESPACES:
        raise ValueError("unsupported_namespace")
    root = _namespace_dir(ns)
    root.mkdir(parents=True, exist_ok=True)

    version_rows = (
        PromptTemplateVersion.objects.filter(namespace=ns)
        .values("template_name")
        .annotate(latest_version=Max("version"))
    )
    version_map = {row["template_name"]: int(row["latest_version"] or 0) for row in version_rows}

    items: List[Dict] = []
    for path in sorted(root.glob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in ALLOWED_EXTENSIONS:
            continue
        items.append(
            {
                "namespace": ns,
                "template_name": path.name,
                "latest_version": version_map.get(path.name, 0),
                "updated_at": path.stat().st_mtime,
            }
        )
    return items


def read_template(namespace: str, template_name: str) -> Dict:
    ns = str(namespace or "quizzes").strip()
    if ns not in SUPPORTED_NAMESPACES:
        raise ValueError("unsupported_namespace")
    name = _validate_template_name(template_name)
    path = _namespace_dir(ns) / name
    if not path.exists():
        raise FileNotFoundError("template_not_found")

    content = path.read_text(encoding="utf-8")
    history_qs = PromptTemplateVersion.objects.filter(namespace=ns, template_name=name).select_related("created_by")[:20]
    history = [
        {
            "id": row.id,
            "version": row.version,
            "change_note": row.change_note,
            "created_by_username": getattr(row.created_by, "username", ""),
            "created_at": row.created_at,
        }
        for row in history_qs
    ]
    latest = history[0]["version"] if history else 0

    return {
        "namespace": ns,
        "template_name": name,
        "content": content,
        "latest_version": latest,
        "history": history,
    }


def _next_version(namespace: str, template_name: str) -> int:
    current_max = (
        PromptTemplateVersion.objects.filter(namespace=namespace, template_name=template_name)
        .aggregate(max_version=Max("version"))
        .get("max_version")
    )
    return int(current_max or 0) + 1


def save_template(namespace: str, template_name: str, content: str, change_note: str = "", operator=None) -> Dict:
    ns = str(namespace or "quizzes").strip()
    if ns not in SUPPORTED_NAMESPACES:
        raise ValueError("unsupported_namespace")
    name = _validate_template_name(template_name)

    root = _namespace_dir(ns)
    root.mkdir(parents=True, exist_ok=True)
    path = root / name
    normalized = str(content or "")
    path.write_text(normalized, encoding="utf-8")

    version = _next_version(ns, name)
    row = PromptTemplateVersion.objects.create(
        namespace=ns,
        template_name=name,
        version=version,
        content=normalized,
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


def rollback_template(namespace: str, template_name: str, version_id: int, operator=None) -> Dict:
    ns = str(namespace or "quizzes").strip()
    if ns not in SUPPORTED_NAMESPACES:
        raise ValueError("unsupported_namespace")
    name = _validate_template_name(template_name)
    target = (
        PromptTemplateVersion.objects.filter(
            id=int(version_id),
            namespace=ns,
            template_name=name,
        )
        .first()
    )
    if not target:
        raise FileNotFoundError("target_version_not_found")

    change_note = f"rollback_from_v{target.version}"
    save_result = save_template(
        namespace=ns,
        template_name=name,
        content=target.content,
        change_note=change_note,
        operator=operator,
    )
    save_result["rollback_source_version"] = target.version
    return save_result

