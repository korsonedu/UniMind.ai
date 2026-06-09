#!/usr/bin/env python3
"""
Memorix Phase 0 — v2: 真实学生模型
====================================
核心改进：
  1. 前置链：知识点有依赖关系，没学父节点不能学子节点
  2. 学生类型：速成型/稳健型/突击型/困难型，认知参数差异大
  3. 覆盖率：每个学生只学知识树的一个子集（30-70%）
  4. 干扰效应：学相似概念时，兄弟节点会互相干扰
  5. 疲劳：连续复习太多题，rating 会下降
  6. 分 session：不是连续300轮，而是多个 session，中间间隔遗忘发生
  7. 真实遗忘：引入 k=0.3 的快忘群体，制造真正的 urgency 差异
"""
import json, math, time, random, os, sys
from collections import defaultdict
import numpy as np

# ═══════════════════════════════════════
# 知识树（加前置依赖）
# ═══════════════════════════════════════

def load_cfa_tree(path, heavy=False):
    with open(path) as f:
        data = json.load(f)
    nodes = data['nodes']
    id2i = {n['id']: i for i, n in enumerate(nodes)}
    n = len(nodes)

    kps = []
    kp_parents = {}
    kp_code_order = {}

    for nd in nodes:
        if nd['level'] == 'kp':
            kps.append(nd)
            if nd['parent_id']:
                kp_parents[nd['id']] = nd['parent_id']
            code = nd.get('code', '')
            parts = code.split('-')
            num = int(parts[-1]) if parts and parts[-1].isdigit() else 0
            kp_code_order[nd['id']] = num

    # Build adjacency
    adj = defaultdict(list)
    for nd in nodes:
        if nd.get('parent_id') and nd['parent_id'] in id2i:
            adj[nd['id']].append((nd['parent_id'], 0.8))
            adj[nd['parent_id']].append((nd['id'], 0.8))

    cbp = defaultdict(list)
    for nd in nodes:
        if nd.get('parent_id'):
            cbp[nd['parent_id']].append(nd['id'])
    for ch in cbp.values():
        for i in range(len(ch)):
            for j in range(i+1, len(ch)):
                adj[ch[i]].append((ch[j], 0.3))
                adj[ch[j]].append((ch[i], 0.3))

    # ── HEAVY: 随机交叉边 ──
    if heavy:
        n_cross = min(120, len(kps) // 2)
        for _ in range(n_cross):
            a = random.choice(kps)
            b = random.choice(kps)
            if a['id'] == b['id']:
                continue
            # Only add cross-edges between different SEC groups
            if kp_parents.get(a['id']) != kp_parents.get(b['id']):
                w = random.uniform(0.12, 0.25)
                adj[a['id']].append((b['id'], w))
                adj[b['id']].append((a['id'], w))

    # Prerequisites
    sec_kps = defaultdict(list)
    for nd in kps:
        sec_kps[nd['parent_id']].append(nd['id'])

    prerequisites = {}
    for sec_id, kp_list in sec_kps.items():
        sorted_kps = sorted(kp_list, key=lambda x: kp_code_order.get(x, 0))
        if heavy:
            # Heavy: only first 2 KPs as prereqs per SEC
            for i in range(2, len(sorted_kps)):
                prerequisites[sorted_kps[i]] = sorted_kps[:2]
        else:
            # Original: ALL previous KPs as prereqs
            for i in range(1, len(sorted_kps)):
                prerequisites[sorted_kps[i]] = sorted_kps[:i]

    # 全局→本地映射
    kp_indices = {nd['id']: i for i, nd in enumerate(kps)}

    # 邻居（本地索引）
    nbrs_local = {}
    for li, nd in enumerate(kps):
        neighbors = []
        for tgt_id, w in adj.get(nd['id'], []):
            if tgt_id in kp_indices:
                neighbors.append((kp_indices[tgt_id], w))
        nbrs_local[li] = neighbors

    # 前置（本地索引）
    prereq_local = {}
    for nd in kps:
        li = kp_indices[nd['id']]
        prereq_local[li] = [kp_indices[p] for p in prerequisites.get(nd['id'], []) if p in kp_indices]

    # sec_groups 转换为本地索引
    sec_groups_local = []
    for kp_ids in sec_kps.values():
        local_ids = [kp_indices[kid] for kid in kp_ids if kid in kp_indices]
        if local_ids:
            sec_groups_local.append(local_ids)

    return {
        'n_kps': len(kps),
        'nbrs': nbrs_local,
        'prereq': prereq_local,        # li → [必须掌握的本地索引]
        'sec_groups': sec_groups_local,  # 本地索引，用于分配学生覆盖范围
        'nodes': nodes,
    }


# ═══════════════════════════════════════
# 学生模型 v2
# ═══════════════════════════════════════

STUDENT_TYPES = {
    'steady':  {'lrn': 0.8,  'fgt': 1.0,  'con': 0.5,  'fatigue': 0.1,  'label': '稳健型'},
    'fast':    {'lrn': 1.2,  'fgt': 1.3,  'con': 0.7,  'fatigue': 0.15, 'label': '速成型'},
    'crammer': {'lrn': 0.9,  'fgt': 0.5,  'con': 0.4,  'fatigue': 0.3,  'label': '突击型'},
    'struggle':{'lrn': 0.4,  'fgt': 0.6,  'con': 0.3,  'fatigue': 0.25, 'label': '困难型'},
}

class StudentV2:
    def __init__(self, sid, student_type='steady', coverage=0.5):
        t = STUDENT_TYPES[student_type]
        self.sid = sid
        self.lrn = t['lrn'] + random.uniform(-0.15, 0.15)
        self.fgt = t['fgt'] + random.uniform(-0.1, 0.1)
        self.con = t['con'] + random.uniform(-0.1, 0.1)
        self.fatigue_rate = t['fatigue'] + random.uniform(-0.05, 0.05)
        self.coverage = coverage
        self.student_type = student_type

    def init(self, n_kps, prereq, sec_groups, seed):
        """初始化：只解锁学生覆盖范围内的 KP"""
        self.S = np.zeros(n_kps)
        self.last = np.full(n_kps, -1.0)
        self.D = np.ones(n_kps) * 3.0   # FSRS difficulty per KP
        self.fatigue = 0.0  # 0=精力充沛, 1=筋疲力尽
        self.session_reviews = 0
        self.total_reviews = 0

        # 选覆盖范围：随机选几个 SEC group
        rng = random.Random(seed)
        n_secs = max(1, int(len(sec_groups) * self.coverage))
        chosen_secs = rng.sample(sec_groups, n_secs)
        self.covered_kps = set()
        for sec_kp_ids in chosen_secs:
            self.covered_kps.update(sec_kp_ids)

        # 可解锁的 KP：前置已掌握
        self.unlocked = set()
        self.mastered = set()
        self._update_unlocked(prereq)

    def _update_unlocked(self, prereq):
        """重新计算当前可解锁的 KP"""
        for li in self.covered_kps:
            if li in self.mastered or li in self.unlocked:
                continue
            prereqs = prereq.get(li, [])
            if not prereqs or all(p in self.mastered for p in prereqs):
                self.unlocked.add(li)

    def R(self, ki, t):
        S = self.S[ki]
        if S <= 0 or self.last[ki] < 0:
            return 0.0
        el = max(0.0, t - self.last[ki])
        if el <= 0:
            return 1.0
        k = max(0.05, min(5.0, self.fgt))
        return float(np.exp(-((el / max(S, 0.01)) ** k)))

    def R_fsrs(self, ki, t):
        """FSRS retrievability: power-law decay"""
        S = self.S[ki]
        if S <= 0 or self.last[ki] < 0:
            return 0.0
        el = max(0.0, t - self.last[ki])
        if el <= 0:
            return 1.0
        D = max(1.0, min(10.0, self.D[ki]))
        return float(pow(1.0 + el / (9.0 * max(S, 0.01)), -D))

    def review(self, ki, t, rating):
        Sold = self.S[ki]
        if Sold <= 0:
            Snew = self.lrn * (1.0 + 0.3 * (rating - 2))
        else:
            fatigue_penalty = max(0.3, 1.0 - self.fatigue)
            gain = self.con * (0.5 + 0.25 * rating) * fatigue_penalty
            Snew = Sold * (1.0 + gain)
        self.S[ki] = max(0.1, min(365.0, Snew))
        self.last[ki] = t
        # FSRS difficulty update
        self.D[ki] = max(1.0, min(10.0, self.D[ki] - 0.2 * (rating - 3)))
        self.total_reviews += 1
        self.session_reviews += 1

        # 疲劳累积
        self.fatigue = min(1.0, self.fatigue + self.fatigue_rate * 0.05)

        # 掌握判定
        if self.S[ki] > 7 and Sold > 0:
            self.mastered.add(ki)

    def end_session(self, prereq):
        """一个 session 结束，疲劳重置，遗忘发生"""
        self.fatigue = max(0.0, self.fatigue - 0.3)  # 休息恢复
        self.session_reviews = 0
        self._update_unlocked(prereq)

    def get_rating(self, ki, t, noise=0.1):
        """模拟学生对题的评分，受疲劳和掌握度影响"""
        R_val = self.R(ki, t)
        skill = self.S[ki]

        # 基础概率
        if skill <= 0:
            # 新题：根据学习速率
            p_good = 0.3 + 0.3 * self.lrn
        elif R_val > 0.85:
            p_good = 0.9 - self.fatigue * 0.3
        elif R_val > 0.6:
            p_good = 0.7 - self.fatigue * 0.2
        elif R_val > 0.4:
            p_good = 0.5 - self.fatigue * 0.15
        else:
            p_good = 0.3 - self.fatigue * 0.1

        p_good = max(0.05, min(0.95, p_good + random.uniform(-noise, noise)))

        if p_good > 0.7:
            return 4 if random.random() < 0.3 else 3
        elif p_good > 0.5:
            return 3 if random.random() < 0.6 else 2
        elif p_good > 0.3:
            return 2 if random.random() < 0.6 else 1
        else:
            return 1


# ═══════════════════════════════════════
# 仿真核心 v2
# ═══════════════════════════════════════

def simulate_student_v2(tree, student, sched, alpha, boost, n_days, budget,
                        study_hours=8, seed=0):
    """
    基于"天"的仿真。
    
    每天：study_hours 学习窗口（复习若干次，每次间隔 min_interval ~ max_interval 小时）
         + (24 - study_hours) 睡眠窗口（时间前进，遗忘发生，无复习）
    
    n_days: 模拟多少天
    budget: 每次复习选几道题
    study_hours: 每天学习窗口的小时数（个体差异 ±2h）
    """
    np.random.seed((seed + student.sid) % (2**31))
    random.seed((seed + student.sid) % (2**31))

    n_kps = tree['n_kps']
    nbrs = tree['nbrs']
    prereq = tree['prereq']
    sec_groups = tree['sec_groups']  # 已经是本地索引

    student.init(n_kps, prereq, sec_groups, seed + student.sid)
    all_kps = list(range(n_kps))
    history = []

    # 个性化学习窗口和复习节奏
    actual_study_hours = max(4, study_hours + random.uniform(-2, 2))    # 个体差异
    sleep_hours = 24 - actual_study_hours
    # 复习间隔：5分钟到2小时不等，取决于学生的勤奋程度
    min_gap = random.uniform(0.05, 0.3)   # 最少 3-18 分钟
    max_gap = random.uniform(0.5, 2.0)    # 最多 30-120 分钟

    cur_t = 0.0     # 绝对时间（小时）
    day = 0
    snapshot_interval_hours = 24  # 每天一个 snapshot

    for day in range(n_days):
        # ═══ 学习窗口 ═══
        day_start = day * 24
        wake_t = day_start + random.uniform(0, 1)  # 醒来时间有波动
        cur_t = wake_t
        
        student.end_session(prereq)  # 睡前疲劳重置 + 解锁新 KP
        student.fatigue = random.uniform(0, 0.15)  # 醒来略带疲劳
        
        reviews_today = 0
        session_end = day_start + actual_study_hours
        
        while cur_t < session_end:
            # 每次复习间的间隔
            gap = random.uniform(min_gap, max_gap)
            cur_t += gap
            
            if cur_t >= session_end:
                break
            
            # 评分：只评可解锁的 KP
            scored = []
            for li in all_kps:
                if li not in student.unlocked and li not in student.mastered:
                    continue
                
                urg = 1.0 - student.R(li, cur_t) if student.last[li] >= 0 else 3.0
                if sched == 'fsrs':
                    urg = 1.0 - student.R_fsrs(li, cur_t) if student.last[li] >= 0 else 3.0
                    scored.append((li, urg))
                elif sched == 'field':
                    fb = sum(w * max(0.0, 1.0 - student.R(nli, cur_t))
                            for nli, w in nbrs.get(li, []))
                    scored.append((li, alpha * urg + (1 - alpha) * fb))
                else:
                    scored.append((li, urg))
            
            if len(scored) < budget:
                for li in all_kps:
                    if li in student.unlocked and li not in [s[0] for s in scored]:
                        scored.append((li, 2.0))
            
            scored.sort(key=lambda x: -x[1])
            selected = [li for li, _ in scored[:budget]]
            
            for li in selected:
                rating = student.get_rating(li, cur_t)
                student.review(li, cur_t, rating)
                
                if sched == 'field':
                    for nli, w in nbrs.get(li, []):
                        if student.S[nli] > 0:
                            boost_effect = boost * w * student.con
                            # 睡前复习效果更好（即将进入长时间睡眠巩固）
                            hours_to_sleep = session_end - cur_t
                            if hours_to_sleep < 2.0:
                                boost_effect *= 1.3  # 睡前复习 boost +30%
                            student.S[nli] *= (1.0 + boost_effect)
            
            reviews_today += len(selected)
        
        # ═══ 睡眠窗口 ═══
        sleep_start = session_end
        cur_t = sleep_start + sleep_hours  # 时间直接跳到第二天醒来
        
        # 睡眠中遗忘：对已解锁但未掌握的 KP，遗忘加速
        for li in all_kps:
            if li in student.mastered:
                continue
            if student.last[li] >= 0 and student.S[li] > 0:
                elapsed_since_review = cur_t - student.last[li]
                if elapsed_since_review > 12:
                    R_now = student.R(li, cur_t)
                    if R_now < 0.5:
                        student.S[li] *= 0.85
        
        # ═══ HEAVY: 周期性考试 ═══
        if day > 0 and day % 20 == 0:
            exam_kps = [li for li in student.covered_kps if student.last[li] >= 0]
            if len(exam_kps) > 20:
                exam_kps = random.sample(exam_kps, 20)
            # 考试：强制复习，无选择（模拟真实考试覆盖）
            for li in exam_kps:
                rating = student.get_rating(li, cur_t, noise=0.05)  # 考试更严格
                student.review(li, cur_t, rating)
                # 考试后的强化巩固（考试效应）
                student.S[li] *= 1.05
        
        # ═══ Snapshot（每天结束时）═══
        covered = [li for li in student.covered_kps if student.last[li] >= 0]
        R_vals = [student.R(li, cur_t) for li in covered]
        history.append({
            'day': day, 't': cur_t,
            'avg_R': float(np.mean(R_vals)) if R_vals else 0.0,
            'reviews': reviews_today,
        })
    
    return {
        'sid': student.sid,
        'student_type': student.student_type,
        'coverage': student.coverage,
        'scheduler': sched,
        'alpha': alpha, 'boost': boost,
        'final_R': history[-1]['avg_R'] if history else 0.0,
        'history': history,
        'total_reviews': student.total_reviews,
    }


# ═══════════════════════════════════════
# 实验运行
# ═══════════════════════════════════════

def summary(group):
    finals = [r['final_R'] for r in group]
    arr = np.array(finals)
    return {'mean': float(np.mean(arr)), 'std': float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0}

def run_experiment(tree, alphas, boosts, students_per_combo, n_days, budget):
    results = {}
    student_types = list(STUDENT_TYPES.keys())
    coverages = [0.4, 0.6, 0.8]

    total_combos = len(alphas) * len(boosts)
    combo_idx = 0

    for alpha in alphas:
        for boost in boosts:
            key = f"a{alpha:.2f}_b{boost:.2f}"
            combo_idx += 1
            t0 = time.time()

            indep_results, field_results = [], []

            for i in range(students_per_combo):
                stype = student_types[i % len(student_types)]
                cov = coverages[i % len(coverages)]
                seed_base = hash(key) + i

                s1 = StudentV2(seed_base, student_type=stype, coverage=cov)
                indep_results.append(simulate_student_v2(
                    tree, s1, 'independent', alpha, boost, n_days, budget,
                    seed=seed_base))

                s2 = StudentV2(seed_base + 10000, student_type=stype, coverage=cov)
                field_results.append(simulate_student_v2(
                    tree, s2, 'field', alpha, boost, n_days, budget,
                    seed=seed_base + 10000))

            isum = summary(indep_results)
            fsum = summary(field_results)
            d = fsum['mean'] - isum['mean']
            pct = d / isum['mean'] * 100 if isum['mean'] > 0 else 0
            dt = time.time() - t0

            print(f"  [{combo_idx}/{total_combos}] {key}  "
                  f"indep={isum['mean']:.3f}  field={fsum['mean']:.3f}  "
                  f"Δ={d:+.3f} ({pct:+.1f}%)  {dt:.0f}s")

            results[key] = {
                'alpha': alpha, 'boost': boost,
                'independent': isum,
                'field': fsum,
                'delta': d, 'delta_pct': pct,
            }

    return results


def main():  
    tree = load_cfa_tree('scripts/cfa_tree.json', heavy=True)
    print(f"CFA Tree HEAVY: {tree['n_kps']} KPs (+cross-edges, relaxed prereqs)")

    alphas = (0.95, 0.9, 0.85, 0.8, 0.7, 0.6)
    boosts = (0.01, 0.02, 0.05, 0.10, 0.15, 0.20)
    students_per_combo = 60
    n_days = 30          # 模拟 30 天（一个月）
    budget = 6

    total = len(alphas) * len(boosts) * students_per_combo * 2
    print(f"Total: {total} student-runs ({len(alphas)}α × {len(boosts)}b × {students_per_combo} pairs)")
    print()

    t0 = time.time()
    results = run_experiment(tree, alphas, boosts, students_per_combo,
                            n_days, budget)
    elapsed = time.time() - t0

    print(f"\n{'='*60}")
    print(f"Done in {elapsed:.0f}s ({elapsed/60:.1f}min)")
    print(f"{'='*60}")
    print(f"{'alpha':>6} {'boost':>6} {'indep':>8} {'field':>8} {'delta':>8}  verdict")
    print("-" * 55)
    for key in sorted(results.keys()):
        r = results[key]
        d = r['delta']
        v = "✅" if d > 0.03 else ("🟡" if d > 0.01 else ("➖" if d > -0.01 else "❌"))
        print(f"  {r['alpha']:.2f}   {r['boost']:.2f}   {r['independent']['mean']:.4f}   "
              f"{r['field']['mean']:.4f}   {d:+.4f}   {v}")

    # Save
    os.makedirs('scripts/output', exist_ok=True)
    with open('scripts/output/results_v2.json', 'w') as f:
        json.dump({'config': {'alphas': alphas, 'boosts': boosts,
                              'students': students_per_combo,
                              'n_days': n_days, 'budget': budget},
                   'results': results}, f, indent=2)
    print("\nSaved: scripts/output/results_v2.json")


if __name__ == '__main__':
    main()
