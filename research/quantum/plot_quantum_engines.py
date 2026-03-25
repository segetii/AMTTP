"""
plot_quantum_engines.py — Comparison Plots for Full Engine Benchmark
=====================================================================

Generates 5 publication-quality figures comparing bare BSDT vs the
full Molecular/Gravity/Hybrid engine pipeline on the quantum QPT.

Author: Odeyemi Olusegun Israel
"""
from __future__ import annotations

import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pathlib import Path

# ── Load results ──
RESULTS_DIR = Path(__file__).parent / 'results'


def load_results():
    with open(RESULTS_DIR / 'engine_benchmark.json') as f:
        return json.load(f)


def setup_style():
    plt.rcParams.update({
        'figure.facecolor': '#0d1117',
        'axes.facecolor': '#161b22',
        'axes.edgecolor': '#30363d',
        'axes.labelcolor': '#c9d1d9',
        'text.color': '#c9d1d9',
        'xtick.color': '#8b949e',
        'ytick.color': '#8b949e',
        'grid.color': '#21262d',
        'grid.alpha': 0.6,
        'font.size': 11,
        'axes.titlesize': 13,
        'legend.fontsize': 9,
        'legend.facecolor': '#161b22',
        'legend.edgecolor': '#30363d',
    })


ENGINE_COLORS = {
    'bare_bsdt': '#8b949e',    # grey
    'molecular': '#f97583',    # red/coral
    'gravity':   '#79c0ff',    # blue
    'hybrid':    '#56d364',    # green
}

ENGINE_LABELS = {
    'bare_bsdt': 'Bare BSDT',
    'molecular': 'Molecular (LJ 6-12)',
    'gravity':   'Gravity (erf/log)',
    'hybrid':    'Hybrid (CV blend)',
}


# ═══════════════════════════════════════════════════════════════════
#  Figure 11: Engine Scores (raw) Comparison
# ═══════════════════════════════════════════════════════════════════

def fig11_engine_scores(data):
    """Raw engine scores across h/J for N=12."""
    r = data['detailed_N12']
    h = np.array(r['h_vals'])
    engines = r['engines']

    fig, ax = plt.subplots(figsize=(10, 5))

    for name in ['bare_bsdt', 'molecular', 'gravity', 'hybrid']:
        eng = engines[name]
        if 'error' in eng:
            continue
        scores = np.array(eng['scores'])
        ax.plot(h, scores, color=ENGINE_COLORS[name],
                label=ENGINE_LABELS[name], linewidth=1.8, alpha=0.9)

    ax.axvline(1.0, color='#ffa657', linestyle='--', alpha=0.6,
               label=r'$h_c/J = 1$')
    ax.axvspan(0.85, 1.15, alpha=0.08, color='#ffa657')

    ax.set_xlabel(r'$h/J$')
    ax.set_ylabel('Anomaly Score')
    ax.set_title('Engine Scores — N = 12 Qubits')
    ax.legend(loc='upper left')
    ax.grid(True)

    fig.tight_layout()
    fig.savefig(RESULTS_DIR / 'plots' / 'fig11_engine_scores.png',
                dpi=180, bbox_inches='tight')
    plt.close(fig)
    print("  fig11_engine_scores.png")


# ═══════════════════════════════════════════════════════════════════
#  Figure 12: Engine MFLS — critical peak localization
# ═══════════════════════════════════════════════════════════════════

def fig12_engine_mfls(data):
    """MFLS = |d(score)/dh| — peak localization comparison."""
    r = data['detailed_N12']
    h = np.array(r['h_vals'])
    engines = r['engines']

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Left: all engines MFLS
    ax = axes[0]
    for name in ['bare_bsdt', 'molecular', 'gravity', 'hybrid']:
        eng = engines[name]
        if 'error' in eng:
            continue
        mfls = np.array(eng['mfls'])
        # Normalise to [0, 1] for comparison
        mfls_n = mfls / (mfls.max() + 1e-10)
        ax.plot(h, mfls_n, color=ENGINE_COLORS[name],
                label=ENGINE_LABELS[name], linewidth=1.8, alpha=0.9)

    ax.axvline(1.0, color='#ffa657', linestyle='--', alpha=0.6,
               label=r'$h_c/J = 1$')
    ax.axvspan(0.85, 1.15, alpha=0.08, color='#ffa657')
    ax.set_xlabel(r'$h/J$')
    ax.set_ylabel('MFLS (normalised)')
    ax.set_title('MFLS Peak Localisation — N = 12')
    ax.legend(loc='upper right', fontsize=8)
    ax.grid(True)

    # Right: peak location comparison across sizes
    ax = axes[1]
    sizes = sorted(data['multi_size'].keys(), key=int)
    engine_names = ['bare_bsdt', 'molecular', 'gravity', 'hybrid']
    bar_width = 0.18
    x = np.arange(len(sizes))

    for i, name in enumerate(engine_names):
        peaks = []
        for s in sizes:
            eng = data['multi_size'][s]['engines'].get(name, {})
            peaks.append(eng.get('peak_h', 0))
        ax.bar(x + i * bar_width, peaks, bar_width,
               color=ENGINE_COLORS[name], label=ENGINE_LABELS[name],
               alpha=0.85)

    ax.axhline(1.0, color='#ffa657', linestyle='--', alpha=0.6,
               label=r'$h_c/J = 1$ (exact)')
    ax.set_xlabel('System Size N')
    ax.set_ylabel('MFLS Peak Location h/J')
    ax.set_title('Peak Localisation vs System Size')
    ax.set_xticks(x + 1.5 * bar_width)
    ax.set_xticklabels([f'N={s}' for s in sizes])
    ax.legend(loc='lower right', fontsize=7)
    ax.set_ylim(0, 1.5)
    ax.grid(True, axis='y')

    fig.tight_layout()
    fig.savefig(RESULTS_DIR / 'plots' / 'fig12_engine_mfls.png',
                dpi=180, bbox_inches='tight')
    plt.close(fig)
    print("  fig12_engine_mfls.png")


