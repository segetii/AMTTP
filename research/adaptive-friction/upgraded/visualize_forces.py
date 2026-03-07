"""
visualize_forces.py
===================
Interactive force-field, attraction/repulsion, Navier-Stokes analogy,
and adaptive-friction dashboard for the GravityEngine model.

Produces a multi-panel figure showing:
  Panel 1  – Particle positions + pairwise force arrows (attraction blue, repulsion red)
  Panel 2  – Quiver force field around the equilibrium with institution positions overlaid
  Panel 3  – Enstrophy / vorticity / strain decomposition (Navier-Stokes analogy)
  Panel 4  – Adaptive friction coefficient γ*(t) + energy E(t) with crisis shading
  Panel 5  – Gradient alignment cos θ(t) with Minsky regime bands
  Panel 6  – Spectral radius λ_max(t) vs critical manifold threshold

Outputs:
  results/force_field_dashboard.png   (300 dpi)
  results/force_field_dashboard.pdf
  results/pairwise_forces_detail.png  (single-snapshot detail view)
  results/navier_stokes_analogy.png   (NS decomposition detail)

Usage:
  python visualize_forces.py [--snapshot 74]  # quarter index for snapshot panels
"""

from __future__ import annotations
import sys, argparse, json
import numpy as np
import pandas as pd
from pathlib import Path
from scipy.special import erf as _erf

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import Normalize
from matplotlib.cm import ScalarMappable
import matplotlib.gridspec as gridspec

sys.path.insert(0, str(Path(__file__).parent))

import gravity_engine as _ge
from gravity_engine import (
    radial_force, pairwise_force, total_force, total_energy,
    BSDTOperator, analyse_trajectory,
    spectral_radius as ge_spectral_radius,
)
ALPHA = _ge.ALPHA
GAMMA = _ge.GAMMA
SIGMA = _ge.SIGMA
LAMBDA_REP = _ge.LAMBDA_REP
EPS = _ge.EPS
from fred_loader import fetch_all
from fdic_loader import fetch_fdic_specgrp
from state_matrix import build_state_matrix_fdic, standardise_panel, get_normal_period
from crisis_analysis import CRISIS_WINDOWS

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# Sector short labels
SECTOR_SHORT = [
    "Mutual\nSavings", "Stock\nSavings", "State\nComm.",
    "National\nComm.", "Federal\nSav.", "State\nSav.", "Foreign\nBranch"
]
SECTOR_COLORS = plt.cm.Set2(np.linspace(0, 1, 7))

CRISIS_SHADING = {
    "Dot-com\n2001":     ("2000-03-01", "2003-06-30", "#FFD70044"),
    "GFC\n2007-09":      ("2007-06-01", "2009-06-30", "#FF634744"),
    "COVID\n2020":       ("2020-01-01", "2020-09-30", "#9370DB44"),
    "Rate Shock\n2022":  ("2022-03-01", "2023-03-31", "#FF8C0044"),
}


# ─────────────────────────────────────────────
# Data loading (reuses pipeline data path)
# ─────────────────────────────────────────────

def load_data(use_cache=True, verbose=False):
    """Load FDIC/FRED data, build state matrix, standardise, fit BSDT."""
    raw_fred = fetch_all(use_cache=use_cache, verbose=verbose)
    slope_col = "slope_10y2y" if "slope_10y2y" in raw_fred.columns else raw_fred.columns[0]
    fred_slope = raw_fred[slope_col].copy()

    try:
        fdic_df = fetch_fdic_specgrp(start="1990-01-01", end="2024-12-31",
                                     use_cache=use_cache, verbose=verbose)
        X_all, dates, sectors = build_state_matrix_fdic(fdic_df, fred_slope)
        src = "FDIC SDI"
    except Exception:
        # Synthetic fallback (matches run_pipeline.py)
        from run_pipeline import _synthetic_fred_fallback
        from state_matrix import standardise_panel as _sp
        print("  [warn] FDIC unavailable, using synthetic fallback")
        raw_fred = _synthetic_fred_fallback()
        X_all = np.random.default_rng(42).standard_normal((len(raw_fred), 7, 6))
        dates = raw_fred.index
        sectors = [f"Sector {i+1}" for i in range(7)]
        src = "Synthetic"

    X_normal, _ = get_normal_period(X_all, dates)
    X_std, _, _ = standardise_panel(X_all, X_ref=X_normal)
    X_norm_std, _, _ = standardise_panel(X_normal, X_ref=X_normal)
    mu_eq = X_norm_std.reshape(-1, X_std.shape[-1]).mean(axis=0)

    bsdt = BSDTOperator().fit(X_norm_std)
    stats = analyse_trajectory(X_std, mu_eq, bsdt, alpha=ALPHA, verbose=verbose)

    return X_std, dates, sectors, mu_eq, bsdt, stats, src


