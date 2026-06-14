#!/usr/bin/env python3
"""
Memorix-Field 纯模型仿真
========================
对比：Field（图扩散 linear-optimal）vs 贪心 urgency vs FSRS

Field 模型：
  du/dt = -α·u + β·L·u         自由演化
  review i: u_i += γ·(1-u_i)    饱和增长
  score_i = (1-u_i) × centrality_i
  centrality = (αI - βL)^(-1)·1  共轭梯度求解

贪心 urgency：
  score_i = 1 - u_i

FSRS：
  Weibull R + per-student stability/difficulty + scheduling
"""

import json, math, time, os, random
from collections import defaultdict
import numpy as np
from scipy.sparse import csr_matrix, eye, diags
from scipy.sparse.linalg import cg

# ═══ 配置 ═══
ALPHA = 0.01       # 统一衰减率 /天
BETA  = 0.0003     # 扩散强度 /天（for λ_max≈19, β_max=0.0005，安全取值）
GAMMA = 0.30       # 单次复习增益
DT    = 1.0        # 动力学步长（天）

# 仿真规模
N_STUDENTS  = 200
N_DAYS      = 150
BUDGET      = 6       # 每次选 K 个 KP
STUDY_HOURS = 8

# 共轭梯度
CG_TOL    = 1e-6
CG_MAXITER = 50


# ═══════════════════════════════════════
# 知识图加载
# ═══════════════════════════════════════

def load_graph(tree_path, llm_edges_path=None):
    """加载 CFA 知识树 + LLM 边 → 邻接表 + KP 列表"""
    with open(tree_path) as f:
        data = json.load(f)

    nodes = data['nodes']
    # 只取 KP
    kps = [n for n in nodes if n.get('level') == 'kp']
    kp_ids = [n['id'] for n in kps]
    id_to_idx = {kid: i for i, kid in enumerate(kp_ids)}

    n = len(kps)

    # 构建邻接表
    adj = defaultdict(list)

    # 树边：parent-child（双向 w=0.8）
    for nd in nodes:
        pid = nd.get('parent_id')
        if pid and nd['id'] in id_to_idx and pid in id_to_idx:
            adj[nd['id']].append((pid, 0.8))
            adj[pid].append((nd['id'], 0.8))

    # 兄弟边（w=0.3）
    children_of = defaultdict(list)
    for nd in nodes:
        pid = nd.get('parent_id')
        if pid and nd['id'] in id_to_idx:
            children_of[pid].append(nd['id'])
    for siblings in children_of.values():
        for i in range(len(siblings)):
            for j in range(i+1, len(siblings)):
                adj[siblings[i]].append((siblings[j], 0.3))
                adj[siblings[j]].append((siblings[i], 0.3))

    # LLM 语义边
    if llm_edges_path and os.path.exists(llm_edges_path):
        with open(llm_edges_path) as f:
            llm_edges = json.load(f)
        # 名字 → id 映射
        name_to_id = {n['name']: n['id'] for n in kps}
        added = 0
        for e in llm_edges:
            src = name_to_id.get(e.get('source_name', ''))
            tgt = name_to_id.get(e.get('target_name', ''))
            if src and tgt and src in id_to_idx and tgt in id_to_idx:
                w = float(e.get('weight', 0.5))
                adj[src].append((tgt, w))
                added += 1
        print(f"  LLM edges loaded: {added}")

    # → 稀疏矩阵格式
    row, col, data = [], [], []
    for src_kid, neighbors in adj.items():
        if src_kid in id_to_idx:
            i = id_to_idx[src_kid]
            for tgt_kid, w in neighbors:
                if tgt_kid in id_to_idx:
                    j = id_to_idx[tgt_kid]
                    row.append(i); col.append(j); data.append(w)

    W = csr_matrix((data, (row, col)), shape=(n, n))
    # 度矩阵 D
    deg = np.array(W.sum(axis=1)).flatten()
    # 有向度（出度），L = D_out - W（行随机游走拉普拉斯）
    # 但扩散 du/dt = β·L·u 用的是入边扩散还是出边？
    # Field: 邻居的激活扩散到我 → 入边
    # L_ij = w_ji（从 j 到 i 的权重）
    # 所以 L = W^T - diag(col_sum)
    L = csr_matrix(W.T, shape=(n, n))
    col_sum = np.array(L.sum(axis=1)).flatten()
    L = L - diags(col_sum, 0, shape=(n, n))

    # KP 前置依赖（解锁逻辑）
    prereq_local = {}
    for nd in nodes:
        if nd['level'] == 'kp':
            code = nd.get('code', '')
            parts = code.split('-') if code else []
            num = int(parts[-1]) if parts and parts[-1].isdigit() else 0
            nd['_order'] = num

    # 按 parent 分组，建立前置依赖
    for pid, kids in children_of.items():
        sorted_kids = sorted(kids, key=lambda k: next(
            (nd.get('_order', 0) for nd in nodes if nd['id'] == k), 0))
        for idx in range(1, len(sorted_kids)):
            later_idx = id_to_idx.get(sorted_kids[idx])
            if later_idx is not None:
                prereqs = [id_to_idx[k] for k in sorted_kids[:idx]
                          if k in id_to_idx]
                prereq_local[later_idx] = prereqs

    # 每个 KP 初始解锁状态：无前置依赖的 KP 初始可见
    initial_unlocked = set()
    for i in range(n):
        if i not in prereq_local or not prereq_local[i]:
            initial_unlocked.add(i)

    return {
        'n': n,
        'W': W,        # 边权重矩阵
        'L': L,        # 图拉普拉斯（入边扩散）
        'adj': adj,    # 原始邻接 {kid: [(kid, w)]}
        'id_to_idx': id_to_idx,
        'prereq': prereq_local,
        'initial_unlocked': initial_unlocked,
    }


