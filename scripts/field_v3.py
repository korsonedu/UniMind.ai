#!/usr/bin/env python3
"""
Field: Bernoulli-GMRF 诊断引擎 — 生产级实现

生成模型:
  y_k ∈ {0,1}: 学生在 KP_i 上做第 k 题, 对/错
  P(y_k=1 | μ_i) = sigmoid(α(μ_i - d_i))
  μ ~ N(μ_0, (λL + τI)⁻¹)  ← GMRF 图平滑先验

MAP 估计: 用 L-BFGS-B 最小化负对数后验
  -log p(μ|y) = -Σ log Bern(y_k|μ_i) + ½(μ-μ₀)ᵀQ(μ-μ₀)

对比基线（同样只给考试结果，不给复习历史）:
  Naive:      测过的抄，没测过猜 0.5
  Global-Avg: 学生全部考试平均正确率
  Item-Avg:   每 KP 用自己的正确率，没考过猜 0.5
  IRT:        1PL Rasch (无图)
  LabelProp:  图标签传播 (有图，但不用 GMRF)
  Field:      我们的方法
"""
import json, math, random, numpy as np
from collections import defaultdict
from scipy.sparse import csr_matrix, diags, eye
from scipy.optimize import minimize


class FieldBernoulliGMRF:
    """
    Bernoulli-GMRF: MAP via L-BFGS-B
    
    负对数后验:
      nlp(μ) = -Σ_k [y_k log(p_k) + (1-y_k) log(1-p_k)] 
                + ½λ μᵀLμ + ½τ||μ-μ₀||²
    
    梯度:
      ∂nlp/∂μ_i = -α Σ_{k∈obs(i)} (y_k - p_k) + λ(Lμ)_i + τ(μ_i - μ₀)
    """
    def __init__(self, tree_file, edge_file):
        with open(tree_file) as f: data = json.load(f)
        nodes = data['nodes']
        kps = [n for n in nodes if n.get('level') == 'kp']
        self.n = len(kps)
        self.n2id = {nd['name']: nd['id'] for nd in kps}
        self.id2i = {kid: i for i, kid in enumerate([n['id'] for n in kps])}
        
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
        
        A = csr_matrix((dat, (row, col)), shape=(self.n, self.n))
        deg = np.array(A.sum(axis=1)).flatten()
        deg[deg < 1e-8] = 1.0
        D_inv_sqrt = diags(1.0 / np.sqrt(deg), 0)
        self.L = eye(self.n, format='csr') - D_inv_sqrt.dot(A).dot(D_inv_sqrt)
        self.L_dense = self.L.toarray()  # for fast matvec in optimization
        self.A_sparse = A  # keep for LabelProp baseline
    
    def diagnose(self, obs_idx, obs_y, difficulties, lam=1.0, prior_mean=0.5, 
                 prior_prec=0.1, alpha=5.0):
        """
        obs_idx[k]: 第 k 次观测对应的 KP index
        obs_y[k]:   第 k 次观测的 0/1 结果
        difficulties[i]: KP_i 的题目难度
        """
        n_obs = len(obs_idx)
        if n_obs == 0:
            return np.full(self.n, prior_mean)
        
        # 预处理：每个 KP 的观测列表
        obs_list = defaultdict(list)
        for k in range(n_obs):
            obs_list[obs_idx[k]].append(obs_y[k])
        obs_kps = list(obs_list.keys())
        
        # L-BFGS-B
        mu0 = np.full(self.n, prior_mean)
        bounds = [(0.001, 0.999) for _ in range(self.n)]
        
        L = self.L_dense
        mu0_vec = np.full(self.n, prior_mean)
        
        def objective(mu):
            # Negative log posterior
            nlp = 0.0
            # Likelihood
            for k in range(n_obs):
                i = obs_idx[k]
                d = difficulties[i]
                x = alpha * (mu[i] - d)
                # stable sigmoid
                if x > 30: p = 1.0
                elif x < -30: p = 0.0
                else: p = 1.0 / (1.0 + math.exp(-x))
                p = np.clip(p, 1e-12, 1 - 1e-12)
                y = obs_y[k]
                nlp -= y * math.log(p) + (1 - y) * math.log(1 - p)
            # Prior: ½ λ μᵀLμ + ½ τ ||μ - μ₀||²
            diff = mu - mu0_vec
            nlp += 0.5 * lam * mu.dot(L.dot(mu))
            nlp += 0.5 * prior_prec * diff.dot(diff)
            return nlp
        
        def gradient(mu):
            grad = np.zeros(self.n)
            # Likelihood gradient
            for k in range(n_obs):
                i = obs_idx[k]
                d = difficulties[i]
                x = alpha * (mu[i] - d)
                if x > 30: p = 1.0
                elif x < -30: p = 0.0
                else: p = 1.0 / (1.0 + math.exp(-x))
                p = np.clip(p, 1e-12, 1 - 1e-12)
                grad[i] -= alpha * (obs_y[k] - p)
            # Prior gradient
            grad += lam * L.dot(mu)
            grad += prior_prec * (mu - mu0_vec)
            return grad
        
        result = minimize(objective, mu0, method='L-BFGS-B', jac=gradient,
                         bounds=bounds, options={'maxiter': 200, 'ftol': 1e-8})
        
        return result.x


