"""Single prompt loader and fail-fast structured DeepSeek boundary."""
import json
from pathlib import Path

import jsonschema
from ai_engine.ai_service import AIService
from .exceptions import AIResponseError
from .schemas import SCHEMAS

PROMPT_DIR = Path(__file__).resolve().parent.parent / 'prompts' / 'knowledge_builder'

# Fields moved into an immutable stage-level system_prompt so repeated calls share KV prefix cache.
SYSTEM_PREFIX_KEYS = {
    'atom_generate': ('subject', 'profile', 'outline'),
    'edge_classify': ('subject', 'profile', 'atom_catalog'),
    'block_naming': ('subject', 'profile', 'block_outline'),
    'interblock_review': ('subject', 'profile', 'blocks'),
    'intrablock_steps': ('subject', 'profile', 'block_summaries'),
    'intrablock_repair': ('subject', 'profile', 'block_summaries'),
    'interface_bind': ('subject', 'profile', 'block_summaries'),
}


def _compact_json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def render_prompt(name, context):
    template = (PROMPT_DIR / f'{name}.txt').read_text(encoding='utf-8')
    return template.format(context=_compact_json(context))


def render_messages(name, context):
    template = (PROMPT_DIR / f'{name}.txt').read_text(encoding='utf-8')
    instructions = template.replace('{context}', '').strip()
    prefix_keys = SYSTEM_PREFIX_KEYS.get(name, ())
    sys_context = {key: context[key] for key in prefix_keys if key in context}
    user_context = {key: value for key, value in context.items() if key not in sys_context}
    system_prompt = instructions
    if sys_context:
        system_prompt += '\n共享前置上下文：\n' + _compact_json(sys_context)
    user_prompt = '输入数据如下：\n' + _compact_json(user_context)
    return system_prompt, user_prompt


def ask(name, context, operation):
    payload = context
    for attempt in range(2):
        system_prompt, user_prompt = render_messages(name, payload)
        result = AIService.structured_output(
            system_prompt=system_prompt, user_prompt=user_prompt,
            schema=SCHEMAS[name], tool_name=name, operation=operation, raise_on_error=True,
        )
        try:
            json.dumps(result, allow_nan=False)
            jsonschema.validate(result, SCHEMAS[name])
            return result
        except (ValueError, TypeError, jsonschema.ValidationError) as exc:
            if attempt == 1:
                raise AIResponseError(f'{name}: invalid structured response: {exc}') from exc
            detail = f"{list(exc.path)}: {exc.message}" if isinstance(exc, jsonschema.ValidationError) else str(exc)
            payload = {**context, 'schema_error': f'上一次返回未通过Schema校验，请严格修正：{detail}'}
