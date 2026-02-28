"""
generate_figures.py - Generate all figures for main.tex
========================================================
Produces publication-quality PDF/PNG figures for the paper.
Uses data from the upgraded pipeline (real FDIC) and variant comparison.
"""

from __future__ import annotations
import sys, json
import numpy as np
import pandas as pd
from pathlib import Path

# Add upgraded pipeline to path
PAPER_DIR = Path(__file__).resolve().parent
REPO_ROOT = PAPER_DIR.parent.parent  # c:\amttp
UPGRADED = REPO_ROOT / "adaptive-friction-stability-upgraded" / "pipeline"
VARIANT  = REPO_ROOT / "adaptive-friction-stability-variants" / "pipeline"
sys.path.insert(0, str(UPGRADED))
sys.path.insert(0, str(VARIANT))

from fred_loader     import fetch_all
from fdic_loader     import fetch_fdic_specgrp
from state_matrix    import build_state_matrix_fdic, standardise_panel, get_normal_period
from network_builder import lw_correlation_network
from gravity_engine  import BSDTOperator, analyse_trajectory, ALPHA
from bsdt_operators  import BSDTOperators
from mfls_variants   import MFLSBaseline, MFLSFullBSDT, MFLSQuadSurf, MFLSSignedLR, MFLSExpoGate, make_crisis_labels

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import FancyBboxPatch
from matplotlib.gridspec import GridSpec

plt.rcParams.update({
    "font.family": "serif",
    "font.size": 9,
    "axes.labelsize": 10,
    "axes.titlesize": 11,
    "legend.fontsize": 8,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "text.usetex": False,
})

FIGDIR = Path(__file__).parent / "figures"
FIGDIR.mkdir(exist_ok=True)

CRISIS_WINDOWS = {
    "GFC 2008":       ("2007-01-01", "2009-12-31", "2008-09-15"),
    "COVID 2020":     ("2019-10-01", "2021-06-30", "2020-03-23"),
    "Rate Shock 2022":("2022-01-01", "2023-06-30", "2022-10-01"),
}
CRISIS_COLORS = {"GFC 2008": "#e74c3c", "COVID 2020": "#3498db", "Rate Shock 2022": "#f39c12"}


def _reindex(series, dates, fill=0.0):
    if series is None or (isinstance(series, pd.Series) and series.empty):
        return np.full(len(dates), fill)
    s = series.copy()
    s.index = pd.to_datetime(s.index)
    return s.reindex(dates, method="ffill").fillna(fill).values


def _norm01(x):
    mn, mx = x.min(), x.max()
    return (x - mn) / (mx - mn + 1e-12)


def load_all_data():
    """Load all data needed for figures."""
    print("[data] Loading...")
    raw_fred = fetch_all(use_cache=True, verbose=False)
    slope_col = "slope_10y2y" if "slope_10y2y" in raw_fred.columns else raw_fred.columns[0]
    fdic_df = fetch_fdic_specgrp(use_cache=True, verbose=False)
    X_all, dates, sectors = build_state_matrix_fdic(fdic_df, raw_fred[slope_col])
    X_normal, dates_normal = get_normal_period(X_all, dates)
    X_std, mu_ref, sigma_ref = standardise_panel(X_all, X_ref=X_normal)
    X_norm_std, _, _ = standardise_panel(X_normal, X_ref=X_normal)
    mu = X_norm_std.reshape(-1, X_norm_std.shape[-1]).mean(axis=0)

    # Gravity engine trajectory
    bsdt = BSDTOperator().fit(X_norm_std)
    stats = analyse_trajectory(X_std, mu, bsdt, verbose=False)

    # Benchmarks
    stlfsi = _reindex(raw_fred.get("stlfsi"), dates)
    vix    = _reindex(raw_fred.get("vix"), dates)
    nfci   = _reindex(raw_fred.get("nfci"), dates)

    # BSDT channels (variant pipeline)
    ops = BSDTOperators(n_components=4, velocity_pctl=95.0)
    ops.fit(X_norm_std)
    channels = ops.compute_channels(X_std)
    ch = channels["channels"]

    # Crisis labels
    y_labels = make_crisis_labels(dates)

    # Train mask
    train_mask = dates <= "2006-12-31"

    return {
        "dates": dates, "X_std": X_std, "X_norm_std": X_norm_std,
        "sectors": sectors, "stats": stats, "bsdt": bsdt,
        "stlfsi": stlfsi, "vix": vix, "nfci": nfci,
        "channels": ch, "y_labels": y_labels, "train_mask": train_mask,
        "raw_fred": raw_fred, "mu": mu,
    }


