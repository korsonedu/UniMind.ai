import json
from datetime import date
from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from users.models import Institution
from users.models_workspace import Workspace, WorkspaceMembership, WorkspaceCourse, WorkspaceInvite, WorkspaceEnrollment, WorkspaceLearner
from users.workspaces.identity import select_learner
from courses.models import Course

LEARNING_APPS = {'notes', 'ai_assistant', 'courses', 'quizzes', 'study_room', 'faq_system'}
USER_LEARNING_MODELS = {'DailyPlan', 'DailyCheckIn', 'UserAchievement', 'LearningSession', 'UserProfile'}
PROFILE_FIELDS = ('elo_score', 'has_completed_initial_assessment', 'current_task', 'current_timer_end',
                  'today_focused_minutes', 'today_completed_tasks')


def ownership_fields():
    User = get_user_model()
    for model in apps.get_models(include_auto_created=True):
        if model._meta.app_label in LEARNING_APPS or (model._meta.app_label == 'users' and model.__name__ in USER_LEARNING_MODELS):
            for field in model._meta.fields:
                if field.name == 'user' and getattr(field, 'related_model', None) == User:
                    yield model, field.name
        if model._meta.label == 'knowledge_builder.KnowledgeTreeBuild':
            yield model, 'created_by'


class Command(BaseCommand):
    help = '将已运营机构接入 Workspace，保留课程编号并迁移指定成员的学习记录。默认只预览。'

    def add_arguments(self, parser):
        parser.add_argument('--institution', required=True, type=int)
        parser.add_argument('--owner', required=True)
        parser.add_argument('--members', required=True, nargs='+')
        parser.add_argument('--apply', action='store_true')

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()
        inst = Institution.objects.select_for_update().get(pk=options['institution'])
        names = set(options['members']) | {options['owner']}
        users = list(User.objects.select_for_update(of=('self',)).filter(username__in=names, is_active=True, institution=inst,
            workspace_learner__isnull=True).order_by('pk'))
        if {user.username for user in users} != names:
            raise CommandError('成员须为该机构下已存在且有效的登录账号。')
        courses = list(Course.objects.filter(institution=inst).select_related('transcript', 'outline'))
        if WorkspaceCourse.objects.filter(course__in=courses).exclude(workspace__institution=inst).exists():
            raise CommandError('课程已属于其他 Workspace，请先人工核对。')
        fields = list(ownership_fields())
        report = {'institution': inst.pk, 'name': inst.name, 'courses': len(courses), 'members': []}
        for user in users:
            rows = {model._meta.label: model.objects.filter(**{field: user}).count() for model, field in fields}
            report['members'].append({'id': user.pk, 'username': user.username, 'role': 'admin' if user.username == options['owner'] else 'student',
                                      'learning_rows': {label: count for label, count in rows.items() if count}})
        if not options['apply']:
            self.stdout.write(json.dumps(report, ensure_ascii=False))
            return
        end = inst.plan_expires_at.date() if inst.plan_expires_at else date.max
        workspace, _ = Workspace.objects.get_or_create(institution=inst, defaults={
            'name': inst.name, 'service_ends_on': end, 'max_students': inst.max_students})
        owner = next(user for user in users if user.username == options['owner'])
        for course in courses:
            transcript = getattr(course, 'transcript', None)
            outline = getattr(course, 'outline', None)
            knowledge = [{'name': item.title, 'children': [item.description] if item.description else []}
                         for item in outline.items.all()] if outline else []
            WorkspaceCourse.objects.get_or_create(course=course, defaults={'workspace': workspace,
                'processing_status': 'completed' if transcript and transcript.asr_status == 'completed' else 'failed',
                'error_message': '' if transcript and transcript.asr_status == 'completed' else '历史讲稿未完成，请核对原内容。',
                'transcript_revision': transcript.revision if transcript else 0, 'knowledge': knowledge})
        invite, _ = WorkspaceInvite.objects.get_or_create(code=f'MIGRATED-{inst.pk}-{workspace.pk}', defaults={
            'workspace': workspace, 'created_by': owner, 'name': '原机构学员迁移', 'expires_on': end,
            'service_ends_on': end, 'max_uses': len(users), 'is_active': False})
        invite.courses.set(courses)
        for user in users:
            existing_identity = WorkspaceLearner.objects.filter(account=user, workspace=workspace).exists()
            role = 'admin' if user == owner else 'student'
            WorkspaceMembership.objects.filter(user=user, is_current=True).update(is_current=False)
            member, _ = WorkspaceMembership.objects.update_or_create(user=user, workspace=workspace,
                defaults={'role': role, 'is_current': True})
            if role == 'student':
                user_end = min(user.membership_expires_at.date(), end) if user.membership_expires_at else end
                grant, _ = WorkspaceEnrollment.objects.get_or_create(membership=member, invite=invite,
                    defaults={'service_ends_on': user_end})
                grant.courses.set(courses)
            learner = select_learner(user, workspace.pk)
            moved = {}
            for model, field in fields:
                source = model.objects.filter(**{field: user})
                if source.exists() and model.objects.filter(**{field: learner}).exists():
                    raise CommandError(f'{user.username} 的目标空间已有 {model._meta.label} 数据，请先核对，未执行任何迁移。')
                count = source.update(**{field: learner})
                if count:
                    moved[model._meta.label] = count
            if moved or not existing_identity:
                for field in PROFILE_FIELDS:
                    setattr(learner, field, getattr(user, field))
                    setattr(user, field, User._meta.get_field(field).get_default())
                learner.save(update_fields=PROFILE_FIELDS)
                user.save(update_fields=PROFILE_FIELDS)
            if moved or not existing_identity:
                from users.models_learning import AIUsageReservation
                AIUsageReservation.objects.filter(user=user, workspace__isnull=True).update(workspace=workspace)
            next(item for item in report['members'] if item['id'] == user.pk)['moved'] = moved
        invite.used_count = invite.enrollments.count()
        invite.save(update_fields=['used_count'])
        report['workspace_id'] = workspace.pk
        report['service_ends_on'] = str(workspace.service_ends_on)
        report['max_students'] = workspace.max_students
        self.stdout.write(json.dumps(report, ensure_ascii=False))
