from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.decorators import method_decorator
from datetime import timedelta

from core.rate_limit import rate_limit

from django.contrib.auth import get_user_model
from .models import Institution, PlanInviteCode, get_plan_features, PLAN_FEATURES, compute_expiry, DEFAULT_DURATION_DAYS, DURATION_PERMANENT, MAX_DURATION_DAYS

User = get_user_model()
from .permissions import IsPlatformAdmin, IsInstitutionAdmin, IsInstitutionActive
from .serializers_institution import (
    InstitutionSerializer, CreateInstitutionSerializer, ChangePlanSerializer,
    InstitutionStudentSerializer, CreateStudentSerializer, InstitutionFeatureSerializer,
)


# ── Super Admin: Institution CRUD ──

class InstitutionListView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def get(self, request):
        qs = Institution.objects.all()
        search = request.query_params.get('search', '')
        plan_filter = request.query_params.get('plan', '')
        active_filter = request.query_params.get('is_active', '')
        if search:
            qs = qs.filter(name__icontains=search)
        if plan_filter:
            qs = qs.filter(plan=plan_filter)
        if active_filter in ('true', 'false'):
            qs = qs.filter(is_active=(active_filter == 'true'))
        serializer = InstitutionSerializer(qs, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = CreateInstitutionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        institution = serializer.save(created_by=request.user)
        return Response(InstitutionSerializer(institution).data, status=status.HTTP_201_CREATED)


class InstitutionDetailView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def get(self, request, pk):
        inst = get_object_or_404(Institution, pk=pk)
        return Response(InstitutionSerializer(inst).data)

    def put(self, request, pk):
        inst = get_object_or_404(Institution, pk=pk)
        serializer = InstitutionSerializer(inst, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, pk):
        inst = get_object_or_404(Institution, pk=pk)
        inst.delete()
        return Response({'status': 'deleted'}, status=status.HTTP_204_NO_CONTENT)


class InstitutionActivateView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def post(self, request, pk):
        inst = get_object_or_404(Institution, pk=pk)
        inst.is_active = True
        inst.save(update_fields=['is_active', 'updated_at'])
        return Response({'status': 'activated'})


class InstitutionDeactivateView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def post(self, request, pk):
        inst = get_object_or_404(Institution, pk=pk)
        inst.is_active = False
        inst.save(update_fields=['is_active', 'updated_at'])
        return Response({'status': 'deactivated'})


class InstitutionChangePlanView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def post(self, request, pk):
        inst = get_object_or_404(Institution, pk=pk)
        serializer = ChangePlanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        old_plan = inst.plan
        old_expires = inst.plan_expires_at

        inst.plan = serializer.validated_data['plan']
        if 'plan_expires_at' in serializer.validated_data:
            inst.plan_expires_at = serializer.validated_data['plan_expires_at']
        inst.save(update_fields=['plan', 'plan_expires_at', 'updated_at'])

        # 审计日志
        from users.models_commercial import InstitutionAuditLog
        InstitutionAuditLog.objects.create(
            institution=inst,
            operator=request.user,
            action='change_plan',
            detail=f'{old_plan} → {inst.plan} (expires: {old_expires} → {inst.plan_expires_at})',
        )

        return Response(InstitutionSerializer(inst).data)


class InstitutionStatsView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def get(self, request, pk):
        inst = get_object_or_404(Institution, pk=pk)
        return Response({
            'id': inst.id, 'name': inst.name, 'plan': inst.plan,
            'student_count': inst.student_count,
            'admin_count': inst.students.filter(institution_role='admin').count(),
            'is_active': inst.is_active,
            'plan_expires_at': inst.plan_expires_at,
            'created_at': inst.created_at,
        })


# ── Institution Admin: Student Management ──

class InstitutionStudentListView(APIView):
    permission_classes = [IsAuthenticated, IsInstitutionAdmin, IsInstitutionActive]

    def get(self, request):
        inst = request.user.institution
        qs = inst.students.filter(institution_role='student').order_by('-date_joined')
        serializer = InstitutionStudentSerializer(qs, many=True)
        return Response(serializer.data)

    def post(self, request):
        inst = request.user.institution

        # 批量导入
        students_data = request.data.get('students')
        if isinstance(students_data, list):
            if not students_data:
                return Response({'error': '学员列表为空'}, status=status.HTTP_400_BAD_REQUEST)
            remaining = inst.max_students - inst.student_count
            if len(students_data) > remaining:
                return Response(
                    {'error': f'当前剩余{remaining}个名额，无法导入{len(students_data)}人。请升级版本。'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            created = []
            failed = []
            for i, item in enumerate(students_data):
                try:
                    serializer = CreateStudentSerializer(data=item)
                    serializer.is_valid(raise_exception=True)
                    user = User.objects.create_user(
                        username=serializer.validated_data['username'],
                        email=serializer.validated_data.get('email', ''),
                        password=serializer.validated_data['password'],
                        nickname=serializer.validated_data.get('nickname', ''),
                        institution=inst,
                        institution_role='student',
                        is_member=True,
                        email_verified=True,
                    )
                    created.append(InstitutionStudentSerializer(user).data)
                except Exception as e:
                    failed.append({'index': i, 'username': item.get('username', ''), 'error': str(e)})

            return Response({
                'created': created,
                'created_count': len(created),
                'failed': failed,
            }, status=status.HTTP_201_CREATED if created else status.HTTP_400_BAD_REQUEST)

        # 单个创建
        if inst.student_count >= inst.max_students:
            return Response(
                {'error': f'学员数已达{inst.get_plan_display()}版上限{inst.max_students}人，请升级版本。'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = CreateStudentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.create_user(
            username=serializer.validated_data['username'],
            email=serializer.validated_data['email'],
            password=serializer.validated_data['password'],
            nickname=serializer.validated_data.get('nickname', ''),
            institution=inst,
            institution_role='student',
            is_member=True,
            email_verified=True,
        )
        return Response(InstitutionStudentSerializer(user).data, status=status.HTTP_201_CREATED)


class InstitutionStudentDetailView(APIView):
    permission_classes = [IsAuthenticated, IsInstitutionAdmin, IsInstitutionActive]

    def get(self, request, pk):
        student = get_object_or_404(
            User, pk=pk, institution=request.user.institution, institution_role='student')
        return Response(InstitutionStudentSerializer(student).data)

    def delete(self, request, pk):
        student = get_object_or_404(
            User, pk=pk, institution=request.user.institution, institution_role='student')
        student.institution = None
        student.save(update_fields=['institution'])
        return Response({'status': 'removed'}, status=status.HTTP_204_NO_CONTENT)


class InstitutionStudentStatsView(APIView):
    """机构管理员查看学员详细学习统计"""
    permission_classes = [IsAuthenticated, IsInstitutionAdmin, IsInstitutionActive]

    def get(self, request, pk):
        student = get_object_or_404(
            User, pk=pk, institution=request.user.institution, institution_role='student')
        from quizzes.models import (
            UserQuestionStatus, UserKnowledgeState, QuizExam, ReviewLog,
            KnowledgePointAnnotation,
        )
        from django.db.models import Count, Avg, Sum, Q
        from django.utils import timezone

        week_ago = timezone.now() - timezone.timedelta(days=7)

        # Question stats
        qs_all = UserQuestionStatus.objects.filter(user=student)
        total_answered = qs_all.aggregate(t=Sum('reps'))['t'] or 0
        total_wrong = qs_all.aggregate(t=Sum('wrong_count'))['t'] or 0
        total_correct = total_answered - total_wrong
        correct_rate = round(total_correct / total_answered * 100, 1) if total_answered > 0 else 0
        mastered_count = qs_all.filter(is_mastered=True).count()
        total_questions = qs_all.count()
        due_review = qs_all.filter(next_review_at__lte=timezone.now()).count()

        # Recent activity (last 7 days)
        recent_reviews = ReviewLog.objects.filter(user=student, review_time__gte=week_ago).count()
        recent_exams = QuizExam.objects.filter(user=student, created_at__gte=week_ago).count()

        # Knowledge mastery breakdown
        annotations = KnowledgePointAnnotation.objects.filter(user=student)
        mastery_breakdown = {
            'mastered': annotations.filter(mastery_level='mastered').count(),
            'stable': annotations.filter(mastery_level='stable').count(),
            'learning': annotations.filter(mastery_level='learning').count(),
            'weak': annotations.filter(mastery_level='weak').count(),
            'unknown': annotations.filter(mastery_level='unknown').count(),
        }

        # Recent exam scores (last 5)
        recent_scores = list(QuizExam.objects.filter(user=student).order_by('-created_at')[:5].values(
            'total_score', 'max_score', 'created_at'))

        # Review logs trend (last 7 days, daily counts)
        from django.db.models.functions import TruncDate
        daily_reviews = list(
            ReviewLog.objects.filter(user=student, review_time__gte=week_ago)
            .annotate(day=TruncDate('review_time')).values('day')
            .annotate(count=Count('id')).order_by('day')
        )

        return Response({
            'student': {
                'id': student.id, 'username': student.username,
                'nickname': student.nickname, 'email': student.email,
                'elo_score': student.elo_score, 'last_active': student.last_active,
            },
            'questions': {
                'total_answered': total_answered, 'total_correct': total_correct,
                'total_wrong': total_wrong, 'correct_rate': correct_rate,
                'mastered': mastered_count, 'total': total_questions,
                'due_review': due_review,
            },
            'activity': {
                'reviews_this_week': recent_reviews,
                'exams_this_week': recent_exams,
            },
            'mastery': mastery_breakdown,
            'recent_scores': recent_scores,
            'daily_reviews': daily_reviews,
        })


class InstitutionStudentResetPasswordView(APIView):
    """机构管理员重置学员密码"""
    permission_classes = [IsAuthenticated, IsInstitutionAdmin, IsInstitutionActive]

    def post(self, request, pk):
        student = get_object_or_404(
            User, pk=pk, institution=request.user.institution, institution_role='student')
        password = request.data.get('password', '')
        if len(password) < 6:
            return Response({'error': '密码至少 6 位'}, status=status.HTTP_400_BAD_REQUEST)
        student.set_password(password)
        student.save(update_fields=['password'])
        return Response({'status': 'ok'})


# ── Feature Info ──

class InstitutionFeatureView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        inst = user.institution

        inst_data = None
        if inst:
            inst_data = {
                'id': inst.id, 'name': inst.name,
                'plan': inst.plan, 'plan_label': inst.get_plan_display(),
                'plan_expires_at': inst.plan_expires_at,
                'is_active': inst.is_active,
                'is_plan_active': inst.is_plan_active,
                'max_students': inst.max_students,
                'student_count': inst.student_count,
            }

        # Platform admins without an institution see all features.
        # Platform admins WITH an institution see that institution's plan features.
        if user.is_platform_admin and inst is None:
            features = get_plan_features('pro')
        elif inst:
            features = get_plan_features(inst.plan)
        else:
            features = []

        from users.quota import get_ai_quota_info
        usage = get_ai_quota_info(inst)

        return Response(InstitutionFeatureSerializer({
            'is_platform_admin': user.is_platform_admin,
            'institution': inst_data,
            'features': features,
            'usage': usage,
        }).data)


# ── Institution Dashboard ──

class InstitutionDashboardView(APIView):
    """机构管理员仪表盘 / 平台超管机构总览"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        inst = user.institution

        # Platform admin without institution → list all institutions for overview
        if user.is_platform_admin and inst is None:
            qs = Institution.objects.all()
            return Response({
                'mode': 'platform_admin',
                'institutions': [
                    {
                        'id': i.id, 'name': i.name, 'plan': i.plan,
                        'plan_label': i.get_plan_display(),
                        'plan_expires_at': i.plan_expires_at,
                        'is_active': i.is_active,
                        'is_plan_active': i.is_plan_active,
                        'max_students': i.max_students,
                        'student_count': i.student_count,
                        'admin_count': i.students.filter(institution_role='admin').count(),
                    }
                    for i in qs
                ],
                'plan_matrix': {p: get_plan_features(p) for p in ['free', 'solo', 'plus', 'pro']},
            })

        # Institution admin or platform admin with institution → their dashboard
        if inst and (user.institution_role == 'admin' or user.is_platform_admin):
            # 7-day active student count
            from django.utils import timezone
            from datetime import timedelta
            from django.db.models import Count, Q
            week_ago = timezone.now() - timedelta(days=7)
            student_ids = inst.students.filter(institution_role='student').values_list('id', flat=True)
            weekly_active = 0
            if student_ids:
                from quizzes.models import ReviewLog
                weekly_active = ReviewLog.objects.filter(
                    user_id__in=student_ids, review_time__gte=week_ago
                ).values('user_id').distinct().count()

            # AI 用量
            from users.quota import get_ai_quota_info
            ai_usage = get_ai_quota_info(inst)

            # 薄弱知识点排行 (取掌握度最低的前 5 个)
            top_weak = []
            if student_ids:
                from quizzes.models import KnowledgePointAnnotation
                weak_annotations = (
                    KnowledgePointAnnotation.objects
                    .filter(user_id__in=student_ids, mastery_level='weak')
                    .values('knowledge_point__label')
                    .annotate(count=Count('id'))
                    .order_by('-count')[:5]
                )
                top_weak = [
                    {'label': a['knowledge_point__label'], 'weak_count': a['count']}
                    for a in weak_annotations
                ]

            return Response({
                'mode': 'institution_admin',
                'institution': {
                    'id': inst.id, 'name': inst.name, 'plan': inst.plan,
                    'plan_label': inst.get_plan_display(),
                    'plan_expires_at': inst.plan_expires_at,
                    'is_active': inst.is_active,
                    'is_plan_active': inst.is_plan_active,
                    'max_students': inst.max_students,
                    'student_count': inst.student_count,
                    'admin_count': inst.students.filter(institution_role='admin').count(),
                },
                'stats': {
                    'weekly_active_students': weekly_active,
                    'ai_usage': ai_usage,
                    'top_weak_points': top_weak,
                },
                'features': get_plan_features(inst.plan),
                'plan_matrix': {p: get_plan_features(p) for p in ['free', 'solo', 'plus', 'pro']},
            })

        return Response({'error': '无机构管理权限'}, status=403)


# ── Preview as Institution (平台超管专用) ──

class InstitutionPreviewView(APIView):
    """平台管理员以任意机构身份预览功能集"""
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def get(self, request, pk):
        inst = get_object_or_404(Institution, pk=pk)
        return Response({
            'preview': True,
            'is_platform_admin': False,  # preview mode → behave as institution member
            'institution': {
                'id': inst.id, 'name': inst.name,
                'plan': inst.plan, 'plan_label': inst.get_plan_display(),
                'plan_expires_at': inst.plan_expires_at,
                'is_active': inst.is_active,
                'is_plan_active': inst.is_plan_active,
                'max_students': inst.max_students,
                'student_count': inst.student_count,
            },
            'features': get_plan_features(inst.plan),
        })


# ── Public Join Link ──

from django.shortcuts import redirect
from django.conf import settings
from rest_framework.permissions import AllowAny


class JoinInstitutionView(APIView):
    """邀请链接：/join/{slug} → 重定向到前端注册页预填邀请码"""
    permission_classes = [AllowAny]

    def get(self, request, slug):
        institution = get_object_or_404(Institution, slug=slug, is_active=True)
        frontend_url = getattr(settings, 'FRONTEND_URL', '')
        return redirect(f'{frontend_url}/register?invite={slug}&name={institution.name}')


# ── Institution Self-Update (机构管理员编辑自己的机构信息) ──

class InstitutionSelfUpdateView(APIView):
    """机构管理员可编辑机构名称、联系人等信息。学生无权访问。"""
    permission_classes = [IsAuthenticated, IsInstitutionAdmin, IsInstitutionActive]

    def get(self, request):
        inst = request.user.institution
        return Response({
            'id': inst.id,
            'name': inst.name,
            'slug': inst.slug,
            'contact_name': inst.contact_name,
            'contact_email': inst.contact_email,
            'contact_phone': inst.contact_phone,
            'plan': inst.plan,
            'plan_label': inst.get_plan_display(),
            'plan_expires_at': inst.plan_expires_at,
            'is_plan_active': inst.is_plan_active,
            'max_students': inst.max_students,
            'student_count': inst.student_count,
        })

    def put(self, request):
        inst = request.user.institution
        allowed = ['name', 'contact_name', 'contact_email', 'contact_phone']
        for field in allowed:
            if field in request.data:
                setattr(inst, field, request.data[field])
        inst.save(update_fields=[f for f in allowed if f in request.data] + ['updated_at'])
        return Response({'status': 'ok', 'name': inst.name, 'contact_name': inst.contact_name})


# ── Student Join via Invite Code ──

class InstitutionJoinView(APIView):
    """学生通过邀请码加入机构"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        code = (request.data.get('invite_code') or '').strip().upper()
        if not code:
            return Response({'error': '请输入邀请码'}, status=400)
        try:
            inst = Institution.objects.get(invite_code=code)
        except Institution.DoesNotExist:
            return Response({'error': '邀请码无效'}, status=404)
        if not inst.is_active:
            return Response({'error': '该机构已被停用'}, status=403)
        if not inst.is_plan_active:
            return Response({'error': '该机构已到期，请联系机构管理员'}, status=403)
        if inst.student_count >= inst.max_students:
            return Response({'error': f'该机构学员数已达上限 {inst.max_students} 人'}, status=403)

        user = request.user
        if user.institution and user.institution != inst:
            return Response({'error': '你已加入其他机构，请先退出'}, status=409)

        user.institution = inst
        user.institution_role = 'student'
        user.is_member = True
        user.save(update_fields=['institution', 'institution_role', 'is_member'])
        return Response({
            'status': 'ok',
            'institution': {'id': inst.id, 'name': inst.name, 'plan_label': inst.get_plan_display()},
        })


# ── Lookup Institution by Invite Code ──

class InstitutionInviteLookupView(APIView):
    """公开：通过邀请码查询机构名称（注册时前端校验）"""
    permission_classes = [AllowAny]

    @method_decorator(rate_limit(key_prefix="invite_lookup", max_requests=10, window_seconds=300))
    def get(self, request):
        code = (request.query_params.get('code') or '').strip().upper()
        if not code:
            return Response({'error': '请输入邀请码'}, status=400)
        try:
            inst = Institution.objects.get(invite_code=code, is_active=True)
        except Institution.DoesNotExist:
            return Response({'error': '邀请码无效'}, status=404)
        return Response({'id': inst.id, 'name': inst.name, 'plan_label': inst.get_plan_display()})


# ── Teacher: Create Own Institution ──

class InstitutionCreateView(APIView):
    """注册后用户通过方案邀请码自建机构，成功后自动成为机构管理员"""
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        user = request.user
        if user.institution is not None:
            return Response({'error': '你已有所属机构，不能重复创建'}, status=409)

        invite_code = (request.data.get('invite_code') or '').strip().upper()
        if not invite_code:
            return Response({'error': '需要方案邀请码才能创建机构，请联系 UniMind 获取'}, status=400)

        valid, result = PlanInviteCode.validate_and_use(invite_code)
        if not valid:
            return Response({'error': result}, status=400)
        plan, duration_days = result

        name = (request.data.get('name') or '').strip()
        if not name:
            return Response({'error': '机构名称不能为空'}, status=400)

        slug_base = name.lower().replace(' ', '-')
        slug = slug_base
        counter = 1
        while Institution.objects.filter(slug=slug).exists():
            slug = f'{slug_base}-{counter}'
            counter += 1

        contact_name = (request.data.get('contact_name') or user.nickname or user.username).strip()
        contact_email = (request.data.get('contact_email') or user.email or '').strip()
        contact_phone = (request.data.get('contact_phone') or '').strip()
        description = (request.data.get('description') or '').strip()

        inst = Institution.objects.create(
            name=name, slug=slug,
            contact_name=contact_name,
            contact_email=contact_email,
            contact_phone=contact_phone,
            notes=description,
            plan=plan,
            plan_expires_at=compute_expiry(duration_days),
            created_by=user,
            is_active=True,
        )

        user.institution = inst
        user.institution_role = 'admin'
        user.is_member = True
        user.save(update_fields=['institution', 'institution_role', 'is_member'])

        return Response({
            'status': 'ok',
            'institution': {
                'id': inst.id, 'name': inst.name, 'slug': inst.slug,
                'plan': inst.plan, 'plan_label': inst.get_plan_display(),
                'invite_code': inst.invite_code,
            },
        }, status=status.HTTP_201_CREATED)


# ── Plan Invite Code Management (平台超管) ──

class PlanInviteCodeListView(APIView):
    """超管：查看所有方案邀请码"""
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def get(self, request):
        qs = PlanInviteCode.objects.select_related('created_by').all()
        plan_filter = request.query_params.get('plan', '')
        if plan_filter:
            qs = qs.filter(plan=plan_filter)
        return Response([{
            'id': c.id, 'code': c.code, 'plan': c.plan,
            'plan_label': c.get_plan_display(),
            'duration_days': c.duration_days,
            'max_uses': c.max_uses, 'used_count': c.used_count,
            'is_active': c.is_active, 'is_exhausted': c.is_exhausted,
            'note': c.note, 'created_at': c.created_at,
            'created_by': c.created_by.nickname if c.created_by else '',
        } for c in qs])


class PlanInviteCodeGenerateView(APIView):
    """超管：按方案批量生成邀请码"""
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def post(self, request):
        plan = (request.data.get('plan') or '').strip()
        if plan not in dict(Institution.PLAN_CHOICES):
            return Response({'error': '无效的方案类型'}, status=400)

        count = max(1, min(int(request.data.get('count', 1)), 100))
        max_uses = max(1, min(int(request.data.get('max_uses', 1)), 1000))
        duration_days = max(DURATION_PERMANENT, min(int(request.data.get('duration_days', DEFAULT_DURATION_DAYS)), MAX_DURATION_DAYS))
        note = (request.data.get('note') or '').strip()

        codes = PlanInviteCode.generate(plan=plan, created_by=request.user, count=count, max_uses=max_uses, duration_days=duration_days, note=note)
        return Response({
            'generated': len(codes),
            'plan': plan,
            'plan_label': dict(Institution.PLAN_CHOICES).get(plan, plan),
            'duration_days': duration_days,
            'codes': codes,
        }, status=status.HTTP_201_CREATED)


class PlanInviteCodeDeactivateView(APIView):
    """超管：停用邀请码"""
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def post(self, request, pk):
        code = get_object_or_404(PlanInviteCode, pk=pk)
        code.is_active = False
        code.save(update_fields=['is_active'])
        return Response({'status': 'deactivated'})
