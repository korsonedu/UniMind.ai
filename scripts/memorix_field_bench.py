#!/usr/bin/env python3
"""
Memorix-Field 统一基准仿真
===========================
统一底盘（真实知识 K）+ 三种调度器 + 真实学生行为

底盘：
  K_i ∈ [0,1]  真实掌握度
  dK_i/dt = -α·K_i                         自然遗忘
  review i: K_i += γ×(1-K_i)               复习增益
  图转移:   K_j += η×w_ij×(1-K_j)         复习 i 时微幅提升邻居（真实结构学习）

学生行为：
  - 每天不一定学习（概率 study_rate）
  - 考试：每 exam_interval 天，随机测一批 KP，正确率影响后续学习效率
  - 隔夜遗忘：每天结束时额外衰减 sleep_decay
  - 疲劳：session 内复习效率递减
  - 难度：每个 KP 有难度 base_difficulty，影响衰减速率

调度器（各自有独立的状态估计器）：
  Greedy: 直接看 K_i，选 max(1-K_i)
  Field:  维护 u_i（含图扩散），选 max((1-u_i)×centrality_i)
  FSRS:   维护 S_i + last_review，选 max(1-R(S_i, elapsed))

评价指标：150 天后 avg(K_i)
"""

import json, math, time, os, random
from collections import defaultdict
import numpy as np
from scipy.sparse import csr_matrix, eye, diags
from scipy.sparse.linalg import cg

# ═══════════════════════════════════════
# 配置
# ═══════════════════════════════════════
ALPHA       = 0.01      # 自然衰减率 /天
BETA        = 0.0003    # Field 内部扩散强度
GAMMA       = 0.30      # 复习增益
ETA         = 0.02      # 图转移强度（邻居微弱受益，~2%复习效果）
SLEEP_DECAY = 0.005     # 隔夜额外衰减
STUDY_RATE  = 0.85      # 每天学习的概率
FATIGUE_MAX = 0.40      # session 内疲劳上限（复习增益最多衰减 40%）
EXAM_INTERVAL = 20      # 考试间隔（天）
EXAM_COVERAGE = 0.15    # 每次考试覆盖 KP 比例
MIN_DIFFICULTY = 0.5    # KP 难度下限
MAX_DIFFICULTY = 2.0    # KP 难度上限

# 仿真规模
N_STUDENTS  = 200
N_DAYS      = 150
BUDGET      = 6
STUDY_HOURS = 8

# 共轭梯度
CG_TOL    = 1e-6
CG_MAXITER = 50

# Weibull shape (FSRS)
K_WEIBULL = 1.2


# ═══════════════════════════════════════
# 知识图加载
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
    # parent-child
    for nd in nodes:
        pid = nd.get('parent_id')
        if pid and nd['id'] in id_to_idx and pid in id_to_idx:
            adj[nd['id']].append((pid, 0.8))
            adj[pid].append((nd['id'], 0.8))
    # siblings
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
    # LLM edges
    if llm_edges_path and os.path.exists(llm_edges_path):
        with open(llm_edges_path) as f:
            llm_edges = json.load(f)
        name_to_id = {n['name']: n['id'] for n in kps}
        added = 0
        for e in llm_edges:
            src = name_to_id.get(e.get('source_name', ''))
            tgt = name_to_id.get(e.get('target_name', ''))
            if src and tgt and src in id_to_idx and tgt in id_to_idx:
                w = float(e.get('weight', 0.5))
                adj[src].append((tgt, w))
                added += 1
        print(f"  LLM edges: {added}")

    # 稀疏矩阵
    row, col, data = [], [], []
    for src_kid, neighbors in adj.items():
        if src_kid in id_to_idx:
            i = id_to_idx[src_kid]
            for tgt_kid, w in neighbors:
                if tgt_kid in id_to_idx:
                    j = id_to_idx[tgt_kid]
                    row.append(i); col.append(j); data.append(w)
    W = csr_matrix((data, (row, col)), shape=(n, n))

    # 图拉普拉斯（入边扩散）
    L = csr_matrix(W.T, shape=(n, n))
    col_sum = np.array(L.sum(axis=1)).flatten()
    L = L - diags(col_sum, 0, shape=(n, n))

    # 前置依赖
    prereq_local = {}
    for nd in nodes:
        if nd['level'] == 'kp':
            code = nd.get('code', '')
            parts = code.split('-') if code else []
            nd['_order'] = int(parts[-1]) if parts and parts[-1].isdigit() else 0
    for pid, kids in cbp.items():
        sorted_kids = sorted(kids, key=lambda k: next(
            (nd.get('_order', 0) for nd in nodes if nd['id'] == k), 0))
        for idx in range(1, len(sorted_kids)):
            li = id_to_idx.get(sorted_kids[idx])
            if li is not None:
                prereq_local[li] = [id_to_idx[k] for k in sorted_kids[:idx] if k in id_to_idx]

    initial_unlocked = {i for i in range(n) if i not in prereq_local or not prereq_local[i]}

    # 难度
    difficulties = {}
    for nd in nodes:
        if nd['level'] == 'kp' and nd['id'] in id_to_idx:
            code = nd.get('code', '')
            depth = code.count('-') if code else 0
            difficulties[id_to_idx[nd['id']]] = min(MAX_DIFFICULTY,
                max(MIN_DIFFICULTY, 0.8 + depth * 0.15))

    return {
        'n': n, 'W': W, 'L': L, 'adj': adj,
        'id_to_idx': id_to_idx, 'prereq': prereq_local,
        'initial_unlocked': initial_unlocked,
        'difficulties': difficulties,
    }


