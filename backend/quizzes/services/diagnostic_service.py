from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from rest_framework import serializers
from core.utils import get_content_institution_id
from quizzes.models import UserQuestionStatus, UserKnowledgeState
from .question_normalizer import normalize_objective_answer

DIAGNOSTIC_QUESTION_COUNT = 10
DIAGNOSTIC_TIME_LIMIT_SECONDS = 300


class DiagnosticQuestionReference(serializers.Serializer):
    id = serializers.IntegerField(min_value=1)


class DiagnosticAnswerInput(serializers.Serializer):
    question = DiagnosticQuestionReference()
    answer = serializers.CharField(allow_blank=True, trim_whitespace=False)


def generate_diagnostic_questions(institution_id):
    """从题库随机抽取诊断题目（仅受管内容范围，不足时返回更少量）。"""
    from quizzes.models import Question

    qs = list(Question.objects.filter(
        q_type='objective',
        institution_id=institution_id,
    ).exclude(correct_answer__isnull=True).exclude(correct_answer='').order_by('?')[:DIAGNOSTIC_QUESTION_COUNT])


    # 转为前端格式
    questions = []
    for q in qs[:DIAGNOSTIC_QUESTION_COUNT]:
        kp = q.knowledge_point
        questions.append({
            'id': q.id,
            'question_text': q.text,
            'q_type': q.q_type,
            'options': q.options or [],
            'knowledge_point_id': kp.id if kp else None,
            '_kp_name': kp.name if kp else '',
        })

    return questions


def grade_diagnostic_answers(answers):
    """评分诊断答案，返回结果和知识点分析。诊断只接受受管范围内的客观题。"""
    from quizzes.models import Question

    serializer = DiagnosticAnswerInput(
        data=answers, many=True, allow_empty=False,
        max_length=DIAGNOSTIC_QUESTION_COUNT,
    )
    serializer.is_valid(raise_exception=True)
    answers = serializer.validated_data
    question_ids = [item['question']['id'] for item in answers]
    if len(set(question_ids)) != len(question_ids):
        raise serializers.ValidationError({'answers': '诊断题目不能重复。'})
    questions = Question.objects.filter(
        pk__in=question_ids,
        institution_id=get_content_institution_id(),
        q_type='objective',
    ).select_related('knowledge_point').in_bulk()
    if len(questions) != len(question_ids):
        raise serializers.ValidationError({'answers': '题目不存在、不适用于诊断或无访问权限。'})

    results = []
    kp_scores = {}  # kp_id -> {correct, total, kp_name}

    for item in answers:
        question = questions[item['question']['id']]
        user_answer = item['answer']
        kp_id = question.knowledge_point_id
        kp_name = question.knowledge_point.name if kp_id else ''
        correct_answer = question.correct_answer
        is_correct = _check_objective_answer(user_answer, correct_answer)
        score = 1.0 if is_correct else 0.0

        result = {
            'question_text': question.text,
            'user_answer': user_answer,
            'correct_answer': correct_answer,
            'is_correct': is_correct,
            'score': score,
            'feedback': '',
            'knowledge_point_id': kp_id,
            'knowledge_point_name': kp_name,
        }
        results.append(result)

        if kp_id:
            if kp_id not in kp_scores:
                kp_scores[kp_id] = {'correct': 0, 'total': 0, 'kp_name': kp_name}
            kp_scores[kp_id]['total'] += 1
            if is_correct:
                kp_scores[kp_id]['correct'] += 1

    return results, kp_scores


def _check_objective_answer(user_answer, correct_answer):
    """客观题精确匹配。"""
    if not user_answer or not correct_answer:
        return False
    return normalize_objective_answer(user_answer) == normalize_objective_answer(correct_answer)


@transaction.atomic
def initialize_memorix_from_diagnostic(user, kp_scores):
    """根据诊断结果初始化 Memorix 状态。"""
    now = timezone.now()

    for kp_id, scores in kp_scores.items():
        accuracy = scores['correct'] / max(scores['total'], 1)

        # 获取该知识点下的题目
        from quizzes.models import Question
        qs = Question.objects.filter(
            knowledge_point_id=kp_id,
            institution_id=get_content_institution_id(),
        )
        questions = qs[:5]

        for q in questions:
            status, created = UserQuestionStatus.objects.get_or_create(
                user=user, question=q,
                defaults={
                    'stability': 5.0 if accuracy >= 0.6 else 1.0,
                    'difficulty': 5.0,
                    'reps': 1,
                    'lapses': 0 if accuracy >= 0.6 else 1,
                    'last_review': now,
                    'next_review_at': now + timedelta(days=3 if accuracy >= 0.6 else 1),
                    'last_correct': accuracy >= 0.6,
                    'wrong_count': 0 if accuracy >= 0.6 else 1,
                }
            )

    # 更新知识点掌握度
    for kp_id, scores in kp_scores.items():
        accuracy = scores['correct'] / max(scores['total'], 1)
        mastery_score = accuracy * 100

        UserKnowledgeState.objects.update_or_create(
            user=user, knowledge_point_id=kp_id,
            defaults={'mastery_score': mastery_score}
        )


def generate_reassessment(user, previous_diagnostic_id=None):
    """生成重新评估题目 — 聚焦之前薄弱的知识点，排除已掌握内容。"""
    from quizzes.models import Question, UserKnowledgeState

    # 获取用户知识点掌握状态
    weak_kp_ids = set()
    known_states = UserKnowledgeState.objects.filter(user=user)
    for state in known_states:
        if state.mastery_score is not None and state.mastery_score >= 80:
            continue  # 已掌握，跳过
        if state.mastery_score is not None:
            weak_kp_ids.add(state.knowledge_point_id)

    scope_id = get_content_institution_id()
    qs = Question.objects.filter(
        q_type='objective',
        institution_id=scope_id,
    ).exclude(
        correct_answer__isnull=True
    ).exclude(correct_answer='')

    # 优先从弱知识点抽题
    if weak_kp_ids:
        qs = qs.filter(knowledge_point_id__in=weak_kp_ids)

    questions = list(qs.order_by('?')[:DIAGNOSTIC_QUESTION_COUNT])

    # 不够则放宽限制（保持内容范围）
    if len(questions) < DIAGNOSTIC_QUESTION_COUNT:
        remaining = DIAGNOSTIC_QUESTION_COUNT - len(questions)
        existing_ids = [q.id for q in questions]
        qs_extra = Question.objects.filter(
            q_type='objective',
            institution_id=scope_id,
        ).exclude(id__in=existing_ids).exclude(
            correct_answer__isnull=True
        ).exclude(correct_answer='')
        extra = list(qs_extra.order_by('?')[:remaining])
        questions += extra

    result = []
    for q in questions[:DIAGNOSTIC_QUESTION_COUNT]:
        kp = q.knowledge_point
        result.append({
            'id': q.id,
            'question_text': q.text,
            'q_type': q.q_type,
            'options': q.options or [],
            'knowledge_point_id': kp.id if kp else None,
            '_kp_name': kp.name if kp else '',
        })

    return result
