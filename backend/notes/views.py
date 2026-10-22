from django.db import transaction
from django.db.models import F, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView
from ai_assistant.models import AIChatMessage, Conversation
from core.authentication import CookieTokenAuthentication
from users.permissions import IsMember, has_capability
from .access import accessible_bot, notebook_ids
from .exports import export_note, export_notebook
from .links import index_links
from .models import AgentNoteBinding, ConversationNoteReference, Note, Notebook, Tag
from .serializers import BindingSerializer, NoteSerializer, NotebookSerializer


class PrivateNotesView:
    authentication_classes = [CookieTokenAuthentication]
    permission_classes = [IsMember]
    pagination_class = None


class NotebookListView(PrivateNotesView, generics.ListCreateAPIView):
    serializer_class = NotebookSerializer

    def get_queryset(self):
        return Notebook.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class NotebookDetailView(PrivateNotesView, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = NotebookSerializer
    http_method_names = ['get', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        return Notebook.objects.filter(user=self.request.user)

    @transaction.atomic
    def patch(self, request, *args, **kwargs):
        # Serialize tree edits so two moves cannot create a cycle together.
        list(Notebook.objects.filter(user=request.user).select_for_update())
        return self.partial_update(request, *args, **kwargs)

    @transaction.atomic
    def delete(self, request, *args, **kwargs):
        list(Notebook.objects.filter(user=request.user).select_for_update())
        return self.destroy(request, *args, **kwargs)

    def perform_destroy(self, notebook):
        Note.objects.filter(user=notebook.user, notebook=notebook).update(
            notebook=notebook.parent, version=F('version') + 1, updated_at=timezone.now())
        notebook.children.filter(user=notebook.user).update(parent=notebook.parent)
        notebook.delete()


def bound_notes(user, bot):
    bindings = AgentNoteBinding.objects.filter(user=user, bot=bot)
    books = notebook_ids(user, bindings.filter(notebook__isnull=False).values_list('notebook_id', flat=True))
    return Q(id__in=bindings.filter(note__isnull=False).values_list('note_id', flat=True)) | Q(notebook_id__in=books)


class NoteListView(PrivateNotesView, generics.ListCreateAPIView):
    serializer_class = NoteSerializer

    def get_queryset(self):
        params = self.request.query_params
        qs = Note.objects.filter(user=self.request.user, deleted_at__isnull=params.get('trash') != '1')
        if params.get('q'):
            qs = qs.filter(Q(title__icontains=params['q']) | Q(content__icontains=params['q']))
        if params.get('notebook') == 'unfiled':
            qs = qs.filter(notebook__isnull=True)
        elif params.get('notebook'):
            value = serializers.IntegerField(min_value=1).run_validation(params['notebook'])
            qs = qs.filter(notebook_id__in=notebook_ids(self.request.user, [value]))
        if params.get('tag'):
            qs = qs.filter(tags__user=self.request.user, tags__name=params['tag'])
        if params.get('favorite') in ('1', 'true'):
            qs = qs.filter(is_favorite=True)
        if params.get('bot'):
            bot_id = serializers.IntegerField(min_value=1).run_validation(params['bot'])
            qs = qs.filter(bound_notes(self.request.user, accessible_bot(self.request.user, bot_id)))
        return qs.prefetch_related('tags').distinct()

    @transaction.atomic
    def perform_create(self, serializer):
        index_links(serializer.save())


class NoteDetailView(PrivateNotesView, generics.RetrieveAPIView):
    serializer_class = NoteSerializer

    def get_queryset(self):
        return Note.objects.filter(user=self.request.user).prefetch_related('tags')

    @transaction.atomic
    def patch(self, request, *args, **kwargs):
        note = self.get_object()
        if note.deleted_at:
            raise serializers.ValidationError('请先恢复笔记。')
        if 'version' not in request.data:
            raise serializers.ValidationError({'version': '保存时必须提供版本号。'})
        serializer = self.get_serializer(note, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        version = data.pop('version')
        tags = data.pop('tags', None)
        changed = Note.objects.filter(pk=note.pk, user=request.user, version=version, deleted_at__isnull=True).update(
            **data, version=F('version') + 1, updated_at=timezone.now())
        if not changed:
            return Response({'detail': '笔记已在其他位置更新，请保留本地内容后重新加载。'}, status=status.HTTP_409_CONFLICT)
        note.refresh_from_db()
        if tags is not None:
            NoteSerializer.save_tags(note, tags)
        index_links(note)
        return Response(self.get_serializer(note).data)

    @transaction.atomic
    def delete(self, request, *args, **kwargs):
        note = get_object_or_404(self.get_queryset().select_for_update(), pk=kwargs['pk'])
        if request.query_params.get('permanent') == '1':
            if note.deleted_at is None:
                raise serializers.ValidationError('只能永久删除回收站中的笔记。')
            note.delete()
        else:
            Note.objects.filter(pk=note.pk, deleted_at__isnull=True).update(
                deleted_at=timezone.now(), updated_at=timezone.now(), version=F('version') + 1)
        return Response(status=status.HTTP_204_NO_CONTENT)


class RestoreNoteView(PrivateNotesView, APIView):
    def post(self, request, pk):
        note = get_object_or_404(Note, user=request.user, pk=pk)
        Note.objects.filter(pk=pk, deleted_at__isnull=False).update(
            deleted_at=None, updated_at=timezone.now(), version=F('version') + 1)
        note.refresh_from_db()
        return Response(NoteSerializer(note, context={'request': request}).data)


class NoteExportView(PrivateNotesView, APIView):
    def get(self, request, pk):
        return export_note(get_object_or_404(Note, user=request.user, pk=pk, deleted_at__isnull=True))


class NotebookExportView(PrivateNotesView, APIView):
    def get(self, request, pk):
        return export_notebook(get_object_or_404(Notebook, user=request.user, pk=pk))


class TagListView(PrivateNotesView, APIView):
    def get(self, request):
        return Response(list(Tag.objects.filter(user=request.user).values('id', 'name')))


class BindingListView(PrivateNotesView, generics.ListCreateAPIView):
    serializer_class = BindingSerializer

    def get_queryset(self):
        if not has_capability(self.request.user, 'ai.assistant'):
            raise PermissionDenied('该账号不能使用 Agent。')
        qs = AgentNoteBinding.objects.filter(user=self.request.user)
        bot_id = self.request.query_params.get('bot')
        if bot_id:
            bot_id = serializers.IntegerField(min_value=1).run_validation(bot_id)
            return qs.filter(bot=accessible_bot(self.request.user, bot_id))
        # Permission revocation takes effect for existing bindings too.
        allowed = []
        from django.http import Http404
        for bot_id in qs.values_list('bot_id', flat=True).distinct():
            try:
                accessible_bot(self.request.user, bot_id)
                allowed.append(bot_id)
            except (PermissionDenied, NotFound, Http404):
                pass
        return qs.filter(bot_id__in=allowed)


class BindingDetailView(PrivateNotesView, generics.DestroyAPIView):
    def get_queryset(self):
        return AgentNoteBinding.objects.filter(user=self.request.user)

    def perform_destroy(self, binding):
        accessible_bot(self.request.user, binding.bot_id)
        binding.delete()


class ReferenceInputSerializer(serializers.Serializer):
    bot = serializers.IntegerField(min_value=1)
    conversation_id = serializers.UUIDField()
    note_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), required=False)


class ReferencesView(PrivateNotesView, APIView):
    @transaction.atomic
    def handle(self, request, write=False):
        params = ReferenceInputSerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        bot = accessible_bot(request.user, params.validated_data['bot'])
        conversation_id = params.validated_data['conversation_id']
        if AIChatMessage.objects.filter(conversation_id=conversation_id).exclude(user=request.user, bot=bot).exists():
            raise NotFound('会话不存在。')
        note_ids = []
        if write:
            payload = ReferenceInputSerializer(data={**params.validated_data, 'note_ids': request.data.get('note_ids')})
            payload.is_valid(raise_exception=True)
            note_ids = list(dict.fromkeys(payload.validated_data['note_ids']))
            if Note.objects.filter(user=request.user, pk__in=note_ids, deleted_at__isnull=True).count() != len(note_ids):
                raise serializers.ValidationError({'note_ids': '笔记不存在、已删除或不属于你。'})
            conversation, _ = Conversation.objects.get_or_create(
                conversation_id=conversation_id, defaults={'user': request.user, 'bot': bot})
        else:
            conversation = Conversation.objects.filter(conversation_id=conversation_id).first()
            if conversation is None:
                return Response({'note_ids': []})
        if conversation.user_id != request.user.pk or conversation.bot_id != bot.pk:
            raise NotFound('会话不存在。')
        refs = ConversationNoteReference.objects.filter(user=request.user, bot=bot, conversation=conversation)
        if write:
            # Lock the same conversation for concurrent replacements of its references.
            Conversation.objects.select_for_update().get(pk=conversation.pk)
            refs.delete()
            ConversationNoteReference.objects.bulk_create([
                ConversationNoteReference(user=request.user, bot=bot, conversation=conversation, note_id=pk) for pk in note_ids])
        return Response({'note_ids': list(refs.filter(note__deleted_at__isnull=True).order_by('note_id').values_list('note_id', flat=True))})

    def get(self, request):
        return self.handle(request)

    def put(self, request):
        return self.handle(request, write=True)
