"""
Generate publication-quality figures for Universal Deviation Law paper.

Produces 6 PDF figures in paper/figures/:
  1. operator_correlation_heatmap.pdf   — 14×14 Spearman ρ, clustered
  2. projection_scatter.pdf             — 2D UDL projection, anomalies vs normal
  3. coverage_radar.pdf                 — coverage profile across 5 datasets
  4. strategy_coverage_heatmap.pdf      — strategy × dataset coverage grid
  5. operator_solo_coverage.pdf         — ranked bar chart of 14 operators
  6. auc_vs_coverage.pdf                — scatter showing AUC ≠ coverage
"""

import os, sys, json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.patches import FancyBboxPatch
from matplotlib import cm
from scipy.cluster.hierarchy import linkage, dendrogram, leaves_list
from scipy.spatial.distance import squareform
from copy import deepcopy
from math import pi

# ── Paths ──────────────────────────────────────────────────────────
OUT_DIR = os.path.join(os.path.dirname(__file__), "figures")
os.makedirs(OUT_DIR, exist_ok=True)

# ── Style ──────────────────────────────────────────────────────────
plt.rcParams.update({
    "font.family":        "serif",
    "font.serif":         ["Computer Modern Roman", "Times New Roman", "DejaVu Serif"],
    "mathtext.fontset":   "cm",
    "font.size":          9,
    "axes.titlesize":     10,
    "axes.labelsize":     9,
    "xtick.labelsize":    8,
    "ytick.labelsize":    8,
    "legend.fontsize":    8,
    "figure.dpi":         300,
    "savefig.dpi":        300,
    "savefig.bbox":       "tight",
    "savefig.pad_inches": 0.05,
    "axes.spines.top":    False,
    "axes.spines.right":  False,
})

# ── Colour palettes ───────────────────────────────────────────────
FAMILY_COLORS = {
    "Basis":      "#2E86AB",   # teal-blue
    "Embedding":  "#A23B72",   # magenta
    "Algebraic":  "#F18F01",   # orange
    "Topological":"#C73E1D",   # red
    "Information":"#3B1F2B",   # dark purple
}

OP_FAMILY = {
    "Fourier":     "Basis",
    "BSpline":     "Basis",
    "Wavelet":     "Basis",
    "Legendre":    "Basis",
    "Phase":       "Embedding",
    "Statistical": "Algebraic",
    "Geometric":   "Algebraic",
    "Exponential": "Algebraic",
    "Recon":       "Algebraic",
    "Rank":        "Algebraic",
    "Topo":        "Topological",
    "Dependency":  "Information",
    "Kernel":      "Information",
    "Compress":    "Information",
}

STRATEGY_COLORS = {
    "Fisher":     "#264653",
    "RankFuse":   "#2A9D8F",
    "QuadSurf":   "#E9C46A",
    "Hybrid":     "#E76F51",
    "MetaFusion": "#F4A261",
}

DATASET_NAMES = ["Synthetic", "Mimic", "Mammography", "Shuttle", "Pendigits"]

# ══════════════════════════════════════════════════════════════════
#  DATA — from correlation_audit.py and lean_results.txt
# ══════════════════════════════════════════════════════════════════

OP_NAMES = ["Fourier","BSpline","Wavelet","Legendre","Phase",
            "Statistical","Geometric","Exponential","Recon","Rank",
            "Topo","Dependency","Kernel","Compress"]

