from rest_framework import serializers
from .models import AIChatMessage, AgentMemory, Bot, BotVisibility, Conversation, StudyPlan
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
            'is_exclusive',
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
        fields = ('conversation_id', 'title', 'message_count', 'created_at', 'updated_at')


class AIChatMessageSerializer(serializers.ModelSerializer):
    conversation_title = serializers.SerializerMethodField()

    class Meta:
        model = AIChatMessage
        fields = ('id', 'role', 'content', 'timestamp', 'bot', 'metadata', 'feedback', 'conversation_id', 'conversation_title')

    def get_conversation_title(self, obj):
        title = getattr(obj, '_conversation_title', None)
        return title or ''


class StudyPlanSerializer(serializers.ModelSerializer):
    task_progress = serializers.SerializerMethodField()

    class Meta:
        model = StudyPlan
        fields = (
            'id', 'title', 'summary', 'status', 'plan_data',
            'auto_generated', 'completed_at', 'created_at', 'updated_at',
            'task_progress',
        )
        read_only_fields = ('id', 'auto_generated', 'completed_at', 'created_at', 'updated_at', 'task_progress')

    def get_task_progress(self, obj):
        tasks = (obj.plan_data or {}).get('tasks', [])
        total = len(tasks)
        completed = sum(1 for t in tasks if t.get('status') == 'completed')
        skipped = sum(1 for t in tasks if t.get('status') == 'skipped')
        return {'total': total, 'completed': completed, 'skipped': skipped}


class AgentMemorySerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentMemory
        fields = (
            'id', 'memory_type', 'key', 'value', 'source',
            'confidence', 'last_used_at', 'use_count', 'is_active',
            'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'source', 'last_used_at', 'use_count', 'created_at', 'updated_at')