# ═══════════════════════════════════════
# 共轭梯度求解 centrality
# ═══════════════════════════════════════

def compute_centrality(graph, alpha, beta):
    """求解 (αI - βL)·x = 1，返回 centrality 向量"""
    n = graph['n']
    A = alpha * eye(n) - beta * graph['L']  # αI - βL
    b = np.ones(n)
    x, info = cg(A, b, rtol=CG_TOL, maxiter=CG_MAXITER)
    if info != 0:
        # CG 不收敛时回退到 Jacobi 迭代
        x = np.ones(n) * (1.0 / alpha)  # 初始猜测：β=0 退化
        for _ in range(200):
            x_new = (b + beta * graph['L'].dot(x)) / alpha
            if np.linalg.norm(x_new - x) < CG_TOL * n:
                x = x_new
                break
            x = x_new
    return x


# ═══════════════════════════════════════
# 学生模型（纯 Field 动力学）
# ═══════════════════════════════════════

class FieldStudent:
    def __init__(self, sid, n, coverage=0.5):
        self.sid = sid
        self.n = n
        self.u = np.zeros(n)
        self.total_reviews = 0
        self.mastered = set()   # u > 0.7 的 KP 算掌握
        self.covered_kps = set()
        self.unlocked = set()
        self.coverage = coverage

    def init(self, graph, seed):
        rng = random.Random(seed)
        # 随机选择覆盖范围
        n_secs = max(1, int(len(graph.get('sec_groups', [[0]])) * self.coverage))
        # 简化：随机选 n_kps * coverage 个 KP
        n_covered = max(10, int(self.n * self.coverage))
        all_ids = list(range(self.n))
        self.covered_kps = set(rng.sample(all_ids, min(n_covered, self.n)))
        self.unlocked = set(graph['initial_unlocked'])
        self._update_unlocked(graph)

    def _update_unlocked(self, graph):
        for i in self.covered_kps:
            if i in self.mastered or i in self.unlocked:
                continue
            prereqs = graph['prereq'].get(i, [])
            if not prereqs or all(p in self.mastered for p in prereqs):
                self.unlocked.add(i)

    def eligible(self):
        return [i for i in range(self.n)
                if i in self.unlocked or i in self.mastered]

    def review(self, i, boost=GAMMA):
        self.u[i] += boost * (1.0 - self.u[i])
        self.total_reviews += 1
        if self.u[i] > 0.7:
            self.mastered.add(i)

    def evolve(self, graph, alpha=ALPHA, beta=BETA):
        # u += (-alpha*u + beta*L*u) * DT
        decay = -alpha * self.u
        diffusion = beta * graph['L'].dot(self.u)
        self.u += (decay + diffusion) * DT
        self.u = np.clip(self.u, 0.0, 1.0)

    def end_session(self, graph):
        self._update_unlocked(graph)


# ═══════════════════════════════════════
# FSRS 学生模型（简化版，复用 Phase 0 的参数结构）
# ═══════════════════════════════════════

