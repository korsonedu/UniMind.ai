#!/usr/bin/env python3
"""
Field 重新定义：Bernoulli-GMRF 诊断引擎

正确的生成模型：
  y_i ∈ {0,1}: 学生做 KP_i 的一道题，对/错
  P(y_i=1 | μ_i, d_i) = sigmoid(α(μ_i - d_i))
  μ ~ N(μ_0, (λL + τI)^{-1})  ← GMRF 先验

其中 d_i 是题目难度（已知或可估计），μ_i 是掌握度，α 是区分度。
这才是正确的观测模型——Bernoulli 似然 + GMRF 先验。
"""
import json, math, random, numpy as np
from collections import defaultdict
from scipy.sparse import csr_matrix, diags, eye
from scipy.sparse.linalg import cg
from scipy.optimize import minimize


# ═══════════════════════════════════════════════════
# Bernoulli-GMRF: Laplace 近似求解
# ═══════════════════════════════════════════════════

class BernoulliGMRF:
    """
    Model: y_i ~ Bernoulli(sigmoid(α(μ_i - d_i)))
    Prior: μ ~ N(μ_0, Q^{-1}) where Q = λL + τI
    
    MAP via Newton's method (iteratively reweighted least squares):
    μ^{(t+1)} = (Q + W)^{-1} (Q μ_0 + W z)
    where W = diag(α² p_i(1-p_i)), z_i = μ_i + (y_i - p_i)/(α p_i(1-p_i))
    """
    def __init__(self, tree_file, edge_file):
        with open(tree_file) as f: data = json.load(f)
        nodes = data['nodes']
        kps = [n for n in nodes if n.get('level') == 'kp']
        self.n = len(kps)
        self.n2id = {nd['name']: nd['id'] for nd in kps}
        self.id2i = {kid: i for i, kid in enumerate([n['id'] for n in kps])}
        self._build_adj(edge_file, nodes)
    
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
        deg = np.array(self.A.sum(axis=1)).flatten(); deg[deg < 1e-8] = 1.0
        D_inv_sqrt = diags(1.0 / np.sqrt(deg), 0)
        self.L = eye(self.n, format='csr') - D_inv_sqrt.dot(self.A).dot(D_inv_sqrt)
    
    def diagnose(self, obs_idx, obs_y, difficulties, lam=2.0, prior_mean=0.5, 
                 prior_prec=0.1, alpha=5.0, max_iter=20):
        """
        obs_idx: 被测试的 KP indices
        obs_y: 0/1 结果
        difficulties: 每个 KP 的题目难度 d_i
        alpha: IRT 区分度参数
        """
        n_obs = len(obs_idx)
        if n_obs == 0:
            return np.full(self.n, prior_mean)
        
        # 先验精度矩阵
        Q = lam * self.L + prior_prec * eye(self.n, format='csr')
        Q_dense = Q.toarray()
        
        # 初始化
        mu = np.full(self.n, prior_mean)
        
        for it in range(max_iter):
            # 计算 Hessian 和 working response
            W_diag = np.zeros(self.n)
            z = mu.copy()
            
            for k in range(n_obs):
                i = obs_idx[k]
                y = obs_y[k]
                d = difficulties[i]
                x = alpha * (mu[i] - d)
                if x > 50: p = 1.0
                elif x < -50: p = 0.0
                else: p = 1.0 / (1.0 + math.exp(-x))
                p = np.clip(p, 1e-6, 1 - 1e-6)
                w = alpha * alpha * p * (1 - p)
                W_diag[i] += w
                z[i] += (y - p) / (alpha * p * (1 - p))
            
            # 求解: (Q + W) * mu_new = Q*prior_mean + W*z
            # 但 z 里已经包含了旧的 mu，实际上我们解的是：
            # (Q + W) * delta = W*(z - mu) - Q*(mu - prior_mean)
            # 简化：直接解 (Q + W) * mu_new = Q*prior_mean + W*z
            
            H = Q_dense + np.diag(W_diag)
            rhs = Q_dense.dot(np.full(self.n, prior_mean)) + W_diag * z
            
            try:
                mu_new = np.linalg.solve(H, rhs)
            except np.linalg.LinAlgError:
                # fallback: CG
                H_sparse = Q + diags(W_diag, 0)
                b = Q.dot(np.full(self.n, prior_mean))
                for k in range(n_obs):
                    b[obs_idx[k]] += W_diag[obs_idx[k]] * z[obs_idx[k]]
                mu_new, info = cg(H_sparse, b, rtol=1e-6, maxiter=500)
                if info != 0:
                    mu_new = mu
            
            change = np.max(np.abs(mu_new - mu))
            mu = mu_new
            if change < 1e-4:
                break
        
        return mu


