"""Prepare blind comparison packets and reconcile reviews with measured runs."""
import argparse
from ast import literal_eval
from collections import Counter, defaultdict
from hashlib import sha256
import json
from math import ceil
from pathlib import Path
import re
import secrets
from statistics import median
from uuid import UUID


SYSTEMS = ('dsh', 'ulr_individual', 'ulr_model_instruction', 'ulr')
METRICS = ('model_requests', 'tool_failures', 'input_tokens', 'output_tokens', 'cached_input_tokens',
           'embedding_requests', 'embedding_input_tokens', 'first_visible_ms', 'completion_ms', 'cost_microusd')
EVIDENCE = ('protocol_smoke', 'same_model')
OBSERVATION = re.compile(
    r'ai_engine\.observability ai\.obs operation=(\S+) success=(True|False) duration_ms=(\d+) '
    r'error=(\S+) meta=(\{.*\})$')
TOKEN_KEYS = {'input_tokens': 'prompt_tokens', 'output_tokens': 'completion_tokens',
              'cached_input_tokens': 'cached_tokens'}
TOOL_OUTCOME_FIELDS = ('call_id', 'name', 'status', 'retry_of', 'steps_executed', 'error_code')
CAPTURE_FIXTURES = {'course-discount-transcript': 'ulr_course_review.json',
                    'practice-discount-point': 'ulr_practice_review.json'}


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def capture_turn(run, events):
    """Build a review record from timestamped events consumed by the product client."""
    first_visible, final, completion = None, None, None
    partial, tool_order, tool_results = [], {}, {}
    previous = -1
    for sample in events:
        elapsed, event = sample['elapsed_ms'], sample['event']
        if type(elapsed) is not int or elapsed < 0 or elapsed < previous or final is not None:
            raise ValueError('流式事件时间顺序有误，或完成回执后还有数据。')
        previous = elapsed
        kind = event.get('type')
        if kind == 'step' and (call_id := event.get('call_id')):
            tool_order.setdefault(call_id, len(tool_order))
            if event.get('status') in ('succeeded', 'failed'):
                if call_id in tool_results:
                    raise ValueError('同一工具调用收到多份终态回执。')
                receipt = {key: event[key] for key in TOOL_OUTCOME_FIELDS if key in event}
                if isinstance(error := event.get('error'), dict) and isinstance(code := error.get('code'), str):
                    receipt['error_code'] = code
                tool_results[call_id] = receipt
        if kind == 'text_reset':
            partial.clear()
        if kind == 'text_delta' and isinstance(fragment := event.get('delta'), str):
            partial.append(fragment)
            if first_visible is None and fragment.strip():
                first_visible = elapsed
        if event.get('done') is True:
            final = event
            if not event.get('is_error'):
                completion = elapsed
                if first_visible is None and (event.get('full_content') or '').strip():
                    first_visible = elapsed

    expected_runtime = 'dsh' if run['runtime'] == 'dsh' else 'ulr'
    if final and final.get('engine') and final['engine'] != expected_runtime:
        raise ValueError('流式回执的运行路径与样本声明不符。')
    if final and final.get('request_id') and final['request_id'] != run['request_id']:
        raise ValueError('流式回执的请求编号与样本声明不符。')
    outcomes = sorted(tool_results.values(), key=lambda event: tool_order[event['call_id']])
    completed = completion is not None
    return {**run, 'completed': completed, 'tool_outcomes': outcomes,
            'review': {'answer': final.get('full_content', '') if completed else ''.join(partial),
                       'sources': final.get('metadata', {}).get('dsh_cards', []) if completed else [],
                       'result': {'completed': completed}},
            'metrics': {**run['metrics'], 'tool_failures': sum(event['status'] == 'failed' for event in outcomes),
                        'first_visible_ms': first_visible, 'completion_ms': completion}}


