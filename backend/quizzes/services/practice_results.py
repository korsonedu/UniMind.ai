"""Practice card bindings and read models for exam results and history."""

import hashlib
import json

from django.db.models import Count, Q, Sum
from rest_framework.exceptions import ValidationError

from quizzes.models import ExamQuestionResult, PracticeSubmission, QuizExam
from quizzes.services.exam_grading_state import can_resume_grading


def _practice_fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def _practice_display_fingerprint(rows):
    return _practice_fingerprint([[row[key] for key in ('id', 'text', 'q_type', 'subjective_type', 'options')] for row in rows])


def prepare_practice_card(reservation, question_points, payload):
    questions = payload['questions']
    question_ids = [row['id'] for row in questions]
    PracticeSubmission.objects.create(user_id=reservation.user_id, session_id=payload['practice_id'], answers_hash='',
        response={'ulr_practice': {'source': reservation.pk, 'question_ids': question_ids,
            'question_points': [question_points[pk] for pk in question_ids], 'display': _practice_display_fingerprint(questions)}})


def validate_practice_card(user, binding, answers, request):
    from ai_assistant.services.ulr_capabilities import require_visible_practice_sources
    from quizzes.ai_workflow import validate_exam_answers
    from users.models import AIUsageReservation

    source = AIUsageReservation.objects.select_for_update().filter(pk=binding['source'], user=user, status='succeeded').first()
    if not source or source.response.get('engine') != 'ulr' or source.response.get('deleted'):
        raise ValidationError('原练习卡已失效，请重新准备。')
    question_ids = binding['question_ids']
    if [int(row['question_id']) for row in answers] != question_ids or any(not (row.get('answer') or '').strip() for row in answers):
        raise ValidationError('请按原练习卡提交全部题目的答案。')
    questions = validate_exam_answers(user, answers, request=request, lock=True)
    points = binding.get('question_points')
    if points is None:
        points = [binding['point_id']] * len(question_ids)
    require_visible_practice_sources(user, dict(zip(question_ids, points, strict=True)))
    rows = [{'id': question_id, **question_snapshot(questions[question_id])} for question_id in question_ids]
    if _practice_display_fingerprint(rows) != binding['display']:
        raise ValidationError('练习题已更新，请重新准备。')
    return questions


def question_snapshot(question) -> dict:
    """Capture the parts of a question that a result page must keep after edits."""
    knowledge_point = question.knowledge_point if question.knowledge_point_id else None
    return {
        'text': question.text or '',
        'options': question.options or [],
        'q_type': question.q_type or '',
        'subjective_type': question.subjective_type or '',
        'correct_answer': question.correct_answer or '',
        'ai_answer': question.ai_answer or '',
        'grading_points': question.grading_points or '',
        'difficulty_level': question.difficulty_level or '',
        'kp_id': knowledge_point.id if knowledge_point else None,
        'kp_name': knowledge_point.name if knowledge_point else '',
        'kp_code': knowledge_point.code if knowledge_point else '',
    }


def versioned_question_snapshot(question, *, practice_card=False):
    snapshot = question_snapshot(question)
    grading = [snapshot[key] for key in ('text', 'options', 'q_type', 'subjective_type', 'correct_answer', 'grading_points', 'kp_id')]
    key = 'ulr_practice_version' if practice_card else 'ulr_grading_version'
    snapshot[key] = _practice_fingerprint([grading, question.rubric])
    return snapshot


def validate_grading_question(question, snapshot, scope):
    practice_card = 'ulr_practice_version' in snapshot
    key = 'ulr_practice_version' if practice_card else 'ulr_grading_version'
    if ((question.knowledge_point_id and question.knowledge_point.institution_id != scope)
            or versioned_question_snapshot(question, practice_card=practice_card)[key] != snapshot[key]):
        raise ValidationError('原题或知识点已变更，请重新准备。')


def _saved_result_analysis(snapshot, analysis):
    if snapshot.get('q_type') == 'objective' and 'ulr_practice_version' in snapshot:
        return snapshot.get('ai_answer') or ''
    return analysis or snapshot.get('ai_answer') or ''


_REVIEW_FIELDS = ('pk', 'question_id', 'exam_id', 'position', 'status', 'graded_at', 'score', 'max_score',
                  'user_answer', 'question_snapshot', 'feedback', 'analysis')


def _saved_grade(row):
    snapshot = row['question_snapshot'] or {}
    return (row['status'] == 'graded' and row['graded_at'] and 0 < row['max_score'] and 0 <= row['score'] <= row['max_score']
            and snapshot.get('q_type') in ('objective', 'subjective') and bool(snapshot.get('text')))


def saved_practice_review_rows(results):
    for row in results.filter(status='graded', graded_at__isnull=False).values(*_REVIEW_FIELDS).iterator():
        if _saved_grade(row):
            row['analysis'] = _saved_result_analysis(row['question_snapshot'], row['analysis'])
            yield row