def fig1_mfls_crisis(data):
    """Figure 1: MFLS signal with crisis windows and benchmark stress indices."""
    print("[fig1] MFLS signal + crisis windows...")
    dates = data["dates"]
    mfls  = data["stats"]["mfls"]
    stlfsi = data["stlfsi"]
    vix    = data["vix"]

    fig, axes = plt.subplots(2, 1, figsize=(7.5, 5), sharex=True,
                              gridspec_kw={"height_ratios": [3, 1.5]})

    # Panel A: MFLS
    ax = axes[0]
    ax.plot(dates, mfls, color="#1a1a2e", lw=1.5, label="MFLS score", zorder=3)

    # OOS threshold
    p75 = np.percentile(mfls[data["train_mask"]], 75)
    ax.axhline(p75, color="#888", ls="--", lw=0.8, alpha=0.7, label=f"P75 threshold (train)")

    # OOS alarm
    test_mask = ~data["train_mask"]
    above = mfls[test_mask] > p75
    if above.any():
        alarm_idx = np.argmax(above)
        alarm_dt = dates[test_mask][alarm_idx]
        ax.axvline(alarm_dt, color="#e74c3c", ls="-", lw=1.2, alpha=0.8,
                   label=f"OOS alarm: {alarm_dt.year}-Q{(alarm_dt.month-1)//3+1}")
        alarm_label = f"{alarm_dt.year}-Q{(alarm_dt.month-1)//3+1}"
        ax.annotate(f"Alarm\n{alarm_label}", xy=(alarm_dt, mfls[test_mask][alarm_idx]),
                    xytext=(15, 10), textcoords="offset points", fontsize=7,
                    arrowprops=dict(arrowstyle="->", color="#e74c3c"), color="#e74c3c")

    for cname, (cs, ce, cp) in CRISIS_WINDOWS.items():
        ax.axvspan(pd.Timestamp(cs), pd.Timestamp(ce), alpha=0.12,
                   color=CRISIS_COLORS[cname], label=cname)
    ax.axvline(pd.Timestamp("2006-12-31"), color="gray", ls=":", lw=0.8)
    ax.text(pd.Timestamp("2005-01-01"), mfls.max() * 0.92, "Train", fontsize=7, color="gray")
    ax.text(pd.Timestamp("2008-01-01"), mfls.max() * 0.92, "Test (OOS)", fontsize=7, color="gray")

    ax.set_ylabel(r"MFLS $\|\nabla E_{BS}\|_F$")
    ax.set_title("(a) MFLS Detection Signal with OOS Alarm")
    ax.legend(fontsize=7, ncol=2, loc="upper left")
    ax.grid(alpha=0.2)

    # Panel B: Benchmark indices
    ax = axes[1]
    ax.plot(dates, _norm01(stlfsi), color="#3498db", lw=1, label="STLFSI", alpha=0.8)
    ax.plot(dates, _norm01(vix), color="#e67e22", lw=1, label="VIX", alpha=0.8)
    ax.plot(dates, _norm01(data["nfci"]), color="#2ecc71", lw=1, label="NFCI", alpha=0.8)
    for cname, (cs, ce, cp) in CRISIS_WINDOWS.items():
        ax.axvspan(pd.Timestamp(cs), pd.Timestamp(ce), alpha=0.12, color=CRISIS_COLORS[cname])
    ax.set_ylabel("Normalised index")
    ax.set_title("(b) Benchmark Stress Indices (normalised)")
    ax.legend(fontsize=7, ncol=3, loc="upper left")
    ax.grid(alpha=0.2)
    ax.set_xlabel("Date")

    plt.tight_layout()
    fig.savefig(FIGDIR / "fig1_mfls_crisis.pdf")
    fig.savefig(FIGDIR / "fig1_mfls_crisis.png")
    plt.close()


