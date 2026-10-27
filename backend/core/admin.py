from django.contrib import admin
from .admin_base import PlatformModelAdmin
from .models import PromptTemplate, PromptQualityLog, LegalDocument

admin.site.site_header = 'UniMind 统一管理后台'
admin.site.site_title = 'UniMind 管理'
admin.site.index_title = '内容与服务配置'


@admin.register(PromptTemplate)
class PromptTemplateAdmin(PlatformModelAdmin):
    list_display = ('name', 'version', 'agent_role', 'temperature', 'is_active', 'created_at')
    list_filter = ('agent_role', 'is_active')
    search_fields = ('name', 'content')


@admin.register(PromptQualityLog)
class PromptQualityLogAdmin(PlatformModelAdmin):
    list_display = ('task_type', 'prompt_name', 'prompt_version', 'accepted', 'quality_score', 'created_at')
    list_filter = ('task_type', 'accepted')
    readonly_fields = ('created_at',)
    date_hierarchy = 'created_at'


admin.site.register(LegalDocument, PlatformModelAdmin)
