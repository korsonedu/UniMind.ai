#!/usr/bin/env python3
"""Field v5: 推高 bc 上限（单向正向耦合）"""
import json, math, time, random, numpy as np
from collections import defaultdict

BETAS_C = [0.005, 0.01, 0.02, 0.05, 0.1, 0.2]  # 推高耦合
BETAS_A = [0.5, 1.0]          # field_benefit 放大器（精简）
GAMMAS  = [0.2, 0.3]
ETAS    = [0.02, 0.05]
ALPHA   = 0.01                # v4 最优 α
N_STUDENTS = 200
N_DAYS = 150
BUDGET = 6

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
from scipy.sparse import csr_matrix
W = csr_matrix((dat,(row,col)),shape=(n,n))
neighbors = {}
for i in range(n):
    nb = []
    for j in range(n):
        w = W[i,j]
        if w > 0: nb.append((j, w))
    neighbors[i] = nb
print(f'n={n} sweep={len(BETAS_C)*len(BETAS_A)*len(GAMMAS)*len(ETAS)} combos × {N_STUDENTS} students')

def run_sim(sched, bc, ba, gamma, eta, seed):
    K = np.zeros(n); u = np.zeros(n)
    if sched=='fsrs': S = np.ones(n)*1.5; last = np.full(n,-1.0)
    covered = set(random.Random(seed).sample(list(range(n)), max(10,int(n*0.5))))
    np.random.seed(seed%(2**31)); random.seed(seed%(2**31))
    for day in range(N_DAYS):
        if sched=='field':
            diff = np.zeros(n)
            for i in range(n):
                inflow = sum(w*max(0, K[j]-K[i]) for j,w in neighbors[i])
                diff[i] = -ALPHA*K[i] + bc*inflow
            K += diff
        else:
            K *= (1 - ALPHA - 0.005)
        K = np.clip(K, 0, 1)
        if random.random() > 0.85: continue
        for _ in range(6):
            eligible = list(covered)
            if not eligible: continue
            if sched=='greedy': scores = [1-u[i] for i in eligible]
            elif sched=='field':
                scores = [(1-u[i])*(1.0+ba*sum(w*(1-K[j]) for j,w in neighbors[i])) for i in eligible]
            else:
                scores = []
                for i in eligible:
                    if last[i]<0: scores.append(3.0)
                    else:
                        el=max(0.1, day-last[i] if last[i]>=0 else 99)
                        scores.append(1-math.exp(-((el/max(S[i],0.01))**1.2)))
            top = sorted(zip(eligible,scores), key=lambda x:-x[1])[:BUDGET]
            for i,_ in top:
                K[i] += gamma*(1-K[i])
                for j,w in neighbors[i]: K[j] += eta*w*K[i]*(1-K[j])
                K=np.clip(K,0,1); u[i]=K[i]
                if sched=='fsrs':
                    r=int(max(1,min(4,K[i]*5-1))); So=S[i]
                    S[i]=max(1,min(365,(2.5+0.5*(r-2)) if So<=1.5 else So*(1+0.15*(0.5+0.25*r))))
                    last[i]=day
    cov=list(covered)
    return float(np.mean([K[i] for i in cov]))

t0=time.time(); results=[]
for bc in BETAS_C:
    for ba in BETAS_A:
        for gamma in GAMMAS:
            for eta in ETAS:
                vals={}
                for sched in ['greedy','field','fsrs']:
                    finals=[]
                    for i in range(N_STUDENTS):
                        finals.append(run_sim(sched, bc, ba, gamma, eta, 10000+i))
                    vals[f'{sched}']=np.mean(finals)
                vals['bc']=bc; vals['ba']=ba; vals['gamma']=gamma; vals['eta']=eta
                vals['dF']=vals['field']-vals['greedy']
                vsfs=vals['field']-vals['fsrs']
                results.append(vals)
                star='⭐' if vsfs>0.05 else ('+' if vsfs>0 else '-')
                print(f"bc={bc:.3f} ba={ba:.1f} γ={gamma:.1f} η={eta:.2f} "
                      f"F={vals['field']:.4f} G={vals['greedy']:.4f} FS={vals['fsrs']:.4f} "
                      f"vFS={vsfs:+.4f}{star}", flush=True)

top5=sorted(results,key=lambda r:r['field']-r['fsrs'],reverse=True)[:5]
print(f"\n{'='*50}\nTOP 5 vs FSRS\n{'='*50}")
for r in top5:
    print(f"bc={r['bc']:.3f} ba={r['ba']:.1f} γ={r['gamma']:.1f} η={r['eta']:.2f} "
          f"F={r['field']:.4f} FS={r['fsrs']:.4f} Δ={r['field']-r['fsrs']:+.4f}")
best=top5[0]
print(f"\nBest: bc={best['bc']:.3f} ba={best['ba']:.1f} γ={best['gamma']:.1f} η={best['eta']:.2f} "
      f"Δ={best['field']-best['fsrs']:+.4f}")
print(f"Total: {time.time()-t0:.0f}s")
