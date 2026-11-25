from rest_framework import serializers
from .models import AIChatMessage, AgentMemory, Bot, Conversation
from .prompt_sync import get_bot_prompt_path, get_bot_prompt_template_name


class BotSerializer(serializers.ModelSerializer):
    prompt_template_name = serializers.SerializerMethodField()
    prompt_file_exists = serializers.SerializerMethodField()
    institution_name = serializers.SerializerMethodField()

    class Meta:
        model = Bot
        fields = (
            'id',
            'name',
            'avatar',
            'system_prompt',
            'bot_type',
            'is_active',
            'created_at',
            'prompt_template_name',
            'prompt_file_exists',
            'institution',
            'institution_name',
        )
        read_only_fields = (
            'id', 'created_at', 'prompt_template_name', 'prompt_file_exists',
            'institution', 'institution_name',
        )

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # 非管理员不暴露 system_prompt（含敏感指令和工具配置）
        request = self.context.get('request')
        if request and not getattr(request.user, 'is_staff', False):
            data.pop('system_prompt', None)
        return data

    def get_prompt_template_name(self, obj):
        return get_bot_prompt_template_name(obj)

    def get_prompt_file_exists(self, obj):
        return get_bot_prompt_path(obj).exists()

    def get_institution_name(self, obj):
        if obj.institution:
            return obj.institution.name
        return None


class ConversationSerializer(serializers.ModelSerializer):
    message_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Conversation
        fields = ('conversation_id', 'title', 'is_pinned', 'project_id', 'message_count', 'created_at', 'updated_at')


class AIChatMessageSerializer(serializers.ModelSerializer):
    conversation_title = serializers.SerializerMethodField()
    metadata = serializers.SerializerMethodField()
    conversation_project = serializers.IntegerField(source='_conversation_project', read_only=True, allow_null=True)
    conversation_pinned = serializers.BooleanField(source='_conversation_pinned', read_only=True, default=False)

    class Meta:
        model = AIChatMessage
        fields = ('id', 'role', 'content', 'timestamp', 'bot', 'metadata', 'feedback', 'conversation_id', 'conversation_title', 'conversation_project', 'conversation_pinned')

    def get_conversation_title(self, obj):
        title = getattr(obj, '_conversation_title', None)
        return title or ''

    def get_metadata(self, obj):
        metadata = obj.metadata
        return {key: value for key, value in metadata.items()
                if key not in {'learning_snapshot', 'ulr_context_sources'}} if isinstance(metadata, dict) else metadata


class AgentMemorySerializer(serializers.ModelSerializer):
    def to_representation(self, instance):
        data = super().to_representation(instance)
        from .services.fact_evidence import active, current
        if active():
            views = self.context.setdefault('fact_control_views', {})
            if instance.user_id not in views:
                snapshot = current(instance.user, include_inactive=True)
                views[instance.user_id] = ({row['id']: row for row in snapshot['items']},
                    {row['id']: row['status'] for row in snapshot['unavailable']})
            known, unavailable = views[instance.user_id]
            row = known.get(instance.pk)
            data['memory_state'] = 'known' if row else unavailable.get(instance.pk, 'excluded')
            if row:
                data.update(value=row['value'], confidence=row['confidence'], source=row['source'],
                    updated_at=self.fields['updated_at'].to_representation(row['updated_at']))
            else:
                data.update(value='', confidence=0.0)
        return data

    def create(self, validated_data):
        from .services.memory_core import save_manual_fact
        return save_manual_fact(validated_data)

    def update(self, instance, validated_data):
        from .services.memory_core import save_manual_fact
        return save_manual_fact(validated_data, instance)

    class Meta:
        model = AgentMemory
        fields = (
            'id', 'memory_type', 'key', 'value', 'source',
            'confidence', 'last_used_at', 'use_count', 'is_active',
            'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'source', 'last_used_at', 'use_count', 'created_at', 'updated_at')
