import logging
import threading
from typing import Any, Dict, List

from django.conf import settings
from django.db import connections

from quizzes.ai_workflow import run_exam_grading
from quizzes.tasks import run_exam_grading_task


logger = logging.getLogger(__name__)


def _start_thread_grading(user_id: int, exam_id: int, questions_data: List[Dict[str, Any]]) -> None:
    def grade():
        try:
            run_exam_grading(user_id, exam_id, questions_data)
        finally:
            connections.close_all()

    thread = threading.Thread(
        target=grade,
        daemon=True,
    )
    thread.start()


def dispatch_exam_grading(user_id: int, exam_id: int, questions_data: List[Dict[str, Any]]) -> None:
    use_celery = bool(getattr(settings, "QUIZ_EXAM_GRADING_USE_CELERY", False))
    if not use_celery:
        _start_thread_grading(user_id, exam_id, questions_data)
        return

    try:
        run_exam_grading_task.delay(user_id, exam_id, questions_data)
    except Exception as exc:
        logger.exception("Celery dispatch exam grading unavailable, fallback thread mode: %s", exc)
        _start_thread_grading(user_id, exam_id, questions_data)

