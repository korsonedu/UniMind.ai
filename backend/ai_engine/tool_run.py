import json
from dataclasses import dataclass
from typing import Any
from uuid import uuid4


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

    def execute_batch(self, tool_calls: list[dict], round_number: int) -> list[ToolCallOutcome]:
        outcomes = []
        for index, tool_call in enumerate(tool_calls):
            prepared = self._normalize_call(tool_call, index)
            if prepared.error:
                outcomes.append(ToolCallOutcome(
                    call=prepared,
                    result=self._error_result(prepared.error),
                    failed=True,
                    error=prepared.error,
                ))
                continue
            result = str(self.tool_executor(prepared.name, prepared.arguments))
            outcomes.append(ToolCallOutcome(
                call=prepared,
                result=result,
                failed=False,
            ))
        return outcomes
