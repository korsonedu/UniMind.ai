"""L1 Fact Layer — live source reads, provenance dependency checks, pagination and node view records."""

import re
from itertools import zip_longest
from json import dumps
from math import isfinite, log1p
from types import SimpleNamespace
from uuid import UUID

from django.db import transaction
from django.db.models import Case, Count, FloatField, IntegerField, OuterRef, Q, Subquery, Value, When
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from ai_assistant.models import (
    AIChatMessage, Conversation, LearningKnowledgeVersion, ProjectLearning, ProjectLearningEvent,
)
from courses.access import visible_courses
from courses.models import VideoProgress
from users.feature_access import has_learning_feature
from users.workspaces.access import membership_for


HISTORY_LOOKUP_MAX_TOPICS = 3

SOURCE_TOOL = {
    'name': 'read_learning_source',
    'description': '按来源读取旧问答、课程讲稿和播放位置、练习原作答及批改，或翻页查练习、错题与复习历史。'
                   '历史线索分散时，可用 conversation_history 和 topics 在一次调用中分别查找并读取相邻原文。用 next_offset 继续读取单个来源。',
    'inputSchema': {'type': 'object', 'properties': {
        'source': {'type': 'string', 'maxLength': 80, 'description': '例如 exam:42、answer:42、course:42、conversation:<UUID>、message:42，'
                   '或 practice、wrong_answers、review_history、conversation_history'},
        'topic': {'type': 'string', 'maxLength': 120, 'description': '可选的关键词，用来查讲稿和历史记录'},
        'topics': {'type': 'array', 'minItems': 1, 'maxItems': HISTORY_LOOKUP_MAX_TOPICS,
                   'items': {'type': 'string', 'minLength': 1, 'maxLength': 120},
                   'description': '仅用于 conversation_history。不与 topic 或 offset 同时使用。每项填写一条独立线索，例如不同的人、事件或缺失事实。'},
        'offset': {'type': 'integer', 'minimum': 0, 'maximum': 1000000},
        'start_seconds': {'type': 'number', 'minimum': 0, 'maximum': 10000000, 'description': '仅用于课程，从视频指定时间附近读讲稿'},
    }, 'required': ['source'], 'additionalProperties': False},
    'annotations': {'readOnlyHint': True, 'openWorldHint': False},
}

HISTORY_STOP_WORDS = frozenset(
    'a an and are as at be been being but by can could did do does for from had has have he her him his how i if '
    'in into is it its me my of on or our she that the their them then there these they this to us was we were '
    'what when where which who why will with would you your d ll m re s t ve'.split()
)
HISTORY_PAGE_SIZE = 8
HISTORY_LOOKUP_MAX_ENTRIES = 32
HISTORY_LOOKUP_MAX_BYTES = 16_384


def _matching(rows, words, *fields):
    if not words:
        return rows
    clauses = Q()
    for word in words:
        for field in fields:
            clauses |= Q(**{f'{field}__icontains': word})
    return rows.filter(clauses)


def _ranked_history(rows, topic):
    words = re.findall(r'[^\W_]+', topic.casefold())
    terms = [word for word in words if word not in HISTORY_STOP_WORDS] or words
    terms = list(dict.fromkeys(terms))[:12]
    if not terms:
        return rows.order_by('-pk'), ()

    filters = {f'term_{index}': Q(content__icontains=term) for index, term in enumerate(terms)}
    counts = rows.aggregate(total=Count('pk'), **{name: Count('pk', filter=match) for name, match in filters.items()})
    ranked = sorted(((counts[name], name, term) for name, term in zip(filters, terms, strict=True) if counts[name]),
                    key=lambda match: match[0])
    if not ranked:
        return rows.none(), ()

    matches = Q()
    score = Value(0.0)
    for count, name, _ in ranked:
        match = filters[name]
        matches |= match
        weight = log1p((counts['total'] - count + 0.5) / (count + 0.5))
        score += Case(When(match, then=Value(weight)), default=Value(0.0), output_field=FloatField())
    return rows.filter(matches).order_by(score.desc(), '-pk'), tuple(term for _, _, term in ranked)


def _excerpt(text, words, limit=800):
    match = re.search('|'.join(re.escape(word) for word in words), text, re.IGNORECASE) if words else None
    begin = max(0, match.start() - 160) if match else 0
    return {'excerpt': text[begin:begin + limit], 'excerpt_start': begin}


def last_viewed_node(project, version):
    if version is None:
        return None
    event = project.learning_events.filter(kind='knowledge_view').first()
    if not event:
        return None
    original = event.content
    node = next((row for row in version.snapshot['nodes'] if row['id'] == original['node_id']), None)
    if not node:
        return None
    if original['version_id'] != version.pk:
        from ai_assistant.services.state.knowledge.learning_continuity import signatures
        if (original['map_id'] != version.knowledge_map_id
                or original['definition'] != signatures(version.snapshot).get(node['id'])):
            return None
    return {'source': f'event:{event.pk}', 'at': event.created_at, 'node_id': node['id'], 'title': node['title'],
            'version_id': version.pk, 'original_version_id': original['version_id']}


