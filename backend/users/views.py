from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from django.utils.decorators import method_decorator
from .serializers import (
    UserSerializer,
    RegisterSerializer,
    SystemConfigSerializer,
    DailyPlanSerializer,
    ActivationCodeSerializer,
)
from .models import User, SystemConfig, DailyPlan, ActivationCode
from .permissions import IsPlatformAdmin, IsAdmin, is_platform_admin
from django.utils import timezone
from django.conf import settings
from django.utils.dateparse import parse_datetime
from core.rate_limit import rate_limit
import datetime
import logging
import re


logger = logging.getLogger(__name__)

class IsMember(permissions.BasePermission):
    """
    允许会员或管理员访问。
    """
    message = "您需要先成为学员（激活会员）才能使用此功能。"

    def has_permission(self, request, view):
        from users.permissions import is_platform_admin, is_institution_admin
        return bool(
            request.user and
            request.user.is_authenticated and
            (request.user.is_member or is_platform_admin(request.user) or is_institution_admin(request.user))
        )

class ActivateMembershipView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        code_str = request.data.get('code')
        if not code_str:
            return Response({'error': '请输入激活码'}, status=400)
        
        try:
            code_obj = ActivationCode.objects.get(code=code_str, is_used=False)
        except ActivationCode.DoesNotExist:
            return Response({'error': '无效或已被使用的激活码'}, status=400)
        
        # 激活会员
        user = request.user
        user.is_member = True
        user.save()
        
        # 标记激活码已使用
        code_obj.is_used = True
        code_obj.used_by = user
        code_obj.used_at = timezone.now()
        code_obj.save()
        
        return Response({'status': 'ok', 'message': '会员已成功激活', 'user': UserSerializer(user).data})

class ActivationCodeListView(generics.ListCreateAPIView):
    queryset = ActivationCode.objects.all().order_by('-created_at')
    serializer_class = ActivationCodeSerializer
    permission_classes = [IsAdmin]

    def perform_create(self, serializer):
        # 可以在这里增加逻辑自动生成 code，或者由前端传入
        serializer.save()

class ActivationCodeDetailView(generics.DestroyAPIView):
    queryset = ActivationCode.objects.all()
    serializer_class = ActivationCodeSerializer
    permission_classes = [IsAdmin]

    def perform_destroy(self, instance):
        # 如果已被使用，需要收回用户的会员权限
        if instance.is_used and instance.used_by:
            user = instance.used_by
            user.is_member = False
            user.save()
        instance.delete()

class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = (AllowAny,)
    serializer_class = RegisterSerializer

    @method_decorator(rate_limit(key_prefix="register", max_requests=5, window_seconds=3600))
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        email = str(self.request.data.get('email', '')).strip().lower()
        code = str(self.request.data.get('code', '')).strip()
        nickname = str(self.request.data.get('nickname', '')).strip()
        password = self.request.data.get('password', '')

        if not email or not code or not password:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'error': '邮箱、验证码、密码为必填项'})
        if len(password) < 6:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'error': '密码至少需要 6 位'})

        if User.objects.filter(email=email, email_verified=True).exists():
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'error': '该邮箱已被注册'})

        from datetime import timedelta
        existing = User.objects.filter(email=email, email_verified=False).order_by('-date_joined').first()
        from django.contrib.auth.hashers import check_password
        if not existing or not check_password(code, existing.verification_code):
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'error': '验证码错误或已过期'})
        if existing.verification_code_sent_at:
            expires = existing.verification_code_sent_at + timedelta(minutes=10)
            if timezone.now() > expires:
                from rest_framework.exceptions import ValidationError
                raise ValidationError({'error': '验证码已过期，请重新发送'})

        user = existing
        if nickname:
            user.nickname = nickname
        user.email_verified = True
        user.verification_code = ''
        user.set_password(password)
        user.save()

        # 新用户初始积分
        from users.models import EloPointsLedger
        EloPointsLedger.objects.create(
            user=user, amount=50, balance_after=50,
            reason='admin_adjust', description='新用户初始积分',
        )

class UpdateProfileView(generics.UpdateAPIView):
    serializer_class = UserSerializer
    def get_object(self):
        return self.request.user
    
    def perform_update(self, serializer):
        user = serializer.save()
        # 移除了对 avatar_url 的手动赋值，因为它现在是动态属性
        user.save()

from django.db.models import Q
from django.db.models.functions import TruncDate

