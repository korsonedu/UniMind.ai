#!/usr/bin/env python3
"""
Field 论文级实验
仿真: 学生先学新知识（40天），再混合复习（60天），产生真实的 KP 异质性
"""
import json, math, random, numpy as np
from collections import defaultdict
from scipy.sparse import csr_matrix, diags, eye
from scipy.sparse.linalg import cg


class BernoulliGMRF:
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
    
    def diagnose(self, obs_idx, obs_y, difficulties, lam=2.0, prior_mean=0.5, prior_prec=0.1, alpha=5.0, max_iter=15):
        n_obs = len(obs_idx)
        if n_obs == 0: return np.full(self.n, prior_mean)
        Q = lam * self.L + prior_prec * eye(self.n, format='csr')
        Q_dense = Q.toarray()
        mu = np.full(self.n, prior_mean)
        for it in range(max_iter):
            W_diag = np.zeros(self.n); z = mu.copy()
            for k in range(n_obs):
                i = obs_idx[k]; d = difficulties[i]
                x = alpha * (mu[i] - d)
                p = 1.0/(1.0+math.exp(-max(min(x,50),-50)))
                p = np.clip(p, 1e-6, 1-1e-6)
                w = alpha*alpha*p*(1-p)
                W_diag[i] += w
                z[i] += (obs_y[k] - p) / (alpha*p*(1-p))
            H = Q_dense + np.diag(W_diag)
            rhs = Q_dense.dot(np.full(self.n, prior_mean)) + W_diag * z
            try:
                mu_new = np.linalg.solve(H, rhs)
            except:
                H_sp = Q + diags(W_diag, 0)
                b = Q.dot(np.full(self.n, prior_mean))
                for k in range(n_obs): b[obs_idx[k]] += W_diag[obs_idx[k]] * z[obs_idx[k]]
                mu_new, info = cg(H_sp, b, rtol=1e-6, maxiter=500)
                if info != 0: mu_new = mu
            if np.max(np.abs(mu_new - mu)) < 1e-4: mu = mu_new; break
            mu = mu_new
        return mu


def simulate_learning_curve(tree_file, n_students=300, learn_days=40, review_days=60, seed=42):
    """
    阶段1 (learn_days): 学生逐步学习新 KP（每天解锁 3%），创建异质性
    阶段2 (review_days): urgency 复习
    
    这模拟真实场景：不是所有 KP 同时开始学，早期学的 KP 掌握度高
    """
    with open(tree_file) as f: data = json.load(f)
    nodes = data['nodes']
    kps = [n for n in nodes if n.get('level') == 'kp']
    n = len(kps)
    
    np.random.seed(seed)
    difficulty = np.clip(np.random.beta(3, 7, n), 0.05, 0.95)
    
    results = []
    for s in range(n_students):
        np.random.seed(30000+s); random.seed(30000+s)
        K = np.zeros(n)
        n_reviews = np.zeros(n)
        observations = []
        
        for day in range(learn_days + review_days):
            if day < learn_days:
                # 学习阶段：每天解锁 3% 的新 KP
                n_new = max(1, int(n * 0.03))
                unlearned = [i for i in range(n) if K[i] < 0.05]
                newly_learned = random.sample(unlearned, min(n_new, len(unlearned)))
                for i in newly_learned:
                    K[i] = 0.15 + np.random.uniform(0, 0.1)
                
                # 复习已学的
                learned = [i for i in range(n) if K[i] >= 0.05]
                if learned:
                    urgencies = [(1.0-K[i])/max(K[i], 0.01) for i in learned]
                    budget = min(10, len(learned))
                    top = sorted(learned, key=lambda i: -urgencies[learned.index(i)])[:budget]
                    for i in top:
                        K[i] += 0.30 * (1 - K[i])
                        n_reviews[i] += 1
            else:
                # 复习阶段：标准 urgency
                urgencies = [(1.0-K[i])/max(K[i], 0.01) for i in range(n)]
                top = sorted(range(n), key=lambda i: -urgencies[i])[:10]
                for i in top:
                    K[i] += 0.25 * (1 - K[i])
                    n_reviews[i] += 1
            
            K *= 0.985
            K += np.random.normal(0, 0.005, n)
            K = np.clip(K, 0, 1)
            
            # 考试：每 7 天测试 10% KP
            if day > 0 and day % 7 == 0:
                testable = [i for i in range(n) if K[i] >= 0.05] or list(range(n))
                n_test = max(5, int(len(testable) * 0.1))
                tested = random.sample(testable, min(n_test, len(testable)))
                for i in tested:
                    p = 1.0/(1.0+math.exp(-5*(K[i]-difficulty[i])))
                    correct = 1 if random.random() < p else 0
                    observations.append((day, i, correct))
        
        results.append({'true_K': K.copy(), 'n_reviews': n_reviews.copy(), 'observations': observations})
    
    return results, difficulty


