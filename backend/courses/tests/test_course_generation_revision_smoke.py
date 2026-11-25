import json
from datetime import timedelta
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import transaction
from django.test import override_settings
from django.utils import timezone
from kombu.exceptions import OperationalError

from backoffice.transcripts import save_transcript
from courses.models import Course, CourseOutline, CourseVideoQuestion, OutlineItem, PendingCourseQuestions, TranscriptSegment, VideoTranscript
from courses.services.ai_course_service import AICourseService
from courses.services.course_question_jobs import publish_course_questions
from courses.tasks import dispatch_pending_course_questions, generate_course_questions_task, generate_outline_task


ORIGINAL = '原版现金流讲稿'
REVISED = '改版后的现金流讲稿'


@pytest.fixture
def course_source(admin_user, settings):
    settings.UNIMIND_CONTENT_INSTITUTION_ID = 'global'
    settings.UNIMIND_LEARNING_RUNTIME = 'ulr'
    course = Course.objects.create(title='合成课程')
    transcript = VideoTranscript.objects.create(course=course, asr_status='completed', full_text=ORIGINAL)
    segment = TranscriptSegment.objects.create(transcript=transcript, index=0, text=ORIGINAL, start_time=0, end_time=10)

    def revise():
        with transaction.atomic():
            return save_transcript(SimpleNamespace(user=admin_user), {
                'id': course.pk, 'revision': transcript.revision, 'segments': [{'id': segment.pk, 'text': REVISED}],
            })['revision']

    return course, transcript, revise


def submit(name, item):
    return {'choices': [{'finish_reason': 'tool_calls', 'message': {'tool_calls': [
        {'function': {'name': name, 'arguments': json.dumps({'items': [item]})}},
    ]}}]}


def question_result(question):
    return submit('submit_questions', {'question': question, 'q_type': 'objective', 'subjective_type': '',
        'options': ['A.甲', 'B.乙'], 'answer': 'A', 'grading_points': None, 'difficulty_level': 'normal'})


@pytest.mark.django_db
def test_revised_transcript_does_not_publish_a_late_outline(course_source, django_capture_on_commit_callbacks):
    course, transcript, revise = course_source
    outline = CourseOutline.objects.create(course=course, status='completed')
    OutlineItem.objects.create(outline=outline, title='原有大纲', timestamp=0, index=0)

    def model(messages, **kwargs):
        assert kwargs['operation'] == 'courses.generate_outline'
        if ORIGINAL in messages[-1]['content']:
            assert revise() == 1
            title = '旧讲稿生成的晚到大纲'
        else:
            assert REVISED in messages[-1]['content']
            title = '按新讲稿生成的大纲'
        return submit('submit_outline', {'title': title, 'timestamp_seconds': 0, 'description': '合成摘要'})

    with (
        patch('ai_engine.service.AIEngine.call_provider', side_effect=model) as provider,
        patch('courses.services.course_question_jobs.publish_after_commit') as followup,
    ):
        with django_capture_on_commit_callbacks(execute=True):
            generate_outline_task.run(course.pk)
        assert list(outline.items.values_list('title', flat=True)) == ['原有大纲']
        assert not PendingCourseQuestions.objects.exists()
        followup.assert_not_called()
        outline.refresh_from_db()
        assert outline.status == 'pending'
        with django_capture_on_commit_callbacks(execute=True):
            generate_outline_task.run(course.pk)
        assert list(outline.items.values_list('title', flat=True)) == ['按新讲稿生成的大纲']
        job = PendingCourseQuestions.objects.get(transcript=transcript, revision=1)
        followup.assert_called_once_with(publish_course_questions, job.pk)
    assert provider.call_count == 2


@pytest.mark.django_db
def test_cutover_waits_for_a_running_legacy_course_outline(course_source, settings, tmp_path):
    from ai_assistant.models import Bot

    course, transcript, _ = course_source
    Bot.objects.create(is_xiaoyu=True, name='小宇', bot_type='planner')
    settings.UNIMIND_DSH_ENABLED = False
    settings.UNIMIND_LEARNING_RUNTIME = 'legacy'
    original = CourseOutline.objects.create(course=course, status='completed')
    OutlineItem.objects.create(outline=original, title='上一版大纲', timestamp=0, index=0)

    def audit(output):
        call_command('audit_dsh_sessions', state_dir=str(tmp_path), api_url='http://127.0.0.1:8000',
                     require_migrated=True, stdout=output)
        return json.loads(output.getvalue())

    def generate(service, transcript_text):
        assert ORIGINAL in transcript_text
        if provider.call_count == 1:
            output = StringIO()
            with pytest.raises(CommandError, match='未完成的迁移项'):
                audit(output)
            blocked = json.loads(output.getvalue())
            assert blocked['blockers'] == {'active_legacy_course_outlines': 1}
            assert blocked['active_course_outline_ids'] == [original.pk]
            assert '上一版大纲' not in output.getvalue() and ORIGINAL not in output.getvalue()
            original.refresh_from_db()
            assert original.status == 'generating'
            CourseOutline.objects.filter(pk=original.pk).update(updated_at=timezone.now() - timedelta(minutes=11))
            with override_settings(UNIMIND_LEARNING_RUNTIME='ulr'):
                assert audit(StringIO())['migrated']
                generate_outline_task.run(course.pk)
            return [{'title': '旧进程迟到的大纲', 'timestamp_seconds': 0}]
        assert provider.call_count == 2
        assert audit(StringIO())['migrated']
        with override_settings(UNIMIND_LEARNING_RUNTIME='legacy'), patch.object(
                timezone, 'now', return_value=timezone.now() + timedelta(minutes=11)):
            generate_outline_task.run(course.pk)
        return [{'title': 'ULR 完成的大纲', 'timestamp_seconds': 0}]

    with patch.object(AICourseService, '_request_outline_items', autospec=True, side_effect=generate) as provider, \
            patch('courses.services.course_question_jobs.publish_after_commit'):
        generate_outline_task.run(course.pk)
    assert provider.call_count == 2
    assert list(original.items.values_list('title', flat=True)) == ['ULR 完成的大纲']
    original.refresh_from_db()
    assert original.status == 'completed'
    assert PendingCourseQuestions.objects.get().transcript_id == transcript.pk


