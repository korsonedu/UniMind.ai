#!/usr/bin/env python3
"""
Field 审计 Part 5: 隔离观测噪声 vs 图结构
核心问题：Field 输是因为观测太吵（0.85/0.15），还是图结构无用？
"""
import json, math, random, numpy as np
from collections import defaultdict
from scipy.sparse import csr_matrix, diags, eye
from scipy.sparse.linalg import cg


class GMRF:
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
        deg = np.array(A.sum(axis=1)).flatten(); deg[deg < 1e-8] = 1.0
        D_inv_sqrt = diags(1.0 / np.sqrt(deg), 0)
        self.L = eye(self.n, format='csr') - D_inv_sqrt.dot(A).dot(D_inv_sqrt)
    
    def diagnose(self, obs_idx, obs_val, obs_prec=None, lam=2.0, prior_mean=0.5, prior_prec=0.1):
        if obs_prec is None: obs_prec = [4.0] * len(obs_idx)
        Q_base = lam * self.L + prior_prec * eye(self.n, format='csr')
        d_data = np.zeros(self.n)
        for idx, prec in zip(obs_idx, obs_prec): d_data[idx] = prec
        D = diags(d_data, 0, shape=(self.n, self.n))
        b = Q_base.dot(np.full(self.n, prior_mean))
        for idx, val, prec in zip(obs_idx, obs_val, obs_prec):
            b[idx] += val * prec
        Q = Q_base + D
        mu, info = cg(Q, b, rtol=1e-6, maxiter=500)
        if info != 0:
            mu = np.full(self.n, prior_mean)
            for idx, val in zip(obs_idx, obs_val): mu[idx] = val
        return mu


# ═══════════════════════════════════════════════════
# 统一仿真
# ═══════════════════════════════════════════════════

class UniformSim:
    def __init__(self, tree_file, n_students=200, n_days=100, seed=42):
        with open(tree_file) as f: data = json.load(f)
        nodes = data['nodes']
        self.kps = [n for n in nodes if n.get('level') == 'kp']
        self.n = len(self.kps)
        np.random.seed(seed)
        difficulty = np.random.beta(2, 5, self.n)
        self.difficulty = np.clip(difficulty, 0.01, 0.99)
    def run(self):
        results = []
        for s in range(200):
            np.random.seed(10000+s); random.seed(10000+s)
            K = np.zeros(self.n)
            for day in range(100):
                u = [(1.0-K[i])/max(K[i],0.01) for i in range(self.n)]
                top = sorted(range(self.n), key=lambda i: -u[i])[:10]
                for i in top:
                    K[i] += 0.30*(1-0.6*self.difficulty[i])*(1-K[i])
                K *= 0.985; K += np.random.normal(0,0.008,self.n)
                K = np.clip(K,0,1)
            # 生成考试观测（最后一天）— 全量观测，多个 noise 等级
            true_K = K.copy()
            results.append(true_K)
        return np.array(results)


# ═══════════════════════════════════════════════════
# 实验：控制观测质量
# ═══════════════════════════════════════════════════

