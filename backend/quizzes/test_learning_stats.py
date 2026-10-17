from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from quizzes.models import KnowledgePoint, Question, UserQuestionStatus
from quizzes.services.learning_stats import build_learning_stats


def _status(user, question, **overrides):
    return UserQuestionStatus.objects.create(user=user, question=question, **overrides)


@pytest.mark.django_db
def test_excludes_zero_rep_rows_and_computes_accuracy():
    user = get_user_model().objects.create_user(username='stats-user-1')
    attempted = Question.objects.create(text='练习一')
    favorited = Question.objects.create(text='练习二')
    _status(user, attempted, reps=2, wrong_count=1, last_correct=True)
    _status(user, favorited, reps=0)

    stats = build_learning_stats(user)

    assert stats['attempted_questions'] == 1
    assert stats['total_attempts'] == 2
    assert stats['last_accuracy'] == 100.0
    assert stats['lifetime_accuracy'] == 50.0
    assert stats['has_attempts'] is True


@pytest.mark.django_db
def test_no_attempts_does_not_report_zero_percent():
    user = get_user_model().objects.create_user(username='stats-user-2')
    question = Question.objects.create(text='收藏题')
    _status(user, question, reps=0)

    stats = build_learning_stats(user)

    assert stats['attempted_questions'] == 0
    assert stats['last_accuracy'] is None
    assert stats['lifetime_accuracy'] is None
    assert stats['accuracy'] == 0
    assert stats['has_attempts'] is False
    assert stats['is_new_user'] is True


@pytest.mark.django_db
def test_subject_coverage_ignores_empty_and_counts_unclassified():
    user = get_user_model().objects.create_user(username='stats-user-3')
    kp = KnowledgePoint.objects.create(name='函数', code='math-function', subject='数学')
    bound = Question.objects.create(text='绑定知识点', knowledge_point=kp)
    unbound = Question.objects.create(text='未绑定知识点')
    _status(user, bound, reps=1, last_correct=True)
    _status(user, unbound, reps=1)

    stats = build_learning_stats(user)

    assert stats['subjects'] == ['数学']
    assert stats['subject_count'] == 1
    assert stats['unclassified_questions'] == 1


@pytest.mark.django_db
def test_institution_filter_limits_questions():
    from users.models import Institution

    user = get_user_model().objects.create_user(username='stats-user-4')
    institution = Institution.objects.create(
        name='测试机构', slug='stats-inst', contact_name='测试', contact_email='test@example.com',
    )
    inst_question = Question.objects.create(text='机构题', institution=institution)
    global_question = Question.objects.create(text='全局题')
    _status(user, inst_question, reps=1, last_correct=True)
    _status(user, global_question, reps=1, last_correct=True)

    stats = build_learning_stats(user, institution=institution)

    assert stats['attempted_questions'] == 1


@pytest.mark.django_db
def test_date_range_filters_by_last_review():
    user = get_user_model().objects.create_user(username='stats-user-5')
    old_question = Question.objects.create(text='旧题')
    recent_question = Question.objects.create(text='新题')
    old_status = _status(user, old_question, reps=1, last_correct=True)
    recent_status = _status(user, recent_question, reps=1, last_correct=True)
    now = timezone.now()
    UserQuestionStatus.objects.filter(pk=old_status.pk).update(
        last_review=now - timedelta(days=10),
    )
    UserQuestionStatus.objects.filter(pk=recent_status.pk).update(last_review=now)

    stats = build_learning_stats(
        user, date_from=now - timedelta(days=1), date_to=now,
    )

    assert stats['attempted_questions'] == 1
    assert stats['date_filter']['basis'] == 'last_review'
