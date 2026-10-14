from django.contrib import admin
from django import forms
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from core.admin_base import PlatformAdminMixin, PlatformModelAdmin, InstitutionContentAdmin
from .models import (User, Institution, InstitutionInvite, JoinRequest, SystemConfig,
                     PermissionGroup, UserTag, UserAccessProfile, PlanInviteCode,
                     LearningProduct, LearningGrant, LearningUsage)


@admin.register(User)
class UserAdmin(PlatformAdminMixin, DjangoUserAdmin):
    list_display = ('username', 'email', 'nickname', 'institution', 'institution_role', 'is_staff', 'is_active')
    list_filter = ('is_staff', 'is_active', 'institution', 'institution_role')
    fieldsets = DjangoUserAdmin.fieldsets + (
        ('学习账户', {'fields': ('nickname', 'email_verified', 'role', 'institution', 'institution_role', 'elo_score')}),
        ('历史权益', {'fields': ('is_member', 'personal_plan', 'membership_tier', 'membership_expires_at', 'membership_source')}),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        ('账户资料', {'fields': ('email', 'nickname', 'email_verified', 'institution', 'institution_role')}),
    )


@admin.register(Institution)
class InstitutionAdmin(PlatformAdminMixin, admin.ModelAdmin):
    list_display = ('name', 'slug', 'is_active')
    search_fields = ('name', 'slug')
    fields = ('name', 'slug', 'is_active', 'contact_name', 'contact_email', 'contact_phone', 'notes')


class LearningProductForm(forms.ModelForm):
    class Meta:
        model = LearningProduct
        fields = '__all__'

    def clean(self):
        data = super().clean()
        if data.get('duration_days', 0) < 1:
            self.add_error('duration_days', '有效期至少为一天。')
        if data.get('is_active') and data.get('price_cents', 0) < 1:
            self.add_error('price_cents', '上架前请设置销售价格，单位为分。')
        return data


@admin.register(LearningProduct)
class LearningProductAdmin(PlatformAdminMixin, admin.ModelAdmin):
    form = LearningProductForm
    list_display = ('name', 'price_cents', 'duration_days', 'monthly_ai_calls', 'is_active', 'sort_order')
    list_filter = ('is_active',)
    search_fields = ('name',)
    filter_horizontal = ('modules',)


class LearningGrantForm(forms.ModelForm):
    class Meta:
        model = LearningGrant
        fields = '__all__'

    def clean(self):
        data = super().clean()
        if not self.instance.pk:
            user = data.get('user')
            if user and (not user.email_verified or not user.is_active):
                self.add_error('user', '请使用已验证且启用的学习账号。')
            if data.get('source') == 'payment':
                self.add_error('source', '支付权益由订单自动生成，请选择课程配套或管理员赠送。')
        return data


@admin.register(LearningGrant)
class LearningGrantAdmin(PlatformAdminMixin, admin.ModelAdmin):
    form = LearningGrantForm
    list_display = ('user', 'product', 'source', 'starts_at', 'expires_at', 'revoked')
    list_filter = ('source', 'revoked', 'product')
    search_fields = ('user__email', 'user__username', 'snapshot__name')
    autocomplete_fields = ('user', 'product')
    actions = ('revoke_grants',)

    def get_readonly_fields(self, request, obj=None):
        fields = ('snapshot', 'order', 'starts_at', 'expires_at')
        return fields + ('user', 'product', 'source') if obj else fields + ('revoked',)

    def save_model(self, request, obj, form, change):
        if change:
            return super().save_model(request, obj, form, change)
        from .learning import grant_product
        grant = grant_product(obj.user, obj.product, source=obj.source)
        obj.pk = grant.pk
        obj.snapshot, obj.starts_at, obj.expires_at = grant.snapshot, grant.starts_at, grant.expires_at
        obj._state = grant._state

    @admin.action(description='撤销选中的学习权益')
    def revoke_grants(self, request, queryset):
        self.message_user(request, f'已撤销 {queryset.update(revoked=True)} 条学习权益。')

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(LearningUsage)
class LearningUsageAdmin(PlatformAdminMixin, admin.ModelAdmin):
    list_display = ('user', 'month', 'ai_calls')
    search_fields = ('user__email', 'user__username')
    readonly_fields = ('user', 'month', 'ai_calls')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PlanInviteCode)
class PlanInviteCodeAdmin(PlatformAdminMixin, admin.ModelAdmin):
    list_display = ('code', 'plan', 'duration_days', 'used_count', 'max_uses', 'is_active')
    search_fields = ('code',)
    readonly_fields = ('used_count', 'created_at')


admin.site.register([SystemConfig, PermissionGroup, UserTag, UserAccessProfile], PlatformModelAdmin)

@admin.register(InstitutionInvite)
class InstitutionInviteAdmin(InstitutionContentAdmin):
    list_display = ('slug', 'institution', 'assigned_role', 'used_count', 'requires_approval', 'is_active', 'created_at')
    list_filter = ('assigned_role', 'requires_approval', 'is_active')
    search_fields = ('slug', 'institution__name')

@admin.register(JoinRequest)
class JoinRequestAdmin(InstitutionContentAdmin):
    list_display = ('user', 'institution', 'status', 'created_at', 'reviewed_at')
    list_filter = ('status',)
    search_fields = ('user__username', 'institution__name')
