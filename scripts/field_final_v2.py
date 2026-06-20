#!/usr/bin/env python3
"""
Field 最终对比实验
正确的问题: 只给稀疏考试结果，能否推断全部 KP 的掌握度？
公平基线: 同样只看到考试结果的方法
FSRS 是不同问题（有完整复习历史），不算基线
"""
import json, math, random, numpy as np
from collections import defaultdict
from scipy.sparse import csr_matrix, diags, eye
from scipy.sparse.linalg import cg


class FieldGMRF:
    def __init__(self, tree_file, edge_file):
        with open(tree_file) as f: data = json.load(f)
        nodes = data['nodes']
        kps = [n for n in nodes if n.get('level') == 'kp']
        self.n = len(kps); self.n2id = {nd['name']: nd['id'] for nd in kps}
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
            s = self.n2id.get(e.get('source_name', '')); t = self.n2id.get(e.get('target_name', ''))
            if not (s and t and s in self.id2i and t in self.id2i): continue
            si, ti = self.id2i[s], self.id2i[t]; pair = tuple(sorted([si, ti]))
            if pair in pair_seen: continue
            pair_seen.add(pair); w = float(e.get('weight', 0.5))
            adj[s].append((t, w)); adj[t].append((s, w))
        row, col, dat = [], [], []
        for sk, ns in adj.items():
            if sk in self.id2i:
                si = self.id2i[sk]
                for tk, w in ns:
                    if tk in self.id2i: row.append(si); col.append(self.id2i[tk]); dat.append(w)
        A = csr_matrix((dat, (row, col)), shape=(self.n, self.n))
        deg = np.array(A.sum(axis=1)).flatten(); deg[deg < 1e-8] = 1.0
        D_inv_sqrt = diags(1.0 / np.sqrt(deg), 0)
        self.L = eye(self.n, format='csr') - D_inv_sqrt.dot(A).dot(D_inv_sqrt)
    
    def diagnose(self, obs_idx, obs_y, difficulties, lam=2.0, prior_mean=0.5, prior_prec=0.5, alpha=5.0):
        """
        Bernoulli-GMRF with Laplace approximation.
        Uses CG instead of dense solve for stability.
        """
        n_obs = len(obs_idx)
        if n_obs == 0: return np.full(self.n, prior_mean)
        
        mu = np.full(self.n, prior_mean)
        
        for it in range(20):
            W_diag = np.zeros(self.n)
            z = mu.copy()  # working response, initially = mu
            
            for k in range(n_obs):
                i = obs_idx[k]; d = difficulties[i]
                x = alpha * (mu[i] - d)
                if x > 30: p = 0.9999
                elif x < -30: p = 0.0001
                else: p = 1.0/(1.0+math.exp(-x))
                p = max(1e-6, min(1-1e-6, p))
                w = alpha * alpha * p * (1 - p)
                W_diag[i] += w
                # working response: z_i = mu_i + (y_i - p_i) / (alpha * p_i * (1-p_i))
                # but we accumulate: z[i] starts at mu[i], add correction
                z[i] += (obs_y[k] - p) / (alpha * p * (1 - p))
            
            # Solve: (Q + diag(W_avg)) * mu_new = Q*mu_0 + diag(W_avg)*z
            Q = lam * self.L + prior_prec * eye(self.n, format='csr')
            H = Q + diags(W_diag, 0)
            
            b = Q.dot(np.full(self.n, prior_mean))
            for i in range(self.n):
                if W_diag[i] > 0:
                    b[i] += W_diag[i] * z[i]
            
            mu_new, info = cg(H, b, x0=mu, rtol=1e-4, maxiter=500)
            if info != 0: break
            
            change = np.max(np.abs(mu_new - mu))
            mu = mu_new
            if change < 1e-5: break
        
        return mu


def simulate_learning_curve(tree_file, n_students=300, learn_days=40, review_days=60, seed=42):
    with open(tree_file) as f: data = json.load(f)
    nodes = data['nodes']
    kps = [n for n in nodes if n.get('level') == 'kp']
    n = len(kps)
    np.random.seed(seed)
    difficulty = np.clip(np.random.beta(3, 7, n), 0.05, 0.95)
    
    results = []
    for s in range(n_students):
        np.random.seed(30000+s); random.seed(30000+s)
        K = np.zeros(n); observations = []
        
        for day in range(learn_days + review_days):
            if day < learn_days:
                n_new = max(1, int(n * 0.03))
                unlearned = [i for i in range(n) if K[i] < 0.05]
                newly = random.sample(unlearned, min(n_new, len(unlearned)))
                for i in newly: K[i] = 0.15 + np.random.uniform(0, 0.1)
                learned = [i for i in range(n) if K[i] >= 0.05]
                if learned:
                    u = [(1.0-K[i])/max(K[i],0.01) for i in learned]
                    for i in sorted(learned, key=lambda i: -u[learned.index(i)])[:min(10,len(learned))]:
                        K[i] += 0.30*(1-K[i])
            else:
                u = [(1.0-K[i])/max(K[i],0.01) for i in range(n)]
                for i in sorted(range(n), key=lambda i: -u[i])[:10]:
                    K[i] += 0.25*(1-K[i])
            
            K *= 0.985; K += np.random.normal(0, 0.005, n); K = np.clip(K, 0, 1)
            
            if day > 0 and day % 7 == 0:
                testable = [i for i in range(n) if K[i] >= 0.05] or list(range(n))
                n_test = max(3, int(len(testable) * 0.1))
                tested = random.sample(testable, min(n_test, len(testable)))
                for i in tested:
                    p = 1.0/(1.0+math.exp(-5*(K[i]-difficulty[i])))
                    observations.append((day, i, 1 if random.random() < p else 0))
        
        results.append({'true_K': K.copy(), 'observations': observations})
    
    return results, difficulty


