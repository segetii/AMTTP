#!/usr/bin/env python3
"""
test_udl_final.py
=================
Final UDL pipeline demo on two REAL-WORLD datasets.

Key improvement: seasonal-deviation features that make anomalies
visible to UDL's geometry operators.

ERCOT approach:
  - Compute rolling 30-day baseline for each feature
  - Features become DEVIATIONS from recent seasonal baseline
  - Uri: extreme negative temp-deviation, high load_temp_stress
  - COVID: persistent negative load-deviation despite normal temps

Bank approach:
  - Cross-bank panel rolling windows (8Q × N_banks × d)
  - Captures coordinated distress across the banking network

Data provenance: 100% REAL, no synthetic values.
  - FDIC SDI: cached call-report data (real US bank financials 1994-2022)
  - EIA API: real ERCOT hourly actual demand (35,063 hourly records)
  - Open-Meteo: real Dallas TX daily max temperature
"""

import sys, os, time, warnings
sys.path.insert(0, r'c:\amttp\research\udl')
sys.path.insert(0, r'c:\amttp\research\adaptive-friction\banklevel_enhanced')
os.environ['CUDA_VISIBLE_DEVICES'] = ''
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
warnings.filterwarnings('ignore')

import numpy as np
import json
from pathlib import Path
from sklearn.metrics import roc_auc_score

ROOT        = Path(r'c:\amttp')
ERCOT_NPZ   = ROOT / 'data' / 'ercot' / 'ercot_daily_2018_2022.npz'
RESULTS_DIR = ROOT / 'results' / 'udl_final'
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def op_metrics(y_true, scores):
    if len(np.unique(y_true)) < 2:
        return dict(auc=0.5, f1=0.0, prec=0.0, recall=0.0,
                    fpr=0.0, fnr=1.0, tp=0, fn=int(y_true.sum()), fp=0, tn=int((1-y_true).sum()))
    thr    = float(np.percentile(scores, 100 * (1 - y_true.mean())))
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
           f"{'Recall':>7} {'FPR':>7} {'TP/Total':>10}")
    print(hdr)
    print('    ' + '-' * 72)
    for eng, m in results.items():
        caught = f"{m['tp']}/{m['tp']+m['fn']}"
        print(f"    {eng:<18} {m['auc']:6.4f} {m['f1']:6.3f} {m['prec']:6.3f}"
              f" {m['recall']:7.3f} {m['fpr']:7.4f} {caught:>10}")
    print('    ' + '-' * 72)


def rolling_deviation(X, window=30):
    """
    Replace each value with its deviation from a local rolling mean.
    Handles NaNs. Uses only past data (causal).
    """
    T, d = X.shape
    X_dev = np.zeros_like(X)
    for col in range(d):
        for i in range(T):
            start = max(0, i - window)
            chunk = X[start:i, col]
            chunk = chunk[~np.isnan(chunk)]
            if len(chunk) >= 5:
                mu = chunk.mean()
                sd = chunk.std() + 1e-9
                X_dev[i, col] = (X[i, col] - mu) / sd if not np.isnan(X[i, col]) else 0.0
            else:
                X_dev[i, col] = 0.0
    return X_dev


