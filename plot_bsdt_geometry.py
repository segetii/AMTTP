# -*- coding: utf-8 -*-
"""
plot_bsdt_geometry.py
=====================
10 diagnostic plots for the BSDT sphere → ellipsoid → gap → collapse geometry.

Plots
-----
 1  Raw BSDT shape         PCA/UMAP 3-D scatter by state
 2  Occupancy density      KDE surface Φ = −log p̂(x) on PC1-PC2 grid
 3  Ellipsoid shells       95% / 99% Mahalanobis ellipsoid + state cloud
 4  Energy shells          Points in thin E_BS bands [1,1.1], [2,2.1], [3,3.1]
 5  Curvature heatmap      κ_norm coloured scatter on PCA cloud
 6  Soft-direction compass  v_min(Hessian of Φ) arrows on 2-D PCA grid
 7  Betti barcode          β₀ and β₁ vs radius ε (Vietoris-Rips 1-skeleton)
 8  Morse skeleton         Critical points + gradient streamlines of Φ
 9  Spectral anisotropy    λ_max, λ_min, κ(H) through time
10  Master 2×2 figure      Cloud | Density | Curvature | Betti

Input:  UCI EEG Eye-State ARFF (same path as domain_real_eeg.py)
Output: bsdt_geometry/plot_XX_*.png  +  bsdt_geometry/master.png

Author: Copilot — June 2026
"""
from __future__ import annotations

import os
import sys
import warnings

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from mpl_toolkits.mplot3d import Axes3D          # noqa: F401
from scipy.stats import chi2 as _chi2
from scipy.spatial import cKDTree
from sklearn.decomposition import PCA

warnings.filterwarnings("ignore")
np.random.seed(20260602)

# ── Paths ───────────────────────────────────────────────────────────────────
ROOT   = r"C:\amttp"
NS     = os.path.join(ROOT, "research", "neural-stability")
DATA   = r"C:\amttp\data\external_validation\eeg\uci_eeg_eye_state.arff"
OUTDIR = os.path.join(ROOT, "bsdt_geometry")
os.makedirs(OUTDIR, exist_ok=True)

sys.path.insert(0, NS)
from canonical_v4_engine import FrozenCanonicalV4   # noqa: E402
import trading_stack_brakes as TSB                   # noqa: E402

# ── Palette ──────────────────────────────────────────────────────────────────
C_NORMAL   = "#2ca02c"    # green
C_PRECRISIS = "#ff7f0e"   # orange
C_CRISIS   = "#d62728"    # red
STATE_COL   = {0: C_NORMAL, 1: C_PRECRISIS, 2: C_CRISIS}
STATE_LBL   = {0: "Normal", 1: "Pre-crisis", 2: "Crisis"}
STATE_ALPHA = {0: 0.12, 1: 0.65, 2: 0.90}
STATE_SZ    = {0: 3, 1: 18, 2: 24}

EPS          = 1e-12
W_PRE        = 64         # pre-onset window width (same as benchmark)
G7_KAPPA_MAX = 10.0
REF_N        = 1500       # reference calibration samples (eye-open)
N_BETTI      = 500        # subsample size for Betti barcode
N_EPS        = 60         # number of ε values for barcode
W_SPEC       = 200        # rolling window for spectral anisotropy
CHANNELS = ["AF3","F7","F3","FC5","T7","P7","O1","O2","P8","T8","FC6","F4","F8","AF4"]

# ════════════════════════════════════════════════════════════════════════════
#  1. Data loading
# ════════════════════════════════════════════════════════════════════════════

def load_eeg() -> tuple[np.ndarray, np.ndarray]:
    rows = []
    with open(DATA, "r") as fh:
        in_data = False
        for line in fh:
            line = line.strip()
            if not line or line.startswith("%"):
                continue
            if line.upper().startswith("@DATA"):
                in_data = True; continue
            if in_data:
                vals = line.split(",")
                if len(vals) == 15:
                    rows.append(vals)
    arr = np.array(rows, dtype=float)
    X, y = arr[:, :14], arr[:, 14].astype(int)
    # Artefact rejection — same as domain_real_eeg.py
    med = np.median(X, axis=0)
    mad = np.median(np.abs(X - med), axis=0) + EPS
    keep = np.all(np.abs(X - med) < 8.0 * mad, axis=1)
    return X[keep], y[keep]


def make_state_labels(y: np.ndarray, w: int = W_PRE) -> np.ndarray:
    """0=Normal, 1=Pre-crisis, 2=Crisis"""
    state = np.where(y == 1, 2, 0).astype(int)
    onsets = np.where(np.diff(y) > 0)[0] + 1
    if y[0] == 1:
        onsets = np.concatenate([[0], onsets])
    for o in onsets:
        lo = max(0, o - w)
        state[lo:o] = np.where(state[lo:o] == 0, 1, state[lo:o])
    return state


# ════════════════════════════════════════════════════════════════════════════
#  2. Engine fit + observable computation
# ════════════════════════════════════════════════════════════════════════════

def fit_engine(X: np.ndarray, y: np.ndarray):
    ref_idx = np.where(y == 0)[0][:REF_N]
    X_ref   = X[ref_idx]
    engine  = FrozenCanonicalV4(alpha_base=0.05)
    engine.fit(X_ref)
    TSB.apply_g7_to_engine(engine, G7_KAPPA_MAX)
    return engine, X_ref


