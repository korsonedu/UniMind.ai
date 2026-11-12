"""Owner-scoped G/E shadow comparisons. Nothing here activates a teaching policy."""
import json
import math
import time
from pathlib import Path
from uuid import UUID

from django.conf import settings
from rest_framework.exceptions import PermissionDenied, ValidationError

from ai_assistant.models import ConversationProject, ProjectLearningTask, TeachingResearchRun
from users.feature_access import has_learning_feature
from .teaching_sidecar import canonical_hash, current_bundle, register_mechanism

OPERATION = 'assistant.chat.planner.rsi_shadow'
CASE_FIELDS = {'id', 'domain', 'prompt', 'response', 'criteria', 'assistance', 'teacher_help', 'task_id'}
SCORE_SCHEMA = {'type': 'object', 'properties': {
    'score': {'type': 'number', 'minimum': 0, 'maximum': 1},
    'independent_support': {'type': 'boolean'}, 'reason': {'type': 'string', 'maxLength': 2000}},
    'required': ['score', 'independent_support', 'reason'], 'additionalProperties': False}
METHOD_SCHEMA = {'type': 'object', 'properties': {
    'method': {'type': 'string', 'minLength': 1, 'maxLength': 6000},
    'covered_subskills': {'type': 'array', 'items': {'type': 'string'}, 'maxItems': 12},
    'independent_check': {'type': 'string', 'minLength': 1, 'maxLength': 2000}},
    'required': ['method', 'covered_subskills', 'independent_check'], 'additionalProperties': False}


def _check(condition, message):
    if not condition:
        raise ValidationError(message)


def _instruction(value):
    _check(isinstance(value, dict) and set(value) == {'instruction'}, '制品只允许 instruction 字段。')
    text = value['instruction']
    _check(isinstance(text, str) and 1 <= len(text) <= 8000, 'instruction 长度须为1至8000字符。')
    return {'instruction': text}


def _authorize(project):
    current = ConversationProject.objects.select_related('user').filter(pk=project.pk, user_id=project.user_id).first()
    if not current or not has_learning_feature(current.user, 'ai.assistant'):
        raise PermissionDenied('项目所有者当前无权使用小宇。')
    return current


