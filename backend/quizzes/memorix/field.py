"""
Memorix-Field Diffusion State Estimator.

基于 field-paper.md §2.2：维护 per-user 知识点激活向量 u，
每次成功复习后即时向邻居传播，每天一次全局扩散步。

核心方程:  du/dt = -α·u + βe·L·u
评分公式:  score_i = (1 - u_i) × (1 + βa × Σ_j w_ij × (1 - u_j))

参数自进化: 每机构独立参数集，每周扰动一个参数 ±10%，
对比 Brier score 决定接受/回退。Redis 热缓存 + DB 持久化 + settings 兜底。
"""
import json
import logging
from collections import defaultdict
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

# ── Redis key patterns ──
FIELD_U_PREFIX = "memorix:field:u"             # per-user hash: {kp_id: u_value}
FIELD_LAST_DIFFUSION = "memorix:field:last"     # hash: {user_id: iso_timestamp}
FIELD_ADJ_IN_KEY = "memorix:field:adj_in"       # incoming adjacency cache
FIELD_PARAMS_KEY = "memorix:field:params"        # hash: {inst_id|'global': json}

# ── 默认参数（论文 §4.1 最优值）──
DEFAULT_DECAY = 0.02       # α:  自然衰减率/天
DEFAULT_BETA_E = 0.005     # βe: 扩散强度（§4.3: 0.001 已饱和）
DEFAULT_BETA_A = 0.5       # βa: 评分放大系数
DEFAULT_ETA = 0.02         # η:  复习转移系数

# 安全边界（防止自进化跑偏）
SAFE_BOUNDS = {
    'decay':   (0.005, 0.10),
    'beta_e':  (0.0005, 0.02),
    'beta_a':  (0.1, 2.0),
    'eta':     (0.005, 0.08),
}

# 每日扩散只处理近 N 天活跃用户
ACTIVE_USER_WINDOW_DAYS = 7
# 两次扩散最小间隔（小时）
MIN_DIFFUSION_INTERVAL_H = 20
# 参数缓存 TTL（秒）
PARAMS_CACHE_TTL = 300


# ═══════════════════════════════════════════
# Redis helpers
# ═══════════════════════════════════════════

def _get_redis():
    try:
        from django_redis import get_redis_connection
        return get_redis_connection("default")
    except Exception:
        return None


def _get_param(name, default):
    return float(getattr(settings, name, default))


def _u_key(user_id: int) -> str:
    return f"{FIELD_U_PREFIX}:{user_id}"


# ═══════════════════════════════════════════
# 参数解析（Redis 热缓存 → DB → settings 兜底）
# ═══════════════════════════════════════════

def get_field_params(institution_id=None) -> dict:
    """
    获取 Field 参数，按机构隔离。

    查询链：Redis 缓存 → MemorixFieldConfig DB → settings 全局默认。
    结果缓存在 Redis 5 分钟。
    """
    auto_tune = getattr(settings, 'MEMORIX_FIELD_AUTO_TUNE_ENABLED', False)

    if not auto_tune or not institution_id:
        return _global_params()

    r = _get_redis()
    cache_key = str(institution_id)

    # 1. Redis 热缓存
    if r:
        raw = r.hget(FIELD_PARAMS_KEY, cache_key)
        if raw:
            try:
                return json.loads(raw.decode() if isinstance(raw, bytes) else raw)
            except (json.JSONDecodeError, TypeError):
                pass

    # 2. DB
    try:
        from quizzes.models import MemorixFieldConfig
        config = MemorixFieldConfig.objects.only(
            'decay', 'beta_e', 'beta_a', 'eta'
        ).get(institution_id=institution_id)
        params = {
            'decay': config.decay,
            'beta_e': config.beta_e,
            'beta_a': config.beta_a,
            'eta': config.eta,
        }
    except Exception:
        params = _global_params()

    # 3. 写回 Redis 缓存
    if r:
        r.hset(FIELD_PARAMS_KEY, cache_key, json.dumps(params))

    return params


