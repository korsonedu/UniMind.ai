import logging
import threading
from typing import Optional

from django.conf import settings

logger = logging.getLogger(__name__)


def _start_thread_transcribe(course_id: int, force: bool = False) -> None:
    def _run():
        from courses.models import Course
        from courses.services.ai_course_service import AICourseService
        try:
            course = Course.objects.get(pk=course_id)
            AICourseService().transcribe_video(course, force=force)
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


def dispatch_transcription(course_id: int, force: bool = False) -> None:
    use_celery = bool(getattr(settings, "COURSE_AI_USE_CELERY", False))
    if not use_celery:
        _start_thread_transcribe(course_id, force=force)
        return

    # 生产环境不允许静默回退到 daemon 线程（部署重启会丢任务）。
    if not _has_active_celery_worker():
        raise RuntimeError("Celery 转录队列不可用：没有活动的 worker")
    from courses.tasks import transcribe_course_task

    try:
        transcribe_course_task.delay(course_id, force=force)
    except Exception as exc:
        logger.error(
            "Celery dispatch transcribe failed for course %s: %s",
            course_id, exc.__class__.__name__,
        )
        raise RuntimeError("Celery 转录任务投递失败") from None


def dispatch_outline_generation(course_id: int) -> None:
    use_celery = bool(getattr(settings, "COURSE_AI_USE_CELERY", False))
    if not use_celery:
        _start_thread_outline(course_id)
        return

    # 生产环境不允许静默回退到 daemon 线程（部署重启会丢任务）。
    if not _has_active_celery_worker():
        raise RuntimeError("Celery 大纲队列不可用：没有活动的 worker")
    from courses.tasks import generate_outline_task

    try:
        generate_outline_task.delay(course_id)
    except Exception as exc:
        logger.error(
            "Celery dispatch outline failed for course %s: %s",
            course_id, exc.__class__.__name__,
        )
        raise RuntimeError("Celery 大纲任务投递失败") from None
