"""Project-scoped learning recall from the application's live source records."""

import re
from math import isfinite
from types import SimpleNamespace
from uuid import UUID

from django.db import transaction
from django.db.models import IntegerField, Q
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from ai_assistant.models import (
    AIChatMessage, Conversation, ConversationProject, LearningKnowledgeVersion, LearningMemoryCheckpoint,
    ProjectLearning, ProjectLearningEvent,
)
from courses.access import visible_courses
from courses.models import VideoProgress
from notes.models import ConversationNoteReference, Note
from users.feature_access import has_learning_feature
from users.workspaces.access import membership_for


RECALL_TOOL = {
    'name': 'recall_learning',
    'description': '找回当前学习范围内的计划、知识结构、历史问答、笔记、课程进度及跨应用学习记录。继续上次学习时可不传关键词。',
    'inputSchema': {
        'type': 'object',
        'properties': {'topic': {'type': 'string', 'maxLength': 120, 'description': '找回旧资料时填写关键词或知识点名称'}},
        'additionalProperties': False,
    },
    'annotations': {'readOnlyHint': True, 'openWorldHint': False},
}

SOURCE_TOOL = {
    'name': 'read_learning_source',
    'description': '按来源读取旧问答、课程讲稿和播放位置、练习原作答及批改，或翻页查练习、错题与复习历史。'
                   '先用 recall_learning 找来源。用 next_offset 继续读取。',
    'inputSchema': {'type': 'object', 'properties': {
        'source': {'type': 'string', 'maxLength': 80, 'description': '例如 exam:42、answer:42、course:42、conversation:<UUID>、message:42，'
                   '或 practice、wrong_answers、review_history、conversation_history'},
        'topic': {'type': 'string', 'maxLength': 120, 'description': '可选的关键词，用来查讲稿和历史记录'},
        'offset': {'type': 'integer', 'minimum': 0, 'maximum': 1000000},
        'start_seconds': {'type': 'number', 'minimum': 0, 'maximum': 10000000, 'description': '仅用于课程，从视频指定时间附近读讲稿'},
    }, 'required': ['source'], 'additionalProperties': False},
    'annotations': {'readOnlyHint': True, 'openWorldHint': False},
}

def _matching(rows, words, *fields):
    if not words:
        return rows
    clauses = Q()
    for word in words:
        for field in fields:
            clauses |= Q(**{f'{field}__icontains': word})
    return rows.filter(clauses)


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
        from .learning_continuity import signatures
        if (original['map_id'] != version.knowledge_map_id
                or original['definition'] != signatures(version.snapshot).get(node['id'])):
            return None
    return {'source': f'event:{event.pk}', 'at': event.created_at, 'node_id': node['id'], 'title': node['title'],
            'version_id': version.pk, 'original_version_id': original['version_id']}


@transaction.atomic
def remember_view(project, version_id, node_id):
    from .learning_continuity import signatures
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
    from .learning_practice_memory import PRACTICE_SOURCES
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


def _stage(state):
    return next((row for row in state.plan.get('stages', []) if row['id'] == state.current_stage), None) if state else None


def _project_summary(project, state):
    plan = state.plan if state else {}
    stage = _stage(state)
    return {'id': project.pk, 'name': project.name, 'goal': str(plan.get('goal', ''))[:500],
            'status': state.status if state else 'unplanned', 'revision': state.revision if state else None,
            'deadline': plan.get('deadline'), 'weekly_minutes': plan.get('weekly_minutes'),
            'current_stage': {key: stage[key] for key in ('id', 'title') if key in stage} if stage else None,
            'next_action': state.next_action[:500] if state else ''}


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
    from .ulr_history import require_receipt_sources
    try:
        require_receipt_sources(learner, {'done': True, 'engine': engine, 'message_id': row.pk})
    except (PermissionDenied, ValidationError):
        return False
    return True


def _message_record(row, offset=0, limit=800):
    entry = {'source': f'message:{row.pk}', 'conversation_id': str(row.conversation_id),
             'role': row.role, 'text': row.content[offset:offset + limit], 'at': row.timestamp}
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


