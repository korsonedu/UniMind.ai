#!/usr/bin/env python3
"""
Field v14: 真实学习习惯

规则：
1. 已学 KP：urgency = (1-K)/K → K=0.2时urgency=4，K=0.8时=0.25
2. 新学 KP：吸引力 = 1.5（相当于 K≈0.4 的复习优先级）
3. 前置门槛：前置 KP 的 K < 0.4 → 下游不可解锁
4. 综合目标：depth × mastery（深且精）
"""
import json, math, time, random, numpy as np
from collections import defaultdict, deque
from scipy.sparse import csr_matrix

ALPHA   = 0.015
BETA_A  = 0.5
GAMMA   = 0.3
ETA     = 0.05
N_STUDENTS = 300
N_DAYS = 150
DAILY_BUDGET = 8
INIT_K = 0.25
UNLOCK_PREREQ_THRESHOLD = 0.4   # ★ 前置 K > 此值才能学下游
EXAM_INTERVAL = 20
EXAM_COVERAGE = 0.3
BASE_DECAY = 0.005
DAY_NOISE = 0.01

# ═══ 加载图 ═══
with open('math_tree.json') as f:
    data = json.load(f)
nodes = data['nodes']
kps = [n for n in nodes if n.get('level') == 'kp']
kp_ids = [n['id'] for n in kps]
id2i = {kid: i for i, kid in enumerate(kp_ids)}
n2id = {nd['name']: nd['id'] for nd in kps}
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
with open('math_llm_edges.json') as f:
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

# ═══ 前置链 ═══
pair_dir = {}
for e in llm:
    if e.get('edge_type') != 'prerequisite':
        continue
    s = n2id.get(e.get('source_name', ''))
    t = n2id.get(e.get('target_name', ''))
    if not (s and t and s in id2i and t in id2i):
        continue
    si, ti = id2i[s], id2i[t]
    w = float(e.get('weight', 0.5))
    pair = tuple(sorted([si, ti]))
    if pair not in pair_dir or w > pair_dir[pair][0]:
        pair_dir[pair] = (w, (si, ti))

prereqs = defaultdict(list)
dependents = defaultdict(list)
for (a, b), (w, (src, dst)) in pair_dir.items():
    prereqs[dst].append(src)
    dependents[src].append(dst)

# 去环
indeg_arr = np.zeros(n)
for i in prereqs:
    indeg_arr[i] = len(prereqs[i])
q_dag = deque([i for i in range(n) if indeg_arr[i] == 0])
topo = []
while q_dag:
    i = q_dag.popleft()
    topo.append(i)
    for j in dependents[i]:
        indeg_arr[j] -= 1
        if indeg_arr[j] == 0:
            q_dag.append(j)
for i in set(range(n)) - set(topo):
    for p in list(prereqs[i]):
        dependents[p].remove(i)
    prereqs[i].clear()

depth_map = {}
def get_depth(i, visited=None):
    if i in depth_map:
        return depth_map[i]
    if visited is None:
        visited = set()
    if i in visited:
        return 0
    visited.add(i)
    if not prereqs[i]:
        depth_map[i] = 0
        return 0
    d = 1 + max((get_depth(p, visited) for p in prereqs[i]), default=0)
    depth_map[i] = d
    return d

max_chain = max((get_depth(i) for i in range(n)), default=0)
n_roots = sum(1 for i in range(n) if not prereqs[i])
n_prereq = sum(1 for i in range(n) if prereqs[i])

print(f'n={n} roots={n_roots} with_prereq={n_prereq} max_chain={max_chain}')
print(f'DAILY_BUDGET={DAILY_BUDGET} UNLOCK_THRESHOLD={UNLOCK_PREREQ_THRESHOLD}')


def is_available(i, learned, K):
    """前置 KP 必须已学 且 掌握度达标"""
    if not prereqs[i]:
        return True
    for p in prereqs[i]:
        if not learned[p] or K[p] < UNLOCK_PREREQ_THRESHOLD:
            return False
    return True


def urgency(K_val):
    """复习紧急度：(1-K)/K。K=0.2→4, K=0.5→1, K=0.8→0.25"""
    if K_val <= 0.01:
        return 10.0
    return (1.0 - K_val) / K_val