# ═══════════════════════════════════════════════════
# 对比基线
# ═══════════════════════════════════════════════════

def baseline_fsrs_like(review_count, n_kps, decay=0.985):
    """
    FSRS-like: 从复习次数估算掌握度
    每次复习: K += 0.3*(1-K), 每天的衰减: K *= decay
    稳态: K*decay + 0.3*(1-K)*freq ≈ K
    → K ≈ 0.3*freq / (0.3*freq + (1-decay))
    """
    freq = review_count / 100  # 每天被复习的概率
    K = 0.30 * freq / (0.30 * freq + 0.015)
    return np.clip(K, 0, 1)


# ═══════════════════════════════════════════════════
# 生产级仿真: 模拟真实教育场景
# ═══════════════════════════════════════════════════

class ProductionSimulator:
    """
    真实场景:
    - 学生随机学习（不强制 urgency）
    - 每个 KP 有难度 d_i
    - 学生能力 θ_s ~ N(0, 1)
    - 掌握过程: K_i(t+1) = K_i(t) + γ*(1-K_i(t)) 当 KP 被学习
    - 遗忘: K_i *= 0.98 daily
    - 考试: 随机选择一些 KP，P(correct) = sigmoid(α*(K_i - d_i))
    - 学习选择: urgency-based (标准 FSRS 行为)
    
    这创造真实的 KP 间异质性：
    - 学了/没学的 KP 差异巨大
    - 难度不同的 KP 掌握度不同
    - 前置依赖（如果有）创造深度差异
    """
    def __init__(self, tree_file, n_students=500, n_days=100, seed=42):
        with open(tree_file) as f: data = json.load(f)
        nodes = data['nodes']
        kps = [n for n in nodes if n.get('level') == 'kp']
        self.n = len(kps)
        self.names = [n['name'] for n in kps]
        
        np.random.seed(seed)
        # 题目难度（生成考试题目时使用）
        self.difficulty = np.random.beta(3, 7, self.n)
        self.difficulty = np.clip(self.difficulty, 0.05, 0.95)
        
        self.n_students = n_students
        self.n_days = n_days
    
    def run(self, learn_rate=0.25, test_interval=7, test_coverage=0.1):
        results = []
        for s in range(self.n_students):
            np.random.seed(20000 + s); random.seed(20000 + s)
            
            K = np.zeros(self.n)
            n_reviews = np.zeros(self.n)
            observations = []  # (day, kp_idx, correct/incorrect)
            
            for day in range(self.n_days):
                # Urgency-based 学习选择
                urgencies = [(1.0 - K[i]) / max(K[i], 0.01) for i in range(self.n)]
                budget = 10
                top = sorted(range(self.n), key=lambda i: -urgencies[i])[:budget]
                
                for i in top:
                    K[i] += learn_rate * (1 - K[i])
                    n_reviews[i] += 1
                
                # 遗忘
                K *= 0.985
                K += np.random.normal(0, 0.005, self.n)
                K = np.clip(K, 0, 1)
                
                # 定期考试
                if day > 0 and day % test_interval == 0:
                    n_test = max(5, int(self.n * test_coverage))
                    tested = random.sample(range(self.n), min(n_test, self.n))
                    for i in tested:
                        p_correct = 1.0 / (1.0 + math.exp(-5 * (K[i] - self.difficulty[i])))
                        correct = 1 if random.random() < p_correct else 0
                        observations.append((day, i, correct))
            
            results.append({
                'true_K': K.copy(),
                'n_reviews': n_reviews.copy(),
                'observations': observations,
            })
        
        return results


