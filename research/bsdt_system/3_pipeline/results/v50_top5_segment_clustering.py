# -*- coding: utf-8 -*-
"""
v50_top5_segment_clustering.py
==============================

Clustering analysis on segments pooled across the TOP 5 algorithm variants:

  A. v34 baseline       d=0.25  q=0.50  w=90d   ($617K, MDD=-34.6%)
  B. v45 wide window    d=0.25  q=0.50  w=180d  ($131K, MDD=-14.0%)
  C. v45 mid window     d=0.25  q=0.50  w=120d
  D. alt theta scale    d=0.25  q=1.00  w=90d
  E. alt frac diff      d=0.50  q=0.50  w=90d

For each variant:
  - Run sim and extract every active segment with full feature set.
Pool everything → standardise → KMeans (k=4) + PCA(2) → scatter plots.

Outputs:
  v50_clustering/segments_pooled.csv
  v50_clustering/cluster_summary.csv
  v50_clustering/plots/pca_by_cluster.png
  v50_clustering/plots/pca_by_outcome.png
  v50_clustering/plots/pca_by_variant.png
  v50_clustering/plots/feature_means_by_cluster.png
"""
from __future__ import annotations

import json, sys, time
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).parent))

import run_crypto_godmode_v27_all_microstructure as v27
import run_crypto_godmode_v28_canonical_stability as v28
from run_crypto_pairs_v34_full_combined import OUT_DIR, TEST_START, TRAIN_START, build_1h_df
from run_crypto_godmode_v1 import W_TARGET_A1, build_b_aligned, build_w_star
from run_crypto_canonical_v4 import build_factor_returns
from run_crypto_godmode_v8_multiasset_shell import (
    ASSETS, build_asset_inputs, fetch_futures_ohlcv_symbol,
)
from run_crypto_godmode_v9_multiasset_tune import attach_q_hot
from test_daily_geometry_stop_tp_ohlc import get_channel_series
from simulate_master_strategy import HOURS_PER_DAY, equity_metrics
from run_crypto_godmode_v35_top5_cb_transition import (
    REG_VARIANT, K_NORMAL, RT_BPS, build_sigma, theta_from,
)

from v49_mode1_feature_search import run_ode, simulate_v34_trace, extract_segments

BAR = "=" * 110
OUT = Path(OUT_DIR) / "v50_clustering"
PLOT = OUT / "plots"

# (label, d, q, cb_halt, cb_resume, cb_window_d, color)
VARIANTS = [
    ("A_v34_base",    0.25, 0.50, 0.08, 0.04,  90, "tab:red"),
    ("B_v45_w180",    0.25, 0.50, 0.08, 0.04, 180, "tab:blue"),
    ("C_v45_w120",    0.25, 0.50, 0.08, 0.04, 120, "tab:purple"),
    ("D_q1.00",       0.25, 1.00, 0.08, 0.04,  90, "tab:green"),
    ("E_d0.50",       0.50, 0.50, 0.08, 0.04,  90, "tab:orange"),
]

CB_HALT_ALL    = 0.08  # constant across variants
N_CLUSTERS = 4

CLUSTER_FEATURES = [
    "duration_h", "seg_return", "peak_gain", "seg_maxdd", "pnl_skew",
    "gamma_0", "rhs_norm_0", "omega_0", "cos_theta_0", "E_0", "rho_0",
    "conv_0", "mfls_0", "w_abs_0",
    "prev_lock_h", "prev_seg_ret",
    "first4_ret", "first4_vol", "first4_dd", "first24_vol",
    "btc_24h_ret", "btc_24h_vol",
]