def baseline_labelprop(obs_indices, obs_values, A, n, alpha=0.5, n_iter=30):
    """图标签传播"""
    Y = np.full((n, 1), 0.5)
    for idx, val in zip(obs_indices, obs_values):
        Y[idx, 0] = val
    Y0 = Y.copy()
    deg = np.array(A.sum(axis=1)).flatten()
    deg[deg < 1e-8] = 1.0
    A_norm = diags(1.0 / deg, 0).dot(A)
    for _ in range(n_iter):
        Y = alpha * A_norm.dot(Y) + (1 - alpha) * Y0
    return Y.flatten()


def baseline_irt(observations, difficulties, n):
    """1PL Rasch: 从观测估计每个学生的 θ，然后 P(correct|i) = sigmoid(θ - d_i)"""
    if not observations:
        return np.full(n, 0.5)
    
    # MLE for theta
    theta = 0.0
    for _ in range(10):
        grad = 0.0; hess = 0.0
        for _, idx, correct in observations:
            p = 1.0 / (1.0 + math.exp(-(theta - difficulties[idx])))
            p = np.clip(p, 1e-6, 1 - 1e-6)
            y = 1.0 if correct else 0.0
            grad += y - p
            hess += p * (1 - p)
        if hess > 1e-8:
            theta += grad / hess
        theta = np.clip(theta, -3, 3)
    
    mu = np.zeros(n)
    for i in range(n):
        mu[i] = 1.0 / (1.0 + math.exp(-(theta - difficulties[i])))
    return mu


# ═══════════════════════════════════════════════════
# 仿真
# ═══════════════════════════════════════════════════

def simulate(tree_file, n_students=300, learn_days=30, review_days=70, seed=42):
    """
    学习曲线仿真:
    - 前 learn_days: 逐步解锁新 KP + 复习已学
    - 后 review_days: urgency 维持
    - 考试: 每 7 天考一次, 但不覆盖全部 KP
    创造真实的 KP 间异质性: 早期学的 KP 掌握度高, 晚期学的低
    """
    with open(tree_file) as f: data = json.load(f)
    nodes = data['nodes']
    kps = [n for n in nodes if n.get('level') == 'kp']
    n = len(kps)
    
    np.random.seed(seed)
    # 难度: 每个 KP 有一组题的难度分布
    difficulty = np.clip(np.random.beta(3, 7, n), 0.05, 0.95)
    
    results = []
    for s in range(n_students):
        np.random.seed(40000 + s); random.seed(40000 + s)
        K = np.zeros(n)
        observations = []  # (day, kp_idx, 0/1)
        
        for day in range(learn_days + review_days):
            if day < learn_days:
                n_new = max(1, int(n * 0.04))
                unlearned = [i for i in range(n) if K[i] < 0.05]
                newly = random.sample(unlearned, min(n_new, len(unlearned)))
                for i in newly:
                    K[i] = 0.10 + np.random.uniform(0, 0.10)
                
                learned = [i for i in range(n) if K[i] >= 0.05]
                if learned:
                    u = [(1.0 - K[i]) / max(K[i], 0.01) for i in learned]
                    budget = min(8, len(learned))
                    top = sorted(learned, key=lambda i: -u[learned.index(i)])[:budget]
                    for i in top:
                        K[i] += 0.35 * (1 - K[i])
            else:
                u = [(1.0 - K[i]) / max(K[i], 0.01) for i in range(n)]
                for i in sorted(range(n), key=lambda i: -u[i])[:8]:
                    K[i] += 0.25 * (1 - K[i])
            
            K *= 0.986
            K += np.random.normal(0, 0.004, n)
            K = np.clip(K, 0, 1)
            
            # 考试: 每 5 天, 随机 8% KP
            if day > 0 and day % 5 == 0:
                testable = [i for i in range(n) if K[i] >= 0.03] or list(range(n))
                n_test = max(3, int(len(testable) * 0.08))
                tested = random.sample(testable, min(n_test, len(testable)))
                for i in tested:
                    p = 1.0 / (1.0 + math.exp(-5 * (K[i] - difficulty[i])))
                    observations.append((day, i, 1 if random.random() < p else 0))
        
        results.append({
            'true_K': K.copy(),
            'observations': observations,
        })
    
    return results, difficulty


# ═══════════════════════════════════════════════════
# 评测
# ═══════════════════════════════════════════════════

