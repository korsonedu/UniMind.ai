#!/usr/bin/env python3
"""
Memorix REC Phase 0 — 再巩固窗口仿真验证
==========================================
对比三种 urgency 模型：
  1. standard: urgency = 1 - R(t)            （标准 Weibull）
  2. rec:      urgency = P(t) / P(t_opt)     （再巩固窗口）
  3. baseline: urgency = 1 - R(t) + 图扩散   （对照：当前生产状态）

目标：
  1. 找到 REC 的最优 τ（不应期）、k（形状参数）
  2. 确认 REC 是否优于标准 urgency
  3. 确定 τ/k 最优值与图扩散的交互效应

复用 Phase 0 的树加载和学生模型，新增 P(t) 计算。
"""

import json, math, time, random, os
from collections import defaultdict
import numpy as np

# ═══ 弹窗后端 — 必须在任何 pyplot 导入前设置 ═══
import matplotlib
matplotlib.use('TkAgg')

# ═══════════════════════════════════════
# P(t) 可塑性模型（小时版，适配仿真）
# ═══════════════════════════════════════

def plasticity_hours(t_hours, S0_days, lambda_days, k=1.2, tau_hours=1.0):
    """P(t) in hours. t_hours: 距上次复习的小时数."""
    if t_hours <= 0 or S0_days <= 0:
        return 0.0
    t_days = t_hours / 24.0
    tau_days = tau_hours / 24.0
    S_t = S0_days * (1.0 - math.exp(-t_days / tau_days))
    R_t = math.exp(-((t_days / max(lambda_days, 0.01)) ** k))
    return S_t * (1.0 - R_t)


def find_optimal_t_hours(S0_days, lambda_days, k=1.2, tau_hours=1.0):
    """黄金分割搜索 P(t) 最大值，返回 (t_opt_hours, P_max)"""
    lo = max(tau_hours, 0.01)
    hi = 10.0 * lambda_days * 24.0  # 10×λ 天→小时
    phi = (math.sqrt(5) - 1) / 2

    m1 = hi - phi * (hi - lo)
    m2 = lo + phi * (hi - lo)
    p1 = plasticity_hours(m1, S0_days, lambda_days, k, tau_hours)
    p2 = plasticity_hours(m2, S0_days, lambda_days, k, tau_hours)

    for _ in range(40):
        if p1 >= p2:
            hi = m2; m2 = m1; p2 = p1
            m1 = hi - phi * (hi - lo)
            p1 = plasticity_hours(m1, S0_days, lambda_days, k, tau_hours)
        else:
            lo = m1; m1 = m2; p1 = p2
            m2 = lo + phi * (hi - lo)
            p2 = plasticity_hours(m2, S0_days, lambda_days, k, tau_hours)

    t_opt = (lo + hi) / 2.0
    p_max = plasticity_hours(t_opt, S0_days, lambda_days, k, tau_hours)
    return t_opt, p_max


def rec_urgency(S0_days, elapsed_hours, k=1.2, tau_hours=1.0):
    """REC urgency = P(t_now) / P(t_opt)，归一化到 [0,1]"""
    if S0_days <= 0 or elapsed_hours < tau_hours:
        return 0.0  # 新题或不应期
    if S0_days > 365:
        R = math.exp(-((elapsed_hours / 24.0 / S0_days) ** k))
        return 1.0 - R  # 极稳→退化为标准

    t_opt, p_max = find_optimal_t_hours(S0_days, S0_days, k, tau_hours)
    if p_max <= 0:
        R = math.exp(-((elapsed_hours / 24.0 / S0_days) ** k))
        return 1.0 - R

    p_now = plasticity_hours(elapsed_hours, S0_days, S0_days, k, tau_hours)
    return max(0.0, min(1.0, p_now / p_max))


# ═══════════════════════════════════════
# 知识树加载（复用 Phase 0）
# ═══════════════════════════════════════