def fig2_energy_spectral(data):
    """Figure 2: Energy, spectral radius, and gamma* trajectories."""
    print("[fig2] Energy + spectral radius + gamma*...")
    dates = data["dates"]
    s = data["stats"]

    fig, axes = plt.subplots(3, 1, figsize=(7.5, 6.5), sharex=True)

    # Panel A: Total energy
    ax = axes[0]
    ax.plot(dates, s["energy"], color="#1a1a2e", lw=1.2)
    for cname, (cs, ce, cp) in CRISIS_WINDOWS.items():
        ax.axvspan(pd.Timestamp(cs), pd.Timestamp(ce), alpha=0.12, color=CRISIS_COLORS[cname])
    ax.set_ylabel(r"$\Phi(X_t)$")
    ax.set_title(r"(a) Total Potential Energy $\Phi(X_t)$")
    ax.grid(alpha=0.2)

    # Panel B: Spectral radius
    ax = axes[1]
    ax.plot(dates, s["lambda_max"], color="#8e44ad", lw=1.2, label=r"$\lambda_{\max}(D^2\Phi_{pair})$")
    ax.axhline(ALPHA, color="#e74c3c", ls="--", lw=1, label=rf"$\alpha = {ALPHA}$")
    above = s["lambda_max"] > ALPHA
    frac = above.mean()
    ax.fill_between(dates, 0, s["lambda_max"], where=above, alpha=0.15, color="#e74c3c")
    for cname, (cs, ce, cp) in CRISIS_WINDOWS.items():
        ax.axvspan(pd.Timestamp(cs), pd.Timestamp(ce), alpha=0.12, color=CRISIS_COLORS[cname])
    ax.set_ylabel(r"$\lambda_{\max}$")
    ax.set_title(f"(b) Spectral Radius - {frac:.0%} of quarters above critical threshold")
    ax.legend(fontsize=7, loc="upper right")
    ax.grid(alpha=0.2)

    # Panel C: cos theta alignment
    ax = axes[2]
    ax.plot(dates, s["cos_theta"], color="#16a085", lw=1.2)
    ax.axhline(0.0, color="gray", ls="-", lw=0.5)
    ax.axhline(0.7, color="#27ae60", ls="--", lw=0.8, alpha=0.5, label=r"$\cos\theta = 0.7$")
    for cname, (cs, ce, cp) in CRISIS_WINDOWS.items():
        ax.axvspan(pd.Timestamp(cs), pd.Timestamp(ce), alpha=0.12, color=CRISIS_COLORS[cname])
    mean_ct = s["cos_theta"].mean()
    ax.axhline(mean_ct, color="#e74c3c", ls=":", lw=0.8, label=f"mean = {mean_ct:.3f}")
    ax.set_ylabel(r"$\cos\theta$")
    ax.set_title(rf"(c) Gradient Alignment - mean $\cos\theta = {mean_ct:.3f}$")
    ax.legend(fontsize=7, loc="upper right")
    ax.grid(alpha=0.2)
    ax.set_xlabel("Date")
    ax.set_ylim(-0.8, 0.8)

    plt.tight_layout()
    fig.savefig(FIGDIR / "fig2_energy_spectral.pdf")
    fig.savefig(FIGDIR / "fig2_energy_spectral.png")
    plt.close()


