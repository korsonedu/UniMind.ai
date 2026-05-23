# Payment System — System-Level Architecture Plan

Date: 2026-05-21 | Status: Design Phase

## 1. Audit Summary (What Exists vs. What's Missing)

### Existing (Keep & Wire Up)

| Asset | Location | Status |
|-------|----------|--------|
| User: `is_member`, `membership_tier`, `membership_expires_at`, `trial_ends_at` | `users/models.py:36-38` | Fields exist, `trial_ends_at` never set |
| Institution: `plan`, `plan_expires_at` | `users/models.py:151-153` | Working, manually changed by admin |
| `PLAN_FEATURES` matrix | `users/models.py:237-264` | Complete |
| `ActivationCode` + `ActivateMembershipView` | `users/models.py:66-75`, `views.py:39-63` | Working (manual code redemption) |
| `PlanInviteCode` + full CRUD API | `users/models.py:286-344`, `views_institution.py:900-976` | Working |
| `InstitutionPaymentConfig` | `users/models_commercial.py:49-72` | Model exists, **no API** |
| `check_membership_expiry` celery task | `users/tasks.py:14-46` | Working, but `trial_ends_at` never populated |
| `is_member_or_admin` permission | `users/permissions.py:48-63` | Working |
| Landing Pricing section | `frontend/src/pages/Landing.tsx:476-593` | Display only, CTAs go to `/register` |
| `UpgradeModal` | `frontend/src/components/UpgradeModal.tsx` | Goes to landing `#pricing` — dead end for logged-in users |
| `MembershipPanel` (admin) | `frontend/src/pages/maintenance/MembershipPanel.tsx` | Invite code management only |

### Missing (Need to Build)

1. **Trial activation** — `trial_ends_at` never set on registration
2. **Order/Payment/Transaction models** — no payment tracking at all
3. **Payment gateway integration** — Stripe + WeChat Pay + Alipay
4. **`InstitutionPaymentConfig` API** — model exists, no endpoints
5. **Checkout page (frontend)** — no payment UI
6. **Billing/Settings page (frontend)** — no subscription management UI
7. **Webhook handlers** — no payment callback processing
8. **Invoice generation** — PDF invoice for each payment
9. **Trial expiry notifications** — no reminder before/after trial ends

---

## 2. Architecture Decision: Landing vs. In-App

```
┌──────────────────────────────────────────────────────┐
│                    LANDING PAGE                       │
│   Pricing (informational)                            │
│   All CTAs → "免费试用 14 天" → /register            │
│   No payment form, no checkout                       │
│   Converts visitors → trial users                    │
└──────────────────────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────┐
│                   REGISTRATION                        │
│   Auto-set: trial_ends_at = now + 14 days            │
│   Auto-set: is_member = True (trial period)          │
│   membership_tier = 'free'                           │
│   User enters app with full feature access           │
└──────────────────────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────┐
│                 UNIMIND APP (AUTHED)                   │
│                                                       │
│  ┌─────────────────────────────────────────────┐     │
│  │ Trial Day 1-11: Full access, subtle banner   │     │
│  │ "试用期还剩 X 天 · 升级解锁永久使用"           │     │
│  ├─────────────────────────────────────────────┤     │
│  │ Trial Day 12-14: Prominent banner + email    │     │
│  │ "试用即将到期"                                 │     │
│  ├─────────────────────────────────────────────┤     │
│  │ Trial Expired: Downgrade to Free tier        │     │
│  │ Feature-gate kicks in, UpgradeModal on       │     │
│  │ restricted feature access                    │     │
│  └─────────────────────────────────────────────┘     │
│                                                       │
│  Settings → 「方案与账单」tab:                          │
│   Current plan display                               │
│   Upgrade options (Solo/Plus/Pro)                    │
│   Payment method selection (WeChat/Alipay/Stripe)    │
│   Billing history                                    │
│   Invoice download                                   │
│                                                       │
│  Pro Institution Admin → 「收款配置」:                  │
│   Bind WeChat merchant / Alipay app                  │
│   Toggle student.payment on/off                      │
│   View student payment history                       │
└──────────────────────────────────────────────────────┘
```

