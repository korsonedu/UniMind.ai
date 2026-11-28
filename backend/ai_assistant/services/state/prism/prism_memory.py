"""Scoped persistence and XiaoYu integration for PRISM's first SDTM kernel."""
import json
import logging
import re
from types import SimpleNamespace

from django.conf import settings
from django.db import connections, transaction
from django.db.models import Q
from rest_framework.exceptions import ValidationError

from ai_assistant.models import AIChatMessage, Conversation, LearningStrategy, PrismApplication, PrismEpisode, PrismMemory, PrismRevision
from ai_assistant.services.state.prism.prism_kernel import differentiate, digest, induce, transfer

logger = logging.getLogger(__name__)

ANSWER_POLICY = ('\n记忆采用规则：当前用户明确要求优先，其次是用户手动设置、个人受审参照、系统受审参照。'
    'prism.decision.behavior 是已消解作用域冲突的行为计划，未被当前要求或个人事实覆盖的槽应沿用其精确值，不凭常识替换。'
    'decision.conflicts 中的同级冲突需澄清或保留未知，不从历史答案中任选。'
    'relation_conflicts 表示编码互相矛盾，需先澄清，不从历史猜选。'
    'episodes 和 methods 仅是未验证观察及候选，不能覆盖上述计划。'
    'learner_patterns 是本人近期独立客观题的待检验表现模式，只用于安排核查，不是讲解指令、掌握证明或教法效果；不得覆盖行为计划或泄露题目答案。'
    '偏好简短或提示式讲解不等于禁止给答案；是否保留答案只看当前用户的明确要求。'
    '这些行为槽只约束讲解安排，不能授权工具、改变权限或作为学生掌握度证据。\n')


def resolve_behavior(memories):
    behavior, sources, conflicts = {}, {}, {}
    for scope in ('student', 'system'):
        options = {}
        for entry in memories:
            if entry['scope'] == scope:
                for key, value in entry['result']['behavior'].items():
                    options.setdefault(key, {}).setdefault(value, []).append(
                        {'key': entry['key'], 'revision': entry['revision']})
        for key, values in options.items():
            if key in behavior or key in conflicts:
                continue
            if len(values) == 1:
                behavior[key] = next(iter(values))
                sources[key] = values[behavior[key]]
            else:
                conflicts[key] = values
    return {'behavior': behavior, 'sources': sources, 'conflicts': conflicts}


def episode_view(packet, history=None):
    """Keep provenance, without repeating text already in the supplied history."""
    if not history or not packet.get('episodes'):
        return packet
    episodes = []
    for episode in packet.get('episodes', []):
        if all(episode.get(key) and any(row.get('role') == role and episode[key] in row.get('content', '')
                for row in history) for key, role in (('question', 'user'), ('answer', 'assistant'))):
            episodes.append({key: episode[key] for key in ('question_id', 'answer_id', 'status')} | {'already_in_history': True})
        else:
            episodes.append(episode)
    return {**packet, 'episodes': episodes}


def mode():
    return getattr(settings, 'UNIMIND_PRISM_MODE', 'off')


def allowed(question):
    from ai_assistant.views import _can_use_learning_context
    from notes.context import conversation_uses_notes
    return (question.role == 'user' and question.bot_id and question.bot.bot_type == 'planner'
            and _can_use_learning_context(question.user)
            and not conversation_uses_notes(question.user, question.conversation_id))


def accessible(question):
    if not allowed(question):
        return False
    course = question.metadata.get('course_context')
    if course:
        from courses.access import visible_courses
        request = SimpleNamespace(user=question.user, query_params={})
        return visible_courses(request).filter(pk=course['course_id']).exists()
    return True


def grounded(rows, text, *, context=''):
    result = {}
    for row in rows[:16]:
        key, value, quote = row['key'], row['value'], row['evidence']
        if (re.fullmatch('[a-z][a-z0-9_]{0,47}', key) and 0 < len(value) <= 240
                and quote.strip() and (quote in text or quote in context)):
            result[key] = value
    return result


