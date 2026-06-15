#!/usr/bin/env python3
"""Field v3: 图耦合衰减 vs 独立衰减"""
import json, math, time, random, numpy as np
from collections import defaultdict
from scipy.sparse import csr_matrix, diags
from scipy.sparse.linalg import eigsh

# ═══ 扫参 ═══
BETAS_COUPLE = [0.001, 0.002, 0.005, 0.01]  # 图耦合强度
BETAS_AMP    = [0.5, 1.0, 2.0]               # field_benefit 放大器
GAMMAS = [0.2, 0.3]
ETAS   = [0.02, 0.05]
ALPHA  = 0.02
N_STUDENTS = 60
N_DAYS = 150
BUDGET = 6

# ═══ 加载图 ═══
with open('cfa_tree.json') as f: data = json.load(f)
nodes = data['nodes']; kps = [n for n in nodes if n.get('level')=='kp']
kp_ids = [n['id'] for n in kps]; id2i = {kid:i for i,kid in enumerate(kp_ids)}
n = len(kps)
adj = defaultdict(list)
for nd in nodes:
    pid = nd.get('parent_id')
    if pid and nd['id'] in id2i and pid in id2i: adj[nd['id']].append((pid,0.8)); adj[pid].append((nd['id'],0.8))
cbp = defaultdict(list)
for nd in nodes:
    pid = nd.get('parent_id')
    if pid and nd['id'] in id2i: cbp[pid].append(nd['id'])
for s in cbp.values():
    for i in range(len(s)):
        for j in range(i+1,len(s)): adj[s[i]].append((s[j],0.3)); adj[s[j]].append((s[i],0.3))
with open('cfa_llm_edges.json') as f: llm = json.load(f)
n2id = {nd['name']:nd['id'] for nd in kps}
for e in llm:
    s=n2id.get(e.get('source_name','')); t=n2id.get(e.get('target_name',''))
    if s and t and s in id2i and t in id2i: adj[s].append((t,float(e.get('weight',0.5))))
row,col,dat=[],[],[]
for sk,ns in adj.items():
    if sk in id2i:
        for tk,w in ns:
            if tk in id2i: row.append(id2i[sk]); col.append(id2i[tk]); dat.append(w)
W = csr_matrix((dat,(row,col)),shape=(n,n))
# 度 & 邻居列表
degrees = np.array(W.sum(axis=1)).flatten()
neighbors = {}
for i in range(n):
    nb = []
    for j in range(n):
        w = W[i,j]
        if w > 0: nb.append((j, w))
    neighbors[i] = nb

# 稳定性检查
from scipy.sparse.linalg import eigsh
Lmat = csr_matrix(W.T, shape=(n,n))
cs_arr = np.array(Lmat.sum(axis=1)).flatten()
Lmat = Lmat - diags(cs_arr, 0, shape=(n,n))
lm = eigsh(-Lmat, k=1, which='LM', return_eigenvectors=False)[0]
print(f'n={n} edges={W.nnz} λ_max={lm:.1f}')
print(f'sweep={len(BETAS_COUPLE)*len(BETAS_AMP)*len(GAMMAS)*len(ETAS)} combos')

