from django.contrib import admin
from .models import ChatMessage

@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('user', 'content', 'related_plan', 'timestamp')
    list_filter = ('timestamp',)
    search_fields = ('content', 'user__username')

