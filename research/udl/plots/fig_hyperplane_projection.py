"""
Hyperplane Projection Visualization
=====================================
Shows how the Fisher Linear Discriminant projects multi-spectrum
representation vectors onto the separating hyperplane.

Produces a 4-panel figure:
  (a) 2D PCA view of representation space with hyperplane
  (b) 1D projection histogram (normal vs anomaly)
  (c) Scatter of parallel vs perpendicular components
  (d) 3D view: two principal components + projection axis
"""

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch
from mpl_toolkits.mplot3d import Axes3D
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

from udl.pipeline import UDLPipeline
from udl.spectra import (
    StatisticalSpectrum, ChaosSpectrum, SpectralSpectrum,
    GeometricSpectrum, ReconstructionSpectrum,
)
from udl.datasets import make_synthetic


# ── Colours ──
C_NORMAL  = "#2196F3"  # blue
C_ANOMALY = "#F44336"  # red
C_HYPER   = "#4CAF50"  # green  (hyperplane line)
C_PROJ    = "#FF9800"  # orange (projection arrows)
C_CENTROID= "#9C27B0"  # purple


def build_pipeline():
    ops = [
        ("statistical", StatisticalSpectrum()),
        ("chaos",       ChaosSpectrum()),
        ("spectral",    SpectralSpectrum()),
        ("geometric",   GeometricSpectrum()),
        ("recon",       ReconstructionSpectrum()),
    ]
    return UDLPipeline(
        operators=ops,
        centroid_method="auto",
        projection_method="fisher",
    )