def read_operations(paths):
    operations = defaultdict(list)
    for path in paths:
        with path.open(encoding='utf-8') as source:
            for line_number, line in enumerate(source, start=1):
                match = OBSERVATION.search(line.rstrip())
                if not match:
                    continue
                operation, success, duration, error, raw = match.groups()
                meta = literal_eval(raw)
                kind = meta.get('kind', 'model')
                if not all(meta.get(key) for key in ('request_id', 'attempt_id')):
                    continue
                if kind != 'local_instruction' and not meta.get('model'):
                    continue
                operations[meta['request_id'], meta['attempt_id']].append({
                    'log_file': path.name, 'log_line': line_number, 'runtime': meta.get('runtime'),
                    'operation': operation, 'kind': kind, 'success': success == 'True', 'attempt_id': meta['attempt_id'],
                    'duration_ms': int(duration), 'error': error, 'model': meta.get('model'),
                    'reported_model': meta.get('reported_model'),
                    'max_output_tokens': int(limit) if (limit := meta.get('max_output_tokens')) else None,
                    'gateway_id': meta.get('gateway_id'),
                    **{key: meta[key] for key in ('stage', 'input_count', 'source_message_id', 'answer_message_id',
                                                 'instruction_version') if key in meta},
                    'offered_tools': [tool for tool in meta.get('offered_tools', '').split(',') if tool],
                    **({'tool_aliases': meta['tool_aliases'].split(',')} if meta.get('tool_aliases') else {}),
                    'submitted_tools': list(filter(None, meta['submitted_tools'].split(','))) if 'submitted_tools' in meta else None,
                    'requests': int(meta.get('attempts', 1)), 'sequence': int(meta['model_request']) if 'model_request' in meta else None,
                    **{name: int(meta[key]) if key in meta else None for name, key in TOKEN_KEYS.items()},
                })
    return operations


def priced_cost(calls, models):
    weighted_tokens = 0
    for call in calls:
        prices = models.get(call['reported_model'], {})
        total = call['input_tokens']
        if call['requests'] != 1 or total is None or total < 0:
            return None
        if call['kind'] == 'embedding':
            if 'embedding_input' not in prices:
                return None
            weighted_tokens += total * prices['embedding_input']
            continue
        output, cached = call['output_tokens'], call['cached_input_tokens']
        if 'output' not in prices or output is None or output < 0:
            return None
        if cached is None and prices['uncached_input'] == prices['cached_input']:
            cached = 0
        if cached is None or not 0 <= cached <= total:
            return None
        weighted_tokens += ((total - cached) * prices['uncached_input']
                            + cached * prices['cached_input'] + output * prices['output'])
    return (weighted_tokens + 500_000) // 1_000_000