def _global_params() -> dict:
    return {
        'decay': _get_param('MEMORIX_FIELD_DECAY', DEFAULT_DECAY),
        'beta_e': _get_param('MEMORIX_FIELD_BETA_E', DEFAULT_BETA_E),
        'beta_a': _get_param('MEMORIX_FIELD_BETA_A', DEFAULT_BETA_A),
        'eta': _get_param('MEMORIX_FIELD_ETA', DEFAULT_ETA),
    }


def set_field_params(institution_id: int, params: dict):
    """更新机构参数：DB 持久化 + 清除 Redis 缓存。"""
    # 安全裁剪
    for key, (lo, hi) in SAFE_BOUNDS.items():
        if key in params:
            params[key] = max(lo, min(hi, params[key]))

    from quizzes.models import MemorixFieldConfig
    MemorixFieldConfig.objects.update_or_create(
        institution_id=institution_id,
        defaults={
            'decay': params.get('decay', DEFAULT_DECAY),
            'beta_e': params.get('beta_e', DEFAULT_BETA_E),
            'beta_a': params.get('beta_a', DEFAULT_BETA_A),
            'eta': params.get('eta', DEFAULT_ETA),
        },
    )

    # 清除 Redis 缓存
    invalidate_param_cache(institution_id)


def invalidate_param_cache(institution_id=None):
    """清除参数缓存。institution_id=None 时清全部。"""
    r = _get_redis()
    if not r:
        return
    if institution_id:
        r.hdel(FIELD_PARAMS_KEY, str(institution_id))
    else:
        r.delete(FIELD_PARAMS_KEY)


# ═══════════════════════════════════════════
# u 向量读写
# ═══════════════════════════════════════════

def get_u_vector(user_id: int) -> dict:
    """加载用户的 u 向量 {kp_id: u_value}，无数据返 {}。"""
    r = _get_redis()
    if not r:
        return {}
    raw = r.hgetall(_u_key(user_id))
    if not raw:
        return {}
    return {
        int(k.decode() if isinstance(k, bytes) else k): float(v.decode() if isinstance(v, bytes) else v)
        for k, v in raw.items()
    }


def set_u_vector(user_id: int, u: dict):
    """持久化 u 向量到 Redis。<= 0.001 的值不存储（节省空间）。"""
    r = _get_redis()
    if not r:
        return
    key = _u_key(user_id)
    payload = {str(kp): str(round(v, 6)) for kp, v in u.items() if v > 0.001}
    if payload:
        r.hset(key, mapping=payload)
    dead = [str(kp) for kp, v in u.items() if v <= 0.001]
    if dead:
        r.hdel(key, *dead)


def u_vector_exists(user_id: int) -> bool:
    r = _get_redis()
    if not r:
        return False
    return r.exists(_u_key(user_id)) > 0


# ═══════════════════════════════════════════
# 邻接表（incoming + outgoing）
# ═══════════════════════════════════════════

def _get_dynamic_edges(redis_conn) -> dict:
    """从 Redis 读取动态边 → {source_id: [(target_id, weight)]}。"""
    from quizzes.tasks import MEMORIX_DYNAMIC_EDGE_PREFIX
    dyn = defaultdict(list)
    cursor = 0
    while True:
        cursor, keys = redis_conn.scan(cursor, match=f"{MEMORIX_DYNAMIC_EDGE_PREFIX}:*", count=100)
        for key in keys:
            data = redis_conn.hgetall(key)
            if not data:
                continue
            try:
                src = int(data.get(b'source_id', 0))
                tgt = int(data.get(b'target_id', 0))
                w = float(data.get(b'weight', 0))
            except (ValueError, TypeError):
                continue
            if w > 0:
                dyn[src].append((tgt, w))
        if cursor == 0:
            break
    return dyn


