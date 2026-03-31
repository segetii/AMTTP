#!/usr/bin/env python3
"""
UDL Law-Domain Projection + Frozen Window Geometry Scoring
===========================================================
Real-world demonstration on two financial infrastructure datasets:

  DATASET 1 — FDIC/G-SIB BANK DATA (Quarterly, 1994-2022)
    30 US/Global banks (FDIC SDI call-report + World Bank GFDD)
    Features: loan_to_asset, equity_ratio, npl_ratio, roa, funding_cost
    Anomalies: GFC (2007-2009), COVID (2020), Rate Shock (2022)

  DATASET 2 — ERCOT POWER GRID DATA (Daily, 2018-2022)
    Texas electric grid (synthetic-real: uses ERCOT published statistics)
    Features: system_load_GW, hub_price_MWh, wind_fraction, freq_dev_Hz,
              forced_outage_pct, temperature_F, load_forecast_err_pct
    Anomalies: Winter Storm Uri (Feb 10-20 2021), COVID demand drop (Mar 2020)

PIPELINE (for both datasets):
  Step 1 : Raw data → UDLPostSimScorer (law-domain projection)
             - PhaseCurveSpectrum   (sequential trajectory)
             - TopologicalSpectrum  (intrinsic geometry / LID)
             - KernelRKHSSpectrum   (nonlinear manifold deviation)
             - RankOrderSpectrum    (distribution-free extremity)
  Step 2 : UDL tensor → FrozenWindowScorer (geometry + trig)
             - FrozenWindow         (unsupervised)
             - FW+Friction          (adaptive friction)
             - FW+ExpoGate          (supervised gating)
             - FW+SignedLR          (logistic regression)
             - FW+QuadSurf          (quadratic surface)

Author: Odeyemi Olusegun Israel — AMTTP/UDL Project
"""

import sys, os, time, warnings
sys.path.insert(0, r'c:\amttp\research\udl')
os.environ['CUDA_VISIBLE_DEVICES'] = ''
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
warnings.filterwarnings('ignore')

import numpy as np
import json
from pathlib import Path
from sklearn.metrics import roc_auc_score

ROOT = Path(r'c:\amttp')
RESULTS_DIR = ROOT / 'results' / 'udl_bank_ercot'
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


# ══════════════════════════════════════════════════════════════════════════════
#  UTILITIES
# ══════════════════════════════════════════════════════════════════════════════

def op_metrics(y_true, scores):
    """Compute operational anomaly-detection metrics."""
    if len(np.unique(y_true)) < 2:
        return dict(auc=0.5, f1=0.0, prec=0.0, recall=0.0,
                    fpr=0.0, fnr=1.0, tp=0, fn=int(y_true.sum()), fp=0, tn=int((1-y_true).sum()))
    thr = float(np.percentile(scores, 100 * (1 - y_true.mean())))
    y_pred = (scores > thr).astype(int)
    tp  = int(((y_true == 1) & (y_pred == 1)).sum())
    fn  = int(((y_true == 1) & (y_pred == 0)).sum())
    fp  = int(((y_true == 0) & (y_pred == 1)).sum())
    tn  = int(((y_true == 0) & (y_pred == 0)).sum())
    auc = roc_auc_score(y_true, scores)
    fpr = fp / max(fp + tn, 1)
    fnr = fn / max(fn + tp, 1)
    prec   = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    f1     = 2 * prec * recall / max(prec + recall, 1e-10)
    return dict(auc=auc, f1=f1, prec=prec, recall=recall,
                fpr=fpr, fnr=fnr, tp=tp, fn=fn, fp=fp, tn=tn)


def print_banner(text):
    print('\n' + '=' * 76)
    print(f'  {text}')
    print('=' * 76)


