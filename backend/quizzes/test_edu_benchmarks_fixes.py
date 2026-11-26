"""Regression & correctness tests for IRT MAP estimation, Memorix online gradients,
UnifiedMasteryEstimator (Memorix-KT), and MisconceptionDiagnoser.
"""
import numpy as np
import pytest

from quizzes.memorix.mastery import MasteryConfig, StudentMasteryState, UnifiedMasteryEstimator
from quizzes.memorix.optimizer import MemorixOptimizer, W_COST_SENS, W_WEIBULL_K
from quizzes.services.irt_estimator import IRTEstimator, ItemEstimate
from quizzes.services.misconception_diagnosis import MisconceptionDiagnoser, MisconceptionEntry


def test_irt_estimate_user_ability_distinguishes_hard_vs_easy_items():
    items = {
        1: ItemEstimate(1.5, -2.0, 0.1, 100),  # easy
        2: ItemEstimate(1.5, -1.5, 0.1, 100),  # easy
        3: ItemEstimate(1.5, 0.0, 0.1, 100),   # medium
        4: ItemEstimate(1.5, 0.5, 0.1, 100),   # medium
        5: ItemEstimate(1.5, 2.0, 0.1, 100),   # hard
        6: ItemEstimate(1.5, 2.5, 0.1, 100),   # hard
    }
    # Both students have identical 50% (2/4) accuracy, on an easier vs harder test form:
    easy_form_50pct = [
        {"question_id": 1, "is_correct": True},
        {"question_id": 2, "is_correct": True},
        {"question_id": 3, "is_correct": False},
        {"question_id": 4, "is_correct": False},
    ]
    hard_form_50pct = [
        {"question_id": 3, "is_correct": True},
        {"question_id": 4, "is_correct": True},
        {"question_id": 5, "is_correct": False},
        {"question_id": 6, "is_correct": False},
    ]
    all_correct = [{"question_id": i, "is_correct": True} for i in range(1, 5)]
    all_wrong = [{"question_id": i, "is_correct": False} for i in range(1, 5)]

    theta_easy_form = IRTEstimator.estimate_user_ability(easy_form_50pct, items)
    theta_hard_form = IRTEstimator.estimate_user_ability(hard_form_50pct, items)
    theta_all_ok = IRTEstimator.estimate_user_ability(all_correct, items)
    theta_all_bad = IRTEstimator.estimate_user_ability(all_wrong, items)

    # Previously both returned 0.0 (= 6*0.5 - 3), completely ignoring item difficulty b
    assert theta_hard_form > 0.3 > -0.3 > theta_easy_form
    assert theta_all_ok > theta_hard_form
    assert theta_all_bad < theta_easy_form
    assert -3.0 < theta_all_bad < 0.0 < theta_all_ok < 3.0


def test_memorix_optimizer_gradient_updates_stability_weights_and_uses_regret():
    opt = MemorixOptimizer()
    r_pred = opt.predict_retrievability(stability=2.5, elapsed_days=3.0)
    grad = opt._compute_gradient(
        grade=3, elapsed_days=3.0, stability=2.5, difficulty=5.0,
        retrievability_pred=r_pred, y=1.0,
    )
    nonzero = [i for i, v in enumerate(grad) if abs(v) > 1e-12]
    assert W_WEIBULL_K in nonzero
    # Must update stability/difficulty weights as well (previously only index 17 was nonzero)
    assert len(nonzero) >= 5

    # Higher review opportunity cost alpha should yield a shorter or equal/different regret-adjusted schedule
    opt_low_cost = MemorixOptimizer()
    opt_low_cost.weights[W_COST_SENS] = 0.01
    opt_high_cost = MemorixOptimizer()
    opt_high_cost.weights[W_COST_SENS] = 0.40
    t_low = opt_low_cost.schedule_next_review(stability=10.0, difficulty=5.0, target_retrievability=0.80)
    t_high = opt_high_cost.schedule_next_review(stability=10.0, difficulty=5.0, target_retrievability=0.80)
    assert t_low > 0 and t_high > 0
    assert t_high <= t_low


def test_unified_mastery_estimator_calibration_decay_and_graph_transfer():
    est = UnifiedMasteryEstimator.fit_priors(
        interactions=[
            ("q_easy", "kc_a", 1), ("q_easy", "kc_a", 1), ("q_easy", "kc_a", 1),
            ("q_hard", "kc_b", 0), ("q_hard", "kc_b", 0), ("q_hard", "kc_b", 0),
        ],
        kc_graph={"kc_a": [("kc_b", 0.9)], "kc_b": [("kc_a", 0.9)]},
    )
    st = StudentMasteryState()
    p_easy = est.predict(st, "kc_a", question_id="q_easy", ts_sec=0.0)
    p_hard = est.predict(st, "kc_b", question_id="q_hard", ts_sec=0.0)
    assert p_easy > p_hard

    # Success on kc_a raises prediction on both kc_a and graph-connected kc_b
    est.update(st, "kc_a", True, question_id="q_easy", ts_sec=0.0)
    p_b_after = est.predict(st, "kc_b", question_id="q_hard", ts_sec=10.0)
    assert p_b_after > p_hard

    # Temporal forgetting: 60 days later, positive kc_a mastery residual decays
    p_a_now = est.predict(st, "kc_a", question_id="q_easy", ts_sec=60.0)
    p_a_later = est.predict(st, "kc_a", question_id="q_easy", ts_sec=60 * 86400.0)
    assert p_a_now > p_a_later

    # Guided assistance does not inflate independent mastery
    st_guided = StudentMasteryState()
    est.update(st_guided, "kc_a", True, assistance="guided", ts_sec=0.0)
    assert st_guided.theta_global == 0.0 and st_guided.theta_kc["kc_a"] == 0.0
    assert isinstance(st.to_dict(), dict)


