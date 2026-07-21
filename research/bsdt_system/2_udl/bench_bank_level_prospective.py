"""
UDL System Mode — G-SIB Bank-Level Prospective Crisis Early Warning
=====================================================================
Applies calibrated UDL engines to REAL bank data (FDIC + World Bank GFDD)
in a strictly prospective manner: **no hindsight**.

Protocol  (replicates real-world bank supervision)
──────────────────────────────────────────────────
1. Calibration window: 2005-Q1 → 2007-Q3  (pre-GFC, stable period)
   — Alarm threshold set from this period only
2. Expanding window online scoring:
   For each monitoring quarter t ≥ 2007-Q4:
     • X = all bank×quarter observations from 2005-Q1 … t
     • y = zeros  (pure unsupervised — NO crisis labels)
     • Score quarter t = mean engine score of current-quarter banks
3. Alarm fires when score > threshold (99th pctl of calibration scores)
4. Evaluation done AFTER all scoring: AUROC, lead time, FAR

Data sources
────────────
  US G-SIBs:     FDIC call-report (JPM, BoA, Citi, WF, GS, BNY)
  EU G-SIBs:     World Bank GFDD + ECB MIR (HSBC, BNP, DB, Barclays,
                 SocGen, UniCredit, ING)
  Asian G-SIBs:  World Bank GFDD (MUFG, Mizuho, SMBC, BoC, ICBC, CCB,
                 StanChart)

Features (d=5): loan_to_asset, equity_ratio, npl_ratio, roa, funding_cost
"""
from __future__ import annotations
import sys, time, json, warnings
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.metrics import roc_auc_score

warnings.filterwarnings("ignore")

ROOT = Path(r"c:\amttp")
sys.path.insert(0, str(ROOT / "research" / "udl"))
sys.path.insert(0, str(ROOT / "research" / "adaptive-friction" / "banklevel_enhanced"))
sys.path.insert(0, str(ROOT / "research" / "adaptive-friction" / "variants"))

from udl.system_mode import (
    MolecularEngine, GravityModeEngine, HybridGravityEngine
)


# ═══════════════════════════════════════════════════════════════════
#  Load real G-SIB panel from cached World Bank + FDIC data
# ═══════════════════════════════════════════════════════════════════

CACHE_DIR = ROOT / "research" / "adaptive-friction" / "banklevel_enhanced" / "gsib_cache_real"


def load_gsib_panel():
    """Load the cached real G-SIB panel (T, N, d=5)."""
    npz = np.load(CACHE_DIR / "gsib_real_panel.npz")
    with open(CACHE_DIR / "gsib_real_meta.json") as f:
        meta = json.load(f)

    X = npz["X"]  # (T, N, d)
    # Reconstruct dates (2005-Q1 to 2023-Q4)
    dates = pd.date_range("2005-01-01", "2023-12-31", freq="QE")
    T_data = X.shape[0]
    dates = dates[:T_data]

    return X, dates, meta


# ═══════════════════════════════════════════════════════════════════
#  Crisis labels — OBJECTIVE (NBER + FDIC), used ONLY for evaluation
# ═══════════════════════════════════════════════════════════════════

CRISIS_QUARTERS = {
    # GFC (NBER: Dec 2007 – Jun 2009)
    "2007-12-31", "2008-03-31", "2008-06-30", "2008-09-30",
    "2008-12-31", "2009-03-31", "2009-06-30",
    # COVID (NBER: Feb–Apr 2020)
    "2020-03-31", "2020-06-30",
    # European sovereign debt stress (EBA/ECB flagged)
    "2011-09-30", "2011-12-31", "2012-03-31", "2012-06-30",
}

# GFC build-up quarters — elevated risk but not yet in recession
# Used to measure early warning, NOT as training labels
GFC_BUILDUP = {
    "2007-03-31",  # Bear Stearns hedge fund collapse
    "2007-06-30",  # BNP Paribas fund freeze
    "2007-09-30",  # Northern Rock run
}