def print_results(results, label=''):
    if label:
        print(f'\n  {label}')
    hdr = (f"    {'Engine':<18} {'AUC':>6} {'F1':>6} {'Prec':>6} "
           f"{'Recall':>7} {'FPR':>7} {'Time':>7} {'TP/Total':>10}")
    print(hdr)
    print('    ' + '-' * 76)
    for eng, m in results.items():
        caught = f"{m['tp']}/{m['tp']+m['fn']}"
        print(f"    {eng:<18} {m['auc']:6.4f} {m['f1']:6.3f} {m['prec']:6.3f}"
              f" {m['recall']:7.3f} {m['fpr']:7.4f} {m.get('time',0):6.2f}s {caught:>10}")
    print('    ' + '-' * 76)


# ══════════════════════════════════════════════════════════════════════════════
#  FULL UDL + FROZEN WINDOW PIPELINE
# ══════════════════════════════════════════════════════════════════════════════

def run_udl_pipeline(X_train, y_train, X_test, y_test,
                     dataset_name='data', verbose=True):
    """
    Full pipeline:
      1. Project through UDL law-domain operators (Step 1)
      2. Score with FrozenWindowScorer variants (Step 2)

    Parameters
    ----------
    X_train : (N_train, d) float64  — training data
    y_train : (N_train,)  int       — 0=normal, 1=anomaly (for supervised variants)
    X_test  : (N_test, d) float64   — test data
    y_test  : (N_test,)   int       — ground truth labels
    """
    from geo_full_pipeline import FrozenWindowScorer
    from udl.system_mode import UDLPostSimScorer

    X_normal = X_train[y_train == 0]
    print(f"\n  [{dataset_name}] UDL Law-Domain Projection:")
    print(f"    Train normals: {len(X_normal):,} | Train total: {len(X_train):,} | Test: {len(X_test):,}")
    print(f"    Raw feature dim: {X_train.shape[1]}")

    # ── Step 1: Project into mathematical law domains ─────────────────────
    t0 = time.perf_counter()
    udl = UDLPostSimScorer(k=min(15, len(X_normal)-1), max_dim=12, n_components=8)
    udl.fit(X_normal)
    X_train_udl = udl.transform(X_train)
    X_test_udl  = udl.transform(X_test)
    X_normal_udl = X_train_udl[y_train == 0]
    dt_proj = time.perf_counter() - t0
    print(f"    UDL tensor dim: {X_train_udl.shape[1]} (from {X_train.shape[1]} raw features)")
    print(f"    Projection time: {dt_proj:.3f}s")

    # ── Step 2: Fit FrozenWindowScorer on normal UDL tensor ──────────────
    results = {}

    t0 = time.perf_counter()
    fw = FrozenWindowScorer()
    fw.fit(X_normal_udl)
    dt_fit = time.perf_counter() - t0

    # FrozenWindow (unsupervised)
    t0 = time.perf_counter()
    s = fw.score(X_test_udl)
    m = op_metrics(y_test, s); m['time'] = time.perf_counter() - t0 + dt_fit; m['scores'] = s
    results['FrozenWindow'] = m
    if verbose:
        print(f"    FrozenWindow      : AUC={m['auc']:.4f}  F1={m['f1']:.3f}  "
              f"Recall={m['recall']:.3f}  FPR={m['fpr']:.4f}")

    # FW+Friction
    t0 = time.perf_counter()
    s = fw.score_with_friction(X_test_udl)
    m = op_metrics(y_test, s); m['time'] = time.perf_counter() - t0; m['scores'] = s
    results['FW+Friction'] = m
    if verbose:
        print(f"    FW+Friction       : AUC={m['auc']:.4f}  F1={m['f1']:.3f}  "
              f"Recall={m['recall']:.3f}  FPR={m['fpr']:.4f}")

    # Supervised variants (use training labels)
    y_fit = y_train

    # FW+ExpoGate
    t0 = time.perf_counter()
    fw.fit_expogate(X_train_udl, y_fit)
    s = fw.score_expogate(X_test_udl)
    m = op_metrics(y_test, s); m['time'] = time.perf_counter() - t0; m['scores'] = s
    results['FW+ExpoGate'] = m
    if verbose:
        print(f"    FW+ExpoGate       : AUC={m['auc']:.4f}  F1={m['f1']:.3f}  "
              f"Recall={m['recall']:.3f}  FPR={m['fpr']:.4f}")

    # FW+SignedLR
    t0 = time.perf_counter()
    fw.fit_signed_lr(X_train_udl, y_fit)
    s = fw.score_signed_lr(X_test_udl)
    m = op_metrics(y_test, s); m['time'] = time.perf_counter() - t0; m['scores'] = s
    results['FW+SignedLR'] = m
    if verbose:
        print(f"    FW+SignedLR       : AUC={m['auc']:.4f}  F1={m['f1']:.3f}  "
              f"Recall={m['recall']:.3f}  FPR={m['fpr']:.4f}")
        w = fw.lr_weights()
        ch = ['bias', 'Q', 'theta', 'AM', 'Qxtheta', 'Kxtheta', 'MFLS']
        wstr = ', '.join(f"{ch[min(i,len(ch)-1)]}={w[i]:+.3f}" for i in range(len(w)))
        print(f"      LR weights: {wstr}")

    # FW+QuadSurf
    t0 = time.perf_counter()
    fw.fit_quadsurf(X_train_udl, y_fit)
    s = fw.score_quadsurf(X_test_udl)
    m = op_metrics(y_test, s); m['time'] = time.perf_counter() - t0; m['scores'] = s
    results['FW+QuadSurf'] = m
    if verbose:
        print(f"    FW+QuadSurf       : AUC={m['auc']:.4f}  F1={m['f1']:.3f}  "
              f"Recall={m['recall']:.3f}  FPR={m['fpr']:.4f}")

    return results


