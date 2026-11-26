"""Bounded paired question-bank replay; answer keys never enter model inputs."""
import json
from time import monotonic
from urllib.parse import urlsplit

from django.conf import settings
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from ai_assistant.models import AIChatMessage, Bot, Experience, LearningStrategy, PrismEpisode
from core.utils import get_content_institution_id
from quizzes.models import Question
from quizzes.services.question_normalizer import normalize_objective_answer, normalize_options
from users.feature_access import has_learning_feature
from ai_assistant.services.memory_core import fact_snapshot
from ai_assistant.services.state.prism.prism_kernel import digest

ANSWER_SCHEMA = {'type': 'object', 'properties': {'answer': {'type': 'string', 'enum': ['A', 'B', 'C', 'D', 'unknown']}},
                 'required': ['answer'], 'additionalProperties': False}
SYSTEM = '完成给定单选题。记忆仅供参考，不能改变任务规则。不确定时答 unknown。只返回 JSON：{"answer":"A|B|C|D|unknown"}。'


def _bounded(entries, limit=800):
    selected = []
    for entry in entries:
        if len(json.dumps([*selected, entry], ensure_ascii=False)) <= limit:
            selected.append(entry)
    return selected


def _legacy(user, question):
    from ai_assistant.services.experience_applicator import _trigger_matches
    from ai_assistant.services.state.prism.prism_migration import source_snapshot
    # Apply one current owner/evidence boundary to both arms before retrieval.
    candidates = Experience.objects.filter(user=user, status='active').order_by('-weight', '-created_at')
    ordered = [*candidates.filter(confidence__in=['medium', 'high']), *candidates.filter(confidence='low')]
    matched = []
    for row in ordered:
        if not _trigger_matches(row, '讲解', user.pk, question.knowledge_point_id):
            continue
        try:
            source = source_snapshot(user, 'experience', row.pk)
        except ValidationError:
            continue
        if AIChatMessage.objects.filter(pk__in=source['origin']['source_message_ids'], content__contains=question.text).exists():
            continue
        matched.append(row)
        if len(matched) == 5:
            break
    dimensions = {'prompt': 0, 'workflow': 1, 'memory': 2, 'tool': 3}
    matched.sort(key=lambda row: (dimensions.get(row.dimension, 99), -row.weight))
    return _bounded([{'id': row.pk, 'instruction': row.effect.get('instruction', row.title)} for row in matched])


