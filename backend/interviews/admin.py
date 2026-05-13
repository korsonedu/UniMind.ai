from django.contrib import admin
from .models import ResumeRecord, InterviewSession, InterviewTurn

@admin.register(ResumeRecord)
class ResumeRecordAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_at', 'updated_at')
    search_fields = ('user__username',)

class InterviewTurnInline(admin.TabularInline):
    model = InterviewTurn
    extra = 0
    readonly_fields = ('turn_number', 'speaker', 'content_text', 'audio_url', 'latency_ms', 'created_at')

@admin.register(InterviewSession)
class InterviewSessionAdmin(admin.ModelAdmin):
    list_display = ('user', 'session_type', 'interviewer_style', 'status', 'started_at', 'finished_at')
    list_filter = ('session_type', 'interviewer_style', 'status')
    inlines = [InterviewTurnInline]

@admin.register(InterviewTurn)
class InterviewTurnAdmin(admin.ModelAdmin):
    list_display = ('session', 'turn_number', 'speaker', 'latency_ms', 'created_at')
    list_filter = ('speaker',)