def test_misconception_diagnoser_bilingual_bm25_and_llm_rerank():
    catalog = [
        MisconceptionEntry("m1", "Adds numerators and denominators directly when adding fractions", "Math", "Fractions"),
        MisconceptionEntry("m2", "Forgets to flip inequality sign when multiplying by a negative number", "Math", "Algebra"),
        MisconceptionEntry("m3", "计算久期时把票息现金流当成终值直接相加，忽略折现因子", "Finance", "Duration"),
    ]
    diag = MisconceptionDiagnoser(catalog)
    en_hits = diag.retrieve("fraction addition 1/2 + 1/3 = 2/5 adding numerators and denominators", top_k=2)
    assert en_hits[0]["misconception_id"] == "m1"

    zh_hits = diag.retrieve("计算久期忘记折现直接把票息相加", top_k=2)
    assert zh_hits[0]["misconception_id"] == "m3"

    reranked = diag.diagnose_with_llm(
        question="Solve -2x > 6",
        correct_answer="x < -3",
        student_answer="x > -3",
        llm_call=lambda _p: '{"reasoning": "Did not flip inequality sign", "ranked_ids": ["m2"]}',
        top_k=2,
    )
    assert reranked["candidates"][0]["misconception_id"] == "m2"


def test_multimodal_vision_routing_and_image_validation():
    import base64
    import pytest
    from rest_framework.exceptions import ValidationError
    from ai_engine.config import FALLBACK_FAST, get_vision_model_for_task, messages_contain_images
    from ai_assistant.services.chat_images import chat_image_messages, prepare_chat_images

    text_msgs = [{"role": "user", "content": "解释久期"}]
    img_msgs = [{"role": "user", "content": [
        {"type": "text", "text": "帮我看看这道题"},
        {"type": "image_url", "image_url": {"url": "https://cdn.example.com/q1.png"}},
    ]}]
    assert not messages_contain_images(text_msgs)
    assert messages_contain_images(img_msgs)
    # Even for a pro-tier operation (e.g. quizzes.grade), vision routing must use vision-capable model (deepseek-v4-flash)
    v_cfg = get_vision_model_for_task("quizzes.grade")
    assert v_cfg["model"] == FALLBACK_FAST

    # Valid PNG magic bytes data URL + safe HTTPS URL
    png_b64 = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32).decode()
    sanitized = prepare_chat_images([f"data:image/png;base64,{png_b64}", "https://oss.example.com/p.jpg"])
    assert len(sanitized) == 2
    blocks = chat_image_messages(sanitized)
    assert len(blocks) == 2 and blocks[0]["type"] == "image_url"

    # Reject SSRF / non-HTTPS / spoofed bytes / >3 images
    with pytest.raises(ValidationError):
        prepare_chat_images(["http://127.0.0.1/secret.png"])
    with pytest.raises(ValidationError):
        prepare_chat_images(["https://127.0.0.1/internal.png"])
    with pytest.raises(ValidationError):
        prepare_chat_images(["data:image/png;base64," + base64.b64encode(b"not-a-png").decode()])
    with pytest.raises(ValidationError):
        prepare_chat_images(["https://a.com/1.png"] * 4)


@pytest.mark.django_db
def test_estimate_user_mastery_and_wrong_question_misconception_breakdown(user):
    from django.utils import timezone
    from quizzes.memorix.service import estimate_user_mastery
    from quizzes.models import ExamQuestionResult, KnowledgePoint, Question, QuizExam, UserQuestionStatus
    from quizzes.services.wrong_question_insights import build_wrong_question_insights

    kp = KnowledgePoint.objects.create(name="债券久期与凸性", subject="金融431")
    q1 = Question.objects.create(knowledge_point=kp, text="当市场利率上升时，计算修正久期对债券价格的影响", correct_answer="A")
    q2 = Question.objects.create(knowledge_point=kp, text="计算零息债券的麦考利久期", correct_answer="B")
    exam = QuizExam.objects.create(user=user, status="graded", total_questions=2, graded_count=2)
    now = timezone.now()
    ExamQuestionResult.objects.create(
        exam=exam, question=q1, position=1, status="graded", is_correct=False,
        score=0, max_score=10, graded_at=now,
        feedback="混淆了麦考利久期与修正久期，且忽略利率上升时债券价格下跌的反向关系",
    )
    ExamQuestionResult.objects.create(
        exam=exam, question=q2, position=2, status="graded", is_correct=True,
        score=10, max_score=10, graded_at=now,
    )
    UserQuestionStatus.objects.create(user=user, question=q1, wrong_count=2, reps=2)

    mastery = estimate_user_mastery(user, [q1.id, q2.id], now=now)
    assert mastery["history_count"] == 2
    assert 0.0 < mastery["predictions"][q1.id] < 1.0
    assert 0.0 < mastery["predictions"][q2.id] < 1.0

    insights = build_wrong_question_insights(user, top_k=3)
    assert "misconception_breakdown" in insights
    assert len(insights["misconception_breakdown"]) >= 1
    assert insights["misconception_breakdown"][0]["misconception_id"] == "fin_duration_convexity_sign"
