"""
Tests for payments module — gateway router, subscription lifecycle,
order flow, and stub gateway interface.
"""
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from payments.models import Order, Subscription
from users.models import User, Institution, AIAddonProduct


def _create_institution(name='Test School', plan='free', creator=None):
    slug = name.lower().replace(' ', '-') + '-' + uuid.uuid4().hex[:6]
    return Institution.objects.create(
        name=name, slug=slug,
        contact_name='Admin', contact_email='admin@test.com',
        plan=plan, created_by=creator,
    )


def _create_owner(username='owner', email='owner@test.com', institution=None):
    user = User.objects.create_user(username=username, email=email, password='testpass')
    if institution:
        user.institution = institution
        user.institution_role = 'owner'
        user.save()
    return user


def _historical_subscription(*, institution, plan='starter', billing_cycle='monthly', gateway='stub'):
    # Existing subscriptions must remain manageable after new sales are retired.
    start = timezone.now()
    return Subscription.objects.create(
        institution=institution, plan=plan, billing_cycle=billing_cycle, gateway=gateway,
        current_period_start=start,
        current_period_end=start + timedelta(days=365 if billing_cycle == 'annual' else 30),
    )


def _create_ai_product():
    return AIAddonProduct.objects.create(
        name='AI 加量', price_cents=9900, ai_calls=100, validity_days=30, is_active=True,
    )


# ═══════════════════════════════════════════════════════════════════
# Gateway Router
# ═══════════════════════════════════════════════════════════════════


class GatewayRouterTests(TestCase):
    def test_get_gateway_known_stub(self):
        from payments.services.gateway_router import get_gateway
        gw = get_gateway('stub')
        self.assertIsNotNone(gw)
        self.assertTrue(hasattr(gw, 'create_checkout_session'))

    def test_get_gateway_unknown_raises(self):
        from payments.services.gateway_router import get_gateway
        with self.assertRaises(ValueError):
            get_gateway('nonexistent')

    def test_get_gateway_stripe_removed(self):
        from payments.services.gateway_router import get_gateway
        with self.assertRaises(ValueError):
            get_gateway('stripe')

    def test_get_gateway_airwallex_removed(self):
        from payments.services.gateway_router import get_gateway
        with self.assertRaises(ValueError):
            get_gateway('airwallex')

    def test_gateway_supports_subscriptions_stub(self):
        from payments.services.gateway_router import gateway_supports_subscriptions
        self.assertTrue(gateway_supports_subscriptions('stub'))

    def test_gateway_supports_subscriptions_unknown(self):
        from payments.services.gateway_router import gateway_supports_subscriptions
        self.assertFalse(gateway_supports_subscriptions('nonexistent'))


# ═══════════════════════════════════════════════════════════════════
# Plan Pricing
# ═══════════════════════════════════════════════════════════════════


class PlanPricingTests(TestCase):
    def test_monthly_prices(self):
        from payments.services.base import get_plan_price
        self.assertEqual(get_plan_price('starter', 'monthly'), 49900)
        self.assertEqual(get_plan_price('growth', 'monthly'), 129900)
        self.assertEqual(get_plan_price('enterprise', 'monthly'), 399900)

    def test_annual_prices(self):
        from payments.services.base import get_plan_price
        self.assertEqual(get_plan_price('starter', 'annual'), 499200)
        self.assertEqual(get_plan_price('growth', 'annual'), 1299600)
        self.assertEqual(get_plan_price('enterprise', 'annual'), 3999600)

    def test_unknown_plan_returns_zero(self):
        from payments.services.base import get_plan_price
        self.assertEqual(get_plan_price('nonexistent', 'monthly'), 0)


# ═══════════════════════════════════════════════════════════════════
# Subscription Business Layer
# ═══════════════════════════════════════════════════════════════════


