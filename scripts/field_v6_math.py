#!/usr/bin/env python3
"""Field v6 跨学科验证：高中数学"""
import json, math, time, random, numpy as np
from collections import defaultdict
from scipy.sparse import csr_matrix, diags

# ═══ 扫参 ═══
ALPHAS  = [0.02]
BETAS_E = [0.0, 0.001, 0.005]
BETAS_A = [0.5, 1.0]
GAMMAS  = [0.2, 0.3]
ETAS    = [0.02, 0.05]
N_STUDENTS = 200
N_DAYS = 150
BUDGET_BASE = 35  # 每35个KP配1次复习
BUDGET_MAX  = 10
UNLOCK_EVERY = 10              # 614 KP → 每10天一批
KPS_PER_UNLOCK = 40            # 614/40 ≈ 15批
INIT_K = 0.3
EXAM_INTERVAL = 30
EXAM_COVERAGE = 0.3
SLEEP_DECAY = 0.005

# ═══ 加载图 ═══
tree_path = 'math_tree.json'
edges_path = 'math_llm_edges.json'
with open(tree_path) as f: data = json.load(f)
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
with open(edges_path) as f: llm = json.load(f)
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
# Lmat
Lmat_pre = csr_matrix(W.T, shape=(n,n))
col_sum = np.array(Lmat_pre.sum(axis=1)).flatten()
Lmat_pre = Lmat_pre - diags(col_sum, 0, shape=(n,n))
# syllabus
from collections import deque
indeg = np.zeros(n)
for i in range(n):
    for j,_ in neighbors[i]: indeg[j] += 1
q = deque([i for i in range(n) if indeg[i]==0])
syllabus = []
while q:
    i = q.popleft(); syllabus.append(i)
    for j,_ in neighbors[i]:
        indeg[j] -= 1
        if indeg[j]==0: q.append(j)
missing = set(range(n)) - set(syllabus); syllabus.extend(missing)
batches = [syllabus[i:i+KPS_PER_UNLOCK] for i in range(0, len(syllabus), KPS_PER_UNLOCK)]
print(f'n={n} edges={W.nnz} batches={len(batches)}')

def run_sim(sched, alpha, beta_e, beta_a, gamma, eta, seed):
    K = np.zeros(n); u = np.zeros(n)
    if sched=='fsrs': S = np.ones(n)*1.5; last = np.full(n,-1.0)
    np.random.seed(seed%(2**31)); random.seed(seed%(2**31))
    unlocked = set(); next_batch = 0
    for day in range(N_DAYS):
        if day % UNLOCK_EVERY == 0 and next_batch < len(batches):
            for i in batches[next_batch]:
                if i<n: unlocked.add(i); K[i]=INIT_K; u[i]=INIT_K
                if sched=='fsrs': last[i]=-1; S[i]=1.5
            next_batch += 1
        K *= (1 - alpha - SLEEP_DECAY); K = np.clip(K, 0, 1)
        if sched=='field' and beta_e > 0:
            u += (-alpha*u + beta_e*Lmat_pre.dot(u)); u = np.clip(u, 0, 1)
        if random.random() > 0.85: continue
        budget = min(BUDGET_MAX, max(1, (len(unlocked) + BUDGET_BASE - 1) // BUDGET_BASE))
        for _ in range(budget):
            eligible = sorted(unlocked)
            if not eligible: continue
            if sched=='greedy': scores = [1-u[i] for i in eligible]
            elif sched=='field':
                scores = [(1-u[i])*(1.0+beta_a*sum(w*(1-u[j]) for j,w in neighbors[i])) for i in eligible]
            else:
                scores = []
                for i in eligible:
                    if last[i]<0: scores.append(3.0)
                    else:
                        el = max(0.1, day-last[i] if last[i]>=0 else 99)
                        scores.append(1-math.exp(-((el/max(S[i],0.01))**1.2)))
            top = sorted(zip(eligible,scores),key=lambda x:-x[1])[:budget]
            for i,_ in top:
                K[i] += gamma*(1-K[i])
                for j,w in neighbors[i]: K[j] += eta*w*K[i]*(1-K[j])
                K=np.clip(K,0,1); u[i]=K[i]
                if sched=='fsrs':
                    r=int(max(1,min(4,K[i]*5-1))); So=S[i]
                    S[i]=max(1,min(365,(2.5+0.5*(r-2)) if So<=1.5 else So*(1+0.15*(0.5+0.25*r))))
                    last[i]=day
        if day>0 and day%EXAM_INTERVAL==0:
            testable=sorted(unlocked); nt=max(3,int(len(testable)*EXAM_COVERAGE))
            for i in random.sample(testable,min(nt,len(testable))):
                if random.random()<K[i]: K[i]+=0.05*(1-K[i]); u[i]=K[i]; K=np.clip(K,0,1)
    return float(np.mean([K[i] for i in unlocked])) if unlocked else 0.0

t0=time.time(); results=[]
for a in ALPHAS:
    for be in BETAS_E:
        for ba in BETAS_A:
            for g in GAMMAS:
                for e in ETAS:
                    vals={}
                    for sched in ['greedy','field','fsrs']:
                        finals=[run_sim(sched,a,be,ba,g,e,10000+i) for i in range(N_STUDENTS)]
                        vals[f'{sched}']=np.mean(finals)
                    vals['be']=be; vals['ba']=ba; vals['g']=g; vals['e']=e
                    vsfs=vals['field']-vals['fsrs']
                    results.append(vals)
                    print(f"βe={be:.3f} βa={ba:.1f} γ={g:.1f} η={e:.2f} "
                          f"F={vals['field']:.4f} G={vals['greedy']:.4f} FS={vals['fsrs']:.4f} "
                          f"vFS={vsfs:+.4f}{'⭐' if vsfs>0.03 else ('+' if vsfs>0 else '-')}", flush=True)

top5=sorted(results,key=lambda r:r['field']-r['fsrs'],reverse=True)[:5]
print(f"\nTOP 5 vs FSRS")
for r in top5:
    print(f"βe={r['be']:.3f} βa={r['ba']:.1f} γ={r['g']:.1f} η={r['e']:.2f} "
          f"F={r['field']:.4f} FS={r['fsrs']:.4f} Δ={r['field']-r['fsrs']:+.4f}")
best=top5[0]
be0=[r for r in results if r['be']==0.0]
be0_best=max(be0,key=lambda r:r['field']-r['fsrs']) if be0 else None
print(f"\nBest: βe={best['be']:.3f} Δ={best['field']-best['fsrs']:+.4f}")
if be0_best: print(f"Ablation βe=0: Δ={be0_best['field']-be0_best['fsrs']:+.4f}")
print(f"Total: {time.time()-t0:.0f}s")
