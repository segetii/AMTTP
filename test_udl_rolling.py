#!/usr/bin/env python3
"""
test_udl_rolling.py
===================
Rolling-window UDL pipeline for temporal financial + energy datasets.

The problem with flat per-row data (one row = one day or one bank×quarter)
is that UDL's geometry operators (Phase, Topo, RKHS, Rank) act on the
STATIC distribution of training normals.  Anomalies show up only if the
DISTRIBUTION of raw features deviates — which is weak for macro-correlated
panel data.

FIX: Treat each observation as a TEMPORAL WINDOW (W steps × d features).
  - Flattened window → (W×d, ) gives UDL a trajectory signal
  - UDL then scores HOW MUCH the recent trajectory deviates from the
    geometry of normal training trajectories

For bank data:  W=8 quarters (2 years context), stride=1 quarter
For ERCOT data: W=21 days (3 weeks context), stride=1 day

Data sources:
  Bank  : FDIC SDI call-report cached data (real, N=30 banks, T=140 Q)
  ERCOT : EIA hourly demand + Open-Meteo temperature (real, T=1826 days)
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

ROOT         = Path(r'c:\amttp')
ERCOT_NPZ    = ROOT / 'data' / 'ercot' / 'ercot_daily_2018_2022.npz'
RESULTS_DIR  = ROOT / 'results' / 'udl_rolling'
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


def make_rolling_windows(X_full, y_full, W, stride=1):
    """
    Convert (T, d) time-series into (T-W, W*d) rolling windows.
    Label: window is anomalous if ANY step in it is anomalous.

    Returns X_win (n_windows, W*d), y_win (n_windows,)
    """
    T, d = X_full.shape
    n    = (T - W) // stride
    X_win = np.empty((n, W * d), dtype=np.float64)
    y_win = np.zeros(n, dtype=int)
    for i in range(n):
        start = i * stride
        end   = start + W
        X_win[i] = X_full[start:end].ravel()
        if y_full[start:end].any():
            y_win[i] = 1
    return X_win, y_win


def run_udl_pipeline(X_train, y_train, X_test, y_test, dataset_name='data'):
    """
    Full UDLPostSimScorer → FrozenWindowScorer pipeline.
    """
    from geo_full_pipeline import FrozenWindowScorer
    from udl.system_mode import UDLPostSimScorer

    X_normal = X_train[y_train == 0]
    print(f"\n  [{dataset_name}] UDL pipeline:")
    print(f"    Train normals: {len(X_normal):,} | Total train: {len(X_train):,} | Test: {len(X_test):,}")
    print(f"    Window feature dim: {X_train.shape[1]}")

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
    print(f"    UDL tensor dim: {Z_train.shape[1]}   [proj {proj_time:.2f}s]")

    # ── Step 2: FrozenWindowScorer ────────────────────────────────────────────
    t_fit = time.perf_counter()
    fw = FrozenWindowScorer()
    fw.fit(Z_norm)
    dt_fit = time.perf_counter() - t_fit

    results = {}

    # FrozenWindow (unsupervised)
    t0 = time.perf_counter()
    s  = fw.score(Z_test)
    m  = op_metrics(y_test, s)
    m['time'] = time.perf_counter() - t0 + dt_fit
    m['scores'] = s
    results['FrozenWindow'] = m
    print(f"    FrozenWindow      : AUC={m['auc']:.4f}  F1={m['f1']:.3f}  Recall={m['recall']:.3f}  FPR={m['fpr']:.4f}")

    # FW+Friction
    t0 = time.perf_counter()
    s  = fw.score_with_friction(Z_test)
    m  = op_metrics(y_test, s)
    m['time'] = time.perf_counter() - t0
    m['scores'] = s
    results['FW+Friction'] = m
    print(f"    FW+Friction       : AUC={m['auc']:.4f}  F1={m['f1']:.3f}  Recall={m['recall']:.3f}  FPR={m['fpr']:.4f}")

    # FW+ExpoGate (supervised)
    t0 = time.perf_counter()
    fw.fit_expogate(Z_train, y_train)
    s  = fw.score_expogate(Z_test)
    m  = op_metrics(y_test, s)
    m['time'] = time.perf_counter() - t0
    m['scores'] = s
    results['FW+ExpoGate'] = m
    print(f"    FW+ExpoGate       : AUC={m['auc']:.4f}  F1={m['f1']:.3f}  Recall={m['recall']:.3f}  FPR={m['fpr']:.4f}")

    # FW+SignedLR (supervised)
    t0 = time.perf_counter()
    fw.fit_signed_lr(Z_train, y_train)
    s  = fw.score_signed_lr(Z_test)
    m  = op_metrics(y_test, s)
    m['time'] = time.perf_counter() - t0
    m['scores'] = s
    results['FW+SignedLR'] = m
    print(f"    FW+SignedLR       : AUC={m['auc']:.4f}  F1={m['f1']:.3f}  Recall={m['recall']:.3f}  FPR={m['fpr']:.4f}")

    # FW+QuadSurf (supervised, try/catch for API variance)
    try:
        t0 = time.perf_counter()
        fw.fit_quad_surf(Z_train, y_train)
        s  = fw.score_quad_surf(Z_test)
        m  = op_metrics(y_test, s)
        m['time'] = time.perf_counter() - t0
        m['scores'] = s
        results['FW+QuadSurf'] = m
        print(f"    FW+QuadSurf       : AUC={m['auc']:.4f}  F1={m['f1']:.3f}  Recall={m['recall']:.3f}  FPR={m['fpr']:.4f}")
    except Exception as e:
        print(f"    FW+QuadSurf       : skipped ({e})")

    return results


# ─────────────────────────────────────────────────────────────────────────────
#  DATASET 1 — FDIC BANK DATA  (rolling quarterly windows)
# ─────────────────────────────────────────────────────────────────────────────

def load_bank_rolling(W=4):
    """
    Load FDIC bank panel as rolling cross-sectional temporal windows.

    Each observation = W quarters × (N_banks × d_features) = W × N × d
    reshaping to (W * N * d,) so UDL sees the FULL cross-bank trajectory.
    This lets Phase/Topo/RKHS capture inter-bank comovement patterns.

    Train: up to 2006 Q4 (pre-GFC baseline)
    Test:  2007 Q1 onwards (GFC, COVID, Rate Shock)
    """
    import pandas as pd
    sys.path.insert(0, r'c:\amttp\research\adaptive-friction\banklevel_enhanced')
    from bank_level_loader import build_bank_panel

    print("\n  [Bank] Loading FDIC bank panel ...")
    panel = build_bank_panel(n_banks=30, force_refresh=False)
    X_raw = panel['X']       # (T, N, d)
    dates = panel['dates']   # (T,) DatetimeIndex
    T, N, d = X_raw.shape
    print(f"    Panel: T={T} Q, N={N} banks, d={d} features")

    # Standardise on 1994-2003 normal period
    pre_mask  = (dates >= pd.Timestamp('1994-01-01')) & (dates <= pd.Timestamp('2003-12-31'))
    norm_data = X_raw[pre_mask].reshape(-1, d)
    mu = norm_data.mean(axis=0)
    sd = norm_data.std(axis=0) + 1e-9
    X_std = (X_raw - mu) / sd                    # (T, N, d)
    X_std = np.nan_to_num(np.clip(X_std, -8, 8))

    # Flatten each timestep to (N*d,) cross-section vector
    X_flat  = X_std.reshape(T, N * d)             # (T, N*d)

    # Crisis labels per timestep
    y_t = np.zeros(T, dtype=int)
    for t, dt in enumerate(dates):
        if (pd.Timestamp('2007-01-01') <= dt <= pd.Timestamp('2009-12-31') or
            pd.Timestamp('2020-01-01') <= dt <= pd.Timestamp('2020-12-31') or
            pd.Timestamp('2022-01-01') <= dt <= pd.Timestamp('2022-12-31')):
            y_t[t] = 1

    # Rolling windows over T: each obs = W consecutive cross-sections
    X_win, y_win = make_rolling_windows(X_flat, y_t, W=W, stride=1)
    win_dates    = dates[W:]     # date of LAST quarter in window

    train_mask = win_dates < pd.Timestamp('2007-01-01')
    test_mask  = ~train_mask
    X_train, y_train = X_win[train_mask], y_win[train_mask]
    X_test,  y_test  = X_win[test_mask],  y_win[test_mask]

    print(f"    Window: W={W} Q × (N={N} banks × d={d}) = {W*N*d} dims/obs")
    print(f"    Train: {len(X_train):,} windows  "
          f"(normals={int((y_train==0).sum()):,}, crises={int(y_train.sum()):,})")
    print(f"    Test:  {len(X_test):,} windows  "
          f"(normals={int((y_test==0).sum()):,}, crises={int(y_test.sum()):,})")
    print(f"    Anomaly rate (test): {100*y_test.mean():.1f}%")
    return X_train, y_train, X_test, y_test


# ─────────────────────────────────────────────────────────────────────────────
#  DATASET 2 — ERCOT DATA  (rolling daily windows)
# ─────────────────────────────────────────────────────────────────────────────

def load_ercot_rolling(W=21):
    """
    Load real ERCOT daily panel as rolling temporal windows.

    Each observation = W days × 6 real features.
    Train: 2018-01-01 to 2019-12-31 (pre-COVID baseline)
    Test:  2020-01-01 onwards
    """
    if not ERCOT_NPZ.exists():
        raise FileNotFoundError(f"ERCOT NPZ not found: {ERCOT_NPZ}")

    npz    = np.load(ERCOT_NPZ, allow_pickle=True)
    X_raw  = npz['X'].astype(np.float64)
    y_raw  = npz['y'].astype(int)
    dates  = npz['dates']

    # Forward-fill NaNs
    for col in range(X_raw.shape[1]):
        last_v = np.nanmean(X_raw[:, col]) if not np.all(np.isnan(X_raw[:, col])) else 0.0
        for i in range(len(X_raw)):
            if np.isnan(X_raw[i, col]):
                X_raw[i, col] = last_v
            else:
                last_v = X_raw[i, col]

    # Standardise on 2018-2019 normal days
    train_day_mask = np.array([str(d)[:10] < '2020-01-01' for d in dates])
    norm_mask      = train_day_mask & (y_raw == 0)
    mu  = X_raw[norm_mask].mean(axis=0)
    sd  = X_raw[norm_mask].std(axis=0) + 1e-9
    X_s = (X_raw - mu) / sd
    X_s = np.nan_to_num(np.clip(X_s, -8, 8))

    # Rolling windows
    X_win, y_win = make_rolling_windows(X_s, y_raw, W=W, stride=1)
    win_dates    = dates[W:]        # date of the LAST step in each window

    train_mask   = np.array([str(d)[:10] < '2020-01-01' for d in win_dates])
    test_mask    = ~train_mask

    X_train, y_train = X_win[train_mask], y_win[train_mask]
    X_test,  y_test  = X_win[test_mask],  y_win[test_mask]

    print(f"\n  [ERCOT] Real ERCOT data (EIA demand + Open-Meteo temp) as rolling windows:")
    print(f"    Window size: W={W} days  |  obs dim: {W*6}")
    print(f"    Train: {len(X_train):,} windows  "
          f"(normals={int((y_train==0).sum()):,}, anomalies={int(y_train.sum()):,})")
    print(f"    Test:  {len(X_test):,} windows  "
          f"(normals={int((y_test==0).sum()):,}, anomalies={int(y_test.sum()):,})")
    print(f"    Anomaly rate (test): {100*y_test.mean():.1f}%")
    print(f"    Events in test: WinterStormUri, COVID_Collapse, WinterStormElliott")
    return X_train, y_train, X_test, y_test


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    t_global = time.perf_counter()
    all_results = {}

    print_banner("UDL Rolling-Window Pipeline — Real FDIC Bank + Real ERCOT Data")
    print("  Each observation = W-step temporal context window")
    print("  Step 1: Window → UDL law-domain tensor (Phase+Topo+RKHS+Rank)")
    print("  Step 2: UDL tensor → FrozenWindowScorer (Q + θ + AM + Q×θ + K×θ)")

    # ── BANK ─────────────────────────────────────────────────────────────────
    print_banner("DATASET 1 — FDIC/G-SIB BANK DATA  (30 banks, W=8 quarters)")
    try:
        t0 = time.perf_counter()
        X_train, y_train, X_test, y_test = load_bank_rolling(W=8)
        bank_res = run_udl_pipeline(X_train, y_train, X_test, y_test, 'Bank-Rolling')
        dt = time.perf_counter() - t0
        print_results(bank_res, f'BANK Rolling-Window  (W=8Q, runtime={dt:.1f}s)')
        best = max(bank_res, key=lambda e: bank_res[e]['auc'])
        print(f"\n  Best: {best}  AUC={bank_res[best]['auc']:.4f}  "
              f"F1={bank_res[best]['f1']:.3f}  Recall={bank_res[best]['recall']:.3f}")
        all_results['bank_rolling'] = {
            k: {kk: (float(v) if isinstance(v, (float, np.floating))
                     else int(v) if isinstance(v, (int, np.integer)) else None)
                for kk, v in m.items() if kk != 'scores'}
            for k, m in bank_res.items()
        }
    except Exception as e:
        import traceback; traceback.print_exc()
        all_results['bank_rolling'] = {'error': str(e)}

    # ── ERCOT ────────────────────────────────────────────────────────────────
    print_banner("DATASET 2 — ERCOT POWER GRID  (Real EIA+OpenMeteo, W=21 days)")
    try:
        t0 = time.perf_counter()
        X_train, y_train, X_test, y_test = load_ercot_rolling(W=21)
        ercot_res = run_udl_pipeline(X_train, y_train, X_test, y_test, 'ERCOT-Rolling')
        dt = time.perf_counter() - t0
        print_results(ercot_res, f'ERCOT Rolling-Window  (W=21d, runtime={dt:.1f}s)')
        best = max(ercot_res, key=lambda e: ercot_res[e]['auc'])
        print(f"\n  Best: {best}  AUC={ercot_res[best]['auc']:.4f}  "
              f"F1={ercot_res[best]['f1']:.3f}  Recall={ercot_res[best]['recall']:.3f}")

        # Key event breakdown
        npz       = np.load(ERCOT_NPZ, allow_pickle=True)
        y_raw     = npz['y'].astype(int)
        dates_raw = npz['dates']
        labels    = npz['labels']
        W_e       = 21
        win_dates = dates_raw[W_e:]
        test_mask = np.array([str(d)[:10] >= '2020-01-01' for d in win_dates])
        y_scores  = ercot_res[best]['scores']

        # Per-event detection rate using anomaly windows
        print(f"\n  Event detection (best engine = {best}):")
        for evt in ['WinterStormUri', 'COVID_Collapse', 'SummerPeak2019', 'WinterStormElliott']:
            # Find test windows that INCLUDE an anomaly day of this event
            evt_test_idx = []
            for i, (d, tm) in enumerate(zip(win_dates, test_mask)):
                if not tm:
                    continue
                # The window covers dates[i:i+W_e]
                start_idx = np.where(dates_raw == d)[0]
                if len(start_idx) == 0:
                    continue
                si = int(start_idx[0]) - W_e
                if si < 0: continue
                window_labels = labels[si:si+W_e]
                if evt in window_labels:
                    evt_test_idx.append(sum(test_mask[:i+1]) - 1)
            if evt_test_idx:
                evt_scores = y_scores[np.array(evt_test_idx)]
                thr = float(np.percentile(y_scores, 100 * (1 - y_test.mean())))
                n_det = int((evt_scores > thr).sum())
                print(f"    {evt:<26}: {n_det}/{len(evt_test_idx)} windows flagged")

        all_results['ercot_rolling'] = {
            k: {kk: (float(v) if isinstance(v, (float, np.floating))
                     else int(v) if isinstance(v, (int, np.integer)) else None)
                for kk, v in m.items() if kk != 'scores'}
            for k, m in ercot_res.items()
        }
    except Exception as e:
        import traceback; traceback.print_exc()
        all_results['ercot_rolling'] = {'error': str(e)}

    # ── SUMMARY ──────────────────────────────────────────────────────────────
    dt_total = time.perf_counter() - t_global
    print_banner(f"COMPLETE — Total runtime: {dt_total:.1f}s")
    print("\n  DATA PROVENANCE (100% real, no synthetic values):")
    print("    Bank  : FDIC SDI call-report cache (real US bank financials 1994-2022)")
    print("    ERCOT : EIA API ERCO hourly demand + Open-Meteo Dallas TX temperature")
    print("\n  PIPELINE: W-step rolling window → UDL (Phase+Topo+RKHS+Rank) → FrozenWindow")

    out = RESULTS_DIR / 'udl_rolling_results.json'
    with open(out, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n  Results saved → {out}")


if __name__ == '__main__':
    main()
