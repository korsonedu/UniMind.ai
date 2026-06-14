#!/usr/bin/env python3
"""
Memorix-Field 参数扫描
======================
系统级搜索最优参数：跨知识结构稳定有效，非特异值。

扫描维度：
  α (衰减率)     → 知识遗忘速率
  β_ratio (图扩散/衰减比)  → 图结构权重
  γ (复习增益)   → 单次复习效果
  η (图转移)     → 复习 i 对邻居的真实帮助

跨结构验证：
  1. CFA 原始知识图
  2. 随机扰动图（边权重 shuffle 20%）
  3. 度保持随机图（重新连边但保持度数分布）

输出：每个 α,β,γ,η 组合下 Field Δ vs Greedy，找最优且跨结构稳定的组合。
"""

import json, math, time, os, random
from collections import defaultdict
import numpy as np
from scipy.sparse import csr_matrix, eye, diags
from scipy.sparse.linalg import cg

# ═══ 参数搜索空间 ═══
ALPHAS      = [0.005, 0.01, 0.02]
BETA_RATIOS = [0.2, 0.4, 0.6, 0.8]   # β/β_limit
GAMMAS      = [0.2, 0.3, 0.4]
ETAS        = [0.01, 0.02, 0.05]

# 仿真规模
N_STUDENTS  = 100
N_DAYS      = 150
BUDGET      = 6
STUDY_HOURS = 8

# 固定参数
SLEEP_DECAY = 0.005
STUDY_RATE  = 0.85
FATIGUE_MAX = 0.40
EXAM_INTERVAL = 20
EXAM_COVERAGE = 0.15
MIN_DIFFICULTY = 0.5
MAX_DIFFICULTY = 2.0
K_WEIBULL = 1.2
CG_TOL = 1e-6
CG_MAXITER = 50


# ═══════════════════════════════════════
# 知识图加载 + 变换
# ═══════════════════════════════════════

def load_graph(tree_path, llm_edges_path=None):
    with open(tree_path) as f:
        data = json.load(f)
    nodes = data['nodes']
    kps = [n for n in nodes if n.get('level') == 'kp']
    kp_ids = [n['id'] for n in kps]
    id_to_idx = {kid: i for i, kid in enumerate(kp_ids)}
    n = len(kps)

    adj = defaultdict(list)
    for nd in nodes:
        pid = nd.get('parent_id')
        if pid and nd['id'] in id_to_idx and pid in id_to_idx:
            adj[nd['id']].append((pid, 0.8))
            adj[pid].append((nd['id'], 0.8))
    cbp = defaultdict(list)
    for nd in nodes:
        pid = nd.get('parent_id')
        if pid and nd['id'] in id_to_idx:
            cbp[pid].append(nd['id'])
    for siblings in cbp.values():
        for i in range(len(siblings)):
            for j in range(i+1, len(siblings)):
                adj[siblings[i]].append((siblings[j], 0.3))
                adj[siblings[j]].append((siblings[i], 0.3))
    if llm_edges_path and os.path.exists(llm_edges_path):
        with open(llm_edges_path) as f:
            llm_edges = json.load(f)
        name_to_id = {n['name']: n['id'] for n in kps}
        for e in llm_edges:
            src = name_to_id.get(e.get('source_name', ''))
            tgt = name_to_id.get(e.get('target_name', ''))
            if src and tgt and src in id_to_idx and tgt in id_to_idx:
                adj[src].append((tgt, float(e.get('weight', 0.5))))

    row, col, data = [], [], []
    for src_kid, neighbors in adj.items():
        if src_kid in id_to_idx:
            i = id_to_idx[src_kid]
            for tgt_kid, w in neighbors:
                if tgt_kid in id_to_idx:
                    j = id_to_idx[tgt_kid]
                    row.append(i); col.append(j); data.append(w)
    W = csr_matrix((data, (row, col)), shape=(n, n))
    L = csr_matrix(W.T, shape=(n, n))
    col_sum = np.array(L.sum(axis=1)).flatten()
    L = L - diags(col_sum, 0, shape=(n, n))

    return {'n': n, 'W': W, 'L': L, 'adj': adj,
            'id_to_idx': id_to_idx, 'nodes': nodes}