class DailyPlanListView(generics.ListCreateAPIView):
    serializer_class = DailyPlanSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Return incomplete plans OR plans completed today (Beijing Time)
        now = timezone.now().astimezone(datetime.timezone(datetime.timedelta(hours=8)))
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        return DailyPlan.objects.filter(
            Q(user=self.request.user) & 
            (Q(is_completed=False) | Q(is_completed=True, completed_at__gte=today_start))
        ).order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

class DailyPlanDetailView(generics.UpdateAPIView, generics.DestroyAPIView):
    serializer_class = DailyPlanSerializer
    permission_classes = [permissions.IsAuthenticated]
    def get_queryset(self):
        return DailyPlan.objects.filter(user=self.request.user)

    def perform_update(self, serializer):
        is_completed = self.request.data.get('is_completed')
        if is_completed is not None:
            # If marking as completed, set timestamp
            if is_completed:
                serializer.save(completed_at=timezone.now())
            else:
                serializer.save(completed_at=None)
        else:
            serializer.save()

from django.db.models import Sum, Count, Q, Avg
from quizzes.models import UserQuestionStatus, KnowledgePoint, QuizAttempt
from courses.models import VideoProgress, Course
from study_room.models import ChatMessage

class BIAnalyticsView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        user = request.user
        inst = getattr(user, 'institution', None)
        is_platform = is_platform_admin(user)

        # 机构管理员只看本机构数据
        user_filter = {} if is_platform else {'user__institution': inst}
        qs_filter = {} if is_platform else {'institution': inst}

        # 1. 知识点错题热力图 (取前10)
        kp_errors = UserQuestionStatus.objects.values(
            'question__knowledge_point__name'
        ).annotate(
            total_errors=Sum('wrong_count')
        ).filter(
            question__knowledge_point__name__isnull=False,
            **user_filter,
        ).order_by('-total_errors')[:10]

        # 2. 课程完播率统计
        course_stats = VideoProgress.objects.values(
            'course__title'
        ).annotate(
            total_views=Count('user', distinct=True),
            completions=Count('id', filter=Q(is_finished=True))
        ).filter(
            **user_filter,
        ).order_by('-total_views')[:10]

        # 3. 活跃用户概览
        if is_platform:
            total_users = User.objects.count()
            member_users = User.objects.filter(is_member=True).count()
        else:
            total_users = User.objects.filter(institution=inst).count()
            member_users = User.objects.filter(is_member=True, institution=inst).count()

        return Response({
            'kp_errors': list(kp_errors),
            'course_stats': list(course_stats),
            'user_overview': {
                'total': total_users,
                'members': member_users,
                'member_rate': round(member_users / total_users * 100, 1) if total_users > 0 else 0
            }
        })