def main():
    print("Loading data …")
    X, y = make_synthetic()
    # Split
    from sklearn.model_selection import train_test_split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.3, random_state=42, stratify=y,
    )

    print("Fitting UDL pipeline …")
    pipe = build_pipeline()
    pipe.fit(X_train, y_train)

    # Get representations
    R_test = pipe.transform(X_test)
    centroid = pipe.centroid_est.get_centroid()
    W = pipe.projector.W_.ravel()          # Fisher direction (D-dim)
    threshold = pipe.projector.threshold_

    # Decompose each test vector
    decomp = pipe.projector.decompose_vector(R_test)
    proj_scores = pipe.projector.project(R_test).ravel()

    # ── PCA for 2D/3D visualisation of the D-dimensional space ──
    pca2 = PCA(n_components=2, random_state=42)
    R2 = pca2.fit_transform(R_test)  # (N, 2)

    # Project the Fisher direction into PCA-2D space
    W_unit = W / (np.linalg.norm(W) + 1e-10)
    W_2d = pca2.transform(W_unit.reshape(1, -1) + centroid) - pca2.transform(centroid.reshape(1, -1))
    W_2d = W_2d.ravel()
    W_2d /= (np.linalg.norm(W_2d) + 1e-10)

    # Centroid in PCA space
    c_2d = pca2.transform(centroid.reshape(1, -1)).ravel()

    mask_n = y_test == 0
    mask_a = y_test == 1

    # ── Figure ──
    fig = plt.figure(figsize=(16, 14))
    fig.suptitle(
        "Fisher Linear Discriminant — Hyperplane Projection\n"
        r"$\mathbf{w}^* = S_W^{-1}(\boldsymbol{\mu}_1 - \boldsymbol{\mu}_0)$"
        "  projects D-dim representation onto 1-D decision axis",
        fontsize=14, fontweight="bold", y=0.98,
    )

    # ─────────────────────────────────────────────
    # (a) 2D PCA view with hyperplane & projection arrows
    # ─────────────────────────────────────────────
    ax1 = fig.add_subplot(2, 2, 1)
    ax1.scatter(R2[mask_n, 0], R2[mask_n, 1], c=C_NORMAL, alpha=0.4,
                s=15, label="Normal", edgecolors="none")
    ax1.scatter(R2[mask_a, 0], R2[mask_a, 1], c=C_ANOMALY, alpha=0.6,
                s=25, label="Anomaly", edgecolors="none")

    # Draw Fisher axis (projection direction)
    arrow_len = np.ptp(R2[:, 0]) * 0.4
    ax1.annotate("", xy=c_2d + W_2d * arrow_len, xytext=c_2d,
                 arrowprops=dict(arrowstyle="-|>", color=C_PROJ, lw=2.5))
    ax1.text(*(c_2d + W_2d * arrow_len * 1.05), r"$\mathbf{w}^*$",
             fontsize=14, color=C_PROJ, fontweight="bold",
             ha="center", va="bottom")

    # Draw the hyperplane (perpendicular to w at threshold location)
    # In 2D: direction perpendicular to W_2d
    perp_2d = np.array([-W_2d[1], W_2d[0]])

    # Map the threshold to 2D: point along W_2d at threshold distance
    # First find where threshold falls in PCA space
    # threshold is in projected 1D space — scale appropriately
    t_proj_scores_2d = R2 @ W_2d  # scalar proj in 2D PCA space
    t_scale = threshold * np.std(t_proj_scores_2d) / (np.std(proj_scores) + 1e-10)
    t_point = c_2d + W_2d * t_scale

    hp_len = np.ptp(R2[:, 1]) * 0.6
    hp_start = t_point - perp_2d * hp_len
    hp_end   = t_point + perp_2d * hp_len
    ax1.plot([hp_start[0], hp_end[0]], [hp_start[1], hp_end[1]],
             color=C_HYPER, lw=2.5, ls="--", label="Decision hyperplane")

    # Draw a few example projection arrows (from point to its projection on w)
    rng = np.random.RandomState(99)
    sample_idx = rng.choice(len(R2), min(12, len(R2)), replace=False)
    for i in sample_idx:
        pt = R2[i]
        proj_on_w = c_2d + W_2d * np.dot(pt - c_2d, W_2d)
        colour = C_ANOMALY if y_test[i] == 1 else C_NORMAL
        ax1.plot([pt[0], proj_on_w[0]], [pt[1], proj_on_w[1]],
                 color=colour, alpha=0.3, lw=0.8, ls=":")

    ax1.plot(*c_2d, marker="*", color=C_CENTROID, markersize=18, zorder=5,
             markeredgecolor="k", markeredgewidth=0.5, label="Centroid")

    ax1.set_xlabel("PC-1", fontsize=11)
    ax1.set_ylabel("PC-2", fontsize=11)
    ax1.set_title("(a) Representation Space — PCA-2D View", fontsize=12, fontweight="bold")
    ax1.legend(fontsize=8, loc="upper left")
    ax1.grid(True, alpha=0.2)

    # ─────────────────────────────────────────────
    # (b) 1D projection histogram
    # ─────────────────────────────────────────────
    ax2 = fig.add_subplot(2, 2, 2)
    bins = np.linspace(proj_scores.min(), proj_scores.max(), 50)
    ax2.hist(proj_scores[mask_n], bins=bins, alpha=0.6, color=C_NORMAL,
             label="Normal", density=True, edgecolor="white", lw=0.5)
    ax2.hist(proj_scores[mask_a], bins=bins, alpha=0.6, color=C_ANOMALY,
             label="Anomaly", density=True, edgecolor="white", lw=0.5)
    ax2.axvline(threshold, color=C_HYPER, lw=2.5, ls="--",
                label=f"Threshold = {threshold:.2f}")

    # Add formula annotation
    ax2.annotate(
        r"$s_i = (\mathbf{r}_i - \mathbf{c}) \cdot \mathbf{w}^*$"
        "\n"
        r"$\hat{y}_i = \mathbb{1}[s_i > \tau]$",
        xy=(0.98, 0.95), xycoords="axes fraction",
        fontsize=12, ha="right", va="top",
        bbox=dict(boxstyle="round,pad=0.4", fc="lightyellow", ec="gray", alpha=0.9),
    )

    ax2.set_xlabel("Fisher Projection Score  $s = (\\mathbf{r} - \\mathbf{c}) \\cdot \\mathbf{w}^*$",
                   fontsize=11)
    ax2.set_ylabel("Density", fontsize=11)
    ax2.set_title("(b) 1-D Projection — Class Separation", fontsize=12, fontweight="bold")
    ax2.legend(fontsize=9)
    ax2.grid(True, alpha=0.2)

    # ─────────────────────────────────────────────
    # (c) Parallel vs Perpendicular decomposition
    # ─────────────────────────────────────────────
    ax3 = fig.add_subplot(2, 2, 3)
    ax3.scatter(decomp["parallel"][mask_n], decomp["perpendicular"][mask_n],
                c=C_NORMAL, alpha=0.4, s=15, label="Normal", edgecolors="none")
    ax3.scatter(decomp["parallel"][mask_a], decomp["perpendicular"][mask_a],
                c=C_ANOMALY, alpha=0.6, s=25, label="Anomaly", edgecolors="none")

    # Add explanatory annotations
    ax3.annotate(
        "Parallel = discriminative\n(along hyperplane normal $\\mathbf{w}^*$)\n"
        "→ class-separating signal",
        xy=(0.02, 0.98), xycoords="axes fraction",
        fontsize=8, ha="left", va="top",
        bbox=dict(boxstyle="round", fc="lightyellow", ec="gray", alpha=0.8),
    )
    ax3.annotate(
        "Perpendicular = within-class\n(along hyperplane surface)\n"
        "→ intra-class variability",
        xy=(0.98, 0.02), xycoords="axes fraction",
        fontsize=8, ha="right", va="bottom",
        bbox=dict(boxstyle="round", fc="lightyellow", ec="gray", alpha=0.8),
    )

    ax3.set_xlabel(r"$\|\mathbf{d}_\parallel\|$ — Parallel to $\mathbf{w}^*$  (class-discriminative)",
                   fontsize=10)
    ax3.set_ylabel(r"$\|\mathbf{d}_\perp\|$ — Perpendicular to $\mathbf{w}^*$  (within-class)",
                   fontsize=10)
    ax3.set_title("(c) Vector Decomposition — Parallel vs Perpendicular", fontsize=12, fontweight="bold")
    ax3.legend(fontsize=9)
    ax3.grid(True, alpha=0.2)

    # ─────────────────────────────────────────────
    # (d) 3D view:  PC1 × PC2 × Fisher projection
    # ─────────────────────────────────────────────
    ax4 = fig.add_subplot(2, 2, 4, projection="3d")
    ax4.scatter(R2[mask_n, 0], R2[mask_n, 1], proj_scores[mask_n],
                c=C_NORMAL, alpha=0.3, s=10, label="Normal")
    ax4.scatter(R2[mask_a, 0], R2[mask_a, 1], proj_scores[mask_a],
                c=C_ANOMALY, alpha=0.5, s=20, label="Anomaly")

    # Draw threshold plane
    xx = np.linspace(R2[:, 0].min(), R2[:, 0].max(), 2)
    yy = np.linspace(R2[:, 1].min(), R2[:, 1].max(), 2)
    XX, YY = np.meshgrid(xx, yy)
    ZZ = np.full_like(XX, threshold)
    ax4.plot_surface(XX, YY, ZZ, alpha=0.15, color=C_HYPER, label="Threshold plane")

    # Drop projection lines from a few points down to the threshold plane
    for i in sample_idx[:8]:
        ax4.plot([R2[i, 0], R2[i, 0]], [R2[i, 1], R2[i, 1]],
                 [proj_scores[i], threshold],
                 color="gray", alpha=0.4, lw=0.5, ls=":")

    ax4.set_xlabel("PC-1", fontsize=9)
    ax4.set_ylabel("PC-2", fontsize=9)
    ax4.set_zlabel("Fisher score $s$", fontsize=9)
    ax4.set_title("(d) 3-D View — PC1 × PC2 × Fisher Score", fontsize=12, fontweight="bold")
    ax4.legend(fontsize=8, loc="upper left")
    ax4.view_init(elev=25, azim=-55)

    # ── Formula box at bottom ──
    formula_text = (
        "Fisher Linear Discriminant Projection\n"
        r"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" + "\n"
        r"1. Within-class scatter:   $S_W = \sum_{c \in \{0,1\}} \sum_{i \in c} "
        r"(\mathbf{r}_i - \boldsymbol{\mu}_c)(\mathbf{r}_i - \boldsymbol{\mu}_c)^T$" + "\n"
        r"2. Between-class scatter:  $S_B = \sum_{c} n_c "
        r"(\boldsymbol{\mu}_c - \boldsymbol{\mu})(\boldsymbol{\mu}_c - \boldsymbol{\mu})^T$" + "\n"
        r"3. Optimal direction:       $\mathbf{w}^* = \arg\max_{\mathbf{w}} "
        r"\frac{\mathbf{w}^T S_B \mathbf{w}}{\mathbf{w}^T S_W \mathbf{w}} "
        r"= S_W^{-1}(\boldsymbol{\mu}_1 - \boldsymbol{\mu}_0)$" + "\n"
        r"4. Projection score:        $s_i = (\mathbf{r}_i - \mathbf{c}) \cdot \mathbf{w}^*$" + "\n"
        r"5. Classification:            $\hat{y}_i = \mathbb{1}[s_i > \tau],\quad "
        r"\tau = \frac{\bar{s}_0 + \bar{s}_1}{2}$"
    )
    fig.text(0.5, 0.01, formula_text, fontsize=10, ha="center", va="bottom",
             family="monospace",
             bbox=dict(boxstyle="round,pad=0.6", fc="#f5f5f5", ec="#888", alpha=0.95))

    plt.tight_layout(rect=[0, 0.13, 1, 0.95])

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "fig_hyperplane_projection.png")
    fig.savefig(out_path, dpi=180, bbox_inches="tight", facecolor="white")
    print(f"✓ Saved: {out_path}")
    plt.close()


if __name__ == "__main__":
    main()
