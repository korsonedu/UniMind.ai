import secrets
from django.conf import settings
from django.db import models


def workspace_invite_code():
    return secrets.token_hex(8).upper()


class Workspace(models.Model):
    institution = models.OneToOneField('users.Institution', on_delete=models.PROTECT, related_name='learning_workspace')
    description = models.CharField(max_length=200, blank=True)
    service_ends_on = models.DateField()
    max_students = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.institution.name


class WorkspaceMembership(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='workspace_membership')
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT, related_name='memberships')
    role = models.CharField(max_length=10, choices=[('admin', '管理员'), ('student', '学生')], default='student')
    is_active = models.BooleanField(default=True)
    joined_at = models.DateTimeField(auto_now_add=True)


class WorkspaceLearner(models.Model):
    """An account's independent learning identity inside one workspace.

    Existing learning tables reference User. A separate, non-login identity keeps
    their ownership checks, background jobs and caches scoped without copying data.
    Authentication and billing continue to belong to account.
    """
    account = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='workspace_learners')
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT, related_name='learners')
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='workspace_learner')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['account', 'workspace'], name='workspace_learner_account_space')]


class WorkspaceCourse(models.Model):
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT, related_name='course_links')
    course = models.OneToOneField('courses.Course', on_delete=models.CASCADE, related_name='workspace_content')
    size_bytes = models.PositiveBigIntegerField(default=0)
    processing_status = models.CharField(max_length=12, default='pending', choices=[
        ('pending', '待处理'), ('processing', '处理中'), ('completed', '已完成'), ('failed', '失败'),
    ])
    knowledge = models.JSONField(default=list, blank=True)
    transcript_revision = models.PositiveIntegerField(default=0)
    error_message = models.CharField(max_length=200, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class WorkspaceInvite(models.Model):
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT, related_name='invites')
    code = models.CharField(max_length=32, unique=True, default=workspace_invite_code)
    name = models.CharField(max_length=100)
    courses = models.ManyToManyField('courses.Course', related_name='workspace_invites')
    expires_on = models.DateField()
    service_ends_on = models.DateField()
    max_uses = models.PositiveIntegerField()
    used_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')


class WorkspaceEnrollment(models.Model):
    membership = models.ForeignKey(WorkspaceMembership, on_delete=models.CASCADE, related_name='enrollments')
    invite = models.ForeignKey(WorkspaceInvite, on_delete=models.PROTECT, related_name='enrollments')
    courses = models.ManyToManyField('courses.Course', related_name='workspace_enrollments')
    service_ends_on = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['membership', 'invite'], name='workspace_enrollment_once')]
