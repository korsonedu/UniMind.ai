from django.db import transaction, models
from django.db.models import F


def _create_ledger(user_id, amount, balance_after, reason, description,
                   reference_type=None, reference_id=None):
    from .models import EloPointsLedger
    EloPointsLedger.objects.create(
        user_id=user_id, amount=amount, balance_after=balance_after,
        reason=reason, description=description or '',
        reference_type=reference_type, reference_id=reference_id,
    )


def _resolve_ref(reference_obj):
    if reference_obj is None:
        return None, None
    return reference_obj._meta.label, reference_obj.pk


def award_elo_points(user_id: int, amount: int, reason: str,
                     description: str = '', reference_obj=None) -> int:
    """
    为用户发放积分。仅正数有效，负数或零直接返回0。
    调用方不应处于 select_for_update 事务中——本函数自行管理事务和锁。
    """
    if amount <= 0:
        return 0
    from .models import User
    ref_type, ref_id = _resolve_ref(reference_obj)
    with transaction.atomic():
        locked = User.objects.select_for_update().get(id=user_id)
        locked.elo_points += amount
        locked.save(update_fields=['elo_points'])
        _create_ledger(
            user_id=user_id, amount=amount, balance_after=locked.elo_points,
            reason=reason, description=description,
            reference_type=ref_type, reference_id=ref_id,
        )
    return amount


def spend_elo_points(user_id: int, amount: int, reason: str,
                     description: str = '', reference_obj=None) -> bool:
    """
    消费积分。余额不足返回False，成功返回True。
    """
    if amount <= 0:
        return False
    from .models import User
    ref_type, ref_id = _resolve_ref(reference_obj)
    with transaction.atomic():
        locked = User.objects.select_for_update().get(id=user_id)
        if locked.elo_points < amount:
            return False
        locked.elo_points -= amount
        locked.save(update_fields=['elo_points'])
        _create_ledger(
            user_id=user_id, amount=-amount, balance_after=locked.elo_points,
            reason=reason, description=description,
            reference_type=ref_type, reference_id=ref_id,
        )
    return True


def reset_elo_points(user_id: int) -> int:
    """ELO 重置时积分归零，返回清零前的余额。"""
    from .models import User, EloPointsLedger
    with transaction.atomic():
        locked = User.objects.select_for_update().get(id=user_id)
        previous = locked.elo_points
        if previous == 0:
            return 0
        locked.elo_points = 0
        locked.save(update_fields=['elo_points'])
        EloPointsLedger.objects.create(
            user_id=user_id, amount=-previous, balance_after=0,
            reason='elo_reset', description=f'ELO 重置清零积分',
        )
    return previous
