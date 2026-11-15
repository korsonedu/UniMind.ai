from rest_framework import serializers
from .models import Notification
from .messages import notification_text


class NotificationSerializer(serializers.ModelSerializer):
    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['title'], data['content'] = notification_text(instance)
        return data

    class Meta:
        model = Notification
        fields = ('id', 'recipient', 'sender', 'ntype', 'title', 'content', 'link', 'is_read', 'created_at')
        read_only_fields = ('recipient', 'sender')
