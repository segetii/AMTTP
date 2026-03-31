#!/usr/bin/env python3
"""
FROZEN WINDOW SCORER — Full Cybersecurity Validation (NO sample reduction)
==========================================================================

The Frozen Calibration Protocol on full-size cybersecurity datasets.

  Geometry (radial Q on C*) + Trigonometry (angular d on S^{d-1})
  = COMPLETE anomaly representation.  No separate families needed.

  Features (all O(N*d)):
    Q         : radial Mahalanobis distance (chi^2(d) under H0)
    theta     : angular isolation from frozen reference centroid
    AM        : angular Mahalanobis on S^{d-1}
    Q*theta   : radial-angular cross-interaction
    K*theta   : curvature-weighted angular deviation

  Scoring:
    FrozenWindow   : unsupervised (frozen z-scores, Fisher VR weights)
    FW+Friction    : with adaptive friction pre-processing
    FW+ExpoGate   : supervised (QuadSurf -> tanh -> sigmoid gating)
    FW+SignedLR    : supervised (logistic regression, interpretable weights)
    FW+QuadSurf   : supervised (polynomial ridge)

  Experiments:
    1) APT Detection       CIC-IDS-2017 (2.8M flows, FULL)
    2) Zero-Day Detection  UNSW-NB15 (leave-one-out, FULL)

  All parameters frozen on normal reference window.  No re-estimation.

Author: Odeyemi Olusegun Israel
"""

import sys, os, time, warnings
sys.path.insert(0, r'c:\amttp\research\udl')
os.environ['CUDA_VISIBLE_DEVICES'] = ''
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
warnings.filterwarnings('ignore')

import numpy as np
from pathlib import Path
from collections import Counter
from sklearn.metrics import roc_auc_score

ROOT = Path(r'c:\amttp')
CYBER_DIR = ROOT / 'data' / 'external_validation' / 'cyber'

ENGINE_NAMES = ['FrozenWindow', 'FW+Friction', 'FW+ExpoGate',
                'FW+SignedLR', 'FW+QuadSurf']


# ======================================================================
#  Utilities
# ======================================================================

def load_dataset(name: str):
    """Load a cyber dataset, return (X, y_binary, attack_labels)."""
    path = CYBER_DIR / f'{name}.npz'
    if not path.exists():
        raise FileNotFoundError(f"Dataset {path} not found")
    d = np.load(path, allow_pickle=True)
    X = d['X10'] if 'X10' in d else d['X_full']
    y = d['y'].astype(int)
    at_key = 'attack_types' if 'attack_types' in d else 'attack_categories'
    attack_types = d[at_key] if at_key in d else np.array(['unknown'] * len(y))
    print(f"  Loaded {name}: {len(y):,} flows, {int(y.sum()):,} attacks "
          f"({100*y.mean():.1f}%), {X.shape[1]}D")
    return X, y, attack_types


def op_metrics(y_true, scores):
    """Compute operational metrics."""
    thr = float(np.percentile(scores, 100 * (1 - y_true.mean())))
    y_pred = (scores > thr).astype(int)
    tp = int(((y_true == 1) & (y_pred == 1)).sum())
    fn = int(((y_true == 1) & (y_pred == 0)).sum())
    fp = int(((y_true == 0) & (y_pred == 1)).sum())
    tn = int(((y_true == 0) & (y_pred == 0)).sum())
    auc = roc_auc_score(y_true, scores) if len(np.unique(y_true)) > 1 else 0.5
    fpr = fp / max(fp + tn, 1)
    fnr = fn / max(fn + tp, 1)
    prec = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    f1 = 2 * prec * recall / max(prec + recall, 1e-10)
    return dict(auc=auc, f1=f1, prec=prec, recall=recall,
                fpr=fpr, fnr=fnr, tp=tp, fn=fn, fp=fp, tn=tn)