# ═══════════════════════════════════════════════════
# 评测
# ═══════════════════════════════════════════════════

def evaluate(sim_results, engine, difficulties):
    """
    对比方法:
    1. Bernoulli-GMRF: 我们的方法，正确使用 Bernoulli 似然
    2. Gaussian-GMRF: 当前方法，0.85/0.15 编码
    3. FSRS-like: 从复习次数估算
    4. Item Average: 每个 KP 的观测正确率（有观测就用，没观测猜 0.5）
    5. Global Average: 学生整体正确率
    """
    n = engine.n
    
    metrics = {
        'Bernoulli-GMRF': [],
        'Gaussian-GMRF': [],
        'FSRS-like': [],
        'Item-Avg': [],
        'Global-Avg': [],
    }
    
    for r in sim_results:
        true_K = r['true_K']
        n_reviews = r['n_reviews']
        obs = r['observations']
        
        # 整理观测
        obs_by_kp = defaultdict(list)
        for day, idx, correct in obs:
            obs_by_kp[idx].append(correct)
        
        # Bernoulli-GMRF
        all_idx = []; all_y = []
        for idx, outcomes in obs_by_kp.items():
            for y in outcomes:
                all_idx.append(idx); all_y.append(y)
        if all_idx:
            mu_bern = engine.diagnose(all_idx, all_y, difficulties, lam=2.0, 
                                      prior_mean=0.5, prior_prec=0.1, alpha=5.0)
        else:
            mu_bern = np.full(n, 0.5)
        metrics['Bernoulli-GMRF'].append(np.mean(np.abs(mu_bern - true_K)))
        
        # Gaussian-GMRF (当前方法)
        gau_idx = []; gau_val = []; gau_prec = []
        for idx, outcomes in obs_by_kp.items():
            avg = np.mean(outcomes)
            gau_idx.append(idx)
            gau_val.append(0.85*avg + 0.15*(1-avg))
            gau_prec.append(4.0 * len(outcomes))
        if gau_idx:
            Q = 2.0 * engine.L + 0.1 * eye(n, format='csr')
            D_data = np.zeros(n)
            for i, p in zip(gau_idx, gau_prec): D_data[i] = p
            D = diags(D_data, 0, shape=(n, n))
            b = Q.dot(np.full(n, 0.5))
            for i, v, p in zip(gau_idx, gau_val, gau_prec): b[i] += v * p
            mu_gau, info = cg(Q + D, b, rtol=1e-6, maxiter=500)
            if info != 0:
                mu_gau = np.full(n, 0.5)
                for i, v in zip(gau_idx, gau_val): mu_gau[i] = v
        else:
            mu_gau = np.full(n, 0.5)
        metrics['Gaussian-GMRF'].append(np.mean(np.abs(mu_gau - true_K)))
        
        # FSRS-like (从复习次数估算)
        mu_fsrs = baseline_fsrs_like(n_reviews, n)
        metrics['FSRS-like'].append(np.mean(np.abs(mu_fsrs - true_K)))
        
        # Item Average
        mu_item = np.full(n, 0.5)
        for idx, outcomes in obs_by_kp.items():
            mu_item[idx] = np.mean(outcomes)
        metrics['Item-Avg'].append(np.mean(np.abs(mu_item - true_K)))
        
        # Global Average
        all_outcomes = [y for _, _, y in obs]
        global_avg = np.mean(all_outcomes) if all_outcomes else 0.5
        metrics['Global-Avg'].append(np.mean(np.abs(global_avg - true_K)))
    
    return {k: (np.mean(v), np.std(v)) for k, v in metrics.items()}


