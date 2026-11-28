"""Ground turn-specific bindings, resolve precedence and gate unresolved plans."""
from ai_assistant.services.state.prism.prism_kernel import digest

FACT_SLOTS = {'呈现方式': 'layout', '讲解深度': 'depth', '材料定位': 'anchor'}
FACT_VALUES = {'图解': 'diagram', '分步算例': 'worked_example', '提示': 'hint',
    '完整讲解': 'full', '关系式': 'formula', '课程时间点': 'timestamp'}


def canonical_bindings(facts, domains):
    rows = []
    for fact in facts:
        key = FACT_SLOTS.get(fact['key'])
        value = FACT_VALUES.get(fact['value'].strip(), fact['value'].strip())
        if fact['memory_type'] in ('preference', 'interaction') and key and value in domains.get(key, []):
            rows.append({'key': key, 'value': value, 'evidence': fact['value'], 'source': 'fact', 'fact_id': fact['id']})
    return rows


def condition_domains(memories):
    result = {}
    for memory in memories:
        for key in memory.fields:
            row = result.setdefault(key, {'values': set(), 'definitions': set()})
            row['definitions'].add(memory.definitions.get(key, ''))
            row['values'].update(case['features'][key] for case in memory.cases if key in case['features'])
    return result


def bindings_for(question, rows, domains, facts=None, frame=None, condition_schema=None):
    if facts is None:
        from ai_assistant.services.memory_core import question_facts
        facts = question_facts(question.user, {'message_id': question.pk, 'bot_id': question.bot_id,
            'conversation_id': str(question.conversation_id)})['items']
    facts = {fact['id']: fact for fact in facts}
    canonical = canonical_bindings(facts.values(), domains)
    for row in canonical:
        row.update(fact_scope='global', conditions=[])
    bound_ids = {row['fact_id'] for row in canonical}
    rows = [row for row in rows if not (row['source'] == 'fact' and row.get('fact_id') in bound_ids)] + canonical
    valid = []
    for row in rows:
        key, value, quote = row['key'], row['value'], row['evidence']
        if value not in domains.get(key, []) or not quote.strip():
            continue
        fact = facts.get(row.get('fact_id'))
        if row['source'] == 'question' and row.get('fact_id') is None and quote in question.content:
            fingerprint, rank = digest(question.content), 0
            condition_text = question.content
        elif row['source'] == 'fact' and fact and quote in f"{fact['key']}：{fact['value']}":
            fingerprint = digest([fact['id'], fact['memory_type'], fact['key'], fact['value'], fact['source']])
            rank = 1 if fact['source'] == 'manual' else 2
            condition_text = f"{fact['key']}：{fact['value']}"
        else:
            continue
        scoped = row['source'] == 'fact' or row.get('fact_scope') == 'conditional'
        if scoped:
            scope, conditions = row.get('fact_scope'), row.get('conditions')
            if scope == 'global' and conditions == []:
                pass
            elif scope == 'conditional' and isinstance(conditions, list) and 0 < len(conditions) <= 4:
                task_digest = digest([question.content, getattr(question, 'metadata', {}).get('course_context')])
                if row.get('task_digest', task_digest) != task_digest:
                    continue
                checked, matches = [], []
                for condition in conditions:
                    evidence = condition.get('evidence', row.get('scope_evidence', ''))
                    schema = (condition_schema or {}).get(condition['key'], {})
                    definitions = schema.get('definitions', set())
                    signature = digest([condition['key'], sorted(definitions)])
                    if (not evidence.strip() or evidence not in condition_text
                            or condition['key'] not in (frame or {}) or condition['operator'] not in ('eq', 'ne')
                            or frame[condition['key']] not in schema.get('values', set())
                            or condition['value'] not in schema.get('values', set()) or len(definitions) != 1
                            or condition.get('schema_digest', signature) != signature):
                        break
                    checked.append({**condition, 'evidence': evidence, 'schema_digest': signature})
                    matches.append((frame[condition['key']] == condition['value']) == (condition['operator'] == 'eq'))
                if len(checked) != len(conditions):
                    continue
                combination = row.get('condition_mode', 'all')
                if combination not in ('all', 'any') or not (all(matches) if combination == 'all' else any(matches)):
                    continue
                conditions = checked
            else:
                continue
        if row.get('source_digest', fingerprint) != fingerprint:
            continue
        binding = {key: row[key] for key in ('key', 'value', 'evidence', 'source', 'fact_id')} | {'source_digest': fingerprint, 'rank': rank}
        if scoped:
            binding.update(fact_scope=scope, conditions=conditions)
            if scope == 'conditional':binding.update(task_digest=task_digest, condition_mode=combination)
        valid.append(binding)
    return valid


def bind_decision(decision, bindings):
    result = {key: dict(value) for key, value in decision.items()}
    for rank in (2, 1, 0):
        slots = {}
        for row in bindings:
            if row['rank'] == rank:
                slots.setdefault(row['key'], {}).setdefault(row['value'], []).append(
                    {'source': row['source'], 'fact_id': row['fact_id'], 'source_digest': row['source_digest'],
                     **({'conditions': row['conditions'], 'condition_mode': row['condition_mode']}
                        if row.get('fact_scope') == 'conditional' else {})})
        for key, values in slots.items():
            for name in ('behavior', 'sources', 'conflicts'):
                result[name].pop(key, None)
            if len(values) == 1:
                result['behavior'][key] = next(iter(values))
                result['sources'][key] = values[result['behavior'][key]]
            else:
                result['conflicts'][key] = values
    return result


def clarification(user, bot, identity):
    from ai_assistant.models import AIChatMessage
    from ai_assistant.services.state.prism.prism_memory import context, mode
    if mode() != 'active' or not identity or not bot or bot.bot_type != 'planner':
        return ''
    question = AIChatMessage.objects.filter(user=user, bot=bot, role='user', pk=identity.get('message_id'),
        conversation_id=identity.get('conversation_id')).select_related('user', 'bot').first()
    if not question:
        return ''
    conflicts = context(question).get('decision', {}).get('conflicts', {})
    metadata = {**question.metadata}
    if conflicts:
        metadata['prism_clarification'] = True
    else:
        metadata.pop('prism_clarification', None)
    if metadata != question.metadata:
        question.metadata = metadata
        question.save(update_fields=['metadata'])
    if not conflicts:
        return ''
    from ai_assistant.services.language import message_language
    english = message_language(question) == 'en'
    names = {'layout': ('呈现方式', 'presentation'), 'depth': ('讲解深度', 'explanation depth'), 'anchor': ('材料定位', 'reference style')}
    labels = {'diagram': ('图解', 'a diagram'), 'worked_example': ('分步算例', 'a worked example'),
        'hint': ('提示', 'hints'), 'full': ('完整讲解', 'a full explanation'),
        'formula': ('关系式', 'the formula'), 'timestamp': ('课程时间点', 'a course timestamp')}
    index = int(english)
    options = ['{}：{}'.format(names.get(key, ('讲解安排', 'explanation'))[index],
        ' / '.join(labels.get(value, (value, value))[index] for value in values)) for key, values in conflicts.items()]
    return ("I have different preferences recorded for this task. Which would you like this time?\n" if english else
        '这次任务有不同的有效讲解约定。你希望这次采用哪一种？\n') + '\n'.join(options)
