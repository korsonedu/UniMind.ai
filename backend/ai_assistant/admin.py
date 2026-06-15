from django.contrib import admin
from django.db.models import Count, Avg

from .models import Experience, ExperienceVerification


class ExperienceDimensionFilter(admin.SimpleListFilter):
    title = '维度'
    parameter_name = 'dimension'

    def lookups(self, request, model_admin):
        return Experience.DIMENSION_CHOICES

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(dimension=self.value())
        return queryset


class ExperienceConfidenceFilter(admin.SimpleListFilter):
    title = '置信度'
    parameter_name = 'confidence'

    def lookups(self, request, model_admin):
        return Experience.CONFIDENCE_CHOICES

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(confidence=self.value())
        return queryset


class ExperienceGapTypeFilter(admin.SimpleListFilter):
    title = '工具类型'
    parameter_name = 'gap_type'

    def lookups(self, request, model_admin):
        return [
            ('parameter', '参数级'),
            ('capability', '能力缺口'),
        ]

    def queryset(self, request, queryset):
        val = self.value()
        if val == 'parameter':
            return queryset.filter(dimension='tool').exclude(effect__has_key='gap_type')
        if val == 'capability':
            return queryset.filter(dimension='tool', effect__gap_type='capability')
        return queryset


@admin.register(Experience)
class ExperienceAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'dimension_display',
        'gap_indicator',
        'scope_type',
        'confidence_display',
        'status',
        'weight',
        'verify_count',
        'last_triggered_at',
        'created_at',
    )
    list_filter = (
        ExperienceDimensionFilter,
        ExperienceConfidenceFilter,
        ExperienceGapTypeFilter,
        'scope_type',
        'status',
    )
    search_fields = ('title', 'effect__instruction')
    readonly_fields = ('verify_count', 'verify_fail_count', 'last_triggered_at', 'created_at', 'updated_at')
    ordering = ('-weight', '-created_at')
    list_per_page = 50

    fieldsets = (
        ('路由信息', {
            'fields': ('dimension', 'scope_type', 'scope_value'),
        }),
        ('内容', {
            'fields': ('title', 'trigger', 'effect'),
        }),
        ('来源', {
            'fields': ('user', 'trajectory'),
        }),
        ('生命周期', {
            'fields': ('confidence', 'weight', 'status', 'verify_count', 'verify_fail_count'),
        }),
        ('时间', {
            'fields': ('last_triggered_at', 'created_at', 'updated_at'),
        }),
    )

    def dimension_display(self, obj):
        return obj.get_dimension_display()
    dimension_display.short_description = '维度'
    dimension_display.admin_order_field = 'dimension'

    def confidence_display(self, obj):
        return obj.get_confidence_display()
    confidence_display.short_description = '置信度'
    confidence_display.admin_order_field = 'confidence'

    def gap_indicator(self, obj):
        if obj.dimension == 'tool' and (obj.effect or {}).get('gap_type') == 'capability':
            return '⚠️ 能力缺口'
        return ''
    gap_indicator.short_description = ''

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(ExperienceVerification)
class ExperienceVerificationAdmin(admin.ModelAdmin):
    list_display = (
        'experience_link',
        'user',
        'kp_id',
        'score',
        'max_score',
        'score_ratio_display',
        'created_at',
    )
    list_filter = ('experience__dimension', 'experience__confidence')
    search_fields = ('experience__title', 'user__email')
    readonly_fields = (
        'experience', 'user', 'kp_id', 'score', 'max_score',
        'score_ratio', 'created_at',
    )
    ordering = ('-created_at',)
    list_per_page = 100

    def experience_link(self, obj):
        from django.urls import reverse
        from django.utils.html import format_html
        url = reverse('admin:ai_assistant_experience_change', args=[obj.experience_id])
        return format_html('<a href="{}">{}</a>', url, obj.experience.title)
    experience_link.short_description = '经验'
    experience_link.admin_order_field = 'experience__title'

    def score_ratio_display(self, obj):
        return f'{obj.score_ratio:.0%}'
    score_ratio_display.short_description = '得分率'

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return False  # 只读

    def has_change_permission(self, request, obj=None):
        return False  # 只读

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
