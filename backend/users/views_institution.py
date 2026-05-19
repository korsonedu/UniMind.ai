import logging
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.utils import timezone
from datetime import timedelta



logger = logging.getLogger(__name__)

from django.contrib.auth import get_user_model
from .models import Institution, PlanInviteCode, get_plan_features, PLAN_FEATURES, compute_expiry, DEFAULT_DURATION_DAYS, DURATION_PERMANENT, MAX_DURATION_DAYS

User = get_user_model()
from .permissions import IsPlatformAdmin, IsInstitutionAdmin, IsInstitutionOwner, IsInstitutionActive, IsInstitutionMember
from .serializers_institution import (
    InstitutionSerializer, CreateInstitutionSerializer, ChangePlanSerializer,
    InstitutionStudentSerializer, CreateStudentSerializer, InstitutionFeatureSerializer,
)

DIRECTION_LIMITS = {'solo': 1, 'plus': 3, 'pro': 999999}


def _clone_knowledge_tree(subject_name, institution):
    """Clone all global KnowledgePoints for a subject into an institution scope."""
    from quizzes.models import KnowledgePoint

    global_kps = list(
        KnowledgePoint.objects.filter(
            subject=subject_name,
            institution__isnull=True,
        ).order_by('level', 'order')
    )
    if not global_kps:
        return 0

    old_to_new = {}
    for kp in global_kps:
        new_kp = KnowledgePoint(
            code=kp.code,
            name=kp.name,
            level=kp.level,
            prefix_category=kp.prefix_category,
            description=kp.description,
            parent=None,
            institution=institution,
            order=kp.order,
            subject=kp.subject,
        )
        new_kp.save()
        old_to_new[kp.id] = new_kp

    # Remap parent FK relationships
    for kp in global_kps:
        if kp.parent_id and kp.parent_id in old_to_new:
            new_kp = old_to_new[kp.id]
            new_kp.parent_id = old_to_new[kp.parent_id].id
            new_kp.save(update_fields=['parent'])

    return len(old_to_new)


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
            'staff_count': inst.students.filter(institution_role__in=('owner', 'teacher')).count(),
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
                except (ValueError, TypeError) as e:
                    failed.append({'index': i, 'username': item.get('username', ''), 'error': str(e)})
                except Exception:
                    logger.exception("批量创建学员失败: index=%s username=%s", i, item.get('username', ''))
                    failed.append({'index': i, 'username': item.get('username', ''), 'error': '系统错误，请重试'})

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
            UserQuestionStatus, QuizExam, ReviewLog,
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

        # Knowledge mastery breakdown (Memorix Weibull retrievability)
        from quizzes.memorix.service import predict_retrievability as weibull_r
        now = timezone.now()
        statuses = UserQuestionStatus.objects.filter(
            user=student, stability__gt=0, last_review__isnull=False,
        ).select_related('question__knowledge_point')
        kp_retrievability: dict[int, list[float]] = {}
        for s in statuses:
            kp = s.question.knowledge_point
            if kp is None:
                continue
            elapsed = max(0.0, (now - s.last_review).total_seconds() / 86400.0)
            r = weibull_r(stability=s.stability, elapsed_days=elapsed)
            kp_retrievability.setdefault(kp.id, []).append(r)
        mastery_breakdown = {
            'mastered': 0, 'stable': 0, 'learning': 0, 'weak': 0, 'unknown': 0,
        }
        for scores in kp_retrievability.values():
            avg_r = sum(scores) / len(scores)
            if avg_r >= 0.8:
                mastery_breakdown['mastered'] += 1
            elif avg_r >= 0.6:
                mastery_breakdown['stable'] += 1
            elif avg_r >= 0.4:
                mastery_breakdown['learning'] += 1
            elif avg_r > 0:
                mastery_breakdown['weak'] += 1
            else:
                mastery_breakdown['unknown'] += 1

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