def gaussian_gmrf_diagnose(L, n, obs_idx, obs_val, obs_prec, lam=2.0, prior_mean=0.5, prior_prec=0.1):
    Q = lam * L + prior_prec * eye(n, format='csr')
    D_data = np.zeros(n)
    for i, p in zip(obs_idx, obs_prec): D_data[i] = p
    D = diags(D_data, 0, shape=(n, n))
    b = Q.dot(np.full(n, prior_mean))
    for i, v, p in zip(obs_idx, obs_val, obs_prec): b[i] += v * p
    mu, info = cg(Q + D, b, rtol=1e-6, maxiter=500)
    if info != 0:
        mu = np.full(n, prior_mean)
        for i, v in zip(obs_idx, obs_val): mu[i] = v
    return mu


def fsrs_like_estimate(n_reviews, n_days=100):
    freq = n_reviews / n_days
    K = 0.30 * freq / (0.30 * freq + 0.015)
    return np.clip(K, 0, 1)


if __name__ == '__main__':
    TREES = {'CFA': ('cfa_tree.json', 'cfa_llm_edges.json'),
             'Math': ('math_tree.json', 'math_llm_edges.json')}
    
    print("=" * 90)
    print("Field: Bernoulli-GMRF — 论文级实验")
    print("场景: 学习曲线 — 前40天逐步解锁新KP，后60天混合复习")
    print("=" * 90)
    
    for name, (tf, ef) in TREES.items():
        engine = BernoulliGMRF(tf, ef)
        sim_results, difficulty = simulate_learning_curve(tf)
        
        all_K = np.array([r['true_K'] for r in sim_results])
        kp_means = all_K.mean(axis=0)
        avg_obs = np.mean([len(r['observations']) for r in sim_results])
        
        print(f"\n{'─'*90}")
        print(f"  {name}: n={engine.n}  students=300  obs/student={avg_obs:.0f}")
        print(f"  KP mean={all_K.mean():.4f}  std={kp_means.std():.4f}  "
              f"range=[{kp_means.min():.3f}, {kp_means.max():.3f}]")
        print(f"{'─'*90}")
        
        # === 方法对比 ===
        methods = {
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
            
            obs_by_kp = defaultdict(list)
            for day, idx, correct in obs:
                obs_by_kp[idx].append(correct)
            
            # Bernoulli-GMRF
            all_idx, all_y = [], []
            for idx, outcomes in obs_by_kp.items():
                for y in outcomes: all_idx.append(idx); all_y.append(y)
            mu_b = engine.diagnose(all_idx, all_y, difficulty, lam=2.0, prior_mean=0.5, prior_prec=0.1, alpha=5.0) if all_idx else np.full(engine.n, 0.5)
            methods['Bernoulli-GMRF'].append(np.mean(np.abs(mu_b - true_K)))
            
            # Gaussian-GMRF
            gi, gv, gp = [], [], []
            for idx, outcomes in obs_by_kp.items():
                avg = np.mean(outcomes)
                gi.append(idx); gv.append(0.85*avg+0.15*(1-avg)); gp.append(4.0*len(outcomes))
            mu_g = gaussian_gmrf_diagnose(engine.L, engine.n, gi, gv, gp) if gi else np.full(engine.n, 0.5)
            methods['Gaussian-GMRF'].append(np.mean(np.abs(mu_g - true_K)))
            
            # FSRS-like
            mu_f = fsrs_like_estimate(n_reviews)
            methods['FSRS-like'].append(np.mean(np.abs(mu_f - true_K)))
            
            # Item-Avg
            mu_i = np.full(engine.n, 0.5)
            for idx, outcomes in obs_by_kp.items():
                mu_i[idx] = np.mean(outcomes)
            methods['Item-Avg'].append(np.mean(np.abs(mu_i - true_K)))
            
            # Global-Avg
            all_y_all = [y for _,_,y in obs]
            ga = np.mean(all_y_all) if all_y_all else 0.5
            methods['Global-Avg'].append(np.mean(np.abs(ga - true_K)))
        
        print(f"\n  {'Method':25s} {'MAE':>8s} {'±std':>8s} {'vs FSRS':>10s} {'Gain':>8s}")
        print(f"  {'─'*25} {'─'*8} {'─'*8} {'─'*10} {'─'*8}")
        
        fsrs_mae = np.mean(methods['FSRS-like'])
        for method in ['Bernoulli-GMRF', 'Gaussian-GMRF', 'FSRS-like', 'Item-Avg', 'Global-Avg']:
            mae, std = np.mean(methods[method]), np.std(methods[method])
            vs_fsrs = (fsrs_mae - mae) / fsrs_mae * 100
            print(f"  {method:25s} {mae:8.4f} {std:8.4f} {vs_fsrs:+9.1f}%")
    
    print(f"\n{'='*90}")
    print("结论")
    print(f"{'='*90}")
