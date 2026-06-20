#!/usr/bin/env python3
"""
Field 深度审计脚本
回答三个核心问题：
1. Field 为什么输给 LabelProp 和 Ability？
2. GMRF 公式化是否有问题？
3. 图结构到底有多大信息量？
"""
import json, math, random, numpy as np
from collections import defaultdict
from scipy.sparse import csr_matrix, diags, eye
from scipy.sparse.linalg import cg


# ═══════════════════════════════════════════════════
# 1. 图诊断
# ═══════════════════════════════════════════════════

def diagnose_graph(tree_file, edge_file):
    with open(tree_file) as f: data = json.load(f)
    nodes = data['nodes']
    kps = [n for n in nodes if n.get('level') == 'kp']
    kp_ids = set(n['id'] for n in kps)
    id2name = {n['id']: n['name'] for n in kps}
    
    # 树结构边
    parent_child = 0; sibling = 0
    topics = defaultdict(list)
    for nd in kps:
        pid = nd.get('parent_id')
        if pid and pid in kp_ids:
            parent_child += 1
        topics[pid].append(nd['id'])
    for s in topics.values():
        n = len(s); sibling += n*(n-1)//2
    
    # LLM边
    with open(edge_file) as f: llm = json.load(f)
    n2id = {nd['name']: nd['id'] for nd in kps}
    llm_valid = 0; edge_types = defaultdict(int)
    for e in llm:
        edge_types[e.get('edge_type', '?')] += 1
        s = n2id.get(e.get('source_name', ''))
        t = n2id.get(e.get('target_name', ''))
        if s and t and s in kp_ids and t in kp_ids:
            llm_valid += 1
    
    # 度数分布
    adj = defaultdict(set)
    for nd in kps:
        pid = nd.get('parent_id')
        if pid and pid in kp_ids:
            adj[nd['id']].add(pid); adj[pid].add(nd['id'])
    for s in topics.values():
        for i in range(len(s)):
            for j in range(i+1, len(s)):
                adj[s[i]].add(s[j]); adj[s[j]].add(s[i])
    for e in llm:
        s = n2id.get(e.get('source_name', ''))
        t = n2id.get(e.get('target_name', ''))
        if s and t and s in kp_ids and t in kp_ids:
            adj[s].add(t); adj[t].add(s)
    
    degrees = [len(v) for v in adj.values()]
    n_kps = len(kps)
    n_topics = len(topics)
    n_components = count_components(adj, kp_ids)
    
    print(f"\n{'='*60}")
    print(f"[图诊断] {tree_file}")
    print(f"{'='*60}")
    print(f"  KPs: {n_kps}  Topics: {n_topics}  Avg KP/topic: {n_kps/n_topics:.1f}")
    print(f"  树 parent-child: {parent_child}  树 sibling: {sibling}")
    print(f"  LLM 边: {llm_valid} (total raw: {len(llm)})")
    print(f"  LLM 类型: {dict(edge_types)}")
    print(f"  度数: min={min(degrees)} max={max(degrees)} mean={np.mean(degrees):.1f} median={np.median(degrees):.1f}")
    print(f"  连通分量: {n_components}")
    
    return degrees, n_kps, topics

def count_components(adj, kp_ids):
    visited = set()
    comps = 0
    for node in kp_ids:
        if node not in visited:
            comps += 1
            stack = [node]
            while stack:
                v = stack.pop()
                if v in visited: continue
                visited.add(v)
                stack.extend(adj.get(v, set()))
    return comps


# ═══════════════════════════════════════════════════
# 2. 仿真数据诊断
# ═══════════════════════════════════════════════════

