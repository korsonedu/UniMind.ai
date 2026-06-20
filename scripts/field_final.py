#!/usr/bin/env python3
"""
Field vFinal: GMRF 诊断 + FSRS 基线 + 独立学生仿真

五大基线：Naive / Elo / IRT / FSRS / Field(GMRF)
FSRS: 从复习历史独立估算每个 KP 的掌握度
Field: 从部分考试结果图推断全局
"""
import json, math, time, random, numpy as np
from collections import defaultdict, deque
from scipy.sparse import csr_matrix, diags, eye
from scipy.sparse.linalg import cg


# ═══════════════════════════════════════════════════
# Part 1: GMRF 诊断引擎
# ═══════════════════════════════════════════════════

class FieldGMRF:
    def __init__(self, tree_file, edge_file, lam=2.0):
        self.lam = lam
        with open(tree_file) as f: data = json.load(f)
        nodes = data['nodes']
        self.kps = [n for n in nodes if n.get('level') == 'kp']
        self.kp_names = [n['name'] for n in self.kps]
        self.kp_ids = [n['id'] for n in self.kps]
        self.id2i = {kid: i for i, kid in enumerate(self.kp_ids)}
        self.n = len(self.kps)
        self.n2id = {nd['name']: nd['id'] for nd in self.kps}
        self._build_graph(edge_file, nodes)
        self._build_precision()

    def _build_graph(self, edge_file, nodes):
        adj = defaultdict(list)
        for nd in nodes:
            pid = nd.get('parent_id')
            if pid and nd['id'] in self.id2i and pid in self.id2i:
                adj[nd['id']].append((pid, 0.8)); adj[pid].append((nd['id'], 0.8))
        cbp = defaultdict(list)
        for nd in nodes:
            pid = nd.get('parent_id')
            if pid and nd['id'] in self.id2i: cbp[pid].append(nd['id'])
        for s in cbp.values():
            for i in range(len(s)):
                for j in range(i+1,len(s)): adj[s[i]].append((s[j],0.3)); adj[s[j]].append((s[i],0.3))
        with open(edge_file) as f: llm = json.load(f)
        pair_seen = set()
        for e in llm:
            s=self.n2id.get(e.get('source_name','')); t=self.n2id.get(e.get('target_name',''))
            if not(s and t and s in self.id2i and t in self.id2i): continue
            si,ti=self.id2i[s],self.id2i[t]; pair=tuple(sorted([si,ti]))
            if pair in pair_seen: continue
            pair_seen.add(pair)
            w=float(e.get('weight',0.5)); adj[s].append((t,w)); adj[t].append((s,w))
        row,col,dat=[],[],[]
        for sk,ns in adj.items():
            if sk in self.id2i:
                si=self.id2i[sk]
                for tk,w in ns:
                    if tk in self.id2i: row.append(si);col.append(self.id2i[tk]);dat.append(w)
        self.A=csr_matrix((dat,(row,col)),shape=(self.n,self.n))

    def _build_precision(self):
        deg=np.array(self.A.sum(axis=1)).flatten(); deg[deg<1e-8]=1.0
        D_inv_sqrt=diags(1.0/np.sqrt(deg),0)
        L_norm=eye(self.n,format='csr')-D_inv_sqrt.dot(self.A).dot(D_inv_sqrt)
        self.Q_base=self.lam*L_norm+1e-4*eye(self.n,format='csr')

    def diagnose(self, observed_indices, observed_values, observed_precisions=None):
        if observed_precisions is None: observed_precisions=[4.0]*len(observed_indices)
        d_data=np.zeros(self.n)
        for idx,prec in zip(observed_indices,observed_precisions): d_data[idx]=prec
        D=diags(d_data,0,shape=(self.n,self.n))
        b=np.zeros(self.n)
        for idx,val,prec in zip(observed_indices,observed_values,observed_precisions): b[idx]=val*prec
        Q=self.Q_base+D
        mu,info=cg(Q,b,rtol=1e-6,maxiter=500)
        if info!=0:
            mu=np.full(self.n,0.5)
            for idx,val in zip(observed_indices,observed_values): mu[idx]=val
        return mu


# ═══════════════════════════════════════════════════
# Part 2: 学生轨迹仿真
# ═══════════════════════════════════════════════════

