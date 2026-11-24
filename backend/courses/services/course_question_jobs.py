"""Persist course question work before attempting to send it to Celery."""
from ai_assistant.services.ulr_outbox import consume_job, publish_after_commit, publish_job
from ai_engine.observability import observe_background
from courses.models import PendingCourseQuestions


def schedule_course_questions(transcript):
    job = PendingCourseQuestions.objects.create(transcript=transcript, revision=transcript.revision)
    publish_after_commit(publish_course_questions, job.pk)


def publish_course_questions(job_id):
    from courses.tasks import generate_course_questions_task

    return publish_job(PendingCourseQuestions.objects.filter(pk=job_id), lambda job:
        generate_course_questions_task.apply_async((job.pk,), retry=False, ignore_result=True))


def consume_course_questions(job_id):
    from .ai_course_service import AICourseService

    def generate(job, claimed):
        with observe_background('ulr', f'course-questions:{job.pk}'):
            return AICourseService().generate_questions_from_transcript(job.transcript.course,
                transcript_version=(job.transcript_id, job.revision), pending_job=claimed)

    jobs = PendingCourseQuestions.objects.select_related('transcript__course').filter(pk=job_id)
    return len(consume_job(jobs, generate) or ())