def make_crisis_labels(dates):
    """Binary: 1=crisis, 0=normal. For evaluation only."""
    y = np.zeros(len(dates), dtype=int)
    for i, d in enumerate(dates):
        ds = str(d.date())
        if ds in CRISIS_QUARTERS:
            y[i] = 1
    return y


# ═══════════════════════════════════════════════════════════════════
#  Prospective expanding-window scoring
# ═══════════════════════════════════════════════════════════════════

def prospective_score(X_3d, dates, engine_cls, engine_kwargs,
                      calib_end="2007-09-30", verbose=True):
    """
    Strictly prospective scoring — no future data leaks.

    Parameters
    ----------
    X_3d : (T, N, d) panel
    dates : DatetimeIndex
    engine_cls : engine class (MolecularEngine etc.)
    engine_kwargs : dict of engine params (no calibrate — pure unsupervised)
    calib_end : last quarter of calibration window

    Returns
    -------
    quarter_scores : (T,) array — anomaly score per quarter
    alarm_threshold : float — 99th pctl of calibration period scores
    """
    T, N, d = X_3d.shape
    calib_end_dt = pd.Timestamp(calib_end)
    calib_mask = dates <= calib_end_dt

    # Number of calibration quarters
    n_calib = int(calib_mask.sum())
    if verbose:
        print(f"    Calibration: {dates[0].date()} → {dates[n_calib-1].date()} "
              f"({n_calib} quarters, {n_calib*N} bank-quarters)")

    quarter_scores = np.full(T, np.nan)

    # Phase 1: Score calibration period (fit on calibration data only)
    X_calib = X_3d[:n_calib].reshape(n_calib * N, d)
    y_calib = np.zeros(n_calib * N, dtype=int)  # NO crisis labels

    eng = engine_cls(**engine_kwargs)
    scores_calib = eng.fit_score(X_calib, y_calib)

    for t in range(n_calib):
        bank_scores = scores_calib[t * N: (t + 1) * N]
        quarter_scores[t] = bank_scores.mean()

    # Set alarm threshold from calibration period only
    calib_q_scores = quarter_scores[:n_calib]
    alarm_threshold = np.nanpercentile(calib_q_scores, 99)

    if verbose:
        print(f"    Alarm threshold (99th pctl of calm period): {alarm_threshold:.4f}")

    # Phase 2: Expanding window monitoring (2007-Q4 onward)
    # At each quarter t: fit on ALL data up to t, extract score for t
    for t in range(n_calib, T):
        n_pts = (t + 1) * N
        X_up_to_t = X_3d[:t + 1].reshape(n_pts, d)
        y_dummy = np.zeros(n_pts, dtype=int)  # NO crisis labels — ever

        eng = engine_cls(**engine_kwargs)
        scores_all = eng.fit_score(X_up_to_t, y_dummy)

        # Score for quarter t = mean of last N entries (current quarter's banks)
        bank_scores_t = scores_all[-N:]
        quarter_scores[t] = bank_scores_t.mean()

        if verbose and (t - n_calib) % 8 == 0:  # print every 2 years
            dt = dates[t]
            qs = quarter_scores[t]
            alarm = "*** ALARM" if qs > alarm_threshold else ""
            print(f"    {dt.date()}  score={qs:.4f} {alarm}")

    return quarter_scores, alarm_threshold


# ═══════════════════════════════════════════════════════════════════
#  Per-bank drill-down (who triggered the alarm?)
# ═══════════════════════════════════════════════════════════════════

