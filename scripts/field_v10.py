#!/usr/bin/env python3
"""
Field v10: 前置解锁 + 进度 × 掌握度损失函数

真实场景：
- KP 按前置关系排列，前置 K > θ 才能解锁下游
- 每天固定小预算（不是 budget²）
- 目标：推进深度 × 掌握度，不是平均 K

对比：FSRS vs Field(v6公式) vs Greedy
"""
import json, math, time, random, numpy as np
from collections import defaultdict
from scipy.sparse import csr_matrix
from collections import deque

# ═══ 参数 ═══
ALPHA   = 0.015
BETA_A  = 0.5
GAMMA   = 0.3
ETA     = 0.05
N_STUDENTS = 500
N_DAYS = 150
DAILY_BUDGET = 5         # ★ 固定每天 5 次复习（紧预算）
UNLOCK_THRESHOLD = 0.6   # ★ 前置 K > 0.6 才能解锁
INIT_K = 0.25             # 新解锁 KP 初始掌握度较低
EXAM_INTERVAL = 20
EXAM_COVERAGE = 0.3
BASE_DECAY = 0.005
DAY_NOISE = 0.01

# ═══ 加载图 ═══
with open('cfa_tree.json') as f:
    data = json.load(f)
nodes = data['nodes']
kps = [n for n in nodes if n.get('level') == 'kp']
kp_ids = [n['id'] for n in kps]
id2i = {kid: i for i, kid in enumerate(kp_ids)}
n = len(kps)

# 构建邻接
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

neighbors = {}
for i in range(n):
    nb = []
    for j in range(n):
        w = W[i, j]
        if w > 0:
            nb.append((j, w))
    neighbors[i] = nb

# ═══ 前置依赖：用 parent_id 构建 unlock graph ═══
# 节点依赖其 parent（先学父节点才能学子节点）
prereqs = defaultdict(list)  # i → [需要先解锁的 KP 列表]
dependents = defaultdict(list)  # i → [依赖 i 的 KP 列表]
id_to_node = {}
for nd in nodes:
    kid = nd['id']
    if kid in id2i:
        id_to_node[kid] = nd

for nd in nodes:
    kid = nd['id']
    pid = nd.get('parent_id')
    if kid in id2i and pid and pid in id2i:
        prereqs[id2i[kid]].append(id2i[pid])
        dependents[id2i[pid]].append(id2i[kid])

# 章节结构：按 parent chain 计算深度/章节
depth = {}
def get_depth(i):
    if i in depth:
        return depth[i]
    if not prereqs[i]:
        depth[i] = 0
        return 0
    d = 1 + max(get_depth(p) for p in prereqs[i])
    depth[i] = d
    return d

for i in range(n):
    get_depth(i)

max_depth = max(depth.values()) if depth else 0
print(f'n={n} edges={len(dat)} max_depth={max_depth}')
print(f'DAILY_BUDGET={DAILY_BUDGET} THRESHOLD={UNLOCK_THRESHOLD}')


def check_unlock(i, K):
    """检查所有前置 KP 是否达到阈值"""
    for p in prereqs[i]:
        if K[p] < UNLOCK_THRESHOLD:
            return False
    return True


