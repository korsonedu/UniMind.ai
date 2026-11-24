"""Bounded ULR execution for a teacher's workbench task."""
import json
import re
from time import monotonic

from django.db import close_old_connections
from jsonschema import validate

from ai_assistant.services.dsh_scope import check_execution, current_execution, generation_scope
from ai_engine.service import AIEngine
from ai_engine.tool_run import ToolRunCoordinator


GROUPS = {
    'questions': ('search_knowledge', 'quick_generate', 'launch_arc_pipeline', 'check_pipeline_status',
                  'get_workbench_stats', 'list_questions'),
    'students': ('get_student_detail', 'generate_student_report', 'send_notification'),
    'content': ('list_courses', 'list_articles'),
}


@generation_scope()
def run_workbench(messages, tools, executor, progress):
    execution = current_execution()
    definitions = {tool['function']['name']: tool for tool in tools}
    discovery = AIEngine._tool_def('find_teaching_tools',
        '切换教研工具。questions 为出题、审题和题库，students 为学情和通知预览，content 为课程和文章。',
        {'type': 'object', 'properties': {'group': {'type': 'string', 'enum': list(GROUPS)}},
         'required': ['group'], 'additionalProperties': False})
    definitions['find_teaching_tools'] = discovery
    prompt = messages[-1]['content'].casefold()
    group = ('students' if re.search(r'通知|学情|学生|学员|\bstudents?\b|\bnotif(?:y|ications?)\b', prompt) else
             'content' if re.search(r'课程|文章|\bcourses?\b|\barticles?\b', prompt) else 'questions')
    pending_group = None

    def execute(name, arguments):
        nonlocal pending_group
        close_old_connections()
        try:
            with generation_scope(execution):
                validate(arguments, definitions[name]['function']['parameters'])
                if name == 'find_teaching_tools':
                    pending_group = arguments['group']
                    return {'group': pending_group, 'tools': list(GROUPS[pending_group])}
                executor.check_dsh_scope()
                return executor(name, arguments)
        finally:
            close_old_connections()

    coordinator = ToolRunCoordinator(execute, [], on_step=progress, tool_timeout_seconds=35)
    for index in range(8):
        check_execution(execution)
        offered = [definitions[name] for name in GROUPS[group] if name in definitions] + [discovery] if index < 7 else []
        model_messages = [*messages, coordinator.response_context()]
        if len(json.dumps([model_messages, offered], ensure_ascii=False).encode()) > 65536:
            raise ValueError('教研对话上下文超过本轮预算。')
        remaining = execution['deadline'] - monotonic()
        if remaining <= 0:
            raise ValueError('教研对话超过本轮时限。')
        response = AIEngine.call_provider(model_messages, operation='assistant.chat.exam_generator',
            temperature=0.6, max_tokens=2500, tools=offered or None, tool_choice='auto' if offered else None,
            raise_on_error=True, max_retries=0, timeout_seconds=min(30, remaining))
        check_execution(execution)
        result = response['choices'][0]
        calls = AIEngine._extract_tool_calls(response)
        if result.get('finish_reason') == 'stop' and not calls:
            result['message']['content'] = AIEngine._strip_dsml(result['message'].get('content') or '')
            return response
        if result.get('finish_reason') != 'tool_calls' or not offered or not 1 <= len(calls) <= 7:
            raise ValueError('教研对话未返回完整答复。')
        coordinator.tool_definitions = offered
        outcomes = coordinator.execute_batch(calls, index + 1)
        messages.append({**result['message'], 'role': 'assistant', 'tool_calls': [outcome.call.tool_call for outcome in outcomes]})
        messages.extend({'role': 'tool', 'tool_call_id': outcome.call.call_id, 'content': outcome.result} for outcome in outcomes)
        if pending_group:
            group, pending_group = pending_group, None