def _cases(project, packet):
    rows = packet['cases']
    _check(isinstance(rows, list) and 1 <= len(rows) <= 6, '每轮只接受1至6个冻结案例。')
    cases, ids, task_ids, result_ids = [], set(), set(), set()
    for row in rows:
        _check(isinstance(row, dict) and not set(row) - CASE_FIELDS, '案例含未允许字段；锚点必须独立存放。')
        key = row.get('id')
        _check(isinstance(key, str) and 1 <= len(key) <= 80 and key not in ids, '案例编号缺失或重复。')
        ids.add(key)
        if packet['provenance']['origin'] == 'observational':
            _check(set(row) <= {'id', 'task_id'}, '实际案例只能引用本人任务，不接受替换的作答或标准。')
            try:
                task_id = UUID(str(row.get('task_id')))
            except (ValueError, TypeError) as exc:
                raise ValidationError('案例需要有效的本人任务编号。') from exc
            _check(task_id not in task_ids, '同一任务不能换编号重复计为多个案例。')
            task_ids.add(task_id)
            task = ProjectLearningTask.objects.select_related('project', 'exam').filter(pk=task_id, project=project).first()
            _check(task is not None and task.exam_id is not None, '本人已提交任务不可用。')
            from .learning_tasks import task_result_snapshot, task_label_source, task_prompt_hash
            from quizzes.models import ExamQuestionResult
            results = list(task.exam.results.filter(status='graded').select_related('exam', 'question'))
            _check(bool(results), '任务尚无可核验成果。')
            material = {'id': key, 'task_id': str(task.pk), 'goal': task.title,
                        'assistance': task.assistance, 'assistance_source': 'submission_report',
                        'teacher_help': 'unknown', 'actual_exposure': {'status': 'unknown', 'adherence': 'unverified'},
                        'results': []}
            if task.strategy_use_id:
                from .teaching_sidecar import validate_strategy_use
                from ai_assistant.models import AIChatMessage
                use = validate_strategy_use(project, task.strategy_use_id)
                reply = AIChatMessage.objects.filter(pk=use.exposure.get('reply_id'), user=project.user,
                    conversation_id=use.message.conversation_id, bot_id=use.message.bot_id, role='assistant',
                    metadata__learning_turn__message_id=use.message_id, metadata__learning_turn__completed=True).first()
                if reply and use.exposure.get('reply_hash') == canonical_hash(reply.content):
                    material['actual_exposure'] = {'status': 'completed_reply_observed', 'adherence': 'unverified',
                                                   'use_id': use.pk, 'reply_id': reply.pk}
                    material['teacher_help'] = reply.content
            for result in results:
                _check(result.pk not in result_ids, '同一作答结果不能重复计入案例。')
                result_ids.add(result.pk)
                snapshot = task_result_snapshot(task, result)
                prior = ExamQuestionResult.objects.filter(exam__user_id=project.user_id,
                    exam__created_at__lt=result.exam.created_at).exclude(pk=result.pk).values('question_id', 'question_snapshot')
                repeated = any((result.question_id is not None and item['question_id'] == result.question_id)
                    or (item['question_snapshot'].get('text')
                        and task_prompt_hash(item['question_snapshot']) == task_prompt_hash(snapshot)) for item in prior)
                material['results'].append({'result_id': result.pk, 'prompt': snapshot['text'],
                    'response': result.user_answer, 'options': snapshot.get('options', []),
                    'q_type': snapshot.get('q_type', ''), 'subjective_type': snapshot.get('subjective_type', ''),
                    'correct_answer': snapshot.get('correct_answer', ''),
                    'reference_explanation': snapshot.get('ai_answer', ''),
                    'criteria': task.definition.get('criteria', []) if task.definition else snapshot.get('rubric', {}),
                    'reference_answer': task.definition.get('reference_answer', '') if task.definition else snapshot.get('correct_answer', ''),
                    'rubric': snapshot.get('rubric', {}), 'grading_points': snapshot.get('grading_points', ''),
                    'max_score': snapshot.get('max_score'), 'original_label_source': task_label_source(task, result),
                    'repetition': 'observed_repeat' if repeated else 'not_seen_in_available_history',
                    'novelty_verified': False})
        else:
            _check('task_id' not in row, '合成案例不能引用实际任务。')
            _check(isinstance(row.get('prompt'), str) and 1 <= len(row['prompt']) <= 8000, '案例需要明确 prompt。')
            _check(isinstance(row.get('criteria'), list) and 1 <= len(row['criteria']) <= 8
                   and all(isinstance(item, str) and len(item) <= 1000 for item in row['criteria']), '案例需要冻结标准。')
            _check(all(isinstance(row.get(key, ''), str) and len(row.get(key, '')) <= 8000
                       for key in ('response', 'teacher_help', 'domain')), '案例文本超出范围。')
            _check(row.get('assistance', 'unknown') in ('unknown', 'independent', 'hint', 'guided'), '帮助条件无效。')
            material = dict(row)
        cases.append(material)
    return cases


