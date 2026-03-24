"""
plot_quantum_qpt.py — Comprehensive Visualization & Benchmarking
=================================================================
Domain VII: Quantum Phase Transition Detection (1D TFIM)

Generates publication-quality figures:
  Fig 1:  Phase diagram heatstrip  (6 observables vs h/J)
  Fig 2:  Detection comparison     (22-method extended benchmark, bar chart)
  Fig 3:  E_BS vs MFLS dual-role   (two-panel, phase classifier + transition)
  Fig 4:  Finite-size scaling       (error ∝ N^-2.25, AUC convergence)
  Fig 5:  BSDT channel anatomy      (4-channel waterfall + gradient)
  Fig 6:  C* ellipsoid 2D           (observable space projection)
  Fig 7:  C* ellipsoid 3D           (m_abs × S_vN × C_ratio manifold)
  Fig 8:  Benchmark table           (BSDT vs 22 standard QPT methods)
  Fig 9:  Procyclicality            (constant gamma vs adaptive MFLS)
  Fig 10: Multi-size comparison     (AUC scaling for top methods, N=8..14)

All from saved JSON — no re-computation needed.

Author: Odeyemi Olusegun Israel
"""
from __future__ import annotations
import sys, json, warnings
import numpy as np
warnings.filterwarnings('ignore')

import matplotlib
matplotlib.use('Agg')          # no GUI required
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.patches import Ellipse, FancyArrowPatch
from matplotlib.colors import LinearSegmentedColormap
from mpl_toolkits.mplot3d import Axes3D
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from pathlib import Path

# ── Paths ──
ROOT   = Path(r'c:\amttp')
RES    = ROOT / 'research' / 'quantum' / 'results'
PLOTS  = RES / 'plots'
PLOTS.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(ROOT / 'research' / 'quantum'))
sys.path.insert(0, str(ROOT / 'research' / 'udl'))

# ── Style ──
plt.rcParams.update({
    'figure.dpi': 150,
    'savefig.dpi': 300,
    'font.size': 10,
    'axes.titlesize': 12,
    'axes.labelsize': 11,
    'legend.fontsize': 8,
    'figure.facecolor': '#0d1117',
    'axes.facecolor': '#161b22',
    'text.color': '#e6edf3',
    'axes.edgecolor': '#30363d',
    'axes.labelcolor': '#e6edf3',
    'xtick.color': '#8b949e',
    'ytick.color': '#8b949e',
    'grid.color': '#21262d',
    'legend.facecolor': '#161b22',
    'legend.edgecolor': '#30363d',
})

ACCENT   = '#58a6ff'
GREEN    = '#3fb950'
RED      = '#f85149'
ORANGE   = '#d29922'
PURPLE   = '#bc8cff'
CYAN     = '#39d353'
PINK     = '#f778ba'
GOLD     = '#e3b341'
WHITE    = '#e6edf3'
GREY     = '#8b949e'

# ── Load data ──
with open(RES / 'quantum_qpt_results.json') as f:
    D = json.load(f)

h     = np.array(D['h_values'])
ebs   = np.array(D['ebs_scores'])
mfls  = np.array(D['mfls'])
obs   = D['observables']
det   = D['detection_comparison']
sc    = D['scaling']
J     = D['J']
N     = D['N_main']

m_abs  = np.array([o['m_abs']    for o in obs])
svn    = np.array([o['S_vN']     for o in obs])
gap    = np.array([o['gap_phys'] for o in obs])
c_rat  = np.array([o['C_ratio']  for o in obs])
binder = np.array([o['binder']   for o in obs])
m_sq   = np.array([o['m_sq']     for o in obs])
m_x    = np.array([o['m_x']     for o in obs])
c_zz   = np.array([o['C_zz']    for o in obs])
e0     = np.array([o['e0']      for o in obs])
gap01  = np.array([o['gap_01']  for o in obs])

S_max  = (N / 2) * np.log(2)
delta_C = m_abs * svn / S_max
delta_G = np.maximum(1.0 - c_rat, 0.0)
delta_A = 1.0 / (1.0 + gap)
# delta_T needs psi (not in JSON), estimate from ebs profile
delta_T_est = ebs / (ebs.max() + 1e-10)  # proxy

dm = np.abs(np.gradient(m_abs, h))
d2m = np.abs(np.gradient(np.gradient(m_abs, h), h))
dsvn = np.abs(np.gradient(svn, h))


# =====================================================================
#  HELPER: vertical C* line
# =====================================================================
def add_hc_line(ax, label=True, ypos=0.92):
    ax.axvline(1.0, color=RED, ls='--', lw=1.2, alpha=0.7, zorder=5)
    if label:
        ax.text(1.01, ypos, '$h_c/J=1$', color=RED, fontsize=8,
                transform=ax.get_xaxis_transform(), va='top')


