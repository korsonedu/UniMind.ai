#!/usr/bin/env python3
"""
物理推演：扫 η，看 Oracle 上界 vs FSRS 的差距
假说：η 越大 → 知识级联越强 → Oracle（完美信息）甩 FSRS 越远
目标：找到 η 使 Oracle vs FSRS > 10%，验证图调度是否有操作空间

对比：FSRS | Field (v9 estimator) | Oracle (读真实K) | Field-global (v8 linear system)
"""
import json, math, time, random, numpy as np
from collections import defaultdict
from scipy.sparse import csr_matrix, eye
from scipy.sparse.linalg import bicgstab
from collections import deque

# ═══ 固定参数 ═══
ALPHA   = 0.02
GAMMA   = 0.3
N_STUDENTS = 200      # 扫参用较小学生数加速
N_DAYS = 150
BUDGET_PER_KP = 35
BUDGET_MAX = 10
UNLOCK_EVERY = 15
KPS_PER_UNLOCK = 20
INIT_K = 0.3
EXAM_INTERVAL = 30
EXAM_COVERAGE = 0.3
DAY_NOISE = 0.02
BASE_DECAY = 0.005

# 扫参范围
ETAS = [0.05, 0.10, 0.15, 0.20, 0.30]

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

print(f'n={n} edges={len(dat)} batches={len(batches)}')
print(f'ETAS={ETAS}')
print()


def compute_global_influence(urgency, K_vec, W, eta_eff):
    from scipy.sparse import diags
    K_diag = diags(K_vec, 0, shape=(n, n))
    A = eye(n, format='csr') - eta_eff * K_diag.dot(W)
    influence, exit_code = bicgstab(A, urgency, rtol=1e-4, maxiter=50)
    if exit_code != 0:
        influence = urgency.copy()
        for _ in range(3):
            influence = urgency + eta_eff * K_vec * W.dot(influence)
            influence = np.clip(influence, 0, None)
    return influence


def run_sim(sched, eta, seed):
    K = np.zeros(n)
    u = np.zeros(n)
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
                    last[i] = -1
                    S[i] = 1.5
            next_batch += 1

        K *= (1 - ALPHA - BASE_DECAY)
        K += np.random.normal(0, DAY_NOISE, n)
        K = np.clip(K, 0, 1)
        u *= (1 - ALPHA)
        u = np.clip(u, 0, 1)

        if random.random() > 0.85:
            continue

        n_unlocked = len(unlocked)
        if n_unlocked == 0:
            continue
        budget = min(BUDGET_MAX, max(1, (n_unlocked + BUDGET_PER_KP - 1) // BUDGET_PER_KP))

        for _ in range(budget):
            eligible = sorted(unlocked)
            if not eligible:
                break

            if sched == 'oracle':
                scores = [1 - K[i] for i in eligible]
            elif sched == 'field':
                scores = [1 - u[i] for i in eligible]
            elif sched == 'field_global':
                urgency = np.array([1 - u[i] for i in range(n)])
                eta_eff = eta * 0.3
                influence = compute_global_influence(urgency, u, W, eta_eff)
                scores = [influence[i] for i in eligible]
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

            for i, _ in top:
                K[i] += GAMMA * (1 - K[i])
                for j, w in neighbors[i]:
                    K[j] += eta * w * K[i] * (1 - K[j])
                K = np.clip(K, 0, 1)
                u[i] = K[i]

                # Field v9: graph-aware u cascade
                if sched in ('field', 'field_global'):
                    for j, w in neighbors[i]:
                        u[j] += eta * w * u[i] * (1 - u[j])
                        u[j] = np.clip(u[j], 0, 1)
                else:  # fsrs / oracle
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
t0 = time.time()

for eta in ETAS:
    results = {}
    for sched in ['fsrs', 'field', 'field_global', 'oracle']:
        finals, cumuls = [], []
        for i in range(N_STUDENTS):
            f, c = run_sim(sched, eta, 10000 + i)
            finals.append(f)
            cumuls.append(c)
        results[sched] = {'final': np.mean(finals), 'cumul': np.mean(cumuls)}

    fsrs = results['fsrs']['final']
    field = results['field']['final']
    fg = results['field_global']['final']
    oracle = results['oracle']['final']

    print(f"η={eta:.2f}  "
          f"FSRS={fsrs:.4f}  "
          f"Field={field:.4f} (vFSRS {field-fsrs:+.4f})  "
          f"F-global={fg:.4f} (vFSRS {fg-fsrs:+.4f})  "
          f"Oracle={oracle:.4f} (vFSRS {oracle-fsrs:+.4f})  "
          f"gap={oracle-fsrs:.1%}",
          flush=True)

print(f"\nTotal: {time.time()-t0:.0f}s")
