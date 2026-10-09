import re

from django import forms
from django.contrib.auth.password_validation import validate_password


def clean_account_password(value):
    if len(value) < 8 or not re.search(r'[A-Z]', value) or not re.search(r'[0-9]', value):
        raise forms.ValidationError('密码至少 8 位，包含大写字母和数字。')
    validate_password(value)
    return value


class LoginForm(forms.Form):
    identifier = forms.CharField(label='邮箱或原用户名', max_length=254, widget=forms.TextInput(attrs={'autocomplete': 'username', 'autofocus': True}))
    password = forms.CharField(label='密码', strip=False, widget=forms.PasswordInput(attrs={'autocomplete': 'current-password'}))


class CodeForm(forms.Form):
    email = forms.EmailField(label='邮箱', widget=forms.EmailInput(attrs={'autocomplete': 'email'}))
    code = forms.RegexField(r'^\d{6}$', label='邮箱验证码', widget=forms.TextInput(attrs={'autocomplete': 'one-time-code', 'inputmode': 'numeric', 'maxlength': 6}), error_messages={'invalid': '请输入 6 位数字验证码。'})
    password = forms.CharField(label='密码', strip=False, widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}))

    def clean_email(self):
        return self.cleaned_data['email'].strip().lower()

    def clean_password(self):
        return clean_account_password(self.cleaned_data['password'])


class RegisterForm(CodeForm):
    nickname = forms.CharField(label='昵称', max_length=100, required=False, widget=forms.TextInput(attrs={'autocomplete': 'nickname'}))
    agreed_to_terms = forms.BooleanField(label='我已阅读并同意用户协议与隐私政策', error_messages={'required': '请先阅读并同意用户协议与隐私政策。'})


class ResetPasswordForm(CodeForm):
    pass
