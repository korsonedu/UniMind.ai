#!/usr/bin/env python3
"""
重现原始 v6 满扫参：α×βe×βa×γ×η 全 48 组合
找出真实最优，确认 +5.8% 是否存在
"""
import json, math, time, random, numpy as np
from collections import defaultdict
from scipy.sparse import csr_matrix, diags
from collections import deque

ALPHAS  = [0.01, 0.02]
BETAS_E = [0.0, 0.001, 0.005]
BETAS_A = [0.5, 1.0]
GAMMAS  = [0.2, 0.3]
ETAS    = [0.02, 0.05]
N_STUDENTS = 300
N_DAYS = 150
BUDGET_PER_KP = 35
BUDGET_MAX = 10
UNLOCK_EVERY = 15
KPS_PER_UNLOCK = 20
INIT_K = 0.3
EXAM_INTERVAL = 30
EXAM_COVERAGE = 0.3

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

# Lmat for βe diffusion
Lmat = csr_matrix(W.T, shape=(n, n))
col_sum = np.array(Lmat.sum(axis=1)).flatten()
Lmat = Lmat - diags(col_sum, 0, shape=(n, n))

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

print(f'n={n} edges={W.nnz} batches={len(batches)}')
print(f'sweep={len(ALPHAS)*len(BETAS_E)*len(BETAS_A)*len(GAMMAS)*len(ETAS)} combos × {N_STUDENTS}')
print()


def run_sim(sched, alpha, beta_e, beta_a, gamma, eta, seed):
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
                    if sched == 'fsrs':
                        last[i] = -1
                        S[i] = 1.5
            next_batch += 1

        K *= (1 - alpha - 0.005)
        K = np.clip(K, 0, 1)

        if sched == 'field' and beta_e > 0:
            u += (-alpha * u + beta_e * Lmat.dot(u))
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

            if sched == 'greedy':
                scores = [1 - u[i] for i in eligible]
            elif sched == 'field':
                scores = []
                for i in eligible:
                    fb = sum(w * (1 - u[j]) for j, w in neighbors[i]) if neighbors[i] else 0.0
                    scores.append((1 - u[i]) * (1.0 + beta_a * fb))
            else:  # fsrs
                scores = []
                for i in eligible:
                    if last[i] < 0:
                        scores.append(3.0)
                    else:
                        el = max(0.1, day - last[i] if last[i] >= 0 else 99)
                        R = math.exp(-((el / max(S[i], 0.01)) ** 1.2))
                        scores.append(1 - R)

            top = sorted(zip(eligible, scores), key=lambda x: -x[1])[:budget]

            for i, _ in top:
                K[i] += gamma * (1 - K[i])
                for j, w in neighbors[i]:
                    K[j] += eta * w * K[i] * (1 - K[j])
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


t0 = time.time()
results = []

for a in ALPHAS:
    for be in BETAS_E:
        for ba in BETAS_A:
            for g in GAMMAS:
                for e in ETAS:
                    vals = {'a': a, 'be': be, 'ba': ba, 'g': g, 'e': e}
                    for sched in ['greedy', 'field', 'fsrs']:
                        finals, cumuls = [], []
                        for i in range(N_STUDENTS):
                            f, c = run_sim(sched, a, be, ba, g, e, 10000 + i)
                            finals.append(f)
                            cumuls.append(c)
                        vals[f'{sched}_final'] = np.mean(finals)
                        vals[f'{sched}_cumul'] = np.mean(cumuls)
                    vals['dG'] = vals['field_final'] - vals['greedy_final']
                    vsfs = vals['field_final'] - vals['fsrs_final']
                    vals['vsFS'] = vsfs
                    results.append(vals)
                    star = '⭐' if vsfs > 0.03 else ('+' if vsfs > 0 else '-')
                    print(f"α={a:.2f} βe={be:.3f} βa={ba:.1f} γ={g:.1f} η={e:.2f}  "
                          f"F={vals['field_final']:.4f} G={vals['greedy_final']:.4f} FS={vals['fsrs_final']:.4f}  "
                          f"vFS={vsfs:+.4f}{star}",
                          flush=True)

print(f"\n{'='*60}")
print("TOP 10 vs FSRS")
print(f"{'='*60}")
top10 = sorted(results, key=lambda r: r['vsFS'], reverse=True)[:10]
for r in top10:
    print(f"  α={r['a']:.2f} βe={r['be']:.3f} βa={r['ba']:.1f} γ={r['g']:.1f} η={r['e']:.2f}  "
          f"F={r['field_final']:.4f} FS={r['fsrs_final']:.4f} Δ={r['vsFS']:+.4f}")

best = top10[0]
print(f"\nBest: α={best['a']:.2f} βe={best['be']:.3f} βa={best['ba']:.1f} γ={best['g']:.1f} η={best['e']:.2f}")
print(f"  Field vs Greedy: {best['dG']:+.4f}")
print(f"  Field vs FSRS:   {best['vsFS']:+.4f}  ({best['vsFS']*100:+.1f}%)")

# 消融
be0 = [r for r in results if r['be'] == 0.0 and r['a'] == best['a'] and r['ba'] == best['ba'] and r['g'] == best['g'] and r['e'] == best['e']]
if be0:
    r = be0[0]
    print(f"  Ablation (βe=0): F={r['field_final']:.4f} FS={r['fsrs_final']:.4f} Δ={r['vsFS']:+.4f}")

print(f"\nTotal: {time.time()-t0:.0f}s")