# ─────────────────────────────────────────────
# Navier-Stokes decomposition
# ─────────────────────────────────────────────

def navier_stokes_decomposition(X_series: np.ndarray, dates: pd.DatetimeIndex):
    """
    Compute strain rate, vorticity, and enstrophy from velocity field
    dX/dt (finite differences on institution position changes).

    Returns dict of time series arrays.
    """
    T, N, d = X_series.shape
    # Velocity field: dX/dt ≈ X(t+1) - X(t)
    V = np.diff(X_series, axis=0)  # (T-1, N, d)

    enstrophy = np.zeros(T - 1)
    strain_energy = np.zeros(T - 1)
    vorticity_norm = np.zeros(T - 1)
    divergence = np.zeros(T - 1)

    for t in range(T - 1):
        Vt = V[t]  # (N, d)
        # Velocity gradient tensor (finite difference across agents)
        # Approximate: use outer product of velocity differences
        # J_ij = dv_i/dx_j  ≈  covariance-like
        Vt_centered = Vt - Vt.mean(axis=0)
        J = Vt_centered.T @ Vt_centered / (N - 1)  # (d, d)

        # Symmetric part (strain rate tensor)
        S = 0.5 * (J + J.T)
        # Anti-symmetric part (vorticity tensor)
        Omega = 0.5 * (J - J.T)

        strain_energy[t] = float(np.sum(S ** 2))
        vort_sq = float(np.sum(Omega ** 2))
        vorticity_norm[t] = np.sqrt(vort_sq)
        enstrophy[t] = 0.5 * vort_sq  # ε = ½||ω||²_F
        divergence[t] = float(np.trace(J))

    return {
        "enstrophy": enstrophy,
        "strain_energy": strain_energy,
        "vorticity_norm": vorticity_norm,
        "divergence": divergence,
        "dates": dates[1:],
    }


# ─────────────────────────────────────────────
# Minsky regime classification
# ─────────────────────────────────────────────

def classify_minsky(stats, dates):
    """
    Classify each quarter into hedge/speculative/Ponzi regime
    based on gradient alignment and energy.
    """
    cos = stats["cos_theta"]
    gamma = stats["gamma_star"]
    regimes = np.full(len(cos), "Hedge", dtype=object)
    regimes[gamma > 0.5] = "Speculative"
    regimes[(gamma > 0.8) | (cos < -0.5)] = "Ponzi"
    return regimes


# ─────────────────────────────────────────────
# Panel 1: Pairwise force arrows
# ─────────────────────────────────────────────

