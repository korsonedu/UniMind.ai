import logging
from django.db.models.signals import post_delete
from django.dispatch import receiver

logger = logging.getLogger(__name__)


def _get_file_size(field) -> int:
    """安全获取文件大小，文件不存在时返回 0。"""
    try:
        if field and hasattr(field, 'size'):
            return field.size or 0
    except Exception:
        pass
    return 0


@receiver(post_delete, sender='quizzes.TeacherExam')
def _on_teacher_exam_deleted(sender, instance, **kwargs):
    """教师试卷删除时递减机构存储用量。"""
    inst = instance.institution
    if not inst:
        return
    total = _get_file_size(instance.exam_pdf)
    if total > 0:
        from users.quota import remove_storage_usage
        remove_storage_usage(inst, total)
        logger.info("TeacherExam %s deleted, freed %d bytes from institution %s", instance.pk, total, inst.pk)


@receiver(post_delete, sender='quizzes.StudentExamSubmission')
def _on_exam_submission_deleted(sender, instance, **kwargs):
    """学生答卷删除时递减机构存储用量。"""
    inst = instance.exam.institution if instance.exam else None
    if not inst:
        return
    total = (
        _get_file_size(instance.answer_pdf)
        + _get_file_size(instance.graded_pdf)
    )
    if total > 0:
        from users.quota import remove_storage_usage
        remove_storage_usage(inst, total)
        logger.info("StudentExamSubmission %s deleted, freed %d bytes from institution %s", instance.pk, total, inst.pk)
