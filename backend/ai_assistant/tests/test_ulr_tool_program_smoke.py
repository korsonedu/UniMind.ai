"""Smoke the instruction contract before any dependent query can run."""
from rest_framework.exceptions import PermissionDenied

from ai_assistant.services.ulr_tool_program import CURRENT_COURSE_NAME, NAME, PRACTICE_NAME, PROGRAM_OPS, VERSION, run_program


def test_course_instruction_checks_fields_and_binds_the_selected_course():
    tools = PROGRAM_OPS[NAME]
    calls = []

    def execute(name, args):
        calls.append((name, args))
        if name == 'search_courses':
            return {'courses': [{'id': 77}, {'id': 81}][:args['limit']]}
        return {'segments': []}

    payload = {'v': VERSION, 'find': '久期', 'query': '凸性'}
    for args, code, field in (
        ({**payload, 'v': VERSION - 1}, 'stale_tool_version', '$.v'),
        ({'find': '久期'}, 'missing_tool_version', '$.v'),
        ({**payload, 'rank': 0}, 'invalid_arguments', '$.rank'),
        ({**payload, 'limit': 11}, 'invalid_arguments', '$.limit'),
        ({**payload, 'rank': '200'}, 'invalid_arguments', '$.rank'),
        ({**payload, 'limit': '11'}, 'invalid_arguments', '$.limit'),
        ({**payload, 'course_id': 77}, 'invalid_arguments', '$.course_id'),
    ):
        error = run_program(args, tools, execute)
        assert error['error']['code'] == code and not error['error']['repairable']
        assert error['field'] == field and error['steps_executed'] == []
    assert run_program(payload, tools[:1], execute)['error']['code'] == 'tool_not_offered'
    assert calls == []

    ambiguous = run_program({**payload, 'rank': 1}, tools, execute, message='有同名课请先问我。')
    assert ambiguous['error']['code'] == 'ambiguous_dependency'
    assert ambiguous['steps_executed'] == ['search_courses']
    assert calls == [('search_courses', {'query': '久期', 'limit': 2})]

    for rank in ('first', '02', '２', 2.0):
        invalid = run_program({**payload, 'rank': rank}, tools, execute)
        assert invalid['field'] == '$.rank' and invalid['error']['repairable'] and invalid['steps_executed'] == []
    mismatch = run_program({**payload, 'rank': 1}, tools, execute, message='请选第二门相关课程。')
    assert mismatch['error']['code'] == 'rank_mismatch' and mismatch['expected'] == 2 and mismatch['steps_executed'] == []
    selected = run_program({**payload, 'rank': '2', 'limit': '1'}, tools, execute, message='请选第二门相关课程。')
    assert selected['_ulr_source_id'] == 81 and selected['steps_executed'] == list(tools)
    assert calls[-2:] == [('search_courses', {'query': '久期', 'limit': 2}),
                         ('search_asr', {'query': '凸性', 'course_id': 81, 'limit': 1})]

    def withdrawn(name, args):
        if name == 'search_courses':
            return {'courses': [{'id': 77}]}
        assert args == {'course_id': 77, 'query': '久期'}
        raise PermissionDenied()

    revoked = run_program({'v': VERSION, 'find': '久期'}, tools, withdrawn)
    assert revoked['error']['code'] == 'source_access_revoked' and not revoked['error']['repairable']
    assert revoked['step'] == 'search_asr' and revoked['steps_executed'] == ['search_courses']


def test_practice_instruction_never_widens_a_missing_or_ambiguous_match():
    tools = PROGRAM_OPS[PRACTICE_NAME]
    calls = []

    def execute(name, arguments):
        calls.append(name)
        return {'results': [] if arguments['query'] == '久期' else [{'id': 1}, {'id': 2}]}

    payload = {'v': VERSION, 'find': '久期', 'limit': 1}
    for extra, field in (
        ({'knowledge_point_id': 77}, '$.knowledge_point_id'),
        ({'find': ' '}, '$.find'),
        ({'q_type': 'objective', 'subjective_type': 'essay'}, '$.subjective_type'),
    ):
        error = run_program({**payload, **extra}, tools, execute, name=PRACTICE_NAME)
        assert error['field'] == field and not error['error']['repairable']
    assert calls == []

    missing = run_program(payload, tools, execute, name=PRACTICE_NAME)
    assert missing['error']['code'] == 'missing_dependency'
    ambiguous = run_program({**payload, 'find': '折现', 'rank': 1}, tools, execute, name=PRACTICE_NAME,
                            message='有同名知识点请先向我确认。')
    assert ambiguous['error']['code'] == 'ambiguous_dependency' and not ambiguous['error']['repairable']
    assert ambiguous['steps_executed'] == ['search_knowledge_tree'] and calls == ['search_knowledge_tree'] * 2


def test_current_course_instruction_only_accepts_the_server_source():
    calls = []

    def execute(name, arguments):
        calls.append((name, arguments))
        return {'segments': []}

    args = {'v': VERSION, 'query': '凸性'}
    tools = PROGRAM_OPS[CURRENT_COURSE_NAME]
    missing = run_program(args, tools, execute, name=CURRENT_COURSE_NAME)
    forged = run_program({**args, 'course_id': 81}, tools, execute, name=CURRENT_COURSE_NAME, current_course_id=77)
    assert missing['error']['code'] == 'missing_course_context' and forged['field'] == '$.course_id'
    assert calls == []
    result = run_program(args, tools, execute, name=CURRENT_COURSE_NAME, current_course_id=77)
    assert result['_ulr_source_id'] == 77 and result['steps_executed'] == ['search_asr']
    assert calls == [('search_asr', {'query': '凸性', 'course_id': 77})]
