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

# ═══ 弹窗 — 必须在任何 pyplot 导入前 ═══
import matplotlib
import os as _os
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

_HEADLESS = True
plt.ion() if not _HEADLESS else None  # 交互模式（仅 GUI）

# ═══ 配色方案 ═══
C = {
    'bg':     '#0d1117',
    'panel':  '#161b22',
    'border': '#30363d',
    'green':  '#3fb950',
    'blue':   '#58a6ff',
    'purple': '#a371f7',
    'orange': '#d2991d',
    'red':    '#f85149',
    'text':   '#c9d1d9',
    'dim':    '#8b949e',
    'accent': '#7ee787',
}

# ═══ 全局：持久 figure ═══
_live_fig = None
_live_axes = None


def _live_dashboard(round_results, tau_values, k_values, rnd_num, combo_done, combo_total):
    global _live_fig, _live_axes

    n_tau, n_k = len(tau_values), len(k_values)

    std_mean = None
    fld_mean = None
    std_arr = round_results.get('standard')
    fld_arr = round_results.get('field_a0.60')
    if std_arr:
        std_mean = np.mean([r['final_R'] for r in std_arr])
    if fld_arr:
        fld_mean = np.mean([r['final_R'] for r in fld_arr])

    heatmap = np.full((n_k, n_tau), np.nan)
    rec_entries = []
    for i, tau in enumerate(tau_values):
        for j, k in enumerate(k_values):
            key = f"rec_t{tau:.1f}_k{k:.1f}"
            if key in round_results:
                vals = [r['final_R'] for r in round_results[key]]
                m = np.mean(vals)
                heatmap[j, i] = m - std_mean if std_mean else m
                rec_entries.append((key, tau, k, m))
    rec_entries.sort(key=lambda x: -x[3])

    if _live_fig is None:
        _live_fig, _live_axes = plt.subplots(2, 2, figsize=(15, 10),
                                              num='Memorix REC — Live',
                                              facecolor=C['bg'])
        if not _HEADLESS:
            _live_fig.show()

    fig, axes = _live_fig, _live_axes
    for ax in axes.flat:
        ax.clear()
        ax.set_facecolor(C['panel'])
        for spine in ax.spines.values():
            spine.set_color(C['border'])

    fig.suptitle(f'Memorix REC — Round {rnd_num}    {combo_done}/{combo_total} combos',
                 fontsize=13, color=C['accent'], fontfamily='monospace', y=0.98)

    # ═══ (0,0) 热力图 ═══
    ax = axes[0, 0]
    im = ax.imshow(heatmap, cmap='RdYlGn', aspect='auto', vmin=-0.06, vmax=0.06)
    ax.set_xticks(range(n_tau)); ax.set_xticklabels([f'{t:.1f}' for t in tau_values], color=C['dim'])
    ax.set_yticks(range(n_k)); ax.set_yticklabels([f'{k:.1f}' for k in k_values], color=C['dim'])
    ax.set_xlabel('τ (hours)', color=C['dim'], fontsize=9)
    ax.set_ylabel('k', color=C['dim'], fontsize=9)
    ax.set_title('Δ Retention vs Standard', color=C['text'], fontsize=11)
    ax.tick_params(colors=C['dim'], labelsize=8)
    for i in range(n_tau):
        for j in range(n_k):
            v = heatmap[j, i]
            if not np.isnan(v):
                ax.text(i, j, f'{v:+.3f}', ha='center', va='center', fontsize=7,
                        color='#000' if v > 0.02 else C['text'], fontweight='bold')
    cbar = plt.colorbar(im, ax=ax, shrink=0.8)
    cbar.ax.yaxis.set_tick_params(color=C['dim'], labelsize=7)
    cbar.outline.set_edgecolor(C['border'])
    cbar.set_label('Δ', color=C['dim'], fontsize=8)

    # ═══ (0,1) 柱状图 ═══
    ax = axes[0, 1]
    bars_data = []
    if std_mean: bars_data.append(('Standard', std_mean, C['dim']))
    if fld_mean: bars_data.append(('Field', fld_mean, C['blue']))
    if rec_entries:
        b = rec_entries[0]
        bars_data.append((f'REC\nτ={b[1]:.1f} k={b[2]:.1f}', b[3], C['purple']))
    x = np.arange(len(bars_data))
    vals = [b[1] for b in bars_data]
    bars = ax.bar(x, vals, 0.45, color=[b[2] for b in bars_data], edgecolor=C['border'], linewidth=0.5)
    ax.set_xticks(x); ax.set_xticklabels([b[0] for b in bars_data], fontsize=8, color=C['dim'])
    ax.set_title('Model Comparison', color=C['text'], fontsize=11)
    ax.tick_params(colors=C['dim'], labelsize=8)
    for spine in ax.spines.values(): spine.set_visible(False)
    ax.yaxis.grid(True, alpha=0.08, color=C['border'])
    for bar, val in zip(bars, vals):
        ax.text(bar.get_x()+bar.get_width()/2, bar.get_height()+0.003,
                f'{val:.4f}', ha='center', fontweight='bold', fontsize=10, color=C['text'])
    if vals:
        ax.set_ylim(0, max(vals)*1.25)

    # ═══ (1,0) 指标 ═══
    ax = axes[1, 0]; ax.axis('off')
    pct = combo_done/max(combo_total, 1)*100
    lines = [f'Progress  {combo_done}/{combo_total}  ({pct:.0f}%)', '',
             'Baselines']
    if std_mean: lines.append(f'  Standard  {std_mean:.4f}')
    if fld_mean: lines.append(f'  Field     {fld_mean:.4f}')
    if rec_entries:
        lines += ['', 'Best REC', f'  τ={rec_entries[0][1]:.1f}h  k={rec_entries[0][2]:.1f}',
                  f'  R = {rec_entries[0][3]:.4f}']
        if std_mean: lines.append(f'  Δ = {rec_entries[0][3]-std_mean:+.4f}')
    ax.text(0.05, 0.95, '\n'.join(lines), transform=ax.transAxes, fontsize=11,
            fontfamily='monospace', color=C['text'], va='top')

    # ═══ (1,1) Top 5 ═══
    ax = axes[1, 1]; ax.axis('off')
    lines = ['Top 5']
    for rank, (_, tau, k, mean) in enumerate(rec_entries[:5]):
        d = f'{mean-std_mean:+.4f}' if std_mean else '?'
        lines.append(f'  {rank+1}.  τ={tau:.1f}  k={k:.1f}  R={mean:.4f}  Δ={d}')
    ax.text(0.05, 0.95, '\n'.join(lines), transform=ax.transAxes, fontsize=11,
            fontfamily='monospace', color=C['text'], va='top')

    if not _HEADLESS:
        fig.canvas.draw()
        fig.canvas.flush_events()

    os.makedirs('scripts/output', exist_ok=True)
    fig.savefig('scripts/output/rec_live.png', dpi=120, facecolor=C['bg'], edgecolor='none')

