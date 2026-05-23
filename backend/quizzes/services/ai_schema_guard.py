from typing import Any, List, Tuple


OBJECTIVE_HINTS = {'objective', '单选', '单选题', '选择题', '单项选择题'}
SUBJECTIVE_HINTS = {'subjective', '主观题', 'noun', 'short', 'essay', 'calculate', '名词解释', '简答题', '论述题', '计算题'}


def validate_question_list_payload(payload: Any, allow_empty: bool = False) -> Tuple[bool, List[str]]:
    """校验用户提交的题目列表 payload（前端输入校验，非 AI 输出校验）。"""
    errors: List[str] = []
    if not isinstance(payload, list):
        return False, ['payload_not_list']

    if not payload and not allow_empty:
        return False, ['payload_empty']

    for idx, item in enumerate(payload):
        prefix = f'item_{idx}'
        if not isinstance(item, dict):
            errors.append(f'{prefix}_not_object')
            continue

        question_text = str(item.get('question') or item.get('text') or '').strip()
        if not question_text:
            errors.append(f'{prefix}_missing_question')
            continue

        q_type_raw = str(
            item.get('q_type')
            or item.get('question_type')
            or item.get('type')
            or ''
        ).strip().lower()
        subjective_type_raw = str(item.get('subjective_type') or '').strip().lower()
        answer_text = str(item.get('answer') or item.get('correct_answer') or '').strip()

        is_objective = q_type_raw in OBJECTIVE_HINTS or (q_type_raw == '' and isinstance(item.get('options'), (dict, list)))
        is_subjective = q_type_raw in SUBJECTIVE_HINTS or subjective_type_raw in {'noun', 'short', 'essay', 'calculate'}

        if is_objective:
            options = item.get('options')
            if not isinstance(options, (dict, list)):
                errors.append(f'{prefix}_objective_missing_options')
            if not answer_text:
                errors.append(f'{prefix}_objective_missing_answer')

        if is_subjective and not answer_text:
            errors.append(f'{prefix}_subjective_missing_answer')

    return len(errors) == 0, errors
