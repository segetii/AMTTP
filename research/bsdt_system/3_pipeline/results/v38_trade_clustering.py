"""
v38_trade_clustering.py
========================
Clustering / data-mining analysis of winning vs losing trades for v38.

Re-runs variants:
  38a  d=0.25, q=0.50, η=3e-4, lm=1000, G7 off  → Final $997k (equity record)
  38b  d=0.30, q=0.65, η=2e-4, lm=1000, κ=10    → Max-DD −27.8% (DD record)

Two layers of clustering
------------------------
  1. SEGMENT level  — contiguous active (non-halted) periods between CB trips.
     Each segment is one "trade epoch"; features describe duration, return,
     weights, ODE geometry, and preceding lock state.

  2. BAR level      — every active 1h bar; features come from the ODE log
     (E, γ, cos θ, rhs_norm, conviction, weights) plus rolling returns.
     Clusters label individual bars as winners or losers.

Outputs (console + PNG)
------------------------
  v38_clustering/segment_summary.txt     — per-cluster statistics
  v38_clustering/bar_summary.txt         — per-cluster bar statistics
  v38_clustering/equity_segments_38a.png — equity curve coloured by cluster
  v38_clustering/equity_segments_38b.png
  v38_clustering/features_38a.png        — violin plots per cluster
  v38_clustering/features_38b.png
  v38_clustering/pca_38a.png             — PCA scatter coloured by cluster
  v38_clustering/pca_38b.png
  v38_clustering/dd_drivers.png          — bars ranked by DD contribution
"""
from __future__ import annotations

import sys
import time
from collections import deque
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score

sys.path.insert(0, str(Path(__file__).parent))

import run_crypto_godmode_v27_all_microstructure as v27
import run_crypto_godmode_v28_canonical_stability as v28
from run_crypto_pairs_v34_full_combined import OUT_DIR, TEST_START, TRAIN_START, build_1h_df
from run_crypto_godmode_v1 import (
    KAPPA_A, W_TARGET_A1, build_b_aligned, build_w_star,
    _predictive_scalars, CONV_MIN, CONV_MAX, W_BOX,
    ANNEAL_AMP, ANNEAL_PEAK, TradingDomain, EPSILON,
)
from run_crypto_canonical_v4 import (
    A_FACTORS, N_STATE, K_FACTOR, DT,
    build_factor_returns, rescale_to_correlation,
)
from run_crypto_godmode_v8_multiasset_shell import (
    ASSETS, build_asset_inputs, fetch_futures_ohlcv_symbol,
)
from run_crypto_godmode_v9_multiasset_tune import attach_q_hot
from test_daily_geometry_stop_tp_ohlc import get_channel_series
from simulate_master_strategy import (
    DYN_DD_SOFT, DYN_DD_STOP, DYN_Y_FLOOR, INIT, HOURS_PER_DAY,
    equity_metrics, period_table,
)
from run_crypto_godmode_v35_top5_cb_transition import (
    ffd_weights, frac_diff_series, ffd_covariance,
    build_sigma, theta_from,
    TOP5, REG_VARIANT, FFD_THRESHOLD, FFD_MAX_LAG,
    K_NORMAL, RT_BPS, KAPPA_CAP,
)
from run_crypto_godmode_v38_ito_tightcb import (
    regularise_sigma_g7, fisher_weight_noise_sqrt, c_sigma_per_bar,
    run_godmode_det, CB_HALT, CB_RESUME, CB_WINDOW,
)

# ── Constants ──────────────────────────────────────────────────────────────────
OUT_DIR_ = Path(OUT_DIR) / "v38_clustering"
OUT_DIR_.mkdir(parents=True, exist_ok=True)

N_CLUSTERS_SEG = 5   # trade-segment clusters
N_CLUSTERS_BAR = 6   # bar-level clusters
RANDOM_STATE   = 42

# Target variants
VARIANTS = [
    dict(name="38a", d=0.25, q=0.50, eta=3e-4, lock_min=1000, kappa_max=None),
    dict(name="38b", d=0.30, q=0.65, eta=2e-4, lock_min=1000, kappa_max=10),
]

CLUSTER_PALETTE = ["#e63946", "#457b9d", "#2a9d8f", "#e9c46a", "#f4a261", "#264653"]


# ── Extended CB simulation (returns per-bar arrays) ───────────────────────────

