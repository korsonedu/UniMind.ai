"""Capture learning tasks through the XiaoYu product routes with isolated data."""
from contextlib import ExitStack, contextmanager
from functools import partial
from hashlib import sha256
from itertools import permutations
import json
import os
from pathlib import Path
from runpy import run_path
from subprocess import check_output
import sys
from time import monotonic
from unittest.mock import Mock, patch
from urllib.parse import urlsplit
from uuid import uuid4

from asgiref.sync import async_to_sync
import pytest

from ai_assistant import views_dsh
from ai_assistant.models import (
    AIChatMessage, AgentMemory, Bot, Conversation, ConversationProject, MemoryExtractionLog, PendingMemoryExtraction,
    ProjectLearning,
)
from ai_assistant.services import memory_service, ulr_memory, ulr_runtime
from ai_assistant.services.dsh_runtime import log_model_observation
from ai_assistant.services.dsh_service import build_context
from ai_engine.config import get_model_for_task
from ai_engine.observability import observe_background, runtime_observation
from backoffice.tasks import run_teaching_task
from courses.models import Course, TranscriptSegment, VideoTranscript
from quizzes.ai_workflow import run_exam_grading
from quizzes.models import KnowledgePoint, Question, QuizExam
from quizzes.services.question_normalizer import normalize_objective_answer, normalize_options
from users.models import AIUsageReservation, CourseStudentStatus, WeeklyAIQuotaConfig


LIMITS = {'dsh': 6, 'ulr_individual': 4, 'ulr': 4}
OUTPUT_LIMIT = 1024
REPLY = 'PV = FV / (1 + r)^t。一年后 110 元按 10% 折现，现值 100 元。'


async def consume(response, started):
    return [{'elapsed_ms': round((monotonic() - started) * 1000), 'event': json.loads(frame[6:])}
            async for frame in response.streaming_content if frame.startswith(b'data: ')]


def capture_order(paths, trial):
    forward = [order for order in permutations(paths) if order[0] < order[-1]]
    order = forward[((trial - 1) // 2) % len(forward)]
    return enumerate(order if trial % 2 else reversed(order), start=1)


def bounded_context(builder, limit, model, *args, **kwargs):
    context = builder(*args, **kwargs)
    policy = context['model_policy']
    assert policy['max_tokens'] >= OUTPUT_LIMIT
    policy.update(model=model, max_requests=min(policy['max_requests'], limit), max_tokens=OUTPUT_LIMIT)
    return context


def scripted_provider(definitions, reply):
    calls = iter(definitions)

    class Response:
        status_code = 200

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def raise_for_status(self):
            pass

        def iter_lines(self, **_):
            name, arguments = next(calls, (None, {}))
            delta = {'content': reply}
            if name:
                delta = {'tool_calls': [{'index': 0, 'id': str(uuid4()),
                    'function': {'name': name, 'arguments': json.dumps(arguments)}}]}
            payload = {'model': 'capture-fixture-model', 'usage': {'prompt_tokens': 50, 'completion_tokens': 10},
                       'choices': [{'delta': delta, 'finish_reason': 'tool_calls' if name else 'stop'}]}
            yield f'data: {json.dumps(payload)}'.encode()
            yield b'data: [DONE]'

    return Response()


def capture_revision(repo):
    revision = check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip()
    files = check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z', '--',
                          'backend', 'dsh', 'scripts/fixtures', 'scripts/ulr_review_pairs.py'], cwd=repo)
    digest = sha256()
    for name in sorted(set(files.split(b'\0')) - {b''}):
        path = repo / os.fsdecode(name)
        if path.is_file():
            digest.update(name + b'\0' + sha256(path.read_bytes()).digest())
    return f'{revision}:{digest.hexdigest()}'


def prepare_capture(repo, output, records, caplog, tool, baselines):
    revision = capture_revision(repo)
    assert all(record['revision'] == revision for record in records), '采集期间候选源码已变化。'
    source_log = output / 'operations.log'
    source_log.write_text('\n'.join(f'{row.name} {row.getMessage()}' for row in caplog.records
                                    if row.name == 'ai_engine.observability'))
    operations = tool['read_operations']([source_log])
    models = {row['reported_model'] for calls in operations.values() for row in calls if row['reported_model']}
    if len(models) == 1:
        for record in records:
            record['model'] = next(iter(models))
    tool['write'](output / 'runs.json', records)
    for baseline in baselines:
        tool['prepare'](records, output / baseline, baseline, operations)
    return operations


@contextmanager
def capture_attempt(attempts, runtime, request_id, **source):
    with observe_background(runtime, request_id, **source):
        attempts.setdefault(request_id, []).append(str(runtime_observation.get()['attempt_id']))
        yield


def structured_capture_config(settings, official, state_dir, operation):
    config = (get_model_for_task(operation) if official else
              {'api_key': 'fixture', 'base_url': 'https://example.invalid/chat', 'model': 'capture-fixture-model'})
    if official:
        provider = urlsplit(config['base_url'])
        assert config['api_key'] and (provider.scheme, provider.hostname) == ('https', 'api.deepseek.com')
        assert Path(settings.UNIMIND_DSH_PYTHON).is_absolute() and Path(settings.UNIMIND_DSH_PYTHON).is_file()
    else:
        settings.UNIMIND_DSH_PYTHON = sys.executable
    settings.DEBUG = True
    settings.UNIMIND_DSH_FIXTURE_URL = '' if official else 'http://127.0.0.1:8912/v1/messages'
    settings.UNIMIND_DSH_STATE_DIR = str(state_dir)
    settings.UNIMIND_ULR_PROTOTYPE = False
    settings.UNIMIND_CONTENT_INSTITUTION_ID = 'global'
    return config