def subsample_sparse(observations, sparsity):
    """随机保留 sparsity 比例的 KP 的观测"""
    obs_by_kp = defaultdict(list)
    for day, idx, correct in observations:
        obs_by_kp[idx].append(correct)
    all_kps = list(obs_by_kp.keys())
    n_keep = max(1, int(len(all_kps) * sparsity))
    kept_kps = set(random.sample(all_kps, n_keep))
    kept = {}
    for kp in kept_kps:
        kept[kp] = obs_by_kp[kp]
    return kept


def evaluate_one_student(true_K, kept, engine, difficulty):
    """评测一个学生的各种方法"""
    n = engine.n
    
    all_idx = []; all_y = []
    for idx, outcomes in kept.items():
        all_idx.extend([idx] * len(outcomes))
        all_y.extend(outcomes)
    
    results = {}
    
    # Naive
    mu = np.full(n, 0.5)
    for idx, outcomes in kept.items():
        mu[idx] = np.mean(outcomes)
    results['Naive'] = np.mean(np.abs(mu - true_K))
    
    # Global-Avg
    ga = np.mean(all_y) if all_y else 0.5
    results['Global-Avg'] = np.mean(np.abs(ga - true_K))
    
    # IRT
    irt_obs = []
    for idx, outcomes in kept.items():
        for y in outcomes:
            irt_obs.append((0, idx, y))
    mu = baseline_irt(irt_obs, difficulty, n)
    results['IRT (1PL)'] = np.mean(np.abs(mu - true_K))
    
    # LabelProp
    obs_dict = {}
    for idx, outcomes in kept.items():
        obs_dict[idx] = np.mean(outcomes)
    obs_idx = list(obs_dict.keys())
    obs_val = [obs_dict[i] for i in obs_idx]
    mu = baseline_labelprop(obs_idx, obs_val, engine.A_sparse, n)
    results['LabelProp'] = np.mean(np.abs(mu - true_K))
    
    # Field
    mu = engine.diagnose(all_idx, all_y, difficulty, lam=1.0,
                        prior_mean=0.5, prior_prec=0.1, alpha=5.0)
    results['Field (ours)'] = np.mean(np.abs(mu - true_K))
    
    return results


if __name__ == '__main__':
    TREES = {
        'CFA': ('cfa_tree.json', 'cfa_llm_edges.json'),
        'Math': ('math_tree.json', 'math_llm_edges.json'),
    }
    
    print("=" * 80)
    print("Field: Bernoulli-GMRF 诊断引擎")
    print("场景: 学习曲线 (30天解锁 + 70天复习)，稀疏诊断测试")
    print("基线: Naive / Global-Avg / IRT(1PL) / LabelProp — 同样只看考试结果")
    print("=" * 80)
    
    for name, (tf, ef) in TREES.items():
        engine = FieldBernoulliGMRF(tf, ef)
        sim_results, difficulty = simulate(tf)
        
        all_K = np.array([r['true_K'] for r in sim_results])
        kp_means = all_K.mean(axis=0)
        avg_obs = np.mean([len(r['observations']) for r in sim_results])
        
        print(f"\n{'─'*80}")
        print(f"  {name}: {engine.n} KPs, {len(sim_results)} students, "
              f"{avg_obs:.0f} obs/student")
        print(f"  K: mean={all_K.mean():.3f}, KP std={kp_means.std():.4f}, "
              f"range=[{kp_means.min():.3f}, {kp_means.max():.3f}]")
        print(f"{'─'*80}")
        
        for sparsity in [0.05, 0.10, 0.20]:
            agg = defaultdict(list)
            for r in sim_results:
                kept = subsample_sparse(r['observations'], sparsity)
                res = evaluate_one_student(r['true_K'], kept, engine, difficulty)
                for k, v in res.items():
                    agg[k].append(v)
            
            n_tested = int(engine.n * sparsity)
            print(f"\n  [{sparsity:.0%} = {n_tested}/{engine.n} KPs tested]:")
            print(f"  {'Method':20s} {'MAE':>8s} {'±std':>8s}")
            print(f"  {'─'*20} {'─'*8} {'─'*8}")
            
            best_other = 999
            best_field = 999
            for method in ['Naive', 'Global-Avg', 'IRT (1PL)', 'LabelProp', 'Field (ours)']:
                vals = agg[method]
                mae, std = np.mean(vals), np.std(vals)
                marker = ' ★' if method == 'Field (ours)' else '  '
                print(f"  {method:20s} {mae:8.4f} {std:8.4f}{marker}")
                if method == 'Field (ours)':
                    best_field = mae
                else:
                    best_other = min(best_other, mae)
            
            gain = (best_other - best_field) / best_other * 100
            print(f"  Field vs best other: {gain:+.1f}%")
