import csv
import logging
from django.db import transaction
from django.db.models import F
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.utils import timezone
from datetime import timedelta



logger = logging.getLogger(__name__)

from django.contrib.auth import get_user_model
from .models import Institution, PlanInviteCode, get_plan_features, PLAN_FEATURES, compute_expiry, DEFAULT_DURATION_DAYS, DURATION_PERMANENT, MAX_DURATION_DAYS, ClassCourse, InstitutionInvite, JoinRequest

User = get_user_model()
from .permissions import IsPlatformAdmin, IsInstitutionAdmin, IsInstitutionOwner, IsInstitutionActive, IsInstitutionMember, IsInstitutionTeacher, is_platform_admin
from .serializers_institution import (
    InstitutionSerializer, CreateInstitutionSerializer, ChangePlanSerializer,
    InstitutionStudentSerializer, CreateStudentSerializer, InstitutionFeatureSerializer,
    InstitutionInviteSerializer, CreateInstitutionInviteSerializer, JoinRequestSerializer,
)

DIRECTION_LIMITS = {'starter': 1, 'growth': 3, 'enterprise': 999999}


def _get_institution_ids_for_query(inst, include_children: bool = False) -> list[int]:
    """返回查询范围：若 include_children 且为根机构，则包含所有子孙校区 ID。"""
    if include_children and inst and inst.is_root():
        return [inst.pk] + inst.get_descendant_ids()
    return [inst.pk] if inst else []


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
        # 创建机构的用户应升级为管理员
        request.user.role = 'admin'
        request.user.institution_role = 'owner'
        request.user.institution = institution
        request.user.save()
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


# ── Institution Admin: Student Management ──

class InstitutionStudentListView(APIView):
    permission_classes = [IsAuthenticated, IsInstitutionAdmin, IsInstitutionActive]

    def get(self, request):
        inst = request.user.institution
        include_children = request.query_params.get('include_children') == 'true'
        inst_ids = _get_institution_ids_for_query(inst, include_children)
        qs = User.objects.filter(institution_id__in=inst_ids, institution_role='student').order_by('-date_joined')
        try:
            page = int(request.query_params.get('page', 1))
            page_size = int(request.query_params.get('page_size', 20))
        except (ValueError, TypeError):
            page, page_size = 1, 20
        total = qs.count()
        start = (page - 1) * page_size
        end = start + page_size
        serializer = InstitutionStudentSerializer(qs[start:end], many=True)
        return Response({
            'results': serializer.data,
            'total': total,
            'page': page,
            'total_pages': (total + page_size - 1) // page_size,
            'aggregated': include_children,
        })

    def post(self, request):
        inst = request.user.institution

        # 批量导入
        students_data = request.data.get('students')
        if isinstance(students_data, list):
            if not students_data:
                return Response({'error': '学员列表为空'}, status=status.HTTP_400_BAD_REQUEST)

            with transaction.atomic():
                inst = Institution.objects.select_for_update().get(pk=inst.pk)
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
        include_children = request.query_params.get('include_children') == 'true'
        inst_ids = _get_institution_ids_for_query(inst, include_children)
        qs = User.objects.filter(institution_id__in=inst_ids).order_by('-elo_score')[:50]
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
            effective_plan = inst.get_effective_plan()
            plan_label = dict(Institution.PLAN_CHOICES).get(effective_plan, effective_plan)
            inst_data = {
                'id': inst.id, 'name': inst.name, 'slug': inst.slug,
                'plan': effective_plan, 'plan_label': plan_label,
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
        if is_platform_admin(user) and inst is None:
            features = get_plan_features('enterprise')
        elif inst:
            features = get_plan_features(inst.get_effective_plan())
        else:
            features = []

        from users.quota import get_all_quota_info
        usage = get_all_quota_info(inst) if inst else {}
        # 向后兼容：顶层 used/limit → ai_question
        ai_q = usage.get('ai_question', {})
        usage.setdefault('used', ai_q.get('used', 0))
        usage.setdefault('limit', ai_q.get('limit', 0))

        return Response(InstitutionFeatureSerializer({
            'is_platform_admin': is_platform_admin(user),
            'institution': inst_data,
            'features': features,
            'usage': usage,
        }).data)


# ── Institution Dashboard ──

class InstitutionDashboardView(APIView):
    """机构管理员仪表盘"""
    permission_classes = [IsAuthenticated, IsInstitutionAdmin, IsInstitutionActive]

    def get(self, request):
        user = request.user
        inst = user.institution
        include_children = request.query_params.get('include_children') == 'true'
        inst_ids = _get_institution_ids_for_query(inst, include_children)

        # 7-day active student count
        from django.utils import timezone
        from datetime import timedelta
        from django.db.models import Count, Q
        week_ago = timezone.now() - timedelta(days=7)
        student_ids = User.objects.filter(
            institution_id__in=inst_ids, institution_role='student'
        ).values_list('id', flat=True)
        weekly_active = 0
        if student_ids:
            from quizzes.models import ReviewLog
            weekly_active = ReviewLog.objects.filter(
                user_id__in=student_ids, review_time__gte=week_ago
            ).values('user_id').distinct().count()

        # 配额用量（始终基于根机构）
        from users.quota import get_all_quota_info
        root_inst = inst.get_root() if inst else None
        quota_info = get_all_quota_info(root_inst) if root_inst else {}

        # 薄弱知识点排行
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

        # 待批改作业 + 进行中作业（Workbench 操作卡片数据）
        pending_grading = 0
        active_assignments = 0
        try:
            from quizzes.models import Assignment, AssignmentSubmission
            assignment_ids = Assignment.objects.filter(
                institution_id__in=inst_ids, status='published'
            ).values_list('id', flat=True)
            active_assignments = len(assignment_ids)
            pending_grading = AssignmentSubmission.objects.filter(
                assignment__institution_id__in=inst_ids, score__isnull=True
            ).count()
        except Exception:
            pass

        return Response({
            'mode': 'institution_admin',
            'institution': {
                'id': inst.id, 'name': inst.name, 'plan': inst.get_effective_plan(),
                'plan_label': dict(Institution.PLAN_CHOICES).get(inst.get_effective_plan(), inst.get_effective_plan()),
                'plan_expires_at': inst.plan_expires_at,
                'is_active': inst.is_active,
                'is_plan_active': inst.is_plan_active,
                'max_students': inst.max_students,
                'student_count': User.objects.filter(institution_id__in=inst_ids, institution_role='student').count(),
                'staff_count': User.objects.filter(institution_id__in=inst_ids, institution_role__in=('owner', 'teacher', 'registrar')).count(),
            },
            'stats': {
                'weekly_active_students': weekly_active,
                'ai_usage': {'used': quota_info.get('ai_question', {}).get('used', 0), 'limit': quota_info.get('ai_question', {}).get('limit', 0)},
                'quota': quota_info,
                'top_weak_points': top_weak,
                'pending_grading': pending_grading,
                'active_assignments': active_assignments,
            },
            'features': get_plan_features(inst.plan),
            'plan_matrix': {p: get_plan_features(p) for p in ['free', 'starter', 'growth', 'enterprise']},
        })


class PlatformAdminInstitutionOverviewView(APIView):
    """平台管理员机构总览"""
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def get(self, request):
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
                    'staff_count': i.students.filter(institution_role__in=('owner', 'teacher', 'registrar')).count(),
                }
                for i in qs
            ],
            'plan_matrix': {p: get_plan_features(p) for p in ['free', 'starter', 'growth', 'enterprise']},
        })


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


