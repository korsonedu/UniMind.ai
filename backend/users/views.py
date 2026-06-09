from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from django.utils.decorators import method_decorator
from django.contrib.auth import authenticate
from .serializers import (
    UserSerializer,
    RegisterSerializer,
    DailyPlanSerializer,
)
from .models import User, DailyPlan
from .permissions import IsPlatformAdmin, IsAdmin, is_platform_admin
from django.utils import timezone
from django.conf import settings
from django.utils.dateparse import parse_datetime
from core.rate_limit import rate_limit, _get_client_ip
from core.analytics import record_event
from core.utils import apply_institution_filter
from quizzes.utils import safe_int as _safe_int
import datetime
import logging
import re


logger = logging.getLogger(__name__)
security_logger = logging.getLogger('core.security')

from users.permissions import IsMember  # noqa: F401 — 向后兼容 re-export

class ActivateMembershipView(APIView):
    """用户输入邀请码激活会员。只查 PlanInviteCode 表。"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        from .models import PlanInviteCode

        code_str = request.data.get('code')
        if not code_str:
            return Response({'error': '请输入激活码'}, status=400)

        try:
            invite = PlanInviteCode.objects.get(code=code_str, is_active=True)
        except PlanInviteCode.DoesNotExist:
            return Response({'error': '无效或已被使用的激活码'}, status=400)

        if invite.is_exhausted:
            return Response({'error': '邀请码已达到使用次数上限'}, status=400)

        user = request.user
        plan = invite.plan
        duration_days = invite.duration_days
        code_type = invite.code_type

        from .services.membership import activate_membership
        activate_membership(user, plan, duration_days, source='code')
        # 不在这里消耗邀请码，由 InstitutionCreateView 统一消耗

        return Response({
            'status': 'ok',
            'message': '会员已成功激活',
            'code_type': code_type,
            'plan': plan,
            'duration_days': duration_days,
            'user': UserSerializer(user).data,
        })



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

        agreed_to_terms = self.request.data.get('agreed_to_terms', False)
        if not agreed_to_terms:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'error': '请先阅读并同意用户协议和隐私政策'})

        if not email or not code or not password:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'error': '邮箱、验证码、密码为必填项'})
        if len(password) < 8:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'error': '密码至少需要 8 位'})
        if not re.search(r'[A-Z]', password) or not re.search(r'[0-9]', password):
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'error': '密码需包含大写字母和数字'})

        if User.objects.filter(email=email, email_verified=True).exists():
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'error': '该邮箱已被注册'})

        from django.contrib.auth.hashers import check_password
        from django.core.cache import cache
        from datetime import timedelta

        cached = cache.get(f"verification_code:{email}")
        if not cached or not check_password(code, cached.get("code_hash", "")):
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'error': '验证码错误或已过期'})

        sent_at = parse_datetime(cached["sent_at"]) if cached.get("sent_at") else None
        if sent_at and timezone.now() > sent_at + timedelta(minutes=10):
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'error': '验证码已过期，请重新发送'})

        cache.delete(f"verification_code:{email}")

        username_base = email.split('@')[0]
        username = username_base
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{username_base}{counter}"
            counter += 1
        user = User.objects.create_user(username=username, email=email)
        if nickname:
            user.nickname = nickname
        user.email_verified = True
        user.agreed_to_terms = True
        user.agreed_to_terms_at = timezone.now()
        user.set_password(password)
        user.save()

class UpdateProfileView(generics.UpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]
    def get_object(self):
        return self.request.user
    
    def perform_update(self, serializer):
        serializer.save()

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
        if not is_platform and not inst:
            return Response({"results": []})
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

        # 2. ELO 战胜率（仅同机构用户排名）
        inst = getattr(user, 'institution', None)
        if inst:
            all_active_users = User.objects.filter(is_active=True, institution=inst).order_by('elo_score')
        else:
            all_active_users = User.objects.filter(is_active=True, institution__isnull=True).order_by('elo_score')
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
        now = timezone.now()
        active_window_seconds = max(getattr(settings, "ONLINE_USER_ACTIVE_WINDOW_SECONDS", 300), 10)
        threshold = now - datetime.timedelta(seconds=active_window_seconds)
        qs = User.objects.filter(is_active=True, last_active__gte=threshold)
        qs = apply_institution_filter(qs, self.request.user, self.request)
        return qs.order_by('-last_active', '-elo_score')


class HeartbeatView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        now = timezone.now()

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
        return Response({
            "status": "ok",
            "last_active": user.last_active,
            "current_task": user.current_task,
            "current_timer_end": user.current_timer_end,
        })

class LoginView(APIView):
    permission_classes = (AllowAny,)

    @method_decorator(rate_limit(key_prefix="login", max_requests=10, window_seconds=300))
    def post(self, request, *args, **kwargs):
        from core.models import SecurityAuditLog

        login_id = request.data.get('email') or request.data.get('username') or ''
        password = request.data.get('password')
        logger.debug("Login attempt id=%s", login_id)

        if not login_id or not password:
            return Response({'error': '请提供邮箱和密码'}, status=status.HTTP_400_BAD_REQUEST)

        # 查找用户（锁定检查需要拿到 user 对象）
        target_user = None
        if '@' in str(login_id):
            target_user = User.objects.filter(email__iexact=login_id).first()
        else:
            target_user = User.objects.filter(username=login_id).first()

        # 账号锁定检查
        if target_user and target_user.locked_until and target_user.locked_until > timezone.now():
            remaining = int((target_user.locked_until - timezone.now()).total_seconds() / 60) + 1
            SecurityAuditLog.objects.create(
                event_type='login_locked',
                user=target_user,
                ip_address=_get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')[:255],
                detail=f'账号锁定中，剩余 {remaining} 分钟',
            )
            security_logger.warning("login_locked user=%s ip=%s remaining=%dmin", target_user.username, _get_client_ip(request), remaining)
            return Response(
                {'error': f'账号已锁定，请 {remaining} 分钟后重试', 'code': 'account_locked'},
                status=status.HTTP_423_LOCKED,
            )

        # 执行认证
        user = None
        if target_user:
            user = authenticate(username=target_user.username, password=password)
        else:
            user = authenticate(username=login_id, password=password)

        client_ip = _get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')[:255]

        if user:
            # 登录成功：重置失败计数
            if user.failed_login_count > 0 or user.locked_until:
                user.failed_login_count = 0
                user.locked_until = None
                user.save(update_fields=['failed_login_count', 'locked_until'])
            Token.objects.filter(user=user).delete()
            token = Token.objects.create(user=user)
            user.last_login = timezone.now()
            user.save(update_fields=['last_login'])
            SecurityAuditLog.objects.create(
                event_type='login_success',
                user=user,
                ip_address=client_ip,
                user_agent=user_agent,
            )
            security_logger.info("login_success user=%s ip=%s", user.username, client_ip)
            record_event('user_login', user=user)
            
            # 异步预计算用户画像（用于自适应指令）
            try:
                from ai_assistant.tasks import precompute_user_profile
                precompute_user_profile.delay(user_id=user.id)
            except Exception:
                pass  # 异步任务失败不影响登录
            
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
            # 登录失败：累加计数，≥5次锁定15分钟
            if target_user:
                target_user.failed_login_count += 1
                if target_user.failed_login_count >= 5:
                    target_user.locked_until = timezone.now() + datetime.timedelta(minutes=15)
                    SecurityAuditLog.objects.create(
                        event_type='login_locked',
                        user=target_user,
                        ip_address=client_ip,
                        user_agent=user_agent,
                        detail=f'连续失败 {target_user.failed_login_count} 次，锁定 15 分钟',
                    )
                    security_logger.warning("account_locked user=%s ip=%s failures=%d", target_user.username, client_ip, target_user.failed_login_count)
                else:
                    SecurityAuditLog.objects.create(
                        event_type='login_failure',
                        user=target_user,
                        ip_address=client_ip,
                        user_agent=user_agent,
                        detail=f'第 {target_user.failed_login_count} 次失败',
                    )
                    security_logger.info("login_failure user=%s ip=%s attempt=%d", target_user.username, client_ip, target_user.failed_login_count)
                target_user.save(update_fields=['failed_login_count', 'locked_until'])
            logger.debug("Authentication failed id=%s", login_id)
            return Response({'error': '邮箱或密码错误'}, status=status.HTTP_401_UNAUTHORIZED)


class LogoutView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        if request.user.is_authenticated:
            Token.objects.filter(user=request.user).delete()
        response = Response({'status': 'ok'})
        response.delete_cookie('auth_token', samesite='Lax')
        return response


class UserDetailView(generics.RetrieveAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

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
        from rest_framework.authtoken.models import Token
        user = self.get_object()
        old_p = request.data.get('old_password', '')
        new_p = request.data.get('new_password', '')
        if not new_p or len(str(new_p)) < 8:
            return Response({'error': '新密码至少需要 8 位'}, status=400)
        if old_p and old_p == new_p:
            return Response({'error': '新密码不能与旧密码相同'}, status=400)
        if user.check_password(old_p):
            user.set_password(new_p)
            user.save(update_fields=['password'])
            # 删除所有旧 token，使泄露的 token 失效，创建新 token 保持登录
            Token.objects.filter(user=user).delete()
            new_token = Token.objects.create(user=user)
            resp = Response({'status': 'ok'})
            is_secure = getattr(settings, 'IS_PROD', False)
            resp.set_cookie(
                'auth_token', new_token.key,
                max_age=30 * 24 * 3600, httponly=True, secure=is_secure, samesite='Lax',
            )
            return resp
        return Response({'error': '旧密码错误'}, status=400)


class SendVerificationCodeView(APIView):
    """发送邮箱验证码。存入 Redis 缓存（10 分钟有效），不建用户。"""
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
        from django.contrib.auth.hashers import make_password
        from django.core.cache import cache

        code = generate_verification_code()
        cache.set(
            f"verification_code:{email}",
            {"code_hash": make_password(code), "sent_at": timezone.now().isoformat()},
            timeout=600,
        )

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


class DiagnosticGenerateView(APIView):
    """生成诊断测试题目。"""
    permission_classes = [IsMember]

    def post(self, request):
        user = request.user
        if user.has_completed_initial_assessment:
            return Response({'error': '诊断已完成', 'status': 'already_completed'}, status=400)

        inst = user.institution
        if not inst:
            return Response({'error': '请先加入机构'}, status=400)

        from quizzes.services.diagnostic_service import (
            generate_diagnostic_questions, DIAGNOSTIC_TIME_LIMIT_SECONDS,
        )
        questions = generate_diagnostic_questions(inst)

        if not questions:
            return Response({'error': '暂无可用知识点，请联系管理员'}, status=400)

        record_event('diagnostic_start', user=user)

        return Response({
            'questions': questions,
            'time_limit_seconds': DIAGNOSTIC_TIME_LIMIT_SECONDS,
        })


class DiagnosticSubmitView(APIView):
    """提交诊断答案，获取结果和学习计划。"""
    permission_classes = [IsMember]

    def post(self, request):
        from django.db import transaction

        answers = request.data.get('answers', [])
        if not answers:
            return Response({'error': '请提交答案'}, status=400)

        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=request.user.pk)
            if user.has_completed_initial_assessment:
                return Response({'error': '诊断已完成'}, status=400)

            from quizzes.services.diagnostic_service import (
                grade_diagnostic_answers, initialize_memorix_from_diagnostic, build_study_plan,
            )

            results, kp_scores = grade_diagnostic_answers(user, answers)
            initialize_memorix_from_diagnostic(user, kp_scores)
            study_plan = build_study_plan(kp_scores)

            # 标记诊断完成
            user.has_completed_initial_assessment = True
            user.save(update_fields=['has_completed_initial_assessment'])
        record_event('diagnostic_complete', user=user, properties={
            'total_score': sum(1 for r in results if r['is_correct']),
            'total_questions': len(results),
        })

        total_correct = sum(1 for r in results if r['is_correct'])
        return Response({
            'total_score': total_correct,
            'total_questions': len(results),
            'results': results,
            'study_plan': study_plan,
        })


# ──────────────────────────────────────────────
# 平台数据分析 Dashboard（仅超管）
# ──────────────────────────────────────────────

class AnalyticsDashboardView(APIView):
    """平台数据分析 Dashboard，仅超管可见。"""
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def get(self, request):
        from core.models import DailyPlatformStats, AnalyticsEvent, NPSSurvey
        from django.db.models import Sum, Count

        days = _safe_int(request.query_params.get('days'), 30)
        stats = list(DailyPlatformStats.objects.order_by('-date')[:days])

        # ── 汇总 ──
        today = stats[0] if stats else None
        summary = {
            'total_users': today.total_users if today else 0,
            'total_institutions': today.total_institutions if today else 0,
            'dau': today.dau if today else 0,
            'mau': today.mau if today else 0,
            'day7_retention': round(today.day7_retention, 4) if today else 0,
        }

        # ── 趋势 ──
        trends = [{
            'date': str(s.date),
            'dau': s.dau,
            'new_users': s.new_users,
            'new_institutions': s.new_institutions,
            'quiz_attempts': s.quiz_attempts,
            'quiz_correct_rate': round(s.quiz_correct_rate, 4),
            'ai_chat_sessions': s.ai_chat_sessions,
            'course_views': s.course_views,
            'day1_retention': round(s.day1_retention, 4),
        } for s in reversed(stats)]

        # ── 功能使用分布（近 N 天事件计数）──
        from_date = stats[-1].date if stats else timezone.now().date()
        event_counts = (
            AnalyticsEvent.objects
            .filter(created_at__date__gte=from_date)
            .values('event_type')
            .annotate(count=Count('id'))
            .order_by('-count')
        )
        feature_breakdown = {e['event_type']: e['count'] for e in event_counts}

        # ── 机构 Top 10（按学生数）──
        from users.models import Institution
        institution_top = []
        for inst in Institution.objects.order_by('-created_at')[:10]:
            student_count = inst.members.filter(institution_role='student').count()
            institution_top.append({
                'id': inst.id,
                'name': inst.name,
                'student_count': student_count,
                'created_at': str(inst.created_at.date()),
            })
        institution_top.sort(key=lambda x: x['student_count'], reverse=True)

        # ── NPS 汇总 ──
        nps_data = self._get_nps_summary()

        return Response({
            'summary': summary,
            'trends': trends,
            'feature_breakdown': feature_breakdown,
            'institution_top': institution_top[:10],
            'nps': nps_data,
        })

    def _get_nps_summary(self):
        from core.models import NPSSurvey
        from django.db.models import Count

        total = NPSSurvey.objects.count()
        if total == 0:
            return {'score': 0, 'total': 0, 'distribution': {}, 'recent_feedback': []}

        distribution = (
            NPSSurvey.objects
            .values('score')
            .annotate(count=Count('id'))
            .order_by('score')
        )
        dist = {d['score']: d['count'] for d in distribution}

        promoters = sum(dist.get(s, 0) for s in [9, 10])
        detractors = sum(dist.get(s, 0) for s in range(0, 7))
        nps_score = round((promoters - detractors) / total * 100)

        recent = list(
            NPSSurvey.objects
            .select_related('user')
            .filter(feedback__gt='')
            .order_by('-created_at')[:5]
            .values('user__username', 'score', 'feedback', 'created_at')
        )

        return {
            'score': nps_score,
            'total': total,
            'distribution': {
                'promoters': promoters,
                'passives': total - promoters - detractors,
                'detractors': detractors,
            },
            'recent_feedback': [{
                'username': r['user__username'],
                'score': r['score'],
                'feedback': r['feedback'],
                'created_at': str(r['created_at']),
            } for r in recent],
        }


class AnalyticsExportView(APIView):
    """导出平台分析数据为 CSV，仅超管可见。

    GET /api/users/admin/analytics/export/?type=trends|events|nps&days=30
    """
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def get(self, request):
        import csv
        from django.http import HttpResponse
        from core.models import DailyPlatformStats, AnalyticsEvent, NPSSurvey

        export_type = request.query_params.get('type', 'trends')
        days = _safe_int(request.query_params.get('days'), 90)

        if export_type == 'trends':
            return self._export_trends(days)
        elif export_type == 'events':
            return self._export_events(days)
        elif export_type == 'nps':
            return self._export_nps()
        return Response({'error': '无效的导出类型，支持: trends, events, nps'}, status=400)

    def _export_trends(self, days):
        import csv
        from django.http import HttpResponse
        from core.models import DailyPlatformStats

        stats = DailyPlatformStats.objects.order_by('-date')[:days]
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = 'attachment; filename="platform_trends.csv"'
        writer = csv.writer(response)
        writer.writerow([
            '日期', '总用户', '新增用户', 'DAU', 'WAU', 'MAU',
            '总机构', '新增机构', '活跃机构',
            '答题次数', '答题正确率', '诊断完成',
            'AI对话', 'AI调用总量',
            '课程浏览', '课程完成', 'PDF导出',
            '次日留存', '7日留存', '30日留存',
        ])
        for s in stats:
            writer.writerow([
                s.date, s.total_users, s.new_users, s.dau, s.wau, s.mau,
                s.total_institutions, s.new_institutions, s.active_institutions,
                s.quiz_attempts, f'{s.quiz_correct_rate:.4f}', s.diagnostic_completions,
                s.ai_chat_sessions, s.ai_calls_total,
                s.course_views, s.course_completions, s.pdf_exports,
                f'{s.day1_retention:.4f}', f'{s.day7_retention:.4f}', f'{s.day30_retention:.4f}',
            ])
        return response

    def _export_events(self, days):
        import csv
        from django.http import HttpResponse
        from core.models import AnalyticsEvent
        from django.utils import timezone

        since = timezone.now() - timezone.timedelta(days=days)
        events = AnalyticsEvent.objects.filter(created_at__gte=since).order_by('-created_at')[:10000]
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = 'attachment; filename="analytics_events.csv"'
        writer = csv.writer(response)
        writer.writerow(['时间', '事件类型', '用户ID', '用户名', '机构ID', '机构名', '属性'])
        for e in events:
            writer.writerow([
                e.created_at, e.get_event_type_display(),
                e.user_id, getattr(e.user, 'username', ''),
                e.institution_id, getattr(e.institution, 'name', ''),
                str(e.properties),
            ])
        return response

    def _export_nps(self):
        import csv
        from django.http import HttpResponse
        from core.models import NPSSurvey

        surveys = NPSSurvey.objects.select_related('user').order_by('-created_at')
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = 'attachment; filename="nps_surveys.csv"'
        writer = csv.writer(response)
        writer.writerow(['时间', '用户', '评分', '分类', '反馈', '来源'])
        for s in surveys:
            writer.writerow([
                s.created_at, s.user.username, s.score,
                s.category, s.feedback, s.source,
            ])
        return response


# ──────────────────────────────────────────────
# NPS 问卷
# ──────────────────────────────────────────────

class NPSSubmitView(APIView):
    """提交 NPS 问卷响应。"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from core.models import NPSSurvey
        score = request.data.get('score')
        feedback = request.data.get('feedback', '')

        if score is None or not (0 <= int(score) <= 10):
            return Response({'error': '评分必须为 0-10'}, status=400)

        NPSSurvey.objects.create(
            user=request.user,
            score=int(score),
            feedback=feedback,
            source=request.data.get('source', 'auto'),
        )
        return Response({'status': 'ok'})


