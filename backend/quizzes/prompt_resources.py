import json
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from django.conf import settings


_DEFAULT_FINANCE_MODULE_RULES = {
    'MB': '货币银行学（基础理论组）：突出核心概念与传导机制，题干需给出具体经济情境。主观题答案需形成“定义-假设-机制-结论”的链条，并覆盖短期/长期或正反两面。',
    'IF': '国际金融学（基础理论组）：在开放经济框架下强调汇率、国际收支与资本流动机制，明确变量方向与条件，答案需给出模型逻辑与情境解释。',
    'MA': '宏观基础（基础理论组）：强调模型推导与经济直觉一致，避免只给结论；适度设置情境以检验机制链条。',
    'CF': '公司理财（计算与实务组）：优先考核估值与资本结构，题干必须给出完整数据，计算题需列公式、逐步代入、写明单位与经济含义。',
    'IV': '投资学（计算与实务组）：突出风险-收益、组合优化与资产定价框架，答案需说明前提假设；计算题过程必须完整可复核。',
    'DR': '衍生品（计算与实务组）：以无套利与复制组合为核心，强调定价步骤、关键公式与中间过程。',
    'CE': '中国经济专题（论述与现实组）：必须结合中国政策背景与工具，答案结构为“理论框架提取 + 中国机制对应 + 政策评价/建议”。',
    'AF': '高阶专题（拔高组）：要求跨模型比较、指出适用边界与现实偏离，体现批判性与学术视角。',
    'AD': '前沿专题（拔高组）：覆盖行为金融/金融科技/市场异象，要求机制解释、风险识别与反例讨论。',
}

_DEFAULT_GRADING_POINTS_MAP = {
    'noun': '1. 概念定义准确(2分)；2. 关键机制或假设(2分)；3. 实际意义或应用(1分)。',
    'essay': '1. 先解释核心原理并写出关键公式/恒等式(6分)；2. 至少3个分论点，每点含机制链条与定量关系(8分)；3. 结论与术语归纳准确(6分)。',
    'calculate': '1. 公式与方法正确(4分)；2. 过程完整且代入准确(4分)；3. 结果与解释(2分)。',
    'short': '1. 要点覆盖完整(4分)；2. 相近概念边界辨析准确(3分)；3. 逻辑清晰且结论准确(3分)。',
}

_SHARED_ANSWER_REQUIREMENTS_FALLBACK = (
    "- 客观题：`answer` 只能是 A/B/C/D 单个字母。\n"
    “- 名词解释（noun）：标准答案控制在 120-220 字，必须包含定义、关键机制/假设、实际意义。\n”
    “- 简答题（short）：标准答案至少 3 个要点，建议 220-400 字，每点有展开；可采用相似概念对比/辨析结构（如”A与B的联系与区别”）。\n”
    “- 论述题（essay）：标准答案必须采用以下结构（建议 500-900 字）：\n”
    “  1) 先解释本题涉及的核心原理（概念 + 关键公式/恒等式 + 变量含义）；\n”
    “  2) 给出至少 3 个”分论点”；\n”
    “  3) 每个分论点都要展开”理论机制 -> 公式/数量关系 -> 结论”，并尽量给出定量表达或变量间关系的趋势判断。\n”
    “  禁止空泛口号式表述，避免写成政策评论/研究报告风格。\n”
    “- 计算题（calculate）：标准答案必须有”已知条件-公式-代入-中间过程-最终结果（含单位/含义）”。”
)

_SHARED_QUESTION_SHAPE_FALLBACK = (
    "- `subjective_type=noun`：`question` 必须是“单个名词/概念词组”，例如“流动性陷阱”，不要问句、不要背景材料、不要“请解释/什么是”前缀。\n"
    "- `subjective_type=short`：`question` 必须带简要业务或政策背景，要求考生分点作答；允许采用“比较/辨析相近概念”的问法。\n"
    "- `subjective_type=essay`：`question` 必须带完整现实背景与分析任务，要求系统论证与评价建议。"
)

