#!/usr/bin/env python3
"""
诊断：数学树上 20x 差距的真正原因
对比：FSRS(new=2.5) vs FSRS(new=1.2) vs Field(w=0, new=1.2) vs Field(w=0.3, new=1.2)
隔离：图权重贡献 vs 保守学新贡献
"""
import json, math, time, random, numpy as np
from collections import defaultdict, deque
from scipy.sparse import csr_matrix

ALPHA   = 0.015
GAMMA   = 0.3
ETA     = 0.05
N_STUDENTS = 500
N_DAYS = 150
DAILY_BUDGET = 8
INIT_K = 0.25
UNLOCK_PREREQ_THRESHOLD = 0.45
DANGER_THRESHOLD = 0.30
MAX_REVIEW_DEBT = 8
EXAM_INTERVAL = 20
EXAM_COVERAGE = 0.3
BASE_DECAY = 0.005
DAY_NOISE = 0.01

# ═══ 加载数学图 ═══
with open('math_tree.json') as f:
    data = json.load(f)
nodes = data['nodes']
kps = [n for n in nodes if n.get('level') == 'kp']
n2id = {nd['name']: nd['id'] for nd in kps}
kp_ids = [n['id'] for n in kps]
id2i = {kid: i for i, kid in enumerate(kp_ids)}
n = len(kps)

adj = defaultdict(list)
for nd in nodes:
    pid = nd.get('parent_id')
    if pid and nd['id'] in id2i and pid in id2i:
        adj[nd['id']].append((pid, 0.8))
        adj[pid].append((nd['id'], 0.8))
cbp = defaultdict(list)
for nd in nodes:
    pid = nd.get('parent_id')
    if pid and nd['id'] in id2i:
        cbp[pid].append(nd['id'])
for s in cbp.values():
    for i in range(len(s)):
        for j in range(i+1, len(s)):
            adj[s[i]].append((s[j], 0.3))
            adj[s[j]].append((s[i], 0.3))
with open('math_llm_edges.json') as f:
    llm = json.load(f)
for e in llm:
    s = n2id.get(e.get('source_name', ''))
    t = n2id.get(e.get('target_name', ''))
    if s and t and s in id2i and t in id2i:
        adj[s].append((t, float(e.get('weight', 0.5))))

row, col, dat = [], [], []
for sk, ns in adj.items():
    if sk in id2i:
        for tk, w in ns:
            if tk in id2i:
                row.append(id2i[sk]); col.append(id2i[tk]); dat.append(w)
W = csr_matrix((dat, (row, col)), shape=(n, n))
neighbors = {}
for i in range(n):
    nb = []
    for j in range(n):
        w = W[i,j]
        if w > 0: nb.append((j,w))
    neighbors[i] = nb

pair_dir = {}
for e in llm:
    if e.get('edge_type') != 'prerequisite': continue
    s = n2id.get(e.get('source_name',''))
    t = n2id.get(e.get('target_name',''))
    if not (s and t and s in id2i and t in id2i): continue
    si, ti = id2i[s], id2i[t]
    w = float(e.get('weight', 0.5))
    pair = tuple(sorted([si,ti]))
    if pair not in pair_dir or w > pair_dir[pair][0]:
        pair_dir[pair] = (w, (si,ti))

prereqs = defaultdict(list)
dependents = defaultdict(list)
for (a,b), (w,(src,dst)) in pair_dir.items():
    prereqs[dst].append(src); dependents[src].append(dst)

indeg_arr = np.zeros(n)
for i in prereqs: indeg_arr[i] = len(prereqs[i])
q_dag = deque([i for i in range(n) if indeg_arr[i]==0])
topo = []
while q_dag:
    i = q_dag.popleft(); topo.append(i)
    for j in dependents[i]:
        indeg_arr[j] -= 1
        if indeg_arr[j]==0: q_dag.append(j)
for i in set(range(n)) - set(topo):
    for p in list(prereqs[i]): dependents[p].remove(i)
    prereqs[i].clear()

descendant_count = np.zeros(n, dtype=int)
for i in reversed(topo):
    cnt = 0
    for child in dependents[i]: cnt += 1 + descendant_count[child]
    descendant_count[i] = cnt

n_roots = sum(1 for i in range(n) if not prereqs[i])
print(f'n={n} roots={n_roots} max_desc={descendant_count.max()}')


def is_available(i, learned, K):
    if not prereqs[i]: return True
    for p in prereqs[i]:
        if not learned[p] or K[p] < UNLOCK_PREREQ_THRESHOLD: return False
    return True

