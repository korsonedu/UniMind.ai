import logging
from django.db.models.signals import post_delete
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_delete, sender='articles.Article')
def _on_article_deleted(sender, instance, **kwargs):
    """文章删除时递减机构存储用量。"""
    inst = instance.institution
    if not inst:
        return
    try:
        size = instance.cover_image.size if instance.cover_image else 0
    except Exception:
        size = 0
    if size > 0:
        from users.quota import remove_storage_usage
        remove_storage_usage(inst, size)
        logger.info("Article %s deleted, freed %d bytes from institution %s", instance.pk, size, inst.pk)