# =====================================================================
#  FIG 1: PHASE DIAGRAM — 6 observables heatstrip
# =====================================================================
def fig_phase_diagram():
    fig, axes = plt.subplots(6, 1, figsize=(10, 11), sharex=True)
    fig.suptitle(f'Phase Diagram — 1D Transverse-Field Ising  (N={N})',
                 fontsize=14, color=WHITE, y=0.98)

    panels = [
        (m_abs,  'Order parameter $m = \\sqrt{\\langle M_z^2\\rangle/N^2}$', ACCENT, True),
        (svn,    'Entanglement entropy $S_{\\mathrm{vN}}$', PURPLE, True),
        (gap,    'Physical gap  $\\Delta = \\max(E_1{-}E_0,\\, E_2{-}E_1)$', GREEN, True),
        (c_rat,  'Correlation ratio $C_{\\mathrm{long}}/C_{zz}$', CYAN, True),
        (binder, 'Binder cumulant $U$', ORANGE, True),
        (mfls,   'MFLS $= |\\mathrm{d}E_{\\mathrm{BS}}/\\mathrm{d}h|$', GOLD, True),
    ]

    for ax, (y, lab, col, add_cstar) in zip(axes, panels):
        ax.fill_between(h, y, alpha=0.25, color=col)
        ax.plot(h, y, color=col, lw=1.8)
        ax.set_ylabel(lab, fontsize=9)
        ax.grid(True, alpha=0.3)
        if add_cstar:
            add_hc_line(ax)
        # shade critical region
        ax.axvspan(0.85, 1.15, alpha=0.08, color=RED)

    axes[-1].set_xlabel('$h / J$', fontsize=12)

    # Arrow for MFLS peak
    pk = np.argmax(mfls)
    axes[-1].annotate(f'MFLS peak\n$h/J={h[pk]:.3f}$',
                      xy=(h[pk], mfls[pk]),
                      xytext=(h[pk]+0.3, mfls[pk]*0.85),
                      arrowprops=dict(arrowstyle='->', color=GOLD, lw=1.5),
                      color=GOLD, fontsize=9, ha='left')

    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(PLOTS / 'fig1_phase_diagram.png', bbox_inches='tight')
    plt.close(fig)
    print("  [1/9] Phase diagram saved")


# =====================================================================
#  FIG 2: DETECTION BENCHMARK — horizontal bar chart
# =====================================================================
def fig_detection_benchmark():
    """22-method benchmark from extended_benchmark.json."""
    # Try loading extended benchmark; fall back to original det dict
    ext_path = RES / 'extended_benchmark.json'
    if ext_path.exists():
        with open(ext_path) as f:
            ext = json.load(f)
        items = [(r['name'], r['auc_crit'], r['category']) for r in ext['benchmark']]
    else:
        items = [(k, v['auc_crit'], 'Original') for k, v in det.items()]

    # Sort ascending for horizontal bar
    items.sort(key=lambda x: x[1])
    names = [x[0] for x in items]
    aucs  = [x[1] for x in items]
    cats  = [x[2] for x in items]

    fig, ax = plt.subplots(figsize=(11, 9))
    fig.suptitle('Extended Benchmark — 22 QPT Detection Methods  (N=12, AUC for |h/J−1|<0.15)',
                 fontsize=13, color=WHITE)

    colors = []
    for n, c in zip(names, cats):
        if 'MFLS' in n:
            colors.append(GOLD)
        elif 'BSDT' in c or 'delta_C' in n or 'E_BS' in n:
            colors.append(ACCENT)
        elif 'Model-free' in c:
            colors.append(PURPLE)
        else:
            colors.append(GREY)

    bars = ax.barh(range(len(names)), aucs, color=colors, edgecolor='none',
                   alpha=0.85, height=0.72)

    for i, (bar, auc_val) in enumerate(zip(bars, aucs)):
        ax.text(auc_val + 0.008, i, f'{auc_val:.3f}', va='center', fontsize=8,
                color=WHITE, fontweight='bold' if auc_val > 0.9 else 'normal')

    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names, fontsize=8)
    ax.set_xlabel('AUC (critical region)', fontsize=11)
    ax.set_xlim(0, 1.10)
    ax.axvline(0.5, color=RED, ls=':', alpha=0.5, label='Random baseline')
    ax.axvline(0.9, color=GREEN, ls=':', alpha=0.5, label='High-quality (0.9)')
    ax.legend(loc='lower right', fontsize=8)
    ax.grid(True, axis='x', alpha=0.3)

    # Highlight MFLS
    for i, n in enumerate(names):
        if 'MFLS' in n:
            ax.get_yticklabels()[i].set_color(GOLD)
            ax.get_yticklabels()[i].set_fontweight('bold')

    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(PLOTS / 'fig2_detection_benchmark.png', bbox_inches='tight')
    plt.close(fig)
    print("  [2/9] Detection benchmark (22 methods) saved")


