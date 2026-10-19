"""Read models shared by exam result, status, history and the XiaoYu tool."""

from django.db.models import Count, Q, Sum

from quizzes.models import ExamQuestionResult, QuizExam


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
        'correct_answer': _snapshot_value(snapshot, question, 'correct_answer'),
        'analysis': result.analysis or snapshot.get('ai_answer') or '',
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
    summary = exam.summary or ''
    if exam.status in ('pending', 'grading'):
        summary = f'正在批改，已完成 {graded} / {total_questions} 题。'
    elif exam.status == 'partial':
        summary = summary or f'部分题目未完成，已完成 {graded} / {total_questions} 题。'
    elif exam.status == 'failed':
        summary = summary or '批改未完成，请稍后重试。'
    elif not summary and max_score:
        summary = f'正确率 {round(total_score / max_score * 100, 1)}%。'
    return {
        'kind': 'exam',
        'id': exam.id,
        'status': exam.status,
        'total_questions': total_questions,
        'graded_count': graded,
        'failed_count': failed,
        'total_score': round(total_score, 1),
        'max_score': round(max_score, 1),
        'correct_rate': round(total_score / max_score * 100, 1) if max_score else 0,
        'summary_text': summary,
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
