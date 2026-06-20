#!/usr/bin/env python3
"""
Field v22: 风险感知 Bellman Backup

V(i) = urgency(K_i) + risk(K_i) × ETA × Σ V(child)
risk(K) = exp(-λ × max(0, K - THRESHOLD))

接近解锁门槛的守门员 KP 被天然推高优先级。
"""
import json, math, time, random, numpy as np
from collections import defaultdict, deque
from scipy.sparse import csr_matrix

ALPHA=0.015; GAMMA=0.3; ETA_CASCADE=0.05; ETA_VALUE=0.15
N_STUDENTS=500; N_DAYS=150; DAILY_BUDGET=8; INIT_K=0.25
UNLOCK_PREREQ_THRESHOLD=0.45; DANGER_THRESHOLD=0.30; MAX_REVIEW_DEBT=8
EXAM_INTERVAL=20; EXAM_COVERAGE=0.3; BASE_DECAY=0.005; DAY_NOISE=0.01
NEW_ATTRACTION=1.2; RISK_LAMBDA=8.0


def load_graph(tree_file, edge_file):
    with open(tree_file) as f: data = json.load(f)
    nodes = data['nodes']
    kps = [n for n in nodes if n.get('level')=='kp']
    kp_ids = [n['id'] for n in kps]
    id2i = {kid:i for i,kid in enumerate(kp_ids)}
    n2id = {nd['name']:nd['id'] for nd in kps}
    n = len(kps)
    adj = defaultdict(list)
    for nd in nodes:
        pid = nd.get('parent_id')
        if pid and nd['id'] in id2i and pid in id2i:
            adj[nd['id']].append((pid,0.8)); adj[pid].append((nd['id'],0.8))
    cbp = defaultdict(list)
    for nd in nodes:
        pid = nd.get('parent_id')
        if pid and nd['id'] in id2i: cbp[pid].append(nd['id'])
    for s in cbp.values():
        for i in range(len(s)):
            for j in range(i+1,len(s)): adj[s[i]].append((s[j],0.3)); adj[s[j]].append((s[i],0.3))
    with open(edge_file) as f: llm = json.load(f)
    for e in llm:
        s=n2id.get(e.get('source_name','')); t=n2id.get(e.get('target_name',''))
        if s and t and s in id2i and t in id2i: adj[s].append((t,float(e.get('weight',0.5))))
    row,col,dat=[],[],[]
    for sk,ns in adj.items():
        if sk in id2i:
            for tk,w in ns:
                if tk in id2i: row.append(id2i[sk]);col.append(id2i[tk]);dat.append(w)
    W=csr_matrix((dat,(row,col)),shape=(n,n))
    neighbors={}
    for i in range(n):
        nb=[]
        for j in range(n):
            w=W[i,j]
            if w>0:nb.append((j,w))
        neighbors[i]=nb
    pair_dir={}
    for e in llm:
        if e.get('edge_type')!='prerequisite':continue
        s=n2id.get(e.get('source_name','')); t=n2id.get(e.get('target_name',''))
        if not(s and t and s in id2i and t in id2i):continue
        si,ti=id2i[s],id2i[t]; w=float(e.get('weight',0.5))
        pair=tuple(sorted([si,ti]))
        if pair not in pair_dir or w>pair_dir[pair][0]: pair_dir[pair]=(w,(si,ti))
    prereqs=defaultdict(list); dependents=defaultdict(list)
    for(a,b),(w,(src,dst)) in pair_dir.items(): prereqs[dst].append(src); dependents[src].append(dst)
    indeg_arr=np.zeros(n)
    for i in prereqs: indeg_arr[i]=len(prereqs[i])
    q_dag=deque([i for i in range(n) if indeg_arr[i]==0]); topo=[]
    while q_dag:
        i=q_dag.popleft();topo.append(i)
        for j in dependents[i]:
            indeg_arr[j]-=1
            if indeg_arr[j]==0:q_dag.append(j)
    for i in set(range(n))-set(topo):
        for p in list(prereqs[i]):dependents[p].remove(i)
        prereqs[i].clear()
    return n,neighbors,prereqs,dependents,topo


def is_available(i,learned,K,prereqs):
    if not prereqs[i]:return True
    for p in prereqs[i]:
        if not learned[p] or K[p]<UNLOCK_PREREQ_THRESHOLD:return False
    return True

def count_debt(learned,K,n):
    return sum(1 for i in range(n) if learned[i] and K[i]<DANGER_THRESHOLD)

def urgency(K_val):
    if K_val<=0.01:return 10.0
    return (1.0-K_val)/K_val