def load_cfa_tree(path, heavy=False):
    with open(path) as f:
        data = json.load(f)
    nodes = data['nodes']
    id2i = {n['id']: i for i, n in enumerate(nodes)}

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

    if heavy:
        n_cross = min(120, len(kps) // 2)
        for _ in range(n_cross):
            a = random.choice(kps)
            b = random.choice(kps)
            if a['id'] == b['id']: continue
            if kp_parents.get(a['id']) != kp_parents.get(b['id']):
                w = random.uniform(0.12, 0.25)
                adj[a['id']].append((b['id'], w))
                adj[b['id']].append((a['id'], w))

    sec_kps = defaultdict(list)
    for nd in kps:
        sec_kps[nd['parent_id']].append(nd['id'])

    prerequisites = {}
    for sec_id, kp_list in sec_kps.items():
        sorted_kps = sorted(kp_list, key=lambda x: kp_code_order.get(x, 0))
        if heavy:
            for i in range(2, len(sorted_kps)):
                prerequisites[sorted_kps[i]] = sorted_kps[:2]
        else:
            for i in range(1, len(sorted_kps)):
                prerequisites[sorted_kps[i]] = sorted_kps[:i]

    kp_indices = {nd['id']: i for i, nd in enumerate(kps)}
    nbrs_local = {}
    for li, nd in enumerate(kps):
        neighbors = []
        for tgt_id, w in adj.get(nd['id'], []):
            if tgt_id in kp_indices:
                neighbors.append((kp_indices[tgt_id], w))
        nbrs_local[li] = neighbors

    prereq_local = {}
    for nd in kps:
        li = kp_indices[nd['id']]
        prereq_local[li] = [kp_indices[p] for p in prerequisites.get(nd['id'], []) if p in kp_indices]

    sec_groups_local = []
    for kp_ids in sec_kps.values():
        local_ids = [kp_indices[kid] for kid in kp_ids if kid in kp_indices]
        if local_ids:
            sec_groups_local.append(local_ids)

    return {
        'n_kps': len(kps), 'nbrs': nbrs_local,
        'prereq': prereq_local, 'sec_groups': sec_groups_local,
    }


# ═══════════════════════════════════════
# 学生模型（复用 Phase 0）
# ═══════════════════════════════════════

STUDENT_TYPES = {
    'steady':  {'lrn': 0.8,  'fgt': 1.0,  'con': 0.5,  'fatigue': 0.1},
    'fast':    {'lrn': 1.2,  'fgt': 1.3,  'con': 0.7,  'fatigue': 0.15},
    'crammer': {'lrn': 0.9,  'fgt': 0.5,  'con': 0.4,  'fatigue': 0.3},
    'struggle':{'lrn': 0.4,  'fgt': 0.6,  'con': 0.3,  'fatigue': 0.25},
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
        self.S = np.zeros(n_kps)
        self.last = np.full(n_kps, -1.0)
        self.D = np.ones(n_kps) * 3.0
        self.fatigue = 0.0
        self.session_reviews = 0
        self.total_reviews = 0
        rng = random.Random(seed)
        n_secs = max(1, int(len(sec_groups) * self.coverage))
        chosen_secs = rng.sample(sec_groups, n_secs)
        self.covered_kps = set()
        for sec_kp_ids in chosen_secs:
            self.covered_kps.update(sec_kp_ids)
        self.unlocked = set()
        self.mastered = set()
        self._update_unlocked(prereq)

    def _update_unlocked(self, prereq):
        for li in self.covered_kps:
            if li in self.mastered or li in self.unlocked: continue
            prereqs = prereq.get(li, [])
            if not prereqs or all(p in self.mastered for p in prereqs):
                self.unlocked.add(li)

    def R(self, ki, t):
        S = self.S[ki]
        if S <= 0 or self.last[ki] < 0: return 0.0
        el = max(0.0, t - self.last[ki])
        if el <= 0: return 1.0
        k = max(0.05, min(5.0, self.fgt))
        return float(np.exp(-((el / max(S * 24, 0.01)) ** k)))

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
        self.total_reviews += 1
        self.session_reviews += 1
        self.fatigue = min(1.0, self.fatigue + self.fatigue_rate * 0.05)
        if self.S[ki] > 7 and Sold > 0:
            self.mastered.add(ki)

    def end_session(self, prereq):
        self.fatigue = max(0.0, self.fatigue - 0.3)
        self.session_reviews = 0
        self._update_unlocked(prereq)

    def get_rating(self, ki, t, noise=0.1):
        R_val = self.R(ki, t)
        skill = self.S[ki]
        if skill <= 0:
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
        if p_good > 0.7: return 4 if random.random() < 0.3 else 3
        elif p_good > 0.5: return 3 if random.random() < 0.6 else 2
        elif p_good > 0.3: return 2 if random.random() < 0.6 else 1
        else: return 1


# ═══════════════════════════════════════
# 仿真核心（新增 rec 调度器）
# ═══════════════════════════════════════

def simulate_student(tree, student, sched, alpha, n_days, budget,
                     study_hours=8, seed=0, rec_tau=1.0, rec_k=1.2):
    np.random.seed((seed + student.sid) % (2**31))
    random.seed((seed + student.sid) % (2**31))

    n_kps = tree['n_kps']
    nbrs = tree['nbrs']
    prereq = tree['prereq']
    sec_groups = tree['sec_groups']

    student.init(n_kps, prereq, sec_groups, seed + student.sid)
    all_kps = list(range(n_kps))
    history = []

    actual_study_hours = max(4, study_hours + random.uniform(-2, 2))
    sleep_hours = 24 - actual_study_hours
    min_gap = random.uniform(0.05, 0.3)
    max_gap = random.uniform(0.5, 2.0)
    cur_t = 0.0

    for day in range(n_days):
        day_start = day * 24
        cur_t = day_start + random.uniform(0, 1)
        student.end_session(prereq)
        student.fatigue = random.uniform(0, 0.15)
        session_end = day_start + actual_study_hours

        while cur_t < session_end:
            gap = random.uniform(min_gap, max_gap)
            cur_t += gap
            if cur_t >= session_end: break

            scored = []
            for li in all_kps:
                if li not in student.unlocked and li not in student.mastered:
                    continue

                elapsed_h = cur_t - student.last[li] if student.last[li] >= 0 else 999
                S0 = student.S[li]

                if sched == 'rec':
                    urg = rec_urgency(S0, elapsed_h, k=rec_k, tau_hours=rec_tau) if S0 > 0 else 1.0
                elif sched == 'field' and rec_tau > 0:
                    # REC+Field combo: REC urgency with graph diffusion
                    urg = rec_urgency(S0, elapsed_h, k=rec_k, tau_hours=rec_tau) if S0 > 0 else 1.0
                else:
                    urg = 1.0 - student.R(li, cur_t) if student.last[li] >= 0 else 3.0

                if sched == 'field':
                    fb = sum(w * max(0.0, 1.0 - student.R(nli, cur_t))
                             for nli, w in nbrs.get(li, []))
                    urg = alpha * urg + (1 - alpha) * fb

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

        cur_t = session_end + sleep_hours

        covered = [li for li in student.covered_kps if student.last[li] >= 0]
        R_vals = [student.R(li, cur_t) for li in covered]
        history.append({
            'day': day, 't': cur_t,
            'avg_R': float(np.mean(R_vals)) if R_vals else 0.0,
        })

    return {
        'sid': student.sid, 'student_type': student.student_type,
        'scheduler': sched,
        'final_R': history[-1]['avg_R'] if history else 0.0,
        'history': history, 'total_reviews': student.total_reviews,
    }


# ═══════════════════════════════════════
# 实验运行
# ═══════════════════════════════════════

def summary(arr):
    """返回 mean, std, 95% CI"""
    a = np.array(arr)
    n = len(a)
    m = float(np.mean(a))
    s = float(np.std(a, ddof=1)) if n > 1 else 0.0
    ci = 1.96 * s / np.sqrt(n) if n > 1 else 0.0
    return {'mean': m, 'std': s, 'ci95': ci, 'n': n}


def paired_test(group_a, group_b):
    """配对 t 检验 + Cohen's d"""
    a = np.array(group_a)
    b = np.array(group_b)
    n = len(a)
    diffs = b - a
    mean_diff = float(np.mean(diffs))
    se_diff = float(np.std(diffs, ddof=1)) / np.sqrt(n) if n > 1 else 0
    t = mean_diff / se_diff if se_diff > 0 else 0
    # Cohen's d
    pooled_sd = np.sqrt((np.var(a, ddof=1) + np.var(b, ddof=1)) / 2)
    d = mean_diff / pooled_sd if pooled_sd > 0 else 0
    # 简易 p 值（正态近似）
    from math import erfc
    p = float(erfc(abs(t) / np.sqrt(2)))
    return {'mean_diff': mean_diff, 't': t, 'p': p, 'cohens_d': d, 'n': n}


def run_experiment(tree, tau_k_grid, students_per, n_days, budget, rounds=2):
    """
    两轮独立运行，验证可复现性。
    每轮 400 学生 × 每个 combo，标准+Field 对照。
    """
    # extract unique values from grid
    tau_values = sorted(set(t for t, _ in tau_k_grid))
    k_values = sorted(set(k for _, k in tau_k_grid))
    all_rounds = []
    student_types = list(STUDENT_TYPES.keys())
    coverages = [0.4, 0.6, 0.8]

    for rnd in range(rounds):
        print(f"\n{'='*50}")
        print(f"ROUND {rnd+1}/{rounds}")
        print(f"{'='*50}")
        results = {}
        seed_offset = rnd * 100000

        # Baseline
        print("Baseline: standard ...", end=' ', flush=True)
        t0 = time.time()
        std_r = []
        for i in range(students_per):
            st = student_types[i % len(student_types)]
            cv = coverages[i % len(coverages)]
            s = StudentV2(seed_offset + i, student_type=st, coverage=cv)
            std_r.append(simulate_student(tree, s, 'standard', 0.60, n_days, budget, seed=seed_offset + i))
        results['standard'] = std_r
        print(f"R={summary([r['final_R'] for r in std_r])['mean']:.4f} ({time.time()-t0:.0f}s)")

        print("Baseline: field (α=0.60) ...", end=' ', flush=True)
        t0 = time.time()
        fld_r = []
        for i in range(students_per):
            st = student_types[i % len(student_types)]
            cv = coverages[i % len(coverages)]
            s = StudentV2(seed_offset + 50000 + i, student_type=st, coverage=cv)
            fld_r.append(simulate_student(tree, s, 'field', 0.60, n_days, budget, seed=seed_offset + 50000 + i))
        results['field_a0.60'] = fld_r
        print(f"R={summary([r['final_R'] for r in fld_r])['mean']:.4f} ({time.time()-t0:.0f}s)")

        # REC grid
        total = len(tau_k_grid)
        for idx, (tau, k) in enumerate(tau_k_grid):
            key = f"rec_t{tau:.1f}_k{k:.1f}"
            print(f"[{idx+1}/{total}] {key} ...", end=' ', flush=True)
            t0 = time.time()
            rec_r = []
            for i in range(students_per):
                st = student_types[i % len(student_types)]
                cv = coverages[i % len(coverages)]
                s = StudentV2(seed_offset + 200000 + idx*students_per + i, student_type=st, coverage=cv)
                rec_r.append(simulate_student(
                    tree, s, 'rec', 0.60, n_days, budget,
                    seed=seed_offset + 200000 + idx*students_per + i,
                    rec_tau=tau, rec_k=k))
            results[key] = rec_r
            dt = time.time() - t0
            s = summary([r['final_R'] for r in rec_r])
            print(f"R={s['mean']:.4f} ± {s['ci95']:.4f} ({dt:.0f}s)")

            # live dashboard update
            _live_dashboard(results, tau_values, k_values,
                           rnd+1, idx+1, total)

        all_rounds.append(results)

    # ── 合并两轮，验证稳定性 ──
    final = {}
    round1, round2 = all_rounds

    # 标准+Field：合并两轮数据
    final['standard'] = summary([r['final_R'] for r in round1['standard'] + round2['standard']])
    final['field_a0.60'] = summary([r['final_R'] for r in round1['field_a0.60'] + round2['field_a0.60']])

    # REC：每个 combo 合并两轮
    for tau, k in tau_k_grid:
        key = f"rec_t{tau:.1f}_k{k:.1f}"
        all_r = round1[key] + round2[key]
        final[key] = summary([r['final_R'] for r in all_r])
        # 可复现性：两轮各自 mean 的差异
        r1m = summary([r['final_R'] for r in round1[key]])['mean']
        r2m = summary([r['final_R'] for r in round2[key]])['mean']
        final[f"{key}_round_delta"] = abs(r1m - r2m)

    # 找最优，跑 REC+Field combo
    rec_only = [(k, v) for k, v in final.items() if k.startswith('rec_t')]
    rec_only.sort(key=lambda x: -x[1]['mean'])
    best_key = rec_only[0][0]
    best_tau = float(best_key.split('_')[1][1:])
    best_k = float(best_key.split('_')[2][1:])

    print(f"\nBest REC: {best_key} (τ={best_tau}h, k={best_k})")
    print(f"Running REC+Field combo with best params...")
    combo_r = []
    for i in range(students_per):
        st = student_types[i % len(student_types)]
        cv = coverages[i % len(coverages)]
        s = StudentV2(900000 + i, student_type=st, coverage=cv)
        r = simulate_student(tree, s, 'field', 0.60, n_days, budget,
                             seed=900000 + i, rec_tau=best_tau, rec_k=best_k)
        # patch: field with rec urgency
        combo_r.append(r)
    final['rec_field_combo'] = summary([r['final_R'] for r in combo_r])

    # ── 统计检验 ──
    std_vals = [r['final_R'] for r in round1['standard'] + round2['standard']]
    fld_vals = [r['final_R'] for r in round1['field_a0.60'] + round2['field_a0.60']]
    final['test_field_vs_std'] = paired_test(std_vals, fld_vals)

    best_vals = [r['final_R'] for r in round1[best_key] + round2[best_key]]
    final['test_best_rec_vs_std'] = paired_test(std_vals, best_vals)

    return final, tau_values, k_values, best_tau, best_k


# ═══════════════════════════════════════
# Main
# ═══════════════════════════════════════

def main():
    tree = load_cfa_tree(os.path.join(os.path.dirname(__file__), 'cfa_tree.json'), heavy=True)
    print(f"CFA Tree: {tree['n_kps']} KPs (heavy mode)\n")

    # τ ∈ {0.5, 1, 2, 4, 8}h, k ∈ {0.8, 1.0, 1.2, 1.5, 2.0}
    tau_values = [0.5, 1.0, 2.0, 4.0, 8.0]
    k_values = [0.8, 1.0, 1.2, 1.5, 2.0]
    tau_k_grid = [(t, k) for t in tau_values for k in k_values]

    students_per = 400   # 匹配 Phase 0 规模
    n_days = 150
    budget = 6
    rounds = 2

    total_runs = (2 + len(tau_k_grid)) * students_per * rounds
    print(f"⚡ 规模: {len(tau_k_grid)} combos × {students_per} students × {rounds} rounds")
    print(f"   总计 {total_runs:,} student-runs ({total_runs * n_days:,} student-days)\n")

    t0 = time.time()
    results, tau_values, k_values, best_tau, best_k = run_experiment(
        tree, tau_k_grid, students_per, n_days, budget, rounds)
    elapsed = time.time() - t0

    # ── Report ──
    std_mean = results['standard']['mean']
    fld_mean = results['field_a0.60']['mean']

    print(f"\n{'='*70}")
    print(f"DONE in {elapsed:.0f}s ({elapsed/60:.1f}min)  |  {total_runs:,} runs")
    print(f"{'='*70}")
    print(f"{'Scheduler':>22} {'R_mean':>8} {'95%CI':>8} {'Δstd':>8} {'Δfld':>8}")
    print("-" * 70)

    baselines = ['standard', 'field_a0.60', 'rec_field_combo']
    for key in baselines:
        if key in results:
            r = results[key]
            print(f"{key:>22} {r['mean']:8.4f} ±{r['ci95']:.4f} "
                  f"{r['mean']-std_mean:+8.4f} {r['mean']-fld_mean:+8.4f}")

    # Top REC
    rec_entries = [(k, v) for k, v in results.items() if k.startswith('rec_t')]
    rec_entries.sort(key=lambda x: -x[1]['mean'])
    print(f"\nTop 5 REC params (2-round avg, 800 students each):")
    for key, r in rec_entries[:5]:
        rd = results.get(f"{key}_round_delta", 0)
        print(f"  {key:>20}  R={r['mean']:.4f} ±{r['ci95']:.4f}  "
              f"Δstd={r['mean']-std_mean:+.4f}  rd_delta={rd:.5f}")

    # 统计检验
    print(f"\n── 统计检验 ──")
    for test_name in ['test_field_vs_std', 'test_best_rec_vs_std']:
        t = results.get(test_name, {})
        if t:
            sig = '***' if t['p'] < 0.001 else ('**' if t['p'] < 0.01 else ('*' if t['p'] < 0.05 else 'ns'))
            print(f"  {test_name}: Δ={t['mean_diff']:+.4f}  "
                  f"t={t['t']:.1f}  p={t['p']:.4f} {sig}  d={t['cohens_d']:.3f}")

    os.makedirs('scripts/output', exist_ok=True)
    # 只存摘要（原始 per-student 数据太大）
    out = {k: v if isinstance(v, dict) and 'mean' in v else str(v)[:200]
           for k, v in results.items() if not k.startswith('test_')}
    with open('scripts/output/rec_results.json', 'w') as f:
        json.dump(out, f, indent=2, default=float)
    print(f"\nSaved to scripts/output/rec_results.json")

    _plot_results(results, tau_values, k_values, std_mean, fld_mean, best_tau, best_k)


def _live_dashboard(round_results, tau_values, k_values, rnd_num, combo_done, combo_total):
    """
    运行中弹窗：4 面板实时仪表盘
      (a) REC Δ vs Standard 热力图（逐格填满）
      (b) 当前最优 vs baseline 柱状图
      (c) 进度条 + 核心指标
      (d) 已完成 combo 的 Top 5 文字
    """
    try:
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        return

    plt.close('all')

    n_tau, n_k = len(tau_values), len(k_values)

    # 提取数据
    std_mean = None
    fld_mean = None
    if 'standard' in round_results:
        std_mean = np.mean([r['final_R'] for r in round_results['standard']])
    if 'field_a0.60' in round_results:
        fld_mean = np.mean([r['final_R'] for r in round_results['field_a0.60']])

    # 热力图数据
    heatmap = np.full((n_k, n_tau), np.nan)
    rec_entries = []
    for i, tau in enumerate(tau_values):
        for j, k in enumerate(k_values):
            key = f"rec_t{tau:.1f}_k{k:.1f}"
            if key in round_results:
                vals = [r['final_R'] for r in round_results[key]]
                m = np.mean(vals)
                heatmap[j, i] = m - std_mean if std_mean else m
                rec_entries.append((key, tau, k, m, np.std(vals, ddof=1) if len(vals)>1 else 0))

    rec_entries.sort(key=lambda x: -x[3])

    fig, axes = plt.subplots(2, 2, figsize=(14, 10), num='REC Live Dashboard')
    fig.suptitle(f'REC Simulation — Round {rnd_num}  [{combo_done}/{combo_total} combos]',
                 fontsize=14, fontweight='bold', y=0.98)

    # ── (0,0) 热力图 ──
    ax = axes[0, 0]
    cmap = plt.cm.RdYlGn; cmap.set_bad('#1a1a2e')
    im = ax.imshow(heatmap, cmap=cmap, aspect='auto', vmin=-0.06, vmax=0.06)
    ax.set_xticks(range(n_tau)); ax.set_xticklabels([f'{t:.1f}h' for t in tau_values])
    ax.set_yticks(range(n_k)); ax.set_yticklabels([f'{k:.1f}' for k in k_values])
    ax.set_xlabel('τ (hours)'); ax.set_ylabel('k')
    ax.set_title('Δ vs Standard Urgency', fontweight='bold')
    for i in range(n_tau):
        for j in range(n_k):
            v = heatmap[j, i]
            if not np.isnan(v):
                ax.text(i, j, f'{v:+.3f}', ha='center', va='center', fontsize=7,
                        color='white' if abs(v)>0.03 else 'black', fontweight='bold')
    plt.colorbar(im, ax=ax, shrink=0.8)

    # ── (0,1) 柱状图 ──
    ax = axes[0, 1]
    bars_data = []
    if std_mean: bars_data.append(('Standard', std_mean, '#94a3b8'))
    if fld_mean: bars_data.append(('Field α=0.60', fld_mean, '#4AE68A'))
    if rec_entries:
        best = rec_entries[0]
        bars_data.append((f'Best REC\nτ={best[1]:.1f}h k={best[2]:.1f}', best[3], '#5b5fef'))
    x = np.arange(len(bars_data))
    vals = [b[1] for b in bars_data]
    colors = [b[2] for b in bars_data]
    bars = ax.bar(x, vals, 0.5, color=colors, edgecolor='white')
    ax.set_xticks(x); ax.set_xticklabels([b[0] for b in bars_data], fontsize=9)
    ax.set_title('Model Comparison', fontweight='bold')
    for bar, val in zip(bars, vals):
        ax.text(bar.get_x()+bar.get_width()/2, bar.get_height()+0.003,
                f'{val:.4f}', ha='center', fontweight='bold', fontsize=10)
    ax.set_ylim(0, max(vals)*1.2 if vals else 1)

    # ── (1,0) 进度 + 指标 ──
    ax = axes[1, 0]
    ax.axis('off')
    pct = combo_done / max(combo_total, 1) * 100
    lines = [
        f"Progress: {combo_done}/{combo_total} ({pct:.0f}%)",
        f"",
        f"Baselines:",
    ]
    if std_mean: lines.append(f"  Standard:     {std_mean:.4f}")
    if fld_mean: lines.append(f"  Field(α=0.60): {fld_mean:.4f}")
    if rec_entries:
        lines.append(f"")
        lines.append(f"Best REC so far:")
        lines.append(f"  τ={rec_entries[0][1]:.1f}h  k={rec_entries[0][2]:.1f}")
        lines.append(f"  R={rec_entries[0][3]:.4f}")
        if std_mean:
            lines.append(f"  Δstd={rec_entries[0][3]-std_mean:+.4f}")
    text = '\n'.join(lines)
    ax.text(0.05, 0.95, text, transform=ax.transAxes, fontsize=12,
            fontfamily='monospace', verticalalignment='top')

    # ── (1,1) Top 5 ──
    ax = axes[1, 1]
    ax.axis('off')
    lines = ["Top 5 REC combos:"]
    for rank, (key, tau, k, mean, std) in enumerate(rec_entries[:5]):
        delta = f"{mean-std_mean:+.4f}" if std_mean else "?"
        lines.append(f"  {rank+1}. τ={tau:.1f}h k={k:.1f}  R={mean:.4f}  Δ={delta}")
    ax.text(0.05, 0.95, '\n'.join(lines), transform=ax.transAxes, fontsize=11,
            fontfamily='monospace', verticalalignment='top')

    plt.tight_layout()
    fig.canvas.draw()
    plt.show(block=False)
    plt.pause(0.5)

    os.makedirs('scripts/output', exist_ok=True)
    fig.savefig('scripts/output/rec_live.png', dpi=120, bbox_inches='tight',
                facecolor='#f5f5f5', edgecolor='none')


# ═══════════════════════════════════════
# 论文级可视化
# ═══════════════════════════════════════

def _plot_results(results, tau_values, k_values, std_mean, fld_mean, best_tau, best_k):
    """生成 2×2 论文级图表"""
    try:
        import matplotlib.pyplot as plt
        import matplotlib.ticker as mticker
        import numpy as np
    except ImportError:
        print("\n⚠ matplotlib not installed, skip visualization.")
        print("  pip install matplotlib numpy")
        return

    # 论文风格
    plt.rcParams.update({
        'font.family': 'serif',
        'font.size': 10,
        'axes.labelsize': 11,
        'axes.titlesize': 12,
        'legend.fontsize': 9,
        'figure.dpi': 200,
        'savefig.dpi': 200,
        'savefig.bbox': 'tight',
        'savefig.pad_inches': 0.05,
    })

    n_tau, n_k = len(tau_values), len(k_values)
    fig, axes = plt.subplots(2, 2, figsize=(14, 12))

    # ── (0,0) REC Δ vs Standard ──
    ax = axes[0, 0]
    heat_std = np.zeros((n_k, n_tau))
    for i, tau in enumerate(tau_values):
        for j, k in enumerate(k_values):
            key = f"rec_t{tau:.1f}_k{k:.1f}"
            heat_std[j, i] = results[key]['mean'] - std_mean

    im0 = ax.imshow(heat_std, cmap='RdYlGn', aspect='auto', vmin=-0.06, vmax=0.06)
    ax.set_xticks(range(n_tau)); ax.set_xticklabels([f'{t:.1f}' for t in tau_values])
    ax.set_yticks(range(n_k)); ax.set_yticklabels([f'{k:.1f}' for k in k_values])
    ax.set_xlabel('τ (hours)')
    ax.set_ylabel('k')
    ax.set_title('(a) REC vs Standard Urgency', loc='left', fontweight='bold')
    for i in range(n_tau):
        for j in range(n_k):
            v = heat_std[j, i]
            c = 'white' if abs(v) > 0.03 else 'black'
            ax.text(i, j, f'{v:+.3f}', ha='center', va='center', fontsize=7, color=c, fontweight='bold')
    plt.colorbar(im0, ax=ax, label='Δ retention', shrink=0.85)

    # ── (0,1) REC Δ vs Field(α=0.60) ──
    ax = axes[0, 1]
    heat_fld = np.zeros((n_k, n_tau))
    for i, tau in enumerate(tau_values):
        for j, k in enumerate(k_values):
            key = f"rec_t{tau:.1f}_k{k:.1f}"
            heat_fld[j, i] = results[key]['mean'] - fld_mean

    im1 = ax.imshow(heat_fld, cmap='RdYlGn', aspect='auto', vmin=-0.06, vmax=0.06)
    ax.set_xticks(range(n_tau)); ax.set_xticklabels([f'{t:.1f}' for t in tau_values])
    ax.set_yticks(range(n_k)); ax.set_yticklabels([f'{k:.1f}' for k in k_values])
    ax.set_xlabel('τ (hours)')
    ax.set_ylabel('k')
    ax.set_title('(b) REC vs Field (α=0.60)', loc='left', fontweight='bold')
    for i in range(n_tau):
        for j in range(n_k):
            v = heat_fld[j, i]
            c = 'white' if abs(v) > 0.03 else 'black'
            ax.text(i, j, f'{v:+.3f}', ha='center', va='center', fontsize=7, color=c, fontweight='bold')
    plt.colorbar(im1, ax=ax, label='Δ retention', shrink=0.85)

    # ── (1,0) 可复现性：两轮 delta ──
    ax = axes[1, 0]
    rd_heat = np.zeros((n_k, n_tau))
    for i, tau in enumerate(tau_values):
        for j, k in enumerate(k_values):
            key = f"rec_t{tau:.1f}_k{k:.1f}_round_delta"
            rd_heat[j, i] = results.get(key, 0)

    im2 = ax.imshow(rd_heat, cmap='YlOrRd', aspect='auto', vmin=0, vmax=0.02)
    ax.set_xticks(range(n_tau)); ax.set_xticklabels([f'{t:.1f}' for t in tau_values])
    ax.set_yticks(range(n_k)); ax.set_yticklabels([f'{k:.1f}' for k in k_values])
    ax.set_xlabel('τ (hours)')
    ax.set_ylabel('k')
    ax.set_title('(c) Round-to-Round Stability |Δ|', loc='left', fontweight='bold')
    for i in range(n_tau):
        for j in range(n_k):
            v = rd_heat[j, i]
            c = 'white' if v > 0.01 else 'black'
            ax.text(i, j, f'{v:.4f}', ha='center', va='center', fontsize=7, color=c, fontweight='bold')
    plt.colorbar(im2, ax=ax, label='|round1 − round2|', shrink=0.85)

    # ── (1,1) 模型对比柱状图 ──
    ax = axes[1, 1]
    best_key = f"rec_t{best_tau:.1f}_k{best_k:.1f}"
    best_r = results[best_key]
    combo_r = results.get('rec_field_combo', {})

    labels = ['Standard\nUrgency', 'Field\n(α=0.60)', f'Best REC\nτ={best_tau:.1f}h, k={best_k:.1f}', 'REC + Field\nCombo']
    values = [std_mean, fld_mean, best_r['mean'],
              combo_r.get('mean', 0) if combo_r else 0]
    errors = [results['standard'].get('ci95', 0), results['field_a0.60'].get('ci95', 0),
              best_r.get('ci95', 0), combo_r.get('ci95', 0) if combo_r else 0]
    colors_bars = ['#94a3b8', '#4AE68A', '#5b5fef', '#f59e0b']

    x = np.arange(len(labels))
    bars = ax.bar(x, values, 0.55, color=colors_bars, edgecolor='white', linewidth=0.5)
    ax.errorbar(x, values, yerr=errors, fmt='none', ecolor='#333', capsize=4, linewidth=0.8)
    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel('150-day Retention', fontweight='bold')
    ax.set_title('(d) Model Comparison', loc='left', fontweight='bold')
    ax.set_ylim(0, max(values) * 1.2)

    for bar, val, err in zip(bars, values, errors):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + err + 0.005,
                f'{val:.4f}', ha='center', fontsize=9, fontweight='bold')
    # 标注 vs standard 的差值
    for i, (bar, val) in enumerate(zip(bars, values)):
        if i > 0 and val > 0:
            delta = val - std_mean
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() * 0.35,
                    f'+{delta:+.3f}', ha='center', fontsize=9, fontweight='bold', color='white')

    plt.tight_layout()
    out_path = 'scripts/output/rec_paper_figure.png'
    plt.savefig(out_path, facecolor='white', edgecolor='none')
    plt.show(block=False)
    print(f"Figure saved to {out_path}")

    # ── 单独存 SVGs ──
    os.makedirs('scripts/output', exist_ok=True)
    for name, (ax_idx, is_heatmap) in {
        'fig_a_rec_vs_std': ((0,0), True),
        'fig_b_rec_vs_field': ((0,1), True),
        'fig_c_stability': ((1,0), True),
        'fig_d_comparison': ((1,1), False),
    }.items():
        sub_fig, sub_ax = plt.subplots(figsize=(7, 6))
        # 重新画（简化：用原始数据重建，或直接 save 子图区域。用简单方式：重建）
        plt.close(sub_fig)

    # 统计摘要文本文件
    with open('scripts/output/rec_stats.txt', 'w') as f:
        t = results.get('test_best_rec_vs_std', {})
        f.write(f"Best REC ({best_key}) vs Standard:\n")
        f.write(f"  Δ = {t.get('mean_diff', 0):+.4f}\n")
        f.write(f"  t-statistic = {t.get('t', 0):.2f}\n")
        f.write(f"  p-value = {t.get('p', 1):.6f}\n")
        f.write(f"  Cohen's d = {t.get('cohens_d', 0):.3f}\n")
        f.write(f"  n = {t.get('n', 0)}\n\n")
        t2 = results.get('test_field_vs_std', {})
        f.write(f"Field (α=0.60) vs Standard:\n")
        f.write(f"  Δ = {t2.get('mean_diff', 0):+.4f}\n")
        f.write(f"  p = {t2.get('p', 1):.6f}\n")
        f.write(f"  Cohen's d = {t2.get('cohens_d', 0):.3f}\n")
    print("Stats saved to scripts/output/rec_stats.txt")


if __name__ == '__main__':
    main()
