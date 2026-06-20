#!/usr/bin/env python3
"""
Field: 分层抽样诊断 — 每个 topic 至少测 1 个 KP

这才是 Field 的真实价值场景：
- 老师出诊断试卷，每个章节至少出 1 道题
- 试卷覆盖所有 topic，但每个 topic 只测少数 KP
- Field 利用图从"每 topic 1 题"推断"每 topic 全部 KP"
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
    
    def diagnose(self, obs_idx, obs_y, difficulties, lam=1.0, prior_mean=0.5, prior_prec=0.5, alpha=5.0):
        n_obs = len(obs_idx)
        if n_obs == 0: return np.full(self.n, prior_mean)
        mu0 = np.full(self.n, prior_mean); mu0_vec = np.full(self.n, prior_mean)
        bounds = [(0.001, 0.999) for _ in range(self.n)]
        L = self.L_dense
        
        def obj_grad(mu):
            nlp = 0.0; g = np.zeros(self.n)
            for k in range(n_obs):
                i = obs_idx[k]; d = difficulties[i]
                x = alpha * (mu[i] - d)
                if x > 30: p = 1.0
                elif x < -30: p = 0.0
                else: p = 1.0/(1.0+math.exp(-x))
                p = max(1e-12, min(1-1e-12, p))
                y = obs_y[k]
                nlp -= y*math.log(p) + (1-y)*math.log(1-p)
                g[i] -= alpha*(y - p)
            diff = mu - mu0_vec
            nlp += 0.5*lam*mu.dot(L.dot(mu)) + 0.5*prior_prec*diff.dot(diff)
            g += lam*L.dot(mu) + prior_prec*diff
            return nlp, g
        
        def objective(mu): return obj_grad(mu)[0]
        def gradient(mu): return obj_grad(mu)[1]
        
        try:
            result = minimize(objective, mu0, method='L-BFGS-B', jac=gradient, bounds=bounds,
                            options={'maxiter': 50, 'ftol': 1e-5})
            if not result.success or np.any(np.isnan(result.x)) or np.any(np.isinf(result.x)):
                return mu0
            # Sanity: values should be in [0,1]
            if np.max(result.x) > 2 or np.min(result.x) < -1:
                return mu0
            return result.x
        except:
            return mu0


def simulate_stratified(tree_file, n_students=300, n_per_topic=1, seed=42):
    """
    分层抽样: 每 topic 随机抽 n_per_topic 个 KP 测试
    学生学 30-60% topic（截面异质）
    """
    with open(tree_file) as f: data = json.load(f)
    nodes = data['nodes']; kps = [n for n in nodes if n.get('level') == 'kp']
    n = len(kps)
    np.random.seed(seed)
    
    topics = defaultdict(list)
    for i, nd in enumerate(kps):
        pid = nd.get('parent_id', 'root')
        topics[pid].append(i)
    topic_ids = list(topics.keys()); n_topics = len(topic_ids)
    
    topic_difficulty = {pid: np.random.beta(3, 7) for pid in topic_ids}
    difficulty = np.zeros(n)
    for pid, indices in topics.items():
        base = topic_difficulty[pid]
        for i in indices: difficulty[i] = np.clip(base + np.random.normal(0, 0.03), 0.05, 0.95)
    
    results = []
    for s in range(n_students):
        np.random.seed(70000+s); random.seed(70000+s)
        frac = np.random.uniform(0.3, 0.6)
        n_learned = max(1, int(n_topics * frac))
        learned_topics = set(random.sample(topic_ids, n_learned))
        
        K = np.zeros(n)
        for pid, indices in topics.items():
            if pid in learned_topics:
                tm = np.random.uniform(0.55, 0.90)
                for i in indices: K[i] = np.clip(tm + np.random.normal(0, 0.08), 0.3, 0.98)
            else:
                for i in indices: K[i] = np.random.uniform(0.0, 0.12)
        
        # 分层抽样: 每 topic 抽 n_per_topic 个 KP
        observations = []
        for pid, indices in topics.items():
            n_sample = min(n_per_topic, len(indices))
            sampled = random.sample(indices, n_sample)
            for i in sampled:
                p = 1.0/(1.0+math.exp(-5*(K[i]-difficulty[i])))
                observations.append((i, 1 if random.random() < p else 0))
        
        results.append({'true_K': K.copy(), 'observations': observations})
    
    return results, difficulty


def baseline_labelprop(obs_dict, A, n, alpha=0.5, n_iter=30):
    Y = np.full((n, 1), 0.5)
    for idx, val in obs_dict.items(): Y[idx, 0] = val
    Y0 = Y.copy()
    deg = np.array(A.sum(axis=1)).flatten(); deg[deg < 1e-8] = 1.0
    for _ in range(n_iter):
        Y = alpha * diags(1.0/deg, 0).dot(A).dot(Y) + (1-alpha)*Y0
    return Y.flatten()


def baseline_irt(obs_list, difficulty, n):
    if not obs_list: return np.full(n, 0.5)
    theta = 0.0
    for _ in range(10):
        g = 0.0; h = 0.0
        for idx, correct in obs_list:
            p = 1.0/(1.0+math.exp(-(theta-difficulty[idx])))
            p = np.clip(p, 1e-6, 1-1e-6); g += correct-p; h += p*(1-p)
        if h > 1e-8: theta += g/h
        theta = np.clip(theta, -3, 3)
    return np.array([1.0/(1.0+math.exp(-(theta-difficulty[i]))) for i in range(n)])


if __name__ == '__main__':
    TREES = {'CFA': ('cfa_tree.json', 'cfa_llm_edges.json'),
             'Math': ('math_tree.json', 'math_llm_edges.json')}
    
    print("=" * 80)
    print("Field: 分层抽样诊断 — 每 topic 至少测 1 个 KP")
    print("场景: 学生学不同 topic，诊断试卷覆盖所有章节但每章只测少数 KP")
    print("=" * 80)
    
    for npt in [1, 2]:
        print(f"\n{'#'*80}")
        print(f"# 每 topic {npt} 题")
        print(f"{'#'*80}")
        
        for name, (tf, ef) in TREES.items():
            engine = FieldBernoulliGMRF(tf, ef)
            sim_results, difficulty = simulate_stratified(tf, n_per_topic=npt)
            
            n = engine.n
            all_K = np.array([r['true_K'] for r in sim_results])
            avg_obs = np.mean([len(r['observations']) for r in sim_results])
            coverage = avg_obs / n * 100
            
            print(f"\n  {name}: {n} KPs, {avg_obs:.0f} obs ({coverage:.1f}%), "
                  f"KP std={all_K.mean(axis=0).std():.4f}")
            
            agg = defaultdict(list)
            for r in sim_results:
                true_K = r['true_K']
                obs_dict = {idx: 1.0 if c else 0.0 for idx, c in r['observations']}
                all_idx = list(obs_dict.keys()); all_y = [obs_dict[i] for i in all_idx]
                
                # Naive
                mu_n = np.full(n, 0.5)
                for idx, val in obs_dict.items(): mu_n[idx] = val
                agg['Naive'].append(np.mean(np.abs(mu_n - true_K)))
                
                # Global-Avg
                ga = np.mean(all_y) if all_y else 0.5
                agg['Global-Avg'].append(np.mean(np.abs(ga - true_K)))
                
                # IRT
                mu_i = baseline_irt([(i, int(y)) for i, y in obs_dict.items()], difficulty, n)
                agg['IRT (1PL)'].append(np.mean(np.abs(mu_i - true_K)))
                
                # LabelProp
                lp_obs = {i: 0.85 if y > 0.5 else 0.15 for i, y in obs_dict.items()}
                mu_lp = baseline_labelprop(lp_obs, engine.A_sparse, n)
                agg['LabelProp'].append(np.mean(np.abs(mu_lp - true_K)))
                
                # Field (多种 λ，含消融)
                for lam in [0.0, 0.01, 0.1, 0.5, 1.0]:
                    mu_f = engine.diagnose(all_idx, all_y, difficulty, lam=lam,
                                          prior_mean=0.5, prior_prec=0.5)
                    agg[f'Field(λ={lam})'].append(np.mean(np.abs(mu_f - true_K)))
            
            methods = ['Naive', 'Global-Avg', 'IRT (1PL)', 'LabelProp',
                      'Field(λ=0)', 'Field(λ=0.01)', 'Field(λ=0.1)', 'Field(λ=0.5)', 'Field(λ=1)']
            
            print(f"  {'Method':20s} {'MAE':>8s} {'±std':>8s} {'vs best':>10s}")
            
            best_other = 999; best_field = 999
            results = {}
            for m in methods:
                v = [x for x in agg[m] if not np.isnan(x)]
                if not v: 
                    results[m] = (float('nan'), float('nan'))
                    continue
                mae, std = np.mean(v), np.std(v)
                results[m] = (mae, std)
                if 'Field' in m: best_field = min(best_field, mae)
                else: best_other = min(best_other, mae)
            
            for m in methods:
                mae, std = results[m]
                vs = (best_other - mae) / best_other * 100 if not np.isnan(mae) else float('nan')
                marker = ' ★' if 'Field' in m else '  '
                print(f"  {m:20s} {mae:8.4f} {std:8.4f} {vs:+9.1f}%{marker}")
            
            gain = (best_other - best_field) / best_other * 100
            print(f"  ── Field gain vs best other: {gain:+.1f}%")