def main():
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    PLOT.mkdir(parents=True, exist_ok=True)

    print(BAR)
    print("  v50 — TOP 5 SEGMENT CLUSTERING")
    for v in VARIANTS:
        print(f"   {v[0]:<14}  d={v[1]:.2f}  q={v[2]:.2f}  win={v[5]:>3}d")
    print(BAR)

    # ── Microstructure cache ──
    print("\n[0] Microstructure cache ...")
    for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
        v27._get_ms(sym)

    # ── Inputs ──
    print("\n[1] Building 1h DF ...")
    df, _ = build_1h_df(start="2021-01-01", end="2026-06-01")
    train_mask = np.asarray((df.index >= TRAIN_START) & (df.index < TEST_START))
    test_ts = pd.Timestamp(TEST_START)
    w_star = build_w_star(df, W_TARGET=W_TARGET_A1)
    b_aligned = build_b_aligned(w_star)
    factor_R = build_factor_returns(df)
    v27.RT_COST = RT_BPS / 10_000.0

    btc_ret = df["btc"].pct_change().fillna(0.0)
    btc_ma = df["btc"].rolling(200 * HOURS_PER_DAY, min_periods=24).mean().bfill()

    ohlc_map = {symbol: fetch_futures_ohlcv_symbol(symbol) for _, symbol, _, _ in ASSETS}
    ch = get_channel_series()

    # ── Pre-compute ODE per unique (d, q) ──
    dq_set = sorted({(v[1], v[2]) for v in VARIANTS})
    print(f"\n[2] Pre-computing ODE for {len(dq_set)} unique (d, q) pairs ...")
    ode_cache = {}    # (d,q) -> (log_ann, unit)
    for d, q in dq_set:
        print(f"\n  [d={d}, q={q}]")
        Sigma_base, _, sdiag, bdiag = build_sigma(factor_R, train_mask, df, d)
        theta = theta_from(b_aligned, train_mask, Sigma_base, bdiag["budget"], q)
        log_ann, _ = run_ode(df, train_mask, w_star, b_aligned, Sigma_base, theta)
        # Build unit returns for this ODE log
        inputs_noq = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map,
                                         signal_kind="wstar", use_quadrant=False)
        inputs_q = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map,
                                       signal_kind="wstar", use_quadrant=True)
        inputs = attach_q_hot(inputs_noq, inputs_q)
        sig_map = {a: pd.Series(w_star[:, idx], index=df.index, name=f"wstar_{a}")
                   for a, _, _, idx in ASSETS}
        unit = v28.run_variant_v28(REG_VARIANT, inputs, sig_map, log_ann)["unit"]
        ode_cache[(d, q)] = (log_ann, unit)

    # ── Run each variant + extract segments ──
    print(f"\n[3] Simulating {len(VARIANTS)} variants and extracting segments ...")
    pooled = []
    metrics_rows = []
    for label, d, q, cb_h, cb_r, w_d, color in VARIANTS:
        log_ann, unit = ode_cache[(d, q)]
        sim = simulate_v34_trace(unit, K_NORMAL, cb_h, cb_r, w_d)
        eq_test = sim["eq"][sim["eq"].index >= test_ts]
        m = equity_metrics(eq_test, label)
        metrics_rows.append(dict(variant=label, final=m["final"], maxdd=m["maxdd"],
                                  calmar=m["calmar"], sharpe=m["sharpe"]))
        seg = extract_segments(sim, log_ann, df, btc_ret, btc_ma, test_ts)
        seg.insert(0, "variant", label)
        seg.insert(1, "color", color)
        pooled.append(seg)
        print(f"  {label:<14} segments={len(seg):>3}  Final=${m['final']:>10,.0f}  "
              f"MDD={m['maxdd']:>+7.2%}  Cal={m['calmar']:>5.2f}")

    pool = pd.concat(pooled, ignore_index=True)
    pool["outcome"] = np.where(pool["seg_return"] > 0, "win", "lose")
    pool.to_csv(OUT / "segments_pooled.csv", index=False)
    print(f"\n  Total pooled segments: {len(pool)}")
    print(f"    Winners: {(pool['outcome']=='win').sum()}   Losers: {(pool['outcome']=='lose').sum()}")
    print(f"  → segments_pooled.csv")

    # ── KMeans clustering in standardised feature space ──
    print(f"\n[4] KMeans clustering (k={N_CLUSTERS}) on {len(CLUSTER_FEATURES)} features ...")
    X = pool[CLUSTER_FEATURES].astype(float).fillna(0.0).values
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)
    km = KMeans(n_clusters=N_CLUSTERS, n_init=20, random_state=42)
    pool["cluster"] = km.fit_predict(Xs)
    pca = PCA(n_components=2, random_state=42)
    XY = pca.fit_transform(Xs)
    pool["pca1"] = XY[:, 0]
    pool["pca2"] = XY[:, 1]
    print(f"  PCA explained variance: PC1={pca.explained_variance_ratio_[0]:.2%}  "
          f"PC2={pca.explained_variance_ratio_[1]:.2%}  "
          f"(cum {pca.explained_variance_ratio_.sum():.2%})")

    # ── Cluster summary ──
    print(f"\n[5] Cluster summary:")
    summary = pool.groupby("cluster").agg(
        n=("seg_return", "size"),
        n_losers=("outcome", lambda s: (s == "lose").sum()),
        win_rate=("outcome", lambda s: (s == "win").mean()),
        mean_return=("seg_return", "mean"),
        median_return=("seg_return", "median"),
        mean_peak=("peak_gain", "mean"),
        mean_maxdd=("seg_maxdd", "mean"),
        mean_skew=("pnl_skew", "mean"),
        mean_dur_h=("duration_h", "mean"),
        mean_omega0=("omega_0", "mean"),
        mean_gamma0=("gamma_0", "mean"),
        mean_first4_ret=("first4_ret", "mean"),
        mean_btc24h=("btc_24h_ret", "mean"),
    ).reset_index()
    summary.to_csv(OUT / "cluster_summary.csv", index=False)
    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 20)
    print(summary.to_string(index=False))
    print(f"  → cluster_summary.csv")

    # ── Variant × cluster cross-tab ──
    print(f"\n[6] Variant × cluster cross-tab:")
    ctab = pd.crosstab(pool["variant"], pool["cluster"], margins=True)
    print(ctab.to_string())

    # ── Plots ──
    print(f"\n[7] Generating scatter plots ...")
    cluster_colors = ["tab:cyan", "tab:olive", "tab:pink", "tab:brown",
                      "tab:gray", "tab:purple"]

    # Plot 1: PCA coloured by cluster
    fig, ax = plt.subplots(figsize=(11, 8))
    for c in sorted(pool["cluster"].unique()):
        sub = pool[pool["cluster"] == c]
        # Marker shape by outcome
        for outcome, marker in [("win", "o"), ("lose", "X")]:
            ss = sub[sub["outcome"] == outcome]
            if len(ss) == 0: continue
            ax.scatter(ss["pca1"], ss["pca2"], c=cluster_colors[c % len(cluster_colors)],
                       marker=marker, s=120, edgecolor="black", linewidth=0.7,
                       alpha=0.85, label=f"C{c} {outcome} (n={len(ss)})")
    ax.axhline(0, color="black", lw=0.5, alpha=0.3)
    ax.axvline(0, color="black", lw=0.5, alpha=0.3)
    ax.set_xlabel(f"PC1 ({pca.explained_variance_ratio_[0]:.1%} var)")
    ax.set_ylabel(f"PC2 ({pca.explained_variance_ratio_[1]:.1%} var)")
    ax.set_title(f"v50 — PCA scatter coloured by KMeans cluster (k={N_CLUSTERS})  •  "
                 f"O = winner   X = loser",
                 fontweight="bold")
    ax.legend(loc="best", fontsize=8, ncol=2)
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(PLOT / "pca_by_cluster.png", dpi=160, bbox_inches="tight")
    plt.close(fig)

    # Plot 2: PCA coloured by outcome (win/lose)
    fig, ax = plt.subplots(figsize=(11, 8))
    for outcome, color in [("win", "tab:green"), ("lose", "tab:red")]:
        sub = pool[pool["outcome"] == outcome]
        ax.scatter(sub["pca1"], sub["pca2"], c=color, s=140, alpha=0.75,
                   edgecolor="black", linewidth=0.7, label=f"{outcome} (n={len(sub)})")
    # Annotate Mode 1 reversals
    for _, r in pool[(pool["peak_gain"] > 0.02) & (pool["seg_return"] < -0.02)].iterrows():
        ax.annotate(f"M1", (r["pca1"], r["pca2"]),
                    xytext=(5, 5), textcoords="offset points", fontsize=8, color="darkred")
    # Annotate stillborn
    for _, r in pool[(pool["peak_gain"] < 0.005) & (pool["seg_return"] < -0.03)].iterrows():
        ax.annotate(f"M0", (r["pca1"], r["pca2"]),
                    xytext=(5, -10), textcoords="offset points", fontsize=8, color="black")
    ax.axhline(0, color="black", lw=0.5, alpha=0.3)
    ax.axvline(0, color="black", lw=0.5, alpha=0.3)
    ax.set_xlabel(f"PC1 ({pca.explained_variance_ratio_[0]:.1%} var)")
    ax.set_ylabel(f"PC2 ({pca.explained_variance_ratio_[1]:.1%} var)")
    ax.set_title("v50 — PCA scatter coloured by outcome  •  M1=reversal-loser  M0=stillborn-loser",
                 fontweight="bold")
    ax.legend(loc="best", fontsize=10)
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(PLOT / "pca_by_outcome.png", dpi=160, bbox_inches="tight")
    plt.close(fig)

    # Plot 3: PCA coloured by variant
    fig, ax = plt.subplots(figsize=(11, 8))
    for label, _, _, _, _, _, color in VARIANTS:
        sub = pool[pool["variant"] == label]
        for outcome, marker in [("win", "o"), ("lose", "X")]:
            ss = sub[sub["outcome"] == outcome]
            if len(ss) == 0: continue
            ax.scatter(ss["pca1"], ss["pca2"], c=color, marker=marker, s=130,
                       alpha=0.8, edgecolor="black", linewidth=0.7,
                       label=f"{label} {outcome} (n={len(ss)})")
    ax.axhline(0, color="black", lw=0.5, alpha=0.3)
    ax.axvline(0, color="black", lw=0.5, alpha=0.3)
    ax.set_xlabel(f"PC1 ({pca.explained_variance_ratio_[0]:.1%} var)")
    ax.set_ylabel(f"PC2 ({pca.explained_variance_ratio_[1]:.1%} var)")
    ax.set_title("v50 — PCA scatter coloured by variant  •  O = winner   X = loser",
                 fontweight="bold")
    ax.legend(loc="best", fontsize=7, ncol=2)
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(PLOT / "pca_by_variant.png", dpi=160, bbox_inches="tight")
    plt.close(fig)

    # Plot 4: feature means by cluster (heat-map style)
    print("[8] Feature means by cluster heat-map ...")
    means = pool.groupby("cluster")[CLUSTER_FEATURES].mean()
    means_z = (means - means.mean()) / (means.std() + 1e-9)
    fig, ax = plt.subplots(figsize=(13, max(4, 0.45*len(CLUSTER_FEATURES))))
    im = ax.imshow(means_z.T.values, aspect="auto", cmap="RdBu_r",
                   vmin=-2, vmax=2)
    ax.set_xticks(range(len(means_z)))
    ax.set_xticklabels([f"C{c}\n(n={int((pool['cluster']==c).sum())})"
                         for c in means_z.index])
    ax.set_yticks(range(len(CLUSTER_FEATURES)))
    ax.set_yticklabels(CLUSTER_FEATURES)
    for i in range(len(means_z.index)):
        for j in range(len(CLUSTER_FEATURES)):
            ax.text(i, j, f"{means.iloc[i,j]:.2f}", ha="center", va="center",
                    fontsize=7, color="black")
    fig.colorbar(im, ax=ax, label="z-score across clusters")
    ax.set_title("v50 — Feature means by cluster (z-scored across clusters)",
                 fontweight="bold")
    fig.tight_layout()
    fig.savefig(PLOT / "feature_means_by_cluster.png", dpi=160, bbox_inches="tight")
    plt.close(fig)

    # Plot 5: 6-panel feature-pair scatter (most informative pairs)
    print("[9] Feature-pair scatter grid ...")
    pairs = [
        ("peak_gain", "seg_return"),
        ("first4_ret", "seg_return"),
        ("btc_24h_ret", "seg_return"),
        ("duration_h", "seg_return"),
        ("conv_0", "seg_return"),
        ("omega_0", "seg_return"),
    ]
    fig, axes = plt.subplots(2, 3, figsize=(16, 9))
    for ax, (xf, yf) in zip(axes.ravel(), pairs):
        for c in sorted(pool["cluster"].unique()):
            sub = pool[pool["cluster"] == c]
            ax.scatter(sub[xf], sub[yf], c=cluster_colors[c % len(cluster_colors)],
                       s=80, alpha=0.8, edgecolor="black", linewidth=0.5,
                       label=f"C{c}")
        ax.axhline(0, color="black", lw=0.5, alpha=0.3)
        ax.axvline(0, color="black", lw=0.5, alpha=0.3)
        ax.set_xlabel(xf); ax.set_ylabel(yf)
        ax.grid(True, alpha=0.25)
        ax.legend(fontsize=7)
    fig.suptitle("v50 — Feature-pair scatter, coloured by cluster", fontweight="bold")
    fig.tight_layout()
    fig.savefig(PLOT / "feature_pair_scatter.png", dpi=160, bbox_inches="tight")
    plt.close(fig)

    print(f"\n[10] Saving JSON ...")
    json.dump({
        "version": "v50",
        "n_pooled": len(pool),
        "variants": metrics_rows,
        "n_clusters": N_CLUSTERS,
        "pca_explained": [float(x) for x in pca.explained_variance_ratio_],
        "cluster_summary": summary.to_dict(orient="records"),
        "variant_x_cluster": ctab.to_dict(),
    }, open(OUT / "v50_clustering.json", "w"), indent=2, default=str)

    print(f"\n  Plots:")
    for p in PLOT.glob("*.png"):
        print(f"    {p}")

    print(f"\n{BAR}")
    print(f"  v50 COMPLETE  |  elapsed={time.time()-t0:.1f}s")
    print(BAR)


if __name__ == "__main__":
    main()
