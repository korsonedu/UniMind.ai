"""Reauthorize historical model input without altering the saved conversation."""
from itertools import chain
from math import isfinite
import re

from django.apps import apps
from django.db.models import F, Q
from django.db.models.functions import Substr
from rest_framework.exceptions import PermissionDenied, ValidationError

from ai_assistant.models import AIChatMessage, Conversation
from courses.models import TranscriptSegment
from quizzes.services.practice_results import practice_question_reviews
from ai_assistant.services.course_context import current_transcript_sources, require_current_transcript_sources
from ai_assistant.services.runtime.ulr_capabilities import (
    require_visible_course_sources, require_visible_practice_review_sources, visible_course_ids, visible_practice_review_sources,
)
from .workbench_grounding import current_workbench_source_versions, require_workbench_source_versions


COURSE_LINK = re.compile(r'/course/([1-9][0-9]*)(?:\?t=(-?[0-9.]+(?:e[+-]?[0-9]+)?))?')
SOURCE_FIELDS = {
    'course_id': F('metadata__course_context__course_id'),
    'course_transcript_id': F('metadata__course_context__transcript_id'),
    'course_revision': F('metadata__course_context__revision'),
    'sources': F('metadata__ulr_context_sources'),
    'cards': F('metadata__dsh_cards'),
    'attachments': F('metadata__note_attachments'),
    'note_selection': F('metadata__note_selection'),
}


def conversation_project_id(user, conversation_id):
    return Conversation.objects.filter(user=user, conversation_id=conversation_id, project__user=user).values_list(
        'project_id', flat=True,
    ).first()


def course_card_items(cards, tools):
    for card in cards or ():
        if not isinstance(card, dict) or card.get('tool') not in tools:
            continue
        payload = card.get('payload')
        items = payload.get('items') if isinstance(payload, dict) else None
        if not isinstance(items, list):
            continue
        for item in items:
            url = item.get('action_link') if isinstance(item, dict) else None
            if isinstance(url, str) and (link := COURSE_LINK.fullmatch(url)):
                yield int(link[1]), link[2], item


def legacy_courses(row):
    courses = {row['course_id']} if type(row['course_id']) is int else set()
    courses.update(course for course, _, _ in course_card_items(row['cards'], {'search_asr', 'search_courses'}))
    return courses


def reply_sources(prompt, reply):
    sources = reply['sources']
    if sources is not None:
        return set(sources.get('courses', ())), {tuple(note) for note in sources.get('notes', ())}, sources.get('selection')
    courses = legacy_courses(reply) | (legacy_courses(prompt) if prompt else set())
    notes = {(note['note_id'], note['version']) for note in prompt.get('attachments') or ()}
    return courses, notes, prompt.get('note_selection')


def reply_transcript_sources(prompt, reply):
    sources = {tuple(ref) for ref in (reply['sources'] or {}).get('transcripts', ())}
    for row in (prompt, reply):
        if row and type(row['course_id']) is int and type(row['course_revision']) is int:
            sources.add((row['course_id'], row['course_transcript_id'] or 0, row['course_revision']))
    return sources


def legacy_transcript_excerpts(cards, sources):
    versioned_courses = {course for course, _, _ in sources}
    excerpts = set()
    for course, timestamp, item in course_card_items(cards, {'search_asr'}):
        excerpt = item.get('value')
        if timestamp is None or course in versioned_courses or not isinstance(excerpt, str) or not excerpt.strip():
            continue
        try:
            start = float(timestamp)
        except ValueError:
            continue
        if isfinite(start) and start >= 0:
            excerpts.add((course, start, excerpt))
    return excerpts


def match_legacy_transcript_excerpts(excerpts):
    if not excerpts:
        return {}
    courses, starts, texts = zip(*excerpts)
    # The legacy search tool stored the first 200 characters of the segment in the card.
    segments = TranscriptSegment.objects.annotate(excerpt=Substr('text', 1, 200)).filter(
        transcript__asr_status='completed', transcript__course_id__in=set(courses),
        start_time__in=set(starts), excerpt__in=set(texts)).order_by().values_list(
            'transcript__course_id', 'start_time', 'excerpt', 'transcript_id', 'transcript__revision')
    return {(course, start, text): (course, transcript, revision)
            for course, start, text, transcript, revision in segments.iterator() if (course, start, text) in excerpts}