# ═══════════════════════════════════════
# P(t) 可塑性模型（小时版，适配仿真）
# ═══════════════════════════════════════
#
# 与生产 reconsolidation.py 行为对齐：
#   - 黄金分割 50 迭代（匹配生产）
#   - 已遗忘 R<0.1 → urgency=1.0（需重学）
#   - S0≤0 → urgency=1.0（新知识点尽快复习）
#   + 分桶缓存加速：S0 离散化到 0.1 天，(bucket,k,tau) 三元组缓存 t_opt

_OPT_CACHE = {}  # (S0_bucket: float, k: float, tau: float) → (t_opt_hours, P_max)

def plasticity_hours(t_hours, S0_days, lambda_days, k=1.2, tau_hours=1.0):
    """P(t) in hours. t_hours: 距上次复习的小时数。
    
    P(t) = S₀ × [1-e^(-t/τ)] × e^(-t/T_stab) × [1-e^(-(t/S₀)^k)]
           └──不应期恢复──┘  └──稳定性衰减──┘  └──遗忘驱动──────┘
    
    T_stab = S₀：稳定性衰减时间常数 = 当前稳定性本身。
    e^(-t/T_stab) 让 P(t) 在 t≈k×S₀ 处产生真实内部峰值，而非单调递增。
    """
    if t_hours <= 0 or S0_days <= 0:
        return 0.0
    t_days = t_hours / 24.0
    tau_days = tau_hours / 24.0
    # 不应期恢复
    S_t = S0_days * (1.0 - math.exp(-t_days / tau_days))
    # 稳定性缓慢衰减（T_stab = S0_days）
    S_t *= math.exp(-t_days / S0_days)
    # 遗忘驱动
    R_t = math.exp(-((t_days / max(lambda_days, 0.01)) ** k))
    return S_t * (1.0 - R_t)