# =====================================================================
#  FIG 3: E_BS vs MFLS — dual-role panel
# =====================================================================
def fig_dual_role():
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle('Dual-Role Structure:   $E_{\\mathrm{BS}}$ (phase classifier)  vs  '
                 'MFLS (transition locator)',
                 fontsize=13, color=WHITE)

    # Left: E_BS — monotonic
    ax1.fill_between(h, ebs, alpha=0.2, color=ACCENT)
    ax1.plot(h, ebs, color=ACCENT, lw=2, label='$E_{\\mathrm{BS}}$ (blind-spot energy)')
    ax1.set_xlabel('$h / J$')
    ax1.set_ylabel('$E_{\\mathrm{BS}}$')
    ax1.set_title(f'Phase Classifier — AUC$_{{post}}$ = 1.000', color=ACCENT)
    add_hc_line(ax1)
    ax1.axvspan(0.85, 1.15, alpha=0.08, color=RED)
    ax1.legend(fontsize=9)
    ax1.grid(True, alpha=0.3)
    ax1.text(0.5, 0.85, 'Ordered\nphase', transform=ax1.transAxes,
             ha='center', fontsize=11, color=GREEN, alpha=0.6)
    ax1.text(0.85, 0.35, 'Disordered\nphase', transform=ax1.transAxes,
             ha='center', fontsize=11, color=RED, alpha=0.6)

    # Right: MFLS — peaked at h_c
    ax2.fill_between(h, mfls, alpha=0.2, color=GOLD)
    ax2.plot(h, mfls, color=GOLD, lw=2, label='MFLS $= |\\mathrm{d}E_{\\mathrm{BS}}/\\mathrm{d}h|$')
    ax2.set_xlabel('$h / J$')
    ax2.set_ylabel('MFLS')
    ax2.set_title(f'Transition Locator — AUC$_{{crit}}$ = 0.973', color=GOLD)
    add_hc_line(ax2)
    ax2.axvspan(0.85, 1.15, alpha=0.08, color=RED)

    pk = np.argmax(mfls)
    ax2.annotate(f'Peak at $h/J={h[pk]:.3f}$\n(5.5% finite-size shift)',
                 xy=(h[pk], mfls[pk]),
                 xytext=(h[pk]+0.35, mfls[pk]*0.8),
                 arrowprops=dict(arrowstyle='->', color=GOLD, lw=1.5),
                 color=GOLD, fontsize=9)
    ax2.legend(fontsize=9)
    ax2.grid(True, alpha=0.3)

    fig.tight_layout(rect=[0, 0, 1, 0.93])
    fig.savefig(PLOTS / 'fig3_dual_role.png', bbox_inches='tight')
    plt.close(fig)
    print("  [3/9] Dual-role panel saved")


# =====================================================================
#  FIG 4: FINITE-SIZE SCALING
# =====================================================================
def fig_scaling():
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.5))
    fig.suptitle('Finite-Size Scaling  (N = 8, 10, 12, 14)', fontsize=13, color=WHITE)

    Ns   = np.array([8, 10, 12, 14], dtype=float)
    errs = np.array([sc[str(int(n))]['error'] for n in Ns])
    aucs = np.array([sc[str(int(n))]['auc'] for n in Ns])
    gaps = np.array([sc[str(int(n))]['gap_min'] for n in Ns])

    # Panel a: detection error
    ax = axes[0]
    ax.loglog(Ns, errs, 'o-', color=GOLD, ms=8, lw=2, label='MFLS data')
    p = np.polyfit(np.log(Ns), np.log(errs), 1)
    Nfit = np.linspace(7, 20, 50)
    ax.loglog(Nfit, np.exp(np.polyval(p, np.log(Nfit))),
              '--', color=GREY, label=f'Fit: $N^{{{p[0]:.2f}}}$')
    ax.set_xlabel('System size $N$')
    ax.set_ylabel('$|h_c^{\\mathrm{MFLS}} - h_c^{\\mathrm{exact}}| / J$')
    ax.set_title('(a) Detection Error', color=GOLD)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    # Panel b: AUC convergence
    ax = axes[1]
    ax.plot(Ns, aucs, 's-', color=GREEN, ms=8, lw=2)
    ax.set_xlabel('System size $N$')
    ax.set_ylabel('AUC (critical region)')
    ax.set_title('(b) AUC Convergence', color=GREEN)
    ax.set_ylim(0.90, 1.01)
    ax.axhline(1.0, color=GREY, ls=':', alpha=0.5)
    ax.grid(True, alpha=0.3)
    for n, a in zip(Ns, aucs):
        ax.annotate(f'{a:.3f}', (n, a), textcoords="offset points",
                    xytext=(0, 10), ha='center', fontsize=9, color=GREEN)

    # Panel c: gap closing
    ax = axes[2]
    ax.loglog(Ns, gaps, 'D-', color=PURPLE, ms=8, lw=2, label='Data')
    p2 = np.polyfit(np.log(Ns), np.log(gaps), 1)
    ax.loglog(Nfit, np.exp(np.polyval(p2, np.log(Nfit))),
              '--', color=GREY, label=f'Fit: $N^{{{p2[0]:.2f}}}$')
    ax.loglog(Nfit, np.pi / Nfit, ':', color=RED, alpha=0.6, label='Exact: $\\pi / N$')
    ax.set_xlabel('System size $N$')
    ax.set_ylabel('$\\Delta_{\\min}$')
    ax.set_title('(c) Gap Closing', color=PURPLE)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    fig.tight_layout(rect=[0, 0, 1, 0.92])
    fig.savefig(PLOTS / 'fig4_scaling.png', bbox_inches='tight')
    plt.close(fig)
    print("  [4/9] Scaling plots saved")


