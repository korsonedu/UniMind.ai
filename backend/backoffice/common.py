import logging

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from users.models import Institution


def content_institution(required=False):
    value = settings.UNIMIND_CONTENT_INSTITUTION_ID
    if not value:
        if required:
            raise serializers.ValidationError('内容归属未配置，暂不能修改教学内容。')
        return None
    if value == 'global':
        return None
    key = serializers.IntegerField(min_value=1).run_validation(value)
    return get_object_or_404(Institution, pk=key, is_active=True)


def managed(queryset):
    if settings.UNIMIND_CONTENT_INSTITUTION_ID:
        return queryset.filter(institution=content_institution())
    return queryset


def identity(data, field='id'):
    value = serializers.IntegerField(min_value=1).run_validation(data.get(field))
    return value


def paginate(queryset, data, serialize):
    page = serializers.IntegerField(min_value=1).run_validation(data.get('page', 1))
    size = serializers.IntegerField(min_value=1, max_value=100).run_validation(data.get('page_size', 25))
    return {'items': [serialize(item) for item in queryset[(page - 1) * size:page * size]],
            'total': queryset.count(), 'page': page, 'page_size': size}


def delete_files_after_commit(files):
    def cleanup():
        for file in files:
            if file:
                try:
                    file.storage.delete(file.name)
                except Exception:
                    logging.getLogger(__name__).exception('Backoffice file cleanup failed')
    transaction.on_commit(cleanup)