CORR_MATRIX = np.array([
 [1.00, 0.53, 0.66, 0.58, 0.66, 0.14, 0.33, 0.38, 0.53, 0.25, 0.25, 0.48, 0.30,  0.01],
 [0.53, 1.00, 0.67, 0.77, 0.68, 0.14, 0.30, 0.36, 0.42, 0.24, 0.20, 0.41, 0.24, -0.03],
 [0.66, 0.67, 1.00, 0.75, 0.92, 0.15, 0.33, 0.42, 0.48, 0.23, 0.38, 0.46, 0.25, -0.06],
 [0.58, 0.77, 0.75, 1.00, 0.78, 0.15, 0.32, 0.41, 0.49, 0.21, 0.25, 0.41, 0.25, -0.06],
 [0.66, 0.68, 0.92, 0.78, 1.00, 0.17, 0.33, 0.43, 0.46, 0.24, 0.39, 0.45, 0.27, -0.04],
 [0.14, 0.14, 0.15, 0.15, 0.17, 1.00, 0.19, 0.19, 0.17, 0.15, 0.08, 0.14, 0.17,  0.02],
 [0.33, 0.30, 0.33, 0.32, 0.33, 0.19, 1.00, 0.28, 0.46, 0.55, 0.08, 0.50, 0.66,  0.05],
 [0.38, 0.36, 0.42, 0.41, 0.43, 0.19, 0.28, 1.00, 0.31, 0.21, 0.25, 0.31, 0.18, -0.05],
 [0.53, 0.42, 0.48, 0.49, 0.46, 0.17, 0.46, 0.31, 1.00, 0.33, 0.16, 0.54, 0.38,  0.00],
 [0.25, 0.24, 0.23, 0.21, 0.24, 0.15, 0.55, 0.21, 0.33, 1.00, 0.13, 0.35, 0.42,  0.07],
 [0.25, 0.20, 0.38, 0.25, 0.39, 0.08, 0.08, 0.25, 0.16, 0.13, 1.00, 0.09, 0.10,  0.11],
 [0.48, 0.41, 0.46, 0.41, 0.45, 0.14, 0.50, 0.31, 0.54, 0.35, 0.09, 1.00, 0.41,  0.06],
 [0.30, 0.24, 0.25, 0.25, 0.27, 0.17, 0.66, 0.18, 0.38, 0.42, 0.10, 0.41, 1.00,  0.07],
 [0.01,-0.03,-0.06,-0.06,-0.04, 0.02, 0.05,-0.05, 0.00, 0.07, 0.11, 0.06, 0.07,  1.00],
])

# Solo operator mean coverage (from corr_output.txt Phase 3)
SOLO_MCOV = {
    "Phase": 86, "Wavelet": 84, "Topo": 78, "Geometric": 75,
    "Legendre": 75, "Recon": 73, "Exponential": 73, "Fourier": 72,
    "BSpline": 71, "Dependency": 67, "Kernel": 67, "Rank": 67,
    "Compress": 51, "Statistical": 30,
}

# Solo operator mean AUC (from corr_output.txt Phase 3)
SOLO_MAUC = {
    "Phase": 0.9601, "Wavelet": 0.9595, "Topo": 0.9273, "Geometric": 0.8921,
    "Legendre": 0.9142, "Recon": 0.8757, "Exponential": 0.8855, "Fourier": 0.8789,
    "BSpline": 0.8975, "Dependency": 0.8461, "Kernel": 0.8707, "Rank": 0.8606,
    "Compress": 0.6478, "Statistical": 0.7154,
}

# Strategy coverage per dataset (from lean_results.txt)
STRATEGY_COV = {
    "Fisher":     [100, 100, 49, 54, 13],
    "RankFuse":   [100, 100, 59, 94, 89],
    "QuadSurf":   [100,  73, 69, 92, 96],
    "Hybrid":     [100, 100, 65, 98, 93],
    "MetaFusion": [100, 100, 58, 98, 57],
}
STRATEGY_AUC = {
    "Fisher":     [1.000, 1.000, 0.884, 0.760, 0.345],
    "RankFuse":   [0.999, 1.000, 0.910, 0.979, 0.956],
    "QuadSurf":   [1.000, 0.798, 0.912, 0.920, 0.966],
    "Hybrid":     [0.999, 0.999, 0.911, 0.991, 0.960],
    "MetaFusion": [1.000, 0.995, 0.917, 0.974, 0.866],
}
STRATEGY_MCOV  = {"Fisher": 63, "RankFuse": 88, "QuadSurf": 86, "Hybrid": 91, "MetaFusion": 83}
STRATEGY_MINCOV= {"Fisher": 13, "RankFuse": 59, "QuadSurf": 69, "Hybrid": 65, "MetaFusion": 57}


