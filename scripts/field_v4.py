#!/usr/bin/env python3
"""Field v4: 单向正向图耦合 + 扫 α + 扫 β"""
import json, math, time, random, numpy as np
from collections import defaultdict
from scipy.sparse import csr_matrix, diags
from scipy.sparse.linalg import eigsh

# ═══ 扫参 ═══
ALPHAS  = [0.01, 0.02, 0.03]
BETAS_C = [0.001, 0.002, 0.005]    # 图耦合强度（单向正向）
BETAS_A = [0.5, 1.0, 2.0]          # field_benefit 放大器
GAMMAS  = [0.2, 0.3]
ETAS    = [0.02, 0.05]
N_STUDENTS = 80
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
neighbors = {}
for i in range(n):
    nb = []
    for j in range(n):
        w = W[i,j]
        if w > 0: nb.append((j, w))
    neighbors[i] = nb
print(f'n={n} edges={W.nnz}')

# 稳定性检查
Lmat = csr_matrix(W.T,shape=(n,n)); cs_arr=np.array(Lmat.sum(axis=1)).flatten()
Lmat=Lmat-diags(cs_arr,0,shape=(n,n))
lm=eigsh(-Lmat,k=1,which='LM',return_eigenvectors=False)[0]
print(f'λ_max={lm:.1f} sweep={len(ALPHAS)*len(BETAS_C)*len(BETAS_A)*len(GAMMAS)*len(ETAS)} combos')

def run_sim(sched, alpha, beta_c, beta_a, gamma, eta, seed):
    K = np.zeros(n); u = np.zeros(n)
    if sched=='fsrs': S = np.ones(n)*1.5; last = np.full(n,-1.0)
    covered = set(random.Random(seed).sample(list(range(n)), max(10,int(n*0.5))))
    np.random.seed(seed%(2**31)); random.seed(seed%(2**31))
    cumul = 0.0
    for day in range(N_DAYS):
        # ── 衰减 ──
        if sched=='field':
            # 单向正向: dK_i/dt = -α·K_i + β·Σ w_ij·max(0, K_j-K_i)
            diff = np.zeros(n)
            for i in range(n):
                inflow = sum(w*max(0, K[j]-K[i]) for j,w in neighbors[i])
                diff[i] = -alpha*K[i] + beta_c*inflow
            K += diff
        else:
            K *= (1 - alpha - 0.005)
        K = np.clip(K, 0, 1)

        if random.random() > 0.85: continue

        for _ in range(6):
            eligible = list(covered)
            if not eligible: continue
            if sched=='greedy':
                scores = [1-u[i] for i in eligible]
            elif sched=='field':
                scores = []
                for i in eligible:
                    fb = sum(w*(1-K[j]) for j,w in neighbors[i]) if neighbors[i] else 0.0
                    scores.append((1-u[i]) * (1.0 + beta_a*fb))
            else:
                scores = []
                for i in eligible:
                    if last[i]<0: scores.append(3.0)
                    else:
                        el=max(0.1, day-last[i] if last[i]>=0 else 99)
                        R=math.exp(-((el/max(S[i],0.01))**1.2)); scores.append(1-R)
            top = sorted(zip(eligible,scores), key=lambda x:-x[1])[:BUDGET]
            for i,_ in top:
                K[i] += gamma*(1-K[i])
                for j,w in neighbors[i]:
                    K[j] += eta*w*K[i]*(1-K[j])
                K=np.clip(K,0,1); u[i]=K[i]
                if sched=='fsrs':
                    r=int(max(1,min(4,K[i]*5-1))); So=S[i]
                    S[i]=max(1,min(365,(2.5+0.5*(r-2)) if So<=1.5 else So*(1+0.15*(0.5+0.25*r))))
                    last[i]=day
        cov=list(covered); cumul+=float(np.mean([K[i] for i in cov]))
    cov=list(covered)
    return float(np.mean([K[i] for i in cov])), cumul/N_DAYS

t0=time.time(); results=[]
for a in ALPHAS:
    for bc in BETAS_C:
        for ba in BETAS_A:
            for gamma in GAMMAS:
                for eta in ETAS:
                    vals={}
                    for sched in ['greedy','field','fsrs']:
                        finals, cumuls = [], []
                        for i in range(N_STUDENTS):
                            f,c = run_sim(sched, a, bc, ba, gamma, eta, 10000+i)
                            finals.append(f); cumuls.append(c)
                        vals[f'{sched}_final']=np.mean(finals)
                        vals[f'{sched}_cumul']=np.mean(cumuls)
                    vals.update({'a':a,'bc':bc,'ba':ba,'gamma':gamma,'eta':eta})
                    vals['dF']=vals['field_final']-vals['greedy_final']
                    vals['dFS']=vals['fsrs_final']-vals['greedy_final']
                    results.append(vals)
                    d=vals['dF']; vsfs=vals['field_final']-vals['fsrs_final']
                    star='⭐' if vsfs>0.03 else ('+' if vsfs>0 else ('-' if d>0.01 else '✗'))
                    print(f"α={a:.2f} bc={bc:.3f} ba={ba:.1f} γ={gamma:.1f} η={eta:.2f} "
                          f"F={vals['field_final']:.4f} G={vals['greedy_final']:.4f} FS={vals['fsrs_final']:.4f} "
                          f"ΔF={d:+.4f} vFS={vsfs:+.4f}{star}", flush=True)

print(f"\n{'='*50}\nTOP 5 by Field-FSRS Δ\n{'='*50}")
top5=sorted(results,key=lambda r:r['field_final']-r['fsrs_final'],reverse=True)[:5]
for r in top5:
    d=r['field_final']-r['fsrs_final']
    print(f"α={r['a']:.2f} bc={r['bc']:.3f} ba={r['ba']:.1f} γ={r['gamma']:.1f} η={r['eta']:.2f} "
          f"F={r['field_final']:.4f} FS={r['fsrs_final']:.4f} Δ={d:+.4f}")

best=top5[0]
print(f"\nBest: α={best['a']:.2f} bc={best['bc']:.3f} ba={best['ba']:.1f} γ={best['gamma']:.1f} η={best['eta']:.2f}")
print(f"  Field vs Greedy: {best['dF']*100:+.1f}%")
print(f"  Field vs FSRS:   {best['field_final']-best['fsrs_final']:+.4f}")
print(f"Total: {time.time()-t0:.0f}s")