def print_results_table(results: dict, title: str):
    """Print formatted results table."""
    print(f"\n  {title}")
    hdr = (f"    {'Engine':<18} {'AUC':>6} {'F1':>6} {'Prec':>6} "
           f"{'Recall':>7} {'FPR':>7} {'Time':>8} {'Caught':>12}")
    print(hdr)
    print("    " + "-" * 80)
    for name, m in results.items():
        caught = f"{m['tp']}/{m['tp']+m['fn']}"
        t_str = f"{m.get('time', 0):.2f}s"
        print(f"    {name:<18} {m['auc']:6.4f} {m['f1']:6.3f} {m['prec']:6.3f} "
              f"{m['recall']:7.3f} {m['fpr']:7.4f} {t_str:>8} {caught:>12}")
    print("    " + "-" * 80)


def per_attack_breakdown(results: dict, y_test, attack_test, engine_name: str):
    """Per-attack-type detection for a specific engine."""
    if engine_name not in results or 'scores' not in results[engine_name]:
        return
    scores = results[engine_name]['scores']
    thr = float(np.percentile(scores, 100 * (1 - y_test.mean())))
    y_pred = (scores > thr).astype(int)

    cats = Counter(attack_test[y_test == 1])
    if len(cats) < 2:
        return
    print(f"\n    Per-attack detection ({engine_name}):")
    print(f"    {'Attack':<25} {'Total':>6} {'Caught':>7} {'Rate':>7}")
    print("    " + "-" * 50)
    for atype, count in sorted(cats.items(), key=lambda x: -x[1]):
        mask = (attack_test == atype) & (y_test == 1)
        detected = int(y_pred[mask].sum())
        rate = 100 * detected / count if count > 0 else 0
        marker = " ***" if rate < 20 else ""
        print(f"    {str(atype):<25} {count:>6} {detected:>7} {rate:>6.1f}%{marker}")


# ======================================================================
#  FROZEN WINDOW SCORING (the complete system)
# ======================================================================