class SubscriptionLifecycleTests(TestCase):
    def setUp(self):
        self.institution = _create_institution(name='Sub School', plan='free')
        self.owner = _create_owner(institution=self.institution)
        self.institution.created_by = self.owner
        self.institution.save()

    def test_create_subscription_monthly_rejected(self):
        from payments.services.subscription import create_subscription

        with self.assertRaisesMessage(ValueError, '机构套餐已停止销售。'):
            create_subscription(
                institution=self.institution, plan='growth',
                billing_cycle='monthly', gateway='stub',
            )
        self.assertFalse(Subscription.objects.exists())
        self.assertFalse(Order.objects.exists())

    def test_create_subscription_annual_rejected(self):
        from payments.services.subscription import create_subscription

        with self.assertRaisesMessage(ValueError, '机构套餐已停止销售。'):
            create_subscription(
                institution=self.institution, plan='enterprise',
                billing_cycle='annual', gateway='stub',
            )
        self.assertFalse(Subscription.objects.exists())
        self.assertFalse(Order.objects.exists())

    def test_activate_subscription(self):
        from payments.services.subscription import activate_subscription

        sub = _historical_subscription(
            institution=self.institution, plan='growth',
            billing_cycle='monthly', gateway='stub',
        )
        sub = activate_subscription(sub, 'sub_test_123', 'cus_test_456')

        self.assertEqual(sub.status, 'active')
        self.assertEqual(sub.gateway_subscription_id, 'sub_test_123')
        self.assertEqual(sub.gateway_customer_id, 'cus_test_456')

        self.owner.refresh_from_db()
        self.assertTrue(self.owner.is_member)
        self.assertEqual(self.owner.membership_tier, 'growth')
        self.assertIsNotNone(self.owner.membership_expires_at)
        self.assertTrue(self.owner.membership_source.startswith('subscription:'))

        self.institution.refresh_from_db()
        self.assertEqual(self.institution.plan, 'free')

    def test_cancel_subscription(self):
        from payments.services.subscription import (
            activate_subscription, cancel_subscription,
        )

        sub = _historical_subscription(
            institution=self.institution, plan='growth',
            billing_cycle='monthly', gateway='stub',
        )
        sub = activate_subscription(sub, 'sub_test_123')
        sub = cancel_subscription(sub)

        self.assertEqual(sub.status, 'canceled')
        self.assertIsNotNone(sub.canceled_at)

    def test_renew_subscription(self):
        from payments.services.subscription import (
            activate_subscription, renew_subscription,
        )

        sub = _historical_subscription(
            institution=self.institution, plan='starter',
            billing_cycle='monthly', gateway='stub',
        )
        sub = activate_subscription(sub, 'sub_test_123')
        original_end = sub.current_period_end
        new_end = original_end + timedelta(days=30)
        sub = renew_subscription(sub, new_end)

        self.assertEqual(sub.status, 'active')
        self.assertGreater(sub.current_period_end, original_end)

    def test_expire_subscription(self):
        from payments.services.subscription import (
            activate_subscription, expire_subscription,
        )

        sub = _historical_subscription(
            institution=self.institution, plan='growth',
            billing_cycle='monthly', gateway='stub',
        )
        sub = activate_subscription(sub, 'sub_test_123')
        sub = expire_subscription(sub)

        self.assertEqual(sub.status, 'expired')

        self.institution.refresh_from_db()
        self.assertEqual(self.institution.plan, 'free')
        self.assertIsNone(self.institution.plan_expires_at)

        self.owner.refresh_from_db()
        self.assertFalse(self.owner.is_member)
        self.assertEqual(self.owner.membership_tier, 'free')

    def test_get_active_subscription(self):
        from payments.services.subscription import (
            activate_subscription, get_active_subscription,
        )

        self.assertIsNone(get_active_subscription(self.institution))

        sub = _historical_subscription(
            institution=self.institution, plan='starter',
            billing_cycle='annual', gateway='stub',
        )
        sub = activate_subscription(sub, 'sub_test_123')

        active = get_active_subscription(self.institution)
        self.assertIsNotNone(active)
        self.assertEqual(active.id, sub.id)

    def test_get_active_subscription_ignores_canceled(self):
        from payments.services.subscription import (
            activate_subscription,
            cancel_subscription, get_active_subscription,
        )

        sub = _historical_subscription(
            institution=self.institution, plan='starter',
            billing_cycle='monthly', gateway='stub',
        )
        sub = activate_subscription(sub, 'sub_test_123')
        cancel_subscription(sub)

        self.assertIsNone(get_active_subscription(self.institution))


