from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions, status
from django.shortcuts import get_object_or_404
from .models import EloPointsLedger, InstitutionRewardConfig, User
from .permissions import IsInstitutionAdmin, IsInstitutionOwner
from .serializers_points import PointsBalanceSerializer, PointsLedgerSerializer
from .points import award_elo_points


class PointsBalanceView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response(PointsBalanceSerializer({
            'elo_score': user.elo_score,
            'elo_points': user.elo_points,
        }).data)


class PointsLedgerView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        page = int(request.query_params.get('page', 1))
        page_size = 20
        start = (page - 1) * page_size
        qs = EloPointsLedger.objects.filter(user=user).order_by('-created_at')
        total = qs.count()
        items = qs[start:start + page_size]
        return Response({
            'results': PointsLedgerSerializer(items, many=True).data,
            'total': total,
            'page': page,
            'page_size': page_size,
        })


# ── 机构管理员：积分配置 ──

class InstitutionRewardConfigView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsInstitutionAdmin]

    def get(self, request):
        inst = request.user.institution
        if inst is None:
            return Response({'error': '未绑定机构'}, status=400)
        cfg, _ = InstitutionRewardConfig.objects.get_or_create(institution=inst)
        return Response({
            'is_enabled': cfg.is_enabled,
            'points_multiplier': cfg.points_multiplier,
            'monthly_bonus_points': cfg.monthly_bonus_points,
            'daily_login_bonus': cfg.daily_login_bonus,
            'updated_at': cfg.updated_at,
        })

    def patch(self, request):
        inst = request.user.institution
        if inst is None:
            return Response({'error': '未绑定机构'}, status=400)
        cfg, _ = InstitutionRewardConfig.objects.get_or_create(institution=inst)
        for field in ('is_enabled', 'points_multiplier', 'monthly_bonus_points', 'daily_login_bonus'):
            if field in request.data:
                setattr(cfg, field, request.data[field])
        cfg.save()
        return Response({'status': 'ok', 'updated_at': cfg.updated_at})


# ── 机构管理员：手动发放积分 ──

class InstitutionAwardPointsView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsInstitutionAdmin]

    def post(self, request):
        inst = request.user.institution
        if inst is None:
            return Response({'error': '未绑定机构'}, status=400)

        student_id = request.data.get('student_id')
        amount = int(request.data.get('amount', 0))
        reason_text = str(request.data.get('reason', '')).strip() or '管理员手动发放'

        if amount <= 0:
            return Response({'error': 'amount 必须为正数'}, status=400)

        student = get_object_or_404(User, id=student_id, institution=inst)
        awarded = award_elo_points(student.id, amount, 'admin_adjust', description=reason_text)
        return Response({'status': 'ok', 'awarded': awarded})
