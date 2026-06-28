"""
自习室学习会话管理器 — Redis 后端持有权威状态。

Key 结构：
  unimind:study:session:{user_id}   — hash: status, task_name, duration, timer_end_ts, heartbeat_ts, total_focus
  unimind:study:snapshot:{user_id}  — hash: 最后一次快照（重连回放用）
  unimind:study:agent_ctx:{user_id} — hash: 督学对话上下文
"""

import json
import logging
import time
from typing import Optional

import redis
from django.conf import settings

logger = logging.getLogger(__name__)

# ── Redis 连接 ──
REDIS_URL = getattr(settings, 'REDIS_URL', 'redis://127.0.0.1:6379/0')

_pool: Optional[redis.ConnectionPool] = None


def _get_redis() -> redis.Redis:
    global _pool
    if _pool is None:
        _pool = redis.ConnectionPool.from_url(REDIS_URL, decode_responses=True)
    return redis.Redis(connection_pool=_pool)


def _safe_float(val: str, default: float = 0.0) -> float:
    """安全解析 float，空字符串返回 default。"""
    if not val or val == '':
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


# ── Key helpers ──
def _session_key(user_id: int) -> str:
    return f'unimind:study:session:{user_id}'


def _snapshot_key(user_id: int) -> str:
    return f'unimind:study:snapshot:{user_id}'


def _agent_ctx_key(user_id: int) -> str:
    return f'unimind:study:agent_ctx:{user_id}'


# ── Session CRUD ──

def get_session(user_id: int) -> Optional[dict]:
    """获取当前会话状态，无活跃会话返回 None。"""
    r = _get_redis()
    data = r.hgetall(_session_key(user_id))
    if not data:
        return None
    timer_end = _safe_float(data.get('timer_end_ts', ''))
    heartbeat = _safe_float(data.get('heartbeat_ts', ''))
    return {
        'status': data.get('status', 'active'),
        'task_name': data.get('task_name', ''),
        'duration': int(data.get('duration', 25)),
        'timer_end_ts': timer_end or None,
        'heartbeat_ts': heartbeat or None,
        'total_focus': int(data.get('total_focus', 0)),
    }


def start_session(user_id: int, task_name: str, duration_minutes: int) -> dict:
    """开始新学习会话。"""
    r = _get_redis()
    key = _session_key(user_id)
    now = time.time()
    timer_end = now + duration_minutes * 60

    session = {
        'status': 'active',
        'task_name': task_name,
        'duration': duration_minutes,
        'timer_end_ts': timer_end,
        'heartbeat_ts': now,
        'total_focus': 0,
    }
    r.hset(key, mapping={k: str(v) for k, v in session.items()})
    # Timer TTL: duration + 60s buffer
    r.expire(key, duration_minutes * 60 + 60)

    _save_snapshot(user_id, session)
    return session


def pause_session(user_id: int) -> Optional[dict]:
    """暂停当前会话，记录剩余时间。"""
    r = _get_redis()
    key = _session_key(user_id)
    data = r.hgetall(key)
    if not data or data.get('status') != 'active':
        return None

    now = time.time()
    timer_end = _safe_float(data.get('timer_end_ts', ''))
    remaining = max(0, timer_end - now) if timer_end else 0

    r.hset(key, mapping={
        'status': 'paused',
        'timer_end_ts': '0',  # 暂停时无倒计时，用 0 表示
        'heartbeat_ts': str(now),
    })
    # 暂停后延长 TTL 30 分钟
    r.expire(key, 1800)

    session = {
        'status': 'paused',
        'task_name': data.get('task_name', ''),
        'duration': int(data.get('duration', 25)),
        'timer_end_ts': None,
        'remaining_seconds': int(remaining),
        'heartbeat_ts': now,
        'total_focus': int(data.get('total_focus', 0)),
    }
    _save_snapshot(user_id, session)
    return session