def plot_pairwise_forces(ax, X, mu, sectors, title="Pairwise Forces"):
    """
    Plot institutions as circles with pairwise force arrows.
    Blue = attraction, Red = repulsion.  Arrow width ∝ |force|.
    """
    N, d = X.shape
    # Project to 2D via PCA if d > 2
    if d > 2:
        from numpy.linalg import svd
        Xc = X - X.mean(axis=0)
        U, S, Vt = svd(Xc, full_matrices=False)
        pos = (Xc @ Vt[:2].T)
        mu2 = ((mu - X.mean(axis=0)) @ Vt[:2].T)
    else:
        pos = X[:, :2]
        mu2 = mu[:2]

    # Compute pairwise distances and force magnitudes
    for i in range(N):
        for j in range(i + 1, N):
            diff = X[i] - X[j]
            r = np.linalg.norm(diff) + EPS
            # Attraction: γ exp(-r²/σ²)
            f_att = GAMMA * np.exp(-(r ** 2) / (SIGMA ** 2))
            # Repulsion: γ λ / r
            f_rep = GAMMA * LAMBDA_REP / (r + EPS)
            net = f_att - f_rep  # positive = net attraction

            if d > 2:
                diff2 = pos[i] - pos[j]
            else:
                diff2 = pos[i] - pos[j]
            r2 = np.linalg.norm(diff2) + 1e-8
            unit = diff2 / r2

            mid = 0.5 * (pos[i] + pos[j])
            mag = abs(net) * 0.3  # scale for visibility

            color = "#2166AC" if net > 0 else "#B2182B"
            alpha = min(0.9, 0.3 + abs(net) * 0.5)

            # Arrow from j toward i if attraction, i toward j if repulsion
            if net > 0:
                ax.annotate("", xy=pos[i], xytext=pos[j],
                            arrowprops=dict(arrowstyle="-|>", color=color,
                                            lw=1.0 + mag * 3, alpha=alpha,
                                            connectionstyle="arc3,rad=0.1"))
            else:
                ax.annotate("", xy=pos[j], xytext=pos[i],
                            arrowprops=dict(arrowstyle="-|>", color=color,
                                            lw=1.0 + mag * 3, alpha=alpha,
                                            connectionstyle="arc3,rad=0.1"))

    # Plot institutions
    for i in range(N):
        ax.scatter(pos[i, 0], pos[i, 1], s=250, c=[SECTOR_COLORS[i]],
                   edgecolors="k", linewidths=1.5, zorder=5)
        label = SECTOR_SHORT[i] if i < len(SECTOR_SHORT) else f"S{i}"
        ax.annotate(label, pos[i], fontsize=6, ha="center", va="bottom",
                    xytext=(0, 12), textcoords="offset points")

    # Equilibrium
    ax.scatter(mu2[0], mu2[1], s=120, c="gold", marker="*",
               edgecolors="k", linewidths=1, zorder=6, label="μ (equilibrium)")

    ax.set_title(title, fontsize=11, fontweight="bold")
    att_patch = mpatches.Patch(color="#2166AC", label="Attraction")
    rep_patch = mpatches.Patch(color="#B2182B", label="Repulsion")
    ax.legend(handles=[att_patch, rep_patch], loc="lower right", fontsize=7)
    ax.set_xlabel("PC1", fontsize=8)
    ax.set_ylabel("PC2", fontsize=8)
    ax.grid(True, alpha=0.3)


# ─────────────────────────────────────────────
# Panel 2: Force field quiver
# ─────────────────────────────────────────────

def plot_force_field(ax, X, mu, title="Total Force Field"):
    """
    Show a 2D quiver plot of the total force field on a grid around
    the institution positions, with institutions overlaid.
    """
    N, d = X.shape
    if d > 2:
        from numpy.linalg import svd
        Xm = X.mean(axis=0)
        Xc = X - Xm
        U, S, Vt = svd(Xc, full_matrices=False)
        proj = Vt[:2]
        pos = Xc @ proj.T
        mu2 = (mu - Xm) @ proj.T
    else:
        pos = X[:, :2]
        mu2 = mu[:2]
        proj = np.eye(d)[:2]

    # Grid
    pad = 1.5
    x_range = [pos[:, 0].min() - pad, pos[:, 0].max() + pad]
    y_range = [pos[:, 1].min() - pad, pos[:, 1].max() + pad]
    gx = np.linspace(x_range[0], x_range[1], 18)
    gy = np.linspace(y_range[0], y_range[1], 18)
    GX, GY = np.meshgrid(gx, gy)

    FX = np.zeros_like(GX)
    FY = np.zeros_like(GY)

    for ii in range(GX.shape[0]):
        for jj in range(GX.shape[1]):
            # Build a full-d state by replacing one agent's position
            pt2 = np.array([GX[ii, jj], GY[ii, jj]])
            # Reconstruct in d-space
            pt_d = mu + pt2 @ proj  # approximate
            X_test = X.copy()
            X_test[0] = pt_d  # test force on "agent 0" at this position
            F = total_force(X_test, mu)
            F0 = F[0]  # force on agent 0
            F2 = F0 @ proj.T  # project to 2D
            FX[ii, jj] = F2[0]
            FY[ii, jj] = F2[1]

    # Normalize for display
    mag = np.sqrt(FX ** 2 + FY ** 2)
    mag_max = mag.max() + 1e-10

    ax.quiver(GX, GY, FX, FY, mag, cmap="coolwarm", alpha=0.7,
              scale=mag_max * 15, width=0.004)

    for i in range(N):
        ax.scatter(pos[i, 0], pos[i, 1], s=200, c=[SECTOR_COLORS[i]],
                   edgecolors="k", linewidths=1.5, zorder=5)

    ax.scatter(mu2[0], mu2[1], s=100, c="gold", marker="*",
               edgecolors="k", linewidths=1, zorder=6)

    ax.set_title(title, fontsize=11, fontweight="bold")
    ax.set_xlabel("PC1", fontsize=8)
    ax.set_ylabel("PC2", fontsize=8)
    ax.grid(True, alpha=0.3)