def fig3_bsdt_channels(data):
    """Figure 3: BSDT operator channels over time."""
    print("[fig3] BSDT channels...")
    dates = data["dates"]
    ch = data["channels"]
    ch_names = [r"$\delta_C$ (Camouflage)", r"$\delta_G$ (Feature Gap)",
                r"$\delta_A$ (Activity)", r"$\delta_T$ (Temporal)"]
    ch_colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"]

    fig, axes = plt.subplots(4, 1, figsize=(7.5, 7), sharex=True)

    for k in range(4):
        ax = axes[k]
        col = ch[:, k]
        ax.plot(dates, col, color=ch_colors[k], lw=1.2)
        ax.fill_between(dates, 0, col, alpha=0.15, color=ch_colors[k])
        for cname, (cs, ce, cp) in CRISIS_WINDOWS.items():
            ax.axvspan(pd.Timestamp(cs), pd.Timestamp(ce), alpha=0.12, color=CRISIS_COLORS[cname])
        ax.set_ylabel(ch_names[k], fontsize=9)
        if k == 0:
            ax.set_title("BSDT Operator Channels on Real FDIC Data")
        ax.grid(alpha=0.2)

    axes[-1].set_xlabel("Date")
    plt.tight_layout()
    fig.savefig(FIGDIR / "fig3_bsdt_channels.pdf")
    fig.savefig(FIGDIR / "fig3_bsdt_channels.png")
    plt.close()


def fig4_variant_comparison(data):
    """Figure 4: MFLS variant signals comparison."""
    print("[fig4] Variant comparison...")
    dates = data["dates"]
    ch = data["channels"]
    y = data["y_labels"]
    train_mask = data["train_mask"]

    # Fit all variants
    X_norm_std = data["X_norm_std"]
    X_std = data["X_std"]

    v1 = MFLSBaseline()
    v1.fit(X_norm_std)
    sig1 = v1.score_series(X_std)

    v2 = MFLSFullBSDT()
    v2.fit(ch[train_mask])
    sig2 = v2.score(ch)

    v3 = MFLSQuadSurf(ridge_alpha=1.0)
    v3.fit(ch[train_mask], y[train_mask])
    sig3 = v3.score(ch)

    v4 = MFLSSignedLR(lr=0.1, n_iter=1000, reg=0.01)
    v4.fit(ch[train_mask], y[train_mask])
    sig4 = v4.score(ch)

    v5 = MFLSExpoGate(ridge_alpha=1.0, smooth_sigma=1.0, gate_scale=3.0)
    v5.fit(ch[train_mask], y[train_mask])
    sig5 = v5.score(ch)

    variants = [
        ("Baseline (Mahalanobis)", sig1, "#1a1a2e"),
        ("Full BSDT (4-ch uniform)", sig2, "#e67e22"),
        ("QuadSurf (poly ridge)", sig3, "#2ecc71"),
        ("Signed LR (logistic)", sig4, "#3498db"),
        ("Expo Gate (quad+tanh)", sig5, "#9b59b6"),
    ]

    fig, axes = plt.subplots(len(variants), 1, figsize=(7.5, 8), sharex=True)

    for i, (name, sig, color) in enumerate(variants):
        ax = axes[i]
        sig_n = _norm01(sig)
        ax.plot(dates, sig_n, color=color, lw=1.2)
        ax.fill_between(dates, 0, sig_n, alpha=0.12, color=color)
        for cname, (cs, ce, cp) in CRISIS_WINDOWS.items():
            ax.axvspan(pd.Timestamp(cs), pd.Timestamp(ce), alpha=0.10, color=CRISIS_COLORS[cname])
        ax.axvline(pd.Timestamp("2006-12-31"), color="gray", ls=":", lw=0.7)
        ax.set_ylabel(name, fontsize=8)
        ax.set_ylim(-0.05, 1.15)
        ax.grid(alpha=0.2)
        if i == 0:
            ax.set_title("MFLS Variant Signals (normalised to [0,1])")

    axes[-1].set_xlabel("Date")
    plt.tight_layout()
    fig.savefig(FIGDIR / "fig4_variant_comparison.pdf")
    fig.savefig(FIGDIR / "fig4_variant_comparison.png")
    plt.close()

    return v4  # return Signed LR for weight plot


