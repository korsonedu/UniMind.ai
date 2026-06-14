"""
GEPA Variant Manager — Prompt 变体的选择、应用、生命周期管理。

Variant 存储在文件系统中（非 DB），每个 bot_type 一个 JSON 文件：
    backend/prompts/ai_assistant/variants/{bot_type}.json

Variant 只做 prompt 后缀追加，不改原文件。
所有 variant 初始 traffic_split=0.0，需手动调高后才生效。
"""
import json
import logging
import random
from pathlib import Path
from typing import Optional, Tuple

from django.conf import settings

logger = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────────────

def _variants_dir() -> Path:
    base = Path(getattr(settings, 'BASE_DIR', Path(__file__).resolve().parent.parent))
    path = base / 'prompts' / 'ai_assistant' / 'variants'
    path.mkdir(parents=True, exist_ok=True)
    return path


def _variants_path(bot_type: str) -> Path:
    return _variants_dir() / f'{bot_type}.json'


def _load_variants(bot_type: str) -> dict:
    """加载 bot_type 的 variant 配置文件，不存在则返回空结构。"""
    path = _variants_path(bot_type)
    if not path.exists():
        return {'variants': []}
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError):
        logger.warning("Failed to parse variants file: %s", path)
        return {'variants': []}


def _save_variants(bot_type: str, data: dict) -> None:
    """持久化 variant 配置。"""
    path = _variants_path(bot_type)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


# ── Public API ──────────────────────────────────────────────────────────

def get_variant_for_request(bot) -> Optional[Tuple[str, dict]]:
    """
    按 traffic_split 概率选择一个 active variant。

    Returns:
        (variant_name, overrides) 或 None（表示使用 baseline）
    """
    if not bot:
        return None

    data = _load_variants(bot.bot_type)
    active = [v for v in data.get('variants', []) if v.get('status') == 'active' and v.get('traffic_split', 0) > 0]

    if not active:
        return None

    # 按 traffic_split 加权随机选择
    roll = random.random()
    cumulative = 0.0
    for v in active:
        cumulative += v.get('traffic_split', 0)
        if roll < cumulative:
            logger.debug("Selected variant '%s' for bot %s (roll=%.3f)", v['name'], bot.bot_type, roll)
            return v['name'], v.get('overrides', {})

    # fallthrough → baseline
    return None


def apply_variant_prompt(system_prompt: str, variant_overrides: dict) -> str:
    """
    将 variant overrides 应用到 system_prompt。
    当前仅支持 suffix 追加，未来可扩展更多 override 类型。
    """
    suffix = variant_overrides.get('suffix', '')
    if suffix:
        return system_prompt + '\n\n' + suffix
    return system_prompt


def list_variants(bot_type: str) -> list[dict]:
    """列出 bot_type 的所有 variant（含非 active）。"""
    data = _load_variants(bot_type)
    return data.get('variants', [])


def create_variant(
    bot_type: str,
    name: str,
    overrides: dict,
    traffic_split: float = 0.0,
    source_suggestion_id: int | None = None,
) -> dict:
    """
    创建新 variant。

    Returns:
        创建的 variant dict
    """
    from django.utils import timezone

    data = _load_variants(bot_type)

    # 去重：同名则更新
    existing = next((v for v in data['variants'] if v['name'] == name), None)
    if existing:
        existing['overrides'] = overrides
        existing['traffic_split'] = traffic_split
        existing['updated_at'] = timezone.now().isoformat()
        _save_variants(bot_type, data)
        logger.info("Updated variant '%s' for %s (traffic=%.2f)", name, bot_type, traffic_split)
        return existing

    variant = {
        'name': name,
        'status': 'active',
        'traffic_split': traffic_split,
        'overrides': overrides,
        'created_at': timezone.now().isoformat(),
        'source_suggestion_id': source_suggestion_id,
    }
    data['variants'].append(variant)
    _save_variants(bot_type, data)
    logger.info("Created variant '%s' for %s (traffic=%.2f)", name, bot_type, traffic_split)
    return variant


def retire_variant(bot_type: str, name: str) -> bool:
    """
    退役 variant：标记 inactive，traffic 归零。

    Returns:
        True if found and updated
    """
    from django.utils import timezone

    data = _load_variants(bot_type)
    target = next((v for v in data['variants'] if v['name'] == name), None)
    if not target:
        return False

    target['status'] = 'retired'
    target['traffic_split'] = 0.0
    target['retired_at'] = timezone.now().isoformat()
    _save_variants(bot_type, data)
    logger.info("Retired variant '%s' for %s", name, bot_type)
    return True


def update_traffic(bot_type: str, name: str, traffic_split: float) -> bool:
    """调整 variant 流量比例。"""
    data = _load_variants(bot_type)
    target = next((v for v in data['variants'] if v['name'] == name), None)
    if not target:
        return False
    target['traffic_split'] = max(0.0, min(1.0, traffic_split))
    _save_variants(bot_type, data)
    logger.info("Updated traffic for '%s' to %.2f", name, traffic_split)
    return True
