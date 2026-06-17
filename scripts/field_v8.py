#!/usr/bin/env python3
"""
Field v8: 修正线性系统方向 + 状态依赖 + 扫 η_eff
v7 bug: 用了 W⊤（反向）而非 W（正向级联）
v8 fix: (I - η_eff·W)⁻¹ × urgency，正向传播
  再加 K_i 状态依赖：级联收益 = K_i × downstream_urgency
"""
import json, math, time, random, numpy as np
from collections import defaultdict
from scipy.sparse import csr_matrix, eye
from scipy.sparse.linalg import bicgstab
from collections import deque

# ═══ 参数 ═══
ALPHA   = 0.02       # 统一日衰减率
ETA     = 0.05       # η 转移强度
GAMMA   = 0.3        # 复习增益
N_STUDENTS = 300
N_DAYS = 150
BUDGET_PER_KP = 35   # 每 35 个已解锁 KP 配 1 次复习
BUDGET_MAX = 10
UNLOCK_EVERY = 15
KPS_PER_UNLOCK = 20
INIT_K = 0.3
EXAM_INTERVAL = 30
EXAM_COVERAGE = 0.3
DAY_NOISE = 0.02
BASE_DECAY = 0.005

# ═══ 加载图 ═══
with open('cfa_tree.json') as f:
    data = json.load(f)
nodes = data['nodes']
kps = [n for n in nodes if n.get('level') == 'kp']
kp_ids = [n['id'] for n in kps]
id2i = {kid: i for i, kid in enumerate(kp_ids)}
n = len(kps)

adj = defaultdict(list)
for nd in nodes:
    pid = nd.get('parent_id')
    if pid and nd['id'] in id2i and pid in id2i:
        adj[nd['id']].append((pid, 0.8))
        adj[pid].append((nd['id'], 0.8))
cbp = defaultdict(list)
for nd in nodes:
    pid = nd.get('parent_id')
    if pid and nd['id'] in id2i:
        cbp[pid].append(nd['id'])
for s in cbp.values():
    for i in range(len(s)):
        for j in range(i + 1, len(s)):
            adj[s[i]].append((s[j], 0.3))
            adj[s[j]].append((s[i], 0.3))
n2id = {nd['name']: nd['id'] for nd in kps}
with open('cfa_llm_edges.json') as f:
    llm = json.load(f)
for e in llm:
    s = n2id.get(e.get('source_name', ''))
    t = n2id.get(e.get('target_name', ''))
    if s and t and s in id2i and t in id2i:
        adj[s].append((t, float(e.get('weight', 0.5))))

row, col, dat = [], [], []
for sk, ns in adj.items():
    if sk in id2i:
        for tk, w in ns:
            if tk in id2i:
                row.append(id2i[sk])
                col.append(id2i[tk])
                dat.append(w)
W = csr_matrix((dat, (row, col)), shape=(n, n))
print(f'n={n} edges={len(dat)}')

neighbors = {}
for i in range(n):
    nb = []
    for j in range(n):
        w = W[i, j]
        if w > 0:
            nb.append((j, w))
    neighbors[i] = nb

indeg = np.zeros(n)
for i in range(n):
    for j, _ in neighbors[i]:
        indeg[j] += 1
q = deque([i for i in range(n) if indeg[i] == 0])
syllabus = []
while q:
    i = q.popleft()
    syllabus.append(i)
    for j, _ in neighbors[i]:
        indeg[j] -= 1
        if indeg[j] == 0:
            q.append(j)
missing = set(range(n)) - set(syllabus)
syllabus.extend(missing)
batches = [syllabus[i:i + KPS_PER_UNLOCK] for i in range(0, len(syllabus), KPS_PER_UNLOCK)]
print(f'batches={len(batches)}')


def compute_global_influence(urgency, K_vec, W, eta_eff):
    """
    influence = (I - η_eff·W)⁻¹ × urgency
    正向传播：urgency 沿边 i→j 传播给下游
    再加状态依赖：级联效应 ∝ K_i（只有掌握度高的 KP 才能有效传播）
    """
    # 状态依赖权重：cascade_through_i ∝ K_i
    # urgency_weighted = urgency ⊙ K_vec  （将 K_vec 融入 urgency，低掌握度 KP 的 urgency 不打折）
    # 但在影响传播中，K_i 决定传播强度
    # 近似：influence = urgency + η_eff × (K_vec ⊙ (W × influence))
    # 即只有 K_i 高时，审查 i 的级联才能真正传播
    # 简化：influence = (I - η_eff · diag(K) · W)⁻¹ × urgency

    from scipy.sparse import diags
    K_diag = diags(K_vec, 0, shape=(n, n))
    A = eye(n, format='csr') - eta_eff * K_diag.dot(W)

    influence, exit_code = bicgstab(A, urgency, rtol=1e-6, maxiter=100)
    if exit_code != 0:
        # fallback: power iteration
        influence = urgency.copy()
        for _ in range(5):
            influence = urgency + eta_eff * K_vec * W.dot(influence)
            influence = np.clip(influence, 0, None)
    return influence


