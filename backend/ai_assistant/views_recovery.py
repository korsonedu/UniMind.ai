"""Read existing request state without reserving quota or starting execution."""
from datetime import timedelta

from django.utils import timezone
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from users.models import AIUsageReservation


class ChatRequestStatusView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, request_id):
        reservation = AIUsageReservation.objects.filter(user=request.user, request_id=request_id).first()
        payload = {'request_id': str(request_id), 'status': 'unknown'}
        if reservation:
            if reservation.status == 'succeeded' and not reservation.response.get('deleted'):
                payload.update(status='completed', response=reservation.response)
            elif reservation.status == 'pending' and reservation.updated_at >= timezone.now() - timedelta(hours=1):
                payload['status'] = 'pending'
        response = Response(payload)
        response['Cache-Control'] = 'no-store'
        return response