class WeeklyCognitiveReportView(APIView):
    permission_classes = [IsMember]

    def get(self, request):
        user = request.user
        now = timezone.now()
        
        # 计算上周的起止时间 (周一 00:00:00 到 周日 23:59:59)
        # weekday(): 0 是周一, 6 是周日
        current_weekday = now.weekday()
        # 本周一的凌晨
        start_of_this_week = (now - datetime.timedelta(days=current_weekday)).replace(hour=0, minute=0, second=0, microsecond=0)
        # 上周一的凌晨
        start_of_last_week = start_of_this_week - datetime.timedelta(days=7)
        # 上周日的深夜
        end_of_last_week = start_of_this_week - datetime.timedelta(seconds=1)

        # 1. 认知资产转化 (基于上周数据)
        # 统计上周复习过且稳定性提升到长期的题目 (稳定性 > 21天视为初步进入永久资产)
        last_week_qs = UserQuestionStatus.objects.filter(user=user, last_review__range=(start_of_last_week, end_of_last_week))
        total_attempted = last_week_qs.count()
        permanent_assets = last_week_qs.filter(stability__gte=21).count()
        conversion_rate = round(permanent_assets / total_attempted * 100, 1) if total_attempted > 0 else 0

        # 2. ELO 战胜率
        all_active_users = User.objects.filter(is_active=True).order_by('elo_score')
        total_active = all_active_users.count()
        below_me = all_active_users.filter(elo_score__lt=user.elo_score).count()
        percentile = round(below_me / total_active * 100, 1) if total_active > 0 else 0

        # 3. 核心统计
        week_reviews = last_week_qs.aggregate(total_reps=Sum('reps'))['total_reps'] or 0
        
        # 4. 行为指标（用于周趋势图）
        last_week_attempts = QuizAttempt.objects.filter(
            user=user,
            created_at__range=(start_of_last_week, end_of_last_week)
        )
        attempts_by_day = (
            last_week_attempts
            .annotate(day=TruncDate('created_at'))
            .values('day')
            .annotate(avg_score=Avg('score'), question_count=Count('id'))
        )
        attempts_day_map = {}
        for row in attempts_by_day:
            day = row.get('day')
            if not day:
                continue
            key = day.isoformat()
            attempts_day_map[key] = {
                'accuracy': round((row.get('avg_score') or 0) * 100, 1),
                'question_count': int(row.get('question_count') or 0),
            }

        focus_messages = ChatMessage.objects.filter(
            user=user,
            timestamp__range=(start_of_last_week, end_of_last_week)
        ).values('timestamp', 'content')
        focus_pattern = re.compile(r'专注\s*(\d+)\s*分钟')
        focus_day_map = {}
        for msg in focus_messages:
            ts = msg.get('timestamp')
            if not ts:
                continue
            local_day = timezone.localtime(ts).date().isoformat()
            text = str(msg.get('content') or '')
            parsed = sum(int(v) for v in focus_pattern.findall(text))
            if parsed <= 0:
                continue
            focus_day_map[local_day] = focus_day_map.get(local_day, 0) + parsed

        lesson_by_day = (
            VideoProgress.objects.filter(
            user=user,
            updated_at__range=(start_of_last_week, end_of_last_week)
            )
            .annotate(day=TruncDate('updated_at'))
            .values('day')
            .annotate(total_seconds=Sum('last_position'))
        )
        lesson_day_map = {}
        for row in lesson_by_day:
            day = row.get('day')
            if not day:
                continue
            key = day.isoformat()
            lesson_day_map[key] = round(float(row.get('total_seconds') or 0) / 60, 1)

        daily_series = []
        total_questions = 0
        weighted_accuracy_sum = 0.0
        total_focus_minutes = 0
        total_lesson_minutes = 0.0

        for offset in range(7):
            day_date = (start_of_last_week + datetime.timedelta(days=offset)).date()
            day_key = day_date.isoformat()
            attempt_info = attempts_day_map.get(day_key, {})
            question_count = int(attempt_info.get('question_count', 0))
            accuracy = float(attempt_info.get('accuracy', 0))
            focus_minutes = int(focus_day_map.get(day_key, 0))
            lesson_minutes = float(lesson_day_map.get(day_key, 0))

            total_questions += question_count
            weighted_accuracy_sum += (accuracy / 100.0) * question_count
            total_focus_minutes += focus_minutes
            total_lesson_minutes += lesson_minutes

            daily_series.append({
                'date': day_key,
                'label': day_date.strftime('%m-%d'),
                'weekday': day_date.strftime('%a'),
                'accuracy': round(accuracy, 1),
                'question_count': question_count,
                'focus_minutes': focus_minutes,
                'lesson_minutes': round(lesson_minutes, 1),
            })

        weekly_question_count = total_questions
        weekly_accuracy = round((weighted_accuracy_sum / total_questions) * 100, 1) if total_questions > 0 else 0
        weekly_focus_minutes = total_focus_minutes
        weekly_lesson_minutes = round(total_lesson_minutes, 1)
        
        return Response({
            'user_nickname': user.nickname or user.username,
            'conversion_rate': conversion_rate,
            'permanent_count': permanent_assets,
            'elo_percentile': percentile,
            'week_reviews': week_reviews,
            'current_elo': user.elo_score,
            'report_date': f"{start_of_last_week.strftime('%Y.%m.%d')} - {end_of_last_week.strftime('%m.%d')}",
            'week_label': f"{start_of_last_week.isocalendar()[0]}-W{start_of_last_week.isocalendar()[1]}",
            'weekly_accuracy': weekly_accuracy,
            'weekly_question_count': weekly_question_count,
            'weekly_focus_minutes': weekly_focus_minutes,
            'weekly_lesson_minutes': weekly_lesson_minutes,
            'daily_series': daily_series,
        })

class OnlineUserListView(generics.ListAPIView):
    serializer_class = UserSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        from users.permissions import is_platform_admin
        from django.db.models import Q
        now = timezone.now()
        active_window_seconds = max(getattr(settings, "ONLINE_USER_ACTIVE_WINDOW_SECONDS", 300), 10)
        threshold = now - datetime.timedelta(seconds=active_window_seconds)
        qs = User.objects.filter(is_active=True, last_active__gte=threshold)
        user = self.request.user
        if not is_platform_admin(user):
            inst = getattr(user, 'institution', None)
            if inst:
                qs = qs.filter(Q(institution=inst) | Q(institution__isnull=True))
            else:
                qs = qs.filter(institution__isnull=True)
        return qs.order_by('-last_active', '-elo_score')