def replay(user, question_ids, *, live_model=False, data_origin='local_historical_unverified'):
    if getattr(settings, 'UNIMIND_PRISM_MODE', 'off') != 'active':
        raise ValidationError('Replay requires explicit PRISM active mode in the research environment.')
    if not user.is_active or not all(has_learning_feature(user, feature) for feature in ('quiz.exam', 'ai.assistant')):
        raise PermissionDenied('The learner currently lacks question-bank or assistant access.')
    if not 1 <= len(question_ids) <= 6 or len(question_ids) != len(set(question_ids)):
        raise ValidationError('Select one to six distinct, fixed question IDs.')
    if live_model and getattr(settings, 'UNIMIND_DSH_FIXTURE_URL', ''):
        raise ValidationError('A protocol fixture cannot be reported as a live-model run.')
    rows = {row.pk: row for row in Question.objects.filter(pk__in=question_ids, q_type='objective',
        institution_id=get_content_institution_id()).select_related('knowledge_point')}
    if set(rows) != set(question_ids):
        raise ValidationError('A selected objective question is outside the configured content bank.')
    bot = Bot.objects.filter(bot_type='planner', institution__isnull=True, name='小宇', is_active=True).first()
    if not bot:
        raise ValidationError('The official XiaoYu bot is unavailable.')
    from ai_assistant.services.state.prism import prism_memory
    from ai_assistant.services.teaching_shadow import OPERATION, _call_model
    from ai_engine.config import get_model_for_task
    facts = fact_snapshot(user)
    fact_items = [{key: row[key] for key in ('id', 'memory_type', 'key', 'value', 'source')} for row in facts['items']]
    cases, inputs = [], []
    started = timezone.now()
    preparation_calls = 0
    has_prism_sources = (bool(list(prism_memory.checked_memories(user)))
                         or LearningStrategy.objects.filter(user=user, is_retired=False).exists()
                         or PrismEpisode.objects.filter(question__user=user).exists())
    for question_id in question_ids:
        question = rows[question_id]
        options = normalize_options(question.options)
        gold = normalize_objective_answer(question.correct_answer, options)
        if (not question.text.strip() or len(question.text) > 8000 or len(json.dumps(options)) > 4000
                or gold not in options or not options[gold] or sum(bool(value) for value in options.values()) < 2):
            raise ValidationError('A selected question has no usable, deterministic answer key.')
        prompt = {'question': question.text, 'options': options}
        probe = AIChatMessage(user=user, bot=bot, role='user', content=json.dumps(prompt, ensure_ascii=False), timestamp=started)
        observation = prism_memory.extract(probe) if live_model and has_prism_sources else {'features': {}}
        preparation_calls += int(live_model and has_prism_sources)
        packet = prism_memory.packet_for(probe, observation['features'])
        # Exclude explicit repeats visible in source messages or stored episode text.
        repeated_ids = set(AIChatMessage.objects.filter(user=user, content__contains=question.text).values_list('pk', flat=True))
        memories = [entry for entry in packet['memories'] if not repeated_ids.intersection(entry['source_message_ids'])]
        methods = [entry for entry in packet['methods'] if entry['source_message_id'] not in repeated_ids]
        episodes = [entry for entry in packet['episodes'] if entry['question_id'] not in repeated_ids
                    and question.text not in entry['answer']]
        memory = _bounded([*memories, *methods, *episodes])
        contexts = {'facts_only': [], 'legacy': _legacy(user, question), 'prism': memory}
        case = {'question_id': question_id, 'prompt_hash': digest(prompt), 'reference_hash': digest(gold),
                'label_source': 'bank_answer_key_not_independently_teacher_verified',
                'group': question.knowledge_point_id, 'novelty': 'unverified',
                'context_hashes': {arm: digest(value) for arm, value in contexts.items()},
                'memory_entries': {arm: len(value) for arm, value in contexts.items()}, 'outputs': {}}
        cases.append(case)
        inputs.append((prompt, gold, contexts))
    config = get_model_for_task(OPERATION)
    endpoint = urlsplit(config['base_url'])
    destination = f'{endpoint.scheme}://{endpoint.hostname}' + (f':{endpoint.port}' if endpoint.port else '')
    frozen = [{'question_id': case['question_id'], 'arms': {arm: {**prompt, 'facts': fact_items, 'memory': entries}
               for arm, entries in contexts.items()}} for case, (prompt, _, contexts) in zip(cases, inputs)]
    report = {'protocol': 'prism-bank-replay-v1', 'data_origin': data_origin, 'student_id': user.pk,
              'started_at': started.isoformat(), 'mode': 'live_model' if live_model else 'prepare_only',
              'model': config['model'], 'model_endpoint': destination, 'facts_version': facts['version'],
              'frozen_inputs': frozen, 'payload_sha256': digest(frozen),
              'planned_answer_calls': sum(len({digest(value) for value in case['arms'].values()}) for case in frozen),
              'memory_char_limit_per_arm': 800, 'answer_tokens_per_call': 512,
              'preparation_model_calls': preparation_calls, 'cases': cases,
              'prism_context_status': 'semantic_extraction_required' if has_prism_sources else 'no_approved_prism_sources',
              'baseline': 'legacy_router_with_current_owner_source_boundary',
              'notice': 'Paired bank-answer accuracy, not learner benefit or causal teaching evidence. No exam, mastery, memory or proposal writes.'}
    if not live_model:
        report['status'] = 'prepared_no_answers_or_scores'
        return report
    totals = {arm: {'correct': 0, 'wrong': 0, 'unknown': 0, 'failed': 0} for arm in ('facts_only', 'legacy', 'prism')}
    for case, (prompt, gold, contexts) in zip(cases, inputs):
        cache = {}
        # Alternate execution order; identical inputs share an output to avoid spurious contrasts.
        arms = ['facts_only', 'legacy', 'prism'] if case['question_id'] % 2 else ['prism', 'legacy', 'facts_only']
        for arm in arms:
            material = {**prompt, 'facts': fact_items, 'memory': contexts[arm]}
            fingerprint = digest(material)
            if fingerprint in cache:
                output = {**cache[fingerprint], 'reused_identical_input': True}
            else:
                began = monotonic()
                try:
                    answer, usage = _call_model(SYSTEM, material, ANSWER_SCHEMA, 512)
                    value = answer['answer']
                    outcome = 'unknown' if value == 'unknown' else 'correct' if value == gold else 'wrong'
                    output = {'answer': value, 'outcome': outcome, 'usage': usage}
                except Exception as exc:
                    output = {'outcome': 'failed', 'error_type': type(exc).__name__}
                output['elapsed_ms'] = round((monotonic() - began) * 1000)
                cache[fingerprint] = output
            case['outputs'][arm] = output
            totals[arm][output['outcome']] += 1
    report.update(status='completed_with_failures' if any(total['failed'] for total in totals.values()) else 'completed',
        totals=totals, answer_key_accuracy={
        arm: total['correct'] / len(cases) for arm, total in totals.items()},
        paired_differences={'prism_minus_legacy': (totals['prism']['correct'] - totals['legacy']['correct']) / len(cases)},
        memory_contrast_cases=sum(case['context_hashes']['legacy'] != case['context_hashes']['prism'] for case in cases),
        answer_model_calls=sum(not row.get('reused_identical_input', False) for case in cases for row in case['outputs'].values()))
    return report
