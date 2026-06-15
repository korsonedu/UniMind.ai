#!/usr/bin/env python3
"""Field 正确仿真：选题重排 → η 效率最大化"""
import json, math, time, random, numpy as np
from collections import defaultdict
from scipy.sparse import csr_matrix, diags

# ═══ 扫参 ═══
ALPHAS = [0.3, 0.4, 0.5, 0.6, 0.7]  # score 融合权重
GAMMAS = [0.2, 0.3]
ETAS   = [0.02, 0.05]
DECAY  = 0.02  # 固定 α=0.02（最优）
N_STUDENTS = 100
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
with open('cfa_llm_edges.json') as f:
    llm = json.load(f); n2id = {nd['name']:nd['id'] for nd in kps}
    for e in llm:
        s=n2id.get(e.get('source_name','')); t=n2id.get(e.get('target_name',''))
        if s and t and s in id2i and t in id2i: adj[s].append((t,float(e.get('weight',0.5))))
row,col,dat=[],[],[]
for sk,ns in adj.items():
    if sk in id2i:
        for tk,w in ns:
            if tk in id2i: row.append(id2i[sk]); col.append(id2i[tk]); dat.append(w)
W = csr_matrix((dat,(row,col)),shape=(n,n))
idx2kid = {v:k for k,v in id2i.items()}

# 预计算每节点的邻居列表（快速查询）
neighbors = {}
for i in range(n):
    kid = idx2kid.get(i)
    nbrs = []
    if kid:
        for tk,w in adj.get(kid,[]):
            ti = id2i.get(tk)
            if ti is not None: nbrs.append((ti,w))
    neighbors[i] = nbrs

print(f'n={n} edges={W.nnz} sweep={len(ALPHAS)*len(GAMMAS)*len(ETAS)} combos')

# ═══ 物理底盘（共享） ═══
def run_sim(sched, alpha_fusion, gamma, eta, seed_off):
    """统一底盘 K，不同的选题公式"""
    K = np.zeros(n)
    u = np.zeros(n)  # 简单追踪器
    if sched=='fsrs': S = np.ones(n)*1.5; last = np.full(n,-1.0)
    covered = set(random.Random(seed_off).sample(list(range(n)), max(10,int(n*0.5))))
    np.random.seed((seed_off)%(2**31)); random.seed((seed_off)%(2**31))
    cum_K = 0.0
    total_eta = 0.0
    eta_rounds = 0
    for day in range(N_DAYS):
        if random.random()>0.85:
            K*=(1-DECAY-0.005); K=np.clip(K,0,1)
            continue
        for _ in range(6):
            eligible=list(covered)
            if not eligible: continue

            # ── 选题公式（唯一区别） ──
            if sched=='greedy':
                scores=[1-u[i] for i in eligible]
            elif sched=='field':
                scores=[]
                for i in eligible:
                    fb = sum(w*(1-K[j]) for j,w in neighbors[i])
                    scores.append(alpha_fusion*(1-u[i]) + (1-alpha_fusion)*fb)
            else:  # fsrs
                scores=[]
                for i in eligible:
                    if last[i]<0: scores.append(3.0)
                    else:
                        el=max(0.1,day-last[i] if last[i]>=0 else 99)
                        R=math.exp(-((el/max(S[i],0.01))**1.2)); scores.append(1-R)

            top=sorted(zip(eligible,scores),key=lambda x:-x[1])[:BUDGET]

            # ── 共享物理：复习 + η ──
            for i,_ in top:
                K[i]+=gamma*(1-K[i])
                # η 转移（所有人共享）
                round_eta = 0.0
                for j,w in neighbors[i]:
                    t = eta*w*(1-K[j])
                    K[j] += t
                    round_eta += t
                total_eta += round_eta
                eta_rounds += 1
                K=np.clip(K,0,1)
                u[i]=K[i]
                if sched=='fsrs':
                    r=int(max(1,min(4,K[i]*5-1)))
                    So=S[i]; S[i]=max(1,min(365,(2.5+0.5*(r-2)) if So<=1.5 else So*(1+0.15*(0.5+0.25*r))))
                    last[i]=day

        K*=(1-DECAY-0.005); K=np.clip(K,0,1)
        cum_K += float(np.mean([K[i] for i in covered]))

    final_K = float(np.mean([K[i] for i in covered]))
    avg_eta = total_eta / max(1, eta_rounds)
    return final_K, cum_K/N_DAYS, avg_eta