def simulate_extended(
    unit_normal:     pd.Series,
    unit_crash:      pd.Series,
    K_normal:        float,
    K_crash:         float,
    dd_soft:         float,
    dd_stop:         float,
    y_floor:         float,
    cb_halt:         float,
    cb_resume:       float,
    cb_window_days:  int,
    ito_c_sigma_bar: float,
    lock_min:        int,
) -> dict:
    """
    Identical logic to simulate_combined_lockmin from v38 run script,
    but also returns full per-bar arrays for clustering:
      cb_flag        1 = halted, 0 = active
      lock_bars_arr  bars locked at this point (0 when active)
      y_arr          position-scaling factor
      dd_aty_arr     all-time drawdown at each bar
      cb_dd_arr      rolling-window drawdown at each bar
      reset_flag     1 at G2.4 override bars
    """
    window_bars = cb_window_days * HOURS_PER_DAY
    mono_dq: deque = deque()
    eq = INIT
    peak_alltime = INIT
    halted = False
    halt_start_bar = 0

    eq_vals       = []
    cb_flag_arr   = []
    lock_bars_arr = []
    y_arr         = []
    dd_aty_arr    = []
    cb_dd_arr     = []
    reset_flag    = []
    ito_resets    = 0

    for bar_i in range(len(unit_normal)):
        ur_n = float(unit_normal.iloc[bar_i])
        ur_c = float(unit_crash.iloc[bar_i])

        while mono_dq and mono_dq[0][0] <= bar_i - window_bars:
            mono_dq.popleft()
        while mono_dq and mono_dq[-1][1] <= eq:
            mono_dq.pop()
        mono_dq.append((bar_i, eq))
        roll_peak = mono_dq[0][1]

        dd_aty = max(0.0, 1.0 - eq / max(peak_alltime, 1e-12))
        cb_dd  = max(0.0, 1.0 - eq / max(roll_peak,    1e-12))

        fired_reset = False
        if not halted and cb_dd >= cb_halt:
            halted = True
            halt_start_bar = bar_i
        elif halted:
            lock_bars = bar_i - halt_start_bar
            if cb_dd <= cb_resume:
                halted = False
            elif ito_c_sigma_bar > 0.0 and lock_bars >= lock_min:
                noise_budget = ito_c_sigma_bar * lock_bars
                if cb_dd <= cb_resume + noise_budget:
                    halted = False
                    ito_resets += 1
                    fired_reset = True
                    halt_start_bar = bar_i

        if halted:
            y = 0.0
        elif dd_aty <= dd_soft:
            y = 1.0
        elif dd_aty >= dd_stop:
            y = y_floor
        else:
            y = y_floor + (1.0 - y_floor) * (dd_stop - dd_aty) / (dd_stop - dd_soft)

        r = K_normal * y * ur_n + K_crash * ur_c
        r = max(r, -0.95)
        eq *= (1.0 + r)
        peak_alltime = max(peak_alltime, eq)

        eq_vals.append(eq)
        cb_flag_arr.append(int(halted))
        lock_bars_arr.append(bar_i - halt_start_bar if halted else 0)
        y_arr.append(y)
        dd_aty_arr.append(dd_aty)
        cb_dd_arr.append(cb_dd)
        reset_flag.append(int(fired_reset))

    idx  = unit_normal.index
    eqs  = pd.Series(eq_vals,       index=idx, name="equity")
    rets = eqs.pct_change().fillna(eqs.iloc[0] / INIT - 1.0)
    dd_s = (eqs - eqs.cummax()) / eqs.cummax()

    return dict(
        eq          = eqs,
        rets        = rets,
        drawdown    = dd_s,
        cb_flag     = pd.Series(cb_flag_arr,   index=idx, name="cb_flag"),
        lock_bars   = pd.Series(lock_bars_arr, index=idx, name="lock_bars"),
        y           = pd.Series(y_arr,         index=idx, name="y"),
        dd_aty      = pd.Series(dd_aty_arr,    index=idx, name="dd_aty"),
        cb_dd       = pd.Series(cb_dd_arr,     index=idx, name="cb_dd"),
        reset_flag  = pd.Series(reset_flag,    index=idx, name="reset_flag"),
        ito_resets  = ito_resets,
        final       = float(eqs.iloc[-1]),
        maxdd       = float(dd_s.min()),
    )


# ── Segment extraction ─────────────────────────────────────────────────────────

def extract_segments(sim: dict, ode_log: pd.DataFrame, test_ts: pd.Timestamp) -> pd.DataFrame:
    """
    Identify contiguous active (non-halted) periods in the test window.
    For each segment compute:
      duration_h, seg_return, seg_maxdd, seg_pnl_std, seg_pnl_skew
      mean/std of ODE features (E, gamma, cos_theta, rhs_norm, conviction, w_sum)
      start_month, start_year, start_hour
      prev_lock_h (how long the CB was locked before this segment)
      had_g2_reset (did this segment start with a G2.4 override?)
    """
    test_mask = sim["eq"].index >= test_ts
    cb_flag   = sim["cb_flag"][test_mask]
    eq        = sim["eq"][test_mask]
    rets      = sim["rets"][test_mask]
    rf        = sim["reset_flag"][test_mask]
    lb        = sim["lock_bars"][test_mask]
    # Align ode_log to sim index (handles 1-bar sol-ffill offset)
    ode       = ode_log.reindex(sim["eq"].index, method="ffill")[test_mask]

    segments = []
    in_seg   = False
    seg_start_i = None
    prev_lock_h = 0

    arr = cb_flag.values
    idx = cb_flag.index

    for i in range(len(arr)):
        active_now = (arr[i] == 0)

        if active_now and not in_seg:
            in_seg = True
            seg_start_i = i
            # How long was the prior halt?
            if i > 0:
                j = i - 1
                while j >= 0 and arr[j] == 1:
                    j -= 1
                prev_lock_h = (i - j - 1)
            else:
                prev_lock_h = 0

        elif (not active_now or i == len(arr) - 1) and in_seg:
            seg_end_i = i if not active_now else i + 1
            in_seg = False

            seg_idx   = slice(seg_start_i, seg_end_i)
            seg_rets  = rets.iloc[seg_idx]
            seg_eq    = eq.iloc[seg_idx]
            seg_ode   = ode.iloc[seg_idx]
            seg_rf    = rf.iloc[seg_idx]

            if len(seg_eq) < 2:
                continue

            cum   = seg_eq / seg_eq.iloc[0]
            maxdd = float((cum / cum.cummax() - 1).min())

            seg_return = float(seg_eq.iloc[-1] / seg_eq.iloc[0] - 1.0)
            start_ts   = idx[seg_start_i]

            row = dict(
                start           = start_ts,
                end             = idx[seg_end_i - 1],
                duration_h      = len(seg_rets),
                seg_return      = seg_return,
                seg_maxdd       = maxdd,
                seg_pnl_mean    = float(seg_rets.mean()),
                seg_pnl_std     = float(seg_rets.std()),
                seg_pnl_skew    = float(seg_rets.skew()) if len(seg_rets) > 3 else 0.0,
                seg_pnl_min     = float(seg_rets.min()),
                # ODE geometry averages
                mean_E          = float(seg_ode["E"].mean()),
                mean_gamma      = float(seg_ode["gamma"].mean()),
                mean_cos_theta  = float(seg_ode["cos_theta"].mean()),
                mean_rhs_norm   = float(seg_ode["rhs_norm"].mean()),
                mean_conviction = float(seg_ode["conviction"].mean()),
                mean_drift      = float(seg_ode["drift_flag"].mean()),
                mean_stop       = float(seg_ode["stop_flag"].mean()),
                mean_stale      = float(seg_ode["stale_flag"].mean()),
                mean_rho_eff    = float(seg_ode["rho_eff"].mean()),
                # Portfolio weights
                mean_w_btc      = float(seg_ode["w_btc"].mean()),
                mean_w_eth      = float(seg_ode["w_eth"].mean()),
                mean_w_sol      = float(seg_ode["w_sol"].mean()),
                mean_w_abs      = float((seg_ode[["w_btc","w_eth","w_sol"]].abs().sum(axis=1)).mean()),
                # Context
                start_month     = int(start_ts.month),
                start_year      = int(start_ts.year),
                start_hour      = int(start_ts.hour),
                prev_lock_h     = prev_lock_h,
                had_g2_reset    = int(seg_rf.iloc[0] == 1 if len(seg_rf) > 0 else 0),
                label           = "win" if seg_return > 0 else "lose",
            )
            segments.append(row)

    return pd.DataFrame(segments)