def run_udl_pipeline(X_train, y_train, X_test, y_test, dataset_name='data'):
    """
    UDLPostSimScorer → FrozenWindowScorer pipeline.
    """
    from geo_full_pipeline import FrozenWindowScorer
    from udl.system_mode import UDLPostSimScorer

    X_normal = X_train[y_train == 0]
    print(f"\n  [{dataset_name}] UDL Projection:")
    print(f"    Train normals: {len(X_normal):,} | Total train: {len(X_train):,} | Test: {len(X_test):,}")
    print(f"    Feature dim: {X_train.shape[1]}")

    # ── Step 1: UDL law-domain projection ────────────────────────────────────
    t_proj = time.perf_counter()
    k_val  = min(15, len(X_normal) - 1)
    nc_val = min(10, len(X_normal) - 1)
    scorer = UDLPostSimScorer(k=k_val, max_dim=12, n_components=nc_val)
    scorer.fit(X_normal)
    Z_train = scorer.transform(X_train)
    Z_test  = scorer.transform(X_test)
    Z_norm  = Z_train[y_train == 0]
    proj_time = time.perf_counter() - t_proj
    print(f"    UDL tensor dim: {Z_train.shape[1]}   [{proj_time:.2f}s]")

    # ── Step 2: FrozenWindowScorer ────────────────────────────────────────────
    fw = FrozenWindowScorer()
    fw.fit(Z_norm)

    results = {}

    # Unsupervised variants
    for name, fn in [('FrozenWindow', lambda: fw.score(Z_test)),
                     ('FW+Friction',  lambda: fw.score_with_friction(Z_test))]:
        t0 = time.perf_counter()
        s  = fn()
        m  = op_metrics(y_test, s)
        m['time'] = time.perf_counter() - t0
        m['scores'] = s
        results[name] = m

    # Supervised variants
    fw.fit_expogate(Z_train, y_train)
    for name, fn in [('FW+ExpoGate', lambda: fw.score_expogate(Z_test))]:
        t0 = time.perf_counter()
        s  = fn()
        m  = op_metrics(y_test, s)
        m['time'] = time.perf_counter() - t0
        m['scores'] = s
        results[name] = m

    fw.fit_signed_lr(Z_train, y_train)
    for name, fn in [('FW+SignedLR', lambda: fw.score_signed_lr(Z_test))]:
        t0 = time.perf_counter()
        s  = fn()
        m  = op_metrics(y_test, s)
        m['time'] = time.perf_counter() - t0
        m['scores'] = s
        results[name] = m

    return results


# ─────────────────────────────────────────────────────────────────────────────
#  DATASET 1 — FDIC BANK DATA
# ─────────────────────────────────────────────────────────────────────────────

def load_bank_data():
    """
    FDIC bank panel as cross-bank rolling windows.
    Each obs = W quarters × (N_banks × d_features) — full cross-sectional context.
    """
    import pandas as pd
    from bank_level_loader import build_bank_panel

    print("\n  [Bank] Loading FDIC bank panel (cached FDIC SDI call-report data) ...")
    panel = build_bank_panel(n_banks=30, force_refresh=False)
    X_raw = panel['X']       # (T, N, d)
    dates = panel['dates']   # (T,) DatetimeIndex
    T, N, d = X_raw.shape

    # Crisis quarter labels
    y_t = np.zeros(T, dtype=int)
    for t, dt in enumerate(dates):
        if (pd.Timestamp('2007-01-01') <= dt <= pd.Timestamp('2009-12-31') or
            pd.Timestamp('2020-01-01') <= dt <= pd.Timestamp('2020-12-31') or
            pd.Timestamp('2022-01-01') <= dt <= pd.Timestamp('2022-12-31')):
            y_t[t] = 1

    # Standardise on 1994-2003 pre-crisis baseline
    pre_mask  = (dates >= pd.Timestamp('1994-01-01')) & (dates <= pd.Timestamp('2003-12-31'))
    norm_data = X_raw[pre_mask].reshape(-1, d)
    mu = norm_data.mean(axis=0); sd = norm_data.std(axis=0) + 1e-9
    X_std = np.nan_to_num(np.clip((X_raw - mu) / sd, -8, 8))   # (T, N, d)

    # Flatten each quarter to cross-bank cross-section: (T, N*d)
    X_flat = X_std.reshape(T, N * d)

    # Rolling windows over T: W=8 quarters
    W = 8
    Xw = np.stack([X_flat[i:i+W].ravel() for i in range(T - W)])   # (T-W, W*N*d)
    yw = np.array([1 if y_t[i:i+W].any() else 0 for i in range(T - W)])
    wd = dates[W:]     # date of last quarter in each window

    train_mask = wd < pd.Timestamp('2007-01-01')
    X_train, y_train = Xw[train_mask], yw[train_mask]
    X_test,  y_test  = Xw[~train_mask], yw[~train_mask]

    print(f"    Panel: T={T} Q, N={N} banks, d={d} — Window W={W} Q")
    print(f"    Obs dim: {W*N*d:,}")
    print(f"    Train: {len(X_train):,}  (normals={int((y_train==0).sum())}, crises={int(y_train.sum())})")
    print(f"    Test:  {len(X_test):,}  (normals={int((y_test==0).sum())}, crises={int(y_test.sum())})")
    print(f"    Test anomaly rate: {100*y_test.mean():.1f}%  [GFC 2007-09 | COVID 2020 | Rate 2022]")
    return X_train, y_train, X_test, y_test


# ─────────────────────────────────────────────────────────────────────────────
#  DATASET 2 — ERCOT POWER GRID DATA  (Real EIA + Open-Meteo)
# ─────────────────────────────────────────────────────────────────────────────

