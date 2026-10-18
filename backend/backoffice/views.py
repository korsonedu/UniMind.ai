import json

from django.conf import settings
from django.db import IntegrityError, transaction
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import SecurityAuditLog
from .authentication import DirectusAdminAuthentication
from .common import content_institution, paginate
from . import courses, people, quizzes, uploads, commerce, teaching


def meta(request, data):
    return {'operator': {'id': request.user.pk, 'name': request.user.nickname or request.user.username},
            'content_configured': bool(settings.UNIMIND_CONTENT_INSTITUTION_ID),
            'uploads_enabled': bool(settings.OSS_BUCKET_NAME and settings.OSS_ACCESS_KEY_ID and settings.OSS_ACCESS_KEY_SECRET and settings.OSS_ENDPOINT)}


def audit(request, data):
    queryset = SecurityAuditLog.objects.filter(event_type='admin_action', detail__startswith='{"channel": "directus"').select_related('user')
    return paginate(queryset, data, lambda item: {
        'id': item.pk, 'operator': str(item.user) if item.user else '已删除账号',
        'created_at': item.created_at, 'detail': json.loads(item.detail), 'request_id': item.request_id})


READS = {'meta': meta, 'options': courses.options, 'courses.list': courses.list_courses,
         'modules.list': courses.list_modules, 'students.list': people.list_students,
         'students.detail': people.student_detail, 'products.list': people.list_products, 'audit.list': audit,
         'knowledge.list': quizzes.list_catalog, 'questions.list': quizzes.list_questions,
         'questions.detail': quizzes.question_detail}
WRITES = {'courses.save': courses.save_course, 'courses.delete': courses.delete_course,
          'courses.assign': courses.assign_courses, 'modules.save': courses.save_module,
          'modules.delete': courses.delete_module, 'grants.revoke': people.revoke_grant,
          'students.access.save': people.save_access,
          'students.status.save': people.save_student_status,
          'knowledge.save': quizzes.save_catalog, 'knowledge.delete': quizzes.delete_catalog,
          'questions.save': quizzes.save_question, 'questions.delete': quizzes.delete_question,
          'questions.assign': quizzes.assign_questions,
          'uploads.start': uploads.start, 'uploads.complete': uploads.complete, 'uploads.cancel': uploads.cancel}

READS.update(commerce.READS)
READS.update(teaching.READS)
WRITES.update(commerce.WRITES)
WRITES.update(teaching.WRITES)


class OperationView(APIView):
    authentication_classes = [DirectusAdminAuthentication]
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]
    throttle_classes = []

    def post(self, request, operation):
        if len(request.body) > 256 * 1024:
            raise serializers.ValidationError('管理请求过大。')
        data = request.data
        if not isinstance(data, dict):
            raise serializers.ValidationError('请求须为 JSON 对象。')
        if operation in READS:
            return Response(READS[operation](request, data))
        if operation not in WRITES:
            raise NotFound('未开放的管理操作。')
        request_id = serializers.UUIDField().run_validation(data.get('request_id'))
        if operation.startswith(('courses.', 'modules.', 'uploads.', 'knowledge.', 'questions.')):
            content_institution(required=True)
        try:
            with transaction.atomic():
                result = WRITES[operation](request, data)
                if not getattr(request, 'backoffice_no_change', False):
                    SecurityAuditLog.objects.create(
                        event_type='admin_action', user=request.user, request_id=str(request_id),
                        detail=json.dumps({'channel': 'directus', 'operator': request.auth, 'operation': operation,
                                           'target': result.get('id'), 'updated': result.get('updated'),
                                           'enabled_features': result.get('enabled_features'),
                                           'is_course_student': result.get('is_course_student')}, ensure_ascii=False))
        except Exception as exc:
            cleanup = getattr(request, 'backoffice_rollback', None)
            if cleanup:
                cleanup()
            if isinstance(exc, IntegrityError):
                raise serializers.ValidationError('数据已被其他操作更新或存在重复记录，请刷新后核对。') from exc
            raise
        return Response(result)
