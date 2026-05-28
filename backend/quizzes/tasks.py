import logging

from celery import shared_task

from quizzes.ai_workflow import run_exam_grading
from quizzes.services.ai_parse_service import run_parse_task

logger = logging.getLogger(__name__)


@shared_task(name='quizzes.run_exam_grading_task')
def run_exam_grading_task(user_id: int, exam_id: int, questions_data):
    run_exam_grading(user_id, exam_id, questions_data)


@shared_task(name='quizzes.run_ai_parse_task')
def run_ai_parse_task(raw_text: str, task_id: str):
    run_parse_task(raw_text, task_id)


@shared_task(name='quizzes.run_adversarial_pipeline_task')
def run_adversarial_pipeline_task(task_id: int, kp_ids: list, questions_per_kp: int, difficulty: str = "normal", types: list = None):
    from quizzes.models import ContentPipelineTask, KnowledgePoint
    from quizzes.services.adversarial_pipeline import _execute_pipeline

    task = ContentPipelineTask.objects.select_related('institution').get(id=task_id)
    kps = list(KnowledgePoint.objects.filter(id__in=kp_ids))
    try:
        _execute_pipeline(task, kps, questions_per_kp, difficulty=difficulty, types=types, institution=task.institution)
    except Exception as e:
        logger.exception("Adversarial pipeline task failed: task_id=%s", task_id)
        task.status = 'failed'
        task.error_message = str(e)[:500]
        from django.utils import timezone
        task.finished_at = timezone.now()
        task.save(update_fields=['status', 'error_message', 'finished_at', 'updated_at'])


@shared_task(name='quizzes.generate_personalized_pdf_mock_exam')
def generate_personalized_pdf_mock_exam(record_id: int):
    from quizzes.models import PersonalizedMockExam
    from quizzes.services.pdf_generator import generate_mock_exam_pdf

    record = PersonalizedMockExam.objects.get(id=record_id)
    try:
        record.status = 'processing'
        record.save(update_fields=['status'])
        generate_mock_exam_pdf(record)
        record.status = 'ready'
        record.save(update_fields=['status'])
    except Exception as e:
        record.status = 'failed'
        record.error_message = str(e)
        record.save(update_fields=['status', 'error_message'])