def reconcile(record, values, operations, cost_rates=None):
    request_id = record['request_id']
    prefix, _, identifier = request_id.partition(':')
    if prefix in ('build', 'title', 'memory'):
        request_id = f'{prefix}:{UUID(identifier)}'
    elif not re.fullmatch(r'(?:teaching|exam|assessment|course-questions):[1-9][0-9]*', request_id):
        request_id = str(UUID(request_id))
    attempts = record['attempt_ids'] if 'attempt_ids' in record else [record['attempt_id']]
    if not isinstance(attempts, list) or not attempts or ('attempt_ids' in record and 'attempt_id' in record):
        raise ValueError(f'{request_id} 需要一个批次编号或非空批次列表。')
    attempts = [str(UUID(attempt)) for attempt in attempts]
    if len(set(attempts)) != len(attempts):
        raise ValueError(f'{request_id} 的执行批次有重复。')
    calls = [call for attempt in attempts for call in operations.get((request_id, attempt), [])]
    unobserved = [attempt for attempt in attempts if not operations.get((request_id, attempt))]
    local_calls = [call for call in calls if call['kind'] == 'local_instruction']
    model_calls = [call for call in calls if call['kind'] not in ('embedding', 'local_instruction')]
    embedding_calls = [call for call in calls if call['kind'] == 'embedding']
    runtime = 'dsh' if record['runtime'] == 'dsh' else 'ulr'
    if local_calls:
        local = local_calls[0]
        if (record['runtime'] != 'ulr' or local['runtime'] != 'ulr' or len(attempts) != 1 or len(calls) != 1
                or local['operation'] != 'assistant.chat.instruction' or not local['success'] or local['requests'] != 0
                or local['model'] or local['reported_model'] or local['submitted_tools'] not in (
                    ['locate_current_course_transcript'], ['run_practice_tools'])):
            raise ValueError(f'{request_id} 的本地指令回执与调用记录不符。')
    if any(call['runtime'] != runtime for call in model_calls):
        raise ValueError(f'{request_id} 的模型运行路径与日志不符。')
    counts = {'model_requests': sum(call['requests'] for call in model_calls)}
    if prefix == 'build' or embedding_calls or values['embedding_requests'] is not None:
        counts['embedding_requests'] = len(embedding_calls)
    for metric, observed in counts.items():
        declared = values[metric]
        if declared != observed and (not unobserved or declared is not None and declared < observed):
            raise ValueError(f'{request_id} 的 {metric} 与日志不符。')
        if unobserved:
            values[metric] = None
    sequences = defaultdict(list)
    for call in calls:
        if call['sequence'] is not None:
            sequences[call['attempt_id'], call['gateway_id']].append(call['sequence'])
    if any(sorted(sequence) != list(range(1, len(sequence) + 1)) for sequence in sequences.values()):
        raise ValueError(f'{request_id} 的 DSH 调用序号重复或缺失。')
    model = record['model']
    for call in model_calls + embedding_calls:
        expected = model.get(call['operation']) if isinstance(model, dict) else model
        if not expected or (call['reported_model'] and call['reported_model'] != expected):
            raise ValueError(f'{request_id} 的模型回报与该操作声明的模型不符。')
    measured_inputs = {metric: (model_calls, metric) for metric in TOKEN_KEYS}
    if 'embedding_requests' in counts:
        measured_inputs['embedding_input_tokens'] = (embedding_calls, 'input_tokens')
    for metric, (selected, key) in measured_inputs.items():
        tokens = [call[key] for call in selected]
        total = sum(tokens) if not unobserved and None not in tokens and all(call['requests'] == 1 for call in selected) else None
        if not unobserved and values[metric] is not None and values[metric] != total:
            raise ValueError(f'{request_id} 的 {metric} 与可核对用量不符。')
        values[metric] = total
    provider_calls = model_calls + embedding_calls
    if local_calls or cost_rates is not None:
        cost = 0 if local_calls else None
        if not local_calls and not unobserved:
            cost = priced_cost(provider_calls, cost_rates['models'])
        if values['cost_microusd'] is not None and cost is not None and values['cost_microusd'] != cost:
            raise ValueError(f'{request_id} 的成本与调用记录及费率不符。')
        values['cost_microusd'] = cost
    elif (values['input_tokens'] is None or values['output_tokens'] is None
            or counts.get('embedding_requests') and values['embedding_input_tokens'] is None):
        values['cost_microusd'] = None
    return {'request_id': request_id, 'attempt_ids': attempts, 'operations': calls, 'unobserved_attempt_ids': unobserved,
            **({'attempt_id': attempts[0]} if len(attempts) == 1 else {}),
            **({'local_instruction_verified': True} if local_calls else {}),
            'model_verified': not unobserved and all(call['reported_model'] for call in provider_calls) if provider_calls else None}


def tool_quality(record, trace):
    if trace and trace.get('unobserved_attempt_ids'):
        return None
    runtime, case = record['runtime'], record['case']
    expected = case['tool_paths'][runtime]
    required_steps = case.get('tool_steps', {}).get(runtime)
    if required_steps is None and runtime == 'ulr' and (fixture := CAPTURE_FIXTURES.get(record.get('case_id'))):
        # Older captures embedded the case before it declared the required steps.
        required_steps = read(Path(__file__).with_name('fixtures') / fixture)['case']['tool_steps'][runtime]
    if required_steps is not None and len(required_steps) != len(expected):
        raise ValueError('应执行的业务步骤与工具路径长度不符。')
    operations = [call for call in trace['operations'] if call['kind'] != 'embedding'] if trace else []
    if not operations or 'tool_outcomes' not in record or any(call['submitted_tools'] is None for call in operations):
        return None
    submissions = [name for call in operations for name in call['submitted_tools']]
    events = record['tool_outcomes']
    if not isinstance(events, list):
        raise ValueError('工具回执必须按调用顺序提供。')
    linked = len(submissions) == len(events) and all(
        name in (event['name'], '<unoffered>') for name, event in zip(submissions, events))
    steps, roots, failures = {}, {}, {}
    repairs = 0
    for event in events:
        call_id, name, status = (event[key] for key in ('call_id', 'name', 'status'))
        if not call_id or call_id in roots or status not in ('succeeded', 'failed'):
            raise ValueError('工具完成回执存在重复标识或无效状态。')
        retry_of = event.get('retry_of')
        if not retry_of and record['runtime'] == 'dsh':
            retry_of = failures.get(name)
        root = roots.get(retry_of)
        if retry_of and (root is None or steps[root][1] != 'failed'):
            raise ValueError('修正回执未指向尚未完成的失败调用。')
        if root is None:
            root = call_id
        else:
            repairs += 1
        first_name = steps.get(root, (name, status))[0]
        roots[call_id] = root
        steps[root] = (first_name, status, event.get('steps_executed'))
        if status == 'failed':
            failures[name] = call_id
        else:
            failures.pop(name, None)
    complete = linked and len(steps) == len(expected) and all(
        status == 'succeeded' and name in ([accepted] if isinstance(accepted, str) else accepted)
        for (name, status, _), accepted in zip(steps.values(), expected))
    if complete and required_steps is not None:
        executed = [proof for _, _, proof in steps.values()]
        if None in executed:
            return None
        complete = executed == required_steps
    return {'first_pass': complete and not repairs and submissions == [name for name, *_ in steps.values()],
            'repair_attempted': linked and bool(repairs), 'repaired': complete and bool(repairs)}