def _validate_packet(project, kind, packet, live):
    allowed = {'schema_version', 'provenance', 'development', 'cases', 'baseline', 'fixture_candidate',
               'fixture_outputs', 'budget', 'anchors', 'protocol'}
    _check(isinstance(packet, dict) and not set(packet) - allowed, '研究材料含未知字段。')
    _check(packet.get('schema_version') == 'rsi-shadow-1' and kind in ('G', 'E'), '研究材料版本或机制类型无效。')
    provenance = packet.get('provenance', {})
    _check(isinstance(provenance, dict) and not set(provenance) - {'origin', 'split_note'}
           and provenance.get('origin') in ('synthetic', 'observational'), '须声明合成或实际材料来源。')
    development = packet.get('development')
    _check(isinstance(development, dict) and set(development) <= {'goal', 'failure', 'teacher_help', 'limitations'}
           and isinstance(development.get('goal'), str)
           and all(isinstance(value, str) and len(value) <= 8000 for value in development.values()), '开发材料字段无效。')
    _instruction(packet.get('baseline'))
    if not live:
        _check(provenance['origin'] == 'synthetic', 'fixture 模式只允许明确的合成材料。')
        _instruction(packet.get('fixture_candidate'))
    budget = packet.get('budget', {})
    _check(isinstance(budget, dict) and set(budget) == {'max_tokens_per_call', 'max_calls_per_arm'}, '须明确相同的两臂预算上限。')
    _check(type(budget['max_tokens_per_call']) is int and 128 <= budget['max_tokens_per_call'] <= 4096
           and type(budget['max_calls_per_arm']) is int and 1 <= budget['max_calls_per_arm'] <= 20, '预算超出影子研究范围。')
    anchors = packet.get('anchors', [])
    _check(isinstance(anchors, list), 'anchors 须为独立列表。')
    _check(kind == 'E' or not anchors, '作答分数锚点只适用于E，不能用于G的方法质量比较。')
    _check(isinstance(packet.get('protocol', {}), dict) and not set(packet.get('protocol', {})) - {'note'}, 'protocol 只接受研究说明，不接受生效或晋级参数。')
    cases = _cases(project, packet)
    seen = set()
    for anchor in anchors:
        _check(isinstance(anchor, dict) and {'case_id', 'expected_score', 'source'} <= set(anchor)
               and not set(anchor) - {'case_id', 'expected_score', 'source', 'expected_independent_support'}
               and anchor['case_id'] in {case['id'] for case in cases} and anchor['case_id'] not in seen, '锚点编号无效或重复。')
        seen.add(anchor['case_id'])
        _check('expected_independent_support' not in anchor or type(anchor['expected_independent_support']) is bool,
               '独立支持锚点必须是明确布尔值。')
        _check(type(anchor['expected_score']) in (int, float) and math.isfinite(anchor['expected_score'])
               and 0 <= anchor['expected_score'] <= 1 and isinstance(anchor['source'], str)
               and 1 <= len(anchor['source']) <= 1000, '锚点需要有限分数和来源。')
    return cases


def _template(name):
    return (Path(settings.BASE_DIR) / 'prompts/ai_assistant/bots/xiaoyu' / name).read_text()


def _call_model(system, material, schema, max_tokens):
    """Return observed usage; adapter retries/DSH usage may remain unknown."""
    from ai_engine.service import AIEngine
    from jsonschema import validate
    response = AIEngine.call_ai([{'role': 'system', 'content': system},
        {'role': 'user', 'content': json.dumps(material, ensure_ascii=False)}], temperature=.2,
        max_tokens=max_tokens, raise_on_error=True, operation=OPERATION,
        _response_format={'type': 'json_object'})
    content = response['choices'][0]['message']['content'].strip()
    if content.startswith('```'):
        content = content.split('\n', 1)[1].rsplit('```', 1)[0]
    output = json.loads(content)
    validate(output, schema)
    return output, {'usage': response.get('usage'), 'observed_model': response.get('model')}


