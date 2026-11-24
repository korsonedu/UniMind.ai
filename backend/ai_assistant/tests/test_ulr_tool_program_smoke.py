"""Smoke the instruction contract before any dependent query can run."""
from rest_framework.exceptions import PermissionDenied

from ai_assistant.services.ulr_tool_program import (
    CURRENT_COURSE_NAME, LEGACY_VERSION, NAME, PRACTICE_NAME, PROGRAM_OPS, PROGRAM_TOOLS, VERSION,
    compile_current_course_locator, compile_practice_request, run_program,
)


def test_course_instruction_checks_fields_and_binds_the_selected_course():
    tools = PROGRAM_OPS[NAME]
    calls = []

    def execute(name, args):
        calls.append((name, args))
        if name == 'search_courses':
            return {'courses': [{'id': 77}, {'id': 81}][:args['limit']]}
        return {'segments': []}

    payload = {'find': '久期', 'query': '凸性'}
    for tool in PROGRAM_TOOLS.values():
        assert {'v', 'rank'}.isdisjoint(tool['function']['parameters']['properties'])
    for args, code, field in (
        ({**payload, 'v': LEGACY_VERSION - 1}, 'stale_tool_version', '$.v'),
        ({**payload, 'v': None}, 'stale_tool_version', '$.v'),
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
    inferred = run_program({**payload, 'limit': 1}, tools, execute, message='请选第二门相关课程。')
    assert inferred == selected
    assert run_program({**payload, 'v': LEGACY_VERSION, 'rank': 2, 'limit': 1},
                       tools, execute, message='请选第二门相关课程。') == selected
    missing = run_program(payload, tools, execute, message='请选第三门课。')
    assert missing['error']['code'] == 'missing_dependency' and missing['steps_executed'] == ['search_courses']
    assert calls[-1] == ('search_courses', {'query': '久期', 'limit': 3})
    count = len(calls)
    for message in ('选第11门课。', '选第0门课。', '选第100门课。', '选第十六门课。', 'Use the 101st course.'):
        outside = run_program(payload, tools, execute, message=message)
        assert outside['error']['code'] == 'rank_out_of_range' and outside['steps_executed'] == []
        assert len(calls) == count

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

    payload = {'find': '久期', 'limit': 1}
    for extra, field in (
        ({'knowledge_point_id': 77}, '$.knowledge_point_id'),
        ({'find': ' '}, '$.find'),
        ({'output': 'answer'}, '$.output'),
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


def test_practice_compiler_requires_an_explicit_card_and_literal_topic():
    request = '请给我2道「第2项现金流折现」知识点的练习题。只要练习卡。'
    assert compile_practice_request(request) == {'find': '第2项现金流折现', 'limit': 2}
    for invalid in (request.replace('我2道', '我11道'), request.replace('我2道', '我0道'),
                    request.replace('只要练习卡。', '还要讲解。'), '先提示我一下。' + request,
                    request.replace('「第2项现金流折现」', '第2项现金流折现')):
        assert compile_practice_request(invalid) is None


def test_current_course_instruction_only_accepts_the_server_source():
    request = '请定位当前课程的「折现率」讲稿。只要时间点。'
    assert compile_current_course_locator(request) == {'query': '折现率'}
    for question in (request.replace('「折现率」', '折现率'), request.replace('只要时间点。', '请解释。'),
                     request + '再给我两道题。', request.replace('折现率', ' ')):
        assert compile_current_course_locator(question) is None

    calls = []

    def execute(name, arguments):
        calls.append((name, arguments))
        return {'segments': []}

    args = {'query': '凸性'}
    tools = PROGRAM_OPS[CURRENT_COURSE_NAME]
    missing = run_program(args, tools, execute, name=CURRENT_COURSE_NAME)
    forged = run_program({**args, 'course_id': 81}, tools, execute, name=CURRENT_COURSE_NAME, current_course_id=77)
    assert missing['error']['code'] == 'missing_course_context' and forged['field'] == '$.course_id'
    assert calls == []
    result = run_program(args, tools, execute, name=CURRENT_COURSE_NAME, current_course_id=77)
    assert result['_ulr_source_id'] == 77 and result['steps_executed'] == ['search_asr']
    assert calls == [('search_asr', {'query': '凸性', 'course_id': 77})]


def test_instruction_waits_for_a_single_affirmative_ordinal():
    calls = []

    def execute(name, args):
        calls.append((name, args))
        if name == 'search_courses':
            return {'courses': [{'id': 77}, {'id': 81}][:args['limit']]}
        if name == 'search_knowledge_tree':
            return {'results': [{'id': 77}]}
        return {'segments': []}

    for name, message in (
        (NAME, '不要第一门课。'),
        (NAME, '请不选择第一门课。'),
        (NAME, '第一门相关课程先跳过。'),
        (NAME, '第一门课还是第二门课，请等我确认。'),
        (NAME, '请选第二门课，不要第二门课。'),
        (NAME, 'Do not use the first course.'),
        (NAME, 'Skip the 2nd course and use the 2nd course.'),
        (NAME, 'Skip the first course and the second course.'),
        (PRACTICE_NAME, '别用第一项出练习。'),
        (PRACTICE_NAME, 'Skip the first matching knowledge point.'),
    ):
        receipt = run_program({'find': '折现率', 'rank': 1}, PROGRAM_OPS[name], execute, name=name, message=message)
        assert receipt['error']['code'] == 'selection_needs_confirmation'
        assert not receipt['error']['repairable'] and not receipt['steps_executed']
        assert not calls

    for message in (
        '不要第一门课，请选第二门相关课程。',
        'Skip the first course and use the second matching course.',
        '请选第２门课。',
        'Use the 2nd matching course.',
    ):
        receipt = run_program({'find': '折现率'}, PROGRAM_OPS[NAME], execute, message=message)
        assert receipt['_ulr_source_id'] == 81
        assert calls[-1] == ('search_asr', {'query': '折现率', 'course_id': 81})