def run_sim(sched, seed):
    K = np.zeros(n)
    u = np.zeros(n)
    S = np.ones(n) * 1.5
    last = np.full(n, -1.0)

    np.random.seed(seed % (2**31))
    random.seed(seed % (2**31))

    unlocked = set()
    reached = set()     # 曾经解锁过的（衡量深度）
    newly_unlocked = []  # 待初始化的 KP

    # 初始解锁：所有无前置的根 KP
    for i in range(n):
        if not prereqs[i]:
            unlocked.add(i)
            reached.add(i)
            K[i] = INIT_K
            u[i] = INIT_K

    cumul = 0.0
    cumul_days = 0

    for day in range(N_DAYS):
        # ── 检查新解锁 ──
        for i in range(n):
            if i not in unlocked and check_unlock(i, K):
                newly_unlocked.append(i)

        for i in newly_unlocked:
            unlocked.add(i)
            reached.add(i)
            K[i] = INIT_K
            u[i] = INIT_K
            if sched == 'fsrs':
                last[i] = -1
                S[i] = 1.5
        newly_unlocked.clear()

        # ── 统一衰减 ──
        K *= (1 - ALPHA - BASE_DECAY)
        K += np.random.normal(0, DAY_NOISE, n)
        K = np.clip(K, 0, 1)

        if random.random() > 0.85:
            continue

        eligible = sorted(unlocked)
        if not eligible:
            continue

        budget = DAILY_BUDGET

        # ── 选题（只选一次，不循环）──
        if sched == 'greedy':
            scores = [1 - u[i] for i in eligible]
        elif sched == 'field':
            scores = []
            for i in eligible:
                fb = sum(w * (1 - u[j]) for j, w in neighbors[i]) if neighbors[i] else 0.0
                scores.append((1 - u[i]) * (1.0 + BETA_A * fb))
        else:  # fsrs
            scores = []
            for i in eligible:
                if last[i] < 0:
                    scores.append(3.0)
                else:
                    el = max(0.1, day - last[i])
                    R = math.exp(-((el / max(S[i], 0.01)) ** 1.2))
                    scores.append(1 - R)

        top = sorted(zip(eligible, scores), key=lambda x: -x[1])[:budget]

        # ── 复习 ──
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

        # ── 考试 ──
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

    # ═══ 指标 ═══
    # 1. 深度：解锁比例
    depth_ratio = len(reached) / n

    # 2. 掌握度：已解锁 KP 的平均 K
    if unlocked:
        final_mastery = float(np.mean([K[i] for i in unlocked]))
    else:
        final_mastery = 0.0

    # 3. 综合分数：深度的平方 × 掌握度（鼓励深度推进）
    #    深度更重要（解锁更多章节），但浅掌握也不行
    composite = depth_ratio * depth_ratio * final_mastery

    # 4. 其他指标
    avg_cumul = cumul / max(1, cumul_days)
    max_section = max(depth[i] for i in reached) if reached else 0

    return {
        'final_mastery': final_mastery,
        'depth_ratio': depth_ratio,
        'composite': composite,
        'avg_cumul': avg_cumul,
        'max_section': max_section,
        'n_reached': len(reached),
    }


# ═══ 跑 ═══
t0 = time.time()
results = {}

for sched in ['fsrs', 'greedy', 'field']:
    all_res = defaultdict(list)
    for i in range(N_STUDENTS):
        r = run_sim(sched, 10000 + i)
        for k, v in r.items():
            all_res[k].append(v)

    agg = {k: (np.mean(v), np.std(v)) for k, v in all_res.items()}
    results[sched] = agg

    print(f"\n{sched:>8s}:")
    print(f"  composite     = {agg['composite'][0]:.4f} ±{agg['composite'][1]:.4f}")
    print(f"  depth_ratio   = {agg['depth_ratio'][0]:.4f} ({agg['n_reached'][0]:.0f}/{n} KPs)")
    print(f"  max_section   = {agg['max_section'][0]:.1f}/{max_depth}")
    print(f"  final_mastery = {agg['final_mastery'][0]:.4f}")
    print(f"  avg_cumul     = {agg['avg_cumul'][0]:.4f}", flush=True)

print(f"\n{'='*60}")
fsrs_c = results['fsrs']['composite'][0]
greedy_c = results['greedy']['composite'][0]
field_c = results['field']['composite'][0]

print(f"  Field  vs FSRS:   composite Δ={field_c-fsrs_c:+.4f}  ({(field_c/fsrs_c-1)*100:+.1f}%)")
print(f"  Greedy vs FSRS:   composite Δ={greedy_c-fsrs_c:+.4f}")
print(f"  Field  vs Greedy: composite Δ={field_c-greedy_c:+.4f}")

fsrs_d = results['fsrs']['depth_ratio'][0]
field_d = results['field']['depth_ratio'][0]
fsrs_m = results['fsrs']['final_mastery'][0]
field_m = results['field']['final_mastery'][0]
print(f"\n  Depth:  FSRS={fsrs_d:.4f}  Field={field_d:.4f}  Δ={field_d-fsrs_d:+.4f}")
print(f"  Mastery: FSRS={fsrs_m:.4f}  Field={field_m:.4f}  Δ={field_m-fsrs_m:+.4f}")

print(f"\nTotal: {time.time()-t0:.0f}s")
