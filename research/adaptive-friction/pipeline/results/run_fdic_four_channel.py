"""
FDIC / World Bank — Four-Channel BSDT Simulation
=================================================
Applies the same four-channel MasterOperator used in the crypto simulation
(v39b / v58 champion) to the FDIC banking sector data.

Theory (§VI, §XII of the paper):
  δ_C = Mahalanobis distance         (familiar stress)
  δ_G = PCA residual gap             (novel structural stress)
  δ_A = activity / cascade velocity  (velocity anomaly)
  δ_T = temporal novelty             (regime transition)

Attribution:  a_k = S̃_k² / ‖S̃‖²   (S̃_k = S_k / μ_k^normal)

Theoretical firing order before a collapse:
  δ_T → δ_G → δ_A → δ_C → return stress

Data:
  FDIC SDI quarterly call-report (SPECGRP 1-7), 1990–2024
  FRED macro features (yield slope, etc.)
  Falls back to FRED-only synthetic panel if FDIC API is unavailable

Events tracked:
  GFC 2008            onset 2008-Q3
  COVID 2020          onset 2020-Q1
  Rate Shock 2022     onset 2022-Q3

Output:
  pipeline/results/fdic_four_channel_results.json
"""

from __future__ import annotations
import os, sys, json, time, warnings
import numpy as np
import pandas as pd
from pathlib import Path

warnings.filterwarnings('ignore')
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR   = Path(__file__).parent
UPGRADED_DIR = SCRIPT_DIR.parent.parent / "upgraded"
COLL_DIR     = SCRIPT_DIR.parent.parent

sys.path.insert(0, str(UPGRADED_DIR))
sys.path.insert(0, str(COLL_DIR))
sys.path.insert(0, str(SCRIPT_DIR))

from collapse_geometry import MasterOperator, Snapshot

# ── upgraded/ helpers ────────────────────────────────────────────────────────
from fred_loader      import fetch_all, apply_transforms, standardise
from fdic_loader      import fetch_fdic_specgrp
from state_matrix     import (build_state_matrix_fdic, standardise_panel,
                               get_normal_period, NORMAL_START, NORMAL_END)

OUT_DIR = SCRIPT_DIR
PCA_K   = 1          # same as v39b/v58 champion
MU_FLOOR = 1e-6
FIRE_PCT = 90        # 90th-percentile threshold over calibration window
HIST_WIN = 8         # look-back quarters for Snapshot history (≈ 2 years)

CRISIS_EVENTS = {
    "GFC 2008":          pd.Timestamp("2008-09-30"),
    "COVID 2020":        pd.Timestamp("2020-03-31"),
    "Rate Shock 2022":   pd.Timestamp("2022-09-30"),
}

CH_NAMES = {0: 'C(Mahal)', 1: 'G(Gap)', 2: 'A(Vel)', 3: 'T(Novel)'}


# ─────────────────────────────────────────────────────────────────────────────
#  DATA LOADING  (mirrors run_pipeline.py fallback logic)
# ─────────────────────────────────────────────────────────────────────────────

def _synthetic_fred_fallback():
    """Minimal synthetic FRED quarterly frame when API unavailable."""
    dates = pd.date_range("1990-03-31", "2024-12-31", freq="QE")
    T = len(dates)
    rng = np.random.default_rng(42)
    t   = np.arange(T)
    cc  = 1.5 * np.sin(2 * np.pi * t / 40) + 0.3 * rng.standard_normal(T)
    def spike(c, w=3, h=4.0):
        return h * np.exp(-((t - c) ** 2) / (2 * w ** 2))
    stress = (rng.standard_normal(T) * 0.3
              + spike(74, 4, 5.0) + spike(121, 3, 6.0) + spike(132, 3, 3.5))
    return pd.DataFrame({
        "credit_gdp":  100 + 10 * cc,
        "total_loans":  8 + 2 * cc + rng.standard_normal(T),
        "stlfsi":       stress,
        "nfci":         0.8 * stress + 0.2 * rng.standard_normal(T),
        "vix":          np.abs(15 + 10 * stress + rng.standard_normal(T)),
        "baa_spread":   np.abs(3 + 4 * np.maximum(stress, 0) + 0.5 * rng.standard_normal(T)),
        "hy_spread":    np.abs(7 + 10 * np.maximum(stress, 0) + rng.standard_normal(T)),
        "slope_10y2y":  1.5 - 0.3 * cc + 0.5 * rng.standard_normal(T),
        "fed_funds":    np.clip(2.5 + cc + 0.3 * rng.standard_normal(T), 0, 20),
        "roa":          1.2 - 0.4 * np.maximum(stress, 0) + 0.1 * rng.standard_normal(T),
    }, index=dates)