@pytest.mark.django_db
def test_revised_transcript_discards_late_and_queued_questions(course_source):
    course, transcript, revise = course_source
    service = AICourseService()

    def model(messages, **kwargs):
        assert kwargs['operation'] == 'courses.generate_questions'
        if ORIGINAL in messages[-1]['content']:
            assert revise() == 1
            question = '旧讲稿生成的晚到练习'
        else:
            assert REVISED in messages[-1]['content']
            question = '按新讲稿生成的练习'
        return question_result(question)

    with patch('ai_engine.service.AIEngine.call_provider', side_effect=model) as provider:
        assert service.generate_questions_from_transcript(course) == []
        assert not CourseVideoQuestion.objects.filter(course=course).exists()
        assert service.generate_questions_from_transcript(course, transcript_version=(transcript.pk, 0)) == []
        provider.assert_called_once()
        assert service.generate_questions_from_transcript(course, transcript_version=(transcript.pk, 1))
    assert provider.call_count == 2
    row = CourseVideoQuestion.objects.get(course=course)
    assert row.question_data['question'] == '按新讲稿生成的练习'


@pytest.mark.django_db
def test_outline_replay_does_not_regenerate_questions_for_the_same_transcript(course_source):
    course, transcript, revise = course_source
    question_sources = []

    def model(messages, **kwargs):
        if kwargs['operation'] == 'courses.generate_outline':
            return submit('submit_outline', {'title': '课程大纲', 'timestamp_seconds': 0, 'description': '合成摘要'})
        assert kwargs['operation'] == 'courses.generate_questions'
        question_sources.append(REVISED if REVISED in messages[-1]['content'] else ORIGINAL)
        return question_result(question_sources[-1] + '练习')

    with patch('ai_engine.service.AIEngine.call_provider', side_effect=model), \
            patch('courses.services.course_question_jobs.publish_after_commit') as publish:
        generate_outline_task.run(course.pk)
        job = PendingCourseQuestions.objects.get(transcript=transcript)
        generate_outline_task.run(course.pk)
        publish.assert_called_once_with(publish_course_questions, job.pk)
        assert generate_course_questions_task.run(job.pk) == 1
        generate_outline_task.run(course.pk)
        publish.assert_called_once()
        assert generate_course_questions_task.run(job.pk) == 0
        assert question_sources == [ORIGINAL]

        assert revise() == 1
        generate_outline_task.run(course.pk)
        revised_job = PendingCourseQuestions.objects.get(transcript=transcript, revision=1)
        assert revised_job.pk != job.pk
        assert generate_course_questions_task.run(revised_job.pk) == 1
    assert question_sources == [ORIGINAL, REVISED]
    assert CourseVideoQuestion.objects.filter(course=course).count() == 2


@pytest.mark.django_db
def test_course_question_work_recovers_the_original_job_once(course_source):
    course, transcript, _ = course_source
    job = PendingCourseQuestions.objects.create(transcript=transcript, revision=transcript.revision)
    jobs = PendingCourseQuestions.objects.filter(pk=job.pk)
    with patch.object(generate_course_questions_task, 'apply_async', side_effect=OperationalError('broker offline')):
        assert not publish_course_questions(job.pk)
    with patch.object(generate_course_questions_task, 'apply_async') as enqueue:
        assert dispatch_pending_course_questions.run() == 1
        enqueue.assert_called_once_with((job.pk,), retry=False, ignore_result=True)

    with patch('ai_engine.service.AIEngine.call_provider', side_effect=[
        SystemExit, question_result('按原讲稿生成的练习'),
    ]) as provider:
        with override_settings(UNIMIND_LEARNING_RUNTIME='legacy'):
            assert generate_course_questions_task.run(job.pk) == 0
            provider.assert_not_called()
        with pytest.raises(SystemExit):
            generate_course_questions_task.run(job.pk)
        assert jobs.filter(running_until__isnull=False).exists()
        assert not CourseVideoQuestion.objects.filter(course=course).exists()
        assert generate_course_questions_task.run(job.pk) == 0
        provider.assert_called_once()
        jobs.update(running_until=timezone.now(), dispatch_after=timezone.now())
        with patch.object(generate_course_questions_task, 'apply_async') as enqueue:
            assert dispatch_pending_course_questions.run() == 1
            enqueue.assert_called_once_with((job.pk,), retry=False, ignore_result=True)
        assert generate_course_questions_task.run(job.pk) == 1
        assert generate_course_questions_task.run(job.pk) == 0
    assert provider.call_count == 2
    job.refresh_from_db()
    assert job.completed_at is not None and job.running_until is None
    jobs.update(dispatch_after=timezone.now())
    with patch.object(generate_course_questions_task, 'apply_async') as enqueue:
        assert dispatch_pending_course_questions.run() == 0
        assert not publish_course_questions(job.pk)
        enqueue.assert_not_called()
    assert CourseVideoQuestion.objects.get(course=course).question_data['question'] == '按原讲稿生成的练习'
