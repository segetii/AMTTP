"""
UDL Benchmark Results — Comprehensive Visualization
=====================================================
Generates 2D bar/heatmap charts, 3D surface plots, and
standard comparison plots from the SOTA benchmark results.
"""

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import cm
from mpl_toolkits.mplot3d import Axes3D
import os

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "plots")
os.makedirs(OUT_DIR, exist_ok=True)

# ═══════════════════════════════════════════════════════════════
#  DATA — from sota_comparison.txt (benchmark run 2026-02-19)
# ═══════════════════════════════════════════════════════════════

datasets = ["Synthetic", "Mimic", "Mammography", "Shuttle", "Pendigits"]

# Ordered by rank (best first)
methods = [
    "UDL-v3e-CombB+R",   # #1  NEW CHAMPION
    "KNN-Distance",       # #2
    "LOF",                # #3
    "UDL-CombinedA",      # #4
    "UDL-B3phase",        # #5
    "UDL-CombA+Recon",    # #6
    "UDL-A3wavelet",      # #7
    "UDL-v3e-CombA+R",    # #8
    "UDL-CombB+Recon",    # #9
    "Isolation Forest",   # #10
    "UDL-CombinedB",      # #11
    "One-Class SVM",      # #12
    "UDL-v3e-6laws",      # #13
    "Elliptic Envelope",  # #14
    "UDL-v3c-6laws",      # #15
    "UDL-6laws-v2",       # #16
    "UDL-ReconOnly",      # #17
    "UDL-RankOnly",       # #18
    "UDL-5laws",          # #19
]

# AUC-ROC values: rows=methods, cols=datasets
auc_data = np.array([
    [1.0000, 1.0000, 0.9389, 0.9693, 0.9274],  # UDL-v3e-CombB+R
    [1.0000, 1.0000, 0.8764, 0.9840, 0.9720],  # KNN
    [1.0000, 1.0000, 0.8375, 0.9911, 0.9774],  # LOF
    [1.0000, 1.0000, 0.8803, 0.9835, 0.9417],  # UDL-CombinedA
    [1.0000, 1.0000, 0.8905, 0.9780, 0.9320],  # UDL-B3phase
    [1.0000, 1.0000, 0.8862, 0.9830, 0.9300],  # UDL-CombA+Recon
    [1.0000, 1.0000, 0.8633, 0.9796, 0.9548],  # UDL-A3wavelet
    [1.0000, 1.0000, 0.9109, 0.9686, 0.8755],  # UDL-v3e-CombA+R
    [1.0000, 0.8913, 0.8800, 0.9938, 0.9697],  # UDL-CombB+Recon
    [1.0000, 1.0000, 0.8744, 0.9433, 0.9057],  # Isolation Forest
    [1.0000, 0.8862, 0.8721, 0.9944, 0.9696],  # UDL-CombinedB
    [1.0000, 1.0000, 0.7979, 0.9217, 0.9382],  # One-Class SVM
    [1.0000, 1.0000, 0.9005, 0.8797, 0.8658],  # UDL-v3e-6laws
    [1.0000, 1.0000, 0.8550, 0.9177, 0.8674],  # Elliptic Envelope
    [0.9933, 0.9973, 0.8609, 0.8631, 0.7883],  # UDL-v3c-6laws
    [1.0000, 1.0000, 0.8842, 0.8254, 0.7823],  # UDL-6laws-v2
    [1.0000, 1.0000, 0.8842, 0.8254, 0.7823],  # UDL-ReconOnly
    [1.0000, 1.0000, 0.8842, 0.8254, 0.7823],  # UDL-RankOnly
    [1.0000, 1.0000, 0.8842, 0.8254, 0.7765],  # UDL-5laws
])

mean_auc = auc_data.mean(axis=1)

# Classify methods: UDL vs Baseline
is_udl = [m.startswith("UDL") for m in methods]