class StudentSimulator:
    def __init__(self, tree_file, edge_file, n_students=200, n_days=100):
        with open(tree_file) as f: data=json.load(f)
        nodes=data['nodes']
        kps=[n for n in nodes if n.get('level')=='kp']
        self.kp_ids=[n['id'] for n in kps]
        self.id2i={kid:i for i,kid in enumerate(self.kp_ids)}
        self.n2id={nd['name']:nd['id'] for nd in kps}
        self.n=len(kps); self.names=[n['name'] for n in kps]
        with open(edge_file) as f: llm=json.load(f)
        pair_dir={}
        for e in llm:
            if e.get('edge_type')!='prerequisite':continue
            s=self.n2id.get(e.get('source_name','')); t=self.n2id.get(e.get('target_name',''))
            if not(s and t and s in self.id2i and t in self.id2i):continue
            si,ti=self.id2i[s],self.id2i[t]; w=float(e.get('weight',0.5))
            pair=tuple(sorted([si,ti]))
            if pair not in pair_dir or w>pair_dir[pair][0]: pair_dir[pair]=(w,(si,ti))
        self.prereqs=defaultdict(list); self.children=defaultdict(list)
        for(a,b),(w,(src,dst)) in pair_dir.items(): self.prereqs[dst].append(src); self.children[src].append(dst)
        indeg=np.zeros(self.n)
        for i in self.prereqs: indeg[i]=len(self.prereqs[i])
        q=deque([i for i in range(self.n) if indeg[i]==0]); self.topo=[]
        while q:
            i=q.popleft();self.topo.append(i)
            for j in self.children[i]:
                indeg[j]-=1
                if indeg[j]==0:q.append(j)
        for i in set(range(self.n))-set(self.topo):
            for p in list(self.prereqs[i]):self.children[p].remove(i)
            self.prereqs[i].clear()
        self.n_students=n_students; self.n_days=n_days

    def run(self, daily_budget=5, test_interval=7, test_coverage=0.15):
        results=[]
        for s in range(self.n_students):
            seed=10000+s; np.random.seed(seed); random.seed(seed)
            K=np.zeros(self.n); learned=np.zeros(self.n,bool)
            observations=[]
            review_events=[]  # ★ [(day, kp_idx, rating_1_to_4)]

            for day in range(self.n_days):
                for i in range(self.n):
                    if not learned[i]:
                        ok=all(learned[p] and K[p]>0.3 for p in self.prereqs[i])
                        if ok: learned[i]=True; K[i]=0.2
                eligible=[i for i in range(self.n) if learned[i]]
                for i in range(self.n):
                    if not learned[i] and all(learned[p] and K[p]>0.3 for p in self.prereqs[i]):
                        eligible.append(i)
                urgencies=[]
                for i in eligible:
                    if not learned[i]: urgencies.append(2.0)
                    else: urgencies.append((1.0-K[i])/max(K[i],0.05))
                top=sorted(zip(eligible,urgencies),key=lambda x:-x[1])[:daily_budget]
                for i,_ in top:
                    was_learned=learned[i]
                    if not learned[i]: learned[i]=True; K[i]=0.2
                    K[i]+=0.25*(1-K[i]); K=np.clip(K,0,1)
                    if was_learned:
                        # ★ 记录复习事件：K→评分 1-4
                        if K[i]<0.3: rating=1
                        elif K[i]<0.6: rating=2
                        elif K[i]<0.8: rating=3
                        else: rating=4
                        review_events.append((day,i,rating))

                K*=0.985; K+=np.random.normal(0,0.01,self.n); K=np.clip(K,0,1)
                if day>0 and day%test_interval==0:
                    testable=[i for i in range(self.n) if learned[i]]
                    n_test=max(3,int(len(testable)*test_coverage))
                    tested=random.sample(testable,min(n_test,len(testable)))
                    for i in tested:
                        p_correct=1.0/(1.0+math.exp(-5*(K[i]-0.5)))
                        correct=random.random()<p_correct
                        observations.append((day,i,correct))
                        if correct: K[i]+=0.03*(1-K[i])
                        K=np.clip(K,0,1)
            results.append({'true_K':K.copy(),'observations':observations,'review_events':review_events,'n_learned':int(learned.sum())})
        return results


# ═══════════════════════════════════════════════════
# Part 3: 基线
# ═══════════════════════════════════════════════════

def baseline_naive(obs_indices, obs_values, n):
    mu=np.full(n,0.5)
    for i,v in zip(obs_indices,obs_values): mu[i]=v
    return mu

def baseline_elo(observations, n):
    ratings=np.full(n,1000.0); q_diff=1000.0; K_elo=32.0
    for day,idx,correct in observations:
        expected=1.0/(1.0+10**((q_diff-ratings[idx])/400.0))
        actual=1.0 if correct else 0.0
        ratings[idx]+=K_elo*(actual-expected)
    return 1.0/(1.0+np.exp(-(ratings-1000)/200))

def baseline_irt(observations, n):
    mu=np.full(n,0.5)
    obs_by_kp=defaultdict(list)
    for day,idx,correct in observations: obs_by_kp[idx].append(1.0 if correct else 0.0)
    for i in range(n):
        if obs_by_kp[i]: mu[i]=np.mean(obs_by_kp[i])
    return mu