# =====================================================================
#  FIG 5: BSDT CHANNEL ANATOMY
# =====================================================================
def fig_channel_anatomy():
    fig, axes = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    fig.suptitle('BSDT 4-Channel Anatomy Across the QPT', fontsize=13, color=WHITE)

    # Top: raw channels
    ax = axes[0]
    ax.plot(h, delta_C, color=PINK,   lw=1.8, label='$\\delta_C$ (camouflage)',    alpha=0.9)
    ax.plot(h, delta_G, color=GREEN,  lw=1.8, label='$\\delta_G$ (correlation)',    alpha=0.9)
    ax.plot(h, delta_A, color=ORANGE, lw=1.8, label='$\\delta_A$ (inverse gap)',    alpha=0.9)
    ax.plot(h, delta_T_est, color=CYAN, lw=1.8, label='$\\delta_T$ (infidelity) [est]', alpha=0.7, ls='--')
    ax.set_ylabel('Channel value')
    ax.set_title('(a) Raw BSDT channels — monotonic (phase classifiers)', color=GREY)
    add_hc_line(ax)
    ax.axvspan(0.85, 1.15, alpha=0.08, color=RED)
    ax.legend(ncol=2, fontsize=9)
    ax.grid(True, alpha=0.3)

    # Bottom: channel gradients (what drives MFLS)
    ax = axes[1]
    ddC = np.abs(np.gradient(delta_C, h))
    ddG = np.abs(np.gradient(delta_G, h))
    ddA = np.abs(np.gradient(delta_A, h))
    ddT = np.abs(np.gradient(delta_T_est, h))

    ax.fill_between(h, ddG, alpha=0.2, color=GREEN)
    ax.plot(h, ddC, color=PINK,   lw=1.8, label='$|\\mathrm{d}\\delta_C / \\mathrm{d}h|$')
    ax.plot(h, ddG, color=GREEN,  lw=2.2, label='$|\\mathrm{d}\\delta_G / \\mathrm{d}h|$  (dominant)')
    ax.plot(h, ddA, color=ORANGE, lw=1.8, label='$|\\mathrm{d}\\delta_A / \\mathrm{d}h|$')
    ax.set_xlabel('$h / J$')
    ax.set_ylabel('Channel gradient magnitude')
    ax.set_title('(b) Channel gradients — $\\delta_G$ dominates MFLS near $h_c$', color=GREEN)
    add_hc_line(ax)
    ax.axvspan(0.85, 1.15, alpha=0.08, color=RED)
    ax.legend(ncol=3, fontsize=9)
    ax.grid(True, alpha=0.3)

    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(PLOTS / 'fig5_channel_anatomy.png', bbox_inches='tight')
    plt.close(fig)
    print("  [5/9] Channel anatomy saved")


