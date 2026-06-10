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

                if sched in ('standard', 'field'):
                    urg = 1.0 - student.R(li, cur_t) if student.last[li] >= 0 else 3.0
                elif sched == 'rec':
                    urg = rec_urgency(S0, elapsed_h, k=rec_k, tau_hours=rec_tau) if S0 > 0 else 1.0
                else:
                    urg = 0.0

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

def summary(group):
    arr = np.array([r['final_R'] for r in group])
    return {'mean': float(np.mean(arr)), 'std': float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0}


def run_experiment(tree, tau_k_grid, students_per=60, n_days=150, budget=6):
    results = {}
    student_types = list(STUDENT_TYPES.keys())
    coverages = [0.4, 0.6, 0.8]

    # Baseline: standard + field (alpha=0.60, current production)
    print("Baseline: standard urgency...")
    std_results = []
    for i in range(students_per):
        stype = student_types[i % len(student_types)]
        cov = coverages[i % len(coverages)]
        s = StudentV2(i, student_type=stype, coverage=cov)
        std_results.append(simulate_student(tree, s, 'standard', 0.60, n_days, budget, seed=i))
    results['standard'] = summary(std_results)

    print("Baseline: field (alpha=0.60)...")
    fld_results = []
    for i in range(students_per):
        stype = student_types[i % len(student_types)]
        cov = coverages[i % len(coverages)]
        s = StudentV2(i + 10000, student_type=stype, coverage=cov)
        fld_results.append(simulate_student(tree, s, 'field', 0.60, n_days, budget, seed=i + 10000))
    results['field_a0.60'] = summary(fld_results)

    # REC grid search
    total = len(tau_k_grid)
    for idx, (tau, k) in enumerate(tau_k_grid):
        key = f"rec_t{tau:.1f}_k{k:.1f}"
        print(f"[{idx+1}/{total}] {key} ...", end=' ', flush=True)
        t0 = time.time()

        rec_results = []
        for i in range(students_per):
            stype = student_types[i % len(student_types)]
            cov = coverages[i % len(coverages)]
            s = StudentV2(idx * 1000 + i, student_type=stype, coverage=cov)
            rec_results.append(simulate_student(
                tree, s, 'rec', 0.60, n_days, budget,
                seed=idx * 1000 + i, rec_tau=tau, rec_k=k))

        s = summary(rec_results)
        results[key] = s
        dt = time.time() - t0
        print(f"R={s['mean']:.4f} ± {s['std']:.4f} ({dt:.0f}s)")

    return results


def main():
    tree = load_cfa_tree(os.path.join(os.path.dirname(__file__), 'cfa_tree.json'), heavy=True)
    print(f"CFA Tree: {tree['n_kps']} KPs (heavy mode)\n")

    # Grid search: τ ∈ {0.5, 1, 2, 4, 8} hours, k ∈ {0.8, 1.0, 1.2, 1.5, 2.0}
    # τ=0.5 对应 30min 不应期, τ=8 对应 8h (约等于一天的学习窗口)
    tau_values = [0.5, 1.0, 2.0, 4.0, 8.0]
    k_values = [0.8, 1.0, 1.2, 1.5, 2.0]
    tau_k_grid = [(t, k) for t in tau_values for k in k_values]

    students_per = 60
    n_days = 150
    budget = 6

    print(f"Grid: {len(tau_k_grid)} combos × {students_per} students × {n_days}d\n")

    t0 = time.time()
    results = run_experiment(tree, tau_k_grid, students_per, n_days, budget)
    elapsed = time.time() - t0

    # ── Report ──
    print(f"\n{'='*70}")
    print(f"Done in {elapsed:.0f}s ({elapsed/60:.1f}min)")
    print(f"{'='*70}")
    print(f"{'Scheduler':>20}  {'R_mean':>8}  {'R_std':>8}  vs_standard  vs_field")
    print("-" * 70)

    std_mean = results['standard']['mean']
    fld_mean = results['field_a0.60']['mean']

    for key in ['standard', 'field_a0.60']:
        r = results[key]
        d_std = r['mean'] - std_mean
        d_fld = r['mean'] - fld_mean
        print(f"{key:>20}  {r['mean']:8.4f}  {r['std']:8.4f}  {d_std:+8.4f}  {d_fld:+8.4f}")

    # Top REC performers
    rec_entries = [(k, v) for k, v in results.items() if k.startswith('rec')]
    rec_entries.sort(key=lambda x: -x[1]['mean'])

    print(f"\nTop 5 REC params:")
    for key, r in rec_entries[:5]:
        d_std = r['mean'] - std_mean
        d_fld = r['mean'] - fld_mean
        print(f"  {key:>20}  R={r['mean']:.4f}  Δstd={d_std:+.4f}  Δfld={d_fld:+.4f}")

    os.makedirs('scripts/output', exist_ok=True)
    with open('scripts/output/rec_results.json', 'w') as f:
        json.dump(results, f, indent=2, default=float)
    print(f"\nSaved to scripts/output/rec_results.json")

    # ── Visualization ──
    _plot_results(results, tau_values, k_values, std_mean, fld_mean)


