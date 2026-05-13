import re
from typing import Any, Dict, List, Optional, Tuple


def _build_question_type_aliases() -> Dict[str, Tuple[str, str]]:
    alias_groups = [
        (('objective', ''), ['objective', '单选', '单选题', '选择题', '单项选择题']),
        (('subjective', ''), ['subjective', '主观题']),
        (('subjective', 'noun'), ['noun', '名词解释']),
        (('subjective', 'short'), ['short', '简答', '简答题', '辨析', '辨析题', '比较题', '对比题', '简析']),
        (('subjective', 'essay'), ['essay', '论述', '论述题']),
        (('subjective', 'calculate'), ['calculate', '计算', '计算题']),
    ]

    alias_map: Dict[str, Tuple[str, str]] = {}
    for target, aliases in alias_groups:
        for alias in aliases:
            key = str(alias).strip()
            if not key:
                continue

            if key in alias_map and alias_map[key] != target:
                raise ValueError(f'QUESTION_TYPE_ALIASES 冲突: {key} -> {alias_map[key]} / {target}')

            alias_map[key] = target

    return alias_map


QUESTION_TYPE_ALIASES: Dict[str, Tuple[str, str]] = _build_question_type_aliases()

DIFFICULTY_ORDER: Dict[str, int] = {
    'entry': 0,
    'easy': 1,
    'normal': 2,
    'hard': 3,
    'extreme': 4,
}

TYPE_RATIO_LABELS: Dict[str, str] = {
    'objective': '单项选择题',
    'subjective:noun': '名词解释',
    'subjective:short': '简答题',
    'subjective:essay': '论述题',
    'subjective:calculate': '计算题',
}


def normalize_question_type(raw_q_type: Any, subjective_type: Any = None) -> Tuple[str, str]:
    """Normalize question type and subjective type into canonical form."""
    q_type = str(raw_q_type or '').strip()
    raw_sub_type = str(subjective_type or '').strip()

    if q_type in QUESTION_TYPE_ALIASES:
        mapped_q_type, mapped_sub_type = QUESTION_TYPE_ALIASES[q_type]
        if mapped_sub_type:
            return mapped_q_type, mapped_sub_type
        if raw_sub_type in QUESTION_TYPE_ALIASES:
            _, mapped_sub = QUESTION_TYPE_ALIASES[raw_sub_type]
            return mapped_q_type, mapped_sub
        return mapped_q_type, raw_sub_type.lower() if raw_sub_type.lower() in {'noun', 'short', 'essay', 'calculate'} else ''

    q_lower = q_type.lower()
    if q_lower in QUESTION_TYPE_ALIASES:
        mapped_q_type, mapped_sub_type = QUESTION_TYPE_ALIASES[q_lower]
        if mapped_sub_type:
            return mapped_q_type, mapped_sub_type
        if raw_sub_type.lower() in {'noun', 'short', 'essay', 'calculate'}:
            return mapped_q_type, raw_sub_type.lower()
        return mapped_q_type, ''

    if q_lower in {'noun', 'short', 'essay', 'calculate'}:
        return 'subjective', q_lower

    if raw_sub_type.lower() in {'noun', 'short', 'essay', 'calculate'}:
        return 'subjective', raw_sub_type.lower()

    return 'subjective', 'short'


def normalize_difficulty_level(difficulty_level: Any, difficulty: Any = None) -> str:
    """Normalize difficulty level string or numeric difficulty value."""
    if difficulty_level:
        level = str(difficulty_level).strip().lower()
        if level in {'entry', 'easy', 'normal', 'hard', 'extreme'}:
            return level

    try:
        value = int(float(difficulty))
    except Exception:
        return 'normal'

    if value <= 900:
        return 'entry'
    if value <= 1100:
        return 'easy'
    if value <= 1300:
        return 'normal'
    if value <= 1500:
        return 'hard'
    return 'extreme'


def normalize_target_difficulty(target_difficulty: Any) -> str:
    """Normalize target difficulty to a canonical level string."""
    if target_difficulty is None:
        return 'normal'
    level = str(target_difficulty).strip().lower()
    if level in {'entry', 'easy', 'normal', 'hard', 'extreme'}:
        return level
    if level in {'mixed', 'auto', 'any', 'random'}:
        return 'mixed'
    return 'normal'