def compute_observables(engine: FrozenCanonicalV4, X: np.ndarray) -> dict:
    r       = engine.evaluate(X)
    Z       = (X - engine.mu_[None, :]) / engine.sigma_[None, :]
    kappa   = 2.0 * float(np.linalg.eigvalsh(engine.G_)[-1])
    GS      = Z @ engine.G_
    E       = np.einsum("ij,ij->i", Z, GS)
    gX      = 2.0 * GS
    gsq     = np.einsum("ij,ij->i", gX, gX)
    kn      = kappa * E / (gsq + EPS)
    # Normalized 4-channel BSDT delta vector
    dC = r.delta_C;  dG = r.delta_G;  dA = r.delta_A;  dT = r.delta_T
    # E_BS in normalized delta-space units
    sig_C = float(np.std(dC)) + EPS;  sig_G = float(np.std(dG)) + EPS
    sig_A = float(np.std(dA)) + EPS;  sig_T = float(np.std(dT)) + EPS
    E_BS  = (dC/sig_C)**2 + (dG/sig_G)**2 + (dA/sig_A)**2 + (dT/sig_T)**2
    return dict(
        Z=Z, E=E, kappa_norm=kn, E_BS=E_BS,
        delta_C=dC, delta_G=dG, delta_A=dA, delta_T=dT,
        cos_theta=r.cos_theta, rho_eff=-r.Edot/(np.abs(E)+EPS),
    )


# ════════════════════════════════════════════════════════════════════════════
#  3. Dimensionality reduction helpers
# ════════════════════════════════════════════════════════════════════════════

def fit_pca(Z: np.ndarray, n: int = 3) -> tuple[PCA, np.ndarray]:
    pca   = PCA(n_components=n, random_state=0)
    Z_pca = pca.fit_transform(Z)
    return pca, Z_pca


def try_umap(Z: np.ndarray, n: int = 3) -> np.ndarray | None:
    try:
        import umap as _umap
        reducer = _umap.UMAP(n_components=n, random_state=0, n_neighbors=30,
                              min_dist=0.1)
        return reducer.fit_transform(Z).astype(float)
    except Exception:
        return None


# ════════════════════════════════════════════════════════════════════════════
#  4. KDE helpers (2-D, on PC1-PC2 projection)
# ════════════════════════════════════════════════════════════════════════════

def build_kde_grid(Z2: np.ndarray, n_grid: int = 80):
    """Returns (grid_x, grid_y, Phi_grid, kde_grid, h) for PC1-PC2 slice."""
    from scipy.stats import gaussian_kde
    # Fit KDE on all 2-D data
    kde   = gaussian_kde(Z2.T, bw_method="scott")
    h     = float(np.sqrt(kde.covariance[0, 0]))
    # Evaluation grid
    pad   = 1.5 * float(Z2.std(axis=0).max())
    xlo, xhi = Z2[:, 0].min() - pad, Z2[:, 0].max() + pad
    ylo, yhi = Z2[:, 1].min() - pad, Z2[:, 1].max() + pad
    gx    = np.linspace(xlo, xhi, n_grid)
    gy    = np.linspace(ylo, yhi, n_grid)
    GX, GY = np.meshgrid(gx, gy)
    pts   = np.column_stack([GX.ravel(), GY.ravel()])
    p_raw = kde(pts.T).reshape(n_grid, n_grid)
    p_raw = np.maximum(p_raw, EPS)
    Phi   = -np.log(p_raw)
    return gx, gy, GX, GY, Phi, p_raw, h


def hessian_of_phi(Phi: np.ndarray, gx: np.ndarray, gy: np.ndarray):
    """Return 2×2 Hessian components of Φ = −log p̂ on the grid."""
    dx = gx[1] - gx[0];  dy = gy[1] - gy[0]
    dPhi_dx  = np.gradient(Phi, dx, axis=1)
    dPhi_dy  = np.gradient(Phi, dy, axis=0)
    d2Phi_xx = np.gradient(dPhi_dx, dx, axis=1)
    d2Phi_yy = np.gradient(dPhi_dy, dy, axis=0)
    d2Phi_xy = np.gradient(dPhi_dx, dy, axis=0)
    return dPhi_dx, dPhi_dy, d2Phi_xx, d2Phi_yy, d2Phi_xy


# ════════════════════════════════════════════════════════════════════════════
#  5. Betti barcode helper (Vietoris-Rips 1-skeleton)
# ════════════════════════════════════════════════════════════════════════════