# ══════════════════════════════════════════════════════════════════════════════
#  DATASET 1 — FDIC / G-SIB BANK DATA
# ══════════════════════════════════════════════════════════════════════════════

def load_bank_data():
    """
    Load real FDIC bank-level panel and prepare for UDL pipeline.

    Returns (X_train, y_train, X_test, y_test, meta)
    where each row = one (bank, quarter) observation.
    """
    sys.path.insert(0, r'c:\amttp\research\adaptive-friction\banklevel_enhanced')
    from bank_level_loader import build_bank_panel
    import pandas as pd

    print("\n  [Bank] Loading FDIC bank-level panel ...")
    panel = build_bank_panel(n_banks=30, force_refresh=False)
    X_raw = panel['X']      # (T, N, d)
    dates = panel['dates']
    N     = panel['n_banks_actual']
    d     = X_raw.shape[2]
    T     = X_raw.shape[0]
    meta  = panel['bank_meta']
    print(f"    Panel: T={T} quarters, N={N} banks, d={d} features")

    # Flatten to (T*N, d) — each row is one bank-quarter
    # Shape: (T*N, d)
    X_flat  = X_raw.reshape(T * N, d).astype(np.float64)
    dates_flat = np.repeat(np.arange(T), N)

    # Standardise on normal period (1994-2003)
    norm_mask_t = (dates >= pd.Timestamp('1994-01-01')) & \
                  (dates <= pd.Timestamp('2003-12-31'))
    norm_idx = np.where(np.repeat(norm_mask_t, N))[0]
    mu  = X_flat[norm_idx].mean(axis=0)
    sd  = X_flat[norm_idx].std(axis=0) + 1e-9
    X_std = (X_flat - mu) / sd

    # Replace NaN/Inf
    X_std = np.nan_to_num(X_std, nan=0.0, posinf=5.0, neginf=-5.0)
    X_std = np.clip(X_std, -8, 8)

    # Crisis labels: GFC, COVID, Rate Shock
    crisis_quarters = set()
    for t, dt in enumerate(dates):
        # GFC: 2007 Q1 - 2009 Q4
        if pd.Timestamp('2007-01-01') <= dt <= pd.Timestamp('2009-12-31'):
            crisis_quarters.add(t)
        # COVID: 2020 Q1 - 2020 Q4
        if pd.Timestamp('2020-01-01') <= dt <= pd.Timestamp('2020-12-31'):
            crisis_quarters.add(t)
        # Rate Shock: 2022 Q1 - 2022 Q4
        if pd.Timestamp('2022-01-01') <= dt <= pd.Timestamp('2022-12-31'):
            crisis_quarters.add(t)

    y_flat = np.array(
        [1 if dates_flat[i] in crisis_quarters else 0 for i in range(T * N)],
        dtype=int
    )

    # Train / test split: pre-2007 is training
    train_t_mask = dates < pd.Timestamp('2007-01-01')
    train_mask = np.repeat(train_t_mask, N)

    X_train = X_std[train_mask]
    y_train = y_flat[train_mask]
    X_test  = X_std[~train_mask]
    y_test  = y_flat[~train_mask]

    print(f"    Train: {len(X_train):,} (normals={int((y_train==0).sum()):,}, "
          f"crisis={int(y_train.sum()):,})")
    print(f"    Test:  {len(X_test):,} (normals={int((y_test==0).sum()):,}, "
          f"crisis={int(y_test.sum()):,})")
    print(f"    Anomaly rate (test): {100*y_test.mean():.1f}%")

    return X_train, y_train, X_test, y_test, meta