def extract(question, answer=None):
    from ai_assistant.services.dsh_tasks import run_structured
    from ai_assistant.services.state.prism.prism_feedback import previous_episode
    if not accessible(question):
        return {'features': {}, 'behavior': {}, 'verified': False}
    course = question.metadata.get('course_context') or {}
    material = '\n'.join(str(segment.get('text', '')) for segment in course.get('segments', []))[:1200]
    from ai_assistant.services.state.prism.prism_mapping import memory_groups
    groups = memory_groups(question.user)
    checked = list(checked_memories(question.user, [memory for memory, _ in groups]))
    definitions, values, behavior_values = {}, {}, {}
    for memory in checked:
        for case in memory.cases:
            for key, value in case['behavior'].items():
                behavior_values.setdefault(key, set()).add(value)
        for key in memory.fields:
            if key not in definitions:
                definitions[key] = memory.definitions.get(key, '')[:120]
                values[key] = set()
            values[key].update(case['features'][key] for case in memory.cases
                              if key in case['features'] and len(case['features'][key]) <= 60)
    schema_fields = list(definitions)[:24]
    previous = previous_episode(question)
    if previous and not accessible(previous.question):
        previous = None
    known_values = {key: sorted(values[key], key=lambda value: (
        re.search(r'(?<![A-Za-z0-9_-])' + re.escape(value) + r'(?![A-Za-z0-9_-])',
                  question.content + '\n' + material) is None, value))[:4] for key in schema_fields[:8]}
    aliases = []
    for _, mappings in groups:
        for row in mappings:
            alias = {key: row.payload[key] for key in ('source_field', 'target_field', 'values')}
            if alias not in aliases:
                aliases.append(alias)
    aliases = aliases[:8]
    from ai_assistant.services.memory_core import question_facts
    snapshot = question_facts(question.user, {'message_id': question.pk, 'bot_id': question.bot_id,
        'conversation_id': str(question.conversation_id)})
    binding_facts = [{key: row[key] for key in ('id', 'memory_type', 'key', 'value', 'source')} for row in snapshot['items']]
    known_behaviors = {key: sorted(values)[:8] for key, values in list(behavior_values.items())[:8]}
    from ai_assistant.services.decision.prism_gate import canonical_bindings
    canonical_ids = {row['fact_id'] for row in canonical_bindings(binding_facts, known_behaviors)}
    signature = digest([question.content, material, schema_fields, {key: definitions[key] for key in schema_fields[:8]}, known_values, aliases,
        known_behaviors, snapshot['version']])
    application = PrismApplication.objects.filter(question=question).first() if answer else None
    prepared = application.result.get('prepared') if application else None
    if not prepared or prepared.get('input_digest') != signature:
        prepared = None
    pending = PrismEpisode.objects.filter(question=question).first() if answer else None
    from ai_assistant.services.fact_evidence import active as task_memory_active
    collect_facts = bool(pending and pending.observation.get('collect_facts')) and not task_memory_active()
    from ai_assistant.services.memory_core import active_facts
    known_facts = list(active_facts(question.user).values('id', 'memory_type', 'key')[:20]) if collect_facts else []
    prompt = json.dumps({'question': question.content[:2500], 'material': material,
                         'answer': answer.content[:2500] if answer else '',
                         'known_fields': schema_fields,
                         'known_relations': {key: definitions[key] for key in schema_fields[:8]},
                         'known_values': known_values,
                         'known_behaviors': known_behaviors,
                         **({'binding_facts': [fact for fact in binding_facts if fact['id'] not in canonical_ids]} if not prepared else {}),
                         **({'known_aliases': aliases} if aliases else {}),
                         **({'prepared_features': prepared['features'] if prepared else None,
                             'collect_facts': collect_facts, 'known_fact_keys': known_facts} if answer else {}),
                         'previous': {'question': previous.question.content[:1000],
                                      'answer': previous.answer.content[:1000],
                                      'features': {key: str(value)[:80] for key, value in
                                                   list(previous.observation.get('features', {}).items())[:8]}} if previous else None},
                        ensure_ascii=False)
    result = run_structured('assistant.prism_complete' if answer and mode() == 'active' else 'assistant.prism_observe', prompt,
                            reuse_prepared=bool(prepared))
    rows = prepared['evidence']['features'] if prepared else result['features']
    features = grounded(rows, question.content, context=material)
    feature_sources = {row['key']: 'question' if row['evidence'] in question.content else 'course'
                       for row in rows if row['key'] in features and row['evidence'].strip()
                       and (row['evidence'] in question.content or row['evidence'] in material)}
    facts = []
    for row in result.get('memories', []) if collect_facts else []:
        if row.get('temporal_scope') != 'enduring':
            continue
        reference = row.get('existing_id')
        if reference is not None and reference not in {fact['id'] for fact in known_facts}:
            continue
        facts.append({**row, **({'_existing_id': reference} if reference is not None else {})})
    from ai_assistant.services.decision.prism_gate import bindings_for, condition_domains
    bindings = bindings_for(question, prepared.get('bindings', []) if prepared else result.get('bindings', []), known_behaviors, binding_facts,
                            features, condition_domains(checked))
    return {'features': features, 'feature_sources': feature_sources, 'bindings': bindings,
            'behavior': grounded(result['behavior'], answer.content) if answer else {},
            'evidence': {**result, 'features': rows}, 'verified': False, 'input_digest': signature,
            'reused_features': bool(prepared), 'collect_facts': collect_facts,
            'memories': facts,
            'feedback': result.get('feedback', {}), 'previous_episode_id': previous.pk if previous else None}


