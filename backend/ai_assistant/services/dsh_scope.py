"""Identity and deadline shared by a teaching job and its nested generation."""
from contextlib import contextmanager
from contextvars import ContextVar
from threading import Event
from time import monotonic

from .dsh_runtime import DshUnavailable


_job = ContextVar('dsh_teaching_job', default=None)
_execution = ContextVar('dsh_generation_execution', default=None)


@contextmanager
def teaching_job(task_id):
    token = _job.set(task_id)
    try:
        yield
    finally:
        _job.reset(token)


def check_teaching_task(task_id=None):
    task_id = task_id or _job.get()
    if task_id is None:
        return
    from backoffice.common import content_institution
    from quizzes.models import ContentPipelineTask
    from users.permissions import is_platform_admin
    task = ContentPipelineTask.objects.select_related('created_by').get(pk=task_id)
    scope = content_institution(required=True)
    if (task.status != 'running' or not is_platform_admin(task.created_by)
            or task.institution_id != (scope.pk if scope else None)):
        raise DshUnavailable('教研任务身份、状态或内容范围已变更。')


def current_execution():
    return _execution.get()


def check_execution(execution, *, check_cancel=True):
    if execution is None:
        return
    if monotonic() >= execution['deadline'] or check_cancel and execution['cancelled'].is_set():
        raise DshUnavailable('DSH 任务已结束或超过截止时间。')
    check_teaching_task(execution['task_id'])


@contextmanager
def generation_scope(execution=None):
    parent = _execution.get()
    owner = execution is None and parent is None
    execution = execution or parent or {'deadline': monotonic() + 90, 'cancelled': Event(), 'task_id': _job.get()}
    token = _execution.set(execution)
    try:
        check_execution(execution)
        yield
        # A successful bridge closes its callbacks before returning its result.
        check_execution(execution, check_cancel=False)
    finally:
        if owner:
            execution['cancelled'].set()
        _execution.reset(token)
