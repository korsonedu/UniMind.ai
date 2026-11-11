from django.db.models import Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny

from core.utils import get_content_institution
from .models import Institution, PlanInviteCode, get_plan_features
from .permissions import IsPlatformAdmin, IsInstitutionOwner, IsInstitutionActive, is_platform_admin
from .serializers_institution import InstitutionSerializer


class RetiredInstitutionView(APIView):
    """已退出的机构/激活/API 销售入口，不读取或修改历史数据。"""
    authentication_classes = []
    permission_classes = [AllowAny]

    def _retired(self, request, *args, **kwargs):
        return Response({'detail': '该入口已停用，请在科晟平台使用个人账号。'}, status=410)

    get = post = put = patch = delete = _retired


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