def run_sim(sched, beta_couple, beta_amp, gamma, eta, seed):
    K = np.zeros(n); u = np.zeros(n)
    if sched=='fsrs': S = np.ones(n)*1.5; last = np.full(n,-1.0)
    covered = set(random.Random(seed).sample(list(range(n)), max(10,int(n*0.5))))
    np.random.seed(seed%(2**31)); random.seed(seed%(2**31))
    cumul = 0.0
    for day in range(N_DAYS):
        # ── 衰减（Field=图耦合，Greedy/FSRS=独立）──
        if sched=='field':
            # dK/dt = -α·K + β·Σ w_ij·(K_j - K_i)
            # K_i += (-α·K_i + β·Σ w_ij·(K_j-K_i)) * dt
            diff = np.zeros(n)
            for i in range(n):
                inflow = sum(w*K[j] for j,w in neighbors[i])
                outflow = degrees[i]*K[i] if degrees[i]>0 else 0
                diff[i] = -ALPHA*K[i] + beta_couple*(inflow - outflow)
            K += diff
        else:
            K *= (1 - ALPHA - 0.005)
        K = np.clip(K, 0, 1)

        if random.random() > 0.85: continue  # skip day

        for _ in range(6):
            eligible = list(covered)
            if not eligible: continue
            # ── 选题 ──
            if sched=='greedy':
                scores = [1-u[i] for i in eligible]
            elif sched=='field':
                scores = []
                for i in eligible:
                    fb = sum(w*(1-K[j]) for j,w in neighbors[i]) if neighbors[i] else 0.0
                    scores.append((1-u[i]) * (1.0 + beta_amp*fb))
            else:  # fsrs
                scores = []
                for i in eligible:
                    if last[i]<0: scores.append(3.0)
                    else:
                        el = max(0.1, day-last[i] if last[i]>=0 else 99)
                        R = math.exp(-((el/max(S[i],0.01))**1.2))
                        scores.append(1-R)
            top = sorted(zip(eligible,scores), key=lambda x:-x[1])[:BUDGET]
            # ── 复习 + η ──
            for i,_ in top:
                K[i] += gamma*(1-K[i])
                for j,w in neighbors[i]:
                    K[j] += eta*w*K[i]*(1-K[j])
                K = np.clip(K,0,1); u[i] = K[i]
                if sched=='fsrs':
                    r = int(max(1,min(4,K[i]*5-1)))
                    So = S[i]
                    S[i] = max(1, min(365, (2.5+0.5*(r-2)) if So<=1.5 else So*(1+0.15*(0.5+0.25*r))))
                    last[i] = day
        cov = list(covered)
        cumul += float(np.mean([K[i] for i in cov]))
    cov = list(covered)
    final = float(np.mean([K[i] for i in cov]))
    minK  = float(np.min([K[i] for i in cov]))
    return final, cumul/N_DAYS, minK

t0 = time.time()
results = []
for bc in BETAS_COUPLE:
    for ba in BETAS_AMP:
        for gamma in GAMMAS:
            for eta in ETAS:
                vals = {}
                for sched in ['greedy','field','fsrs']:
                    finals, cumuls, mins = [], [], []
                    for i in range(N_STUDENTS):
                        f, c, m = run_sim(sched, bc, ba, gamma, eta, 10000+i)
                        finals.append(f); cumuls.append(c); mins.append(m)
                    vals[f'{sched}_final'] = np.mean(finals)
                    vals[f'{sched}_cumul'] = np.mean(cumuls)
                    vals[f'{sched}_min'] = np.mean(mins)
                vals['bc']=bc; vals['ba']=ba; vals['gamma']=gamma; vals['eta']=eta
                vals['d_final'] = vals['field_final'] - vals['greedy_final']
                vals['d_fsrs'] = vals['fsrs_final'] - vals['greedy_final']
                results.append(vals)
                d = vals['d_final']
                star = '⭐' if d>0.05 else ('+' if d>0.02 else ('-' if d>-0.01 else '✗'))
                print(f"bc={bc:.3f} ba={ba:.1f} γ={gamma:.1f} η={eta:.2f} "
                      f"F={vals['field_final']:.4f} G={vals['greedy_final']:.4f} FS={vals['fsrs_final']:.4f} "
                      f"ΔF={d:+.4f}{star}  ΔFS={vals['d_fsrs']:+.4f}",
                      flush=True)

print(f"\n{'='*50}\nTOP 5 by ΔF\n{'='*50}")
top5 = sorted(results, key=lambda r: r['d_final'], reverse=True)[:5]
for r in top5:
    print(f"bc={r['bc']:.3f} ba={r['ba']:.1f} γ={r['gamma']:.1f} η={r['eta']:.2f} "
          f"F={r['field_final']:.4f} G={r['greedy_final']:.4f} FS={r['fsrs_final']:.4f} "
          f"ΔF={r['d_final']:+.4f} ΔFS={r['d_fsrs']:+.4f}")

best = top5[0]
print(f"\nBest: bc={best['bc']:.3f} ba={best['ba']:.1f} γ={best['gamma']:.1f} η={best['eta']:.2f}")
print(f"  Field vs Greedy: {best['d_final']*100:+.1f}%")
print(f"  Field vs FSRS:   {best['field_final']-best['fsrs_final']:+.4f}")
print(f"Total: {time.time()-t0:.0f}s")
