import logging
from django.db.models.signals import post_delete
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_delete, sender='faq_system.Question')
def _on_question_deleted(sender, instance, **kwargs):
    """答疑问题删除时递减机构存储用量。"""
    inst = instance.institution
    if not inst:
        return
    try:
        size = instance.attachment.size if instance.attachment else 0
    except Exception:
        size = 0
    if size > 0:
        from users.quota import remove_storage_usage
        remove_storage_usage(inst, size)
        logger.info("Question %s deleted, freed %d bytes from institution %s", instance.pk, size, inst.pk)