class IndependentStudentSim:
    """与 field_paper.py 完全一致的仿真"""
    def __init__(self, tree_file, n_students=200, n_days=100, seed=42):
        with open(tree_file) as f: data = json.load(f)
        nodes = data['nodes']
        self.kps = [n for n in nodes if n.get('level') == 'kp']
        self.n = len(self.kps); self.names = [n['name'] for n in self.kps]
        np.random.seed(seed)
        topic_difficulty = {}
        for nd in nodes:
            pid = nd.get('parent_id', 'root')
            if pid not in topic_difficulty:
                topic_difficulty[pid] = np.random.beta(2, 5)
        self.difficulty = np.zeros(self.n)
        for i, nd in enumerate(self.kps):
            pid = nd.get('parent_id', 'root')
            base = topic_difficulty.get(pid, 0.3)
            self.difficulty[i] = np.clip(base + np.random.normal(0, 0.05), 0.01, 0.99)
        self.n_students = n_students; self.n_days = n_days

    def run(self, daily_budget=10, test_interval=14, test_coverage=0.05):
        results = []
        for s in range(self.n_students):
            np.random.seed(10000+s); random.seed(10000+s)
            K = np.zeros(self.n); observations = []
            for day in range(self.n_days):
                urgencies = [(1.0-K[i])/max(K[i], 0.01) for i in range(self.n)]
                top = sorted(range(self.n), key=lambda i: -urgencies[i])[:daily_budget]
                for i in top:
                    gamma = 0.30 * (1 - 0.6 * self.difficulty[i])
                    K[i] += gamma * (1 - K[i])
                K *= 0.985; K += np.random.normal(0, 0.008, self.n); K = np.clip(K, 0, 1)
                if day > 0 and day % test_interval == 0:
                    n_test = max(3, int(self.n * test_coverage))
                    tested = random.sample(range(self.n), min(n_test, self.n))
                    for i in tested:
                        p = 1.0/(1.0+math.exp(-5*(K[i]-self.difficulty[i])))
                        correct = random.random() < p
                        observations.append((day, i, correct))
                        if correct: K[i] += 0.03*(1-K[i])
                        K = np.clip(K, 0, 1)
            results.append({'true_K': K.copy(), 'observations': observations, 'difficulty': self.difficulty.copy()})
        return results

def diagnose_simulation(sim_results, topics, n_kps):
    """分析仿真数据的真实结构"""
    # 每个学生的 true_K 的统计
    all_K = np.array([r['true_K'] for r in sim_results])
    
    # KP 间方差 vs 学生间方差
    kp_means = all_K.mean(axis=0)
    kp_stds = all_K.std(axis=0)
    
    # 同 topic 内 KP 的相关性
    topic_corrs = []
    for pid, kp_ids in topics.items():
        if len(kp_ids) < 2: continue
        # 取这些 KP 的 index
        pass
    
    # 更简单：所有 KP pair 的相关系数
    corr_matrix = np.corrcoef(all_K.T)
    
    # 按是否是同 topic 分组
    intra_topic_corrs = []
    inter_topic_corrs = []
    
    # 需要 kp_id → index 的映射
    # 这个比较 tricky，先跳过
    
    # 基本统计
    print(f"\n[仿真诊断]")
    print(f"  true_K mean: {kp_means.mean():.4f}  std: {kp_means.std():.4f}")
    print(f"  KP间方差: {kp_means.var():.6f}  学生内KP方差均值: {all_K.var(axis=1).mean():.6f}")
    print(f"  KP均值范围: [{kp_means.min():.4f}, {kp_means.max():.4f}]")
    
    # Ability 基线能到什么水平？
    # Ability = 每个学生的全局平均正确率
    ability_maes = []
    for r in sim_results:
        true_K = r['true_K']
        obs = r['observations']
        if not obs:
            ability_maes.append(np.mean(np.abs(0.5 - true_K)))
            continue
        avg = np.mean([1.0 if c else 0.0 for _, _, c in obs])
        ability_maes.append(np.mean(np.abs(avg - true_K)))
    print(f"  Ability MAE: {np.mean(ability_maes):.4f} ± {np.std(ability_maes):.4f}")
    
    # 最优可能 MAE: 每个 KP 用其真实均值预测
    optimal_mae = np.mean(np.abs(all_K - kp_means))
    print(f"  Oracle MAE (per-KP mean): {optimal_mae:.4f}")
    
    # 随机猜测 MAE
    random_mae = np.mean(np.abs(all_K - 0.5))
    print(f"  Random MAE (guess 0.5): {random_mae:.4f}")
    
    # 观测到的任何信息能降低多少 MAE？
    # 观测过的 KP 抄答案
    observed_maes = []
    for r in sim_results:
        true_K = r['true_K']
        obs = r['observations']
        obs_dict = {}
        for day, idx, correct in obs:
            obs_dict[idx] = 0.85 if correct else 0.15
        mu = np.full(n_kps, 0.5)
        for idx, val in obs_dict.items():
            mu[idx] = val
        observed_maes.append(np.mean(np.abs(mu - true_K)))
    print(f"  Naive MAE: {np.mean(observed_maes):.4f}")
    
    return kp_means, all_K, corr_matrix


# ═══════════════════════════════════════════════════
# 3. GMRF 变体对比
# ═══════════════════════════════════════════════════