if __name__ == '__main__':
    TREES = {
        'CFA': ('cfa_tree.json', 'cfa_llm_edges.json'),
        'Math': ('math_tree.json', 'math_llm_edges.json'),
    }
    
    print("=" * 90)
    print("Field: Bernoulli-GMRF 诊断引擎")
    print("=" * 90)
    print()
    print("正确生成模型: y_i ~ Bernoulli(sigmoid(α(μ_i - d_i))), μ ~ GMRF(λL)")
    print("对比: Gaussian-GMRF (0.85/0.15), FSRS-like, Item-Avg, Global-Avg")
    print()
    
    for name, (tf, ef) in TREES.items():
        print(f"\n{'─'*90}")
        print(f"  {name}")
        print(f"{'─'*90}")
        
        sim = ProductionSimulator(tf, n_students=500, n_days=100, seed=42)
        sim_results = sim.run()
        
        engine = BernoulliGMRF(tf, ef)
        
        # 统计
        all_K = np.array([r['true_K'] for r in sim_results])
        kp_means = all_K.mean(axis=0)
        avg_obs = np.mean([len(r['observations']) for r in sim_results])
        
        print(f"  n={engine.n}  students=500  avg obs/student={avg_obs:.0f}")
        print(f"  true_K: mean={all_K.mean():.4f}  KP std={kp_means.std():.4f}  "
              f"range=[{kp_means.min():.3f}, {kp_means.max():.3f}]")
        
        # Bernoulli-GMRF 在不同 λ 下的表现
        print(f"\n  Bernoulli-GMRF (λ scan):")
        for lam in [0.5, 1.0, 2.0, 4.0, 8.0]:
            maes = []
            for r in sim_results:
                true_K = r['true_K']
                obs = r['observations']
                obs_by_kp = defaultdict(list)
                for day, idx, correct in obs:
                    obs_by_kp[idx].append(correct)
                all_idx = []; all_y = []
                for idx, outcomes in obs_by_kp.items():
                    for y in outcomes:
                        all_idx.append(idx); all_y.append(y)
                if all_idx:
                    mu = engine.diagnose(all_idx, all_y, sim.difficulty, lam=lam,
                                        prior_mean=0.5, prior_prec=0.1, alpha=5.0)
                else:
                    mu = np.full(engine.n, 0.5)
                maes.append(np.mean(np.abs(mu - true_K)))
            print(f"    λ={lam:.1f}: {np.mean(maes):.4f}")
        
        # 全面对比（使用最佳 λ≈1 或 2）
        print(f"\n  方法对比 (λ=2):")
        results = evaluate(sim_results, engine, sim.difficulty)
        for method, (mae, std) in sorted(results.items(), key=lambda x: x[1][0]):
            bar = '█' * int(mae * 50)
            print(f"    {method:20s}: {mae:.4f} ± {std:.4f}  {bar}")
        
        # 密度敏感性
        print(f"\n  观测密度敏感性 (Bernoulli-GMRF, λ=2):")
        for frac in [0.1, 0.25, 0.5, 1.0]:
            maes = []
            for r in sim_results:
                true_K = r['true_K']
                obs = r['observations']
                obs_by_kp = defaultdict(list)
                for day, idx, correct in obs:
                    obs_by_kp[idx].append(correct)
                # 随机下采样
                all_items = list(obs_by_kp.items())
                n_keep = max(1, int(len(all_items) * frac))
                kept = dict(random.sample(all_items, n_keep))
                all_idx = []; all_y = []
                for idx, outcomes in kept.items():
                    for y in outcomes:
                        all_idx.append(idx); all_y.append(y)
                if all_idx:
                    mu = engine.diagnose(all_idx, all_y, sim.difficulty, lam=2.0,
                                        prior_mean=0.5, prior_prec=0.1, alpha=5.0)
                else:
                    mu = np.full(engine.n, 0.5)
                maes.append(np.mean(np.abs(mu - true_K)))
            print(f"    {frac:.0%} obs: MAE = {np.mean(maes):.4f}")
