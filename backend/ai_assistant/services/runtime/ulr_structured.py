"""Collect one typed result through the native provider transport."""
from contextlib import contextmanager
from contextvars import ContextVar
import json
from time import monotonic

from jsonschema import ValidationError as SchemaError, validate

from ai_engine.service import AICallError, AIEngine
from ai_engine.tool_run import TOOL_ARGUMENT_DECODER
from ai_assistant.services.dsh_scope import check_execution, check_teaching_task, current_execution
from ai_assistant.services.runtime.ulr_config import ulr_enabled


TEACHING_COLLECTORS = frozenset({
    'pipeline.author', 'pipeline.author_revise', 'pipeline.reviewer', 'pipeline.classifier',
    'quizzes.bulk_generate', 'quizzes.single_pipeline.reviewer',
    'knowledge_tree_dispatch', 'knowledge_tree_decompose', 'knowledge_tree_edges',
    'knowledge_tree_repair', 'knowledge_tree_block',
})
_ulr_question_pipeline = ContextVar('ulr_question_pipeline', default=False)


class InvalidStructuredOutput(ValueError):
    pass


class RetryableProviderFailure(ValueError):
    pass


@contextmanager
def question_pipeline_runtime(requires_ulr):
    token = _ulr_question_pipeline.set(requires_ulr)
    try:
        yield
    finally:
        _ulr_question_pipeline.reset(token)


def teaching_enabled(operation):
    return operation in TEACHING_COLLECTORS and (
        ulr_enabled() or (_ulr_question_pipeline.get() and operation.startswith('pipeline.')))


def run_collector(prompt, *, instruction, operation, name, schema, max_tokens, temperature,
                  repair=False, research_tools=(), executor=None, max_requests=1, deadline=None):
    if len(prompt.encode()) > 48000:
        raise ValueError('任务材料超过结构化执行预算。')
    return collect_messages([{'role': 'system', 'content': instruction}, {'role': 'user', 'content': prompt}],
        operation=operation, name=name, schema=schema, max_tokens=max_tokens, temperature=temperature,
        repair=repair, research_tools=research_tools, executor=executor, max_requests=max_requests, array_key='questions',
        deadline=deadline)


def collect_messages(messages, *, operation, name, schema, max_tokens, temperature,
                     repair=False, research_tools=(), executor=None, max_requests=1, array_key='items',
                     description='提交本次结构化结果', deadline=None):
    array_result = schema.get('type') == 'array'
    if array_result:
        schema = {'type': 'object', 'properties': {array_key: schema},
                  'required': [array_key], 'additionalProperties': False}
    tool = AIEngine._tool_def(name, description, schema)
    research = {item['function']['name']: item['function']['parameters'] for item in research_tools}
    if research.keys() - {'lookup_knowledge_point_definition', 'search_similar_questions'}:
        raise ValueError('审题只允许查询知识点和同类题。')
    messages = list(messages)
    execution = current_execution()
    scope_deadline = execution['deadline'] if execution else monotonic() + 90
    deadline = min(deadline, scope_deadline) if deadline is not None else scope_deadline

    def check_scope():
        if execution:
            check_execution(execution)
        else:
            check_teaching_task()
    budget = 2 if repair else min(max_requests, 5)
    seen_ids = set()
    for attempt in range(budget):
        offered = [*research_tools, tool] if attempt < budget - 1 else [tool]
        remaining = deadline - monotonic()
        if remaining <= 0 or len(json.dumps([messages, offered], ensure_ascii=False).encode()) > 65536:
            raise ValueError('结构化任务超出执行预算。')
        check_scope()
        try:
            response = AIEngine.call_provider(messages, operation=operation, temperature=temperature,
                tools=offered, tool_choice='auto' if research else 'required', max_tokens=max_tokens,
                timeout_seconds=min(30, remaining),
                max_retries=0, raise_on_error=True)
        except AICallError as exc:
            if exc.error_category == 'invalid_json':
                if repair and attempt == 0:
                    continue
                raise InvalidStructuredOutput('模型未返回可解析的结构化结果。') from exc
            failure = RetryableProviderFailure if exc.retryable else ValueError
            raise failure('结构化任务未完成，可重试。') from exc
        check_scope()
        choices = response.get('choices') or []
        calls = AIEngine._extract_tool_calls(response)
        if monotonic() >= deadline:
            raise ValueError('结构化任务超出执行时限。')
        choice = choices[0] if choices else {}
        message = choice.get('message') or {}
        content = message.get('content') or ''
        if (not AIEngine._complete_tool_round(choice.get('finish_reason'), calls, offered)
                or AIEngine._has_open_dsml(content)
                or not 1 <= len(calls) <= 8):
            break
        names = [call.get('function', {}).get('name') for call in calls]
        if names == [name]:
            try:
                result = TOOL_ARGUMENT_DECODER.decode(calls[0]['function']['arguments'])
            except (ValueError, KeyError, TypeError, RecursionError):
                if repair:
                    continue
                break
            try:
                json.dumps(result, allow_nan=False)
                validate(result, schema)
            except SchemaError as exc:
                path = '.'.join(map(str, exc.absolute_path))[:180] or '$'
                raise InvalidStructuredOutput(f'字段 {path} 未通过 {exc.validator} 校验。') from None
            except ValueError:
                raise InvalidStructuredOutput('结构化结果含有非有限数值。') from None
            return result[array_key] if array_result else result
        if attempt == budget - 1 or not set(names) <= research.keys():
            break
        messages.append({**message, 'role': 'assistant', 'content': AIEngine._strip_dsml(content) or None,
                         'tool_calls': calls})
        for call, tool_name in zip(calls, names):
            call_id = call.get('id')
            if not isinstance(call_id, str) or not call_id or call_id in seen_ids:
                raise InvalidStructuredOutput('审题工具调用标识无效。')
            seen_ids.add(call_id)
            try:
                arguments = TOOL_ARGUMENT_DECODER.decode(call['function']['arguments'])
                validate(arguments, research[tool_name])
            except (KeyError, TypeError, ValueError, SchemaError):
                raise InvalidStructuredOutput('审题工具参数不符合要求。') from None
            check_scope()
            content = executor(tool_name, arguments)
            check_scope()
            messages.append({'role': 'tool', 'tool_call_id': call_id, 'content': content})
    raise InvalidStructuredOutput('未收到完整结构化结果，可重试。')
