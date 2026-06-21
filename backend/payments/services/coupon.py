"""
优惠券验证与应用服务。
"""

from django.utils import timezone
from django.db import transaction, models

from ..models import Coupon, UserCouponUse


def validate_coupon(code: str, user, plan: str, amount_cents: int) -> dict:
    """验证优惠码并计算折扣金额。

    Returns:
        {valid, discount_cents, final_amount_cents, coupon|None, error}
    """
    try:
        coupon = Coupon.objects.get(code=code.upper().strip(), is_active=True)
    except Coupon.DoesNotExist:
        return {
            'valid': False, 'discount_cents': 0,
            'final_amount_cents': amount_cents, 'coupon': None,
            'error': '优惠码无效',
        }

    if coupon.expires_at and coupon.expires_at < timezone.now():
        return {
            'valid': False, 'discount_cents': 0,
            'final_amount_cents': amount_cents, 'coupon': None,
            'error': '优惠码已过期',
        }

    if coupon.max_uses > 0 and coupon.current_uses >= coupon.max_uses:
        return {
            'valid': False, 'discount_cents': 0,
            'final_amount_cents': amount_cents, 'coupon': None,
            'error': '优惠码已被用完',
        }

    if amount_cents < coupon.min_order_cents:
        min_yuan = coupon.min_order_cents / 100
        return {
            'valid': False, 'discount_cents': 0,
            'final_amount_cents': amount_cents, 'coupon': None,
            'error': f'订单金额未达到最低使用门槛 ¥{min_yuan:.2f}',
        }

    if coupon.plan_restriction:
        allowed_plans = [p.strip() for p in coupon.plan_restriction.split(',')]
        if plan not in allowed_plans:
            return {
                'valid': False, 'discount_cents': 0,
                'final_amount_cents': amount_cents, 'coupon': None,
                'error': '该优惠码不适用于所选方案',
            }

    used_count = UserCouponUse.objects.filter(coupon=coupon, user=user).count()
    if used_count >= coupon.max_uses_per_user:
        return {
            'valid': False, 'discount_cents': 0,
            'final_amount_cents': amount_cents, 'coupon': None,
            'error': '您已达到该优惠码的使用上限',
        }

    if coupon.discount_value <= 0:
        return {
            'valid': False, 'discount_cents': 0,
            'final_amount_cents': amount_cents, 'coupon': None,
            'error': '优惠券配置异常',
        }

    if coupon.discount_type == 'percent':
        if coupon.discount_value > 100:
            return {
                'valid': False, 'discount_cents': 0,
                'final_amount_cents': amount_cents, 'coupon': None,
                'error': '折扣百分比不能超过 100',
            }
        discount_cents = int(amount_cents * coupon.discount_value / 100)
    else:
        discount_cents = min(coupon.discount_value, amount_cents)

    final_amount_cents = max(amount_cents - discount_cents, 0)

    return {
        'valid': True,
        'discount_cents': discount_cents,
        'final_amount_cents': final_amount_cents,
        'coupon': coupon,
        'error': None,
    }


@transaction.atomic
def apply_coupon(coupon, user, order):
    """原子性扣减优惠券使用次数并记录使用（带 per-user 限制）。"""
    coupon = Coupon.objects.select_for_update().get(id=coupon.id, is_active=True)

    if coupon.max_uses > 0 and coupon.current_uses >= coupon.max_uses:
        raise ValueError('优惠码已被用完')

    # 在事务内检查 per-user 限制
    user_use_count = UserCouponUse.objects.filter(
        coupon=coupon, user=user,
    ).count()
    if user_use_count >= coupon.max_uses_per_user:
        raise ValueError(f'您已达到该优惠码的使用上限（{coupon.max_uses_per_user}次）')

    coupon.current_uses += 1
    coupon.save(update_fields=['current_uses'])

    UserCouponUse.objects.create(user=user, coupon=coupon, order=order)