def run_shadow(project, kind, packet, *, live_model=False):
    """Explicit operator run; no implicit production scan or policy activation."""
    project = _authorize(project)
    from .dsh_generation import enabled
    dsh_adapter = enabled(OPERATION)
    if live_model and dsh_adapter and getattr(settings, 'UNIMIND_DSH_FIXTURE_URL', ''):
        raise ValidationError('DSH协议模拟不能标记为真实模型研究。')
    cases = _validate_packet(project, kind, packet, live_model)
    from ai_engine.config import get_model_for_task
    config = get_model_for_task(OPERATION)
    limits = packet['budget']
    calls, outputs = [], {'baseline': {}, 'candidate': {}}
    spent = {'baseline': 0, 'candidate': 0}

    def invoke(arm, purpose, system, material, schema, case_id=None):
        if spent[arm] >= limits['max_calls_per_arm']:
            calls.append({'arm': arm, 'purpose': purpose, 'case_id': case_id, 'status': 'budget_exhausted'})
            return None
        spent[arm] += 1
        record = {'arm': arm, 'purpose': purpose, 'case_id': case_id, 'input_hash': canonical_hash(material),
                  'system_hash': canonical_hash(system), 'status': 'failed', 'usage': None}
        started = time.monotonic()
        try:
            if live_model:
                output, observed = _call_model(system, material, schema, limits['max_tokens_per_call'])
                usage = observed.get('usage')
                valid_usage = isinstance(usage, dict) and all(type(usage.get(key)) is int and usage[key] >= 0
                    for key in ('prompt_tokens', 'completion_tokens', 'total_tokens'))
                record['usage'] = usage if valid_usage else None
                record['observed_model'] = observed.get('observed_model')
            else:
                from jsonschema import validate
                output = packet.get('fixture_outputs', {}).get(arm, {}).get(case_id, {}).get(purpose)
                validate(output, schema)
            if 'score' in output and not math.isfinite(output['score']):
                raise ValidationError('模型分数必须有限。')
            record['status'] = 'completed'
            return output
        except Exception as exc:
            # Provider exceptions can include request details. Persist class, never raw credentials/URL.
            record['error_type'] = type(exc).__name__
            return None
        finally:
            record['elapsed_ms'] = round((time.monotonic() - started) * 1000)
            calls.append(record)

    bundle = current_bundle()
    from ai_assistant.models import TeachingMechanismVersion
    ancestor = TeachingMechanismVersion.objects.get(pk=bundle[kind]['id'])
    baseline = register_mechanism(kind, {'instruction': packet['baseline']['instruction'],
        'scope': 'operator_supplied_shadow_seed'}, owner=project.user, parent=ancestor)
    candidate_instruction = None
    if live_model:
        proposal = invoke('candidate', 'proposal', _template('rsi_propose.txt'),
            {'kind': kind, 'baseline': packet['baseline'], 'development': packet['development']},
            {'type': 'object', 'properties': {'instruction': {'type': 'string', 'minLength': 1, 'maxLength': 8000}},
             'required': ['instruction'], 'additionalProperties': False})
        if proposal:
            candidate_instruction = proposal['instruction']
    else:
        candidate_instruction = packet['fixture_candidate']['instruction']
    candidate = register_mechanism(kind, {'instruction': candidate_instruction, 'scope': 'shadow_candidate',
        'development_hash': canonical_hash(packet['development'])}, owner=project.user, parent=baseline) if candidate_instruction else None
    instructions = {'baseline': packet['baseline']['instruction'], 'candidate': candidate_instruction}
    for case in cases:
        for arm in ('baseline', 'candidate'):
            if instructions[arm] is None:
                continue
            material = case
            if kind == 'G':
                generated = invoke(arm, 'generate', _template('rsi_generate.txt') + '\n' + instructions[arm], case, METHOD_SCHEMA, case['id'])
                if generated is None:
                    continue
                material = {'case': case, 'method': generated}
                outputs[arm][case['id']] = {'generated': generated}
                evaluator = _template('rsi_evaluate_method.txt')
            else:
                evaluator = _template('rsi_evaluate_answer.txt') + '\n' + instructions[arm]
            evaluation = invoke(arm, 'evaluate', evaluator, material, SCORE_SCHEMA, case['id'])
            outputs[arm].setdefault(case['id'], {})['evaluation'] = evaluation

    # Re-resolve references and current permissions before persisting/exporting results.
    project = _authorize(project)
    _cases(project, packet)
    labels = {item['case_id']: item['expected_score'] for item in packet.get('anchors', [])}
    support_labels = {item['case_id']: item['expected_independent_support'] for item in packet.get('anchors', [])
                      if 'expected_independent_support' in item}
    metrics = {}
    for arm in ('baseline', 'candidate'):
        scored = [(key, item['evaluation']['score']) for key, item in outputs[arm].items() if item.get('evaluation')]
        errors = [abs(score - labels[key]) for key, score in scored if key in labels]
        metrics[arm] = {'completed_cases': len(scored), 'proxy_mean': sum(score for _, score in scored) / len(scored) if scored else None,
            'operator_anchor_mae': sum(errors) / len(errors) if errors else None, 'operator_anchor_count': len(errors),
            'operator_false_independent_support': sum(item['evaluation']['independent_support'] and not support_labels[key]
                for key, item in outputs[arm].items() if item.get('evaluation') and key in support_labels),
            'operator_support_anchor_count': sum(key in support_labels for key, _ in scored)}
    completed = all(metrics[arm]['completed_cases'] == len(cases) for arm in metrics)
    report = {'schema_version': 'rsi-shadow-report-1', 'kind': kind,
        'execution': 'live_model' if live_model else 'synthetic_fixture',
        'status': 'awaiting_independent_anchors' if completed else 'incomplete',
        'eligible': False, 'activated': False, 'learning_effect_verified': False,
        'scope': {'project_id': project.pk, 'owner_id': project.user_id, 'origin': packet['provenance']['origin'],
                  'baseline': 'operator_supplied_shadow_seed', 'split': 'operator_declared_not_verified'},
        'anchor_validation': 'operator_supplied_not_attested', 'anchors_sent_to_models': False,
        'packet_hash': canonical_hash(packet), 'case_hashes': {case['id']: canonical_hash(case) for case in cases},
        'artifacts': {'baseline_instruction': packet['baseline']['instruction'],
                      'candidate_instruction': candidate_instruction},
        'frozen_materials': {'development': packet['development'], 'cases': cases},
        'prompt_templates': {name: _template(name) for name in
            ('rsi_propose.txt', 'rsi_generate.txt', 'rsi_evaluate_method.txt', 'rsi_evaluate_answer.txt')},
        'operator_anchors': packet.get('anchors', []),
        'mechanisms': {'runtime_baseline': bundle[kind], 'baseline': baseline.digest, 'candidate': candidate.digest if candidate else None},
        'comparison': {'changed_kind': kind, 'fixed_evaluator_hash': canonical_hash(_template('rsi_evaluate_method.txt')) if kind == 'G' else None,
                       'same_frozen_materials': True, 'matched_evaluation_caps': True, 'actual_cost_equal': False,
                       'candidate_instruction_changed': candidate_instruction != packet['baseline']['instruction'] if candidate_instruction else False},
        'model': {'operation': OPERATION, 'configured_model': config['model'],
                  'adapter': 'dsh' if dsh_adapter else 'ai_engine_direct', 'temperature': .2,
                  'configured_retry_limit': getattr(settings, 'LLM_REQUEST_MAX_RETRIES', 1),
                  'provider_attempt_count_observed': False},
        'budget': {'limits_per_arm': limits, 'engine_call_slots_used': spent,
                   'proposal_charged_to_candidate': live_model,
                   'observed_success_usage_complete': live_model and any(call['status'] == 'completed' for call in calls)
                       and all(call.get('usage') is not None for call in calls if call['status'] == 'completed'),
                   'provider_total_usage_complete': False,
                   'status': 'limited' if any(call['status'] != 'completed' for call in calls) else 'within_call_caps_token_cost_unverified'},
        'calls': calls, 'outputs': outputs, 'metrics': metrics,
        'notice': 'Shadow comparison only. Model scores and operator-declared anchors do not attest independent accuracy, learning gain, or recursive improvement. No policy activation.'}
    run = TeachingResearchRun.objects.create(owner=project.user, project=project, kind=kind,
        baseline=baseline, candidate=candidate, packet_hash=report['packet_hash'],
        protocol={'schema_version': packet['schema_version'], 'provenance': packet['provenance'],
                  'budget': limits, 'note': packet.get('protocol', {}).get('note', ''),
                  'case_hashes': report['case_hashes'], 'anchors_hash': canonical_hash(packet.get('anchors', []))}, report=report)
    return {'run_id': run.pk, **report}