**Rule**: Landing converts → trial. In-app converts → paid. Never mix.

---

## 3. Database Schema (New Models)

### 3.1 Order & Payment (`users/models_commercial.py` additions)

```python
class Order(models.Model):
    """Payment order — one per upgrade/purchase attempt."""
    STATUS_CHOICES = [
        ('pending', 'Pending'),       # created, waiting for payment
        ('paid', 'Paid'),             # payment confirmed
        ('expired', 'Expired'),       # timeout, no payment
        ('refunded', 'Refunded'),     # fully refunded
        ('cancelled', 'Cancelled'),   # user cancelled
    ]
    user = FK(User)
    institution = FK(Institution, null=True)  # null = personal upgrade
    plan = CharField (solo/plus/pro)
    billing_cycle = CharField (monthly/annual)
    amount_yuan = IntegerField  # amount in 分 (cent) to avoid float issues
    status = CharField
    gateway = CharField (stripe/wechat/alipay)
    gateway_order_id = CharField (max_length=64, unique=True, null=True)
    paid_at = DateTimeField(null=True)
    created_at = DateTimeField(auto_now_add=True)
    expires_at = DateTimeField  # order timeout (e.g. created_at + 30min)

class PaymentTransaction(models.Model):
    """Raw callback from payment gateway — immutable audit trail."""
    order = FK(Order)
    gateway = CharField
    gateway_txn_id = CharField(max_length=128)
    raw_callback = JSONField  # full gateway callback payload
    amount_received_yuan = IntegerField
    status = CharField  # success/fail/refund
    created_at = DateTimeField(auto_now_add=True)

class Invoice(models.Model):
    """Generated PDF invoice per successful payment."""
    order = OneToOneField(Order)
    invoice_number = CharField(max_length=32, unique=True)  # INV-20260521-XXXX
    pdf_file = FileField(upload_to='invoices/')
    created_at = DateTimeField(auto_now_add=True)
```

### 3.2 Plan Change Audit (enhance existing `InstitutionAuditLog`)

Already exists with `action='change_plan'`. Needs new action types:
- `purchase_plan` — user purchased via payment
- `renew_plan` — auto/manual renewal
- `refund_plan` — refund processed

---

## 4. Payment Flow (Per Gateway)

### 4.1 Stripe (International Credit Card)

```
Frontend                    Backend                     Stripe
──────────────────────────────────────────────────────────────
1. Select plan → POST /api/payments/stripe/create-intent/
                           │
                           ├─ Create Order (pending)
                           ├─ stripe.PaymentIntent.create(amount, currency='cny')
                           └─ Return {clientSecret, orderId}
2. stripe.confirmCardPayment(clientSecret)
   (Stripe Elements UI)
                           │
                           ├─ Stripe webhook → POST /api/payments/stripe/webhook/
                           │  ├─ Verify signature
                           │  ├─ Create PaymentTransaction
                           │  ├─ Update Order → paid
                           │  ├─ Activate membership
                           │  └─ Generate Invoice PDF
                           │
3. Redirect to success page
```

### 4.2 WeChat Pay (JSAPI / Native)

```
Frontend                    Backend                     WeChat
──────────────────────────────────────────────────────────────
1. Select plan → POST /api/payments/wechat/create-order/
                           │
                           ├─ Create Order (pending)
                           ├─ WeChat unifiedorder API
                           └─ Return {prepay_id, ...} (JSAPI)
                              or {code_url} (Native QR)
2. WeChat JSAPI pay() or show QR
                           │
                           ├─ WeChat callback → POST /api/payments/wechat/notify/
                           │  ├─ Verify signature (APIv3)
                           │  ├─ Decrypt resource
                           │  ├─ Create PaymentTransaction
                           │  ├─ Update Order → paid
                           │  ├─ Activate membership
                           │  └─ Generate Invoice PDF
                           │
3. Poll order status → navigate on success
```

### 4.3 Alipay (Page Pay / QR)