def resume_session(user_id: int) -> Optional[dict]:
    """恢复暂停的会话，重新设置 timer_end。"""
    r = _get_redis()
    key = _session_key(user_id)
    data = r.hgetall(key)
    if not data or data.get('status') != 'paused':
        return None

    # 从快照获取剩余时间
    snap = _get_snapshot(user_id)
    remaining = snap.get('remaining_seconds', int(data.get('duration', 25)) * 60) if snap else int(data.get('duration', 25)) * 60
    now = time.time()
    timer_end = now + remaining

    r.hset(key, mapping={
        'status': 'active',
        'timer_end_ts': timer_end,
        'heartbeat_ts': now,
    })
    r.expire(key, int(remaining) + 60)

    session = {
        'status': 'active',
        'task_name': data.get('task_name', ''),
        'duration': int(data.get('duration', 25)),
        'timer_end_ts': timer_end,
        'heartbeat_ts': now,
        'total_focus': int(data.get('total_focus', 0)),
    }
    _save_snapshot(user_id, session)
    return session


def end_session(user_id: int) -> Optional[dict]:
    """结束当前会话，返回最终统计。"""
    r = _get_redis()
    key = _session_key(user_id)
    pipe = r.pipeline()
    pipe.hgetall(key)
    pipe.delete(key)
    pipe.delete(_snapshot_key(user_id))
    pipe.delete(_agent_ctx_key(user_id))
    results = pipe.execute()
    data = results[0]

    if not data:
        return None

    now = time.time()
    timer_end = _safe_float(data.get('timer_end_ts', ''))
    total_focus = int(data.get('total_focus', 0))
    duration_secs = int(data.get('duration', 25)) * 60
    if data.get('status') == 'active' and timer_end:
        # 本次已消耗的秒数 = 设定时长 - 剩余秒数
        remaining_at_end = max(0, timer_end - now)
        elapsed = max(0, duration_secs - int(remaining_at_end))
        total_focus += elapsed

    return {
        'status': 'ended',
        'task_name': data.get('task_name', ''),
        'duration': int(data.get('duration', 25)),
        'total_focus_seconds': total_focus,
        'ended_at': now,
    }


def update_heartbeat(user_id: int) -> Optional[float]:
    """更新心跳时间戳，返回上次心跳距今秒数。"""
    r = _get_redis()
    key = _session_key(user_id)
    data = r.hgetall(key)
    if not data:
        return None

    now = time.time()
    last_hb = _safe_float(data.get('heartbeat_ts', ''))
    r.hset(key, 'heartbeat_ts', str(now))

    # 更新 active 会话的 TTL
    if data.get('status') == 'active':
        timer_end = _safe_float(data.get('timer_end_ts', ''))
        remaining = max(0, timer_end - now) if timer_end else 0
        r.expire(key, int(remaining) + 60)

    return now - last_hb if last_hb else 0


def add_focus_seconds(user_id: int, seconds: int):
    """累加聚焦秒数。"""
    r = _get_redis()
    key = _session_key(user_id)
    if r.exists(key):
        r.hincrby(key, 'total_focus', seconds)


# ── Snapshot ──

def _save_snapshot(user_id: int, session: dict):
    """保存快照供重连回放。"""
    r = _get_redis()
    snap = {k: str(v) if v is not None else '0' for k, v in session.items()}
    r.hset(_snapshot_key(user_id), mapping=snap)
    r.expire(_snapshot_key(user_id), 3600)  # 1h TTL


def _get_snapshot(user_id: int) -> Optional[dict]:
    r = _get_redis()
    data = r.hgetall(_snapshot_key(user_id))
    if not data:
        return None
    remaining = data.get('remaining_seconds')
    return {
        'status': data.get('status', 'active'),
        'task_name': data.get('task_name', ''),
        'duration': int(data.get('duration', 25)),
        'timer_end_ts': _safe_float(data.get('timer_end_ts', '')) or None,
        'remaining_seconds': int(remaining) if remaining else None,
        'total_focus': int(data.get('total_focus', 0)),
    }


# ── Agent context ──