# ═══════════════════════════════════════════════════════════════════
#  Figure 13: AUC Scaling — Multi-size comparison
# ═══════════════════════════════════════════════════════════════════

def fig13_auc_scaling(data):
    """AUC_crit vs system size for each engine."""
    sizes = sorted(data['multi_size'].keys(), key=int)
    Ns = [int(s) for s in sizes]

    fig, ax = plt.subplots(figsize=(9, 5))

    engine_names = ['bare_bsdt', 'molecular', 'gravity', 'hybrid']
    for name in engine_names:
        aucs = []
        for s in sizes:
            eng = data['multi_size'][s]['engines'].get(name, {})
            aucs.append(eng.get('auc_mfls_crit', float('nan')))
        ax.plot(Ns, aucs, 'o-', color=ENGINE_COLORS[name],
                label=ENGINE_LABELS[name], linewidth=2, markersize=8)

    ax.axhline(1.0, color='#ffa657', linestyle=':', alpha=0.4)
    ax.set_xlabel('System Size N')
    ax.set_ylabel('MFLS AUC (critical region)')
    ax.set_title('Detection Quality vs System Size')
    ax.legend()
    ax.set_ylim(0.7, 1.02)
    ax.grid(True)

    fig.tight_layout()
    fig.savefig(RESULTS_DIR / 'plots' / 'fig13_auc_scaling.png',
                dpi=180, bbox_inches='tight')
    plt.close(fig)
    print("  fig13_auc_scaling.png")


# ═══════════════════════════════════════════════════════════════════
#  Figure 14: Morse Index & Convergence
# ═══════════════════════════════════════════════════════════════════

def fig14_morse_convergence(data):
    """Morse index and convergence diagnostics across sizes."""
    sizes = sorted(data['multi_size'].keys(), key=int)
    Ns = [int(s) for s in sizes]

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # Left: Morse index
    ax = axes[0]
    for name in ['molecular', 'gravity']:
        indices = []
        for s in sizes:
            eng = data['multi_size'][s]['engines'].get(name, {})
            indices.append(eng.get('morse_index', 0))
        ax.plot(Ns, indices, 's-', color=ENGINE_COLORS[name],
                label=ENGINE_LABELS[name], linewidth=2, markersize=10)

    ax.set_xlabel('System Size N')
    ax.set_ylabel('Morse Index (ind)')
    ax.set_title('Morse Topology Alarm')
    ax.legend()
    ax.grid(True)
    ax.set_ylim(0, max(7, max(
        max(data['multi_size'][s]['engines'].get('gravity', {}).get(
            'morse_index', 0) for s in sizes),
        max(data['multi_size'][s]['engines'].get('molecular', {}).get(
            'morse_index', 0) for s in sizes)
    ) + 1))

    # Add annotation
    ax.annotate('ind ≥ 1 → saddle → QPT detected',
                xy=(Ns[0], 1), fontsize=9, color='#ffa657',
                arrowprops=dict(arrowstyle='->', color='#ffa657'),
                xytext=(Ns[0] + 1.5, 0.5))

    # Right: engine comparison radar (summary metrics for N=14)
    ax = axes[1]
    best = data['multi_size'][str(max(Ns))]

    metrics = ['MFLS AUC', 'Score AUC', 'Peak Acc.', 'Morse det.']
    engine_names = ['bare_bsdt', 'molecular', 'gravity', 'hybrid']

    bar_data = []
    for name in engine_names:
        eng = best['engines'].get(name, {})
        mfls_auc = eng.get('auc_mfls_crit', 0)
        score_auc = eng.get('auc_score_crit', 0)
        peak_acc = 1.0 - eng.get('peak_error', 1.0)
        morse_det = 1.0 if eng.get('morse_alarm', False) else 0.0
        bar_data.append([mfls_auc, score_auc, peak_acc, morse_det])

    bar_data = np.array(bar_data)
    x = np.arange(len(metrics))
    bar_w = 0.18

    for i, name in enumerate(engine_names):
        ax.bar(x + i * bar_w, bar_data[i], bar_w,
               color=ENGINE_COLORS[name], label=ENGINE_LABELS[name],
               alpha=0.85)

    ax.set_xticks(x + 1.5 * bar_w)
    ax.set_xticklabels(metrics, fontsize=9)
    ax.set_ylabel('Score [0, 1]')
    ax.set_title(f'Engine Metrics Summary — N = {max(Ns)}')
    ax.legend(fontsize=7, loc='upper left')
    ax.grid(True, axis='y')
    ax.set_ylim(0, 1.1)

    fig.tight_layout()
    fig.savefig(RESULTS_DIR / 'plots' / 'fig14_morse_convergence.png',
                dpi=180, bbox_inches='tight')
    plt.close(fig)
    print("  fig14_morse_convergence.png")