def fig5_signed_lr_weights(v4):
    """Figure 5: Signed LR learned channel weights."""
    print("[fig5] Signed LR weights...")
    beta = v4.beta_
    labels = [r"$\beta_0$ (bias)", r"$\beta_{\delta_C}$"+"\n(Camouflage)",
              r"$\beta_{\delta_G}$"+"\n(Feature Gap)", r"$\beta_{\delta_A}$"+"\n(Activity)",
              r"$\beta_{\delta_T}$"+"\n(Temporal)"]
    colors = ["#95a5a6", "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"]

    fig, ax = plt.subplots(figsize=(5, 3.5))
    bars = ax.bar(range(len(beta)), beta, color=colors, edgecolor="white", lw=0.5, width=0.6)
    ax.axhline(0, color="black", lw=0.5)
    ax.set_xticks(range(len(beta)))
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("Learned weight")
    ax.set_title("Signed LR: Learned BSDT Channel Weights (trained 1990-2006)")

    # Annotate values
    for i, (b, bar_) in enumerate(zip(beta, bars)):
        va = "bottom" if b >= 0 else "top"
        offset = 0.05 if b >= 0 else -0.05
        ax.text(i, b + offset, f"{b:+.2f}", ha="center", va=va, fontsize=8, fontweight="bold")

    ax.grid(axis="y", alpha=0.2)
    plt.tight_layout()
    fig.savefig(FIGDIR / "fig5_signed_lr_weights.pdf")
    fig.savefig(FIGDIR / "fig5_signed_lr_weights.png")
    plt.close()


def fig6_selectivity(data):
    """Figure 6: Precision-recall frontier across variants."""
    print("[fig6] Selectivity comparison...")
    # Load variant results
    with open(VARIANT / "results" / "variant_comparison.json") as f:
        vc = json.load(f)

    names = []
    hit_rates = []
    selectivities = []
    for vname, vdata in vc["variants"].items():
        names.append(vdata["name"].split("(")[0].strip())
        hit_rates.append(vdata["oos_backtest"]["hit_rate"])
        selectivities.append(vdata["selectivity"]["ratio"])

    fig, ax = plt.subplots(figsize=(5.5, 4))
    colors = ["#1a1a2e", "#e67e22", "#2ecc71", "#3498db", "#9b59b6"]
    for i, (n, hr, sel) in enumerate(zip(names, hit_rates, selectivities)):
        ax.scatter(hr, sel, s=120, color=colors[i], zorder=3, edgecolor="white", lw=1)
        offset_x = 0.03 if i != 2 else -0.06
        offset_y = 0.15 if i < 3 else -0.25
        ax.annotate(n, (hr, sel), xytext=(offset_x, offset_y),
                    textcoords="offset fontsize", fontsize=8, color=colors[i])

    # Draw Pareto frontier
    pts = sorted(zip(hit_rates, selectivities), reverse=True)
    pareto_x = [pts[0][0]]
    pareto_y = [pts[0][1]]
    for hr, sel in pts[1:]:
        if sel >= pareto_y[-1]:
            pareto_x.append(hr)
            pareto_y.append(sel)
    ax.plot(pareto_x, pareto_y, color="#e74c3c", ls="--", lw=1.2, alpha=0.6, label="Pareto frontier")

    ax.set_xlabel("OOS Hit Rate (recall)")
    ax.set_ylabel("Selectivity (crisis/calm ratio)")
    ax.set_title("Precision-Recall Frontier Across MFLS Variants")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.2)
    plt.tight_layout()
    fig.savefig(FIGDIR / "fig6_selectivity.pdf")
    fig.savefig(FIGDIR / "fig6_selectivity.png")
    plt.close()


