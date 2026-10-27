"""Focused cohort configuration, rights and context smoke."""
from datetime import timedelta
from types import SimpleNamespace
import hashlib
import hmac
import json
import time
from uuid import uuid4

import pytest
from django.utils import timezone
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_two_current_cohorts_have_independent_context(user):
    from users.models import StudentCohort, CourseStudentStatus
    from users.learning import is_course_student, cohort_info
    from ai_assistant.services.dsh_service import build_context
    today = timezone.localdate()
    cohorts = [StudentCohort.objects.create(name=f'synthetic batch {year}', target_year=year,
               starts_on=today, ends_on=today + timedelta(days=10), is_active=True) for year in (2027, 2028)]
    other = type(user).objects.create_user(username='other-cohort-student')
    for student, cohort in zip((user, other), cohorts):
        CourseStudentStatus.objects.create(user=student, is_course_student=True, cohort=cohort)
        assert is_course_student(student)
        assert cohort_info(student)['target_year'] == cohort.target_year
    first = build_context(user, '学习统计')
    second = build_context(other, '学习统计')
    assert first['student']['cohort']['target_year'] == 2027
    assert second['student']['cohort']['target_year'] == 2028
    cohorts[0].target_year = 2029
    cohorts[0].save()
    updated = build_context(user, '学习统计')
    assert updated['permissions_version'] != first['permissions_version']
    assert updated['available_tools'] == first['available_tools']


@pytest.mark.django_db
def test_expiry_does_not_fall_back_or_reset_usage(auth_client, user):
    from users.models import StudentCohort, CourseStudentStatus, WeeklyAIUsage
    from users.learning import is_course_student, week_bounds, set_weekly_quota_config
    today = timezone.localdate()
    from courses.models import Course
    course = Course.objects.create(title='private cohort course')
    cohort = StudentCohort.objects.create(name='expired synthetic', target_year=2027,
        starts_on=today-timedelta(days=2), ends_on=today-timedelta(days=1), is_active=True)
    CourseStudentStatus.objects.create(user=user, is_course_student=True, cohort=cohort)
    user.is_member = True
    user.save(update_fields=['is_member'])
    set_weekly_quota_config(experience_calls=20, course_calls=200)
    usage = WeeklyAIUsage.objects.create(user=user, week=week_bounds()[0], ai_calls=7)
    assert not is_course_student(user)
    assert auth_client.get(f'/api/courses/{course.pk}/').status_code == 404
    response = auth_client.get('/api/users/learning/access/')
    assert response.status_code == 200
    assert response.json()['cohort']['state'] == 'expired'
    assert response.json()['ai_usage']['used'] == 7
    assert response.json()['ai_usage']['limit'] == 20
    usage.refresh_from_db()
    assert usage.ai_calls == 7
    cohort.ends_on = today
    cohort.save()
    assert is_course_student(user)  # Inclusive final service day.
    assert auth_client.get(f'/api/courses/{course.pk}/').status_code == 200
    cohort.is_active = False
    cohort.save()
    assert not is_course_student(user)
    assert auth_client.get(f'/api/courses/{course.pk}/').status_code == 404


@pytest.mark.django_db
def test_management_assigns_batches_and_preserves_omitted_choice(user, admin_user, settings):
    from backoffice import people
    from users.models import CourseStudentStatus
    from users.learning import is_course_student, cohort_info
    from rest_framework.exceptions import ValidationError
    today = timezone.localdate()
    request = SimpleNamespace(user=admin_user)
    CourseStudentStatus.objects.create(user=user, is_course_student=True)
    assert is_course_student(user) and cohort_info(user) is None
    cohort = people.save_cohort(request, {'name': 'configurable batch', 'target_year': 2028,
        'starts_on': str(today), 'ends_on': str(today+timedelta(days=30)), 'is_active': True})
    people.save_student_status(request, {'id': user.pk, 'is_course_student': True, 'cohort_id': cohort['id']})
    second = people.save_cohort(request, {'name': 'another batch', 'target_year': 2029,
        'starts_on': str(today), 'ends_on': str(today+timedelta(days=30)), 'is_active': True})
    people.save_student_status(request, {'id': user.pk, 'is_course_student': True, 'cohort_id': second['id']})
    people.save_student_status(request, {'id': user.pk, 'is_course_student': False})
    people.save_student_status(request, {'id': user.pk, 'is_course_student': True})
    assert CourseStudentStatus.objects.get(user=user).cohort_id == second['id']
    assert people.student_detail(request, {'id': user.pk})['cohort']['target_year'] == 2029
    with pytest.raises(ValidationError):
        people.save_cohort(request, {'name': 'bad dates', 'target_year': 2028,
            'starts_on': str(today), 'ends_on': str(today-timedelta(days=1))})
    assert APIClient().post('/api/backoffice/operations/cohorts.save/', {}).status_code == 401
    from rest_framework.authtoken.models import Token
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION='Token ' + Token.objects.get_or_create(user=user)[0].key)
    assert client.post('/api/backoffice/operations/cohorts.save/', {}).status_code == 401
    from rest_framework.test import APIRequestFactory
    from backoffice.views import OperationView
    second_admin = type(user).objects.create_superuser(username='cohort-operator-two')
    actor, other_actor = str(uuid4()), str(uuid4())
    settings.UNIMIND_ADMIN_BRIDGE_SECRET = 'synthetic-cohort-smoke-bridge-secret'
    settings.UNIMIND_DIRECTUS_ADMIN_MAP = {actor: admin_user.pk, other_actor: second_admin.pk}

    def operation(name, payload):
        path = f'/api/backoffice/operations/{name}/'
        body, stamp, nonce = json.dumps(payload), str(int(time.time())), str(uuid4())
        canonical = '\n'.join(['v1', 'POST', path, actor, stamp, nonce, hashlib.sha256(body.encode()).hexdigest()])
        signature = hmac.new(settings.UNIMIND_ADMIN_BRIDGE_SECRET.encode(), canonical.encode(), hashlib.sha256).hexdigest()
        request = APIRequestFactory().post(path, data=body, content_type='application/json', HTTP_X_UNIMIND_OPERATOR=actor,
            HTTP_X_UNIMIND_TIMESTAMP=stamp, HTTP_X_UNIMIND_NONCE=nonce, HTTP_X_UNIMIND_SIGNATURE=signature)
        return OperationView.as_view()(request, operation=name)

    changed = operation('cohorts.save', {'id': second['id'], 'name': 'signed cohort update', 'request_id': str(uuid4())})
    assert changed.status_code == 200 and changed.data['name'] == 'signed cohort update'
    listed = operation('cohorts.list', {})
    assert listed.status_code == 200 and len(listed.data['items']) == 2