# ── Bar-level feature extraction ──────────────────────────────────────────────

def extract_bars(sim: dict, ode_log: pd.DataFrame, df: pd.DataFrame,
                 test_ts: pd.Timestamp) -> pd.DataFrame:
    """
    Active bars in test window. Adds:
      rolling_ret_btc_24h, rolling_vol_btc_24h
      equity drawdown, lock_bars preceding this bar
      pnl (bar return from ODE log = w · R)
    """
    test_mask_idx = df.index >= test_ts
    cb_flag   = sim["cb_flag"]
    active    = (cb_flag == 0) & pd.Series(cb_flag.index >= test_ts,
                                           index=cb_flag.index)

    # Align ode_log to sim index (handles 1-bar sol-ffill offset)
    ode_aligned = ode_log.reindex(cb_flag.index, method="ffill")

    active_idx = active[active].index
    ode  = ode_aligned.loc[active_idx].copy()
    mkt  = df.reindex(active_idx, method="ffill").copy()
    eq   = sim["eq"][active]
    dd   = sim["drawdown"][active]
    lb   = sim["lock_bars"][active]
    y    = sim["y"][active]

    # Rolling 24h market momentum/vol (from full df, then select active)
    for col in ["ret_btc", "ret_eth", "ret_sol"]:
        if col in df.columns:
            mkt[f"roll_ret_{col}_24h"] = df[col].rolling(24).mean()[active]
            mkt[f"roll_vol_{col}_24h"] = df[col].rolling(24).std()[active]

    bars = ode[["E","gamma","dE_dt","cos_theta","mfls","v_E","rho_eff",
                "rhs_norm","w_btc","w_eth","w_sol","pnl","conviction",
                "theta_t","stop_flag","stale_flag","drift_flag"]].copy()
    bars["eq_dd"]       = dd.values
    bars["lock_bars_b"] = lb.values
    bars["y_scale"]     = y.values
    bars["hour"]        = bars.index.hour
    bars["month"]       = bars.index.month

    for col in ["ret_btc","ret_eth","ret_sol"]:
        if col in mkt.columns:
            bars[f"roll_ret_{col}"]  = mkt[f"roll_ret_{col}_24h"].values
            bars[f"roll_vol_{col}"]  = mkt[f"roll_vol_{col}_24h"].values

    bars["w_total_abs"] = bars[["w_btc","w_eth","w_sol"]].abs().sum(axis=1)
    bars["pnl_sign"]    = np.sign(bars["pnl"])
    return bars.dropna()


# ── Cluster segments ──────────────────────────────────────────────────────────

SEG_FEATURES = [
    "duration_h", "seg_return", "seg_maxdd", "seg_pnl_std",
    "seg_pnl_skew", "seg_pnl_min",
    "mean_E", "mean_gamma", "mean_cos_theta", "mean_rhs_norm",
    "mean_conviction", "mean_drift", "mean_stop", "mean_rho_eff",
    "mean_w_btc", "mean_w_eth", "mean_w_sol", "mean_w_abs",
    "prev_lock_h", "start_month",
]

BAR_FEATURES = [
    "E", "gamma", "cos_theta", "rhs_norm", "conviction",
    "w_btc", "w_eth", "w_sol", "w_total_abs",
    "eq_dd", "y_scale", "pnl",
    "roll_ret_ret_btc", "roll_vol_ret_btc",
    "roll_ret_ret_eth", "roll_vol_ret_eth",
    "hour", "month",
]