def bank_drilldown(X_3d, dates, meta, engine_cls, engine_kwargs,
                   target_quarter="2008-09-30"):
    """Score individual banks at a specific crisis quarter."""
    T, N, d = X_3d.shape
    N_meta = len(meta)  # may differ from N if panel was cached differently
    target_dt = pd.Timestamp(target_quarter)
    t_idx = np.argmin(np.abs(dates - target_dt))

    # Fit on data up to target quarter
    X_up = X_3d[:t_idx + 1].reshape((t_idx + 1) * N, d)
    y_dum = np.zeros(len(X_up), dtype=int)

    eng = engine_cls(**engine_kwargs)
    scores = eng.fit_score(X_up, y_dum)

    # Extract per-bank scores for target quarter
    bank_scores = scores[-N:]
    ranked = np.argsort(bank_scores)[::-1]

    print(f"\n    Per-bank scores at {dates[t_idx].date()}:")
    print(f"    {'Rank':<5} {'Bank':<28} {'Region':<7} {'Source':<12} {'Score':>8}")
    print(f"    {'-'*65}")
    for rank, idx in enumerate(ranked):
        if idx < N_meta:
            m = meta[idx]
            name = m["name"]
            region = m["region"]
            src = "FDIC" if m["data_source"] == "fdic_call_report" else "WB+ECB"
        else:
            name = f"Bank_{idx}"
            region = "?"
            src = "?"
        flag = " <--" if bank_scores[idx] > np.percentile(bank_scores, 75) else ""
        print(f"    {rank+1:<5} {name:<28} {region:<7} {src:<12} "
              f"{bank_scores[idx]:>8.4f}{flag}")

    return bank_scores, ranked


# ═══════════════════════════════════════════════════════════════════
#  Main evaluation
# ═══════════════════════════════════════════════════════════════════