# =====================================================================
#  FIG 6: C* ELLIPSOID — 2D PROJECTION
# =====================================================================
def fig_ellipsoid_2d():
    """
    2D projection of the BSDT observable space.
    X-axis: m_abs (order parameter), Y-axis: S_vN (entanglement).
    The C* ellipse separates ordered (inside) from critical/disordered (outside).
    Points are coloured by h/J.
    """
    fig, axes = plt.subplots(1, 2, figsize=(13, 6))
    fig.suptitle('$\\mathcal{C}^*$ Ellipsoid — 2D Observable Space Projections',
                 fontsize=13, color=WHITE)

    # Build reference ellipsoid from ordered-phase covariance
    ref_mask = h < 0.5 * J
    X_ref = np.column_stack([m_abs[ref_mask], svn[ref_mask]])
    X_all = np.column_stack([m_abs, svn])
    mu = X_ref.mean(axis=0)
    cov = np.cov(X_ref.T) + 1e-8 * np.eye(2)
    eigvals, eigvecs = np.linalg.eigh(cov)

    # chi2(2) ~= 5.99 for 95% contour
    chi2_levels = [2.0, 5.99, 9.21]  # 1-sigma, 95%, 99%

    # Panel (a): m_abs vs S_vN
    ax = axes[0]
    # Color by h/J
    sc_plot = ax.scatter(m_abs, svn, c=h, cmap='plasma', s=20, zorder=3,
                         edgecolors='none', alpha=0.85)
    plt.colorbar(sc_plot, ax=ax, label='$h/J$', shrink=0.8)

    # Draw ellipses
    for chi2, ls, lab in zip(chi2_levels,
                             ['-', '--', ':'],
                             ['$Q = 2$', '$Q = 5.99$ ($\\mathcal{C}^*$)', '$Q = 9.21$']):
        w = 2 * np.sqrt(chi2 * eigvals[0])
        ht = 2 * np.sqrt(chi2 * eigvals[1])
        angle = np.degrees(np.arctan2(eigvecs[1, 0], eigvecs[0, 0]))
        ell = Ellipse(mu, w, ht, angle=angle, fill=False,
                      edgecolor=RED if '5.99' in lab else GREY,
                      lw=2 if '5.99' in lab else 1.2,
                      ls=ls, label=lab, zorder=4)
        ax.add_patch(ell)

    # Mark h_c region
    crit = (np.abs(h - 1.0) < 0.1)
    ax.scatter(m_abs[crit], svn[crit], s=60, facecolors='none',
               edgecolors=RED, lw=1.5, zorder=5, label='$|h/J - 1| < 0.1$')

    ax.set_xlabel('$m = \\sqrt{\\langle M_z^2 \\rangle / N^2}$')
    ax.set_ylabel('$S_{\\mathrm{vN}}$')
    ax.set_title('(a) Order parameter vs Entanglement', color=ACCENT)
    ax.legend(fontsize=8, loc='lower left')
    ax.grid(True, alpha=0.3)

    # Panel (b): C_ratio vs gap
    ax = axes[1]
    X_ref2 = np.column_stack([c_rat[ref_mask], gap[ref_mask]])
    X_all2 = np.column_stack([c_rat, gap])
    mu2 = X_ref2.mean(axis=0)
    cov2 = np.cov(X_ref2.T) + 1e-8 * np.eye(2)
    ev2, evec2 = np.linalg.eigh(cov2)

    sc2 = ax.scatter(c_rat, gap, c=h, cmap='plasma', s=20, zorder=3,
                     edgecolors='none', alpha=0.85)
    plt.colorbar(sc2, ax=ax, label='$h/J$', shrink=0.8)

    for chi2, ls, lab in zip(chi2_levels,
                             ['-', '--', ':'],
                             ['$Q = 2$', '$Q = 5.99$ ($\\mathcal{C}^*$)', '$Q = 9.21$']):
        w = 2 * np.sqrt(chi2 * ev2[0])
        ht = 2 * np.sqrt(chi2 * ev2[1])
        angle = np.degrees(np.arctan2(evec2[1, 0], evec2[0, 0]))
        ell = Ellipse(mu2, w, ht, angle=angle, fill=False,
                      edgecolor=RED if '5.99' in lab else GREY,
                      lw=2 if '5.99' in lab else 1.2, ls=ls, label=lab, zorder=4)
        ax.add_patch(ell)

    ax.scatter(c_rat[crit], gap[crit], s=60, facecolors='none',
               edgecolors=RED, lw=1.5, zorder=5, label='$|h/J - 1| < 0.1$')
    ax.set_xlabel('Correlation ratio  $C_{\\mathrm{long}} / C_{zz}$')
    ax.set_ylabel('Physical gap $\\Delta$')
    ax.set_title('(b) Correlation ratio vs Spectral gap', color=ACCENT)
    ax.legend(fontsize=8, loc='upper right')
    ax.grid(True, alpha=0.3)

    fig.tight_layout(rect=[0, 0, 1, 0.93])
    fig.savefig(PLOTS / 'fig6_ellipsoid_2d.png', bbox_inches='tight')
    plt.close(fig)
    print("  [6/9] 2D ellipsoid projections saved")


