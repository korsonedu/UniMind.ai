from rest_framework import serializers
from .models import Notification, Announcement, AnnouncementRead


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ('id', 'recipient', 'sender', 'ntype', 'title', 'content', 'link', 'is_read', 'created_at')
        read_only_fields = ('recipient', 'sender')


class AnnouncementSerializer(serializers.ModelSerializer):
    publisher_name = serializers.CharField(source='publisher.nickname', read_only=True)
    is_read = serializers.SerializerMethodField()
    read_count = serializers.SerializerMethodField()

    class Meta:
        model = Announcement
        fields = (
            'id', 'publisher', 'publisher_name', 'title', 'content',
            'audience', 'institution', 'is_platform', 'status',
            'created_at', 'updated_at', 'published_at',
            'is_read', 'read_count',
        )
        read_only_fields = ('publisher', 'institution', 'is_platform', 'published_at')

    def get_is_read(self, obj) -> bool:
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        return obj.reads.filter(user=request.user).exists()

    def get_read_count(self, obj) -> int:
        return obj.reads.count()

    def validate(self, data):
        request = self.context.get('request')
        user = request.user
        from users.permissions import is_platform_admin

        # 机构所有者只能给自己机构发，audience 强制 everyone
        if not is_platform_admin(user):
            data['audience'] = 'everyone'
            data['institution'] = user.institution
            data['is_platform'] = False
        else:
            data['institution'] = None
            data['is_platform'] = True

        return data

    def create(self, validated_data):
        validated_data['publisher'] = self.context['request'].user
        return super().create(validated_data)


class AnnouncementReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnnouncementRead
        fields = ('id', 'announcement', 'user', 'read_at')
        read_only_fields = ('user', 'read_at')