def run_experiment(all_true_K, gmrf, n_obs_per_kp=1, noise_level='binary', obs_sparsity=0.3):
    """
    noise_level:
      'binary': correct/wrong → 0.85/0.15 (当前方式)
      'true': 直接用 true_K (无噪声，oracle)
      'true_noise': true_K + N(0, σ²) (可控噪声)
      'irt_calibrated': 用难度校准的估计
    """
    n_students, n_kps = all_true_K.shape
    
    field_maes = []; naive_maes = []; ability_maes = [];
    
    for s in range(n_students):
        true_K = all_true_K[s]
        
        # 随机选哪些 KP 被观测
        n_obs = max(1, int(n_kps * obs_sparsity))
        obs_kps = random.sample(range(n_kps), min(n_obs, n_kps))
        
        obs_idx = []; obs_val = []; obs_prec = []
        
        for i in obs_kps:
            for _ in range(n_obs_per_kp):
                if noise_level == 'binary':
                    # 模拟考试：P(correct) = sigmoid(5*(K - difficulty))
                    # 用固定 difficulty=0.3 简化
                    p = 1.0/(1.0+math.exp(-5*(true_K[i] - 0.3)))
                    correct = random.random() < p
                    obs_idx.append(i)
                    obs_val.append(0.85 if correct else 0.15)
                    obs_prec.append(4.0)
                
                elif noise_level == 'true':
                    obs_idx.append(i)
                    obs_val.append(true_K[i])
                    obs_prec.append(100.0)  # 高精度 ≈ oracle
                
                elif noise_level == 'true_noise':
                    obs_idx.append(i)
                    obs_val.append(true_K[i] + np.random.normal(0, 0.1))
                    obs_prec.append(1.0/0.01)  # σ=0.1 → prec=100
                
                elif noise_level == 'irt_calibrated':
                    # 使用 IRT 逆推：给定 P(correct), difficulty → 估计 K
                    p = 1.0/(1.0+math.exp(-5*(true_K[i] - 0.3)))
                    correct = random.random() < p
                    # 用 MLE 从结果反推: K_est = logit(p_correct) / 5 + difficulty
                    # 简化：p̂ = 0.85 if correct else 0.15
                    # logit(0.85) = ln(0.85/0.15) = 1.735, K_est = 1.735/5 + 0.3 = 0.647
                    # logit(0.15) = ln(0.15/0.85) = -1.735, K_est = -1.735/5 + 0.3 = -0.047
                    k_est = 1.735/5 + 0.3 if correct else -1.735/5 + 0.3
                    k_est = np.clip(k_est, 0.01, 0.99)
                    obs_idx.append(i)
                    obs_val.append(k_est)
                    obs_prec.append(2.0)  # 中等精度
        
        # Aggregate: 同一 KP 的多次观测取平均
        agg_val = defaultdict(list)
        for idx, val, prec in zip(obs_idx, obs_val, obs_prec):
            agg_val[idx].append((val, prec))
        
        final_idx = []; final_val = []; final_prec = []
        for idx, vals in agg_val.items():
            # 精度加权平均
            total_prec = sum(p for _, p in vals)
            weighted_val = sum(v*p for v, p in vals) / total_prec
            final_idx.append(idx); final_val.append(weighted_val); final_prec.append(total_prec)
        
        # Field
        mu_f = gmrf.diagnose(final_idx, final_val, final_prec, lam=2.0, prior_mean=0.5, prior_prec=0.1)
        field_maes.append(np.mean(np.abs(mu_f - true_K)))
        
        # Naive
        mu_n = np.full(n_kps, 0.5)
        for i, v in zip(final_idx, final_val): mu_n[i] = v
        naive_maes.append(np.mean(np.abs(mu_n - true_K)))
        
        # Ability
        if final_val:
            avg = np.mean(final_val)
        else:
            avg = 0.5
        ability_maes.append(np.mean(np.abs(avg - true_K)))
    
    return {
        'Field': (np.mean(field_maes), np.std(field_maes)),
        'Naive': (np.mean(naive_maes), np.std(naive_maes)),
        'Ability': (np.mean(ability_maes), np.std(ability_maes)),
    }


if __name__ == '__main__':
    print("=" * 80)
    print("观测噪声 vs 图结构 — 控制变量实验")
    print("=" * 80)
    
    for name, (tf, ef) in [('CFA', ('cfa_tree.json', 'cfa_llm_edges.json')),
                            ('Math', ('math_tree.json', 'math_llm_edges.json'))]:
        gmrf = GMRF(tf, ef)
        sim = UniformSim(tf)
        all_true_K = sim.run()
        
        true_mean = all_true_K.mean()
        kp_means = all_true_K.mean(axis=0)
        
        print(f"\n{'#'*80}")
        print(f"# {name}  n={gmrf.n}  true_K mean={true_mean:.4f}  KP std={kp_means.std():.5f}")
        print(f"{'#'*80}")
        
        for noise in ['binary', 'irt_calibrated', 'true_noise', 'true']:
            for obs_sparsity in [0.1, 0.3, 0.5]:
                for n_obs in [1, 3]:
                    res = run_experiment(all_true_K, gmrf, 
                                       n_obs_per_kp=n_obs,
                                       noise_level=noise,
                                       obs_sparsity=obs_sparsity)
                    best_other = min(res['Naive'][0], res['Ability'][0])
                    gain = (best_other - res['Field'][0]) / best_other * 100
                    
                    print(f"  noise={noise:16s}  sparsity={obs_sparsity:.1f}  "
                          f"obs/KP={n_obs}  |  "
                          f"Field={res['Field'][0]:.4f}  "
                          f"Naive={res['Naive'][0]:.4f}  "
                          f"Ability={res['Ability'][0]:.4f}  "
                          f"vs_best={gain:+.1f}%")
