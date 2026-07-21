"""
ERCOT Full Simulation — All Available Data
==========================================
Runs Omega = rho * ell * lambda_max(W) on every ERCOT dataset:

  Dataset 1: demand_hourly  (35064 x 5)  demand/weather features
  Dataset 2: supply_hourly  (35064 x 5)  energy sources (COUPLED AGENTS: wind/solar/gas/coal/nuclear)
  Dataset 3: combined_hourly(35064 x 10) all 10 features together
  Dataset 4: daily_2018_2022(1826  x 6)  daily aggregates

Events (2019-2022):
  COVID_Collapse     2020-03-23
  WinterStorm Uri    2021-02-10
  WinterStorm Elliott 2022-12-22
  SummerPeak 2019    2019-08-12

NOTE: supply_hourly is the physically correct dataset for Omega.
Wind/solar/gas/coal/nuclear are GENUINE coupled agents — they interact via
merit-order dispatch (wind up -> gas down; Uri: wind+gas BOTH down -> correlation
structure breaks -> Omega spikes). This is the correct multi-agent mechanism.
"""

import numpy as np
import pandas as pd
import json
import os

DATA_DIR = r"C:\amttp\data\ercot"
OUT_DIR  = r"C:\amttp\research\adaptive-friction\pipeline\results"


# ─────────────────────────────────────────────────────────────
#  CORE: Omega computation
# ─────────────────────────────────────────────────────────────
def compute_omega_series(X_2d, window=168):
    """
    X_2d : (T, N)  — T timesteps, N coupled agents
    Returns: omega (T,), above_cman (T,)

    Omega_t = rho_t * ell_t * lambda_max(W_norm)
      rho   = mean |pairwise correlation| in rolling window  (0..1)
      ell   = mean |x_i| at time t
      W_norm = row-normalised abs(corr_matrix)
      lambda_max(row-normalised W) = 1 by Perron-Frobenius when W is doubly-stochastic
      => Omega = 1 iff rho * ell >= 1
    """
    T, N = X_2d.shape
    omega = np.zeros(T)
    for t in range(T):
        lo = max(0, t - window)
        wd = X_2d[lo:t+1]
        if wd.shape[0] < 4 or N < 2:
            continue
        corr = np.corrcoef(wd.T)
        # Replace NaN/inf (e.g. from constant features) with 0; keep diagonal at 1
        if not np.all(np.isfinite(corr)):
            corr = np.where(np.isfinite(corr), corr, 0.0)
            np.fill_diagonal(corr, 1.0)
        upper = corr[np.triu_indices(N, k=1)]
        rho = float(np.mean(np.abs(upper)))
        ell = float(np.mean(np.abs(X_2d[t])))
        W = np.abs(corr)
        row_sums = W.sum(axis=1, keepdims=True) + 1e-12
        W_norm = W / row_sums
        lam_W = float(np.linalg.eigvalsh(W_norm)[-1])
        omega[t] = rho * ell * lam_W
    return omega, omega > 1.0


def omega_stats_table(omega, dates, events, normal_mask, label, window=168, step="h"):
    """Print comprehensive Omega stats for one dataset around all events."""
    print(f"\n  --- {label} ---")
    print(f"  Omega global stats:  min={omega.min():.4f}  "
          f"mean={omega.mean():.4f}  p90={np.percentile(omega,90):.4f}  "
          f"max={omega.max():.4f}")
    print(f"  Pct above C_man (Omega>1): {(omega>1.0).mean()*100:.2f}%")
    print(f"  Normal period Omega:  mean={omega[normal_mask].mean():.4f}  "
          f"max={omega[normal_mask].max():.4f}")

    print(f"\n  Early-warning lead-time per event:")
    print(f"  {'Event':>28}  {'Thr':>4}  {'FirstAlarm':>11}  {'Lead':>8}  {'HR':>6}  {'FAR':>6}")
    results = {}
    for ev_name, onset_dt in events.items():
        onset_idx = int(np.searchsorted(dates, onset_dt))
        # crisis window: onset to onset + 10 days
        if step == "h":
            crisis_end = min(len(omega), onset_idx + 240)
            pre_start  = max(0, onset_idx - window)  # same as window used
        else:
            crisis_end = min(len(omega), onset_idx + 30)
            pre_start  = max(0, onset_idx - 30)

        crisis_mask = np.zeros(len(omega), dtype=bool)
        crisis_mask[onset_idx:crisis_end] = True

        for thr in [0.5, 0.7, 0.9, 1.0]:
            alarm = omega > thr
            pre = np.where(alarm[:onset_idx])[0]
            if len(pre) == 0:
                print(f"  {ev_name:>28}  {thr:>4.1f}  {'never':>11}")
                continue
            first = int(pre[0])
            lead  = onset_idx - first
            lead_str = f"{lead:+d}{step}"
            hr   = float(alarm[crisis_mask].mean())
            far  = float(alarm[normal_mask].mean())
            alarm_date = str(dates[first])[:16] if hasattr(dates[first], 'strftime') else str(dates[first])
            print(f"  {ev_name:>28}  {thr:>4.1f}  {alarm_date:>11}  {lead_str:>8}  {hr:>6.3f}  {far:>6.3f}")

        # find Omega peak around the event
        ev_slice = slice(max(0, onset_idx - (window if step=='h' else 30)),
                         min(len(omega), onset_idx + (240 if step=='h' else 10)))
        peak_omega = omega[ev_slice].max()
        peak_offset = int(omega[ev_slice].argmax()) - (window if step=='h' else 30)
        print(f"  {'':>28}       peak_Omega={peak_omega:.4f} at onset{peak_offset:+d}{step}")
        results[ev_name] = {"peak_omega": float(peak_omega), "lead_offset": peak_offset}

    return results


