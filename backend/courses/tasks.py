import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def transcribe_course_task(self, course_id: int):
    from courses.models import Course
    from courses.services.ai_course_service import AICourseService

    course = Course.objects.filter(id=course_id).first()
    if not course:
        return None
    try:
        AICourseService().transcribe_video(course)
    except Exception as exc:
        logger.exception("Celery transcription failed for course %s", course_id)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def generate_outline_task(self, course_id: int):
    from courses.services.ai_course_service import AICourseService

    try:
        AICourseService().generate_outline(course_id)
    except Exception as exc:
        logger.exception("Celery outline generation failed for course %s", course_id)
        raise self.retry(exc=exc)
