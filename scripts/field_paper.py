#!/usr/bin/env python3
"""
Field 论文对比：Naive / Ability / IRT / LabelProp / Field GMRF

五组基线回答三个审稿问题：
  Naive:     图比不用图好吗？（下界）
  Ability:   图比"用全班平均推测个人"好吗？
  IRT:       图比标准心理测量模型好吗？
  LabelProp: 图比简单图平滑好吗？
  Field:     我们的方法
  λ=0:       图贡献消融
"""
import json, math, time, random, numpy as np
from collections import defaultdict
from scipy.sparse import csr_matrix, diags, eye
from scipy.sparse.linalg import cg


# ═══════════════════════════════════════════════════
# GMRF 诊断引擎
# ═══════════════════════════════════════════════════

class FieldGMRF:
    def __init__(self, tree_file, edge_file, lam=2.0):
        self.lam = lam
        with open(tree_file) as f: data = json.load(f)
        nodes = data['nodes']
        self.kps = [n for n in nodes if n.get('level') == 'kp']
        self.n = len(self.kps)
        self.n2id = {nd['name']: nd['id'] for nd in self.kps}
        self.id2i = {kid: i for i, kid in enumerate([n['id'] for n in self.kps])}
        self._build_graph(edge_file, nodes)
        self._build_precision()

    def _build_graph(self, edge_file, nodes):
        adj = defaultdict(list)
        for nd in nodes:
            pid = nd.get('parent_id')
            if pid and nd['id'] in self.id2i and pid in self.id2i:
                adj[nd['id']].append((pid, 0.8)); adj[pid].append((nd['id'], 0.8))
        cbp = defaultdict(list)
        for nd in nodes:
            pid = nd.get('parent_id')
            if pid and nd['id'] in self.id2i: cbp[pid].append(nd['id'])
        for s in cbp.values():
            for i in range(len(s)):
                for j in range(i+1,len(s)): adj[s[i]].append((s[j],0.3)); adj[s[j]].append((s[i],0.3))
        with open(edge_file) as f: llm = json.load(f)
        pair_seen = set()
        for e in llm:
            s=self.n2id.get(e.get('source_name','')); t=self.n2id.get(e.get('target_name',''))
            if not(s and t and s in self.id2i and t in self.id2i): continue
            si,ti=self.id2i[s],self.id2i[t]; pair=tuple(sorted([si,ti]))
            if pair in pair_seen: continue
            pair_seen.add(pair)
            w=float(e.get('weight',0.5)); adj[s].append((t,w)); adj[t].append((s,w))
        row,col,dat=[],[],[]
        for sk,ns in adj.items():
            if sk in self.id2i:
                si=self.id2i[sk]
                for tk,w in ns:
                    if tk in self.id2i: row.append(si);col.append(self.id2i[tk]);dat.append(w)
        self.A=csr_matrix((dat,(row,col)),shape=(self.n,self.n))

    def _build_precision(self):
        deg=np.array(self.A.sum(axis=1)).flatten(); deg[deg<1e-8]=1.0
        D_inv_sqrt=diags(1.0/np.sqrt(deg),0)
        L_norm=eye(self.n,format='csr')-D_inv_sqrt.dot(self.A).dot(D_inv_sqrt)
        self.Q_base=self.lam*L_norm+1e-4*eye(self.n,format='csr')

    def diagnose(self, observed_indices, observed_values, observed_precisions=None):
        if observed_precisions is None: observed_precisions=[4.0]*len(observed_indices)
        d_data=np.zeros(self.n)
        for idx,prec in zip(observed_indices,observed_precisions): d_data[idx]=prec
        D=diags(d_data,0,shape=(self.n,self.n))
        b=np.zeros(self.n)
        for idx,val,prec in zip(observed_indices,observed_values,observed_precisions): b[idx]=val*prec
        Q=self.Q_base+D
        mu,info=cg(Q,b,rtol=1e-6,maxiter=500)
        if info!=0:
            mu=np.full(self.n,0.5)
            for idx,val in zip(observed_indices,observed_values): mu[idx]=val
        return mu


# ═══════════════════════════════════════════════════
# 独立学生仿真（不变）
# ═══════════════════════════════════════════════════