class CheckInviteView(APIView):
    """前端检测：是否有有效的机构邀请 cookie"""
    permission_classes = [AllowAny]

    def get(self, request):
        invite_slug = request.COOKIES.get('institution_invite', '')
        exists = bool(
            invite_slug and (
                InstitutionInvite.objects.filter(slug=invite_slug, is_active=True).exists()
                or Institution.objects.filter(invite_slug=invite_slug, is_active=True).exists()
            )
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
        effective_plan = inst.get_effective_plan()
        plan_label = dict(Institution.PLAN_CHOICES).get(effective_plan, effective_plan)
        return Response({
            'id': inst.id,
            'name': inst.name,
            'slug': inst.slug,
            'contact_name': inst.contact_name,
            'contact_email': inst.contact_email,
            'contact_phone': inst.contact_phone,
            'plan': effective_plan,
            'plan_label': plan_label,
            'plan_expires_at': inst.plan_expires_at,
            'is_plan_active': inst.is_plan_active,
            'max_students': inst.max_students,
            'student_count': inst.student_count,
            'staff_count': inst.students.filter(institution_role__in=('owner', 'teacher', 'registrar')).count(),
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
            from core.file_validation import validate_upload_file
            validate_upload_file(request.FILES['logo'], allowed_extensions={'.jpg', '.jpeg', '.png', '.webp'})
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


class UpdateDirectionsView(APIView):
    """机构所有者更新业务方向 —— 删旧 KP，克隆新方向 KP。"""
    permission_classes = [IsAuthenticated, IsInstitutionOwner, IsInstitutionActive]

    def put(self, request):
        inst = request.user.institution
        plan = inst.plan

        subject_names = (request.data.get('subject_names') or [])
        if isinstance(subject_names, str):
            subject_names = [s.strip() for s in subject_names.split(',') if s.strip()]
        subject_names = [s for s in subject_names if s and s != 'custom']

        max_dirs = DIRECTION_LIMITS.get(plan, 1)
        if len(subject_names) > max_dirs:
            return Response(
                {'error': f'{plan.upper()} 方案最多选择 {max_dirs} 个学科方向'},
                status=400,
            )

        # Delete existing institution KPs
        from quizzes.models import KnowledgePoint
        deleted, _ = KnowledgePoint.objects.filter(institution=inst).delete()

        # Clone selected subjects
        imported_count = 0
        for s in subject_names:
            imported_count += _clone_knowledge_tree(s, inst)

        inst.business_type = ', '.join(subject_names) if subject_names else '自定义'
        inst.save(update_fields=['business_type'])

        return Response({
            'status': 'ok',
            'deleted': deleted,
            'imported_nodes': imported_count,
            'subjects': subject_names,
            'business_type': inst.business_type,
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
        include_children = request.query_params.get('include_children') == 'true'
        inst_ids = _get_institution_ids_for_query(inst, include_children)
        qs = User.objects.filter(institution_id__in=inst_ids).exclude(institution_role='owner').order_by('institution_role', '-date_joined')
        serializer = InstitutionStudentSerializer(qs, many=True)
        return Response(serializer.data)


class InstitutionMemberRoleView(APIView):
    """机构所有者修改成员角色（student ↔ teacher ↔ registrar）"""
    permission_classes = [IsAuthenticated, IsInstitutionOwner, IsInstitutionActive]

    def patch(self, request, pk):
        inst = request.user.institution
        member = get_object_or_404(
            User, pk=pk, institution=inst)
        if member.institution_role not in ('teacher', 'student', 'registrar'):
            return Response({'error': '不能修改此用户的角色'}, status=400)
        new_role = (request.data.get('role') or '').strip()
        if new_role not in ('teacher', 'student', 'registrar'):
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
    """通过机构标识（slug 或 invite_slug）加入机构，role 由邀请链接或请求参数决定"""
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

        role = 'student'  # 通过邀请链接加入的用户只能是学生，教师角色需机构管理员指定

        if inst.student_count >= inst.max_students:
            return Response({'error': '该机构学员数已达上限'}, status=403)

        user = request.user
        if user.institution == inst:
            return Response({'status': 'ok', 'institution': {'id': inst.id, 'name': inst.name}})
        if user.institution is not None:
            return Response({'error': '你已加入其他机构，请先退出'}, status=409)

        user.institution = inst
        user.institution_role = role
        user.is_member = True
        user.membership_tier = inst.get_effective_plan()
        user.save(update_fields=['institution', 'institution_role', 'is_member', 'membership_tier'])

        return Response({
            'status': 'ok',
            'institution': {'id': inst.id, 'name': inst.name},
        })


class InstitutionJoinByInviteSlugView(APIView):
    """已登录用户通过邀请链接加入机构。支持审批流。"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        invite_slug = (request.data.get('invite_slug') or '').strip()
        if not invite_slug:
            return Response({'error': '缺少邀请标识'}, status=400)

        # 优先查 InstitutionInvite，fallback 到旧的 Institution.invite_slug
        invite = InstitutionInvite.objects.filter(slug=invite_slug, is_active=True).first()
        if invite:
            inst = invite.institution
            if not inst.is_active or not inst.is_plan_active:
                return Response({'error': '该机构已停用或服务已到期'}, status=403)
            assigned_role = invite.assigned_role
            requires_approval = invite.requires_approval
        else:
            try:
                inst = Institution.objects.get(invite_slug=invite_slug, is_active=True)
            except Institution.DoesNotExist:
                return Response({'error': '邀请链接无效或机构已停用'}, status=404)
            if not inst.is_plan_active:
                return Response({'error': '该机构服务已到期'}, status=403)
            assigned_role = 'student'
            requires_approval = False  # 旧链接向后兼容：无需审批

        if inst.student_count >= inst.max_students:
            return Response({'error': '该机构学员数已达上限'}, status=403)

        user = request.user
        if user.institution == inst:
            return Response({'status': 'ok', 'institution': {'id': inst.id, 'name': inst.name}})
        if user.institution is not None:
            return Response({'error': '你已加入其他机构，请先退出'}, status=409)

        # 检查是否已有待审批的申请
        existing_req = JoinRequest.objects.filter(user=user, institution=inst, status='pending').first()
        if existing_req:
            return Response({
                'status': 'pending_approval',
                'institution': {'id': inst.id, 'name': inst.name},
            })

        if requires_approval:
            # 创建加入申请
            join_req = JoinRequest.objects.create(
                institution=inst, user=user, invite=invite,
                status='pending',
            )
            # 通知机构管理员
            from notifications.models import Notification
            admins = inst.students.filter(institution_role__in=('owner', 'teacher', 'registrar'))
            for admin in admins:
                Notification.objects.create(
                    recipient=admin, sender=user, ntype='join_request',
                    title='新的加入申请',
                    content=f'{user.nickname or user.username} 申请加入机构',
                    link='/management?tab=join-requests',
                )
            return Response({
                'status': 'pending_approval',
                'institution': {'id': inst.id, 'name': inst.name},
            })

        # 无需审批：直接加入并更新计数
        user.institution = inst
        user.institution_role = assigned_role
        user.is_member = True
        user.membership_tier = inst.get_effective_plan()
        user.save(update_fields=['institution', 'institution_role', 'is_member', 'membership_tier'])

        if invite:
            InstitutionInvite.objects.filter(pk=invite.pk).update(
                used_count=F('used_count') + 1
            )

        return Response({
            'status': 'ok',
            'institution': {'id': inst.id, 'name': inst.name},
        })


# ── Institution Invites CRUD ──

class InstitutionInviteListView(APIView):
    """教师管理机构邀请链接：GET 列表 / POST 创建"""
    permission_classes = [IsAuthenticated, IsInstitutionTeacher, IsInstitutionActive]

    def get(self, request):
        inst = request.user.institution
        qs = InstitutionInvite.objects.filter(institution=inst).order_by('-created_at')
        return Response(InstitutionInviteSerializer(qs, many=True).data)

    def post(self, request):
        inst = request.user.institution
        serializer = CreateInstitutionInviteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invite = InstitutionInvite.objects.create(
            institution=inst,
            created_by=request.user,
            **serializer.validated_data,
        )
        return Response(InstitutionInviteSerializer(invite).data, status=201)


class InstitutionInviteDetailView(APIView):
    """PATCH 更新 / DELETE 删除邀请链接"""
    permission_classes = [IsAuthenticated, IsInstitutionTeacher, IsInstitutionActive]

    def patch(self, request, pk):
        inst = request.user.institution
        invite = get_object_or_404(InstitutionInvite, pk=pk, institution=inst)
        for field in ['is_active', 'max_uses', 'expires_at', 'requires_approval', 'assigned_role']:
            if field in request.data:
                setattr(invite, field, request.data[field])
        invite.save()
        return Response(InstitutionInviteSerializer(invite).data)

    def delete(self, request, pk):
        inst = request.user.institution
        invite = get_object_or_404(InstitutionInvite, pk=pk, institution=inst)
        invite.delete()
        return Response(status=204)


class InstitutionJoinRequestListView(APIView):
    """GET 加入申请列表（按状态筛选）"""
    permission_classes = [IsAuthenticated, IsInstitutionTeacher, IsInstitutionActive]

    def get(self, request):
        inst = request.user.institution
        status_filter = request.query_params.get('status', 'pending')
        qs = JoinRequest.objects.filter(
            institution=inst, status=status_filter,
        ).select_related('user', 'invite').order_by('-created_at')
        return Response(JoinRequestSerializer(qs, many=True).data)


class InstitutionJoinRequestReviewView(APIView):
    """PATCH 审批加入申请（通过/拒绝）"""
    permission_classes = [IsAuthenticated, IsInstitutionTeacher, IsInstitutionActive]

    def patch(self, request, pk):
        inst = request.user.institution
        join_req = get_object_or_404(JoinRequest, pk=pk, institution=inst, status='pending')
        action = (request.data.get('status') or '').strip()
        if action not in ('approved', 'rejected'):
            return Response({'error': 'status 必须是 approved 或 rejected'}, status=400)

        join_req.status = action
        join_req.reviewed_by = request.user
        join_req.reviewed_at = timezone.now()
        join_req.save()

        if action == 'approved':
            user = join_req.user
            user.institution = inst
            user.institution_role = join_req.invite.assigned_role if join_req.invite else 'student'
            user.is_member = True
            user.membership_tier = inst.get_effective_plan()
            user.save(update_fields=['institution', 'institution_role', 'is_member', 'membership_tier'])
            if join_req.invite:
                InstitutionInvite.objects.filter(pk=join_req.invite_id).update(
                    used_count=F('used_count') + 1
                )

        return Response(JoinRequestSerializer(join_req).data)


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
        student_scale = (request.data.get('student_scale') or '').strip()

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
            student_scale=student_scale,
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
        user.role = 'admin'
        user.is_member = True
        user.membership_tier = user.institution.get_effective_plan() if user.institution else 'free'
        user.save(update_fields=['institution', 'institution_role', 'role', 'is_member', 'membership_tier'])

        # 创建「初始化题库」通知
        if imported_count > 0:
            from notifications.models import Notification
            Notification.objects.create(
                recipient=user,
                ntype='bulk_init',
                title='初始化题库',
                content=f'你的机构「{inst.name}」已导入 {imported_count} 个知识点。可以现在用 AI 批量生成题目。',
                link='/workbench',
            )

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
            'id': c.id, 'code': c.code, 'code_type': c.code_type,
            'plan': c.plan,
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
        code_type = (request.data.get('code_type') or 'formal').strip()
        if code_type not in ('trial', 'formal'):
            return Response({'error': '无效的码类型'}, status=400)

        plan = (request.data.get('plan') or '').strip()
        if code_type == 'trial':
            plan = 'growth'
        elif plan not in dict(Institution.PLAN_CHOICES):
            return Response({'error': '无效的方案类型'}, status=400)

        count = max(1, min(int(request.data.get('count', 1)), 100))
        max_uses = max(1, min(int(request.data.get('max_uses', 1)), 1000))
        duration_days = 7 if code_type == 'trial' else max(DURATION_PERMANENT, min(int(request.data.get('duration_days', DEFAULT_DURATION_DAYS)), MAX_DURATION_DAYS))
        note = (request.data.get('note') or '').strip()

        codes = PlanInviteCode.generate(plan=plan, created_by=request.user, count=count, max_uses=max_uses, duration_days=duration_days, note=note, code_type=code_type)
        return Response({
            'generated': len(codes),
            'code_type': code_type,
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


# ── Institution Analytics (teacher/owner) ──

class InstitutionClassPerformanceView(APIView):
    """GET /api/users/institution/me/analytics/class-performance/
    各知识点的班级正确率、趋势、参与学生数。仅 teacher/owner 可用。
    """
    permission_classes = [IsAuthenticated, IsInstitutionAdmin, IsInstitutionActive]

    def get(self, request):
        from django.db.models import Sum, Count, Q
        from quizzes.models import UserQuestionStatus, Question

        inst = request.user.institution
        include_children = request.query_params.get('include_children') == 'true'
        inst_ids = _get_institution_ids_for_query(inst, include_children)
        student_ids = list(
            User.objects.filter(institution_id__in=inst_ids, institution_role='student').values_list('id', flat=True)
        )
        if not student_ids:
            return Response({'results': []})

        now = timezone.now()
        week_ago = now - timedelta(days=7)
        two_weeks_ago = now - timedelta(days=14)

        # Aggregate by knowledge_point: reps + lapses = total_attempts, reps = correct
        qs = (
            UserQuestionStatus.objects
            .filter(user_id__in=student_ids, question__knowledge_point__isnull=False)
            .values(
                'question__knowledge_point__id',
                'question__knowledge_point__name',
                'question__knowledge_point__code',
            )
            .annotate(
                total_reps=Sum('reps'),
                total_lapses=Sum('lapses'),
                student_count=Count('user_id', distinct=True),
            )
        )

        # Build per-KP weekly trend: this week vs last week correct rate
        weekly_qs = (
            UserQuestionStatus.objects
            .filter(
                user_id__in=student_ids,
                question__knowledge_point__isnull=False,
                last_review__gte=two_weeks_ago,
            )
            .values(
                'question__knowledge_point__id',
                'last_review__date',
            )
            .annotate(
                day_reps=Sum('reps'),
                day_lapses=Sum('lapses'),
            )
        )

        # Compute per-KP this-week and last-week rates
        kp_weekly: dict[int, dict[str, tuple[int, int]]] = {}
        for row in weekly_qs:
            kp_id = row['question__knowledge_point__id']
            date = row['last_review__date']
            bucket = 'this_week' if date >= week_ago.date() else 'last_week'
            r, l = row['day_reps'] or 0, row['day_lapses'] or 0
            kp_weekly.setdefault(kp_id, {}).setdefault(bucket, [0, 0])
            kp_weekly[kp_id][bucket][0] += r
            kp_weekly[kp_id][bucket][1] += l

        results = []
        for row in qs:
            kp_id = row['question__knowledge_point__id']
            total = (row['total_reps'] or 0) + (row['total_lapses'] or 0)
            correct_rate = round((row['total_reps'] or 0) / total * 100, 1) if total > 0 else 0

            # Trend
            trend = 'stable'
            wk = kp_weekly.get(kp_id, {})
            tw = wk.get('this_week', [0, 0])
            lw = wk.get('last_week', [0, 0])
            tw_total = tw[0] + tw[1]
            lw_total = lw[0] + lw[1]
            if tw_total > 0 and lw_total > 0:
                tw_rate = tw[0] / tw_total
                lw_rate = lw[0] / lw_total
                diff = tw_rate - lw_rate
                if diff > 0.05:
                    trend = 'up'
                elif diff < -0.05:
                    trend = 'down'

            results.append({
                'kp_id': kp_id,
                'kp_name': row['question__knowledge_point__name'] or '',
                'kp_code': row['question__knowledge_point__code'] or '',
                'correct_rate': correct_rate,
                'total_attempts': total,
                'student_count': row['student_count'] or 0,
                'trend': trend,
            })

        results.sort(key=lambda x: x['correct_rate'])
        return Response({'results': results})


class InstitutionSuggestedTopicsView(APIView):
    """GET /api/users/institution/me/analytics/suggested-topics/
    基于班级数据，返回 top 5 最弱知识点及建议。仅 teacher/owner 可用。
    """
    permission_classes = [IsAuthenticated, IsInstitutionAdmin, IsInstitutionActive]

    def get(self, request):
        # Reuse the class-performance logic (compact version)
        from django.db.models import Sum, Count
        from quizzes.models import UserQuestionStatus

        inst = request.user.institution
        include_children = request.query_params.get('include_children') == 'true'
        inst_ids = _get_institution_ids_for_query(inst, include_children)
        student_ids = list(
            User.objects.filter(institution_id__in=inst_ids, institution_role='student').values_list('id', flat=True)
        )
        if not student_ids:
            return Response({'suggested_topics': []})

        qs = (
            UserQuestionStatus.objects
            .filter(user_id__in=student_ids, question__knowledge_point__isnull=False)
            .values(
                'question__knowledge_point__id',
                'question__knowledge_point__name',
                'question__knowledge_point__code',
            )
            .annotate(
                total_reps=Sum('reps'),
                total_lapses=Sum('lapses'),
                student_count=Count('user_id', distinct=True),
            )
        )

        scored = []
        for row in qs:
            total = (row['total_reps'] or 0) + (row['total_lapses'] or 0)
            if total == 0:
                continue
            correct_rate = (row['total_reps'] or 0) / total
            scored.append({
                'kp_id': row['question__knowledge_point__id'],
                'kp_name': row['question__knowledge_point__name'] or '',
                'kp_code': row['question__knowledge_point__code'] or '',
                'correct_rate': round(correct_rate * 100, 1),
                'total_attempts': total,
                'student_count': row['student_count'] or 0,
            })

        scored.sort(key=lambda x: x['correct_rate'])
        top5 = scored[:5]

        for item in top5:
            rate = item['correct_rate']
            if rate < 40:
                item['priority'] = 'high'
                item['suggested_action'] = '建议立即加强练习，当前正确率过低'
            elif rate < 60:
                item['priority'] = 'medium'
                item['suggested_action'] = '建议安排专项训练，巩固薄弱环节'
            else:
                item['priority'] = 'low'
                item['suggested_action'] = '建议适当复习，保持记忆强度'

        return Response({'suggested_topics': top5})


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


# ── Institution Payment Config (Pro 机构专属) ──

class InstitutionPaymentConfigView(APIView):
    """Pro 机构读写自有收款配置。仅机构 owner 可访问。"""
    permission_classes = [IsAuthenticated, IsInstitutionOwner, IsInstitutionActive]

    def get(self, request):
        inst = request.user.institution
        from users.models_commercial import InstitutionPaymentConfig
        cfg, _ = InstitutionPaymentConfig.objects.get_or_create(institution=inst)
        return Response({
            'is_enabled': cfg.is_enabled,
            'wechat_merchant_id': cfg.wechat_merchant_id,
            'wechat_cert_serial': cfg.wechat_cert_serial,
            'alipay_app_id': cfg.alipay_app_id,
            # Keys are encrypted — only return masked versions
            'wechat_has_key': bool(cfg.wechat_api_v3_key),
            'alipay_has_key': bool(cfg.alipay_private_key),
        })

    def put(self, request):
        inst = request.user.institution
        if inst.get_effective_plan() != 'enterprise':
            return Response({'error': '仅 Enterprise 方案支持自有收款配置'}, status=403)

        from users.models_commercial import InstitutionPaymentConfig
        cfg, _ = InstitutionPaymentConfig.objects.get_or_create(institution=inst)

        allowed = ['wechat_merchant_id', 'wechat_api_v3_key', 'wechat_cert_serial',
                   'alipay_app_id', 'alipay_private_key', 'is_enabled']
        for field in allowed:
            if field in request.data:
                setattr(cfg, field, request.data[field])
        cfg.save()

        return Response({
            'is_enabled': cfg.is_enabled,
            'wechat_merchant_id': cfg.wechat_merchant_id,
            'wechat_cert_serial': cfg.wechat_cert_serial,
            'alipay_app_id': cfg.alipay_app_id,
            'wechat_has_key': bool(cfg.wechat_api_v3_key),
            'alipay_has_key': bool(cfg.alipay_private_key),
        })


class InstitutionAuditLogView(APIView):
    """机构操作审计日志（机构管理员可见）。

    GET /api/users/institution/me/audit-logs/?page=1
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        inst = request.user.institution
        if not inst:
            return Response({'error': '未加入机构'}, status=400)
        if request.user.institution_role not in ('owner', 'teacher'):
            return Response({'error': '无权限'}, status=403)

        from .models import InstitutionAuditLog
        page = int(request.query_params.get('page', 1))
        page_size = 20
        qs = InstitutionAuditLog.objects.filter(institution=inst).select_related('operator')
        total = qs.count()
        items = qs[(page - 1) * page_size: page * page_size]

        return Response({
            'total': total,
            'page': page,
            'page_size': page_size,
            'items': [
                {
                    'id': log.id,
                    'operator': log.operator.username if log.operator else '系统',
                    'action': log.action,
                    'detail': log.detail,
                    'created_at': log.created_at.isoformat(),
                }
                for log in items
            ],
        })


class InstitutionNotificationConfigView(APIView):
    """机构通知配置 CRUD.

    GET  /api/users/institution/me/notification-config/
    PUT  /api/users/institution/me/notification-config/
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        inst = request.user.institution
        if not inst:
            return Response({'error': '未加入机构'}, status=400)
        if request.user.institution_role not in ('owner', 'teacher'):
            return Response({'error': '无权限'}, status=403)

        from users.models_commercial import InstitutionNotificationConfig
        config, _ = InstitutionNotificationConfig.objects.get_or_create(
            institution=inst,
            defaults={'enabled': False, 'channel': 'email', 'due_threshold': 5},
        )
        return Response({
            'enabled': config.enabled,
            'channel': config.channel,
            'due_threshold': config.due_threshold,
        })

    def put(self, request):
        inst = request.user.institution
        if not inst:
            return Response({'error': '未加入机构'}, status=400)
        if request.user.institution_role not in ('owner', 'teacher'):
            return Response({'error': '无权限'}, status=403)

        from users.models_commercial import InstitutionNotificationConfig
        config, _ = InstitutionNotificationConfig.objects.get_or_create(
            institution=inst,
        )

        if 'enabled' in request.data:
            config.enabled = bool(request.data['enabled'])
        if 'channel' in request.data:
            channel = request.data['channel']
            if channel in ('email', 'feishu'):
                config.channel = channel
        if 'due_threshold' in request.data:
            try:
                threshold = int(request.data['due_threshold'])
                config.due_threshold = max(1, min(threshold, 100))
            except (ValueError, TypeError):
                pass

        config.save()
        return Response({
            'enabled': config.enabled,
            'channel': config.channel,
            'due_threshold': config.due_threshold,
        })


# ── Class Management API ──────────────────────────────────────────

from rest_framework import generics, status
from users.models import Class as ClassModel
from django.db import IntegrityError


class ClassListCreateView(APIView):
    """GET /api/users/institution/me/classes/ — 班级列表 + 创建。"""
    permission_classes = [IsAuthenticated, IsInstitutionAdmin, IsInstitutionActive]

    def get(self, request):
        inst = request.user.institution
        include_children = request.query_params.get('include_children') == 'true'
        inst_ids = _get_institution_ids_for_query(inst, include_children)
        classes = ClassModel.objects.filter(institution_id__in=inst_ids).order_by('-created_at')
        data = []
        for c in classes:
            data.append({
                'id': c.id,
                'name': c.name,
                'institution_name': c.institution.name,
                'institution_id': c.institution_id,
                'student_count': c.students.count(),
                'students': [{'id': s.id, 'name': s.nickname or s.username}
                           for s in c.students.all()[:50]],
                'created_at': c.created_at.isoformat(),
            })
        return Response(data)

    def post(self, request):
        inst = request.user.institution
        name = (request.data.get('name') or '').strip()
        if not name:
            return Response({'error': '班级名称不能为空'}, status=400)
        try:
            c = ClassModel.objects.create(institution=inst, name=name)
            return Response({'id': c.id, 'name': c.name, 'student_count': 0}, status=201)
        except IntegrityError:
            return Response({'error': f'班级「{name}」已存在'}, status=409)


class ClassDetailView(APIView):
    """PUT/DELETE /api/users/institution/me/classes/<id>/ — 编辑/删除班级。"""
    permission_classes = [IsAuthenticated, IsInstitutionAdmin, IsInstitutionActive]

    def put(self, request, pk):
        inst = request.user.institution
        try:
            c = ClassModel.objects.get(id=pk, institution=inst)
        except ClassModel.DoesNotExist:
            return Response({'error': '班级不存在'}, status=404)
        name = (request.data.get('name') or '').strip()
        if not name:
            return Response({'error': '班级名称不能为空'}, status=400)
        c.name = name
        try:
            c.save()
        except IntegrityError:
            return Response({'error': f'班级「{name}」已存在'}, status=409)
        return Response({'id': c.id, 'name': c.name})

    def delete(self, request, pk):
        inst = request.user.institution
        try:
            c = ClassModel.objects.get(id=pk, institution=inst)
        except ClassModel.DoesNotExist:
            return Response({'error': '班级不存在'}, status=404)
        c.delete()
        return Response({'ok': True})


class ClassStudentView(APIView):
    """POST /api/users/institution/me/classes/<id>/students/ — 添加/移除学生。"""
    permission_classes = [IsAuthenticated, IsInstitutionAdmin, IsInstitutionActive]

    def post(self, request, pk):
        inst = request.user.institution
        try:
            c = ClassModel.objects.get(id=pk, institution=inst)
        except ClassModel.DoesNotExist:
            return Response({'error': '班级不存在'}, status=404)

        action = request.data.get('action', 'add')
        student_ids = request.data.get('student_ids', [])

        if action == 'add':
            for sid in student_ids:
                student = User.objects.filter(id=sid, institution=inst).first()
                if student:
                    c.students.add(student)
        elif action == 'remove':
            for sid in student_ids:
                c.students.remove(sid)

        return Response({
            'id': c.id,
            'student_count': c.students.count(),
            'students': [{'id': s.id, 'name': s.nickname or s.username}
                       for s in c.students.all()[:50]],
        })


# ── Bulk Init ──

class InstitutionBulkInitView(APIView):
    """机构批量初始化出题资格查询。"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        inst = getattr(request.user, 'institution', None)
        if not inst:
            return Response({'eligible': False, 'reason': '无机构'})

        # 只统计机构专属知识点（不含全局）
        from quizzes.models import KnowledgePoint
        kps = KnowledgePoint.objects.filter(
            institution=inst,
            level='kp',
        )
        kp_count = kps.count()
        subjects = sorted(set(
            s for s in kps.values_list('subject', flat=True) if s
        ))

        return Response({
            'eligible': not inst.has_used_bulk_init,
            'has_used': inst.has_used_bulk_init,
            'kp_count': kp_count,
            'max_questions': 500,
            'available_subjects': subjects[:20],  # 最多 20 个学科
        })


# ── Class Course Management ──

class ClassCourseManageView(APIView):
    """POST/GET /api/users/institution/me/class-courses/ — 管理班级课程分配。"""
    permission_classes = [IsAuthenticated, IsInstitutionTeacher, IsInstitutionActive]

    def get(self, request):
        inst = request.user.institution
        qs = ClassCourse.objects.filter(institution=inst).select_related('class_obj', 'course').order_by('-created_at')
        data = []
        for cc in qs:
            data.append({
                'id': cc.id,
                'class_id': cc.class_obj_id,
                'class_name': cc.class_obj.name,
                'course_id': cc.course_id,
                'course_title': cc.course.title,
                'created_at': cc.created_at.isoformat(),
            })
        return Response(data)

    def post(self, request):
        inst = request.user.institution
        class_id = request.data.get('class_id')
        course_id = request.data.get('course_id')
        if not class_id or not course_id:
            return Response({'error': '缺少 class_id 或 course_id'}, status=400)

        try:
            class_obj = ClassModel.objects.get(id=int(class_id), institution=inst)
        except (ClassModel.DoesNotExist, ValueError, TypeError):
            return Response({'error': '班级不存在'}, status=404)

        from courses.models import Course
        if not Course.objects.filter(id=int(course_id), institution=inst).exists():
            return Response({'error': '课程不存在或不属于本机构'}, status=404)

        try:
            cc = ClassCourse.objects.create(
                class_obj=class_obj, course_id=int(course_id), institution=inst,
            )
            return Response({
                'id': cc.id,
                'class_id': cc.class_obj_id,
                'class_name': cc.class_obj.name,
                'course_id': cc.course_id,
                'course_title': cc.course.title,
                'created_at': cc.created_at.isoformat(),
            }, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({'error': f'创建失败: {str(e)}'}, status=400)

    def delete(self, request, pk=None):
        inst = request.user.institution
        cc_id = pk if pk else request.data.get('class_course_id')
        if not cc_id:
            return Response({'error': '缺少 class_course_id'}, status=400)
        try:
            cc = ClassCourse.objects.get(id=int(cc_id), institution=inst)
            cc.delete()
            return Response({'status': 'deleted'})
        except (ClassCourse.DoesNotExist, ValueError, TypeError):
            return Response({'error': '分配不存在'}, status=404)


class StudentClassCourseView(APIView):
    """GET /api/users/me/class-courses/ — 学生查看自己班级分配的课程。"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        class_ids = user.classes.values_list('id', flat=True)
        if not class_ids:
            return Response([])

        qs = ClassCourse.objects.filter(
            class_obj_id__in=class_ids,
        ).select_related('class_obj', 'course').order_by('-created_at')

        data = []
        seen = set()
        for cc in qs:
            if cc.course_id in seen:
                continue
            seen.add(cc.course_id)
            data.append({
                'class_id': cc.class_obj_id,
                'class_name': cc.class_obj.name,
                'course_id': cc.course_id,
                'course_title': cc.course.title,
                'created_at': cc.created_at.isoformat(),
            })
        return Response(data)


class ClassGradebookView(APIView):
    """GET /api/users/institution/me/gradebook/?class_id=X — 班级成绩册（学生 × 作业矩阵）。"""
    permission_classes = [IsAuthenticated, IsInstitutionAdmin, IsInstitutionActive]

    def get(self, request):
        inst = request.user.institution
        include_children = request.query_params.get('include_children') == 'true'
        inst_ids = _get_institution_ids_for_query(inst, include_children)
        class_id = request.query_params.get('class_id')
        if not class_id:
            return Response({'error': '缺少 class_id 参数'}, status=400)

        try:
            class_obj = ClassModel.objects.get(id=int(class_id), institution_id__in=inst_ids)
        except (ClassModel.DoesNotExist, ValueError, TypeError):
            return Response({'error': '班级不存在'}, status=404)

        from quizzes.models import Assignment, AssignmentSubmission

        assignments = Assignment.objects.filter(
            target_classes=class_obj, institution_id__in=inst_ids,
        ).order_by('-created_at')

        assignment_list = []
        for a in assignments:
            assignment_list.append({
                'id': a.id,
                'title': a.title,
                'due_date': a.due_date.isoformat() if a.due_date else None,
            })

        students = class_obj.students.all().order_by('id')
        student_list = []
        for student in students:
            submissions = AssignmentSubmission.objects.filter(
                student=student, assignment__in=assignments,
            ).select_related('assignment')
            sub_map = {s.assignment_id: s for s in submissions}

            scores = []
            for a in assignments:
                sub = sub_map.get(a.id)
                max_score = sum(aq.points for aq in a.assignment_questions.all())
                scores.append({
                    'assignment_id': a.id,
                    'assignment_title': a.title,
                    'score': sub.score if sub else None,
                    'submitted': sub is not None,
                    'max_score': max_score if max_score > 0 else None,
                })

            student_list.append({
                'id': student.id,
                'name': student.nickname or student.username,
                'scores': scores,
            })

        return Response({
            'class_name': class_obj.name,
            'students': student_list,
            'assignments': assignment_list,
        })


class InstitutionBusinessDashboardView(APIView):
    """GET /api/users/institution/me/business-dashboard/ — 机构商业指标仪表盘。"""
    permission_classes = [IsAuthenticated, IsInstitutionOwner, IsInstitutionActive]

    def get(self, request):
        inst = request.user.institution
        now = timezone.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        student_count = inst.students.filter(institution_role='student').count()

        from quizzes.models import ReviewLog
        active_student_ids = ReviewLog.objects.filter(
            user__institution=inst,
            user__institution_role='student',
            review_time__gte=month_start,
        ).values('user_id').distinct()
        active_this_month = active_student_ids.count()

        from quizzes.models import Assignment
        total_assignments = Assignment.objects.filter(institution=inst).count()

        from courses.models import Course
        total_courses = Course.objects.filter(institution=inst).count()

        retention_rate = 0.0
        if student_count > 0:
            retention_rate = round(active_this_month / student_count * 100, 1)

        # 营收指标：从 Order 表聚合
        from payments.models import Order
        paid_orders = Order.objects.filter(institution=inst, status='paid')
        total_revenue = paid_orders.aggregate(total=models.Sum('amount_cents'))['total'] or 0
        revenue_this_month = paid_orders.filter(paid_at__gte=month_start).aggregate(
            total=models.Sum('amount_cents')
        )['total'] or 0

        # ARPU：有付费订单的用户人均消费
        paying_user_ids = paid_orders.values('user_id').distinct()
        paying_count = paying_user_ids.count()
        arpu = round(total_revenue / paying_count / 100, 2) if paying_count > 0 else 0

        # 续费率：有 ≥2 笔付费订单的用户占比
        from django.db.models import Count
        renewing = paid_orders.values('user_id').annotate(
            order_count=Count('id')
        ).filter(order_count__gte=2).count()
        renewal_rate = round(renewing / paying_count * 100, 1) if paying_count > 0 else 0

        # MRR / ARR：从活跃订阅计算
        from payments.models import Subscription
        PLAN_MONTHLY_PRICE = {
            ('starter', 'monthly'): 9900, ('starter', 'annual'): 9900,   # annual 折算月均
            ('growth', 'monthly'): 29900, ('growth', 'annual'): 24917,
            ('enterprise', 'monthly'): 99900, ('enterprise', 'annual'): 83250,
        }
        active_subs = Subscription.objects.filter(
            institution=inst, status__in=('active', 'trialing', 'past_due')
        )
        mrr = 0
        subs_by_plan: dict[str, int] = {}
        for sub in active_subs:
            price = PLAN_MONTHLY_PRICE.get((sub.plan, sub.billing_cycle), 0)
            mrr += price
            subs_by_plan[sub.plan] = subs_by_plan.get(sub.plan, 0) + 1
        mrr_yuan = round(mrr / 100, 2)
        arr_yuan = round(mrr * 12 / 100, 2)

        return Response({
            'student_count': student_count,
            'active_students_this_month': active_this_month,
            'total_assignments': total_assignments,
            'total_courses': total_courses,
            'revenue': round(total_revenue / 100, 2),
            'revenue_this_month': round(revenue_this_month / 100, 2),
            'mrr': mrr_yuan,
            'arr': arr_yuan,
            'active_subscriptions': active_subs.count(),
            'subscriptions_by_plan': subs_by_plan,
            'retention_rate': retention_rate,
            'arpu': arpu,
            'renewal_rate': renewal_rate,
            'paying_users': paying_count,
        })


class InstitutionDataExportView(APIView):
    """GET /api/users/institution/me/data-export/ — 导出机构数据为 CSV/JSON。"""
    permission_classes = [IsAuthenticated, IsInstitutionAdmin, IsInstitutionActive]

    def get(self, request):
        inst = request.user.institution
        include_children = request.query_params.get('include_children') == 'true'
        inst_ids = _get_institution_ids_for_query(inst, include_children)
        export_type = request.query_params.get('type', 'students')

        if export_type == 'students':
            students = User.objects.filter(
                institution_id__in=inst_ids, institution_role='student'
            ).order_by('-date_joined')
            # 聚合模式下加校区列
            header = ['姓名', '邮箱', '校区', 'ELO', '加入日期'] if include_children else ['姓名', '邮箱', 'ELO', '加入日期']
            response = HttpResponse(content_type='text/csv; charset=utf-8')
            response['Content-Disposition'] = 'attachment; filename="students.csv"'
            response.write('﻿')  # BOM for Excel UTF-8 compatibility
            writer = csv.writer(response)
            writer.writerow(header)
            for s in students:
                row = [
                    s.nickname or s.username,
                    s.email,
                    s.elo_score,
                    s.date_joined.strftime('%Y-%m-%d') if s.date_joined else '',
                ]
                if include_children:
                    row.insert(2, s.institution.name if s.institution else '')
                writer.writerow(row)
            return response

        elif export_type == 'assignments':
            from quizzes.models import Assignment, AssignmentSubmission
            from django.db.models import Count, Avg
            assignments = Assignment.objects.filter(institution_id__in=inst_ids).order_by('-created_at')
            response = HttpResponse(content_type='text/csv; charset=utf-8')
            response['Content-Disposition'] = 'attachment; filename="assignments.csv"'
            response.write('﻿')
            writer = csv.writer(response)
            writer.writerow(['作业标题', '提交数', '平均分'])
            for a in assignments:
                subs = AssignmentSubmission.objects.filter(assignment=a)
                submitted = subs.count()
                avg_score = subs.aggregate(avg=Avg('score'))['avg']
                writer.writerow([
                    a.title,
                    submitted,
                    round(avg_score, 1) if avg_score else '',
                ])
            return response

        elif export_type == 'usage':
            return Response({
                'export_type': 'usage',
                'message': '使用数据导出暂不可用',
                'student_count': User.objects.filter(institution_id__in=inst_ids, institution_role='student').count(),
                'teacher_count': User.objects.filter(institution_id__in=inst_ids, institution_role='teacher').count(),
            })

        return Response({'error': f'不支持的导出类型: {export_type}'}, status=400)


class InstitutionStudentReportCardView(APIView):
    """GET /api/users/institution/me/students/<pk>/report-card/ — 教师查看学生报告。"""
    permission_classes = [IsAuthenticated, IsInstitutionAdmin, IsInstitutionActive]

    def get(self, request, pk):
        from users.views import _build_report_data
        inst = request.user.institution
        student = get_object_or_404(
            User, id=pk, institution=inst, institution_role='student',
        )
        return Response(_build_report_data(student))


# ═══════════════════════════════════════════════════════════════
# 子机构/校区管理
# ═══════════════════════════════════════════════════════════════

class InstitutionChildListView(APIView):
    """GET /api/users/institution/me/children/ — 列出子校区 + 创建。"""
    permission_classes = [IsAuthenticated, IsInstitutionAdmin, IsInstitutionActive]

    def get(self, request):
        inst = request.user.institution
        children = inst.children.all().order_by('-created_at')
        data = []
        for child in children:
            data.append({
                'id': child.id,
                'name': child.name,
                'slug': child.slug,
                'plan': child.get_effective_plan(),
                'inherit_plan': child.inherit_plan,
                'is_active': child.is_active,
                'is_plan_active': child.is_plan_active,
                'student_count': child.student_count,
                'staff_count': child.students.filter(
                    institution_role__in=('owner', 'teacher', 'registrar')
                ).count(),
                'business_type': child.business_type,
                'created_at': child.created_at.isoformat(),
            })
        return Response(data)

    def post(self, request):
        inst = request.user.institution
        if not inst.is_root():
            return Response({'error': '仅总校可创建子校区'}, status=403)
        if request.user.institution_role != 'owner':
            return Response({'error': '仅机构所有者可创建子校区'}, status=403)

        name = (request.data.get('name') or '').strip()
        if not name:
            return Response({'error': '校区名称不能为空'}, status=400)

        slug = (request.data.get('slug') or '').strip()
        if slug and Institution.objects.filter(slug=slug).exists():
            return Response({'error': f'标识 {slug} 已被使用'}, status=409)

        import secrets
        if not slug:
            slug = secrets.token_urlsafe(8).lower()

        inherit_plan = request.data.get('inherit_plan', True)
        if isinstance(inherit_plan, str):
            inherit_plan = inherit_plan.lower() != 'false'

        child = Institution.objects.create(
            parent=inst,
            name=name,
            slug=slug,
            contact_name=request.data.get('contact_name', inst.contact_name),
            contact_email=request.data.get('contact_email', inst.contact_email),
            contact_phone=request.data.get('contact_phone', inst.contact_phone),
            plan=inst.plan if inherit_plan else request.data.get('plan', 'free'),
            inherit_plan=inherit_plan,
            business_type=inst.business_type,
            created_by=request.user,
        )
        return Response({
            'id': child.id,
            'name': child.name,
            'slug': child.slug,
            'inherit_plan': child.inherit_plan,
            'plan': child.get_effective_plan(),
        }, status=201)


class InstitutionChildDetailView(APIView):
    """GET/PUT/DELETE /api/users/institution/me/children/<pk>/ — 单个子校区管理。"""
    permission_classes = [IsAuthenticated, IsInstitutionOwner, IsInstitutionActive]

    def get(self, request, pk):
        inst = request.user.institution
        child = get_object_or_404(Institution, id=pk, parent=inst)
        return Response({
            'id': child.id,
            'name': child.name,
            'slug': child.slug,
            'plan': child.get_effective_plan(),
            'own_plan': child.plan,
            'inherit_plan': child.inherit_plan,
            'is_active': child.is_active,
            'is_plan_active': child.is_plan_active,
            'student_count': child.student_count,
            'staff_count': child.students.filter(
                institution_role__in=('owner', 'teacher', 'registrar')
            ).count(),
            'contact_name': child.contact_name,
            'contact_email': child.contact_email,
            'contact_phone': child.contact_phone,
            'business_type': child.business_type,
            'created_at': child.created_at.isoformat(),
        })

    def put(self, request, pk):
        inst = request.user.institution
        child = get_object_or_404(Institution, id=pk, parent=inst)
        allowed = ['name', 'contact_name', 'contact_email', 'contact_phone', 'business_type', 'inherit_plan']
        for field in allowed:
            if field in request.data:
                setattr(child, field, request.data[field])
        # 取消继承时可设置独立 plan
        if not child.inherit_plan and 'plan' in request.data:
            child.plan = request.data['plan']
        child.save()
        return Response({
            'id': child.id,
            'name': child.name,
            'plan': child.get_effective_plan(),
            'own_plan': child.plan,
            'inherit_plan': child.inherit_plan,
        })

    def delete(self, request, pk):
        inst = request.user.institution
        child = get_object_or_404(Institution, id=pk, parent=inst)
        # 软删除：标记为 inactive 而非真删
        child.is_active = False
        child.save(update_fields=['is_active'])
        return Response({'status': 'deactivated'})


class InstitutionChildContextView(APIView):
    """POST /api/users/institution/me/children/<pk>/context/ — 切换校区上下文。"""
    permission_classes = [IsAuthenticated, IsInstitutionAdmin, IsInstitutionActive]

    def post(self, request, pk):
        inst = request.user.institution
        child = get_object_or_404(Institution, id=pk)
        # 必须是子校区或就是自身
        if child.id != inst.id and child.parent_id != inst.id:
            return Response({'error': '无权访问此校区'}, status=403)
        request.session['current_institution_id'] = child.id
        return Response({
            'current_institution_id': child.id,
            'name': child.name,
            'plan': child.get_effective_plan(),
        })


class InstitutionStudentHealthView(APIView):
    """GET /api/users/institution/me/student-health/ — 学员流失风险评估。
    基于活跃度、Memorix 复习率、连续签到、学习趋势四个维度综合评分。
    """
    permission_classes = [IsAuthenticated, IsInstitutionAdmin, IsInstitutionActive]

    def get(self, request):
        inst = request.user.institution
        include_children = request.query_params.get('include_children') == 'true'
        inst_ids = _get_institution_ids_for_query(inst, include_children)

        from quizzes.services.student_health import compute_student_health

        students = User.objects.filter(
            institution_id__in=inst_ids, institution_role='student'
        ).order_by('-last_active')

        results = []
        for s in students:
            h = compute_student_health(s)
            results.append({
                'student_id': s.id,
                'name': s.nickname or s.username,
                'email': s.email,
                'avatar_url': getattr(s, 'avatar_url', None),
                'date_joined': s.date_joined.isoformat() if s.date_joined else None,
                'last_active': s.last_active.isoformat() if s.last_active else None,
                **h,
            })

        results.sort(key=lambda x: x['score'])
        return Response({
            'results': results,
            'summary': {
                'total': len(results),
                'healthy': sum(1 for r in results if r['level'] == 'healthy'),
                'at_risk': sum(1 for r in results if r['level'] == 'at_risk'),
                'critical': sum(1 for r in results if r['level'] == 'critical'),
            },
        })
