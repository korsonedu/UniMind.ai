"""Coordinate build recovery with the worker that owns the original task."""
from datetime import timedelta
from hashlib import blake2b
from uuid import UUID

from django.db import connection
from django.utils import timezone

from ai_assistant.services.ulr_config import ulr_enabled
from .models import KnowledgeTreeBuild


BUILD_RECOVERY_DELAY = timedelta(minutes=5)


def build_lock_key(build_id):
    digest = blake2b(UUID(str(build_id)).bytes, digest_size=8, person=b'kb-build').digest()
    return int.from_bytes(digest, 'big', signed=True)


def can_resume_build(build):
    status = KnowledgeTreeBuild.Status
    if not build.requires_ulr and (build.status == status.RUNNING or not ulr_enabled()):
        return False
    return (
        build.status == status.FAILED
        or (
            connection.vendor == 'postgresql'
            and build.status in (status.PENDING, status.RUNNING)
            and build.updated_at <= timezone.now() - BUILD_RECOVERY_DELAY
        )
    )


def lock_build_for_resume(build):
    """For in-flight recovery, hold the lock through the retry transaction."""
    if build.status == KnowledgeTreeBuild.Status.FAILED:
        return True
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_try_advisory_xact_lock(%s)', [build_lock_key(build.pk)])
        return cursor.fetchone()[0]


def reset_for_queue(build):
    now = timezone.now()
    updated = KnowledgeTreeBuild.objects.filter(
        pk=build.pk, created_by_id=build.created_by_id, status=build.status, updated_at=build.updated_at,
    ).update(status=KnowledgeTreeBuild.Status.PENDING, requires_ulr=True, error_message='', updated_at=now)
    if updated:
        build.updated_at = now
    return bool(updated)
