#!/usr/bin/env python3
"""Field 正确仿真：固定教案 + 统一底盘 + 公平信息条件"""
import json, math, time, random, numpy as np
from collections import defaultdict
from scipy.sparse import csr_matrix
from collections import deque

# ═══ 扫参 ═══
ALPHAS  = [0.01, 0.02]         # 统一衰减率
BETAS_E = [0.0, 0.001, 0.005]  # Field u 扩散追踪（β=0 是消融）
BETAS_A = [0.5, 1.0]           # field_benefit 放大器
GAMMAS  = [0.2, 0.3]
ETAS    = [0.02, 0.05]
N_STUDENTS = 300
N_DAYS = 150
BUDGET = 6
UNLOCK_EVERY = 15              # 每 15 天解锁一批
KPS_PER_UNLOCK = 20            # 每批 20 个 KP
INIT_K = 0.3                   # 新学 KP 初始掌握度
EXAM_INTERVAL = 30             # 考试间隔
EXAM_COVERAGE = 0.3            # 考试覆盖已解锁 KP 的比例

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

# 预计算 Lmat（常数，不每天重建）
from scipy.sparse import diags
Lmat_pre = csr_matrix(W.T, shape=(n,n))
col_sum = np.array(Lmat_pre.sum(axis=1)).flatten()
Lmat_pre = Lmat_pre - diags(col_sum, 0, shape=(n,n))
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
missing = set(range(n)) - set(syllabus)
syllabus.extend(missing)  # 孤立节点放最后
# 分批
batches = [syllabus[i:i+KPS_PER_UNLOCK] for i in range(0, min(len(syllabus), n), KPS_PER_UNLOCK)]

print(f'n={n} edges={W.nnz} batches={len(batches)} '
      f'sweep={len(ALPHAS)*len(BETAS_E)*len(BETAS_A)*len(GAMMAS)*len(ETAS)} combos × {N_STUDENTS}')

# ═══ 统一底盘 ═══
def run_sim(sched, alpha, beta_e, beta_a, gamma, eta, seed):
    K = np.zeros(n)          # 真实掌握度（共享）
    u = np.zeros(n)          # Greedy/Field 估计器
    if sched=='fsrs': S = np.ones(n)*1.5; last = np.full(n,-1.0)
    np.random.seed(seed%(2**31)); random.seed(seed%(2**31))
    unlocked = set()
    cumul = 0.0; cumul_days = 0
    next_batch = 0

    for day in range(N_DAYS):
        # ── 教案解锁 ──
        if day % UNLOCK_EVERY == 0 and next_batch < len(batches):
            for i in batches[next_batch]:
                if i<n: unlocked.add(i); K[i]=INIT_K; u[i]=INIT_K
                if sched=='fsrs': last[i]=-1; S[i]=1.5
            next_batch += 1

        # ── 统一衰减（独立）──
        K *= (1 - alpha - 0.005); K = np.clip(K, 0, 1)

        # Field 的 u 演化（追踪 η 转移）
        if sched=='field' and beta_e > 0:
            u += (-alpha*u + beta_e*Lmat_pre.dot(u))
            u = np.clip(u, 0, 1)

        if random.random() > 0.85: continue  # skip day

        for _ in range(6):
            eligible = sorted(unlocked)
            if not eligible: continue

            # ── 选题（只用估计器，不用真实 K）──
            if sched=='greedy':
                scores = [1-u[i] for i in eligible]
            elif sched=='field':
                scores = []
                for i in eligible:
                    fb = sum(w*(1-u[j]) for j,w in neighbors[i]) if neighbors[i] else 0.0
                    scores.append((1-u[i]) * (1.0 + beta_a*fb))
            else:
                scores = []
                for i in eligible:
                    if last[i]<0: scores.append(3.0)
                    else:
                        el = max(0.1, day-last[i] if last[i]>=0 else 99)
                        R = math.exp(-((el/max(S[i],0.01))**1.2))
                        scores.append(1-R)
            top = sorted(zip(eligible,scores), key=lambda x:-x[1])[:BUDGET]

            # ── 共享物理：复习 + η ──
            for i,_ in top:
                K[i] += gamma*(1-K[i])
                for j,w in neighbors[i]:
                    K[j] += eta*w*K[i]*(1-K[j])
                K = np.clip(K,0,1)
                u[i] = K[i]  # 复习后更新估计器
                if sched=='fsrs':
                    r = int(max(1,min(4,K[i]*5-1)))
                    So = S[i]; S[i]=max(1,min(365,(2.5+0.5*(r-2)) if So<=1.5 else So*(1+0.15*(0.5+0.25*r))))
                    last[i]=day

        # ── 考试 ──
        if day>0 and day%EXAM_INTERVAL==0:
            testable = sorted(unlocked)
            n_test = max(3, int(len(testable)*EXAM_COVERAGE))
            tested = random.sample(testable, min(n_test, len(testable)))
            for i in tested:
                if random.random() < K[i]:
                    K[i] += 0.05*(1-K[i])
                    u[i] = K[i]
                K = np.clip(K,0,1)

        if unlocked:
            cumul += float(np.mean([K[i] for i in unlocked]))
            cumul_days += 1

    final = float(np.mean([K[i] for i in unlocked])) if unlocked else 0.0
    avg_cumul = cumul/max(1,cumul_days)
    return final, avg_cumul