# ─────────────────────────────────────────────
# Panel 3: Navier-Stokes analogy
# ─────────────────────────────────────────────

def plot_navier_stokes(ax, ns_data, title="Navier–Stokes Analogy"):
    """Plot enstrophy, strain, and vorticity over time with crisis shading."""
    dates = ns_data["dates"]

    ax2 = ax.twinx()

    l1, = ax.plot(dates, ns_data["enstrophy"], color="#D32F2F", lw=1.8,
                  label="Enstrophy ε", alpha=0.9)
    l2, = ax.plot(dates, ns_data["strain_energy"], color="#1976D2", lw=1.2,
                  label="Strain ||S||²", alpha=0.7)
    l3, = ax2.plot(dates, ns_data["vorticity_norm"], color="#388E3C", lw=1.2,
                   label="Vorticity ||Ω||", alpha=0.7, linestyle="--")

    # Crisis shading
    for label, (s, e, col) in CRISIS_SHADING.items():
        ax.axvspan(pd.Timestamp(s), pd.Timestamp(e), color=col, zorder=0)

    ax.set_ylabel("Enstrophy / Strain", fontsize=8)
    ax2.set_ylabel("Vorticity", fontsize=8, color="#388E3C")
    ax.set_title(title, fontsize=11, fontweight="bold")

    lines = [l1, l2, l3]
    ax.legend(lines, [l.get_label() for l in lines], loc="upper left", fontsize=7)
    ax.grid(True, alpha=0.3)


# ─────────────────────────────────────────────
# Panel 4: γ*(t) + Energy
# ─────────────────────────────────────────────

def plot_friction_energy(ax, stats, dates, title="Adaptive Friction γ*(t) & Energy"):
    """γ* and total energy over time with crisis shading."""
    ax2 = ax.twinx()

    l1, = ax.plot(dates, stats["gamma_star"], color="#E65100", lw=2,
                  label="γ*(t)", alpha=0.9)
    l2, = ax2.plot(dates, stats["energy"], color="#4A148C", lw=1.2,
                   label="Φ(X) energy", alpha=0.7, linestyle="--")

    # Crisis shading
    for label, (s, e, col) in CRISIS_SHADING.items():
        ax.axvspan(pd.Timestamp(s), pd.Timestamp(e), color=col, zorder=0)

    # Critical threshold line
    ax.axhline(1.0, color="red", linestyle=":", lw=1, alpha=0.5, label="γ*=1 (max)")

    ax.set_ylabel("γ*(t)", fontsize=8, color="#E65100")
    ax2.set_ylabel("Φ(X)", fontsize=8, color="#4A148C")
    ax.set_title(title, fontsize=11, fontweight="bold")

    lines = [l1, l2]
    ax.legend(lines, [l.get_label() for l in lines], loc="upper left", fontsize=7)
    ax.grid(True, alpha=0.3)


# ─────────────────────────────────────────────
# Panel 5: Gradient alignment cos θ + Minsky
# ─────────────────────────────────────────────