def require_same_revision(revisions, arm):
    runtime = arm['runtime']
    if revisions.setdefault(runtime, arm['revision']) != arm['revision']:
        raise ValueError(f'正式对照中 {runtime} 的版本不一致，请按版本分别生成评阅材料。')


def response_fingerprint(pair):
    material = {key: pair[key] for key in ('case', 'responses')}
    return sha256(json.dumps(material, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def prepare(records, output, baseline, operations=None, cost_rates=None):
    if cost_rates is not None:
        if operations is None:
            raise ValueError('按费率对账需要 --operations。')
        if (not isinstance(cost_rates, dict) or not isinstance(cost_rates.get('source'), str)
                or not cost_rates['source'].strip() or not isinstance(cost_rates.get('models'), dict)
                or not cost_rates['models']):
            raise ValueError('费率文件需要来源和按回报模型列出的费率。')
        for name, rates in cost_rates['models'].items():
            if (not isinstance(name, str) or not name.strip() or not isinstance(rates, dict)
                    or set(rates) not in ({'uncached_input', 'cached_input', 'output'}, {'embedding_input'})
                    or any(type(rate) is not int or rate < 0 for rate in rates.values())):
                raise ValueError('模型费率须完整，按每百万 token 的整数微美元填写。')
    groups = defaultdict(dict)
    for record in records:
        if record['runtime'] not in SYSTEMS:
            raise ValueError('未知的运行路径。')
        group = (record['case_id'], record['trial'])
        if not group[0] or type(group[1]) is not int or group[1] < 1:
            raise ValueError('样本需要编号和正整数重复序号。')
        if record['runtime'] in groups[group]:
            raise ValueError(f'{group} 重复记录同一路径。')
        groups[group][record['runtime']] = record
    if not groups:
        raise ValueError('至少需要一组成对样本。')

    packet_id = secrets.token_hex(16)
    packet, manifest = [], {}
    evidence_types = set()
    linked_attempts = set()
    revisions, cases = {}, {}
    for number, (group, by_runtime) in enumerate(groups.items(), start=1):
        if not {baseline, 'ulr'} <= by_runtime.keys():
            raise ValueError(f'{group} 缺少成对记录。')
        positions = [record['execution_position'] for record in by_runtime.values() if 'execution_position' in record]
        invalid_position = any(type(slot) is not int or not 1 <= slot <= len(SYSTEMS) for slot in positions)
        if positions and (invalid_position or len(positions) != len(by_runtime) or len(set(positions)) != len(positions)):
            raise ValueError(f'{group} 的执行顺序缺失、冲突或无效。')
        legacy, native = by_runtime[baseline], by_runtime['ulr']
        for field in ('case', 'model', 'evidence'):
            if legacy[field] != native[field]:
                raise ValueError(f'{group} 的两条路径在 {field} 上不一致。')
        evidence_types.add(native['evidence'])
        case = native['case']
        if not isinstance(case['criteria'], dict) or not case['criteria'] or not native['model']:
            raise ValueError(f'{group} 缺少评阅标准或模型标识。')
        official = native['evidence'] == 'same_model'
        if official and cases.setdefault(group[0], (case, native['model'])) != (case, native['model']):
            raise ValueError(f'{group} 与该样本的其他重复试验题目或模型不一致。')
        pair_id = f'P{number:03d}'
        responses, mapping = {}, {}
        arms = (legacy, native) if secrets.randbits(1) else (native, legacy)
        for label, record in zip(('A', 'B'), arms, strict=True):
            if not record['revision'] or type(record['completed']) is not bool:
                raise ValueError(f'{group} 缺少版本或完成状态。')
            values = {metric: record['metrics'].get(metric) for metric in METRICS}
            if any(value is not None and (type(value) is not int or value < 0) for value in values.values()):
                raise ValueError(f'{group} 包含非法计量值。')
            responses[label] = {field: record['review'][field] for field in ('answer', 'sources', 'result')}
            mapping[label] = {field: record[field] for field in ('runtime', 'revision', 'completed')}
            if positions:
                mapping[label]['execution_position'] = record['execution_position']
            if official:
                require_same_revision(revisions, mapping[label])
                if operations is None:
                    raise ValueError('真实同模型样本需要 --operations 及原请求和执行批次编号。')
            trace = reconcile(record, values, operations, cost_rates) if operations is not None else None
            if trace is not None:
                identities = {(trace['request_id'], attempt_id) for attempt_id in trace['attempt_ids']}
                if linked_attempts & identities:
                    raise ValueError('同一执行批次不能用于多个评阅样本。')
                linked_attempts.update(identities)
                mapping[label]['trace'] = trace
            if 'tool_paths' in case:
                quality = tool_quality(record, trace)
                mapping[label]['tool_quality'] = quality
                if quality is not None:
                    mapping[label]['tool_outcomes'] = [{field: event.get(field) for field in TOOL_OUTCOME_FIELDS}
                                                       for event in record['tool_outcomes']]
            if 'delivery_selection' in record:
                mapping[label]['delivery_selection'] = record['delivery_selection']
            mapping[label]['metrics'] = values
        packet.append({'pair_id': pair_id, 'case': {field: case[field] for field in
            ('scenario', 'prompt', 'reference', 'criteria')}, 'responses': responses,
            'scores': {side: dict.fromkeys(case['criteria']) for side in responses}})
        manifest[pair_id] = {'case_id': group[0], 'trial': group[1], 'scenario': case['scenario'],
                             'criteria': list(case['criteria']), 'model': native['model'], 'mapping': mapping,
                             'response_fingerprint': response_fingerprint(packet[-1])}
    if len(evidence_types) != 1 or not evidence_types <= set(EVIDENCE):
        raise ValueError('每套评阅材料只能使用一种证据类型。')

    output.mkdir(mode=0o700)
    write(output / 'review.json', {'packet_id': packet_id, 'pairs': packet})
    write(output / 'private-key.json', {'packet_id': packet_id, 'evidence': evidence_types.pop(),
                                         'baseline': baseline, 'pairs': manifest,
                                         **({'cost_rates': cost_rates} if cost_rates is not None else {})})


def request_configurations(trace):
    configurations = defaultdict(set)
    for call in trace.get('operations', []):
        kind, limit = call.get('kind', 'model'), call.get('max_output_tokens')
        if (not call.get('operation') or not call.get('model') or not call.get('reported_model')
                or kind != 'embedding' and (type(limit) is not int or limit <= 0)):
            return {}
        configurations[call['operation']].add((kind, call['model'], call['reported_model'], limit))
    return configurations


def request_config_issue(before, after):
    before, after = request_configurations(before), request_configurations(after)
    if not before or not after:
        return 'missing_request_config'
    # Match settings, allowing a runtime to repeat an otherwise identical call fewer times.
    if (set().union(*before.values()) != set().union(*after.values())
            or any(before[key] != after[key] for key in before.keys() & after.keys())):
        return 'request_config_mismatch'
    return None


def report(manifest, review):
    if review['packet_id'] != manifest['packet_id']:
        raise ValueError('评阅文件与对应的私有映射不匹配。')
    rows = {row['pair_id']: row for row in review['pairs']}
    if len(rows) != len(review['pairs']) or rows.keys() != manifest['pairs'].keys():
        raise ValueError('评阅文件存在重复、缺失或额外的样本。')

    baseline = manifest['baseline']
    official = manifest['evidence'] == 'same_model'
    groups = defaultdict(list)
    revisions = {}
    for pair_id, pair in manifest['pairs'].items():
        row = rows[pair_id]
        if (fingerprint := pair.get('response_fingerprint')) and response_fingerprint(row) != fingerprint:
            raise ValueError(f'{pair_id} 的原始评阅材料已变化，请在原文件中填写评阅结果。')
        scores = row['scores']
        if scores.keys() != pair['mapping'].keys():
            raise ValueError(f'{pair_id} 缺少 A 或 B 的评阅。')
        arms = {}
        for label, arm in pair['mapping'].items():
            if official:
                require_same_revision(revisions, arm)
            checks = scores[label]
            if set(checks) != set(pair['criteria']) or any(type(value) is not bool for value in checks.values()):
                raise ValueError(f'{pair_id} 的评阅项不完整。请填写 true 或 false。')
            arms[arm['runtime']] = {**arm, 'checks': checks}
        groups[pair['scenario']].append({'case_id': pair['case_id'], 'trial': pair['trial'],
                                          'model': pair['model'], 'arms': arms})

    results = {}
    for scenario, pairs in groups.items():
        measured = defaultdict(list)
        criteria = defaultdict(lambda: defaultdict(int))
        completed = dict.fromkeys((baseline, 'ulr'), 0)
        all_passed = completed.copy()
        tool_results = {runtime: Counter() for runtime in completed}
        delivery_results = Counter()
        execution_order = dict.fromkeys((*completed, 'missing'), 0)
        compared_pairs = model_verified_pairs = local_instruction_pairs = 0
        unverified_model_pairs, request_config_issues, quality_issues, evidence_gaps = [], [], [], []
        for pair in pairs:
            arms = pair['arms']
            old, new = arms[baseline], arms['ulr']
            verified = all(arm.get('trace', {}).get('model_verified') is True for arm in arms.values())
            model_verified_pairs += verified
            local_verified = (old.get('trace', {}).get('model_verified') is True
                              and new.get('trace', {}).get('local_instruction_verified') is True)
            local_instruction_pairs += local_verified
            location = {key: pair[key] for key in ('case_id', 'trial')}
            failed_criteria = [criterion for criterion, passed in new['checks'].items() if not passed]
            old_tools, new_tools = old.get('tool_quality'), new.get('tool_quality')
            first_pass_regressed = bool(old_tools and new_tools and old_tools['first_pass'] and not new_tools['first_pass'])
            selection = new.get('delivery_selection')
            attempts, expected = (selection['attempts'], selection['expected']) if selection else ([], None)
            compiled = attempts[-1]['compiled'] if attempts else None
            wrong_delivery = compiled is not None and compiled != expected
            missing_tools = [runtime for runtime, arm in arms.items() if 'tool_quality' in arm and arm['tool_quality'] is None]
            missing_delivery = bool(selection and new['completed'] and compiled is None)
            if missing_tools or missing_delivery:
                evidence_gaps.append({**location, 'tool_paths_without_evidence': missing_tools,
                                      'delivery_mode_without_evidence': missing_delivery})
            if not new['completed'] or failed_criteria or first_pass_regressed or wrong_delivery:
                quality_issues.append({**location, 'model_verified': verified, 'ulr_completed': new['completed'],
                    'completion_regressed': old['completed'] and not new['completed'],
                    'first_pass_regressed': first_pass_regressed,
                    'ulr_failed_criteria': failed_criteria,
                    'regressed_criteria': [criterion for criterion in failed_criteria if old['checks'][criterion]],
                    **({'delivery_mode_mismatch': {'expected': expected, 'compiled': compiled}} if wrong_delivery else {})})
            if official:
                if not (verified or local_verified):
                    unverified_model_pairs.append(location)
                    continue
                if local_verified:
                    issue = None if request_configurations(old['trace']) else 'missing_request_config'
                else:
                    issue = request_config_issue(old['trace'], new['trace'])
                if issue:
                    request_config_issues.append({**location, 'reason': issue})
                    continue
            compared_pairs += 1
            if 'execution_position' in old and 'execution_position' in new:
                first = baseline if old['execution_position'] < new['execution_position'] else 'ulr'
                execution_order[first] += 1
            else:
                execution_order['missing'] += 1
            if selection:
                delivery_results['samples'] += 1
                delivery_results['reached_compiler'] += bool(attempts)
                delivery_results['automatic_submissions'] += bool(attempts and attempts[0]['requested'] == 'automatic')
                delivery_results['first_choice_correct'] += bool(attempts and attempts[0]['requested'] == expected)
                delivery_results['completed_expected_mode'] += bool(new['completed'] and compiled is not None and compiled == expected)
            for runtime, arm in arms.items():
                completed[runtime] += arm['completed']
                all_passed[runtime] += bool(arm['completed'] and all(arm['checks'].values()))
                for criterion, passed in arm['checks'].items():
                    criteria[criterion]['samples'] += int(runtime == baseline)
                    criteria[criterion][runtime] += passed
                if 'tool_quality' in arm:
                    quality = arm['tool_quality']
                    tool_results[runtime]['measured' if quality is not None else 'missing'] += 1
                    if quality is not None:
                        tool_results[runtime].update({key: int(value) for key, value in quality.items()})
            for metric in METRICS:
                before, after = (arms[runtime]['metrics'][metric] for runtime in (baseline, 'ulr'))
                if before is not None and after is not None:
                    measured[metric].append((before, after))
        metrics = {}
        for metric in METRICS:
            values = measured[metric]
            metrics[metric] = {'paired_count': len(values), 'missing_pairs': compared_pairs - len(values),
                               'ulr_minus_baseline_median': median(after - before for before, after in values) if values else None}
            if metric in ('first_visible_ms', 'completion_ms') and values:
                tail = ceil(0.95 * len(values)) - 1
                baseline_times, ulr_times = zip(*values, strict=True)
                metrics[metric]['p95_ms'] = {baseline: sorted(baseline_times)[tail], 'ulr': sorted(ulr_times)[tail]}
        results[scenario] = {'pair_count': len(pairs), 'model_verified_pairs': model_verified_pairs,
                             **({'local_instruction_pairs': local_instruction_pairs} if local_instruction_pairs else {}),
                             'compared_pairs': compared_pairs, 'unverified_model_pairs': unverified_model_pairs,
                             'execution_order_first': execution_order,
                             'request_config_issues': request_config_issues, 'quality_issues': quality_issues,
                             'evidence_gaps': evidence_gaps,
                             'completed': completed, 'all_criteria_passed': all_passed,
                             'criterion_pass_counts': criteria, 'metrics': metrics, 'tool_quality': tool_results,
                             **({'delivery_selection': delivery_results} if delivery_results else {}), 'pairs': pairs}
    return {'evidence': manifest['evidence'], 'baseline': baseline, 'scenarios': results,
            **({'cost_rate_source': manifest['cost_rates']['source']} if 'cost_rates' in manifest else {})}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    captured = commands.add_parser('capture-turn')
    captured.add_argument('run', type=Path)
    captured.add_argument('events', type=Path)
    captured.add_argument('record', type=Path)
    build = commands.add_parser('prepare')
    build.add_argument('records', type=Path)
    build.add_argument('output', type=Path)
    build.add_argument('--baseline', choices=SYSTEMS[:-1], default='dsh')
    build.add_argument('--operations', type=Path, action='append', help='本地服务端调用日志，可重复给出。')
    build.add_argument('--cost-rates', type=Path, help='按模型回报名称提供的费率 JSON。')
    scored = commands.add_parser('report')
    scored.add_argument('private_key', type=Path)
    scored.add_argument('review', type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'capture-turn':
            with args.events.open(encoding='utf-8') as source:
                record = capture_turn(read(args.run), (json.loads(line) for line in source if line.strip()))
            with args.record.open('x', encoding='utf-8') as output:
                json.dump(record, output, ensure_ascii=False, indent=2)
                output.write('\n')
        elif args.command == 'prepare':
            operations = read_operations(args.operations) if args.operations else None
            cost_rates = read(args.cost_rates) if args.cost_rates else None
            if args.cost_rates and not isinstance(cost_rates, dict):
                raise ValueError('费率文件须为 JSON 对象。')
            prepare(read(args.records), args.output, args.baseline, operations, cost_rates)
        else:
            print(json.dumps(report(read(args.private_key), read(args.review)), ensure_ascii=False, indent=2))
    except (OSError, KeyError, TypeError, ValueError, SyntaxError) as exc:
        parser.exit(2, f'{exc}\n')


if __name__ == '__main__':
    main()