class HeartbeatView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        from django.db.models import F
        user = request.user
        now = timezone.now()
        today = now.date()

        # 每日首次心跳发积分（F() 更新避免 select_for_update）
        daily_bonus = 0
        last_date = user.last_active.date() if user.last_active else None
        if last_date != today:
            from users.points import _get_multiplier
            daily_bonus = max(1, int(5 * _get_multiplier(user.institution_id)))
            from users.models import EloPointsLedger, User as UserModel
            UserModel.objects.filter(id=user.id).update(
                elo_points=F('elo_points') + daily_bonus,
            )
            user.refresh_from_db(fields=['elo_points'])
            EloPointsLedger.objects.create(
                user_id=user.id, amount=daily_bonus,
                balance_after=user.elo_points,
                reason='admin_adjust', description='每日登录',
            )

        user.last_active = now
        update_fields = ["last_active"]

        if "current_task" in request.data:
            task = request.data.get("current_task")
            if task is None:
                normalized_task = None
            else:
                normalized_task = str(task).strip() or None
                if normalized_task and len(normalized_task) > 200:
                    return Response({"error": "current_task cannot exceed 200 characters."}, status=400)
            user.current_task = normalized_task
            update_fields.append("current_task")

        if "current_timer_end" in request.data:
            raw_timer_end = request.data.get("current_timer_end")
            if raw_timer_end in (None, ""):
                normalized_timer_end = None
            elif isinstance(raw_timer_end, str):
                normalized_timer_end = parse_datetime(raw_timer_end)
                if normalized_timer_end is None:
                    return Response({"error": "current_timer_end must be a valid ISO datetime."}, status=400)
                if timezone.is_naive(normalized_timer_end):
                    normalized_timer_end = timezone.make_aware(
                        normalized_timer_end,
                        timezone.get_current_timezone(),
                    )
            else:
                return Response({"error": "current_timer_end must be a string or null."}, status=400)

            user.current_timer_end = normalized_timer_end
            update_fields.append("current_timer_end")

        user.save(update_fields=update_fields)
        resp = {
            "status": "ok",
            "last_active": user.last_active,
            "current_task": user.current_task,
            "current_timer_end": user.current_timer_end,
            "daily_bonus": daily_bonus,
        }
        if daily_bonus > 0:
            resp['elo_points'] = user.elo_points
        return Response(resp)

class SystemConfigView(generics.RetrieveUpdateAPIView):
    queryset = SystemConfig.objects.all()
    serializer_class = SystemConfigSerializer
    def get_object(self):
        config, created = SystemConfig.objects.get_or_create(id=1)
        return config
    def get_permissions(self):
        if self.request.method in permissions.SAFE_METHODS: return [permissions.AllowAny()]
        return [IsAdmin()]

class ResetEloView(generics.UpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request, *args, **kwargs):
        user = self.request.user
        if user.elo_reset_count >= 1:
            return Response({'error': 'You can only reset ELO once.'}, status=400)
        user.elo_score = 1000
        user.has_completed_initial_assessment = False
        user.elo_reset_count += 1
        from users.points import reset_elo_points
        reset_elo_points(user.id)
        user.save()
        return Response(UserSerializer(user).data)

from django.contrib.auth import authenticate
from rest_framework.views import APIView

class LoginView(APIView):
    permission_classes = (AllowAny,)

    @method_decorator(rate_limit(key_prefix="login", max_requests=10, window_seconds=300))
    def post(self, request, *args, **kwargs):
        from django.contrib.auth import authenticate

        login_id = request.data.get('email') or request.data.get('username') or ''
        password = request.data.get('password')
        logger.debug("Login attempt id=%s", login_id)

        if not login_id or not password:
            return Response({'error': '请提供邮箱和密码'}, status=status.HTTP_400_BAD_REQUEST)

        user = None
        if '@' in str(login_id):
            try:
                u = User.objects.get(email__iexact=login_id)
                user = authenticate(username=u.username, password=password)
            except User.DoesNotExist:
                pass
        else:
            user = authenticate(username=login_id, password=password)

        if user:
            Token.objects.filter(user=user).delete()
            token = Token.objects.create(user=user)
            user.last_login = timezone.now()
            user.save(update_fields=['last_login'])
            response = Response({
                'token': token.key,
                'user': UserSerializer(user).data
            })
            is_secure = getattr(settings, 'IS_PROD', False)
            response.set_cookie(
                'auth_token', token.key,
                httponly=True,
                secure=is_secure,
                samesite='Lax',
                max_age=30 * 24 * 3600,
            )
            return response
        else:
            logger.debug("Authentication failed id=%s", login_id)
            return Response({'error': '邮箱或密码错误'}, status=status.HTTP_401_UNAUTHORIZED)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        response = Response({'status': 'ok'})
        response.delete_cookie('auth_token', samesite='Lax')
        return response