def scripted_structured_provider(scope, model, operation, collector, limit, result):
    worker_record = {'status': 'completed', 'operation': operation, 'elapsed_ms': 1, 'model': model,
                     'reported_model': model, 'max_output_tokens': limit, 'request': 1,
                     'offered_tools': [collector], 'submitted_tools': [collector], 'usage_complete': True,
                     'usage': {'input_tokens': 50, 'output_tokens': 10}}
    popen = scope.enter_context(patch('ai_assistant.services.dsh_tasks.subprocess.Popen'))
    worker = popen.return_value.__enter__.return_value
    worker.returncode = 0
    worker.communicate.return_value = (json.dumps({'status': 200, 'result': result,
        'observations': [worker_record]}).encode(), b'')
    provider_response = Mock(status_code=200)
    provider_response.json.return_value = {'model': model, 'usage': {'prompt_tokens': 50, 'completion_tokens': 10},
        'choices': [{'finish_reason': 'tool_calls', 'message': {'tool_calls': [
            {'function': {'name': collector, 'arguments': json.dumps(result)}}]}}]}
    transport = scope.enter_context(patch('ai_engine.service._session.post', return_value=provider_response))
    return popen, worker, transport


def capture_acceptance(case_name, official, auth_client, user, settings, request, tmp_path, caplog, *, delivery=None):
    repo = Path(settings.BASE_DIR).parent
    tool = run_path(str(repo / 'scripts/ulr_review_pairs.py'))
    sample_path = repo / f'scripts/fixtures/ulr_{case_name}_review.json'
    sample = tool['read'](sample_path)
    delivery_cases = sample.pop('delivery_cases', {})
    direct = delivery == 'direct'
    if delivery:
        variant = delivery_cases[delivery].copy()
        sample['case_id'] = variant.pop('case_id')
        sample['case'].update(variant)
        if not direct:
            for baseline in ('dsh', 'ulr_individual'):
                sample['case']['tool_paths'][baseline] = ['search_courses', 'search_asr']
    source = sample['case']['fixture']
    practice = case_name == 'practice'
    project_case = case_name == 'project'
    limits = {'dsh': LIMITS['dsh'], 'ulr': LIMITS['ulr']} if project_case else LIMITS
    if direct:
        limits = {'dsh': LIMITS['dsh'], 'ulr_model_instruction': LIMITS['ulr'], 'ulr': LIMITS['ulr']}
    if project_case:
        proposal = source['proposal']
        individual = [('read_learning_project', {}), ('plan_learning_project', {
            'revision': 0, 'plan': proposal, 'next_action': proposal['stages'][0]['task'],
            'reason': '在现值计算后增加解释阶段', 'major_change': True, 'require_confirmation': True,
        })]
        combined = individual
        reply = '两阶段草稿已保存，请在学习路径确认后采用。'
    elif practice:
        point = KnowledgePoint.objects.create(name=source['point'])
        question = Question.objects.create(knowledge_point=point, text=source['stem'], options=source['options'],
            correct_answer=source['correct_answer'], grading_points=source['grading_points'])
        individual = [('search_knowledge_tree', {'query': point.name}),
                      ('get_practice_questions', {'knowledge_point_id': point.pk, 'limit': 1})]
        combined = [('run_practice_tools', {'find': point.name, 'limit': 1})]
        reply = '练习已准备好，请在卡片里独立作答。'
    else:
        course = Course.objects.create(is_published=True, title=source['course_title'])
        transcript = VideoTranscript.objects.create(course=course, asr_status='completed')
        TranscriptSegment.objects.create(transcript=transcript, text=source['transcript'],
                                         start_time=source['start_time'], end_time=source['end_time'], index=0)
        individual = [('find_learning_tools', {'group': 'resources'}), ('search_courses', {'query': '折现率'}),
                      ('search_asr', {'course_id': course.pk, 'query': '折现率'})]
        combined = [('run_course_tools', {'find': '折现率'})]
        if direct:
            other_course = Course.objects.create(is_published=True, title=course.title)
            other_transcript = VideoTranscript.objects.create(course=other_course, asr_status='completed')
            TranscriptSegment.objects.create(transcript=other_transcript, text='折现率在同名课程的讲稿。',
                                             start_time=120, end_time=140, index=0)
            individual = individual[-1:]
            combined = [('locate_current_course_transcript', {'query': '折现率'})]
        elif delivery:
            individual = individual[1:]
        if delivery == 'explanation':
            # An old client may still send a card hint for a mixed request.
            combined[0][1]['output'] = 'card'
        reply = '已找到 01:00 的讲稿片段。' if delivery in ('timestamp', 'direct') else REPLY
    CourseStudentStatus.objects.create(user=user, is_course_student=True)
    WeeklyAIQuotaConfig.objects.update_or_create(pk=1, defaults={'course_calls': 20})
    bot, _ = Bot.objects.get_or_create(is_xiaoyu=True, defaults={'name': '小宇'})
    settings.DEBUG = True
    settings.UNIMIND_ULR_PROTOTYPE = False
    settings.UNIMIND_DSH_TITLE_ENABLED = settings.UNIMIND_DSH_MEMORY_ENABLED = False
    settings.UNIMIND_DSH_STATE_DIR = str(tmp_path / 'isolated-dsh')
    Path(settings.UNIMIND_DSH_STATE_DIR).mkdir()
    settings.UNIMIND_DSH_FIXTURE_URL = ''
    settings.UNIMIND_CONTENT_INSTITUTION_ID = 'global'
    settings.USE_MEM0 = False
    caplog.set_level('INFO', logger='ai_engine.observability')
    trial = int(os.environ.get('ULR_OFFICIAL_TRIAL', '1'))
    assert trial > 0
    output_key = f'ULR_{case_name.upper()}{"_" + delivery.upper() if delivery else ""}_OFFICIAL_OUTPUT'
    output = Path(os.environ[output_key]) if official else tmp_path / 'capture'
    output.mkdir(mode=0o700)
    config = (get_model_for_task('assistant.chat.planner') if official else
              {'api_key': 'fixture', 'base_url': 'https://example.invalid/chat', 'model': 'capture-fixture-model'})
    if official:
        provider = urlsplit(config['base_url'])
        assert config['api_key'] and (provider.scheme, provider.hostname) == ('https', 'api.deepseek.com')
        assert Path(settings.UNIMIND_DSH_PYTHON).is_absolute() and Path(settings.UNIMIND_DSH_PYTHON).is_file()
        settings.UNIMIND_DSH_API_URL = request.getfixturevalue('live_server').url.replace('localhost', '127.0.0.1')

    def fake_dsh(user, action, *, message, session_id, reservation, on_event, chat_context):
        offered = sample['case']['tool_paths']['dsh']
        if practice or project_case or delivery:
            context = views_dsh.build_context(user, message, chat_context=chat_context)
            offered = [tool['function']['name'] for tool in context['tools']]
        for index, (name, args) in enumerate([*individual, (None, None)], 1):
            if (practice or project_case or delivery) and name:
                assert name in offered
                result = views_dsh.execute_tool(user, name, args, context['memory']['version'],
                    source=reservation, chat_context=chat_context)
                if name == 'search_knowledge_tree':
                    assert [row['id'] for row in result['results']] == [point.pk]
                if name == 'plan_learning_project':
                    assert result['pending_plan']
            log_model_observation({'status': 'completed', 'operation': 'assistant.chat.planner', 'elapsed_ms': 1,
                'model': config['model'], 'reported_model': config['model'], 'max_output_tokens': OUTPUT_LIMIT,
                'request': index, 'offered_tools': offered, 'submitted_tools': [name] if name else [],
                'usage_complete': True, 'usage': {'input_tokens': 50, 'output_tokens': 10}}, reservation)
            if name:
                on_event({'type': 'tool_status', 'call_id': f'scripted-{index}', 'name': name, 'status': 'succeeded'})
        if project_case:
            cards = []
        elif practice or delivery:
            card = result['visual']
            cards = [card]
        else:
            cards = [{'type': 'data_card', 'payload': {'items': [{'action_link': f'/course/{course.pk}?t=60'}]}}]
        return {'finish_reason': 'completed', 'content': reply, 'session': {'id': uuid4().hex,
                'messages': [{'role': 'assistant', 'cards': cards}]}}

    revision = capture_revision(repo)
    records = []
    compile_instruction = ulr_runtime.run_program
    for position, runtime in capture_order(limits, trial):
        limit = limits[runtime]
        dsh = runtime == 'dsh'
        settings.UNIMIND_LEARNING_RUNTIME = 'legacy' if dsh else 'ulr'
        settings.UNIMIND_DSH_ENABLED = settings.UNIMIND_DSH_SITE_ENABLED = settings.UNIMIND_DSH_XIAOYU_ENABLED = dsh
        project = None
        if project_case:
            project = ConversationProject.objects.create(user=user, name='合成折现学习项目')
            initial = source['initial_plan']
            ProjectLearning.objects.create(project=project, planning_enabled=True, status='active',
                plan=initial, current_stage=initial['stages'][0]['id'], next_action=initial['stages'][0]['task'])
        conversation = Conversation.objects.create(user=user, bot=bot, conversation_id=uuid4(), title='合成学习验收', project=project)
        request_id = str(uuid4())
        body = {'bot_id': bot.pk, 'conversation_id': str(conversation.conversation_id),
                'request_id': request_id, 'message': sample['case']['prompt']}
        if direct and not practice:
            body['course_context'] = {'course_id': course.pk, 'video_seconds': source['start_time']}
        course_attempts = []

        def observe_instruction(arguments, *args, **kwargs):
            result = compile_instruction(arguments, *args, **kwargs)
            if kwargs['name'] == 'run_course_tools':
                submitted = 'invalid'
                if isinstance(arguments, dict):
                    submitted = 'automatic' if 'output' not in arguments else 'card' if arguments['output'] == 'card' else 'invalid'
                course_attempts.append({'requested': submitted,
                    'compiled': None if result.get('error') else 'card' if result.get('_ulr_card_only') else 'answer'})
            return result

        with ExitStack() as scope:
            for module in (views_dsh, ulr_runtime):
                scope.enter_context(patch.object(module, 'build_context',
                    partial(bounded_context, module.build_context, limit, config['model'])))
            scope.enter_context(patch('ai_engine.service.get_model_for_task', return_value={**config, 'thinking': False}))
            scope.enter_context(patch('ai_assistant.services.dsh_xiaoyu.extract_memories_async'))
            if runtime == 'ulr_individual':
                scope.enter_context(patch.object(ulr_runtime, 'PROGRAM_OPS', {}))
            if runtime == 'ulr_model_instruction':
                compiler = 'compile_practice_request' if practice else 'compile_current_course_locator'
                scope.enter_context(patch.object(ulr_runtime, compiler, return_value=None))
            if runtime == 'ulr' and delivery and not direct:
                scope.enter_context(patch.object(ulr_runtime, 'run_program', side_effect=observe_instruction))
            if not official:
                scope.enter_context(patch('ai_assistant.services.dsh_xiaoyu.run_site_action', side_effect=fake_dsh))
                response = scripted_provider(individual if runtime in ('dsh', 'ulr_individual') else combined, reply)
                transport = scope.enter_context(patch('ai_engine.service._session.post', return_value=response))
            started = monotonic()
            endpoint = auth_client.post('/api/ai/chat/stream/', body, format='json')
            assert endpoint.status_code == 200
            events = async_to_sync(consume)(endpoint, started)
        if not official and practice and runtime != 'dsh':
            payloads = [call.kwargs['json']['messages'] for call in transport.call_args_list]
            sent = json.dumps(payloads, ensure_ascii=False)
            assert source['stem'] not in sent and source['grading_points'] not in sent
            if runtime == 'ulr_individual':
                assert json.loads(payloads[-1][-1]['content']) == {'question_count': 1, 'card_prepared': True}
            else:
                if direct and runtime == 'ulr':
                    assert not payloads
                else:
                    assert len(payloads) == 1 and payloads[0][-1]['role'] == 'user'
                assert events[-1]['event']['full_content'] == '练习已准备好。'
        tool['write'](output / f'{runtime}-events.json', events)
        reservation = AIUsageReservation.objects.get(request_id=request_id)
        rows = [row.args[4] for row in caplog.records if row.name == 'ai_engine.observability'
                and row.args[4].get('request_id') == request_id and row.args[4].get('max_output_tokens')]
        assert all(row['model'] == config['model'] and int(row['max_output_tokens']) == OUTPUT_LIMIT for row in rows)
        count = sum(int(row.get('attempts', 1)) for row in rows)
        assert count <= limit
        record = tool['capture_turn']({**sample, 'runtime': runtime, 'trial': trial, 'execution_position': position, 'revision': revision,
            'request_id': request_id, 'attempt_id': str(reservation.attempt_id), 'model': config['model'],
            'evidence': 'same_model' if official else 'protocol_smoke', 'metrics': {'model_requests': count}}, events)
        if runtime == 'ulr' and delivery and not direct:
            record['delivery_selection'] = {'expected': sample['case']['expected_delivery'], 'attempts': course_attempts}
        if project_case:
            url = f'/api/ai/projects/{project.pk}/learning/'
            snapshot = auth_client.get(url)
            assert snapshot.status_code == 200
            draft = snapshot.data['pending_plan'].get('plan')
            accepted = None
            if record['completed'] and draft:
                accepted = auth_client.patch(url, {'action': 'accept', 'revision': snapshot.data['revision']}, format='json')
            current = auth_client.get(url)
            assert current.status_code == 200
            record['review']['result'].update(pending_plan=draft, plan_before_confirmation=snapshot.data['plan'],
                confirmation_status=accepted.status_code if accepted is not None else None,
                plan_after_confirmation=current.data['plan'], pending_after_confirmation=bool(current.data['pending_plan']),
                next_action_after_confirmation=current.data['next_action'])
        records.append(record)

    operations = prepare_capture(repo, output, records, caplog, tool, limits.keys() - {'ulr'})
    if not official:
        expected_requests = ([3 if practice else 2, 1, 0] if direct else
            {'course': [4, 4, 2], 'practice': [3, 3, 1], 'project': [3, 3],
             'timestamp': [3, 3, 1], 'explanation': [3, 3, 2]}[delivery or case_name])
        by_runtime = {record['runtime']: record for record in records}
        assert {runtime: row['metrics']['model_requests'] for runtime, row in by_runtime.items()} == dict(
            zip(limits, expected_requests, strict=True))
        for record in records:
            assert record['completed'] and record['metrics']['tool_failures'] == 0
            values = dict.fromkeys(tool['METRICS']) | record['metrics']
            trace = tool['reconcile'](record, values, operations)
            assert tool['tool_quality'](record, trace)['first_pass']
            if direct and record['runtime'] == 'ulr':
                assert trace['local_instruction_verified'] and values['input_tokens'] == values['output_tokens'] == 0
            if record['runtime'] == 'ulr' and not project_case:
                outcome, = record['tool_outcomes']
                assert [outcome['steps_executed']] == sample['case']['tool_steps']['ulr']
                if not delivery:
                    legacy = {**record, 'tool_outcomes': [{key: value for key, value in outcome.items() if key != 'steps_executed'}]}
                    assert tool['tool_quality'](legacy, trace) is None
                    legacy['case'] = {key: value for key, value in record['case'].items() if key != 'tool_steps'}
                    assert tool['tool_quality'](legacy, trace) is None
            if case_name == 'course' and not delivery and record['runtime'] == 'ulr':
                initial = trace['operations'][0]
                assert initial['tool_aliases'] == initial['submitted_tools'] == ['run_course_tools']
                assert 'run_course_tools' not in initial['offered_tools']
            if project_case:
                result = record['review']['result']
                assert result == {'completed': True, 'pending_plan': proposal, 'plan_before_confirmation': initial,
                    'confirmation_status': 200, 'plan_after_confirmation': proposal, 'pending_after_confirmation': False,
                    'next_action_after_confirmation': proposal['stages'][0]['task']}
            elif practice:
                card, = [card for card in record['review']['sources'] if card['type'] == 'practice_quiz']
                selected, = card['payload']['questions']
                assert (selected['id'], selected['text'], selected['options']) == (question.pk, question.text, question.options)
                assert not {'answer', 'correct_answer', 'grading_points', 'rubric'} & selected.keys()
            elif direct:
                links = [item.get('action_link') for card in record['review']['sources']
                         for item in card['payload'].get('items', ())]
                assert links == [f'/course/{course.pk}?t={source["start_time"]}']
            else:
                assert any(item.get('action_link') == f'/course/{course.pk}?t={source["start_time"]}'
                           for card in record['review']['sources'] for item in card['payload'].get('items', ()))
        if practice:
            assert not QuizExam.objects.filter(user=user).exists()
        if delivery and not direct:
            native = by_runtime['ulr']
            expected = sample['case']['expected_delivery']
            requested = 'automatic' if delivery == 'timestamp' else 'card'
            assert native['delivery_selection'] == {'expected': expected,
                'attempts': [{'requested': requested, 'compiled': expected}]}
            assert native['review']['answer'] == ('已找到所选课程的讲稿片段。' if delivery == 'timestamp' else REPLY)
            if delivery == 'timestamp':
                manifest = tool['read'](output / 'dsh' / 'private-key.json')
                review = tool['read'](output / 'dsh' / 'review.json')
                pair, = review['pairs']
                for scores in pair['scores'].values():
                    scores.update(dict.fromkeys(scores, True))
                arm = next(arm for arm in manifest['pairs'][pair['pair_id']]['mapping'].values() if arm['runtime'] == 'ulr')
                arm['tool_quality'] = None
                arm['delivery_selection']['attempts'][-1]['compiled'] = 'answer'
                scenario, = tool['report'](manifest, review)['scenarios'].values()
                location = {'case_id': native['case_id'], 'trial': native['trial']}
                assert scenario['evidence_gaps'] == [{**location, 'tool_paths_without_evidence': ['ulr'],
                                                       'delivery_mode_without_evidence': False}]
                issue, = scenario['quality_issues']
                assert issue['delivery_mode_mismatch'] == {'expected': 'card', 'compiled': 'answer'}
                assert all(issue[key] == value for key, value in location.items())
        baseline = by_runtime['dsh']
        if len(baseline['tool_outcomes']) > 1:
            reversed_path = {**baseline, 'tool_outcomes': list(reversed(baseline['tool_outcomes']))}
            trace = {'operations': list(reversed(operations[baseline['request_id'], baseline['attempt_id']]))}
            assert not tool['tool_quality'](reversed_path, trace)['first_pass']


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize('official', [False, pytest.param(True, marks=pytest.mark.skipif(
    not os.environ.get('ULR_COURSE_OFFICIAL_OUTPUT'), reason='manual, authorized official-provider comparison'))])