def fig7_network_heatmap(data):
    """Figure 7: Ledoit-Wolf correlation network heatmap."""
    print("[fig7] Network heatmap...")
    X_std = data["X_std"]
    sectors = data["sectors"]

    W, rho = lw_correlation_network(X_std)
    short_names = [s.replace("Mutual Savings Banks", "Mut. Sav.")
                    .replace("Stock Savings Banks", "Stk. Sav.")
                    .replace("State Commercial Banks", "State Comm.")
                    .replace("National Commercial Banks", "Natl. Comm.")
                    .replace("Federal Savings Associations", "Fed. Sav.")
                    .replace("State Savings Associations", "State Sav.")
                    .replace("Foreign Institution Branches", "Foreign Br.")
                   for s in sectors]

    fig, ax = plt.subplots(figsize=(5.5, 4.5))
    im = ax.imshow(W, cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")
    ax.set_xticks(range(len(short_names)))
    ax.set_yticks(range(len(short_names)))
    ax.set_xticklabels(short_names, rotation=45, ha="right", fontsize=7)
    ax.set_yticklabels(short_names, fontsize=7)

    # Annotate cells
    for i in range(W.shape[0]):
        for j in range(W.shape[1]):
            color = "white" if abs(W[i, j]) > 0.6 else "black"
            ax.text(j, i, f"{W[i,j]:.2f}", ha="center", va="center", fontsize=6, color=color)

    cbar = fig.colorbar(im, ax=ax, shrink=0.8)
    cbar.set_label("Leverage correlation (Ledoit-Wolf)", fontsize=8)
    ax.set_title(r"Inter-Sector Exposure Network $\mathbf{W}$ (Ledoit-Wolf)")
    plt.tight_layout()
    fig.savefig(FIGDIR / "fig7_network_heatmap.pdf")
    fig.savefig(FIGDIR / "fig7_network_heatmap.png")
    plt.close()


def fig8_granger_pvalues():
    """Figure 8: Granger p-values across variants."""
    print("[fig8] Granger p-values...")
    with open(VARIANT / "results" / "variant_comparison.json") as f:
        vc = json.load(f)

    fig, ax = plt.subplots(figsize=(6, 3.5))
    colors = ["#1a1a2e", "#e67e22", "#2ecc71", "#3498db", "#9b59b6"]
    markers = ["o", "s", "^", "D", "v"]

    for i, (vname, vdata) in enumerate(vc["variants"].items()):
        lags = [g["lag"] for g in vdata["granger"]]
        pvals = [g["p"] for g in vdata["granger"]]
        label = vdata["name"].split("(")[0].strip()
        ax.plot(lags, pvals, color=colors[i], marker=markers[i], ms=5,
                lw=1.2, label=label, alpha=0.8)

    ax.axhline(0.10, color="#e74c3c", ls="--", lw=1, label=r"$\alpha = 0.10$")
    ax.axhline(0.05, color="#e74c3c", ls=":", lw=0.8, alpha=0.5, label=r"$\alpha = 0.05$")
    ax.set_xlabel("Lag (quarters)")
    ax.set_ylabel("p-value")
    ax.set_title("Granger Causality: MFLS -> SRISK-proxy (all variants)")
    ax.legend(fontsize=7, ncol=2, loc="lower right")
    ax.set_ylim(-0.02, 1.05)
    ax.grid(alpha=0.2)
    plt.tight_layout()
    fig.savefig(FIGDIR / "fig8_granger_pvalues.pdf")
    fig.savefig(FIGDIR / "fig8_granger_pvalues.png")
    plt.close()


if __name__ == "__main__":
    data = load_all_data()
    fig1_mfls_crisis(data)
    fig2_energy_spectral(data)
    fig3_bsdt_channels(data)
    v4 = fig4_variant_comparison(data)
    fig5_signed_lr_weights(v4)
    fig6_selectivity(data)
    fig7_network_heatmap(data)
    fig8_granger_pvalues()
    print(f"\n  All figures written to {FIGDIR}/")