def score_frozen_window(X_train, y_train, X_test, y_test,
                        mode='unsupervised', verbose=True):
    """
    Score using the FrozenWindowScorer — the complete system.

    Geometry (Q) + Trigonometry (theta) = full representation.
    All parameters frozen on normal reference window.

    mode='unsupervised'   : frozen ellipsoid on normals, no labels
    mode='semisupervised' : frozen ellipsoid on normals, labels for
                            ExpoGate/SignedLR/QuadSurf only
    """
    from geo_full_pipeline import FrozenWindowScorer
    from udl.system_mode import UDLPostSimScorer

    # Reference window = normal training data (raw, not pre-standardised)
    X_normal = X_train[y_train == 0]

    # ── Project all data through UDLPostSimScorer to form the tensor ──
    udl = UDLPostSimScorer(k=15, max_dim=12, n_components=10)
    udl.fit(X_normal)
    X_train_udl = udl.transform(X_train)
    X_test_udl = udl.transform(X_test)
    X_normal_udl = X_train_udl[y_train == 0]

    if verbose:
        label = 'Unsupervised' if mode == 'unsupervised' else 'Semi-supervised'
        print(f"      {label}: {len(X_normal_udl):,} normals for frozen window | "
              f"{len(X_train_udl):,} train | {len(X_test_udl):,} test (UDL tensor)")

    results = {}

    # ── Fit frozen window on UDL tensor ──
    t0 = time.perf_counter()
    fw = FrozenWindowScorer()
    fw.fit(X_normal_udl)
    dt_fit = time.perf_counter() - t0

    # ── Unsupervised: pure frozen window ──
    t0 = time.perf_counter()
    s_fw = fw.score(X_test_udl)
    dt = time.perf_counter() - t0 + dt_fit
    m = op_metrics(y_test, s_fw)
    m['scores'] = s_fw; m['time'] = dt
    results['FrozenWindow'] = m
    if verbose:
        print(f"    {'FrozenWindow':<18}: AUC={m['auc']:.4f}, F1={m['f1']:.3f} ({dt:.2f}s)")

    # ── With adaptive friction ──
    t0 = time.perf_counter()
    s_af = fw.score_with_friction(X_test_udl)
    dt = time.perf_counter() - t0
    m = op_metrics(y_test, s_af)
    m['scores'] = s_af; m['time'] = dt
    results['FW+Friction'] = m
    if verbose:
        print(f"    {'FW+Friction':<18}: AUC={m['auc']:.4f}, F1={m['f1']:.3f} ({dt:.2f}s)")

    # ── Supervised variants (labels used for weighting, not geometry) ──
    y_fit = y_train if mode == 'semisupervised' else np.zeros(len(X_train_udl))

    # ExpoGate
    t0 = time.perf_counter()
    fw.fit_expogate(X_train_udl, y_fit)
    s_eg = fw.score_expogate(X_test_udl)
    dt = time.perf_counter() - t0
    m = op_metrics(y_test, s_eg)
    m['scores'] = s_eg; m['time'] = dt
    results['FW+ExpoGate'] = m
    if verbose:
        print(f"    {'FW+ExpoGate':<18}: AUC={m['auc']:.4f}, F1={m['f1']:.3f} ({dt:.2f}s)")

    # SignedLR
    t0 = time.perf_counter()
    fw.fit_signed_lr(X_train_udl, y_fit)
    s_slr = fw.score_signed_lr(X_test_udl)
    dt = time.perf_counter() - t0
    m = op_metrics(y_test, s_slr)
    m['scores'] = s_slr; m['time'] = dt
    results['FW+SignedLR'] = m
    if verbose:
        print(f"    {'FW+SignedLR':<18}: AUC={m['auc']:.4f}, F1={m['f1']:.3f} ({dt:.2f}s)")
        w = fw.lr_weights()
        ch = ['bias', 'Q', 'theta', 'AM', 'Qxtheta', 'Kxtheta', 'MFLS']
        wstr = ', '.join(f"{ch[i]}={w[i]:+.3f}" for i in range(len(w)))
        print(f"      LR weights: {wstr}")

    # QuadSurf
    t0 = time.perf_counter()
    fw.fit_quadsurf(X_train_udl, y_fit)
    s_qs = fw.score_quadsurf(X_test_udl)
    dt = time.perf_counter() - t0
    m = op_metrics(y_test, s_qs)
    m['scores'] = s_qs; m['time'] = dt
    results['FW+QuadSurf'] = m
    if verbose:
        print(f"    {'FW+QuadSurf':<18}: AUC={m['auc']:.4f}, F1={m['f1']:.3f} ({dt:.2f}s)")

    return results, y_test


# ======================================================================
#  EXPERIMENT 1:  APT DETECTION  (CIC-IDS-2017, FULL SIZE)
# ======================================================================

