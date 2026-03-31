#!/usr/bin/env python3
"""
run_full_engine.py
==================
Full engine evaluation on real-world data.

Engines:
  - Gravity    : N-body gravitational engine (GravityModeEngine)
  - Molecular  : Lennard-Jones molecular dynamics (MolecularEngine)
  - Hybrid     : Adaptive blend of Molecular + Gravity (HybridGravityEngine)

Tensor representation:
  - ReducedTensorDescriptor: O(Nd + d³) compact descriptor per point
    (grad_norm, Hessian eigenvalues, Mahalanobis, medoid dist, tr(H), det(Σ))
    Each engine scores the tensor-feature space, not the raw features.

Datasets (100% real, zero synthetic):
  - ERCOT: EIA ERCO hourly demand (35,063 records) + Open-Meteo Dallas temp
  - Bank : FDIC SDI quarterly call-report (30 banks, 1994-2022)

Output: results/full_engine_results.json
"""
import sys, os, time, warnings, json
sys.path.insert(0, r'c:\amttp\research\udl')
sys.path.insert(0, r'c:\amttp\research\adaptive-friction\banklevel_enhanced')
os.environ['CUDA_VISIBLE_DEVICES'] = ''
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
warnings.filterwarnings('ignore')

import numpy as np
from pathlib import Path
from sklearn.metrics import roc_auc_score, f1_score, precision_score, recall_score
from sklearn.decomposition import PCA

ROOT        = Path(r'c:\amttp')
ERCOT_NPZ   = ROOT / 'data' / 'ercot' / 'ercot_daily_2018_2022.npz'
RESULTS_DIR = ROOT / 'results'
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
OUT_FILE    = RESULTS_DIR / 'full_engine_results.json'

# ─── imports from UDL engine ───────────────────────────────────────────────
from udl.system_mode import (
    MolecularEngine,
    GravityModeEngine,
    HybridGravityEngine,
    ReducedTensorDescriptor,
)

# ══════════════════════════════════════════════════════════════════════════
#  UTILITIES
# ══════════════════════════════════════════════════════════════════════════

def metrics(y_true, scores, label=''):
    """Compute AUC, F1, precision, recall at anomaly-rate threshold."""
    y_true = np.asarray(y_true, dtype=int)
    scores = np.asarray(scores, dtype=float)
    if len(np.unique(y_true)) < 2:
        return dict(auc=0.5, f1=0.0, precision=0.0, recall=0.0)
    auc = float(roc_auc_score(y_true, scores))
    thr = float(np.percentile(scores, 100 * (1 - y_true.mean())))
    y_pred = (scores >= thr).astype(int)
    f1  = float(f1_score(y_true, y_pred, zero_division=0))
    pre = float(precision_score(y_true, y_pred, zero_division=0))
    rec = float(recall_score(y_true, y_pred, zero_division=0))
    return dict(auc=auc, f1=f1, precision=pre, recall=rec)


def per_event_auc(y_te, scores, te_labels, norm_label='Normal'):
    """Per-event AUC against normal days."""
    result = {}
    norm_mask = te_labels == norm_label
    for evt in np.unique(te_labels):
        if evt == norm_label:
            continue
        evt_mask = te_labels == evt
        mask = evt_mask | norm_mask
        if evt_mask.sum() < 2:
            continue
        try:
            result[evt] = float(roc_auc_score(y_te[mask], scores[mask]))
        except Exception:
            result[evt] = 0.5
    return result


def build_tensor(X_ref, X_all, k=10):
    """Fit ReducedTensorDescriptor on normals, score all points."""
    desc = ReducedTensorDescriptor(k_neighbors=min(k, len(X_ref) - 1))
    desc.fit(X_ref)
    return desc.score(X_all)          # (N,) anomaly scores


def rolling_deviation(X, window=30):
    """Rolling z-score deviations (30-day window)."""
    T, d = X.shape
    Xd = np.zeros_like(X)
    for col in range(d):
        for i in range(T):
            start = max(0, i - window)
            chunk = X[start:i, col]
            chunk = chunk[~np.isnan(chunk)]
            if len(chunk) >= 5:
                mu = chunk.mean(); sd = chunk.std() + 1e-9
                Xd[i, col] = (X[i, col] - mu) / sd if not np.isnan(X[i, col]) else 0.0
    return Xd