# ═══════════════════════════════════════════════════════════════════
#  Figure 15: Grand Comparison — All engines + Original 22 methods
# ═══════════════════════════════════════════════════════════════════

def fig15_grand_comparison(data):
    """Bar chart comparing engine MFLS AUC with the extended benchmark."""
    # Load extended benchmark for comparison
    ext_path = RESULTS_DIR / 'extended_benchmark.json'
    if not ext_path.exists():
        print("  (skipping fig15 — extended_benchmark.json not found)")
        return

    with open(ext_path) as f:
        ext = json.load(f)

    # Get engine results for N=12 (to match original benchmark)
    r12 = data['multi_size']['12']
    eng12 = r12['engines']

    # Build comparison data
    methods = []
    aucs = []
    colors = []

    # Add original benchmark methods (top 10)
    orig = ext.get('methods', [])
    # Sort by AUC descending
    orig_sorted = sorted(orig, key=lambda m: m.get('auc_crit', 0),
                         reverse=True)

    for m in orig_sorted[:10]:
        methods.append(m['name'][:20])
        aucs.append(m.get('auc_crit', 0))
        colors.append('#58a6ff')  # blue for benchmark methods

    # Add our engine MFLS results
    engine_entries = [
        ('MFLS (Bare)', eng12.get('bare_bsdt', {}).get('auc_mfls_crit', 0)),
        ('MFLS (Molecular)', eng12.get('molecular', {}).get('auc_mfls_crit', 0)),
        ('MFLS (Gravity)', eng12.get('gravity', {}).get('auc_mfls_crit', 0)),
        ('MFLS (Hybrid)', eng12.get('hybrid', {}).get('auc_mfls_crit', 0)),
    ]

    for name, auc in engine_entries:
        methods.append(name)
        aucs.append(auc)
        if 'Bare' in name:
            colors.append(ENGINE_COLORS['bare_bsdt'])
        elif 'Molecular' in name:
            colors.append(ENGINE_COLORS['molecular'])
        elif 'Gravity' in name:
            colors.append(ENGINE_COLORS['gravity'])
        else:
            colors.append(ENGINE_COLORS['hybrid'])

    # Sort all by AUC
    order = np.argsort(aucs)[::-1]
    methods = [methods[i] for i in order]
    aucs = [aucs[i] for i in order]
    colors = [colors[i] for i in order]

    fig, ax = plt.subplots(figsize=(12, 6))
    y = np.arange(len(methods))
    bars = ax.barh(y, aucs, color=colors, alpha=0.85, height=0.7)

    # Highlight our engines
    for i, (m, a) in enumerate(zip(methods, aucs)):
        if 'MFLS' in m and ('Molecular' in m or 'Gravity' in m or
                            'Hybrid' in m):
            ax.barh(i, a, color=colors[i], alpha=1.0, height=0.7,
                    edgecolor='white', linewidth=1.5)

    ax.set_yticks(y)
    ax.set_yticklabels(methods, fontsize=8)
    ax.set_xlabel('AUC (critical region)')
    ax.set_title('Grand Comparison: All Methods + BSDT Engines — N = 12')
    ax.invert_yaxis()
    ax.grid(True, axis='x')
    ax.set_xlim(0.5, 1.02)

    fig.tight_layout()
    fig.savefig(RESULTS_DIR / 'plots' / 'fig15_grand_comparison.png',
                dpi=180, bbox_inches='tight')
    plt.close(fig)
    print("  fig15_grand_comparison.png")


# ═══════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════

def main():
    setup_style()
    data = load_results()

    plots_dir = RESULTS_DIR / 'plots'
    plots_dir.mkdir(exist_ok=True)

    print("\nGenerating engine comparison plots...")
    fig11_engine_scores(data)
    fig12_engine_mfls(data)
    fig13_auc_scaling(data)
    fig14_morse_convergence(data)
    fig15_grand_comparison(data)
    print("\nAll plots saved to", plots_dir)


if __name__ == '__main__':
    main()
