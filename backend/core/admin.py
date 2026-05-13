from django.contrib import admin
from .models import PromptTemplate, PromptQualityLog


@admin.register(PromptTemplate)
class PromptTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'version', 'agent_role', 'temperature', 'is_active', 'created_at')
    list_filter = ('agent_role', 'is_active')
    search_fields = ('name', 'content')


@admin.register(PromptQualityLog)
class PromptQualityLogAdmin(admin.ModelAdmin):
    list_display = ('task_type', 'prompt_name', 'prompt_version', 'accepted', 'quality_score', 'created_at')
    list_filter = ('task_type', 'accepted')
    readonly_fields = ('created_at',)
    date_hierarchy = 'created_at'