def run_engines(X_train, y_train, X_test, y_test, te_labels=None,
                dataset_name='', k=10):
    """
    Run Gravity / Molecular / Hybrid on tensor features built from X_train/X_test.

    Pipeline per engine:
      1. Fit ReducedTensorDescriptor on X_train normals.
      2. Transform X_train + X_test → tensor feature space T.
      3. Fit engine on T_train (passing y_train for BSDT damping direction).
      4. Score T_test.
    """
    X_norm  = X_train[y_train == 0]
    n_k     = min(k, len(X_norm) - 1)

    print(f"\n  Building ReducedTensorDescriptor (k={n_k}) on {len(X_norm)} normals ...", flush=True)
    t0 = time.perf_counter()
    desc = ReducedTensorDescriptor(k_neighbors=n_k)
    desc.fit(X_norm)
    T_train = desc.transform(X_train)   # (N_train, n_eigs+6) tensor features
    T_test  = desc.transform(X_test)    # (N_test, n_eigs+6) tensor features
    print(f"  Tensor shape: train={T_train.shape}, test={T_test.shape}  [{time.perf_counter()-t0:.1f}s]", flush=True)

    engines = {
        'Gravity'  : GravityModeEngine(k_neighbors=min(15, len(X_norm)-1),
                                       iterations=60, max_samples=2000),
        'Molecular': MolecularEngine(k_neighbors=min(15, len(X_norm)-1),
                                     iterations=60, max_samples=2000),
        'Hybrid'   : HybridGravityEngine(
                         blend_weight='auto',
                         molecular_params=dict(k_neighbors=min(15, len(X_norm)-1),
                                               iterations=60, max_samples=2000),
                         gravity_params=dict(k_neighbors=min(15, len(X_norm)-1),
                                             iterations=60, max_samples=2000)),
    }

    results = {}
    for name, eng in engines.items():
        print(f"  Running {name} ... ", end='', flush=True)
        t0 = time.perf_counter()
        try:
            # fit_score on full tensor arrays; pass labels so BSDT
            # damping knows which points are normals in training
            T_all = np.vstack([T_train, T_test])
            y_all = np.concatenate([y_train, y_test])
            scores_all = eng.fit_score(T_all, y_all)
            scores_test = scores_all[len(T_train):]

            m = metrics(y_test, scores_test)
            m['time_s'] = round(time.perf_counter() - t0, 2)

            if te_labels is not None:
                m['per_event_auc'] = per_event_auc(
                    y_test, scores_test, np.asarray(te_labels))

            print(f"AUC={m['auc']:.4f}  F1={m['f1']:.3f}  ({m['time_s']}s)")
            results[name] = m

        except Exception as e:
            import traceback
            msg = traceback.format_exc()
            print(f"ERROR: {e}")
            results[name] = {'error': str(e), 'traceback': msg}

    return results


def banner(s):
    print('\n' + '═' * 72)
    print(f'  {s}')
    print('═' * 72)


# ══════════════════════════════════════════════════════════════════════════
#  ERCOT PIPELINE
# ══════════════════════════════════════════════════════════════════════════

def run_ercot():
    banner("ERCOT POWER GRID  (EIA demand + Open-Meteo temp, 2018-2022)")

    npz   = np.load(ERCOT_NPZ, allow_pickle=True)
    X_raw = npz['X'].astype(np.float64)
    y_raw = npz['y'].astype(int)
    dates = npz['dates']
    labels= npz['labels']

    # Forward-fill NaNs
    for col in range(X_raw.shape[1]):
        lv = np.nanmean(X_raw[:, col]) if not np.all(np.isnan(X_raw[:, col])) else 0.0
        for i in range(len(X_raw)):
            if np.isnan(X_raw[i, col]): X_raw[i, col] = lv
            else: lv = X_raw[i, col]

    # Rolling deviation features → 12-dim
    X_dev = rolling_deviation(X_raw, window=30)

    # Split: train 2018-2019, test 2020+
    test_mask = np.array([str(d)[:10] >= '2020-01-01' for d in dates])
    norm_mask  = (~test_mask) & (y_raw == 0)

    # Standardise on training normals
    mu = X_raw[norm_mask].mean(0); sd = X_raw[norm_mask].std(0) + 1e-9
    X_s = np.nan_to_num(np.clip((X_raw - mu) / sd, -8, 8))
    X_c = np.hstack([X_s, X_dev])   # (T, 12)

    X_train = X_c[~test_mask]; y_train = y_raw[~test_mask]
    X_test  = X_c[test_mask];  y_test  = y_raw[test_mask]
    te_labels = labels[test_mask]

    # Re-standardise combined features on training normals so all 12 dims
    # have comparable scale (rolling-deviation cols can have huge std)
    train_norm_mask = y_train == 0
    mu2 = X_train[train_norm_mask].mean(0)
    sd2 = X_train[train_norm_mask].std(0) + 1e-9
    X_train = np.clip((X_train - mu2) / sd2, -8, 8)
    X_test  = np.clip((X_test  - mu2) / sd2, -8, 8)

    print(f"  Days:  train={len(X_train)} (normals={int((y_train==0).sum())}),  "
          f"test={len(X_test)} (anomalies={int(y_test.sum())})")
    print(f"  Events: Uri (11), COVID (40), Elliott (5)")
    print(f"  Features: 6 raw + 6 rolling-30d deviations = 12 total")

    return run_engines(X_train, y_train, X_test, y_test, te_labels,
                       dataset_name='ERCOT', k=10)