def cluster_dataframe(df: pd.DataFrame, features: list[str], n_clusters: int,
                      label: str) -> tuple[pd.DataFrame, KMeans, PCA, StandardScaler]:
    """Fit K-Means and PCA; add 'cluster' column to df. Returns fitted objects."""
    feat_cols = [f for f in features if f in df.columns]
    X = df[feat_cols].copy()
    X = X.replace([np.inf, -np.inf], np.nan).fillna(X.median())

    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)

    # Pick best k by silhouette (search 3 to n_clusters)
    best_k, best_sil, best_km = n_clusters, -1.0, None
    for k in range(3, n_clusters + 1):
        km = KMeans(n_clusters=k, random_state=RANDOM_STATE, n_init=20)
        labs = km.fit_predict(Xs)
        if len(set(labs)) < 2:
            continue
        sil = silhouette_score(Xs, labs, sample_size=min(5000, len(Xs)))
        if sil > best_sil:
            best_sil, best_k, best_km = sil, k, km

    print(f"  [{label}] best k={best_k}  silhouette={best_sil:.3f}")
    df = df.copy()
    df["cluster"] = best_km.labels_

    pca = PCA(n_components=2, random_state=RANDOM_STATE)
    pca.fit(Xs)
    df["pc1"] = pca.transform(Xs)[:, 0]
    df["pc2"] = pca.transform(Xs)[:, 1]

    return df, best_km, pca, scaler


# ── Summarise clusters ────────────────────────────────────────────────────────

def segment_cluster_summary(seg_df: pd.DataFrame, variant_name: str) -> str:
    lines = [f"\n{'='*80}",
             f"  SEGMENT CLUSTERS — variant {variant_name}",
             f"{'='*80}"]

    for k in sorted(seg_df["cluster"].unique()):
        sub = seg_df[seg_df["cluster"] == k]
        wins   = (sub["seg_return"] > 0).sum()
        losses = (sub["seg_return"] <= 0).sum()
        total_ret = sub["seg_return"].sum()
        pattern = "WINNER" if sub["seg_return"].mean() > 0 else "LOSER"
        dd_cat  = "HIGH-DD" if sub["seg_maxdd"].mean() < -0.10 else "LOW-DD"

        lines.append(f"\n  Cluster {k}  [{pattern} / {dd_cat}]  n={len(sub)}")
        lines.append(f"    wins={wins}  losses={losses}  "
                     f"avg_ret={sub['seg_return'].mean():+.3f}  "
                     f"total_ret={total_ret:+.3f}")
        lines.append(f"    avg_dur={sub['duration_h'].mean():.0f}h  "
                     f"avg_maxdd={sub['seg_maxdd'].mean():.3f}  "
                     f"avg_pnl_skew={sub['seg_pnl_skew'].mean():.2f}")
        lines.append(f"    avg_gamma={sub['mean_gamma'].mean():.4f}  "
                     f"avg_cos_theta={sub['mean_cos_theta'].mean():.4f}  "
                     f"avg_conviction={sub['mean_conviction'].mean():.4f}")
        lines.append(f"    avg_rhs_norm={sub['mean_rhs_norm'].mean():.4f}  "
                     f"avg_w_abs={sub['mean_w_abs'].mean():.4f}  "
                     f"avg_prev_lock={sub['prev_lock_h'].mean():.0f}h")
        lines.append(f"    g2_resets={sub['had_g2_reset'].sum()}  "
                     f"start_yr={sub['start_year'].mode().iloc[0] if len(sub)>0 else 'N/A'}")

    return "\n".join(lines)


def bar_cluster_summary(bar_df: pd.DataFrame, variant_name: str) -> str:
    lines = [f"\n{'='*80}",
             f"  BAR CLUSTERS — variant {variant_name}",
             f"{'='*80}"]

    for k in sorted(bar_df["cluster"].unique()):
        sub = bar_df[bar_df["cluster"] == k]
        pos  = (sub["pnl"] > 0).mean()
        pattern = "WINNING_BAR" if sub["pnl"].mean() > 0 else "LOSING_BAR"
        lines.append(f"\n  Cluster {k}  [{pattern}]  n={len(sub)}")
        lines.append(f"    pct_positive={pos:.2%}  avg_pnl={sub['pnl'].mean():.5f}  "
                     f"std_pnl={sub['pnl'].std():.5f}")
        lines.append(f"    avg_gamma={sub['gamma'].mean():.4f}  "
                     f"avg_cos_theta={sub['cos_theta'].mean():.4f}  "
                     f"avg_E={sub['E'].mean():.4f}")
        lines.append(f"    avg_conviction={sub['conviction'].mean():.4f}  "
                     f"avg_rhs_norm={sub['rhs_norm'].mean():.4f}  "
                     f"avg_eq_dd={sub['eq_dd'].mean():.4f}")
        lines.append(f"    avg_w_btc={sub['w_btc'].mean():.4f}  "
                     f"avg_w_eth={sub['w_eth'].mean():.4f}  "
                     f"avg_w_sol={sub['w_sol'].mean():.4f}")

    return "\n".join(lines)


# ── DD contributor analysis ────────────────────────────────────────────────────

