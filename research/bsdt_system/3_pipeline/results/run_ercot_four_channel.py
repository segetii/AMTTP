"""
ERCOT — Four-Channel BSDT Simulation
======================================
Applies the same four-channel MasterOperator used in the crypto simulation
(v39b / v58 champion) to ERCOT hourly energy supply data.

Theory (§VI, §XII):
  δ_C = Mahalanobis distance         (familiar coupling stress)
  δ_G = PCA residual gap             (novel structural stress)
  δ_A = activity / cascade velocity  (dispatch velocity anomaly)
  δ_T = temporal novelty             (regime transition / precedent-free)

Attribution:  a_k = S̃_k² / ‖S̃‖²   (S̃_k = S_k / μ_k^normal)

Multi-agent encoding:
  Each ERCOT supply source is one agent (N = 5):
    wind, solar, gas, coal, nuclear
  Each agent's state vector has d = 4 features:
    f0  current z-score         (normalised level)
    f1  24h change              (hourly momentum)
    f2  168h change             (weekly drift)
    f3  48h rolling z-score     (short-range deviation)
  This mirrors the crypto approach: multi-agent × multi-feature state.

Datasets used:
  combined_hourly.npz  (35064 × 10) — unified supply + demand dataset
                                       wind_cf, solar_cf, gas_cf, coal_cf,
                                       nuclear_cf, demand_gw, ramp_rate,
                                       vol_6h, dev_24h, temp_stress
                                       All 10 columns are equal co-variates of
                                       a single multivariate observation; no
                                       column is privileged over another.

Events tracked:
  COVID_Collapse 2020-03-23
  WinterStorm Uri 2021-02-10
  WinterStorm Elliott 2022-12-22
  SummerPeak 2019 2019-08-12

Normal period for calibration:
  Full year 2019 (same as existing ERCOT simulation)

Output:
  pipeline/results/ercot_four_channel_results.json
"""

from __future__ import annotations
import os, sys, json, time, warnings
import numpy as np
import pandas as pd
from pathlib import Path

warnings.filterwarnings('ignore')
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).parent
COLL_DIR   = SCRIPT_DIR.parent.parent

sys.path.insert(0, str(COLL_DIR))
sys.path.insert(0, str(SCRIPT_DIR))

from collapse_geometry import MasterOperator, Snapshot

DATA_DIR = Path(r"C:\amttp\data\ercot")
OUT_DIR  = SCRIPT_DIR

PCA_K    = 1     # same as crypto champion
MU_FLOOR = 1e-6
FIRE_PCT = 90
HIST_WIN = 168   # 1-week look-back for Snapshot history
N_FEAT   = 4     # features per agent (see module docstring)

CH_NAMES = {0: 'C(Mahal)', 1: 'G(Gap)', 2: 'A(Vel)', 3: 'T(Novel)'}

EVENTS = {
    "COVID_Collapse 2020-03-23":      pd.Timestamp("2020-03-23"),
    "WinterStorm Uri 2021-02-10":     pd.Timestamp("2021-02-10"),
    "WinterStorm Elliott 2022-12-22": pd.Timestamp("2022-12-22"),
    "SummerPeak 2019 2019-08-12":     pd.Timestamp("2019-08-12"),
}

NORMAL_YEAR = 2019