# =====================================================================
#  FIG 7: C* ELLIPSOID — 3D MANIFOLD
# =====================================================================
def fig_ellipsoid_3d():
    """
    3D scatter of (m_abs, S_vN, C_ratio) coloured by MFLS score.
    C* ellipsoid surface shown as wireframe.
    The trajectory through observable space traces a curve that
    punctures C* at the QPT.
    """
    fig = plt.figure(figsize=(11, 9))
    ax = fig.add_subplot(111, projection='3d')
    ax.set_facecolor('#0d1117')
    fig.patch.set_facecolor('#0d1117')

    # Trajectory coloured by MFLS
    mfls_n = mfls / (mfls.max() + 1e-10)
    cmap = plt.cm.hot

    # Draw the trajectory as a tube-like scatter
    sc3 = ax.scatter(m_abs, svn, c_rat,
                     c=mfls_n, cmap=cmap, s=25, alpha=0.85,
                     edgecolors='none', depthshade=True)
    fig.colorbar(sc3, ax=ax, label='MFLS (normalised)', shrink=0.6, pad=0.1)

    # Connect with a thin line
    ax.plot(m_abs, svn, c_rat, color=GREY, lw=0.7, alpha=0.5)

    # Mark h_c region
    crit = np.abs(h - 1.0) < 0.1
    ax.scatter(m_abs[crit], svn[crit], c_rat[crit],
               s=80, facecolors='none', edgecolors=RED, lw=2,
               label='$|h/J - 1| < 0.1$  (QPT)', depthshade=False)

    # Mark endpoints
    ax.scatter([m_abs[0]], [svn[0]], [c_rat[0]],
               s=120, marker='^', color=GREEN, zorder=10, label='$h/J \\to 0$ (ordered)')
    ax.scatter([m_abs[-1]], [svn[-1]], [c_rat[-1]],
               s=120, marker='v', color=PURPLE, zorder=10, label='$h/J = 2$ (disordered)')

    # Draw C* ellipsoid (fitted to reference data)
    ref_mask = h < 0.5 * J
    X_ref = np.column_stack([m_abs[ref_mask], svn[ref_mask], c_rat[ref_mask]])
    mu3 = X_ref.mean(axis=0)
    cov3 = np.cov(X_ref.T) + 1e-6 * np.eye(3)
    eigvals3, eigvecs3 = np.linalg.eigh(cov3)

    # Wireframe ellipsoid at Q = 5.99 (chi2(3), 95%)
    chi2_3d = 7.81  # chi2(3) at 95%
    u = np.linspace(0, 2 * np.pi, 30)
    v = np.linspace(0, np.pi, 20)
    semi = np.sqrt(chi2_3d * np.maximum(eigvals3, 1e-12))

    ex = semi[0] * np.outer(np.cos(u), np.sin(v))
    ey = semi[1] * np.outer(np.sin(u), np.sin(v))
    ez = semi[2] * np.outer(np.ones_like(u), np.cos(v))

    # Rotate and translate
    for i in range(ex.shape[0]):
        for j in range(ex.shape[1]):
            pt = eigvecs3 @ np.array([ex[i, j], ey[i, j], ez[i, j]]) + mu3
            ex[i, j], ey[i, j], ez[i, j] = pt

    ax.plot_wireframe(ex, ey, ez, color=RED, alpha=0.15, linewidth=0.5,
                      label='$\\mathcal{C}^*$ ellipsoid ($\\chi^2_3 = 7.81$)')

    ax.set_xlabel('$m$  (order param.)', labelpad=10)
    ax.set_ylabel('$S_{\\mathrm{vN}}$', labelpad=10)
    ax.set_zlabel('$C_{\\mathrm{ratio}}$', labelpad=8)
    ax.set_title('3D Observable Manifold — Trajectory Punctures $\\mathcal{C}^*$ at QPT',
                 fontsize=12, color=WHITE, pad=15)
    ax.legend(fontsize=8, loc='upper left')
    ax.view_init(elev=25, azim=-50)

    fig.savefig(PLOTS / 'fig7_ellipsoid_3d.png', bbox_inches='tight')
    plt.close(fig)
    print("  [7/9] 3D ellipsoid manifold saved")


# =====================================================================
#  FIG 8: BENCHMARK TABLE — BSDT vs 11 standard QPT methods
# =====================================================================
def fig_benchmark_table():
    """Full 22-method benchmark table from extended_benchmark.json."""
    ext_path = RES / 'extended_benchmark.json'
    if ext_path.exists():
        with open(ext_path) as f:
            ext = json.load(f)
        bench = ext['benchmark']
    else:
        # Fallback to original det dict
        bench = [{'name': k, 'category': 'Original', 'domain_knowledge': False,
                  'auc_crit': v['auc_crit'], 'auc_post': v['auc_post'],
                  'peak_h': 0, 'lead': v.get('lead_steps', 0), 'ref': ''}
                 for k, v in det.items()]

    fig, ax = plt.subplots(figsize=(14, 11))
    ax.axis('off')
    fig.suptitle('Extended Benchmark: BSDT vs 22 QPT Detection Methods  (N=12)',
                 fontsize=14, color=WHITE, y=0.98)

    rows = []
    for r in bench:
        dk = 'Yes' if r['domain_knowledge'] else 'No'
        rows.append([
            r['name'], r['category'], dk,
            f"{r['auc_crit']:.3f}", f"{r['auc_post']:.3f}",
            f"{r['peak_h']:.3f}", str(r['lead']), r.get('ref', '')
        ])

    col_labels = ['Method', 'Category', 'DK', 'AUC\n(crit)',
                  'AUC\n(post)', 'Peak\n$h/J$', 'Lead', 'Reference']
    col_widths = [0.22, 0.14, 0.04, 0.06, 0.06, 0.06, 0.04, 0.10]

    table = ax.table(
        cellText=rows, colLabels=col_labels,
        loc='center', cellLoc='center',
        colWidths=col_widths,
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8)
    table.scale(1, 1.35)

    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor('#30363d')
        if row == 0:
            cell.set_facecolor('#21262d')
            cell.set_text_props(color=WHITE, fontweight='bold', fontsize=8)
        else:
            cell.set_facecolor('#0d1117')
            cell.set_text_props(color='#c9d1d9', fontsize=8)
            cat = rows[row - 1][1]
            if 'BSDT' in cat:
                cell.set_facecolor('#1a1f35')
            if col == 3:
                val = float(rows[row - 1][3])
                if val >= 0.95:
                    cell.set_text_props(color=GOLD, fontweight='bold')
                elif val >= 0.90:
                    cell.set_text_props(color=GREEN, fontweight='bold')
                elif val < 0.5:
                    cell.set_text_props(color=RED)
            if 'MFLS' in rows[row - 1][0]:
                cell.set_facecolor('#2a1f00')
                if col == 0:
                    cell.set_text_props(color=GOLD, fontweight='bold')

    fig.tight_layout(rect=[0.01, 0.01, 0.99, 0.96])
    fig.savefig(PLOTS / 'fig8_benchmark_table.png', bbox_inches='tight')
    plt.close(fig)
    print("  [8/9] Benchmark table (22 methods) saved")


