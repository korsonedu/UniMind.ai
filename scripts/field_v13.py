#!/usr/bin/env python3
"""
Field v13: 用 math_llm_edges 的 prerequisite 边建前置链
- 去双向环（同对保留高权重方向）
- Kahn 去环验证
- 用高中数学树 614 KP
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

# 邻接（用于 Field 选题 + η 级联）
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

# ═══ ★ 前置链构建：从 LLM prerequisite 边，去环 ═══
prereq_edges = []
# 收集所有 prerequisite 边，去双向
pair_dir = {}  # (s,t) → (weight, dir)
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
    if pair not in pair_dir:
        pair_dir[pair] = (w, (si, ti))
    else:
        old_w, old_dir = pair_dir[pair]
        if w > old_w:
            # 新方向权重更高，替换
            pair_dir[pair] = (w, (si, ti))
        # 否则保留原方向

# 去重后建边
for (a, b), (w, (src, dst)) in pair_dir.items():
    prereq_edges.append((src, dst, w))

print(f'prereq edges after dedup: {len(prereq_edges)}')

# Kahn 去环
prereqs = defaultdict(list)
dependents = defaultdict(list)
indeg = np.zeros(n)
for src, dst, w in prereq_edges:
    prereqs[dst].append(src)
    dependents[src].append(dst)
    indeg[dst] += 1

q = deque([i for i in range(n) if indeg[i] == 0])
topo = []
while q:
    i = q.popleft()
    topo.append(i)
    for j in dependents[i]:
        indeg[j] -= 1
        if indeg[j] == 0:
            q.append(j)

# 不在 topo 里的→环中，删除这些节点的入边
in_cycle = set(range(n)) - set(topo)
removed = 0
for i in list(in_cycle):
    for p in list(prereqs[i]):
        if p in in_cycle:
            prereqs[i].remove(p)
            dependents[p].remove(i)
            removed += 1

# 重新 Kahn
indeg2 = np.zeros(n)
for i in prereqs:
    indeg2[i] = len(prereqs[i])
q = deque([i for i in range(n) if indeg2[i] == 0])
topo2 = []
while q:
    i = q.popleft()
    topo2.append(i)
    for j in dependents[i]:
        indeg2[j] -= 1
        if indeg2[j] == 0:
            q.append(j)

in_cycle2 = set(range(n)) - set(topo2)
if in_cycle2:
    # 仍有环，删所有环内节点的 prereq
    for i in in_cycle2:
        for p in list(prereqs[i]):
            dependents[p].remove(i)
        prereqs[i].clear()

# 最终统计
n_roots = sum(1 for i in range(n) if not prereqs[i])
n_prereq = sum(1 for i in range(n) if prereqs[i])

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
total_prereq_edges = sum(len(v) for v in prereqs.values())

print(f'n={n} roots={n_roots} with_prereq={n_prereq} max_chain={max_chain}')
print(f'prereq edges={total_prereq_edges} removed_cycles={removed} residual_cycle={len(in_cycle2)}')
print(f'DAILY_BUDGET={DAILY_BUDGET}')


def is_available(i, learned):
    if not prereqs[i]:
        return True
    return all(learned[p] for p in prereqs[i])


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
        # ── 标记可用 ──
        for i in range(n):
            if not learned[i] and is_available(i, learned):
                pass  # becomes eligible below

        # ── 衰减 ──
        K *= (1 - ALPHA - BASE_DECAY)
        K += np.random.normal(0, DAY_NOISE, n)
        K = np.clip(K, 0, 1)

        if random.random() > 0.85:
            continue

        # ── 候选：所有已学 + 所有可用未学 ──
        eligible = []
        for i in range(n):
            if learned[i]:
                eligible.append(i)
            elif is_available(i, learned):
                eligible.append(i)

        if not eligible:
            continue

        # ── 算分 ──
        if sched == 'field':
            scores = []
            for i in eligible:
                if not learned[i]:
                    fb = sum(w * (1 - u[j]) for j, w in neighbors[i] if j in set(eligible) and learned[j]) if neighbors[i] else 0.0
                    scores.append((1.0 - INIT_K) * (1.0 + BETA_A * fb))
                else:
                    fb = sum(w * (1 - u[j]) for j, w in neighbors[i]) if neighbors[i] else 0.0
                    scores.append((1 - u[i]) * (1.0 + BETA_A * fb))
        else:  # fsrs
            scores = []
            for i in eligible:
                if not learned[i]:
                    scores.append(2.5)
                else:
                    if last[i] < 0:
                        scores.append(2.5)
                    else:
                        el = max(0.1, day - last[i])
                        R = math.exp(-((el / max(S[i], 0.01)) ** 1.2))
                        scores.append(1 - R)

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

    depth_ratio = n_learned / n
    composite = depth_ratio * final_mastery

    return {
        'final_mastery': final_mastery,
        'depth_ratio': depth_ratio,
        'composite': composite,
        'avg_cumul': cumul / max(1, cumul_days),
        'n_learned': n_learned,
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
    print(f"  depth_ratio   = {agg['depth_ratio'][0]:.4f} ({agg['n_learned'][0]:.0f}/{n} KPs)")
    print(f"  max_depth     = {agg['max_depth'][0]:.1f}/{max_chain}")
    print(f"  final_mastery = {agg['final_mastery'][0]:.4f}", flush=True)

fsrs_c = results['fsrs']['composite'][0]
field_c = results['field']['composite'][0]

print(f"\n{'='*60}")
print(f"  Field vs FSRS: composite Δ={field_c-fsrs_c:+.4f}  ({(field_c/fsrs_c-1)*100:+.1f}%)")
print(f"  Depth:    FSRS={results['fsrs']['depth_ratio'][0]:.4f}  Field={results['field']['depth_ratio'][0]:.4f}")
print(f"  N learned: FSRS={results['fsrs']['n_learned'][0]:.0f}  Field={results['field']['n_learned'][0]:.0f}")
print(f"  Mastery:  FSRS={results['fsrs']['final_mastery'][0]:.4f}  Field={results['field']['final_mastery'][0]:.4f}")
print(f"Total: {time.time()-t0:.0f}s")