def compute_centrality(graph, alpha, beta):
    """解 (αI - βL)·x = 1"""
    n = graph['n']
    A = alpha * eye(n) - beta * graph['L']
    b = np.ones(n)
    x, info = cg(A, b, rtol=CG_TOL, maxiter=CG_MAXITER)
    if info != 0:
        x = np.ones(n) * (1.0/alpha)
        for _ in range(200):
            x_new = (b + beta * graph['L'].dot(x)) / alpha
            if np.linalg.norm(x_new - x) < CG_TOL * n:
                return x_new
            x = x_new
    return x


# ═══════════════════════════════════════
# 调度器状态（各自的估计器）
# ═══════════════════════════════════════

class GreedyEstimator:
    """贪心 urgency：直接看 K"""
    def __init__(self, n):
        pass
    def score(self, kp_indices, K, _graph):
        return [1.0 - K[i] for i in kp_indices]


class FieldEstimator:
    """Field：维护 u + 图扩散，score = (1-u) × centrality"""
    def __init__(self, n, centrality):
        self.u = np.zeros(n)
        self.centrality = centrality
    def score(self, kp_indices, K, graph):
        return [(1.0 - self.u[i]) * self.centrality[i] for i in kp_indices]
    def evolve(self, graph, alpha, beta):
        self.u += (-alpha * self.u + beta * graph['L'].dot(self.u))
        self.u = np.clip(self.u, 0.0, 1.0)


class FSRSEstimator:
    """FSRS：维护 per-KP stability + Weibull 遗忘"""
    def __init__(self, n):
        self.S = np.ones(n) * 1.5   # 初始稳定性（天）
        self.last = np.full(n, -1.0)
    def score(self, kp_indices, K, graph):
        scores = []
        for i in kp_indices:
            if self.last[i] < 0:
                scores.append(3.0)  # 新知识点，高优先级
            else:
                elapsed = max(0.001, self.S[i])   # 用 S 近似 elapsed
                R = math.exp(-((elapsed / max(self.S[i], 0.01)) ** K_WEIBULL))
                scores.append(1.0 - R)
        return scores
    def update(self, i, rating):
        """FSRS 稳定性更新"""
        Sold = self.S[i]
        if Sold <= 1.5:
            Snew = 2.5 + 0.5 * (rating - 2)
        else:
            gain = 0.15 * (0.5 + 0.25 * rating)
            Snew = Sold * (1.0 + gain)
        self.S[i] = max(1.0, min(365.0, Snew))


# ═══════════════════════════════════════
# 统一学生（真实知识 K）
# ═══════════════════════════════════════

