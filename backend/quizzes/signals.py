"""
知识图边自动维护信号。

监听 KnowledgePoint (level='kp') 的变更：
- 新增 KP → 自动生成父子边 + 兄弟边
- 移动 KP（parent 变更）→ 删旧边、建新边、修复旧兄弟群
- 删除 KP → CASCADE 自动删边，无需处理

变更为 SEC/CH/SUB 层级时不触发（它们不参与边生成）。
"""
from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver
from quizzes.models import KnowledgePoint
from quizzes.services.knowledge_edge_sync import sync_kp_neighborhood


@receiver(pre_save, sender=KnowledgePoint)
def capture_old_parent(sender, instance, **kwargs):
    """保存前记录旧 parent_id，供 post_save 做 diff。"""
    if instance.level != 'kp':
        return
    if instance.pk:
        try:
            old = KnowledgePoint.objects.get(pk=instance.pk)
            instance._old_parent_id = old.parent_id
        except KnowledgePoint.DoesNotExist:
            instance._old_parent_id = None
    else:
        instance._old_parent_id = None


@receiver(post_save, sender=KnowledgePoint)
def on_kp_saved(sender, instance, created, **kwargs):
    """KP 保存后增量同步边。"""
    if instance.level != 'kp':
        return
    old_parent_id = getattr(instance, '_old_parent_id', None)
    sync_kp_neighborhood(instance, old_parent_id=old_parent_id)


@receiver(post_delete, sender=KnowledgePoint)
def on_kp_deleted(sender, instance, **kwargs):
    """树边随知识点级联删除，提交后清除邻接缓存。"""
    from django.db import transaction
    from quizzes.services.memorix_scheduler import invalidate_adjacency_cache
    transaction.on_commit(invalidate_adjacency_cache)
