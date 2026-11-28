"""Optional local Redis and Celery smoke for the standalone runtime."""
from base64 import b64decode
from contextlib import ExitStack, closing
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shlex
import shelve
import shutil
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Thread
from time import monotonic, sleep
from uuid import uuid4

import pytest


CHAT = '我习惯先看例子。'
TITLE = '例子优先'
DRAFT = {'question': '解释折现率。', 'q_type': 'subjective', 'subjective_type': 'short',
         'options': None, 'answer': '', 'grading_points': None, 'difficulty_level': 'normal'}
BULK_DRAFT = {**DRAFT, 'question': '合成恢复批量题', 'q_type': 'objective', 'subjective_type': None,
              'options': ['A.核对原题范围', 'B.更改题型'], 'answer': 'A'}
SUBJECT = '合成金融'
FOREIGN = 'OUTSIDE_QUEUE_SCOPE'
CUTOVER_QUEUE = 'runtime_cutover_smoke'
EXAM_ANSWER = '需要先将现金流折现到同一时点。'
CRASH_ANSWER = '中断复验时仍将现金流折现到同一时点。'
COURSE_TRANSCRIPT = '合成讲稿：现值等于未来现金流除以折现系数。'
COURSE_EXERCISE = dict(question='如何把未来现金流折算为现值？', q_type='objective', subjective_type=None,
                       options=['A.除以折现系数', 'B.直接相加'], answer='A', grading_points=None, difficulty_level='normal')
EDGE = {'source_name': '时间价值', 'target_name': '折现率', 'relation': 'prerequisite', 'confidence': 0.9}
PROFILE = {'learning_style': 'example_driven', 'response_length': 'balanced', 'interaction_style': 'passive_learner',
           'cognitive_state': 'focused', 'domain_expertise': 'intermediate', 'confidence': 0.9}


def wait_for(predicate, timeout=25):
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        if value := predicate():
            return value
        sleep(.05)
    raise AssertionError('Timed out waiting for the local queue smoke')


