"""Read existing request state without reserving quota or starting execution."""
from django.utils import timezone
from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from users.learning import AI_RESERVATION_TTL, CHAT_RESERVATION_TTL
from users.models import AIUsageReservation
from .models import chat_receipt_deleted
from .services.dsh_runtime import quota_write_lock
from .services.ulr_history import require_receipt_sources


class ChatRequestStatusView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, request_id):
        with quota_write_lock():
            reservation = AIUsageReservation.objects.filter(user=request.user, request_id=request_id).first()
            deleted = reservation is not None and chat_receipt_deleted(reservation)
        payload = {'request_id': str(request_id), 'status': 'unknown'}
        if reservation:
            ttl = CHAT_RESERVATION_TTL if reservation.conversation_id else AI_RESERVATION_TTL
            if reservation.status == 'succeeded' and not deleted:
                try:
                    require_receipt_sources(request.user, reservation.response)
                except (PermissionDenied, ValidationError) as exc:
                    payload.update(status='failed', response={'done': True, 'is_error': True, 'full_content': str(exc.detail)})
                else:
                    payload.update(status='completed', response=reservation.response)
            elif reservation.status == 'released' and reservation.response.get('is_error'):
                payload.update(status='failed', response={
                    key: value for key, value in reservation.response.items() if key != 'rsi_sidecar'})
            elif reservation.status == 'pending' and reservation.updated_at >= timezone.now() - ttl:
                payload['status'] = 'pending'
        response = Response(payload)
        response['Cache-Control'] = 'no-store'
        return response