def dd_contributor_analysis(sim: dict, ode_log: pd.DataFrame,
                             df: pd.DataFrame, test_ts: pd.Timestamp) -> pd.DataFrame:
    """
    Find every bar where equity is BELOW the current all-time max (i.e., in drawdown).
    For each drawdown episode (contiguous below ATH), compute:
      - magnitude of drawdown
      - which assets were net negative contributors (w * R < 0 by asset)
      - ODE geometry at the start of the episode
    Returns a DataFrame of drawdown episodes ranked by severity.
    """
    cb_flag   = sim["cb_flag"]
    active_mask = (cb_flag == 0) & pd.Series(cb_flag.index >= test_ts,
                                              index=cb_flag.index)
    eq        = sim["eq"]
    # Align ode_log to sim index
    ode_aligned = ode_log.reindex(cb_flag.index, method="ffill")

    active = active_mask
    eq_t   = eq[active]
    ode_t  = ode_aligned[active]

    R = np.column_stack([
        df["ret_btc"].fillna(0).values,
        df["ret_eth"].fillna(0).values,
        (df["ret_sol"].fillna(0).values if "ret_sol" in df.columns
         else df["ret_eth"].fillna(0).values),
    ])
    # R is indexed on df; eq_t is on sim index. Build per-asset R aligned to sim.
    df_reindexed = df.reindex(cb_flag.index, method="ffill")
    R_aligned = np.column_stack([
        df_reindexed["ret_btc"].fillna(0).values,
        df_reindexed["ret_eth"].fillna(0).values,
        (df_reindexed["ret_sol"].fillna(0).values if "ret_sol" in df_reindexed.columns
         else df_reindexed["ret_eth"].fillna(0).values),
    ])
    R_t = R_aligned[active.values]

    ath     = eq_t.cummax()
    in_dd   = (eq_t < ath)

    episodes = []
    in_ep = False
    ep_start = None
    ep_peak  = None

    for i in range(len(in_dd)):
        if in_dd.iloc[i] and not in_ep:
            in_ep    = True
            ep_start = i
            ep_peak  = float(ath.iloc[i])
        elif (not in_dd.iloc[i] or i == len(in_dd) - 1) and in_ep:
            ep_end = i
            in_ep  = False

            sl         = slice(ep_start, ep_end)
            eq_ep      = eq_t.iloc[sl]
            ode_ep     = ode_t.iloc[sl]
            pnl_ep     = ode_ep["pnl"].values
            R_ep       = R_t[sl]
            w_ep       = ode_ep[["w_btc","w_eth","w_sol"]].values

            # Per-asset PnL contribution
            btc_contr = float((w_ep[:, 0] * R_ep[:, 0]).sum())
            eth_contr = float((w_ep[:, 1] * R_ep[:, 1]).sum())
            sol_contr = float((w_ep[:, 2] * R_ep[:, 2]).sum())

            mag = float((eq_ep.min() / ep_peak) - 1.0)   # negative

            episodes.append(dict(
                start           = eq_t.index[ep_start],
                end             = eq_t.index[ep_end - 1],
                duration_h      = ep_end - ep_start,
                dd_magnitude    = mag,
                btc_contribution= btc_contr,
                eth_contribution= eth_contr,
                sol_contribution= sol_contr,
                # ODE state at beginning of episode
                gamma_start     = float(ode_t.iloc[ep_start]["gamma"]),
                cos_theta_start = float(ode_t.iloc[ep_start]["cos_theta"]),
                conviction_start= float(ode_t.iloc[ep_start]["conviction"]),
                rhs_norm_start  = float(ode_t.iloc[ep_start]["rhs_norm"]),
                E_start         = float(ode_t.iloc[ep_start]["E"]),
                # Mean features over episode
                mean_gamma      = float(ode_ep["gamma"].mean()),
                mean_cos_theta  = float(ode_ep["cos_theta"].mean()),
                mean_conviction = float(ode_ep["conviction"].mean()),
                mean_w_abs      = float(ode_ep[["w_btc","w_eth","w_sol"]].abs().sum(axis=1).mean()),
            ))

    ep_df = pd.DataFrame(episodes)
    if not ep_df.empty:
        ep_df = ep_df.sort_values("dd_magnitude").reset_index(drop=True)
    return ep_df


# ── Plotting ───────────────────────────────────────────────────────────────────

def plot_equity_segments(sim: dict, seg_df: pd.DataFrame,
                         test_ts: pd.Timestamp, variant_name: str) -> str:
    """Equity curve with active segments colour-coded by cluster."""
    eq     = sim["eq"][sim["eq"].index >= test_ts]
    cb     = sim["cb_flag"][sim["cb_flag"].index >= test_ts]
    k_vals = sorted(seg_df["cluster"].unique())
    colors = {k: CLUSTER_PALETTE[i % len(CLUSTER_PALETTE)] for i, k in enumerate(k_vals)}

    fig, axes = plt.subplots(2, 1, figsize=(18, 9), sharex=True,
                             gridspec_kw={"height_ratios": [3, 1]})
    ax, ax2 = axes

    ax.semilogy(eq.index, eq.values, lw=0.6, color="#cccccc", zorder=1)

    for _, row in seg_df.iterrows():
        seg_eq = eq[(eq.index >= row["start"]) & (eq.index <= row["end"])]
        if len(seg_eq) < 2:
            continue
        clr = colors[row["cluster"]]
        ax.semilogy(seg_eq.index, seg_eq.values, lw=1.5, color=clr,
                    alpha=0.75, zorder=2)

    # CB halted shading
    halted_start = None
    for i, (ts, flag) in enumerate(cb.items()):
        if flag == 1 and halted_start is None:
            halted_start = ts
        elif flag == 0 and halted_start is not None:
            ax.axvspan(halted_start, ts, color="#888888", alpha=0.10, zorder=0)
            halted_start = None

    # Legend
    handles = [mpatches.Patch(color=colors[k],
               label=f"C{k} {'WIN' if seg_df[seg_df['cluster']==k]['seg_return'].mean()>0 else 'LOSE'}"
                     f" (n={len(seg_df[seg_df['cluster']==k])})")
               for k in k_vals]
    ax.legend(handles=handles, fontsize=8, ncol=2)
    ax.set_ylabel("Equity ($)")
    ax.set_title(f"v{variant_name}: Equity Curve — Trade Segment Clusters", fontweight="bold")
    ax.grid(True, alpha=0.2)
    ax.axhline(730056, ls=":", lw=1, color="purple", alpha=0.5, label="$730k ref")

    # Panel 2: per-segment return scatter
    for _, row in seg_df.iterrows():
        mid_ts = row["start"] + (row["end"] - row["start"]) / 2
        clr    = colors[row["cluster"]]
        ax2.bar(mid_ts, row["seg_return"] * 100, width=pd.Timedelta(
            hours=max(row["duration_h"], 12)), color=clr, alpha=0.7)

    ax2.axhline(0, lw=0.8, color="black")
    ax2.set_ylabel("Seg. Return (%)")
    ax2.set_xlabel("Date")
    ax2.grid(True, alpha=0.2)

    plt.tight_layout()
    out = OUT_DIR_ / f"equity_segments_{variant_name}.png"
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return str(out)