def build_outgoing_adjacency() -> dict:
    """
    构建出边邻接表 {kp_id: [(neighbor_kp_id, weight)]}。
    合并 KnowledgeEdge 固定边 + Redis 动态边。
    """
    from quizzes.models import KnowledgeEdge

    adj = defaultdict(list)
    for edge in KnowledgeEdge.objects.filter(is_active=True).only('source_id', 'target_id', 'weight'):
        adj[edge.source_id].append((edge.target_id, float(edge.weight)))

    r = _get_redis()
    if r:
        try:
            for src, neighbors in _get_dynamic_edges(r).items():
                adj[src].extend(neighbors)
        except Exception:
            logger.warning("Field: Redis unavailable, using static edges only")

    return dict(adj)


def build_incoming_adjacency() -> dict:
    """
    构建入边邻接表 {kp_id: [(source_kp_id, weight)]}。
    用于每日扩散步的 Laplacian 计算，缓存 1 小时。
    """
    cached = cache.get(FIELD_ADJ_IN_KEY)
    if cached is not None:
        adj_in = defaultdict(list)
        for kp_id, sources in cached:
            adj_in[kp_id] = sources
        return dict(adj_in)

    from quizzes.models import KnowledgeEdge

    adj_in = defaultdict(list)
    for edge in KnowledgeEdge.objects.filter(is_active=True).only('source_id', 'target_id', 'weight'):
        adj_in[edge.target_id].append((edge.source_id, float(edge.weight)))

    r = _get_redis()
    if r:
        try:
            for src, neighbors in _get_dynamic_edges(r).items():
                for tgt, w in neighbors:
                    adj_in[tgt].append((src, w))
        except Exception:
            pass

    payload = [(kp_id, list(sources)) for kp_id, sources in adj_in.items()]
    cache.set(FIELD_ADJ_IN_KEY, payload, 3600)

    return dict(adj_in)


def invalidate_adjacency_caches():
    """KnowledgeEdge 变更时调用，清除邻接表缓存。"""
    from quizzes.services.memorix_scheduler import MEMORIX_ADJ_CACHE_KEY
    cache.delete(MEMORIX_ADJ_CACHE_KEY)
    cache.delete(FIELD_ADJ_IN_KEY)


# ═══════════════════════════════════════════
# 复习时传播
# ═══════════════════════════════════════════

def ensure_u_entry(user_id: int, kp_id: int, retrievability: float):
    """确保 KP 在用户 u 向量中有条目。首次出现时用 Weibull R(t) 初始化。"""
    u = get_u_vector(user_id)
    if kp_id not in u:
        u[kp_id] = max(0.0, min(1.0, retrievability))
        set_u_vector(user_id, u)


def propagate_review(user_id: int, kp_id: int, retrievability: float, institution_id=None):
    """
    成功复习 KP i 后，向邻居传播激活（按机构参数）。

    对每条出边 i→j，权重 w_ij：
        u_j += η × w_ij × u_i × (1 - u_j)

    论文 §2.1 物理模型：转移量与复习者的掌握度成正比。
    """
    params = get_field_params(institution_id)
    eta = params['eta']
    if eta <= 0:
        return

    ensure_u_entry(user_id, kp_id, retrievability)

    u = get_u_vector(user_id)
    u_i = u.get(kp_id, retrievability)
    if u_i <= 0.01:
        return

    adj_out = build_outgoing_adjacency()
    neighbors = adj_out.get(kp_id, [])
    if not neighbors:
        return

    modified = False
    for neighbor_kp, w in neighbors:
        if w <= 0:
            continue
        u_j = u.get(neighbor_kp, 0.0)
        delta = eta * w * u_i * max(0.0, 1.0 - u_j)
        if delta > 0.0001:
            u[neighbor_kp] = min(1.0, u_j + delta)
            modified = True

    if modified:
        set_u_vector(user_id, u)


# ═══════════════════════════════════════════
# 每日扩散
# ═══════════════════════════════════════════