def require_receipt_sources(user, receipt):
    if receipt.get('done') is not True or receipt.get('engine') not in ('dsh', 'ulr'):
        return
    messages = AIChatMessage.objects.filter(user=user)
    answer = messages.filter(pk=receipt['message_id'], role='assistant').values('bot_id', 'conversation_id', **SOURCE_FIELDS).first()
    if not answer:
        raise ValidationError('原答复已不可用。')
    project_id = conversation_project_id(user, answer['conversation_id'])
    answer_sources = answer['sources'] or {}
    if 'workbench_sources' in answer_sources:
        require_workbench_source_versions(user, project_id, answer_sources['workbench_project'],
                                          answer_sources['workbench_sources'])
    history = messages.filter(bot_id=answer['bot_id'], conversation_id=answer['conversation_id'],
                              pk__lte=receipt['message_id']).order_by()
    legacy = receipt['engine'] == 'dsh' and answer['sources'] is None
    rows = (answer,)
    if legacy:
        # Older replies could quote an earlier turn without emitting another source card.
        rows = history.values(notes_context_used=F('metadata__notes_context_used'), **SOURCE_FIELDS).iterator()
    courses, transcripts, excerpts, notes = set(), set(), set(), set()
    question_answers, practice_reviews = set(), set()
    for row in rows:
        versions = reply_transcript_sources(None, row)
        transcripts.update(versions)
        excerpts.update(legacy_transcript_excerpts(row['cards'], versions))
        courses.update(legacy_courses(row))
        sources = row['sources'] or {}
        courses.update(sources.get('courses', ()))
        attached = {(note['note_id'], note['version']) for note in row['attachments'] or ()}
        if row.get('notes_context_used') and not attached and not row['note_selection']:
            raise ValidationError('旧笔记来源无法核对，请重新提问。')
        notes.update(attached)
        notes.update(map(tuple, sources.get('notes', ())))
        question_answers.update(reply_question_answers(row))
        practice_reviews.update(reply_practice_reviews(row))
    if not legacy and 'question_answers' not in (answer['sources'] or {}):
        earlier = history.filter(role='assistant', pk__lt=receipt['message_id']).values(
            sources=SOURCE_FIELDS['sources'], cards=SOURCE_FIELDS['cards'])
        for row in earlier.iterator():
            question_answers.update(reply_question_answers(row))
            question_answers.update(pk for pk, _ in reply_practice_reviews(row))
    require_current_practice_answers(user, question_answers)
    require_visible_practice_review_sources(user, practice_reviews)
    courses.update(course for course, _, _ in transcripts | excerpts)
    require_visible_course_sources(user, courses, project_id=project_id)
    require_current_transcript_sources(transcripts)
    if len(match_legacy_transcript_excerpts(excerpts)) != len(excerpts):
        raise ValidationError('当前课程讲稿已更新，请重新发起提问。')
    if notes:
        if not apps.is_installed('notes'):
            raise PermissionDenied('引用笔记已不可访问，请重新提问。')
        from notes.models import Note, NoteAISettings

        note_ids = {note_id for note_id, _ in notes}
        available = Note.objects.filter(user=user, deleted_at__isnull=True, pk__in=note_ids)
        if not NoteAISettings.objects.filter(user=user, enabled=True).exists():
            available = available.filter(conversation_references__user=user, conversation_references__bot_id=answer['bot_id'],
                conversation_references__conversation__conversation_id=answer['conversation_id'])
        current = dict(available.values_list('pk', 'version'))
        if note_ids != current.keys():
            raise PermissionDenied('引用笔记已不可访问，请重新提问。')
        if notes != current.items():
            raise ValidationError('引用笔记已更新，请重新提问。')


def card_question_answers(cards):
    return {row['id'] for card in cards or () if isinstance(card, dict)
            and card.get('tool') in ('lookup_question', 'get_user_wrong_questions') and card.get('type') == 'question_preview'
            for row in (card.get('payload') or {}).get('questions', ())
            if isinstance(row, dict) and type(row.get('id')) is int and 'answer' in row}


def reply_question_answers(reply):
    saved = (reply['sources'] or {}).get('question_answers')
    return set(saved) if saved is not None else card_question_answers(reply['cards'])


def bound_practice_answers(user, questions):
    return practice_question_reviews(user, questions).keys()


def require_current_practice_answers(user, question_ids):
    if bound_practice_answers(user, question_ids):
        raise PermissionDenied('原题已进入正式练习，请重新提问。')


def reply_practice_reviews(reply):
    return {tuple(reference) for reference in (reply['sources'] or {}).get('practice_reviews', ())}


def unversioned_history_courses(row):
    sources = row['sources'] or {}
    if row.get('engine') in {'dsh', 'ulr'} and 'transcripts' not in sources:
        return set(sources.get('courses', ()))
    return set()


