from rest_framework import serializers
from .models import EloPointsLedger


class PointsBalanceSerializer(serializers.Serializer):
    elo_score = serializers.IntegerField()
    elo_points = serializers.IntegerField()


class PointsLedgerSerializer(serializers.ModelSerializer):
    class Meta:
        model = EloPointsLedger
        fields = ('id', 'amount', 'balance_after', 'reason', 'description',
                  'reference_type', 'reference_id', 'created_at')
