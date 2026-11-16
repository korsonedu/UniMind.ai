"""Internal learning identities have the same account lifecycle as their owner."""
from django.db.models.signals import post_delete, post_save, pre_delete
from django.dispatch import receiver

from users.models import User, WorkspaceLearner


@receiver(pre_delete, sender=User)
def remember_learners(sender, instance, **kwargs):
    instance._workspace_learner_ids = list(WorkspaceLearner.objects.filter(account=instance).values_list('user_id', flat=True))


@receiver(post_delete, sender=User)
def delete_learners(sender, instance, **kwargs):
    ids = getattr(instance, '_workspace_learner_ids', [])
    if ids:
        User.objects.filter(pk__in=ids).delete()


@receiver(post_save, sender=User)
def sync_account_status(sender, instance, created, update_fields, **kwargs):
    if not created and (update_fields is None or 'is_active' in update_fields):
        User.objects.filter(workspace_learner__account=instance).update(is_active=instance.is_active)