def submit_from_web():
    import django
    django.setup()
    from importlib.util import find_spec
    from django.conf import settings
    from django.core.cache import cache
    from django.db import connection, transaction
    from django.utils import timezone
    from django.test import override_settings
    from requests import Session
    from rest_framework.test import APIClient
    from types import SimpleNamespace
    from unittest.mock import patch

    from ai_assistant.models import (AIChatMessage, AgentMemory, Conversation, ConversationProject,
                                     MemoryExtractionLog, ProjectLearning, ProjectLearningEvent)
    from ai_assistant.services.ulr_profile import _snapshot
    from ai_assistant.tasks import extract_memory_turn, generate_conversation_title, precompute_user_profile
    from ai_assistant.tasks_learning import send_project_learning_followups
    from backoffice.tasks import run_teaching_task
    from backoffice.teaching import launch, retry
    from courses.models import Course, CourseVideoQuestion, TranscriptSegment, VideoTranscript
    from courses.services.ai_course_service import AICourseService
    from notifications.models import Notification
    from quizzes.models import ContentPipelineTask, KnowledgeEdge, KnowledgePoint, Question, QuizExam
    from quizzes.services.exam_grading_state import GRADING_RECOVERY_DELAY
    from quizzes.tasks import run_exam_grading_task, run_semantic_edge_analysis_task
    from users.login_sessions import LoginSession
    from users.models import CourseStudentStatus, User, WeeklyAIUsage

    assert settings.IS_PROD and not settings.DEBUG and settings.UNIMIND_LEARNING_RUNTIME == 'ulr'
    assert 'UNIMIND_LEARNING_RUNTIME' not in os.environ
    assert not settings.UNIMIND_DSH_ENABLED and not settings.UNIMIND_DSH_TEACHING_ENABLED
    assert find_spec('deepseek_harness') is None and not (settings.BASE_DIR.parent / 'dsh').exists()
    user_id, bot_id, kp_id, ready, public_url = sys.argv[1:]
    user = User.objects.get(pk=user_id)
    client = Session()
    client.trust_env = False
    client.headers.update({'Authorization': f'Token {LoginSession.issue(user).pk}', 'X-Forwarded-Proto': 'https'})
    conversation_id = str(uuid4())
    request_id = str(uuid4())
    with client.post(f'{public_url}/api/ai/chat/stream/', json={'bot_id': int(bot_id), 'conversation_id': conversation_id,
            'request_id': request_id, 'message': CHAT}, stream=True, timeout=15, allow_redirects=False) as response:
        assert response.status_code == 200 and response.headers['Content-Type'].startswith('text/event-stream')
        reply = [json.loads(frame[6:]) for frame in response.iter_lines() if frame.startswith(b'data: ')][-1]
    assert reply['engine'] == 'ulr' and reply['conversation_title'] == CHAT
    recovered = client.get(f'{public_url}/api/ai/chat-requests/{request_id}/', timeout=8)
    assert recovered.json()['response'] == reply
    client.close()

    course = Course.objects.create(title='合成队列课程')
    transcript = VideoTranscript.objects.create(course=course, asr_status='completed', full_text=COURSE_TRANSCRIPT)
    TranscriptSegment.objects.create(transcript=transcript, text=COURSE_TRANSCRIPT, start_time=0, end_time=10, index=0)
    assert AICourseService().generate_outline(course.pk)

    source = Course.objects.create(title='待撤权课程', is_published=True)
    saved_title = '保留初始标题'
    old = Conversation.objects.create(user=user, bot_id=bot_id, conversation_id=uuid4(), title=saved_title)
    exchange = {'user': user, 'bot_id': bot_id, 'conversation_id': old.conversation_id}
    AIChatMessage.objects.create(**exchange, role='user', content='解释课程内容。')
    AIChatMessage.objects.create(**exchange, role='assistant', content='REVOKED_QUEUED_TITLE_SOURCE',
                                  metadata={'ulr_context_sources': {'courses': [source.pk]}})
    revoked_title = generate_conversation_title.delay(str(old.conversation_id), user.pk, int(bot_id), expected_title=saved_title)
    Course.objects.filter(pk=source.pk).update(is_published=False)

    initial_title = '待交接标题'
    cutover_chat = Conversation.objects.create(user=user, bot_id=bot_id, conversation_id=uuid4(), title=initial_title)
    dialogue = {'user': user, 'bot_id': bot_id, 'conversation_id': cutover_chat.conversation_id}
    AIChatMessage.objects.create(**dialogue, role='user', content=initial_title)
    AIChatMessage.objects.create(**dialogue, role='assistant', content='识别交接前后的原会话。')
    cutover_title = generate_conversation_title.apply_async(
        (str(cutover_chat.conversation_id), user.pk, int(bot_id)), {'expected_title': initial_title}, queue=CUTOVER_QUEUE)

    AgentMemory.objects.create(user=user, key='偏好', value='ACTIVE_QUEUED_PROFILE')
    profile = precompute_user_profile.delay(user.pk)
    revoked_student = User.objects.create_user(username='synthetic-queued-profile-revoked')
    access = CourseStudentStatus.objects.create(user=revoked_student, is_course_student=True)
    AgentMemory.objects.create(user=revoked_student, key='偏好', value='REVOKED_QUEUED_PROFILE')
    before_revocation, _ = _snapshot(revoked_student.pk)
    revoked_profile = precompute_user_profile.delay(revoked_student.pk)
    CourseStudentStatus.objects.filter(pk=access.pk).update(is_course_student=False)

    good_id, revoked_id = json.loads(settings.UNIMIND_DIRECTUS_ADMIN_MAP).values()
    def submit(author_id):
        with transaction.atomic():
            return launch(SimpleNamespace(user=User.objects.get(pk=author_id)), {'kind': 'parse', 'kp_ids': [int(kp_id)],
                'request_id': str(uuid4()), 'raw_text': DRAFT['question']})['id']

    with override_settings(UNIMIND_LEARNING_RUNTIME='legacy', UNIMIND_DSH_TEACHING_ENABLED=True):
        good = submit(good_id)
    assert not ContentPipelineTask.objects.get(pk=good).payload.get('requires_ulr')
    revoked = submit(revoked_id)
    with patch.object(run_teaching_task, 'delay', side_effect=lambda task_id: run_teaching_task.apply_async((task_id,), queue=CUTOVER_QUEUE)):
        mismatch_id = submit(good_id)
    assert ContentPipelineTask.objects.get(pk=mismatch_id).payload['requires_ulr']
    User.objects.filter(pk=revoked_id).update(is_staff=False, is_superuser=False)
    edges = run_semantic_edge_analysis_task.delay(SUBJECT)

    objective = Question.objects.create(text='分期现金流是否需要折现？', q_type='objective', options=['需要', '不需要'],
                                        correct_answer='A')
    subjective = Question.objects.create(text='解释为何要折现。', q_type='subjective', subjective_type='short',
                                         correct_answer='统一现金流计价时点。', grading_points='说明计价时点。')
    exams = APIClient(HTTP_HOST='127.0.0.1', HTTP_X_FORWARDED_PROTO='https')
    exams.force_authenticate(user=user)
    answers = [{'question_id': subjective.pk, 'answer': EXAM_ANSWER}, {'question_id': objective.pk, 'answer': 'A'}]
    with patch.object(run_exam_grading_task, 'delay', side_effect=lambda *args: run_exam_grading_task.apply_async(args, queue=CUTOVER_QUEUE)):
        submitted = exams.post('/api/quizzes/submit-exam/', {'answers': answers}, format='json')
    assert submitted.status_code == 202, submitted.data
    exam = QuizExam.objects.get(pk=submitted.data['exam_id'])
    assert exam.requires_ulr and exam.results.filter(question_snapshot__has_key='ulr_grading_version').count() == 2
    Question.objects.filter(pk=objective.pk).update(correct_answer='B')
    with override_settings(UNIMIND_LEARNING_RUNTIME='legacy'):
        legacy_submission = exams.post('/api/quizzes/submit-exam/', {
            'answers': [{**answers[0], 'answer': '现金流统一到同一时点。'}],
        }, format='json')
    assert legacy_submission.status_code == 202, legacy_submission.data
    legacy_exam_id = legacy_submission.data['exam_id']
    assert not QuizExam.objects.get(pk=legacy_exam_id).requires_ulr
    project = ConversationProject.objects.create(user=user, name='合成队列复习')
    review_chat = Conversation.objects.create(user=user, bot_id=bot_id, conversation_id=uuid4(), project=project)
    ProjectLearning.objects.create(project=project, planning_enabled=True, reminders_enabled=True, status='active',
        last_conversation=review_chat, followup_at=timezone.now(), followup_text='复习原折现率案例。')
    ready_path = Path(ready)
    bulk_id = None
    if connection.vendor == 'postgresql':
        bulk_point = KnowledgePoint.objects.create(name='合成批量考点', code='BULK-QUEUE', subject='合成批量学科')
        bulk_admin = APIClient(HTTP_HOST='127.0.0.1', HTTP_X_FORWARDED_PROTO='https')
        bulk_admin.force_authenticate(user=User.objects.get(pk=good_id))
        with override_settings(UNIMIND_LEARNING_RUNTIME='legacy'):
            bulk = bulk_admin.post('/api/quizzes/admin/bulk-pipeline/', {
                'subject': bulk_point.subject, 'kp_code': bulk_point.code, 'total_target': 1,
                'difficulty_dist': {'normal': 1}, 'type_dist': {'objective': 1},
            }, format='json')
        assert bulk.status_code == 201, bulk.data
        bulk_id = bulk.data['task_id']
        ready_path.with_suffix('.bulk').write_text(str(bulk_id))
    ready_path.with_suffix('.tmp').write_text(str(good))
    ready_path.with_suffix('.tmp').replace(ready_path)
    if connection.vendor == 'postgresql':
        removed = ready_path.with_suffix('.removed')
        wait_for(removed.exists)
        with transaction.atomic():
            resumed = retry(SimpleNamespace(user=User.objects.get(pk=good_id)), {'id': good, 'request_id': str(uuid4())})
        assert resumed['id'] == good and resumed['payload']['requires_ulr']
        retry_bulk = f'/api/quizzes/admin/pipeline-tasks/{bulk_id}/retry/'
        recovered_bulk = bulk_admin.post(retry_bulk)
        assert recovered_bulk.status_code == 202 and recovered_bulk.data['id'] == bulk_id
        assert bulk_admin.post(retry_bulk).status_code == 200
        ready_path.with_suffix('.requeued').touch()

    def finished():
        title = Conversation.objects.get(conversation_id=conversation_id).title
        accepted, rejected = ContentPipelineTask.objects.get(pk=good), ContentPipelineTask.objects.get(pk=revoked)
        if title == TITLE and accepted.status == 'review' and rejected.status == 'failed':
            return accepted, rejected

    accepted, rejected = wait_for(finished)
    assert accepted.payload['requires_ulr'] and accepted.result['questions'][0]['question'] == DRAFT['question']
    assert not rejected.result
    mismatch = wait_for(lambda: ContentPipelineTask.objects.filter(pk=mismatch_id, status='failed').first())
    assert '工作进程配置不一致' in mismatch.error_message and mismatch.started_at is None and not mismatch.result
    cutover_title.get(timeout=10)
    cutover_chat.refresh_from_db()
    assert cutover_chat.title == TITLE
    with transaction.atomic():
        restarted = retry(SimpleNamespace(user=User.objects.get(pk=good_id)),
                          {'id': mismatch_id, 'request_id': str(uuid4())})['id']
    retry_job = wait_for(lambda: ContentPipelineTask.objects.filter(pk=restarted, status='review').first())
    assert retry_job.payload['requires_ulr'] and retry_job.result['questions'][0]['question'] == DRAFT['question']

    if connection.vendor == 'postgresql':
        test_directory = Path(ready).parent
        wait_for((test_directory / 'grading-active').exists)
        run_exam_grading_task.delay(user.pk, exam.pk, answers).get(timeout=10)
        assert QuizExam.objects.get(pk=exam.pk).status == 'grading'
        (test_directory / 'grading-continue').touch()
    handoff_exam = wait_for(lambda: QuizExam.objects.filter(pk=exam.pk, status='partial').first())
    assert handoff_exam.total_score == 8 and handoff_exam.failed_count == 1
    failed = handoff_exam.results.get(question=objective)
    assert failed.status == 'failed' and failed.attempts == 1 and failed.user_answer == 'A'
    assert failed.question_snapshot['correct_answer'] == 'A' and '已变更' in failed.error_metadata['error']
    assert handoff_exam.results.get(question=subjective).user_answer == EXAM_ANSWER
    accepted_old = wait_for(lambda: QuizExam.objects.filter(pk=legacy_exam_id, status='completed').first())
    assert accepted_old.total_score == 8 and accepted_old.requires_ulr

    Question.objects.filter(pk=objective.pk).update(correct_answer='A')
    run_exam_grading_task.apply_async((user.pk, exam.pk, answers), queue=CUTOVER_QUEUE).get(timeout=10)
    failed.refresh_from_db()
    assert failed.attempts == 1 and failed.status == 'failed'
    resumed = exams.post(f'/api/quizzes/exams/{exam.pk}/retry/', {'question_id': objective.pk}, format='json')
    assert resumed.status_code == 202, resumed.data
    recovered = wait_for(lambda: QuizExam.objects.filter(pk=exam.pk, status='completed').first())
    assert recovered.total_score == 18 and list(recovered.results.order_by('position').values_list('attempts', flat=True)) == [1, 2]
    if connection.vendor == 'postgresql':
        with patch.object(run_exam_grading_task, 'delay',
                          side_effect=lambda *args: run_exam_grading_task.apply_async(args, queue=CUTOVER_QUEUE)):
            submitted = exams.post('/api/quizzes/submit-exam/', {
                'answers': [answers[1], {**answers[0], 'answer': CRASH_ANSWER}],
            }, format='json')
        assert submitted.status_code == 202, submitted.data
        interrupted_id = submitted.data['exam_id']
        detail_url = f'/api/quizzes/exams/{interrupted_id}/'
        wait_for((test_directory / 'crash-model-started').exists)
        in_progress = exams.get(detail_url).data
        assert in_progress['status'] == 'grading' and in_progress['graded_count'] == 1
        assert not in_progress.get('can_resume')
        expired = timezone.now() - GRADING_RECOVERY_DELAY - timedelta(seconds=1)
        QuizExam.objects.filter(pk=interrupted_id).update(started_at=expired)
        # Elapsed time alone cannot replace a worker that still holds the exam.
        assert exams.post(f'{detail_url}retry/', {}, format='json').status_code == 200
        (test_directory / 'kill-allowed').touch()
        wait_for((test_directory / 'crash-worker-killed').exists)
        assert exams.get(detail_url).data['can_resume'] is True
        resumed = exams.post(f'{detail_url}retry/', {}, format='json')
        assert resumed.status_code == 202 and not resumed.data.get('can_resume')
        assert exams.post(f'{detail_url}retry/', {}, format='json').status_code == 200
        recovered = wait_for(lambda: QuizExam.objects.filter(pk=interrupted_id, status='completed').first())
        assert recovered.total_score == 18
        assert list(recovered.results.order_by('position').values_list('attempts', flat=True)) == [1, 1]
        assert recovered.results.get(question=subjective).user_answer == CRASH_ANSWER
        assert Notification.objects.filter(recipient=user, ntype='practice_result',
                                           link=f'/tests/results/{interrupted_id}').count() == 1
    revoked_title.get(timeout=10)
    old.refresh_from_db()
    assert old.title == saved_title
    profile.get(timeout=10)
    revoked_profile.get(timeout=10)
    revision, _ = _snapshot(user.pk)
    assert cache.get(f'ulr:user_profile:{user.pk}:{revision}') == PROFILE
    assert cache.get(f'ulr:user_profile:{revoked_student.pk}:{before_revocation}') is None
    run_teaching_task.delay(good).get(timeout=10)
    assert edges.get(timeout=10)['created'] == 1
    assert run_semantic_edge_analysis_task.delay(SUBJECT).get(timeout=10)['created'] == 0
    edge = KnowledgeEdge.objects.get()
    assert (edge.source.name, edge.target.name, edge.edge_type) == ('时间价值', '折现率', 'prerequisite')
    assert not edge.is_active and edge.institution_id is None
    assert send_project_learning_followups.delay().get(timeout=10)['sent'] == 0
    assert Notification.objects.filter(recipient=user, ntype='learning_followup',
        link=f'/xiaoyu?project={project.pk}&conversation={review_chat.conversation_id}').count() == 1
    assert ProjectLearningEvent.objects.filter(project=project, kind='followup').count() == 1
    assert AIChatMessage.objects.filter(conversation_id=review_chat.conversation_id, role='assistant').count() == 1
    extraction = wait_for(lambda: MemoryExtractionLog.objects.filter(conversation_id=conversation_id).first())
    assert (extraction.source_message_id, extraction.answer_message_id) == (
        reply['user_message']['message_id'], reply['message_id'])
    assert extract_memory_turn.delay(extraction.source_message_id, extraction.answer_message_id).get(timeout=10) == 0
    course_question = wait_for(lambda: CourseVideoQuestion.objects.filter(course=course).first())
    assert course_question.question_data == COURSE_EXERCISE
    assert AICourseService().generate_outline(course.pk)
    assert CourseVideoQuestion.objects.filter(course=course).count() == 1
    if bulk_id is not None:
        bulk = wait_for(lambda: ContentPipelineTask.objects.filter(pk=bulk_id, status='completed').first())
        assert bulk.result['questions_saved'] == 1 and Question.objects.get(text=BULK_DRAFT['question']).knowledge_point_id == bulk_point.pk
    assert Question.objects.count() == 2 + int(bulk_id is not None) and WeeklyAIUsage.objects.get(user=user).ai_calls == 1
    if settings.DATABASES['default']['ENGINE'].endswith('postgresql'):
        assert not (settings.BASE_DIR / 'logs' / 'chat-locks').exists()
    print(json.dumps({'title': TITLE, 'preview': accepted.status, 'revoked': rejected.status, 'candidate_edges': 1}, ensure_ascii=False))