def test_capture_course_acceptance(official, auth_client, user, settings, request, tmp_path, caplog):
    capture_acceptance('course', official, auth_client, user, settings, request, tmp_path, caplog)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize('delivery', ['timestamp', 'explanation'])
@pytest.mark.parametrize('official', [False, True])
def test_capture_course_delivery_acceptance(official, delivery, auth_client, user, settings, request, tmp_path, caplog):
    if official and not os.environ.get(f'ULR_COURSE_{delivery.upper()}_OFFICIAL_OUTPUT'):
        pytest.skip('manual, authorized official-provider comparison')
    capture_acceptance('course', official, auth_client, user, settings, request, tmp_path, caplog, delivery=delivery)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize('case_name', ['course', 'practice'])
@pytest.mark.parametrize('official', [False, True])
def test_capture_direct_instruction_acceptance(official, case_name, auth_client, user, settings, request, tmp_path, caplog):
    if official and not os.environ.get(f'ULR_{case_name.upper()}_DIRECT_OFFICIAL_OUTPUT'):
        pytest.skip('manual, authorized official-provider comparison')
    capture_acceptance(case_name, official, auth_client, user, settings, request, tmp_path, caplog, delivery='direct')


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize('official', [False, pytest.param(True, marks=pytest.mark.skipif(
    not os.environ.get('ULR_PRACTICE_OFFICIAL_OUTPUT'), reason='manual, authorized official-provider comparison'))])