# ══════════════════════════════════════════════════════════════════
#  FIGURE 1: Operator Correlation Heatmap (clustered)
# ══════════════════════════════════════════════════════════════════
def fig1_correlation_heatmap():
    # Hierarchical clustering for ordering
    dist = 1 - np.abs(CORR_MATRIX)
    np.fill_diagonal(dist, 0)
    condensed = squareform(dist)
    Z = linkage(condensed, method="ward")
    order = leaves_list(Z)

    mat_ordered = CORR_MATRIX[np.ix_(order, order)]
    names_ordered = [OP_NAMES[i] for i in order]

    fig, ax = plt.subplots(figsize=(5.5, 4.8))

    # Custom diverging colormap: blue → white → red
    cmap = cm.RdBu_r
    norm = mcolors.TwoSlopeNorm(vmin=-0.1, vcenter=0.0, vmax=1.0)

    im = ax.imshow(mat_ordered, cmap=cmap, norm=norm, aspect="equal")

    # Annotate cells
    for i in range(14):
        for j in range(14):
            v = mat_ordered[i, j]
            color = "white" if abs(v) > 0.6 else "black"
            fontw = "bold" if abs(v) > 0.80 else "normal"
            ax.text(j, i, f"{v:.2f}", ha="center", va="center",
                    fontsize=6, color=color, fontweight=fontw)

    ax.set_xticks(range(14))
    ax.set_yticks(range(14))
    ax.set_xticklabels(names_ordered, rotation=45, ha="right", fontsize=7)
    ax.set_yticklabels(names_ordered, fontsize=7)

    # Color-code tick labels by family
    for i, name in enumerate(names_ordered):
        fam = OP_FAMILY.get(name, "Algebraic")
        ax.get_xticklabels()[i].set_color(FAMILY_COLORS[fam])
        ax.get_yticklabels()[i].set_color(FAMILY_COLORS[fam])

    cbar = fig.colorbar(im, ax=ax, shrink=0.82, pad=0.02)
    cbar.set_label("Spearman $\\rho$", fontsize=8)

    # Mark the one redundant pair with a box
    for i, n1 in enumerate(names_ordered):
        for j, n2 in enumerate(names_ordered):
            if {n1, n2} == {"Wavelet", "Phase"} and i != j:
                rect = plt.Rectangle((j-0.5, i-0.5), 1, 1,
                                     fill=False, edgecolor="#C73E1D",
                                     linewidth=2, linestyle="--")
                ax.add_patch(rect)

    ax.set_title("Inter-Operator Spearman Correlation\n(hierarchically clustered)",
                 fontsize=10, fontweight="bold", pad=8)

    # Legend for families
    from matplotlib.lines import Line2D
    handles = [Line2D([0],[0], marker="s", color="w",
                      markerfacecolor=c, markersize=7, label=f)
               for f, c in FAMILY_COLORS.items()]
    ax.legend(handles=handles, loc="lower left", fontsize=6,
              framealpha=0.9, ncol=2, handletextpad=0.3,
              borderpad=0.3, columnspacing=0.5)

    fig.savefig(os.path.join(OUT_DIR, "operator_correlation_heatmap.pdf"))
    plt.close(fig)
    print("  ✓ operator_correlation_heatmap.pdf")


# ══════════════════════════════════════════════════════════════════
#  FIGURE 2: 2D Projection Scatter (live data)
# ══════════════════════════════════════════════════════════════════
def fig2_projection_scatter():
    """2D Fisher-projected scatter for 3 datasets side by side.
    Memory-safe: loads one dataset at a time, keeps only 2D coords."""
    import gc
    from sklearn.model_selection import train_test_split

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from udl.compare_sota import load_all_datasets
    from udl.pipeline import UDLPipeline
    from udl.meta_fusion import default_operators

    datasets_to_plot = ["mammography", "shuttle", "pendigits"]
    nice_names = {"mammography": "Mammography", "shuttle": "Shuttle", "pendigits": "Pendigits"}

    # Pre-compute scatter data one dataset at a time, store only coords
    scatter_data = {}
    all_ds = load_all_datasets()
    for ds_name in datasets_to_plot:
        X, y = all_ds[ds_name]
        # Subsample large datasets to avoid OOM (keep 2000 max)
        if len(X) > 2000:
            rng = np.random.RandomState(42)
            idx = rng.choice(len(X), 2000, replace=False)
            X, y = X[idx], y[idx]
        X_tr, X_te, y_tr, y_te = train_test_split(
            X, y, test_size=0.3, stratify=y, random_state=42)
        pipe = UDLPipeline(
            operators=default_operators(),
            centroid_method="auto",
            projection_method="fisher",
        )
        pipe.fit(X_tr, y_tr)
        tr = pipe.build_tensor(X_te)
        law_mags = tr.law_magnitudes
        scatter_data[ds_name] = {
            "x1": law_mags[:, 0].copy(),
            "x2": law_mags[:, 1].copy(),
            "y": y_te.copy(),
        }
        del pipe, X, y, X_tr, X_te, y_tr, y_te, law_mags, tr
        gc.collect()
    del all_ds
    gc.collect()

    fig, axes = plt.subplots(1, 3, figsize=(7.0, 2.5))
    for ax, ds_name in zip(axes, datasets_to_plot):
        d = scatter_data[ds_name]
        norm_mask = d["y"] == 0
        anom_mask = d["y"] == 1
        ax.scatter(d["x1"][norm_mask], d["x2"][norm_mask],
                   s=4, alpha=0.25, c="#90B4CE", edgecolors="none",
                   label="Normal", rasterized=True)
        ax.scatter(d["x1"][anom_mask], d["x2"][anom_mask],
                   s=18, alpha=0.85, c="#C73E1D", edgecolors="white",
                   linewidths=0.3, label="Anomaly", zorder=5)
        ax.set_title(nice_names[ds_name], fontsize=9, fontweight="bold")
        ax.set_xlabel("Law dimension 1", fontsize=7)
        if ax == axes[0]:
            ax.set_ylabel("Law dimension 2", fontsize=7)
        ax.tick_params(labelsize=6)

    axes[-1].legend(fontsize=7, loc="upper right", framealpha=0.9,
                     markerscale=1.5, handletextpad=0.2)
    fig.suptitle("UDL Multi-Law Projection: Anomaly Separation in 2D",
                 fontsize=10, fontweight="bold", y=1.02)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "projection_scatter.pdf"))
    plt.close(fig)
    del scatter_data
    gc.collect()
    print("  ✓ projection_scatter.pdf")