def plot_feature_violins(seg_df: pd.DataFrame, variant_name: str) -> str:
    """Violin + box plots of key features per cluster."""
    k_vals  = sorted(seg_df["cluster"].unique())
    colors  = {k: CLUSTER_PALETTE[i % len(CLUSTER_PALETTE)] for i, k in enumerate(k_vals)}
    feat    = ["seg_return", "seg_maxdd", "duration_h",
               "mean_gamma", "mean_cos_theta", "mean_conviction",
               "mean_rhs_norm", "mean_w_abs", "prev_lock_h", "seg_pnl_skew"]
    labels  = ["Seg. Return", "Seg. MaxDD", "Duration (h)",
               "Mean γ", "Mean cos θ", "Mean conviction",
               "Mean rhs_norm", "Mean |W|", "Prev. Lock (h)", "PnL Skew"]

    fig, axes = plt.subplots(2, 5, figsize=(22, 8))
    axes = axes.flatten()

    for i, (col, lbl) in enumerate(zip(feat, labels)):
        ax = axes[i]
        data = [seg_df[seg_df["cluster"] == k][col].dropna().values for k in k_vals]
        parts = ax.violinplot(data, positions=range(len(k_vals)), showmedians=True)
        for j, pc in enumerate(parts["bodies"]):
            pc.set_facecolor(CLUSTER_PALETTE[j % len(CLUSTER_PALETTE)])
            pc.set_alpha(0.6)
        ax.set_xticks(range(len(k_vals)))
        ax.set_xticklabels([f"C{k}" for k in k_vals], fontsize=8)
        ax.set_title(lbl, fontsize=9)
        ax.grid(True, alpha=0.2)

    fig.suptitle(f"v{variant_name}: Segment Feature Distributions by Cluster",
                 fontweight="bold")
    plt.tight_layout()
    out = OUT_DIR_ / f"features_{variant_name}.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return str(out)


def plot_pca(seg_df: pd.DataFrame, variant_name: str) -> str:
    """PCA scatter of trade segments coloured by cluster."""
    k_vals = sorted(seg_df["cluster"].unique())
    colors = {k: CLUSTER_PALETTE[i % len(CLUSTER_PALETTE)] for i, k in enumerate(k_vals)}

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    for ax, (col, title) in zip(axes, [("cluster", "Cluster"), ("label", "Win/Lose")]):
        if col == "cluster":
            c_arr = [colors[k] for k in seg_df["cluster"]]
            handles = [mpatches.Patch(color=colors[k],
                       label=f"C{k} {'WIN' if seg_df[seg_df['cluster']==k]['seg_return'].mean()>0 else 'LOSE'}")
                       for k in k_vals]
        else:
            c_arr = ["#2a9d8f" if v == "win" else "#e63946" for v in seg_df["label"]]
            handles = [mpatches.Patch(color="#2a9d8f", label="Win"),
                       mpatches.Patch(color="#e63946", label="Lose")]

        sc = ax.scatter(seg_df["pc1"], seg_df["pc2"], c=c_arr, alpha=0.7, s=50,
                        edgecolors="white", linewidths=0.3)
        ax.set_xlabel("PC1")
        ax.set_ylabel("PC2")
        ax.set_title(f"PCA of Segments — {title}")
        ax.legend(handles=handles, fontsize=8)
        ax.grid(True, alpha=0.2)

    fig.suptitle(f"v{variant_name}: Segment PCA", fontweight="bold")
    plt.tight_layout()
    out = OUT_DIR_ / f"pca_{variant_name}.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return str(out)


