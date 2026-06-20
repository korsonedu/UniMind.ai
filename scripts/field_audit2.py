#!/usr/bin/env python3
"""
Field 审计 Part 2: 量化图信息量 + 理论极限
"""
import json, math, random, numpy as np
from collections import defaultdict
from scipy.sparse import csr_matrix, diags, eye
from scipy.sparse.linalg import cg

# ═══════════════════════════════════════════════════
# 复用 Part 1 的类和仿真
# ═══════════════════════════════════════════════════

class FieldGMRF_variants:
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
                for j in range(i+1, len(s)):
                    adj[s[i]].append((s[j], 0.3)); adj[s[j]].append((s[i], 0.3))
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
        D_inv_sqrt = diags(1.0 / np.sqrt(self.deg), 0)
        self.L_norm = eye(self.n, format='csr') - D_inv_sqrt.dot(self.A).dot(D_inv_sqrt)
        self.L_unnorm = diags(self.deg, 0, format='csr') - self.A
    
    def diagnose_v2(self, obs_indices, obs_values, lam=2.0, prior_mean=0.5, prior_prec=0.1):
        """L_norm + 显式先验均值"""
        Q_base = lam * self.L_norm + prior_prec * eye(self.n, format='csr')
        d_data = np.zeros(self.n)
        for idx in obs_indices: d_data[idx] = 4.0
        D = diags(d_data, 0, shape=(self.n, self.n))
        b = Q_base.dot(np.full(self.n, prior_mean))
        for idx, val in zip(obs_indices, obs_values):
            b[idx] += val * 4.0
        Q = Q_base + D
        mu, info = cg(Q, b, rtol=1e-6, maxiter=500)
        if info != 0:
            mu = np.full(self.n, prior_mean)
            for idx, val in zip(obs_indices, obs_values): mu[idx] = val
        return mu

class IndependentStudentSim:
    def __init__(self, tree_file, n_students=200, n_days=100, seed=42):
        with open(tree_file) as f: data = json.load(f)
        nodes = data['nodes']
        self.kps = [n for n in nodes if n.get('level') == 'kp']
        self.n = len(self.kps)
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


# ═══════════════════════════════════════════════════
# 分析 1: 图信息 vs 噪声
# ═══════════════════════════════════════════════════

def analyze_signal_noise(tree_file, sim_results):
    with open(tree_file) as f: data = json.load(f)
    nodes = data['nodes']
    kps = [n for n in nodes if n.get('level') == 'kp']
    n = len(kps)
    
    # 按 topic 分组
    topics = defaultdict(list)
    for i, nd in enumerate(kps):
        pid = nd.get('parent_id', 'root')
        topics[pid].append(i)
    
    all_K = np.array([r['true_K'] for r in sim_results])
    kp_means = all_K.mean(axis=0)
    global_mean = kp_means.mean()
    
    # 方差分解
    ss_total = np.sum((all_K - global_mean)**2)
    # Between-topic: 用 topic mean 替代每个 KP
    topic_means = {}
    for pid, indices in topics.items():
        topic_means[pid] = kp_means[indices].mean()
    between_topic = 0
    for pid, indices in topics.items():
        between_topic += len(indices) * all_K.shape[0] * (topic_means[pid] - global_mean)**2
    within_topic = ss_total - between_topic
    
    print(f"\n[信号分解]")
    print(f"  Total SS: {ss_total:.4f}")
    print(f"  Between-topic SS: {between_topic:.4f} ({between_topic/ss_total*100:.1f}%)")
    print(f"  Within-topic SS: {within_topic:.4f} ({within_topic/ss_total*100:.1f}%)")
    print(f"  KP mean std: {kp_means.std():.5f}")
    print(f"  Topic mean std: {np.array(list(topic_means.values())).std():.5f}")
    
    # ★ 关键问题：观测噪声多大？
    # 模拟一次观测：true_K → binary outcome 的噪声
    # 对每个 KP，给定 1 次观测，观测值 (0.15/0.85) 的期望 MAE
    single_obs_mae = 0
    for r in sim_results[:10]:  # 采样 10 个学生
        true_K = r['true_K']
        difficulty = r['difficulty']
        for i in range(n):
            p = 1.0/(1.0+math.exp(-5*(true_K[i]-difficulty[i])))
            obs_val = 0.85 if np.random.random() < p else 0.15
            single_obs_mae += abs(obs_val - true_K[i])
    single_obs_mae /= (10 * n)
    
    # 多次观测能降多少
    print(f"\n[观测噪声]")
    print(f"  单次观测 MAE (0.15/0.85 → true_K): {single_obs_mae:.4f}")
    print(f"  对比: KP间 std = {kp_means.std():.5f}")
    print(f"  结论: 观测噪声 >> KP间信号" if single_obs_mae > 3*kp_means.std() 
          else f"  结论: 观测噪声与信号可比")
    
    return topics, kp_means


