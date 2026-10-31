import csv
import logging
from django.core.cache import cache
from django.db import transaction
from django.db.models import Q, Sum
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
from core.utils import get_content_institution
from .models import Institution, PlanInviteCode, get_plan_features, PLAN_FEATURES, JoinRequest

User = get_user_model()
from .permissions import IsPlatformAdmin, IsInstitutionAdmin, IsInstitutionOwner, IsInstitutionActive, IsInstitutionMember, IsInstitutionTeacher, is_platform_admin, is_institution_admin
from .serializers_institution import (
    InstitutionSerializer, InstitutionStudentSerializer, CreateStudentSerializer,
    InstitutionFeatureSerializer, JoinRequestSerializer,
)

class RetiredInstitutionView(APIView):
    """已退出的机构/激活/API 销售入口，不读取或修改历史数据。"""
    permission_classes = [AllowAny]

    def _retired(self, request, *args, **kwargs):
        return Response({'detail': '该入口已停用，请在科晟平台使用个人账号。'}, status=410)

    get = post = put = patch = delete = _retired


def _get_institution_ids_for_query(inst) -> list[int]:
    """返回查询范围：仅当前机构。"""
    return [inst.pk] if inst else []


# ── Super Admin: Historical Institution Queries ──

class InstitutionListView(APIView):
    http_method_names = ['get', 'head', 'options']
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


class InstitutionDetailView(APIView):
    http_method_names = ['get', 'head', 'options']
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def get(self, request, pk):
        inst = get_object_or_404(Institution, pk=pk)
        return Response(InstitutionSerializer(inst).data)


# ── Institution Admin: Student Management ──

class InstitutionStudentListView(APIView):
    permission_classes = [IsAuthenticated, IsInstitutionAdmin, IsInstitutionActive]

    def get(self, request):
        inst = request.user.institution
        inst_ids = _get_institution_ids_for_query(inst)
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
            'aggregated': False,
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
        serializer = CreateStudentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.create_user(
            username=serializer.validated_data['username'],
            email=serializer.validated_data['email'],
            password=serializer.validated_data['password'],
            nickname=serializer.validated_data.get('nickname', ''),
            institution=inst,
            institution_role='student',
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
        from quizzes.services.learning_stats import build_learning_stats
        stats = build_learning_stats(student, institution=request.user.institution)
        qs_all = UserQuestionStatus.objects.filter(user=student)
        total_answered = stats['total_attempts']
        total_wrong = stats['wrong_attempts']
        total_correct = stats['lifetime_correct_count']
        correct_rate = stats['lifetime_accuracy'] or 0
        mastered_count = stats['mastered_question_count']
        total_questions = stats['attempted_questions']
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
        inst_ids = _get_institution_ids_for_query(inst)
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
        from users.learning import usage_info
        from users.feature_access import learning_features
        user = request.user
        features = learning_features(user)
        inst_data = None
        personal_usage = usage_info(user)
        usage = {'ai_call_total': personal_usage, 'ai_question': personal_usage,
                 'used': personal_usage['used'], 'limit': personal_usage['limit']}
        return Response({'is_platform_admin': is_platform_admin(user),
                         'institution': inst_data, 'features': features, 'usage': usage})

# ── Institution Dashboard ──

class InstitutionDashboardView(APIView):
    """机构管理员仪表盘"""
    permission_classes = [IsAuthenticated, IsInstitutionAdmin, IsInstitutionActive]

    def get(self, request):
        user = request.user
        inst = user.institution
        inst_ids = _get_institution_ids_for_query(inst)

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
                'staff_count': User.objects.filter(institution_id__in=inst_ids, institution_role__in=('owner', 'teacher')).count(),
            },
            'stats': {
                'weekly_active_students': weekly_active,
                'ai_usage': {'used': quota_info.get('ai_question', {}).get('used', 0), 'limit': quota_info.get('ai_question', {}).get('limit', 0)},
                'quota': quota_info,
                'top_weak_points': top_weak,
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
                    'staff_count': i.students.filter(institution_role__in=('owner', 'teacher')).count(),
                }
                for i in qs
            ],
            'plan_matrix': {p: get_plan_features(p) for p in ['free', 'starter', 'growth', 'enterprise']},
        })