class IndependentStudentSim:
    """
    独立学生仿真。

    ★ 同一 Topic（树 parent 节点）下的 KP 共享相似难度。
    这是真实的教育场景：同一章的知识点天然难度相近。
    这创造了图可以利用的真实结构，但不等于 Field 的平滑假设。
    """
    def __init__(self, tree_file, n_students=200, n_days=100, seed=42):
        with open(tree_file) as f: data = json.load(f)
        nodes = data['nodes']
        self.kps = [n for n in nodes if n.get('level') == 'kp']
        self.n = len(self.kps)
        self.names = [n['name'] for n in self.kps]

        # ★ 按 parent_id 分组 → 同一 Topic 的 KP 共享难度
        np.random.seed(seed)
        topic_difficulty = {}  # parent_id → 难度
        for nd in nodes:
            pid = nd.get('parent_id', 'root')
            if pid not in topic_difficulty:
                topic_difficulty[pid] = np.random.beta(2, 5)  # 偏容易的分布

        self.difficulty = np.zeros(self.n)
        for i, nd in enumerate(self.kps):
            pid = nd.get('parent_id', 'root')
            base = topic_difficulty.get(pid, 0.3)
            self.difficulty[i] = np.clip(base + np.random.normal(0, 0.05), 0.01, 0.99)

        self.n_students = n_students
        self.n_days = n_days
        self.gamma_base = 0.30
        self.diff_impact = 0.6

    def run(self, daily_budget=10, test_interval=14, test_coverage=0.05):
        results = []
        for s in range(self.n_students):
            student_seed = 10000 + s
            np.random.seed(student_seed); random.seed(student_seed)
            K = np.zeros(self.n); observations = []
            for day in range(self.n_days):
                urgencies = []
                for i in range(self.n):
                    if K[i] < 0.01: u = 10.0 * (1 - 0.3 * self.difficulty[i])
                    else: u = (1.0 - K[i]) / K[i] * (1 - 0.3 * self.difficulty[i])
                    urgencies.append(u)
                top = sorted(range(self.n), key=lambda i: -urgencies[i])[:daily_budget]
                for i in top:
                    gamma_i = self.gamma_base * (1 - self.diff_impact * self.difficulty[i])
                    K[i] += gamma_i * (1 - K[i]); K[i] = np.clip(K[i], 0, 1)
                K *= 0.985; K += np.random.normal(0, 0.008, self.n); K = np.clip(K, 0, 1)
                if day > 0 and day % test_interval == 0:
                    n_test = max(3, int(self.n * test_coverage))
                    tested = random.sample(range(self.n), min(n_test, self.n))
                    for i in tested:
                        p = 1.0 / (1.0 + math.exp(-5 * (K[i] - self.difficulty[i])))
                        correct = random.random() < p
                        observations.append((day, i, correct))
                        if correct: K[i] += 0.03 * (1 - K[i])
                        K = np.clip(K, 0, 1)
            results.append({'true_K': K.copy(), 'observations': observations, 'difficulty': self.difficulty.copy()})
        return results


# ═══════════════════════════════════════════════════
# 五大基线
# ═══════════════════════════════════════════════════

def baseline_naive(obs_indices, obs_values, n):
    mu = np.full(n, 0.5)
    for i, v in zip(obs_indices, obs_values): mu[i] = v
    return mu

def baseline_ability(observations, n):
    """学生整体能力：观测到的平均正确率作为全局估计"""
    if not observations: return np.full(n, 0.5)
    avg_correct = np.mean([1.0 if c else 0.0 for _, _, c in observations])
    return np.full(n, avg_correct)

def baseline_irt(observations, difficulties, n):
    """
    1PL Rasch: P(correct | θ, b_i) = sigmoid(θ - b_i)
    先用所有学生的数据估计项目难度 b_i，再估计每个学生的能力 θ
    """
    # 项目难度：从该 KP 所有观测的正确率估计
    obs_by_kp = defaultdict(list)
    for _, idx, correct in observations:
        obs_by_kp[idx].append(1.0 if correct else 0.0)

    # 对每个有观测的 KP，用正确率转换难度
    b = np.zeros(n)
    for i in range(n):
        if obs_by_kp[i]:
            p = np.mean(obs_by_kp[i])
            p = np.clip(p, 0.05, 0.95)
            b[i] = -math.log(p / (1 - p))  # logit
        else:
            b[i] = 0  # 无观测 → 默认中等难度

    # 学生能力 θ: 使观测的 log-likelihood 最大
    # 用牛顿法一步近似
    theta = 0.0
    for _ in range(5):
        grad = 0.0; hess = 0.0
        for _, idx, correct in observations:
            p = 1.0 / (1.0 + math.exp(-(theta - b[idx])))
            y = 1.0 if correct else 0.0
            grad += y - p
            hess += p * (1 - p)
        if hess > 0:
            theta += grad / hess
    theta = np.clip(theta, -3, 3)

    # 输出每个 KP 的掌握度估计
    mu = np.zeros(n)
    for i in range(n):
        mu[i] = 1.0 / (1.0 + math.exp(-(theta - b[i])))
    return mu