t0=time.time()
results=[]
for alpha in ALPHAS:
    for gamma in GAMMAS:
        for eta in ETAS:
            vals={}
            for sched in ['greedy','field','fsrs']:
                finals, cumuls, etas_avg = [], [], []
                for i in range(N_STUDENTS):
                    f,c,e = run_sim(sched, alpha, gamma, eta, 1000+i)
                    finals.append(f); cumuls.append(c); etas_avg.append(e)
                vals[sched] = np.mean(finals)
                vals[f'{sched}_cumul'] = np.mean(cumuls)
                vals[f'{sched}_eta'] = np.mean(etas_avg)
            vals['alpha']=alpha; vals['gamma']=gamma; vals['eta']=eta
            vals['d_final']=vals['field']-vals['greedy']
            vals['d_cumul']=vals['field_cumul']-vals['greedy_cumul']
            vals['d_fsrs']=vals['fsrs']-vals['greedy']
            results.append(vals)
            d=vals['d_final']; c=vals['d_cumul']
            star='⭐' if d>0.08 else ('+' if d>0.04 else '')
            print(f"α={alpha:.1f} γ={gamma:.1f} η={eta:.2f} "
                  f"F={vals['field']:.4f} G={vals['greedy']:.4f} FS={vals['fsrs']:.4f} "
                  f"ΔF={d:+.4f}{star}  cumulΔ={c:+.4f}  "
                  f"ηF={vals['field_eta']:.4f} ηG={vals['greedy_eta']:.4f} ηFS={vals['fsrs_eta']:.4f}",
                  flush=True)

print(f"\n{'='*60}")
print("TOP 5 by final Δ")
print(f"{'='*60}")
top5_final = sorted(results, key=lambda r: r['d_final'], reverse=True)[:5]
for r in top5_final:
    print(f"α={r['alpha']:.1f} γ={r['gamma']:.1f} η={r['eta']:.2f} "
          f"F={r['field']:.4f} FS={r['fsrs']:.4f} G={r['greedy']:.4f} "
          f"ΔF={r['d_final']:+.4f} ΔFS={r['d_fsrs']:+.4f}")

print(f"\nTOP 5 by cumulative Δ")
top5_cumul = sorted(results, key=lambda r: r['d_cumul'], reverse=True)[:5]
for r in top5_cumul:
    print(f"α={r['alpha']:.1f} γ={r['gamma']:.1f} η={r['eta']:.2f} "
          f"F_c={r['field_cumul']:.4f} G_c={r['greedy_cumul']:.4f} "
          f"Δcumul={r['d_cumul']:+.4f}")

best = top5_final[0]
print(f"\nBest: α={best['alpha']:.1f} γ={best['gamma']:.1f} η={best['eta']:.2f}")
print(f"  Field final={best['field']:.4f} vs Greedy={best['greedy']:.4f} FSRS={best['fsrs']:.4f}")
print(f"  ΔField={best['d_final']:+.4f}  ΔFSRS={best['d_fsrs']:+.4f}")
print(f"  η/round: F={best['field_eta']:.4f} G={best['greedy_eta']:.4f} "
      f"FS={best['fsrs_eta']:.4f}  Δη={best['field_eta']-best['greedy_eta']:+.4f}")
print(f"Total: {time.time()-t0:.0f}s")