def visible_memories(user):
    return PrismMemory.objects.filter(Q(scope='system', owner__isnull=True) |
                                      Q(scope='student', owner=user), active=True).order_by('scope', 'key')


def checked_memories(user, candidates=None):
    from ai_assistant.services.state.prism.prism_migration import validate_origin
    for memory in visible_memories(user) if candidates is None else candidates:
        if memory.provenance.get('kind') == 'objective_outcomes':
            continue
        try:
            validate_origin(memory)
        except ValidationError:
            continue
        cases = [case for case in memory.cases if case.get('verified') is True]
        if len(cases) != len(memory.cases):
            continue
        source_ids = [case['source_message_id'] for case in cases if case.get('source_message_id')]
        sources = list(AIChatMessage.objects.filter(pk__in=source_ids, user=user).select_related('user', 'bot'))
        if memory.scope == 'system' and source_ids:
            continue
        if len(sources) != len(set(source_ids)) or any(not accessible(source) for source in sources):
            continue
        yield memory


def method_candidates(question, frame):
    """Reference the owned method library; never copy candidates into verified cases."""
    from ai_assistant.services.teaching_sidecar import canonical_hash, method_snapshot
    text = ' '.join([question.content, *frame.values()]).casefold()
    rows = LearningStrategy.objects.filter(user=question.user, is_retired=False,
        source_event__project__user=question.user, source_event__message__user=question.user,
        source_event__message__role='user').select_related(
            'source_event__message__user', 'source_event__message__bot').order_by('-id')[:24]
    scored = []
    for row in rows:
        source = row.source_event.message
        score = sum(bool(value.strip()) and value.casefold() in text for value in (row.domain, row.topic))
        method = str(row.source_event.content.get('strategy', '')).strip()
        if not score or not method or not accessible(source):
            continue
        entry = {'id': row.pk, 'revision': row.revision, 'source_message_id': source.pk,
                 'version': canonical_hash(method_snapshot(row)),
                 'method': method[:1000], 'domain': row.domain, 'topic': row.topic,
                 'status': 'candidate_not_verified'}
        scored.append((score, entry))
    return [entry for _, entry in sorted(scored, key=lambda item: (-item[0], -item[1]['id']))[:3]]


def packet_for(question, frame, bindings=None):
    from ai_assistant.services.state.prism.prism_mapping import memory_groups, mapped_frame, mapping_version
    from ai_assistant.services.decision.prism_gate import bindings_for, bind_decision, condition_domains
    groups = memory_groups(question.user)
    checked = list(checked_memories(question.user, [memory for memory, _ in groups]))
    memories, candidates, relation_conflicts, domains = [], [], [], {}
    for memory, mappings in groups:
        if memory in checked:
            for case in memory.cases:
                for key, value in case['behavior'].items():
                    domains.setdefault(key, set()).add(value)
        target, conflict = mapped_frame(memory, mappings, frame)
        if conflict:
            relation_conflicts.append(memory.key)
        elif memory.fields and all(key in target and target[key] in {
                case['features'].get(key) for case in memory.cases} for key in memory.fields):
            candidates.append((memory, mappings, target))
    candidates.sort(key=lambda item: (item[0].scope != 'student', -len(item[0].fields), item[0].key))
    attempts = 0
    for memory, mappings, target in candidates:
        if not list(checked_memories(question.user, [memory])):
            continue
        if attempts == 8:
            break
        attempts += 1
        source_ids = [case['source_message_id'] for case in memory.cases if case.get('source_message_id')]
        result = transfer(memory.cases, memory.fields, target, memory.operators)
        if result['status'] == 'matched':
            entry = {'key': memory.key, 'revision': memory.revision, 'scope': memory.scope,
                     'result': {key: result[key] for key in ('source', 'behavior', 'operators')},
                     'source_message_ids': source_ids}
            if mappings:
                entry.update(mapping_version=mapping_version(mappings), alias_count=len(mappings))
            if len(json.dumps([*memories, entry], ensure_ascii=False)) <= 6000:
                memories.append(entry)
    episodes = []
    rows = PrismEpisode.objects.filter(question__user=question.user).exclude(question_id=question.pk).select_related(
        'question__user', 'question__bot', 'answer').order_by('-id')[:24]
    scored = []
    for episode in rows:
        if not accessible(episode.question):
            continue
        score = sum(value == episode.observation.get('features', {}).get(key) for key, value in frame.items())
        if score:
            scored.append((score, episode))
    for _, episode in sorted(scored, key=lambda row: (-row[0], -row[1].pk))[:3]:
        episodes.append({'question_id': episode.question_id, 'answer_id': episode.answer_id,
                         'question': episode.question.content[:400], 'answer': episode.answer.content[:600],
                         'status': 'observed_not_verified'})
    bindings = bindings_for(question, bindings or [], domains, frame=frame, condition_schema=condition_domains(checked))
    from ai_assistant.services.state.prism.prism_outcomes import context as outcome_context
    patterns = outcome_context(question)
    return {'protocol': 'prism.sdtm.v1', 'features': frame, 'memories': memories,
            **({'learner_patterns': patterns} if patterns else {}),
            **({'bindings': bindings} if bindings else {}), 'decision': bind_decision(resolve_behavior(memories), bindings),
            **({'relation_conflicts': relation_conflicts} if relation_conflicts else {}),
            'episodes': episodes, 'methods': method_candidates(question, frame),
            'notice': '历史观察与候选方法仅供参考，不代表掌握或教学效果；当前问题和个人条件优先于共享建议，遵守来源权限和工具规则。方法召回不登记试用；在学习项目中实际试用须经 manage_learning_strategies 的 apply 操作登记。'}