class FSRSStudent:
    """简化 FSRS：per-KP stability + Weibull 遗忘 + FSRS 更新规则"""
    def __init__(self, sid, n, coverage=0.5):
        self.sid = sid
        self.n = n
        self.S = np.ones(n) * 1.0      # stability（天）
        self.last = np.full(n, -1.0)    # 上次复习时刻
        self.D = np.ones(n) * 3.0       # difficulty
        self.total_reviews = 0
        self.mastered = set()
        self.covered_kps = set()
        self.unlocked = set()
        self.coverage = coverage

    def init(self, graph, seed):
        rng = random.Random(seed)
        n_covered = max(10, int(self.n * self.coverage))
        all_ids = list(range(self.n))
        self.covered_kps = set(rng.sample(all_ids, min(n_covered, self.n)))
        self.unlocked = set(graph['initial_unlocked'])

    def _update_unlocked(self, graph):
        for i in self.covered_kps:
            if i in self.mastered or i in self.unlocked:
                continue
            prereqs = graph['prereq'].get(i, [])
            if not prereqs or all(p in self.mastered for p in prereqs):
                self.unlocked.add(i)

    def eligible(self):
        return [i for i in range(self.n)
                if i in self.unlocked or i in self.mastered]

    def R(self, i, t):
        """Weibull 检索概率"""
        S = self.S[i]
        if S <= 0 or self.last[i] < 0:
            return 0.0
        elapsed = max(0.0, t - self.last[i])
        if elapsed <= 0:
            return 1.0
        k = 1.2
        return float(np.exp(-((elapsed / max(S, 0.01)) ** k)))

    def review(self, i, t, rating=3):
        Sold = self.S[i]
        if Sold <= 1.0:
            Snew = 2.0 + 0.5 * (rating - 2)
        else:
            gain = 0.15 * (0.5 + 0.25 * rating)
            Snew = Sold * (1.0 + gain)
        self.S[i] = max(0.5, min(365.0, Snew))
        self.last[i] = t
        self.total_reviews += 1
        if self.S[i] > 7:
            self.mastered.add(i)

    def get_rating(self, i, t):
        R_val = self.R(i, t)
        skill = self.S[i]
        if skill <= 1.0:
            p_good = 0.4
        elif R_val > 0.85:
            p_good = 0.9
        elif R_val > 0.6:
            p_good = 0.7
        elif R_val > 0.4:
            p_good = 0.5
        else:
            p_good = 0.3
        p_good = max(0.05, min(0.95, p_good + random.uniform(-0.1, 0.1)))
        if p_good > 0.7: return 4 if random.random() < 0.3 else 3
        elif p_good > 0.5: return 3 if random.random() < 0.6 else 2
        elif p_good > 0.3: return 2 if random.random() < 0.6 else 1
        else: return 1

    def end_session(self, graph):
        self._update_unlocked(graph)

    def avg_R(self, t):
        vals = [self.R(i, t) for i in self.covered_kps if self.last[i] >= 0]
        return float(np.mean(vals)) if vals else 0.0


# ═══════════════════════════════════════
# 仿真主循环
# ═══════════════════════════════════════