def find_optimal_t_hours(S0_days, lambda_days, k=1.2, tau_hours=1.0):
    """黄金分割搜索 P(t) 最大值，返回 (t_opt_hours, P_max)。
    50 次迭代，匹配生产 reconsolidation.py。结果缓存。"""
    bucket = round(S0_days * 10) / 10  # 0.1 天精度
    cache_key = (bucket, k, tau_hours)
    cached = _OPT_CACHE.get(cache_key)
    if cached is not None:
        return cached

    lo = max(tau_hours, 0.01)
    hi = 10.0 * lambda_days * 24.0  # 10×λ 天→小时
    phi = (math.sqrt(5) - 1) / 2

    m1 = hi - phi * (hi - lo)
    m2 = lo + phi * (hi - lo)
    p1 = plasticity_hours(m1, S0_days, lambda_days, k, tau_hours)
    p2 = plasticity_hours(m2, S0_days, lambda_days, k, tau_hours)

    for _ in range(50):
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
    _OPT_CACHE[cache_key] = (t_opt, p_max)
    return t_opt, p_max


def rec_urgency(S0_days, elapsed_hours, k=1.2, tau_hours=1.0):
    """REC urgency = P(t_now) / P(t_opt)，归一化到 [0,1]。
    与生产 compute_urgency 行为对齐。"""
    # 新知识点：尽快第一次复习
    if S0_days <= 0:
        return 1.0

    # 不应期内
    if elapsed_hours < tau_hours:
        return 0.0

    # 极高稳定性 → 退化为标准 Weibull urgency
    if S0_days > 365:
        R = math.exp(-((elapsed_hours / 24.0 / S0_days) ** k))
        return 1.0 - R

    # 已遗忘 → 该重学了
    R = math.exp(-((elapsed_hours / 24.0 / S0_days) ** k))
    if R < 0.1:
        return 1.0

    # 正常路径：P(t_elapsed) / P(t_opt)
    t_opt, p_max = find_optimal_t_hours(S0_days, S0_days, k, tau_hours)
    if p_max <= 0:
        return 1.0 - R  # fallback

    p_now = plasticity_hours(elapsed_hours, S0_days, S0_days, k, tau_hours)
    return max(0.0, min(1.0, p_now / p_max))


# ═══════════════════════════════════════
# 知识树加载（复用 Phase 0）
# ═══════════════════════════════════════