# ── Institution Member Management (owner + teacher) ──

class InstitutionMemberListView(APIView):
    http_method_names = ['get', 'head', 'options']
    """机构管理员（owner / teacher）列出所有成员（教师 + 学员）"""
    permission_classes = [IsAuthenticated, IsInstitutionAdmin, IsInstitutionActive]

    def get(self, request):
        inst = request.user.institution
        inst_ids = _get_institution_ids_for_query(inst)
        qs = User.objects.filter(institution_id__in=inst_ids).exclude(institution_role='owner').order_by('institution_role', '-date_joined')
        serializer = InstitutionStudentSerializer(qs, many=True)
        return Response(serializer.data)


class InstitutionJoinRequestListView(APIView):
    http_method_names = ['get', 'head', 'options']
    """GET 加入申请列表（按状态筛选）"""
    permission_classes = [IsAuthenticated, IsInstitutionTeacher, IsInstitutionActive]

    def get(self, request):
        inst = request.user.institution
        status_filter = request.query_params.get('status', 'pending')
        qs = JoinRequest.objects.filter(
            institution=inst, status=status_filter,
        ).select_related('user', 'invite').order_by('-created_at')
        return Response(JoinRequestSerializer(qs, many=True).data)


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


class InstitutionAuditLogView(APIView):
    """机构操作审计日志（机构管理员可见）。

    GET /api/users/institution/me/audit-logs/?page=1
    """
    permission_classes = [IsAuthenticated, IsInstitutionTeacher, IsInstitutionActive]

    def get(self, request):
        inst = request.user.institution
        if not inst:
            return Response({'error': '未加入机构'}, status=400)

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
    permission_classes = [IsAuthenticated, IsInstitutionTeacher, IsInstitutionActive]

    def get(self, request):
        inst = request.user.institution
        if not inst:
            return Response({'error': '未加入机构'}, status=400)

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


class InstitutionBusinessDashboardView(APIView):
    """GET /api/users/institution/me/business-dashboard/ — 机构商业指标仪表盘。"""
    permission_classes = [IsAuthenticated, IsInstitutionOwner, IsInstitutionActive]

    def get(self, request):
        inst = get_content_institution()
        if inst is None:
            return Response(
                {'error': '当前内容范围为全局，无机构业务指标。'},
                status=status.HTTP_400_BAD_REQUEST,
            )
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

        from courses.models import Course
        total_courses = Course.objects.filter(institution=inst).count()

        retention_rate = 0.0
        if student_count > 0:
            retention_rate = round(active_this_month / student_count * 100, 1)

        # 营收指标：从 Order 表聚合
        from payments.models import Order
        paid_orders = Order.objects.filter(institution=inst, status='paid')
        total_revenue = paid_orders.aggregate(total=Sum('amount_cents'))['total'] or 0
        revenue_this_month = paid_orders.filter(paid_at__gte=month_start).aggregate(
            total=Sum('amount_cents')
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
        inst_ids = _get_institution_ids_for_query(inst)
        export_type = request.query_params.get('type', 'students')

        if export_type == 'students':
            students = User.objects.filter(
                institution_id__in=inst_ids, institution_role='student'
            ).order_by('-date_joined')
            header = ['姓名', '邮箱', 'ELO', '加入日期']
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
                writer.writerow(row)
            return response

        elif export_type == 'usage':
            return Response({
                'export_type': 'usage',
                'message': '使用数据导出暂不可用',
                'student_count': User.objects.filter(institution_id__in=inst_ids, institution_role='student').count(),
                'teacher_count': User.objects.filter(institution_id__in=inst_ids, institution_role='teacher').count(),
            })

        return Response({'error': f'不支持的导出类型: {export_type}'}, status=400)


class InstitutionStudentHealthView(APIView):
    """GET /api/users/institution/me/student-health/ — 学员流失风险评估。
    基于活跃度、Memorix 复习率、连续签到、学习趋势四个维度综合评分。
    """
    permission_classes = [IsAuthenticated, IsInstitutionAdmin, IsInstitutionActive]

    def get(self, request):
        inst = request.user.institution
        inst_ids = _get_institution_ids_for_query(inst)

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
