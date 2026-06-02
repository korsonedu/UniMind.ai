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


@receiver(post_delete, sender='courses.Course')
def _on_course_deleted(sender, instance, **kwargs):
    """课程删除时递减机构存储用量。"""
    inst = instance.institution
    if not inst:
        return
    total = (
        _get_file_size(instance.video_file)
        + _get_file_size(instance.cover_image)
        + _get_file_size(instance.courseware)
        + _get_file_size(instance.reference_materials)
    )
    if total > 0:
        from users.quota import remove_storage_usage
        remove_storage_usage(inst, total)
        logger.info("Course %s deleted, freed %d bytes from institution %s", instance.pk, total, inst.pk)


@receiver(post_delete, sender='courses.Album')
def _on_album_deleted(sender, instance, **kwargs):
    """专辑删除时递减机构存储用量。"""
    inst = instance.institution
    if not inst:
        return
    total = _get_file_size(instance.cover_image)
    if total > 0:
        from users.quota import remove_storage_usage
        remove_storage_usage(inst, total)
        logger.info("Album %s deleted, freed %d bytes from institution %s", instance.pk, total, inst.pk)


@receiver(post_delete, sender='courses.StartupMaterial')
def _on_startup_material_deleted(sender, instance, **kwargs):
    """启动资料删除时递减机构存储用量。"""
    inst = instance.institution
    if not inst:
        return
    total = _get_file_size(instance.file)
    if total > 0:
        from users.quota import remove_storage_usage
        remove_storage_usage(inst, total)
        logger.info("StartupMaterial %s deleted, freed %d bytes from institution %s", instance.pk, total, inst.pk)