def subsample_sparse(observations, sparsity):
    """随机保留 sparsity 比例的观测"""
    obs_by_kp = defaultdict(list)
    for day, idx, correct in observations:
        obs_by_kp[idx].append(correct)
    
    all_kps = list(obs_by_kp.keys())
    n_keep = max(1, int(len(all_kps) * sparsity))
    kept_kps = set(random.sample(all_kps, n_keep))
    
    kept_obs = defaultdict(list)
    for kp in kept_kps:
        kept_obs[kp] = obs_by_kp[kp]
    
    return kept_obs


if __name__ == '__main__':
    TREES = {'CFA': ('cfa_tree.json', 'cfa_llm_edges.json'),
             'Math': ('math_tree.json', 'math_llm_edges.json')}
    
    print("=" * 80)
    print("Field 最终实验")
    print("问题: 只给稀疏考试结果 → 推断全部 KP 的掌握度")
    print("公平基线: Naive / Global-Avg / Item-Avg (同样只看到考试结果)")
    print("FSRS 不是基线 (它有完整复习历史，是不同问题)")
    print("=" * 80)
    
    for name, (tf, ef) in TREES.items():
        engine = FieldGMRF(tf, ef)
        sim_results, difficulty = simulate_learning_curve(tf)
        
        all_K = np.array([r['true_K'] for r in sim_results])
        kp_means = all_K.mean(axis=0)
        print(f"\n{'='*80}")
        print(f"  {name}: n={engine.n}  KP std={kp_means.std():.4f}  "
              f"range=[{kp_means.min():.3f}, {kp_means.max():.3f}]")
        print(f"{'='*80}")
        
        for sparsity in [0.05, 0.1, 0.2, 0.3, 0.5]:
            results = {'Naive': [], 'Global-Avg': [], 'Item-Avg': [], 
                      'Field(λ=0.5)': [], 'Field(λ=1)': [], 'Field(λ=2)': [],
                      'Field(λ=4)': [], 'Field(λ=8)': []}
            
            for r in sim_results:
                true_K = r['true_K']
                kept = subsample_sparse(r['observations'], sparsity)
                
                all_idx = []; all_y = []
                for idx, outcomes in kept.items():
                    all_idx.extend([idx]*len(outcomes))
                    all_y.extend(outcomes)
                
                # Naive
                mu_n = np.full(engine.n, 0.5)
                for idx in kept:
                    mu_n[idx] = np.mean(kept[idx])
                results['Naive'].append(np.mean(np.abs(mu_n - true_K)))
                
                # Global-Avg
                if all_y:
                    ga = np.mean(all_y)
                else:
                    ga = 0.5
                results['Global-Avg'].append(np.mean(np.abs(ga - true_K)))
                
                # Item-Avg
                mu_i = np.full(engine.n, 0.5)
                for idx, outcomes in kept.items():
                    mu_i[idx] = np.mean(outcomes)
                results['Item-Avg'].append(np.mean(np.abs(mu_i - true_K)))
                
                # Field (多种λ)
                for lam in [0.5, 1, 2, 4, 8]:
                    mu_f = engine.diagnose(all_idx, all_y, difficulty, lam=lam,
                                          prior_mean=0.5, prior_prec=0.5, alpha=5.0)
                    results[f'Field(λ={lam})'].append(np.mean(np.abs(mu_f - true_K)))
            
            best_field = min(np.mean(v) for k, v in results.items() if 'Field' in k)
            best_other = min(np.mean(v) for k, v in results.items() if 'Field' not in k)
            gain = (best_other - best_field) / best_other * 100
            
            print(f"\n  sparsity={sparsity:.0%} ({int(engine.n*sparsity):3d} KPs tested):")
            print(f"  {'Method':20s} {'MAE':>8s} {'±':>8s}")
            print(f"  {'─'*20} {'─'*8} {'─'*8}")
            for method in ['Naive', 'Global-Avg', 'Item-Avg', 
                          'Field(λ=0.5)', 'Field(λ=1)', 'Field(λ=2)', 
                          'Field(λ=4)', 'Field(λ=8)']:
                mae, std = np.mean(results[method]), np.std(results[method])
                print(f"  {method:20s} {mae:8.4f} {std:8.4f}")
            print(f"  Best Field vs Best Other: {gain:+.1f}%")