@transaction.atomic
def remember_view(project, version_id, node_id):
    from ai_assistant.services.state.knowledge.learning_continuity import signatures
    state = ProjectLearning.objects.select_for_update().filter(project=project).first()
    if not state or (state.plan.get('knowledge_path') or {}).get('version_id') != version_id:
        raise ValidationError('知识结构已更新，请刷新后再查看。')
    version = LearningKnowledgeVersion.objects.filter(pk=version_id, knowledge_map__user=project.user).first()
    definition = signatures(version.snapshot).get(node_id) if version else None
    if not definition:
        raise ValidationError('该节点不在项目的知识结构中。')
    value = {'version_id': version_id, 'node_id': node_id, 'map_id': version.knowledge_map_id, 'definition': definition}
    previous = project.learning_events.filter(kind='knowledge_view').first()
    if not previous or previous.content != value:
        ProjectLearningEvent.objects.create(project=project, kind='knowledge_view', content=value)


@transaction.atomic
def record_recall_sources(message, result):
    course_ids = {int(row['source'].split(':', 1)[1]) for row in result.get('course_progress', [])}
    if course_id := result.get('course_id'):
        course_ids.add(course_id)
    course_ids.update(result.get('course_dependencies', []))
    course_ids.update(row['course_segment']['course_id'] for row in result.get('conversation', [])
                      if row.get('course_segment', {}).get('course_id') is not None)
    from ai_assistant.services.facts.learning_practice_memory import PRACTICE_SOURCES
    source = result.get('source', '')
    practice_used = (source in PRACTICE_SOURCES or source.startswith(('exam:', 'answer:', 'wrong:', 'review:'))
                     or result.get('practice_dependency') or any(row['items'] for row in result.get('practice_sources', [])))
    if not result.get('notes') and not course_ids and not practice_used:
        return
    question = AIChatMessage.objects.select_for_update().get(pk=message.pk, user_id=message.user_id, role='user')
    if result.get('notes'):
        question.metadata['notes_context_used'] = True
    if practice_used:
        question.metadata['learning_practice_used'] = True
    if course_ids:
        prior = question.metadata.get('learning_recall_courses', [])
        question.metadata['learning_recall_courses'] = sorted(course_ids.union(prior))
    question.save(update_fields=['metadata'])


def _scope(project, learner):
    if not learner.is_active or (project and project.user_id != learner.pk):
        raise PermissionDenied('无权读取这个学习项目。')
    membership_for(learner)
    visible = visible_courses(SimpleNamespace(user=learner, query_params={}))
    return visible, AIChatMessage.objects.filter(user=learner)


def _project_scope(project, learner, state, visible, messages):
    rooms = Conversation.objects.filter(user=learner, project=project)
    messages = messages.filter(conversation_id__in=rooms.values('conversation_id'))
    attached_ids = [int(match[1]) for row in (state.resources if state else [])
                    if (match := re.fullmatch(r'/course/(\d+)', row.get('url') or ''))]
    # PostgreSQL JSONB and integer columns do not support a direct IN comparison.
    course_ids = messages.filter(role='user', metadata__has_key='course_context').annotate(
        course_key=Cast(KeyTextTransform.from_lookup('metadata__course_context__course_id'), IntegerField()),
    ).values('course_key')
    links = project.memory_sources.all()
    courses = visible.filter(Q(pk__in=course_ids) | Q(pk__in=attached_ids) |
                             Q(pk__in=links.filter(course__isnull=False).values('course_id')))
    return rooms, messages, courses


def _readable_history(messages, visible, courses, current_message, include_practice):
    course_messages = messages.annotate(
        course_key=Cast(KeyTextTransform.from_lookup('metadata__course_context__course_id'), IntegerField()),
    )
    blocked_courses = course_messages.filter(course_key__isnull=False).exclude(course_key__in=visible.values('pk'))
    dependencies = list(messages.filter(metadata__has_key='learning_recall_courses').values_list(
        'conversation_id', 'metadata__learning_recall_courses'))
    usable_courses = set(courses.filter(pk__in={pk for _, ids in dependencies for pk in ids}).values_list('pk', flat=True))
    blocked_recalls = {room for room, ids in dependencies if set(ids) - usable_courses}
    history = messages.filter(role__in=['user', 'assistant']).exclude(
        Q(conversation_id__in=messages.filter(Q(metadata__notes_context_used=True) |
          Q(metadata__ulr_context_sources__notes__0__isnull=False) |
          Q(metadata__ulr_context_sources__selection=True)).values('conversation_id')) |
        Q(conversation_id__in=blocked_courses.values('conversation_id')) |
        Q(conversation_id__in=blocked_recalls),
    )
    if not include_practice:
        history = history.exclude(conversation_id__in=messages.filter(metadata__learning_practice_used=True).values('conversation_id'))
    return history.exclude(pk=current_message.pk) if current_message is not None else history