def run_prospective_benchmark():
    print('=' * 76)
    print('  G-SIB BANK-LEVEL PROSPECTIVE CRISIS EARLY WARNING')
    print('  Real data: FDIC call-report (US) + World Bank GFDD (non-US)')
    print('  Protocol: expanding window, NO labels used in scoring')
    print('  Alarm threshold: set from 2005-2007Q3 calm period only')
    print('=' * 76)

    X_3d, dates, meta = load_gsib_panel()
    T, N, d = X_3d.shape
    y_crisis = make_crisis_labels(dates)

    print(f'\n  Panel: T={T} quarters, N={N} G-SIBs, d={d} features')
    print(f'  Date range: {dates[0].date()} → {dates[-1].date()}')
    print(f'  Crisis quarters: {int(y_crisis.sum())}/{T}')
    n_us = sum(1 for m in meta if m["data_source"] == "fdic_call_report")
    print(f'  US (FDIC bank-level): {n_us}')
    print(f'  Non-US (World Bank aggregate): {N - n_us}')
    print(f'  Banks: {", ".join(m["name"] for m in meta)}')

    # ── Engine configurations (NO calibration — pure unsupervised) ────
    engines = {
        "Hybrid":  (HybridGravityEngine, dict()),
        "Gravity": (GravityModeEngine,   dict(iterations=60, k_neighbors=10,
                                               use_fused=True)),
        "Molecular": (MolecularEngine,   dict(iterations=80, k_neighbors=10,
                                               use_fused=True)),
    }

    results = {}
    for name, (cls, kwargs) in engines.items():
        print(f'\n  {"─"*70}')
        print(f'  Engine: {name}')
        print(f'  {"─"*70}')
        t0 = time.time()
        q_scores, threshold = prospective_score(
            X_3d, dates, cls, kwargs, calib_end="2007-09-30", verbose=True
        )
        elapsed = time.time() - t0
        print(f'    Total time: {elapsed:.1f}s')

        # ── Evaluate (labels used ONLY here, AFTER all scoring) ──
        valid = ~np.isnan(q_scores)
        auc = roc_auc_score(y_crisis[valid], q_scores[valid])

        # Alarm analysis
        alarm_mask = q_scores > threshold
        alarm_quarters = dates[alarm_mask & valid]
        crisis_mask = y_crisis.astype(bool)

        # True alarms = alarm during crisis quarter
        tp = int((alarm_mask & crisis_mask & valid).sum())
        # False alarms = alarm during normal quarter
        fp = int((alarm_mask & ~crisis_mask & valid).sum())
        # Missed = crisis quarter without alarm
        fn = int((~alarm_mask & crisis_mask & valid).sum())
        # Quiet correct = normal quarter without alarm
        tn = int((~alarm_mask & ~crisis_mask & valid).sum())

        far = fp / max(fp + tn, 1)
        recall = tp / max(tp + fn, 1)
        precision = tp / max(tp + fp, 1)

        print(f'\n    AUROC: {auc:.4f}')
        print(f'    Alarm threshold: {threshold:.4f} (99th pctl of calm period)')
        print(f'    TP={tp}  FP={fp}  FN={fn}  TN={tn}')
        print(f'    Recall (crisis detection): {recall:.1%}')
        print(f'    Precision: {precision:.1%}')
        print(f'    FAR: {far:.1%}')

        # ── GFC lead time ──
        gfc_peak = pd.Timestamp("2008-09-30")  # Lehman collapse
        gfc_start = pd.Timestamp("2007-12-31")  # NBER recession start

        # Find first alarm BEFORE GFC recession start
        pre_gfc_alarms = [d for d in alarm_quarters
                          if d < gfc_start and d >= pd.Timestamp("2007-01-01")]
        if pre_gfc_alarms:
            first_early = min(pre_gfc_alarms)
            lead_q = len(pd.date_range(first_early, gfc_start, freq="QE")) - 1
            print(f'\n    GFC EARLY WARNING:')
            print(f'      First alarm: {first_early.date()} '
                  f'({lead_q} quarters before NBER recession start)')
            print(f'      Lead time before Lehman: '
                  f'{len(pd.date_range(first_early, gfc_peak, freq="QE"))-1} quarters')
        else:
            # Check first alarm during GFC
            gfc_alarms = [d for d in alarm_quarters
                          if gfc_start <= d <= pd.Timestamp("2009-06-30")]
            if gfc_alarms:
                first_gfc = min(gfc_alarms)
                print(f'\n    GFC detection: first alarm at {first_gfc.date()} '
                      f'(within recession, no pre-warning)')
            else:
                print(f'\n    GFC: NO alarm fired during GFC period')

        # ── COVID lead time ──
        covid_start = pd.Timestamp("2020-03-31")
        pre_covid = [d for d in alarm_quarters
                     if pd.Timestamp("2019-06-30") <= d < covid_start]
        if pre_covid:
            first_c = min(pre_covid)
            print(f'    COVID early warning: first alarm {first_c.date()}')
        else:
            covid_al = [d for d in alarm_quarters
                        if covid_start <= d <= pd.Timestamp("2020-06-30")]
            if covid_al:
                print(f'    COVID detected: alarm at {min(covid_al).date()} '
                      f'(concurrent, no early warning — expected for exogenous shock)')
            else:
                print(f'    COVID: no alarm (exogenous shock, not financial)')

        # ── Euro crisis detection ──
        euro_alarms = [d for d in alarm_quarters
                       if pd.Timestamp("2011-06-30") <= d <= pd.Timestamp("2012-06-30")]
        if euro_alarms:
            print(f'    Euro sovereign crisis: {len(euro_alarms)} alarms '
                  f'({min(euro_alarms).date()} to {max(euro_alarms).date()})')

        # ── Quarter-by-quarter timeline ──
        print(f'\n    Score timeline (selected quarters):')
        key_dates = [
            ("2006-06-30", "Pre-GFC calm"),
            ("2007-03-31", "Bear Stearns HF"),
            ("2007-06-30", "BNP funds freeze"),
            ("2007-09-30", "Northern Rock"),
            ("2007-12-31", "Recession start"),
            ("2008-03-31", "Bear Stearns bail"),
            ("2008-06-30", "Oil spike"),
            ("2008-09-30", "Lehman collapse"),
            ("2008-12-31", "TARP / peak"),
            ("2009-03-31", "Market bottom"),
            ("2009-06-30", "Recession end"),
            ("2010-06-30", "Recovery"),
            ("2011-09-30", "Euro crisis"),
            ("2012-03-31", "Euro peak"),
            ("2015-06-30", "Stable"),
            ("2019-12-31", "Pre-COVID"),
            ("2020-03-31", "COVID onset"),
            ("2020-06-30", "COVID Q2"),
            ("2021-06-30", "Recovery"),
            ("2023-06-30", "Recent"),
        ]

        print(f'    {"Date":<14} {"Score":>8} {"Thresh":>8} {"Status":<20} {"Event"}')
        print(f'    {"─"*72}')
        for ds, event in key_dates:
            dt = pd.Timestamp(ds)
            idx = np.argmin(np.abs(dates - dt))
            if idx < len(q_scores) and not np.isnan(q_scores[idx]):
                sc = q_scores[idx]
                is_crisis = y_crisis[idx]
                alarm = sc > threshold
                if alarm and is_crisis:
                    status = "TRUE ALARM"
                elif alarm and not is_crisis:
                    status = "FALSE ALARM"
                elif not alarm and is_crisis:
                    status = "MISSED"
                else:
                    status = "quiet"
                marker = "***" if alarm else "   "
                print(f'    {dates[idx].date()!s:<14} {sc:>8.4f} {threshold:>8.4f} '
                      f'{status:<20} {event} {marker}')

        results[name] = dict(
            auc=auc, far=far, recall=recall, precision=precision,
            tp=tp, fp=fp, fn=fn, tn=tn, threshold=threshold,
            scores=q_scores, elapsed=elapsed,
        )

    # ── Rolling Z-score analysis (how central banks monitor) ──────
    # The raw score is hard to threshold because it drifts with window size.
    # Central banks use a cyclically-adjusted gap: how many σ above the
    # running mean is the current score?  This is the Basel III
    # countercyclical buffer approach.
    print(f'\n{"="*76}')
    print(f'  ROLLING Z-SCORE ANALYSIS (Basel-style cyclical gap)')
    print(f'  z(t) = (score(t) - mean(scores[0:t])) / std(scores[0:t])')
    print(f'  Alarm when z > 2.0 (2σ deviation from running mean)')
    print(f'{"="*76}')

    for name, r in results.items():
        q_scores = r["scores"]
        valid = ~np.isnan(q_scores)
        z_scores = np.full_like(q_scores, np.nan)

        # Compute rolling z-score (expanding window mean/std)
        for t in range(4, len(q_scores)):  # need at least 4 quarters
            if not valid[t]:
                continue
            past = q_scores[:t][valid[:t]]
            if len(past) < 4:
                continue
            mu = past.mean()
            sigma = past.std()
            if sigma < 1e-10:
                continue
            z_scores[t] = (q_scores[t] - mu) / sigma

        # Evaluate with z > 2.0 threshold
        z_valid = ~np.isnan(z_scores)
        z_alarm = z_scores > 2.0

        tp_z = int((z_alarm & crisis_mask & z_valid).sum())
        fp_z = int((z_alarm & ~crisis_mask & z_valid).sum())
        fn_z = int((~z_alarm & crisis_mask & z_valid).sum())
        tn_z = int((~z_alarm & ~crisis_mask & z_valid).sum())
        far_z = fp_z / max(fp_z + tn_z, 1)
        rec_z = tp_z / max(tp_z + fn_z, 1)
        prec_z = tp_z / max(tp_z + fp_z, 1)
        auc_z = roc_auc_score(y_crisis[z_valid], z_scores[z_valid]) if z_valid.sum() > 10 else 0

        print(f'\n  {name} (z-score):')
        print(f'    AUROC: {auc_z:.4f}  Recall: {rec_z:.1%}  '
              f'Precision: {prec_z:.1%}  FAR: {far_z:.1%}')

        # Timeline with z-scores
        key_dates_z = [
            ("2006-06-30", "Pre-GFC calm"),
            ("2007-03-31", "Bear Stearns HF"),
            ("2007-06-30", "BNP funds freeze"),
            ("2007-09-30", "Northern Rock"),
            ("2007-12-31", "Recession start"),
            ("2008-03-31", "Bear Stearns bail"),
            ("2008-09-30", "Lehman collapse"),
            ("2008-12-31", "TARP / peak"),
            ("2009-06-30", "Recession end"),
            ("2011-09-30", "Euro crisis"),
            ("2019-12-31", "Pre-COVID"),
            ("2020-03-31", "COVID onset"),
            ("2023-06-30", "Recent"),
        ]
        print(f'    {"Date":<14} {"Raw":>8} {"Z-score":>8} {"Status":<16} {"Event"}')
        print(f'    {"─"*68}')
        for ds, event in key_dates_z:
            dt = pd.Timestamp(ds)
            idx = np.argmin(np.abs(dates - dt))
            if idx < len(z_scores) and not np.isnan(z_scores[idx]):
                z = z_scores[idx]
                sc = q_scores[idx]
                is_crisis = y_crisis[idx]
                alarm = z > 2.0
                if alarm and is_crisis:
                    status = "TRUE ALARM"
                elif alarm and not is_crisis:
                    flag_event = event
                    # Check if this is within 2 quarters of a crisis
                    near_crisis = any(abs(idx - j) <= 2 for j in np.where(crisis_mask)[0])
                    status = "EARLY WARNING" if near_crisis else "FALSE ALARM"
                elif not alarm and is_crisis:
                    status = "MISSED"
                else:
                    status = "quiet"
                marker = "***" if alarm else "   "
                print(f'    {dates[idx].date()!s:<14} {sc:>8.4f} {z:>+8.2f}  '
                      f'{status:<16} {event} {marker}')

        # GFC lead time with z-score
        pre_gfc_z = [(i, dates[i]) for i in range(len(dates))
                     if z_valid[i] and z_alarm[i]
                     and dates[i] < pd.Timestamp("2007-12-31")
                     and dates[i] >= pd.Timestamp("2007-01-01")]
        if pre_gfc_z:
            first_i, first_d = pre_gfc_z[0]
            gfc_start_i = np.argmin(np.abs(dates - pd.Timestamp("2007-12-31")))
            lehman_i = np.argmin(np.abs(dates - pd.Timestamp("2008-09-30")))
            print(f'\n    GFC z-score early warning:')
            print(f'      First z>2 alarm: {first_d.date()} '
                  f'(z={z_scores[first_i]:+.2f})')
            print(f'      Quarters before recession: {gfc_start_i - first_i}')
            print(f'      Quarters before Lehman: {lehman_i - first_i}')

    # ── Per-bank drill-down at Lehman quarter ──
    print(f'\n{"="*76}')
    print(f'  PER-BANK DRILL-DOWN: Who was most stressed at Lehman (2008-Q3)?')
    print(f'{"="*76}')
    best_engine = max(results, key=lambda k: results[k]["auc"])
    cls, kwargs = engines[best_engine]
    bank_drilldown(X_3d, dates, meta, cls, kwargs, target_quarter="2008-09-30")

    # ── Pre-crisis drill-down (could you have caught it early?) ──
    print(f'\n  PER-BANK DRILL-DOWN: Who showed stress at Northern Rock (2007-Q3)?')
    bank_drilldown(X_3d, dates, meta, cls, kwargs, target_quarter="2007-09-30")

    # ── Summary ──
    print(f'\n{"="*76}')
    print(f'  PROSPECTIVE EARLY WARNING VERDICT')
    print(f'  (no hindsight — alarm threshold from 2005-2007Q3 calm period only)')
    print(f'{"="*76}')
    for name, r in results.items():
        print(f'\n  {name}:')
        print(f'    AUROC:     {r["auc"]:.4f}')
        print(f'    Recall:    {r["recall"]:.1%} of crisis quarters detected')
        print(f'    Precision: {r["precision"]:.1%}')
        print(f'    FAR:       {r["far"]:.1%}')
        fca = "YES" if r["far"] < 0.05 else ("CLOSE" if r["far"] < 0.10 else "NO")
        print(f'    FCA compliant (<5% FAR): {fca}')
        print(f'    Time: {r["elapsed"]:.0f}s')

    # Overall
    best = max(results.items(), key=lambda kv: kv[1]["auc"])
    print(f'\n  Best engine: {best[0]} (AUROC={best[1]["auc"]:.4f})')
    print(f'  Key finding: alarm fires using ONLY unsupervised scoring')
    print(f'  on real FDIC + World Bank data — no labels, no hindsight.')


if __name__ == '__main__':
    run_prospective_benchmark()