class InstitutionStudentRankingView(APIView):
    """机构内 ELO 排行榜"""
    permission_classes = [IsAuthenticated, IsInstitutionMember, IsInstitutionActive]

    def get(self, request):
        inst = request.user.institution
        qs = inst.students.order_by('-elo_score')[:50]
        serializer = InstitutionStudentSerializer(qs, many=True)
        return Response(serializer.data)


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
                'id': inst.id, 'name': inst.name, 'slug': inst.slug,
                'plan': inst.plan, 'plan_label': inst.get_plan_display(),
                'plan_expires_at': inst.plan_expires_at,
                'is_active': inst.is_active,
                'is_plan_active': inst.is_plan_active,
                'max_students': inst.max_students,
                'student_count': inst.student_count,
                'invite_slug': inst.invite_slug,
                'business_type': inst.business_type,
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
                        'staff_count': i.students.filter(institution_role__in=('owner', 'teacher')).count(),
                    }
                    for i in qs
                ],
                'plan_matrix': {p: get_plan_features(p) for p in ['free', 'solo', 'plus', 'pro']},
            })

        # Institution admin or platform admin with institution → their dashboard
        if inst and (user.institution_role in ('owner', 'teacher') or user.is_platform_admin):
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

            # 薄弱知识点排行 (Memorix Weibull retrievability, R < 0.4 即为薄弱)
            top_weak = []
            if student_ids:
                from quizzes.models import UserQuestionStatus
                from quizzes.memorix.service import predict_retrievability as weibull_r
                now = timezone.now()
                statuses = UserQuestionStatus.objects.filter(
                    user_id__in=student_ids, stability__gt=0, last_review__isnull=False,
                ).select_related('question__knowledge_point')
                user_kp_scores: dict[tuple[int, int], list[float]] = {}
                kp_name_map: dict[int, str] = {}
                for s in statuses:
                    kp = s.question.knowledge_point
                    if kp is None:
                        continue
                    kp_name_map[kp.id] = kp.name
                    elapsed = max(0.0, (now - s.last_review).total_seconds() / 86400.0)
                    r = weibull_r(stability=s.stability, elapsed_days=elapsed)
                    user_kp_scores.setdefault((s.user_id, kp.id), []).append(r)
                # Count weak users per KP
                weak_counts: dict[int, int] = {}
                for (uid, kp_id), scores in user_kp_scores.items():
                    avg_r = sum(scores) / len(scores)
                    if avg_r < 0.4:
                        weak_counts[kp_id] = weak_counts.get(kp_id, 0) + 1
                top_weak = sorted(
                    [{'label': kp_name_map.get(kp_id, '?'), 'weak_count': c}
                     for kp_id, c in weak_counts.items()],
                    key=lambda x: x['weak_count'], reverse=True,
                )[:5]

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
                    'staff_count': inst.students.filter(institution_role__in=('owner', 'teacher')).count(),
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
                'id': inst.id, 'name': inst.name, 'slug': inst.slug,
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
    """邀请链接：/join/{invite_slug} → 种 cookie → 重定向到 /register"""
    permission_classes = [AllowAny]

    def get(self, request, invite_slug):
        institution = get_object_or_404(Institution, invite_slug=invite_slug, is_active=True)
        frontend_url = getattr(settings, 'FRONTEND_URL', '')
        response = redirect(f'{frontend_url}/register')
        response.set_cookie(
            'institution_invite', invite_slug,
            max_age=7 * 24 * 3600,
            httponly=False,
            samesite='Lax',
        )
        return response


class CheckInviteView(APIView):
    """前端检测：是否有有效的机构邀请 cookie"""
    permission_classes = [AllowAny]

    def get(self, request):
        invite_slug = request.COOKIES.get('institution_invite', '')
        exists = bool(
            invite_slug
            and Institution.objects.filter(invite_slug=invite_slug, is_active=True).exists()
        )
        return Response({'has_invite': exists})


# ── Institution Self-Update (机构管理员编辑自己的机构信息) ──

class InstitutionSelfUpdateView(APIView):
    """机构管理员可编辑机构名称、联系人、Logo、简介等信息。学生无权访问。"""
    permission_classes = [IsAuthenticated, IsInstitutionOwner, IsInstitutionActive]

    def _build_logo_url(self, inst, request):
        if inst.logo:
            return request.build_absolute_uri(inst.logo.url)
        return None

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
            'staff_count': inst.students.filter(institution_role__in=('owner', 'teacher')).count(),
            'notes': inst.notes or '',
            'description': inst.description or '',
            'custom_domain': inst.custom_domain or '',
            'business_type': inst.business_type or '',
            'logo_url': self._build_logo_url(inst, request),
        })

    def put(self, request):
        inst = request.user.institution
        allowed = ['name', 'contact_name', 'contact_email', 'contact_phone', 'notes', 'description', 'business_type']
        updated = []
        for field in allowed:
            if field in request.data:
                setattr(inst, field, request.data[field])
                updated.append(field)
        if 'logo' in request.FILES:
            inst.logo = request.FILES['logo']
            updated.append('logo')
        if updated:
            updated.append('updated_at')
            inst.save(update_fields=updated)
        return Response({
            'status': 'ok',
            'name': inst.name,
            'contact_name': inst.contact_name,
            'notes': inst.notes or '',
            'logo_url': self._build_logo_url(inst, request),
        })


class RegenerateInviteSlugView(APIView):
    """机构所有者重新生成邀请链接 slug"""
    permission_classes = [IsAuthenticated, IsInstitutionOwner, IsInstitutionActive]

    def post(self, request):
        inst = request.user.institution
        inst.regenerate_invite_slug()
        return Response({'invite_slug': inst.invite_slug})


# ── Institution Member Management (owner + teacher) ──

class InstitutionMemberListView(APIView):
    """机构管理员（owner / teacher）列出所有成员（教师 + 学员）"""
    permission_classes = [IsAuthenticated, IsInstitutionAdmin, IsInstitutionActive]

    def get(self, request):
        inst = request.user.institution
        qs = inst.students.exclude(institution_role='owner').order_by('institution_role', '-date_joined')
        serializer = InstitutionStudentSerializer(qs, many=True)
        return Response(serializer.data)


