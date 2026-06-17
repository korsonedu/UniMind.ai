#!/usr/bin/env python3
"""
Field v19: 聚焦链策略

策略不改 urgency——改预算分配。
Field 维护一条「当前链」：预算全部投给链上的 KP。
链满了（所有 KP mastered）→换下一条最深可用链。
非链 KP 只在 K < 0.25 时抢修（紧急维护）。

对比 FSRS：urgency 贪心 = 并行维护所有已学 KP。
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
MASTERED_THRESHOLD = 0.65   # ★ 链上 KP 的"已掌握"门槛
EMERGENCY_K = 0.25          # ★ 非链 KP 低于此才抢修
EXAM_INTERVAL = 20
EXAM_COVERAGE = 0.3
BASE_DECAY = 0.005
DAY_NOISE = 0.01

# ═══ 加载图 ═══
with open('cfa_tree.json') as f:
    data = json.load(f)
nodes = data['nodes']
kps = [n for n in nodes if n.get('level') == 'kp']
kp_ids = [n['id'] for n in kps]
id2i = {kid: i for i, kid in enumerate(kp_ids)}
n2id = {nd['name']: nd['id'] for nd in kps}
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
        for j in range(i + 1, len(s)):
            adj[s[i]].append((s[j], 0.3))
            adj[s[j]].append((s[i], 0.3))
with open('cfa_llm_edges.json') as f:
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
                row.append(id2i[sk])
                col.append(id2i[tk])
                dat.append(w)
W = csr_matrix((dat, (row, col)), shape=(n, n))

neighbors = {}
for i in range(n):
    nb = []
    for j in range(n):
        w = W[i, j]
        if w > 0:
            nb.append((j, w))
    neighbors[i] = nb

# ═══ 前置链（只用 LLM prerequisite 边）═══
pair_dir = {}
for e in llm:
    if e.get('edge_type') != 'prerequisite':
        continue
    s = n2id.get(e.get('source_name', ''))
    t = n2id.get(e.get('target_name', ''))
    if not (s and t and s in id2i and t in id2i):
        continue
    si, ti = id2i[s], id2i[t]
    w = float(e.get('weight', 0.5))
    pair = tuple(sorted([si, ti]))
    if pair not in pair_dir or w > pair_dir[pair][0]:
        pair_dir[pair] = (w, (si, ti))

prereqs = defaultdict(list)
dependents = defaultdict(list)
for (a, b), (w, (src, dst)) in pair_dir.items():
    prereqs[dst].append(src)
    dependents[src].append(dst)

indeg_arr = np.zeros(n)
for i in prereqs:
    indeg_arr[i] = len(prereqs[i])
q_dag = deque([i for i in range(n) if indeg_arr[i] == 0])
topo = []
while q_dag:
    i = q_dag.popleft()
    topo.append(i)
    for j in dependents[i]:
        indeg_arr[j] -= 1
        if indeg_arr[j] == 0:
            q_dag.append(j)
for i in set(range(n)) - set(topo):
    for p in list(prereqs[i]):
        dependents[p].remove(i)
    prereqs[i].clear()

depth_map = {}
def compute_depth(i, visited=None):
    if i in depth_map:
        return depth_map[i]
    if visited is None:
        visited = set()
    if i in visited:
        return 0
    visited.add(i)
    if not prereqs[i]:
        depth_map[i] = 1
        return 1
    d = 1 + max((compute_depth(p, visited) for p in prereqs[i]), default=0)
    depth_map[i] = d
    return d
for i in range(n):
    compute_depth(i)

max_depth = max(depth_map.values())
n_roots = sum(1 for i in range(n) if not prereqs[i])
n_with = sum(1 for i in range(n) if prereqs[i])
print(f'n={n} roots={n_roots} with_prereq={n_with} max_depth={max_depth}')
print(f'BUDGET={DAILY_BUDGET}')


def is_available(i, learned, K):
    if not prereqs[i]:
        return True
    for p in prereqs[i]:
        if not learned[p] or K[p] < UNLOCK_PREREQ_THRESHOLD:
            return False
    return True


def count_debt(learned, K):
    return sum(1 for i in range(n) if learned[i] and K[i] < DANGER_THRESHOLD)


def urgency(K_val):
    if K_val <= 0.01:
        return 10.0
    return (1.0 - K_val) / K_val


def masterable_chain_depth(learned, K):
    """返回 deepest 的未学但 available 的 KP 的前置链深度"""
    best = 0
    for i in range(n):
        if learned[i]:
            continue
        if not is_available(i, learned, K):
            continue
        best = max(best, depth_map[i])
    return best


def pick_focus_chain(learned, K):
    """
    ★ 选一个 available 未学 KP 作为链头，找最深的一个。
    返回链上所有 KP 的列表（按拓扑序），从根到最深可用 KP。
    """
    # 找所有 available 但未学的 KP 中最深的
    candidates = []
    for i in range(n):
        if not learned[i] and is_available(i, learned, K):
            candidates.append((depth_map[i], i))
    if not candidates:
        return []
    candidates.sort(key=lambda x: -x[0])
    # 取最深的，向上追溯完整链
    deepest_i = candidates[0][1]
    chain = []
    curr = deepest_i
    while True:
        chain.append(curr)
        got_parent = False
        for p in prereqs[curr]:
            if p not in chain:
                curr = p
                got_parent = True
                break
        if not got_parent:
            break
    chain.reverse()  # 根在前，深在后
    return chain


def chain_mastered(chain, K):
    """链上所有 KP 都 mastered？"""
    return all(K[i] >= MASTERED_THRESHOLD for i in chain if len(chain) > 0) if chain else True


def run_sim(sched, seed):
    K = np.zeros(n)
    u = np.zeros(n)
    learned = np.zeros(n, dtype=bool)

    np.random.seed(seed % (2**31))
    random.seed(seed % (2**31))

    cumul = 0.0
    cumul_days = 0
    can_learn_new = True
    focus_chain = []  # ★ Field 当前聚焦链

    for day in range(N_DAYS):
        K *= (1 - ALPHA - BASE_DECAY)
        K += np.random.normal(0, DAY_NOISE, n)
        K = np.clip(K, 0, 1)

        if random.random() > 0.85:
            continue

        debt = count_debt(learned, K)
        if can_learn_new and debt >= MAX_REVIEW_DEBT:
            can_learn_new = False
        elif not can_learn_new and debt <= MAX_REVIEW_DEBT // 2:
            can_learn_new = True

        # ★ Field: 维护 focus_chain
        if sched == 'field':
            if not focus_chain or chain_mastered(focus_chain, K):
                focus_chain = pick_focus_chain(learned, K)

        # ── 候选 ──
        eligible = []
        for i in range(n):
            if learned[i]:
                eligible.append(i)
            elif can_learn_new and is_available(i, learned, K):
                eligible.append(i)

        if not eligible:
            continue

        # ── 选题 ──
        if sched == 'field':
            scores = []
            for i in eligible:
                if not learned[i]:
                    # 新学：链上的优先
                    in_chain = i in focus_chain
                    scores.append(5.0 if in_chain else 0.5)
                else:
                    base = urgency(u[i])
                    # ★ 链上 KP：优先复习
                    if i in focus_chain:
                        base *= 3.0
                    # 非链 KP：仅紧急时复习
                    elif K[i] > EMERGENCY_K:
                        base *= 0.0  # 不复习非紧急 KP
                    scores.append(base)
        else:
            # FSRS: 标准 urgency 贪心
            scores = []
            for i in eligible:
                if not learned[i]:
                    scores.append(2.5)
                else:
                    scores.append(urgency(K[i]))

        top = sorted(zip(eligible, scores), key=lambda x: -x[1])[:DAILY_BUDGET]

        for i, _ in top:
            if not learned[i]:
                learned[i] = True
                K[i] = INIT_K
                u[i] = INIT_K

            K[i] += GAMMA * (1 - K[i])
            for j, w in neighbors[i]:
                K[j] += ETA * w * K[i] * (1 - K[j])
            K = np.clip(K, 0, 1)
            u[i] = K[i]

        if day > 0 and day % EXAM_INTERVAL == 0:
            testable = [i for i in range(n) if learned[i]]
            if testable:
                n_test = max(3, int(len(testable) * EXAM_COVERAGE))
                tested = random.sample(testable, min(n_test, len(testable)))
                for i in tested:
                    if random.random() < K[i]:
                        K[i] += 0.05 * (1 - K[i])
                        u[i] = K[i]
                    K = np.clip(K, 0, 1)

        learned_list = [i for i in range(n) if learned[i]]
        if learned_list:
            cumul += float(np.mean([K[i] for i in learned_list]))
            cumul_days += 1

    learned_list = [i for i in range(n) if learned[i]]
    chain_len = 0
    if learned_list:
        for i in learned_list:
            if K[i] > MASTERED_THRESHOLD:
                cl = 1
                curr = i
                visited_chain = {curr}
                while True:
                    found = False
                    for p in prereqs[curr]:
                        if p not in visited_chain and learned[p] and K[p] > MASTERED_THRESHOLD:
                            cl += 1
                            visited_chain.add(p)
                            curr = p
                            found = True
                            break
                    if not found:
                        break
                chain_len = max(chain_len, cl)

    n_learned = len(learned_list)
    n_mastered = sum(1 for i in learned_list if K[i] > 0.5)
    n_chain_mastered = sum(1 for i in learned_list if K[i] > MASTERED_THRESHOLD)
    final_mastery = float(np.mean([K[i] for i in learned_list])) if learned_list else 0.0

    return {
        'n_learned': n_learned,
        'n_mastered': n_mastered,
        'n_chain_mastered': n_chain_mastered,
        'final_mastery': final_mastery,
        'chain_len': chain_len,
        'mastered_ratio': n_chain_mastered / n,
        'composite': (n_learned / n) * final_mastery,
        'avg_cumul': cumul / max(1, cumul_days),
    }


t0 = time.time()
results = {}

for sched in ['fsrs', 'field']:
    all_res = defaultdict(list)
    for i in range(N_STUDENTS):
        r = run_sim(sched, 10000 + i)
        for k, v in r.items():
            all_res[k].append(v)

    agg = {k: (np.mean(v), np.std(v)) for k, v in all_res.items()}
    results[sched] = agg

    print(f"\n{sched:>8s}:")
    print(f"  chain_len       = {agg['chain_len'][0]:.1f}")
    print(f"  n_chain_mastered= {agg['n_chain_mastered'][0]:.0f} (K>{MASTERED_THRESHOLD})")
    print(f"  n_mastered      = {agg['n_mastered'][0]:.0f} (K>0.5)")
    print(f"  n_learned       = {agg['n_learned'][0]:.0f}/{n}")
    print(f"  final_mastery   = {agg['final_mastery'][0]:.4f}", flush=True)

print(f"\n{'='*60}")
for metric in ['chain_len', 'n_chain_mastered', 'n_mastered', 'final_mastery']:
    f_val = results['field'][metric][0]
    s_val = results['fsrs'][metric][0]
    if s_val > 0:
        print(f"  {metric:>18s}: FSRS={s_val:.1f}  Field={f_val:.1f}  Δ={(f_val/s_val-1)*100:+.1f}%")
    else:
        print(f"  {metric:>18s}: FSRS={s_val:.1f}  Field={f_val:.1f}")

print(f"Total: {time.time()-t0:.0f}s")
