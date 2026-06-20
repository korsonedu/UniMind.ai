#!/usr/bin/env python3
"""
Field: 截面诊断 — 真实业务场景

场景: 学生上了不同的课（不同 topic），参加期中考试（覆盖 5-20% KP）
Field 从稀疏考试推断全部 KP 掌握度

这才是 Field 真正的价值：考了 20 道题，告诉你 200 个知识点的掌握度
"""
import json, math, random, numpy as np
from collections import defaultdict
from scipy.sparse import csr_matrix, diags, eye
from scipy.optimize import minimize


class FieldBernoulliGMRF:
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
        self.L_dense = (eye(self.n, format='csr') - D_inv_sqrt.dot(A).dot(D_inv_sqrt)).toarray()
        self.A_sparse = A
    
    def diagnose(self, obs_idx, obs_y, difficulties, lam=1.0, prior_mean=0.5, prior_prec=1.0, alpha=5.0):
        n_obs = len(obs_idx)
        if n_obs == 0: return np.full(self.n, prior_mean)
        
        mu0 = np.full(self.n, prior_mean)
        mu0_vec = np.full(self.n, prior_mean)
        bounds = [(0.001, 0.999) for _ in range(self.n)]
        L = self.L_dense
        
        def objective(mu):
            nlp = 0.0
            for k in range(n_obs):
                i = obs_idx[k]; d = difficulties[i]
                x = alpha * (mu[i] - d)
                if x > 30: p = 1.0
                elif x < -30: p = 0.0
                else: p = 1.0 / (1.0 + math.exp(-x))
                p = np.clip(p, 1e-12, 1 - 1e-12)
                y = obs_y[k]
                nlp -= y * math.log(p) + (1 - y) * math.log(1 - p)
            diff = mu - mu0_vec
            nlp += 0.5 * lam * mu.dot(L.dot(mu)) + 0.5 * prior_prec * diff.dot(diff)
            return nlp
        
        def gradient(mu):
            g = np.zeros(self.n)
            for k in range(n_obs):
                i = obs_idx[k]; d = difficulties[i]
                x = alpha * (mu[i] - d)
                if x > 30: p = 1.0
                elif x < -30: p = 0.0
                else: p = 1.0 / (1.0 + math.exp(-x))
                p = np.clip(p, 1e-12, 1 - 1e-12)
                g[i] -= alpha * (obs_y[k] - p)
            g += lam * L.dot(mu) + prior_prec * (mu - mu0_vec)
            return g
        
        result = minimize(objective, mu0, method='L-BFGS-B', jac=gradient, bounds=bounds,
                         options={'maxiter': 100, 'ftol': 1e-6})
        return result.x