def _build_specgrp_synthetic(raw_fred: pd.DataFrame):
    """
    FDIC-unavailable fallback: 7 SPECGRP sectors × 6 FRED features.
    Same logic as run_pipeline.py.
    """
    xf = apply_transforms(raw_fred)
    std_fred, _, _ = standardise(xf)

    SPECGRP_WEIGHTS = np.array([
        [1.6,  0.5,  0.8, -0.7,  0.4,  1.1],
        [1.4,  0.7,  0.9, -0.6,  0.5,  1.0],
        [1.1,  1.0,  0.8, -0.4,  0.7,  1.0],
        [1.5,  1.3,  1.1, -0.3,  1.2,  1.2],
        [2.0,  0.6,  0.7, -0.9,  0.4,  1.3],
        [1.5,  0.5,  0.7, -0.7,  0.4,  1.1],
        [1.0,  1.4,  1.2,  0.2,  1.1,  0.8],
    ], dtype=float)
    FEAT_COLS   = ["total_loans", "stlfsi", "baa_spread", "slope_10y2y", "vix", "fed_funds"]
    FALLBACK_MAP = {"stlfsi": "nfci", "baa_spread": "hy_spread", "total_loans": "credit_gdp"}
    cols = []
    for c in FEAT_COLS:
        if c in std_fred.columns:
            cols.append(std_fred[c])
        elif c in FALLBACK_MAP and FALLBACK_MAP[c] in std_fred.columns:
            cols.append(std_fred[FALLBACK_MAP[c]].rename(c))
        else:
            cols.append(pd.Series(0.0, index=std_fred.index, name=c))
    feat   = pd.concat(cols, axis=1).dropna()
    Z      = feat.values
    rng    = np.random.default_rng(42)
    noise  = rng.standard_normal((len(feat), 7, 6)) * 0.08
    X_all  = Z[:, None, :] * SPECGRP_WEIGHTS[None, :, :] + noise
    dates  = feat.index
    names  = ["Mutual Savings", "Stock Savings", "State Commercial",
              "National Commercial", "Federal Savings", "State Savings", "Foreign Branches"]
    return X_all, dates, names


def load_data(use_cache: bool = True, verbose: bool = True):
    """Return (X_all, dates, sector_names, data_label)  with X_all (T, N, d)."""
    print("\n[1/4] FRED data...")
    try:
        raw_fred  = fetch_all(use_cache=use_cache, verbose=verbose)
    except Exception as e:
        print(f"  FRED unavailable ({e}) — using synthetic fallback")
        raw_fred  = _synthetic_fred_fallback()

    slope_col = "slope_10y2y" if "slope_10y2y" in raw_fred.columns else raw_fred.columns[0]
    fred_slope = raw_fred[slope_col].copy()

    print("\n[2/4] FDIC call-report data...")
    try:
        fdic_df   = fetch_fdic_specgrp(start="1990-01-01", end="2024-12-31",
                                       use_cache=use_cache, verbose=verbose)
        X_all, dates, sector_names = build_state_matrix_fdic(fdic_df, fred_slope)
        label     = "FDIC SDI (real)"
    except Exception as e:
        print(f"  FDIC unavailable ({e}) — using FRED-calibrated synthetic panel")
        X_all, dates, sector_names = _build_specgrp_synthetic(raw_fred)
        label     = "FRED-calibrated synthetic (FDIC unavailable)"

    print(f"  {label}")
    print(f"  Shape: (T={X_all.shape[0]}, N={X_all.shape[1]}, d={X_all.shape[2]})  "
          f"{dates[0].date()} → {dates[-1].date()}")
    return X_all, dates, sector_names, label