# ─────────────────────────────────────────────────────────────────────────────
#  MULTI-AGENT PANEL BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def build_ercot_agent_panel(
    X_raw:  np.ndarray,
    dates:  pd.DatetimeIndex,
    normal_mask: np.ndarray,
) -> np.ndarray:
    """
    Convert (T, N_agents) raw ERCOT supply data to (T, N_agents, N_FEAT) panel.

    Feature vector per agent per timestep:
      f0  level_z     current z-score against 2019 stats
      f1  d24h        24-hour change (level, not z-scored)
      f2  d168h       168-hour (weekly) change
      f3  roll48_z    48-hour rolling std, z-scored against 2019 std-of-stds

    All features are nan_to_num'd to 0 at boundaries.
    """
    T, N  = X_raw.shape
    mu    = X_raw[normal_mask].mean(0)        # (N,)
    sigma = X_raw[normal_mask].std(0) + 1e-8  # (N,)

    level_z  = (X_raw - mu) / sigma           # (T, N)
    d24      = np.zeros_like(X_raw)
    d168     = np.zeros_like(X_raw)
    roll48_z = np.zeros_like(X_raw)

    df_raw = pd.DataFrame(X_raw)
    for i in range(N):
        col = df_raw.iloc[:, i]
        d24[:, i]      = col.diff(24).fillna(0.0).values
        d168[:, i]     = col.diff(168).fillna(0.0).values
        rs             = col.rolling(48, min_periods=4).std()
        rs_mu = rs[normal_mask].mean()
        rs_sg = rs[normal_mask].std() + 1e-8
        roll48_z[:, i] = ((rs - rs_mu) / rs_sg).fillna(0.0).values

    # stack into (T, N, 4)
    panel = np.stack([level_z, d24, d168, roll48_z], axis=2)   # (T, N, 4)
    return np.nan_to_num(panel, nan=0.0)


# ─────────────────────────────────────────────────────────────────────────────
#  FOUR-CHANNEL CALIBRATION
# ─────────────────────────────────────────────────────────────────────────────

def calibrate_four_channel(
    X_panel:     np.ndarray,
    calib_mask:  np.ndarray,
    k:           int = 1,
):
    """
    Calibrate MasterOperator on the normal window.
    Returns (M, mu_norm, fire_thresholds).
    """
    X_calib = X_panel[calib_mask]
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
        return M, np.ones(4), np.ones(4) * 2.0

    S_arr    = np.array(S_list)
    mu_norm  = np.maximum(S_arr.mean(0), MU_FLOOR)
    fire_thr = np.percentile(S_arr, FIRE_PCT, axis=0)

    print("  [4CH] Channel calibration (normal 2019):")
    for k_idx, name in CH_NAMES.items():
        print(f"    {name}: μ={mu_norm[k_idx]:.4f}  fire_thr={fire_thr[k_idx]:.4f}")
    return M, mu_norm, fire_thr


# ─────────────────────────────────────────────────────────────────────────────
#  FOUR-CHANNEL SWEEP
# ─────────────────────────────────────────────────────────────────────────────

def run_four_channel_sweep(
    X_panel:  np.ndarray,
    dates:    pd.DatetimeIndex,
    M,
    mu_norm:  np.ndarray,
    fire_thr: np.ndarray,
    stride:   int = 4,          # only print progress every N bars
) -> pd.DataFrame:
    """
    Compute δ_C/G/A/T and attributions a_k for every timestep.
    stride: for large hourly datasets, log progress every `stride*1000` bars.
    """
    T    = len(X_panel)
    bsdt = M.bsdt
    E    = M.energy
    keys = ['e_C','e_G','e_A','e_T','a_C','a_G','a_A','a_T',
            'fire_C','fire_G','fire_A','fire_T','dom_channel']
    buf  = {k: np.full(T, np.nan) for k in keys}

    t0   = time.time()
    step = max(1000 * stride, 1)
    for t in range(1, T):
        snap = Snapshot(
            X       = X_panel[t],
            X_prev  = X_panel[t - 1],
            history = X_panel[max(0, t - min(HIST_WIN, 20)):t],
        )
        try:
            S  = bsdt.channel_state(snap)
            buf['e_C'][t] = S[0]; buf['e_G'][t] = S[1]
            buf['e_A'][t] = S[2]; buf['e_T'][t] = S[3]

            S_norm = S / mu_norm
            a      = E.channel_attribution(S_norm)
            buf['a_C'][t] = a[0]; buf['a_G'][t] = a[1]
            buf['a_A'][t] = a[2]; buf['a_T'][t] = a[3]
            buf['dom_channel'][t] = float(np.argmax(a))

            buf['fire_C'][t] = float(S[0] > fire_thr[0])
            buf['fire_G'][t] = float(S[1] > fire_thr[1])
            buf['fire_A'][t] = float(S[2] > fire_thr[2])
            buf['fire_T'][t] = float(S[3] > fire_thr[3])
        except Exception:
            pass

        if t % step == 0:
            elapsed = time.time() - t0
            print(f"    {t:>6}/{T}  ({elapsed:.1f}s)")

    elapsed = time.time() - t0
    print(f"  [4CH] Sweep complete: {T:,} bars in {elapsed:.1f}s")

    idx = dates
    def _ff(arr, fill=0.0):
        return pd.Series(arr, index=idx).ffill().fillna(fill)

    return pd.DataFrame({k: _ff(buf[k]) for k in keys}, index=idx)