def canonical_question_type_key(q_type: Any, subjective_type: Any = None) -> str:
    """Return a canonical type key like 'objective' or 'subjective:short'."""
    normalized_q_type, normalized_subjective_type = normalize_question_type(q_type, subjective_type)
    if normalized_q_type == 'objective':
        return 'objective'
    return f"subjective:{normalized_subjective_type or 'short'}"


def normalize_target_types(target_types: Optional[List[str]]) -> List[str]:
    """Normalize a list of target type strings into canonical type keys."""
    normalized: List[str] = []
    for item in target_types or []:
        key = canonical_question_type_key(item, '')
        if key not in normalized:
            normalized.append(key)
    return normalized


def normalize_target_type_ratio(
    target_type_ratio: Any,
    target_types: Optional[List[str]],
) -> Dict[str, float]:
    """Normalize target type ratio dict, falling back to target_types or defaults."""
    ratio_map: Dict[str, float] = {}
    if isinstance(target_type_ratio, dict):
        for raw_key, raw_value in target_type_ratio.items():
            key = canonical_question_type_key(raw_key, '')
            try:
                weight = float(raw_value)
            except Exception:
                continue
            if weight <= 0:
                continue
            ratio_map[key] = ratio_map.get(key, 0.0) + weight

    if not ratio_map:
        for key in normalize_target_types(target_types):
            ratio_map[key] = 1.0

    if not ratio_map:
        ratio_map = {
            'objective': 1.0,
            'subjective:short': 1.0,
            'subjective:essay': 1.0,
        }

    total = sum(ratio_map.values())
    if total <= 0:
        return {'objective': 1.0}
    return {k: v / total for k, v in ratio_map.items()}


def render_target_type_ratio(ratio_map: Dict[str, float], count_per_kp: int) -> str:
    """Render a human-readable description of the target type ratio distribution."""
    if not ratio_map:
        return '未指定，按教学常规自动配比。'

    lines = []
    for key, weight in sorted(ratio_map.items(), key=lambda x: x[1], reverse=True):
        label = TYPE_RATIO_LABELS.get(key, key)
        per_kp = weight * max(1, int(count_per_kp or 1))
        lines.append(f"- {label}: {weight * 100:.0f}% (每考点约 {per_kp:.1f} 题)")
    return '\n'.join(lines)


def normalize_options(options: Any) -> Dict[str, str]:
    """Normalize options from dict or list into a canonical A/B/C/D dict."""
    letters = ['A', 'B', 'C', 'D']
    normalized = {key: '' for key in letters}

    if isinstance(options, dict):
        for key, value in options.items():
            letter = str(key).strip().upper()[:1]
            if letter in normalized:
                normalized[letter] = str(value or '').strip()
        return normalized

    if isinstance(options, list):
        for idx, value in enumerate(options[:4]):
            text = str(value or '').strip()
            match = re.match(r'^([A-Da-d])[\.、\s:：-]*(.*)$', text)
            if match:
                normalized[match.group(1).upper()] = match.group(2).strip()
            elif idx < 4:
                normalized[letters[idx]] = text
        return normalized

    return normalized


def normalize_objective_answer(answer: Any, options: Optional[Dict[str, str]] = None) -> str:
    """Normalize an objective question answer to its canonical letter form."""
    text = str(answer or '').strip()
    if not text:
        return ''

    m = re.match(r'^([A-Da-d])(?:[\.、\s:：-].*)?$', text)
    if m:
        return m.group(1).upper()

    if options:
        for letter, content in options.items():
            if text == content:
                return letter

    upper = text.upper()
    return upper if upper in {'A', 'B', 'C', 'D'} else text


def normalize_noun_question_text(question_text: str) -> str:
    """Strip common prefixes and trailing punctuation from noun-explanation questions."""
    text = str(question_text or '').strip()
    if not text:
        return ''

    prefixes = [
        r'^名词解释[\s:：-]*',
        r'^请解释(?:下列)?(?:名词|概念)?[\s:：-]*',
        r'^请对(?:下列)?(?:名词|概念)进行解释[\s:：-]*',
        r'^什么是[\s:：-]*',
    ]
    for pattern in prefixes:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE).strip()

    text = re.sub(r'[。；;？！?]+$', '', text).strip()
    return text