def diffuse_user(user_id: int, institution_id=None) -> int:
    """
    对单个用户执行一次扩散步（按机构参数）。

    对每个 KP i：
        u_i_new = (1 - α - βe·deg_out(i)) × u_i + βe × Σ_{j→i} w_ji × u_j

    Returns: 扩散的 KP 数量，0 表示跳过。
    """
    params = get_field_params(institution_id)
    alpha = params['decay']
    beta_e = params['beta_e']

    u = get_u_vector(user_id)
    if not u:
        return 0

    # 检查上次扩散时间，避免短间隔重复
    r = _get_redis()
    if r:
        last_ts = r.hget(FIELD_LAST_DIFFUSION, str(user_id))
        if last_ts:
            try:
                last = timezone.datetime.fromisoformat(
                    last_ts.decode() if isinstance(last_ts, bytes) else last_ts
                )
                if timezone.now() - last < timedelta(hours=MIN_DIFFUSION_INTERVAL_H):
                    return 0
            except (ValueError, TypeError):
                pass

    adj_out = build_outgoing_adjacency()
    adj_in = build_incoming_adjacency()

    u_new = {}
    for kp_id, u_i in u.items():
        deg_out = sum(w for _, w in adj_out.get(kp_id, []))
        incoming = 0.0
        for src_id, w in adj_in.get(kp_id, []):
            incoming += w * u.get(src_id, 0.0)
        u_new_i = (1.0 - alpha - beta_e * deg_out) * u_i + beta_e * incoming
        u_new[kp_id] = max(0.0, min(1.0, u_new_i))

    set_u_vector(user_id, u_new)

    if r:
        r.hset(FIELD_LAST_DIFFUSION, str(user_id), timezone.now().isoformat())

    return len(u_new)


def _resolve_user_institution(user_id: int):
    """查用户所属机构 ID，缓存 5 分钟。"""
    cache_key = f"memorix:field:user_inst:{user_id}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.only('institution_id').get(id=user_id)
        inst_id = user.institution_id
    except Exception:
        inst_id = None

    cache.set(cache_key, inst_id, 300)
    return inst_id


def diffuse_all_active_users() -> dict:
    """
    对所有活跃用户的 u 向量执行每日扩散步。

    扫描 Redis 中所有 memorix:field:u:* 键，
    按用户所属机构使用对应参数。

    Returns: {"processed": N, "skipped": N}
    """
    r = _get_redis()
    if not r:
        return {"error": "Redis unavailable"}

    # 预加载所有机构参数（减少重复查询）
    processed = 0
    skipped = 0

    cursor = 0
    while True:
        cursor, keys = r.scan(cursor, match=f"{FIELD_U_PREFIX}:*", count=200)
        for key in keys:
            try:
                uid = int(key.decode().split(":")[-1] if isinstance(key, bytes) else key.split(":")[-1])
            except (ValueError, IndexError):
                continue
            inst_id = _resolve_user_institution(uid)
            count = diffuse_user(uid, institution_id=inst_id)
            if count > 0:
                processed += 1
            else:
                skipped += 1
        if cursor == 0:
            break

    logger.info("Field daily diffusion: %d users processed, %d skipped", processed, skipped)
    return {"processed": processed, "skipped": skipped}


# ═══════════════════════════════════════════
# 评分
# ═══════════════════════════════════════════

def compute_field_score(u: dict, kp_id, adj_out: dict, params: dict) -> float:
    """
    计算 Field 选题评分（按机构参数）。

    score_i = (1 - u_i) × (1 + βa × Σ_j w_ij × max(0, 1 - u_j))

    乘性形式：u_i 高 → score 低，无论邻居多弱。
    """
    beta_a = params.get('beta_a', DEFAULT_BETA_A)

    u_i = u.get(kp_id, 0.0)
    urgency = max(0.0, 1.0 - u_i)
    if urgency <= 0.001:
        return 0.0

    fb = 0.0
    for neighbor_kp, w in adj_out.get(kp_id, []):
        u_j = u.get(neighbor_kp, 0.0)
        fb += w * max(0.0, 1.0 - u_j)

    return urgency * (1.0 + beta_a * fb)
