from django import forms
from django.contrib import admin
from django.contrib.auth import get_user_model

from core.admin_base import PlatformModelAdmin
from .models import Notification


class NotificationForm(forms.ModelForm):
    broadcast = forms.BooleanField(required=False, label='向所有启用的账号发送')

    class Meta:
        model = Notification
        fields = ('recipient', 'title', 'content', 'link', 'broadcast')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['recipient'].required = False

    def clean(self):
        data = super().clean()
        if data.get('broadcast'):
            data['recipient'] = get_user_model().objects.filter(is_active=True).order_by('pk').first()
        if not data.get('recipient'):
            self.add_error('recipient', '请选择收件人，或勾选向所有启用的账号发送。')
        return data


@admin.register(Notification)
class NotificationAdmin(PlatformModelAdmin):
    form = NotificationForm
    list_display = ('title', 'recipient', 'sender', 'is_read', 'created_at')
    list_filter = ('ntype', 'is_read')
    search_fields = ('title', 'recipient__email', 'recipient__username')
    autocomplete_fields = ('recipient',)

    def get_fields(self, request, obj=None):
        return ('recipient', 'title', 'content', 'link', 'sender', 'is_read', 'created_at') if obj else ('recipient', 'title', 'content', 'link', 'broadcast')

    def get_readonly_fields(self, request, obj=None):
        return self.get_fields(request, obj) if obj else ()

    def save_model(self, request, obj, form, change):
        obj.sender = request.user
        super().save_model(request, obj, form, change)
        if not change and form.cleaned_data.get('broadcast'):
            recipients = get_user_model().objects.filter(is_active=True).exclude(pk=obj.recipient_id)
            batch = []
            for user_id in recipients.values_list('pk', flat=True).iterator(chunk_size=2000):
                batch.append(Notification(recipient_id=user_id, sender=request.user, title=obj.title,
                                          content=obj.content, link=obj.link, ntype='system'))
                if len(batch) == 2000:
                    Notification.objects.bulk_create(batch)
                    batch = []
            if batch:
                Notification.objects.bulk_create(batch)