def practice_question_reviews(user, question_ids):
    """Resolve the latest bound attempt and any outstanding card for this learner."""
    from users.models import AIUsageReservation

    if not question_ids:
        return {}
    cards = [card for card in PracticeSubmission.objects.filter(user=user, response__has_key='ulr_practice')
             .values_list('response__ulr_practice', flat=True) if question_ids.intersection(card['question_ids'])]
    sources = AIUsageReservation.objects.filter(user=user, status='succeeded', response__engine='ulr',
        pk__in={card['source'] for card in cards}).values_list('pk', 'response__deleted')
    active = {pk for pk, deleted in sources if not deleted}
    reviews = {question_id: {'practice_status': 'unsubmitted'} for card in cards if card['source'] in active
               for question_id in question_ids.intersection(card['question_ids'])}
    results = ExamQuestionResult.objects.filter(exam__user=user, question_id__in=question_ids - reviews.keys(),
        question_snapshot__has_key='ulr_practice_version').order_by('question_id', '-exam_id', '-pk')
    for row in results.values(*_REVIEW_FIELDS).iterator():
        if row['question_id'] in reviews:
            continue
        graded = _saved_grade(row)
        if graded:
            row['analysis'] = _saved_result_analysis(row['question_snapshot'], row['analysis'])
        reviews[row['question_id']] = ({'practice_status': 'graded', **row} if graded else {'practice_status': 'awaiting_review'})
    return reviews


def _options_list(options):
    if isinstance(options, dict):
        return [options[key] for key in sorted(options)]
    return options if isinstance(options, list) else []


def _snapshot_value(snapshot: dict, question, key: str, fallback_key: str | None = None):
    value = snapshot.get(key)
    if value not in (None, '', []):
        return value
    if question is None:
        return ''
    return getattr(question, fallback_key or key, '') or ''


def _knowledge_point(snapshot: dict, question):
    if snapshot.get('kp_name') or snapshot.get('kp_id'):
        return (
            snapshot.get('kp_id'),
            snapshot.get('kp_name') or '',
            snapshot.get('kp_code') or '',
        )
    if question is not None and question.knowledge_point_id:
        point = question.knowledge_point
        return point.id, point.name or '', point.code or ''
    return None, '', ''


def _result_payload(result: ExamQuestionResult) -> dict:
    snapshot = result.question_snapshot or {}
    question = result.question
    kp_id, kp_name, kp_code = _knowledge_point(snapshot, question)
    return {
        'question_id': result.question_id,
        'position': result.position,
        'status': result.status,
        'question_text': _snapshot_value(snapshot, question, 'text'),
        'q_type': _snapshot_value(snapshot, question, 'q_type'),
        'subjective_type': _snapshot_value(snapshot, question, 'subjective_type'),
        'options': _options_list(_snapshot_value(snapshot, question, 'options')),
        'user_answer': result.user_answer or '',
        'correct_answer': _snapshot_value(snapshot, question, 'correct_answer') if result.status == 'graded' else '',
        'analysis': _saved_result_analysis(snapshot, result.analysis) if result.status == 'graded' else '',
        'response_type': snapshot.get('response_type', ''),
        'label_source': snapshot.get('label_source') or ('objective_answer_key' if snapshot.get('q_type') == 'objective' else 'model_rubric_grade'),
        'feedback': result.feedback or '',
        'error_type': result.error_type or '',
        'error_metadata': result.error_metadata or {},
        'score': result.score,
        'max_score': result.max_score,
        'is_correct': result.is_correct,
        'kp_id': kp_id,
        'kp_name': kp_name,
        'kp_code': kp_code,
        'graded_at': result.graded_at,
    }


def _summary_text(exam: QuizExam, results: list[dict]) -> str:
    graded = [item for item in results if item['status'] == 'graded']
    if exam.status in ('pending', 'grading'):
        return f'正在批改，已完成 {len(graded)} / {exam.total_questions} 题。'
    if exam.status == 'failed':
        return exam.summary or '批改未完成，请稍后重试。'
    if exam.status == 'partial':
        return exam.summary or f'部分题目未完成，已完成 {len(graded)} / {exam.total_questions} 题。'

    total_score = sum(item['score'] for item in graded)
    max_score = sum(item['max_score'] for item in graded)
    correct = sum(1 for item in graded if item['is_correct'])
    if max_score and any(item['label_source'] == 'model_rubric_grade' for item in graded):
        return f'模型依据评价标准评分 {round(total_score, 1)}/{round(max_score, 1)}；尚未独立复核。'
    if max_score:
        rate = round(total_score / max_score * 100, 1)
        return exam.summary or f'正确率 {rate}%（{correct}/{len(graded)}）。'
    return exam.summary or '本次练习已完成。'