# =====================================================================
#  FIG 9: PROCYCLICALITY
# =====================================================================
def fig_procyclicality():
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.5))
    fig.suptitle('Procyclicality — Constant Friction Fails, Adaptive MFLS Succeeds',
                 fontsize=13, color=WHITE)

    y_crit = (np.abs(h - 1.0) < 0.15).astype(int)
    mfls_n = mfls / (mfls.max() + 1e-10)
    thr = np.percentile(mfls_n, 85)

    # Panel (a): Signal comparison
    ax = ax1
    inv_gap_n = (1.0 / (gap + 1e-10))
    inv_gap_n = inv_gap_n / inv_gap_n.max()
    dm_n = dm / (dm.max() + 1e-10)
    dsvn_n = dsvn / (dsvn.max() + 1e-10)

    ax.plot(h, inv_gap_n, color=GREY, lw=1.5, alpha=0.7, label='$\\gamma \\times 1/\\Delta$ (constant)')
    ax.plot(h, dm_n, color=CYAN, lw=1.5, alpha=0.7, label='$|dm/dh|$ (single obs.)')
    ax.plot(h, dsvn_n, color=PINK, lw=1.5, alpha=0.7, label='$|dS/dh|$ (single obs.)')
    ax.plot(h, mfls_n, color=GOLD, lw=2.5, label='MFLS (adaptive, multi-factor)')
    ax.axhline(thr, color=RED, ls=':', alpha=0.5, label=f'85th percentile threshold')
    ax.axvspan(0.85, 1.15, alpha=0.1, color=RED, label='Critical region')
    add_hc_line(ax, label=False)
    ax.set_xlabel('$h / J$')
    ax.set_ylabel('Normalised score')
    ax.set_title('(a) Detection Signals', color=GOLD)
    ax.legend(fontsize=8, loc='upper right')
    ax.grid(True, alpha=0.3)

    # Panel (b): FAR vs Miss tradeoff
    ax = ax2
    gammas = np.linspace(0.01, 5.0, 100)
    far_inv, miss_inv = [], []
    far_dm, miss_dm = [], []
    far_mfls, miss_mfls = [], []

    for pct in np.linspace(50, 99, 50):
        for sig, far_l, miss_l in [(inv_gap_n, far_inv, miss_inv),
                                    (dm_n, far_dm, miss_dm),
                                    (mfls_n, far_mfls, miss_mfls)]:
            t = np.percentile(sig, pct)
            alarm = sig > t
            nc = y_crit.sum()
            nn = len(y_crit) - nc
            f = alarm[y_crit == 0].sum() / max(nn, 1)
            m = (~alarm)[y_crit == 1].sum() / max(nc, 1)
            far_l.append(f)
            miss_l.append(m)

    ax.plot(far_inv, miss_inv, 'o-', color=GREY, ms=3, lw=1.2, alpha=0.7,
            label='$1/\\Delta$ (constant $\\gamma$)')
    ax.plot(far_dm, miss_dm, 's-', color=CYAN, ms=3, lw=1.2, alpha=0.7,
            label='$|dm/dh|$ (single obs.)')
    ax.plot(far_mfls, miss_mfls, 'D-', color=GOLD, ms=4, lw=2,
            label='MFLS (adaptive)')

    ax.set_xlabel('False Alarm Rate')
    ax.set_ylabel('Miss Rate')
    ax.set_title('(b) FAR vs Miss Tradeoff', color=GOLD)
    ax.set_xlim(-0.02, 0.5)
    ax.set_ylim(-0.02, 1.02)
    ax.plot([0, 1], [1, 0], ':', color=GREY, alpha=0.3)
    ax.axhline(0.1, color=RED, ls=':', alpha=0.3)
    ax.axvline(0.1, color=RED, ls=':', alpha=0.3)
    ax.fill_between([0, 0.1], 0, 0.1, alpha=0.1, color=GREEN)
    ax.text(0.03, 0.03, 'Target\nzone', fontsize=8, color=GREEN, alpha=0.7)
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    fig.tight_layout(rect=[0, 0, 1, 0.93])
    fig.savefig(PLOTS / 'fig9_procyclicality.png', bbox_inches='tight')
    plt.close(fig)
    print("  [9/9] Procyclicality plots saved")