class UserDetailView(generics.RetrieveAPIView):

    serializer_class = UserSerializer

    def get_object(self):

        user = self.request.user

        user.last_active = timezone.now()

        user.save(update_fields=['last_active'])

        return user

class UpdateEmailView(generics.UpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user

    def patch(self, request, *args, **kwargs):
        user = self.get_object()
        email = str(request.data.get('email', '')).strip().lower()
        if not email or '@' not in email:
            return Response({'error': '请提供有效的邮箱地址'}, status=400)
        if User.objects.filter(email=email, email_verified=True).exclude(id=user.id).exists():
            return Response({'error': '该邮箱已被注册'}, status=409)
        user.email = email
        user.email_verified = False
        user.save(update_fields=['email', 'email_verified'])
        return Response(UserSerializer(user).data)

class UpdatePasswordView(generics.UpdateAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user

    def patch(self, request, *args, **kwargs):
        user = self.get_object()
        old_p = request.data.get('old_password', '')
        new_p = request.data.get('new_password', '')
        if not new_p or len(str(new_p)) < 6:
            return Response({'error': '新密码至少需要 6 位'}, status=400)
        if user.check_password(old_p):
            user.set_password(new_p)
            user.save(update_fields=['password'])
            return Response({'status': 'ok'})
        return Response({'error': '旧密码错误'}, status=400)


class SendVerificationCodeView(APIView):
    """发送邮箱验证码。注册场景：自动创建临时未验证用户。"""
    permission_classes = [AllowAny]

    @method_decorator(rate_limit(key_prefix="send_code", max_requests=3, window_seconds=600))
    def post(self, request):
        email = str(request.data.get('email', '')).strip().lower()
        if not email:
            return Response({'error': '请提供邮箱地址'}, status=400)

        existing_verified = User.objects.filter(email=email, email_verified=True).first()
        if existing_verified:
            if request.user.is_authenticated and existing_verified == request.user:
                pass
            else:
                return Response({'error': '该邮箱已被注册'}, status=400)

        from core.email_service import generate_verification_code, send_verification_email
        from datetime import timedelta

        code = generate_verification_code()

        if request.user.is_authenticated:
            # 已登录用户只重发验证码到当前邮箱，不允许通过此接口改邮箱
            user = request.user
            email = user.email
        else:
            user = User.objects.filter(email=email, email_verified=False).order_by('-date_joined').first()
            if not user:
                username_base = email.split('@')[0]
                username = username_base
                counter = 1
                while User.objects.filter(username=username).exists():
                    username = f"{username_base}{counter}"
                    counter += 1
                user = User.objects.create_user(
                    username=username,
                    email=email,
                )
                user.set_unusable_password()

        from django.contrib.auth.hashers import make_password
        user.verification_code = make_password(code)
        user.verification_code_sent_at = timezone.now()
        user.save(update_fields=['email', 'verification_code', 'verification_code_sent_at'])

        ok = send_verification_email(email, code)
        if not ok:
            return Response({'error': '验证码发送失败，请稍后重试'}, status=500)

        return Response({'status': 'ok', 'message': f'验证码已发送至 {email}，10 分钟内有效'})


class MyKnowledgeMasteryView(APIView):
    """返回当前用户所有知识点的掌握度映射 {kp_id: mastery_level}，基于 Memorix Weibull retrievability"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.utils import timezone
        from quizzes.models import UserQuestionStatus
        from quizzes.memorix.service import predict_retrievability as weibull_r

        def _r_to_level(r: float) -> str:
            if r >= 0.8:
                return 'mastered'
            if r >= 0.6:
                return 'stable'
            if r >= 0.4:
                return 'learning'
            if r > 0:
                return 'weak'
            return 'unknown'

        now = timezone.now()
        qs = UserQuestionStatus.objects.filter(
            user=request.user, stability__gt=0, last_review__isnull=False,
        ).select_related('question__knowledge_point')

        kp_scores: dict[int, list[float]] = {}
        for s in qs:
            kp = s.question.knowledge_point
            if kp is None:
                continue
            elapsed = max(0.0, (now - s.last_review).total_seconds() / 86400.0)
            r = weibull_r(stability=s.stability, elapsed_days=elapsed, user_id=request.user.id)
            kp_scores.setdefault(kp.id, []).append(r)

        data = {}
        for kp_id, scores in kp_scores.items():
            avg_r = sum(scores) / len(scores)
            data[str(kp_id)] = _r_to_level(avg_r)
        return Response(data)