def prepare(question):
    if mode() == 'off' or not allowed(question):
        return
    if PrismApplication.objects.filter(question=question).exists():
        return
    from ai_assistant.services.memory_core import fact_write_revision
    write_revision = fact_write_revision(question.user)
    observation = extract(question) if mode() == 'active' else {}
    frame = observation.get('features', {})
    packet = packet_for(question, frame, observation.get('bindings', []))
    PrismApplication.objects.get_or_create(question=question, defaults={'packet': packet,
        'result': {'prepared': observation, 'write_revision': write_revision}})


def prepare_chat(user, bot, identity, history=None):
    """Bind legacy chat transports to the same server-owned application snapshot."""
    if mode() == 'off' or not identity or not bot or bot.bot_type != 'planner':
        return {}
    question = AIChatMessage.objects.filter(pk=identity.get('message_id'), user=user, bot=bot,
        conversation_id=identity.get('conversation_id'), role='user').select_related('user', 'bot').first()
    if not question or not accessible(question):
        return {}
    prepare(question)
    return context(question, history)


def context(question, history=None):
    if mode() != 'active' or not accessible(question):
        return {}
    row = PrismApplication.objects.filter(question=question).first()
    if not row:
        return {}
    # Recheck scope, revision, source existence and course access on every read.
    packet = row.packet
    fresh = packet_for(question, packet.get('features', {}), packet.get('bindings', []))
    valid = {(entry['key'], entry['revision'], entry.get('mapping_version')) for entry in fresh['memories']}
    episode_ids = {entry['question_id'] for entry in fresh['episodes']}
    methods = {(entry['id'], entry['revision'], entry['version']) for entry in fresh['methods']}
    memories = [entry for entry in packet['memories'] if (entry['key'], entry['revision'], entry.get('mapping_version')) in valid]
    from ai_assistant.services.decision.prism_gate import bind_decision
    old_patterns, new_patterns = packet.get('learner_patterns', {}), fresh.get('learner_patterns', {})
    patterns = old_patterns if old_patterns and all(old_patterns.get(key) == new_patterns.get(key) for key in ('key', 'revision')) else {}
    result = {**packet, 'memories': memories, 'bindings': fresh.get('bindings', []), 'learner_patterns': patterns,
            'decision': bind_decision(resolve_behavior(memories), fresh.get('bindings', [])),
            'relation_conflicts': fresh.get('relation_conflicts', []),
            'episodes': [entry for entry in packet['episodes'] if entry['question_id'] in episode_ids],
            'methods': [entry for entry in packet.get('methods', []) if (entry['id'], entry['revision'], entry['version']) in methods]}
    return episode_view(result, history)