def test_capture_practice_acceptance(official, auth_client, user, settings, request, tmp_path, caplog):
    capture_acceptance('practice', official, auth_client, user, settings, request, tmp_path, caplog)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize('official', [False, pytest.param(True, marks=pytest.mark.skipif(
    not os.environ.get('ULR_PROJECT_OFFICIAL_OUTPUT'), reason='manual, authorized official-provider comparison'))])
def test_capture_project_acceptance(official, auth_client, user, settings, request, tmp_path, caplog):
    capture_acceptance('project', official, auth_client, user, settings, request, tmp_path, caplog)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize('official', [False, pytest.param(True, marks=pytest.mark.skipif(
    not os.environ.get('ULR_GRADING_OFFICIAL_OUTPUT'), reason='manual, authorized official-provider comparison'))])
def test_capture_grading_acceptance(official, auth_client, user, settings, tmp_path, caplog):
    repo = Path(settings.BASE_DIR).parent
    tool = run_path(str(repo / 'scripts/ulr_review_pairs.py'))
    sample_path = repo / 'scripts/fixtures/ulr_grading_review.json'
    sample = tool['read'](sample_path)
    source = sample['case']['fixture']
    operation, collector = 'quizzes.grade_question', 'submit_grading_result'
    config = structured_capture_config(settings, official, tmp_path / 'grading-dsh', operation)
    CourseStudentStatus.objects.create(user=user, is_course_student=True)
    question = Question.objects.create(text=sample['case']['prompt'], q_type='subjective', subjective_type='short',
        correct_answer=source['reference_answer'], grading_points=source['grading_points'])
    trial = int(os.environ.get('ULR_OFFICIAL_TRIAL', '1'))
    assert trial > 0
    output = Path(os.environ['ULR_GRADING_OFFICIAL_OUTPUT']) if official else tmp_path / 'capture'
    output.mkdir(mode=0o700)
    caplog.set_level('INFO', logger='ai_engine.observability')
    expected = {'score': 6, 'feedback': '判断方向正确，缺少折现公式中的分母变化。',
                'analysis': source['reference_answer'], 'memorix_rating': 2, 'error_analysis': None}
    revision = capture_revision(repo)
    records = []
    attempts = {}
    for position, runtime in capture_order(('dsh', 'ulr'), trial):
        settings.UNIMIND_LEARNING_RUNTIME = 'legacy' if runtime == 'dsh' else 'ulr'
        settings.UNIMIND_DSH_GRADING_ENABLED = runtime == 'dsh'
        body = {'submission_id': str(uuid4()), 'answers': [{'question_id': question.pk, 'answer': source['answer']}]}
        with ExitStack() as scope:
            scope.enter_context(patch('quizzes.views_exam.dispatch_exam_grading'))
            scope.enter_context(patch('quizzes.ai_workflow.observe_background', side_effect=partial(capture_attempt, attempts)))
            for path in ('ai_engine.service.get_model_for_task', 'ai_assistant.services.dsh_tasks.get_model_for_task'):
                scope.enter_context(patch(path, return_value={**config, 'thinking': False}))
            if not official:
                popen, worker, transport = scripted_structured_provider(scope, config['model'], operation, collector, 2500, expected)
            started = monotonic()
            submission = auth_client.post('/api/quizzes/submit-exam/', body, format='json')
            assert submission.status_code == 202, submission.data
            exam_id = submission.data['exam_id']
            run_exam_grading(user.pk, exam_id)
            result = auth_client.get(f'/api/quizzes/exams/{exam_id}/')
            elapsed = round((monotonic() - started) * 1000)
            assert result.status_code == 200, result.data
            replay = auth_client.post('/api/quizzes/submit-exam/', body, format='json')
            assert replay.status_code == 202 and replay.data['exam_id'] == exam_id
            if result.data['status'] == 'completed':
                run_exam_grading(user.pk, exam_id)
                recovered = auth_client.get(f'/api/quizzes/exams/{exam_id}/')
                assert recovered.status_code == 200 and recovered.data['results'] == result.data['results']
            if not official:
                if runtime == 'dsh':
                    popen.assert_called_once()
                    transport.assert_not_called()
                    sent = json.loads(worker.communicate.call_args.args[0])['prompt']
                else:
                    transport.assert_called_once()
                    popen.assert_not_called()
                    sent = json.dumps(transport.call_args.kwargs['json']['messages'], ensure_ascii=False)
                assert all(value in sent for value in (question.text, source['answer'], source['grading_points']))
        item, = result.data['results']
        assert item['user_answer'] == source['answer']
        request_id = f'exam:{exam_id}'
        rows = [row.args[4] for row in caplog.records if row.name == 'ai_engine.observability'
                and row.args[4].get('request_id') == request_id and row.args[4].get('max_output_tokens')]
        attempt_id, = attempts[request_id]
        assert all(row['attempt_id'] == attempt_id for row in rows)
        assert all(row['model'] == config['model'] and int(row['max_output_tokens']) == 2500 for row in rows)
        requests = sum(int(row.get('attempts', 1)) for row in rows)
        assert requests <= 2
        completed = result.data['status'] == 'completed'
        snapshot = {key: item[key] for key in ('user_answer', 'score', 'max_score', 'status', 'label_source', 'analysis')}
        snapshot['same_exam_on_replay'] = True
        tool['write'](output / f'{runtime}-exam.json', {'id': exam_id, 'feedback': item['feedback'], **snapshot})
        records.append({**sample, 'runtime': runtime, 'trial': trial, 'execution_position': position, 'revision': revision,
            'request_id': request_id, 'attempt_id': attempt_id, 'model': config['model'],
            'evidence': 'same_model' if official else 'protocol_smoke', 'completed': completed,
            'review': {'answer': item['feedback'], 'sources': [], 'result': snapshot},
            'metrics': {'model_requests': requests, 'completion_ms': elapsed if completed else None}})
    prepare_capture(repo, output, records, caplog, tool, ('dsh',))
    if not official:
        assert all(row['completed'] and row['metrics']['model_requests'] == 1 for row in records)
        assert records[0]['review'] == records[1]['review']
        result = records[1]['review']['result']
        assert (result['score'], result['max_score'], result['label_source']) == (6, 10, 'model_rubric_grade')


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize('official', [False, pytest.param(True, marks=pytest.mark.skipif(
    not os.environ.get('ULR_MEMORY_OFFICIAL_OUTPUT'), reason='manual, authorized official-provider comparison'))])
