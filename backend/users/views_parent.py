import secrets
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .models import ParentStudentLink
from .serializers import ParentStudentLinkSerializer


class ParentLinkRequestView(APIView):
    """POST /api/users/parent/link-request/ — 家长发起绑定请求，返回验证码给学生。"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        student_email = request.data.get('student_email', '').strip()
        if not student_email:
            return Response({'error': '请输入学生邮箱'}, status=400)

        from django.contrib.auth import get_user_model
        User = get_user_model()
        try:
            student = User.objects.get(email=student_email, institution_role='student')
        except User.DoesNotExist:
            return Response({'error': '未找到该学生'}, status=404)

        if ParentStudentLink.objects.filter(parent=request.user, student=student, verified=True).exists():
            return Response({'error': '已绑定该学生'}, status=400)

        # 清理该家长对该学生的旧未验证链接（24h 过期）
        ParentStudentLink.objects.filter(
            parent=request.user, student=student, verified=False,
            created_at__lt=timezone.now() - timezone.timedelta(hours=24),
        ).delete()

        code = secrets.token_hex(3).upper()[:6]
        link = ParentStudentLink.objects.create(
            parent=request.user,
            student=student,
            verification_code=code,
        )

        return Response({
            'message': f'验证码已生成（24h内有效）：{code}，请让学生在其设置页面输入此验证码完成绑定',
            'verification_code': code,
            'student_name': student.nickname or student.username,
        }, status=201)


class ParentLinkVerifyView(APIView):
    """POST /api/users/parent/link-verify/ — 学生输入验证码确认家长绑定。"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        code = request.data.get('code', '').strip().upper()
        if not code:
            return Response({'error': '请输入验证码'}, status=400)

        cutoff = timezone.now() - timezone.timedelta(hours=24)
        link = ParentStudentLink.objects.filter(
            student=request.user, verified=False,
            verification_code=code,
            created_at__gte=cutoff,
        ).first()

        if not link:
            return Response({'error': '验证码无效或已过期（24h内有效）'}, status=400)

        link.verified = True
        link.verified_at = timezone.now()
        link.save(update_fields=['verified', 'verified_at'])

        return Response({'message': f'已成功绑定家长：{link.parent.nickname or link.parent.username}',
                        'parent_name': link.parent.nickname or link.parent.username})


class ParentChildListView(APIView):
    """GET /api/users/parent/children/ — 已绑定孩子列表。"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        links = ParentStudentLink.objects.filter(
            parent=request.user, verified=True
        ).select_related('student')
        return Response(ParentStudentLinkSerializer(links, many=True).data)


class ParentChildProgressView(APIView):
    """GET /api/users/parent/children/<child_id>/progress/ — 孩子学习进度。"""
    permission_classes = [IsAuthenticated]

    def get(self, request, child_id):
        link = get_object_or_404(ParentStudentLink, parent=request.user, student_id=child_id, verified=True)
        student = link.student

        from quizzes.services.student_health import compute_student_health
        from quizzes.models import ReviewLog, UserKnowledgeState
        from users.models import DailyCheckIn

        health = compute_student_health(student)

        # 本周复习次数
        week_ago = timezone.now() - timezone.timedelta(days=7)
        weekly_reviews = ReviewLog.objects.filter(user=student, review_time__gte=week_ago).count()

        # 掌握知识点数
        kp_count = UserKnowledgeState.objects.filter(
            user=student, mastery_score__gte=80
        ).count()

        # 连续签到
        latest_checkin = DailyCheckIn.objects.filter(user=student).order_by('-date').first()
        streak = latest_checkin.streak if latest_checkin else 0

        return Response({
            'student_id': student.id,
            'student_name': student.nickname or student.username,
            'health': health,
            'weekly_reviews': weekly_reviews,
            'mastered_kp_count': kp_count,
            'streak': streak,
        })


class ParentChildWeeklyReportView(APIView):
    """GET /api/users/parent/children/<child_id>/weekly-report/ — 学习周报。"""
    permission_classes = [IsAuthenticated]

    def get(self, request, child_id):
        link = get_object_or_404(ParentStudentLink, parent=request.user, student_id=child_id, verified=True)
        student = link.student

        from quizzes.services.weekly_report import build_weekly_report_data
        data = build_weekly_report_data(student)
        return Response(data)


class MyParentLinksView(APIView):
    """GET /api/users/me/parent-links/ — 当前用户的家长关联（学生看家长，家长看孩子）。"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if user.role == 'parent' or user.institution_role == 'parent':
            links = ParentStudentLink.objects.filter(parent=user).select_related('student', 'parent')
        else:
            links = ParentStudentLink.objects.filter(student=user).select_related('student', 'parent')
        return Response(ParentStudentLinkSerializer(links, many=True).data)
