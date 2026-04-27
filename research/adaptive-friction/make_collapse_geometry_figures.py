"""High-resolution figures for collapse_geometry — SIAM paper §7 results.

Reuses loaders + frozen-normal calibration from run_frozen_normal_simulation.py
and produces, per dataset, the SIAM minimum figure set:

    Fig 1  state-space trajectory + collapse direction  (2D PCA, with ellipse)
    Fig 2  state-space trajectory + collapse direction  (3D PCA)
    Fig 3  Mahalanobis-energy landscape (PCA grid contours + trajectory)
    Fig 4  P_t / Q_t regime map  (controllable vs uncontrollable shading)
    Fig 5  Per-channel V̇_k  (stacked area C, G, A, T)
    Fig 6  Two-layer EWS  (Layer A precursor + Layer B geometry)
    Fig 7  Alignment ψ_t and cos θ_state
    Fig 8  Energy trajectory e_BSDT(t) with χ² threshold

Plus a single cross-domain summary figure.

Output: research/adaptive-friction/figures/<dataset>/*.png  @ 300 DPI
"""
from __future__ import annotations
import sys
from pathlib import Path

import numpy as np
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401  (registers 3d projection)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research" / "adaptive-friction"))

from collapse_geometry import (
    MasterOperator, Snapshot, LedoitWolfNetwork,
    LyapunovCertificate, CollapseGeometry, EarlyWarning, PrecursorScale,
    InformationGeometry,
)
from run_frozen_normal_simulation import (
    load_fdic_panel, load_gsib_panel, load_ercot_panel, load_terra_luna_panel,
)

# ─────────────────────────── style ───────────────────────────
mpl.rcParams.update({
    "figure.dpi": 120,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "font.family": "serif",
    "font.size": 10,
    "axes.titlesize": 11,
    "axes.labelsize": 10,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "grid.linestyle": ":",
    "legend.frameon": False,
    "legend.fontsize": 8.5,
    "lines.linewidth": 1.6,
})

CRISIS_COLOR = "#c0392b"
ALARM_COLOR  = "#e67e22"
SAFE_COLOR   = "#2ecc71"
TRAJ_COLOR   = "#2c3e50"
CHAN_COLORS  = {"C": "#3498db", "G": "#9b59b6",
                "A": "#e67e22", "T": "#16a085"}


# ═════════════════════════════════════════════════════════════
# Per-snapshot data collection (recomputes everything once)
# ═════════════════════════════════════════════════════════════

def collect_diagnostics(name, panel, labels, t_cut, t_eval, t_crisis,
                        history_len: int):
    """Run the frozen-normal protocol and capture the full per-snapshot
    quantities needed for plotting (not just scalars)."""
    T, N, d = panel.shape
    X_normal = panel[:t_cut]

    M = MasterOperator.calibrate(X_normal, k=min(4, d), theta=1.0)
    net = LedoitWolfNetwork.from_panel(X_normal[..., 0])
    info = InformationGeometry(op=M)
    e_star = info.chi2_threshold(N, d, alpha_conf=0.01)
    geom = CollapseGeometry(op=M)
    lyap = LyapunovCertificate(op=M)
    ews = EarlyWarning(op=M, geom=geom)
    ews.precursor_scale = PrecursorScale.from_panel(M, X_normal)
    ews_thresh_fixed = ews.threshold(theta=M.damp.theta, e_star=e_star)

    # Layer-B dynamic threshold from normal window
    normal_ews = []
    for t in range(1, t_cut):
        snap = Snapshot(X=panel[t], X_prev=panel[t - 1],
                        history=panel[max(0, t - history_len): t])
        try:
            normal_ews.append(ews.score(snap, net))
        except Exception:
            pass
    mu_n = float(np.nanmean(normal_ews)) if normal_ews else 0.0
    sd_n = float(np.nanstd(normal_ews))  if normal_ews else 1e-10
    sd_n = max(sd_n, 1e-10)
    ews_thresh_dyn = mu_n + 2.0 * sd_n

    # Per-snapshot collection over full panel (needed for mean state PCA)
    diag = {
        "name": name, "labels": labels, "panel": panel,
        "t_cut": t_cut, "t_eval": t_eval, "t_crisis": t_crisis,
        "M": M, "net": net, "lyap": lyap, "ews": ews, "geom": geom,
        "e_star": e_star, "ews_thresh_dyn": ews_thresh_dyn,
        "ews_thresh_fixed": ews_thresh_fixed,
    }

    # Mean-state trajectory: x̄_t (one point per period, mean over agents)
    x_bar = panel.mean(axis=1)                # (T, d)
    diag["x_bar"] = x_bar

    # Per-period diagnostics (computed for every t≥1 over the full panel so that
    # background plots can show normal+crisis context together)
    rows = []
    G_list = []   # collapse-direction G̃_t (N,d) — projected later
    F_list = []   # restoring force F_t (N,d)
    for t in range(1, T):
        snap = Snapshot(X=panel[t], X_prev=panel[t - 1],
                        history=panel[max(0, t - history_len): t])
        snap_prev = Snapshot(
            X=panel[t - 1],
            X_prev=panel[t - 2] if t > 1 else panel[t - 1],
            history=panel[max(0, t - 1 - history_len): t - 1],
        ) if t >= 2 else None
        try:
            b   = lyap._bundle(snap)
            ch  = lyap.channel_decomposition(snap)
            tl  = ews.two_layer(snap, net, snap_prev, e_star,
                                geometry_threshold=ews_thresh_dyn)
            rows.append(dict(
                t=t, label=labels[t],
                e_BSDT=float(M.damp.e_BSDT(snap)),
                gamma=float(M.damp.gamma_star(snap)),
                psi=float(M.mfls.psi(snap)),
                rho_mfls=float(M.mfls.rho_mfls(snap)),
                cos_theta_state=float(geom.cos_theta_state(snap)),
                cos_theta_chan=float(geom.cos_theta_channel(snap)),
                Pt=float(b["Pt"]), Qt=float(b["Qt"]),
                dV_dt=float(lyap.dV_dt(snap)),
                margin=float(lyap.margin(snap)),
                v_C=float(ch["C"]["v_total"]),
                v_G=float(ch["G"]["v_total"]),
                v_A=float(ch["A"]["v_total"]),
                v_T=float(ch["T"]["v_total"]),
                ews=float(tl["geometry_score"]),
                pre=float(tl["precursor_score"]),
                alarm_A=bool(tl["precursor_alarm"]),
                alarm_B=bool(tl["geometry_alarm"]),
            ))
            G_list.append(M.mfls.state_pullback(snap))
            F_list.append(M.force(snap))
        except Exception as e:
            rows.append(dict(t=t, label=labels[t], error=str(e)))
            G_list.append(None); F_list.append(None)

    # Materialise scalar columns
    valid = [r for r in rows if "error" not in r]
    diag["rows"] = valid
    diag["t_arr"]  = np.array([r["t"] for r in valid])
    diag["e_arr"]  = np.array([r["e_BSDT"] for r in valid])
    diag["psi"]    = np.array([r["psi"] for r in valid])
    diag["rho"]    = np.array([r["rho_mfls"] for r in valid])
    diag["cosS"]   = np.array([r["cos_theta_state"] for r in valid])
    diag["cosC"]   = np.array([r["cos_theta_chan"] for r in valid])
    diag["Pt"]     = np.array([r["Pt"] for r in valid])
    diag["Qt"]     = np.array([r["Qt"] for r in valid])
    diag["dVdt"]   = np.array([r["dV_dt"] for r in valid])
    diag["v_C"]    = np.array([r["v_C"] for r in valid])
    diag["v_G"]    = np.array([r["v_G"] for r in valid])
    diag["v_A"]    = np.array([r["v_A"] for r in valid])
    diag["v_T"]    = np.array([r["v_T"] for r in valid])
    diag["ews"]    = np.array([r["ews"] for r in valid])
    diag["pre"]    = np.array([r["pre"] for r in valid])
    diag["alarm_A"] = np.array([r["alarm_A"] for r in valid])
    diag["alarm_B"] = np.array([r["alarm_B"] for r in valid])
    diag["G_list"] = G_list
    diag["F_list"] = F_list
    return diag