def recall(project, learner, topic='', *, current_message=None, include_notes=True,
           include_workspace_checkpoints=False, note_versions=None):
    words = re.findall(r'[\w]+', topic)[:6]
    state = ProjectLearning.objects.filter(project=project).first() if project else None
    plan = state.plan if state else {}
    path = plan.get('knowledge_path') or {}
    version = LearningKnowledgeVersion.objects.filter(
        pk=path.get('version_id'), knowledge_map__user=learner).first()

    visible, messages = _scope(project, learner)
    notes = Note.objects.filter(user=learner, deleted_at__isnull=True)
    if note_versions is not None:
        authorized_notes = Q(pk__in=[])
        for note_id, note_version in note_versions:
            authorized_notes |= Q(pk=note_id, version=note_version)
        notes = notes.filter(authorized_notes)
    courses = visible
    if project:
        rooms, messages, courses = _project_scope(project, learner, state, visible, messages)
        references = ConversationNoteReference.objects.filter(user=learner, conversation__in=rooms)
        notes = notes.filter(Q(pk__in=references.values('note_id')) |
                             Q(pk__in=project.memory_sources.filter(note__isnull=False).values('note_id')))
    progress = VideoProgress.objects.filter(user=learner, course__in=courses)
    progress = _matching(progress, words, 'course__title')
    course_rows = [{
        'source': f'course:{row.course_id}', 'title': row.course.title, 'position_seconds': row.last_position,
        'finished': row.is_finished, 'updated_at': row.updated_at,
    } for row in progress.select_related('course').order_by('-updated_at', '-pk')[:5]]
    if project and len(course_rows) < 5:
        remaining = _matching(courses.exclude(pk__in=progress.values('course_id')), words, 'title')
        course_rows.extend({
            'source': f'course:{row.pk}', 'title': row.title, 'position_seconds': None,
            'finished': None, 'updated_at': None,
        } for row in remaining.order_by('pk')[:5 - len(course_rows)])

    note_rows = [{
        'source': f'note:{row.pk}', 'title': row.title, 'version': row.version, **_excerpt(row.content, words),
        'updated_at': row.updated_at,
    } for row in _matching(notes, words, 'title', 'content').order_by('-updated_at', '-pk')[:5]] if include_notes else []

    include_practice = (include_workspace_checkpoints or not project) and has_learning_feature(learner, 'quiz.exam')
    history = _matching(_readable_history(messages, visible, courses, current_message, include_practice), words, 'content')
    reply_rows = [_message_record(row) for row in history.order_by('-id')[:8] if _current_sources(learner, row)]

    stage = _stage(state)
    nodes = version.snapshot.get('nodes', []) if version else []
    focus = set((stage or {}).get('knowledge_nodes', []) or path.get('targets', []))
    viewed_node = last_viewed_node(project, version)
    if viewed_node:
        focus.add(viewed_node['node_id'])
    nodes = [node for node in nodes if (node['id'] in focus or any(word.casefold() in node['title'].casefold() for word in words))]
    tasks = []
    if state and has_learning_feature(learner, 'quiz.exam'):
        from .learning_tasks import task_states
        rows = [row for row in task_states(project, state) if row['is_current'] and row['status'] != 'unavailable']
        pending = sorted((row for row in rows if row['status'] != 'completed'),
                         key=lambda row: row['stage_id'] != state.current_stage)
        completed = [row for row in reversed(rows) if row['status'] == 'completed']
        for row in (pending + completed)[:8]:
            task = {key: row[key] for key in ('id', 'title', 'status', 'stage_id', 'node_id', 'version_id', 'assistance')}
            if row['summary']:
                task['result'] = {key: row['summary'].get(key) for key in ('total_score', 'max_score', 'label_source')}
            tasks.append(task)
    events = ProjectLearningEvent.objects.filter(kind='agent_checkpoint')
    events = events.filter(project=project) if project else events.filter(project__user=learner)
    checkpoints = [(row, 'event') for row in _matching(events, words, 'content__text')[:5]]
    if include_workspace_checkpoints or not project:
        records = LearningMemoryCheckpoint.objects.filter(learner=learner).order_by('-pk')
        checkpoints.extend((row, 'checkpoint') for row in _matching(records, words, 'content__text')[:5])
        checkpoints = sorted(checkpoints, key=lambda item: item[0].created_at, reverse=True)[:5]
    result = {
        'read_at': timezone.now(),
        'knowledge': {'version_id': version.pk, 'revision': version.revision, 'title': version.knowledge_map.title,
                      'nodes': [{key: row[key] for key in ('id', 'title', 'prerequisites') if key in row}
                                for row in nodes[:12]]} if version else None,
        'last_viewed_node': viewed_node, 'tasks': tasks, 'course_progress': course_rows, 'notes': note_rows, 'conversation': reply_rows,
        'external_checkpoints': [{'source': f'{kind}:{row.pk}', 'at': row.created_at,
                                  'kind': 'external_self_report', 'agent': row.content['agent'], 'text': row.content['text']}
                                 for row, kind in checkpoints],
        'interpretation': '播放、阅读和外部自报是学习记录。独立作答和正式评分以原任务为准。',
    }
    if project:
        result['project'] = _project_summary(project, state)
    else:
        projects = ConversationProject.objects.filter(user=learner).select_related('learning').order_by('-pk')
        matches = list(_matching(projects, words, 'name', 'learning__next_action')[:12])
        result['projects'] = [_project_summary(item, getattr(item, 'learning', None)) for item in matches or projects[:12]]
    if include_workspace_checkpoints or not project:
        from .learning_practice_memory import recent_practice
        result['practice_sources'] = list(recent_practice(learner, words))
    if current_message is not None and reply_rows:
        result.update(_history_dependencies(messages, reply_rows))
    return result


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
                         current_message=None, include_practice=False):
    if start_seconds is not None and not isfinite(start_seconds):
        raise NotFound('时间位置无效。')
    visible, messages = _scope(project, learner)
    words = re.findall(r'[\w]+', topic)[:6]
    kind, _, key = source.partition(':')
    if kind in ('exam', 'answer', 'wrong', 'review', 'course', 'message') and not re.fullmatch(r'[1-9]\d{0,17}', key):
        raise NotFound('找不到可读取的学习来源。')
    from .learning_practice_memory import PRACTICE_SOURCES, read_practice
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
        if kind == 'message':
            row = history.filter(pk=key).first()
            if row and _current_sources(learner, row):
                entries = [_message_record(row, offset, 4000)]
                next_offset = offset + 4000 if len(row.content) > offset + 4000 else None
                return {'source': source, 'conversation': entries, 'next_offset': next_offset,
                        **_history_dependencies(messages, entries)}
        else:
            rows = list(_matching(history, words, 'content').order_by('-pk' if source == 'conversation_history' else 'pk')[offset:offset + 9])
            if rows or source == 'conversation_history' or history.exists():
                entries = [_message_record(row) for row in rows[:8] if _current_sources(learner, row)]
                return {'source': source, 'conversation': entries, 'next_offset': offset + 8 if len(rows) > 8 else None,
                        **_history_dependencies(messages, entries)}
    raise NotFound('找不到可读取的学习来源。')