```
Frontend                    Backend                     Alipay
──────────────────────────────────────────────────────────────
1. Select plan → POST /api/payments/alipay/create-order/
                           │
                           ├─ Create Order (pending)
                           ├─ Alipay page pay API
                           └─ Return {pay_url}
2. window.open(pay_url) or show QR
                           │
                           ├─ Alipay return → GET /api/payments/alipay/return/
                           ├─ Alipay notify → POST /api/payments/alipay/notify/
                           │  ├─ Verify signature (RSA2)
                           │  ├─ Create PaymentTransaction
                           │  ├─ Update Order → paid
                           │  ├─ Activate membership
                           │  └─ Generate Invoice PDF
                           │
3. Redirect to success page
```

---

## 5. Membership Activation Logic

Centralized in a single function (avoid scattered activation):

```python
# backend/users/services/membership.py

def activate_membership(user, plan, duration_days, source='payment'):
    """Single entry point for membership activation."""
    now = timezone.now()
    expires_at = None if duration_days <= 0 else now + timedelta(days=duration_days)

    user.is_member = True
    user.membership_tier = plan
    user.membership_expires_at = expires_at
    user.trial_ends_at = None  # trial overridden by paid
    user.save()

    # If user belongs to institution, upgrade institution plan too (for personal plans)
    # If upgrading institution, update institution.plan

    InstitutionAuditLog.objects.create(
        institution=user.institution,
        operator=user,
        action='purchase_plan',
        detail=f'{plan} (expires: {expires_at}) via {source}',
    )
```

---

## 6. Trial System (Fix the Half-Built)

### Registration Changes

```python
# In RegisterView.create():
user.trial_ends_at = timezone.now() + timedelta(days=14)
user.is_member = True  # trial = member access
user.membership_tier = 'free'
user.save()
```

### Permission Gate

Existing `is_member_or_admin` already checks `trial_ends_at` (line 61 of `permissions.py`). No change needed — it just needs `trial_ends_at` to actually be populated.

### Celery Tasks (already working)

`check_membership_expiry` in `users/tasks.py` already:
1. Downgrades trial-expired users (trial_ends_at < now, membership_tier='free', no paid membership)
2. Downgrades paid-expired users (membership_expires_at < now)

### Trial Expiry Reminders (new)

New celery task runs daily: notify users 3 days before trial ends via in-app notification + email.

---

## 7. Frontend Architecture

### 7.1 New Pages / Components

| Component | Path | Purpose |
|-----------|------|---------|
| `BillingPage` | `frontend/src/pages/Billing.tsx` | Settings > 方案与账单 tab content |
| `CheckoutModal` | `frontend/src/components/CheckoutModal.tsx` | Plan selection → payment method → pay |
| `PaymentMethodSelector` | `frontend/src/components/PaymentMethodSelector.tsx` | WeChat / Alipay / Stripe |
| `StripeCheckout` | `frontend/src/components/StripeCheckout.tsx` | Stripe Elements embedded form |
| `WechatPayQR` | `frontend/src/components/WechatPayQR.tsx` | WeChat Native QR display + poll |
| `AlipayRedirect` | `frontend/src/components/AlipayRedirect.tsx` | Alipay page pay redirect handler |
| `TrialBanner` | `frontend/src/components/TrialBanner.tsx` | Global trial countdown banner |
| `BillingHistory` | `frontend/src/components/BillingHistory.tsx` | Past orders + invoice download |
| `PaymentConfigPanel` | `frontend/src/pages/institution/PaymentConfigPanel.tsx` | Pro institution merchant config |

### 7.2 Route Changes

```
/settings/billing     → BillingPage (方案与账单)
/payments/result      → PaymentResultPage (支付结果页，success/fail)
```

### 7.3 State Flow

```
useAuthStore:
  + isTrial: boolean (computed: is_member && membership_tier === 'free' && trial_ends_at exists)
  + trialDaysLeft: number (computed)
  + membershipExpiresAt: string

UpgradeModal (existing, modify):
  - Remove navigate to landing #pricing
  + Open CheckoutModal with plan pre-selected

CheckoutModal:
  - Select plan → select billing cycle → select gateway → pay
  - On success → refresh user state → close
```

---

## 8. Implementation Phases

### Phase 1: Foundation (数据库 + 试用修复 + 网关集成层)