def simulate_cross_sectional(tree_file, n_students=300, seed=42):
    """
    截面场景: 学生学不同 topic 子集，模拟真实的课程差异。
    
    - 将 KP 按 topic (parent_id) 分组
    - 每个学生随机学过 30-60% 的 topic
    - 学过的 topic 内 KP 掌握度 0.5-0.95（正态）
    - 没学过的 topic 内 KP 掌握度 0.0-0.15（几乎为零）
    - 考试覆盖: 每学生随机抽 5-15% KP 测试
    
    这创造了真实的图信号：同一 topic 的 KP 要么一起高（学过）要么一起低（没学过）
    """
    with open(tree_file) as f: data = json.load(f)
    nodes = data['nodes']
    kps = [n for n in nodes if n.get('level') == 'kp']
    n = len(kps)
    
    np.random.seed(seed)
    # 按 topic 分组
    topics = defaultdict(list)
    for i, nd in enumerate(kps):
        pid = nd.get('parent_id', 'root')
        topics[pid].append(i)
    topic_ids = list(topics.keys())
    n_topics = len(topic_ids)
    
    # 每 topic 的题目难度
    topic_difficulty = {}
    for pid in topic_ids:
        topic_difficulty[pid] = np.random.beta(3, 7)
    
    difficulty = np.zeros(n)
    for pid, indices in topics.items():
        base = topic_difficulty[pid]
        for i in indices:
            difficulty[i] = np.clip(base + np.random.normal(0, 0.03), 0.05, 0.95)
    
    results = []
    for s in range(n_students):
        np.random.seed(60000 + s); random.seed(60000 + s)
        
        # 随机学过 30-60% topic
        frac_learned = np.random.uniform(0.3, 0.6)
        n_learned = max(1, int(n_topics * frac_learned))
        learned_topics = set(random.sample(topic_ids, n_learned))
        
        # 生成 true_K
        K = np.zeros(n)
        for pid, indices in topics.items():
            if pid in learned_topics:
                # 学过: 掌握度高，topic 内有微小差异
                topic_mean = np.random.uniform(0.55, 0.90)
                for i in indices:
                    K[i] = np.clip(topic_mean + np.random.normal(0, 0.08), 0.3, 0.98)
            else:
                # 没学过: 掌握度接近零
                for i in indices:
                    K[i] = np.random.uniform(0.0, 0.12)
        
        # 考试: 随机抽 5-15% KP，每 KP 考 1 道题
        test_frac = np.random.uniform(0.05, 0.15)
        n_test = max(3, int(n * test_frac))
        tested = random.sample(range(n), min(n_test, n))
        
        observations = []
        for i in tested:
            p = 1.0 / (1.0 + math.exp(-5 * (K[i] - difficulty[i])))
            observations.append((i, 1 if random.random() < p else 0))
        
        results.append({
            'true_K': K.copy(),
            'observations': observations,
            'learned_topics': learned_topics,
        })
    
    return results, difficulty, topics


def baseline_labelprop(obs_dict, A, n, alpha=0.5, n_iter=30):
    Y = np.full((n, 1), 0.5)
    for idx, val in obs_dict.items(): Y[idx, 0] = val
    Y0 = Y.copy()
    deg = np.array(A.sum(axis=1)).flatten(); deg[deg < 1e-8] = 1.0
    A_norm = diags(1.0 / deg, 0).dot(A)
    for _ in range(n_iter):
        Y = alpha * A_norm.dot(Y) + (1 - alpha) * Y0
    return Y.flatten()


def baseline_irt(observations, difficulty, n):
    if not observations: return np.full(n, 0.5)
    theta = 0.0
    for _ in range(10):
        grad = 0.0; hess = 0.0
        for idx, correct in observations:
            p = 1.0 / (1.0 + math.exp(-(theta - difficulty[idx])))
            p = np.clip(p, 1e-6, 1 - 1e-6)
            grad += correct - p
            hess += p * (1 - p)
        if hess > 1e-8: theta += grad / hess
        theta = np.clip(theta, -3, 3)
    mu = np.zeros(n)
    for i in range(n):
        mu[i] = 1.0 / (1.0 + math.exp(-(theta - difficulty[i])))
    return mu