# ─────────────────────────────────────────────────────────────────────────────
#  CRISIS LEAD-TIME ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────

def _lead_hours(fire_col: pd.Series, onset: pd.Timestamp, window_h: int = 168 * 4):
    """Hours from first fire to onset within pre-onset window. None if never."""
    pre = fire_col[fire_col.index < onset].iloc[-window_h:]
    hits = pre[pre > 0.5]
    if hits.empty:
        return None
    delta = onset - hits.index[0]
    return int(delta.total_seconds() / 3600)


def analyse_crises(
    sig:    pd.DataFrame,
    dates:  pd.DatetimeIndex,
    normal_mask: np.ndarray,
) -> dict:
    results = {}
    print("\n── Crisis Attribution ──────────────────────────────────────────────")
    print("""
  Theoretical firing order:
    δ_T first → δ_G second → δ_A third → δ_C last
  If lead_T > lead_G > lead_A > lead_C → theory validated.
""")

    for ev_name, onset in EVENTS.items():
        if onset > dates[-1]:
            continue
        if onset > sig.index[-1]:
            continue

        # attribution at onset
        idx_on = int(sig.index.searchsorted(onset))
        idx_on = max(0, min(idx_on, len(sig) - 1))
        row    = sig.iloc[idx_on]
        att    = {c: round(float(row.get(f'a_{c}', np.nan)), 4)
                  for c in ('C','G','A','T')}
        dom    = f"a_{max(att, key=att.get)}"

        # lead times
        lead = {}
        for c in ('C','G','A','T'):
            lead[c] = _lead_hours(sig[f'fire_{c}'], onset)

        # pre-onset 48h mean attribution
        pre_win = sig[(sig.index >= onset - pd.Timedelta(hours=48))
                      & (sig.index < onset)]
        pre_mean = {c: round(float(pre_win[f'a_{c}'].mean()), 4)
                    if len(pre_win) > 0 else None
                    for c in ('C','G','A','T')}

        # check theory order from lead times
        ordered = sorted(
            [(c, lead[c]) for c in ('C','G','A','T') if lead[c] is not None],
            key=lambda x: -x[1]          # longest lead = fires earliest
        )
        theory_ok = ordered == sorted(ordered, key=lambda x: -x[1])

        firing_seq_str = " → ".join(
            f"δ_{c}({lead[c]}h)" for c, _ in ordered
        ) if ordered else "none"

        results[ev_name] = {
            "onset":                 str(onset.date()),
            "attribution_at_onset":  att,
            "dominant_channel":      dom,
            "lead_times_hours":      {c: lead[c] for c in ('C','G','A','T')},
            "firing_sequence":       firing_seq_str,
            "pre_48h_mean_attr":     pre_mean,
        }

        print(f"  ── {ev_name} ──")
        print(f"    Attribution at onset:  " +
              "  ".join(f"a_{c}={att[c]:.3f}" for c in ('C','G','A','T')))
        print(f"    Dominant channel:      {dom}")
        print(f"    Firing sequence:       {firing_seq_str}")
        print(f"    Pre-48h mean attr:     " +
              "  ".join(f"a_{c}={pre_mean[c]:.3f}" if pre_mean[c] is not None else f"a_{c}=None"
                        for c in ('C','G','A','T')))

    return results