def baseline_fsrs(review_events, n, n_days):
    """
    FSRS: 从复习历史估算每个 KP 的当前掌握度。

    复习评分 1-4 → 映射到 recall 概率估计。
    S(stability): 初始 1.5, 每次成功复习增加
    D(difficulty): 固定 1.2
    最终估计: P(recall) = exp(-((days_since_last/S)^D))
    """
    S = np.full(n, 1.5)
    last_day = np.full(n, -1)

    for day, idx, rating in review_events:
        if last_day[idx] >= 0:
            elapsed = max(1, day - last_day[idx])
        else:
            elapsed = 999

        # FSRS 核心更新（简化版）
        if rating >= 3:
            # 成功回忆 → 增加稳定性
            S[idx] = S[idx] * (1 + 0.2 * (rating - 2))
        else:
            # 失败 → 重置稳定性
            S[idx] = max(0.5, S[idx] * 0.5)

        S[idx] = min(365, max(0.5, S[idx]))
        last_day[idx] = day

    # 最终估计
    mu = np.full(n, 0.5)
    D = 1.2
    for i in range(n):
        if last_day[i] >= 0:
            elapsed = max(0.1, n_days - last_day[i])
            mu[i] = math.exp(-((elapsed / S[i]) ** D))
        # else: mu[i] stays 0.5 (never reviewed)

    return mu


def evaluate(tree_file, edge_file, sim_results, lam=2.0):
    engine = FieldGMRF(tree_file, edge_file, lam=lam)
    all_mae = {k: [] for k in ['naive','elo','irt','fsrs','field']}
    all_corr_field = []

    for r in sim_results:
        true_K = r['true_K']
        obs = r['observations']
        reviews = r['review_events']

        obs_dict = {}
        for day, idx, correct in obs:
            obs_dict[idx] = 0.85 if correct else 0.15
        obs_indices = list(obs_dict.keys())
        obs_values = [obs_dict[i] for i in obs_indices]

        # Naive
        all_mae['naive'].append(np.mean(np.abs(baseline_naive(obs_indices, obs_values, engine.n) - true_K)))
        # Elo
        all_mae['elo'].append(np.mean(np.abs(baseline_elo(obs, engine.n) - true_K)))
        # IRT
        all_mae['irt'].append(np.mean(np.abs(baseline_irt(obs, engine.n) - true_K)))
        # FSRS
        mu_fsrs = baseline_fsrs(reviews, engine.n, 100)
        all_mae['fsrs'].append(np.mean(np.abs(mu_fsrs - true_K)))
        # Field
        mu_field = engine.diagnose(obs_indices, obs_values)
        all_mae['field'].append(np.mean(np.abs(mu_field - true_K)))
        all_corr_field.append(np.corrcoef(mu_field, true_K)[0, 1])

    results = {k: (np.mean(v), np.std(v)) for k, v in all_mae.items()}
    results['field_corr'] = (np.mean(all_corr_field), np.std(all_corr_field))
    return results


# ═══════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════
if __name__ == '__main__':
    TREES = {'CFA': ('cfa_tree.json', 'cfa_llm_edges.json'), 'Math': ('math_tree.json', 'math_llm_edges.json')}
    print("Field vFinal: GMRF vs FSRS vs Baselines\n")

    for name, (tf, ef) in TREES.items():
        print(f"[{name}]")
        sim = StudentSimulator(tf, ef, n_students=200, n_days=100)
        sim_results = sim.run()
        avg_obs = np.mean([len(r['observations']) for r in sim_results])
        avg_rev = np.mean([len(r['review_events']) for r in sim_results])
        print(f"  Students={len(sim_results)}  avg obs={avg_obs:.0f}  avg reviews={avg_rev:.0f}")

        for lam in [0.5, 1.0, 2.0, 4.0, 8.0]:
            m = evaluate(tf, ef, sim_results, lam=lam)
            naive = m['naive'][0]; elo = m['elo'][0]; irt = m['irt'][0]
            fsrs = m['fsrs'][0]; field = m['field'][0]; corr = m['field_corr'][0]

            def pct(a,b): return (b-a)/b*100

            print(f"  λ={lam:.1f}: Field={field:.4f}(corr={corr:.3f}) | "
                  f"FSRS={fsrs:.4f}({pct(fsrs,field):+.1f}%) | "
                  f"Naive={naive:.4f}({pct(naive,field):+.1f}%) | "
                  f"Elo={elo:.4f}({pct(elo,field):+.1f}%) | "
                  f"IRT={irt:.4f}({pct(irt,field):+.1f}%)", flush=True)

    # 消融
    print("\nAblation (λ=0 → no graph):")
    for name, (tf, ef) in TREES.items():
        sim = StudentSimulator(tf, ef, n_students=200, n_days=100)
        sim_results = sim.run()
        m0 = evaluate(tf, ef, sim_results, lam=0.01)
        m2 = evaluate(tf, ef, sim_results, lam=2.0)
        print(f"  [{name}] λ≈0={m0['field'][0]:.4f}  λ=2={m2['field'][0]:.4f}  Δ={(m0['field'][0]-m2['field'][0])/m0['field'][0]*100:+.1f}%")