def plot_alignment_minsky(ax, stats, dates, title="Gradient Alignment cos θ(t) & Minsky Regimes"):
    """cos θ over time, background-filled by Minsky regime."""
    cos = stats["cos_theta"]
    regimes = classify_minsky(stats, dates)

    regime_colors = {"Hedge": "#C8E6C9", "Speculative": "#FFF9C4", "Ponzi": "#FFCDD2"}
    # Background fill by regime
    for i in range(len(dates) - 1):
        ax.axvspan(dates[i], dates[i + 1], color=regime_colors.get(regimes[i], "#FFFFFF"),
                   alpha=0.5, zorder=0)

    ax.plot(dates, cos, color="#1A237E", lw=1.5, alpha=0.9)
    ax.axhline(0, color="gray", linestyle="--", lw=0.8, alpha=0.5)
    ax.axhline(0.7, color="green", linestyle=":", lw=0.8, alpha=0.5, label="θ=0.7 threshold")

    # Crisis shading
    for label, (s, e, col) in CRISIS_SHADING.items():
        ax.axvspan(pd.Timestamp(s), pd.Timestamp(e), color=col, zorder=1)

    h_patch = mpatches.Patch(color="#C8E6C9", label="Hedge")
    s_patch = mpatches.Patch(color="#FFF9C4", label="Speculative")
    p_patch = mpatches.Patch(color="#FFCDD2", label="Ponzi")
    ax.legend(handles=[h_patch, s_patch, p_patch], loc="lower left", fontsize=7)

    ax.set_ylabel("cos θ", fontsize=8)
    ax.set_title(title, fontsize=11, fontweight="bold")
    ax.grid(True, alpha=0.3)


# ─────────────────────────────────────────────
# Panel 6: Spectral radius vs critical manifold
# ─────────────────────────────────────────────

def plot_spectral_radius(ax, stats, dates, title="Spectral Radius λ_max(t) vs Critical Manifold"):
    """λ_max over time with critical threshold."""
    lm = stats["lambda_max"]

    ax.fill_between(dates, lm, where=stats["above_cman"],
                    color="#FFCDD2", alpha=0.6, label="Above C (super-critical)")
    ax.fill_between(dates, lm, where=~stats["above_cman"],
                    color="#C8E6C9", alpha=0.4, label="Below C (sub-critical)")
    ax.plot(dates, lm, color="#B71C1C", lw=1.8, alpha=0.9)
    ax.axhline(ALPHA, color="#2E7D32", lw=2, linestyle="--",
               label=f"α = {ALPHA} (critical threshold)")

    for label, (s, e, col) in CRISIS_SHADING.items():
        ax.axvspan(pd.Timestamp(s), pd.Timestamp(e), color=col, zorder=0)

    ax.set_ylabel("λ_max", fontsize=8)
    ax.set_title(title, fontsize=11, fontweight="bold")
    ax.legend(loc="upper left", fontsize=7)
    ax.grid(True, alpha=0.3)


# ─────────────────────────────────────────────
# Detailed pairwise force snapshot
# ─────────────────────────────────────────────