# ─────────────────────────────────────────────────────────────────────────────
#  OMEGA BASELINE (from existing simulation — for direct comparison)
# ─────────────────────────────────────────────────────────────────────────────

def compute_omega_series(X_2d: np.ndarray, window: int = 168):
    T, N = X_2d.shape
    omega = np.zeros(T)
    for t in range(T):
        lo = max(0, t - window)
        wd = X_2d[lo:t + 1]
        if wd.shape[0] < 4 or N < 2:
            continue
        corr = np.corrcoef(wd.T)
        if not np.all(np.isfinite(corr)):
            corr = np.where(np.isfinite(corr), corr, 0.0)
            np.fill_diagonal(corr, 1.0)
        upper = corr[np.triu_indices(N, k=1)]
        rho   = float(np.mean(np.abs(upper)))
        ell   = float(np.mean(np.abs(X_2d[t])))
        W     = np.abs(corr)
        W_norm = W / (W.sum(1, keepdims=True) + 1e-12)
        lam   = float(np.linalg.eigvalsh(W_norm)[-1])
        omega[t] = rho * ell * lam
    return omega


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    Sep = "=" * 70
    print(Sep)
    print("  ERCOT — Four-Channel BSDT Simulation")
    print("  Using same engine as crypto v58 champion (MasterOperator, k=1)")
    print(Sep)

    # ── 1. Load data ─────────────────────────────────────────────────────────
    npz_path = DATA_DIR / "ercot_combined_hourly.npz"
    print(f"\n[1/4] Loading {npz_path.name}...")
    data = np.load(str(npz_path), allow_pickle=True)
    X_raw        = data['X']             # (T, 5)
    dates_raw    = data['dates']
    feature_names = list(data['feature_names'])
    event_onsets  = json.loads(str(data['event_onsets']))

    dates = pd.to_datetime(dates_raw)
    T_raw, N_agents = X_raw.shape
    print(f"  Shape: {X_raw.shape}  Agents: {feature_names}")
    print(f"  Date range: {dates[0].date()} → {dates[-1].date()}")

    normal_mask = np.array(dates.year == NORMAL_YEAR)
    print(f"  Normal period: {NORMAL_YEAR} ({normal_mask.sum()} hours)")

    # ── 2. Build multi-agent panel ───────────────────────────────────────────
    print(f"\n[2/4] Building multi-agent panel (N={N_agents}, d={N_FEAT})...")
    X_panel = build_ercot_agent_panel(X_raw, dates, normal_mask)
    print(f"  Panel shape: {X_panel.shape}  (T, N_agents, d_feat)")

    # ── 3. Calibrate on 2019 normal period ──────────────────────────────────
    print(f"\n[3/4] Calibrating MasterOperator (PCA_K={PCA_K})...")
    M, mu_norm, fire_thr = calibrate_four_channel(X_panel, normal_mask, k=PCA_K)

    # ── 4. Full four-channel sweep ───────────────────────────────────────────
    print(f"\n[4/4] Four-channel sweep ({T_raw:,} hours)...")
    sig = run_four_channel_sweep(X_panel, dates, M, mu_norm, fire_thr)

    # ── 5. Omega baseline for comparison ────────────────────────────────────
    print("\n── Omega baseline (existing ERCOT simulation) ──────────────────────")
    mu_std_raw  = X_raw[normal_mask].mean(0)
    sd_std_raw  = X_raw[normal_mask].std(0) + 1e-8
    X_std_raw   = (X_raw - mu_std_raw) / sd_std_raw
    X_std_raw   = np.nan_to_num(X_std_raw)
    omega       = compute_omega_series(X_std_raw, window=168)
    print(f"  Omega: mean={omega.mean():.4f}  p90={np.percentile(omega,90):.4f}"
          f"  max={omega.max():.4f}  pct>1={np.mean(omega>1)*100:.2f}%")

    # lead time comparison
    omega_s = pd.Series(omega, index=dates)
    print("\n  Omega lead times (threshold=0.5):")
    for ev_name, onset_str in event_onsets.items():
        onset = pd.Timestamp(onset_str)
        if onset > dates[-1]:
            continue
        omega_pre = omega_s[omega_s.index < onset].iloc[-168*4:]
        hits = omega_pre[omega_pre > 0.5]
        if hits.empty:
            print(f"    {ev_name}: never")
        else:
            lead_h = int((onset - hits.index[0]).total_seconds() / 3600)
            print(f"    {ev_name}: +{lead_h}h lead")

    # ── 6. Crisis analysis with four channels ────────────────────────────────
    crisis_results = analyse_crises(sig, dates, normal_mask)

    # ── 7. Full period stats ─────────────────────────────────────────────────
    print("\n── Full Period Statistics ──────────────────────────────────────────")
    for c in ('C','G','A','T'):
        s = sig[f'a_{c}'].dropna()
        print(f"  a_{c}: mean={s.mean():.3f}  p90={s.quantile(0.9):.3f}"
              f"  max={s.max():.3f}  fire_pct={sig[f'fire_{c}'].mean()*100:.1f}%")

    dom_dist = sig['dom_channel'].dropna().value_counts().sort_index()
    print("\n  Dominant channel distribution:")
    for ch_idx, cnt in dom_dist.items():
        print(f"    {CH_NAMES[int(ch_idx)]}: {int(cnt)} hours ({cnt/len(sig)*100:.1f}%)")

    # ── 8. Save ──────────────────────────────────────────────────────────────
    # downsample time series to daily for JSON compactness
    sig_daily  = sig.resample('D').mean()
    omega_daily = pd.Series(omega, index=dates).resample('D').mean()

    out = {
        "dataset":           "ercot_combined_hourly",
        "agents":            feature_names,
        "n_agents":          N_agents,
        "n_feat_per_agent":  N_FEAT,
        "date_range":        [str(dates[0].date()), str(dates[-1].date())],
        "normal_year":       NORMAL_YEAR,
        "pca_k":             PCA_K,
        "mu_norm":           mu_norm.tolist(),
        "fire_thresholds":   fire_thr.tolist(),
        "crisis_attribution": crisis_results,
        "channel_stats": {
            c: {
                "mean_attribution": round(float(sig[f'a_{c}'].mean()), 4),
                "p90_attribution":  round(float(sig[f'a_{c}'].quantile(0.9)), 4),
                "max_attribution":  round(float(sig[f'a_{c}'].max()), 4),
                "fire_pct":         round(float(sig[f'fire_{c}'].mean() * 100), 2),
            }
            for c in ('C','G','A','T')
        },
        "omega_baseline": {
            "mean":       round(float(omega.mean()), 4),
            "p90":        round(float(np.percentile(omega, 90)), 4),
            "max":        round(float(omega.max()), 4),
            "pct_above1": round(float(np.mean(omega > 1) * 100), 3),
        },
        "time_series_daily": {
            "dates":  [str(d)[:10] for d in sig_daily.index],
            "a_C":    [round(v, 4) for v in sig_daily['a_C'].fillna(0).tolist()],
            "a_G":    [round(v, 4) for v in sig_daily['a_G'].fillna(0).tolist()],
            "a_A":    [round(v, 4) for v in sig_daily['a_A'].fillna(0).tolist()],
            "a_T":    [round(v, 4) for v in sig_daily['a_T'].fillna(0).tolist()],
            "omega":  [round(v, 4) for v in omega_daily.fillna(0).tolist()],
            "dom_channel": [int(v) if not np.isnan(v) else -1
                            for v in sig_daily['dom_channel'].tolist()],
        },
    }

    out_path = OUT_DIR / "ercot_four_channel_results.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\n  Saved: {out_path.name}")
    print(Sep)
    return out


if __name__ == "__main__":
    main()