class Student:
    """统一学生模型：K 是真实掌握度，所有调度器共享此底盘"""
    def __init__(self, sid, n, coverage=0.5):
        self.sid = sid
        self.n = n
        self.K = np.zeros(n)          # 真实掌握度
        self.total_reviews = 0
        self.mastered = set()         # K > 0.7
        self.covered_kps = set()
        self.unlocked = set()
        self.coverage = coverage
        self.session_reviews = 0      # 当日复习次数

    def init(self, graph, seed):
        rng = random.Random(seed)
        n_covered = max(10, int(self.n * self.coverage))
        self.covered_kps = set(rng.sample(list(range(self.n)), min(n_covered, self.n)))
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
        return [i for i in range(self.n) if i in self.unlocked or i in self.mastered]

    def review(self, i, graph, fatigue=0.0):
        """复习 KP i，更新 K_i + 图转移"""
        boost = GAMMA * (1.0 - self.K[i]) * (1.0 - fatigue * FATIGUE_MAX)
        self.K[i] += boost

        # 图转移：复习 i → 邻居 j 微幅提升（真实结构学习）
        kid_i = self._idx_kid_map.get(i) if hasattr(self, '_idx_kid_map') else None
        if kid_i is not None:
            for tgt_kid, w in graph['adj'].get(kid_i, []):
                tgt_idx = graph['id_to_idx'].get(tgt_kid)
                if tgt_idx is not None:
                    transfer = ETA * w * (1.0 - self.K[tgt_idx])
                    self.K[tgt_idx] += transfer

        self.K = np.clip(self.K, 0.0, 1.0)
        self.total_reviews += 1
        self.session_reviews += 1

        if self.K[i] > 0.7:
            self.mastered.add(i)

    def _idx_to_kid(self, i):
        """内部索引 → KP ID（用于邻接表查询）"""
        # 需要反向映射，在 main 里注入
        if not hasattr(self, '_idx_kid_map'):
            return None
        return self._idx_kid_map.get(i)

    def overnight_decay(self, graph):
        """隔夜遗忘 + 按难度衰减"""
        for i in range(self.n):
            diff = graph['difficulties'].get(i, 1.0)
            self.K[i] *= (1.0 - ALPHA - SLEEP_DECAY * diff)
        self.K = np.clip(self.K, 0.0, 1.0)

    def exam(self, graph, seed):
        """考试：随机测一批 KP，正确率影响"""
        rng = random.Random(seed)
        covered = list(self.covered_kps)
        n_test = max(3, int(len(covered) * EXAM_COVERAGE))
        tested = rng.sample(covered, min(n_test, len(covered)))

        correct = 0
        for i in tested:
            K_i = self.K[i]
            diff = graph['difficulties'].get(i, 1.0)
            p_correct = K_i / diff  # 难的东西正确率更低
            p_correct = max(0.05, min(0.98, p_correct + random.uniform(-0.1, 0.1)))
            if random.random() < p_correct:
                correct += 1
                # 正确则强化
                self.K[i] += 0.05 * (1.0 - self.K[i])
            else:
                pass  # 错误不改变 K

        self.K = np.clip(self.K, 0.0, 1.0)
        return correct / max(1, len(tested))


# ═══════════════════════════════════════
# 仿真主循环
# ═══════════════════════════════════════