def plot_pairwise_detail(X, mu, sectors, snapshot_date, save_path):
    """Large single-panel showing all pairwise force magnitudes as a heatmap + arrows."""
    N, d = X.shape
    fig, axes = plt.subplots(1, 2, figsize=(16, 7))

    # Left: force arrow diagram
    plot_pairwise_forces(axes[0], X, mu, sectors,
                         title=f"Pairwise Forces ({snapshot_date})")

    # Right: force magnitude matrix (NxN heatmap)
    F_mag = np.zeros((N, N))
    F_sign = np.zeros((N, N))  # +1 attraction, -1 repulsion
    for i in range(N):
        for j in range(N):
            if i == j:
                continue
            diff = X[i] - X[j]
            r = np.linalg.norm(diff) + EPS
            f_att = GAMMA * np.exp(-(r ** 2) / (SIGMA ** 2))
            f_rep = GAMMA * LAMBDA_REP / (r + EPS)
            F_mag[i, j] = abs(f_att - f_rep)
            F_sign[i, j] = 1.0 if (f_att - f_rep) > 0 else -1.0

    labels = [s.replace("\n", " ") for s in SECTOR_SHORT[:N]]

    # Custom colormap: blue (attraction) to red (repulsion)
    F_signed = F_mag * F_sign
    vmax = max(abs(F_signed.min()), abs(F_signed.max()))
    im = axes[1].imshow(F_signed, cmap="coolwarm", vmin=-vmax, vmax=vmax,
                         aspect="equal")

    axes[1].set_xticks(range(N))
    axes[1].set_yticks(range(N))
    axes[1].set_xticklabels(labels, fontsize=7, rotation=45, ha="right")
    axes[1].set_yticklabels(labels, fontsize=7)
    axes[1].set_title(f"Net Force Matrix ({snapshot_date})\nBlue=Attraction, Red=Repulsion",
                      fontsize=11, fontweight="bold")

    # Annotate cells
    for i in range(N):
        for j in range(N):
            if i != j:
                axes[1].text(j, i, f"{F_signed[i,j]:.3f}", ha="center", va="center",
                             fontsize=6, color="white" if abs(F_signed[i, j]) > vmax * 0.5 else "black")

    plt.colorbar(im, ax=axes[1], shrink=0.8, label="Net Force (+ attraction / − repulsion)")

    fig.suptitle("Adaptive Friction – Pairwise Interaction Detail", fontsize=14, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(save_path, dpi=300, bbox_inches="tight")
    print(f"  Saved: {save_path}")
    plt.close(fig)


# ─────────────────────────────────────────────
# Navier-Stokes detail panel
# ─────────────────────────────────────────────

def plot_ns_detail(X_std, dates, save_path):
    """Detailed Navier-Stokes analogy: enstrophy + divergence + viscosity."""
    ns = navier_stokes_decomposition(X_std, dates)
    fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True)

    # 1: Enstrophy + strain
    axes[0].plot(ns["dates"], ns["enstrophy"], color="#D32F2F", lw=2, label="Enstrophy ε = ½||ω||²")
    axes[0].plot(ns["dates"], ns["strain_energy"], color="#1976D2", lw=1.5,
                 label="Strain energy ||S||²", alpha=0.7)
    for label, (s, e, col) in CRISIS_SHADING.items():
        axes[0].axvspan(pd.Timestamp(s), pd.Timestamp(e), color=col, zorder=0)
    axes[0].set_ylabel("Energy", fontsize=9)
    axes[0].legend(fontsize=8, loc="upper left")
    axes[0].set_title("Enstrophy & Strain Rate (Beale–Kato–Majda Indicator)", fontsize=11, fontweight="bold")
    axes[0].grid(True, alpha=0.3)

    # 2: Vorticity norm
    axes[1].fill_between(ns["dates"], ns["vorticity_norm"], color="#388E3C", alpha=0.3)
    axes[1].plot(ns["dates"], ns["vorticity_norm"], color="#388E3C", lw=1.5, label="||Ω|| (vorticity)")
    for label, (s, e, col) in CRISIS_SHADING.items():
        axes[1].axvspan(pd.Timestamp(s), pd.Timestamp(e), color=col, zorder=0)
    axes[1].set_ylabel("Vorticity", fontsize=9)
    axes[1].legend(fontsize=8, loc="upper left")
    axes[1].set_title("Vorticity ||Ω|| – Rotational Energy in Financial Flow", fontsize=11, fontweight="bold")
    axes[1].grid(True, alpha=0.3)

    # 3: Divergence (expansion/contraction)
    div = ns["divergence"]
    axes[2].fill_between(ns["dates"], div, where=div > 0, color="#1565C0", alpha=0.3, label="Expansion")
    axes[2].fill_between(ns["dates"], div, where=div < 0, color="#C62828", alpha=0.3, label="Contraction")
    axes[2].plot(ns["dates"], div, color="#212121", lw=1.2)
    axes[2].axhline(0, color="gray", lw=0.8, linestyle="--")
    for label, (s, e, col) in CRISIS_SHADING.items():
        axes[2].axvspan(pd.Timestamp(s), pd.Timestamp(e), color=col, zorder=0)
    axes[2].set_ylabel("Divergence", fontsize=9)
    axes[2].legend(fontsize=8, loc="upper left")
    axes[2].set_title("Divergence ∇·v – Financial Flow Expansion/Contraction", fontsize=11, fontweight="bold")
    axes[2].grid(True, alpha=0.3)

    fig.suptitle("Navier–Stokes Analogy: Financial Network as Viscous Flow",
                 fontsize=14, fontweight="bold", y=1.01)
    fig.tight_layout()
    fig.savefig(save_path, dpi=300, bbox_inches="tight")
    print(f"  Saved: {save_path}")
    plt.close(fig)


# ─────────────────────────────────────────────
# Main dashboard
# ─────────────────────────────────────────────