# ═══════════════════════════════════════════════════
# 分析 2: Oracle 图 — 完美 topic 分组
# ═══════════════════════════════════════════════════

def test_oracle_graph(tree_file, sim_results):
    """如果图完美编码 topic 关系，Field 能做到多好？"""
    with open(tree_file) as f: data = json.load(f)
    nodes = data['nodes']
    kps = [n for n in nodes if n.get('level') == 'kp']
    n = len(kps)
    
    # 完美图：同 topic 的 KP 互相连接（权重1），跨 topic 无连接
    row, col, dat = [], [], []
    topics = defaultdict(list)
    for i, nd in enumerate(kps):
        pid = nd.get('parent_id', 'root')
        topics[pid].append(i)
    
    for pid, indices in topics.items():
        for i in range(len(indices)):
            for j in range(i+1, len(indices)):
                row.extend([indices[i], indices[j]])
                col.extend([indices[j], indices[i]])
                dat.extend([1.0, 1.0])
    
    A = csr_matrix((dat, (row, col)), shape=(n, n))
    deg = np.array(A.sum(axis=1)).flatten(); deg[deg < 1e-8] = 1.0
    D_inv_sqrt = diags(1.0/np.sqrt(deg), 0)
    L_norm = eye(n, format='csr') - D_inv_sqrt.dot(A).dot(D_inv_sqrt)
    
    # 测试 Field v2 在这个 oracle 图上的表现
    all_mae = []
    for r in sim_results:
        true_K = r['true_K']
        obs = r['observations']
        obs_dict = {}
        for day, idx, correct in obs:
            obs_dict[idx] = 0.85 if correct else 0.15
        
        obs_idx = list(obs_dict.keys())
        obs_val = [obs_dict[i] for i in obs_idx]
        
        # Field v2 with oracle graph
        prior_mean = 0.5; prior_prec = 0.1; lam = 2.0
        Q_base = lam * L_norm + prior_prec * eye(n, format='csr')
        d_data = np.zeros(n)
        for idx in obs_idx: d_data[idx] = 4.0
        D = diags(d_data, 0, shape=(n, n))
        b = Q_base.dot(np.full(n, prior_mean))
        for idx, val in zip(obs_idx, obs_val): b[idx] += val * 4.0
        Q = Q_base + D
        mu, info = cg(Q, b, rtol=1e-6, maxiter=500)
        if info != 0:
            mu = np.full(n, prior_mean)
            for idx, val in zip(obs_idx, obs_val): mu[idx] = val
        all_mae.append(np.mean(np.abs(mu - true_K)))
    
    # 对比：同 topic 内简单平均
    topic_mae = []
    for r in sim_results:
        true_K = r['true_K']
        obs = r['observations']
        # 每 topic 的观测平均
        topic_obs = defaultdict(list)
        for day, idx, correct in obs:
            for pid, indices in topics.items():
                if idx in indices:
                    topic_obs[pid].append(1.0 if correct else 0.0)
                    break
        mu = np.full(n, 0.5)
        for pid, indices in topics.items():
            if topic_obs[pid]:
                t_avg = np.mean(topic_obs[pid])
                for i in indices:
                    mu[i] = t_avg * 0.85 + (1-t_avg) * 0.15
        topic_mae.append(np.mean(np.abs(mu - true_K)))
    
    # 完美信息：直接用 topic 真值
    topic_true_mae = []
    for r in sim_results:
        true_K = r['true_K']
        mu = np.zeros(n)
        for pid, indices in topics.items():
            t_mean = true_K[indices].mean()
            for i in indices:
                mu[i] = t_mean
        topic_true_mae.append(np.mean(np.abs(mu - true_K)))
    
    print(f"\n[Oracle 图分析]")
    print(f"  Field v2 (oracle topic graph): {np.mean(all_mae):.4f}")
    print(f"  同topic简单平均(obs):            {np.mean(topic_mae):.4f}")
    print(f"  同topic真值平均(oracle):         {np.mean(topic_true_mae):.4f}")
    print(f"  → 图能提供的最大增益 vs 全局平均")
    
    return np.mean(all_mae), np.mean(topic_mae), np.mean(topic_true_mae)