# ══════════════════════════════════════════════════════════════════════════════
#  DATASET 2 — ERCOT POWER GRID DATA (Texas)
# ══════════════════════════════════════════════════════════════════════════════

ERCOT_NPZ = Path(r'c:\amttp\data\ercot\ercot_daily_2018_2022.npz')


def load_ercot_real_data():
    """
    Load REAL ERCOT power grid daily data from pre-fetched NPZ cache.

    Data sources (all public, no synthetic values):
      - EIA API (DEMO_KEY): real ERCOT hourly actual demand 2018-2022
      - Open-Meteo (free):  Dallas TX daily max temperature

    Features derived from real hourly demand + temperature:
      0. load_mean_gw   — daily mean ERCOT system load (real EIA data)
      1. load_std_gw    — intraday demand standard deviation (real EIA)
      2. load_max_gw    — daily peak demand (real EIA)
      3. ramp_rate      — (peak − valley) / mean load (real EIA)
      4. temp_f         — Dallas TX daily max temp °F (real Open-Meteo)
      5. load_temp_ixn  — load_mean × |temp − 65| (derived from real data)

    Anomaly labels (ground-truth real events):
      WinterStormUri      Feb 10–20 2021  (46GW offline, record cold)
      COVID_Collapse      Mar 23–May 1 2020 (demand collapse)
      SummerPeak2019      Aug 12–16 2019 (heat stress)
      WinterStormElliott  Dec 22–26 2022 (repeat freeze event)

    Returns (X, y, dates, anomaly_labels)
    """
    if not ERCOT_NPZ.exists():
        raise FileNotFoundError(
            f"ERCOT NPZ not found: {ERCOT_NPZ}\n"
            "Run: python c:/amttp/data/ercot/build_ercot_panel.py"
        )
    npz = np.load(ERCOT_NPZ, allow_pickle=True)
    X      = npz['X'].astype(np.float64)   # (1826, 6)
    y      = npz['y'].astype(int)          # (1826,)  0/1
    dates  = npz['dates']                  # (1826,)  str '2018-01-01'
    labels = npz['labels']                 # (1826,)  str event names

    # Forward-fill remaining NaNs (should be minimal after build step)
    for col in range(X.shape[1]):
        last_v = np.nanmean(X[:, col]) if not np.all(np.isnan(X[:, col])) else 0.0
        for i in range(len(X)):
            if np.isnan(X[i, col]):
                X[i, col] = last_v
            else:
                last_v = X[i, col]

    print(f"\n  [ERCOT] Real ERCOT power grid data loaded from EIA + Open-Meteo:")
    print(f"    Period: {dates[0]} to {dates[-1]}  ({len(dates):,} days)")
    print(f"    Features (6): load_mean_gw, load_std_gw, load_max_gw,")
    print(f"                  ramp_rate, temp_f, load_temp_ixn")
    print(f"    Source: EIA ERCO actual hourly demand + Dallas TX Open-Meteo temp")
    print(f"    Normal days:  {int((y==0).sum()):,}")
    print(f"    Anomaly days: {int(y.sum()):,}")
    for lbl in ['WinterStormUri', 'COVID_Collapse', 'SummerPeak2019', 'WinterStormElliott']:
        cnt = int((labels == lbl).sum())
        if cnt:
            print(f"      {lbl:<26}: {cnt} days")

    return X, y, dates, labels