def _plot_results(results, tau_values, k_values, std_mean, fld_mean):
    """生成两张图：热力图 + 对比柱状图"""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        print("\n⚠ matplotlib not installed, skip visualization.")
        print("  pip install matplotlib")
        return

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

    # ── 左：热力图 (Δ vs standard) ──
    n_tau, n_k = len(tau_values), len(k_values)
    heatmap = np.zeros((n_k, n_tau))
    for i, tau in enumerate(tau_values):
        for j, k in enumerate(k_values):
            key = f"rec_t{tau:.1f}_k{k:.1f}"
            heatmap[j, i] = results[key]['mean'] - std_mean

    im = ax1.imshow(heatmap, cmap='RdYlGn', aspect='auto', vmin=-0.05, vmax=0.05)
    ax1.set_xticks(range(n_tau))
    ax1.set_xticklabels([f'{t:.1f}h' for t in tau_values])
    ax1.set_yticks(range(n_k))
    ax1.set_yticklabels([f'{k:.1f}' for k in k_values])
    ax1.set_xlabel('τ (refractory period, hours)')
    ax1.set_ylabel('k (Weibull shape)')
    ax1.set_title('REC Δ vs Standard Urgency')

    # 标注数值
    for i in range(n_tau):
        for j in range(n_k):
            val = heatmap[j, i]
            color = 'white' if abs(val) > 0.03 else 'black'
            ax1.text(i, j, f'{val:+.3f}', ha='center', va='center',
                     fontsize=8, color=color, fontweight='bold')

    plt.colorbar(im, ax=ax1, label='Δ retention')

    # ── 右：柱状图对比 ──
    rec_entries = [(k, v) for k, v in results.items() if k.startswith('rec')]
    rec_entries.sort(key=lambda x: -x[1]['mean'])
    best_key, best_r = rec_entries[0]

    labels = ['Standard', 'Field\n(α=0.60)', f'Best REC\n({best_key})']
    values = [std_mean, fld_mean, best_r['mean']]
    colors = ['#94a3b8', '#4AE68A', '#5b5fef']

    bars = ax2.bar(labels, values, color=colors, width=0.5)
    ax2.set_ylabel('150-day Retention')
    ax2.set_title('Urgency Model Comparison')
    ax2.set_ylim(0, max(values) * 1.15)

    for bar, val in zip(bars, values):
        ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.005,
                f'{val:.4f}', ha='center', fontweight='bold', fontsize=11)
        if val > std_mean:
            delta = val - std_mean
            ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height()/2,
                    f'+{delta:.3f}', ha='center', fontweight='bold',
                    fontsize=10, color='white')

    plt.tight_layout()
    out_path = 'scripts/output/rec_visualization.png'
    plt.savefig(out_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Saved to {out_path}")


if __name__ == '__main__':
    main()