def simulate_student(graph, student, estimator, scheduler_name,
                     n_days, budget, study_hours=8, seed=0):
    """统一仿真：底盘 K + 调度器的估计器"""
    np.random.seed((seed + student.sid) % (2**31))
    random.seed((seed + student.sid) % (2**31))

    student.init(graph, seed + student.sid)
    history = []

    actual_hours = max(4, study_hours + random.uniform(-2, 2))

    for day in range(n_days):
        # — 跳过休息日 —
        if random.random() > STUDY_RATE:
            student.overnight_decay(graph)
            # estimator 也要衰减（Field u 和 FSRS S 不受影响——它们只在学习日被更新）
            if scheduler_name == 'field':
                estimator.evolve(graph, ALPHA, BETA)
            history.append({'day': day, 'avg_K': float(np.mean(
                [student.K[i] for i in student.covered_kps]) if student.covered_kps else 0)})
            continue

        student.session_reviews = 0
        student._update_unlocked(graph)

        day_start = day * 24
        cur_t = day_start + random.uniform(0, 1)
        session_end = day_start + actual_hours

        while cur_t < session_end:
            gap = random.uniform(0.05, 0.3)
            cur_t += gap
            if cur_t >= session_end:
                break

            eligible = student.eligible()
            if not eligible:
                break

            # ── 调度器选题 ──
            scores = estimator.score(eligible, student.K, graph)
            scored = list(zip(eligible, scores))
            scored.sort(key=lambda x: -x[1])
            selected = [x[0] for x in scored[:budget]]

            # ── 疲劳计算 ──
            fatigue = min(1.0, student.session_reviews / 30.0)

            # ── 执行复习 ──
            for i in selected:
                student.review(i, graph, fatigue)

                # 更新各估计器
                rating = max(1, min(4, int(student.K[i] * 5) - 1))
                if scheduler_name == 'fsrs':
                    estimator.update(i, rating)

                # Field 的 u 也要追 K
                if scheduler_name == 'field':
                    estimator.u[i] += GAMMA * (1.0 - estimator.u[i])

            cur_t += 0.1 * budget

        # 一天结束
        student.overnight_decay(graph)

        if scheduler_name == 'field':
            estimator.evolve(graph, ALPHA, BETA)

        # 考试
        if day > 0 and day % EXAM_INTERVAL == 0:
            student.exam(graph, seed + day * 1000 + student.sid)

        # 记录
        covered_K = [student.K[i] for i in student.covered_kps]
        avg_K = float(np.mean(covered_K)) if covered_K else 0.0
        history.append({'day': day, 'avg_K': avg_K})

    final_K = history[-1]['avg_K']
    return {
        'sid': student.sid,
        'scheduler': scheduler_name,
        'final_K': final_K,
        'history': history,
        'total_reviews': student.total_reviews,
    }


# ═══════════════════════════════════════
# 实验
# ═══════════════════════════════════════

def summary(arr):
    a = np.array(arr)
    n = len(a)
    return {'mean': float(np.mean(a)), 'std': float(np.std(a, ddof=1)) if n>1 else 0,
            'ci95': 1.96*float(np.std(a, ddof=1))/np.sqrt(n) if n>1 else 0, 'n': n}

def paired_test(a, b):
    a, b = np.array(a), np.array(b)
    diffs = b - a
    n = len(diffs)
    md = float(np.mean(diffs))
    se = float(np.std(diffs, ddof=1))/np.sqrt(n) if n>1 else 0
    t = md/se if se>0 else 0
    ps = np.sqrt((np.var(a, ddof=1)+np.var(b, ddof=1))/2)
    d = md/ps if ps>0 else 0
    p = float(math.erfc(abs(t)/np.sqrt(2)))
    return {'mean_diff':md, 't':t, 'p':p, 'cohens_d':d, 'n':n}


def run_experiment(graph, n_students, n_days, budget):
    centrality = compute_centrality(graph, ALPHA, BETA)

    # 三种调度配置
    configs = [
        ('greedy', lambda n: GreedyEstimator(n)),
        ('field',  lambda n: FieldEstimator(n, centrality)),
        ('fsrs',   lambda n: FSRSEstimator(n)),
    ]

    results = {}
    for sched_name, make_est in configs:
        print(f"\n{'='*50}\nScheduler: {sched_name}\n{'='*50}")
        t0 = time.time()
        runs = []
        for i in range(n_students):
            if (i+1) % 50 == 0:
                print(f"  {i+1}/{n_students} students ({time.time()-t0:.0f}s)", flush=True)

            est = make_est(graph['n'])
            stu = Student(i, graph['n'], coverage=0.5 + 0.05*(i%5))
            # 注入反向映射
            idx_to_kid = {v:k for k,v in graph['id_to_idx'].items()}
            stu._idx_kid_map = idx_to_kid

            r = simulate_student(graph, stu, est, sched_name, n_days, budget,
                                 seed=1000+i)
            runs.append(r)

        t_total = time.time() - t0
        vals = [r['final_K'] for r in runs]
        st = summary(vals)
        results[sched_name] = {'runs': runs, 'summary': st}
        print(f"  Done: K={st['mean']:.4f} ± {st['ci95']:.4f} ({t_total:.0f}s)")

    return results


