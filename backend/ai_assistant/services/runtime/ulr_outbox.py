"""Publish committed auxiliary work without blocking the chat response."""
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import BoundedSemaphore

from django.db import connections, transaction
from django.db.models import Q
from django.utils import timezone
from kombu.exceptions import OperationalError

from ai_assistant.services.runtime.ulr_structured import RetryableProviderFailure


logger = logging.getLogger(__name__)
_PUBLISHERS = ThreadPoolExecutor(max_workers=2, thread_name_prefix='ulr-outbox')
_PUBLISH_SLOTS = BoundedSemaphore(2)
_RECOVERY_DELAY = timedelta(minutes=2)


def publish_after_commit(publish, job_id):
    def dispatch():
        try:
            publish(job_id)
        finally:
            try:
                connections.close_all()
            finally:
                _PUBLISH_SLOTS.release()

    def submit():
        # The periodic dispatcher handles overflow without blocking the chat or growing a local queue.
        if _PUBLISH_SLOTS.acquire(blocking=False):
            try:
                _PUBLISHERS.submit(dispatch)
            except RuntimeError:
                _PUBLISH_SLOTS.release()
                raise

    transaction.on_commit(submit, robust=True)


def publish_job(jobs, send):
    now = timezone.now()
    # Keep a durable record even after the broker acknowledges the message.
    claimed_until = now + _RECOVERY_DELAY
    if not jobs.filter(dispatch_after__lte=now).update(dispatch_after=claimed_until):
        return False
    claimed = jobs.filter(dispatch_after=claimed_until)
    job = claimed.first()
    if job is None:
        return False
    try:
        if send(job) is False:
            claimed.delete()
    except OperationalError:
        claimed.update(dispatch_after=timezone.now())
        logger.warning('Could not queue %s job %s', job._meta.model_name, job.pk)
        return False
    return True


def consume_job(jobs, work, *, retry_provider_failure=False):
    now = timezone.now()
    running_until = now + _RECOVERY_DELAY
    if not jobs.filter(Q(running_until__isnull=True) | Q(running_until__lte=now)).update(
            running_until=running_until, dispatch_after=running_until):
        return None
    claimed = jobs.filter(running_until=running_until)
    job = claimed.first()
    if job is None:
        return None
    try:
        result = work(job, claimed)
    except ValueError as exc:
        if retry_provider_failure and isinstance(exc, RetryableProviderFailure) and not job.provider_retry_used:
            claimed.update(provider_retry_used=True)
            return None
        # A rejected model response ends this attempt. An interrupted worker leaves a claim to recover.
        claimed.delete()
        raise
    claimed.delete()
    return result