def plot_dd_drivers(ep_a: pd.DataFrame, ep_b: pd.DataFrame) -> str:
    """Bar chart of top-N drawdown episodes by magnitude for both variants."""
    fig, axes = plt.subplots(1, 2, figsize=(18, 6))
    for ax, ep, name in zip(axes, [ep_a, ep_b], ["38a", "38b"]):
        if ep.empty:
            ax.set_title(f"v{name}: no episodes")
            continue
        top = ep.head(12)
        y   = range(len(top))
        ax.barh(y, top["btc_contribution"] * 100, label="BTC", color="#f4a261", alpha=0.8)
        ax.barh(y, top["eth_contribution"] * 100, left=top["btc_contribution"] * 100,
                label="ETH", color="#457b9d", alpha=0.8)
        ax.barh(y, top["sol_contribution"] * 100,
                left=(top["btc_contribution"] + top["eth_contribution"]) * 100,
                label="SOL", color="#2a9d8f", alpha=0.8)
        ax.set_yticks(list(y))
        ax.set_yticklabels(
            [f"{r['start'].strftime('%Y-%m-%d')} ({r['dd_magnitude']:.1%})"
             for _, r in top.iterrows()],
            fontsize=8)
        ax.axvline(0, color="black", lw=0.8)
        ax.set_xlabel("Cumulative return contribution (%)")
        ax.set_title(f"v{name}: Drawdown Episodes (worst first) — Asset Contribution",
                     fontweight="bold")
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.2)

    plt.tight_layout()
    out = OUT_DIR_ / "dd_drivers.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return str(out)