def graph_variants(base_graph):
    """生成跨结构验证用的图变体"""
    n = base_graph['n']
    W = base_graph['W'].toarray()
    adj = base_graph['adj']
    id_to_idx = base_graph['id_to_idx']

    # 1) 原始
    orig = _make_graph(n, W, adj, id_to_idx)

    # 2) 权重 shuffle 20%
    W2 = W.copy()
    nnz = np.count_nonzero(W2)
    shuffled = np.random.choice(nnz, size=int(nnz*0.2), replace=False)
    vals = W2[W2 > 0]
    rand_idx = np.random.permutation(len(vals))
    flat = W2.flatten()
    nonzero_pos = np.where(flat > 0)[0]
    perm = nonzero_pos.copy()
    np.random.shuffle(perm)
    swap_n = min(int(nnz*0.2), len(nonzero_pos))
    for k in range(swap_n):
        flat[perm[k]] = flat[nonzero_pos[k]]
    W2 = flat.reshape(n, n)
    shuffled_adj = _rebuild_adj(W2, adj, id_to_idx)
    shuf = _make_graph(n, csr_matrix(W2), shuffled_adj, id_to_idx)
    shuf['L'] = _build_L(csr_matrix(W2))

    # 3) 度保持随机重连
    W3 = np.zeros_like(W)
    degrees = W.sum(axis=1)
    for i in range(n):
        di = max(1, int(degrees[i]))
        targets = np.random.choice(n, size=min(di*2, n-1), replace=False)
        targets = targets[targets != i]
        weights = np.random.uniform(0.1, 0.5, size=len(targets))
        for k, t in enumerate(targets[:di]):
            W3[i, int(t)] = weights[k]
    deg_adj = _rebuild_adj(csr_matrix(W3), adj, id_to_idx)
    deg = _make_graph(n, csr_matrix(W3), deg_adj, id_to_idx)
    deg['L'] = _build_L(csr_matrix(W3))

    return {'original': orig, 'shuffle20': shuf, 'degree_preserving': deg}


def _make_graph(n, W, adj, id_to_idx):
    L_mat = _build_L(W)
    return {'n': n, 'W': W, 'L': L_mat, 'adj': adj, 'id_to_idx': id_to_idx}


def _build_L(W):
    L = csr_matrix(W.T, shape=(W.shape[0], W.shape[0]))
    col_sum = np.array(L.sum(axis=1)).flatten()
    return L - diags(col_sum, 0, shape=(W.shape[0], W.shape[0]))


def _rebuild_adj(W, _old_adj, id_to_idx):
    """从 W 矩阵重建邻接表"""
    adj = defaultdict(list)
    W_dense = W.toarray() if hasattr(W, 'toarray') else W
    n = W_dense.shape[0]
    idx_to_id = {v: k for k, v in id_to_idx.items()}
    for i in range(n):
        for j in range(n):
            if W_dense[i, j] > 0:
                adj[idx_to_id[i]].append((idx_to_id[j], float(W_dense[i, j])))
    return adj


# ═══════════════════════════════════════
# 仿真核心（复用 bench 的 Student/Estimator）
# ═══════════════════════════════════════

def compute_centrality(graph, alpha, beta):
    n = graph['n']
    A = alpha * eye(n) - beta * graph['L']
    b = np.ones(n)
    x, info = cg(A, b, rtol=CG_TOL, maxiter=CG_MAXITER)
    if info != 0:
        x = np.ones(n) / alpha
        for _ in range(200):
            x_new = (b + beta * graph['L'].dot(x)) / alpha
            if np.linalg.norm(x_new - x) < CG_TOL * n:
                return x_new
            x = x_new
    return x


class GreedyE:
    def score(self, eligible, K, _g): return [1.0-K[i] for i in eligible]

