#!/usr/bin/env python3
"""Field Audit Part 6: 自适应先验 vs 固定先验"""
import json, math, random, numpy as np
from collections import defaultdict
from scipy.sparse import csr_matrix, diags, eye
from scipy.sparse.linalg import cg

# Build graph
with open('cfa_tree.json') as f: data = json.load(f)
nodes = data['nodes']
kps = [n for n in nodes if n.get('level') == 'kp']
n = len(kps)
n2id = {nd['name']: nd['id'] for nd in kps}
id2i = {kid: i for i, kid in enumerate([nd['id'] for nd in kps])}

adj = defaultdict(list)
for nd in nodes:
    pid = nd.get('parent_id')
    if pid and nd['id'] in id2i and pid in id2i:
        adj[nd['id']].append((pid, 0.8)); adj[pid].append((nd['id'], 0.8))
cbp = defaultdict(list)
for nd in nodes:
    pid = nd.get('parent_id')
    if pid and nd['id'] in id2i: cbp[pid].append(nd['id'])
for s in cbp.values():
    for i in range(len(s)):
        for j in range(i+1, len(s)):
            adj[s[i]].append((s[j], 0.3)); adj[s[j]].append((s[i], 0.3))
with open('cfa_llm_edges.json') as f: llm = json.load(f)
pair_seen = set()
for e in llm:
    s = n2id.get(e.get('source_name', '')); t = n2id.get(e.get('target_name', ''))
    if not (s and t and s in id2i and t in id2i): continue
    si, ti = id2i[s], id2i[t]; pair = tuple(sorted([si, ti]))
    if pair in pair_seen: continue
    pair_seen.add(pair)
    adj[s].append((t, float(e.get('weight', 0.5)))); adj[t].append((s, float(e.get('weight', 0.5))))

row, col, dat_w = [], [], []
for sk, ns in adj.items():
    if sk in id2i:
        si = id2i[sk]
        for tk, w in ns:
            if tk in id2i: row.append(si); col.append(id2i[tk]); dat_w.append(w)
A = csr_matrix((dat_w, (row, col)), shape=(n, n))
deg = np.array(A.sum(axis=1)).flatten(); deg[deg < 1e-8] = 1.0
L = eye(n, format='csr') - diags(1.0/np.sqrt(deg), 0).dot(A).dot(diags(1.0/np.sqrt(deg), 0))

def diagnose(obs_idx, obs_val, obs_prec, lam=2.0, prior_mean=0.5, prior_prec=0.1):
    Q_base = lam * L + prior_prec * eye(n, format='csr')
    d_data = np.zeros(n)
    for idx, prec in zip(obs_idx, obs_prec): d_data[idx] = prec
    D = diags(d_data, 0, shape=(n, n))
    b = Q_base.dot(np.full(n, prior_mean))
    for idx, val, prec in zip(obs_idx, obs_val, obs_prec): b[idx] += val * prec
    Q = Q_base + D
    mu, info = cg(Q, b, rtol=1e-6, maxiter=500)
    if info != 0:
        mu = np.full(n, prior_mean)
        for idx, val in zip(obs_idx, obs_val): mu[idx] = val
    return mu

# Sim
np.random.seed(42); difficulty = np.clip(np.random.beta(2, 5, n), 0.01, 0.99)
all_true_K = []
for s in range(200):
    np.random.seed(10000+s); random.seed(10000+s)
    K = np.zeros(n)
    for day in range(100):
        u = [(1.0-K[i])/max(K[i],0.01) for i in range(n)]
        top = sorted(range(n), key=lambda i: -u[i])[:10]
        for i in top: K[i] += 0.30*(1-0.6*difficulty[i])*(1-K[i])
        K *= 0.985; K += np.random.normal(0,0.008,n); K = np.clip(K,0,1)
    all_true_K.append(K.copy())
all_true_K = np.array(all_true_K)

true_global = all_true_K.mean()
print(f"CFA: true_K mean={true_global:.4f}, KP std={all_true_K.mean(axis=0).std():.5f}\n")
print(f"{'method':42s} {'sparsity':>7s} {'obs/KP':>6s} {'MAE':>8s} {'vs_best':>9s}")
print("-" * 80)

for sparsity in [0.1, 0.2, 0.3, 0.5]:
    for n_obs in [1, 2, 3]:
        f_fixed = []; f_adapt = []; ab = []; nv = []
        for s in range(200):
            true_K = all_true_K[s]
            n_obs_kps = max(1, int(n * sparsity))
            obs_kps = random.sample(range(n), min(n_obs_kps, n))
            obs_idx = []; obs_val = []; obs_prec = []
            for i in obs_kps:
                for _ in range(n_obs):
                    p = 1.0/(1.0+math.exp(-5*(true_K[i]-0.3)))
                    obs_idx.append(i)
                    obs_val.append(0.85 if random.random() < p else 0.15)
                    obs_prec.append(4.0)
            agg = defaultdict(list)
            for idx, val, prec in zip(obs_idx, obs_val, obs_prec): agg[idx].append((val, prec))
            fi = []; fv = []; fp = []
            for idx, vals in agg.items():
                tp = sum(p for _, p in vals)
                fv.append(sum(v*p for v, p in vals) / tp); fi.append(idx); fp.append(tp)
            
            mu_f = diagnose(fi, fv, fp, lam=2.0, prior_mean=0.5, prior_prec=0.1)
            f_fixed.append(np.mean(np.abs(mu_f - true_K)))
            
            am = np.mean(fv) if fv else 0.5
            mu_a = diagnose(fi, fv, fp, lam=2.0, prior_mean=am, prior_prec=0.1)
            f_adapt.append(np.mean(np.abs(mu_a - true_K)))
            
            ab.append(np.mean(np.abs(am - true_K)))
            
            mu_n = np.full(n, 0.5)
            for i, v in zip(fi, fv): mu_n[i] = v
            nv.append(np.mean(np.abs(mu_n - true_K)))
        
        best = min(np.mean(ab), np.mean(nv))
        print(f"  {'Field (fixed 0.5)':42s} {sparsity:7.1f} {n_obs:6d} {np.mean(f_fixed):8.4f} {(best-np.mean(f_fixed))/best*100:+9.1f}%")
        print(f"  {'Field (adaptive)':42s} {sparsity:7.1f} {n_obs:6d} {np.mean(f_adapt):8.4f} {(best-np.mean(f_adapt))/best*100:+9.1f}%")
        print(f"  {'Ability':42s} {sparsity:7.1f} {n_obs:6d} {np.mean(ab):8.4f}")
        print(f"  {'Naive':42s} {sparsity:7.1f} {n_obs:6d} {np.mean(nv):8.4f}")
        print()