# ═══════════════════════════════════════════════════
# 分析 3: 图质量扫描
# ═══════════════════════════════════════════════════

def scan_graph_quality(tree_file, edge_file, sim_results):
    """对比：当前图 vs 随机图 vs 无图 vs Oracle"""
    engine = FieldGMRF_variants(tree_file, edge_file)
    n = engine.n; A = engine.A; deg = engine.deg
    
    # 准备完整的观测数据
    all_data = []
    for r in sim_results:
        true_K = r['true_K']
        obs = r['observations']
        obs_dict = {}
        for day, idx, correct in obs:
            obs_dict[idx] = 0.85 if correct else 0.15
        all_data.append((true_K, list(obs_dict.keys()), [obs_dict[i] for i in obs_dict]))
    
    def test_graph(name, L_custom, lam_range):
        best_mae = 999
        for lam in lam_range:
            maes = []
            for true_K, obs_idx, obs_val in all_data:
                Q_base = lam * L_custom + 0.1 * eye(n, format='csr')
                d_data = np.zeros(n)
                for idx in obs_idx: d_data[idx] = 4.0
                D = diags(d_data, 0, shape=(n, n))
                b = Q_base.dot(np.full(n, 0.5))
                for idx, val in zip(obs_idx, obs_val): b[idx] += val * 4.0
                Q = Q_base + D
                mu, info = cg(Q, b, rtol=1e-6, maxiter=500)
                if info != 0:
                    mu = np.full(n, 0.5)
                    for idx, val in zip(obs_idx, obs_val): mu[idx] = val
                maes.append(np.mean(np.abs(mu - true_K)))
            if np.mean(maes) < best_mae:
                best_mae = np.mean(maes)
        return best_mae
    
    # 1. 当前图
    D_inv_sqrt = diags(1.0 / np.sqrt(deg), 0)
    L_current = eye(n, format='csr') - D_inv_sqrt.dot(A).dot(D_inv_sqrt)
    print(f"\n[图质量扫描]")
    
    # 2. 随机图（同样度数分布）
    np.random.seed(42)
    # 用 configuration model 生成随机图
    # 简化：每条边随机重连
    A_coo = A.tocoo()
    edges = list(zip(A_coo.row, A_coo.col, A_coo.data))
    np.random.shuffle(edges)
    row_r, col_r, dat_r = zip(*edges)
    A_rand = csr_matrix((dat_r, (row_r, col_r)), shape=(n, n))
    deg_rand = np.array(A_rand.sum(axis=1)).flatten(); deg_rand[deg_rand < 1e-8] = 1.0
    D_inv_sqrt_r = diags(1.0 / np.sqrt(deg_rand), 0)
    L_rand = eye(n, format='csr') - D_inv_sqrt_r.dot(A_rand).dot(D_inv_sqrt_r)
    
    mae_current = test_graph("current", L_current, [0.5, 1, 2, 4, 8])
    mae_random = test_graph("random", L_rand, [0.5, 1, 2, 4, 8])
    mae_nograph = test_graph("no-graph", eye(n, format='csr')*0, [0.01])
    
    print(f"  Current graph:  {mae_current:.4f}")
    print(f"  Random graph:   {mae_random:.4f}")
    print(f"  No graph (λ=0): {mae_nograph:.4f}")
    print(f"  Graph gain vs random: {(mae_random - mae_current)/mae_random*100:+.1f}%")
    print(f"  Graph gain vs no-graph: {(mae_nograph - mae_current)/mae_nograph*100:+.1f}%")
    
    return mae_current, mae_random, mae_nograph