def run_sim(sched, eta_eff, seed):
    """统一底盘仿真"""
    K = np.zeros(n)
    u = np.zeros(n)
    if sched == 'fsrs':
        S = np.ones(n) * 1.5
        last = np.full(n, -1.0)

    np.random.seed(seed % (2**31))
    random.seed(seed % (2**31))
    unlocked = set()
    cumul = 0.0
    cumul_days = 0
    next_batch = 0

    for day in range(N_DAYS):
        if day % UNLOCK_EVERY == 0 and next_batch < len(batches):
            for i in batches[next_batch]:
                if i < n:
                    unlocked.add(i)
                    K[i] = INIT_K
                    u[i] = INIT_K
                    if sched == 'fsrs':
                        last[i] = -1
                        S[i] = 1.5
            next_batch += 1

        K *= (1 - ALPHA - BASE_DECAY)
        K += np.random.normal(0, DAY_NOISE, n)
        K = np.clip(K, 0, 1)

        if random.random() > 0.85:
            continue

        budget = min(BUDGET_MAX, max(1, (len(unlocked) + BUDGET_PER_KP - 1) // BUDGET_PER_KP))
        eligible = sorted(unlocked)
        if not eligible or budget == 0:
            continue

        for _ in range(budget):
            if not eligible:
                break

            if sched == 'fsrs':
                scores = []
                for i in eligible:
                    if last[i] < 0:
                        scores.append(3.0)
                    else:
                        el = max(0.1, day - last[i])
                        R = math.exp(-((el / max(S[i], 0.01)) ** 1.2))
                        scores.append(1 - R)
            elif sched in ('field_local', 'field_global'):
                urgency = np.array([1 - u[i] for i in range(n)])

                if sched == 'field_global':
                    influence = compute_global_influence(urgency, u, W, eta_eff)
                    scores = [influence[i] for i in eligible]
                else:
                    beta_a = 1.0
                    scores = []
                    for i in eligible:
                        fb = sum(w * (1 - u[j]) for j, w in neighbors[i]) if neighbors[i] else 0.0
                        scores.append((1 - u[i]) * (1.0 + beta_a * fb))
            else:
                raise ValueError(f"unknown sched: {sched}")

            top = sorted(zip(eligible, scores), key=lambda x: -x[1])[:budget]

            for i, _ in top:
                K[i] += GAMMA * (1 - K[i])
                for j, w in neighbors[i]:
                    K[j] += ETA * w * K[i] * (1 - K[j])
                K = np.clip(K, 0, 1)
                u[i] = K[i]
                if sched == 'fsrs':
                    r = int(max(1, min(4, K[i] * 5 - 1)))
                    So = S[i]
                    S[i] = max(1, min(365, (2.5 + 0.5 * (r - 2)) if So <= 1.5 else So * (1 + 0.15 * (0.5 + 0.25 * r))))
                    last[i] = day

        if day > 0 and day % EXAM_INTERVAL == 0:
            testable = sorted(unlocked)
            n_test = max(3, int(len(testable) * EXAM_COVERAGE))
            tested = random.sample(testable, min(n_test, len(testable)))
            for i in tested:
                if random.random() < K[i]:
                    K[i] += 0.05 * (1 - K[i])
                    u[i] = K[i]
                K = np.clip(K, 0, 1)

        if unlocked:
            cumul += float(np.mean([K[i] for i in unlocked]))
            cumul_days += 1

    final = float(np.mean([K[i] for i in unlocked])) if unlocked else 0.0
    avg_cumul = cumul / max(1, cumul_days)
    return final, avg_cumul


# ═══ 跑 ═══
# 扫 eta_eff: 全局影响的级联强度
ETA_EFFS = [0.005, 0.01, 0.02, 0.03, 0.05, 0.1]

t0 = time.time()

# 先跑 baseline
results = {}
for sched in ['fsrs', 'field_local']:
    finals, cumuls = [], []
    for i in range(N_STUDENTS):
        f, c = run_sim(sched, 0.0, 10000 + i)
        finals.append(f)
        cumuls.append(c)
    results[sched] = {'final': np.mean(finals), 'cumul': np.mean(cumuls)}
    print(f"  {sched:>14s}: final={results[sched]['final']:.4f}  cumul={results[sched]['cumul']:.4f}", flush=True)

# 扫 field_global
best = None
for ee in ETA_EFFS:
    finals, cumuls = [], []
    for i in range(N_STUDENTS):
        f, c = run_sim('field_global', ee, 10000 + i)
        finals.append(f)
        cumuls.append(c)
    f_mean = np.mean(finals)
    c_mean = np.mean(cumuls)
    vs_fsrs = f_mean - results['fsrs']['final']
    results[f'global_{ee}'] = {'final': f_mean, 'cumul': c_mean}
    star = '⭐' if vs_fsrs > 0.03 else ('+' if vs_fsrs > 0 else '-')
    print(f"  global η_eff={ee:.3f}: final={f_mean:.4f}  cumul={c_mean:.4f}  vsFSRS={vs_fsrs:+.4f}{star}",
          flush=True)
    if best is None or f_mean > best[0]:
        best = (f_mean, ee)

print(f"\n{'='*50}")
print(f"  FSRS:        {results['fsrs']['final']:.4f}")
print(f"  Field local: {results['field_local']['final']:.4f} (vFSRS {results['field_local']['final']-results['fsrs']['final']:+.4f})")
if best:
    print(f"  Field global best η_eff={best[1]:.3f}: {best[0]:.4f} (vFSRS {best[0]-results['fsrs']['final']:+.4f})")
    # 报告所有扫参
    print(f"\n  Sweep:")
    for ee in ETA_EFFS:
        vs = results[f'global_{ee}']['final'] - results['fsrs']['final']
        print(f"    η_eff={ee:.3f}: {results[f'global_{ee}']['final']:.4f} vsFSRS={vs:+.4f}")
print(f"Total: {time.time()-t0:.0f}s")