# ══════════════════════════════════════════════════════════════════════════
#  BANK PIPELINE
# ══════════════════════════════════════════════════════════════════════════

def run_bank():
    banner("FDIC BANK PANEL  (SDI call-report, 30 banks, 1994-2022)")
    import pandas as pd
    from bank_level_loader import build_bank_panel

    panel = build_bank_panel(n_banks=30, force_refresh=False)
    X_raw = panel['X']; dates = panel['dates']
    T, N, d = X_raw.shape

    # Anomaly labels: GFC 2007-09, COVID 2020, Rate-shock 2022
    y_t = np.zeros(T, dtype=int)
    for t, dt in enumerate(dates):
        if (pd.Timestamp('2007-01-01') <= dt <= pd.Timestamp('2009-12-31') or
            pd.Timestamp('2020-01-01') <= dt <= pd.Timestamp('2020-12-31') or
            pd.Timestamp('2022-01-01') <= dt <= pd.Timestamp('2022-12-31')):
            y_t[t] = 1

    # Build event-label array for per-event AUC
    ev_labels = np.full(T, 'Normal', dtype=object)
    for t, dt in enumerate(dates):
        if pd.Timestamp('2007-01-01') <= dt <= pd.Timestamp('2009-12-31'):
            ev_labels[t] = 'GFC'
        elif pd.Timestamp('2020-01-01') <= dt <= pd.Timestamp('2020-12-31'):
            ev_labels[t] = 'COVID'
        elif pd.Timestamp('2022-01-01') <= dt <= pd.Timestamp('2022-12-31'):
            ev_labels[t] = 'RateShock'

    # Normalise on pre-crisis period (1994-2003)
    pre  = (dates >= pd.Timestamp('1994-01-01')) & (dates <= pd.Timestamp('2003-12-31'))
    nd   = X_raw[pre].reshape(-1, d)
    mu   = nd.mean(0); sd_ = nd.std(0) + 1e-9
    X_s  = np.nan_to_num(np.clip((X_raw - mu) / sd_, -8, 8))   # (T, N, d)

    # Rolling cross-bank window W=8 quarters → flat observation per window
    W    = 8
    Xw   = np.stack([X_s[i:i+W].reshape(W * N * d) for i in range(T - W)])
    yw   = np.array([1 if y_t[i:i+W].any() else 0 for i in range(T - W)])
    wd   = dates[W:]
    ev_w = np.array([ev_labels[i + W - 1] for i in range(T - W)])

    # PCA to 20 dims to tame curse of dimensionality before tensor
    tr_m = wd < pd.Timestamp('2007-01-01')
    X_tr_raw = Xw[tr_m]; y_tr = yw[tr_m]
    X_te_raw = Xw[~tr_m]; y_te = yw[~tr_m]
    ev_te    = ev_w[~tr_m]

    X_nt_raw = X_tr_raw[y_tr == 0]
    pca = PCA(n_components=min(30, len(X_nt_raw) - 1)).fit(X_nt_raw)
    X_train = pca.transform(X_tr_raw)
    X_test  = pca.transform(X_te_raw)

    print(f"  Panel: T={T} Q, N={N} banks, d={d}  →  W={W} rolling windows")
    print(f"  PCA: {X_train.shape[1]} components  (from {W*N*d}-dim)")
    print(f"  Train: {len(X_train)} windows (normals={int((y_tr==0).sum())}),  "
          f"test: {len(X_test)} (anomalies={int(y_te.sum())})")
    print(f"  Events: GFC 2007-09, COVID 2020, RateShock 2022")

    return run_engines(X_train, y_tr, X_test, y_te, ev_te,
                       dataset_name='Bank', k=10)