def load_ercot_data():
    """
    Real ERCOT power grid data with seasonal-deviation feature engineering.

    Features (all derived from REAL data):
      Raw: load_mean_gw, load_std_gw, load_max_gw, ramp_rate, temp_f, load_temp_ixn
      Derived: rolling 30-day z-scores make anomalies direction-agnostic

    Key signals:
      Uri (Feb 2021)  : temp_dev = -6.5σ, load_dev = +1.5σ (pre-shedding), ixn_dev = +3σ
      COVID (Mar 2020): load_dev = -2σ (demand collapse), temp_dev ≈ 0
    """
    npz    = np.load(ERCOT_NPZ, allow_pickle=True)
    X_raw  = npz['X'].astype(np.float64)   # (1826, 6)
    y_raw  = npz['y'].astype(int)
    dates  = npz['dates']
    labels = npz['labels']

    # Forward-fill NaNs
    for col in range(X_raw.shape[1]):
        last_v = np.nanmean(X_raw[:, col]) if not np.all(np.isnan(X_raw[:, col])) else 0.0
        for i in range(len(X_raw)):
            if np.isnan(X_raw[i, col]):
                X_raw[i, col] = last_v
            else:
                last_v = X_raw[i, col]

    # Compute seasonal-deviation features (rolling 30-day z-scores)
    # This makes high/low deviations in ANY direction visible
    X_dev = rolling_deviation(X_raw, window=30)

    # Also include absolute features (standardised on training period)
    train_day_mask = np.array([str(d)[:10] < '2020-01-01' for d in dates])
    norm_mask      = train_day_mask & (y_raw == 0)
    mu  = X_raw[norm_mask].mean(axis=0)
    sd  = X_raw[norm_mask].std(axis=0) + 1e-9
    X_abs = np.nan_to_num(np.clip((X_raw - mu) / sd, -8, 8))

    # Combined: 12 features (6 absolute + 6 deviation)
    X_combined = np.hstack([X_abs, X_dev])

    X_train = X_combined[train_day_mask]
    y_train = y_raw[train_day_mask]
    X_test  = X_combined[~train_day_mask]
    y_test  = y_raw[~train_day_mask]

    print(f"\n  [ERCOT] Real ERCOT data: EIA hourly demand (35,063 records) + Open-Meteo Dallas TX temp")
    print(f"    Features: 6 raw + 6 rolling-30d deviation = 12 combined features")
    print(f"    Train: {len(X_train):,} days  (normals={int((y_train==0).sum())}, anomalies={int(y_train.sum())})")
    print(f"    Test:  {len(X_test):,} days  (normals={int((y_test==0).sum())}, anomalies={int(y_test.sum())})")
    print(f"    Test anomaly rate: {100*y_test.mean():.1f}%")

    # Print feature signal at Uri peak (Feb 15, 2021)
    uri_idx = [i for i, l in enumerate(labels) if l == 'WinterStormUri']
    if uri_idx:
        peak = uri_idx[5]  # ~Feb 15
        fnames_r = ['load_mean','load_std','load_max','ramp','temp_f','ixn']
        fnames_d = [f+'_dev' for f in fnames_r]
        vals_r = ' | '.join([f'{X_abs[peak,j]:.2f}σ' for j in range(6)])
        vals_d = ' | '.join([f'{X_dev[peak,j]:.2f}σ' for j in range(6)])
        print(f"\n    Uri peak (Feb-15-2021) absolute z-scores: [{vals_r}]")
        print(f"    Uri peak (Feb-15-2021) rolling deviations: [{vals_d}]")

    return X_train, y_train, X_test, y_test, dates, y_raw, labels


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    t_global = time.perf_counter()
    all_results = {}

    print_banner("UDL Law-Domain + FrozenWindow — Real FDIC Bank & Real ERCOT Data")
    print("  All data: real public sources (FDIC SDI + EIA API + Open-Meteo)")
    print("  Pipeline: Features → UDL (Phase+Topo+RKHS+Rank) → FrozenWindow")

    # ── BANK ─────────────────────────────────────────────────────────────────
    print_banner("DATASET 1 — FDIC/G-SIB  (Real FDIC Call-Report, 30 banks, W=8 quarters)")
    try:
        t0 = time.perf_counter()
        X_train, y_train, X_test, y_test = load_bank_data()
        bank_res = run_udl_pipeline(X_train, y_train, X_test, y_test, 'Bank')
        dt = time.perf_counter() - t0
        print_results(bank_res, f'BANK  (runtime={dt:.1f}s)')
        best = max(bank_res, key=lambda e: bank_res[e]['auc'])
        print(f"\n  Best: {best}  AUC={bank_res[best]['auc']:.4f}  "
              f"F1={bank_res[best]['f1']:.3f}  Recall={bank_res[best]['recall']:.3f}")
        print(f"  Crisis events: GFC 2007-09 (N×d network distress) | COVID 2020 | Rate Shock 2022")
        all_results['bank'] = {k: {kk: (float(v) if isinstance(v, (float, np.floating))
                                         else int(v) if isinstance(v, (int, np.integer)) else None)
                                   for kk, v in m.items() if kk != 'scores'}
                               for k, m in bank_res.items()}
    except Exception as e:
        import traceback; traceback.print_exc()
        all_results['bank'] = {'error': str(e)}

    # ── ERCOT ────────────────────────────────────────────────────────────────
    print_banner("DATASET 2 — ERCOT  (Real EIA Demand + Open-Meteo Temp, 2018-2022)")
    try:
        t0     = time.perf_counter()
        X_train, y_train, X_test, y_test, dates, y_raw, labels = load_ercot_data()
        ercot_res = run_udl_pipeline(X_train, y_train, X_test, y_test, 'ERCOT')
        dt = time.perf_counter() - t0
        print_results(ercot_res, f'ERCOT  (runtime={dt:.1f}s)')
        best = max(ercot_res, key=lambda e: ercot_res[e]['auc'])
        print(f"\n  Best: {best}  AUC={ercot_res[best]['auc']:.4f}  "
              f"F1={ercot_res[best]['f1']:.3f}  Recall={ercot_res[best]['recall']:.3f}")

        # Per-event AUC on test set
        best_scores = ercot_res[best]['scores']
        test_mask   = np.array([str(d)[:10] >= '2020-01-01' for d in dates])
        test_labels = labels[test_mask]
        y_test_all  = y_raw[test_mask]
        print(f"\n  Per-event detection (best = {best}):")
        thr = float(np.percentile(best_scores, 95))   # 5% alert rate
        for evt in ['WinterStormUri', 'COVID_Collapse', 'SummerPeak2019', 'WinterStormElliott']:
            evt_mask = test_labels == evt
            if not evt_mask.any():
                continue
            n_evt = evt_mask.sum()
            n_det = (best_scores[evt_mask] > thr).sum()
            mean_score = float(best_scores[evt_mask].mean())
            mean_norm  = float(best_scores[test_labels == 'Normal'].mean()) if (test_labels == 'Normal').any() else 0.0
            print(f"    {evt:<26}: {n_det}/{n_evt} flags @ 5%FAR | mean_score={mean_score:.3f} vs normal={mean_norm:.3f}")

        all_results['ercot'] = {k: {kk: (float(v) if isinstance(v, (float, np.floating))
                                          else int(v) if isinstance(v, (int, np.integer)) else None)
                                    for kk, v in m.items() if kk != 'scores'}
                                for k, m in ercot_res.items()}
    except Exception as e:
        import traceback; traceback.print_exc()
        all_results['ercot'] = {'error': str(e)}

    # ── SUMMARY ──────────────────────────────────────────────────────────────
    dt_total = time.perf_counter() - t_global
    print_banner(f"COMPLETE — Total runtime: {dt_total:.1f}s")

    print("\n  DATA PROVENANCE (100% REAL PUBLIC DATA):")
    print("    FDIC Bank : SDI call-report cache (real US bank financials 1994-2022)")
    print("    ERCOT     : EIA API ERCO hourly demand (35,063 rows)")
    print("                Open-Meteo Dallas TX daily max temperature")

    print("\n  PIPELINE:")
    print("    1. Raw → Seasonal-deviation features (rolling 30-day z-scores)")
    print("    2. Features → UDL Law-Domain Projection")
    print("       Phase (trajectory) | Topo (LID) | RKHS (manifold) | Rank (distribution)")
    print("    3. UDL tensor → FrozenWindowScorer")
    print("       Mahalanobis Q | angular θ | AM | Q×θ | K×θ (Algorithm 2)")

    out = RESULTS_DIR / 'udl_final_results.json'
    with open(out, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n  Results → {out}")


if __name__ == '__main__':
    main()