class FieldE:
    def __init__(self, n, centrality): self.u = np.zeros(n); self.c = centrality
    def score(self, eligible, K, g): return [(1.0-self.u[i])*self.c[i] for i in eligible]
    def evolve(self, g, a, b):
        self.u += (-a*self.u + b*g['L'].dot(self.u)); self.u = np.clip(self.u,0,1)

class FSRSE:
    def __init__(self, n): self.S = np.ones(n)*1.5; self.last = np.full(n,-1.0)
    def score(self, eligible, K, g):
        s = []
        for i in eligible:
            if self.last[i] < 0: s.append(3.0)
            else:
                el = max(0.001, self.S[i])
                R = math.exp(-((el/max(self.S[i],0.01))**K_WEIBULL))
                s.append(1.0-R)
        return s
    def update(self, i, r):
        So = self.S[i]
        Sn = (2.5+0.5*(r-2)) if So<=1.5 else So*(1.0+0.15*(0.5+0.25*r))
        self.S[i] = max(1.0, min(365.0, Sn))


class Student:
    def __init__(self, sid, n, coverage=0.5):
        self.sid = sid; self.n = n; self.K = np.zeros(n)
        self.total_reviews = 0; self.mastered = set()
        self.covered_kps = set(); self.unlocked = set()
        self.coverage = coverage; self.session_reviews = 0
    def init(self, graph, seed):
        rng = random.Random(seed)
        nc = max(5, int(self.n*self.coverage))
        self.covered_kps = set(rng.sample(list(range(self.n)), min(nc, self.n)))
        self.unlocked = set(range(self.n))  # 简化：所有 KP 初始可见
    def eligible(self):
        return list(self.covered_kps)
    def review(self, i, graph, eta, gamma, fatigue=0.0):
        boost = gamma * (1.0-self.K[i]) * (1.0-fatigue*FATIGUE_MAX)
        self.K[i] += boost
        kid_i = self._idx_kid_map.get(i) if hasattr(self,'_idx_kid_map') else None
        if kid_i:
            for tgt_kid, w in graph['adj'].get(kid_i, []):
                tgt_idx = graph['id_to_idx'].get(tgt_kid)
                if tgt_idx is not None:
                    self.K[tgt_idx] += eta*w*(1.0-self.K[tgt_idx])
        self.K = np.clip(self.K,0,1); self.total_reviews += 1; self.session_reviews += 1
    def overnight_decay(self, alpha):
        self.K *= (1.0 - alpha - SLEEP_DECAY); self.K = np.clip(self.K,0,1)


def simulate_one(graph, student, estimator, sched, params, budget, seed):
    alpha, beta, gamma, eta = params
    np.random.seed((seed+student.sid)%(2**31))
    random.seed((seed+student.sid)%(2**31))

    student.init(graph, seed+student.sid)
    ah = max(4, STUDY_HOURS+random.uniform(-2,2))

    for day in range(N_DAYS):
        if random.random() > STUDY_RATE:
            student.overnight_decay(alpha)
            if sched == 'field': estimator.evolve(graph, alpha, beta)
            continue

        student.session_reviews = 0
        ds = day*24; cur = ds+random.uniform(0,1); se = ds+ah

        while cur < se:
            cur += random.uniform(0.05, 0.3)
            if cur >= se: break
            eligible = student.eligible()
            if not eligible: break

            scores = estimator.score(eligible, student.K, graph)
            scored = sorted(zip(eligible, scores), key=lambda x:-x[1])
            selected = [x[0] for x in scored[:budget]]

            fatigue = min(1.0, student.session_reviews/30.0)
            for i in selected:
                student.review(i, graph, eta, gamma, fatigue)
                rating = max(1,min(4,int(student.K[i]*5)-1))
                if sched == 'fsrs': estimator.update(i, rating)
                if sched == 'field': estimator.u[i] += gamma*(1.0-estimator.u[i])
            cur += 0.1*budget

        student.overnight_decay(alpha)
        if sched == 'field': estimator.evolve(graph, alpha, beta)

    covered_K = [student.K[i] for i in student.covered_kps]
    return float(np.mean(covered_K)) if covered_K else 0.0