def _kp_breakdown(results: list[dict]) -> list[dict]:
    grouped: dict = {}
    for item in results:
        if item['status'] != 'graded' or not item['kp_id']:
            continue
        bucket = grouped.setdefault(item['kp_id'], {
            'kp_id': item['kp_id'],
            'kp_name': item['kp_name'],
            'correct': 0,
            'total': 0,
        })
        bucket['total'] += 1
        bucket['correct'] += int(bool(item['is_correct']))
    return [
        {
            'kp_id': value['kp_id'],
            'kp_name': value['kp_name'],
            'correct_rate': round(value['correct'] / value['total'] * 100, 1) if value['total'] else 0,
        }
        for value in grouped.values()
    ]


def exam_result_payload(exam: QuizExam, include_results: bool = True) -> dict:
    results = list(exam.results.select_related('question__knowledge_point').order_by('position', 'id'))
    payload_results = [_result_payload(result) for result in results]
    graded = [item for item in payload_results if item['status'] == 'graded']
    total_score = sum(item['score'] for item in graded)
    max_score = sum(item['max_score'] for item in graded)
    correct_count = sum(1 for item in graded if item['is_correct'])
    total_questions = exam.total_questions or len(results)
    payload = {
        'kind': 'exam',
        'id': exam.id,
        'status': exam.status,
        **({'can_resume': True} if can_resume_grading(exam) else {}),
        'created_at': exam.created_at,
        'completed_at': exam.grading_completed_at,
        'total_questions': total_questions,
        'graded_count': len(graded),
        'failed_count': sum(1 for item in payload_results if item['status'] == 'failed'),
        'pending_count': max(0, total_questions - len(graded) - sum(1 for item in payload_results if item['status'] == 'failed')),
        'total_score': round(total_score, 1),
        'max_score': round(max_score, 1),
        'correct_rate': round(total_score / max_score * 100, 1) if max_score else 0,
        'correct_count': correct_count,
        'summary_text': _summary_text(exam, payload_results),
        'label_source': 'model_rubric_grade' if any(item['label_source'] == 'model_rubric_grade' for item in payload_results) else 'objective_answer_key',
        'kp_breakdown': _kp_breakdown(payload_results),
        'href': f'/tests/results/{exam.id}',
    }
    if include_results:
        payload['results'] = payload_results
    return payload


def exam_status_payload(exam: QuizExam) -> dict:
    aggregate = exam.results.aggregate(
        graded=Count('id', filter=Q(status='graded')),
        failed=Count('id', filter=Q(status='failed')),
        score=Sum('score', filter=Q(status='graded')),
        max_score=Sum('max_score', filter=Q(status='graded')),
    )
    graded = aggregate['graded'] or 0
    failed = aggregate['failed'] or 0
    total_score = aggregate['score'] or 0
    max_score = aggregate['max_score'] or 0
    total_questions = exam.total_questions or exam.results.count()
    label_source = 'model_rubric_grade' if exam.results.filter(question_snapshot__q_type='subjective').exists() else 'objective_answer_key'
    summary = exam.summary or ''
    if exam.status in ('pending', 'grading'):
        summary = f'正在批改，已完成 {graded} / {total_questions} 题。'
    elif exam.status == 'partial':
        summary = summary or f'部分题目未完成，已完成 {graded} / {total_questions} 题。'
    elif exam.status == 'failed':
        summary = summary or '批改未完成，请稍后重试。'
    elif not summary and max_score:
        summary = (f'模型依据评价标准评分 {round(total_score, 1)}/{round(max_score, 1)}；尚未独立复核。'
                   if label_source == 'model_rubric_grade' else f'正确率 {round(total_score / max_score * 100, 1)}%。')
    return {
        'kind': 'exam',
        'id': exam.id,
        'status': exam.status,
        **({'can_resume': True} if can_resume_grading(exam) else {}),
        'total_questions': total_questions,
        'graded_count': graded,
        'failed_count': failed,
        'total_score': round(total_score, 1),
        'max_score': round(max_score, 1),
        'correct_rate': round(total_score / max_score * 100, 1) if max_score else 0,
        'summary_text': summary,
        'label_source': label_source,
        'href': f'/tests/results/{exam.id}',
        'completed_at': exam.grading_completed_at,
    }


def exam_history_items(user, limit: int = 20) -> list[dict]:
    limit = max(1, min(int(limit or 20), 50))
    exams = QuizExam.objects.filter(user=user).order_by('-created_at')[:limit]
    return [
        {
            'kind': 'exam',
            'id': exam.id,
            'title': '习题训练',
            'status': exam.status,
            'created_at': exam.created_at,
            'completed_at': exam.grading_completed_at,
            'total_questions': exam.total_questions,
            'graded_count': exam.graded_count,
            'failed_count': exam.failed_count,
            'total_score': exam.total_score,
            'max_score': exam.max_score,
            'correct_rate': (
                round(exam.total_score / exam.max_score * 100, 1)
                if exam.max_score else 0
            ),
            'summary_text': exam.summary or '',
            'href': f'/tests/results/{exam.id}',
        }
        for exam in exams
    ]
