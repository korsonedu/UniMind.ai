#!/usr/bin/env python3
"""Memorix Phase 0 — Real-time Dashboard (3-way: Independent, FSRS, Field)"""
import json, math, time, random, os, sys
from collections import defaultdict
import numpy as np
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

for name in ['PingFang SC', 'Heiti SC', 'STHeiti', 'Arial Unicode MS', 'DejaVu Sans']:
    try:
        fm.findfont(name, fallback_to_default=False)
        FONT = name
        break
    except Exception:
        continue
FONT = FONT if 'FONT' in dir() else 'DejaVu Sans'
plt.rcParams['font.family'] = FONT
from matplotlib.patches import FancyBboxPatch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from memorix_phase0_sim import (
    load_cfa_tree, StudentV2, simulate_student_v2, summary as summarize,
    STUDENT_TYPES,
)

plt.style.use('dark_background')
COLORS = {
    'bg': '#0d1117', 'panel': '#161b22', 'border': '#30363d',
    'indep': '#58a6ff', 'fsrs': '#3fb950', 'field': '#f78166', 'accent': '#7ee787',
    'text': '#c9d1d9', 'dim': '#8b949e',
}

class Dashboard:
    def __init__(self, tree, alphas, boosts):
        self.tree = tree
        self.alphas = sorted(alphas)
        self.boosts = sorted(boosts)
        self.results = {}
        self.progress = 0
        self.total = len(alphas) * len(boosts)
        self.start_time = time.time()
        
        self.fig = plt.figure(figsize=(16, 9), facecolor=COLORS['bg'])
        self.fig.canvas.manager.set_window_title('Memorix Phase 0 — 3-way')
        
        gs = self.fig.add_gridspec(3, 2, height_ratios=[1, 8, 0.5], width_ratios=[1, 1],
                                    hspace=0.3, wspace=0.25)
        self.ax_header = self.fig.add_subplot(gs[0, :]); self.ax_header.axis('off')
        self.ax_curves = self.fig.add_subplot(gs[1, 0], facecolor=COLORS['panel'])
        self.ax_curves.set_xlabel('Days', color=COLORS['dim'], fontsize=9)
        self.ax_curves.set_ylabel('Avg Retention R(t)', color=COLORS['dim'], fontsize=9)
        self.ax_curves.tick_params(colors=COLORS['dim'], labelsize=8)
        self.ax_curves.grid(True, alpha=0.15, color=COLORS['border'])
        for spine in self.ax_curves.spines.values(): spine.set_color(COLORS['border'])
        self.ax_heat = self.fig.add_subplot(gs[1, 1], facecolor=COLORS['panel'])
        self.ax_heat.tick_params(colors=COLORS['dim'], labelsize=8)
        for spine in self.ax_heat.spines.values(): spine.set_color(COLORS['border'])
        self.ax_progress = self.fig.add_subplot(gs[2, :]); self.ax_progress.axis('off')
        self._init_heatmap()
        self._update_header()
        self._draw_progress()
        plt.ion(); self.fig.show(); self.fig.canvas.draw(); self.fig.canvas.flush_events()

    def _init_heatmap(self):
        self.heat_data = np.full((len(self.alphas), len(self.boosts)), np.nan)
        self.ax_heat.clear(); self.ax_heat.set_facecolor(COLORS['panel'])

    def _update_header(self):
        self.ax_header.clear(); self.ax_header.axis('off')
        e = time.time() - self.start_time
        eta = (e / max(self.progress, 1)) * (self.total - self.progress) if self.progress > 0 else 0
        txt = (f"Memorix Phase 0  |  CFA ({self.tree['n_kps']} KPs)  |  "
               f"Done {self.progress}/{self.total}  |  Elapsed {e:.0f}s  |  ETA ~{eta:.0f}s")
        self.ax_header.text(0.01, 0.5, txt, transform=self.ax_header.transAxes,
                           fontsize=11, color=COLORS['accent'], fontfamily='monospace', va='center')

    def _draw_progress(self):
        self.ax_progress.clear(); self.ax_progress.axis('off')
        pct = self.progress / self.total * 100 if self.total > 0 else 0
        bar_bg = FancyBboxPatch((0.02, 0.2), 0.96, 0.5, boxstyle="round,pad=0.02",
                                facecolor=COLORS['border'], edgecolor='none',
                                transform=self.ax_progress.transAxes)
        self.ax_progress.add_patch(bar_bg)
        if pct > 0:
            bar_fill = FancyBboxPatch((0.02, 0.2), 0.96 * pct/100, 0.5,
                                      boxstyle="round,pad=0.02",
                                      facecolor=COLORS['accent'], edgecolor='none', alpha=0.8,
                                      transform=self.ax_progress.transAxes)
            self.ax_progress.add_patch(bar_fill)
        self.ax_progress.text(0.5, 0.45, f'{pct:.0f}%', transform=self.ax_progress.transAxes,
                             ha='center', va='center', fontsize=10, color=COLORS['text'],
                             fontweight='bold')

    def update(self, key, result):
        self.results[key] = result
        self.progress = len(self.results)
        
        ai = self.alphas.index(result['alpha'])
        bi = self.boosts.index(result['boost'])
        d = result['field']['summary']['mean'] - result['independent']['summary']['mean']
        self.heat_data[ai][bi] = d
        
        self.ax_heat.clear(); self.ax_heat.set_facecolor(COLORS['panel'])
        im = self.ax_heat.imshow(self.heat_data, cmap='RdYlGn', aspect='auto',
                                  vmin=-0.05, vmax=0.20, interpolation='nearest')
        self.ax_heat.set_xticks(range(len(self.boosts)))
        self.ax_heat.set_xticklabels([f'b={b:.2f}' for b in self.boosts], fontsize=8)
        self.ax_heat.set_yticks(range(len(self.alphas)))
        self.ax_heat.set_yticklabels([f'a={a:.2f}' for a in self.alphas], fontsize=8)
        for i in range(len(self.alphas)):
            for j in range(len(self.boosts)):
                if not np.isnan(self.heat_data[i][j]):
                    val = self.heat_data[i][j]
                    c = '#7ee787' if val > 0 else '#f85149'
                    self.ax_heat.text(j, i, f'{val:+.3f}', ha='center', va='center',
                                     fontsize=7, color=c, fontweight='bold', fontfamily='monospace')
        if self.progress == 1:
            cbar = plt.colorbar(im, ax=self.ax_heat, fraction=0.046, pad=0.04)
            cbar.set_label('Delta (Field - Independent)', color=COLORS['dim'], fontsize=8)
        
        # Curves: blue=Independent, green=FSRS, red=Field
        self.ax_curves.clear()
        self.ax_curves.set_facecolor(COLORS['panel'])
        self.ax_curves.grid(True, alpha=0.15, color=COLORS['border'])
        self.ax_curves.set_ylabel('Avg Retention', color=COLORS['dim'], fontsize=9)
        self.ax_curves.set_xlabel('Days', color=COLORS['dim'], fontsize=9)
        self.ax_curves.tick_params(colors=COLORS['dim'], labelsize=8)
        for spine in self.ax_curves.spines.values(): spine.set_color(COLORS['border'])
        
        ic = result['independent']['curve']
        fc = result['fsrs']['curve']
        gc = result['field']['curve']
        ts = [p[0] for p in ic]
        self.ax_curves.plot(ts, [p[1] for p in ic], color=COLORS['indep'], linewidth=1.2, alpha=0.6,
                           label='Memorix (greedy)')
        self.ax_curves.plot(ts, [p[1] for p in fc], color=COLORS['fsrs'], linewidth=1.5, alpha=0.7,
                           label='FSRS (SOTA baseline)')
        self.ax_curves.plot(ts, [p[1] for p in gc], color=COLORS['field'], linewidth=2,
                           label='Memorix-Field (global, graph diffusion)')
        
        if len(self.results) > 1:
            best = max(self.results.values(),
                      key=lambda r: r['field']['summary']['mean'] - r['independent']['summary']['mean'])
            bc = best['field']['curve']
            bd = best['field']['summary']['mean'] - best['independent']['summary']['mean']
            self.ax_curves.plot(ts, [p[1] for p in bc], color=COLORS['accent'],
                               linewidth=2.5, linestyle='--', alpha=0.9,
                               label=f'Best Field Δ={bd:+.3f}')
        
        self.ax_curves.legend(loc='lower right', fontsize=8, facecolor=COLORS['panel'],
                             edgecolor=COLORS['border'], labelcolor=COLORS['text'])
        self.ax_curves.set_ylim(0, 1.05)
        self._update_header(); self._draw_progress()
        self.fig.canvas.draw(); self.fig.canvas.flush_events()

    def finish(self):
        self._update_header(); self._draw_progress()
        self.ax_header.clear(); self.ax_header.axis('off')
        e = time.time() - self.start_time
        self.ax_header.text(0.01, 0.5,
                          f"DONE - {self.progress}/{self.total} combos - {e:.0f}s ({e/60:.1f}min) - Close to exit",
                          transform=self.ax_header.transAxes, fontsize=12,
                          color=COLORS['accent'], fontfamily='monospace', va='center', fontweight='bold')
        self.fig.canvas.draw(); self.fig.canvas.flush_events()
        plt.ioff(); plt.show(block=True)


