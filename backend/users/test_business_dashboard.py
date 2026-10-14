from datetime import timedelta

import pytest
from django.utils import timezone

from payments.models import Order
from users.models import Institution


@pytest.fixture
def institution_owner(user):
    institution = Institution.objects.create(
        name='Revenue school', slug='revenue-school',
        contact_name='Owner', contact_email='owner@example.com', plan='growth',
    )
    user.institution = institution
    user.institution_role = 'owner'
    user.save()
    return user


@pytest.mark.django_db
def test_empty_business_dashboard_returns_zero_revenue(api_client, institution_owner):
    api_client.force_authenticate(user=institution_owner)
    response = api_client.get('/api/users/institution/me/business-dashboard/')
    assert response.status_code == 200
    assert response.data['revenue'] == 0
    assert response.data['revenue_this_month'] == 0


@pytest.mark.django_db
def test_business_revenue_counts_paid_orders_for_current_institution(api_client, institution_owner):
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    other = Institution.objects.create(
        name='Other school', slug='other-revenue-school',
        contact_name='Owner', contact_email='other@example.com', plan='growth',
    )
    for institution, status, amount, paid_at in [
        (institution_owner.institution, 'paid', 9900, now),
        (institution_owner.institution, 'paid', 10000, month_start - timedelta(days=1)),
        (institution_owner.institution, 'pending', 99900, None),
        (other, 'paid', 20000, now),
    ]:
        Order.objects.create(
            user=institution_owner, institution=institution, status=status,
            plan='starter', billing_cycle='monthly', gateway='stub',
            amount_cents=amount, paid_at=paid_at, expires_at=now + timedelta(days=1),
        )
    api_client.force_authenticate(user=institution_owner)
    response = api_client.get('/api/users/institution/me/business-dashboard/')
    assert response.status_code == 200
    assert response.data['revenue'] == 199
    assert response.data['revenue_this_month'] == 99
    assert response.data['paying_users'] == 1
    assert response.data['renewal_rate'] == 100