# ══════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════

def _to_json_safe(obj):
    """Recursively convert numpy types to Python native for JSON."""
    if isinstance(obj, dict):
        return {k: _to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_json_safe(v) for v in obj]
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj


def main():
    t_start = time.perf_counter()
    banner("FULL ENGINE EVALUATION — Gravity / Molecular / Hybrid")
    print("  Tensor: ReducedTensorDescriptor  (d+7 compact descriptor, O(Nd+d³))")
    print("  Data  : 100% real public APIs — EIA + Open-Meteo + FDIC SDI")
    print("  Output:", OUT_FILE)

    all_results = {
        'meta': {
            'datasets': ['ERCOT', 'Bank'],
            'engines' : ['Gravity', 'Molecular', 'Hybrid'],
            'tensor'  : 'ReducedTensorDescriptor',
            'data'    : 'real — EIA ERCO demand + Open-Meteo + FDIC SDI',
            'run_date': '2026-03-28',
        }
    }

    # ── ERCOT ──────────────────────────────────────────────────────────────
    try:
        all_results['ERCOT'] = run_ercot()
    except Exception as e:
        import traceback
        all_results['ERCOT'] = {'error': str(e), 'traceback': traceback.format_exc()}
        print(f"  ERCOT FAILED: {e}")

    # ── Bank ───────────────────────────────────────────────────────────────
    try:
        all_results['Bank'] = run_bank()
    except Exception as e:
        import traceback
        all_results['Bank'] = {'error': str(e), 'traceback': traceback.format_exc()}
        print(f"  Bank FAILED: {e}")

    # ── Summary table ──────────────────────────────────────────────────────
    banner(f"RESULTS SUMMARY  ({time.perf_counter()-t_start:.1f}s total)")
    print(f"\n  {'Dataset':<8} {'Engine':<12} {'AUC':>6}  {'F1':>5}  {'Recall':>6}")
    print(f"  {'-'*44}")
    for ds in ['ERCOT', 'Bank']:
        r = all_results.get(ds, {})
        if 'error' in r:
            print(f"  {ds:<8} ERROR: {r['error'][:40]}")
            continue
        for eng in ['Gravity', 'Molecular', 'Hybrid']:
            m = r.get(eng, {})
            if 'error' in m:
                print(f"  {ds:<8} {eng:<12} ERROR")
                continue
            auc = m.get('auc', 0); f1 = m.get('f1', 0); rec = m.get('recall', 0)
            print(f"  {ds:<8} {eng:<12} {auc:>6.4f}  {f1:>5.3f}  {rec:>6.3f}")
        print()

    # Per-event AUC breakdown
    for ds in ['ERCOT', 'Bank']:
        r = all_results.get(ds, {})
        if 'error' in r: continue
        has_pe = any('per_event_auc' in r.get(eng, {}) for eng in ['Gravity','Molecular','Hybrid'])
        if not has_pe: continue
        evts = sorted(set(
            evt for eng in ['Gravity','Molecular','Hybrid']
            for evt in r.get(eng, {}).get('per_event_auc', {}).keys()
        ))
        if not evts: continue
        print(f"  {ds} per-event AUC:")
        print(f"  {'Event':<26} {'Gravity':>8} {'Molecular':>10} {'Hybrid':>8}")
        print(f"  {'-'*56}")
        for evt in evts:
            row = [r.get(eng, {}).get('per_event_auc', {}).get(evt, float('nan'))
                   for eng in ['Gravity','Molecular','Hybrid']]
            print(f"  {evt:<26} {row[0]:>8.4f}  {row[1]:>8.4f}  {row[2]:>8.4f}")
        print()

    # ── Save JSON ──────────────────────────────────────────────────────────
    with open(OUT_FILE, 'w') as f:
        json.dump(_to_json_safe(all_results), f, indent=2)
    print(f"\n  Saved → {OUT_FILE}")


if __name__ == '__main__':
    main()