def experiment_apt_detection():
    print("\n" + "=" * 80)
    print("  EXPERIMENT 1: APT DETECTION -- Frozen Window (FULL DATASET)")
    print("  Geometry + Trigonometry = Complete Representation")
    print("  Frozen Calibration Protocol -- NO sample reduction")
    print("=" * 80)

    print("\n  Loading CIC-IDS-2017 V2...")
    X_cic, y_cic, at_cic = load_dataset('cicids2017_v2')

    at_str = np.array([str(a).strip() for a in at_cic])
    unique_attacks = Counter(at_str[y_cic == 1])
    print(f"\n  Attack type distribution:")
    for atype, count in sorted(unique_attacks.items(), key=lambda x: -x[1]):
        print(f"    {atype:<30} {count:>8}")

    # Classify APT-like vs bulk
    apt_types_found = set()
    bulk_types_found = set()
    for atype in unique_attacks:
        is_apt = False
        for apt_kw in ['Infiltration', 'Heartbleed', 'SSH-Patator',
                       'FTP-Patator', 'Web Attack', 'Bot', 'Backdoor',
                       'Shellcode', 'Reconnaissance', 'Analysis',
                       'Exploits', 'Generic']:
            if apt_kw.lower() in atype.lower():
                is_apt = True
                break
        if is_apt:
            apt_types_found.add(atype)
        else:
            bulk_types_found.add(atype)

    print(f"\n  APT-like types ({len(apt_types_found)}): {apt_types_found}")
    print(f"  Bulk types ({len(bulk_types_found)}): {bulk_types_found}")

    is_normal = y_cic == 0
    is_apt = np.array([at_str[i] in apt_types_found for i in range(len(y_cic))])
    is_bulk = (y_cic == 1) & ~is_apt

    n_normal = int(is_normal.sum())
    n_apt = int(is_apt.sum())
    n_bulk = int(is_bulk.sum())
    print(f"\n  Normal: {n_normal:,}  |  Bulk: {n_bulk:,}  |  APT-like: {n_apt:,}")

    if n_apt < 10:
        print("  WARNING: Very few APT-like samples. Using UNSW-NB15.")
        return experiment_apt_unsw()

    rng = np.random.RandomState(42)
    normal_idx = np.where(is_normal)[0]
    bulk_idx = np.where(is_bulk)[0]
    apt_idx = np.where(is_apt)[0]

    # FULL SIZE: ALL normals and ALL bulk for training
    rng.shuffle(normal_idx)
    split = int(0.6 * len(normal_idx))
    train_normal_idx = normal_idx[:split]
    test_normal_idx = normal_idx[split:]

    train_idx = np.concatenate([train_normal_idx, bulk_idx])
    test_idx = np.concatenate([test_normal_idx, apt_idx])

    X_train, y_train = X_cic[train_idx], y_cic[train_idx]
    X_test, y_test = X_cic[test_idx], y_cic[test_idx]
    at_test = at_str[test_idx]

    print(f"\n  TRAIN: {len(X_train):,} ({int((y_train==0).sum()):,} normal + "
          f"{int((y_train==1).sum()):,} bulk attacks)")
    print(f"  TEST:  {len(X_test):,} ({int((y_test==0).sum()):,} normal + "
          f"{int((y_test==1).sum()):,} APT-like attacks)  <- FULL SIZE")

    # ── Approach A: Unsupervised ──
    print(f"\n  --- Approach A: Unsupervised (normals only, frozen) ---")
    t0 = time.perf_counter()
    res_A, yt_A = score_frozen_window(X_train, y_train, X_test, y_test,
                                       mode='unsupervised')
    dt_A = time.perf_counter() - t0
    print_results_table(res_A, f"APT Detection -- Unsupervised [{dt_A:.1f}s total]")

    # ── Approach B: Semi-supervised ──
    print(f"\n  --- Approach B: Semi-supervised (frozen geometry, labels for scoring) ---")
    t0 = time.perf_counter()
    res_B, yt_B = score_frozen_window(X_train, y_train, X_test, y_test,
                                       mode='semisupervised')
    dt_B = time.perf_counter() - t0
    print_results_table(res_B, f"APT Detection -- Semi-supervised [{dt_B:.1f}s total]")

    # Per-attack breakdown
    best_engine = max(res_B, key=lambda k: res_B[k].get('auc', 0))
    per_attack_breakdown(res_B, y_test, at_test, best_engine)

    return res_A, res_B


