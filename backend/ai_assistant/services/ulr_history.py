"""Reauthorize historical model input without altering the saved conversation."""
from itertools import chain
import re

from django.db.models import F, Q

from ai_assistant.models import AIChatMessage
from quizzes.services.practice_results import practice_question_reviews
from .ulr_capabilities import visible_course_ids, visible_practice_review_sources


COURSE_LINK = re.compile(r'/course/([1-9][0-9]*)(?:\?t=[0-9.]+)?')
SOURCE_FIELDS = {
    'course_id': F('metadata__course_context__course_id'),
    'sources': F('metadata__ulr_context_sources'),
    'cards': F('metadata__dsh_cards'),
    'attachments': F('metadata__note_attachments'),
    'note_selection': F('metadata__note_selection'),
}


def legacy_courses(row):
    courses = {row['course_id']} if type(row['course_id']) is int else set()
    for card in row['cards'] or []:
        if not isinstance(card, dict) or card.get('tool') not in {'search_asr', 'search_courses'}:
            continue
        for item in (card.get('payload') or {}).get('items') or []:
            url = item.get('action_link') if isinstance(item, dict) else None
            if isinstance(url, str) and (link := COURSE_LINK.fullmatch(url)):
                courses.add(int(link[1]))
    return courses


def reply_sources(prompt, reply):
    sources = reply['sources']
    if sources is not None:
        return set(sources.get('courses', ())), {tuple(note) for note in sources.get('notes', ())}, sources.get('selection')
    courses = legacy_courses(reply) | (legacy_courses(prompt) if prompt else set())
    notes = {(note['note_id'], note['version']) for note in prompt.get('attachments') or ()}
    return courses, notes, prompt.get('note_selection')


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


def reply_practice_reviews(reply):
    return {tuple(reference) for reference in (reply['sources'] or {}).get('practice_reviews', ())}


def scoped_history(user, current, note_versions):
    # The extra row supplies the corresponding question when the window starts on an assistant reply.
    history = AIChatMessage.objects.filter(user_id=current.user_id, bot_id=current.bot_id,
        conversation_id=current.conversation_id).exclude(pk=current.pk).exclude(content='[Thinking...]')
    recent = list(history.order_by('-timestamp', '-id').values(
        'pk', 'timestamp', 'role', 'content', engine=F('metadata__engine'), **SOURCE_FIELDS)[:17])
    legacy = {'dsh', 'dsh_import'}
    older_engines = legacy | {'ulr'}
    infer_legacy_sources = any(row['engine'] in legacy and row['sources'] is None for row in recent)
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
    all_reviews = set()
    previous_courses, previous_notes, previous_selection = set(), set(), False
    for row in chain(earlier, reversed(recent)):
        # Earlier rows carry only provenance. They never enter the model window.
        in_window = 'content' in row
        if row['role'] == 'user':
            prompt = row
            if in_window:
                entries.append(({'role': 'user', 'content': row['content']}, set(), set(), set()))
            continue
        if row['role'] != 'assistant':
            continue
        courses, notes, selection = reply_sources(prompt, row)
        answers = reply_question_answers(row)
        reviews = reply_practice_reviews(row)
        if infer_answers:
            previous_answers.update(answers)
            previous_answers.update(pk for pk, _ in reviews)
            if row.get('engine') in older_engines and 'question_answers' not in (row['sources'] or {}):
                answers = previous_answers.copy()
        if infer_legacy_sources:
            # DSH replies may use earlier exchanges even when no new source card was emitted.
            previous_courses.update(courses)
            previous_notes.update(notes)
            previous_selection = previous_selection or bool(selection)
            if row.get('engine') in legacy and row['sources'] is None:
                courses, notes, selection = previous_courses.copy(), previous_notes, previous_selection
        if in_window and not selection and notes <= note_versions:
            all_courses.update(courses)
            all_answers.update(answers)
            all_reviews.update(reviews)
            entries.append(({'role': 'assistant', 'content': row['content']}, courses, answers, reviews))
    authorized = visible_course_ids(user, all_courses)
    protected = bound_practice_answers(user, all_answers)
    visible_reviews = visible_practice_review_sources(user, all_reviews)
    return [(row, courses, answers, reviews) for row, courses, answers, reviews in entries
            if courses <= authorized and answers.isdisjoint(protected) and reviews <= visible_reviews][-16:]