# ═══════════════════════════════════════
# 参数扫描
# ═══════════════════════════════════════

def lambda_max(graph):
    from scipy.sparse.linalg import eigsh
    return eigsh(-graph['L'], k=1, which='LM', return_eigenvectors=False)[0]


def sweep(graphs_dict, students_per=100):
    """对所有图变体、所有参数组合跑 Field vs Greedy"""
    results = []

    for gname, graph in graphs_dict.items():
        lm = lambda_max(graph)
        print(f"\n{'='*50}\nGraph: {gname}  λ_max={lm:.2f}\n{'='*50}")

        for alpha in ALPHAS:
            beta_limit = alpha / lm
            if beta_limit <= 0:
                continue

            for b_ratio in BETA_RATIOS:
                beta = b_ratio * beta_limit
                for gamma in GAMMAS:
                    for eta in ETAS:
                        params = (alpha, beta, gamma, eta)
                        centrality = compute_centrality(graph, alpha, beta)

                        # Field
                        field_vals = []
                        for i in range(students_per):
                            s = Student(i, graph['n'], 0.5+0.05*(i%5))
                            s._idx_kid_map = {v:k for k,v in graph['id_to_idx'].items()}
                            e = FieldE(graph['n'], centrality)
                            fv = simulate_one(graph, s, e, 'field', params, BUDGET, 1000+i)
                            field_vals.append(fv)

                        # Greedy
                        greedy_vals = []
                        for i in range(students_per):
                            s = Student(i+10000, graph['n'], 0.5+0.05*(i%5))
                            s._idx_kid_map = {v:k for k,v in graph['id_to_idx'].items()}
                            e = GreedyE()
                            gv = simulate_one(graph, s, e, 'greedy', params, BUDGET, 20000+i)
                            greedy_vals.append(gv)

                        f_mean = np.mean(field_vals)
                        g_mean = np.mean(greedy_vals)
                        delta = f_mean - g_mean

                        results.append({
                            'graph': gname, 'alpha': alpha,
                            'beta_ratio': b_ratio, 'beta': beta,
                            'gamma': gamma, 'eta': eta,
                            'field_mean': f_mean, 'greedy_mean': g_mean,
                            'delta': delta,
                        })

                        pref = "⭐" if delta > 0.01 else ("+" if delta > 0 else " ")
                        print(f"  α={alpha:.3f} βr={b_ratio:.1f} γ={gamma:.1f} η={eta:.2f} "
                              f"F={f_mean:.4f} G={g_mean:.4f} Δ={delta:+.4f} {pref}", flush=True)

    return results


