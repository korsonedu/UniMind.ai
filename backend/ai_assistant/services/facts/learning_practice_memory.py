"""Read existing assessment and review records for the current learning identity."""

from core.utils import get_user_content_institution_id
from django.db.models import F
from quizzes.models import ExamQuestionResult, QuizExam, ReviewLog, UserQuestionStatus
from quizzes.services.practice_results import exam_status_payload, question_result_payload
from rest_framework.exceptions import NotFound
from users.feature_access import has_learning_feature, learning_features


PRACTICE_SOURCES = {'practice': 'quiz.exam', 'wrong_answers': 'wrong.review', 'review_history': 'memorix.review'}


def _exam_summary(exam):
    has_score = exam.graded_count or exam.status == 'completed'
    return {'source': f'exam:{exam.pk}', 'status': exam.status, 'at': exam.created_at,
            'total_questions': exam.total_questions, 'graded_count': exam.graded_count,
            'score': exam.total_score if has_score else None,
            'max_score': exam.max_score if has_score else None, 'href': f'/tests/results/{exam.pk}'}


def _answer(row):
    data = question_result_payload(row)
    graded = row.status == 'graded'
    return {'source': f'answer:{row.pk}', 'position': row.position, 'question_id': row.question_id,
            'question_text': data['question_text'], 'user_answer': data['user_answer'], 'options': data['options'],
            'status': row.status, 'score': row.score if graded else None,
            'max_score': row.max_score, 'is_correct': row.is_correct if graded else None,
            'feedback': data['feedback'] if graded else '', 'error_type': data['error_type'] if graded else '',
            'label_source': data['label_source'] if graded else None, 'kp_name': data['kp_name'],
            'graded_at': data['graded_at']}


def _practice_page(learner, source, words, offset, size, key=None):
    from ai_assistant.services.learning_recall import _matching

    if source == 'practice':
        rows = QuizExam.objects.filter(user=learner).order_by('-created_at', '-pk')
        if words:
            matched = _matching(ExamQuestionResult.objects.filter(exam__user=learner), words,
                                'question_snapshot__text', 'question_snapshot__kp_name', 'question__text',
                                'question__knowledge_point__name')
            rows = rows.filter(pk__in=matched.values('exam_id'))
        return _page(rows, _exam_summary, offset, size)
    institution = get_user_content_institution_id(learner)
    if source == 'wrong_answers':
        rows = UserQuestionStatus.objects.filter(user=learner, wrong_count__gt=0, question__institution_id=institution)
        if key is not None:
            rows = rows.filter(pk=key)
        rows = _matching(rows, words, 'question__text', 'question__knowledge_point__name').select_related('question__knowledge_point')
        return _page(rows.order_by(F('last_review').desc(nulls_last=True), '-pk'), lambda row: {
            'source': f'wrong:{row.pk}', 'question_id': row.question_id,
            'question_text': row.question.text if key is not None else row.question.text[:400],
            'kp_name': row.question.knowledge_point.name if row.question.knowledge_point_id else '',
            'wrong_count': row.wrong_count, 'last_correct': row.last_correct, 'error_type': row.error_type,
            'mastered': row.is_mastered, 'last_review_at': row.last_review, 'next_review_at': row.next_review_at,
        }, offset, size)
    rows = ReviewLog.objects.filter(user=learner, knowledge_point__institution_id=institution).select_related('knowledge_point')
    if key is not None:
        rows = rows.filter(pk=key)
    rows = _matching(rows, words, 'knowledge_point__name').order_by('-review_time', '-pk')
    return _page(rows, lambda row: {'source': f'review:{row.pk}', 'kp_id': row.knowledge_point_id,
        'kp_name': row.knowledge_point.name, 'grade': row.grade, 'grade_label': row.get_grade_display(),
        'at': row.review_time, 'elapsed_days': row.elapsed_days}, offset, size)


def _page(rows, serialize, offset, size):
    items = list(rows[offset:offset + size + 1])
    return {'items': [serialize(row) for row in items[:size]],
            'next_offset': offset + size if len(items) > size else None}


def recent_practice(learner, words):
    features = learning_features(learner)
    for source, feature in PRACTICE_SOURCES.items():
        if feature in features:
            yield {'source': source, **_practice_page(learner, source, words, 0, 4)}


def read_practice(learner, source, words, offset):
    if source in PRACTICE_SOURCES and has_learning_feature(learner, PRACTICE_SOURCES[source]):
        return {'source': source, **_practice_page(learner, source, words, offset, 8)}
    kind, _, key = source.partition(':')
    group = {'wrong': 'wrong_answers', 'review': 'review_history'}.get(kind)
    if group and has_learning_feature(learner, PRACTICE_SOURCES[group]):
        page = _practice_page(learner, group, [], 0, 1, key=key)
        if page['items']:
            return page['items'][0]
    if not has_learning_feature(learner, 'quiz.exam'):
        raise NotFound('找不到可读取的练习来源。')
    if kind == 'exam':
        exam = QuizExam.objects.filter(pk=key, user=learner).first()
        if exam:
            rows = exam.results.select_related('question__knowledge_point').order_by('position', 'pk')
            def summary(row):
                data = _answer(row)
                for field in ('question_text', 'user_answer', 'feedback'):
                    data[field] = data[field][:500]
                data.pop('options')
                return data
            return {'source': source, 'exam': exam_status_payload(exam), **_page(rows, summary, offset, 6)}
    if kind == 'answer':
        answer = ExamQuestionResult.objects.filter(pk=key, exam__user=learner).select_related('question__knowledge_point').first()
        if answer:
            return {'source': source, 'exam_source': f'exam:{answer.exam_id}', 'answer': _answer(answer)}
    raise NotFound('找不到可读取的练习来源。')
