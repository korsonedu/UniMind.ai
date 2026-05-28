import logging
from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from quizzes.models import UserQuestionStatus, UserKnowledgeState

logger = logging.getLogger(__name__)

DIAGNOSTIC_QUESTION_COUNT = 10
DIAGNOSTIC_TIME_LIMIT_SECONDS = 300


def generate_diagnostic_questions(institution):
    """从题库随机抽取诊断题目（优先机构题目，fallback 全局题目）。"""
    from quizzes.models import Question

    # 优先从机构题库抽题
    qs = list(Question.objects.filter(
        q_type='objective',
        institution=institution,
    ).exclude(correct_answer__isnull=True).exclude(correct_answer='').order_by('?')[:DIAGNOSTIC_QUESTION_COUNT])

    # 不够则从全局题库补
    if len(qs) < DIAGNOSTIC_QUESTION_COUNT:
        existing_ids = [q.id for q in qs]
        remaining = DIAGNOSTIC_QUESTION_COUNT - len(qs)
        qs += list(Question.objects.filter(
            q_type='objective',
        ).exclude(id__in=existing_ids).exclude(correct_answer__isnull=True).exclude(correct_answer='').order_by('?')[:remaining])

    # 转为前端格式
    questions = []
    for q in qs[:DIAGNOSTIC_QUESTION_COUNT]:
        kp = q.knowledge_point
        questions.append({
            'id': q.id,
            'question_text': q.text,
            'q_type': q.q_type,
            'options': q.options or [],
            'answer': q.correct_answer,
            'knowledge_point_id': kp.id if kp else None,
            '_kp_name': kp.name if kp else '',
        })

    return questions


def grade_diagnostic_answers(user, answers):
    """评分诊断答案，返回结果和知识点分析。"""
    from ai_service import AIService

    results = []
    kp_scores = {}  # kp_id -> {correct, total, kp_name}

    for item in answers:
        question_data = item.get('question', {})
        user_answer = item.get('answer', '')
        kp_id = item.get('knowledge_point_id') or question_data.get('knowledge_point_id')
        kp_name = item.get('_kp_name') or question_data.get('_kp_name', '')

        q_type = question_data.get('q_type', 'objective')
        correct_answer = question_data.get('answer', '')

        # 客观题用精确匹配，主观题用 AI 评分
        feedback = ''
        if q_type == 'objective':
            is_correct = _check_objective_answer(user_answer, correct_answer)
            score = 1.0 if is_correct else 0.0
        else:
            grading = _grade_subjective_answer(AIService, question_data, user_answer)
            score = grading.get('score', 0.0)
            is_correct = score >= 0.6
            feedback = grading.get('feedback', '')

        result = {
            'question_text': question_data.get('question_text', ''),
            'user_answer': user_answer,
            'correct_answer': correct_answer,
            'is_correct': is_correct,
            'score': score,
            'feedback': feedback,
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
    return user_answer.strip().upper() == correct_answer.strip().upper()


def _grade_subjective_answer(ai_service, question_data, user_answer):
    """主观题 AI 评分。"""
    try:
        prompt = (
            f"请对以下答案评分（0-1分）并给出简短反馈。\n\n"
            f"题目：{question_data.get('question_text', '')}\n"
            f"参考答案：{question_data.get('answer', '')}\n"
            f"学生答案：{user_answer}\n\n"
            f"返回 JSON：{{\"score\": 0.0-1.0, \"feedback\": \"简短反馈\"}}"
        )
        messages = [
            {'role': 'system', 'content': '你是阅卷助手。客观评分，给出简短反馈。'},
            {'role': 'user', 'content': prompt},
        ]
        from ai_engine.service import AIEngine
        res = AIEngine.call_ai(messages, temperature=0.3, max_tokens=200, operation='diagnostic.grade')
        if res and 'choices' in res:
            import json
            content = res['choices'][0]['message']['content']
            # 提取 JSON
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0]
            elif '```' in content:
                content = content.split('```')[1].split('```')[0]
            return json.loads(content.strip())
    except Exception as e:
        logger.warning("Diagnostic grading error: %s", e)
    return {'score': 0.0, 'feedback': '评分失败'}


@transaction.atomic
def initialize_memorix_from_diagnostic(user, kp_scores):
    """根据诊断结果初始化 Memorix 状态。"""
    now = timezone.now()

    for kp_id, scores in kp_scores.items():
        accuracy = scores['correct'] / max(scores['total'], 1)

        # 获取该知识点下的题目（优先机构题，回退全局题）
        from quizzes.models import Question
        from django.db.models import Q
        qs = Question.objects.filter(knowledge_point_id=kp_id)
        inst = getattr(user, 'institution', None)
        if inst:
            qs = qs.filter(Q(institution=inst) | Q(institution__isnull=True))
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


def build_study_plan(kp_scores):
    """根据诊断结果生成学习计划建议。"""
    weak_kps = []
    strong_kps = []

    for kp_id, scores in kp_scores.items():
        accuracy = scores['correct'] / max(scores['total'], 1)
        info = {'kp_id': kp_id, 'kp_name': scores['kp_name'], 'accuracy': round(accuracy * 100)}
        if accuracy < 0.4:
            weak_kps.append(info)
        elif accuracy >= 0.7:
            strong_kps.append(info)

    plan = {
        'weak_kps': weak_kps,
        'strong_kps': strong_kps,
        'recommendation': '',
    }

    if weak_kps:
        names = '、'.join([kp['kp_name'] for kp in weak_kps[:3]])
        plan['recommendation'] = f'建议优先复习：{names}。每天花 20 分钟针对薄弱知识点做题。'
    elif strong_kps:
        plan['recommendation'] = '基础不错！建议保持每日复习节奏，巩固已学知识。'
    else:
        plan['recommendation'] = '建议先完成更多练习，系统将自动分析你的薄弱环节。'

    return plan