def main():
    alphas = (0.95, 0.9, 0.85, 0.8, 0.7, 0.6)
    boosts = (0.01, 0.02, 0.05, 0.10, 0.15, 0.20)
    students_per = 400
    n_days = 150
    budget = 6

    tree = load_cfa_tree('scripts/cfa_tree.json', heavy=True)
    total_combos = len(alphas) * len(boosts)
    print(f"CFA HEAVY 3-way: {tree['n_kps']} KPs  |  {students_per}×{total_combos}×3 = {students_per*total_combos*3} runs\n")
    
    dash = Dashboard(tree, alphas, boosts)
    types = list(STUDENT_TYPES.keys())
    coverages = [0.4, 0.6, 0.8]
    combo_idx = 0

    for alpha in alphas:
        for boost in boosts:
            key = f"a{alpha:.2f}_b{boost:.2f}"
            combo_idx += 1
            t0 = time.time()

            indep, fsrs_list, field = [], [], []
            for i in range(students_per):
                st = types[i % len(types)]
                cov = coverages[i % len(coverages)]
                seed = hash(key) + i

                s1 = StudentV2(seed, student_type=st, coverage=cov)
                indep.append(simulate_student_v2(tree, s1, 'independent', alpha, boost, n_days, budget, seed=seed))
                s2 = StudentV2(seed + 20000, student_type=st, coverage=cov)
                fsrs_list.append(simulate_student_v2(tree, s2, 'fsrs', alpha, boost, n_days, budget, seed=seed + 20000))
                s3 = StudentV2(seed + 40000, student_type=st, coverage=cov)
                field.append(simulate_student_v2(tree, s3, 'field', alpha, boost, n_days, budget, seed=seed + 40000))

            i_sum = summarize(indep)
            f_sum = summarize(fsrs_list)
            g_sum = summarize(field)
            dt = time.time() - t0

            ts = [p['t'] for p in indep[0]['history']]
            ic = [np.mean([r['history'][j]['avg_R'] for r in indep]) for j in range(len(ts))]
            fc = [np.mean([r['history'][j]['avg_R'] for r in fsrs_list]) for j in range(len(ts))]
            gc = [np.mean([r['history'][j]['avg_R'] for r in field]) for j in range(len(ts))]

            result = {
                'alpha': alpha, 'boost': boost,
                'independent': {'summary': i_sum, 'curve': list(zip(ts, ic))},
                'fsrs': {'summary': f_sum, 'curve': list(zip(ts, fc))},
                'field': {'summary': g_sum, 'curve': list(zip(ts, gc))},
            }

            print(f"  [{combo_idx}/{total_combos}] {key}  ind={i_sum['mean']:.3f}  fsrs={f_sum['mean']:.3f}  field={g_sum['mean']:.3f}  {dt:.0f}s")
            dash.update(key, result)

    os.makedirs('scripts/output', exist_ok=True)
    with open('scripts/output/results_v3.json', 'w') as f:
        json.dump({k: {'alpha': v['alpha'], 'boost': v['boost'],
                       'indep': v['independent']['summary']['mean'],
                       'fsrs': v['fsrs']['summary']['mean'],
                       'field': v['field']['summary']['mean'],
                       'delta_vs_indep': v['field']['summary']['mean'] - v['independent']['summary']['mean'],
                       'delta_vs_fsrs': v['field']['summary']['mean'] - v['fsrs']['summary']['mean']}
                  for k, v in dash.results.items()}, f, indent=2)

    dash.finish()

if __name__ == '__main__':
    main()