class InstitutionMemberRoleView(APIView):
    """机构所有者修改成员角色（student ↔ teacher）"""
    permission_classes = [IsAuthenticated, IsInstitutionOwner, IsInstitutionActive]

    def patch(self, request, pk):
        inst = request.user.institution
        member = get_object_or_404(
            User, pk=pk, institution=inst)
        if member.institution_role not in ('teacher', 'student'):
            return Response({'error': '不能修改此用户的角色'}, status=400)
        new_role = (request.data.get('role') or '').strip()
        if new_role not in ('teacher', 'student'):
            return Response({'error': '无效的角色'}, status=400)
        member.institution_role = new_role
        member.save(update_fields=['institution_role'])
        return Response(InstitutionStudentSerializer(member).data)


# ── Public Institution Page ──

class PublicInstitutionView(APIView):
    """公开：按 slug 获取机构信息（机构公开页使用）"""
    permission_classes = [AllowAny]

    def get(self, request, slug):
        inst = get_object_or_404(Institution, slug=slug, is_active=True)
        return Response({
            'id': inst.id,
            'name': inst.name,
            'slug': inst.slug,
            'description': inst.description or '',
            'logo_url': request.build_absolute_uri(inst.logo.url) if inst.logo else None,
        })


class InstitutionJoinBySlugView(APIView):
    """学生通过机构标识（slug 或 invite_slug）加入机构"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        identifier = (request.data.get('slug') or '').strip()
        if not identifier:
            return Response({'error': '缺少机构标识'}, status=400)

        from django.db.models import Q
        try:
            inst = Institution.objects.get(
                Q(slug=identifier) | Q(invite_slug=identifier),
                is_active=True,
            )
        except Institution.DoesNotExist:
            return Response({'error': '机构不存在或已停用'}, status=404)
        except Institution.MultipleObjectsReturned:
            inst = Institution.objects.filter(slug=identifier, is_active=True).first()

        if not inst.is_plan_active:
            return Response({'error': '该机构服务已到期'}, status=403)

        if inst.student_count >= inst.max_students:
            return Response({'error': '该机构学员数已达上限'}, status=403)

        user = request.user
        if user.institution == inst:
            return Response({'status': 'ok', 'institution': {'id': inst.id, 'name': inst.name}})
        if user.institution is not None:
            return Response({'error': '你已加入其他机构，请先退出'}, status=409)

        user.institution = inst
        user.institution_role = 'student'
        user.is_member = True
        user.membership_tier = inst.plan
        user.save(update_fields=['institution', 'institution_role', 'is_member', 'membership_tier'])

        return Response({
            'status': 'ok',
            'institution': {'id': inst.id, 'name': inst.name},
        })


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

        # Clone knowledge trees for selected subjects
        subject_names = (request.data.get('subject_names') or [])
        if isinstance(subject_names, str):
            subject_names = [s.strip() for s in subject_names.split(',') if s.strip()]

        # Filter out "custom" — it means user wants empty tree
        subject_names = [s for s in subject_names if s and s != 'custom']

        max_dirs = DIRECTION_LIMITS.get(plan, 1)
        if len(subject_names) > max_dirs:
            return Response(
                {'error': f'{plan.upper()} 方案最多选择 {max_dirs} 个学科方向'},
                status=400,
            )

        inst = Institution.objects.create(
            name=name, slug=slug,
            contact_name=contact_name,
            contact_email=contact_email,
            contact_phone=contact_phone,
            description=description,
            plan=plan,
            plan_expires_at=compute_expiry(duration_days),
            created_by=user,
            is_active=True,
        )

        imported_count = 0
        for s in subject_names:
            imported_count += _clone_knowledge_tree(s, inst)

        # Also store business_type
        inst.business_type = ', '.join(subject_names) if subject_names else '自定义'
        inst.save(update_fields=['business_type'])

        user.institution = inst
        user.institution_role = 'owner'
        user.is_member = True
        user.membership_tier = user.institution.plan if user.institution else 'free'
        user.save(update_fields=['institution', 'institution_role', 'is_member', 'membership_tier'])

        return Response({
            'status': 'ok',
            'institution': {
                'id': inst.id, 'name': inst.name, 'slug': inst.slug,
                'plan': inst.plan, 'plan_label': inst.get_plan_display(),
            },
            'imported_nodes': imported_count,
            'subjects_imported': subject_names,
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


class ValidateInviteCodeView(APIView):
    """Validate a PlanInviteCode without consuming it — returns plan info for UI gating."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        invite_code = (request.data.get('invite_code') or '').strip().upper()
        if not invite_code:
            return Response({'error': '请输入方案邀请码'}, status=400)

        try:
            code_obj = PlanInviteCode.objects.get(code=invite_code, is_active=True)
        except PlanInviteCode.DoesNotExist:
            return Response({'error': '无效的方案邀请码'}, status=400)

        if code_obj.is_exhausted:
            return Response({'error': '该邀请码已达使用上限'}, status=400)

        return Response({
            'plan': code_obj.plan,
            'plan_label': code_obj.get_plan_display(),
            'duration_days': code_obj.duration_days,
        })