# ═══════════════════════════════════════════════════
# 分析 4: 稀疏度敏感性
# ═══════════════════════════════════════════════════

def sparsity_sensitivity(tree_file, sim_results):
    """不同观测密度下 Field vs Ability"""
    with open(tree_file) as f: data = json.load(f)
    nodes = data['nodes']
    kps = [n for n in nodes if n.get('level') == 'kp']
    n = len(kps)
    
    # 从完整观测中采样不同比例
    all_data = []
    for r in sim_results:
        true_K = r['true_K']
        obs = r['observations']
        obs_dict = {}
        for day, idx, correct in obs:
            obs_dict[idx] = 0.85 if correct else 0.15
        all_data.append((true_K, obs_dict))
    
    # 用最简单的 Field 变体（L_norm, prior toward 0.5, lam=2）
    # 构建一次图
    engine = FieldGMRF_variants(tree_file, 'cfa_llm_edges.json' if 'cfa' in tree_file else 'math_llm_edges.json')
    
    print(f"\n[稀疏度敏感性]")
    for frac in [0.1, 0.25, 0.5, 0.75, 1.0]:
        field_maes = []; ability_maes = []; naive_maes = []
        for true_K, full_obs in all_data:
            # 随机采样观测
            all_kps = list(full_obs.keys())
            n_sample = max(1, int(len(all_kps) * frac))
            sampled = random.sample(all_kps, min(n_sample, len(all_kps)))
            obs_idx = sampled
            obs_val = [full_obs[i] for i in sampled]
            
            # Field
            mu = engine.diagnose_v2(obs_idx, obs_val, lam=2.0, prior_mean=0.5, prior_prec=0.1)
            field_maes.append(np.mean(np.abs(mu - true_K)))
            
            # Ability
            avg = np.mean(obs_val)
            ability_maes.append(np.mean(np.abs(avg - true_K)))
            
            # Naive
            mu_n = np.full(n, 0.5)
            for i, v in zip(obs_idx, obs_val): mu_n[i] = v
            naive_maes.append(np.mean(np.abs(mu_n - true_K)))
        
        print(f"  obs={int(len(all_kps)*frac):3d}: "
              f"Field={np.mean(field_maes):.4f}  "
              f"Ability={np.mean(ability_maes):.4f}  "
              f"Naive={np.mean(naive_maes):.4f}  "
              f"Field vs Ability: {(np.mean(ability_maes)-np.mean(field_maes))/np.mean(ability_maes)*100:+.1f}%")


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
        
        sim = IndependentStudentSim(tf, n_students=200, n_days=100, seed=42)
        sim_results = sim.run()
        
        # 分析 1: 信号 vs 噪声
        topics, kp_means = analyze_signal_noise(tf, sim_results)
        
        # 分析 2: Oracle 图
        test_oracle_graph(tf, sim_results)
        
        # 分析 3: 图质量扫描
        scan_graph_quality(tf, ef, sim_results)
        
        # 分析 4: 稀疏度敏感性
        sparsity_sensitivity(tf, sim_results)
