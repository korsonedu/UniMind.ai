from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from ai_assistant.models import Bot
from users.permissions import has_capability
from .models import Notebook


def accessible_bot(user, bot_id=None):
    # Reload account permissions before making private notes available.
    user = get_object_or_404(get_user_model().objects.select_related('access_profile'), pk=user.pk, is_active=True)
    if not has_capability(user, 'ai.assistant'):
        raise PermissionDenied('该账号不能使用 Agent。')
    bots = Bot.objects.filter(is_xiaoyu=True, is_active=True)
    if bot_id is not None:
        bots = bots.filter(pk=serializers.IntegerField(min_value=1).run_validation(bot_id))
    return get_object_or_404(bots)


def notebook_ids(user, root_ids):
    parents = dict(Notebook.objects.filter(user=user).values_list('id', 'parent_id'))
    result = set(root_ids) & parents.keys()
    while True:
        children = {pk for pk, parent in parents.items() if parent in result} - result
        if not children:
            return result
        result.update(children)
