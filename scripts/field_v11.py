#!/usr/bin/env python3
"""
Field v11: 新学+复习 共享预算

真实 Memorix 场景：
- 每天固定预算 B，算法自己决定：新学几个、复习几个
- 新学：选可用但未学的 KP，初始掌握度低
- 复习：选已学的 KP，巩固掌握度
- 前置解锁：父节点被"学过"才能学子节点
- 目标：depth² × mastery（推进深且精）

对比：FSRS | Field(v6公式)
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
DAILY_BUDGET = 8
INIT_K = 0.25
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

# ═══ 前置依赖：用 LLM edges 里的 prerequisite 类型 ═══
# LLM edge types: prerequisite, derivation, similar, co_occur, contrast, confusion
# 只有 prerequisite 是真正的硬前置
prereqs = defaultdict(list)
dependents = defaultdict(list)

for e in llm:
    s = n2id.get(e.get('source_name', ''))
    t = n2id.get(e.get('target_name', ''))
    edge_type = e.get('edge_type', '')
    if s and t and s in id2i and t in id2i:
        if edge_type == 'prerequisite':
            # t 依赖 s（先学 s 才能学 t）
            prereqs[id2i[t]].append(id2i[s])
            dependents[id2i[s]].append(id2i[t])

# 补充：树父→子 也是类前置关系
for nd in nodes:
    kid = nd['id']
    pid = nd.get('parent_id')
    if kid in id2i and pid and pid in id2i:
        if id2i[pid] not in prereqs[id2i[kid]]:
            prereqs[id2i[kid]].append(id2i[pid])
            dependents[id2i[pid]].append(id2i[kid])

# 只保留 KP→KP 的前置（跨 Topic 的也保留）
# 去重
for i in prereqs:
    prereqs[i] = list(set(prereqs[i]))
for i in dependents:
    dependents[i] = list(set(dependents[i]))

# 统计
n_with_prereq = sum(1 for i in range(n) if prereqs[i])
n_roots = sum(1 for i in range(n) if not prereqs[i])
max_chain = 0
def chain_len(i, visited=None):
    if visited is None:
        visited = set()
    if i in visited:
        return 0
    visited.add(i)
    if not prereqs[i]:
        return 1
    return 1 + max(chain_len(p, visited) for p in prereqs[i])
for i in range(n):
    max_chain = max(max_chain, chain_len(i, set()))

print(f'n={n} edges={len(dat)} n_prereq_edges={sum(len(v) for v in prereqs.values())}')
print(f'roots={n_roots} with_prereq={n_with_prereq} max_chain={max_chain}')
print(f'DAILY_BUDGET={DAILY_BUDGET}')


def is_available(i, learned):
    """所有前置 KP 都已学"""
    if not prereqs[i]:
        return True
    return all(learned[p] for p in prereqs[i])


def run_sim(sched, seed):
    K = np.zeros(n)
    u = np.zeros(n)
    learned = np.zeros(n, dtype=bool)
    available = np.zeros(n, dtype=bool)
    S = np.ones(n) * 1.5
    last = np.full(n, -1.0)

    np.random.seed(seed % (2**31))
    random.seed(seed % (2**31))

    # 初始可用：无前置的根 KP
    for i in range(n):
        if not prereqs[i]:
            available[i] = True

    cumul = 0.0
    cumul_days = 0

    for day in range(N_DAYS):
        # ── 更新可用性 ──
        for i in range(n):
            if not learned[i] and not available[i] and is_available(i, learned):
                available[i] = True

        # ── 统一衰减 ──
        K *= (1 - ALPHA - BASE_DECAY)
        K += np.random.normal(0, DAY_NOISE, n)
        K = np.clip(K, 0, 1)
        if sched == 'fsrs':
            # FSRS 的 u 也衰减（但不用 u 选题）
            pass

        if random.random() > 0.85:
            continue

        # ── 选题：可用未学 + 已学 的所有 KP ──
        eligible = []
        for i in range(n):
            if available[i]:  # 可新学 or 已学可复习
                eligible.append(i)

        if not eligible:
            continue

        # ── 算分 ──
        if sched == 'field':
            scores = []
            for i in eligible:
                if not learned[i]:
                    # 未学 KP：field_benefit 来自 neighbor urgencies
                    fb = sum(w * (1 - u[j]) for j, w in neighbors[i] if learned[j]) if neighbors[i] else 0.0
                    # 新学的吸引力：初始掌握度低 + 邻居的级联价值
                    scores.append((1.0 - INIT_K) * (1.0 + BETA_A * fb))
                else:
                    fb = sum(w * (1 - u[j]) for j, w in neighbors[i]) if neighbors[i] else 0.0
                    scores.append((1 - u[i]) * (1.0 + BETA_A * fb))
        else:  # fsrs
            scores = []
            for i in eligible:
                if not learned[i]:
                    # FSRS 第一次见到：高优先级
                    scores.append(2.5)
                else:
                    if last[i] < 0:
                        scores.append(2.5)
                    else:
                        el = max(0.1, day - last[i])
                        R = math.exp(-((el / max(S[i], 0.01)) ** 1.2))
                        scores.append(1 - R)

        top = sorted(zip(eligible, scores), key=lambda x: -x[1])[:DAILY_BUDGET]

        new_learned_today = 0
        reviewed_today = 0

        for i, _ in top:
            was_learned = learned[i]

            if not learned[i]:
                # ── 新学 ──
                learned[i] = True
                K[i] = INIT_K
                u[i] = INIT_K
                new_learned_today += 1
                # 新学也给一次增益
                K[i] += GAMMA * (1 - K[i])
            else:
                # ── 复习 ──
                reviewed_today += 1

            # 共同的增益
            K[i] += GAMMA * (1 - K[i])
            for j, w in neighbors[i]:
                K[j] += ETA * w * K[i] * (1 - K[j])
            K = np.clip(K, 0, 1)
            u[i] = K[i]

            if sched == 'fsrs' and was_learned:
                r = int(max(1, min(4, K[i] * 5 - 1)))
                So = S[i]
                S[i] = max(1, min(365, (2.5 + 0.5 * (r - 2)) if So <= 1.5 else So * (1 + 0.15 * (0.5 + 0.25 * r))))
                last[i] = day
            elif sched == 'fsrs' and not was_learned:
                last[i] = day
                S[i] = 1.5

        # ── 考试 ──
        if day > 0 and day % EXAM_INTERVAL == 0:
            testable = [i for i in range(n) if learned[i]]
            n_test = max(3, int(len(testable) * EXAM_COVERAGE))
            if testable:
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

    # ═══ 指标 ═══
    learned_list = [i for i in range(n) if learned[i]]
    if learned_list:
        final_mastery = float(np.mean([K[i] for i in learned_list]))
    else:
        final_mastery = 0.0

    depth_ratio = len(learned_list) / n
    composite = depth_ratio * depth_ratio * final_mastery

    return {
        'final_mastery': final_mastery,
        'depth_ratio': depth_ratio,
        'composite': composite,
        'avg_cumul': cumul / max(1, cumul_days),
        'n_learned': len(learned_list),
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
    print(f"  final_mastery = {agg['final_mastery'][0]:.4f}")
    print(f"  avg_cumul     = {agg['avg_cumul'][0]:.4f}", flush=True)

fsrs_c = results['fsrs']['composite'][0]
field_c = results['field']['composite'][0]

print(f"\n{'='*60}")
print(f"  Field vs FSRS: composite Δ={field_c-fsrs_c:+.4f}  ({(field_c/fsrs_c-1)*100:+.1f}%)")
print(f"  Depth:  FSRS={results['fsrs']['depth_ratio'][0]:.4f}  Field={results['field']['depth_ratio'][0]:.4f}")
print(f"  Mastery: FSRS={results['fsrs']['final_mastery'][0]:.4f}  Field={results['field']['final_mastery'][0]:.4f}")
print(f"Total: {time.time()-t0:.0f}s")