# ═════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════

def _t_to_idx(diag, t):
    """Map raw period index t → row index inside diag['t_arr']."""
    arr = diag["t_arr"]
    hits = np.flatnonzero(arr == t)
    return int(hits[0]) if hits.size else None


def _xtick_subset(labels, n=8):
    L = len(labels)
    if L <= n:
        return list(range(L)), labels
    step = max(1, L // n)
    idx = list(range(0, L, step))
    if idx[-1] != L - 1:
        idx.append(L - 1)
    return idx, [labels[i] for i in idx]


# ═════════════════════════════════════════════════════════════
# Figures
# ═════════════════════════════════════════════════════════════

def fig_trajectory_2d(diag, out_dir):
    """Mean-state trajectory in 2D PCA, with critical Mahalanobis ellipse and
    collapse-direction arrows projected from G̃_t."""
    M = diag["M"]; t_cut = diag["t_cut"]; t_crisis = diag["t_crisis"]
    x_bar = diag["x_bar"]
    # PCA on normal-window mean states (no lookahead)
    Xn = x_bar[:t_cut] - x_bar[:t_cut].mean(axis=0)
    U, S, Vt = np.linalg.svd(Xn, full_matrices=False)
    PC = Vt[:2]                                                     # (2, d)
    proj = (x_bar - x_bar[:t_cut].mean(axis=0)) @ PC.T              # (T, 2)

    fig, ax = plt.subplots(figsize=(7.5, 6.5))
    # 2D Mahalanobis confidence ellipse (df=2, α=0.01) in PC plane.
    # This is the canonical 99% confidence ellipse for the projected
    # mean-state distribution — far more honest than rescaling a high-d e*.
    from scipy.stats import chi2 as _chi2
    e2 = float(_chi2.ppf(0.99, df=2))                              # ≈ 9.21
    proj_n = proj[:t_cut]
    cov2 = np.cov(proj_n, rowvar=False)
    eigvals, eigvecs = np.linalg.eigh(cov2)
    order = np.argsort(eigvals)[::-1]
    eigvals, eigvecs = eigvals[order], eigvecs[:, order]
    sx = float(np.sqrt(max(eigvals[0], 1e-12) * e2))
    sy = float(np.sqrt(max(eigvals[1], 1e-12) * e2))
    angle = float(np.degrees(np.arctan2(eigvecs[1, 0], eigvecs[0, 0])))
    ell = Ellipse((0, 0), 2 * sx, 2 * sy, angle=angle,
                  facecolor="none", edgecolor=CRISIS_COLOR,
                  linestyle="--", linewidth=1.4,
                  label=f"χ²(0.99, df=2) ellipse  (full e* = {diag['e_star']:.1f})")
    ax.add_patch(ell)

    # trajectory split: normal vs crisis
    n_pre = t_cut
    ax.plot(proj[:n_pre, 0], proj[:n_pre, 1], "-", color=SAFE_COLOR,
            alpha=0.55, lw=1.4, label="normal")
    ax.plot(proj[n_pre:, 0], proj[n_pre:, 1], "-", color=TRAJ_COLOR,
            alpha=0.85, lw=1.6, label="evaluation")
    ax.scatter(proj[:n_pre, 0], proj[:n_pre, 1], s=14,
               color=SAFE_COLOR, alpha=0.5)
    ax.scatter(proj[n_pre:, 0], proj[n_pre:, 1], s=18,
               color=TRAJ_COLOR, alpha=0.85)
    ax.scatter([proj[t_crisis, 0]], [proj[t_crisis, 1]],
               s=140, marker="*", color=CRISIS_COLOR,
               edgecolor="black", linewidth=0.6, zorder=10,
               label=f"crisis onset ({diag['labels'][t_crisis]})")

    # Collapse-direction arrows G̃_t projected (sub-sampled)
    G_list = diag["G_list"]
    every = max(1, len(G_list) // 18)
    for i in range(0, len(G_list), every):
        Gt = G_list[i]
        if Gt is None: continue
        gbar = Gt.mean(axis=0)
        gp = gbar @ PC.T
        gn = np.linalg.norm(gp)
        if gn < 1e-9: continue
        gp = gp / gn * 0.10 * (proj.max() - proj.min())
        t = diag["t_arr"][i]
        ax.arrow(proj[t, 0], proj[t, 1], gp[0], gp[1],
                 head_width=0.04 * (proj.max() - proj.min()),
                 head_length=0.06 * (proj.max() - proj.min()),
                 fc="#8e44ad", ec="#8e44ad", alpha=0.55, length_includes_head=True)

    ax.axhline(0, color="k", lw=0.4, alpha=0.3)
    ax.axvline(0, color="k", lw=0.4, alpha=0.3)
    ax.set_xlabel("PC 1 (mean-state)")
    ax.set_ylabel("PC 2 (mean-state)")
    ax.set_title(f"{diag['name']} — state-space trajectory + collapse direction")
    ax.legend(loc="best")
    ax.set_aspect("equal", adjustable="datalim")
    fig.savefig(out_dir / "fig1_trajectory_2d.png")
    plt.close(fig)


def fig_trajectory_3d(diag, out_dir):
    M = diag["M"]; t_cut = diag["t_cut"]; t_crisis = diag["t_crisis"]
    x_bar = diag["x_bar"]
    if x_bar.shape[1] < 3:
        return  # need ≥3 features
    Xn = x_bar[:t_cut] - x_bar[:t_cut].mean(axis=0)
    _, _, Vt = np.linalg.svd(Xn, full_matrices=False)
    PC = Vt[:3]
    proj = (x_bar - x_bar[:t_cut].mean(axis=0)) @ PC.T  # (T, 3)
    n_pre = t_cut

    fig = plt.figure(figsize=(8.5, 7.0))
    ax = fig.add_subplot(111, projection="3d")
    ax.plot(proj[:n_pre, 0], proj[:n_pre, 1], proj[:n_pre, 2],
            color=SAFE_COLOR, alpha=0.55, lw=1.3, label="normal")
    ax.plot(proj[n_pre:, 0], proj[n_pre:, 1], proj[n_pre:, 2],
            color=TRAJ_COLOR, alpha=0.85, lw=1.6, label="evaluation")
    ax.scatter(proj[:n_pre, 0], proj[:n_pre, 1], proj[:n_pre, 2],
               s=10, color=SAFE_COLOR, alpha=0.5)
    ax.scatter(proj[n_pre:, 0], proj[n_pre:, 1], proj[n_pre:, 2],
               s=12, color=TRAJ_COLOR, alpha=0.85)
    ax.scatter([proj[t_crisis, 0]], [proj[t_crisis, 1]], [proj[t_crisis, 2]],
               s=150, marker="*", color=CRISIS_COLOR,
               edgecolor="black", linewidth=0.6,
               label=f"crisis onset ({diag['labels'][t_crisis]})")
    ax.set_xlabel("PC 1"); ax.set_ylabel("PC 2"); ax.set_zlabel("PC 3")
    ax.set_title(f"{diag['name']} — state-space trajectory (3D PCA)")
    ax.legend(loc="upper left")
    fig.savefig(out_dir / "fig2_trajectory_3d.png")
    plt.close(fig)


def fig_energy_landscape(diag, out_dir):
    """Mahalanobis energy landscape on the 2D PCA plane of mean states.

    Background contours = e_BSDT(x̄) for synthetic x̄ on the PCA grid.
    Trajectory overlaid.
    """
    M = diag["M"]; t_cut = diag["t_cut"]; t_crisis = diag["t_crisis"]
    x_bar = diag["x_bar"]
    Xn = x_bar[:t_cut] - x_bar[:t_cut].mean(axis=0)
    _, _, Vt = np.linalg.svd(Xn, full_matrices=False)
    PC = Vt[:2]
    centre = x_bar[:t_cut].mean(axis=0)
    proj = (x_bar - centre) @ PC.T

    rng = max(np.abs(proj).max() * 1.25, 1e-6)
    grid = np.linspace(-rng, rng, 90)
    GX, GY = np.meshgrid(grid, grid)
    # Lift PCA → state then compute Mahalanobis to mu0 (frozen calibration)
    flat = np.stack([GX.ravel(), GY.ravel()], axis=1) @ PC + centre   # (G,d)
    cen = flat - M.cal.mu0
    e_grid = np.einsum("nd,de,ne->n", cen, M.cal.Sigma0_inv, cen).reshape(GX.shape)

    fig, ax = plt.subplots(figsize=(8.0, 6.5))
    cs = ax.contourf(GX, GY, e_grid, levels=20, cmap="viridis", alpha=0.85)
    ax.contour(GX, GY, e_grid, levels=[diag["e_star"]],
               colors=CRISIS_COLOR, linestyles="--", linewidths=1.6)
    cb = fig.colorbar(cs, ax=ax, shrink=0.86)
    cb.set_label("e_BSDT(X̄) — Mahalanobis energy")

    n_pre = t_cut
    ax.plot(proj[:n_pre, 0], proj[:n_pre, 1], "o-",
            color="white", mec="black", ms=4, lw=1.0, alpha=0.7,
            label="normal")
    ax.plot(proj[n_pre:, 0], proj[n_pre:, 1], "o-",
            color="#f1c40f", mec="black", ms=4.5, lw=1.4,
            label="evaluation")
    ax.scatter([proj[t_crisis, 0]], [proj[t_crisis, 1]],
               s=180, marker="*", color=CRISIS_COLOR,
               edgecolor="white", linewidth=1.0, zorder=10,
               label=f"crisis ({diag['labels'][t_crisis]})")
    ax.set_xlabel("PC 1"); ax.set_ylabel("PC 2")
    ax.set_title(f"{diag['name']} — energy landscape with χ² boundary (e* = {diag['e_star']:.1f})")
    ax.legend(loc="best")
    fig.savefig(out_dir / "fig3_energy_landscape.png")
    plt.close(fig)


def fig_pq_regimes(diag, out_dir):
    """P_t / Q_t time series with controllable / uncontrollable shading."""
    t = diag["t_arr"]; P = diag["Pt"]; Q = diag["Qt"]
    labels = diag["labels"]
    t_crisis = diag["t_crisis"]
    fig, axes = plt.subplots(2, 1, figsize=(9.0, 6.0), sharex=True)

    # Plot signals first so axis auto-scaling adapts to real data ranges
    axes[0].plot(t, P, color="#2c3e50", lw=1.5, label="P_t = ⟨G̃, F⟩")
    axes[1].plot(t, Q, color="#8e44ad", lw=1.5, label="Q_t = ⟨F,g⟩·R_t")
    axes[0].set_ylabel("P_t")
    axes[1].set_ylabel("Q_t"); axes[1].set_xlabel("period")
    axes[0].set_title(f"{diag['name']} — P_t / Q_t regime map")

    # Symmetric log when range is huge
    def _sym(ax, vals):
        v = vals[np.isfinite(vals)]
        if v.size and np.nanmax(np.abs(v)) / max(np.nanstd(v), 1e-9) > 50:
            lin = max(np.median(np.abs(v[v != 0])) if (v != 0).any() else 1.0, 1e-6)
            ax.set_yscale("symlog", linthresh=lin)
    _sym(axes[0], P); _sym(axes[1], Q)

    # Regime shading (axes-fraction y so it spans full height regardless of scale)
    safe   = P < 0
    ctrl   = (P > 0) & (Q > 0)
    unctrl = (P > 0) & (Q <= 0)
    for ax in axes:
        tr = ax.get_xaxis_transform()
        ax.fill_between(t, 0, 1, where=safe,   transform=tr,
                        color=SAFE_COLOR, alpha=0.10, step="mid",
                        label="P<0 safe")
        ax.fill_between(t, 0, 1, where=ctrl,   transform=tr,
                        color="#3498db", alpha=0.08, step="mid",
                        label="P>0, Q>0 controllable")
        ax.fill_between(t, 0, 1, where=unctrl, transform=tr,
                        color=CRISIS_COLOR, alpha=0.18, step="mid",
                        label="P>0, Q≤0 UNCONTROLLABLE")
        ax.axvline(t_crisis, color=CRISIS_COLOR, lw=1.0, ls="--", alpha=0.7)
        ax.axhline(0, color="k", lw=0.5)

    h, l = axes[0].get_legend_handles_labels()
    seen = {}
    for hi, li in zip(h, l):
        seen.setdefault(li, hi)
    axes[0].legend(seen.values(), seen.keys(), loc="upper left", ncol=2)

    idx, lab = _xtick_subset(labels, n=8)
    axes[1].set_xticks(idx); axes[1].set_xticklabels(lab, rotation=20, ha="right")
    axes[1].set_xlim(t[0], t[-1])
    fig.savefig(out_dir / "fig4_pq_regimes.png")
    plt.close(fig)


def fig_channel_stack(diag, out_dir):
    """Per-channel V̇_k as fractional contribution |v_k| / Σ|v_j| ∈ [0,1].

    Plotting the raw V̇_k makes δ_C dominate by 5+ orders of magnitude and
    hides the other three channels — so we normalise to fractional share,
    which makes channel rotation around the crisis visible.
    """
    t = diag["t_arr"]
    vC = diag["v_C"]; vG = diag["v_G"]; vA = diag["v_A"]; vT = diag["v_T"]
    labels = diag["labels"]
    t_crisis = diag["t_crisis"]

    raw = np.stack([np.abs(vC), np.abs(vG), np.abs(vA), np.abs(vT)])
    total = raw.sum(axis=0)
    total = np.where(total > 0, total, 1.0)
    frac = raw / total                                              # (4, T)

    fig, (ax_top, ax_bot) = plt.subplots(2, 1, figsize=(9.0, 6.6),
                                          sharex=True,
                                          gridspec_kw=dict(height_ratios=[2, 1]))
    ax_top.stackplot(t, frac,
                     labels=["δ_C  Mahalanobis", "δ_G  feature gap",
                             "δ_A  activity", "δ_T  novelty"],
                     colors=[CHAN_COLORS["C"], CHAN_COLORS["G"],
                             CHAN_COLORS["A"], CHAN_COLORS["T"]],
                     alpha=0.85, edgecolor="white", linewidth=0.4)
    ax_top.axvline(t_crisis, color=CRISIS_COLOR, lw=1.2, ls="--",
                   label=f"crisis ({diag['labels'][t_crisis]})")
    ax_top.set_ylim(0, 1)
    ax_top.set_ylabel("fractional share |V̇_k| / Σ|V̇_j|")
    ax_top.set_title(f"{diag['name']} — per-channel decomposition of V̇")
    ax_top.legend(loc="upper left", ncol=2)

    # Companion panel: total |V̇| magnitude (symlog), so the absolute scale
    # is also visible — fractional share alone hides intensity.
    ax_bot.plot(t, total, color="#34495e", lw=1.4, label="Σ|V̇_k|")
    ax_bot.axvline(t_crisis, color=CRISIS_COLOR, lw=1.0, ls="--")
    ax_bot.set_yscale("log")
    ax_bot.set_ylabel("Σ|V̇_k|")
    ax_bot.set_xlabel("period")
    idx, lab = _xtick_subset(labels, n=8)
    ax_bot.set_xticks(idx); ax_bot.set_xticklabels(lab, rotation=20, ha="right")
    ax_bot.set_xlim(t[0], t[-1])
    ax_bot.legend(loc="upper left")
    fig.savefig(out_dir / "fig5_channel_stack.png")
    plt.close(fig)


def fig_two_layer_ews(diag, out_dir):
    """Layer A precursor + Layer B geometry, with crisis & first-alarm markers."""
    t = diag["t_arr"]; pre = diag["pre"]; ews = diag["ews"]
    aA = diag["alarm_A"]; aB = diag["alarm_B"]
    labels = diag["labels"]
    t_crisis = diag["t_crisis"]
    thr_dyn = diag["ews_thresh_dyn"]

    fig, axes = plt.subplots(2, 1, figsize=(9.0, 6.4), sharex=True)

    # Layer A
    axes[0].plot(t, pre, color="#e67e22", lw=1.6, label="precursor score (Layer A)")
    axes[0].axhline(1.0, color="k", ls=":", lw=0.9, label="Layer A threshold = 1.0")
    axes[0].fill_between(t, 0, np.maximum(pre, 0), where=aA,
                         color=ALARM_COLOR, alpha=0.18, step="mid",
                         label="Layer A fires")
    axes[0].axvline(t_crisis, color=CRISIS_COLOR, ls="--", lw=1.0)
    axes[0].set_ylabel("precursor / scale")
    axes[0].set_title(f"{diag['name']} — two-layer Early Warning System")
    if pre.max() > 50:
        axes[0].set_yscale("log")
    axes[0].legend(loc="upper left")

    # Layer B
    axes[1].plot(t, ews, color="#2c3e50", lw=1.6, label="geometry score (Layer B)")
    axes[1].axhline(thr_dyn, color="k", ls=":", lw=0.9,
                    label=f"Layer B dyn. threshold = {thr_dyn:.4f}")
    axes[1].fill_between(t, ews.min() if len(ews) else 0, ews,
                         where=aB, color=CRISIS_COLOR, alpha=0.18,
                         step="mid", label="Layer B fires")
    axes[1].axvline(t_crisis, color=CRISIS_COLOR, ls="--", lw=1.0,
                    label=f"crisis ({diag['labels'][t_crisis]})")

    # First pre-crisis alarm marker — robust to edge cases:
    #   (a) skip a 5-snapshot warm-up at the start of the eval window
    #       (degenerate history / scale calibration boundary effects)
    #   (b) require K=2 of the next 3 snapshots to also alarm — kills
    #       single-snapshot blips at the calibration boundary.
    WARMUP = 5
    K_REQ, K_WIN = 2, 3
    eval_mask = (t >= diag["t_eval"]) & (t < t_crisis)
    fired = (aA | aB).astype(int)
    confirmed = np.zeros_like(fired, dtype=bool)
    for i in range(len(fired) - K_WIN + 1):
        confirmed[i] = fired[i:i + K_WIN].sum() >= K_REQ
    # apply warm-up: skip first WARMUP eval indices
    eval_idx = np.flatnonzero(eval_mask)
    if eval_idx.size > WARMUP:
        warm_cutoff = eval_idx[WARMUP]
        candidate = eval_mask & confirmed & (np.arange(len(t)) >= warm_cutoff)
    else:
        candidate = eval_mask & confirmed
    if candidate.any():
        first_idx = int(np.flatnonzero(candidate)[0])
        for ax in axes:
            ax.axvline(t[first_idx], color=ALARM_COLOR, lw=1.4, alpha=0.85)
        axes[0].annotate(f"first alarm: {labels[t[first_idx]]}\n"
                         f"lead = {t_crisis - t[first_idx]} periods",
                         xy=(t[first_idx], pre.max() * 0.8),
                         xytext=(15, 0), textcoords="offset points",
                         color=ALARM_COLOR, fontsize=9,
                         arrowprops=dict(arrowstyle="->",
                                         color=ALARM_COLOR, lw=0.8))

    axes[1].set_xlabel("period"); axes[1].set_ylabel("geometric mean ξ")
    idx, lab = _xtick_subset(labels, n=8)
    axes[1].set_xticks(idx); axes[1].set_xticklabels(lab, rotation=20, ha="right")
    axes[1].set_xlim(t[0], t[-1])
    axes[1].legend(loc="lower left")
    fig.savefig(out_dir / "fig6_two_layer_ews.png")
    plt.close(fig)


def fig_alignment(diag, out_dir):
    """Three-panel alignment figure:
      Panel 1 — log₁₀ ρ_MFLS (over-amplification; ψ ≡ 0 whenever ρ ≥ 1)
      Panel 2 — cos θ_state (state-space alignment, typically −0.2 … −0.5)
      Panel 3 — cos θ_channel (channel-space alignment → −1 at collapse)

    The contrast between panels 2 and 3 is the key result: collapse is a
    low-dimensional manifold phenomenon — near-perfect alignment in the
    4D channel space while remaining diffuse in the full state space.
    """
    t = diag["t_arr"]; rho = diag["rho"]
    cosS = diag["cosS"]; cosC = diag["cosC"]
    labels = diag["labels"]; t_crisis = diag["t_crisis"]
    log_rho = np.log10(np.maximum(rho, 1e-12))

    fig, axes = plt.subplots(3, 1, figsize=(9.0, 8.5), sharex=True,
                             gridspec_kw=dict(hspace=0.12))

    # ── Panel 1: log₁₀ ρ_MFLS ──────────────────────────────────────────
    axes[0].plot(t, log_rho, color="#9b59b6", lw=1.5, label="log₁₀ ρ_MFLS")
    axes[0].axhline(0, color="k", lw=0.7, ls="-",
                    label="ρ = 1  (perfect transmission)")
    axes[0].axvline(t_crisis, color=CRISIS_COLOR, ls="--", lw=1.0)
    axes[0].fill_between(t, 0, log_rho, where=log_rho > 0,
                         color=CRISIS_COLOR, alpha=0.12,
                         label="ρ > 1  over-amplification")
    axes[0].set_ylabel("log₁₀ ρ_MFLS")
    axes[0].set_title(f"{diag['name']} — MFLS amplification & alignment signals")
    axes[0].legend(loc="upper left", ncol=3)

    # ── Panel 2: cos θ_state ───────────────────────────────────────────
    axes[1].plot(t, cosS, color="#16a085", lw=1.5, label="cos θ_state")
    axes[1].axhline(0, color="k", lw=0.5, ls="-")
    axes[1].fill_between(t, 0, cosS, where=cosS < 0, color="#2ecc71",
                         alpha=0.15, label="self-stabilising (cosS < 0)")
    axes[1].axvline(t_crisis, color=CRISIS_COLOR, ls="--", lw=1.0)
    axes[1].set_ylabel("cos θ_state")
    axes[1].set_ylim(-1.05, 0.15)
    axes[1].legend(loc="upper left")

    # ── Panel 3: cos θ_channel ─────────────────────────────────────────
    axes[2].plot(t, cosC, color="#e74c3c", lw=1.8, label="cos θ_channel")
    axes[2].axhline(-1.0, color="k", lw=0.8, ls=":",
                    label="perfect locking (cos_θ_channel = −1)")
    axes[2].axhline(0, color="k", lw=0.4, alpha=0.3)
    axes[2].fill_between(t, -1.0, cosC, where=cosC < -0.9,
                         color=CRISIS_COLOR, alpha=0.20,
                         label="|cos_θC| > 0.9  coherent collapse")
    axes[2].axvline(t_crisis, color=CRISIS_COLOR, ls="--", lw=1.0,
                    label=f"crisis ({labels[t_crisis]})")
    axes[2].set_ylabel("cos θ_channel")
    axes[2].set_ylim(-1.05, 0.15)
    axes[2].set_xlabel("period")
    axes[2].legend(loc="upper left", ncol=2)

    idx, lab = _xtick_subset(labels, n=8)
    axes[2].set_xticks(idx); axes[2].set_xticklabels(lab, rotation=20, ha="right")
    axes[2].set_xlim(t[0], t[-1])
    fig.savefig(out_dir / "fig7_alignment.png")
    plt.close(fig)


def fig_energy_trajectory(diag, out_dir):
    t = diag["t_arr"]; e = diag["e_arr"]; e_star = diag["e_star"]
    labels = diag["labels"]; t_crisis = diag["t_crisis"]
    fig, ax = plt.subplots(figsize=(9.0, 4.5))
    ax.plot(t, e, color="#2c3e50", lw=1.6, label="e_BSDT(t)")
    ax.axhline(e_star, color=CRISIS_COLOR, ls="--", lw=1.2,
               label=f"e* (χ², 99%) = {e_star:.1f}")
    ax.axvline(t_crisis, color=CRISIS_COLOR, ls="--", lw=1.0,
               label=f"crisis ({labels[t_crisis]})")
    ax.fill_between(t, e_star, e, where=e > e_star, color=CRISIS_COLOR,
                    alpha=0.15, label="above threshold")
    ax.set_yscale("log") if (e.max() / max(e_star, 1e-9)) > 30 else None
    ax.set_xlabel("period"); ax.set_ylabel("e_BSDT  (Mahalanobis energy)")
    ax.set_title(f"{diag['name']} — energy trajectory vs χ² boundary")
    idx, lab = _xtick_subset(labels, n=8)
    ax.set_xticks(idx); ax.set_xticklabels(lab, rotation=20, ha="right")
    ax.set_xlim(t[0], t[-1])
    ax.legend(loc="best")
    fig.savefig(out_dir / "fig8_energy_trajectory.png")
    plt.close(fig)


# ═════════════════════════════════════════════════════════════
# Cross-domain summary
# ═════════════════════════════════════════════════════════════

def fig_cross_domain_summary(diags, out_path):
    fig, axes = plt.subplots(2, 2, figsize=(12.5, 8.5))
    for ax, diag in zip(axes.ravel(), diags):
        t = diag["t_arr"]; e = diag["e_arr"]
        e_star = diag["e_star"]; t_crisis = diag["t_crisis"]
        ax.plot(t, e, color=TRAJ_COLOR, lw=1.4, label="e_BSDT")
        ax.axhline(e_star, color=CRISIS_COLOR, ls="--", lw=1.0,
                   label=f"e* = {e_star:.1f}")
        ax.axvline(t_crisis, color=CRISIS_COLOR, ls="--", lw=0.9,
                   label="crisis")
        ax.fill_between(t, e_star, e, where=e > e_star,
                        color=CRISIS_COLOR, alpha=0.15)
        if (e.max() / max(e_star, 1e-9)) > 30:
            ax.set_yscale("log")
        ax.set_title(diag["name"])
        ax.legend(loc="upper left", fontsize=8)
        idx, lab = _xtick_subset(diag["labels"], n=5)
        ax.set_xticks(idx); ax.set_xticklabels(lab, rotation=15, ha="right",
                                              fontsize=8)
        ax.set_xlim(t[0], t[-1])
    fig.suptitle("Cross-domain consistency — energy trajectory vs χ² boundary",
                 fontsize=12)
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)


# ─────────────────────────────────────────────────────────────
# NEW: crisis-aligned cos_θ_channel overlay
# ─────────────────────────────────────────────────────────────

_DS_COLORS  = {"FDIC": "#2980b9", "GSIB": "#8e44ad",
               "ERCOT": "#27ae60", "TerraLuna": "#c0392b"}
_DS_MARKERS = {"FDIC": "o", "GSIB": "s", "ERCOT": "^", "TerraLuna": "D"}
_DS_UNITS   = {"FDIC": "qtr", "GSIB": "yr", "ERCOT": "wk", "TerraLuna": "hr"}
_WINDOW     = (-20, 30)   # periods relative to crisis shown in aligned plots


def _crisis_aligned_cosC(ax, diags):
    """Plot cos_θ_channel(t − t_crisis) for all datasets on *ax*."""
    ax.axvspan(_WINDOW[0], 0, color="#ecf0f1", alpha=0.40, zorder=0)
    ax.axvspan(0, _WINDOW[1], color="#fadbd8", alpha=0.22, zorder=0)
    ax.axvline(0, color=CRISIS_COLOR, lw=1.5, ls="--", alpha=0.85,
               zorder=5, label="crisis onset (t = 0)")
    ax.axhline(-1.0, color="k", lw=0.8, ls=":", alpha=0.65,
               label="perfect locking (cos θ_C = −1)")
    ax.axhline(0.0, color="k", lw=0.3, alpha=0.25)

    for diag in diags:
        name = diag["name"]
        t    = diag["t_arr"]
        cosC = diag["cosC"]
        t_c  = diag["t_crisis"]
        rel  = t - t_c
        mask = (rel >= _WINDOW[0]) & (rel <= _WINDOW[1])
        if not mask.any():
            continue
        crisis_idx = np.flatnonzero(t == t_c)
        crisis_str = (f"{cosC[crisis_idx[0]]:.3f}"
                      if crisis_idx.size else "N/A")
        ax.plot(rel[mask], cosC[mask], "-",
                color=_DS_COLORS.get(name, "gray"), lw=2.0,
                marker=_DS_MARKERS.get(name, "o"), markersize=4.5, markevery=3,
                alpha=0.90,
                label=f"{name}  [onset: {crisis_str}]  ({_DS_UNITS.get(name, 'p')})")
        if crisis_idx.size:
            ax.scatter([0], [cosC[crisis_idx[0]]], s=130,
                       color=_DS_COLORS.get(name, "gray"),
                       marker="*", edgecolors="black", linewidths=0.6, zorder=10)

    ax.set_xlim(_WINDOW[0], _WINDOW[1])
    ax.set_ylim(-1.07, 0.18)
    ax.set_xlabel("periods relative to crisis onset  (0 = crisis)")
    ax.set_ylabel("cos θ_channel")


def fig_costheta_channel_aligned(diags, out_path):
    """Standalone: crisis-aligned cos_θ_channel for all four datasets.

    This is the *universal collapse invariant* figure: across banking,
    global banks, power-grid, and crypto, channel-space alignment locks
    to −1 at every crisis onset (★ markers), while remaining above −0.9
    during normal/recovery phases.
    """
    fig, ax = plt.subplots(figsize=(9.5, 5.5))
    _crisis_aligned_cosC(ax, diags)
    ax.set_title(
        "Universal collapse signature: channel-space alignment locking\n"
        "across four heterogeneous systems  (★ = crisis onset)",
        fontsize=11)
    ax.legend(loc="upper left", ncol=1, fontsize=9)
    # annotation: pre-crisis shading label
    ax.text(_WINDOW[0] + 0.5, 0.10, "pre-crisis", color="#7f8c8d",
            fontsize=8.5, va="top")
    ax.text(0.5, 0.10, "crisis / post-crisis", color="#c0392b",
            fontsize=8.5, va="top", alpha=0.75)
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)


