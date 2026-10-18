import hashlib
import hmac
import json
import time
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from core.models import SecurityAuditLog
from users.learning import (confirm_ai_call, is_course_student, reserve_ai_call,
                            set_weekly_quota_config, usage_info)
from users.models import AIUsageReservation, Institution
from users.permissions import get_user_capabilities
from .views import OperationView


class SinglePlatformAdminSmoke(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admins = [User.objects.create_superuser(username=f'operator-{i}', email=f'operator-{i}@preview.invalid') for i in (1, 2)]
        self.actors = [str(uuid4()), str(uuid4())]
        self.student = User.objects.create_user(username='single-platform-student')
        self.secret = 'isolated-single-platform-smoke-secret'
        config = override_settings(UNIMIND_DIRECTUS_ADMIN_MAP=dict(zip(self.actors, [user.pk for user in self.admins])),
            UNIMIND_ADMIN_BRIDGE_SECRET=self.secret, UNIMIND_CONTENT_INSTITUTION_ID='global',
            CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
        config.enable()
        self.addCleanup(config.disable)

    def operation(self, name, data, actor=0):
        path = f'/api/backoffice/operations/{name}/'
        raw = json.dumps(data)
        timestamp, nonce = str(int(time.time())), str(uuid4())
        canonical = '\n'.join(['v1', 'POST', path, self.actors[actor], timestamp, nonce,
                              hashlib.sha256(raw.encode()).hexdigest()])
        signature = hmac.new(self.secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()
        request = APIRequestFactory().post(path, data=raw, content_type='application/json',
            HTTP_X_UNIMIND_OPERATOR=self.actors[actor], HTTP_X_UNIMIND_TIMESTAMP=timestamp,
            HTTP_X_UNIMIND_NONCE=nonce, HTTP_X_UNIMIND_SIGNATURE=signature)
        return OperationView.as_view()(request, operation=name)

    def test_manual_status_weekly_config_and_distinct_operator_audit(self):
        self.assertFalse(is_course_student(self.student))
        self.assertNotIn('course.video', get_user_capabilities(self.student))
        response = self.operation('students.status.save', {'id': self.student.pk,
            'is_course_student': True, 'request_id': str(uuid4())})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(is_course_student(self.student))
        response = self.operation('quota.save', {'experience_calls': 2, 'course_calls': 5,
                                               'request_id': str(uuid4())}, actor=1)
        self.assertEqual(response.status_code, 200)
        detail = self.operation('students.detail', {'id': self.student.pk})
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data['ai_usage']['limit'], 5)
        self.assertTrue(detail.data['is_course_student'])
        self.assertIn('course.video', detail.data['enabled_features'])
        self.assertEqual(set(SecurityAuditLog.objects.values_list('user_id', flat=True)), {user.pk for user in self.admins})

    def test_stale_reservation_released_and_late_attempt_cannot_charge(self):
        set_weekly_quota_config(experience_calls=1, course_calls=3)
        request_id = uuid4()
        old = reserve_ai_call(self.student, request_id, fingerprint='same question')
        self.assertEqual(usage_info(self.student)['remaining'], 0)
        AIUsageReservation.objects.filter(pk=old.pk).update(updated_at=timezone.now() - timedelta(hours=2))
        self.assertEqual(usage_info(self.student)['remaining'], 1)
        current = reserve_ai_call(self.student, request_id, fingerprint='same question')
        self.assertNotEqual(current.attempt_id, old.attempt_id)
        confirm_ai_call(old)
        self.assertEqual(usage_info(self.student)['used'], 0)
        confirm_ai_call(current, {'full_content': 'Complete answer'})
        confirm_ai_call(old)
        self.assertEqual(usage_info(self.student)['used'], 1)

    def test_course_community_writes_use_platform_scope_for_new_accounts(self):
        from faq_system.views import QuestionListCreateView
        from study_room.views import ChatMessageListView
        scope = Institution.objects.create(name='Isolated course scope', slug='isolated-course-scope')
        request = SimpleNamespace(user=self.student, FILES={}, data={})
        with override_settings(UNIMIND_CONTENT_INSTITUTION_ID=str(scope.pk)):
            for view_class in (QuestionListCreateView, ChatMessageListView):
                view, serializer = view_class(), Mock()
                view.request = request
                view.perform_create(serializer)
                self.assertEqual(serializer.save.call_args.kwargs['institution'], scope)
        self.student.refresh_from_db()
        self.assertIsNone(self.student.institution_id)