class FieldGMRF_variants:
    """测试多种 GMRF 公式化"""
    
    def __init__(self, tree_file, edge_file):
        with open(tree_file) as f: data = json.load(f)
        nodes = data['nodes']
        self.kps = [n for n in nodes if n.get('level') == 'kp']
        self.n = len(self.kps)
        self.n2id = {nd['name']: nd['id'] for nd in self.kps}
        self.id2i = {kid: i for i, kid in enumerate([n['id'] for n in self.kps])}
        self._build_adj(edge_file, nodes)
        self._build_laplacians()
    
    def _build_adj(self, edge_file, nodes):
        adj = defaultdict(list)
        # 树边
        for nd in nodes:
            pid = nd.get('parent_id')
            if pid and nd['id'] in self.id2i and pid in self.id2i:
                adj[nd['id']].append((pid, 0.8)); adj[pid].append((nd['id'], 0.8))
        # 兄弟边
        cbp = defaultdict(list)
        for nd in nodes:
            pid = nd.get('parent_id')
            if pid and nd['id'] in self.id2i: cbp[pid].append(nd['id'])
        for s in cbp.values():
            for i in range(len(s)):
                for j in range(i+1, len(s)):
                    adj[s[i]].append((s[j], 0.3)); adj[s[j]].append((s[i], 0.3))
        # LLM边
        with open(edge_file) as f: llm = json.load(f)
        pair_seen = set()
        for e in llm:
            s = self.n2id.get(e.get('source_name', ''))
            t = self.n2id.get(e.get('target_name', ''))
            if not (s and t and s in self.id2i and t in self.id2i): continue
            si, ti = self.id2i[s], self.id2i[t]
            pair = tuple(sorted([si, ti]))
            if pair in pair_seen: continue
            pair_seen.add(pair)
            w = float(e.get('weight', 0.5))
            adj[s].append((t, w)); adj[t].append((s, w))
        # 构建稀疏邻接矩阵
        row, col, dat = [], [], []
        for sk, ns in adj.items():
            if sk in self.id2i:
                si = self.id2i[sk]
                for tk, w in ns:
                    if tk in self.id2i:
                        row.append(si); col.append(self.id2i[tk]); dat.append(w)
        self.A = csr_matrix((dat, (row, col)), shape=(self.n, self.n))
        self.deg = np.array(self.A.sum(axis=1)).flatten()
        self.deg[self.deg < 1e-8] = 1.0
    
    def _build_laplacians(self):
        # L_norm: symmetric normalized Laplacian (当前使用)
        D_inv_sqrt = diags(1.0 / np.sqrt(self.deg), 0)
        self.L_norm = eye(self.n, format='csr') - D_inv_sqrt.dot(self.A).dot(D_inv_sqrt)
        
        # L_unnorm: 未归一化 Laplacian L = D - A
        self.L_unnorm = diags(self.deg, 0, format='csr') - self.A
        
        # L_rw: random walk Laplacian (非对称，不可直接用作精度矩阵)
        # 但可以通过 Q = D^{1/2} L_norm D^{1/2} = D - A = L_unnorm 来关联
        
        # L_signed: 保留方向性的尝试 — 用不对称权重
        # 跳过，先聚焦主要变体
    
    def diagnose_v1(self, obs_indices, obs_values, lam=2.0, prior_mean=0.5, prior_prec=1e-4):
        """当前公式：L_norm + 无先验均值"""
        Q_base = lam * self.L_norm + 1e-4 * eye(self.n, format='csr')
        d_data = np.zeros(self.n)
        for idx in obs_indices:
            d_data[idx] = 4.0
        D = diags(d_data, 0, shape=(self.n, self.n))
        b = np.zeros(self.n)
        for idx, val in zip(obs_indices, obs_values):
            b[idx] = val * 4.0
        Q = Q_base + D
        mu, info = cg(Q, b, rtol=1e-6, maxiter=500)
        if info != 0:
            mu = np.full(self.n, prior_mean)
            for idx, val in zip(obs_indices, obs_values):
                mu[idx] = val
        return mu
    
    def diagnose_v2(self, obs_indices, obs_values, lam=2.0, prior_mean=0.5, prior_prec=0.1):
        """L_norm + 显式先验均值 μ_0"""
        Q_base = lam * self.L_norm + prior_prec * eye(self.n, format='csr')
        d_data = np.zeros(self.n)
        for idx in obs_indices:
            d_data[idx] = 4.0
        D = diags(d_data, 0, shape=(self.n, self.n))
        # b = Q_base * μ_0 + D * y_obs
        b = Q_base.dot(np.full(self.n, prior_mean))
        for idx, val in zip(obs_indices, obs_values):
            b[idx] += val * 4.0
        Q = Q_base + D
        mu, info = cg(Q, b, rtol=1e-6, maxiter=500)
        if info != 0:
            mu = np.full(self.n, prior_mean)
            for idx, val in zip(obs_indices, obs_values):
                mu[idx] = val
        return mu
    
    def diagnose_v3(self, obs_indices, obs_values, lam=2.0, prior_mean=0.5, prior_prec=0.1):
        """L_unnorm + 显式先验均值"""
        # L_unnorm 的谱更大，需要调整 lam
        Q_base = lam * self.L_unnorm + prior_prec * eye(self.n, format='csr')
        d_data = np.zeros(self.n)
        for idx in obs_indices:
            d_data[idx] = 4.0
        D = diags(d_data, 0, shape=(self.n, self.n))
        b = Q_base.dot(np.full(self.n, prior_mean))
        for idx, val in zip(obs_indices, obs_values):
            b[idx] += val * 4.0
        Q = Q_base + D
        mu, info = cg(Q, b, rtol=1e-6, maxiter=500)
        if info != 0:
            mu = np.full(self.n, prior_mean)
            for idx, val in zip(obs_indices, obs_values):
                mu[idx] = val
        return mu
    
    def diagnose_v4(self, obs_indices, obs_values, lam=2.0, prior_mean=0.5, prior_prec=0.5):
        """L_norm + 聚合多观测（按KP平均）+ 观测精度正比于观测次数"""
        Q_base = lam * self.L_norm + prior_prec * eye(self.n, format='csr')
        d_data = np.zeros(self.n)
        obs_vals = np.zeros(self.n)
        obs_counts = np.zeros(self.n)
        for idx, val in zip(obs_indices, obs_values):
            obs_vals[idx] += val
            obs_counts[idx] += 1
        for idx in range(self.n):
            if obs_counts[idx] > 0:
                d_data[idx] = 4.0 * obs_counts[idx]  # 精度正比于观测次数
        D = diags(d_data, 0, shape=(self.n, self.n))
        b = Q_base.dot(np.full(self.n, prior_mean))
        for idx in range(self.n):
            if obs_counts[idx] > 0:
                avg_val = obs_vals[idx] / obs_counts[idx]
                b[idx] += avg_val * d_data[idx]
        Q = Q_base + D
        mu, info = cg(Q, b, rtol=1e-6, maxiter=500)
        if info != 0:
            mu = np.full(self.n, prior_mean)
            for idx in range(self.n):
                if obs_counts[idx] > 0:
                    mu[idx] = obs_vals[idx] / obs_counts[idx]
        return mu