def risk(K_val):
    """K 越接近解锁门槛，风险越高"""
    margin = K_val - UNLOCK_PREREQ_THRESHOLD
    if margin <= 0: return 1.0
    return math.exp(-RISK_LAMBDA * margin)


def bellman_values(learned,K,prereqs,dependents,topo,n):
    """
    ★ V(i) = urgency(K_i) + risk(K_i) × η × Σ V(child)
    risk(K) 让门槛边缘的守门员价值暴涨
    """
    V=np.zeros(n)
    for i in range(n):
        if learned[i]:
            V[i]=urgency(K[i])
    for i in reversed(topo):
        child_sum = 0.0
        for child in dependents[i]:
            child_sum += V[child]
        V[i] += risk(K[i]) * ETA_VALUE * child_sum
    return V


def run_sim(sched, n, neighbors, prereqs, dependents, topo, seed):
    K=np.zeros(n); u=np.zeros(n); learned=np.zeros(n,bool)
    np.random.seed(seed%(2**31)); random.seed(seed%(2**31))
    cumul=0.0; cumul_days=0; can_learn_new=True
    use_field = (sched=='field')

    for day in range(N_DAYS):
        K*=(1-ALPHA-BASE_DECAY); K+=np.random.normal(0,DAY_NOISE,n); K=np.clip(K,0,1)
        if random.random()>0.85:continue
        debt=count_debt(learned,K,n)
        if can_learn_new and debt>=MAX_REVIEW_DEBT: can_learn_new=False
        elif not can_learn_new and debt<=MAX_REVIEW_DEBT//2: can_learn_new=True

        if use_field:
            V = bellman_values(learned, K, prereqs, dependents, topo, n)

        eligible=[]
        for i in range(n):
            if learned[i]: eligible.append(i)
            elif can_learn_new and is_available(i,learned,K,prereqs): eligible.append(i)
        if not eligible: continue

        if use_field:
            scores=[NEW_ATTRACTION+ETA_VALUE*V[i] if not learned[i] else V[i] for i in eligible]
        else:
            scores=[NEW_ATTRACTION if not learned[i] else urgency(K[i]) for i in eligible]

        top=sorted(zip(eligible,scores),key=lambda x:-x[1])[:DAILY_BUDGET]
        for i,_ in top:
            if not learned[i]: learned[i]=True;K[i]=INIT_K;u[i]=INIT_K
            K[i]+=GAMMA*(1-K[i])
            for j,w in neighbors[i]: K[j]+=ETA_CASCADE*w*K[i]*(1-K[j])
            K=np.clip(K,0,1); u[i]=K[i]

        if day>0 and day%EXAM_INTERVAL==0:
            testable=[i for i in range(n) if learned[i]]
            if testable:
                n_test=max(3,int(len(testable)*EXAM_COVERAGE))
                tested=random.sample(testable,min(n_test,len(testable)))
                for i in tested:
                    if random.random()<K[i]:K[i]+=0.05*(1-K[i]);u[i]=K[i]
                    K=np.clip(K,0,1)

        ll=[i for i in range(n) if learned[i]]
        if ll: cumul+=float(np.mean([K[i] for i in ll])); cumul_days+=1

    learned_list=[i for i in range(n) if learned[i]]
    return {
        'n_learned':len(learned_list),
        'n_mastered':sum(1 for i in learned_list if K[i]>0.5),
        'n_deep':sum(1 for i in learned_list if K[i]>0.65),
        'final_mastery':float(np.mean([K[i] for i in learned_list])) if learned_list else 0.0,
    }


TREES={'cfa':('cfa_tree.json','cfa_llm_edges.json'),'math':('math_tree.json','math_llm_edges.json')}
t0=time.time()
for name,(tf,ef) in TREES.items():
    n,neighbors,prereqs,dependents,topo=load_graph(tf,ef)
    nr=sum(1 for i in range(n) if not prereqs[i]); nc=sum(1 for i in range(n) if dependents[i])
    print(f"\n{'='*60}\n[{name}] n={n} roots={nr} children={nc}")
    for sched in ['fsrs','field']:
        res=defaultdict(list)
        for i in range(N_STUDENTS):
            r=run_sim(sched,n,neighbors,prereqs,dependents,topo,10000+i)
            for k,v in r.items():res[k].append(v)
        agg={k:np.mean(v) for k,v in res.items()}
        print(f"  {sched:>6s}: mastered={agg['n_mastered']:.0f} deep={agg['n_deep']:.0f} "
              f"learned={agg['n_learned']:.0f}/{n} final_K={agg['final_mastery']:.4f}",flush=True)
print(f"\nTotal: {time.time()-t0:.0f}s")