def fig_cross_domain_combined(diags, out_path):
    """Combined publication figure:
      Rows 1–2  (2×2)  — energy trajectories per dataset (existing summary)
      Row  3    (1×1)  — crisis-aligned cos_θ_channel overlay (new result)

    The combination puts the *detection* evidence (energy above e*) and the
    *mechanism* evidence (channel locking → −1) side-by-side in one figure.
    """
    import matplotlib.gridspec as gridspec

    fig = plt.figure(figsize=(14.0, 11.5))
    gs = gridspec.GridSpec(3, 2, figure=fig,
                           hspace=0.50, wspace=0.32,
                           height_ratios=[1, 1, 1.15])

    # ── Rows 0–1: energy per dataset ────────────────────────────────────
    for idx, diag in enumerate(diags):
        row, col = divmod(idx, 2)
        ax = fig.add_subplot(gs[row, col])
        t = diag["t_arr"]; e = diag["e_arr"]
        e_star = diag["e_star"]; t_c = diag["t_crisis"]
        ax.plot(t, e, color=TRAJ_COLOR, lw=1.4, label="e_BSDT")
        ax.axhline(e_star, color=CRISIS_COLOR, ls="--", lw=1.0,
                   label=f"e* = {e_star:.1f}")
        ax.axvline(t_c, color=CRISIS_COLOR, ls="--", lw=0.85)
        ax.fill_between(t, e_star, e, where=e > e_star,
                        color=CRISIS_COLOR, alpha=0.15)
        if (e.max() / max(e_star, 1e-9)) > 30:
            ax.set_yscale("log")
        ax.set_title(diag["name"], fontsize=10)
        ax.legend(loc="upper left", fontsize=7.5)
        _it, _lt = _xtick_subset(diag["labels"], n=5)
        ax.set_xticks(_it)
        ax.set_xticklabels(_lt, rotation=15, ha="right", fontsize=7.5)
        ax.set_xlim(t[0], t[-1])
        if col == 0:
            ax.set_ylabel("e_BSDT", fontsize=8.5)

    # ── Row 2: crisis-aligned cos_θ_channel ─────────────────────────────
    ax_bot = fig.add_subplot(gs[2, :])
    _crisis_aligned_cosC(ax_bot, diags)
    ax_bot.set_title(
        "Universal collapse invariant — channel-space alignment locking  "
        "(★ = crisis onset, ★ color = dataset)",
        fontsize=10.5)
    ax_bot.legend(loc="lower left", ncol=2, fontsize=8.5)
    ax_bot.text(_WINDOW[0] + 0.3, 0.12, "pre-crisis", color="#7f8c8d",
                fontsize=8, va="top")
    ax_bot.text(0.4, 0.12, "crisis / post-crisis", color="#c0392b",
                fontsize=8, va="top", alpha=0.75)

    fig.suptitle(
        "Cross-domain consistency: Mahalanobis energy + channel-space alignment",
        fontsize=12, y=1.002)
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)