def test_capture_memory_acceptance(official, auth_client, user, settings, tmp_path, caplog, monkeypatch):
    repo = Path(settings.BASE_DIR).parent
    tool = run_path(str(repo / 'scripts/ulr_review_pairs.py'))
    sample_path = repo / 'scripts/fixtures/ulr_memory_review.json'
    sample = tool['read'](sample_path)
    source = sample['case']['fixture']
    operation, collector = 'assistant.memory_extract', 'submit_memories'
    config = structured_capture_config(settings, official, tmp_path / 'memory-dsh', operation)
    monkeypatch.setenv('AI_MODEL_FAST', config['model'])
    settings.UNIMIND_DSH_MEMORY_ENABLED = True
    settings.USE_MEM0 = False
    CourseStudentStatus.objects.create(user=user, is_course_student=True)
    bot, _ = Bot.objects.get_or_create(is_xiaoyu=True, defaults={'name': '小宇'})
    trial = int(os.environ.get('ULR_OFFICIAL_TRIAL', '1'))
    assert trial > 0
    output = Path(os.environ['ULR_MEMORY_OFFICIAL_OUTPUT']) if official else tmp_path / 'capture'
    output.mkdir(mode=0o700)
    caplog.set_level('INFO', logger='ai_engine.observability')
    candidate = {'memory_type': 'preference', 'key': '讲解方式', 'value': '只举例，不给公式。',
                 'evidence': source['evidence'], 'confidence': 0.92}
    scripted = {'memories': [candidate, {**candidate, 'key': '助手自述', 'evidence': source['answer']}]}
    revision = capture_revision(repo)
    fields = ('memory_type', 'key', 'value', 'evidence')
    rows = AgentMemory.objects.filter(user=user)
    records, attempts = [], {}
    for position, runtime in capture_order(('dsh', 'ulr'), trial):
        native = runtime == 'ulr'
        settings.UNIMIND_LEARNING_RUNTIME = 'ulr' if native else 'legacy'
        assert not rows.exists()
        conversation = Conversation.objects.create(user=user, bot=bot, conversation_id=uuid4(), title='合成长期记忆')
        turn = {'user': user, 'bot': bot, 'conversation_id': conversation.conversation_id}
        question = AIChatMessage.objects.create(**turn, role='user', content=sample['case']['prompt'])
        answer = AIChatMessage.objects.create(**turn, role='assistant', content=source['answer'],
            metadata={'learning_turn': {'message_id': question.pk, 'completed': True}})
        request_id = f'memory:{conversation.conversation_id}'

        def extract():
            memory_service.extract_memories_async(user, [{'role': 'user', 'content': question.content}],
                conversation.conversation_id, source_message_id=question.pk, answer_message_id=answer.pk)
            if native:
                job = PendingMemoryExtraction.objects.get(answer_message_id=answer.pk)
                ulr_memory.extract_pending_memory(job.pk, question.pk, answer.pk)

        def available_values():
            return [item['value'] for item in build_context(user, source['followup'], ulr=native)['memory']['items']]

        with ExitStack() as scope:
            for module in (memory_service, ulr_memory):
                scope.enter_context(patch.object(module, 'observe_background', side_effect=partial(capture_attempt, attempts)))
            inline = scope.enter_context(patch('ai_assistant.utils._THREAD_POOL.submit'))
            inline.side_effect = lambda func, *args, **kwargs: func(*args, **kwargs)
            scope.enter_context(patch('ai_assistant.tasks.extract_memory_turn.apply_async'))
            for path in ('ai_engine.service.get_model_for_task', 'ai_assistant.services.dsh_tasks.get_model_for_task'):
                scope.enter_context(patch(path, return_value={**config, 'thinking': False}))
            if not official:
                popen, worker, transport = scripted_structured_provider(scope, config['model'], operation, collector, 800, scripted)
            started = monotonic()
            extract()
            persisted = list(rows.order_by('key').values(*fields))
            available = available_values()
            elapsed = round((monotonic() - started) * 1000)
            settled = MemoryExtractionLog.objects.filter(user=user, conversation_id=conversation.conversation_id).exists()
            for pk in rows.values_list('pk', flat=True):
                assert auth_client.delete(f'/api/ai/memories/{pk}/').status_code == 204
            withdrawn = available_values()
            if settled:
                extract()
            replayed = available_values()
            if not official:
                (transport if native else popen).assert_called_once()
                (popen if native else transport).assert_not_called()
                if native:
                    request = transport.call_args.kwargs['json']
                    assert (request['model'], request['max_completion_tokens']) == (config['model'], 800)
                    prompt = json.dumps(request['messages'], ensure_ascii=False)
                else:
                    request = json.loads(worker.communicate.call_args.args[0])
                    policy = request['context']['model_policy']
                    assert (policy['model'], policy['max_tokens']) == (config['model'], 800)
                    prompt = request['prompt']
                assert question.content in prompt and answer.content not in prompt
        attempt_id, = attempts[request_id]
        logs = [row.args[4] for row in caplog.records if row.name == 'ai_engine.observability'
                and row.args[4].get('request_id') == request_id and row.args[4].get('max_output_tokens')]
        assert all(row['attempt_id'] == attempt_id and row['model'] == config['model']
                   and int(row['max_output_tokens']) == 800 and row['source_message_id'] == str(question.pk)
                   and row['answer_message_id'] == str(answer.pk) for row in logs)
        snapshot = {'memories': persisted, 'available_before_withdrawal': available,
                    'available_after_withdrawal': withdrawn, 'available_after_replay': replayed}
        tool['write'](output / f'{runtime}-memory.json', {'source_message_id': question.pk, 'answer_message_id': answer.pk, **snapshot})
        records.append({**sample, 'runtime': runtime, 'trial': trial, 'execution_position': position, 'revision': revision,
            'request_id': request_id, 'attempt_id': attempt_id, 'model': config['model'],
            'evidence': 'same_model' if official else 'protocol_smoke', 'completed': settled,
            'review': {'answer': '', 'sources': [], 'result': snapshot},
            'metrics': {'model_requests': sum(int(row.get('attempts', 1)) for row in logs),
                        'completion_ms': elapsed if settled else None}})
    prepare_capture(repo, output, records, caplog, tool, ('dsh',))
    if not official:
        for record in records:
            value = candidate['value'] if record['runtime'] == 'dsh' else source['evidence']
            assert record['completed'] and record['metrics']['model_requests'] == 1
            assert record['review']['result'] == {'memories': [{**{key: candidate[key] for key in fields}, 'value': value}],
                'available_before_withdrawal': [value], 'available_after_withdrawal': [], 'available_after_replay': []}


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize('official', [False, pytest.param(True, marks=pytest.mark.skipif(
    not os.environ.get('ULR_TEACHING_PARSE_OFFICIAL_OUTPUT'), reason='manual, authorized official-provider comparison'))])