def baseline_labelprop_v2(obs_indices, obs_values, A, n, alpha=0.5, n_iter=20, unobserved_prior=0.5):
    """改进版 LabelProp：未观测节点的先验设为 0.5"""
    Y = np.full((n, 1), unobserved_prior)
    for idx, val in zip(obs_indices, obs_values):
        Y[idx, 0] = val
    Y0 = Y.copy()
    deg = np.array(A.sum(axis=1)).flatten(); deg[deg < 1e-8] = 1.0
    D_inv = diags(1.0 / deg, 0)
    A_norm = D_inv.dot(A)
    for _ in range(n_iter):
        Y = alpha * A_norm.dot(Y) + (1 - alpha) * Y0
    return Y.flatten()


# ═══════════════════════════════════════════════════
# 4. 对比评测
# ═══════════════════════════════════════════════════

def compare_methods(tree_file, edge_file, sim_results):
    engine = FieldGMRF_variants(tree_file, edge_file)
    A = engine.A; n = engine.n
    
    methods = {
        'Naive': [],
        'Ability': [],
        'LabelProp(α=0.5)': [],
        'Field v1 (current)': [],
        'Field v2 (prior μ₀)': [],
        'Field v3 (L_unnorm)': [],
        'Field v4 (multi-obs)': [],
    }
    
    for r in sim_results:
        true_K = r['true_K']
        obs = r['observations']
        
        # 聚合观测：v1/v2/v3 用最后一个（与当前一致），v4 用所有
        obs_last = {}
        obs_all_indices = []; obs_all_values = []
        for day, idx, correct in obs:
            obs_last[idx] = 0.85 if correct else 0.15
            obs_all_indices.append(idx); obs_all_values.append(0.85 if correct else 0.15)
        obs_indices = list(obs_last.keys())
        obs_values = [obs_last[i] for i in obs_indices]
        
        # Naive
        mu = np.full(n, 0.5)
        for i, v in zip(obs_indices, obs_values): mu[i] = v
        methods['Naive'].append(np.mean(np.abs(mu - true_K)))
        
        # Ability
        if obs:
            avg = np.mean([1.0 if c else 0.0 for _, _, c in obs])
        else:
            avg = 0.5
        methods['Ability'].append(np.mean(np.abs(avg - true_K)))
        
        # LabelProp (改进版，未观测用0.5先验)
        mu = baseline_labelprop_v2(obs_indices, obs_values, A, n, alpha=0.5, n_iter=20, unobserved_prior=0.5)
        methods['LabelProp(α=0.5)'].append(np.mean(np.abs(mu - true_K)))
        
        # Field v1: 当前公式
        mu = engine.diagnose_v1(obs_indices, obs_values, lam=2.0)
        methods['Field v1 (current)'].append(np.mean(np.abs(mu - true_K)))
        
        # Field v2: L_norm + 显式先验均值
        mu = engine.diagnose_v2(obs_indices, obs_values, lam=2.0, prior_mean=0.5, prior_prec=0.1)
        methods['Field v2 (prior μ₀)'].append(np.mean(np.abs(mu - true_K)))
        
        # Field v3: L_unnorm + 显式先验均值
        mu = engine.diagnose_v3(obs_indices, obs_values, lam=0.02, prior_mean=0.5, prior_prec=0.1)
        methods['Field v3 (L_unnorm)'].append(np.mean(np.abs(mu - true_K)))
        
        # Field v4: 聚合多观测
        mu = engine.diagnose_v4(obs_all_indices, obs_all_values, lam=2.0, prior_mean=0.5, prior_prec=0.1)
        methods['Field v4 (multi-obs)'].append(np.mean(np.abs(mu - true_K)))
    
    print(f"\n{'='*60}")
    print(f"[方法对比]")
    print(f"{'='*60}")
    for name, maes in methods.items():
        print(f"  {name:25s}: {np.mean(maes):.4f} ± {np.std(maes):.4f}")
    
    return methods


