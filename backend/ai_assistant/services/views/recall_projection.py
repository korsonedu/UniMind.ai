"""L4 View Layer — learning continuity summary projection (`recall_learning`) over L1 facts."""

import re

from django.db.models import Q
from django.utils import timezone

from ai_assistant.models import (
    ConversationProject, LearningKnowledgeVersion, LearningMemoryCheckpoint, ProjectLearning, ProjectLearningEvent,
)
from ai_assistant.services.facts.source_reader import (
    HISTORY_PAGE_SIZE,
    _current_sources,
    _excerpt,
    _history_dependencies,
    _matching,
    _message_record,
    _project_scope,
    _ranked_history,
    _readable_history,
    _scope,
    last_viewed_node,
)
from courses.models import VideoProgress
from notes.models import ConversationNoteReference, Note
from users.feature_access import has_learning_feature


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
    history, search_terms = _ranked_history(
        _readable_history(messages, visible, courses, current_message, include_practice), topic)
    reply_rows = [_message_record(row, search_terms=search_terms) for row in history[:HISTORY_PAGE_SIZE]
                  if _current_sources(learner, row)]

    stage = _stage(state)
    nodes = version.snapshot.get('nodes', []) if version else []
    focus = set((stage or {}).get('knowledge_nodes', []) or path.get('targets', []))
    viewed_node = last_viewed_node(project, version)
    if viewed_node:
        focus.add(viewed_node['node_id'])
    nodes = [node for node in nodes if (node['id'] in focus or any(word.casefold() in node['title'].casefold() for word in words))]
    tasks = []
    if state and has_learning_feature(learner, 'quiz.exam'):
        from ai_assistant.services.facts.learning_tasks import task_states
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
        from ai_assistant.services.facts.learning_practice_memory import recent_practice
        result['practice_sources'] = list(recent_practice(learner, words))
    if current_message is not None and reply_rows:
        result.update(_history_dependencies(messages, reply_rows))
    return result