def simulate_student(graph, student, scheduler, n_days, budget,
                     study_hours=8, seed=0):
    """
    scheduler: 'field' | 'greedy' | 'fsrs'
    """
    np.random.seed((seed + student.sid) % (2**31))
    random.seed((seed + student.sid) % (2**31))

    student.init(graph, seed + student.sid)
    history = []

    actual_hours = max(4, study_hours + random.uniform(-2, 2))
    sleep_hours = 24 - actual_hours
    min_gap = random.uniform(0.05, 0.3)
    max_gap = random.uniform(0.5, 2.0)
    cur_t = 0.0

    # Field：预计算 centrality（整个仿真期间不变）
    if scheduler == 'field':
        centrality = compute_centrality(graph, ALPHA, BETA)

    for day in range(n_days):
        day_start = day * 24
        cur_t = day_start + random.uniform(0, 1)
        student.end_session(graph)
        session_end = day_start + actual_hours

        while cur_t < session_end:
            gap = random.uniform(min_gap, max_gap)
            cur_t += gap
            if cur_t >= session_end:
                break

            eligible = student.eligible()
            if not eligible:
                break

            # ── 选题逻辑 ──
            if scheduler == 'field':
                # score_i = (1-u_i) × centrality_i
                scores = [(1.0 - student.u[i]) * centrality[i] for i in eligible]
                scored = list(zip(eligible, scores))
                scored.sort(key=lambda x: -x[1])
                selected = [x[0] for x in scored[:budget]]

            elif scheduler == 'greedy':
                scores = [1.0 - student.u[i] for i in eligible]
                scored = list(zip(eligible, scores))
                scored.sort(key=lambda x: -x[1])
                selected = [x[0] for x in scored[:budget]]

            elif scheduler == 'fsrs':
                scores = [1.0 - student.R(i, cur_t) if student.last[i] >= 0
                          else 3.0 for i in eligible]
                scored = list(zip(eligible, scores))
                scored.sort(key=lambda x: -x[1])
                selected = [x[0] for x in scored[:budget]]

            # ── 执行复习 ──
            for i in selected:
                if scheduler == 'fsrs':
                    rating = student.get_rating(i, cur_t)
                    student.review(i, cur_t, rating)
                else:
                    student.review(i)
                    # 模拟评分：u 越高 → 评分越高
                    rating = max(1, min(4, int(student.u[i] * 5) - 1))

            cur_t += 0.1 * (budget)  # 每次复习花一点时间

        # 课后演化（一天一次，DT=1天已内置在 evolve 中）
        if scheduler == 'field':
            student.evolve(graph, alpha=ALPHA, beta=BETA)
        elif scheduler == 'greedy':
            student.u *= (1.0 - ALPHA)
            student.u = np.clip(student.u, 0.0, 1.0)

        cur_t = day_start + 24

        # 记录
        if scheduler == 'fsrs':
            final_val = student.avg_R(cur_t)
        else:
            covered_u = [student.u[i] for i in student.covered_kps]
            final_val = float(np.mean(covered_u)) if covered_u else 0.0

        history.append({
            'day': day,
            'avg': final_val,
        })

    final_val = history[-1]['avg']
    return {
        'sid': student.sid,
        'scheduler': scheduler,
        'final': final_val,
        'history': history,
        'total_reviews': student.total_reviews,
    }


# ═══════════════════════════════════════
# 实验运行
# ═══════════════════════════════════════

def summary(arr):
    a = np.array(arr)
    n = len(a)
    return {
        'mean': float(np.mean(a)),
        'std': float(np.std(a, ddof=1)) if n > 1 else 0.0,
        'ci95': 1.96 * float(np.std(a, ddof=1)) / np.sqrt(n) if n > 1 else 0.0,
        'n': n,
    }


def paired_test(a, b):
    """配对 t 检验 + Cohen's d"""
    a, b = np.array(a), np.array(b)
    diffs = b - a
    n = len(diffs)
    mean_diff = float(np.mean(diffs))
    se = float(np.std(diffs, ddof=1)) / np.sqrt(n) if n > 1 else 0
    t = mean_diff / se if se > 0 else 0
    pooled_sd = np.sqrt((np.var(a, ddof=1) + np.var(b, ddof=1)) / 2)
    d = mean_diff / pooled_sd if pooled_sd > 0 else 0
    p = float(math.erfc(abs(t) / np.sqrt(2)))
    return {'mean_diff': mean_diff, 't': t, 'p': p, 'cohens_d': d, 'n': n}


def run_experiment(graph, schedulers, n_students, n_days, budget):
    results = {}
    for sched in schedulers:
        print(f"\n{'='*50}")
        print(f"Scheduler: {sched}")
        print(f"{'='*50}")
        t0 = time.time()
        runs = []
        for i in range(n_students):
            if (i+1) % 25 == 0:
                t_elapsed = time.time() - t0
                print(f"  {i+1}/{n_students} students ({t_elapsed:.0f}s)", flush=True)

            if sched == 'fsrs':
                s = FSRSStudent(i, graph['n'], coverage=0.5 + 0.05 * (i % 5))
            else:
                s = FieldStudent(i, graph['n'], coverage=0.5 + 0.05 * (i % 5))

            r = simulate_student(graph, s, sched, n_days, budget,
                                 seed=1000 + i)
            runs.append(r)

        t_total = time.time() - t0
        final_vals = [r['final'] for r in runs]
        stats = summary(final_vals)
        results[sched] = {
            'runs': runs,
            'summary': stats,
        }
        print(f"  Done: {stats['mean']:.4f} ± {stats['ci95']:.4f} ({t_total:.0f}s)")

    return results