def print_report(results):
    print(f"\n{'='*70}")
    print(f"FINAL REPORT  (N={len(results['greedy']['runs'])})")
    print(f"{'='*70}")
    print(f"{'Scheduler':>10} {'K_mean':>8} {'±CI95':>10} {'Δgreedy':>10}")

    g_mean = results['greedy']['summary']['mean']
    for sched in ['greedy', 'field', 'fsrs']:
        r = results[sched]['summary']
        d = r['mean'] - g_mean if sched != 'greedy' else 0
        print(f"{sched:>10} {r['mean']:8.4f} ±{r['ci95']:8.4f} {d:+10.4f}")

    print(f"\n── 配对检验 ──")
    g_vals = [r['final_K'] for r in results['greedy']['runs']]
    for sched in ['field', 'fsrs']:
        f_vals = [r['final_K'] for r in results[sched]['runs']]
        t = paired_test(g_vals, f_vals)
        sig = '***' if t['p']<0.001 else ('**' if t['p']<0.01 else ('*' if t['p']<0.05 else 'ns'))
        print(f"  {sched} vs greedy: Δ={t['mean_diff']:+.4f}  "
              f"t={t['t']:.1f}  p={t['p']:.4f} {sig}  d={t['cohens_d']:.3f}")

    print()


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    tree_path = os.path.join(script_dir, 'cfa_tree.json')
    llm_path = os.path.join(script_dir, 'cfa_llm_edges.json')

    print("="*60)
    print("Memorix-Field 统一基准仿真")
    print(f"α={ALPHA} β={BETA} γ={GAMMA} η={ETA}")
    print(f"sleep_decay={SLEEP_DECAY} study_rate={STUDY_RATE} exam_interval={EXAM_INTERVAL}")
    print("="*60)

    graph = load_graph(tree_path, llm_path)
    print(f"Graph: {graph['n']} KPs, {graph['W'].nnz} edges")

    # 稳定性检查
    from scipy.sparse.linalg import eigsh
    try:
        evals = eigsh(-graph['L'], k=1, which='LM', return_eigenvectors=False)
        lambda_max = evals[0]
        print(f"λ_max(L)={lambda_max:.2f}  β_limit={ALPHA/lambda_max:.4f}  "
              f"{'✅' if BETA<ALPHA/lambda_max else '⚠️ UNSTABLE'}")
    except Exception as e:
        print(f"λ check skipped: {e}")

    results = run_experiment(graph, N_STUDENTS, N_DAYS, BUDGET)
    print_report(results)

    # 可证伪检验
    print("── 可证伪检验 ──")
    greedy_k = np.array([r['final_K'] for r in results['greedy']['runs']])
    field_k = np.array([r['final_K'] for r in results['field']['runs']])
    fsrs_k = np.array([r['final_K'] for r in results['fsrs']['runs']])

    # 1. Field > Greedy?
    n_field_wins = np.sum(field_k > greedy_k)
    print(f"  1. Field beats Greedy in {n_field_wins}/{len(greedy_k)} students "
          f"({n_field_wins/len(greedy_k)*100:.0f}%)")

    # 2. FSRS 方差更大？
    print(f"  2. FSRS std={np.std(fsrs_k):.4f} vs "
          f"Greedy std={np.std(greedy_k):.4f} vs Field std={np.std(field_k):.4f}")

    # 3. 效应量
    cohens = (np.mean(field_k) - np.mean(greedy_k)) / np.sqrt(
        (np.var(field_k) + np.var(greedy_k))/2)
    print(f"  3. Cohen's d (Field vs Greedy): {cohens:.3f}")
    cohens2 = (np.mean(fsrs_k) - np.mean(greedy_k)) / np.sqrt(
        (np.var(fsrs_k) + np.var(greedy_k))/2)
    print(f"  4. Cohen's d (FSRS vs Greedy):  {cohens2:.3f}")

    # 保存
    os.makedirs(os.path.join(script_dir, 'output'), exist_ok=True)
    out = {s: results[s]['summary'] for s in results}
    with open(os.path.join(script_dir, 'output', 'field_bench_results.json'), 'w') as f:
        json.dump(out, f, indent=2, default=float)
    print(f"\nSaved to scripts/output/field_bench_results.json")


if __name__ == '__main__':
    main()