_SHARED_OUTPUT_SCHEMA_FALLBACK = (
    "[\n"
    "  {{\n"
    "    \"q_type\": \"objective | subjective\",\n"
    "    \"subjective_type\": \"\" ,\n"
    "    \"question\": \"题干\",\n"
    "    \"options\": {{\"A\": \"\", \"B\": \"\", \"C\": \"\", \"D\": \"\"}},\n"
    "    \"answer\": \"客观题填A/B/C/D；主观题填参考答案\",\n"
    "    \"grading_points\": \"客观题写'无'；主观题按分值列点\",\n"
    "    \"difficulty_level\": \"entry | easy | normal | hard | extreme\",\n"
    "    \"related_knowledge_id\": \"知识点code\"\n"
    "  }}\n"
    "]"
)

_TEXT_CACHE: Dict[str, Optional[str]] = {}
_JSON_CACHE: Dict[str, Optional[Dict[str, str]]] = {}


def _templates_dir() -> Path:
    base_dir = Path(getattr(settings, 'BASE_DIR', Path(__file__).resolve().parent.parent))
    return base_dir / 'quizzes' / 'templates'


def _strip_template_meta_comment(raw: str) -> str:
    text = (raw or '').lstrip('\ufeff')
    if not text.startswith('/* PROMPT_META'):
        return raw

    end = text.find('*/')
    if end < 0:
        return raw

    return text[end + 2:].lstrip('\r\n')


def _read_text_template(template_name: str) -> Optional[str]:
    clean_name = Path(template_name).name
    if clean_name in _TEXT_CACHE:
        return _TEXT_CACHE[clean_name]

    path = _templates_dir() / clean_name
    if not path.exists():
        _TEXT_CACHE[clean_name] = None
        return None

    try:
        raw = path.read_text(encoding='utf-8')
        text = _strip_template_meta_comment(raw) if path.suffix.lower() == '.txt' else raw
        _TEXT_CACHE[clean_name] = text
        return text
    except Exception:
        _TEXT_CACHE[clean_name] = None
        return None


def _load_json_dict(template_name: str) -> Dict[str, str]:
    clean_name = Path(template_name).name
    if clean_name in _JSON_CACHE:
        return _JSON_CACHE[clean_name] or {}

    raw = _read_text_template(clean_name)
    if not raw:
        _JSON_CACHE[clean_name] = {}
        return {}

    try:
        data = json.loads(raw)
    except Exception:
        _JSON_CACHE[clean_name] = {}
        return {}

    if not isinstance(data, dict):
        _JSON_CACHE[clean_name] = {}
        return {}

    normalized = {str(k): str(v) for k, v in data.items() if isinstance(v, str)}
    _JSON_CACHE[clean_name] = normalized
    return normalized


def _read_shared_template(template_name: str, fallback: str) -> str:
    text = _read_text_template(template_name)
    return (text or '').strip() or fallback


def get_default_grading_points(subjective_type: str) -> str:
    key = str(subjective_type or 'short').strip().lower()
    points_map = {
        **_DEFAULT_GRADING_POINTS_MAP,
        **_load_json_dict('default_grading_points.json'),
    }
    return points_map.get(key, points_map['short'])


def build_module_rules_text(kps_data: Sequence[Dict[str, Any]]) -> str:
    prefixes = set()
    for kp in kps_data:
        code = str(kp.get('code') or '').strip().upper()
        if '-' in code:
            prefixes.add(code.split('-', 1)[0])

    rules_map = {
        **_DEFAULT_FINANCE_MODULE_RULES,
        **_load_json_dict('finance_module_rules.json'),
    }

    lines = ['- 总体要求：不同知识点模块必须采用与其学科特点匹配的出题风格，避免模板化与同质化。']
    for prefix, rule in rules_map.items():
        if prefix in prefixes:
            lines.append(f'- [{prefix}] {rule}')

    if len(lines) == 1:
        lines.append('- 通用要求：题目必须可判分、可复核、可关联知识点。')

    return '\n'.join(lines)


def get_shared_answer_requirements() -> str:
    return _read_shared_template('shared_answer_requirements.txt', _SHARED_ANSWER_REQUIREMENTS_FALLBACK)


def get_shared_question_shape_constraints() -> str:
    return _read_shared_template('shared_question_shape_constraints.txt', _SHARED_QUESTION_SHAPE_FALLBACK)


def get_shared_output_schema() -> str:
    return _read_shared_template('shared_output_schema.txt', _SHARED_OUTPUT_SCHEMA_FALLBACK)