def test_capture_teaching_parse_acceptance(official, auth_client, admin_user, django_user_model, settings, tmp_path, caplog, monkeypatch):
    repo = Path(settings.BASE_DIR).parent
    tool = run_path(str(repo / 'scripts/ulr_review_pairs.py'))
    sample_path = repo / 'scripts/fixtures/ulr_teaching_parse_review.json'
    sample = tool['read'](sample_path)
    source = sample['case']['fixture']
    operation, collector = 'quizzes.preview_parse', 'submit_questions'
    config = structured_capture_config(settings, official, tmp_path / 'teaching-dsh', f'ulr.{operation}')
    monkeypatch.setenv('AI_MODEL_FAST', config['model'])
    operator = str(uuid4())
    second_admin = django_user_model.objects.create_superuser(username='synthetic-teaching-fallback')
    settings.UNIMIND_DIRECTUS_ADMIN_MAP = {operator: admin_user.pk, str(uuid4()): second_admin.pk}
    auth_client.force_authenticate(admin_user, token=operator)
    point = KnowledgePoint.objects.create(name=source['knowledge_point'], level='kp')
    trial = int(os.environ.get('ULR_OFFICIAL_TRIAL', '1'))
    assert trial > 0
    output = Path(os.environ['ULR_TEACHING_PARSE_OFFICIAL_OUTPUT']) if official else tmp_path / 'capture'
    output.mkdir(mode=0o700)
    caplog.set_level('INFO', logger='ai_engine.observability')
    revision = capture_revision(repo)
    task_api = '/api/backoffice/operations/'
    chosen, incomplete = source['questions']
    chosen_options = normalize_options(chosen['options'])
    scripted = {'questions': [{**chosen, 'options': [f'{key}. {value}' for key, value in chosen_options.items() if value]},
                              incomplete]}
    records, attempts = [], {}
    for position, runtime in capture_order(('dsh', 'ulr'), trial):
        native = runtime == 'ulr'
        settings.UNIMIND_LEARNING_RUNTIME = 'ulr' if native else 'legacy'
        settings.UNIMIND_DSH_TEACHING_ENABLED = not native
        before_ids = set(Question.objects.values_list('pk', flat=True))
        material = sample['case']['reference']
        with ExitStack() as scope:
            dispatch = scope.enter_context(patch('backoffice.tasks.run_teaching_task.delay'))
            scope.enter_context(patch('backoffice.tasks.observe_background', side_effect=partial(capture_attempt, attempts)))
            for path in ('ai_engine.service.get_model_for_task', 'ai_assistant.services.dsh_tasks.get_model_for_task'):
                scope.enter_context(patch(path, return_value={**config, 'thinking': False}))
            if not official:
                popen, worker, transport = scripted_structured_provider(
                    scope, config['model'], operation, collector, 3200, scripted)
            started = monotonic()
            launched = auth_client.post(task_api + 'teaching.generate/', {'kind': 'parse', 'kp_ids': [point.pk],
                'raw_text': material, 'request_id': str(uuid4())}, format='json')
            assert launched.status_code == 200, launched.data
            task_id = launched.data['id']
            dispatch.assert_called_once_with(task_id)
            run_teaching_task(task_id)
            request_id = f'teaching:{task_id}'
            attempt_id, = attempts[request_id]
            preview = auth_client.post(task_api + 'pipeline.detail/', {'id': task_id}, format='json')
            elapsed = round((monotonic() - started) * 1000)
            assert preview.status_code == 200, preview.data
            if preview.data['status'] == 'review':
                run_teaching_task(task_id)
            if not official:
                (transport if native else popen).assert_called_once()
                (popen if native else transport).assert_not_called()
                if native:
                    request = transport.call_args.kwargs['json']
                    assert (request['model'], request['max_completion_tokens']) == (config['model'], 3200)
                    prompt = '\n'.join(message['content'] for message in request['messages'])
                else:
                    request = json.loads(worker.communicate.call_args.args[0])
                    policy = request['context']['model_policy']
                    assert (policy['model'], policy['max_tokens']) == (config['model'], 3200)
                    prompt = request['prompt']
                assert material in prompt
        drafts = (preview.data['result'] or {}).get('questions', [])
        draft_fields = ('question', 'q_type', 'subjective_type', 'options', 'answer', 'grading_points', 'kp_name')
        bank = Question.objects.exclude(pk__in=before_ids)
        before_confirmation = bank.count()
        matches = [index for index, draft in enumerate(drafts) if draft['kp_id'] == point.pk
            and draft['q_type'] == 'objective' and draft['question'] == chosen['question']
            and len(draft['options']) == len(chosen['options'])
            and normalize_options(draft['options']) == chosen_options
            and normalize_objective_answer(draft['answer'], chosen_options) == chosen['answer']]
        first_review = second_review = None
        completed = preview.data['status'] == 'review'
        if completed and len(matches) == 1:
            approval = {'id': task_id, 'action': 'approve', 'question_indices': matches, 'confirmed': True, 'request_id': str(uuid4())}
            first_review = auth_client.post(task_api + 'pipeline.review/', approval, format='json')
            second_review = auth_client.post(task_api + 'pipeline.review/', {**approval, 'request_id': str(uuid4())}, format='json')
        rows = [row.args[4] for row in caplog.records if row.name == 'ai_engine.observability'
                and row.args[4].get('request_id') == request_id and row.args[4].get('max_output_tokens')]
        assert all(row['attempt_id'] == attempt_id and row['model'] == config['model']
                   and int(row['max_output_tokens']) == 3200 for row in rows)
        snapshot = {'drafts': [{key: draft[key] for key in draft_fields} for draft in drafts],
            'bank_added_before_confirmation': before_confirmation,
            'confirmation_status': first_review.status_code if first_review is not None else None,
            'repeated_confirmation_status': second_review.status_code if second_review is not None else None,
            'bank_after_confirmation': list(bank.order_by('pk').values('text', 'options', 'correct_answer'))}
        tool['write'](output / f'{runtime}-task.json', {'id': task_id, 'status': preview.data['status'], **snapshot})
        records.append({**sample, 'runtime': runtime, 'trial': trial, 'execution_position': position, 'revision': revision,
            'request_id': request_id, 'attempt_id': attempt_id, 'model': config['model'],
            'evidence': 'same_model' if official else 'protocol_smoke', 'completed': completed,
            'review': {'answer': '', 'sources': [], 'result': snapshot},
            'metrics': {'model_requests': sum(int(row.get('attempts', 1)) for row in rows),
                        'completion_ms': elapsed if completed else None}})
    prepare_capture(repo, output, records, caplog, tool, ('dsh',))
    if not official:
        assert all(record['completed'] and record['metrics']['model_requests'] == 1 for record in records)
        assert records[0]['review'] == records[1]['review']
        result = records[1]['review']['result']
        assert [draft['question'] for draft in result['drafts']] == [chosen['question'], incomplete['question']]
        assert result['drafts'][1]['answer'] == result['drafts'][1]['grading_points'] == ''
        assert result['bank_added_before_confirmation'] == 0
        assert result['confirmation_status'] == result['repeated_confirmation_status'] == 200
        published, = result['bank_after_confirmation']
        assert published['text'] == chosen['question'] and published['correct_answer'] == chosen['answer']
        assert published['options'] == scripted['questions'][0]['options']