def scoped_history(user, current, note_versions, *, include_continuation=False):
    # The extra row supplies the corresponding question when the window starts on an assistant reply.
    history = AIChatMessage.objects.filter(user_id=current.user_id, bot_id=current.bot_id,
        conversation_id=current.conversation_id).exclude(pk=current.pk).exclude(content='[Thinking...]')
    fields = dict(SOURCE_FIELDS)
    if include_continuation:
        fields['continuation'] = F('metadata__ulr_continuation')
    recent = list(history.order_by('-timestamp', '-id').values(
        'pk', 'timestamp', 'role', 'content', engine=F('metadata__engine'), **fields)[:17])
    project_id = conversation_project_id(user, current.conversation_id)
    workbench_ids = {pk for row in recent for pk in (row['sources'] or {}).get('workbench_sources', ())}
    workbench_versions = current_workbench_source_versions(user, project_id, workbench_ids)
    legacy = {'dsh', 'dsh_import'}
    older_engines = legacy | {'ulr'}
    infer_legacy_sources = any((row['engine'] in legacy and row['sources'] is None) or unversioned_history_courses(row)
                               for row in recent)
    infer_answers = any(row['engine'] in older_engines and 'question_answers' not in (row['sources'] or {})
                        for row in recent)
    earlier = ()
    if (infer_legacy_sources or infer_answers) and len(recent) == 17:
        oldest = recent[-1]
        earlier = history.filter(Q(timestamp__lt=oldest['timestamp']) |
            Q(timestamp=oldest['timestamp'], pk__lt=oldest['pk'])).order_by('timestamp', 'pk').values(
                'role', **SOURCE_FIELDS).iterator()
    prompt = {}
    entries = []
    all_courses = set()
    all_answers, previous_answers = set(), set()
    all_reviews, all_transcripts, previous_transcripts = set(), set(), set()
    all_excerpts, previous_excerpts = set(), set()
    previous_courses, previous_notes, previous_selection = set(), set(), False
    for row in chain(earlier, reversed(recent)):
        # Earlier rows carry only provenance. They never enter the model window.
        in_window = 'content' in row
        if row['role'] == 'user':
            prompt = row
            if in_window:
                entries.append(({'role': 'user', 'content': row['content']}, set(), set(), set(), set(), set()))
            continue
        if row['role'] != 'assistant':
            continue
        sources = row['sources'] or {}
        if 'workbench_sources' in sources and (sources['workbench_project'] != project_id
                or not sources['workbench_sources'].items() <= workbench_versions.items()):
            continue
        courses, notes, selection = reply_sources(prompt, row)
        transcripts = reply_transcript_sources(prompt, row)
        excerpts = legacy_transcript_excerpts(row['cards'], transcripts)
        courses.update(course for course, _, _ in transcripts)
        courses.update(course for course, _, _ in excerpts)
        answers = reply_question_answers(row)
        reviews = reply_practice_reviews(row)
        if infer_answers:
            previous_answers.update(answers)
            previous_answers.update(pk for pk, _ in reviews)
            if row.get('engine') in older_engines and 'question_answers' not in (row['sources'] or {}):
                answers = previous_answers.copy()
        if infer_legacy_sources:
            # DSH replies may use earlier exchanges even when no new source card was emitted.
            if unversioned := unversioned_history_courses(row):
                unversioned.difference_update(ref[0] for ref in transcripts | excerpts)
                transcripts.update(ref for ref in previous_transcripts if ref[0] in unversioned)
                excerpts.update(ref for ref in previous_excerpts if ref[0] in unversioned)
            previous_courses.update(courses)
            previous_transcripts.update(transcripts)
            previous_excerpts.update(excerpts)
            previous_notes.update(notes)
            previous_selection = previous_selection or bool(selection)
            if row.get('engine') in legacy and row['sources'] is None:
                courses, notes, selection = previous_courses.copy(), previous_notes, previous_selection
                transcripts = previous_transcripts.copy()
                excerpts = previous_excerpts.copy()
        if in_window and not selection and notes <= note_versions:
            all_courses.update(courses)
            all_answers.update(answers)
            all_reviews.update(reviews)
            all_transcripts.update(transcripts)
            all_excerpts.update(excerpts)
            visible_reply = {'role': 'assistant', 'content': row['content']}
            if row is recent[0] and row['pk'] < current.pk and (continuation := row.get('continuation')) is not None:
                if continuation or not any(isinstance(card, dict) and card.get('type') == 'action_cards'
                                           for card in row['cards'] or ()):
                    visible_reply['continuation'] = continuation
            entries.append((visible_reply, courses, answers, reviews, transcripts, excerpts))
    authorized = visible_course_ids(user, all_courses, project_id=project_id)
    protected = bound_practice_answers(user, all_answers)
    visible_reviews = visible_practice_review_sources(user, all_reviews)
    current_transcripts = current_transcript_sources(all_transcripts)
    matched_excerpts = match_legacy_transcript_excerpts({ref for ref in all_excerpts if ref[0] in authorized})
    return [(row, courses, answers, reviews, transcripts | {matched_excerpts[ref] for ref in excerpts})
            for row, courses, answers, reviews, transcripts, excerpts in entries
            if courses <= authorized and answers.isdisjoint(protected) and reviews <= visible_reviews
            and transcripts <= current_transcripts and excerpts <= matched_excerpts.keys()][-16:]