if __name__ == '__main__':
    TREES = {
        'CFA': ('cfa_tree.json', 'cfa_llm_edges.json'),
        'Math': ('math_tree.json', 'math_llm_edges.json'),
    }
    
    print("=" * 80)
    print("Field: 截面诊断 — 真实业务场景")
    print("学生学不同 topic，期中考试覆盖 5-15% KP")
    print("基线: Naive / Global-Avg / IRT(1PL) / LabelProp")
    print("=" * 80)
    
    for name, (tf, ef) in TREES.items():
        engine = FieldBernoulliGMRF(tf, ef)
        sim_results, difficulty, topics = simulate_cross_sectional(tf)
        
        all_K = np.array([r['true_K'] for r in sim_results])
        kp_means = all_K.mean(axis=0)
        avg_obs = np.mean([len(r['observations']) for r in sim_results])
        avg_n_topics = np.mean([len(r['learned_topics']) for r in sim_results])
        
        print(f"\n{'─'*80}")
        print(f"  {name}: {engine.n} KPs, {len(sim_results)} students, "
              f"{avg_obs:.0f} obs/student")
        print(f"  Topics: {len(topics)}, avg learned/student: {avg_n_topics:.0f}")
        print(f"  K: mean={all_K.mean():.3f}, KP std={kp_means.std():.4f}, "
              f"range=[{kp_means.min():.3f}, {kp_means.max():.3f}]")
        print(f"{'─'*80}")
        
        # 只用一种观测密度（自然就是 5-15%）
        n = engine.n
        agg = defaultdict(list)
        
        for r in sim_results:
            true_K = r['true_K']
            observations = r['observations']
            
            obs_dict = {}
            for idx, correct in observations:
                obs_dict[idx] = 1.0 if correct else 0.0
            
            all_idx = list(obs_dict.keys())
            all_y = [obs_dict[i] for i in all_idx]
            
            # Naive: 测过的抄，没测过猜 0.5
            mu_n = np.full(n, 0.5)
            for idx, val in obs_dict.items():
                mu_n[idx] = val
            agg['Naive'].append(np.mean(np.abs(mu_n - true_K)))
            
            # Global-Avg
            ga = np.mean(all_y) if all_y else 0.5
            agg['Global-Avg'].append(np.mean(np.abs(ga - true_K)))
            
            # IRT
            irt_obs = [(idx, int(y)) for idx, y in obs_dict.items()]
            mu_irt = baseline_irt(irt_obs, difficulty, n)
            agg['IRT (1PL)'].append(np.mean(np.abs(mu_irt - true_K)))
            
            # LabelProp
            lp_obs = {}
            for idx, y in obs_dict.items():
                lp_obs[idx] = 0.85 if y > 0.5 else 0.15
            mu_lp = baseline_labelprop(lp_obs, engine.A_sparse, n)
            agg['LabelProp'].append(np.mean(np.abs(mu_lp - true_K)))
            
            # Field (多种 λ)
            for lam in [0.5, 1.0, 2.0]:
                mu_f = engine.diagnose(all_idx, all_y, difficulty, lam=lam,
                                      prior_mean=0.5, prior_prec=1.0, alpha=5.0)
                agg[f'Field(λ={lam})'].append(np.mean(np.abs(mu_f - true_K)))
        
        print(f"\n  {'Method':20s} {'MAE':>8s} {'±std':>8s}")
        print(f"  {'─'*20} {'─'*8} {'─'*8}")
        
        best_other = 999; best_field = 999
        for method in ['Naive', 'Global-Avg', 'IRT (1PL)', 'LabelProp',
                      'Field(λ=0.5)', 'Field(λ=1)', 'Field(λ=2)']:
            vals = agg[method]
            mae, std = np.mean(vals), np.std(vals)
            marker = ' ★' if 'Field' in method else '  '
            print(f"  {method:20s} {mae:8.4f} {std:8.4f}{marker}")
            if 'Field' in method:
                best_field = min(best_field, mae)
            else:
                best_other = min(best_other, mae)
        
        gain = (best_other - best_field) / best_other * 100
        print(f"\n  Field gain vs best other: {gain:+.1f}%")
        
        # 额外分析：按"学过 vs 没学过"分组看 Field 的优势
        print(f"\n  分组分析 (Field λ=1):")
        learned_mae = []; unlearned_mae = []
        for r in sim_results:
            true_K = r['true_K']
            obs_dict = {}
            for idx, correct in r['observations']:
                obs_dict[idx] = 1.0 if correct else 0.0
            all_idx = list(obs_dict.keys())
            all_y = [obs_dict[i] for i in all_idx]
            mu_f = engine.diagnose(all_idx, all_y, difficulty, lam=1.0,
                                  prior_mean=0.5, prior_prec=1.0, alpha=5.0)
            
            for i in range(n):
                if true_K[i] > 0.3:
                    learned_mae.append(abs(mu_f[i] - true_K[i]))
                else:
                    unlearned_mae.append(abs(mu_f[i] - true_K[i]))
        print(f"    学过 KP (K>0.3): Field MAE = {np.mean(learned_mae):.4f}")
        print(f"    没学 KP (K<0.3): Field MAE = {np.mean(unlearned_mae):.4f}")