def vr_betti(pts: np.ndarray, eps_vals: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Compute β₀ and β₁ = #edges − #vertices + β₀ for each ε."""
    n  = len(pts)
    # Pairwise distances
    D  = np.sqrt(((pts[:, None] - pts[None, :])**2).sum(-1))
    # Sort edges once
    ri, ci = np.triu_indices(n, k=1)
    edge_d = D[ri, ci]
    order  = np.argsort(edge_d)
    ri_s   = ri[order];  ci_s = ci[order];  ed_s = edge_d[order]

    b0_arr = np.empty(len(eps_vals), int)
    b1_arr = np.empty(len(eps_vals), int)

    parent = np.arange(n, dtype=int)

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    ptr = 0;  n_edges = 0;  b0 = n
    for ei, eps in enumerate(eps_vals):
        while ptr < len(ed_s) and ed_s[ptr] <= eps:
            ra = find(ri_s[ptr]);  rb = find(ci_s[ptr])
            if ra != rb:
                parent[rb] = ra;  b0 -= 1
            n_edges += 1
            ptr += 1
        b0_arr[ei] = b0
        b1_arr[ei] = max(0, n_edges - (n - b0))  # β₁ = E − V + β₀
    return b0_arr, b1_arr


# ════════════════════════════════════════════════════════════════════════════
#  Helpers
# ════════════════════════════════════════════════════════════════════════════

def scatter_by_state(ax, coords, state, alpha_override=None, size_override=None,
                     dims=(0, 1, 2), is_3d=False):
    for s in (0, 1, 2):
        mask = state == s
        if not mask.any():
            continue
        pts  = coords[mask]
        kw   = dict(c=STATE_COL[s], label=STATE_LBL[s],
                    alpha=alpha_override or STATE_ALPHA[s],
                    s=size_override or STATE_SZ[s],
                    linewidths=0)
        if is_3d:
            ax.scatter(pts[:, dims[0]], pts[:, dims[1]], pts[:, dims[2]], **kw)
        else:
            ax.scatter(pts[:, dims[0]], pts[:, dims[1]], **kw)


def savefig(fig, name: str, tight: bool = True) -> str:
    if tight:
        fig.tight_layout()
    path = os.path.join(OUTDIR, name)
    fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    print(f"  → saved {path}")
    return path


# ════════════════════════════════════════════════════════════════════════════
#  PLOT 1 — Raw BSDT shape (PCA or UMAP 3-D scatter)
# ════════════════════════════════════════════════════════════════════════════

def plot_01_shape(Z: np.ndarray, state: np.ndarray,
                  pca_3: np.ndarray, expl: np.ndarray):
    # Try UMAP; fall back to PCA
    Z_sub  = Z[::5]  # subsample for UMAP speed
    s_sub  = state[::5]
    U3     = try_umap(Z_sub, 3)
    use_umap = (U3 is not None)

    fig = plt.figure(figsize=(14, 6))
    fig.suptitle("Plot 1 — Raw BSDT State Cloud", fontsize=13, fontweight="bold")

    for col, (coords, s_arr, title, xl, yl, zl) in enumerate([
        (pca_3[::5], state[::5],
         f"PCA 3-D  (PC1={expl[0]:.1%} | PC2={expl[1]:.1%} | PC3={expl[2]:.1%})",
         "PC 1", "PC 2", "PC 3"),
        (U3 if use_umap else pca_3[::5], s_sub if use_umap else state[::5],
         "UMAP 3-D" if use_umap else "PCA 3-D (UMAP unavailable)",
         "U1" if use_umap else "PC 1",
         "U2" if use_umap else "PC 2",
         "U3" if use_umap else "PC 3"),
    ]):
        ax = fig.add_subplot(1, 2, col + 1, projection="3d")
        scatter_by_state(ax, coords, s_arr, is_3d=True)
        ax.set_xlabel(xl, fontsize=8); ax.set_ylabel(yl, fontsize=8)
        ax.set_zlabel(zl, fontsize=8)
        ax.set_title(title, fontsize=9)
        ax.legend(fontsize=7, loc="upper left", markerscale=2)
        ax.tick_params(labelsize=6)

    return savefig(fig, "plot_01_shape.png")


# ════════════════════════════════════════════════════════════════════════════
#  PLOT 2 — Occupancy density surface  Φ = −log p̂(x)
# ════════════════════════════════════════════════════════════════════════════

def plot_02_density(Z2: np.ndarray, state: np.ndarray,
                    gx, gy, GX, GY, Phi):
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle("Plot 2 — Occupancy Density  Φ = −log p̂(x)  [PC1-PC2]",
                 fontsize=13, fontweight="bold")

    for ax, cmap, title in zip(axes, ["inferno", "viridis"],
                               ["Density landscape (warm=barrier)",
                                "Contours + state cloud"]):
        im = ax.contourf(GX, GY, Phi, levels=20, cmap=cmap, alpha=0.85)
        plt.colorbar(im, ax=ax, label="Φ = −log p̂")
        ax.contour(GX, GY, Phi, levels=10, colors="white", linewidths=0.4,
                   alpha=0.5)
        if "cloud" in title:
            scatter_by_state(ax, Z2, state, alpha_override=0.25, dims=(0, 1))
            ax.legend(fontsize=7, loc="upper right", markerscale=2)
        ax.set_xlabel("PC 1"); ax.set_ylabel("PC 2")
        ax.set_title(title, fontsize=9)

    return savefig(fig, "plot_02_density.png")


# ════════════════════════════════════════════════════════════════════════════
#  PLOT 3 — Ellipsoid reconstruction  (x−μ)ᵀ Σ⁻¹ (x−μ) = c
# ════════════════════════════════════════════════════════════════════════════

def _ellipsoid_surface(semi_axes, n: int = 30):
    """Parameterise unit sphere, scale by semi_axes (3,)."""
    phi   = np.linspace(0, np.pi, n)
    theta = np.linspace(0, 2 * np.pi, n)
    P, T  = np.meshgrid(phi, theta)
    x     = semi_axes[0] * np.sin(P) * np.cos(T)
    y     = semi_axes[1] * np.sin(P) * np.sin(T)
    z     = semi_axes[2] * np.cos(P)
    return x, y, z


def plot_03_ellipsoid(pca_3: np.ndarray, state: np.ndarray,
                      pca: PCA):
    """Mahalanobis ellipsoid fitted on normal data, shown in PCA 3-D."""
    # Normal-state covariance in PCA space (variance = eigenvalues of PCA)
    normal_mask = state == 0
    Z3_normal   = pca_3[normal_mask]
    var_pc      = Z3_normal.var(axis=0) + EPS     # variance along each PC

    # χ² threshold for d=3 degrees of freedom
    c95 = _chi2.ppf(0.95, df=3)
    c99 = _chi2.ppf(0.99, df=3)

    fig = plt.figure(figsize=(14, 6))
    fig.suptitle("Plot 3 — Ellipsoid Reconstruction  (x−μ)ᵀ Σ⁻¹ (x−μ) = c",
                 fontsize=13, fontweight="bold")

    for col, elev in enumerate([25, 10]):
        ax = fig.add_subplot(1, 2, col + 1, projection="3d")

        # Data cloud
        scatter_by_state(ax, pca_3[::5], state[::5], is_3d=True)

        # 95% ellipsoid
        sa95 = np.sqrt(var_pc * c95)
        ex, ey, ez = _ellipsoid_surface(sa95, n=40)
        ax.plot_wireframe(ex, ey, ez, color=C_PRECRISIS, alpha=0.20,
                          linewidth=0.5, rstride=2, cstride=2)
        ax.plot_surface(ex, ey, ez, color=C_PRECRISIS, alpha=0.05)

        # 99% ellipsoid
        sa99 = np.sqrt(var_pc * c99)
        ex9, ey9, ez9 = _ellipsoid_surface(sa99, n=40)
        ax.plot_wireframe(ex9, ey9, ez9, color=C_CRISIS, alpha=0.25,
                          linewidth=0.5, rstride=2, cstride=2)

        ax.set_xlabel("PC 1", fontsize=8); ax.set_ylabel("PC 2", fontsize=8)
        ax.set_zlabel("PC 3", fontsize=8)
        ax.set_title(f"{'Front' if col == 0 else 'Side'} view\n"
                     f"orange=95%  red=99% Mahalanobis", fontsize=8)
        ax.view_init(elev=elev, azim=30 + col * 60)
        ax.tick_params(labelsize=6)
        ax.legend(fontsize=7, loc="upper left", markerscale=2)

    return savefig(fig, "plot_03_ellipsoid.png")


# ════════════════════════════════════════════════════════════════════════════
#  PLOT 4 — Energy shells
# ════════════════════════════════════════════════════════════════════════════

def plot_04_shells(pca_3: np.ndarray, E_BS: np.ndarray, state: np.ndarray):
    SHELLS = [(1.0, 1.1, "#1f77b4"), (2.0, 2.1, "#ff7f0e"), (3.0, 3.1, "#d62728")]

    fig = plt.figure(figsize=(16, 5))
    fig.suptitle("Plot 4 — Energy Shells  E_BS ∈ [lo, hi]", fontsize=13,
                 fontweight="bold")

    for col, (lo, hi, col_c) in enumerate(SHELLS):
        ax    = fig.add_subplot(1, 3, col + 1, projection="3d")
        mask  = (E_BS >= lo) & (E_BS < hi)
        pts   = pca_3[mask];  s_m = state[mask]

        # Background cloud (transparent)
        ax.scatter(pca_3[::10, 0], pca_3[::10, 1], pca_3[::10, 2],
                   c="#aaaaaa", alpha=0.04, s=2, linewidths=0)

        # Shell points coloured by state
        if mask.any():
            scatter_by_state(ax, pts, s_m, alpha_override=0.7, size_override=8,
                             is_3d=True)
        ax.set_xlabel("PC 1", fontsize=7); ax.set_ylabel("PC 2", fontsize=7)
        ax.set_zlabel("PC 3", fontsize=7)
        ax.set_title(f"E_BS ∈ [{lo}, {hi}]  (n={mask.sum()})", fontsize=9)
        ax.tick_params(labelsize=6)
        ax.legend(fontsize=6, markerscale=2)

    return savefig(fig, "plot_04_shells.png")


# ════════════════════════════════════════════════════════════════════════════
#  PLOT 5 — Curvature heatmap  κ_norm
# ════════════════════════════════════════════════════════════════════════════

def plot_05_curvature(pca_3: np.ndarray, kappa_norm: np.ndarray, state: np.ndarray):
    # Clip for visual clarity
    kn   = np.clip(kappa_norm, np.percentile(kappa_norm, 1),
                               np.percentile(kappa_norm, 99))
    norm = mcolors.TwoSlopeNorm(vmin=kn.min(), vcenter=float(np.median(kn)),
                                 vmax=kn.max())

    fig = plt.figure(figsize=(14, 6))
    fig.suptitle("Plot 5 — Curvature Heatmap  κ_norm = κ·E / ‖g_X‖²",
                 fontsize=13, fontweight="bold")

    for col, step in enumerate([5, 1]):
        ax  = fig.add_subplot(1, 2, col + 1, projection="3d")
        idx = np.arange(0, len(pca_3), step)
        sc  = ax.scatter(pca_3[idx, 0], pca_3[idx, 1], pca_3[idx, 2],
                         c=kn[idx], cmap="seismic", norm=norm,
                         s=3 if step > 1 else 8,
                         alpha=0.5 if step > 1 else 0.7, linewidths=0)
        plt.colorbar(sc, ax=ax, label="κ_norm", shrink=0.7)
        # Mark crisis points
        cm = state == 2
        if cm.any():
            ax.scatter(pca_3[cm, 0], pca_3[cm, 1], pca_3[cm, 2],
                       c="black", s=30, marker="x", alpha=0.9,
                       linewidths=1.2, label="Crisis")
        ax.set_xlabel("PC 1", fontsize=8); ax.set_ylabel("PC 2", fontsize=8)
        ax.set_zlabel("PC 3", fontsize=8)
        ax.set_title(
            f"{'All points' if step > 1 else 'Crisis zoom (step=1)'}"
            f" (step={step})\nBlue=low κ   Red=high κ", fontsize=8)
        ax.tick_params(labelsize=6)
        if cm.any():
            ax.legend(fontsize=7)

    return savefig(fig, "plot_05_curvature.png")


# ════════════════════════════════════════════════════════════════════════════
#  PLOT 6 — Soft-direction compass  v_min(H) arrows
# ════════════════════════════════════════════════════════════════════════════

def plot_06_compass(Z2: np.ndarray, state: np.ndarray,
                    gx, gy, GX, GY, Phi):
    _, _, d2xx, d2yy, d2xy = hessian_of_phi(Phi, gx, gy)

    # Compute min-eigenvector at each grid point
    # H = [[d2xx, d2xy], [d2xy, d2yy]]  (scalar field per grid cell)
    # Eigenvalues: λ = ((a+d) ± sqrt((a-d)²+4b²)) / 2  where a,b,c=d2xy,d=d2yy
    a   = d2xx;  b = d2xy;  d = d2yy
    disc = np.sqrt(np.maximum((a - d)**2 + 4 * b**2, 0.0))
    lam1 = 0.5 * (a + d - disc)   # smaller eigenvalue
    vx   = -b;   vy = a - lam1    # eigenvector for λ1
    mag  = np.sqrt(vx**2 + vy**2) + EPS
    vx  /= mag;  vy /= mag

    # Subsample for quiver arrows
    stride = max(len(gx) // 12, 1)
    sl     = slice(None, None, stride)

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle("Plot 6 — Soft-Direction Compass  v_min(H) = Escape Eigenvector",
                 fontsize=13, fontweight="bold")

    for ax in axes:
        im = ax.contourf(GX, GY, Phi, levels=20, cmap="Blues_r", alpha=0.7)
        plt.colorbar(im, ax=ax, label="Φ = −log p̂")
        # Arrows (both ± directions to show axis, not orientation)
        ax.quiver(GX[sl, sl], GY[sl, sl],
                  vx[sl, sl], vy[sl, sl],
                  angles="xy", scale=12, width=0.003,
                  color="#e377c2", alpha=0.85, headwidth=0,
                  label="v_min direction")
        ax.set_xlabel("PC 1"); ax.set_ylabel("PC 2")

    # Right panel: overlay data
    scatter_by_state(axes[1], Z2, state, alpha_override=0.25, dims=(0, 1))
    axes[0].set_title("Escape field only", fontsize=9)
    axes[1].set_title("Escape field + state cloud", fontsize=9)
    axes[1].legend(fontsize=7, loc="upper right", markerscale=2)

    return savefig(fig, "plot_06_compass.png")


# ════════════════════════════════════════════════════════════════════════════
#  PLOT 7 — Betti barcode  β₀, β₁  vs  ε
# ════════════════════════════════════════════════════════════════════════════

def plot_07_betti(Z: np.ndarray, state: np.ndarray):
    """Compute VR barcode on subsamples of each state class."""
    rng = np.random.default_rng(42)

    fig, axes = plt.subplots(2, 3, figsize=(16, 8), sharex=True)
    fig.suptitle("Plot 7 — Vietoris-Rips Betti Barcode  β₀, β₁  vs  ε",
                 fontsize=13, fontweight="bold")

    # Work in 4-D normalised delta space
    for si, (s_lbl, s_col, axes_row) in enumerate([
        (STATE_LBL[0], C_NORMAL,    axes[:, 0]),
        (STATE_LBL[1], C_PRECRISIS, axes[:, 1]),
        (STATE_LBL[2], C_CRISIS,    axes[:, 2]),
    ]):
        s_mask = state == si
        n_pts  = min(N_BETTI, s_mask.sum())
        if n_pts < 5:
            for ax in axes_row:
                ax.text(0.5, 0.5, f"{s_lbl}\n(n<5)", ha="center",
                        transform=ax.transAxes)
            continue

        idx   = rng.choice(np.where(s_mask)[0], n_pts, replace=False)
        pts   = Z[idx]
        # Normalise rows to unit sphere for scale-invariant barcode
        pts   = pts / (np.std(pts, axis=0) + EPS)

        d_max = float(np.percentile(
            np.sqrt(((pts[:, None] - pts[None, :])**2).sum(-1)), 40))
        eps_v = np.linspace(0, d_max, N_EPS)

        b0, b1 = vr_betti(pts, eps_v)

        for ax, bk, blbl in zip(axes_row, [b0, b1], ["β₀ (components)", "β₁ (loops)"]):
            ax.plot(eps_v, bk, color=s_col, linewidth=1.8)
            ax.fill_between(eps_v, 0, bk, color=s_col, alpha=0.18)
            ax.set_ylabel(blbl, fontsize=8)
            if blbl.startswith("β₀"):
                ax.set_title(f"{s_lbl}  (n={n_pts})", fontsize=9,
                              color=s_col, fontweight="bold")
            ax.grid(True, alpha=0.3, linewidth=0.5)
            ax.tick_params(labelsize=7)

    for ax in axes[1]:
        ax.set_xlabel("ε (radius)", fontsize=8)

    fig.text(0.5, 0.01,
             "β₀: # connected components   β₁: # independent loops   (VR 1-skeleton)",
             ha="center", fontsize=8)

    return savefig(fig, "plot_07_betti.png")


# ════════════════════════════════════════════════════════════════════════════
#  PLOT 8 — Morse skeleton  (gradient streamlines of Φ + critical points)
# ════════════════════════════════════════════════════════════════════════════

def plot_08_morse(Z2: np.ndarray, state: np.ndarray,
                  gx, gy, GX, GY, Phi):
    dx = gx[1] - gx[0];  dy = gy[1] - gy[0]
    dPhi_x = np.gradient(Phi, dx, axis=1)   # U component
    dPhi_y = np.gradient(Phi, dy, axis=0)   # V component
    grad_mag = np.sqrt(dPhi_x**2 + dPhi_y**2)

    # Detect approximate critical points: cells where |∇Φ| is locally minimal
    from scipy.ndimage import minimum_filter, label as _label
    min_filt = minimum_filter(grad_mag, size=5)
    is_crit  = (grad_mag == min_filt) & (grad_mag < np.percentile(grad_mag, 5))
    crit_ij  = np.column_stack(np.where(is_crit))

    # Classify by Hessian eigenvalue signs
    _, _, d2xx, d2yy, d2xy = hessian_of_phi(Phi, gx, gy)
    a = d2xx;  b = d2xy;  d = d2yy
    disc  = np.sqrt(np.maximum((a - d)**2 + 4 * b**2, 0.0))
    lam_p = 0.5 * (a + d + disc)
    lam_m = 0.5 * (a + d - disc)
    cat   = np.where((lam_p > 0) & (lam_m > 0), 1,
             np.where((lam_p < 0) & (lam_m < 0), -1, 0))   # 1=min, -1=max, 0=saddle

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle("Plot 8 — Morse Skeleton: Critical Points + Gradient Flow of Φ",
                 fontsize=13, fontweight="bold")

    for ax in axes:
        im = ax.contourf(GX, GY, Phi, levels=25, cmap="terrain", alpha=0.75)
        ax.contour(GX, GY, Phi, levels=12, colors="black", linewidths=0.3,
                   alpha=0.4)
        plt.colorbar(im, ax=ax, label="Φ", shrink=0.85)

        # Gradient streamlines (flow toward −∇Φ = uphill in density)
        speed = grad_mag + EPS
        ax.streamplot(gx, gy, -dPhi_x / speed, -dPhi_y / speed,
                      color="#666666", linewidth=0.6, density=1.2,
                      arrowsize=0.8, arrowstyle="->")

        # Critical points
        for (ci, cj) in crit_ij[:200]:
            px, py = gx[cj], gy[ci]
            kind   = int(cat[ci, cj])
            if kind == 1:
                ax.plot(px, py, "^", color=C_NORMAL,    ms=6, alpha=0.9)  # minimum
            elif kind == -1:
                ax.plot(px, py, "v", color=C_CRISIS,    ms=6, alpha=0.9)  # maximum
            else:
                ax.plot(px, py, "s", color=C_PRECRISIS, ms=5, alpha=0.8)  # saddle

        ax.set_xlabel("PC 1"); ax.set_ylabel("PC 2")

    scatter_by_state(axes[1], Z2, state, alpha_override=0.25, dims=(0, 1))
    axes[0].set_title("Gradient flow + critical points\n"
                      "▲=minimum  ◼=saddle  ▼=maximum", fontsize=8)
    axes[1].set_title("+ state cloud", fontsize=9)
    axes[1].legend(fontsize=7, loc="upper right", markerscale=2)

    return savefig(fig, "plot_08_morse.png")


# ════════════════════════════════════════════════════════════════════════════
#  PLOT 9 — Spectral anisotropy  λ_max(t), λ_min(t), κ(H)(t)
# ════════════════════════════════════════════════════════════════════════════

def plot_09_anisotropy(Z: np.ndarray, state: np.ndarray):
    T, d    = Z.shape
    w       = W_SPEC
    n_eff   = T - w
    t_idx   = np.arange(w, T)
    lam_max = np.full(T, np.nan)
    lam_min = np.full(T, np.nan)

    print(f"  [plot9] Computing rolling covariance  T={T} w={w} ...", end="", flush=True)
    for t in range(w, T):
        cov          = np.cov(Z[t - w:t].T)
        eigs         = np.sort(np.linalg.eigvalsh(cov))
        lam_min[t]   = float(eigs[0])
        lam_max[t]   = float(eigs[-1])
    print(" done")

    kappa_h = lam_max / (lam_min + EPS)
    crisis  = state == 2

    # Downsample for display
    step = max(1, T // 2000)
    tt   = np.arange(T)[::step]

    fig, axes = plt.subplots(3, 1, figsize=(14, 9), sharex=True)
    fig.suptitle("Plot 9 — Spectral Anisotropy of State Manifold",
                 fontsize=13, fontweight="bold")

    labels = [("λ_max  (max eigenvalue of local cov)", lam_max, "#1f77b4"),
              ("λ_min  (min eigenvalue of local cov)", lam_min, "#2ca02c"),
              ("κ(H) = λ_max / λ_min  (condition number)", kappa_h, "#9467bd")]

    for ax, (lbl, sig, col) in zip(axes, labels):
        ax.plot(tt, sig[tt], color=col, linewidth=0.7, alpha=0.85)
        # Shade crisis regions
        cr_mask = crisis[tt]
        ax.fill_between(tt, ax.get_ylim()[0] if ax.get_ylim()[0] != 0 else
                        float(np.nanmin(sig) * 0.95),
                        np.where(cr_mask, np.nanmax(sig[tt]), np.nan),
                        color=C_CRISIS, alpha=0.12, label="Crisis")
        ax.set_ylabel(lbl, fontsize=8)
        ax.grid(True, alpha=0.3, linewidth=0.5)
        ax.tick_params(labelsize=7)

    # Shade pre-crisis
    pre_mask = state == 1
    for ax in axes:
        y0 = float(np.nanmin(ax.get_lines()[0].get_ydata()))
        y1 = float(np.nanmax(ax.get_lines()[0].get_ydata()))
        ax.fill_between(tt,
                        np.where(pre_mask[tt], y0, np.nan),
                        np.where(pre_mask[tt], y1, np.nan),
                        color=C_PRECRISIS, alpha=0.10, label="Pre-crisis")

    axes[0].legend(fontsize=7)
    axes[-1].set_xlabel("Sample index", fontsize=9)

    return savefig(fig, "plot_09_anisotropy.png")


# ════════════════════════════════════════════════════════════════════════════
#  PLOT 10 — Master 2×2 figure
# ════════════════════════════════════════════════════════════════════════════

def plot_10_master(Z2: np.ndarray, state: np.ndarray,
                   gx, gy, GX, GY, Phi,
                   kappa_norm: np.ndarray, pca_3: np.ndarray,
                   Z: np.ndarray):
    import matplotlib.gridspec as gridspec

    fig = plt.figure(figsize=(16, 14))
    fig.suptitle(
        "Master Figure — BSDT Geometry\n"
        "Occupancy  →  Density  →  Curvature  →  Topology  →  Energy",
        fontsize=14, fontweight="bold", y=0.99)

    gs = gridspec.GridSpec(2, 2, figure=fig, hspace=0.35, wspace=0.30)

    # ── Panel A: Occupancy cloud (PCA 3-D projected to 2-D for master) ──────
    ax_a = fig.add_subplot(gs[0, 0])
    ax_a.set_title("A — Occupancy Cloud (PC1 vs PC2)", fontsize=11, fontweight="bold")
    scatter_by_state(ax_a, Z2, state, alpha_override=0.18, dims=(0, 1))
    ax_a.set_xlabel("PC 1", fontsize=9); ax_a.set_ylabel("PC 2", fontsize=9)
    ax_a.legend(fontsize=8, loc="upper right", markerscale=2)

    # ── Panel B: Density surface Φ ───────────────────────────────────────
    ax_b = fig.add_subplot(gs[0, 1])
    ax_b.set_title("B — Density Surface  Φ = −log p̂(x)", fontsize=11, fontweight="bold")
    im_b = ax_b.contourf(GX, GY, Phi, levels=20, cmap="inferno", alpha=0.85)
    ax_b.contour(GX, GY, Phi, levels=10, colors="white", linewidths=0.4, alpha=0.5)
    scatter_by_state(ax_b, Z2, state, alpha_override=0.25, dims=(0, 1))
    fig.colorbar(im_b, ax=ax_b, label="Φ", shrink=0.8)
    ax_b.set_xlabel("PC 1", fontsize=9); ax_b.set_ylabel("PC 2", fontsize=9)

    # ── Panel C: Curvature heatmap (2-D) ────────────────────────────────
    ax_c = fig.add_subplot(gs[1, 0])
    ax_c.set_title("C — Curvature Heatmap  κ_norm", fontsize=11, fontweight="bold")
    kn   = np.clip(kappa_norm, np.percentile(kappa_norm, 2),
                               np.percentile(kappa_norm, 98))
    vctr = float(np.median(kn))
    norm = mcolors.TwoSlopeNorm(vmin=kn.min(), vcenter=vctr, vmax=kn.max())
    sc_c = ax_c.scatter(Z2[::3, 0], Z2[::3, 1],
                        c=kn[::3], cmap="seismic", norm=norm,
                        s=2, alpha=0.5, linewidths=0)
    fig.colorbar(sc_c, ax=ax_c, label="κ_norm", shrink=0.8)
    cm = state == 2
    if cm.any():
        ax_c.scatter(Z2[cm, 0], Z2[cm, 1], c="black", s=24, marker="x",
                     linewidths=1.2, label="Crisis", alpha=0.9, zorder=5)
        ax_c.legend(fontsize=8)
    ax_c.set_xlabel("PC 1", fontsize=9); ax_c.set_ylabel("PC 2", fontsize=9)

    # ── Panel D: Betti barcode (combined β₀ by state) ──────────────────
    ax_d = fig.add_subplot(gs[1, 1])
    ax_d.set_title("D — Betti β₀ (connected components) by state", fontsize=11,
                   fontweight="bold")

    rng = np.random.default_rng(42)
    Z_norm = Z / (np.std(Z, axis=0) + EPS)
    d_all  = []
    for si, s_col in [(0, C_NORMAL), (1, C_PRECRISIS), (2, C_CRISIS)]:
        s_mask = state == si
        n_pts  = min(N_BETTI, s_mask.sum())
        if n_pts < 5:
            continue
        idx   = rng.choice(np.where(s_mask)[0], n_pts, replace=False)
        pts   = Z_norm[idx]
        d_max = float(np.percentile(
            np.sqrt(((pts[:, None] - pts[None, :])**2).sum(-1)), 40))
        d_all.append(d_max)

    if d_all:
        d_max_all = max(d_all)
        eps_v     = np.linspace(0, d_max_all, N_EPS)
        for si, (s_col, s_lbl) in enumerate(
                [(C_NORMAL, STATE_LBL[0]),
                 (C_PRECRISIS, STATE_LBL[1]),
                 (C_CRISIS, STATE_LBL[2])]):
            s_mask = state == si
            n_pts  = min(N_BETTI, s_mask.sum())
            if n_pts < 5:
                continue
            idx   = rng.choice(np.where(s_mask)[0], n_pts, replace=False)
            pts   = Z_norm[idx]
            b0, _ = vr_betti(pts, eps_v)
            ax_d.plot(eps_v, b0, color=s_col, linewidth=2.0,
                      label=f"{s_lbl} (n={n_pts})")
            ax_d.fill_between(eps_v, 0, b0, color=s_col, alpha=0.12)

    ax_d.set_xlabel("ε (radius)", fontsize=9)
    ax_d.set_ylabel("β₀ (components)", fontsize=9)
    ax_d.legend(fontsize=8)
    ax_d.grid(True, alpha=0.3, linewidth=0.5)

    return savefig(fig, "master.png", tight=False)


# ════════════════════════════════════════════════════════════════════════════
#  Main
# ════════════════════════════════════════════════════════════════════════════

def main():
    import time
    t0 = time.time()
    print("=" * 80)
    print("BSDT Geometry — 10 diagnostic plots")
    print("=" * 80)

    # ── Load data ─────────────────────────────────────────────────────────
    print("\n[1/5] Loading EEG data ...")
    X, y      = load_eeg()
    state     = make_state_labels(y)
    T, d      = X.shape
    n_states  = [int((state == s).sum()) for s in range(3)]
    print(f"  T={T}  d={d}  Normal={n_states[0]}  Pre-crisis={n_states[1]}  Crisis={n_states[2]}")

    # ── Fit engine ────────────────────────────────────────────────────────
    print("[2/5] Fitting engine ...")
    engine, X_ref = fit_engine(X, y)
    obs           = compute_observables(engine, X)
    print(f"  E range [{obs['E'].min():.1f}, {obs['E'].max():.1f}]  "
          f"κ_norm range [{obs['kappa_norm'].min():.3f}, {obs['kappa_norm'].max():.3f}]")

    # ── PCA ───────────────────────────────────────────────────────────────
    print("[3/5] PCA ...")
    pca3, Z3 = fit_pca(obs["Z"], n=3)
    _, Z2    = fit_pca(obs["Z"], n=2)
    Z2       = Z3[:, :2]     # consistent: use same PCA object for 2-D
    expl     = pca3.explained_variance_ratio_
    print(f"  PC1={expl[0]:.1%}  PC2={expl[1]:.1%}  PC3={expl[2]:.1%}  "
          f"total={expl.sum():.1%}")

    # ── KDE on PC1-PC2 ────────────────────────────────────────────────────
    print("[4/5] KDE on PC1-PC2 ...")
    gx, gy, GX, GY, Phi, p_raw, h_bw = build_kde_grid(Z2, n_grid=80)
    print(f"  KDE bandwidth h={h_bw:.4f}")

    # ── Generate all plots ────────────────────────────────────────────────
    print("[5/5] Rendering plots ...")

    print("  Plot 1 — Raw shape ...")
    plot_01_shape(obs["Z"], state, Z3, expl)

    print("  Plot 2 — Density surface ...")
    plot_02_density(Z2, state, gx, gy, GX, GY, Phi)

    print("  Plot 3 — Ellipsoid ...")
    plot_03_ellipsoid(Z3, state, pca3)

    print("  Plot 4 — Energy shells ...")
    plot_04_shells(Z3, obs["E_BS"], state)

    print("  Plot 5 — Curvature heatmap ...")
    plot_05_curvature(Z3, obs["kappa_norm"], state)

    print("  Plot 6 — Soft-direction compass ...")
    plot_06_compass(Z2, state, gx, gy, GX, GY, Phi)

    print("  Plot 7 — Betti barcode ...")
    plot_07_betti(obs["Z"], state)

    print("  Plot 8 — Morse skeleton ...")
    plot_08_morse(Z2, state, gx, gy, GX, GY, Phi)

    print("  Plot 9 — Spectral anisotropy ...")
    plot_09_anisotropy(obs["Z"], state)

    print("  Plot 10 — Master 2×2 figure ...")
    plot_10_master(Z2, state, gx, gy, GX, GY, Phi,
                   obs["kappa_norm"], Z3, obs["Z"])

    print(f"\nDone. All plots saved to {OUTDIR}")
    print(f"Elapsed: {time.time() - t0:.1f}s")
    print("=" * 80)


if __name__ == "__main__":
    main()