# ═══════════════════════════════════════════════════════════════════
# Order Flow
# ═══════════════════════════════════════════════════════════════════


class OrderFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='buyer', email='buyer@test.com', password='testpass'
        )
        self.institution = _create_institution(
            name='Buyer School', plan='free', creator=self.user,
        )
        self.user.institution = self.institution
        self.user.institution_role = 'owner'
        self.user.save()
        self.product = _create_ai_product()

    def test_create_institution_order_rejected(self):
        from payments.services.base import create_order

        with self.assertRaisesMessage(ValueError, '机构套餐已停止销售。'):
            create_order(
                user=self.user, plan='starter', billing_cycle='monthly',
                gateway='stub', institution=self.institution,
            )
        self.assertFalse(Order.objects.exists())

    def test_create_order_basic(self):
        from payments.services.base import create_ai_addon_order

        order = create_ai_addon_order(
            user=self.user, product=self.product, gateway='stub',
        )
        self.assertEqual(order.status, 'pending')
        self.assertEqual(order.plan, 'ai_addon')
        self.assertEqual(order.amount_cents, self.product.price_cents)
        self.assertEqual(order.entitlement_snapshot, self.product.snapshot())
        self.assertGreater(order.amount_cents, 0)
        self.assertIsNotNone(order.expires_at)

    def test_create_order_expires_in_30_minutes(self):
        from payments.services.base import create_ai_addon_order

        order = create_ai_addon_order(
            user=self.user, product=self.product, gateway='stub',
        )
        delta = order.expires_at - order.created_at
        self.assertAlmostEqual(delta.total_seconds(), 1800, delta=60)

    def test_confirm_order_grants_ai_addon(self):
        from payments.services.base import create_ai_addon_order, confirm_order

        order = create_ai_addon_order(
            user=self.user, product=self.product, gateway='stub',
        )
        txn_id = f'txn_{uuid.uuid4().hex[:12]}'
        confirm_order(order.id, txn_id, {'source': 'test'}, order.amount_cents)

        order.refresh_from_db()
        self.assertEqual(order.status, 'paid')
        self.assertIsNotNone(order.paid_at)

        self.user.refresh_from_db()
        self.assertFalse(self.user.is_member)
        grant = order.ai_addon_grant
        self.assertEqual(grant.user_id, self.user.id)
        self.assertEqual(grant.ai_calls, self.product.ai_calls)
        self.assertEqual(grant.snapshot, order.entitlement_snapshot)
        self.assertAlmostEqual((grant.expires_at - grant.starts_at).days, self.product.validity_days, delta=1)

        self.institution.refresh_from_db()
        self.assertEqual(self.institution.plan, 'free')

    def test_confirm_order_idempotent(self):
        from payments.services.base import create_ai_addon_order, confirm_order

        order = create_ai_addon_order(
            user=self.user, product=self.product, gateway='stub',
        )
        txn_id = f'txn_{uuid.uuid4().hex[:12]}'
        confirm_order(order.id, txn_id, {'source': 'test'}, order.amount_cents)
        order.refresh_from_db()
        self.assertEqual(order.status, 'paid')

        confirm_order(order.id, txn_id, {'source': 'test'}, order.amount_cents)
        self.assertEqual(order.transactions.count(), 1)
        self.assertEqual(self.user.ai_addon_grants.count(), 1)

        with self.assertRaisesMessage(ValueError, 'Payment transaction mismatch'):
            confirm_order(order.id, f'{txn_id}_dup', {'source': 'test'}, order.amount_cents)
        self.assertEqual(order.transactions.count(), 1)
        self.assertEqual(self.user.ai_addon_grants.count(), 1)

    def test_confirm_order_amount_mismatch_raises(self):
        from payments.services.base import create_ai_addon_order, confirm_order

        order = create_ai_addon_order(
            user=self.user, product=self.product, gateway='stub',
        )
        with self.assertRaises(ValueError):
            confirm_order(order.id, f'txn_{uuid.uuid4().hex[:12]}', {'source': 'test'}, 1)
        order.refresh_from_db()
        self.assertEqual(order.status, 'pending')
        self.assertFalse(order.transactions.exists())
        self.assertFalse(self.user.ai_addon_grants.exists())

    def test_confirm_order_updates_gateway_order_id(self):
        from payments.services.base import create_ai_addon_order, confirm_order

        order = create_ai_addon_order(
            user=self.user, product=self.product, gateway='stub',
        )
        txn_id = f'txn_{uuid.uuid4().hex[:12]}'
        confirm_order(order.id, txn_id, {'source': 'test'}, order.amount_cents)
        order.refresh_from_db()
        self.assertEqual(order.gateway_order_id, txn_id)