def main(snapshot_idx=None, use_cache=True, verbose=False):
    print("Loading data...")
    X_std, dates, sectors, mu_eq, bsdt, stats, src = load_data(use_cache=use_cache, verbose=verbose)
    T, N, d = X_std.shape
    print(f"  Data: {src}  T={T} N={N} d={d}")

    # Pick snapshot (default: GFC peak ~2008-Q3)
    if snapshot_idx is None:
        target = pd.Timestamp("2008-09-30")
        snapshot_idx = int(np.argmin(np.abs(dates - target)))
    snapshot_date = str(dates[snapshot_idx].date())
    X_snap = X_std[snapshot_idx]
    print(f"  Snapshot: t={snapshot_idx} ({snapshot_date})")

    # NS decomposition
    ns_data = navier_stokes_decomposition(X_std, dates)

    # ── Main 6-panel dashboard ──
    print("Building main dashboard...")
    fig = plt.figure(figsize=(20, 14))
    gs = gridspec.GridSpec(3, 2, hspace=0.35, wspace=0.3)

    ax1 = fig.add_subplot(gs[0, 0])
    plot_pairwise_forces(ax1, X_snap, mu_eq, sectors,
                         title=f"① Pairwise Forces ({snapshot_date})")

    ax2 = fig.add_subplot(gs[0, 1])
    plot_force_field(ax2, X_snap, mu_eq,
                     title=f"② Total Force Field ({snapshot_date})")

    ax3 = fig.add_subplot(gs[1, 0])
    plot_navier_stokes(ax3, ns_data,
                       title="③ Navier–Stokes: Enstrophy / Strain / Vorticity")

    ax4 = fig.add_subplot(gs[1, 1])
    plot_friction_energy(ax4, stats, dates,
                         title="④ Adaptive Friction γ*(t) & Energy")

    ax5 = fig.add_subplot(gs[2, 0])
    plot_alignment_minsky(ax5, stats, dates,
                          title="⑤ Gradient Alignment cos θ & Minsky Regimes")

    ax6 = fig.add_subplot(gs[2, 1])
    plot_spectral_radius(ax6, stats, dates,
                         title="⑥ Spectral Radius λ_max vs Critical Manifold")

    fig.suptitle("Adaptive Friction — Force Field & Navier–Stokes Dashboard",
                 fontsize=16, fontweight="bold", y=0.99)

    dash_png = RESULTS_DIR / "force_field_dashboard.png"
    dash_pdf = RESULTS_DIR / "force_field_dashboard.pdf"
    fig.savefig(dash_png, dpi=300, bbox_inches="tight")
    fig.savefig(dash_pdf, bbox_inches="tight")
    print(f"  Saved: {dash_png}")
    print(f"  Saved: {dash_pdf}")
    plt.close(fig)

    # ── Detail views ──
    print("Building pairwise detail...")
    plot_pairwise_detail(X_snap, mu_eq, sectors, snapshot_date,
                         RESULTS_DIR / "pairwise_forces_detail.png")

    print("Building Navier-Stokes detail...")
    plot_ns_detail(X_std, dates, RESULTS_DIR / "navier_stokes_analogy.png")

    # ── Multi-snapshot comparison: normal vs crisis ──
    print("Building normal vs crisis comparison...")
    target_normal = pd.Timestamp("2000-06-30")
    idx_normal = int(np.argmin(np.abs(dates - target_normal)))
    fig2, axes2 = plt.subplots(1, 2, figsize=(16, 7))
    plot_pairwise_forces(axes2[0], X_std[idx_normal], mu_eq, sectors,
                         title=f"Normal Period ({dates[idx_normal].date()})")
    plot_pairwise_forces(axes2[1], X_snap, mu_eq, sectors,
                         title=f"GFC Crisis ({snapshot_date})")
    fig2.suptitle("Attraction/Repulsion: Normal vs Crisis", fontsize=14, fontweight="bold")
    fig2.tight_layout(rect=[0, 0, 1, 0.95])
    comp_path = RESULTS_DIR / "normal_vs_crisis_forces.png"
    fig2.savefig(comp_path, dpi=300, bbox_inches="tight")
    print(f"  Saved: {comp_path}")
    plt.close(fig2)

    print("\nAll visualizations complete!")
    print(f"  Output directory: {RESULTS_DIR}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Adaptive Friction Force-Field Visualization")
    p.add_argument("--snapshot", type=int, default=None, help="Quarter index for snapshot panels")
    p.add_argument("--no-cache", action="store_true")
    p.add_argument("--verbose", action="store_true")
    a = p.parse_args()
    main(snapshot_idx=a.snapshot, use_cache=not a.no_cache, verbose=a.verbose)
