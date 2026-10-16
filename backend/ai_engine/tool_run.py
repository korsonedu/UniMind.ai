import json
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError, as_completed
from dataclasses import dataclass
from typing import Any
from uuid import uuid4


TOOL_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class PreparedToolCall:
    index: int
    tool_call: dict
    call_id: str
    name: str
    arguments: dict
    label: str
    retry_of: str | None = None
    error: dict | None = None


@dataclass(frozen=True)
class ToolCallOutcome:
    call: PreparedToolCall
    result: str
    failed: bool
    error: dict | None = None


def validate_arguments(schema: dict, value: Any, path: str = '$') -> str | None:
    schema_type = schema.get('type')
    if schema_type == 'object':
        if not isinstance(value, dict):
            return f'{path} must be an object'
        properties = schema.get('properties') or {}
        for required_name in schema.get('required') or []:
            if required_name not in value:
                return f'{path}.{required_name} is required'
        if schema.get('additionalProperties') is False:
            unexpected = next((name for name in value if name not in properties), None)
            if unexpected is not None:
                return f'{path}.{unexpected} is not allowed'
        for name, item in value.items():
            item_schema = properties.get(name)
            if item_schema:
                error = validate_arguments(item_schema, item, f'{path}.{name}')
                if error:
                    return error
        return None
    if schema_type == 'array':
        if not isinstance(value, list):
            return f'{path} must be an array'
        item_schema = schema.get('items')
        if item_schema:
            for index, item in enumerate(value):
                error = validate_arguments(item_schema, item, f'{path}[{index}]')
                if error:
                    return error
        return None
    if schema_type == 'string' and not isinstance(value, str):
        return f'{path} must be a string'
    if schema_type == 'integer' and (isinstance(value, bool) or not isinstance(value, int)):
        return f'{path} must be an integer'
    if schema_type == 'number' and (isinstance(value, bool) or not isinstance(value, (int, float))):
        return f'{path} must be a number'
    if schema_type == 'boolean' and not isinstance(value, bool):
        return f'{path} must be a boolean'
    return None