# ═════════════════════════════════════════════════════════════
# Main
# ═════════════════════════════════════════════════════════════

def main():
    out_root = ROOT / "research" / "adaptive-friction" / "figures"
    out_root.mkdir(parents=True, exist_ok=True)

    datasets = [
        ("FDIC",      load_fdic_panel,       12),
        ("GSIB",      load_gsib_panel,        5),
        ("ERCOT",     load_ercot_panel,       8),
        ("TerraLuna", load_terra_luna_panel,  8),
    ]

    diags = []
    for name, loader, hist in datasets:
        print(f"\n[{name}] loading + collecting diagnostics…")
        try:
            panel, labels, t_cut, t_eval, t_crisis = loader()
            diag = collect_diagnostics(name, panel, labels,
                                       t_cut, t_eval, t_crisis, hist)
        except Exception as e:
            print(f"  !! {name} failed: {type(e).__name__}: {e}")
            import traceback; traceback.print_exc()
            continue
        diags.append(diag)

        sub = out_root / name
        sub.mkdir(parents=True, exist_ok=True)
        print(f"  → writing figures to {sub}")
        for fn in (fig_trajectory_2d, fig_trajectory_3d, fig_energy_landscape,
                   fig_pq_regimes, fig_channel_stack, fig_two_layer_ews,
                   fig_alignment, fig_energy_trajectory):
            try:
                fn(diag, sub)
            except Exception as e:
                print(f"     ! {fn.__name__} failed: {type(e).__name__}: {e}")

    if diags:
        fig_cross_domain_summary(diags, out_root / "cross_domain_summary.png")
        print(f"\n[cross-domain] → {out_root / 'cross_domain_summary.png'}")

        fig_costheta_channel_aligned(
            diags, out_root / "cross_domain_costheta_aligned.png")
        print(f"[cross-domain] → {out_root / 'cross_domain_costheta_aligned.png'}")

        fig_cross_domain_combined(
            diags, out_root / "cross_domain_combined.png")
        print(f"[cross-domain] → {out_root / 'cross_domain_combined.png'}")

    print(f"\nDone. Figures in: {out_root}")


if __name__ == "__main__":
    main()