# ══════════════════════════════════════════════════════════════════
#  FIGURE 3: Coverage Radar Chart
# ══════════════════════════════════════════════════════════════════
def fig3_coverage_radar():
    categories = DATASET_NAMES
    N = len(categories)
    angles = [n / float(N) * 2 * pi for n in range(N)]
    angles += angles[:1]  # close polygon

    fig, ax = plt.subplots(figsize=(4.2, 4.2), subplot_kw=dict(polar=True))

    strategies_to_plot = ["Fisher", "RankFuse", "QuadSurf", "Hybrid"]

    for strat in strategies_to_plot:
        vals = [v / 100.0 for v in STRATEGY_COV[strat]]
        vals += vals[:1]
        color = STRATEGY_COLORS[strat]

        ax.plot(angles, vals, linewidth=1.8, label=strat, color=color)
        ax.fill(angles, vals, alpha=0.08, color=color)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(categories, fontsize=8)
    ax.set_ylim(0, 1.05)
    ax.set_yticks([0.25, 0.50, 0.75, 1.00])
    ax.set_yticklabels(["25%", "50%", "75%", "100%"], fontsize=6, color="grey")
    ax.spines["polar"].set_visible(False)

    ax.set_title("Coverage Profile by Strategy\nacross 5 Benchmark Datasets",
                 fontsize=10, fontweight="bold", pad=18)
    ax.legend(loc="lower right", bbox_to_anchor=(1.25, -0.05),
              fontsize=8, framealpha=0.9)

    fig.savefig(os.path.join(OUT_DIR, "coverage_radar.pdf"))
    plt.close(fig)
    print("  ✓ coverage_radar.pdf")


# ══════════════════════════════════════════════════════════════════
#  FIGURE 4: Strategy × Dataset Coverage Heatmap
# ══════════════════════════════════════════════════════════════════
def fig4_strategy_heatmap():
    strats = ["Fisher", "RankFuse", "QuadSurf", "Hybrid", "MetaFusion"]
    data = np.array([STRATEGY_COV[s] for s in strats]) / 100.0

    fig, ax = plt.subplots(figsize=(5.0, 2.8))

    cmap = plt.cm.YlOrRd
    norm = mcolors.Normalize(vmin=0.0, vmax=1.0)
    im = ax.imshow(data, cmap=cmap, norm=norm, aspect="auto")

    # Annotate
    for i in range(len(strats)):
        for j in range(5):
            v = data[i, j]
            color = "white" if v > 0.7 else "black"
            fontw = "bold" if v >= 0.90 else "normal"
            pct = f"{int(v*100)}%"
            ax.text(j, i, pct, ha="center", va="center",
                    fontsize=9, color=color, fontweight=fontw)

    ax.set_xticks(range(5))
    ax.set_yticks(range(len(strats)))
    ax.set_xticklabels(DATASET_NAMES, fontsize=8)

    # Add mCov and minCov as extra columns visually
    ylabels = []
    for s in strats:
        ylabels.append(f"{s}  (mCov={STRATEGY_MCOV[s]}%)")
    ax.set_yticklabels(ylabels, fontsize=8)

    cbar = fig.colorbar(im, ax=ax, shrink=0.9, pad=0.02)
    cbar.set_label("Top-$k$ Coverage", fontsize=8)

    ax.set_title("Anomaly Coverage: Strategy × Dataset",
                 fontsize=10, fontweight="bold", pad=6)

    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "strategy_coverage_heatmap.pdf"))
    plt.close(fig)
    print("  ✓ strategy_coverage_heatmap.pdf")