def run_sim(sched, seed):
    K = np.zeros(n)
    u = np.zeros(n)
    learned = np.zeros(n, dtype=bool)
    S = np.ones(n) * 1.5
    last = np.full(n, -1.0)

    np.random.seed(seed % (2**31))
    random.seed(seed % (2**31))

    cumul = 0.0
    cumul_days = 0

    for day in range(N_DAYS):
        # ── 衰减 ──
        K *= (1 - ALPHA - BASE_DECAY)
        K += np.random.normal(0, DAY_NOISE, n)
        K = np.clip(K, 0, 1)

        if random.random() > 0.85:
            continue

        # ── 候选 ──
        eligible = []
        for i in range(n):
            if learned[i]:
                eligible.append(i)
            elif is_available(i, learned, K):
                eligible.append(i)

        if not eligible:
            continue

        # ── 算分 ──
        NEW_KP_ATTRACTION = 1.5  # 相当于 K≈0.4 的复习优先级

        if sched == 'field':
            scores = []
            for i in eligible:
                if not learned[i]:
                    # 新学吸引力 + 邻居级联价值
                    fb = sum(w * urgency(u[j]) for j, w in neighbors[i] if learned[j]) if neighbors[i] else 0.0
                    scores.append(NEW_KP_ATTRACTION * (1.0 + BETA_A * fb))
                else:
                    fb = sum(w * urgency(u[j]) for j, w in neighbors[i]) if neighbors[i] else 0.0
                    scores.append(urgency(u[i]) * (1.0 + BETA_A * fb))
        else:  # fsrs
            scores = []
            for i in eligible:
                if not learned[i]:
                    scores.append(NEW_KP_ATTRACTION)
                else:
                    scores.append(urgency(K[i]))

        top = sorted(zip(eligible, scores), key=lambda x: -x[1])[:DAILY_BUDGET]

        for i, _ in top:
            was_learned = learned[i]

            if not learned[i]:
                learned[i] = True
                K[i] = INIT_K
                u[i] = INIT_K

            K[i] += GAMMA * (1 - K[i])
            for j, w in neighbors[i]:
                K[j] += ETA * w * K[i] * (1 - K[j])
            K = np.clip(K, 0, 1)
            u[i] = K[i]

            if sched == 'fsrs':
                if was_learned:
                    r = int(max(1, min(4, K[i] * 5 - 1)))
                    So = S[i]
                    S[i] = max(1, min(365, (2.5 + 0.5 * (r - 2)) if So <= 1.5 else So * (1 + 0.15 * (0.5 + 0.25 * r))))
                last[i] = day

        if day > 0 and day % EXAM_INTERVAL == 0:
            testable = [i for i in range(n) if learned[i]]
            if testable:
                n_test = max(3, int(len(testable) * EXAM_COVERAGE))
                tested = random.sample(testable, min(n_test, len(testable)))
                for i in tested:
                    if random.random() < K[i]:
                        K[i] += 0.05 * (1 - K[i])
                        u[i] = K[i]
                    K = np.clip(K, 0, 1)

        learned_list = [i for i in range(n) if learned[i]]
        if learned_list:
            cumul += float(np.mean([K[i] for i in learned_list]))
            cumul_days += 1

    learned_list = [i for i in range(n) if learned[i]]
    if learned_list:
        final_mastery = float(np.mean([K[i] for i in learned_list]))
        max_depth = max((depth_map.get(i, 0) for i in learned_list), default=0)
        n_learned = len(learned_list)
    else:
        final_mastery = 0.0
        max_depth = 0
        n_learned = 0

    return {
        'final_mastery': final_mastery,
        'n_learned': n_learned,
        'depth_ratio': n_learned / n,
        'composite': (n_learned / n) * final_mastery,
        'avg_cumul': cumul / max(1, cumul_days),
        'max_depth': max_depth,
    }


# ═══ 跑 ═══
t0 = time.time()
results = {}

for sched in ['fsrs', 'field']:
    all_res = defaultdict(list)
    for i in range(N_STUDENTS):
        r = run_sim(sched, 10000 + i)
        for k, v in r.items():
            all_res[k].append(v)

    agg = {k: (np.mean(v), np.std(v)) for k, v in all_res.items()}
    results[sched] = agg

    print(f"\n{sched:>8s}:")
    print(f"  composite     = {agg['composite'][0]:.4f} ±{agg['composite'][1]:.4f}")
    print(f"  n_learned     = {agg['n_learned'][0]:.0f}/{n}")
    print(f"  max_depth     = {agg['max_depth'][0]:.1f}/{max_chain}")
    print(f"  final_mastery = {agg['final_mastery'][0]:.4f}", flush=True)

fsrs_c = results['fsrs']['composite'][0]
field_c = results['field']['composite'][0]

print(f"\n{'='*60}")
print(f"  Field vs FSRS: composite Δ={field_c-fsrs_c:+.4f}  ({(field_c/fsrs_c-1)*100:+.1f}%)")
print(f"  N learned: FSRS={results['fsrs']['n_learned'][0]:.0f}  Field={results['field']['n_learned'][0]:.0f}")
print(f"  Mastery:   FSRS={results['fsrs']['final_mastery'][0]:.4f}  Field={results['field']['final_mastery'][0]:.4f}")
print(f"Total: {time.time()-t0:.0f}s")
