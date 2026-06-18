from django.contrib import admin
from .models import InstitutionInvite, JoinRequest

@admin.register(InstitutionInvite)
class InstitutionInviteAdmin(admin.ModelAdmin):
    list_display = ('slug', 'institution', 'assigned_role', 'used_count', 'requires_approval', 'is_active', 'created_at')
    list_filter = ('assigned_role', 'requires_approval', 'is_active')
    search_fields = ('slug', 'institution__name')

@admin.register(JoinRequest)
class JoinRequestAdmin(admin.ModelAdmin):
    list_display = ('user', 'institution', 'status', 'created_at', 'reviewed_at')
    list_filter = ('status',)
    search_fields = ('user__username', 'institution__name')