def observe_completion(question_id, answer_id):
    try:
        question = AIChatMessage.objects.select_related('user', 'bot').filter(pk=question_id).first()
        answer = AIChatMessage.objects.filter(pk=answer_id, user_id=question.user_id if question else None,
                                              conversation_id=question.conversation_id if question else None,
                                              bot_id=question.bot_id if question else None,
                                              role='assistant').first()
        if mode() == 'off' or not question or not answer or not accessible(question):
            return
        existing = PrismEpisode.objects.filter(question=question).first()
        if existing and existing.observation.get('status') != 'pending':
            return
        observation = extract(question, answer)
        with transaction.atomic():
            # Fact writers lock the conversation before the question, consistently
            # with conversation deletion and the standalone extraction path.
            Conversation.objects.select_for_update().filter(user=question.user, conversation_id=question.conversation_id).first()
            current = AIChatMessage.objects.select_for_update().filter(pk=question_id).first()
            if not current or not AIChatMessage.objects.filter(pk=answer_id).exists() or not accessible(current):
                return
            stored = PrismEpisode.objects.filter(question=current).first()
            if stored and stored.observation.get('status') != 'pending':
                return
            if observation.get('collect_facts'):
                from ai_assistant.services.memory_service import store_extracted_facts
                observation['facts_saved'] = store_extracted_facts(current.user, observation.get('memories', []),
                    current.content, str(current.conversation_id), existing.observation['write_revision'],
                    source_message_id=current.pk)
            episode, created = PrismEpisode.objects.get_or_create(question=current,
                defaults={'answer': answer, 'observation': observation})
            if not created and episode.observation.get('status') == 'pending':
                episode.observation = observation
                episode.save(update_fields=['observation'])
            from ai_assistant.services.state.prism.prism_feedback import propose_relations
            proposals = propose_relations(current, observation)
            application, _ = PrismApplication.objects.get_or_create(question=current)
            # Shadow proposals are stored, never injected into the answer.
            update = {'answer_id': answer_id, 'observation': observation, 'proposal_ids': proposals}
            if mode() == 'shadow':
                update['shadow_packet'] = packet_for(current, observation['features'])
            application.result = {**application.result, **update}
            application.save(update_fields=['result'])
    except Exception:
        logger.exception('PRISM observation failed for message %s', question_id)
    finally:
        connections.close_all()


def schedule(question, answer):
    if mode() != 'off' and allowed(question):
        if (answer.role != 'assistant' or answer.user_id != question.user_id
                or answer.bot_id != question.bot_id or answer.conversation_id != question.conversation_id):
            raise ValidationError('PRISM completion must belong to the same learner, bot and conversation.')
        # Bind raw evidence before dispatch: the next question need not wait for
        # the previous background model call to complete.
        from ai_assistant.services.memory_core import fact_write_revision
        application = PrismApplication.objects.filter(question=question).first()
        from ai_assistant.services.fact_evidence import active as task_memory_active
        collect_facts = (not task_memory_active() and mode() == 'active'
            and (answer.metadata.get('engine') != 'dsh' or getattr(settings, 'UNIMIND_DSH_MEMORY_ENABLED', False)))
        revision = application.result.get('write_revision') if application else None
        if revision is None:
            revision = fact_write_revision(question.user)
        _, created = PrismEpisode.objects.get_or_create(question=question, defaults={'answer': answer, 'observation': {
            'status': 'pending', 'verified': False, 'collect_facts': collect_facts, 'write_revision': revision}})
        if created:
            from ai_assistant.utils import _THREAD_POOL
            _THREAD_POOL.submit(observe_completion, question.pk, answer.pk)


def refine(memory_id, expected_revision, training, validation, *, candidate_fields=None, definition=None):
    """Trusted replay entry point; learner/model observations cannot certify cases."""
    with transaction.atomic():
        memory = PrismMemory.objects.select_for_update().get(pk=memory_id)
        from ai_assistant.services.state.prism.prism_migration import validate_origin
        validate_origin(memory)
        if memory.revision != expected_revision:
            raise ValidationError('PRISM memory revision changed.')
        report = differentiate(training, validation, memory.fields, candidate_fields=candidate_fields)
        accepted = report['selected'] is not None
        PrismRevision.objects.create(memory=memory, before={
            'fields': memory.fields, 'cases': memory.cases, 'operators': memory.operators,
            'definitions': memory.definitions, 'active': memory.active,
            'provenance': memory.provenance,
            'revision': memory.revision},
            report=report, accepted=accepted)
        if accepted:
            memory.fields = report['selected']['fields']
            if definition:
                memory.definitions = {**memory.definitions, report['selected']['added']: definition}
            memory.cases = training
            memory.operators = induce(training, memory.fields)
            memory.active = True
            memory.revision += 1
            memory.save(update_fields=['fields', 'definitions', 'cases', 'operators', 'active', 'revision', 'updated_at'])
        return report


def safely(function, *args):
    try:
        return function(*args)
    except Exception:
        logger.exception('PRISM integration failed: %s', function.__name__)
        return None
