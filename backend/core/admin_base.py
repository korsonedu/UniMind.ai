from django import forms
from django.contrib import admin


class PlatformAdminMixin:
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


class PlatformModelAdmin(PlatformAdminMixin, admin.ModelAdmin):
    pass


class InstitutionContentForm(forms.ModelForm):
    class Meta:
        fields = '__all__'

    def clean(self):
        data = super().clean()
        institution = data.get('institution', getattr(self.instance, 'institution', None))
        institution_ids = {institution.pk if institution else None} if hasattr(self.instance, 'institution_id') else set()
        for name in ('module', 'album_obj', 'knowledge_point', 'parent', 'source', 'target', 'tag', 'course'):
            related = data.get(name)
            if related is not None and hasattr(related, 'institution_id'):
                institution_ids.add(related.institution_id)
        if len(institution_ids) > 1:
            raise forms.ValidationError('关联内容必须属于同一教学机构。')
        return data


class InstitutionContentAdmin(admin.ModelAdmin):
    form = InstitutionContentForm
    institution_lookup = 'institution'

    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        return tuple(fields) + ('institution',) if obj and hasattr(obj, 'institution_id') else fields

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.user.is_superuser:
            return queryset
        if not request.user.institution_id:
            return queryset.none()
        return queryset.filter(**{self.institution_lookup: request.user.institution_id})

    def has_add_permission(self, request):
        return (request.user.is_superuser or bool(request.user.institution_id)) and super().has_add_permission(request)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if not request.user.is_superuser:
            model = db_field.remote_field.model
            if db_field.name == 'institution':
                kwargs.update(queryset=model.objects.filter(pk=request.user.institution_id),
                              initial=request.user.institution_id, disabled=True)
            elif any(field.name == 'institution' for field in model._meta.fields):
                kwargs['queryset'] = model.objects.filter(institution_id=request.user.institution_id)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser and hasattr(obj, 'institution_id'):
            obj.institution_id = request.user.institution_id
        super().save_model(request, obj, form, change)