# ─────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────
def print_omega_heatmap(omega, dates, events, window_days=30, step="h"):
    """Print a compact hour-by-hour Omega trace around each event."""
    hrs_per_step = 1 if step == "h" else 24
    window_steps = window_days * 24 // hrs_per_step
    print(f"\n  Omega trace around each event (±{window_days}d):")
    for ev_name, onset_dt in events.items():
        onset_idx = int(np.searchsorted(dates, onset_dt))
        lo = max(0, onset_idx - window_steps)
        hi = min(len(omega), onset_idx + window_steps // 2)
        ev_omega = omega[lo:hi]
        ev_dates = dates[lo:hi]
        peak_i = int(ev_omega.argmax())
        print(f"\n    {ev_name}  (onset={str(onset_dt)[:10]})")
        print(f"    {'Date':>16}  {'Offset':>8}  {'Omega':>8}  {'Cman':>6}")
        # Print every 24 steps (daily summary) for hourly data
        stride = 24 if step == "h" else 1
        for j in range(0, len(ev_omega), stride):
            offset = (lo + j) - onset_idx
            marker = " <<ONSET" if abs(offset) < stride else ""
            marker = " <<PEAK" if j == peak_i else marker
            print(f"    {str(ev_dates[j])[:16]:>16}  {offset:>+8}{step}  "
                  f"{ev_omega[j]:>8.4f}  {'***' if ev_omega[j]>1.0 else '   '}{marker}")


# ─────────────────────────────────────────────────────────────
#  DATASET RUNNERS
# ─────────────────────────────────────────────────────────────
def run_one_dataset(name, npz_path, window, step="h"):
    print(f"\n{'='*70}")
    print(f"ERCOT DATASET: {name}")
    print(f"{'='*70}")

    data = np.load(npz_path, allow_pickle=True)
    X_raw = data['X']
    dates_raw = data['dates']
    feature_names = list(data['feature_names'])
    event_onsets = json.loads(str(data['event_onsets']))
    y = data['y']

    T, d = X_raw.shape
    dates = pd.to_datetime(dates_raw)

    print(f"  Shape: {X_raw.shape}  Features: {feature_names}")
    print(f"  Date range: {dates[0].date()} -> {dates[-1].date()}")
    print(f"  y=1 (crisis) hours: {y.sum()} / {len(y)}  ({y.mean()*100:.1f}%)")

    # Normal period: all of 2019
    normal_mask = np.array(dates.year == 2019)
    print(f"  Normal period: 2019 ({normal_mask.sum()} {step})")

    # z-score on 2019
    mu = X_raw[normal_mask].mean(axis=0)
    sd = X_raw[normal_mask].std(axis=0) + 1e-8
    X_std = (X_raw - mu) / sd
    X_std = np.nan_to_num(X_std, nan=0.0)

    print(f"  Computing Omega (window={window}{step}, N_agents={d})...")
    omega, above_cman = compute_omega_series(X_std, window=window)
    print(f"  Done.  Omega range: [{omega.min():.4f}, {omega.max():.4f}]")

    # Parse events
    events = {k: pd.Timestamp(v) for k, v in event_onsets.items()}

    # Stats
    omega_stats_table(omega, dates, events, normal_mask, name, window_step=window, step=step)

    # Per-event Omega trace
    print_omega_heatmap(omega, dates, events, window_days=14, step=step)

    # Per-event period breakdown
    print(f"\n  Omega by period:")
    print(f"  {'Period':>30}  {'Mean':>8}  {'Max':>8}  {'%>0.5':>7}  {'%>1.0':>7}")
    periods = {
        "Normal 2019":          dates.year == 2019,
        "COVID onset Mar-2020": (dates.year==2020) & (dates.month.isin([3,4])),
        "Pre-Uri Jan-2021":     (dates.year==2021) & (dates.month==1),
        "Uri Feb-2021":         (dates.year==2021) & (dates.month==2),
        "Post-Uri 2021 H2":    (dates.year==2021) & (dates.month>=3),
        "Summer Peak 2022":    (dates.year==2022) & (dates.month.isin([7,8])),
        "Elliott Dec-2022":    (dates.year==2022) & (dates.month==12),
    }
    for p_name, mask in periods.items():
        mask = np.array(mask)
        if not mask.any():
            continue
        ow = omega[mask]
        print(f"  {p_name:>30}  {ow.mean():>8.4f}  {ow.max():>8.4f}  "
              f"{(ow>0.5).mean()*100:>7.1f}%  {(ow>1.0).mean()*100:>7.1f}%")

    return {
        "name": name,
        "shape": list(X_raw.shape),
        "features": feature_names,
        "omega_max": float(omega.max()),
        "omega_mean": float(omega.mean()),
        "omega_p90": float(np.percentile(omega, 90)),
        "pct_above_cman": float((omega > 1.0).mean()),
        "omega": omega.tolist(),
        "dates": [str(d) for d in dates],
        "y": y.tolist(),
        "events": {k: str(v) for k, v in events.items()},
        "normal_mask": normal_mask.tolist(),
    }


# Override omega_stats_table to accept window_step
def omega_stats_table(omega, dates, events, normal_mask, label, window_step=168, step="h"):
    print(f"\n  --- {label} ---")
    print(f"  Omega global:  min={omega.min():.4f}  "
          f"mean={omega.mean():.4f}  median={np.median(omega):.4f}  "
          f"p90={np.percentile(omega,90):.4f}  max={omega.max():.4f}")
    print(f"  Pct above C_man (Omega>1): {(omega>1.0).mean()*100:.3f}%")
    print(f"  Normal 2019:  Omega_mean={omega[normal_mask].mean():.4f}  "
          f"Omega_max={omega[normal_mask].max():.4f}")

    print(f"\n  Early-warning lead-time per event:")
    col_w = 28
    print(f"  {'Event':>{col_w}}  {'Thr':>4}  {'FirstAlarm':>18}  {'Lead':>8}  {'HR':>6}  {'FAR':>6}")

    results = {}
    for ev_name, onset_dt in events.items():
        onset_idx = int(np.searchsorted(dates, onset_dt))
        if step == "h":
            crisis_end = min(len(omega), onset_idx + 240)
        else:
            crisis_end = min(len(omega), onset_idx + 30)
        crisis_mask_ev = np.zeros(len(omega), dtype=bool)
        crisis_mask_ev[onset_idx:crisis_end] = True

        first_printed = False
        for thr in [0.5, 0.7, 0.9, 1.0]:
            alarm = omega > thr
            pre_of_event = np.where(alarm[:onset_idx])[0]
            if len(pre_of_event) == 0:
                ev_display = ev_name if not first_printed else ""
                print(f"  {ev_display:>{col_w}}  {thr:>4.1f}  {'never':>18}")
                first_printed = True
                continue
            first = int(pre_of_event[0])
            lead = onset_idx - first
            lead_str = f"{lead:+d}{step}"
            hr  = float(alarm[crisis_mask_ev].mean())
            far = float(alarm[normal_mask].mean())
            alarm_date = str(dates[first])[:19]
            ev_display = ev_name if not first_printed else ""
            print(f"  {ev_display:>{col_w}}  {thr:>4.1f}  {alarm_date:>18}  {lead_str:>8}  {hr:>6.3f}  {far:>6.3f}")
            first_printed = True

        # Peak Omega around the event
        lo = max(0, onset_idx - window_step)
        hi = min(len(omega), onset_idx + (240 if step=='h' else 30))
        peak_omega = omega[lo:hi].max() if hi > lo else 0.0
        peak_offset = int(omega[lo:hi].argmax()) - (onset_idx - lo)
        print(f"  {'':>{col_w}}       peak_Omega={peak_omega:.4f}  at onset{peak_offset:+d}{step}")
        results[ev_name] = {"peak_omega": float(peak_omega), "lead_offset": peak_offset}

    return results


# ─────────────────────────────────────────────────────────────
#  DAILY DATASET (different structure — 2018-2022, no event_onsets key)
# ─────────────────────────────────────────────────────────────
def run_daily_dataset():
    name = "daily_2018_2022"
    npz_path = os.path.join(DATA_DIR, "ercot_daily_2018_2022.npz")
    print(f"\n{'='*70}")
    print(f"ERCOT DATASET: {name}")
    print(f"{'='*70}")

    data = np.load(npz_path, allow_pickle=True)
    X_raw = data['X']
    dates_raw = data['dates']
    y = data['y']
    feature_names = list(data['feature_names'])

    T, d = X_raw.shape
    dates = pd.to_datetime(dates_raw)

    print(f"  Shape: {X_raw.shape}  Features: {feature_names}")
    print(f"  Date range: {dates[0].date()} -> {dates[-1].date()}")
    print(f"  y=1 days: {y.sum()} / {len(y)}  ({y.mean()*100:.1f}%)")

    # Events (daily resolution)
    events = {
        "COVID_Collapse 2020-03-23":  pd.Timestamp("2020-03-23"),
        "WinterStormUri 2021-02-10":  pd.Timestamp("2021-02-10"),
        "WinterStorm Elliott 2022-12-22": pd.Timestamp("2022-12-22"),
    }

    # Normal period: 2018 (before any events)
    normal_mask = np.array(dates.year == 2018)
    print(f"  Normal period: 2018 ({normal_mask.sum()} days)")

    # z-score on 2018
    mu = X_raw[normal_mask].mean(axis=0)
    sd = X_raw[normal_mask].std(axis=0) + 1e-8
    X_std = (X_raw - mu) / sd
    X_std = np.nan_to_num(X_std, nan=0.0)

    WINDOW = 30  # 30-day rolling
    print(f"  Computing Omega (window={WINDOW}d, N_features={d})...")
    omega, above_cman = compute_omega_series(X_std, window=WINDOW)
    print(f"  Done.  Omega range: [{omega.min():.4f}, {omega.max():.4f}]")

    print(f"\n  Omega global:  min={omega.min():.4f}  mean={omega.mean():.4f}  "
          f"p90={np.percentile(omega,90):.4f}  max={omega.max():.4f}")
    print(f"  Pct above C_man: {(omega>1.0).mean()*100:.3f}%")
    print(f"  Normal 2018: Omega_mean={omega[normal_mask].mean():.4f}  max={omega[normal_mask].max():.4f}")

    print(f"\n  Lead-time analysis (daily):")
    col_w = 32
    print(f"  {'Event':>{col_w}}  {'Thr':>4}  {'FirstAlarm':>12}  {'Lead(days)':>10}  {'HR':>6}  {'FAR':>6}")
    for ev_name, onset_dt in events.items():
        onset_idx = int(np.searchsorted(dates, onset_dt))
        crisis_end = min(len(omega), onset_idx + 30)
        crisis_mask_ev = np.zeros(len(omega), dtype=bool)
        crisis_mask_ev[onset_idx:crisis_end] = True
        first_printed = False
        for thr in [0.5, 0.7, 0.9, 1.0]:
            alarm = omega > thr
            pre = np.where(alarm[:onset_idx])[0]
            if len(pre) == 0:
                ev_d = ev_name if not first_printed else ""
                print(f"  {ev_d:>{col_w}}  {thr:>4.1f}  {'never':>12}")
                first_printed = True
                continue
            first  = int(pre[0])
            lead_d = onset_idx - first
            hr     = float(alarm[crisis_mask_ev].mean())
            far    = float(alarm[normal_mask].mean())
            ev_d   = ev_name if not first_printed else ""
            alarm_date = str(dates[first].date())
            print(f"  {ev_d:>{col_w}}  {thr:>4.1f}  {alarm_date:>12}  {lead_d:>10}  {hr:>6.3f}  {far:>6.3f}")
            first_printed = True
        lo = max(0, onset_idx - WINDOW)
        hi = min(len(omega), onset_idx + 30)
        peak = omega[lo:hi].max()
        print(f"  {'':>{col_w}}       peak_Omega={peak:.4f}")

    # Period breakdown
    print(f"\n  Omega by year/month:")
    print(f"  {'Period':>25}  {'Mean':>8}  {'Max':>8}  {'%>0.5':>7}  {'%>1.0':>7}")
    for yr in [2018, 2019, 2020, 2021, 2022]:
        mask = np.array(dates.year == yr)
        if not mask.any(): continue
        ow = omega[mask]
        print(f"  {str(yr):>25}  {ow.mean():>8.4f}  {ow.max():>8.4f}  "
              f"{(ow>0.5).mean()*100:>7.1f}%  {(ow>1.0).mean()*100:>7.1f}%")

    # Feb 2021 detail
    feb21 = np.array((dates.year == 2021) & (dates.month == 2))
    if feb21.any():
        print(f"\n  Feb 2021 (WinterStorm Uri) day-by-day Omega:")
        print(f"  {'Date':>12}  {'Omega':>8}  {'y':>4}  {'AboveCman':>10}")
        for i in np.where(feb21)[0]:
            print(f"  {str(dates[i].date()):>12}  {omega[i]:>8.4f}  {y[i]:>4}  "
                  f"{'***' if omega[i]>1.0 else ''}")

    return {
        "name": name,
        "omega_max": float(omega.max()),
        "omega_mean": float(omega.mean()),
        "omega_p90": float(np.percentile(omega, 90)),
        "pct_above_cman": float((omega > 1.0).mean()),
    }


# ─────────────────────────────────────────────────────────────
#  SUPPLY DEEP-DIVE: correlation regime analysis
# ─────────────────────────────────────────────────────────────
def supply_correlation_deep_dive():
    """
    For supply_hourly: print rolling correlation structure to show
    how merit-order coupling breaks down during crises.
    Wind-Gas anticorrelation -> both-fail positive-correlation during Uri.
    """
    print(f"\n{'='*70}")
    print("SUPPLY SOURCES: Correlation Regime Deep-Dive")
    print("Normal: wind&gas anticorrelate (displacement) => negative rho_WG")
    print("Uri:    both fail simultaneously => rho_WG flips positive")
    print("This breakdown of normal coupling IS the Omega signal")
    print(f"{'='*70}")

    data = np.load(os.path.join(DATA_DIR, "ercot_supply_hourly.npz"), allow_pickle=True)
    X_raw = data['X']
    dates_raw = data['dates']
    feat = list(data['feature_names'])  # wind_cf, solar_cf, gas_cf, coal_cf, nuclear_cf
    dates = pd.to_datetime(dates_raw)

    wind_i  = feat.index('wind_cf')
    gas_i   = feat.index('gas_cf')
    solar_i = feat.index('solar_cf')
    coal_i  = feat.index('coal_cf')

    normal_mask = np.array(dates.year == 2019)
    mu = X_raw[normal_mask].mean(axis=0)
    sd = X_raw[normal_mask].std(axis=0) + 1e-8
    X_std = (X_raw - mu) / sd
    X_std = np.nan_to_num(X_std, nan=0.0)

    # Rolling 7-day (168h) pairwise correlations
    WIN = 168
    pairs = [(wind_i, gas_i, "wind-gas"), (wind_i, solar_i, "wind-solar"),
             (gas_i, coal_i, "gas-coal"), (wind_i, coal_i, "wind-coal")]

    events = {
        "Normal 2019":       (dates.year == 2019),
        "COVID Mar-2020":    (dates.year==2020) & (dates.month==3),
        "Pre-Uri Jan 2021":  (dates.year==2021) & (dates.month==1),
        "Uri Feb 2021":      (dates.year==2021) & (dates.month==2),
        "Summer Peak 2022":  (dates.year==2022) & (dates.month.isin([7,8])),
        "Elliott Dec 2022":  (dates.year==2022) & (dates.month==12),
    }

    print(f"\n  Rolling 7-day pairwise source correlations by period:")
    header = f"  {'Period':>22}  {'n_hrs':>6}"
    for _, _, pname in pairs:
        header += f"  {pname:>12}"
    print(header)

    for p_name, pmask in events.items():
        pmask = np.array(pmask)
        if not pmask.any():
            continue
        idx = np.where(pmask)[0]
        # compute correlations on the raw capacity factors in this window
        Xp = X_raw[idx]
        if Xp.shape[0] < 10:
            continue
        row = f"  {p_name:>22}  {len(idx):>6}"
        for ia, ib, _ in pairs:
            r = np.corrcoef(Xp[:, ia], Xp[:, ib])[0, 1]
            row += f"  {r:>12.4f}"
        print(row)

    print(f"\n  Interpretation:")
    print(f"    wind-gas  < 0  in normal (merit-order — wind displaces gas)")
    print(f"    wind-gas  > 0  during Uri (BOTH supply sources fail together)")
    print(f"    This correlation-sign flip is the manifestation of Omega -> 1")
    print(f"    The abs(corr) matrix W changes structure: lambda_max(W) spikes")


# ─────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("ERCOT COMPREHENSIVE OMEGA SIMULATION")
    print("All available ERCOT datasets — Omega = rho * ell * lambda_max(W)")
    print()
    print("Datasets:")
    print("  1. demand_hourly  : 5 demand/weather features (ONE system)")
    print("  2. supply_hourly  : 5 energy sources — wind/solar/gas/coal/nuclear (COUPLED AGENTS)")
    print("  3. combined_hourly: 10 features (demand + supply)")
    print("  4. daily_2018_2022: 6 daily aggregates")
    print()
    print("Note: supply_hourly is physically most correct for Omega.")
    print("      Energy sources interact via merit-order dispatch,")
    print("      forming a genuine N=5 coupled agent network.")
    print()

    import time
    all_results = {}

    # ── 1. demand_hourly ──────────────────────────────────────
    t0 = time.time()
    all_results['demand'] = run_one_dataset(
        "demand_hourly (5 demand+weather features)",
        os.path.join(DATA_DIR, "ercot_demand_hourly.npz"),
        window=168, step="h"
    )
    print(f"\n  [demand elapsed: {time.time()-t0:.1f}s]")

    # ── 2. supply_hourly ─────────────────────────────────────
    t0 = time.time()
    all_results['supply'] = run_one_dataset(
        "supply_hourly (5 energy sources — COUPLED AGENTS)",
        os.path.join(DATA_DIR, "ercot_supply_hourly.npz"),
        window=168, step="h"
    )
    print(f"\n  [supply elapsed: {time.time()-t0:.1f}s]")

    # ── 3. combined_hourly ───────────────────────────────────
    t0 = time.time()
    all_results['combined'] = run_one_dataset(
        "combined_hourly (10 features: supply + demand)",
        os.path.join(DATA_DIR, "ercot_combined_hourly.npz"),
        window=168, step="h"
    )
    print(f"\n  [combined elapsed: {time.time()-t0:.1f}s]")

    # ── 4. daily_2018_2022 ───────────────────────────────────
    t0 = time.time()
    all_results['daily'] = run_daily_dataset()
    print(f"\n  [daily elapsed: {time.time()-t0:.1f}s]")

    # ── Supply correlation deep-dive ─────────────────────────
    supply_correlation_deep_dive()

    # ── Cross-dataset comparison table ───────────────────────
    print(f"\n{'='*70}")
    print("ERCOT CROSS-DATASET COMPARISON TABLE")
    print(f"{'='*70}")
    print(f"  {'Dataset':>40}  {'N':>3}  {'Omega_max':>10}  {'%>Cman':>8}  {'Omega_p90':>10}")
    for k, r in all_results.items():
        N = r['shape'][1] if 'shape' in r else '?'
        print(f"  {r['name']:>40}  {str(N):>3}  {r['omega_max']:>10.4f}  "
              f"{r['pct_above_cman']*100:>7.3f}%  {r['omega_p90']:>10.4f}")

    print(f"\n  Physical interpretation:")
    print(f"    demand_hourly : 5 features of ONE system")
    print(f"                    rho*ell*lambda small -> Omega < 1 expected")
    print(f"    supply_hourly : 5 COUPLED AGENTS (energy sources)")
    print(f"                    merit-order coupling -> genuine W matrix")
    print(f"                    Uri: wind+gas BOTH fail -> corr structure breaks")
    print(f"                    -> lambda_max(W) spikes -> Omega->1 possible")
    print(f"    combined      : 10 features, richer but mixed mechanism")
    print(f"    daily         : 6 features, demand-side, coarser grain")

    # Save
    # Remove large lists for JSON
    save_results = {}
    for k, r in all_results.items():
        sr = {kk: vv for kk, vv in r.items() if kk not in ('omega', 'dates', 'y', 'normal_mask')}
        save_results[k] = sr

    out_path = os.path.join(OUT_DIR, "ercot_omega_full_results.json")
    with open(out_path, 'w') as f:
        json.dump(save_results, f, indent=2)
    print(f"\n  Results saved to: {out_path}")
    print("\nDone.")