| # | Task | Files | Verification |
|---|------|-------|-------------|
| 1.1 | New models: Order, PaymentTransaction, Invoice | `users/models_commercial.py` | `makemigrations && migrate` |
| 1.2 | Fix trial: set `trial_ends_at` on registration | `users/views.py` (RegisterView) | Register a new user, verify `trial_ends_at` is set |
| 1.3 | `activate_membership()` service function | `users/services/membership.py` (new) | Unit test |
| 1.4 | Trial banner notification celery task | `users/tasks.py` | Manual trigger, verify notification created |
| 1.5 | Stripe integration: create PaymentIntent + webhook | `payments/` app (new) | Stripe test mode payment end-to-end |
| 1.6 | WeChat Pay integration: unifiedorder + notify | `payments/` | WeChat sandbox payment |
| 1.7 | Alipay integration: page pay + notify | `payments/` | Alipay sandbox payment |

### Phase 2: Platform Payment Flow (用户升级付费)

| # | Task | Files | Verification |
|---|------|-------|-------------|
| 2.1 | Payment API endpoints (create order, query status) | `payments/views.py` | API returns correct clientSecret / prepay_id / pay_url |
| 2.2 | BillingPage (方案与账单) | `frontend/src/pages/Billing.tsx` | Page renders, shows current plan |
| 2.3 | CheckoutModal + payment method selection | `frontend/src/components/CheckoutModal.tsx` | Full checkout flow in browser |
| 2.4 | Stripe Elements checkout | `frontend/src/components/StripeCheckout.tsx` | Test card payment → membership activated |
| 2.5 | WeChat Pay checkout (QR + poll) | `frontend/src/components/WechatPayQR.tsx` | QR scan → payment → membership activated |
| 2.6 | Alipay checkout (redirect) | `frontend/src/components/AlipayRedirect.tsx` | Alipay page → payment → return |
| 2.7 | Payment result page | `frontend/src/pages/PaymentResult.tsx` | Success/failure display |
| 2.8 | Wire UpgradeModal to open CheckoutModal | `UpgradeModal.tsx` | Feature gate → upgrade → pay → unlocked |
| 2.9 | Trial banner (global) | `TrialBanner.tsx` + `MainLayout.tsx` | Shows remaining days, click to upgrade |
| 2.10 | Invoice PDF generation | `payments/invoice.py` | Payment triggers PDF, downloadable from BillingPage |

### Phase 3: Pro Institution Student Payment (学生端收费)

| # | Task | Files | Verification |
|---|------|-------|-------------|
| 3.1 | InstitutionPaymentConfig API (CRUD) | `users/views_institution.py` | Pro owner can save/update merchant config |
| 3.2 | PaymentConfigPanel (frontend) | `frontend/src/pages/institution/PaymentConfigPanel.tsx` | Form binds to API, keys encrypted at rest |
| 3.3 | Institution-gated payment flow | `payments/views.py` | Student pays → money goes to institution's merchant |
| 3.4 | Institution payment history/ledger | `users/views_institution.py` | Pro owner sees student payment records |

---

## 9. Key Design Decisions

1. **金额单位用分（整数）**，不用浮点数。`amount_yuan` 实际上是分（cent），避免精度问题。
2. **Order 30 分钟过期**，未支付自动取消。防止僵尸订单。
3. **PaymentTransaction 不可变** — 只 create，不 update。回调原始数据全量保存，可审计。
4. **微信/支付宝密钥加密存储** — 已有的 `EncryptedCharField` / `EncryptedTextField` 方案继续用。
5. **发票异步生成** — Celery 任务，不阻塞支付回调响应。
6. **单独 `payments/` app** — 支付逻辑足够独立，不和 users 耦合。

---

## 10. Security & Compliance Notes

- **Webhook 签名验证**：Stripe (stripe-signature header)、微信 (APIv3 签名)、支付宝 (RSA2 验签)，必须在处理回调前验证
- **幂等性**：支付回调可能重复发送，通过 `gateway_txn_id` 唯一约束防重
- **HTTPS only**：支付回调 URL 必须 HTTPS
- **PCI-DSS**：信用卡号不经过我们服务器（Stripe Elements 在前端直接 tokenize），降低合规范围
- **Refund**：Phase 1 不做自动退款，管理员后台手动处理
