from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions
from .models import EloPointsLedger
from .serializers_points import PointsBalanceSerializer, PointsLedgerSerializer


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
