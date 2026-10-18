from datetime import timedelta
import uuid

import pytest
from django.utils import timezone

from payments.models import Order
from users.models import Institution, User


@pytest.fixture
def business_admin(db, settings):
    institution = Institution.objects.create(
        name='Revenue school', slug='revenue-school',
        contact_name='Owner', contact_email='owner@example.com', plan='growth',
    )
    admins = [
        User.objects.create_superuser(
            username=f'business_operator{i}', email=f'business_op{i}@example.com',
            password='Pass12345!',
        )
        for i in range(2)
    ]
    actors = [str(uuid.uuid4()), str(uuid.uuid4())]
    settings.UNIMIND_CONTENT_INSTITUTION_ID = str(institution.id)
    settings.UNIMIND_DIRECTUS_ADMIN_MAP = dict(zip(actors, [admin.pk for admin in admins]))
    return admins[0], institution


@pytest.mark.django_db
def test_empty_business_dashboard_returns_zero_revenue(api_client, business_admin):
    admin, _ = business_admin
    api_client.force_authenticate(user=admin)
    response = api_client.get('/api/users/institution/me/business-dashboard/')
    assert response.status_code == 200
    assert response.data['revenue'] == 0
    assert response.data['revenue_this_month'] == 0


@pytest.mark.django_db
def test_business_revenue_counts_paid_orders_for_current_institution(api_client, business_admin):
    admin, institution = business_admin
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    other = Institution.objects.create(
        name='Other school', slug='other-revenue-school',
        contact_name='Owner', contact_email='other@example.com', plan='growth',
    )
    for order_institution, status, amount, paid_at in [
        (institution, 'paid', 9900, now),
        (institution, 'paid', 10000, month_start - timedelta(days=1)),
        (institution, 'pending', 99900, None),
        (other, 'paid', 20000, now),
    ]:
        Order.objects.create(
            user=admin, institution=order_institution, status=status,
            plan='starter', billing_cycle='monthly', gateway='stub',
            amount_cents=amount, paid_at=paid_at, expires_at=now + timedelta(days=1),
        )
    api_client.force_authenticate(user=admin)
    response = api_client.get('/api/users/institution/me/business-dashboard/')
    assert response.status_code == 200
    assert response.data['revenue'] == 199
    assert response.data['revenue_this_month'] == 99
    assert response.data['paying_users'] == 1
    assert response.data['renewal_rate'] == 100