@pytest.mark.django_db(transaction=True)
@pytest.mark.skipif(not os.environ.get('ULR_QUEUE_SMOKE'), reason='optional local Redis queue smoke')
def test_standalone_web_and_celery_share_runtime(user, settings, tmp_path):
    from celery import __version__ as celery_version
    from celery.beat import ScheduleEntry
    from django.db import connection
    from django.utils import timezone
    from redis import Redis
    from redis.exceptions import ConnectionError

    from ai_assistant.models import Bot, PendingConversationTitle, PendingMemoryExtraction
    from courses.models import PendingCourseQuestions
    from quizzes.models import ContentPipelineTask, KnowledgePoint
    from users.models import CourseStudentStatus, Institution, User, WeeklyAIQuotaConfig
    from .test_ulr_process_smoke import child_database_environment

    redis = shutil.which('redis-server')
    if not redis:
        pytest.skip('Redis is required.')
    CourseStudentStatus.objects.create(user=user, is_course_student=True)
    WeeklyAIQuotaConfig.objects.update_or_create(pk=1, defaults={'experience_calls': 20, 'course_calls': 200})
    bot = Bot.objects.create(is_xiaoyu=True, name='小宇', bot_type='planner')
    point = KnowledgePoint.objects.create(name='折现率', subject=SUBJECT, level='kp')
    KnowledgePoint.objects.create(name='时间价值', subject=SUBJECT, level='kp')
    foreign = Institution.objects.create(name='合成机构', slug='ulr-queue-foreign')
    KnowledgePoint.objects.create(name=FOREIGN, subject=SUBJECT, level='kp', institution=foreign)
    admins = [User.objects.create_superuser(username=f'ulr-queue-admin-{index}') for index in range(2)]
    child_db = child_database_environment(connection, tmp_path / 'queue.sqlite3')
    bundle = tmp_path / 'release' / 'backend'
    bundle.mkdir(parents=True)
    for source in settings.BASE_DIR.iterdir():
        if source.is_dir() and ((source / '__init__.py').is_file() or source.name in {'prompts', 'templates', 'static'}):
            shutil.copytree(source, bundle / source.name, ignore=shutil.ignore_patterns('__pycache__'))
        elif source.name in {'ai_service.py', 'manage.py', 'requirements.txt'}:
            shutil.copy2(source, bundle / source.name)

    calls = []

    class Model(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if request.get('stream'):
                calls.append('chat')
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.end_headers()
                self.wfile.write(b'data: {"choices":[{"delta":{"content":"Ready."}}]}\n\n'
                                 b'data: {"choices":[{"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n')
                return
            name, = [tool['function']['name'] for tool in request['tools']]
            messages = json.dumps(request['messages'], ensure_ascii=False)
            course_question = name == 'submit_questions' and COURSE_TRANSCRIPT in messages
            bulk_question = name == 'submit_questions' and 'BULK-QUEUE' in messages
            calls.append('course-questions' if course_question else 'bulk-questions' if bulk_question else name)
            if name == 'submit_edges':
                assert FOREIGN not in json.dumps(request['messages'])
            if name == 'submit_title':
                assert 'REVOKED_QUEUED_TITLE_SOURCE' not in json.dumps(request['messages'])
            if name == 'submit_profile':
                assert 'ACTIVE_QUEUED_PROFILE' in json.dumps(request['messages'])
                assert 'REVOKED_QUEUED_PROFILE' not in json.dumps(request['messages'])
            result = {'submit_title': {'title': TITLE}, 'submit_questions': {'questions': [DRAFT]},
                      'submit_outline': {'items': [{'title': '折现', 'timestamp_seconds': 0, 'description': '合成大纲'}]},
                      'submit_profile': PROFILE,
                      'submit_grading_result': {'score': 8, 'feedback': '说明了时点。', 'analysis': '统一现金流计价时点。', 'memorix_rating': 3},
                      'submit_objective_analysis': {'why_correct': '统一计价时点。', 'why_wrong': '', 'pitfalls': ''},
                      'submit_classification': {'detected_difficulty': 'normal', 'difficulty_match': True,
                          'difficulty_mismatch_reason': '', 'knowledge_tags': ['BULK-QUEUE'], 'question_type': 'objective',
                          'subjective_type': None, 'answer_correct': True, 'answer_accuracy_note': '', 'bloom_level': 'apply'},
                      'submit_memories': {'memories': []}, 'submit_edges': {'items': [EDGE, {**EDGE, 'target_name': FOREIGN}]}}[name]
            if course_question:
                result = {'items': [COURSE_EXERCISE]}
            if bulk_question:
                result = {'questions': [BULK_DRAFT]}
            if name == 'submit_grading_result':
                message = json.dumps(request['messages'], ensure_ascii=False)
                assert '同一时点' in message
                assert request['tools'][0]['function']['parameters']['properties']['score']['maximum'] == 10
                if connection.vendor == 'postgresql' and EXAM_ANSWER in message:
                    (tmp_path / 'grading-active').touch()
                    wait_for((tmp_path / 'grading-continue').exists, timeout=15)
                if CRASH_ANSWER in message and not (tmp_path / 'crash-worker-killed').exists():
                    (tmp_path / 'crash-model-started').touch()
                    wait_for((tmp_path / 'crash-worker-killed').exists, timeout=15)
                    return
            body = {'choices': [{'finish_reason': 'tool_calls', 'message': {'tool_calls': [{
                'id': name, 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(result)},
            }]}}]}
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(body).encode())

    with TemporaryDirectory(prefix='ulrq-', dir='/tmp') as directory, ExitStack() as services:
        address = Path(directory) / 'redis.sock'

        def start(command, log, env=None, *, pass_fds=()):
            output = services.enter_context((tmp_path / log).open('w+'))
            process = subprocess.Popen(command, cwd=bundle, env=env, stdout=output, stderr=subprocess.STDOUT, pass_fds=pass_fds)

            def stop():
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()

            services.callback(stop)
            return process

        redis_process = start([redis, '--port', '0', '--unixsocket', str(address), '--save', '', '--appendonly', 'no'], 'redis.log')
        client = services.enter_context(closing(Redis(unix_socket_path=str(address))))

        def ping():
            assert redis_process.poll() is None
            try:
                return client.ping()
            except ConnectionError:
                return False

        wait_for(ping)
        model = services.enter_context(ThreadingHTTPServer(('127.0.0.1', 0), Model))
        Thread(target=model.serve_forever, daemon=True).start()
        services.callback(model.shutdown)
        env = {**{key: value for key, value in os.environ.items()
                  if not key.startswith('UNIMIND_DSH_') and key != 'UNIMIND_LEARNING_RUNTIME'},
            **child_db, 'PYTHONPATH': str(bundle), 'DJANGO_SETTINGS_MODULE': 'school_system.settings',
            'DJANGO_ENV': 'production', 'DEBUG': 'false', 'ALLOWED_HOSTS': '127.0.0.1', 'SECRET_KEY': 'local-queue-smoke',
            'SECURE_SSL_REDIRECT': 'true', 'USE_X_FORWARDED_PROTO': 'true',
            'ACCOUNT_ENABLED': 'false', 'SENTRY_DSN': '', 'CORS_ALLOW_ALL_ORIGINS': 'false', 'ENABLED_APPS': '',
            'CACHE_REDIS_URL': f'unix://{address}?db=1',
            'CELERY_BROKER_URL': f'redis+socket://{address}?virtual_host=0',
            'CELERY_RESULT_BACKEND': f'redis+socket://{address}?virtual_host=0',
            'CELERY_BEAT_SCHEDULE_FILENAME': str(tmp_path / 'beat-schedule'),
            'CELERY_TASK_DEFAULT_QUEUE': 'default', 'CELERY_TASK_IGNORE_RESULT': 'false',
            'QUIZ_EXAM_GRADING_USE_CELERY': 'true',
            'LLM_API_KEY': 'local-queue-smoke', 'LLM_BASE_URL': f'http://127.0.0.1:{model.server_port}/v1/chat/completions',
            'UNIMIND_DSH_ENABLED': 'true', 'UNIMIND_DSH_TEACHING_ENABLED': 'true',
            'UNIMIND_DSH_STATE_DIR': 'invalid-legacy-directory',
            'UNIMIND_CONTENT_INSTITUTION_ID': 'global',
            'UNIMIND_DIRECTUS_ADMIN_MAP': json.dumps({str(uuid4()): admin.pk for admin in admins})}
        from requests import Session, Timeout, ConnectionError as HTTPConnectionError
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen()
            public_url = f'http://127.0.0.1:{listener.getsockname()[1]}'
            daphne = start([sys.executable, '-m', 'daphne', '--fd', str(listener.fileno()), 'school_system.asgi:application'],
                           'daphne.log', env, pass_fds=(listener.fileno(),))

        with Session() as probe:
            probe.trust_env = False

            def healthy():
                assert daphne.poll() is None, (tmp_path / 'daphne.log').read_text()
                try:
                    check = probe.get(f'{public_url}/health/', headers={'X-Forwarded-Proto': 'https'},
                                      timeout=2, allow_redirects=False)
                except (HTTPConnectionError, Timeout):
                    return False
                assert check.status_code == 200, check.text
                return check.json() == {'status': 'ok', 'database': True, 'cache': True}

            wait_for(healthy)
        ready = tmp_path / 'queued'
        web = start([sys.executable, str(bundle / Path(__file__).relative_to(settings.BASE_DIR)),
                     str(user.pk), str(bot.pk), str(point.pk), str(ready), public_url], 'web.log', env)
        wait_for(lambda: ready.exists() or web.poll() is not None)
        assert ready.exists() and web.poll() is None, (tmp_path / 'web.log').read_text()
        if connection.vendor == 'postgresql':
            task_id = int(ready.read_text())
            for raw in client.lrange('default', 0, -1):
                job = json.loads(raw)
                if job['headers']['task'] == 'backoffice.run_teaching_task' and json.loads(b64decode(job['body']))[0] == [task_id]:
                    assert client.lrem('default', 1, raw) == 1
                    break
            else:
                pytest.fail('Expected the old teaching task in the local queue.')
            bulk_id = int(ready.with_suffix('.bulk').read_text())
            for bulk_raw in client.lrange('default', 0, -1):
                job = json.loads(bulk_raw)
                if (job['headers']['task'] == 'quizzes.run_bulk_pipeline_task'
                        and json.loads(b64decode(job['body']))[1]['task_id'] == bulk_id):
                    assert client.lrem('default', 1, bulk_raw) == 1
                    break
            else:
                pytest.fail('Expected the bulk task in the local queue.')
            ContentPipelineTask.objects.filter(pk=task_id, status='pending').update(updated_at=timezone.now() - timedelta(minutes=6))
            old_bulk = ContentPipelineTask.objects.get(pk=bulk_id, status='running')
            assert not old_bulk.payload.get('requires_ulr')
            ContentPipelineTask.objects.filter(pk=bulk_id).update(status='failed', progress=2,
                payload={**old_bulk.payload, 'current_stage': 'select_kps'}, finished_at=timezone.now())
            ready.with_suffix('.removed').touch()
            wait_for(lambda: ready.with_suffix('.requeued').exists() or web.poll() is not None)
            assert ready.with_suffix('.requeued').exists(), (tmp_path / 'web.log').read_text()
            client.lpush('default', raw, bulk_raw)  # The original deliveries arrive after recovery.
        def service_command(name):
            unit = settings.BASE_DIR.parent / 'deploy' / f'{name}.service'
            return shlex.split(next(line.removeprefix('ExecStart=') for line in unit.read_text().splitlines()
                                    if line.startswith('ExecStart=')))[1:]

        wait_for(lambda: client.llen('high_priority') == 5)
        work = {'ai_assistant.tasks.extract_memory_turn': PendingMemoryExtraction,
                'ai_assistant.tasks.generate_conversation_title': PendingConversationTitle}
        dropped = {}
        expired = timezone.now() - timedelta(seconds=1)
        for raw in client.lrange('high_priority', 0, -1):
            message = json.loads(raw)
            name = message['headers']['task']
            if name not in work:
                continue
            args, kwargs, _ = json.loads(b64decode(message['body']))
            if 'pending_job_id' not in kwargs:
                continue
            assert name not in dropped
            pending = work[name].objects.get(pk=kwargs['pending_job_id'], running_until__isnull=True)
            if work[name] is PendingMemoryExtraction:
                assert args == [pending.source_message_id, pending.answer_message_id]
            else:
                assert kwargs['answer_message_id'] == pending.answer_message_id
            assert pending.dispatch_after > timezone.now() and client.lrem('high_priority', 1, raw) == 1
            work[name].objects.filter(pk=pending.pk).update(dispatch_after=expired)
            dropped[name] = pending.pk
        assert dropped.keys() == work.keys()

        course_job = PendingCourseQuestions.objects.get()
        raw_course_job = wait_for(lambda: next((raw for raw in client.lrange('default', 0, -1)
            if json.loads(raw)['headers']['task'] == 'courses.tasks.generate_course_questions_task'), None))
        assert json.loads(b64decode(json.loads(raw_course_job)['body']))[0] == [course_job.pk]
        assert client.lrem('default', 1, raw_course_job) == 1
        PendingCourseQuestions.objects.filter(pk=course_job.pk).update(dispatch_after=expired)

        schedules = ('project-learning-followups', 'pending-memory-extractions', 'pending-conversation-titles',
                     'pending-course-questions')
        with shelve.open(env['CELERY_BEAT_SCHEDULE_FILENAME']) as store:
            store.update({'entries': {name: ScheduleEntry(name=name, **settings.CELERY_BEAT_SCHEDULE[name],
                last_run_at=timezone.now() - timedelta(minutes=2)) for name in schedules}, '__version__': celery_version,
                'tz': settings.TIME_ZONE, 'utc_enabled': settings.USE_TZ})
        beat = start([sys.executable, '-m', 'celery', *service_command('unimind-celery-beat')], 'beat.log', env)
        extra_deliveries = 3 if connection.vendor == 'postgresql' else 0  # One teaching replay and both bulk deliveries.
        wait_for(lambda: client.llen('default') == 7 + extra_deliveries or beat.poll() is not None)
        assert beat.poll() is None, (tmp_path / 'beat.log').read_text()
        jobs = [json.loads(raw) for raw in client.lrange('default', 0, -1)]
        for name in schedules:
            assert [job['headers']['task'] for job in jobs].count(settings.CELERY_BEAT_SCHEDULE[name]['task']) == 1
        subprocess.run([sys.executable, *service_command('unimind-learning-followups')], cwd=bundle, env=env,
                       check=True, capture_output=True, text=True, timeout=15)
        assert client.llen('high_priority') == 3 and client.llen('default') == 8 + extra_deliveries
        assert client.llen('low_priority') == 1
        assert client.llen(CUTOVER_QUEUE) == 3
        for queue in (CUTOVER_QUEUE, 'default'):
            jobs = [json.loads(raw) for raw in client.lrange(queue, 0, -1)]
            (grading_job,) = [job for job in jobs if job['headers']['task'] == 'quizzes.run_exam_grading_task']
            args, kwargs, _ = json.loads(b64decode(grading_job['body']))
            assert len(args) == 3 and args[0] == user.pk and args[2] is None and not kwargs
        legacy_worker = start([sys.executable, '-m', 'celery', '-A', 'school_system', 'worker', '--pool=solo',
                               '--loglevel=INFO', '--without-gossip', '--without-mingle', '--without-heartbeat',
                               '-Q', CUTOVER_QUEUE, '--hostname=cutover-smoke@%h'],
                              'legacy-worker.log', {**env, 'UNIMIND_LEARNING_RUNTIME': 'legacy'})
        start([sys.executable, '-m', 'celery', '-A', 'school_system', 'worker', '--pool=solo', '--loglevel=INFO',
               '--without-gossip', '--without-mingle', '--without-heartbeat'], 'worker.log', env)
        if connection.vendor == 'postgresql':
            wait_for(lambda: (tmp_path / 'kill-allowed').exists() or web.poll() is not None)
            assert (tmp_path / 'kill-allowed').exists() and legacy_worker.poll() is None, (tmp_path / 'web.log').read_text()
            legacy_worker.kill()
            assert legacy_worker.wait(5) != 0
            (tmp_path / 'crash-worker-killed').touch()
        assert web.wait(35) == 0, ''.join((tmp_path / f'{name}.log').read_text()
                                         for name in ('web', 'daphne', 'worker', 'legacy-worker', 'beat'))
        assert [calls.count(name) for name in ('chat', 'submit_title', 'submit_profile', 'submit_questions', 'submit_edges')] == [1, 2, 1, 2, 2]
        assert calls.count('submit_memories') == 1
        assert (calls.count('submit_outline'), calls.count('course-questions')) == (2, 1)
        assert calls.count('bulk-questions') == calls.count('submit_classification') == int(connection.vendor == 'postgresql')
        assert not any(model.objects.filter(pk=dropped[name]).exists() for name, model in work.items())
        settled = PendingCourseQuestions.objects.get(transcript_id=course_job.transcript_id, revision=course_job.revision)
        assert settled.pk == course_job.pk and settled.completed_at is not None and settled.running_until is None
        assert (calls.count('submit_grading_result'), calls.count('submit_objective_analysis')) == (
            (4, 2) if connection.vendor == 'postgresql' else (2, 1))
        worker_log = (tmp_path / 'worker.log').read_text()
        observations = [line for line in worker_log.splitlines() if 'ai.obs operation=' in line]
        assert any('ulr.quizzes.preview_parse' in line and f"'request_id': 'teaching:{ready.read_text()}'" in line
                   and "'runtime': 'ulr'" in line for line in observations)
        assert any('quizzes.grade_question' in line and "'request_id': 'exam:" in line
                   and "'runtime': 'ulr'" in line for line in observations)
        assert any('courses.generate_questions' in line and f"'request_id': 'course-questions:{course_job.pk}'" in line
                   for line in observations)
        for operation, prefix in (('assistant.title', 'title'), ('assistant.memory_extract', 'memory')):
            assert any(f'operation={operation} ' in line and f"'request_id': '{prefix}:" in line
                       and "'source_message_id':" in line and "'answer_message_id':" in line for line in observations)


if __name__ == '__main__':
    submit_from_web()