def print_comparison(results):
    print(f"\n{'='*70}")
    print(f"FINAL COMPARISON  (N={results[list(results.keys())[0]]['summary']['n']})")
    print(f"{'='*70}")
    print(f"{'Scheduler':>12} {'Mean':>8} {'±CI95':>10} {'Δgreedy':>10}")

    greedy_mean = results.get('greedy', {}).get('summary', {}).get('mean', 0)
    if greedy_mean == 0:
        greedy_mean = results.get('field', {}).get('summary', {}).get('mean', 0)

    for sched in ['field', 'greedy', 'fsrs']:
        if sched in results:
            r = results[sched]['summary']
            delta = r['mean'] - greedy_mean if sched != 'greedy' else 0
            print(f"{sched:>12} {r['mean']:8.4f} ±{r['ci95']:8.4f} {delta:+10.4f}")

    # 配对检验
    if 'field' in results and 'greedy' in results:
        f_vals = [rr['final'] for rr in results['field']['runs']]
        g_vals = [rr['final'] for rr in results['greedy']['runs']]
        t = paired_test(g_vals, f_vals)
        sig = '***' if t['p'] < 0.001 else ('**' if t['p'] < 0.01 else (
            '*' if t['p'] < 0.05 else 'ns'))
        print(f"\nField vs Greedy: Δ={t['mean_diff']:+.4f}  "
              f"t={t['t']:.1f}  p={t['p']:.4f} {sig}  d={t['cohens_d']:.3f}")

    if 'fsrs' in results:
        if 'greedy' in results:
            f_vals2 = [rr['final'] for rr in results['fsrs']['runs']]
            g_vals2 = [rr['final'] for rr in results['greedy']['runs']]
            t2 = paired_test(g_vals2, f_vals2)
            sig2 = '***' if t2['p'] < 0.001 else ('**' if t2['p'] < 0.01 else (
                '*' if t2['p'] < 0.05 else 'ns'))
            print(f"FSRS  vs Greedy: Δ={t2['mean_diff']:+.4f}  "
                  f"t={t2['t']:.1f}  p={t2['p']:.4f} {sig2}  d={t2['cohens_d']:.3f}")

    print()


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    tree_path = os.path.join(script_dir, 'cfa_tree.json')
    llm_path = os.path.join(script_dir, 'cfa_llm_edges.json')

    print("=" * 60)
    print("Memorix-Field 纯模型仿真")
    print(f"α={ALPHA}  β={BETA}  γ={GAMMA}")
    print("=" * 60)

    t0 = time.time()
    graph = load_graph(tree_path, llm_path)

    # 构建 sec_groups（coverage 需要）
    nodes_data = json.load(open(tree_path))['nodes']
    cbp = defaultdict(list)
    for nd in nodes_data:
        if nd.get('parent_id') and nd.get('level') == 'kp':
            idx = graph['id_to_idx'].get(nd['id'])
            if idx is not None:
                cbp[nd['parent_id']].append(idx)
    graph['sec_groups'] = list(cbp.values())

    print(f"Graph: {graph['n']} KPs, {graph['W'].nnz} edges")
    print(f"Max degree: {max(np.array(graph['W'].sum(axis=1)).flatten()):.0f}")

    # 验证稳定性条件
    from scipy.sparse.linalg import eigsh
    try:
        evals = eigsh(-graph['L'], k=1, which='LM', return_eigenvectors=False)
        lambda_max = evals[0]
        print(f"λ_max(L) = {lambda_max:.2f}")
        print(f"β_limit  = α/λ_max = {ALPHA/lambda_max:.4f}")
        if BETA > ALPHA/lambda_max:
            print(f"⚠️  BETA={BETA} > limit={ALPHA/lambda_max:.4f} — 系统可能不稳定！")
        else:
            print(f"✅ BETA={BETA} < limit — 系统稳定")
    except Exception as e:
        print(f"⚠️  特征值计算失败: {e}")

    schedulers = ['field', 'greedy', 'fsrs']
    results = run_experiment(graph, schedulers, N_STUDENTS, N_DAYS, BUDGET)
    print_comparison(results)

    total_elapsed = time.time() - t0
    print(f"Total time: {total_elapsed:.0f}s ({total_elapsed/60:.1f}min)")

    # 保存
    os.makedirs(os.path.join(script_dir, 'output'), exist_ok=True)
    out = {sched: results[sched]['summary']
           for sched in results}
    out_path = os.path.join(script_dir, 'output', 'field_pure_results.json')
    with open(out_path, 'w') as f:
        json.dump(out, f, indent=2, default=float)
    print(f"Results saved to {out_path}")


if __name__ == '__main__':
    main()