t0=time.time(); results=[]
for a in ALPHAS:
    for be in BETAS_E:
        for ba in BETAS_A:
            for g in GAMMAS:
                for e in ETAS:
                    vals={}; vals['a']=a; vals['be']=be; vals['ba']=ba; vals['g']=g; vals['e']=e
                    for sched in ['greedy','field','fsrs']:
                        finals, cumuls = [], []
                        for i in range(N_STUDENTS):
                            f,c = run_sim(sched, a, be, ba, g, e, 10000+i)
                            finals.append(f); cumuls.append(c)
                        vals[f'{sched}_final']=np.mean(finals)
                        vals[f'{sched}_cumul']=np.mean(cumuls)
                    vals['dF']=vals['field_final']-vals['greedy_final']
                    vsfs=vals['field_final']-vals['fsrs_final']
                    results.append(vals)
                    star='⭐' if vsfs>0.03 else ('+' if vsfs>0 else '-')
                    print(f"α={a:.2f} βe={be:.3f} βa={ba:.1f} γ={g:.1f} η={e:.2f} "
                          f"F={vals['field_final']:.4f} G={vals['greedy_final']:.4f} FS={vals['fsrs_final']:.4f} "
                          f"vFS={vsfs:+.4f}{star}", flush=True)

top5=sorted(results,key=lambda r:r['field_final']-r['fsrs_final'],reverse=True)[:5]
print(f"\n{'='*50}\nTOP 5 vs FSRS\n{'='*50}")
for r in top5:
    print(f"α={r['a']:.2f} βe={r['be']:.3f} βa={r['ba']:.1f} γ={r['g']:.1f} η={r['e']:.2f} "
          f"F={r['field_final']:.4f} FS={r['fsrs_final']:.4f} Δ={r['field_final']-r['fsrs_final']:+.4f}")

best=top5[0]
print(f"\nBest: α={best['a']:.2f} βe={best['be']:.3f} βa={best['ba']:.1f} γ={best['g']:.1f} η={best['e']:.2f}")
print(f"  Field vs Greedy: {best['dF']*100:+.1f}%")
print(f"  Field vs FSRS:   {best['field_final']-best['fsrs_final']:+.4f}")

# 消融：βe=0 时的 Field 效果
be0 = [r for r in results if r['be']==0.0 and r['a']==best['a']]
if be0:
    be0_best = max(be0, key=lambda r:r['field_final']-r['fsrs_final'])
    print(f"  Ablation (βe=0): F={be0_best['field_final']:.4f} FS={be0_best['fsrs_final']:.4f} "
          f"Δ={be0_best['field_final']-be0_best['fsrs_final']:+.4f}")
print(f"Total: {time.time()-t0:.0f}s")