class ToolRunCoordinator:
    def __init__(
        self,
        tool_executor,
        tool_definitions,
        on_step=None,
        read_only_tools=frozenset(),
        run_id=None,
        max_workers=4,
    ):
        self.tool_executor = tool_executor
        self.tool_definitions = list(tool_definitions or [])
        self.on_step = on_step
        self.read_only_tools = frozenset(read_only_tools)
        self.run_id = run_id or f'run_{uuid4().hex}'
        self.max_workers = max_workers
        self._seen_call_ids: set[str] = set()
        self._last_failed_by_tool: dict[str, str] = {}

    @staticmethod
    def _definitions_by_name(definitions) -> dict[str, dict]:
        registry = {}
        for definition in definitions or []:
            function = definition.get('function') or {}
            name = function.get('name')
            if name:
                registry[name] = definition
        return registry

    def _tool_registry(self) -> dict[str, dict]:
        permitted = getattr(self.tool_executor, '_permitted_tool_definitions', None)
        if permitted:
            return dict(permitted)
        return self._definitions_by_name(self.tool_definitions)

    def _next_call_id(self) -> str:
        while True:
            call_id = f'call_{uuid4().hex}'
            if call_id not in self._seen_call_ids:
                return call_id

    def _normalize_call(self, tool_call: dict, index: int) -> PreparedToolCall:
        function = tool_call.get('function') or {}
        name = str(function.get('name') or '')
        upstream_id = str(tool_call.get('id') or '')
        if not upstream_id or upstream_id.startswith('dsml_') or upstream_id in self._seen_call_ids:
            call_id = self._next_call_id()
        else:
            call_id = upstream_id
        self._seen_call_ids.add(call_id)

        normalized_tool_call = {
            **tool_call,
            'id': call_id,
            'type': tool_call.get('type') or 'function',
            'function': dict(function),
        }

        try:
            arguments = json.loads(function.get('arguments') or '{}')
        except (json.JSONDecodeError, TypeError):
            arguments = None

        error = self._validate_call(name, arguments)
        safe_arguments = arguments if isinstance(arguments, dict) else {}
        try:
            from ai_assistant.services.tool_executor import generate_step_label
            label = generate_step_label(name, safe_arguments)
        except Exception:
            label = f'执行 {name}'

        return PreparedToolCall(
            index=index,
            tool_call=normalized_tool_call,
            call_id=call_id,
            name=name,
            arguments=safe_arguments,
            label=label,
            retry_of=self._last_failed_by_tool.get(name),
            error=error,
        )

    def _validate_call(self, name: str, arguments: Any) -> dict | None:
        offered_registry = self._definitions_by_name(self.tool_definitions)
        permitted_registry = self._tool_registry()
        if name not in offered_registry and name not in permitted_registry:
            return {'code': 'unknown_tool', 'message': f'Unknown tool: {name}'}

        permitted_names = getattr(self.tool_executor, '_permitted_tool_names', None)
        if permitted_names is not None and name not in permitted_names:
            return {'code': 'permission_denied', 'message': f'Tool not permitted: {name}'}
        if name not in permitted_registry:
            return {'code': 'permission_denied', 'message': f'Tool not permitted: {name}'}
        if not isinstance(arguments, dict):
            return {'code': 'invalid_arguments', 'message': 'Tool arguments must be a JSON object'}

        function = permitted_registry[name].get('function') or {}
        schema = function.get('parameters') or {'type': 'object'}
        validation_error = validate_arguments(schema, arguments)
        if validation_error:
            return {'code': 'invalid_arguments', 'message': validation_error}
        return None

    @staticmethod
    def _error_result(error: dict) -> str:
        return json.dumps({'error': error}, ensure_ascii=False)

    def _emit(self, call: PreparedToolCall, round_number: int, status: str, **fields) -> None:
        if not self.on_step:
            return
        event = {
            'type': 'step',
            'run_id': self.run_id,
            'call_id': call.call_id,
            'round': round_number,
            'name': call.name,
            'label': call.label,
            'status': status,
            'retry_of': call.retry_of,
        }
        event.update(fields)
        self.on_step(event)

    @staticmethod
    def _classify_result_error(result: str) -> dict | None:
        try:
            payload = json.loads(result)
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(payload, dict) or 'error' not in payload:
            return None
        raw_error = payload['error']
        if isinstance(raw_error, dict):
            raw_code = str(raw_error.get('code') or '')
            message = str(raw_error.get('message') or raw_code or 'Tool execution failed')
        else:
            raw_code = str(raw_error)
            message = raw_code or 'Tool execution failed'
        code = 'timeout' if raw_code == 'timeout' else 'execution_error'
        return {'code': code, 'message': message}

    def _run_with_timeout(self, name: str, arguments: dict):
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(self.tool_executor, name, arguments)
        try:
            return future.result(timeout=TOOL_TIMEOUT_SECONDS)
        except FutureTimeoutError as exc:
            future.cancel()
            raise TimeoutError('Tool execution timed out') from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _event_extras(self, call: PreparedToolCall, result: str) -> dict:
        extras = {}
        try:
            from ai_assistant.services.tool_executor import extract_step_actions, summarize_tool_result
            extras['result_summary'] = summarize_tool_result(call.name, result)
            actions = extract_step_actions(result)
            if actions:
                extras['actions'] = actions
        except Exception:
            extras['result_summary'] = result[:200]

        try:
            parsed = json.loads(result)
        except (json.JSONDecodeError, TypeError):
            parsed = None

        if call.name == 'render_visual':
            visual = parsed.get('visual') if isinstance(parsed, dict) else None
            if not visual:
                pending_visuals = getattr(self.tool_executor, 'pending_visuals', None)
                if pending_visuals:
                    visual = pending_visuals[-1]
            if isinstance(visual, dict):
                visual = dict(visual)
                if isinstance(visual.get('payload'), str):
                    try:
                        visual['payload'] = json.loads(visual['payload'])
                    except (json.JSONDecodeError, TypeError):
                        visual['payload'] = {}
                extras['visual'] = visual

        if call.name == 'quick_generate':
            questions = getattr(self.tool_executor, '_last_generated', None)
            if not questions and isinstance(parsed, dict):
                questions = parsed.get('questions')
            if questions:
                extras['questions'] = questions
        return extras

    def _execute_one(self, call: PreparedToolCall, round_number: int) -> ToolCallOutcome:
        self._emit(call, round_number, 'running')
        started = time.monotonic()
        try:
            raw_result = self._run_with_timeout(call.name, call.arguments)
            result = raw_result if isinstance(raw_result, str) else json.dumps(raw_result, ensure_ascii=False, default=str)
            error = self._classify_result_error(result)
        except TimeoutError:
            error = {'code': 'timeout', 'message': 'Tool execution timed out'}
            result = self._error_result(error)
        except Exception as exc:
            error = {'code': 'execution_error', 'message': str(exc)}
            result = self._error_result(error)

        duration_ms = int((time.monotonic() - started) * 1000)
        if error:
            self._emit(
                call,
                round_number,
                'failed',
                duration_ms=duration_ms,
                result_summary=error['message'][:200],
                error=error,
            )
            return ToolCallOutcome(call=call, result=result, failed=True, error=error)

        self._emit(
            call,
            round_number,
            'succeeded',
            duration_ms=duration_ms,
            **self._event_extras(call, result),
        )
        return ToolCallOutcome(call=call, result=result, failed=False)

    def _remember_outcome(self, outcome: ToolCallOutcome) -> None:
        if outcome.failed:
            self._last_failed_by_tool[outcome.call.name] = outcome.call.call_id
        else:
            self._last_failed_by_tool.pop(outcome.call.name, None)

    def execute_batch(self, tool_calls: list[dict], round_number: int) -> list[ToolCallOutcome]:
        prepared_calls = [
            self._normalize_call(tool_call, index)
            for index, tool_call in enumerate(tool_calls)
        ]
        for call in prepared_calls:
            self._emit(call, round_number, 'queued')

        outcomes = []
        valid_calls = []
        for call in prepared_calls:
            if call.error:
                outcome = ToolCallOutcome(
                    call=call,
                    result=self._error_result(call.error),
                    failed=True,
                    error=call.error,
                )
                outcomes.append(outcome)
                self._emit(call, round_number, 'failed', error=call.error, result_summary=call.error['message'])
                self._remember_outcome(outcome)
            else:
                valid_calls.append(call)

        all_read_only = bool(valid_calls) and all(
            call.name in self.read_only_tools for call in valid_calls
        )
        if all_read_only and len(valid_calls) > 1:
            workers = min(self.max_workers, len(valid_calls))
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {
                    executor.submit(self._execute_one, call, round_number): call
                    for call in valid_calls
                }
                for future in as_completed(futures):
                    outcome = future.result()
                    outcomes.append(outcome)
                    self._remember_outcome(outcome)
        else:
            for call in valid_calls:
                if hasattr(self.tool_executor, '_current_call_id'):
                    self.tool_executor._current_call_id = call.call_id
                outcome = self._execute_one(call, round_number)
                outcomes.append(outcome)
                self._remember_outcome(outcome)

        return sorted(outcomes, key=lambda outcome: outcome.call.index)