def experiment_apt_unsw():
    """Fallback APT on UNSW-NB15."""
    print("\n  Using UNSW-NB15 for APT...")
    X, y, at = load_dataset('unsw_nb15')
    at_str = np.array([str(a).strip() for a in at])
    unique_attacks = Counter(at_str[y == 1])

    apt_types = {'Backdoor', 'Backdoors', 'Shellcode', 'Worms',
                 'Reconnaissance', 'Analysis', 'Exploits'}
    apt_found = {a for a in unique_attacks if any(k.lower() in a.lower()
                 for k in apt_types)}

    is_normal = y == 0
    is_apt = np.array([at_str[i] in apt_found for i in range(len(y))])
    is_bulk = (y == 1) & ~is_apt

    rng = np.random.RandomState(42)
    normal_idx = np.where(is_normal)[0]
    bulk_idx = np.where(is_bulk)[0]
    apt_idx = np.where(is_apt)[0]

    rng.shuffle(normal_idx)
    split = int(0.6 * len(normal_idx))
    train_normal = normal_idx[:split]
    test_normal = normal_idx[split:]
    train_idx = np.concatenate([train_normal, bulk_idx])
    test_idx = np.concatenate([test_normal, apt_idx])

    X_train, y_train = X[train_idx], y[train_idx]
    X_test, y_test = X[test_idx], y[test_idx]
    at_test = at_str[test_idx]

    print(f"\n  TRAIN: {len(X_train):,}  |  TEST: {len(X_test):,}")

    print(f"\n  --- Approach A: Unsupervised ---")
    res_A, _ = score_frozen_window(X_train, y_train, X_test, y_test,
                                    mode='unsupervised')
    print_results_table(res_A, "APT -- Unsupervised")

    print(f"\n  --- Approach B: Semi-supervised ---")
    res_B, _ = score_frozen_window(X_train, y_train, X_test, y_test,
                                    mode='semisupervised')
    print_results_table(res_B, "APT -- Semi-supervised")

    best = max(res_B, key=lambda k: res_B[k].get('auc', 0))
    per_attack_breakdown(res_B, y_test, at_test, best)
    return res_A, res_B


# ======================================================================
#  EXPERIMENT 2:  ZERO-DAY DETECTION  (UNSW-NB15, FULL SIZE)
# ======================================================================

def experiment_zeroday_detection():
    print("\n\n" + "=" * 80)
    print("  EXPERIMENT 2: ZERO-DAY DETECTION -- Frozen Window (FULL DATASET)")
    print("  Leave-one-out: train on known attacks -> detect UNSEEN type")
    print("  Geometry + Trigonometry = Complete Representation")
    print("=" * 80)

    datasets_to_try = ['unsw_nb15']
    all_zeroday = {}

    for ds_name in datasets_to_try:
        try:
            print(f"\n  {'='*70}")
            print(f"  Dataset: {ds_name.upper()}")
            print(f"  {'='*70}")
            X, y, at = load_dataset(ds_name)
            at_str = np.array([str(a).strip() for a in at])

            unique_attacks = Counter(at_str[y == 1])
            print(f"\n  Attack categories ({len(unique_attacks)}):")
            for atype, count in sorted(unique_attacks.items(), key=lambda x: -x[1]):
                print(f"    {atype:<30} {count:>8}")

            min_samples = 50
            testable = {a: c for a, c in unique_attacks.items() if c >= min_samples}
            testable = dict(sorted(testable.items(), key=lambda x: -x[1]))
            print(f"\n  Testable categories (>={min_samples} samples): {len(testable)}")

            rng = np.random.RandomState(42)
            zeroday_results = {}

            for held_out in sorted(testable, key=lambda x: -testable[x]):
                print(f"\n  --- Zero-day: '{held_out}' ({testable[held_out]:,} samples) ---")

                is_held_out = (at_str == held_out) & (y == 1)
                train_mask = ~is_held_out

                train_idx = np.where(train_mask)[0]
                X_train = X[train_idx]
                y_train = y[train_idx]

                attack_idx = np.where(is_held_out)[0]
                normal_idx = np.where(y == 0)[0]
                n_test_normal = min(len(attack_idx) * 2, len(normal_idx))
                test_normal_idx = rng.choice(normal_idx, n_test_normal, replace=False)
                test_idx = np.concatenate([test_normal_idx, attack_idx])
                X_test = X[test_idx]
                y_test = y[test_idx]

                print(f"    Train: {len(X_train):,} ({int((y_train==0).sum()):,} normal + "
                      f"{int((y_train==1).sum()):,} known attacks)")
                print(f"    Test:  {len(X_test):,} ({int((y_test==0).sum()):,} normal + "
                      f"{int((y_test==1).sum()):,} '{held_out}' [NEVER SEEN])")

                # Semi-supervised
                res_B, _ = score_frozen_window(X_train, y_train, X_test, y_test,
                                                mode='semisupervised', verbose=True)
                # Unsupervised
                res_A, _ = score_frozen_window(X_train, y_train, X_test, y_test,
                                                mode='unsupervised', verbose=False)

                zeroday_results[held_out] = {
                    'A': res_A, 'B': res_B,
                    'n_attack': testable[held_out],
                }

            # ── Summary table ──
            print(f"\n  {'='*70}")
            print(f"  ZERO-DAY SUMMARY -- {ds_name.upper()}")
            print(f"  {'='*70}")

            print(f"\n  Semi-Supervised AUC on UNSEEN attack type:")
            hdr = f"    {'Zero-Day':<18} {'N':>5}"
            for en in ENGINE_NAMES:
                hdr += f" {en:>14}"
            print(hdr)
            print("    " + "-" * (23 + 15 * len(ENGINE_NAMES)))

            for atype in sorted(zeroday_results, key=lambda x: -zeroday_results[x]['n_attack']):
                zr = zeroday_results[atype]
                row = f"    {atype:<18} {zr['n_attack']:>5}"
                for en in ENGINE_NAMES:
                    auc = zr['B'].get(en, {}).get('auc', 0)
                    row += f" {auc:>14.4f}"
                print(row)

            # Average
            print(f"\n  Average AUC:")
            for approach, label in [('A', 'Unsupervised'), ('B', 'Semi-supervised')]:
                row = f"    {label:<20}"
                for en in ENGINE_NAMES:
                    aucs = [zr[approach].get(en, {}).get('auc', 0)
                            for zr in zeroday_results.values()]
                    row += f" {np.mean(aucs):>14.4f}"
                print(row)

            all_zeroday[ds_name] = zeroday_results

        except Exception as e:
            print(f"  ERROR on {ds_name}: {e}")
            import traceback; traceback.print_exc()

    return all_zeroday