# ─────────────────────────────────────────────────────────────────────────────
#  FOUR-CHANNEL SWEEP
# ─────────────────────────────────────────────────────────────────────────────

def calibrate_four_channel(X_std: np.ndarray, calib_mask: np.ndarray, k: int = 1):
    """
    Calibrate MasterOperator on normal period and compute per-channel means.
    Returns  (M, mu_norm, fire_thresholds)
    """
    X_calib = X_std[calib_mask]
    M       = MasterOperator.calibrate(X_calib, k=k)
    bsdt    = M.bsdt

    S_list = []
    for t in range(1, len(X_calib)):
        snap = Snapshot(
            X       = X_calib[t],
            X_prev  = X_calib[t - 1],
            history = X_calib[max(0, t - HIST_WIN):t],
        )
        try:
            S_list.append(bsdt.channel_state(snap))
        except Exception:
            pass

    if not S_list:
        mu_norm   = np.ones(4)
        fire_thr  = np.ones(4) * 2.0
        return M, mu_norm, fire_thr

    S_arr     = np.array(S_list)            # (T', 4)
    mu_norm   = np.maximum(S_arr.mean(0), MU_FLOOR)
    fire_thr  = np.percentile(S_arr, FIRE_PCT, axis=0)

    print("  [4CH] Channel calibration (normal period):")
    for k_idx, name in CH_NAMES.items():
        print(f"    {name}: μ={mu_norm[k_idx]:.4f}  "
              f"fire_thr={fire_thr[k_idx]:.4f}")
    return M, mu_norm, fire_thr


def run_four_channel_sweep(
    X_std:       np.ndarray,
    dates:       pd.DatetimeIndex,
    M,
    mu_norm:     np.ndarray,
    fire_thr:    np.ndarray,
) -> pd.DataFrame:
    """
    Sweep all T timesteps.  Returns DataFrame with columns:
      e_C, e_G, e_A, e_T          raw channel energies
      a_C, a_G, a_A, a_T          normalized attributions
      fire_C, fire_G, fire_A, fire_T  threshold flags
      dom_channel                  dominant channel index
    """
    T    = len(X_std)
    bsdt = M.bsdt
    E    = M.energy
    keys = ['e_C','e_G','e_A','e_T','a_C','a_G','a_A','a_T',
            'fire_C','fire_G','fire_A','fire_T','dom_channel']
    buf  = {k: np.full(T, np.nan) for k in keys}

    t0 = time.time()
    for t in range(1, T):
        snap = Snapshot(
            X       = X_std[t],
            X_prev  = X_std[t - 1],
            history = X_std[max(0, t - HIST_WIN):t],
        )
        try:
            S = bsdt.channel_state(snap)
            buf['e_C'][t], buf['e_G'][t] = S[0], S[1]
            buf['e_A'][t], buf['e_T'][t] = S[2], S[3]

            S_norm = S / mu_norm
            a      = E.channel_attribution(S_norm)
            buf['a_C'][t], buf['a_G'][t] = a[0], a[1]
            buf['a_A'][t], buf['a_T'][t] = a[2], a[3]
            buf['dom_channel'][t]         = float(np.argmax(a))

            buf['fire_C'][t] = float(S[0] > fire_thr[0])
            buf['fire_G'][t] = float(S[1] > fire_thr[1])
            buf['fire_A'][t] = float(S[2] > fire_thr[2])
            buf['fire_T'][t] = float(S[3] > fire_thr[3])
        except Exception:
            pass

    elapsed = time.time() - t0
    print(f"  [4CH] Sweep complete: {T} quarters in {elapsed:.1f}s")
    return pd.DataFrame(buf, index=dates)


