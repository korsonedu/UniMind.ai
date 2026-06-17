#!/usr/bin/env python3
"""
Field v9: 图感知状态估计器
v8 证明：全局 selector（线性系统求解）不会赢，因为 u 不准。
v9 假说：Field 的优势在 estimator——复习后同步更新所有受影响 KP 的 u。
  FSRS: u_j 独立，不感知级联 → 下周选题时不知道 j 已经通过 η 受益
  Field: u_j 同步 η 级联 → 选题时拿到真实状态，避免重复复习

对比：
  - FSRS:   独立 u，独立选题
  - Field:  图感知 u（复习后级联更新所有受影响 u_j），同样用 urgency 选题
  - Oracle: 直接读 K 选题（上界）
"""
import json, math, time, random, numpy as np
from collections import defaultdict
from scipy.sparse import csr_matrix
from collections import deque

# ═══ 参数 ═══
ALPHA   = 0.02
ETA     = 0.05
GAMMA   = 0.3
N_STUDENTS = 300
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

# 拓扑排序
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


def run_sim(sched, seed):
    """统一底盘仿真。sched in ('fsrs','field','oracle')"""
    K = np.zeros(n)    # 真实掌握度（共享物理）
    u = np.zeros(n)    # 算法估计器

    S = np.ones(n) * 1.5
    last = np.full(n, -1.0)

    np.random.seed(seed % (2**31))
    random.seed(seed % (2**31))
    unlocked = set()
    cumul = 0.0
    cumul_days = 0
    next_batch = 0

    for day in range(N_DAYS):
        # ── 教案解锁 ──
        if day % UNLOCK_EVERY == 0 and next_batch < len(batches):
            for i in batches[next_batch]:
                if i < n:
                    unlocked.add(i)
                    K[i] = INIT_K
                    u[i] = INIT_K
                    last[i] = -1
                    S[i] = 1.5
            next_batch += 1

        # ── 统一独立衰减 ──
        K *= (1 - ALPHA - BASE_DECAY)
        K += np.random.normal(0, DAY_NOISE, n)
        K = np.clip(K, 0, 1)

        # u 也独立衰减（除 Field 会在复习后做图感知更新）
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

            # ── 选题（统一 urgency 公式，但 u 来源不同）──
            if sched == 'oracle':
                # 上界：直接读真实 K
                scores = [1 - K[i] for i in eligible]
            elif sched == 'field':
                # Field：图感知 u（复习后同步 η 级联）
                scores = [1 - u[i] for i in eligible]
            else:  # fsrs
                # FSRS：独立 u（只更新被复习的 KP）
                scores = []
                for i in eligible:
                    if last[i] < 0:
                        scores.append(3.0)
                    else:
                        el = max(0.1, day - last[i])
                        R = math.exp(-((el / max(S[i], 0.01)) ** 1.2))
                        scores.append(1 - R)

            top = sorted(zip(eligible, scores), key=lambda x: -x[1])[:budget]

            # ── 共享物理：复习 + η ──
            for i, _ in top:
                K[i] += GAMMA * (1 - K[i])

                # η 级联：真实知识转移
                for j, w in neighbors[i]:
                    K[j] += ETA * w * K[i] * (1 - K[j])
                K = np.clip(K, 0, 1)

                # === 关键修正：Field 的图感知 u 更新 ===
                # FSRS 只更新 u[i]；Field 额外推断下游 u[j] 的变化
                u[i] = K[i]

                # ★ 统计已更新的节点，防止同一节点在同一轮被多次加
                if sched == 'field':
                    # 一次复习中，下游节点只应获得一次级联的净效果
                    # 简化：按 K 的变化比例更新 u
                    updated = set()
                    for j, w in neighbors[i]:
                        if j not in updated:
                            # 期望级联：复习 i 带来的下游收益
                            u[j] += ETA * w * u[i] * (1 - u[j])
                            u[j] = np.clip(u[j], 0, 1)
                            updated.add(j)

                    # ★ 修复：级联到二阶邻居
                    # 如果 i→j→k，且 j 的 u 刚刚被更新了，k 也应该获得级联
                    for j, w_ij in neighbors[i]:
                        for k, w_jk in neighbors[j]:
                            if k not in updated and k != i:
                                u[k] += ETA * ETA * w_ij * w_jk * u[i] * (1 - u[k])
                                u[k] = np.clip(u[k], 0, 1)
                                updated.add(k)

                else:  # fsrs
                    u[i] = K[i]
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

    final = float(np.mean([K[i] for i in unlocked])) if unlocked else 0.0
    avg_cumul = cumul / max(1, cumul_days)
    return final, avg_cumul


# ═══ 跑 ═══
t0 = time.time()
results = {}
for sched in ['fsrs', 'field', 'oracle']:
    finals, cumuls = [], []
    for i in range(N_STUDENTS):
        f, c = run_sim(sched, 10000 + i)
        finals.append(f)
        cumuls.append(c)
    results[sched] = {'final': np.mean(finals), 'cumul': np.mean(cumuls)}
    orcl = results['oracle']['final'] if 'oracle' in results else None
    print(f"  {sched:>8s}: final={results[sched]['final']:.4f}  cumul={results[sched]['cumul']:.4f}", flush=True)

print(f"\n{'='*50}")
print(f"  FSRS:   {results['fsrs']['final']:.4f}")
print(f"  Field:  {results['field']['final']:.4f}")
print(f"  Oracle: {results['oracle']['final']:.4f}")
print(f"  Field vs FSRS:   {results['field']['final']-results['fsrs']['final']:+.4f}")
print(f"  Oracle vs FSRS:  {results['oracle']['final']-results['fsrs']['final']:+.4f}")
print(f"  Oracle vs Field: {results['oracle']['final']-results['field']['final']:+.4f}")
print(f"Total: {time.time()-t0:.0f}s")