# ======================================================================
#  MAIN
# ======================================================================

def main():
    print("=" * 80)
    print("  FROZEN WINDOW SCORER -- CYBERSECURITY VALIDATION")
    print("  Geometry + Trigonometry = Complete Representation")
    print("  Frozen Calibration Protocol | O(N*d) | FULL DATASET")
    print("=" * 80)

    t_start = time.perf_counter()

    apt_A, apt_B = experiment_apt_detection()
    zeroday = experiment_zeroday_detection()

    t_total = time.perf_counter() - t_start

    # ── Final summary ──
    print("\n\n" + "=" * 80)
    print("  FINAL SUMMARY -- Frozen Window Cybersecurity Validation")
    print("=" * 80)

    print(f"\n  EXPERIMENT 1 -- APT Detection:")
    for label, res in [('Unsupervised', apt_A), ('Semi-supervised', apt_B)]:
        print(f"\n    {label}:")
        for en in ENGINE_NAMES:
            if en not in res:
                continue
            auc, f1 = res[en]['auc'], res[en]['f1']
            t = res[en].get('time', 0)
            print(f"      {en:<18}: AUC={auc:.4f}, F1={f1:.3f} ({t:.2f}s)")

    print(f"\n  EXPERIMENT 2 -- Zero-Day Detection:")
    for ds_name, zr_dict in zeroday.items():
        if not zr_dict:
            continue
        print(f"    Dataset: {ds_name}")
        for atype, zr in sorted(zr_dict.items(), key=lambda x: -x[1]['n_attack']):
            best = max(zr['B'], key=lambda k: zr['B'][k].get('auc', 0))
            best_auc = zr['B'][best]['auc']
            print(f"      '{atype}': best={best} AUC={best_auc:.4f} (N={zr['n_attack']:,})")

    print(f"\n  Total runtime: {t_total:.1f}s")
    print(f"\n  Protocol: Frozen Calibration (Algorithm 2)")
    print(f"  Representation: Geometry (Q) + Trigonometry (theta, AM) = COMPLETE")
    print(f"  Features: Q, theta, AM, Q*theta, K*theta  (5-dim, O(N*d))")
    print(f"  Thresholds: chi^2(d) theory for Q, frozen percentiles for angular")
    print(f"  No kNN trees, no pairwise distances, no separate families.")


if __name__ == '__main__':
    main()
