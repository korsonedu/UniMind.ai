#!/usr/bin/env python3
"""
Field v7: 全局图感知选题
核心修正：selector 从一阶局部 → 无穷阶全局（线性系统 + 共轭梯度）

公式推导：
  复习 i 带来的全局收益 = Σ_j w_j_test × (ΔK_j | review_i)
  ΔK 经过 η 扩散在图上传播：(I - η_eff·W⊤)⁻¹ × ΔK_direct
  influence = (I - η_eff·W⊤)⁻¹ × urgency_vector

对比：
  - FSRS: 独立局部选题（baseline）
  - Field-local: v6 公式，一阶邻域 (I + βa·W) × urgency（旧实现）
  - Field-global: 无穷阶 (I - η_eff·W⊤)⁻¹ × urgency（新实现）
"""
import json, math, time, random, numpy as np
from collections import defaultdict
from scipy.sparse import csr_matrix, diags, eye
from scipy.sparse.linalg import cg
from collections import deque

# ═══ 参数 ═══
ALPHA   = 0.02       # 统一日衰减率
ETA     = 0.05       # η 转移强度
GAMMA   = 0.3        # 复习增益
N_STUDENTS = 300
N_DAYS = 150
BUDGET_PER_KP = 35   # 每 35 个已解锁 KP 配 1 次复习
BUDGET_MAX = 10
UNLOCK_EVERY = 15    # 每 15 天解锁
KPS_PER_UNLOCK = 20
INIT_K = 0.3
EXAM_INTERVAL = 30
EXAM_COVERAGE = 0.3
DAY_NOISE = 0.02     # 每日随机噪声幅度
BASE_DECAY = 0.005   # 基底遗忘率（不可逆）

# ═══ 加载图 ═══
with open('cfa_tree.json') as f:
    data = json.load(f)
nodes = data['nodes']
kps = [n for n in nodes if n.get('level') == 'kp']
kp_ids = [n['id'] for n in kps]
id2i = {kid: i for i, kid in enumerate(kp_ids)}
n = len(kps)

# 构建邻接：tree edges + sibling edges + LLM edges
adj = defaultdict(list)
for nd in nodes:
    pid = nd.get('parent_id')
    if pid and nd['id'] in id2i and pid in id2i:
        adj[nd['id']].append((pid, 0.8))
        adj[pid].append((nd['id'], 0.8))
# sibling edges
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
# LLM edges
n2id = {nd['name']: nd['id'] for nd in kps}
with open('cfa_llm_edges.json') as f:
    llm = json.load(f)
for e in llm:
    s = n2id.get(e.get('source_name', ''))
    t = n2id.get(e.get('target_name', ''))
    if s and t and s in id2i and t in id2i:
        adj[s].append((t, float(e.get('weight', 0.5))))

# 构建稀疏矩阵
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

# ═══ 拓扑排序 → 教案解锁顺序 ═══
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


# ═══ 全局影响力计算 ═══
def compute_global_influence(urgency, W, eta_eff, eligible_indices, max_influence_cg_iters=50):
    """
    求解 influence = (I - eta_eff · W⊤)⁻¹ · urgency
    用共轭梯度法迭代。所有 KP 参与求解，但对非 eligible 的 KP 加惩罚使其不被选中。
    """
    # A = I - eta_eff · W⊤
    I = eye(n, format='csr')
    A = I - eta_eff * W.T

    # 用 CG 求解 A · influence = urgency
    # urgency 是需求向量（1 - u），A 是对称正定吗？不一定。
    # 如果 W 不对称，(I - ηW⊤) 可能不对称。
    # 用 GMRES 或直接 relax：对非对称矩阵用 bicgstab
    from scipy.sparse.linalg import bicgstab
    influence, exit_code = bicgstab(A, urgency, rtol=1e-6, maxiter=max_influence_cg_iters)

    if exit_code != 0:
        # fallback: use local scoring
        influence = urgency.copy()
        for _ in range(3):  # few iterations of power method
            influence = urgency + eta_eff * W.T.dot(influence)

    return influence


def run_sim(sched, seed):
    """统一底盘仿真"""
    K = np.zeros(n)    # 真实掌握度
    u = np.zeros(n)    # 算法估计器
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
        # ── 教案解锁 ──
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

        # ── 统一衰减（所有算法共享同一物理）──
        K *= (1 - ALPHA - BASE_DECAY)
        # 日间随机波动
        K += np.random.normal(0, DAY_NOISE, n)
        K = np.clip(K, 0, 1)

        # ── 跳过日 ──
        if random.random() > 0.85:
            continue

        budget = min(BUDGET_MAX, max(1, (len(unlocked) + BUDGET_PER_KP - 1) // BUDGET_PER_KP))
        eligible = sorted(unlocked)
        if not eligible or budget == 0:
            continue

        for _ in range(budget):
            if not eligible:
                break

            # ── 选题 ──
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
                urgency_full = np.array([1 - u[i] for i in range(n)])

                if sched == 'field_global':
                    # 全局影响力：求解线性系统
                    eta_eff = ETA * 0.3  # effective η for influence calculation
                    influence = compute_global_influence(urgency_full, W, eta_eff, eligible)
                    scores = [influence[i] for i in eligible]
                else:
                    # field_local: v6 一阶近似（基准）
                    beta_a = 1.0
                    scores = []
                    for i in eligible:
                        fb = sum(w * (1 - u[j]) for j, w in neighbors[i]) if neighbors[i] else 0.0
                        scores.append((1 - u[i]) * (1.0 + beta_a * fb))
            else:
                raise ValueError(f"unknown sched: {sched}")

            top = sorted(zip(eligible, scores), key=lambda x: -x[1])[:budget]

            # ── 共享物理：复习 + η ──
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

    final = float(np.mean([K[i] for i in unlocked])) if unlocked else 0.0
    avg_cumul = cumul / max(1, cumul_days)
    return final, avg_cumul


# ═══ 跑 ═══
t0 = time.time()
results = {}
for sched in ['fsrs', 'field_local', 'field_global']:
    finals, cumuls = [], []
    for i in range(N_STUDENTS):
        f, c = run_sim(sched, 10000 + i)
        finals.append(f)
        cumuls.append(c)
    results[sched] = {'final': np.mean(finals), 'cumul': np.mean(cumuls)}
    print(f"  {sched:>14s}: final={results[sched]['final']:.4f}  cumul={results[sched]['cumul']:.4f}",
          flush=True)

print(f"\n{'='*50}")
print(f"  Field (local)  vs FSRS: {results['field_local']['final']-results['fsrs']['final']:+.4f}")
print(f"  Field (global) vs FSRS: {results['field_global']['final']-results['fsrs']['final']:+.4f}")
print(f"  Field (global) vs local: {results['field_global']['final']-results['field_local']['final']:+.4f}")
print(f"Total: {time.time()-t0:.0f}s")
