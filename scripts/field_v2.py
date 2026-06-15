#!/usr/bin/env python3
"""Field 修正测试: K_i加权η + 乘法field_benefit"""
import json, math, time, random, numpy as np
from collections import defaultdict

# ═══ 扫参 ═══
BETAS = [0.1, 0.2, 0.5, 1.0, 2.0]   # field_benefit 放大器
GAMMAS = [0.2, 0.3]
ETAS = [0.02, 0.05]
DECAY = 0.02
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
idx2kid = {v:k for k,v in id2i.items()}
neighbors = {}
for i in range(n):
    kid = idx2kid.get(i); nbrs = []
    if kid:
        for tk,w in adj.get(kid,[]):
            ti = id2i.get(tk)
            if ti is not None: nbrs.append((ti,w))
    neighbors[i] = nbrs

print(f'n={n} sweep={len(BETAS)*len(GAMMAS)*len(ETAS)} combos')

def run_sim(sched, beta_amp, gamma, eta, seed):
    K = np.zeros(n); u = np.zeros(n)
    if sched=='fsrs': S = np.ones(n)*1.5; last = np.full(n,-1.0)
    covered = set(random.Random(seed).sample(list(range(n)), max(10,int(n*0.5))))
    np.random.seed(seed%(2**31)); random.seed(seed%(2**31))
    totals = {'final': 0, 'cumul': 0.0, 'min_K': 1.0}
    for day in range(N_DAYS):
        if random.random()>0.85: K*=(1-DECAY-0.005); K=np.clip(K,0,1); continue
        for _ in range(6):
            eligible=list(covered)
            if not eligible: continue
            # ── 选题 ──
            if sched=='greedy':
                scores=[1-u[i] for i in eligible]
            elif sched=='field':
                scores=[]
                for i in eligible:
                    fb = sum(w*(1-K[j]) for j,w in neighbors[i]) if neighbors[i] else 0.0
                    scores.append((1-u[i]) * (1.0 + beta_amp * fb))
            else:
                scores=[]
                for i in eligible:
                    if last[i]<0: scores.append(3.0)
                    else:
                        el=max(0.1,day-last[i] if last[i]>=0 else 99)
                        R=math.exp(-((el/max(S[i],0.01))**1.2)); scores.append(1-R)
            top=sorted(zip(eligible,scores),key=lambda x:-x[1])[:BUDGET]
            # ── 共享物理：K_i 加权的 η ──
            for i,_ in top:
                K[i]+=gamma*(1-K[i])
                for j,w in neighbors[i]:
                    K[j]+=eta*w*K[i]*(1-K[j])  # ← K_i 加权
                K=np.clip(K,0,1); u[i]=K[i]
                if sched=='fsrs':
                    r=int(max(1,min(4,K[i]*5-1)))
                    So=S[i]; S[i]=max(1,min(365,(2.5+0.5*(r-2)) if So<=1.5 else So*(1+0.15*(0.5+0.25*r))))
                    last[i]=day
        K*=(1-DECAY-0.005); K=np.clip(K,0,1)
        cov = list(covered); kvals = [K[i] for i in cov]
        totals['cumul'] += np.mean(kvals)
    cov = list(covered); kvals = [K[i] for i in cov]
    totals['final'] = float(np.mean(kvals))
    totals['min_K'] = float(np.min(kvals))
    totals['cumul'] /= N_DAYS
    return totals

t0=time.time()
results=[]
for beta in BETAS:
    for gamma in GAMMAS:
        for eta in ETAS:
            vals={}
            for sched in ['greedy','field','fsrs']:
                finals, cumuls, mins = [], [], []
                for i in range(N_STUDENTS):
                    t = run_sim(sched, beta, gamma, eta, 10000+i)
                    finals.append(t['final']); cumuls.append(t['cumul']); mins.append(t['min_K'])
                vals[f'{sched}_final']=np.mean(finals)
                vals[f'{sched}_cumul']=np.mean(cumuls)
                vals[f'{sched}_min']=np.mean(mins)
            vals['beta']=beta; vals['gamma']=gamma; vals['eta']=eta
            vals['d_final']=vals['field_final']-vals['greedy_final']
            vals['d_fsrs']=vals['fsrs_final']-vals['greedy_final']
            results.append(vals)
            d=vals['d_final']
            star='⭐' if d>0.05 else ('+' if d>0.01 else ('-' if d>-0.01 else '✗'))
            print(f"β={beta:.1f} γ={gamma:.1f} η={eta:.2f} "
                  f"F={vals['field_final']:.4f} G={vals['greedy_final']:.4f} FS={vals['fsrs_final']:.4f} "
                  f"ΔF={d:+.4f}{star}  minF={vals['field_min']:.4f} minG={vals['greedy_min']:.4f}",
                  flush=True)

print(f"\n{'='*50}\nTOP 5 by ΔF\n{'='*50}")
top5=sorted(results,key=lambda r:r['d_final'],reverse=True)[:5]
for r in top5:
    print(f"β={r['beta']:.1f} γ={r['gamma']:.1f} η={r['eta']:.2f} "
          f"F={r['field_final']:.4f} G={r['greedy_final']:.4f} FS={r['fsrs_final']:.4f} "
          f"ΔF={r['d_final']:+.4f} ΔFS={r['d_fsrs']:+.4f}")

best=top5[0]
print(f"\nBest: β={best['beta']:.1f} γ={best['gamma']:.1f} η={best['eta']:.2f}")
print(f"  Field vs Greedy: +{best['d_final']*100:.1f}%")
print(f"  Field vs FSRS:   {best['field_final']-best['fsrs_final']:+.4f}")
print(f"  Field min_K: {best['field_min']:.4f} vs Greedy min_K: {best['greedy_min']:.4f}")
print(f"Total: {time.time()-t0:.0f}s")