def plot_bar_clusters(bar_df: pd.DataFrame, sim: dict,
                      test_ts: pd.Timestamp, variant_name: str) -> str:
    """Equity curve dot-coloured by bar cluster (sampled for readability)."""
    eq = sim["eq"][sim["eq"].index >= test_ts]
    sample = bar_df.sample(min(3000, len(bar_df)), random_state=42)
    k_vals = sorted(bar_df["cluster"].unique())
    colors = {k: CLUSTER_PALETTE[i % len(CLUSTER_PALETTE)] for i, k in enumerate(k_vals)}

    fig, ax = plt.subplots(figsize=(18, 6))
    ax.semilogy(eq.index, eq.values, lw=0.5, color="#cccccc", zorder=1)

    c_arr = [colors[k] for k in sample["cluster"]]
    ax.scatter(sample.index, eq.loc[sample.index], c=c_arr,
               s=4, alpha=0.4, zorder=2)

    handles = [mpatches.Patch(color=colors[k],
               label=f"C{k} "
                     f"{'POS' if bar_df[bar_df['cluster']==k]['pnl'].mean()>0 else 'NEG'}"
                     f"  avg_pnl={bar_df[bar_df['cluster']==k]['pnl'].mean():.5f}")
               for k in k_vals]
    ax.legend(handles=handles, fontsize=8, ncol=2)
    ax.set_ylabel("Equity ($)")
    ax.set_title(f"v{variant_name}: Bar-Level Clusters (sampled 3k pts)", fontweight="bold")
    ax.grid(True, alpha=0.2)

    plt.tight_layout()
    out = OUT_DIR_ / f"bar_clusters_{variant_name}.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return str(out)


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    t0 = time.time()
    print("=" * 80)
    print("  v38 TRADE CLUSTERING ANALYSIS")
    print("=" * 80)

    # ── [0] Data & shared inputs ─────────────────────────────────────────────
    print("\n[0] Loading market data ...")
    for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
        ms = v27._get_ms(sym)
        print(f"  {sym}: {ms.shape}")

    df, _      = build_1h_df(start="2021-01-01", end="2026-06-01")
    train_mask = np.asarray((df.index >= TRAIN_START) & (df.index < TEST_START))
    test_mask  = np.asarray(df.index >= TEST_START)
    test_ts    = pd.Timestamp(TEST_START)
    w_star     = build_w_star(df, W_TARGET=W_TARGET_A1)
    b_aligned  = build_b_aligned(w_star)
    factor_R   = build_factor_returns(df)
    v27.RT_COST = RT_BPS / 10_000.0

    ohlc_map = {symbol: fetch_futures_ohlcv_symbol(symbol)
                for _, symbol, _, _ in ASSETS}
    ch = get_channel_series()

    all_seg_summaries = []
    all_bar_summaries = []
    ep_store          = {}
    plots             = []

    for var in VARIANTS:
        name      = var["name"]
        d         = var["d"]
        q         = var["q"]
        eta       = var["eta"]
        lock_min  = var["lock_min"]
        kappa_max = var["kappa_max"]

        print(f"\n{'─'*80}")
        print(f"  Variant {name}: d={d}, q={q}, η={eta:.0e}, lm={lock_min}, "
              f"κ_max={kappa_max}")
        print(f"{'─'*80}")

        # ── [1] Sigma + G7 ───────────────────────────────────────────────────
        Sigma_base, Sigma_ffd, sdiag, bdiag = build_sigma(factor_R, train_mask, df, d)
        if kappa_max is not None:
            Sigma_cap, lam_g7 = regularise_sigma_g7(Sigma_base, float(kappa_max))
        else:
            Sigma_cap, lam_g7 = Sigma_base, 0.0
        _, rank_Ix = fisher_weight_noise_sqrt(Sigma_cap)
        c_sb       = c_sigma_per_bar(eta, rank_Ix)
        theta      = theta_from(b_aligned, train_mask, Sigma_cap, bdiag["budget"], q)
        print(f"  θ={theta:.5f}  λ_g7={lam_g7:.3e}  rank_Ix={rank_Ix}  c_σ/bar={c_sb:.3e}")

        # ── [2] ODE log ──────────────────────────────────────────────────────
        print(f"  Running ODE log ...", end="  ", flush=True)
        t_ode = time.time()
        label = f"v{name}_d{str(d).replace('.','p')}_q{str(q).replace('.','p')}"
        ode_log = run_godmode_det(
            df, train_mask, test_mask, w_star, b_aligned,
            Sigma_cap, theta, kappa=KAPPA_A, label=label,
        )
        print(f"{time.time()-t_ode:.1f}s")

        # ── [3] Build unit signal ────────────────────────────────────────────
        print(f"  Building unit signal ...", end="  ", flush=True)
        t_sig = time.time()
        inputs_noq = build_asset_inputs(df, ode_log, w_star, ch, ohlc_map,
                                        signal_kind="wstar", use_quadrant=False)
        inputs_q   = build_asset_inputs(df, ode_log, w_star, ch, ohlc_map,
                                        signal_kind="wstar", use_quadrant=True)
        inputs     = attach_q_hot(inputs_noq, inputs_q)
        sig_map    = {asset: pd.Series(w_star[:, idx], index=df.index, name=f"wstar_{asset}")
                      for asset, _, _, idx in ASSETS}
        run_out    = v28.run_variant_v28(REG_VARIANT, inputs, sig_map, ode_log)
        unit       = run_out["unit"]
        unit_crash = pd.Series(0.0, index=unit.index)
        print(f"{time.time()-t_sig:.1f}s")

        # ── [4] Extended CB simulation ───────────────────────────────────────
        print(f"  Running extended CB simulation ...", end="  ", flush=True)
        t_sim = time.time()
        sim = simulate_extended(
            unit_normal    = unit,
            unit_crash     = unit_crash,
            K_normal       = K_NORMAL,
            K_crash        = 0.0,
            dd_soft        = DYN_DD_SOFT,
            dd_stop        = DYN_DD_STOP,
            y_floor        = DYN_Y_FLOOR,
            cb_halt        = CB_HALT,
            cb_resume      = CB_RESUME,
            cb_window_days = CB_WINDOW,
            ito_c_sigma_bar= c_sb,
            lock_min       = lock_min,
        )
        print(f"{time.time()-t_sim:.1f}s  "
              f"final={sim['final']:,.0f}  maxdd={sim['maxdd']:.3f}  "
              f"resets={sim['ito_resets']}")

        # ── [5] Segment clustering ───────────────────────────────────────────
        print(f"  Extracting segments ...")
        seg_df = extract_segments(sim, ode_log, test_ts)
        print(f"    {len(seg_df)} segments  "
              f"wins={( seg_df['seg_return']>0).sum()}  "
              f"losses={(seg_df['seg_return']<=0).sum()}")

        print(f"  Clustering segments ...")
        seg_df, km_seg, pca_seg, sc_seg = cluster_dataframe(
            seg_df, SEG_FEATURES, N_CLUSTERS_SEG, f"{name}-seg")

        summary = segment_cluster_summary(seg_df, name)
        print(summary)
        all_seg_summaries.append(summary)

        # ── [6] Bar-level clustering ─────────────────────────────────────────
        print(f"  Extracting active bars ...")
        bar_df = extract_bars(sim, ode_log, df, test_ts)
        print(f"    {len(bar_df)} active bars")

        print(f"  Clustering bars ...")
        bar_df_cl, km_bar, pca_bar, sc_bar = cluster_dataframe(
            bar_df, BAR_FEATURES, N_CLUSTERS_BAR, f"{name}-bar")

        bsummary = bar_cluster_summary(bar_df_cl, name)
        print(bsummary)
        all_bar_summaries.append(bsummary)

        # ── [7] DD contributors ──────────────────────────────────────────────
        print(f"  Analysing drawdown episodes ...")
        ep_df = dd_contributor_analysis(sim, ode_log, df, test_ts)
        ep_store[name] = ep_df
        print(f"    {len(ep_df)} drawdown episodes")
        if not ep_df.empty:
            print(f"    Top-3 worst episodes:")
            for _, row in ep_df.head(3).iterrows():
                print(f"      {row['start'].date()} → {row['end'].date()} "
                      f"dd={row['dd_magnitude']:.2%}  "
                      f"BTC={row['btc_contribution']:+.3f}  "
                      f"ETH={row['eth_contribution']:+.3f}  "
                      f"SOL={row['sol_contribution']:+.3f}  "
                      f"γ_start={row['gamma_start']:.4f}  "
                      f"cos_θ_start={row['cos_theta_start']:.4f}")

        # ── [8] Plots ────────────────────────────────────────────────────────
        print(f"  Plotting ...")
        plots.append(plot_equity_segments(sim, seg_df, test_ts, name))
        plots.append(plot_feature_violins(seg_df, name))
        plots.append(plot_pca(seg_df, name))
        plots.append(plot_bar_clusters(bar_df_cl, sim, test_ts, name))

    # ── DD driver comparison plot ────────────────────────────────────────────
    plots.append(plot_dd_drivers(
        ep_store.get("38a", pd.DataFrame()),
        ep_store.get("38b", pd.DataFrame()),
    ))

    # ── Write text summaries ─────────────────────────────────────────────────
    seg_out = OUT_DIR_ / "segment_summary.txt"
    seg_out.write_text("\n".join(all_seg_summaries), encoding="utf-8")

    bar_out = OUT_DIR_ / "bar_summary.txt"
    bar_out.write_text("\n".join(all_bar_summaries), encoding="utf-8")

    elapsed = time.time() - t0
    print(f"\n{'='*80}")
    print(f"  DONE in {elapsed:.0f}s")
    print(f"  Output directory: {OUT_DIR_}")
    print(f"  Plots ({len(plots)}):")
    for p in plots:
        print(f"    {p}")
    print(f"  Text: {seg_out}")
    print(f"       {bar_out}")
    print(f"{'='*80}")


if __name__ == "__main__":
    main()