# ─────────────────────────────────────────────────────────────────────────────
#  CRISIS ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────

def _lead_time(fire_series: pd.Series, onset: pd.Timestamp, pre_quarters: int = 12):
    """Quarters from first threshold crossing to onset. None if no crossing."""
    window = fire_series[fire_series.index < onset].iloc[-pre_quarters:]
    hits   = window[window > 0.5]
    if hits.empty:
        return None
    return int((onset - hits.index[0]).days // 91)   # approx quarters


def analyse_crises(sig: pd.DataFrame, dates: pd.DatetimeIndex) -> dict:
    results = {}
    for name, onset in CRISIS_EVENTS.items():
        if onset > dates[-1]:
            continue
        # per-channel attribution at onset
        idx_onset  = sig.index.searchsorted(onset)
        idx_onset  = min(idx_onset, len(sig) - 1)
        row        = sig.iloc[idx_onset]
        attributions = {f"a_{c}": round(float(row.get(f"a_{c}", np.nan)), 4)
                        for c in ('C', 'G', 'A', 'T')}
        # check which channel has highest attribution at onset
        dom = max(attributions, key=attributions.get)

        # firing lead times before onset
        lead_times = {}
        for c in ('C', 'G', 'A', 'T'):
            lt = _lead_time(sig[f'fire_{c}'], onset)
            lead_times[f'lead_{c}_quarters'] = lt

        # window attribution (3Q before onset)
        onset_slice = sig[(sig.index >= onset - pd.DateOffset(months=9))
                          & (sig.index <= onset)]
        mean_attr   = {f"pre_mean_a_{c}": round(float(onset_slice[f"a_{c}"].mean()), 4)
                       for c in ('C', 'G', 'A', 'T')}

        # dominant channel in pre-onset window
        if len(onset_slice) > 0:
            dom_pre = CH_NAMES[int(onset_slice['dom_channel'].mode()[0])]
        else:
            dom_pre = "—"

        results[name] = {
            "onset": str(onset.date()),
            **attributions,
            "dominant_channel_at_onset": dom,
            **lead_times,
            **mean_attr,
            "dominant_channel_pre3Q": dom_pre,
        }

        # print summary
        print(f"\n  ── {name} ──")
        print(f"    Attribution at onset:  "
              + "  ".join(f"a_{c}={attributions[f'a_{c}']:.3f}" for c in ('C','G','A','T')))
        print(f"    Dominant channel:      {dom}  (pre-onset 3Q: {dom_pre})")
        print(f"    Channel lead times:    "
              + "  ".join(f"{c}:{lead_times[f'lead_{c}_quarters']}Q"
                          for c in ('C', 'G', 'A', 'T')))
    return results


def print_firing_sequence_theory():
    print("""
  ── Theoretical channel firing order ──
    δ_T fires first  → regime transition (pre-collapse early warning)
    δ_G fires second → novel structural stress (PCA gap)
    δ_A fires third  → cascade velocity (activity anomaly)
    δ_C fires last   → familiar systemic stress fully realised
    If empirical lead times match this order → theory validated.
""")


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main(use_cache: bool = True):
    Sep = "=" * 70
    print(Sep)
    print("  FDIC / World Bank — Four-Channel BSDT Simulation")
    print("  Using same engine as crypto v58 champion (MasterOperator, k=1)")
    print(Sep)

    # ── 1. Load data ─────────────────────────────────────────────────────────
    X_all, dates, sector_names, data_label = load_data(use_cache=use_cache)
    T, N, d = X_all.shape
    print(f"\n  Sectors ({N}): {', '.join(sector_names)}")

    # ── 2. Normal period + standardise ──────────────────────────────────────
    print("\n[3/4] Normal period and standardisation...")
    X_normal, dates_normal = get_normal_period(X_all, dates)
    X_std, _, _  = standardise_panel(X_all, X_ref=X_normal)
    X_norm_std, _, _ = standardise_panel(X_normal, X_ref=X_normal)
    calib_mask   = np.zeros(T, dtype=bool)
    calib_mask[(dates >= pd.Timestamp(NORMAL_START))
               & (dates <= pd.Timestamp(NORMAL_END))] = True
    print(f"  Normal period:  {dates_normal[0].date()} → {dates_normal[-1].date()}"
          f"  ({calib_mask.sum()} quarters)")
    print(f"  Calibration PCA_K = {PCA_K}")

    # ── 3. Calibrate MasterOperator + four-channel sweep ────────────────────
    print("\n[4/4] Four-channel sweep...")
    M, mu_norm, fire_thr = calibrate_four_channel(X_std, calib_mask, k=PCA_K)
    sig = run_four_channel_sweep(X_std, dates, M, mu_norm, fire_thr)

    # ── 4. Crisis analysis ───────────────────────────────────────────────────
    print("\n── Crisis Attribution ──────────────────────────────────────────────")
    print_firing_sequence_theory()
    crisis_results = analyse_crises(sig, dates)

    # ── 5. Full time-series stats ────────────────────────────────────────────
    print("\n── Full Period Statistics ──────────────────────────────────────────")
    for c in ('C', 'G', 'A', 'T'):
        s = sig[f'a_{c}'].dropna()
        print(f"  a_{c}: mean={s.mean():.3f}  p90={s.quantile(0.9):.3f}"
              f"  max={s.max():.3f}  fire_pct={sig[f'fire_{c}'].mean()*100:.1f}%")

    # dominant channel distribution
    dom_counts = sig['dom_channel'].dropna().value_counts().sort_index()
    print("\n  Dominant channel distribution:")
    for ch_idx, cnt in dom_counts.items():
        print(f"    {CH_NAMES[int(ch_idx)]}: {int(cnt)} quarters ({cnt/len(sig)*100:.1f}%)")

    # ── 6. Save results ──────────────────────────────────────────────────────
    out = {
        "data_label":        data_label,
        "shape":             [T, N, d],
        "date_range":        [str(dates[0].date()), str(dates[-1].date())],
        "normal_period":     [str(dates_normal[0].date()), str(dates_normal[-1].date())],
        "sector_names":      sector_names,
        "pca_k":             PCA_K,
        "mu_norm":           mu_norm.tolist(),
        "fire_thresholds":   fire_thr.tolist(),
        "crisis_attribution": crisis_results,
        "channel_stats": {
            c: {
                "mean_attribution":  round(float(sig[f'a_{c}'].mean()), 4),
                "p90_attribution":   round(float(sig[f'a_{c}'].quantile(0.9)), 4),
                "max_attribution":   round(float(sig[f'a_{c}'].max()), 4),
                "fire_pct":          round(float(sig[f'fire_{c}'].mean() * 100), 2),
            }
            for c in ('C', 'G', 'A', 'T')
        },
        "time_series": {
            "dates": [str(d) for d in sig.index],
            "a_C": [round(v, 4) for v in sig['a_C'].fillna(0).tolist()],
            "a_G": [round(v, 4) for v in sig['a_G'].fillna(0).tolist()],
            "a_A": [round(v, 4) for v in sig['a_A'].fillna(0).tolist()],
            "a_T": [round(v, 4) for v in sig['a_T'].fillna(0).tolist()],
            "dom_channel": [int(v) if not np.isnan(v) else -1
                            for v in sig['dom_channel'].tolist()],
        },
    }

    out_path = OUT_DIR / "fdic_four_channel_results.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\n  Saved: {out_path.name}")
    print(Sep)
    return out


if __name__ == "__main__":
    main()
