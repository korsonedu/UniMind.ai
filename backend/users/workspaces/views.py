from pathlib import Path
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Max, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.throttling import UserRateThrottle
from courses.models import Course, CourseModule, VideoTranscript
from core.file_validation import validate_upload_file
from users.models_workspace import Workspace, WorkspaceMembership, WorkspaceCourse, WorkspaceInvite, WorkspaceEnrollment
from users.models_commercial import InstitutionAuditLog
from .access import workspace_active, active_course_ids, require_admin
from .identity import account_membership_for as membership_for
from .tasks import dispatch_processing


class InviteThrottle(UserRateThrottle):
    rate = '20/min'
    scope = 'workspace_invite'


class SelectWorkspaceView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from .identity import select_learner
        from users.serializers import UserSerializer
        learner = select_learner(request.user, request.data.get('workspace_id'))
        return Response({'user': UserSerializer(learner).data})


class CodeInput(serializers.Serializer):
    code = serializers.CharField(max_length=80)


class WorkspaceInput(serializers.Serializer):
    workspace_id = serializers.IntegerField(min_value=1)


class InviteInput(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    courses = serializers.ListField(child=serializers.IntegerField(min_value=1), min_length=1, max_length=500)
    expires_at = serializers.DateField()
    service_ends_at = serializers.DateField()
    max_uses = serializers.IntegerField(min_value=1, max_value=10000)


class UploadInput(serializers.Serializer):
    module = serializers.CharField(max_length=100)
    videos = serializers.ListField(child=serializers.FileField(), min_length=1, max_length=50)


class CourseUpdate(serializers.Serializer):
    status = serializers.ChoiceField(choices=['published', 'draft'], required=False)
    retry = serializers.BooleanField(required=False)


def audit(user, workspace, action, detail=''):
    InstitutionAuditLog.objects.create(institution=workspace.institution, operator=user, action=action, detail=detail)


def processing_stalled(link):
    return link.processing_status in ('pending', 'processing') and link.updated_at < timezone.now() - timedelta(seconds=5500)


def course_row(link, include_content=True):
    course = link.course
    transcript = getattr(course, 'transcript', None)
    seconds = transcript.segments.aggregate(end=Max('end_time'))['end'] if transcript else None
    processing_status = 'failed' if processing_stalled(link) else link.processing_status
    ready = bool(transcript and transcript.asr_status == 'completed' and link.processing_status == 'completed'
                 and link.transcript_revision == transcript.revision)
    result = {'id': course.pk, 'title': course.title, 'module': course.module.name if course.module else '',
              'duration': f'{int(seconds) // 60}:{int(seconds) % 60:02d}' if seconds else '待处理',
              'filename': Path(course.video_file.name).name if course.video_file else '',
              'status': 'published' if course.is_published else 'draft' if ready else 'failed' if processing_status == 'failed' else 'processing',
              'processing_status': processing_status, 'error_message': '处理任务超时，请重试。' if processing_stalled(link) else link.error_message,
              'transcript': transcript.full_text if transcript and include_content else '',
              'knowledge': link.knowledge if ready else []}
    return result


def membership_summary(member):
    workspace = member.workspace
    today = timezone.localdate()
    ends = workspace.service_ends_on
    if member.role == 'student':
        grant_end = member.enrollments.aggregate(end=Max('service_ends_on'))['end']
        ends = min(ends, grant_end) if grant_end else ends
    active = workspace_active(member) and (member.role == 'admin' or ends >= today)
    return {'id': workspace.pk, 'name': workspace.institution.name, 'description': workspace.description,
        'role': member.role, 'is_current': member.is_current, 'joined_at': member.joined_at,
        'service_ends_at': ends, 'service_active': active}


def snapshot(user):
    member = membership_for(user)
    result = {'available': True, 'role': None, 'workspace': None, 'courses': [], 'members': [], 'invites': [], 'usage': [],
        'workspaces': [membership_summary(item) for item in WorkspaceMembership.objects.filter(user=user)
            .select_related('workspace__institution').order_by('joined_at', 'id')]}
    for item in result['workspaces']:
        item['is_current'] = bool(member and item['id'] == member.workspace_id)
    if not member:
        return result
    workspace = member.workspace
    today = timezone.localdate()
    summary = membership_summary(member)
    active = summary['service_active']
    result.update(role=member.role, workspace=summary)
    links = workspace.course_links.select_related('course__module', 'course__transcript').order_by('course__sort_order', 'id')
    if member.role != 'admin':
        links = links.filter(course_id__in=active_course_ids(member), course__is_published=True)
    elif not active:
        links = links.none()
    result['courses'] = [course_row(link, include_content=False) for link in links]
    if member.role == 'admin' and active:
        learners = {row.account_id: row.user for row in workspace.learners.select_related('user')}
        for item in workspace.memberships.filter(role='student').select_related('user').prefetch_related('enrollments__courses'):
            grants = list(item.enrollments.all())
            end = max((grant.service_ends_on for grant in grants), default=today)
            profile = learners.get(item.user_id, item.user)
            result['members'].append({'id': item.pk, 'name': profile.nickname or profile.username,
                'joined_at': item.joined_at, 'service_ends_at': min(end, workspace.service_ends_on),
                'courses': sorted({c.pk for grant in grants if grant.service_ends_on >= today for c in grant.courses.all()}),
                'active': item.is_active and item.user.is_active and end >= today})
        result['invites'] = [{'id': invite.pk, 'code': invite.code, 'name': invite.name,
            'courses': [course.pk for course in invite.courses.all()], 'expires_at': invite.expires_on,
            'service_ends_at': invite.service_ends_on, 'max_uses': invite.max_uses, 'used_count': invite.used_count,
            'active': invite.is_active and invite.expires_on >= today and invite.used_count < invite.max_uses,
            'enabled': invite.is_active,
            'state_label': '已停用' if not invite.is_active else '已过期' if invite.expires_on < today else '已领完' if invite.used_count >= invite.max_uses else '可领取'} for invite in workspace.invites.prefetch_related('courses').order_by('-id')]
        totals = workspace.course_links.aggregate(size=Sum('size_bytes'))
        from users.models_learning import AIUsageReservation
        used = AIUsageReservation.objects.filter(workspace=workspace, status='succeeded').count()
        result['usage'] = [
            {'label': '课程处理时长', 'used': round(sum((link.course.transcript.segments.aggregate(end=Max('end_time'))['end'] or 0)
                for link in links if getattr(link.course, 'transcript', None)) / 60, 1), 'limit': None, 'unit': '分钟'},
            {'label': '学生服务名额', 'used': workspace.memberships.filter(role='student').count(), 'limit': workspace.max_students, 'unit': '人'},
            {'label': '学习问答', 'used': used, 'limit': None, 'unit': '次'},
            {'label': '文件存储', 'used': round((totals['size'] or 0) / 1024 ** 3, 3), 'limit': None, 'unit': 'GB'},
        ]
    return result


def find_invite(request, lock=False):
    payload = CodeInput(data=request.data)
    payload.is_valid(raise_exception=True)
    queryset = WorkspaceInvite.objects.select_related('workspace__institution')
    if lock:
        queryset = queryset.select_for_update(of=('self',))
    invite = queryset.filter(code=payload.validated_data['code'].strip().upper()).first()
    if not invite:
        raise ValidationError('未找到对应的机构，请核对邀请码，或联系机构管理员获取有效邀请码。')
    today = timezone.localdate()
    member = WorkspaceMembership.objects.filter(user=request.user, workspace=invite.workspace).first() if invite else None
    existing = bool(invite and member and member.enrollments.filter(invite=invite).exists())
    if (not invite or not invite.workspace.is_active or not invite.workspace.institution.is_active
            or invite.workspace.service_ends_on < today or invite.service_ends_on < today
            or (not existing and (not invite.is_active or invite.expires_on < today or invite.used_count >= invite.max_uses))):
        raise ValidationError('邀请码无效、已停用、过期或已领完，请联系机构。')
    if member and not member.is_active:
        raise PermissionDenied('机构学习服务已暂停，请联系机构管理员。')
    return invite


class WorkspaceView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(snapshot(request.user))


class InvitePreviewView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [InviteThrottle]

    def post(self, request):
        invite = find_invite(request)
        return Response({'name': invite.workspace.institution.name, 'service': invite.name,
            'courses': list(invite.courses.filter(is_published=True).values_list('title', flat=True)),
            'service_ends_at': invite.service_ends_on})


class JoinView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [InviteThrottle]

    @transaction.atomic
    def post(self, request):
        get_user_model().objects.select_for_update().get(pk=request.user.pk)
        invite = find_invite(request, lock=True)
        workspace = Workspace.objects.select_for_update().get(pk=invite.workspace_id)
        member = WorkspaceMembership.objects.filter(user=request.user, workspace=workspace).first()
        if not member:
            if workspace.memberships.filter(role='student').count() >= workspace.max_students:
                raise ValidationError('机构学生名额已用完，请联系机构。')
            member = WorkspaceMembership.objects.create(user=request.user, workspace=workspace, is_current=False)
        grant, created = WorkspaceEnrollment.objects.get_or_create(membership=member, invite=invite,
            defaults={'service_ends_on': invite.service_ends_on})
        if created:
            grant.courses.set(invite.courses.all())
            invite.used_count += 1
            invite.save(update_fields=['used_count'])
            audit(request.user, workspace, 'workspace.join', str(invite.pk))
        WorkspaceMembership.objects.filter(user=request.user, is_current=True).update(is_current=False)
        WorkspaceMembership.objects.filter(pk=member.pk).update(is_current=True)
        request.user._selected_workspace_id = member.workspace_id
        return Response(snapshot(request.user))


class SwitchView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        get_user_model().objects.select_for_update().get(pk=request.user.pk)
        payload = WorkspaceInput(data=request.data)
        payload.is_valid(raise_exception=True)
        member = WorkspaceMembership.objects.filter(user=request.user, workspace_id=payload.validated_data['workspace_id']).first()
        if not member:
            raise ValidationError('你尚未加入这家机构，请先使用机构邀请码加入。')
        WorkspaceMembership.objects.filter(user=request.user, is_current=True).update(is_current=False)
        WorkspaceMembership.objects.filter(pk=member.pk).update(is_current=True)
        request.user._selected_workspace_id = member.workspace_id
        return Response(snapshot(request.user))


class LeaveView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        get_user_model().objects.select_for_update().get(pk=request.user.pk)
        payload = WorkspaceInput(data=request.data)
        payload.is_valid(raise_exception=True)
        member = WorkspaceMembership.objects.filter(user=request.user, workspace_id=payload.validated_data['workspace_id']).first()
        if not member:
            raise ValidationError('你已不在这家机构中，请刷新机构列表。')
        workspace = Workspace.objects.select_for_update().get(pk=member.workspace_id)
        if member.role == 'admin' and not workspace.memberships.filter(role='admin', is_active=True).exclude(pk=member.pk).exists():
            raise ValidationError('请先联系平台移交管理员身份，再退出机构。')
        was_current = member.is_current
        audit(request.user, workspace, 'workspace.leave')
        member.delete()
        if getattr(request.user, '_selected_workspace_id', None) == workspace.pk:
            request.user._selected_workspace_id = None
        if was_current:
            next_member = WorkspaceMembership.objects.filter(user=request.user).order_by('joined_at', 'id').first()
            if next_member:
                WorkspaceMembership.objects.filter(pk=next_member.pk).update(is_current=True)
        return Response(snapshot(request.user))


class InvitesView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        member = require_admin(request.user)
        data = InviteInput(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        today = timezone.localdate()
        if not today <= values['expires_at'] <= values['service_ends_at'] <= member.workspace.service_ends_on:
            raise ValidationError('领取截止与服务结束日期须在当前机构服务期限内。')
        ids = set(values['courses'])
        courses = Course.objects.filter(pk__in=ids, is_published=True, workspace_content__workspace=member.workspace)
        if courses.count() != len(ids):
            raise ValidationError('只能选择本机构已经发布的课程。')
        invite = WorkspaceInvite.objects.create(workspace=member.workspace, name=values['name'],
            expires_on=values['expires_at'], service_ends_on=values['service_ends_at'],
            max_uses=values['max_uses'], created_by=request.user)
        invite.courses.set(courses)
        audit(request.user, member.workspace, 'workspace.invite.create', str(invite.pk))
        return Response({'id': invite.pk}, status=201)


class InviteDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def patch(self, request, pk):
        member = require_admin(request.user)
        invite = get_object_or_404(WorkspaceInvite, pk=pk, workspace=member.workspace)
        invite.is_active = serializers.BooleanField().run_validation(request.data.get('active'))
        invite.save(update_fields=['is_active'])
        audit(request.user, member.workspace, 'workspace.invite.toggle', str(invite.pk))
        return Response({'id': invite.pk, 'active': invite.is_active})


class MemberDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def patch(self, request, pk):
        actor = require_admin(request.user)
        member = get_object_or_404(WorkspaceMembership, pk=pk, workspace=actor.workspace, role='student')
        member.is_active = serializers.BooleanField().run_validation(request.data.get('active'))
        member.save(update_fields=['is_active'])
        audit(request.user, actor.workspace, 'workspace.member.toggle', str(member.pk))
        return Response({'id': member.pk, 'active': member.is_active})


class CoursesView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        member = require_admin(request.user)
        payload = UploadInput(data={'module': request.data.get('module'), 'videos': request.FILES.getlist('videos')})
        payload.is_valid(raise_exception=True)
        files = payload.validated_data['videos']
        if sum(file.size for file in files) > 200 * 1024 ** 2:
            raise ValidationError('每批视频总大小不能超过 200 MB，请分批上传。')
        for file in files:
            validate_upload_file(file, allowed_extensions={'.mp4'})
        saved = []
        try:
            with transaction.atomic():
                workspace = Workspace.objects.select_for_update().get(pk=member.workspace_id)
                module, _ = CourseModule.objects.get_or_create(institution=workspace.institution,
                    subject='课程学习', name=payload.validated_data['module'])
                for file in files:
                    course = Course.objects.create(title=Path(file.name).stem[:200], module=module,
                        institution=workspace.institution, author=request.user, video_file=file, is_published=False)
                    saved.append(course.video_file)
                    link = WorkspaceCourse.objects.create(workspace=workspace, course=course, size_bytes=file.size)
                    VideoTranscript.objects.create(course=course)
                    transaction.on_commit(lambda pk=link.pk: dispatch_processing(pk), robust=True)
                audit(request.user, workspace, 'workspace.courses.upload', str(len(files)))
        except Exception:
            for file in saved:
                file.storage.delete(file.name)
            raise
        return Response({'created': len(files)}, status=201)


class CourseDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        member = membership_for(request.user)
        if not member:
            raise PermissionDenied('请先加入机构。')
        links = WorkspaceCourse.objects.select_related('course__module', 'course__transcript').filter(
            workspace=member.workspace, course_id__in=active_course_ids(member))
        if member.role != 'admin':
            links = links.filter(course__is_published=True)
        return Response(course_row(get_object_or_404(links, course_id=pk)))

    @transaction.atomic
    def patch(self, request, pk):
        member = require_admin(request.user)
        link = get_object_or_404(WorkspaceCourse.objects.select_for_update().select_related('course'),
                                 course_id=pk, workspace=member.workspace)
        data = CourseUpdate(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        course = link.course
        if 'status' not in values and not values.get('retry'):
            raise ValidationError('请选择发布状态或重试操作。')
        if values.get('retry'):
            if link.processing_status == 'processing' and not processing_stalled(link):
                raise ValidationError('课程正在处理中，请稍后再试。')
            course.is_published = False
            course.save(update_fields=['is_published', 'updated_at'])
            link.processing_status = 'pending'
            link.error_message = ''
            link.save(update_fields=['processing_status', 'error_message', 'updated_at'])
            transaction.on_commit(lambda: dispatch_processing(link.pk), robust=True)
        if 'status' in values:
            if values['status'] == 'published':
                from backoffice.courses import publication_error
                transcript = getattr(course, 'transcript', None)
                error = publication_error(course, transcript)
                if error or link.processing_status != 'completed' or not link.knowledge or link.transcript_revision != transcript.revision:
                    raise ValidationError(error or '请等待知识结构处理完成并检查结果后再发布。')
            course.is_published = values['status'] == 'published'
            course.save(update_fields=['is_published', 'updated_at'])
        audit(request.user, member.workspace, 'workspace.course.update', str(course.pk))
        return Response({'id': course.pk})