def load_cfa_tree(path, heavy=False, llm_edges_path=None):
    """
    加载 CFA 知识树，构建邻接表。

    Args:
        heavy: 启用交叉边（使用 llm_edges_path 或随机边）
        llm_edges_path: LLM 生成的边 JSON 文件路径。提供则用它替代随机交叉边。
    """
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
    # 树结构边：parent-child（双向 w=0.8）
    for nd in nodes:
        if nd.get('parent_id') and nd['parent_id'] in id2i:
            adj[nd['id']].append((nd['parent_id'], 0.8))
            adj[nd['parent_id']].append((nd['id'], 0.8))

    # 兄弟边（同一 parent 下的 KP 之间，w=0.3）
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
        if llm_edges_path and os.path.exists(llm_edges_path):
            # 加载 LLM 语义边
            with open(llm_edges_path) as f:
                llm_edges = json.load(f)
            added = 0
            for e in llm_edges:
                src_id = e['source_id']
                tgt_id = e['target_id']
                if src_id in id2i and tgt_id in id2i:
                    w = float(e.get('weight', 0.5))
                    adj[src_id].append((tgt_id, w))
                    added += 1
            print(f'  [LLM edges] loaded {added} edges from {llm_edges_path}')
        else:
            # fallback: 随机交叉边
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
        return float(np.exp(-((el / max(S, 0.01)) ** k)))

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
                     study_hours=8, seed=0, use_rec=False, rec_tau=1.0, rec_k=1.2):
    """
    仿真单个学生的完整学习轨迹。

    Args:
        sched: 'standard' | 'rec' | 'field' | 'field_rec'
        use_rec: True 时 urgency = P(t)/P(t_opt)，否则 urgency = 1-R(t)
        rec_tau: 不应期时间常数（小时），仅 use_rec=True 时生效
        rec_k: Weibull 形状参数，仅 use_rec=True 时生效
    """
    np.random.seed((seed + student.sid) % (2**31))
    random.seed((seed + student.sid) % (2**31))

    n_kps = tree['n_kps']
    nbrs = tree['nbrs']
    prereq = tree['prereq']
    sec_groups = tree['sec_groups']

    student.init(n_kps, prereq, sec_groups, seed + student.sid)
    history = []

    # 预构建可复习 KP 索引（排除永远不会 unlock 的，动态更新）
    all_kps_list = list(range(n_kps))

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
            if cur_t >= session_end:
                break

            # 只遍历可复习的 KP（unlocked 或 mastered）
            eligible = [li for li in all_kps_list
                        if li in student.unlocked or li in student.mastered]
            if not eligible:
                break

            scored = []
            for li in eligible:
                elapsed_h = cur_t - student.last[li] if student.last[li] >= 0 else 999
                S0 = student.S[li]

                # ── urgency 计算 ──
                if use_rec:
                    urg = rec_urgency(S0, elapsed_h, k=rec_k, tau_hours=rec_tau)
                else:
                    # 标准 Weibull：新 KP urgency=3.0（高优先级首次接触）
                    urg = 1.0 - student.R(li, cur_t) if student.last[li] >= 0 else 3.0

                # ── field_benefit（仅 field / field_rec 模式）──
                if sched in ('field', 'field_rec'):
                    fb = sum(w * max(0.0, 1.0 - student.R(nli, cur_t))
                             for nli, w in nbrs.get(li, []))
                    urg = alpha * urg + (1 - alpha) * fb

                scored.append((li, urg))

            # 候选不够 → 用 unlocked 的未评分 KP 补齐
            if len(scored) < budget:
                scored_ids = {s[0] for s in scored}
                for li in student.unlocked:
                    if li not in scored_ids:
                        scored.append((li, 2.0))
                        scored_ids.add(li)
                        if len(scored) >= budget:
                            break

            scored.sort(key=lambda x: -x[1])
            selected = [li for li, _ in scored[:budget]]

            for li in selected:
                rating = student.get_rating(li, cur_t)
                student.review(li, cur_t, rating)

                # ═══ 生产 pull 模型：调度时重排，复习时不改邻居 ═══
                # 原 push boost 已移除——与生产 _field_rerank 行为对齐

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

        # 立即弹出空仪表盘窗口
        # (headless: skip live dashboard)
        seed_offset = rnd * 100000

        # Baseline
        print("Baseline: standard ...", flush=True)
        t0 = time.time()
        std_r = []
        for i in range(students_per):
            st = student_types[i % len(student_types)]
            cv = coverages[i % len(coverages)]
            s = StudentV2(seed_offset + i, student_type=st, coverage=cv)
            std_r.append(simulate_student(tree, s, 'standard', 0.60, n_days, budget, seed=seed_offset + i))
            if (i+1) % 100 == 0:
                print(f"  {i+1}/{students_per} students ({time.time()-t0:.0f}s)", flush=True)
        results['standard'] = std_r
        print(f"  done: R={summary([r['final_R'] for r in std_r])['mean']:.4f} ({time.time()-t0:.0f}s)")

        print("Baseline: field (α=0.60) ...", flush=True)
        t0 = time.time()
        fld_r = []
        for i in range(students_per):
            st = student_types[i % len(student_types)]
            cv = coverages[i % len(coverages)]
            s = StudentV2(seed_offset + 50000 + i, student_type=st, coverage=cv)
            fld_r.append(simulate_student(tree, s, 'field', 0.60, n_days, budget, seed=seed_offset + 50000 + i))
            if (i+1) % 100 == 0:
                print(f"  {i+1}/{students_per} students ({time.time()-t0:.0f}s)", flush=True)
        results['field_a0.60'] = fld_r
        print(f"  done: R={summary([r['final_R'] for r in fld_r])['mean']:.4f} ({time.time()-t0:.0f}s)")

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
                    use_rec=True, rec_tau=tau, rec_k=k))
            results[key] = rec_r
            dt = time.time() - t0
            s = summary([r['final_R'] for r in rec_r])
            print(f"R={s['mean']:.4f} ± {s['ci95']:.4f} ({dt:.0f}s)")

            # round done, accumulate
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
    rec_only = [(k, v) for k, v in final.items()
                if k.startswith('rec_t') and not k.endswith('_round_delta')]
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
        r = simulate_student(tree, s, 'field_rec', 0.60, n_days, budget,
                             seed=900000 + i, use_rec=True,
                             rec_tau=best_tau, rec_k=best_k)
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
    script_dir = os.path.dirname(__file__)
    tree_path = os.path.join(script_dir, 'cfa_tree.json')
    llm_path = os.path.join(script_dir, 'cfa_llm_edges.json')
    tree = load_cfa_tree(tree_path, heavy=True, llm_edges_path=llm_path)
    print(f"CFA Tree: {tree['n_kps']} KPs (heavy mode + LLM edges)\n")

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

