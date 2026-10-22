from rest_framework import serializers
from .access import accessible_bot
from .models import AgentNoteBinding, Note, Notebook, Tag


class OwnedRelationsMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = self.context['request'].user
        for field, model in (('parent', Notebook), ('notebook', Notebook), ('note', Note)):
            if field in self.fields:
                self.fields[field].queryset = model.objects.filter(user=user)


class NotebookSerializer(OwnedRelationsMixin, serializers.ModelSerializer):
    class Meta:
        model = Notebook
        fields = ['id', 'name', 'parent', 'position']

    def validate_parent(self, parent):
        current = parent
        while current:
            if self.instance and current.pk == self.instance.pk:
                raise serializers.ValidationError('不能将笔记本移入自身或子笔记本。')
            current = current.parent
        return parent


class TagNamesField(serializers.ListField):
    def get_attribute(self, instance):
        return list(instance.tags.values_list('name', flat=True))


class NoteSerializer(OwnedRelationsMixin, serializers.ModelSerializer):
    content = serializers.CharField(trim_whitespace=False, allow_blank=True, required=False)
    tags = TagNamesField(child=serializers.CharField(max_length=100), required=False)
    backlinks = serializers.SerializerMethodField()
    version = serializers.IntegerField(min_value=1, required=False)

    class Meta:
        model = Note
        fields = ['id', 'title', 'content', 'notebook', 'tags', 'is_favorite', 'version', 'deleted_at', 'updated_at', 'backlinks']
        read_only_fields = ['deleted_at', 'updated_at']

    def get_backlinks(self, note):
        return list(Note.objects.filter(user=note.user, deleted_at__isnull=True, outgoing_links__target=note).values('id', 'title'))

    def validate_tags(self, tags):
        return list(dict.fromkeys(tag.strip() for tag in tags if tag.strip()))

    def create(self, validated_data):
        tags = validated_data.pop('tags', [])
        validated_data.pop('version', None)
        note = Note.objects.create(user=self.context['request'].user, **validated_data)
        self.save_tags(note, tags)
        return note

    @staticmethod
    def save_tags(note, names):
        note.tags.set([Tag.objects.get_or_create(user=note.user, name=name)[0] for name in names])


class BindingSerializer(OwnedRelationsMixin, serializers.ModelSerializer):
    bot = serializers.IntegerField(min_value=1)

    class Meta:
        model = AgentNoteBinding
        fields = ['id', 'bot', 'note', 'notebook']
        validators = []

    def validate(self, data):
        if bool(data.get('note')) == bool(data.get('notebook')):
            raise serializers.ValidationError('请选择一篇笔记或一个笔记本。')
        if data.get('note') and data['note'].deleted_at:
            raise serializers.ValidationError('不能关联回收站中的笔记。')
        data['bot'] = accessible_bot(self.context['request'].user, data['bot'])
        return data

    def to_representation(self, instance):
        return {'id': instance.pk, 'bot': instance.bot_id, 'note': instance.note_id, 'notebook': instance.notebook_id}

    def create(self, validated_data):
        return AgentNoteBinding.objects.get_or_create(user=self.context['request'].user, **validated_data)[0]