# ═══════════════════════════════════════════════════
# 5. 超参数扫描
# ═══════════════════════════════════════════════════

def scan_params(tree_file, edge_file, sim_results):
    engine = FieldGMRF_variants(tree_file, edge_file)
    n = engine.n
    
    # 准备数据
    all_data = []
    for r in sim_results:
        true_K = r['true_K']
        obs = r['observations']
        obs_dict = {}
        for day, idx, correct in obs:
            obs_dict[idx] = 0.85 if correct else 0.15
        all_data.append((true_K, list(obs_dict.keys()), [obs_dict[i] for i in obs_dict]))
    
    print(f"\n{'='*60}")
    print(f"[超参数扫描]")
    print(f"{'='*60}")
    
    # v2: L_norm + prior
    print(f"\n  v2 (L_norm + prior_mean={0.5}):")
    for lam in [0.1, 0.5, 1.0, 2.0, 4.0, 8.0]:
        for prior_prec in [0.01, 0.1, 0.5]:
            maes = []
            for true_K, obs_idx, obs_val in all_data:
                mu = engine.diagnose_v2(obs_idx, obs_val, lam=lam, prior_prec=prior_prec)
                maes.append(np.mean(np.abs(mu - true_K)))
            print(f"    λ={lam:.1f} prior_prec={prior_prec:.2f}: MAE={np.mean(maes):.4f}")
    
    # v3: L_unnorm + prior
    print(f"\n  v3 (L_unnorm + prior_mean={0.5}):")
    for lam in [0.001, 0.005, 0.01, 0.02, 0.05, 0.1]:
        for prior_prec in [0.01, 0.1, 0.5]:
            maes = []
            for true_K, obs_idx, obs_val in all_data:
                mu = engine.diagnose_v3(obs_idx, obs_val, lam=lam, prior_prec=prior_prec)
                maes.append(np.mean(np.abs(mu - true_K)))
            print(f"    λ={lam:.3f} prior_prec={prior_prec:.2f}: MAE={np.mean(maes):.4f}")


# ═══════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════

if __name__ == '__main__':
    TREES = {'CFA': ('cfa_tree.json', 'cfa_llm_edges.json'),
             'Math': ('math_tree.json', 'math_llm_edges.json')}
    
    for name, (tf, ef) in TREES.items():
        print(f"\n{'#'*60}")
        print(f"# {name}")
        print(f"{'#'*60}")
        
        # 1. 图诊断
        degrees, n_kps, topics = diagnose_graph(tf, ef)
        
        # 2. 仿真
        sim = IndependentStudentSim(tf, n_students=200, n_days=100, seed=42)
        sim_results = sim.run()
        kp_means, all_K, corr_matrix = diagnose_simulation(sim_results, topics, n_kps)
        
        # 3. 方法对比
        compare_methods(tf, ef, sim_results)
        
        # 4. 超参数扫描（仅 CFA）
        if name == 'CFA':
            scan_params(tf, ef, sim_results)
