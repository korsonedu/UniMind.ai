#!/usr/bin/env python3
"""Field 小批量参数扫描：估计器精度 → 调度效率 → retention"""
import json, math, time, random, numpy as np
from collections import defaultdict
from scipy.sparse import csr_matrix, diags
from scipy.sparse.linalg import cg, eigsh

# ═══ 扫参 ═══
ALPHAS = [0.005, 0.01, 0.02]
BETAS  = [0.001, 0.005, 0.02, 0.1, 0.5]
GAMMAS = [0.2, 0.3]
ETAS   = [0.02, 0.05]
N_STUDENTS = 50
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
if True:
    with open('cfa_llm_edges.json') as f: llm = json.load(f)
    n2id = {n['name']:n['id'] for n in kps}
    for e in llm:
        s=n2id.get(e.get('source_name','')); t=n2id.get(e.get('target_name',''))
        if s and t and s in id2i and t in id2i: adj[s].append((t,float(e.get('weight',0.5))))
row,col,dat=[],[],[]
for sk,ns in adj.items():
    if sk in id2i:
        for tk,w in ns:
            if tk in id2i: row.append(id2i[sk]); col.append(id2i[tk]); dat.append(w)
W = csr_matrix((dat,(row,col)),shape=(n,n))
Lmat = csr_matrix(W.T,shape=(n,n)); cs_arr = np.array(Lmat.sum(axis=1)).flatten()
Lmat = Lmat - diags(cs_arr,0,shape=(n,n))
idx2kid = {v:k for k,v in id2i.items()}

# ═══ 共用物理 ═══
def run_sim(sched, alpha, beta_est, gamma, eta, seed_off):
    """统一底盘 K，调度器各自有估计器"""
    K = np.zeros(n)
    if sched=='greedy': u = np.zeros(n)
    if sched=='field': u = np.zeros(n)
    if sched=='fsrs': S = np.ones(n)*1.5; last = np.full(n,-1.0)
    covered = set(random.Random(seed_off).sample(list(range(n)), max(10,int(n*0.5))))
    np.random.seed((seed_off)%(2**31)); random.seed((seed_off)%(2**31))
    for day in range(N_DAYS):
        if random.random()>0.85:  # skip
            K*=(1-alpha-0.005); K=np.clip(K,0,1)
            if sched=='field': u+=(-alpha*u+beta_est*Lmat.dot(u)); u=np.clip(u,0,1)
            continue
        for _ in range(6):
            eligible=list(covered)
            if not eligible: continue
            # ── 选题 ──
            if sched=='greedy':
                scores=[max(0.001,1-u[i]) for i in eligible]
            elif sched=='field':
                scores=[max(0.001,1-u[i]) for i in eligible]  # u 含扩散
            else:  # fsrs
                scores=[]
                for i in eligible:
                    if last[i]<0: scores.append(3.0)
                    else:
                        el=max(0.1,day-last[i] if last[i]>=0 else 99)
                        R=math.exp(-((el/max(S[i],0.01))**1.2)); scores.append(1-R)
            top=sorted(zip(eligible,scores),key=lambda x:-x[1])[:BUDGET]
            # ── 执行（共享底盘）──
            for i,_ in top:
                K[i]+=gamma*(1-K[i])
                ki=idx2kid.get(i)
                if ki:
                    for tk,w in adj.get(ki,[]):
                        ti=id2i.get(tk)
                        if ti is not None: K[ti]+=eta*w*(1-K[ti])
                K=np.clip(K,0,1)
                # ── 更新估计器 ──
                if sched=='greedy': u[i]=K[i]  # 完美感知自己，看不到邻居
                if sched=='field': u[i]+=gamma*(1-u[i])  # 追踪自己
                if sched=='fsrs':
                    r=int(max(1,min(4,K[i]*5-1)))
                    So=S[i]; S[i]=max(1,min(365,(2.5+0.5*(r-2)) if So<=1.5 else So*(1+0.15*(0.5+0.25*r))))
                    last[i]=day
        K*=(1-alpha-0.005); K=np.clip(K,0,1)
        if sched=='field': u+=(-alpha*u+beta_est*Lmat.dot(u)); u=np.clip(u,0,1)
    return float(np.mean([K[i] for i in covered]))

print(f'n={n} edges={W.nnz} sweep={len(ALPHAS)*len(BETAS)*len(GAMMAS)*len(ETAS)} combos')
t0=time.time()
results=[]
for alpha in ALPHAS:
    for beta_est in BETAS:
        for gamma in GAMMAS:
            for eta in ETAS:
                vals={'alpha':alpha,'beta_est':beta_est,'gamma':gamma,'eta':eta}
                for sched in ['greedy','field','fsrs']:
                    items=[run_sim(sched,alpha,beta_est,gamma,eta,1000+i) for i in range(N_STUDENTS)]
                    vals[sched]=np.mean(items); vals[f'{sched}_std']=np.std(items)
                vals['delta_f']=vals['field']-vals['greedy']
                vals['delta_fsrs']=vals['fsrs']-vals['greedy']
                results.append(vals)
                d=vals['delta_f']; fs=vals['delta_fsrs']
                star='⭐' if d>0.05 else ('+' if d>0.02 else '')
                print(f"α={alpha:.3f} β={beta_est:.3f} γ={gamma:.1f} η={eta:.2f} "
                      f"F={vals['field']:.4f} G={vals['greedy']:.4f} FS={vals['fsrs']:.4f} "
                      f"ΔF={d:+.4f}{star} ΔFS={fs:+.4f}", flush=True)

# ═══ 最佳 ═══
best_field = max(results, key=lambda r: r['delta_f'])
best_fsrs  = max(results, key=lambda r: r['delta_fsrs'])
print(f"\nBest Field: α={best_field['alpha']:.3f} β={best_field['beta_est']:.3f} γ={best_field['gamma']:.1f} η={best_field['eta']:.2f} "
      f"Δ={best_field['delta_f']:+.4f} F={best_field['field']:.4f} G={best_field['greedy']:.4f} FS={best_field['fsrs']:.4f}")
print(f"Best FSRS:  α={best_fsrs['alpha']:.3f} γ={best_fsrs['gamma']:.1f} η={best_fsrs['eta']:.2f} "
      f"Δ={best_fsrs['delta_fsrs']:+.4f}")
print(f"Total: {time.time()-t0:.0f}s")