def fig_multisize_comparison():
    """Fig 10: Multi-size AUC scaling for top methods from extended benchmark."""
    ext_path = RES / 'extended_benchmark.json'
    if not ext_path.exists():
        print("  [10/10] Skipped — no extended_benchmark.json")
        return
    with open(ext_path) as f:
        ext = json.load(f)
    ms = ext.get('multi_size', {})
    if not ms:
        print("  [10/10] Skipped — no multi_size data")
        return

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle('Finite-Size Scaling \u2014 BSDT vs Top QPT Methods',
                 fontsize=14, color=WHITE, y=0.98)

    # Parse multi-size data
    method_names = list(ms.keys())
    # Get sizes from first method
    first = ms[method_names[0]]
    sizes = sorted(int(s.replace('N=', '')) for s in first.keys())

    # Select top methods + MFLS for comparison
    # Rank by average AUC across sizes
    avg_aucs = {}
    for m in method_names:
        vals = [ms[m][f'N={n}'] for n in sizes if f'N={n}' in ms[m]]
        avg_aucs[m] = np.mean(vals) if vals else 0.0

    top_methods = sorted(avg_aucs, key=avg_aucs.get, reverse=True)[:8]
    # Ensure MFLS is included
    mfls_key = [m for m in method_names if 'MFLS' in m]
    if mfls_key and mfls_key[0] not in top_methods:
        top_methods[-1] = mfls_key[0]

    # Color palette
    cpal = [GOLD, ACCENT, GREEN, PURPLE, '#f97583', '#79c0ff', '#c9d1d9', '#56d4dd']

    # ax1: AUC vs system size
    for i, m in enumerate(top_methods):
        vals = [ms[m].get(f'N={n}', np.nan) for n in sizes]
        lw = 2.5 if 'MFLS' in m else 1.5
        ms_ = 8 if 'MFLS' in m else 5
        ax1.plot(sizes, vals, 'o-', color=cpal[i % len(cpal)], lw=lw, ms=ms_,
                 label=m, alpha=0.9)

    ax1.set_xlabel('System size N', fontsize=11)
    ax1.set_ylabel('AUC (critical region)', fontsize=11)
    ax1.set_title('(a) AUC Convergence with System Size', color=GOLD)
    ax1.set_ylim(0.85, 1.005)
    ax1.legend(fontsize=7, loc='lower right', ncol=2)
    ax1.grid(True, alpha=0.3)

    # ax2: Improvement rate (AUC at N=14 - AUC at N=8) / AUC at N=8
    improvements = []
    m_labels = []
    m_colors = []
    for i, m in enumerate(top_methods):
        auc_small = ms[m].get(f'N={sizes[0]}', 0.5)
        auc_large = ms[m].get(f'N={sizes[-1]}', 0.5)
        improvement = (auc_large - auc_small) / max(auc_small, 0.01) * 100
        improvements.append(improvement)
        m_labels.append(m)
        m_colors.append(GOLD if 'MFLS' in m else cpal[i % len(cpal)])

    # Sort by improvement
    order = np.argsort(improvements)[::-1]
    improvements = [improvements[i] for i in order]
    m_labels = [m_labels[i] for i in order]
    m_colors = [m_colors[i] for i in order]

    bars = ax2.barh(range(len(m_labels)), improvements, color=m_colors,
                    edgecolor='none', alpha=0.85, height=0.65)
    for i, (imp, lab) in enumerate(zip(improvements, m_labels)):
        ax2.text(imp + 0.1, i, f'{imp:+.1f}%', va='center', fontsize=9, color=WHITE)
    ax2.set_yticks(range(len(m_labels)))
    ax2.set_yticklabels(m_labels, fontsize=9)
    ax2.set_xlabel('AUC Improvement N=8\u2192N=14 (%)', fontsize=11)
    ax2.set_title('(b) Finite-Size Improvement Rate', color=GOLD)
    ax2.grid(True, axis='x', alpha=0.3)
    ax2.axvline(0, color=GREY, alpha=0.3)

    # Highlight MFLS
    for i, lab in enumerate(m_labels):
        if 'MFLS' in lab:
            ax2.get_yticklabels()[i].set_color(GOLD)
            ax2.get_yticklabels()[i].set_fontweight('bold')

    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(PLOTS / 'fig10_multisize_comparison.png', bbox_inches='tight')
    plt.close(fig)
    print("  [10/10] Multi-size comparison saved")


# =====================================================================
#  MAIN
# =====================================================================
def main():
    print("=" * 70)
    print("  Generating Domain VII Visualizations")
    print("=" * 70)

    fig_phase_diagram()
    fig_detection_benchmark()
    fig_dual_role()
    fig_scaling()
    fig_channel_anatomy()
    fig_ellipsoid_2d()
    fig_ellipsoid_3d()
    fig_benchmark_table()
    fig_procyclicality()
    fig_multisize_comparison()

    print(f"\n  All 10 figures saved to: {PLOTS}")
    print("=" * 70)


if __name__ == '__main__':
    main()