def _current_sources(learner, row):
    engine = row.metadata.get('engine')
    if row.role != 'assistant' or engine not in ('ulr', 'dsh'):
        return True
    from ai_assistant.services.runtime.ulr_history import require_receipt_sources
    try:
        require_receipt_sources(learner, {'done': True, 'engine': engine, 'message_id': row.pk})
    except (PermissionDenied, ValidationError):
        return False
    return True


def _message_record(row, offset=0, limit=800, *, search_terms=()):
    if len(row.content) > limit:
        for term in search_terms:
            if match := re.search(re.escape(term), row.content, re.IGNORECASE):
                offset = max(0, match.start() - 160)
                break
    entry = {'source': f'message:{row.pk}', 'conversation_id': str(row.conversation_id),
             'role': row.role, 'text': row.content[offset:offset + limit], 'at': row.timestamp}
    if search_terms and offset:
        entry['excerpt_start'] = offset
    if course := row.metadata.get('course_context'):
        entry['course_segment'] = {key: course.get(key) for key in ('course_id', 'video_seconds', 'revision')}
        entry['course_segment']['excerpt'] = ' '.join(item.get('text', '') for item in course.get('segments', [])[:2])[:700]
    if activity := row.metadata.get('learning_activity'):
        entry['learning_reference'] = {key: activity[key] for key in ('version_id', 'node_id') if key in activity}
    if row.role == 'assistant':
        entry['question_id'] = row.metadata.get('learning_turn', {}).get('message_id')
    return entry


def _history_dependencies(messages, items):
    rooms = {item['conversation_id'] for item in items if item['conversation_id']}
    sources = messages.filter(conversation_id__in=rooms).filter(
        Q(metadata__has_key='course_context') | Q(metadata__has_key='learning_recall_courses') |
        Q(metadata__learning_practice_used=True),
    ).values_list('metadata__course_context__course_id', 'metadata__learning_recall_courses', 'metadata__learning_practice_used')
    ids = set()
    practice = False
    for course_id, dependencies, practice_used in sources:
        if course_id is not None:
            ids.add(int(course_id))
        ids.update(dependencies or [])
        practice = practice or bool(practice_used)
    return {'course_dependencies': sorted(ids), 'practice_dependency': practice}


def _history_evidence(history, learner, topics):
    ranked_queries = []
    for topic in topics:
        ranked, terms = _ranked_history(history, topic)
        hits = [row for row in ranked[:HISTORY_PAGE_SIZE] if _current_sources(learner, row)][:4]
        ranked_queries.append([(row, terms) for row in hits])
    anchors = {}
    for group in zip_longest(*ranked_queries):
        for hit in group:
            if hit is not None:
                anchors.setdefault(hit[0].pk, hit)
    if not anchors:
        return []

    same_room = history.filter(conversation_id=OuterRef('conversation_id'))
    before = same_room.filter(pk__lt=OuterRef('pk')).order_by('-pk').values('pk')[:1]
    after = same_room.filter(pk__gt=OuterRef('pk')).order_by('pk').values('pk')[:1]
    adjacent = history.filter(pk__in=anchors).annotate(
        previous_pk=Subquery(before), next_pk=Subquery(after),
    ).values_list('previous_pk', 'next_pk')
    neighbor_ids = {pk for pair in adjacent for pk in pair if pk is not None and pk not in anchors}
    neighbors = history.in_bulk(neighbor_ids)

    entries = {}
    remaining = HISTORY_LOOKUP_MAX_BYTES
    candidates = [*anchors.values(), *((neighbors[pk], ()) for pk in sorted(neighbors)
                                      if _current_sources(learner, neighbors[pk]))]
    for row, terms in candidates:
        entry = _message_record(row, limit=480, search_terms=terms)
        size = len(dumps(entry, ensure_ascii=False, default=str).encode()) + 2
        if size <= remaining:
            entries[row.pk] = entry
            remaining -= size
        if len(entries) == HISTORY_LOOKUP_MAX_ENTRIES:
            break
    return [entries[pk] for pk in sorted(entries)]


def _text_page(text, offset):
    return {'text': text[offset:offset + 4000], 'next_offset': offset + 4000 if len(text) > offset + 4000 else None}