def baseline_labelprop(obs_indices, obs_values, A, n, alpha=0.5, n_iter=20):
    """
    Label Propagation: Y^(t+1) = α A_norm Y^(t) + (1-α) Y^(0)
    最简单有效的图半监督学习方法。
    """
    # 初始化
    Y = np.full((n, 1), 0.5)
    for idx, val in zip(obs_indices, obs_values):
        Y[idx, 0] = val
    Y0 = Y.copy()

    # 归一化邻接矩阵
    deg = np.array(A.sum(axis=1)).flatten(); deg[deg < 1e-8] = 1.0
    D_inv = diags(1.0 / deg, 0)
    A_norm = D_inv.dot(A)

    for _ in range(n_iter):
        Y = alpha * A_norm.dot(Y) + (1 - alpha) * Y0

    return Y.flatten()


# ═══════════════════════════════════════════════════
# 评测
# ═══════════════════════════════════════════════════

def evaluate_all(tree_file, edge_file, sim_results, lam=2.0):
    engine = FieldGMRF(tree_file, edge_file, lam=lam)
    A = engine.A  # 邻接矩阵
    n = engine.n

    all_mae = {k: [] for k in ['naive', 'ability', 'irt', 'labelprop', 'field']}
    all_corr_field = []

    for r in sim_results:
        true_K = r['true_K']
        obs = r['observations']
        diff = r['difficulty']

        obs_dict = {}
        for day, idx, correct in obs:
            obs_dict[idx] = 0.85 if correct else 0.15
        obs_indices = list(obs_dict.keys())
        obs_values = [obs_dict[i] for i in obs_indices]

        all_mae['naive'].append(np.mean(np.abs(baseline_naive(obs_indices, obs_values, n) - true_K)))
        all_mae['ability'].append(np.mean(np.abs(baseline_ability(obs, n) - true_K)))
        all_mae['irt'].append(np.mean(np.abs(baseline_irt(obs, diff, n) - true_K)))
        all_mae['labelprop'].append(np.mean(np.abs(baseline_labelprop(obs_indices, obs_values, A, n) - true_K)))

        mu_field = engine.diagnose(obs_indices, obs_values)
        all_mae['field'].append(np.mean(np.abs(mu_field - true_K)))
        all_corr_field.append(np.corrcoef(mu_field, true_K)[0, 1])

    return {k: (np.mean(v), np.std(v)) for k, v in all_mae.items()}, np.mean(all_corr_field)


# ═══════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════
if __name__ == '__main__':
    TREES = {'CFA': ('cfa_tree.json', 'cfa_llm_edges.json'),
             'Math': ('math_tree.json', 'math_llm_edges.json')}

    print("=" * 90)
    print("Field 论文对比：Naive | Ability | IRT | LabelProp | Field(GMRF)")
    print("=" * 90)

    for name, (tf, ef) in TREES.items():
        with open(tf) as f: data = json.load(f)
        n_kps = len([n for n in data['nodes'] if n.get('level') == 'kp'])

        print(f"\n{'─'*90}")
        print(f"[{name}] n={n_kps}  数据: 难度驱动, 独立演化, 无前置")
        print(f"{'─'*90}")

        sim = IndependentStudentSim(tf, n_students=200, n_days=100, seed=42)
        sim_results = sim.run()
        avg_obs = np.mean([len(r['observations']) for r in sim_results])
        avg_K = np.mean([np.mean(r['true_K']) for r in sim_results])
        print(f"  avg observations/student: {avg_obs:.0f}  avg true_K: {avg_K:.4f}")

        # 扫描 λ 和 LP alpha
        for lam in [0.5, 1.0, 2.0, 4.0, 8.0]:
            m, corr = evaluate_all(tf, ef, sim_results, lam=lam)

            def vs(a, b): return (b - a) / max(b, 0.001) * 100

            best_other = min(m['naive'][0], m['ability'][0], m['irt'][0], m['labelprop'][0])
            improvement = vs(m['field'][0], best_other)

            print(f"  λ={lam:.1f} (corr={corr:.4f}):", end="", flush=True)
            for method in ['naive', 'ability', 'irt', 'labelprop', 'field']:
                star = ' ★' if method == 'field' else '  '
                print(f" {method}={m[method][0]:.4f}{star}", end="", flush=True)
            print(f"  vs best={improvement:+.1f}%", flush=True)

    # 消融
    print(f"\n{'='*90}")
    print("消融: λ≈0 (no graph) → 图贡献")
    print(f"{'='*90}")
    for name, (tf, ef) in TREES.items():
        with open(tf) as f: data = json.load(f)
        n_kps = len([n for n in data['nodes'] if n.get('level') == 'kp'])
        sim = IndependentStudentSim(tf, n_students=200, n_days=100, seed=42)
        sim_results = sim.run()
        m0, _ = evaluate_all(tf, ef, sim_results, lam=0.01)
        m2, _ = evaluate_all(tf, ef, sim_results, lam=2.0)
        d = (m0['field'][0] - m2['field'][0]) / m0['field'][0] * 100
        print(f"  [{name}] λ≈0: Field={m0['field'][0]:.4f}  λ=2: Field={m2['field'][0]:.4f}  graph contrib={d:+.1f}%")