def count_debt(learned, K):
    return sum(1 for i in range(n) if learned[i] and K[i] < DANGER_THRESHOLD)

def urgency(K_val):
    if K_val <= 0.01: return 10.0
    return (1.0 - K_val)/K_val


def run_sim(label, new_attraction, use_descendant, desc_weight, seed):
    """label: 'FSRS-2.5', 'FSRS-1.2', 'Field-0', 'Field-0.3'"""
    is_field = label.startswith('Field')
    K = np.zeros(n); u = np.zeros(n)
    learned = np.zeros(n, dtype=bool)

    np.random.seed(seed % (2**31))
    random.seed(seed % (2**31))
    cumul = 0.0; cumul_days = 0
    can_learn_new = True
    new_learned_per_day = []
    review_per_day = []

    for day in range(N_DAYS):
        K *= (1 - ALPHA - BASE_DECAY)
        K += np.random.normal(0, DAY_NOISE, n)
        K = np.clip(K, 0, 1)
        if random.random() > 0.85: continue

        debt = count_debt(learned, K)
        if can_learn_new and debt >= MAX_REVIEW_DEBT:
            can_learn_new = False
        elif not can_learn_new and debt <= MAX_REVIEW_DEBT//2:
            can_learn_new = True

        eligible = []
        for i in range(n):
            if learned[i]: eligible.append(i)
            elif can_learn_new and is_available(i, learned, K): eligible.append(i)
        if not eligible: continue

        scores = []
        for i in eligible:
            if not learned[i]:
                s = new_attraction
                if use_descendant: s *= (1.0 + desc_weight * descendant_count[i])
                scores.append(s)
            else:
                s = urgency(u[i] if is_field else K[i])
                if use_descendant: s *= (1.0 + desc_weight * descendant_count[i])
                scores.append(s)
        top = sorted(zip(eligible,scores), key=lambda x:-x[1])[:DAILY_BUDGET]

        nl, rv = 0, 0
        for i,_ in top:
            if not learned[i]:
                learned[i] = True; K[i] = INIT_K; u[i] = INIT_K; nl += 1
            else:
                rv += 1
            K[i] += GAMMA*(1-K[i])
            for j,w in neighbors[i]: K[j] += ETA*w*K[i]*(1-K[j])
            K = np.clip(K,0,1); u[i] = K[i]
        new_learned_per_day.append(nl); review_per_day.append(rv)

        if day>0 and day%EXAM_INTERVAL==0:
            testable = [i for i in range(n) if learned[i]]
            if testable:
                n_test = max(3,int(len(testable)*EXAM_COVERAGE))
                tested = random.sample(testable, min(n_test, len(testable)))
                for i in tested:
                    if random.random()<K[i]: K[i] += 0.05*(1-K[i]); u[i]=K[i]
                    K = np.clip(K,0,1)

        ll = [i for i in range(n) if learned[i]]
        if ll: cumul += float(np.mean([K[i] for i in ll])); cumul_days += 1

    learned_list = [i for i in range(n) if learned[i]]
    return {
        'n_learned': len(learned_list),
        'n_mastered': sum(1 for i in learned_list if K[i]>0.5),
        'n_deep': sum(1 for i in learned_list if K[i]>0.65),
        'final_mastery': float(np.mean([K[i] for i in learned_list])) if learned_list else 0.0,
        'avg_new_per_day': np.mean(new_learned_per_day),
        'avg_review_per_day': np.mean(review_per_day),
    }


# 4 组对比
configs = [
    ('FSRS-2.5',   2.5, False, 0.0),
    ('FSRS-1.2',   1.2, False, 0.0),
    ('Field-w0',   1.2, True,  0.0),
    ('Field-w0.3', 1.2, True,  0.3),
]

t0 = time.time()
for label, na, use_desc, dw in configs:
    res = defaultdict(list)
    for i in range(N_STUDENTS):
        r = run_sim(label, na, use_desc, dw, 10000+i)
        for k,v in r.items(): res[k].append(v)
    agg = {k: np.mean(v) for k,v in res.items()}
    print(f"\n{label:>12s}:")
    print(f"  mastered={agg['n_mastered']:.0f}  deep={agg['n_deep']:.0f}  learned={agg['n_learned']:.0f}/{n}")
    print(f"  final_K={agg['final_mastery']:.4f}  new/day={agg['avg_new_per_day']:.2f}  review/day={agg['avg_review_per_day']:.2f}")

print(f"\nTotal: {time.time()-t0:.0f}s")
