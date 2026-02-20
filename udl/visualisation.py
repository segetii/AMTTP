"""
UDL Visualisation — Publication-Quality Figures
=================================================
Generates diagrams for the Universal Deviation Law paper:
  1. Multi-spectrum representation heatmap
  2. Tensor MDN decomposition polar plot
  3. Hyperplane projection scatter
  4. Cross-law coupling matrix
  5. Cross-domain AUC comparison bar chart
"""

import numpy as np

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec
    HAS_MPL = True
except ImportError:
    HAS_MPL = False


def _check_mpl():
    if not HAS_MPL:
        raise ImportError("matplotlib required. Install: pip install matplotlib")


def plot_spectrum_heatmap(tensor_result, law_names=None, n_samples=50,
                          title="Multi-Spectrum Representation", save_path=None):
    """
    Heatmap of representation values across law domains.

    Each row = observation, columns grouped by law domain.
    """
    _check_mpl()
    fig, ax = plt.subplots(figsize=(14, 6))

    R = tensor_result.raw[:n_samples]
    dims = tensor_result.law_dims
    names = law_names or [f"Law {k}" for k in range(len(dims))]

    im = ax.imshow(R, aspect="auto", cmap="RdBu_r", interpolation="nearest")
    ax.set_xlabel("Representation Dimension")
    ax.set_ylabel("Observation Index")
    ax.set_title(title)

    # Mark law boundaries
    offset = 0
    for k, (name, dim) in enumerate(zip(names, dims)):
        mid = offset + dim / 2
        ax.axvline(offset - 0.5, color="black", linewidth=0.5, alpha=0.5)
        ax.text(mid, -1.5, name, ha="center", va="bottom", fontsize=8,
                fontweight="bold")
        offset += dim

    plt.colorbar(im, ax=ax, label="Feature Value")
    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches="tight")
    return fig


def plot_mdn_decomposition(tensor_result, y=None, title="MDN Decomposition",
                           save_path=None):
    """
    Polar plot: magnitude (radius) vs novelty (angle).
    Colour = anomaly label (if available).
    """
    _check_mpl()
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    mag = tensor_result.magnitude
    nov = tensor_result.novelty
    scores = tensor_result.anomaly_score()

    if y is not None:
        colors = ['steelblue' if yi == 0 else 'crimson' for yi in y]
    else:
        colors = plt.cm.viridis(scores / (scores.max() + 1e-10))

    # Left: Magnitude vs Novelty scatter
    ax = axes[0]
    ax.scatter(mag, nov, c=colors, alpha=0.5, s=15, edgecolors="none")
    ax.set_xlabel("Magnitude ||v||")
    ax.set_ylabel("Novelty (angular)")
    ax.set_title("Magnitude vs Novelty")
    if y is not None:
        from matplotlib.lines import Line2D
        legend = [
            Line2D([0], [0], marker='o', color='w', markerfacecolor='steelblue',
                   label='Normal', markersize=8),
            Line2D([0], [0], marker='o', color='w', markerfacecolor='crimson',
                   label='Anomaly', markersize=8),
        ]
        ax.legend(handles=legend)

    # Right: Score distribution
    ax = axes[1]
    if y is not None:
        ax.hist(scores[y == 0], bins=50, alpha=0.6, color="steelblue",
                label="Normal", density=True)
        ax.hist(scores[y == 1], bins=50, alpha=0.6, color="crimson",
                label="Anomaly", density=True)
        ax.legend()
    else:
        ax.hist(scores, bins=50, alpha=0.7, color="steelblue", density=True)
    ax.set_xlabel("Composite Anomaly Score")
    ax.set_ylabel("Density")
    ax.set_title("Score Distribution")

    fig.suptitle(title, fontsize=14, fontweight="bold")
    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches="tight")
    return fig


def plot_hyperplane_projection(projector, R, y=None,
                               title="Hyperplane Projection",
                               save_path=None):
    """
    1D projection onto hyperplane normal, showing class separation.
    """
    _check_mpl()
    fig, ax = plt.subplots(figsize=(10, 5))

    scores = projector.project(R).ravel()

    if y is not None:
        ax.hist(scores[y == 0], bins=50, alpha=0.6, color="steelblue",
                label=f"Normal (n={sum(y==0)})", density=True)
        ax.hist(scores[y == 1], bins=50, alpha=0.6, color="crimson",
                label=f"Anomaly (n={sum(y==1)})", density=True)
        ax.legend(fontsize=11)
    else:
        ax.hist(scores, bins=50, alpha=0.7, color="steelblue", density=True)

    if projector.threshold_ is not None:
        ax.axvline(projector.threshold_, color="black", linestyle="--",
                   linewidth=2, label=f"Threshold={projector.threshold_:.2f}")
        ax.legend()

    ax.set_xlabel("Projection Score (hyperplane normal direction)")
    ax.set_ylabel("Density")
    ax.set_title(title)
    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches="tight")
    return fig


def plot_coupling_matrix(coupling, law_names=None,
                         title="Cross-Law Coupling Matrix",
                         save_path=None):
    """
    Heatmap of cross-law correlation matrix.
    """
    _check_mpl()
    K = coupling.shape[0]
    names = law_names or [f"Law {k}" for k in range(K)]

    fig, ax = plt.subplots(figsize=(7, 6))
    im = ax.imshow(coupling, cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(K))
    ax.set_yticks(range(K))
    ax.set_xticklabels(names, rotation=45, ha="right")
    ax.set_yticklabels(names)

    for i in range(K):
        for j in range(K):
            ax.text(j, i, f"{coupling[i,j]:.2f}", ha="center", va="center",
                    fontsize=9, color="white" if abs(coupling[i,j]) > 0.5 else "black")

    plt.colorbar(im, ax=ax, label="Correlation")
    ax.set_title(title)
    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches="tight")
    return fig


def plot_cross_domain_results(results_dict, title="UDL Cross-Domain AUC",
                              save_path=None):
    """
    Bar chart comparing AUC across domains.

    Parameters
    ----------
    results_dict : dict of {name: auc}
    """
    _check_mpl()
    names = list(results_dict.keys())
    aucs = list(results_dict.values())

    fig, ax = plt.subplots(figsize=(10, 5))
    bars = ax.bar(names, aucs, color=plt.cm.Set2(np.linspace(0, 1, len(names))),
                  edgecolor="black", linewidth=0.5)

    ax.axhline(0.5, color="gray", linestyle="--", linewidth=1, alpha=0.5,
               label="Random baseline")
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("AUC-ROC")
    ax.set_title(title)

    for bar, auc in zip(bars, aucs):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.01,
                f"{auc:.3f}", ha="center", va="bottom", fontsize=10,
                fontweight="bold")

    ax.legend()
    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches="tight")
    return fig