# Color scheme
COLOR_UDL = "#2196F3"        # Blue
COLOR_BASELINE = "#FF5722"   # Orange-red
COLOR_CHAMPION = "#FFD700"   # Gold
COLOR_UDL_NEW = "#00C853"    # Green (new operators)


def get_color(i):
    """Color for method by index."""
    if i == 0:
        return COLOR_CHAMPION
    elif methods[i].startswith("UDL") and ("Recon" in methods[i] or "Rank" in methods[i] or "6laws" in methods[i]):
        return COLOR_UDL_NEW
    elif methods[i].startswith("UDL"):
        return COLOR_UDL
    else:
        return COLOR_BASELINE


# ═══════════════════════════════════════════════════════════════
#  PLOT 1: Horizontal Bar Chart — Mean AUC Ranking
# ═══════════════════════════════════════════════════════════════

def plot_mean_auc_ranking():
    fig, ax = plt.subplots(figsize=(14, 10))

    # Reverse for top-down display
    y_pos = np.arange(len(methods))
    colors = [get_color(i) for i in range(len(methods))]

    bars = ax.barh(y_pos, mean_auc[::-1], color=colors[::-1], edgecolor='white',
                   linewidth=0.5, height=0.7)

    ax.set_yticks(y_pos)
    ax.set_yticklabels(methods[::-1], fontsize=10, fontweight='bold')
    ax.set_xlabel("Mean AUC-ROC (across 5 datasets)", fontsize=13, fontweight='bold')
    ax.set_title("UDL vs State-of-the-Art: Overall Ranking\n(New Champion: UDL-v3e-CombB+Recon+RankOrder)",
                 fontsize=15, fontweight='bold', pad=15)

    # Add value labels
    for i, (bar, val) in enumerate(zip(bars, mean_auc[::-1])):
        rank = len(methods) - i
        ax.text(val + 0.002, bar.get_y() + bar.get_height()/2,
                f" {val:.4f}  (#{rank})",
                va='center', fontsize=9, fontweight='bold')

    ax.set_xlim(0.85, 1.01)
    ax.axvline(x=mean_auc[0], color=COLOR_CHAMPION, linestyle='--', alpha=0.5, linewidth=1)

    # Legend
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor=COLOR_CHAMPION, label='Champion (UDL + New Operators)'),
        Patch(facecolor=COLOR_UDL_NEW, label='UDL + Recon/RankOrder (new)'),
        Patch(facecolor=COLOR_UDL, label='UDL (existing operators)'),
        Patch(facecolor=COLOR_BASELINE, label='Baseline Methods'),
    ]
    ax.legend(handles=legend_elements, loc='lower right', fontsize=10,
              framealpha=0.9, edgecolor='gray')

    ax.grid(axis='x', alpha=0.3)
    plt.tight_layout()
    path = os.path.join(OUT_DIR, "01_mean_auc_ranking.png")
    plt.savefig(path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  Saved: {path}")


# ═══════════════════════════════════════════════════════════════
#  PLOT 2: Grouped Bar Chart — Per-Dataset Comparison (Top 8)
# ═══════════════════════════════════════════════════════════════

def plot_per_dataset_top8():
    top_n = 8
    fig, ax = plt.subplots(figsize=(16, 8))

    x = np.arange(len(datasets))
    width = 0.09
    offsets = np.arange(top_n) - (top_n - 1) / 2

    colors_top = [get_color(i) for i in range(top_n)]

    for i in range(top_n):
        bars = ax.bar(x + offsets[i] * width, auc_data[i], width * 0.9,
                      label=f"#{i+1} {methods[i]}", color=colors_top[i],
                      edgecolor='white', linewidth=0.5)
        # Add value on top of bar for mammography (most interesting)
        mamm_idx = 2
        ax.text(x[mamm_idx] + offsets[i] * width, auc_data[i, mamm_idx] + 0.003,
                f"{auc_data[i, mamm_idx]:.3f}", ha='center', va='bottom',
                fontsize=6.5, fontweight='bold', rotation=45)

    ax.set_xticks(x)
    ax.set_xticklabels(datasets, fontsize=12, fontweight='bold')
    ax.set_ylabel("AUC-ROC", fontsize=13, fontweight='bold')
    ax.set_title("Per-Dataset AUC: Top 8 Methods\n(UDL-v3e-CombB+R dominates Mammography at 0.939)",
                 fontsize=14, fontweight='bold', pad=15)
    ax.set_ylim(0.82, 1.02)
    ax.legend(fontsize=8, ncol=2, loc='lower left', framealpha=0.9)
    ax.grid(axis='y', alpha=0.3)

    plt.tight_layout()
    path = os.path.join(OUT_DIR, "02_per_dataset_top8.png")
    plt.savefig(path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  Saved: {path}")


# ═══════════════════════════════════════════════════════════════
#  PLOT 3: Heatmap — All Methods × All Datasets
# ═══════════════════════════════════════════════════════════════

def plot_heatmap():
    fig, ax = plt.subplots(figsize=(12, 12))

    # Show top 14 most relevant
    n_show = 14
    data_show = auc_data[:n_show]
    methods_show = methods[:n_show]

    im = ax.imshow(data_show, cmap='RdYlGn', aspect='auto',
                   vmin=0.82, vmax=1.0)

    ax.set_xticks(np.arange(len(datasets)))
    ax.set_yticks(np.arange(n_show))
    ax.set_xticklabels(datasets, fontsize=11, fontweight='bold')
    ax.set_yticklabels([f"#{i+1} {m}" for i, m in enumerate(methods_show)],
                       fontsize=10, fontweight='bold')

    # Add text annotations
    for i in range(n_show):
        for j in range(len(datasets)):
            val = data_show[i, j]
            color = 'white' if val < 0.88 else 'black'
            fontw = 'bold' if val >= 0.98 else 'normal'
            ax.text(j, i, f"{val:.3f}", ha='center', va='center',
                    fontsize=9, color=color, fontweight=fontw)

    # Highlight champion row
    ax.axhline(y=-0.5, color=COLOR_CHAMPION, linewidth=3)
    ax.axhline(y=0.5, color=COLOR_CHAMPION, linewidth=3)

    cbar = plt.colorbar(im, ax=ax, shrink=0.6, label='AUC-ROC')
    ax.set_title("AUC-ROC Heatmap: Methods × Datasets\n(Green = better, Red = worse)",
                 fontsize=14, fontweight='bold', pad=15)

    plt.tight_layout()
    path = os.path.join(OUT_DIR, "03_heatmap.png")
    plt.savefig(path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  Saved: {path}")


# ═══════════════════════════════════════════════════════════════
#  PLOT 4: 3D Surface — Methods × Datasets × AUC
# ═══════════════════════════════════════════════════════════════

def plot_3d_surface():
    fig = plt.figure(figsize=(16, 10))
    ax = fig.add_subplot(111, projection='3d')

    n_show = 14
    data_show = auc_data[:n_show]

    X = np.arange(len(datasets))
    Y = np.arange(n_show)
    X_grid, Y_grid = np.meshgrid(X, Y)

    # Surface plot
    surf = ax.plot_surface(X_grid, Y_grid, data_show,
                           cmap='coolwarm', alpha=0.7,
                           edgecolors='gray', linewidth=0.3,
                           antialiased=True)

    # Add scatter points on top for emphasis
    for i in range(n_show):
        for j in range(len(datasets)):
            color = COLOR_CHAMPION if i == 0 else (COLOR_UDL if is_udl[i] else COLOR_BASELINE)
            size = 80 if i == 0 else 30
            ax.scatter(j, i, data_show[i, j], c=color, s=size,
                       edgecolors='black', linewidth=0.5, zorder=5)

    ax.set_xticks(X)
    ax.set_xticklabels(datasets, fontsize=9, rotation=15)
    ax.set_yticks(Y[::2])
    ax.set_yticklabels([f"#{i+1}" for i in Y[::2]], fontsize=9)
    ax.set_zlabel("AUC-ROC", fontsize=11, fontweight='bold')
    ax.set_xlabel("Dataset", fontsize=11, fontweight='bold', labelpad=10)
    ax.set_ylabel("Method Rank", fontsize=11, fontweight='bold', labelpad=10)
    ax.set_zlim(0.78, 1.02)
    ax.set_title("3D Surface: AUC-ROC Landscape\n(Methods × Datasets × Performance)",
                 fontsize=14, fontweight='bold', pad=20)
    ax.view_init(elev=25, azim=-50)

    fig.colorbar(surf, ax=ax, shrink=0.4, label='AUC-ROC', pad=0.1)
    plt.tight_layout()
    path = os.path.join(OUT_DIR, "04_3d_surface.png")
    plt.savefig(path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  Saved: {path}")


# ═══════════════════════════════════════════════════════════════
#  PLOT 5: 3D Bar Chart — Top 8 Methods × 5 Datasets
# ═══════════════════════════════════════════════════════════════

def plot_3d_bars():
    fig = plt.figure(figsize=(16, 10))
    ax = fig.add_subplot(111, projection='3d')

    top_n = 8
    dx = dy = 0.6
    colors_map = cm.get_cmap('Set2', top_n)

    for i in range(top_n):
        xs = np.arange(len(datasets))
        ys = np.full(len(datasets), i)
        zs = np.zeros(len(datasets))
        dz = auc_data[i] - 0.8  # offset from base for visibility

        color = colors_map(i)
        if i == 0:
            color = COLOR_CHAMPION

        ax.bar3d(xs - dx/2, ys - dy/2, zs + 0.8, dx, dy, dz,
                 color=color, alpha=0.85, edgecolor='gray', linewidth=0.3)

    ax.set_xticks(np.arange(len(datasets)))
    ax.set_xticklabels(datasets, fontsize=9, rotation=10)
    ax.set_yticks(np.arange(top_n))
    ax.set_yticklabels([f"#{i+1}" for i in range(top_n)], fontsize=9)
    ax.set_zlabel("AUC-ROC", fontsize=11, fontweight='bold')
    ax.set_zlim(0.8, 1.02)
    ax.set_title("3D Bar Chart: Top 8 Methods × Datasets",
                 fontsize=14, fontweight='bold', pad=15)
    ax.view_init(elev=20, azim=-40)

    # Legend
    from matplotlib.patches import Patch
    legend_elements = [Patch(facecolor=COLOR_CHAMPION if i == 0 else colors_map(i),
                             label=f"#{i+1} {methods[i]}")
                       for i in range(top_n)]
    ax.legend(handles=legend_elements, loc='upper left', fontsize=7.5,
              framealpha=0.9, ncol=2)

    plt.tight_layout()
    path = os.path.join(OUT_DIR, "05_3d_bars.png")
    plt.savefig(path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  Saved: {path}")


# ═══════════════════════════════════════════════════════════════
#  PLOT 6: Radar / Spider Chart — Top 5 Methods
# ═══════════════════════════════════════════════════════════════

def plot_radar():
    top_n = 5
    angles = np.linspace(0, 2 * np.pi, len(datasets), endpoint=False).tolist()
    angles += angles[:1]  # close the polygon

    fig, ax = plt.subplots(figsize=(10, 10), subplot_kw=dict(polar=True))

    colors_radar = [COLOR_CHAMPION, COLOR_BASELINE, COLOR_BASELINE, COLOR_UDL, COLOR_UDL]
    styles = ['-', '--', '-.', '-', '--']

    for i in range(top_n):
        values = auc_data[i].tolist() + [auc_data[i, 0]]
        ax.plot(angles, values, styles[i], linewidth=2.5,
                label=f"#{i+1} {methods[i]}", color=colors_radar[i])
        ax.fill(angles, values, alpha=0.08, color=colors_radar[i])

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(datasets, fontsize=12, fontweight='bold')
    ax.set_ylim(0.82, 1.02)
    ax.set_rticks([0.85, 0.90, 0.95, 1.00])
    ax.set_title("Radar Plot: Top 5 Methods Across Datasets\n(Larger area = better overall performance)",
                 fontsize=14, fontweight='bold', pad=30)
    ax.legend(loc='lower right', bbox_to_anchor=(1.25, -0.05),
              fontsize=10, framealpha=0.9)

    plt.tight_layout()
    path = os.path.join(OUT_DIR, "06_radar.png")
    plt.savefig(path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  Saved: {path}")


# ═══════════════════════════════════════════════════════════════
#  PLOT 7: UDL vs Best Baseline — Delta Comparison
# ═══════════════════════════════════════════════════════════════

def plot_delta_comparison():
    """Show how far UDL champion beats/loses to best baseline per dataset."""
    # Best baseline per dataset
    baseline_indices = [i for i, m in enumerate(methods) if not m.startswith("UDL")]
    best_baseline_per_ds = np.max(auc_data[baseline_indices], axis=0)
    best_baseline_names = [methods[baseline_indices[np.argmax(auc_data[baseline_indices, j])]]
                           for j in range(len(datasets))]

    # Champion UDL
    champion_auc = auc_data[0]  # UDL-v3e-CombB+R
    delta = champion_auc - best_baseline_per_ds

    fig, ax = plt.subplots(figsize=(12, 6))

    colors_delta = ['green' if d >= 0 else 'red' for d in delta]
    bars = ax.bar(datasets, delta, color=colors_delta, edgecolor='white',
                  width=0.6, alpha=0.85)

    ax.axhline(y=0, color='black', linewidth=1)

    for i, (bar, d, bl_name) in enumerate(zip(bars, delta, best_baseline_names)):
        y_offset = 0.003 if d >= 0 else -0.008
        ax.text(bar.get_x() + bar.get_width()/2, d + y_offset,
                f"{d:+.4f}\nvs {bl_name}",
                ha='center', va='bottom' if d >= 0 else 'top',
                fontsize=10, fontweight='bold')

    ax.set_ylabel("AUC Difference (UDL Champion - Best Baseline)", fontsize=12, fontweight='bold')
    ax.set_title("UDL-v3e-CombB+R vs Best Baseline Per Dataset\n(Positive = UDL wins)",
                 fontsize=14, fontweight='bold', pad=15)
    ax.grid(axis='y', alpha=0.3)
    ax.set_ylim(-0.06, 0.08)

    plt.tight_layout()
    path = os.path.join(OUT_DIR, "07_delta_comparison.png")
    plt.savefig(path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  Saved: {path}")


# ═══════════════════════════════════════════════════════════════
#  PLOT 8: Operator Evolution — How New Operators Improved UDL
# ═══════════════════════════════════════════════════════════════

def plot_operator_evolution():
    """Show evolution: 5-law → Recon/RankOnly → 6-laws → CombB+Recon → Champion."""
    evolution_methods = [
        "UDL-5laws",          # Original
        "UDL-ReconOnly",      # Recon replaces Exp
        "UDL-6laws-v2",       # Recon + RankOrder (6 laws)
        "UDL-CombinedA",      # CombA (old best)
        "UDL-CombA+Recon",    # CombA + new operators
        "UDL-CombB+Recon",    # CombB + new operators
        "UDL-v3e-CombB+R",    # Champion: CombB + new ops + Fisher scoring
    ]

    evo_indices = [methods.index(m) for m in evolution_methods]
    evo_means = [mean_auc[i] for i in evo_indices]

    fig, ax = plt.subplots(figsize=(14, 7))

    x = np.arange(len(evolution_methods))
    colors_evo = [
        '#9E9E9E',    # gray: old
        COLOR_UDL_NEW,
        COLOR_UDL_NEW,
        COLOR_UDL,
        COLOR_UDL_NEW,
        COLOR_UDL_NEW,
        COLOR_CHAMPION,
    ]

    bars = ax.bar(x, evo_means, color=colors_evo, edgecolor='white',
                  width=0.65, alpha=0.9)

    # Add value labels + delta from previous
    for i, (bar, val) in enumerate(zip(bars, evo_means)):
        ax.text(bar.get_x() + bar.get_width()/2, val + 0.002,
                f"{val:.4f}", ha='center', va='bottom',
                fontsize=10, fontweight='bold')
        if i > 0:
            delta = val - evo_means[i-1]
            color = 'green' if delta > 0 else 'red'
            ax.text(bar.get_x() + bar.get_width()/2, val - 0.008,
                    f"{delta:+.4f}", ha='center', va='top',
                    fontsize=8, fontweight='bold', color=color)

    short_labels = [
        "5-Laws\n(original)",
        "ReconOnly\n(swap Exp→Recon)",
        "6-Laws v2\n(+RankOrder)",
        "CombinedA\n(prev best)",
        "CombA+\nRecon+Rank",
        "CombB+\nRecon+Rank",
        "v3e-CombB+R\n★ CHAMPION"
    ]
    ax.set_xticks(x)
    ax.set_xticklabels(short_labels, fontsize=9, fontweight='bold')
    ax.set_ylabel("Mean AUC-ROC", fontsize=13, fontweight='bold')
    ax.set_title("Operator Evolution: From 5-Laws to New Champion\n"
                 "(How ReconstructionSpectrum + RankOrderSpectrum improved UDL)",
                 fontsize=14, fontweight='bold', pad=15)
    ax.set_ylim(0.88, 0.98)
    ax.grid(axis='y', alpha=0.3)

    # Horizontal line for KNN baseline
    knn_mean = mean_auc[1]
    ax.axhline(y=knn_mean, color=COLOR_BASELINE, linestyle='--', linewidth=2, alpha=0.7)
    ax.text(len(evolution_methods) - 0.5, knn_mean + 0.001,
            f"KNN Baseline ({knn_mean:.4f})", fontsize=10,
            color=COLOR_BASELINE, fontweight='bold', ha='right')

    plt.tight_layout()
    path = os.path.join(OUT_DIR, "08_operator_evolution.png")
    plt.savefig(path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  Saved: {path}")


# ═══════════════════════════════════════════════════════════════
#  PLOT 9: 3D Scatter — Dataset Difficulty vs Method Strength
# ═══════════════════════════════════════════════════════════════

def plot_3d_scatter():
    fig = plt.figure(figsize=(14, 10))
    ax = fig.add_subplot(111, projection='3d')

    top_n = 10
    for i in range(top_n):
        for j, ds in enumerate(datasets):
            color = COLOR_CHAMPION if i == 0 else (COLOR_UDL if is_udl[i] else COLOR_BASELINE)
            marker = '*' if i == 0 else ('o' if is_udl[i] else 's')
            size = 200 if i == 0 else (80 if is_udl[i] else 60)
            alpha = 1.0 if i < 3 else 0.6

            ax.scatter(j, i, auc_data[i, j], c=color, marker=marker,
                       s=size, alpha=alpha, edgecolors='black', linewidth=0.5)

    # Connect champion points with a line
    ax.plot(np.arange(len(datasets)), np.zeros(len(datasets)),
            auc_data[0], color=COLOR_CHAMPION, linewidth=2, alpha=0.7)

    ax.set_xticks(np.arange(len(datasets)))
    ax.set_xticklabels(datasets, fontsize=9, rotation=10)
    ax.set_yticks(np.arange(top_n))
    ax.set_yticklabels([f"#{i+1}" for i in range(top_n)], fontsize=8)
    ax.set_zlabel("AUC-ROC", fontsize=11, fontweight='bold')
    ax.set_xlabel("Dataset", fontsize=11, fontweight='bold', labelpad=10)
    ax.set_ylabel("Method Rank", fontsize=11, fontweight='bold', labelpad=10)
    ax.set_zlim(0.82, 1.02)
    ax.set_title("3D Scatter: Performance Landscape\n(Stars = Champion, Circles = UDL, Squares = Baselines)",
                 fontsize=14, fontweight='bold', pad=15)
    ax.view_init(elev=20, azim=-55)

    from matplotlib.patches import Patch
    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], marker='*', color='w', markerfacecolor=COLOR_CHAMPION,
               markersize=15, label='Champion: UDL-v3e-CombB+R'),
        Line2D([0], [0], marker='o', color='w', markerfacecolor=COLOR_UDL,
               markersize=10, label='Other UDL configs'),
        Line2D([0], [0], marker='s', color='w', markerfacecolor=COLOR_BASELINE,
               markersize=10, label='Baseline methods'),
    ]
    ax.legend(handles=legend_elements, loc='upper right', fontsize=9)

    plt.tight_layout()
    path = os.path.join(OUT_DIR, "09_3d_scatter.png")
    plt.savefig(path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  Saved: {path}")


# ═══════════════════════════════════════════════════════════════
#  PLOT 10: Mammography Focus — UDL Breakthrough
# ═══════════════════════════════════════════════════════════════

def plot_mammography_focus():
    """Mammography is where UDL dominates most — dedicated plot."""
    mamm_idx = 2
    mamm_aucs = auc_data[:, mamm_idx]
    sort_idx = np.argsort(mamm_aucs)[::-1]

    top_12 = sort_idx[:12]

    fig, ax = plt.subplots(figsize=(12, 8))

    method_names = [methods[i] for i in top_12]
    vals = mamm_aucs[top_12]
    colors_m = [get_color(i) for i in top_12]

    bars = ax.barh(np.arange(len(top_12)), vals[::-1], color=colors_m[::-1],
                   edgecolor='white', height=0.7)

    ax.set_yticks(np.arange(len(top_12)))
    ax.set_yticklabels(method_names[::-1], fontsize=10, fontweight='bold')
    ax.set_xlabel("AUC-ROC (Mammography Dataset)", fontsize=13, fontweight='bold')
    ax.set_title("Mammography: Where UDL Dominates\n"
                 "(Medical imaging — 11,183 samples, 6 features, 2.3% anomaly rate)",
                 fontsize=14, fontweight='bold', pad=15)

    for i, (bar, val) in enumerate(zip(bars, vals[::-1])):
        ax.text(val + 0.002, bar.get_y() + bar.get_height()/2,
                f" {val:.4f}", va='center', fontsize=10, fontweight='bold')

    # Show KNN baseline
    knn_mamm = auc_data[1, mamm_idx]
    ax.axvline(x=knn_mamm, color=COLOR_BASELINE, linestyle='--', linewidth=1.5, alpha=0.7)
    ax.text(knn_mamm - 0.003, len(top_12) - 0.5,
            f"KNN: {knn_mamm:.4f}", fontsize=9, color=COLOR_BASELINE,
            fontweight='bold', ha='right')

    ax.set_xlim(0.78, 0.96)
    ax.grid(axis='x', alpha=0.3)

    plt.tight_layout()
    path = os.path.join(OUT_DIR, "10_mammography_focus.png")
    plt.savefig(path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  Saved: {path}")


# ═══════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("  Generating UDL Benchmark Visualization Plots")
    print("=" * 60)
    print()

    plot_mean_auc_ranking()
    plot_per_dataset_top8()
    plot_heatmap()
    plot_3d_surface()
    plot_3d_bars()
    plot_radar()
    plot_delta_comparison()
    plot_operator_evolution()
    plot_3d_scatter()
    plot_mammography_focus()

    print()
    print(f"  All plots saved to: {OUT_DIR}")
    print("=" * 60)