# ═══════════════════════════════════════
# 论文级可视化
# ═══════════════════════════════════════

def _plot_results(results, tau_values, k_values, std_mean, fld_mean, best_tau, best_k):
    """2×2 论文级图表 — 暗色主题"""
    import numpy as np

    n_tau, n_k = len(tau_values), len(k_values)
    fig, axes = plt.subplots(2, 2, figsize=(15, 11),
                              facecolor=C['bg'], num='Memorix REC — Paper')

    for ax in axes.flat:
        ax.set_facecolor(C['panel'])
        for spine in ax.spines.values():
            spine.set_color(C['border'])
            spine.set_linewidth(0.5)

    fig.suptitle('Memorix Reconsolidation Window — Parameter Sweep',
                 fontsize=14, color=C['text'], fontweight='bold', y=0.98)

    # ═══ (a) REC Δ vs Standard ═══
    ax = axes[0, 0]
    heat_std = np.zeros((n_k, n_tau))
    for i, tau in enumerate(tau_values):
        for j, k in enumerate(k_values):
            key = f"rec_t{tau:.1f}_k{k:.1f}"
            heat_std[j, i] = results[key]['mean'] - std_mean
    im0 = ax.imshow(heat_std, cmap='RdYlGn', aspect='auto', vmin=-0.06, vmax=0.06)
    ax.set_xticks(range(n_tau)); ax.set_xticklabels([f'{t:.1f}' for t in tau_values], color=C['dim'])
    ax.set_yticks(range(n_k)); ax.set_yticklabels([f'{k:.1f}' for k in k_values], color=C['dim'])
    ax.set_xlabel('τ (hours)', color=C['dim']); ax.set_ylabel('k', color=C['dim'])
    ax.set_title('(a)  REC  vs  Standard Urgency', color=C['text'], fontsize=11, loc='left')
    ax.tick_params(colors=C['dim'], labelsize=8)
    for i in range(n_tau):
        for j in range(n_k):
            v = heat_std[j, i]
            c = '#000' if v > 0.02 else C['text']
            ax.text(i, j, f'{v:+.3f}', ha='center', va='center', fontsize=7, color=c, fontweight='bold')
    cbar = plt.colorbar(im0, ax=ax, shrink=0.85)
    cbar.ax.yaxis.set_tick_params(color=C['dim'], labelsize=7)
    cbar.outline.set_edgecolor(C['border'])
    cbar.set_label('Δ retention', color=C['dim'], fontsize=8)

    # ═══ (b) REC Δ vs Field ═══
    ax = axes[0, 1]
    heat_fld = np.zeros((n_k, n_tau))
    for i, tau in enumerate(tau_values):
        for j, k in enumerate(k_values):
            key = f"rec_t{tau:.1f}_k{k:.1f}"
            heat_fld[j, i] = results[key]['mean'] - fld_mean
    im1 = ax.imshow(heat_fld, cmap='RdYlGn', aspect='auto', vmin=-0.06, vmax=0.06)
    ax.set_xticks(range(n_tau)); ax.set_xticklabels([f'{t:.1f}' for t in tau_values], color=C['dim'])
    ax.set_yticks(range(n_k)); ax.set_yticklabels([f'{k:.1f}' for k in k_values], color=C['dim'])
    ax.set_xlabel('τ (hours)', color=C['dim']); ax.set_ylabel('k', color=C['dim'])
    ax.set_title('(b)  REC  vs  Field  (α = 0.60)', color=C['text'], fontsize=11, loc='left')
    ax.tick_params(colors=C['dim'], labelsize=8)
    for i in range(n_tau):
        for j in range(n_k):
            v = heat_fld[j, i]
            c = '#000' if v > 0.02 else C['text']
            ax.text(i, j, f'{v:+.3f}', ha='center', va='center', fontsize=7, color=c, fontweight='bold')
    cbar = plt.colorbar(im1, ax=ax, shrink=0.85)
    cbar.ax.yaxis.set_tick_params(color=C['dim'], labelsize=7)
    cbar.outline.set_edgecolor(C['border'])
    cbar.set_label('Δ retention', color=C['dim'], fontsize=8)

    # ═══ (c) 可复现性 ═══
    ax = axes[1, 0]
    rd_heat = np.zeros((n_k, n_tau))
    for i, tau in enumerate(tau_values):
        for j, k in enumerate(k_values):
            key = f"rec_t{tau:.1f}_k{k:.1f}_round_delta"
            rd_heat[j, i] = results.get(key, 0)
    im2 = ax.imshow(rd_heat, cmap='plasma', aspect='auto', vmin=0, vmax=0.02)
    ax.set_xticks(range(n_tau)); ax.set_xticklabels([f'{t:.1f}' for t in tau_values], color=C['dim'])
    ax.set_yticks(range(n_k)); ax.set_yticklabels([f'{k:.1f}' for k in k_values], color=C['dim'])
    ax.set_xlabel('τ (hours)', color=C['dim']); ax.set_ylabel('k', color=C['dim'])
    ax.set_title('(c)  Cross-Round Stability  |Δ|', color=C['text'], fontsize=11, loc='left')
    ax.tick_params(colors=C['dim'], labelsize=8)
    for i in range(n_tau):
        for j in range(n_k):
            v = rd_heat[j, i]
            c = C['text'] if v > 0.01 else C['dim']
            ax.text(i, j, f'{v:.4f}', ha='center', va='center', fontsize=7, color=c, fontweight='bold')
    cbar = plt.colorbar(im2, ax=ax, shrink=0.85)
    cbar.ax.yaxis.set_tick_params(color=C['dim'], labelsize=7)
    cbar.outline.set_edgecolor(C['border'])
    cbar.set_label('|R1 − R2|', color=C['dim'], fontsize=8)

    # ═══ (d) 模型对比 ═══
    ax = axes[1, 1]
    best_key = f"rec_t{best_tau:.1f}_k{best_k:.1f}"
    best_r = results[best_key]
    combo_r = results.get('rec_field_combo', {})

    labels = ['Standard', 'Field\n(α=0.60)', 'Best REC\n(τ=%.1f, k=%.1f)'%(best_tau,best_k), 'REC+Field']
    values = [std_mean, fld_mean, best_r['mean'], combo_r.get('mean',0) if combo_r else 0]
    errors = [results['standard'].get('ci95',0), results['field_a0.60'].get('ci95',0),
              best_r.get('ci95',0), combo_r.get('ci95',0) if combo_r else 0]
    colors_bars = [C['dim'], C['blue'], C['purple'], C['orange']]

    x = np.arange(len(labels))
    bars = ax.bar(x, values, 0.5, color=colors_bars, edgecolor=C['border'], linewidth=0.5)
    ax.errorbar(x, values, yerr=errors, fmt='none', ecolor=C['red'], capsize=3, linewidth=0.8)
    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=8, color=C['dim'])
    ax.set_title('(d)  Model Comparison', color=C['text'], fontsize=11, loc='left')
    ax.tick_params(colors=C['dim'], labelsize=8)
    for spine in ax.spines.values(): spine.set_visible(False)
    ax.yaxis.grid(True, alpha=0.06, color=C['border'])
    for bar, val, err in zip(bars, values, errors):
        ax.text(bar.get_x()+bar.get_width()/2, bar.get_height()+err+0.005,
                f'{val:.4f}', ha='center', fontsize=9, fontweight='bold', color=C['text'])
    for i, (bar, val) in enumerate(zip(bars, values)):
        if i > 0 and val > 0:
            d = val - std_mean
            ax.text(bar.get_x()+bar.get_width()/2, bar.get_height()*0.35,
                    f'{d:+.3f}', ha='center', fontsize=9, fontweight='bold', color=C['bg'])
    if values:
        ax.set_ylim(0, max(values)*1.25)

    plt.tight_layout()
    out_path = 'scripts/output/rec_paper_figure.png'
    fig.savefig(out_path, dpi=200, facecolor=C['bg'], edgecolor='none')
    if not _HEADLESS:
        plt.show(block=False)
    print(f"Figure saved to {out_path}")

    # 统计摘要
    with open('scripts/output/rec_stats.txt', 'w') as f:
        t = results.get('test_best_rec_vs_std', {})
        f.write(f"Best REC ({best_key}) vs Standard:\n")
        f.write(f"  Delta = {t.get('mean_diff', 0):+.4f}\n")
        f.write(f"  t = {t.get('t', 0):.2f}\n")
        f.write(f"  p = {t.get('p', 1):.6f}\n")
        f.write(f"  Cohen's d = {t.get('cohens_d', 0):.3f}\n")
        f.write(f"  n = {t.get('n', 0)}\n\n")
        t2 = results.get('test_field_vs_std', {})
        f.write(f"Field (alpha=0.60) vs Standard:\n")
        f.write(f"  Delta = {t2.get('mean_diff', 0):+.4f}\n")
        f.write(f"  p = {t2.get('p', 1):.6f}\n")
        f.write(f"  Cohen's d = {t2.get('cohens_d', 0):.3f}\n")
    print("Stats saved to scripts/output/rec_stats.txt")


if __name__ == '__main__':
    main()
