#!/usr/bin/env python3
"""
Field v16: 守门员加权——Field 唯一能做到而 FSRS 做不到的事

核心假说：
  调度差不在"怎么选"，在于"选什么值更多"。
  Field 知道哪些 KP 是守门员（有未学子节点在等着），
  FSRS 不知道——它把 K=0.44 的守门员和 K=0.44 的叶子当成一样紧急。
  守门员跌破阈值→下游全线锁死。Field 应该往守门员倾斜预算。

实现：
  对已学 KP，检查是否有未学但 prerequisites 已满足的 dependents。
  有→标为守门员→urgency 额外加权。
"""
import json, math, time, random, numpy as np
from collections import defaultdict, deque
from scipy.sparse import csr_matrix

ALPHA   = 0.015
GAMMA   = 0.3
ETA     = 0.05
N_STUDENTS = 500
N_DAYS = 150
DAILY_BUDGET = 8
INIT_K = 0.25
UNLOCK_PREREQ_THRESHOLD = 0.45
DANGER_THRESHOLD = 0.30
MAX_REVIEW_DEBT = 8
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

# ═══ 前置链（去环）═══
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

prereqs = defaultdict(list)    # i → [需要先学的 KP]
dependents = defaultdict(list)  # i → [依赖 i 的 KP]
for (a, b), (w, (src, dst)) in pair_dir.items():
    prereqs[dst].append(src)
    dependents[src].append(dst)

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

n_roots = sum(1 for i in range(n) if not prereqs[i])
print(f'n={n} roots={n_roots}')
print(f'BUDGET={DAILY_BUDGET} DANGER={DANGER_THRESHOLD} MAX_DEBT={MAX_REVIEW_DEBT}')


def is_available(i, learned, K):
    if not prereqs[i]:
        return True
    for p in prereqs[i]:
        if not learned[p] or K[p] < UNLOCK_PREREQ_THRESHOLD:
            return False
    return True


def identify_gatekeepers(learned, K):
    """
    ★ 守门员：已学 KP，且有未学但 prerequisites 已满足的 dependents
    这些 KP 的 K 跌破阈值会直接锁死下游进度
    """
    gk = np.zeros(n, dtype=bool)
    for i in range(n):
        if not learned[i]:
            continue
        for j in dependents[i]:
            if not learned[j] and is_available(j, learned, K):
                gk[i] = True
                break
    return gk


def count_debt(learned, K):
    return sum(1 for i in range(n) if learned[i] and K[i] < DANGER_THRESHOLD)


def urgency(K_val):
    if K_val <= 0.01:
        return 10.0
    return (1.0 - K_val) / K_val


GATEKEEPER_BONUS = 1.5   # ★ 守门员 urgency 倍率
NEW_ATTRACTION = 1.0


def run_sim(sched, seed):
    K = np.zeros(n)
    u = np.zeros(n)
    learned = np.zeros(n, dtype=bool)

    np.random.seed(seed % (2**31))
    random.seed(seed % (2**31))

    cumul = 0.0
    cumul_days = 0
    can_learn_new = True

    for day in range(N_DAYS):
        K *= (1 - ALPHA - BASE_DECAY)
        K += np.random.normal(0, DAY_NOISE, n)
        K = np.clip(K, 0, 1)

        if random.random() > 0.85:
            continue

        debt = count_debt(learned, K)
        if can_learn_new and debt >= MAX_REVIEW_DEBT:
            can_learn_new = False
        elif not can_learn_new and debt <= MAX_REVIEW_DEBT // 2:
            can_learn_new = True

        # ★ 守门员标记
        gatekeepers = identify_gatekeepers(learned, K) if sched == 'field' else np.zeros(n, dtype=bool)

        eligible = []
        for i in range(n):
            if learned[i]:
                eligible.append(i)
            elif can_learn_new and is_available(i, learned, K):
                eligible.append(i)

        if not eligible:
            continue

        if sched == 'field':
            scores = []
            for i in eligible:
                if not learned[i]:
                    scores.append(NEW_ATTRACTION)
                else:
                    base = urgency(u[i])
                    # ★ 守门员额外加权
                    if gatekeepers[i]:
                        base *= GATEKEEPER_BONUS
                    scores.append(base)
        else:
            scores = []
            for i in eligible:
                if not learned[i]:
                    scores.append(NEW_ATTRACTION)
                else:
                    scores.append(urgency(K[i]))

        top = sorted(zip(eligible, scores), key=lambda x: -x[1])[:DAILY_BUDGET]

        for i, _ in top:
            if not learned[i]:
                learned[i] = True
                K[i] = INIT_K
                u[i] = INIT_K

            K[i] += GAMMA * (1 - K[i])
            for j, w in neighbors[i]:
                K[j] += ETA * w * K[i] * (1 - K[j])
            K = np.clip(K, 0, 1)
            u[i] = K[i]

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
        n_mastered = sum(1 for i in learned_list if K[i] > 0.5)
        n_learned = len(learned_list)
    else:
        final_mastery = 0.0
        n_mastered = 0
        n_learned = 0

    return {
        'n_learned': n_learned,
        'n_mastered': n_mastered,
        'final_mastery': final_mastery,
        'mastered_ratio': n_mastered / n,
        'composite': (n_learned / n) * final_mastery,
        'avg_cumul': cumul / max(1, cumul_days),
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
    print(f"  n_learned     = {agg['n_learned'][0]:.0f}/{n}")
    print(f"  n_mastered    = {agg['n_mastered'][0]:.0f}  (K>0.5)")
    print(f"  mastered_ratio= {agg['mastered_ratio'][0]:.4f}")
    print(f"  final_mastery = {agg['final_mastery'][0]:.4f}", flush=True)

print(f"\n{'='*60}")
for metric in ['composite', 'mastered_ratio', 'n_learned', 'n_mastered', 'final_mastery']:
    f_val = results['field'][metric][0]
    s_val = results['fsrs'][metric][0]
    if s_val > 0:
        delta_pct = (f_val / s_val - 1) * 100
        print(f"  {metric:>16s}: FSRS={s_val:.4f}  Field={f_val:.4f}  Δ={delta_pct:+.1f}%")
    else:
        print(f"  {metric:>16s}: FSRS={s_val:.4f}  Field={f_val:.4f}")

print(f"Total: {time.time()-t0:.0f}s")
