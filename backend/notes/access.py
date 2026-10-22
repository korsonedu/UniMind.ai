from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from ai_assistant.models import Bot, BotVisibility
from users.permissions import has_capability
from .models import Notebook


def accessible_bot(user, bot_id):
    if not has_capability(user, 'ai.assistant'):
        raise PermissionDenied('该账号不能使用 Agent。')
    bot_id = serializers.IntegerField(min_value=1).run_validation(bot_id)
    bot = get_object_or_404(Bot, pk=bot_id, is_active=True)
    if bot.bot_type == 'exam_generator':
        raise PermissionDenied('该 Agent 不支持笔记参考。')
    if bot.institution_id and bot.institution_id != user.institution_id:
        raise PermissionDenied('无法使用其他机构的 Agent。')
    if (not bot.institution_id and bot.bot_type != 'planner' and user.institution_id
            and BotVisibility.objects.filter(bot=bot, institution_id=user.institution_id, is_visible=False).exists()):
        raise PermissionDenied('该 Agent 当前不可见。')
    return bot


def notebook_ids(user, root_ids):
    parents = dict(Notebook.objects.filter(user=user).values_list('id', 'parent_id'))
    result = set(root_ids) & parents.keys()
    while True:
        children = {pk for pk, parent in parents.items() if parent in result} - result
        if not children:
            return result
        result.update(children)