def analyze(results):
    """找出跨图结构稳定的最优参数"""
    print(f"\n{'='*70}")
    print(f"ANALYSIS: {len(results)} combinations across graphs")
    print(f"{'='*70}")

    # 按 (alpha, beta_ratio, gamma, eta) 聚合所有图的平均 Δ
    from collections import defaultdict
    agg = defaultdict(list)
    for r in results:
        key = (r['alpha'], r['beta_ratio'], r['gamma'], r['eta'])
        agg[key].append(r['delta'])

    # 排序：平均 Δ 最高、跨图标准差最小（=稳定性）
    scored = []
    for key, deltas in agg.items():
        mean_d = np.mean(deltas)
        std_d = np.std(deltas)
        # 评分 = 平均优势 - 标准差（越稳定越好）
        score = mean_d - std_d
        scored.append((score, mean_d, std_d, key))

    scored.sort(key=lambda x: -x[0])

    print(f"\nTop 10 across all graphs (sorted by mean-σ):")
    print(f"{'α':>6} {'βr':>5} {'γ':>5} {'η':>5} {'Δ_mean':>8} {'Δ_std':>8} {'score':>8}")
    for s, m, sd, (a, br, g, e) in scored[:10]:
        print(f"{a:6.3f} {br:5.1f} {g:5.1f} {e:5.2f} {m:+8.4f} {sd:8.4f} {s:8.4f}")

    # 按图分开显示每个图的最优
    graphs = sorted(set(r['graph'] for r in results))
    for gname in graphs:
        gr = [r for r in results if r['graph'] == gname]
        best = max(gr, key=lambda r: r['delta'])
        print(f"\n{gname} best: α={best['alpha']:.3f} βr={best['beta_ratio']:.1f} "
              f"γ={best['gamma']:.1f} η={best['eta']:.2f} Δ={best['delta']:+.4f}")

    # FSRS vs best params on each graph
    print(f"\n{'='*50}")
    print(f"FSRS vs Field vs Greedy at Top-5 params")
    print(f"{'='*50}")

    top5 = scored[:5]
    for rank, (score, mean_d, std_d, (a, br, g, e)) in enumerate(top5):
        print(f"\n--- Rank {rank+1}: α={a:.3f} βr={br:.1f} γ={g:.1f} η={e:.2f} ---")
        for gname in graphs:
            graph = graphs_dict[gname]
            lm = lambda_max(graph)
            beta = br * a / lm if lm > 0 else 0
            params = (a, beta, g, e)
            centrality = compute_centrality(graph, a, beta)

            results_for_graph = {'field': [], 'greedy': [], 'fsrs': []}
            for i in range(N_STUDENTS):
                # Field
                s = Student(i, graph['n'], 0.5+0.05*(i%5))
                s._idx_kid_map = {v:k for k,v in graph['id_to_idx'].items()}
                results_for_graph['field'].append(
                    simulate_one(graph, s, FieldE(graph['n'], centrality),
                                 'field', params, BUDGET, 1000+i))
                # Greedy
                s2 = Student(i+10000, graph['n'], 0.5+0.05*(i%5))
                s2._idx_kid_map = {v:k for k,v in graph['id_to_idx'].items()}
                results_for_graph['greedy'].append(
                    simulate_one(graph, s2, GreedyE(),
                                 'greedy', params, BUDGET, 20000+i))
                # FSRS
                s3 = Student(i+30000, graph['n'], 0.5+0.05*(i%5))
                s3._idx_kid_map = {v:k for k,v in graph['id_to_idx'].items()}
                results_for_graph['fsrs'].append(
                    simulate_one(graph, s3, FSRSE(graph['n']),
                                 'fsrs', params, BUDGET, 50000+i))

            f_mean = np.mean(results_for_graph['field'])
            gr_mean = np.mean(results_for_graph['greedy'])
            fs_mean = np.mean(results_for_graph['fsrs'])
            print(f"  {gname:20s}: Field={f_mean:.4f}  Greedy={gr_mean:.4f}  "
                  f"FSRS={fs_mean:.4f}  ΔF={f_mean-gr_mean:+.4f}  ΔFSRS={fs_mean-gr_mean:+.4f}")

    return scored


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    tree_path = os.path.join(script_dir, 'cfa_tree.json')
    llm_path = os.path.join(script_dir, 'cfa_llm_edges.json')

    print("="*60)
    print("Memorix-Field 参数扫描")
    print(f"α∈{ALPHAS}  βr∈{BETA_RATIOS}  γ∈{GAMMAS}  η∈{ETAS}")
    print(f"graphs: original + shuffle20% + degree_preserving")
    print(f"students: {N_STUDENTS}/combo  days: {N_DAYS}")
    print("="*60)

    base = load_graph(tree_path, llm_path)
    print(f"Base graph: {base['n']} KPs, {base['W'].nnz} edges")

    variants = graph_variants(base)
    print(f"Variants: {list(variants.keys())}")

    results = sweep(variants, N_STUDENTS)
    analyze(results)

    # 保存
    out_path = os.path.join(script_dir, 'output', 'field_sweep.json')
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2, default=float)
    print(f"\nSaved to {out_path}")


if __name__ == '__main__':
    graphs_dict = {}  # injected by main
    main()
