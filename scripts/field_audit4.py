#!/usr/bin/env python3
"""
Field 审计 Part 4: 按边类型分离图 + 有向约束初探
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
        
        self.adj_all = defaultdict(list)
        # 树边 (parent-child within KPs)
        for nd in nodes:
            pid = nd.get('parent_id')
            if pid and nd['id'] in self.id2i and pid in self.id2i:
                self.adj_all[nd['id']].append((pid, 0.8, 'tree'))
                self.adj_all[pid].append((nd['id'], 0.8, 'tree'))
        # 兄弟边
        cbp = defaultdict(list)
        for nd in nodes:
            pid = nd.get('parent_id')
            if pid and nd['id'] in self.id2i: cbp[pid].append(nd['id'])
        for s in cbp.values():
            for i in range(len(s)):
                for j in range(i+1, len(s)):
                    self.adj_all[s[i]].append((s[j], 0.3, 'sibling'))
                    self.adj_all[s[j]].append((s[i], 0.3, 'sibling'))
        # LLM 边
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
            etype = e.get('edge_type', '?')
            self.adj_all[s].append((t, w, etype))
            self.adj_all[t].append((s, w, etype))
    
    def build_L(self, edge_types=None):
        """只包含指定类型的边"""
        row, col, dat = [], [], []
        for sk, ns in self.adj_all.items():
            if sk in self.id2i:
                si = self.id2i[sk]
                for tk, w, etype in ns:
                    if tk in self.id2i:
                        if edge_types is None or etype in edge_types:
                            row.append(si); col.append(self.id2i[tk]); dat.append(w)
        A = csr_matrix((dat, (row, col)), shape=(self.n, self.n))
        deg = np.array(A.sum(axis=1)).flatten(); deg[deg < 1e-8] = 1.0
        D_inv_sqrt = diags(1.0 / np.sqrt(deg), 0)
        return eye(self.n, format='csr') - D_inv_sqrt.dot(A).dot(D_inv_sqrt)
    
    def diagnose(self, obs_idx, obs_val, L, lam=2.0, prior_mean=0.5, prior_prec=0.1):
        Q_base = lam * L + prior_prec * eye(self.n, format='csr')
        d_data = np.zeros(self.n)
        for idx in obs_idx: d_data[idx] = 4.0
        D = diags(d_data, 0, shape=(self.n, self.n))
        b = Q_base.dot(np.full(self.n, prior_mean))
        for idx, val in zip(obs_idx, obs_val): b[idx] += val * 4.0
        Q = Q_base + D
        mu, info = cg(Q, b, rtol=1e-6, maxiter=500)
        if info != 0:
            mu = np.full(self.n, prior_mean)
            for idx, val in zip(obs_idx, obs_val): mu[idx] = val
        return mu


# ═══════════════════════════════════════════════════
# 前置依赖仿真（复用 part 3）
# ═══════════════════════════════════════════════════

def simulate_prerequisite(tree_file, edge_file, n_students=200, n_days=100, seed=42):
    with open(tree_file) as f: data = json.load(f)
    nodes = data['nodes']
    kps = [n for n in nodes if n.get('level') == 'kp']
    n = len(kps)
    n2id = {nd['name']: nd['id'] for nd in kps}
    id2i = {kid: i for i, kid in enumerate([nd['id'] for nd in kps])}
    
    with open(edge_file) as f: llm = json.load(f)
    prereqs = defaultdict(list); children = defaultdict(list)
    for e in llm:
        if e.get('edge_type') != 'prerequisite': continue
        s = n2id.get(e.get('source_name', ''))
        t = n2id.get(e.get('target_name', ''))
        if s and t and s in id2i and t in id2i:
            si, ti = id2i[s], id2i[t]
            prereqs[ti].append(si); children[si].append(ti)
    
    from collections import deque
    indeg = np.zeros(n)
    for i in prereqs: indeg[i] = len(prereqs[i])
    q = deque([i for i in range(n) if indeg[i] == 0])
    topo = []
    while q:
        i = q.popleft(); topo.append(i)
        for j in children[i]:
            indeg[j] -= 1
            if indeg[j] == 0: q.append(j)
    
    np.random.seed(seed)
    difficulty = np.random.beta(2, 5, n)
    
    results = []
    for s in range(n_students):
        np.random.seed(10000+s); random.seed(10000+s)
        K = np.zeros(n); learned = np.zeros(n, bool)
        observations = []
        
        for day in range(n_days):
            for i in range(n):
                if not learned[i]:
                    ok = all(learned[p] and K[p] > 0.3 for p in prereqs[i])
                    if ok: learned[i] = True; K[i] = 0.2
            
            learned_list = [i for i in range(n) if learned[i]]
            if not learned_list: continue
            
            urgencies = [(1.0-K[i])/max(K[i], 0.01) for i in learned_list]
            top = sorted(learned_list, key=lambda i: 
                        -urgencies[learned_list.index(i)])[:min(10, len(learned_list))]
            
            for i in top:
                gamma = 0.30 * (1 - 0.6 * difficulty[i])
                K[i] += gamma * (1 - K[i])
            
            K *= 0.985; K += np.random.normal(0, 0.008, n); K = np.clip(K, 0, 1)
            
            if day > 0 and day % 14 == 0:
                testable = [i for i in range(n) if learned[i]]
                n_test = max(3, int(len(testable) * 0.05))
                tested = random.sample(testable, min(n_test, len(testable)))
                for i in tested:
                    p = 1.0/(1.0+math.exp(-5*(K[i]-difficulty[i])))
                    correct = random.random() < p
                    observations.append((day, i, correct))
                    if correct: K[i] += 0.03*(1-K[i])
                    K = np.clip(K, 0, 1)
        
        results.append({'true_K': K.copy(), 'observations': observations})
    
    return results


# ═══════════════════════════════════════════════════
# Main: 按边类型消融
# ═══════════════════════════════════════════════════

if __name__ == '__main__':
    TREES = {'CFA': ('cfa_tree.json', 'cfa_llm_edges.json'),
             'Math': ('math_tree.json', 'math_llm_edges.json')}
    
    print("=" * 80)
    print("边类型消融 — 前置依赖场景")
    print("=" * 80)
    
    for name, (tf, ef) in TREES.items():
        gmrf = GMRF(tf, ef)
        
        # 构建不同边类型组合的 Laplacian
        graphs = {
            'all edges': gmrf.build_L(None),
            'no prerequisite': gmrf.build_L({'tree', 'sibling', 'similar', 'co_occur', 'contrast', 'confusion', 'derivation'}),
            'only sibling+similar': gmrf.build_L({'sibling', 'similar'}),
            'only tree+sibling': gmrf.build_L({'tree', 'sibling'}),
            'no graph (λ=0)': eye(gmrf.n, format='csr') * 0,
        }
        
        prereq_results = simulate_prerequisite(tf, ef)
        avg_obs = np.mean([len(r['observations']) for r in prereq_results])
        all_K = np.array([r['true_K'] for r in prereq_results])
        kp_means = all_K.mean(axis=0)
        
        print(f"\n{'─'*80}")
        print(f"[{name}] n={gmrf.n}  obs={avg_obs:.0f}  KP std={kp_means.std():.4f}  KP range=[{kp_means.min():.3f}, {kp_means.max():.3f}]")
        print(f"{'─'*80}")
        
        # 评测
        all_methods = {}
        for gname, L in graphs.items():
            for lam in [0.5, 1.0, 2.0]:
                maes = []
                for r in prereq_results:
                    true_K = r['true_K']
                    obs = r['observations']
                    obs_dict = {}
                    for day, idx, correct in obs:
                        obs_dict[idx] = 0.85 if correct else 0.15
                    obs_idx = list(obs_dict.keys())
                    obs_val = [obs_dict[i] for i in obs_idx]
                    mu = gmrf.diagnose(obs_idx, obs_val, L, lam=lam, prior_mean=0.5, prior_prec=0.1)
                    maes.append(np.mean(np.abs(mu - true_K)))
                label = f'Field({gname}, λ={lam})'
                all_methods[label] = (np.mean(maes), np.std(maes))
        
        # 基线
        naive_maes = []; ability_maes = []
        for r in prereq_results:
            true_K = r['true_K']
            obs = r['observations']
            obs_dict = {}
            for day, idx, correct in obs:
                obs_dict[idx] = 0.85 if correct else 0.15
            
            mu_n = np.full(gmrf.n, 0.5)
            for i, v in obs_dict.items(): mu_n[i] = v
            naive_maes.append(np.mean(np.abs(mu_n - true_K)))
            
            avg = np.mean(list(obs_dict.values())) if obs_dict else 0.5
            ability_maes.append(np.mean(np.abs(avg - true_K)))
        
        all_methods['Naive'] = (np.mean(naive_maes), np.std(naive_maes))
        all_methods['Ability'] = (np.mean(ability_maes), np.std(ability_maes))
        
        # 按 MAE 排序
        for method, (mae, std) in sorted(all_methods.items(), key=lambda x: x[1][0])[:15]:
            print(f"  {method:45s}: {mae:.4f} ± {std:.4f}")
    
    print("\n\n" + "=" * 80)
    print("均匀场景（复用 part 2 仿真）— 边类型消融")
    print("=" * 80)
    
    # 用 IndependentStudentSim（均匀 urgency）
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
                results.append({'true_K': K.copy(), 'observations': observations})
            return results
    
    for name, (tf, ef) in TREES.items():
        gmrf = GMRF(tf, ef)
        
        graphs = {
            'all edges': gmrf.build_L(None),
            'no prerequisite': gmrf.build_L({'tree', 'sibling', 'similar', 'co_occur', 'contrast', 'confusion', 'derivation'}),
            'only sibling+similar': gmrf.build_L({'sibling', 'similar'}),
            'no graph': eye(gmrf.n, format='csr') * 0,
        }
        
        sim = IndependentStudentSim(tf)
        sim_results = sim.run()
        
        print(f"\n{'─'*80}")
        print(f"[{name}] uniform, KP std ≈ 0.01")
        print(f"{'─'*80}")
        
        for gname, L in graphs.items():
            for lam in [0.5, 2.0]:
                maes = []
                for r in sim_results:
                    true_K = r['true_K']
                    obs = r['observations']
                    obs_dict = {}
                    for day, idx, correct in obs:
                        obs_dict[idx] = 0.85 if correct else 0.15
                    obs_idx = list(obs_dict.keys())
                    obs_val = [obs_dict[i] for i in obs_idx]
                    mu = gmrf.diagnose(obs_idx, obs_val, L, lam=lam, prior_mean=0.5, prior_prec=0.1)
                    maes.append(np.mean(np.abs(mu - true_K)))
                print(f"  Field({gname:25s}, λ={lam:.1f}): {np.mean(maes):.4f}")
