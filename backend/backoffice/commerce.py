from django.core.exceptions import ValidationError as ModelValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import serializers

from ai_assistant.models import Bot
from payments.models import Order
from payments.serializers import OrderSerializer
from users.learning import set_weekly_quota_config
from users.models import AIAddonProduct, WeeklyAIQuotaConfig
from users.views_learning import AIAddonProductSerializer
from .common import content_institution, identity, paginate


def quota_config(request, data):
    config = WeeklyAIQuotaConfig.objects.filter(pk=1).first()
    return {'experience_calls': config.experience_calls if config else None,
            'course_calls': config.course_calls if config else None,
            'resets': '每周一 00:00（上海时间）'}


def save_quota(request, data):
    field = serializers.IntegerField(min_value=0, allow_null=True)
    experience = field.run_validation(data.get('experience_calls'))
    course = field.run_validation(data.get('course_calls'))
    try:
        config = set_weekly_quota_config(experience_calls=experience, course_calls=course, actor=request.user)
    except ModelValidationError as error:
        raise serializers.ValidationError(error.messages) from error
    return {'id': config.pk, **quota_config(request, data)}


def list_addons(request, data):
    return {'items': AIAddonProductSerializer(AIAddonProduct.objects.all(), many=True).data}


def save_addon(request, data):
    instance = get_object_or_404(AIAddonProduct.objects.select_for_update(), pk=identity(data)) if data.get('id') else None
    serializer = AIAddonProductSerializer(instance, data=data, partial=bool(instance))
    serializer.is_valid(raise_exception=True)
    return AIAddonProductSerializer(serializer.save()).data


def list_orders(request, data):
    query = str(data.get('search', '')).strip()[:200]
    queryset = Order.objects.select_related('user').order_by('-created_at', '-id')
    if query:
        queryset = queryset.filter(Q(user__email__icontains=query) | Q(user__username__icontains=query))
    status = data.get('status')
    if status:
        status = serializers.ChoiceField(choices=Order.STATUS_CHOICES).run_validation(status)
        queryset = queryset.filter(status=status)
    return paginate(queryset, data, lambda order: {**OrderSerializer(order).data,
                                                 'email': order.user.email, 'username': order.user.username})


def _bots():
    institution = content_institution(required=True)
    return Bot.objects.filter(Q(institution=institution) | Q(institution__isnull=True),
                              bot_type__in=['planner', 'exam_generator']).order_by('bot_type', 'id')


def ai_config(request, data):
    from ai_assistant.prompt_sync import get_bot_prompt_template_name
    return {'items': [{'id': bot.pk, 'name': bot.name, 'bot_type': bot.bot_type, 'is_active': bot.is_active,
                       'personality': bot.institution_personality or {},
                       'prompt_template': get_bot_prompt_template_name(bot)} for bot in _bots()]}


def save_ai_config(request, data):
    bot = get_object_or_404(_bots().select_for_update(), pk=identity(data))
    class Input(serializers.Serializer):
        name = serializers.CharField(max_length=100)
        is_active = serializers.BooleanField()
        personality = serializers.DictField(child=serializers.CharField(max_length=500, allow_blank=True))
    payload = Input(data=data)
    payload.is_valid(raise_exception=True)
    values = payload.validated_data
    allowed = {'teaching_style', 'tone', 'knowledge_domain', 'custom_instructions'}
    if set(values['personality']) - allowed:
        raise serializers.ValidationError('包含未知的 AI 配置项。')
    bot.name, bot.is_active = values['name'], values['is_active']
    bot.institution_personality = {key: value for key, value in values['personality'].items() if value}
    bot.save(update_fields=['name', 'is_active', 'institution_personality'])
    return {'id': bot.pk}


READS = {'quota.get': quota_config, 'addons.list': list_addons, 'orders.list': list_orders,
         'ai.config.get': ai_config}
WRITES = {'quota.save': save_quota, 'addons.save': save_addon, 'ai.config.save': save_ai_config}
