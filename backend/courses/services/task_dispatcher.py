import logging
import threading
from typing import Optional

from django.conf import settings

logger = logging.getLogger(__name__)


def _start_thread_transcribe(course_id: int) -> None:
    def _run():
        from courses.models import Course
        from courses.services.ai_course_service import AICourseService
        try:
            course = Course.objects.get(pk=course_id)
            AICourseService().transcribe_video(course)
        except Exception as e:
            logger.exception("Threaded transcription failed for course %s", course_id)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()


def _start_thread_outline(course_id: int) -> None:
    def _run():
        from courses.services.ai_course_service import AICourseService
        try:
            AICourseService().generate_outline(course_id)
        except Exception as e:
            logger.exception("Threaded outline generation failed for course %s", course_id)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()


def _has_active_celery_worker(timeout: float = 1.0) -> bool:
    try:
        from courses.tasks import transcribe_course_task
        inspector = transcribe_course_task.app.control.inspect(timeout=timeout)
        ping_result = inspector.ping() if inspector else None
        return bool(ping_result)
    except Exception:
        return False


def dispatch_transcription(course_id: int) -> None:
    use_celery = bool(getattr(settings, "COURSE_AI_USE_CELERY", False))
    if not use_celery:
        _start_thread_transcribe(course_id)
        return

    try:
        if not _has_active_celery_worker():
            raise RuntimeError("no_active_celery_workers")
        from courses.tasks import transcribe_course_task
        transcribe_course_task.delay(course_id)
    except Exception as exc:
        logger.warning("Celery dispatch transcribe unavailable, fallback thread mode: %s", exc)
        _start_thread_transcribe(course_id)


def dispatch_outline_generation(course_id: int) -> None:
    use_celery = bool(getattr(settings, "COURSE_AI_USE_CELERY", False))
    if not use_celery:
        _start_thread_outline(course_id)
        return

    try:
        if not _has_active_celery_worker():
            raise RuntimeError("no_active_celery_workers")
        from courses.tasks import generate_outline_task
        generate_outline_task.delay(course_id)
    except Exception as exc:
        logger.warning("Celery dispatch outline unavailable, fallback thread mode: %s", exc)
        _start_thread_outline(course_id)