# ═══════════════════════════════════════════════════════════════════
# Stub Gateway Interface
# ═══════════════════════════════════════════════════════════════════


class StubGatewayTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='stubber', email='stub@test.com', password='testpass'
        )
        self.institution = _create_institution(
            name='Stub School', creator=self.user,
        )
        self.user.institution = self.institution
        self.user.save()

    def _make_order(self):
        from payments.services.base import create_ai_addon_order
        return create_ai_addon_order(user=self.user, product=_create_ai_product(), gateway='stub')

    def test_create_checkout_session_returns_url(self):
        from payments.services.stub_gateway import create_checkout_session

        order = self._make_order()
        result = create_checkout_session(order)
        self.assertIn('checkout_url', result)
        self.assertIn(str(order.id), result['checkout_url'])

    def test_create_subscription_checkout_returns_url(self):
        from payments.services.stub_gateway import create_subscription_checkout

        order = Order.objects.create(
            user=self.user, institution=self.institution, plan='starter',
            billing_cycle='monthly', amount_cents=49900, gateway='stub',
            expires_at=timezone.now() + timedelta(minutes=30),
        )
        result = create_subscription_checkout(order)
        self.assertIn('checkout_url', result)
        self.assertIn('subscription_id', result)

    def test_verify_webhook_always_passes(self):
        from payments.services.stub_gateway import verify_webhook

        event = verify_webhook({}, b'{"type":"payment.succeeded"}')
        self.assertEqual(event['type'], 'payment.succeeded')

        event = verify_webhook({}, b'invalid json')
        self.assertEqual(event['type'], 'payment.succeeded')

    def test_process_webhook_ignores_irrelevant_events(self):
        from payments.services.stub_gateway import process_webhook_event

        result = process_webhook_event({'type': 'refund.processed', 'data': {}})
        self.assertIsNone(result)

    def test_process_webhook_payment_succeeded(self):
        from payments.services.stub_gateway import process_webhook_event

        result = process_webhook_event({
            'type': 'payment.succeeded',
            'data': {'order_id': 42, 'txn_id': 'stub_abc123'},
        })
        self.assertIsNotNone(result)
        self.assertEqual(result['order_id'], 42)

    def test_process_webhook_subscription_checkout(self):
        from payments.services.stub_gateway import process_webhook_event

        result = process_webhook_event({
            'type': 'subscription_checkout_completed',
            'data': {'order_id': 42, 'txn_id': 'stub_abc123'},
        })
        self.assertIsNotNone(result)
        self.assertEqual(result['type'], 'subscription_checkout_completed')
        self.assertIn('gateway_subscription_id', result)

    def test_process_webhook_subscription_renewed(self):
        from payments.services.stub_gateway import process_webhook_event

        result = process_webhook_event({
            'type': 'subscription_renewed',
            'data': {
                'subscription_id': 'sub_stub_99',
                'new_period_end': '2026-07-23T00:00:00Z',
            },
        })
        self.assertIsNotNone(result)
        self.assertEqual(result['type'], 'subscription_renewed')
        self.assertEqual(result['gateway_subscription_id'], 'sub_stub_99')

    def test_process_webhook_missing_order_id_returns_none(self):
        from payments.services.stub_gateway import process_webhook_event

        result = process_webhook_event({'type': 'payment.succeeded', 'data': {}})
        self.assertIsNone(result)

    def test_cancel_subscription(self):
        from payments.services.stub_gateway import cancel_subscription

        sub = _historical_subscription(
            institution=self.institution, plan='starter',
            billing_cycle='monthly', gateway='stub',
        )
        result = cancel_subscription(sub)
        self.assertTrue(result['success'])


# ═══════════════════════════════════════════════════════════════════
# API Endpoints
# ═══════════════════════════════════════════════════════════════════


class OrderAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='orderer', email='o@test.com', password='testpass'
        )
        self.client.force_authenticate(user=self.user)
        self.product = _create_ai_product()

    @override_settings(DEBUG=True)
    def test_create_checkout_session(self):
        resp = self.client.post('/api/payments/create-session/', {
            'product': self.product.id, 'gateway': 'stub',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertIn('checkout_url', resp.data)
        self.assertIn('order_id', resp.data)

    def test_create_checkout_session_invalid_gateway(self):
        resp = self.client.post('/api/payments/create-session/', {
            'product': self.product.id, 'gateway': 'nonexistent',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    @override_settings(DEBUG=True)
    def test_institution_checkout_payload_rejected(self):
        resp = self.client.post('/api/payments/create-session/', {
            'plan': 'starter', 'billing_cycle': 'monthly', 'gateway': 'stub',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Order.objects.exists())

    def test_subscription_sales_route_retired(self):
        resp = self.client.post('/api/payments/subscriptions/', {
            'plan': 'starter', 'billing_cycle': 'monthly', 'gateway': 'stub',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(Subscription.objects.exists())
        self.assertFalse(Order.objects.exists())

    def test_get_order_status(self):
        from payments.services.base import create_ai_addon_order

        order = create_ai_addon_order(
            user=self.user, product=self.product, gateway='stub',
        )
        resp = self.client.get(f'/api/payments/orders/{order.id}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['plan'], 'ai_addon')
        self.assertEqual(resp.data['product_name'], self.product.name)
        self.assertEqual(resp.data['status'], 'pending')

    def test_get_order_not_found(self):
        resp = self.client.get('/api/payments/orders/99999/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_order_history(self):
        from payments.services.base import create_ai_addon_order

        for i in range(3):
            create_ai_addon_order(
                user=self.user, product=self.product, gateway='stub',
            )
        resp = self.client.get('/api/payments/orders/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 3)

    def test_webhook_rejects_missing_secret(self):
        resp = self.client.post('/api/payments/webhook/?gateway=stub', {}, format='json')
        self.assertIn(resp.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_500_INTERNAL_SERVER_ERROR))

    def test_coupon_validate_retired(self):
        resp = self.client.post('/api/payments/coupons/validate/', {
            'code': 'NOEXIST', 'plan': 'starter', 'billing_cycle': 'monthly',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_410_GONE)
        self.assertEqual(resp.data['error'], '旧版机构套餐优惠码已停止使用。')
        self.assertFalse(Order.objects.exists())

    def test_coupon_list_empty(self):
        resp = self.client.get('/api/payments/coupons/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)


# ═══════════════════════════════════════════════════════════════════
# Celery Tasks
# ═══════════════════════════════════════════════════════════════════


class TaskTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='tasker', email='t@test.com', password='testpass',
        )
        self.institution = _create_institution(
            name='Task School', plan='growth', creator=self.user,
        )
        self.user.institution = self.institution
        self.user.institution_role = 'owner'
        self.user.save()

    def test_expire_stale_orders(self):
        from payments.services.base import create_ai_addon_order
        from payments.tasks import expire_stale_orders

        order = create_ai_addon_order(
            user=self.user, product=_create_ai_product(), gateway='stub',
        )
        expire_stale_orders()
        order.refresh_from_db()
        self.assertEqual(order.status, 'pending')

        order.created_at = timezone.now() - timedelta(minutes=60)
        order.save(update_fields=['created_at'])
        expire_stale_orders()
        order.refresh_from_db()
        self.assertEqual(order.status, 'expired')

    def test_check_subscription_expiry(self):
        from payments.services.subscription import activate_subscription
        from payments.tasks import check_subscription_expiry

        sub = _historical_subscription(
            institution=self.institution, plan='growth',
            billing_cycle='monthly', gateway='stub',
        )
        activate_subscription(sub, 'sub_task_123')

        sub.current_period_end = timezone.now() - timedelta(days=1)
        sub.save(update_fields=['current_period_end'])

        check_subscription_expiry()

        sub.refresh_from_db()
        self.assertEqual(sub.status, 'expired')
        self.institution.refresh_from_db()
        self.assertEqual(self.institution.plan, 'free')
