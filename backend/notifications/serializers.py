from rest_framework import serializers
from .models import Notification

class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ('id', 'recipient', 'sender', 'ntype', 'title', 'content', 'link', 'is_read', 'created_at')
