#!/usr/bin/env python3
"""arXiv-quality figure: retention curves + final comparison."""
import json, numpy as np, matplotlib, os, sys, random
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from memorix_phase0_sim import load_cfa_tree, StudentV2, simulate_student_v2, summary, STUDENT_TYPES

plt.rcParams.update({
    'font.family': 'sans-serif', 'font.size': 10,
    'axes.labelsize': 11, 'axes.titlesize': 12,
    'figure.dpi': 300, 'savefig.dpi': 300,
})

C_INDEP = '#0072B2'
C_FSRS  = '#009E73'
C_FIELD = '#D55E00'

# Best params
ALPHA, BOOST = 0.60, 0.20
N_STUDENTS = 50
N_DAYS = 150
BUDGET = 6

tree = load_cfa_tree('scripts/cfa_tree.json', heavy=True)
types = list(STUDENT_TYPES.keys())

# Run students with daily snapshot
histories = {'Memorix (greedy)': [], 'FSRS': [], 'Memorix-Field': []}

for i in range(N_STUDENTS):
    st = types[i % 4]
    cov = [0.4, 0.6, 0.8][i % 3]
    seed = i
    
    for label, sched in [('Memorix (greedy)', 'independent'), ('FSRS', 'fsrs'), ('Memorix-Field', 'field')]:
        s = StudentV2(seed, student_type=st, coverage=cov)
        r = simulate_student_v2(tree, s, sched, ALPHA, BOOST, N_DAYS, BUDGET, seed=seed)
        histories[label].append(r['history'])

# Aggregate
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.5))

for label, color in [('Memorix (greedy)', C_INDEP), ('FSRS', C_FSRS), ('Memorix-Field', C_FIELD)]:
    hs = histories[label]
    n_days = len(histories[label][0])
    ts = [h['day'] for h in hs[0]]  # use 'day' field, not 't' (hours)
    means, stds = [], []
    for j in range(n_days):
        vals = [h[j]['avg_R'] for h in hs]
        means.append(np.mean(vals))
        stds.append(np.std(vals, ddof=1))
    means, stds = np.array(means), np.array(stds)
    
    lw = 2.8 if label == 'Memorix-Field' else 1.8
    ax1.plot(ts, means, color=color, linewidth=lw, label=label, zorder=3 if label == 'Memorix-Field' else 2)
    ax1.fill_between(ts, np.clip(means-stds, 0, 1), np.clip(means+stds, 0, 1),
                     color=color, alpha=0.12)

# Annotate final values
for label, color, offset in [('FSRS', C_FSRS, -0.045),
                              ('Memorix (greedy)', C_INDEP, -0.015),
                              ('Memorix-Field', C_FIELD, +0.015)]:
    final = np.mean([h[-1]['avg_R'] for h in histories[label]])
    ax1.annotate(f'{final:.3f}', xy=(ts[-1], final),
                xytext=(ts[-1]+8, final+offset), fontsize=9, color=color, fontweight='bold',
                arrowprops=dict(arrowstyle='->', color=color, lw=0.8))

ax1.set_xlabel('Days')
ax1.set_ylabel('Average Retention R(t)')
ax1.set_title('(a) Retention Curves', fontweight='bold')
ax1.legend(loc='lower right', framealpha=0.9)
ax1.set_ylim(0.35, 0.80)
ax1.set_xlim(0, ts[-1])
ax1.xaxis.set_major_locator(MultipleLocator(30))
ax1.yaxis.set_major_locator(MultipleLocator(0.10))
ax1.grid(True, alpha=0.25, linestyle='--')
ax1.spines['top'].set_visible(False)
ax1.spines['right'].set_visible(False)

# ── Panel B: R(150) bar chart with exact values ──
with open('scripts/output/results_v3.json') as f:
    data = json.load(f)
best = data['a0.60_b0.20']

labels_bar = ['Memorix\n(greedy)', 'FSRS', 'Memorix-Field']
values = [best['indep'], best['fsrs'], best['field']]
colors_bar = [C_INDEP, C_FSRS, C_FIELD]

x = np.arange(3)
bars = ax2.bar(x, values, 0.4, color=colors_bar, edgecolor='white', linewidth=0.5)

for bar, val in zip(bars, values):
    ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.01,
             f'{val:.3f}', ha='center', va='bottom', fontsize=11, fontweight='bold')

# Delta bracket
ax2.annotate('', xy=(2, values[2]+0.02), xytext=(1, values[1]+0.02),
            arrowprops=dict(arrowstyle='<->', color='#555', lw=1.5, connectionstyle='bar,fraction=0.2'))
mid = (values[1] + values[2])/2
ax2.text(1.5, mid+0.04, f'+{best["delta_vs_fsrs"]*100:.1f}%', ha='center',
        fontsize=11, fontweight='bold', color='#333')

ax2.set_xticks(x)
ax2.set_xticklabels(labels_bar, fontsize=10)
ax2.set_ylabel('Retention R(150)')
ax2.set_title(f'(b) Day 150  (alpha={ALPHA}, beta={BOOST})', fontweight='bold')
ax2.set_ylim(0, 0.80)
ax2.spines['top'].set_visible(False)
ax2.spines['right'].set_visible(False)
ax2.grid(True, alpha=0.25, linestyle='--', axis='y')

plt.tight_layout()
out = 'scripts/output/memorix_field_final.png'
plt.savefig(out, dpi=300, facecolor='white')
plt.close()
print(f'Saved: {out}')
