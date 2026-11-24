from datetime import timedelta
from hashlib import blake2b

from django.db import connection
from django.utils import timezone


GRADING_HARD_LIMIT = 180
GRADING_RECOVERY_DELAY = timedelta(seconds=GRADING_HARD_LIMIT + 60)


def can_resume_grading(exam):
    progress_at = exam.started_at or exam.grading_queued_at or exam.created_at
    return exam.status in ('pending', 'grading') and progress_at <= timezone.now() - GRADING_RECOVERY_DELAY


def grading_lock_key(user_id, exam_id):
    digest = blake2b(f'{user_id}:{exam_id}'.encode(), digest_size=8, person=b'unimind-exam').digest()
    return int.from_bytes(digest, 'big', signed=True)


def lock_grading_for_recovery(exam):
    """Called inside the retry transaction. Do not interrupt a worker running this exam."""
    if connection.vendor != 'postgresql':
        return True
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_try_advisory_xact_lock(%s)', [grading_lock_key(exam.user_id, exam.pk)])
        return cursor.fetchone()[0]