def get_agent_context(user_id: int) -> list[dict]:
    """获取督学对话上下文（最近 10 轮）。"""
    r = _get_redis()
    raw = r.get(_agent_ctx_key(user_id))
    if not raw:
        return []
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return []


def append_agent_context(user_id: int, entry: dict, max_len: int = 20):
    """追加一条督学对话记录。"""
    r = _get_redis()
    ctx = get_agent_context(user_id)
    ctx.append(entry)
    if len(ctx) > max_len:
        ctx = ctx[-max_len:]
    r.set(_agent_ctx_key(user_id), json.dumps(ctx, ensure_ascii=False))
    r.expire(_agent_ctx_key(user_id), 3600)


# ── F5: 督学 Agent 数据查询 ──

def get_today_focus_stats(user_id: int) -> dict:
    """获取今日累计专注统计（从 DB 查询已结束的会话）。

    返回: {sessions_count, total_focus_minutes, yesterday_total_minutes, trend}
    """
    from django.utils import timezone
    from datetime import timedelta

    today = timezone.localdate()
    yesterday = today - timedelta(days=1)

    def _day_stats(day):
        from study_room.models import StudySession
        sessions = StudySession.objects.filter(
            user_id=user_id,
            status='ended',
            ended_at__date=day,
        )
        count = sessions.count()
        total_secs = sum(s.total_focus_seconds or 0 for s in sessions)
        return count, total_secs

    today_count, today_secs = _day_stats(today)
    yesterday_count, yesterday_secs = _day_stats(yesterday)

    today_mins = today_secs // 60
    yesterday_mins = yesterday_secs // 60

    if yesterday_mins == 0:
        trend = "up" if today_mins > 0 else "neutral"
    else:
        diff = today_mins - yesterday_mins
        if diff > 0:
            trend = "up"
        elif diff < 0:
            trend = "down"
        else:
            trend = "neutral"

    # 同时加入当前活跃会话的已计时长
    active = get_session(user_id)
    current_elapsed = 0
    if active and active.get('status') == 'active':
        import time
        timer_end = active.get('timer_end_ts')
        if timer_end:
            duration_secs = active.get('duration', 25) * 60
            remaining = max(0, timer_end - time.time())
            current_elapsed = max(0, duration_secs - int(remaining))

    return {
        'current_session': active,
        'current_elapsed_seconds': current_elapsed,
        'today_sessions_count': today_count,
        'today_total_focus_minutes': today_mins + (current_elapsed // 60),
        'yesterday_total_focus_minutes': yesterday_mins,
        'trend': trend,
    }


def get_focus_history(user_id: int, days: int = 7) -> list[dict]:
    """获取最近 N 天的每日专注汇总。

    返回: [{date, focus_minutes, sessions_count}, ...]
    """
    from django.utils import timezone
    from datetime import timedelta

    today = timezone.localdate()
    start_date = today - timedelta(days=days - 1)

    from study_room.models import StudySession
    from django.db.models import Sum, Count
    from django.db.models.functions import TruncDate

    qs = (
        StudySession.objects
        .filter(
            user_id=user_id,
            status='ended',
            ended_at__date__gte=start_date,
        )
        .annotate(day=TruncDate('ended_at'))
        .values('day')
        .annotate(total_secs=Sum('total_focus_seconds'), count=Count('id'))
        .order_by('day')
    )

    results_by_day = {}
    for row in qs:
        day_str = row['day'].isoformat() if row['day'] else None
        if day_str:
            results_by_day[day_str] = {
                'date': day_str,
                'focus_minutes': (row['total_secs'] or 0) // 60,
                'sessions_count': row['count'],
            }

    # 补齐没有数据的日期
    history = []
    for i in range(days):
        d = start_date + timedelta(days=i)
        ds = d.isoformat()
        if ds in results_by_day:
            history.append(results_by_day[ds])
        else:
            history.append({
                'date': ds,
                'focus_minutes': 0,
                'sessions_count': 0,
            })

    return history
