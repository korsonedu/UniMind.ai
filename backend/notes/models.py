from django.conf import settings
from django.db import models
from django.db.models import Q


class Notebook(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='children')
    name = models.CharField(max_length=200)
    position = models.IntegerField(default=0)

    class Meta:
        ordering = ['position', 'id']


class Tag(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ['name', 'id']
        constraints = [models.UniqueConstraint(fields=['user', 'name'], name='notes_tag_user_name_unique')]


class Note(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    notebook = models.ForeignKey(Notebook, null=True, blank=True, on_delete=models.SET_NULL, related_name='notes')
    title = models.CharField(max_length=300, blank=True, default='')
    content = models.TextField(blank=True, default='')
    tags = models.ManyToManyField(Tag, blank=True, related_name='notes')
    is_favorite = models.BooleanField(default=False)
    version = models.PositiveIntegerField(default=1)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at', '-id']
        indexes = [models.Index(fields=['user', 'deleted_at'], name='notes_user_deleted_idx')]


class NoteLink(models.Model):
    source = models.ForeignKey(Note, on_delete=models.CASCADE, related_name='outgoing_links')
    target = models.ForeignKey(Note, on_delete=models.CASCADE, related_name='incoming_links')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['source', 'target'], name='notes_link_unique')]


class AgentNoteBinding(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    bot = models.ForeignKey('ai_assistant.Bot', on_delete=models.CASCADE)
    note = models.ForeignKey(Note, null=True, blank=True, on_delete=models.CASCADE, related_name='agent_bindings')
    notebook = models.ForeignKey(Notebook, null=True, blank=True, on_delete=models.CASCADE, related_name='agent_bindings')

    class Meta:
        ordering = ['id']
        constraints = [
            models.CheckConstraint(condition=(Q(note__isnull=False, notebook__isnull=True) | Q(note__isnull=True, notebook__isnull=False)), name='notes_binding_one_target'),
            models.UniqueConstraint(fields=['user', 'bot', 'note'], condition=Q(note__isnull=False), name='notes_binding_note_unique'),
            models.UniqueConstraint(fields=['user', 'bot', 'notebook'], condition=Q(notebook__isnull=False), name='notes_binding_book_unique'),
        ]


class ConversationNoteReference(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    bot = models.ForeignKey('ai_assistant.Bot', on_delete=models.CASCADE)
    conversation = models.ForeignKey('ai_assistant.Conversation', on_delete=models.CASCADE, related_name='note_references')
    note = models.ForeignKey(Note, on_delete=models.CASCADE, related_name='conversation_references')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'bot', 'conversation', 'note'], name='notes_conversation_reference_unique')]
