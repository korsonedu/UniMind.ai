"""One isolated smoke across the migrated read-only tools and content scopes."""
import json
from datetime import timedelta
from uuid import uuid4

import pytest
from django.utils import timezone

from ai_assistant.services.dsh_service import build_context, execute_tool
from ai_assistant.services.dsh_cards import build_tool_card
from courses.models import Course, TranscriptSegment, VideoTranscript
from quizzes.models import KnowledgePoint, Question, QuizExam, UserKnowledgeState, UserQuestionStatus
from users.models import CourseStudentStatus, Institution, LearningSession


def test_report_card_question_unit():
    card = build_tool_card('get_report_card', {'mastered_count': 10})
    assert card['payload']['items'][2] == {'label': '已掌握题目', 'value': '10'}


@pytest.mark.django_db
def test_readonly_student_queries(user, settings):
    settings.UNIMIND_CONTENT_INSTITUTION_ID = 'global'
    CourseStudentStatus.objects.create(user=user, is_course_student=True)
    other = type(user).objects.create_user(username='other-readonly-student')
    private = Institution.objects.create(name='private-content', slug='private-content')
    kp = KnowledgePoint.objects.create(name='M0久期', code='M0-KP', subject='金融431')
    question = Question.objects.create(knowledge_point=kp, text='M0_OWN_QUESTION', correct_answer='M0_OWN_ANSWER', options=['A', 'B'])
    private_question = Question.objects.create(institution=private, text='PRIVATE_CONTENT_QUESTION')
    other_question = Question.objects.create(knowledge_point=kp, text='OTHER_STUDENT_WRONG')
    UserQuestionStatus.objects.create(user=user, question=question, wrong_count=2, reps=3, difficulty=7, stability=2)
    UserQuestionStatus.objects.create(user=other, question=other_question, wrong_count=77, reps=99)
    UserKnowledgeState.objects.create(user=user, knowledge_point=kp, mastery_score=40)
    QuizExam.objects.create(user=user, status='completed', total_score=8, max_score=10, total_questions=1, graded_count=1)
    other_exam = QuizExam.objects.create(user=other, status='completed', total_score=999, max_score=1000)
    course = Course.objects.create(title='M0久期课程', knowledge_point=kp)
    private_course = Course.objects.create(title='M0久期私人课程', institution=private)
    transcript = VideoTranscript.objects.create(course=course, asr_status='completed')
    TranscriptSegment.objects.create(transcript=transcript, start_time=60, end_time=90, text='M0久期片段', index=0)
    now = timezone.now()
    LearningSession.objects.create(user=user, session_id=uuid4(), kind='video', course=course,
        started_at=now-timedelta(minutes=20), ended_at=now, active_seconds=1200)
    LearningSession.objects.create(user=other, session_id=uuid4(), kind='video',
        started_at=now-timedelta(minutes=20), ended_at=now, active_seconds=99999)
    calls = {
        'get_learning_stats': {}, 'get_recent_practice_result': {}, 'get_user_weak_points': {},
        'search_courses': {'query': 'M0久期'}, 'search_asr': {'query': 'M0久期'},
        'search_knowledge_tree': {'query': 'M0久期'}, 'get_user_wrong_questions': {},
        'lookup_question': {'question_id': question.pk}, 'get_learning_sessions': {},
        'get_knowledge_mastery_map': {}, 'get_due_reviews': {}, 'get_knowledge_difficulty_analysis': {},
        'get_practice_questions': {'kp_name': 'M0久期', 'limit': 2}, 'get_exam_history': {},
        'get_report_card': {}, 'get_my_achievements': {}, 'search_similar_questions': {'kp_code': 'M0-KP'},
    }
    context = build_context(user, '')
    assert set(calls) <= {t['function']['name'] for t in context['available_tools']}
    assert len(context['tools']) <= 8
    assert set(calls) | {'get_study_status', 'get_focus_history', 'run_diagnostic', 'create_faq_ticket'} == {t['function']['name'] for group in context['tool_groups'].values() for t in group['tools']}
    original = (QuizExam.objects.count(), UserQuestionStatus.objects.count(), LearningSession.objects.count())
    results = {}
    for name, arguments in calls.items():
        result = execute_tool(user, name, arguments, context['memory']['version'])
        assert not result.get('error'), (name, result)
        assert 'PRIVATE_CONTENT_QUESTION' not in json.dumps(result)
        results[name] = result
    assert [q['id'] for q in results['get_user_wrong_questions']['questions']] == [question.pk]
    assert results['get_learning_sessions']['total_sessions'] == 1
    assert results['get_knowledge_mastery_map']['mastery_map']['金融431'][0]['mastery_score'] == 40
    assert [e['id'] for e in results['get_exam_history']['exams']] != [other_exam.pk]
    assert [c['id'] for c in results['search_courses']['courses']] == [course.pk]
    assert results['search_courses']['visual']['payload']['items'][0]['action_link'] == f'/course/{course.pk}'
    assert results['search_asr']['visual']['payload']['items'][0]['value'] == 'M0久期片段'
    assert results['get_recent_practice_result']['visual']['type'] == 'practice_result'
    assert results['get_practice_questions']['visual']['type'] == 'practice_quiz'
    assert results['get_practice_questions']['visual']['payload']['practice_id']
    assert results['get_practice_questions']['visual']['payload']['questions']
    assert private_course.pk not in [c['id'] for c in results['search_courses']['courses']]
    assert 'correct_answer' not in json.dumps(results['get_practice_questions'])
    assert execute_tool(user, 'lookup_question', {'question_id': private_question.pk}, context['memory']['version']).get('error')
    assert not execute_tool(user, 'get_recent_practice_result', {'exam_id': other_exam.pk}, context['memory']['version'])['has_result']
    assert original == (QuizExam.objects.count(), UserQuestionStatus.objects.count(), LearningSession.objects.count())
