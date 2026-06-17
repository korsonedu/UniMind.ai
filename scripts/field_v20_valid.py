#!/usr/bin/env python3
"""
Field v20 验证：消融 + 扫参 + 跨学科

1. 消融：权重=0→Field 是否退化为 FSRS
2. 扫参：权重 [0.1, 0.2, 0.3, 0.5, 0.7, 1.0]
3. 跨学科：CFA 和 高中数学
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
NEW_ATTRACTION = 1.2

WEIGHTS = [0.0, 0.1, 0.2, 0.3, 0.5, 0.7, 1.0]
TREES = {
    'cfa': ('cfa_tree.json', 'cfa_llm_edges.json'),
    'math': ('math_tree.json', 'math_llm_edges.json'),
}


def load_graph(tree_file, edge_file):
    with open(tree_file) as f:
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
    with open(edge_file) as f:
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

    # prerequisite graph
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
    topo_list = []
    while q_dag:
        i = q_dag.popleft()
        topo_list.append(i)
        for j in dependents[i]:
            indeg_arr[j] -= 1
            if indeg_arr[j] == 0:
                q_dag.append(j)
    for i in set(range(n)) - set(topo_list):
        for p in list(prereqs[i]):
            dependents[p].remove(i)
        prereqs[i].clear()

    descendant_count = np.zeros(n, dtype=int)
    for i in reversed(topo_list):
        count = 0
        for child in dependents[i]:
            count += 1 + descendant_count[child]
        descendant_count[i] = count

    n_roots = sum(1 for i in range(n) if not prereqs[i])
    n_desc = sum(1 for i in range(n) if descendant_count[i] > 0)

    return n, neighbors, prereqs, dependents, descendant_count, topo_list, n_roots, n_desc


def is_available(i, learned, K, prereqs):
    if not prereqs[i]:
        return True
    for p in prereqs[i]:
        if not learned[p] or K[p] < UNLOCK_PREREQ_THRESHOLD:
            return False
    return True


def count_debt(learned, K, n):
    return sum(1 for i in range(n) if learned[i] and K[i] < DANGER_THRESHOLD)


def urgency(K_val):
    if K_val <= 0.01:
        return 10.0
    return (1.0 - K_val) / K_val


def run_sim(sched, weight, n, neighbors, prereqs, descendant_count, seed):
    K = np.zeros(n)
    u = np.zeros(n)
    learned = np.zeros(n, dtype=bool)

    np.random.seed(seed % (2**31))
    random.seed(seed % (2**31))

    cumul = 0.0
    cumul_days = 0
    can_learn_new = True

    for day in range(N_DAYS):
        K *= (1 - ALPHA - BASE_DECAY)
        K += np.random.normal(0, DAY_NOISE, n)
        K = np.clip(K, 0, 1)

        if random.random() > 0.85:
            continue

        debt = count_debt(learned, K, n)
        if can_learn_new and debt >= MAX_REVIEW_DEBT:
            can_learn_new = False
        elif not can_learn_new and debt <= MAX_REVIEW_DEBT // 2:
            can_learn_new = True

        eligible = []
        for i in range(n):
            if learned[i]:
                eligible.append(i)
            elif can_learn_new and is_available(i, learned, K, prereqs):
                eligible.append(i)

        if not eligible:
            continue

        if sched == 'field':
            scores = []
            for i in eligible:
                if not learned[i]:
                    scores.append(NEW_ATTRACTION * (1.0 + weight * descendant_count[i]))
                else:
                    scores.append(urgency(u[i]) * (1.0 + weight * descendant_count[i]))
        else:
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
    n_learned = len(learned_list)
    n_mastered = sum(1 for i in learned_list if K[i] > 0.5)
    n_deep = sum(1 for i in learned_list if K[i] > 0.65)

    return {
        'n_learned': n_learned,
        'n_mastered': n_mastered,
        'n_deep': n_deep,
        'final_mastery': float(np.mean([K[i] for i in learned_list])) if learned_list else 0.0,
        'avg_cumul': cumul / max(1, cumul_days),
    }


def run_sweep(name, tree_file, edge_file):
    n, neighbors, prereqs, dependents, descendant_count, topo_list, n_roots, n_desc = load_graph(tree_file, edge_file)
    print(f"\n{'='*60}")
    print(f"[{name}] n={n} roots={n_roots} with_desc={n_desc} max_desc={descendant_count.max()}")
    print(f"{'='*60}")

    # 先跑 FSRS baseline
    fsrs_res = defaultdict(list)
    for i in range(N_STUDENTS):
        r = run_sim('fsrs', 0, n, neighbors, prereqs, descendant_count, 10000 + i)
        for k, v in r.items():
            fsrs_res[k].append(v)
    fsrs = {k: np.mean(v) for k, v in fsrs_res.items()}
    print(f"  FSRS: mastered={fsrs['n_mastered']:.0f}  deep={fsrs['n_deep']:.0f}  learned={fsrs['n_learned']:.0f}/{n}")
    print(f"  weights: ", end='', flush=True)

    best_w = None
    best_mastered = fsrs['n_mastered']
    best_deep = fsrs['n_deep']
    results = {}

    for w in WEIGHTS:
        field_res = defaultdict(list)
        for i in range(N_STUDENTS):
            r = run_sim('field', w, n, neighbors, prereqs, descendant_count, 10000 + i)
            for k, v in r.items():
                field_res[k].append(v)
        agg = {k: np.mean(v) for k, v in field_res.items()}
        delta = (agg['n_mastered'] - fsrs['n_mastered']) / fsrs['n_mastered'] * 100
        star = '⭐' if agg['n_mastered'] > fsrs['n_mastered'] else '-'
        print(f"{w:.1f}:{agg['n_mastered']:.0f}({delta:+.0f}%){star} ", end='', flush=True)
        results[w] = agg
        if agg['n_mastered'] > best_mastered:
            best_mastered = agg['n_mastered']
            best_deep = agg['n_deep']
            best_w = w

    print(f"\n  best w={best_w:.1f}: mastered={best_mastered:.0f} ({((best_mastered/fsrs['n_mastered'])-1)*100:+.0f}%)  deep={best_deep:.0f}")
    return fsrs, results, best_w


t0 = time.time()
all_results = {}
for name, (tree_file, edge_file) in TREES.items():
    fsrs, results, best_w = run_sweep(name, tree_file, edge_file)
    all_results[name] = (fsrs, results, best_w)

print(f"\n{'='*60}")
print("SUMMARY")
print(f"{'='*60}")
for name in TREES:
    fsrs, results, best_w = all_results[name]
    field_best = results[best_w]
    print(f"\n[{name}] best w={best_w:.1f}")
    print(f"  FSRS:  mastered={fsrs['n_mastered']:.0f}  deep={fsrs['n_deep']:.0f}  learned={fsrs['n_learned']:.0f}  final_K={fsrs['final_mastery']:.4f}")
    print(f"  Field: mastered={field_best['n_mastered']:.0f}  deep={field_best['n_deep']:.0f}  learned={field_best['n_learned']:.0f}  final_K={field_best['final_mastery']:.4f}")
    for metric in ['n_mastered', 'n_deep', 'n_learned', 'final_mastery']:
        fv = field_best[metric]
        sv = fsrs[metric]
        if sv > 0:
            print(f"    {metric:>16s}: Δ={(fv/sv-1)*100:+.1f}%")

print(f"\nTotal: {time.time()-t0:.0f}s")
