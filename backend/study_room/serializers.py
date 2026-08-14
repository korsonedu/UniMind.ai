from rest_framework import serializers
from .models import ChatMessage
from users.serializers import UserSerializer

class ChatMessageSerializer(serializers.ModelSerializer):
    user_detail = UserSerializer(source='user', read_only=True)
    class Meta:
        model = ChatMessage
        fields = ('id', 'user', 'user_detail', 'content', 'timestamp', 'related_plan')
        read_only_fields = ('user',)
