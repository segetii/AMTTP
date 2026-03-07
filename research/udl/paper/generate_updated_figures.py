"""
Generate updated charts for the UDL paper from the latest standalone benchmark.

Produces:
  1. udl_vs_baselines_bar.pdf  — Grouped bar: UDL methods vs XGB/LGB per dataset
  2. udl_mAUC_summary.pdf      — Horizontal bar: mean AUC across all datasets
"""

import os, sys, json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ── Paths ──────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(SCRIPT_DIR, "figures")
RESULTS_FILE = os.path.join(SCRIPT_DIR, "..", "src", "results", "layer2_standalone.json")
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

# ── Load results ──────────────────────────────────────────────────
with open(RESULTS_FILE) as f:
    data = json.load(f)

DATASETS = ["Mammo", "AnnThy", "PenDig", "Satell"]
NICE_NAMES = {"Mammo": "Mammography", "AnnThy": "Annthyroid",
              "PenDig": "Pendigits", "Satell": "Satellite"}

UDL_METHODS = ["UDL-QDA", "UDL-QDA-Opt", "UDL-L2-Score"]
BASELINES = ["XGB-raw", "LGB-raw"]
ALL_METHODS = UDL_METHODS + BASELINES

# UDL colour palette (blue tones)
UDL_COLORS = {
    "UDL-QDA":      "#2E86AB",
    "UDL-QDA-Opt":  "#1B4965",
    "UDL-L2-Score": "#5FA8D3",
    "UDL-L2-QDA":   "#A8DADC",
    "UDL-Full":     "#457B9D",
}
# Baseline colours (grey/red tones)
BASELINE_COLORS = {
    "XGB-raw": "#E76F51",
    "LGB-raw": "#F4A261",
}

def get_color(method):
    if method in UDL_COLORS:
        return UDL_COLORS[method]
    return BASELINE_COLORS.get(method, "#999999")


# ══════════════════════════════════════════════════════════════════
#  FIGURE A: Grouped Bar Chart — UDL vs Baselines per Dataset
# ══════════════════════════════════════════════════════════════════
def fig_grouped_bar():
    n_datasets = len(DATASETS)
    n_methods = len(ALL_METHODS)
    bar_width = 0.13
    x = np.arange(n_datasets)

    fig, ax = plt.subplots(figsize=(7.0, 3.5))

    for i, method in enumerate(ALL_METHODS):
        vals = [data[ds].get(method, 0) for ds in DATASETS]
        offset = (i - n_methods / 2 + 0.5) * bar_width
        bars = ax.bar(x + offset, vals, bar_width, label=method,
                      color=get_color(method), edgecolor="white", linewidth=0.5)
        # Value labels on top
        for bar, v in zip(bars, vals):
            if v > 0.6:
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.005,
                        f"{v:.3f}", ha="center", va="bottom", fontsize=5.5, rotation=90)

    ax.set_xticks(x)
    ax.set_xticklabels([NICE_NAMES[ds] for ds in DATASETS], fontsize=9)
    ax.set_ylabel("AUC-ROC", fontsize=9)
    ax.set_ylim(0.5, 1.05)
    ax.axhline(0.9, color="grey", linestyle=":", linewidth=0.5, alpha=0.5)

    # Two-part legend
    ax.legend(fontsize=7, loc="lower left", ncol=2, framealpha=0.9,
              columnspacing=0.8, handletextpad=0.4)

    ax.set_title("UDL Standalone Methods vs Supervised Baselines (5-fold CV)",
                 fontsize=10, fontweight="bold", pad=8)

    fig.tight_layout()
    path = os.path.join(OUT_DIR, "udl_vs_baselines_bar.pdf")
    fig.savefig(path)
    plt.close(fig)
    print(f"  ✓ {os.path.basename(path)}")


# ══════════════════════════════════════════════════════════════════
#  FIGURE B: Horizontal Bar — Mean AUC Summary
# ══════════════════════════════════════════════════════════════════
def fig_mean_auc():
    all_methods_full = ["UDL-QDA", "UDL-QDA-Opt", "UDL-L2-Score",
                        "UDL-L2-QDA", "UDL-Full", "XGB-raw", "LGB-raw"]

    mean_aucs = {}
    for m in all_methods_full:
        vals = [data[ds].get(m, 0) for ds in DATASETS]
        mean_aucs[m] = np.mean(vals)

    # Sort by mAUC
    sorted_methods = sorted(mean_aucs, key=mean_aucs.get)
    sorted_vals = [mean_aucs[m] for m in sorted_methods]
    colors = [get_color(m) for m in sorted_methods]

    fig, ax = plt.subplots(figsize=(5.5, 3.5))

    bars = ax.barh(range(len(sorted_methods)), sorted_vals,
                   color=colors, edgecolor="white", linewidth=0.5, height=0.65)

    ax.set_yticks(range(len(sorted_methods)))

    # Label UDL methods with "(ours)"
    labels = []
    for m in sorted_methods:
        if "UDL" in m:
            labels.append(f"{m} (ours)")
        else:
            labels.append(f"{m} (baseline)")
    ax.set_yticklabels(labels, fontsize=8)

    ax.set_xlabel("Mean AUC-ROC (4 datasets)", fontsize=9)
    ax.set_xlim(0.5, 1.02)

    # Annotate values
    for i, (bar, v) in enumerate(zip(bars, sorted_vals)):
        ax.text(v + 0.005, i, f"{v:.4f}", va="center", fontsize=7.5,
                fontweight="bold")

    # Vertical separator between UDL and baselines
    ax.axvline(0.9, color="grey", linestyle=":", linewidth=0.5, alpha=0.5)

    ax.set_title("Mean AUC-ROC Across 4 ODDS Benchmarks\n(UDL Standalone vs Supervised Baselines)",
                 fontsize=10, fontweight="bold", pad=8)

    fig.tight_layout()
    path = os.path.join(OUT_DIR, "udl_mAUC_summary.pdf")
    fig.savefig(path)
    plt.close(fig)
    print(f"  ✓ {os.path.basename(path)}")


# ══════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("Generating updated benchmark figures...")
    print(f"  Results: {RESULTS_FILE}")
    print(f"  Output:  {OUT_DIR}\n")

    fig_grouped_bar()
    fig_mean_auc()

    # Also regenerate existing static figures
    sys.path.insert(0, SCRIPT_DIR)
    try:
        from generate_figures import (
            fig1_correlation_heatmap, fig3_coverage_radar,
            fig4_strategy_heatmap, fig5_operator_bars,
            fig6_auc_vs_coverage
        )
        fig1_correlation_heatmap()
        fig3_coverage_radar()
        fig4_strategy_heatmap()
        fig5_operator_bars()
        fig6_auc_vs_coverage()
    except Exception as e:
        print(f"  ⚠ Existing figures skipped: {e}")

    print(f"\nDone. Figures in {OUT_DIR}")