def _read_course(course, learner, words, offset, start_seconds):
    progress = VideoProgress.objects.filter(course=course, user=learner).first()
    position = progress.last_position if progress else None
    link_time = start_seconds if start_seconds is not None else position
    href = f'/course/{course.pk}' + (f'?t={link_time:g}' if link_time is not None else '')
    transcript = getattr(course, 'transcript', None)
    result = {'source': f'course:{course.pk}', 'course_id': course.pk, 'title': course.title, 'href': href,
              'position_seconds': position, 'transcript_status': transcript.asr_status if transcript else 'not_available',
              'materials': [{'kind': kind, 'href': f'/course/{course.pk}'} for kind in ('courseware', 'reference_materials')
                            if getattr(course, kind)]}
    if not transcript or transcript.asr_status != 'completed':
        return result
    result.update(transcript_id=transcript.pk, revision=transcript.revision)
    rows = transcript.segments.all()
    if not rows.exists():
        text = transcript.full_text
        if words:
            text = text[_excerpt(text, words)['excerpt_start']:]
        return {**result, **_text_page(text, offset)}
    if start_seconds is not None:
        rows = rows.filter(end_time__gte=start_seconds)
    segments = list(_matching(rows, words, 'text').order_by('index', 'pk').values('index', 'start_time', 'end_time', 'text')[offset:offset + 9])
    return {**result, 'segments': segments[:8], 'next_offset': offset + 8 if len(segments) > 8 else None}


def read_learning_source(project, learner, source, topic='', offset=0, start_seconds=None, *,
                         topics=None, current_message=None, include_practice=False):
    if start_seconds is not None and not isfinite(start_seconds):
        raise NotFound('时间位置无效。')
    if topics is not None and (source != 'conversation_history' or topic or offset or start_seconds is not None
            or not isinstance(topics, list) or not 1 <= len(topics) <= HISTORY_LOOKUP_MAX_TOPICS
            or any(not isinstance(value, str) or len(value) > 120 or not re.search(r'[^\W_]', value)
                   for value in topics)):
        raise ValidationError('多线索搜索只接受对话历史和一至三条非空线索。')
    visible, messages = _scope(project, learner)
    words = re.findall(r'[\w]+', topic)[:6]
    kind, _, key = source.partition(':')
    if kind in ('exam', 'answer', 'wrong', 'review', 'course', 'message') and not re.fullmatch(r'[1-9]\d{0,17}', key):
        raise NotFound('找不到可读取的学习来源。')
    from ai_assistant.services.facts.learning_practice_memory import PRACTICE_SOURCES, read_practice
    if source in PRACTICE_SOURCES or kind in ('exam', 'answer', 'wrong', 'review'):
        if not include_practice:
            raise NotFound('找不到可读取的学习来源。')
        return read_practice(learner, source, words, offset)
    courses = visible
    if project:
        state = ProjectLearning.objects.filter(project=project).first()
        _, messages, courses = _project_scope(project, learner, state, visible, messages)
    if kind == 'course' and has_learning_feature(learner, 'course.video'):
        course = courses.select_related('transcript').filter(pk=key).first()
        if course:
            return _read_course(course, learner, words, offset, start_seconds)
    if kind == 'message':
        room = messages.filter(pk=key).values_list('conversation_id', flat=True).first()
        messages = messages.filter(conversation_id=room)
    if kind == 'conversation':
        try:
            messages = messages.filter(conversation_id=UUID(key))
        except ValueError as error:
            raise NotFound('找不到可读取的学习来源。') from error
    if kind in ('message', 'conversation') or source == 'conversation_history':
        history = _readable_history(messages, visible, courses, current_message,
                                    include_practice and has_learning_feature(learner, 'quiz.exam'))
        if topics is not None:
            entries = _history_evidence(history, learner, list(dict.fromkeys(value.strip() for value in topics)))
            return {'source': source, 'conversation': entries, 'next_offset': None,
                    **_history_dependencies(messages, entries)}
        if kind == 'message':
            row = history.filter(pk=key).first()
            if row and _current_sources(learner, row):
                entries = [_message_record(row, offset, 4000)]
                next_offset = offset + 4000 if len(row.content) > offset + 4000 else None
                return {'source': source, 'conversation': entries, 'next_offset': next_offset,
                        **_history_dependencies(messages, entries)}
        else:
            if source == 'conversation_history':
                matching, search_terms = _ranked_history(history, topic)
            else:
                matching, search_terms = _matching(history, words, 'content').order_by('pk'), ()
            rows = list(matching[offset:offset + HISTORY_PAGE_SIZE + 1])
            if rows or source == 'conversation_history' or history.exists():
                entries = [_message_record(row, search_terms=search_terms) for row in rows[:HISTORY_PAGE_SIZE]
                           if _current_sources(learner, row)]
                return {'source': source, 'conversation': entries,
                        'next_offset': offset + HISTORY_PAGE_SIZE if len(rows) > HISTORY_PAGE_SIZE else None,
                        **_history_dependencies(messages, entries)}
    raise NotFound('找不到可读取的学习来源。')