# ══════════════════════════════════════════════════════════════════
#  FIGURE 5: Solo Operator Coverage (ranked bar chart)
# ══════════════════════════════════════════════════════════════════
def fig5_operator_bars():
    # Sort by mCov descending
    items = sorted(SOLO_MCOV.items(), key=lambda x: -x[1])
    names = [x[0] for x in items]
    covs  = [x[1] for x in items]
    colors = [FAMILY_COLORS[OP_FAMILY[n]] for n in names]

    fig, ax = plt.subplots(figsize=(5.5, 3.0))

    bars = ax.barh(range(len(names)), covs, color=colors, edgecolor="white",
                   linewidth=0.5, height=0.72)

    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("Mean Coverage (mCov %)", fontsize=9)
    ax.set_xlim(0, 100)

    # Annotate bars
    for i, (bar, v) in enumerate(zip(bars, covs)):
        ax.text(v + 1.5, i, f"{v}%", va="center", fontsize=7, fontweight="bold")

    # Vertical line at 70% threshold
    ax.axvline(70, color="grey", linestyle="--", linewidth=0.8, alpha=0.5)
    ax.text(71, len(names)-0.5, "70% threshold", fontsize=6, color="grey",
            va="top")

    ax.set_title("Solo Operator Mean Coverage (14 Operators, 5 Datasets)",
                 fontsize=10, fontweight="bold", pad=6)

    # Family legend
    from matplotlib.lines import Line2D
    handles = [Line2D([0],[0], marker="s", color="w",
                      markerfacecolor=c, markersize=7, label=f)
               for f, c in FAMILY_COLORS.items()]
    ax.legend(handles=handles, loc="lower right", fontsize=6.5,
              framealpha=0.9, ncol=1, handletextpad=0.3)

    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "operator_solo_coverage.pdf"))
    plt.close(fig)
    print("  ✓ operator_solo_coverage.pdf")


# ══════════════════════════════════════════════════════════════════
#  FIGURE 6: AUC vs Coverage Scatter
# ══════════════════════════════════════════════════════════════════
def fig6_auc_vs_coverage():
    fig, ax = plt.subplots(figsize=(4.5, 3.8))

    # Plot each strategy
    for strat in ["Fisher", "RankFuse", "QuadSurf", "Hybrid", "MetaFusion"]:
        aucs = STRATEGY_AUC[strat]
        covs = [c / 100.0 for c in STRATEGY_COV[strat]]
        color = STRATEGY_COLORS[strat]

        ax.scatter(aucs, covs, s=50, c=color, edgecolors="white",
                   linewidths=0.5, label=strat, zorder=5)

        # Connect points for same strategy
        for a, c, ds in zip(aucs, covs, DATASET_NAMES):
            ax.annotate(ds[0], (a, c), fontsize=5, color=color, alpha=0.7,
                       textcoords="offset points", xytext=(3, 3))

    # Diagonal reference line (AUC = Coverage dream)
    ax.plot([0.3, 1.05], [0.3, 1.05], "k--", alpha=0.15, linewidth=0.8)
    ax.text(0.45, 0.42, "AUC = Cov", fontsize=6, color="grey", alpha=0.5,
            rotation=38)

    # Highlight the "danger zone": high AUC, low coverage
    ax.fill_between([0.7, 1.05], 0, 0.55, alpha=0.04, color="red")
    ax.text(0.82, 0.08, "High AUC,\nLow Coverage", fontsize=6.5,
            color="#C73E1D", alpha=0.6, ha="center", style="italic")

    ax.set_xlabel("AUC-ROC", fontsize=9)
    ax.set_ylabel("Top-$k$ Coverage", fontsize=9)
    ax.set_xlim(0.3, 1.05)
    ax.set_ylim(0, 1.05)

    ax.set_title("AUC vs Coverage: Different Metrics,\nDifferent Stories",
                 fontsize=10, fontweight="bold", pad=6)
    ax.legend(fontsize=7, loc="upper left", framealpha=0.9)

    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "auc_vs_coverage.pdf"))
    plt.close(fig)
    print("  ✓ auc_vs_coverage.pdf")


# ══════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import gc
    print("Generating publication figures...")
    print(f"Output directory: {OUT_DIR}\n")

    # Static figures first (no data loading)
    fig1_correlation_heatmap(); gc.collect()
    fig3_coverage_radar(); gc.collect()
    fig4_strategy_heatmap(); gc.collect()
    fig5_operator_bars(); gc.collect()
    fig6_auc_vs_coverage(); gc.collect()

    # Figure 2 requires UDL imports + data loading
    try:
        fig2_projection_scatter(); gc.collect()
    except Exception as e:
        print(f"  ⚠ projection_scatter.pdf SKIPPED: {e}")

    print(f"\nDone. {len(os.listdir(OUT_DIR))} files in {OUT_DIR}")