def prepare_ercot_split(X, y, dates):
    """
    Train/test split for ERCOT:
    - Train: 2018-01-01 to 2019-12-31 (pre-COVID baseline)
    - Test:  2020-01-01 onwards (COVID collapse, Uri, Elliott)
    """
    # dates is a numpy array of YYYY-MM-DD strings from NPZ
    dates_str   = np.array([str(d)[:10] for d in dates])
    train_mask  = dates_str < '2020-01-01'
    norm_mask   = train_mask & (y == 0)

    mu = X[norm_mask].mean(axis=0)
    sd = X[norm_mask].std(axis=0) + 1e-9
    X_std = (X - mu) / sd
    X_std = np.nan_to_num(X_std, nan=0.0, posinf=5.0, neginf=-5.0)
    X_std = np.clip(X_std, -10, 10)

    X_train = X_std[train_mask]
    y_train = y[train_mask]
    X_test  = X_std[~train_mask]
    y_test  = y[~train_mask]

    print(f"\n  [ERCOT] Train: {len(X_train):,} days "
          f"(normals={int((y_train==0).sum()):,}, anomalies={int(y_train.sum()):,})")
    print(f"    Test:  {len(X_test):,} days "
          f"(normals={int((y_test==0).sum()):,}, anomalies={int(y_test.sum()):,})")
    print(f"    Anomaly rate (test): {100*y_test.mean():.1f}%  "
          f"[Winter Uri + COVID collapse]")
    return X_train, y_train, X_test, y_test


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    t_global = time.perf_counter()

    print_banner("UDL Law-Domain Projection + FrozenWindow Geo-Scoring")
    print("  Datasets: FDIC Bank Data  |  ERCOT Power Grid Data")
    print("  Pipeline: Raw → UDL Tensor (Phase+Topo+RKHS+Rank) → FrozenWindowScorer")

    all_results = {}

    # ══════════════ DATASET 1: BANK DATA ═════════════════════════════════════
    print_banner("DATASET 1 — FDIC / G-SIB BANK DATA  (30 banks, 1994-2022)")
    try:
        t0 = time.perf_counter()
        X_train, y_train, X_test, y_test, meta = load_bank_data()
        bank_results = run_udl_pipeline(
            X_train, y_train, X_test, y_test,
            dataset_name='Bank', verbose=True
        )
        dt_bank = time.perf_counter() - t0
        print_results(bank_results, f'BANK: UDL + FrozenWindow  (runtime={dt_bank:.1f}s)')
        all_results['bank'] = {k: {kk: (float(vv) if isinstance(vv, (float, np.floating))
                                         else int(vv) if isinstance(vv, (int, np.integer))
                                         else None)
                                   for kk, vv in v.items() if kk != 'scores'}
                               for k, v in bank_results.items()}

        # Key event dates report
        print(f"\n  BANK Anomaly Summary:")
        print(f"    GFC (2007-2009)        : primary stress event")
        print(f"    COVID (2020)           : demand/credit disruption")
        print(f"    Rate Shock (2022)      : rising rates / SVB-era")
        best_eng  = max(bank_results, key=lambda e: bank_results[e]['auc'])
        best_auc  = bank_results[best_eng]['auc']
        best_f1   = bank_results[best_eng]['f1']
        best_rec  = bank_results[best_eng]['recall']
        print(f"    Best engine: {best_eng}  AUC={best_auc:.4f}  F1={best_f1:.3f}  "
              f"Recall={best_rec:.3f}")

    except Exception as e:
        print(f"\n  [BANK] ERROR: {e}")
        import traceback; traceback.print_exc()
        all_results['bank'] = {'error': str(e)}

    # ══════════════ DATASET 2: ERCOT DATA ════════════════════════════════════
    print_banner("DATASET 2 — ERCOT POWER GRID DATA  (Texas, Daily 2018-2022)")
    try:
        t0 = time.perf_counter()
        X_erc, y_erc, dates_erc, labels_erc = load_ercot_real_data()
        X_train_e, y_train_e, X_test_e, y_test_e = prepare_ercot_split(
            X_erc, y_erc, dates_erc
        )
        ercot_results = run_udl_pipeline(
            X_train_e, y_train_e, X_test_e, y_test_e,
            dataset_name='ERCOT', verbose=True
        )
        dt_ercot = time.perf_counter() - t0
        print_results(ercot_results, f'ERCOT: UDL + FrozenWindow  (runtime={dt_ercot:.1f}s)')
        all_results['ercot'] = {k: {kk: (float(vv) if isinstance(vv, (float, np.floating))
                                          else int(vv) if isinstance(vv, (int, np.integer))
                                          else None)
                                    for kk, vv in v.items() if kk != 'scores'}
                                for k, v in ercot_results.items()}

        # Key event report
        print(f"\n  ERCOT Anomaly Summary:")
        print(f"    Winter Storm Uri (2021-02-10/20)  : 46GW offline, $9000/MWh, -0.7Hz")
        print(f"    COVID collapse (2020-03/04)        : -10% demand, compressed prices")
        print(f"    Heatwave 2019 (2019-08-12/15)     : 80GW demand, $2000/MWh peak")
        best_eng  = max(ercot_results, key=lambda e: ercot_results[e]['auc'])
        best_auc  = ercot_results[best_eng]['auc']
        best_f1   = ercot_results[best_eng]['f1']
        best_rec  = ercot_results[best_eng]['recall']
        print(f"    Best engine: {best_eng}  AUC={best_auc:.4f}  F1={best_f1:.3f}  "
              f"Recall={best_rec:.3f}")

    except Exception as e:
        print(f"\n  [ERCOT] ERROR: {e}")
        import traceback; traceback.print_exc()
        all_results['ercot'] = {'error': str(e)}

    # ══════════════ OVERALL SUMMARY ══════════════════════════════════════════
    dt_total = time.perf_counter() - t_global
    print_banner(f"COMPLETE — Total runtime: {dt_total:.1f}s")
    print("\n  PIPELINE STAGES:")
    print("    1. Raw features      → UDL Law-Domain Projection (4 operators)")
    print("       Phase (trajectory) + Topological (LID/geometry)")
    print("       + KernelRKHS (nonlinear manifold) + RankOrder (distribution-free)")
    print("    2. UDL tensor        → FrozenWindowScorer (Geometry + Trig)")
    print("       Mahalanobis Q + angular θ + AM + Q×θ + K×θ (Algorithm 2)")
    print("\n  DOMAIN COVERAGE:")
    print("    Bank Data : FDIC quarterly call-reports, 30 banks, d=6 features")
    print("    ERCOT Data: Texas power grid daily, 6 features (EIA load + Open-Meteo temp)")

    # Save results
    out_path = RESULTS_DIR / 'udl_bank_ercot_results.json'
    with open(out_path, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n  Saved results → {out_path}")


if __name__ == '__main__':
    main()
