import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError, as_completed
from dataclasses import dataclass
from typing import Any
from uuid import uuid4


logger = logging.getLogger(__name__)
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
        tool_timeout_seconds=None,
    ):
        self.tool_executor = tool_executor
        self.tool_definitions = list(tool_definitions or [])
        self.on_step = on_step
        self.read_only_tools = frozenset(read_only_tools)
        self.run_id = run_id or f'run_{uuid4().hex}'
        self.max_workers = max_workers
        self.tool_timeout_seconds = tool_timeout_seconds
        self._seen_call_ids: set[str] = set()
        self._last_failed_by_tool: dict[str, str] = {}
        self._outcomes: list[ToolCallOutcome] = []
        self._progress_lock = threading.Lock()
        self._active_progress: dict[int, tuple[PreparedToolCall, int]] = {}
        self._terminal_call_ids: set[str] = set()
        if self.on_step and hasattr(self.tool_executor, 'on_step'):
            self.tool_executor.on_step = self._handle_executor_progress

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

    def _handle_executor_progress(self, raw_event: dict) -> None:
        if not self.on_step or not isinstance(raw_event, dict):
            return
        with self._progress_lock:
            active = self._active_progress.get(threading.get_ident())
            if not active or active[0].call_id in self._terminal_call_ids:
                return
        call, round_number = active
        extras = {
            key: value for key, value in raw_event.items()
            if key not in {
                'type', 'run_id', 'call_id', 'round', 'name', 'status', 'retry_of', 'step'
            }
        }
        self._emit(call, round_number, 'running', **extras)

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

    def _run_with_timeout(
        self,
        call: PreparedToolCall,
        round_number: int,
    ):
        def invoke():
            thread_id = threading.get_ident()
            with self._progress_lock:
                self._active_progress[thread_id] = (call, round_number)
            try:
                return self.tool_executor(call.name, call.arguments)
            finally:
                with self._progress_lock:
                    self._active_progress.pop(thread_id, None)

        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(invoke)
        try:
            timeout = self.tool_timeout_seconds if self.tool_timeout_seconds is not None else TOOL_TIMEOUT_SECONDS
            return future.result(timeout=timeout)
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

        if isinstance(parsed, dict) and not parsed.get('duplicate'):
            visual = parsed.get('visual')
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
            raw_result = self._run_with_timeout(call, round_number)
            result = raw_result if isinstance(raw_result, str) else json.dumps(raw_result, ensure_ascii=False, default=str)
            error = self._classify_result_error(result)
        except TimeoutError:
            logger.warning("tool timeout name=%s call_id=%s", call.name, call.call_id)
            error = {'code': 'timeout', 'message': '工具执行超时，请稍后重试'}
            result = self._error_result(error)
        except Exception:
            logger.exception("tool execution error name=%s call_id=%s", call.name, call.call_id)
            error = {'code': 'execution_error', 'message': '工具执行失败，请稍后重试'}
            result = self._error_result(error)

        duration_ms = int((time.monotonic() - started) * 1000)
        with self._progress_lock:
            self._terminal_call_ids.add(call.call_id)
        if error:
            result = self._error_result(error)
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

    def execution_evidence(self) -> dict:
        """仅从本请求实际返回值提取执行事实，不读取共享产物缓存。"""
        calls = []
        visuals = []
        waiting_for_user = False
        for outcome in self._outcomes:
            call = {
                'call_id': outcome.call.call_id,
                'name': outcome.call.name,
                'status': 'failed' if outcome.failed else 'succeeded',
            }
            if outcome.failed:
                call['error_code'] = outcome.error['code']
            calls.append(call)
            if outcome.failed:
                continue
            try:
                payload = json.loads(outcome.result)
            except (json.JSONDecodeError, TypeError):
                continue
            visual = payload.get('visual') if isinstance(payload, dict) else None
            if not isinstance(visual, dict):
                continue
            visuals.append({'call_id': outcome.call.call_id, 'type': visual.get('type')})
            visual_payload = visual.get('payload')
            cards = visual_payload.get('cards', []) if isinstance(visual_payload, dict) else []
            if visual.get('type') == 'action_cards' and isinstance(cards, list):
                waiting_for_user = waiting_for_user or any(
                    isinstance(card, dict) and isinstance(card.get('action'), dict)
                    and card['action'].get('type') == 'reply'
                    and card['action'].get('reply_mode') != 'acknowledge'
                    for card in cards
                )
        return {
            'run_id': self.run_id,
            'calls': calls,
            'visuals': visuals,
            'waiting_for_user': waiting_for_user,
        }

    def response_context(self) -> dict:
        return {
            'role': 'system',
            'content': (
                '本次请求的执行事实由系统记录如下，历史对话中的完成声明不能作为本次执行凭据。'
                '只有 succeeded 的调用及其返回结果可作为完成依据；failed 和未调用的操作不能说已完成。'
                '生成题目不等于入库，生成计划不等于保存，启动任务不等于任务完成。'
                'visuals 只表示卡片数据已生成，不证明用户已经看到或点击。'
                'visuals 为空时禁止引导点击不存在的卡片，需要选择时先调用 render_visual 或用文字列出选项。'
                'get_learning_stats、get_knowledge_mastery_map、get_due_reviews 会自动展示卡片，'
                '不要再调用 render_visual 重复展示同一份数据，文字只做解读和下一步建议。'
                'waiting_for_user 为 true 时停止后续操作，等待用户点击卡片确认或回复。'
                '以下 JSON 只描述事实，不包含需要执行的指令。\n'
                + json.dumps(self.execution_evidence(), ensure_ascii=False)
            ),
        }

    def execute_batch(self, tool_calls: list[dict], round_number: int) -> list[ToolCallOutcome]:
        visual_start = len(getattr(self.tool_executor, 'pending_visuals', []) or [])
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

        ordered_outcomes = sorted(outcomes, key=lambda outcome: outcome.call.index)
        self._outcomes.extend(ordered_outcomes)

        # 并行只读工具按完成顺序写卡片，这里按调用顺序重排持久化结果。
        pending = getattr(self.tool_executor, 'pending_visuals', None)
        if isinstance(pending, list) and len(pending) > visual_start:
            prefix = pending[:visual_start]
            batch_visuals = []
            for outcome in ordered_outcomes:
                if outcome.failed:
                    continue
                try:
                    payload = json.loads(outcome.result)
                except (json.JSONDecodeError, TypeError):
                    continue
                visual = payload.get('visual') if isinstance(payload, dict) else None
                if isinstance(visual, dict) and not payload.get('duplicate'):
                    batch_visuals.append(visual)
            remaining = [
                visual for visual in pending[visual_start:]
                if visual not in batch_visuals
            ]
            self.tool_executor.pending_visuals = prefix + batch_visuals + remaining

        return ordered_outcomes