class NPSStatusView(APIView):
    """检查当前用户是否需要填写 NPS。"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from core.analytics import should_show_nps
        return Response({'should_show': should_show_nps(request.user)})


# ──────────────────────────────────────────────
# 账户注销（个保法第47条）
# ──────────────────────────────────────────────

class AccountDeleteView(APIView):
    """注销当前用户账户。

    流程：
    1. 验证密码（或邮箱验证码）
    2. 匿名化个人数据（保留统计聚合）
    3. 删除关联的学习数据
    4. 停用账户
    5. 记录安全审计日志

    POST /api/users/me/delete/
    Body: { "password": "xxx" }  或  { "verification_code": "123456" }
    """
    permission_classes = [IsAuthenticated]

    @method_decorator(rate_limit(key_prefix="account_delete", max_requests=3, window_seconds=3600))
    def post(self, request):
        user = request.user
        password = request.data.get('password', '')
        verification_code = request.data.get('verification_code', '')

        # 验证身份
        if not password and not verification_code:
            return Response({'error': '请提供密码或验证码以确认操作'}, status=400)

        if password:
            if not user.has_usable_password() or not user.check_password(password):
                return Response({'error': '密码错误'}, status=400)
        elif verification_code:
            from django.contrib.auth.hashers import check_password as check_pw
            from django.core.cache import cache
            cached = cache.get(f"verification_code:{user.email}")
            if not cached or not check_pw(verification_code, cached.get("code_hash", "")):
                return Response({'error': '验证码错误或已过期'}, status=400)
            cache.delete(f"verification_code:{user.email}")

        from django.db import transaction

        with transaction.atomic():
            # 1. 匿名化个人数据
            user.username = f'deleted_{user.id}'
            user.email = ''
            user.nickname = ''
            user.bio = ''
            user.avatar_seed = ''
            user.verification_code = ''
            user.set_unusable_password()
            user.is_active = False
            user.email_verified = False
            user.is_member = False
            user.membership_tier = 'free'
            user.membership_expires_at = None

            # 清空敏感字段
            user.current_task = ''
            user.today_completed_tasks = []
            user.dashboard_config = {}

            user.save()

            # 2. 删除 Token（使所有登录态失效）
            Token.objects.filter(user=user).delete()

            # 3. 匿名化关联数据
            # AI 对话历史
            from ai_assistant.models import ChatMessage, AgentMemory, StudyPlan, CardInteraction
            ChatMessage.objects.filter(user=user).delete()
            AgentMemory.objects.filter(user=user).delete()
            StudyPlan.objects.filter(user=user).delete()
            CardInteraction.objects.filter(user=user).delete()

            # 学习数据
            from quizzes.models import (
                UserQuestionStatus, UserExam, ReviewLog,
                KnowledgeState, MemorixProfile, KnowledgeAnnotation,
            )
            UserQuestionStatus.objects.filter(user=user).delete()
            UserExam.objects.filter(user=user).delete()
            ReviewLog.objects.filter(user=user).delete()
            KnowledgeState.objects.filter(user=user).delete()
            MemorixProfile.objects.filter(user=user).delete()
            KnowledgeAnnotation.objects.filter(user=user).delete()

            # 其他关联
            from notifications.models import Notification
            Notification.objects.filter(recipient=user).delete()

            from study_room.models import StudySession, StudyMessage
            StudySession.objects.filter(user=user).delete()
            StudyMessage.objects.filter(user=user).delete()

            from faq_system.models import Question
            Question.objects.filter(user=user).delete()

            # 4. 脱离机构
            user.institution = None
            user.institution_role = 'student'
            user.save(update_fields=['institution', 'institution_role'])

            # 5. 安全审计日志
            from core.models import SecurityAuditLog
            SecurityAuditLog.objects.create(
                user=None,  # user 已匿名化
                action='account_deletion',
                ip_address=_get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
                detail=f'Account {user.id} deleted and anonymized',
            )

        security_logger.info(f'Account deleted: user_id={user.id}')

        return Response({'status': 'ok', 'message': '账户已注销，所有个人数据已删除'})


# ──────────────────────────────────────────────
# 数据导出（个保法第45条 - 数据可携带权）
# ──────────────────────────────────────────────

class DataExportView(APIView):
    """导出当前用户的所有个人数据为 JSON。

    GET /api/users/me/data-export/
    """
    permission_classes = [IsAuthenticated]

    @method_decorator(rate_limit(key_prefix="data_export", max_requests=5, window_seconds=3600))
    def get(self, request):
        import json
        from django.http import HttpResponse
        user = request.user

        data = {
            'export_info': {
                'user_id': user.id,
                'username': user.username,
                'exported_at': timezone.now().isoformat(),
                'version': '1.0',
            },
            'profile': {
                'username': user.username,
                'nickname': user.nickname,
                'email': user.email,
                'bio': user.bio,
                'role': user.role,
                'elo_score': user.elo_score,
                'is_member': user.is_member,
                'membership_tier': user.membership_tier,
                'membership_expires_at': str(user.membership_expires_at) if user.membership_expires_at else None,
                'has_completed_initial_assessment': user.has_completed_initial_assessment,
                'date_joined': user.date_joined.isoformat(),
                'last_login': str(user.last_login) if user.last_login else None,
            },
            'daily_plans': list(
                DailyPlan.objects.filter(user=user).values('content', 'is_completed', 'completed_at', 'created_at')
            ),
            'quiz_history': [],
            'ai_conversations': [],
            'study_plans': [],
            'notifications': [],
        }

        # 答题记录
        from quizzes.models import UserQuestionStatus, UserExam
        uqs = UserQuestionStatus.objects.filter(user=user).select_related('question')
        data['quiz_history'] = [
            {
                'question_id': s.question_id,
                'status': s.status,
                'correct_count': s.correct_count,
                'wrong_count': s.wrong_count,
                'last_review': str(s.last_review) if s.last_review else None,
                'stability': s.stability,
            }
            for s in uqs[:5000]  # 上限防止导出过大
        ]

        # 考试记录
        exams = UserExam.objects.filter(user=user)
        data['exam_history'] = [
            {
                'exam_id': e.id,
                'score': e.score,
                'total_score': e.total_score,
                'submitted_at': str(e.submitted_at) if e.submitted_at else None,
            }
            for e in exams[:1000]
        ]

        # AI 对话（最近 200 条）
        from ai_assistant.models import ChatMessage
        messages = ChatMessage.objects.filter(user=user).order_by('-created_at')[:200]
        data['ai_conversations'] = [
            {
                'role': m.role,
                'content': m.content[:500],  # 截断防止过大
                'bot_type': m.bot_type,
                'created_at': m.created_at.isoformat(),
            }
            for m in messages
        ]

        # 学习计划
        from ai_assistant.models import StudyPlan
        plans = StudyPlan.objects.filter(user=user)
        data['study_plans'] = [
            {
                'title': p.title,
                'content': p.content,
                'status': p.status,
                'created_at': p.created_at.isoformat(),
            }
            for p in plans
        ]

        # 通知
        from notifications.models import Notification
        notifs = Notification.objects.filter(recipient=user).order_by('-created_at')[:100]
        data['notifications'] = [
            {
                'title': n.title,
                'message': n.message,
                'is_read': n.is_read,
                'created_at': n.created_at.isoformat(),
            }
            for n in notifs
        ]

        response = HttpResponse(
            json.dumps(data, ensure_ascii=False, indent=2, default=str),
            content_type='application/json; charset=utf-8',
        )
        response['Content-Disposition'] = f'attachment; filename="unimind_data_export_{user.id}.json"'
        return response


# ──────────────────────────────────────────────
# 用户反馈
# ──────────────────────────────────────────────

class FeedbackSubmitView(APIView):
    """提交用户反馈。

    POST /api/users/feedback/
    Body: { "category": "bug|feature|other", "content": "...", "contact": "optional" }
    """
    permission_classes = [IsAuthenticated]

    @method_decorator(rate_limit(key_prefix="feedback", max_requests=10, window_seconds=3600))
    def post(self, request):
        from core.models import Feedback
        category = request.data.get('category', 'other')
        content = request.data.get('content', '').strip()
        contact = request.data.get('contact', '').strip()

        if not content:
            return Response({'error': '请输入反馈内容'}, status=400)
        if len(content) > 2000:
            return Response({'error': '反馈内容不能超过 2000 字'}, status=400)

        Feedback.objects.create(
            user=request.user,
            category=category,
            content=content,
            contact=contact,
            page_url=request.data.get('page_url', ''),
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
        )
        return Response({'status': 'ok', 'message': '感谢您的反馈！'})
