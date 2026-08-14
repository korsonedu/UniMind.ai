import logging
import threading
from typing import Any, Dict, List

from django.conf import settings

from quizzes.ai_workflow import run_exam_grading
from quizzes.tasks import run_exam_grading_task


logger = logging.getLogger(__name__)


def _start_thread_grading(user_id: int, exam_id: int, questions_data: List[Dict[str, Any]]) -> None:
    thread = threading.Thread(
        target=run_exam_grading,
        args=(user_id, exam_id, questions_data),
        daemon=True,
    )
    thread.start()


def _has_active_celery_worker(timeout: float = 1.0) -> bool:
    try:
        inspector = run_exam_grading_task.app.control.inspect(timeout=timeout)
        ping_result = inspector.ping() if inspector else None
        return bool(ping_result)
    except Exception:
        return False


def dispatch_exam_grading(user_id: int, exam_id: int, questions_data: List[Dict[str, Any]]) -> None:
    use_celery = bool(getattr(settings, "QUIZ_EXAM_GRADING_USE_CELERY", False))
    if not use_celery:
        _start_thread_grading(user_id, exam_id, questions_data)
        return

    try:
        if not _has_active_celery_worker():
            raise RuntimeError("no_active_celery_workers")
        run_exam_grading_task.delay(user_id, exam_id, questions_data)
    except Exception as exc:
        logger.exception("Celery dispatch exam grading unavailable, fallback thread mode: %s", exc)
        _start_thread_grading(user_id, exam_id, questions_data)

