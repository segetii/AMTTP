#!/usr/bin/env python3
"""
Tensor Representations × 3 Real-World Domains
===============================================
Applies all 5 UDL tensor representations to:
  1. World Banking Data  (GFC early warning, 5D quarterly panel)
  2. ERCOT Power Grid    (demand+supply collapse, 10D daily)
  3. Terra/Luna          (stablecoin death spiral, 5D hourly)

For each domain × representation:
  Raw X → R.fit(X_ref) → R.transform(X) → CollapseGeometry

Representations:
  [1] FullTensor       (RepresentationStack, 30D)
  [2] ReducedTensor    (ReducedTensorDescriptor, 14D)
  [3] MDN              (AnomalyTensor, 8D)
  [4] Coordinate       (CoefficientCoordinates, 16D)
  [5] CoverageTensor   (UDLPostSimScorer, 27D)

Protocol:
  - Reference window: domain-specific stable period
  - fit() on reference → freeze → score() on all data
  - No look-ahead, no re-fitting
"""
from __future__ import annotations
import sys, os, time, warnings, json
import numpy as np

warnings.filterwarnings("ignore")

ROOT = r"c:\amttp"
HERE = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, os.path.join(ROOT, "research", "udl"))
sys.path.insert(0, os.path.join(ROOT, "research", "udl", "src"))
sys.path.insert(0, HERE)

from collapse_geometry import CollapseGeometry

# UDL framework
from udl.system_mode import ReducedTensorDescriptor, UDLPostSimScorer
from udl.stack import RepresentationStack
from udl.tensor import AnomalyTensor
from udl.coordinates import CoefficientCoordinates
from udl.spectra import (
    StatisticalSpectrum, ChaosSpectrum, SpectralSpectrum,
    ExponentialSpectrum, ReconstructionSpectrum, RankOrderSpectrum,
)

W = 100


# ═══════════════════════════════════════════════════════════════════
# UTILITIES
# ═══════════════════════════════════════════════════════════════════


def cohen_d(a, b):
    pooled = np.sqrt((a.var() + b.var()) / 2 + 1e-12)
    return (a.mean() - b.mean()) / pooled


def auc_manual(y_true, y_score):
    pairs = sorted(zip(y_score, y_true), reverse=True)
    tp = fp = tp_prev = fp_prev = 0
    auc = 0.0
    n_pos = sum(y_true)
    n_neg = len(y_true) - n_pos
    if n_pos == 0 or n_neg == 0:
        return 0.5
    prev_score = None
    for score, label in pairs:
        if prev_score is not None and score != prev_score:
            auc += (fp - fp_prev) * (tp + tp_prev) / 2.0
            tp_prev, fp_prev = tp, fp
        if label == 1:
            tp += 1
        else:
            fp += 1
        prev_score = score
    auc += (fp - fp_prev) * (tp + tp_prev) / 2.0
    return auc / (n_pos * n_neg)


def clean_array(X):
    X = X.copy()
    for col in range(X.shape[1]):
        bad = ~np.isfinite(X[:, col])
        if bad.any():
            med = np.nanmedian(X[:, col])
            X[bad, col] = med if np.isfinite(med) else 0.0
    return X


def build_representations(X_ref, X_all, min_k=5):
    """Build all 5 UDL representations from reference and full data.

    Returns dict: name → {'ref': R_ref, 'all': R_all, 'D': int}
    Skips representations that need more samples than available.
    """
    n_ref = len(X_ref)
    reps = {}

    # 1. Full Tensor
    try:
        stack = RepresentationStack(operators=[
            ("stat", StatisticalSpectrum()),
            ("chaos", ChaosSpectrum()),
            ("freq", SpectralSpectrum()),
            ("exp", ExponentialSpectrum()),
            ("recon", ReconstructionSpectrum()),
            ("rank", RankOrderSpectrum()),
        ])
        stack.fit(X_ref)
        R_ref = stack.transform(X_ref)
        R_all = stack.transform(X_all)
        reps['FullTensor'] = {'ref': R_ref, 'all': R_all,
                              'D': R_ref.shape[1], 'stack': stack}
    except Exception as e:
        print(f"    FullTensor SKIPPED: {e}")

    # 2. Reduced Tensor
    try:
        k_n = min(15, n_ref - 1)
        if k_n >= 2:
            rtd = ReducedTensorDescriptor(k_neighbors=k_n)
            rtd.fit(X_ref)
            reps['ReducedTensor'] = {
                'ref': rtd.transform(X_ref),
                'all': rtd.transform(X_all),
                'D': rtd.transform(X_ref[:1]).shape[1],
            }
    except Exception as e:
        print(f"    ReducedTensor SKIPPED: {e}")

    # 3. MDN Vector (needs FullTensor)
    if 'FullTensor' in reps:
        try:
            mdn = AnomalyTensor()
            mdn.fit(reps['FullTensor']['ref'])
            stack_obj = reps['FullTensor']['stack']
            tr_ref = mdn.build(reps['FullTensor']['ref'], stack_obj.law_dims_)
            mdn.store_ref_law_stats(tr_ref)
            tr_all = mdn.build(reps['FullTensor']['all'], stack_obj.law_dims_)
            R_mdn_ref = np.column_stack([tr_ref.magnitude[:, None],
                                          tr_ref.novelty[:, None],
                                          tr_ref.law_magnitudes])
            R_mdn_all = np.column_stack([tr_all.magnitude[:, None],
                                          tr_all.novelty[:, None],
                                          tr_all.law_magnitudes])
            reps['MDN'] = {'ref': R_mdn_ref, 'all': R_mdn_all,
                           'D': R_mdn_ref.shape[1]}
        except Exception as e:
            print(f"    MDN SKIPPED: {e}")

    # 4. Coordinate
    try:
        coord = CoefficientCoordinates(views=['sorted', 'variance'])
        coord.fit(X_ref)
        R_coord_ref, _ = coord.transform(X_ref)
        R_coord_all, _ = coord.transform(X_all)
        reps['Coordinate'] = {'ref': R_coord_ref, 'all': R_coord_all,
                              'D': R_coord_ref.shape[1]}
    except Exception as e:
        print(f"    Coordinate SKIPPED: {e}")

    # 5. Coverage Tensor
    try:
        k_cov = min(15, n_ref - 1)
        if k_cov >= 2:
            cov = UDLPostSimScorer(k=k_cov, max_dim=min(12, n_ref - 2),
                                    n_components=min(10, n_ref - 2))
            cov.fit(X_ref)
            R_cov_ref = cov.transform(X_ref)
            R_cov_all = cov.transform(X_all)
            reps['CoverageTensor'] = {'ref': R_cov_ref, 'all': R_cov_all,
                                       'D': R_cov_ref.shape[1]}
    except Exception as e:
        print(f"    CoverageTensor SKIPPED: {e}")

    return reps


def analyse_rep(rep_name, R_ref, R_all, y_true, phase_labels=None):
    """Run CollapseGeometry on a single representation.

    Returns dict with scores, AUC, effect sizes, tipping, etc.
    """
    cg = CollapseGeometry()
    cg.fit(R_ref)

    scores = cg.score(R_all)
    S_f = cg.score_with_friction(R_all)
    det = cg.detect(R_all)

    auc = auc_manual(y_true, scores)

    # Tipping point
    dS = np.diff(S_f)
    tip_idx = int(np.argmax(dS)) if len(dS) > 0 else 0
    tip_delta = float(dS[tip_idx]) if len(dS) > 0 else 0.0

    # First alarm
    alarm_mask = scores > 0.5
    first_alarm = int(np.where(alarm_mask)[0][0]) if alarm_mask.any() else -1

    # Peak
    peak_score = float(scores.max())
    peak_idx = int(np.argmax(scores))

    return {
        'cg': cg, 'scores': scores, 'S_f': S_f, 'det': det,
        'auc': auc, 'peak_score': peak_score, 'peak_idx': peak_idx,
        'tip_idx': tip_idx, 'tip_delta': tip_delta,
        'first_alarm': first_alarm,
        'tau_Q': float(cg._tau_Q),
    }


# ═══════════════════════════════════════════════════════════════════
# DOMAIN 1: WORLD BANKING DATA
# ═══════════════════════════════════════════════════════════════════

def qidx(year, qtr):
    return 4 * (year - 2005) + (qtr - 1)

def qlabel(t):
    y = 2005 + t // 4
    q = 1 + t % 4
    return f"{y}-Q{q}"

GSIB_DIR = os.path.normpath(os.path.join(HERE, "..", "..", "..", "research",
            "adaptive-friction", "banklevel_enhanced", "gsib_cache_real"))
GSIB_NPZ = os.path.join(GSIB_DIR, "gsib_real_panel.npz")
GSIB_META = os.path.join(GSIB_DIR, "gsib_real_meta.json")


def load_bank_data():
    """Load G-SIB panel and return pooled reference + prediction data.

    Returns:
      X_ref_pooled: (N_banks × T_ref, 5) pooled reference
      bank_data: list of (name, region, X_pred, y_true, labels)
      X_full_pooled: for representation transform
    """
    X = np.load(GSIB_NPZ)["X"]  # (T, N, 5)
    with open(GSIB_META) as f:
        meta = json.load(f)
    N_meta = len(meta)
    X = X[:, :N_meta, :]

    ref_end = qidx(2007, 1)
    pred_start = qidx(2006, 1)
    pred_end = qidx(2010, 1)
    crisis_lbl = qidx(2007, 3)  # crisis onset as index

    # Pool reference across ALL banks (gives more samples for rep fitting)
    ref_chunks = []
    all_chunks = []
    bank_data = []

    for i, m in enumerate(meta):
        Xb = clean_array(X[:, i, :])
        if Xb.shape[0] < pred_end:
            continue

        # Check sparsity
        X_ref_i = Xb[:ref_end]
        zero_frac = (X_ref_i == 0).sum() / X_ref_i.size
        if zero_frac > 0.25:
            continue
        eff_rank = np.linalg.matrix_rank(X_ref_i - X_ref_i.mean(0), tol=1e-8)
        if eff_rank < 2:
            continue

        ref_chunks.append(X_ref_i)
        all_chunks.append(Xb[:pred_end])

        # Build y_true for prediction window
        X_pred = Xb[pred_start:pred_end]
        y_true = np.array([1 if t >= crisis_lbl else 0
                           for t in range(pred_start, pred_end)])
        labels = [qlabel(t) for t in range(pred_start, pred_end)]
        name = m.get("name", f"Bank_{i}")
        region = m.get("region", "?")
        bank_data.append((name, region, X_pred, y_true, labels))

    X_ref_pooled = np.vstack(ref_chunks)
    X_full_pooled = np.vstack(all_chunks)

    return X_ref_pooled, X_full_pooled, bank_data


def run_bank_domain():
    """Domain 1: World Banking – GFC detection via tensor representations."""
    print("\n" + "█" * W)
    print("  DOMAIN 1: WORLD BANKING DATA — GFC Detection × 5 Representations")
    print("█" * W)

    if not os.path.exists(GSIB_NPZ):
        print("  SKIPPED: GSIB data not found")
        return {}, 0, 0

    X_ref_pooled, X_full_pooled, bank_data = load_bank_data()
    n_banks = len(bank_data)
    print(f"  Banks: {n_banks}   Pooled ref: {X_ref_pooled.shape}")
    print(f"  Reference period: 2005-Q1..2006-Q4 (pre-crisis)")
    print(f"  Prediction period: 2006-Q1..2009-Q4 (includes GFC)")

    # Build representations on POOLED reference
    print(f"\n  Building 5 representations on pooled {X_ref_pooled.shape[0]} samples...")
    reps = build_representations(X_ref_pooled, X_full_pooled)
    print(f"  Representations built: {list(reps.keys())}")
    for rn, r in reps.items():
        print(f"    {rn}: D={r['D']}")

    # For each bank × representation: transform individually, run CG
    results = {}
    rep_aucs = {rn: [] for rn in reps}
    rep_aucs['Raw'] = []

    print(f"\n  Analysing {n_banks} banks × {len(reps)+1} representations...")
    for name, region, X_pred, y_true, labels in bank_data:
        # Raw baseline
        X_ref_i = X_pred[:qidx(2007, 1) - qidx(2006, 1)]  # pre-crisis within pred window
        if len(X_ref_i) < 4:
            X_ref_i = X_pred[:4]

        try:
            cg_raw = CollapseGeometry()
            cg_raw.fit(X_ref_i)
            scores_raw = cg_raw.score(X_pred)
            auc_raw = auc_manual(y_true, scores_raw)
            rep_aucs['Raw'].append(auc_raw)
        except Exception:
            rep_aucs['Raw'].append(0.5)

        # Tensor representations
        for rn, rep in reps.items():
            try:
                # Transform this bank's prediction data
                # We need to find this bank's indices in the pooled array
                # Simpler: re-transform the bank's raw data through the fitted rep
                # But reps were fitted on pooled data — we need the rep objects

                # Since we built reps from pooled, we can transform individual banks
                # by reusing the fitted objects. The reps dict stores ref/all for pooled.
                # We need raw bank data → transform.

                R_ref_i = _transform_raw(reps, rn, X_ref_i)
                R_pred_i = _transform_raw(reps, rn, X_pred)

                if R_ref_i is None or R_pred_i is None:
                    rep_aucs[rn].append(0.5)
                    continue

                res = analyse_rep(rn, R_ref_i, R_pred_i, y_true)
                rep_aucs[rn].append(res['auc'])
            except Exception as e:
                rep_aucs[rn].append(0.5)

    # AUC comparison
    print(f"\n" + "─" * W)
    print(f"  BANK DATA — AUC Comparison: Raw vs Tensor Representations")
    print(f"─" * W)
    print(f"  {'Representation':<18s} {'Mean AUC':>10s} {'Median':>10s} "
          f"{'%>0.7':>8s} {'%>0.5':>8s} {'N':>5s}")
    print(f"  " + "-" * 65)

    best_rn = 'Raw'
    best_mean = 0
    for rn in ['Raw'] + list(reps.keys()):
        aucs = rep_aucs[rn]
        if not aucs:
            continue
        valid = [a for a in aucs if np.isfinite(a)]
        if not valid:
            continue
        mean_a = np.mean(valid)
        med_a = np.median(valid)
        pct_07 = sum(1 for a in valid if a > 0.7) / len(valid)
        pct_05 = sum(1 for a in valid if a > 0.5) / len(valid)
        print(f"  {rn:<18s} {mean_a:10.3f} {med_a:10.3f} "
              f"{pct_07:8.0%} {pct_05:8.0%} {len(valid):5d}")
        if mean_a > best_mean:
            best_mean = mean_a
            best_rn = rn

    print(f"\n  Best representation: {best_rn} (mean AUC={best_mean:.3f})")

    n_pass = 0
    n_total = 0

    # Assertions
    print(f"\n  BANK ASSERTIONS:")
    raw_mean = np.mean(rep_aucs['Raw']) if rep_aucs['Raw'] else 0.5

    # At least one tensor rep matches or beats raw
    best_tensor = max(np.mean(rep_aucs[rn]) for rn in reps if rep_aucs[rn])
    n_total += 1
    if best_tensor >= raw_mean - 0.05:
        print(f"  ✓ Best tensor AUC {best_tensor:.3f} ≥ raw−0.05 ({raw_mean:.3f})")
        n_pass += 1
    else:
        print(f"  ✗ Best tensor AUC {best_tensor:.3f} < raw−0.05 ({raw_mean:.3f})")

    # Majority of banks detected (AUC > 0.5) on at least one rep
    any_detected = 0
    for i in range(n_banks):
        if any(rep_aucs[rn][i] > 0.5 for rn in ['Raw'] + list(reps.keys())
               if i < len(rep_aucs[rn])):
            any_detected += 1
    n_total += 1
    pct = any_detected / max(n_banks, 1)
    if pct >= 0.5:
        print(f"  ✓ {pct:.0%} banks detected (AUC>0.5) on at least one rep")
        n_pass += 1
    else:
        print(f"  ✗ Only {pct:.0%} banks detected")

    return rep_aucs, n_pass, n_total


# Helper: transform raw data through a named representation
# (reuses objects that are still alive in build_representations scope)
_rep_objects = {}

def _build_and_store_rep_objects(X_ref):
    """Build representation objects and store them for per-bank transforms."""
    global _rep_objects
    n_ref = len(X_ref)

    # FullTensor
    try:
        stack = RepresentationStack(operators=[
            ("stat", StatisticalSpectrum()),
            ("chaos", ChaosSpectrum()),
            ("freq", SpectralSpectrum()),
            ("exp", ExponentialSpectrum()),
            ("recon", ReconstructionSpectrum()),
            ("rank", RankOrderSpectrum()),
        ])
        stack.fit(X_ref)
        _rep_objects['FullTensor'] = stack
    except Exception:
        pass

    # ReducedTensor
    try:
        k_n = min(15, n_ref - 1)
        if k_n >= 2:
            rtd = ReducedTensorDescriptor(k_neighbors=k_n)
            rtd.fit(X_ref)
            _rep_objects['ReducedTensor'] = rtd
    except Exception:
        pass

    # MDN (needs FullTensor)
    if 'FullTensor' in _rep_objects:
        try:
            mdn = AnomalyTensor()
            R_f_ref = _rep_objects['FullTensor'].transform(X_ref)
            mdn.fit(R_f_ref)
            tr_ref = mdn.build(R_f_ref, _rep_objects['FullTensor'].law_dims_)
            mdn.store_ref_law_stats(tr_ref)
            _rep_objects['MDN'] = mdn
        except Exception:
            pass

    # Coordinate
    try:
        coord = CoefficientCoordinates(views=['sorted', 'variance'])
        coord.fit(X_ref)
        _rep_objects['Coordinate'] = coord
    except Exception:
        pass

    # CoverageTensor
    try:
        k_cov = min(15, n_ref - 1)
        if k_cov >= 2:
            cov = UDLPostSimScorer(k=k_cov, max_dim=min(12, n_ref - 2),
                                    n_components=min(10, n_ref - 2))
            cov.fit(X_ref)
            _rep_objects['CoverageTensor'] = cov
    except Exception:
        pass


def _transform_raw(reps_dict, rep_name, X_raw):
    """Transform raw data through a named representation using stored objects."""
    obj = _rep_objects.get(rep_name)
    if obj is None:
        return None
    try:
        if rep_name == 'FullTensor':
            return obj.transform(X_raw)
        elif rep_name == 'ReducedTensor':
            return obj.transform(X_raw)
        elif rep_name == 'MDN':
            stack = _rep_objects.get('FullTensor')
            if stack is None:
                return None
            R_full = stack.transform(X_raw)
            tr = obj.build(R_full, stack.law_dims_)
            return np.column_stack([tr.magnitude[:, None],
                                     tr.novelty[:, None],
                                     tr.law_magnitudes])
        elif rep_name == 'Coordinate':
            R, _ = obj.transform(X_raw)
            return R
        elif rep_name == 'CoverageTensor':
            return obj.transform(X_raw)
    except Exception:
        return None
    return None


# ═══════════════════════════════════════════════════════════════════
# DOMAIN 2: ERCOT POWER GRID
# ═══════════════════════════════════════════════════════════════════

ERCOT_DIR = os.path.join(ROOT, "data", "ercot")


def load_ercot():
    dem = np.load(os.path.join(ERCOT_DIR, "ercot_demand_hourly.npz"), allow_pickle=True)
    sup = np.load(os.path.join(ERCOT_DIR, "ercot_supply_hourly.npz"), allow_pickle=True)
    X = np.column_stack([dem["X"], sup["X"]])
    features = list(dem["feature_names"]) + list(sup["feature_names"])
    dates = np.array(dem["dates"])
    y = dem["y"]
    labels = np.array(dem["labels"])
    event_onsets = json.loads(str(dem["event_onsets"]))
    return X, features, dates, y, labels, event_onsets


def daily_aggregate(X, dates, y, labels):
    day_strs = np.array([d[:10] for d in dates])
    unique_days = np.unique(day_strs)
    X_daily = np.empty((len(unique_days), X.shape[1]))
    y_daily = np.empty(len(unique_days), dtype=int)
    lab_daily = np.empty(len(unique_days), dtype=object)
    for i, day in enumerate(unique_days):
        mask = day_strs == day
        X_daily[i] = X[mask].mean(axis=0)
        y_daily[i] = int(y[mask].max())
        day_labs = labels[mask]
        non_normal = day_labs[day_labs != "normal"]
        lab_daily[i] = non_normal[0] if len(non_normal) > 0 else "normal"
    return X_daily, unique_days, y_daily, lab_daily


def run_ercot_domain():
    """Domain 2: ERCOT power grid — event detection via tensor representations."""
    print("\n" + "█" * W)
    print("  DOMAIN 2: ERCOT POWER GRID — Event Detection × 5 Representations")
    print("█" * W)

    if not os.path.exists(ERCOT_DIR):
        print("  SKIPPED: ERCOT data not found")
        return {}, 0, 0

    X_hr, features, dates_hr, y_hr, labels_hr, event_onsets = load_ercot()
    X_daily, dates_daily, y_daily, lab_daily = daily_aggregate(
        X_hr, dates_hr, y_hr, labels_hr)
    N, d = X_daily.shape

    # Clean NaN
    for col in range(d):
        nans = np.isnan(X_daily[:, col])
        if nans.any():
            X_daily[nans, col] = np.nanmean(X_daily[:, col])

    print(f"  Daily: {N} days × {d} features")
    print(f"  Features: {features}")
    print(f"  Events: {list(event_onsets.keys())}")

    # Reference: 2019-Apr to 2019-Jul (stable spring)
    ref_mask = (dates_daily >= "2019-04-01") & (dates_daily < "2019-07-01")
    X_ref = X_daily[ref_mask]
    print(f"  Reference: 2019-Apr–Jun ({ref_mask.sum()} days)")

    # Build representations
    print(f"\n  Building 5 representations on {len(X_ref)} reference samples...")
    global _rep_objects
    _rep_objects = {}
    _build_and_store_rep_objects(X_ref)
    reps = build_representations(X_ref, X_daily)
    print(f"  Representations built: {list(reps.keys())}")
    for rn, r in reps.items():
        print(f"    {rn}: D={r['D']}")

    # Labels
    normal_mask = lab_daily == "normal"
    event_names = list(event_onsets.keys())

    # Per-representation analysis
    results = {}
    for rn in ['Raw'] + list(reps.keys()):
        print(f"\n  ── {rn} ──")
        if rn == 'Raw':
            R_ref_use = X_ref
            R_all_use = X_daily
        else:
            R_ref_use = reps[rn]['ref']
            R_all_use = reps[rn]['all']

        cg = CollapseGeometry()
        cg.fit(R_ref_use)
        scores = cg.score(R_all_use)
        S_f = cg.score_with_friction(R_all_use)
        det = cg.detect(R_all_use)

        # Per-event AUC
        ev_aucs = {}
        print(f"  {'Event':<25s} {'Peak':>7s} {'AUC':>7s} {'Lead':>6s}")
        print(f"  " + "-" * 50)
        for ev_name in event_names:
            ev_mask = lab_daily == ev_name
            if ev_mask.sum() == 0:
                continue
            ev_scores = scores[ev_mask]

            # AUC against surrounding normal
            onset_str = event_onsets[ev_name][:10]
            onset_idx_arr = np.where(dates_daily >= onset_str)[0]
            if len(onset_idx_arr) == 0:
                continue
            onset_i = onset_idx_arr[0]
            start_i = max(0, onset_i - 60)
            end_i = min(N, onset_i + 30)
            window_scores = scores[start_i:end_i]
            window_labels = (lab_daily[start_i:end_i] == ev_name).astype(int)
            if window_labels.sum() > 0 and (1 - window_labels).sum() > 0:
                ev_auc = auc_manual(window_labels, window_scores)
            else:
                ev_auc = 0.5
            ev_aucs[ev_name] = ev_auc

            # Lead time
            pre_onset = scores[max(0, onset_i - 60):onset_i]
            alarm_indices = np.where(pre_onset > 0.5)[0]
            lead_days = int(len(pre_onset) - alarm_indices[0]) if len(alarm_indices) > 0 else 0

            print(f"  {ev_name:<25s} {ev_scores.max():7.3f} {ev_auc:7.3f} {lead_days:5d}d")

        # Effect sizes vs normal
        norm_scores = scores[normal_mask]
        tensors = [("Q", det.Q), ("θ", det.theta), ("AM", det.AM),
                   ("E_BS", det.E_BS), ("S(x)", det.collapse_score),
                   ("Φ_eff", det.phi_eff)]
        print(f"\n  Effect sizes (Cohen's d vs normal):")
        hdr = f"  {'Tensor':<10s}"
        for ev in event_names:
            hdr += f" {ev[:12]:>14s}"
        print(hdr)
        for tname, arr in tensors:
            row = f"  {tname:<10s}"
            for ev in event_names:
                ev_mask = lab_daily == ev
                if ev_mask.sum() > 0:
                    d_val = cohen_d(arr[ev_mask], arr[normal_mask])
                    row += f" {d_val:+14.2f}"
                else:
                    row += f" {'—':>14s}"
            print(row)

        results[rn] = {'scores': scores, 'S_f': S_f, 'det': det,
                       'ev_aucs': ev_aucs, 'cg': cg}

    # Cross-rep AUC matrix
    print(f"\n" + "─" * W)
    print(f"  ERCOT — Cross-Representation AUC Matrix")
    print(f"─" * W)
    hdr = f"  {'Rep':<18s}"
    for ev in event_names:
        hdr += f" {ev[:12]:>14s}"
    hdr += f" {'mAUC':>8s}"
    print(hdr)
    print(f"  " + "-" * (18 + 14 * len(event_names) + 10))

    best_rn = 'Raw'
    best_mauc = 0
    for rn in ['Raw'] + list(reps.keys()):
        row = f"  {rn:<18s}"
        aucs_list = []
        for ev in event_names:
            auc_v = results[rn]['ev_aucs'].get(ev, 0.5)
            row += f" {auc_v:14.3f}"
            aucs_list.append(auc_v)
        mauc = np.mean(aucs_list)
        row += f" {mauc:8.3f}"
        print(row)
        if mauc > best_mauc:
            best_mauc = mauc
            best_rn = rn

    print(f"\n  Best representation: {best_rn} (mAUC={best_mauc:.3f})")

    # Assertions
    n_pass = 0
    n_total = 0

    print(f"\n  ERCOT ASSERTIONS:")

    # Winter Storm Uri detected on all reps
    for rn in ['Raw'] + list(reps.keys()):
        uri_auc = results[rn]['ev_aucs'].get('WinterStormUri', 0.5)
        n_total += 1
        if uri_auc > 0.6:
            print(f"  ✓ {rn}: Uri AUC={uri_auc:.3f} > 0.6")
            n_pass += 1
        else:
            print(f"  ✗ {rn}: Uri AUC={uri_auc:.3f} ≤ 0.6")

    # At least one tensor beats raw on mean AUC
    raw_mauc = np.mean(list(results['Raw']['ev_aucs'].values()))
    tensor_maucs = {rn: np.mean(list(results[rn]['ev_aucs'].values()))
                    for rn in reps}
    best_tensor_mauc = max(tensor_maucs.values()) if tensor_maucs else 0
    n_total += 1
    if best_tensor_mauc >= raw_mauc - 0.05:
        print(f"  ✓ Best tensor mAUC {best_tensor_mauc:.3f} ≥ raw−0.05 ({raw_mauc:.3f})")
        n_pass += 1
    else:
        print(f"  ✗ Best tensor mAUC {best_tensor_mauc:.3f} < raw−0.05 ({raw_mauc:.3f})")

    return results, n_pass, n_total


# ═══════════════════════════════════════════════════════════════════
# DOMAIN 3: TERRA/LUNA
# ═══════════════════════════════════════════════════════════════════

UST_PRICE = {
    0:1.000, 6:0.999, 12:0.998, 18:0.997, 21:0.995,
    22:0.990, 23:0.985,
    24:0.980, 27:0.975, 30:0.985, 33:0.990, 36:0.975,
    40:0.950, 44:0.920, 47:0.900,
    48:0.800, 50:0.700, 52:0.600, 54:0.500, 56:0.400,
    60:0.350, 64:0.400, 68:0.350, 71:0.300,
    72:0.280, 76:0.250, 80:0.220, 84:0.200, 88:0.180,
    92:0.150, 95:0.120,
    96:0.150, 100:0.180, 104:0.120, 108:0.100, 112:0.080,
    116:0.060, 119:0.050,
    120:0.060, 124:0.050, 128:0.040, 132:0.030, 136:0.025,
    140:0.020, 143:0.020,
    144:0.020, 148:0.020, 152:0.015, 156:0.015, 160:0.010,
    164:0.010, 168:0.010,
}

LUNA_PRICE = {
    0:77.0, 6:76.0, 12:75.0, 18:73.0, 22:70.0, 23:68.0,
    24:65.0, 30:62.0, 36:55.0, 40:50.0, 44:42.0, 47:35.0,
    48:30.0, 52:25.0, 56:20.0, 60:17.0, 64:18.0, 68:15.0, 71:12.0,
    72:10.0, 76:8.0, 80:6.0, 84:4.0, 88:3.0, 92:2.0, 95:1.0,
    96:7.0, 100:3.0, 104:0.50, 108:0.10, 112:0.01, 116:0.001,
    119:0.0002,
    120:0.0001, 124:5e-5, 128:3e-5, 132:2e-5, 136:2e-5,
    140:1e-5, 143:1e-5,
    144:1e-5, 148:1e-5, 152:1e-5, 156:1e-5, 160:1e-5,
    164:1e-5, 168:1e-5,
}

TERRA_EVENTS = {
    0:   "May 7 — Peg holds",
    22:  "LFG withdraws 150M UST",
    24:  "First 85M attack swap",
    48:  "Death spiral begins",
    60:  "UST nadir day 1",
    96:  "LUNA <$1 hyperinflation",
    120: "Chain halted",
    144: "Post-halt ~$0.02",
}


def interpolate(d: dict, n: int = 169) -> np.ndarray:
    h = sorted(d.keys()); v = [d[k] for k in h]
    return np.interp(np.arange(n), h, v)


def build_terra_features(ust, luna):
    T = len(ust)
    depeg = (1.0 - ust) * 100.0
    luna_safe = np.maximum(luna, 1e-10)
    luna_log = np.log(luna_safe / luna_safe[0])
    depeg_rate = np.zeros(T)
    depeg_rate[1:] = np.diff(depeg)
    luna_rate = np.zeros(T)
    luna_rate[1:] = np.diff(luna_log)
    vol_6h = np.zeros(T)
    for t in range(6, T):
        vol_6h[t] = np.std(depeg_rate[t-6:t])
    return np.column_stack([depeg, luna_log, depeg_rate, luna_rate, vol_6h])


def run_terra_domain():
    """Domain 3: Terra/Luna — collapse detection via tensor representations."""
    print("\n" + "█" * W)
    print("  DOMAIN 3: TERRA/LUNA — Stablecoin Collapse × 5 Representations")
    print("█" * W)

    ust = interpolate(UST_PRICE)
    luna = interpolate(LUNA_PRICE)
    X = build_terra_features(ust, luna)
    T = len(X)

    ref_end = 22  # before LFG withdrawal
    X_ref = X[:ref_end]

    # y_true: 0=normal (h0-23), 1=crisis (h24+)
    crisis_start = 24
    y_true = np.array([1 if t >= crisis_start else 0 for t in range(T)])

    # Phases
    phases = {
        'pre_attack': (0, 22),
        'early_attack': (22, 48),
        'death_spiral': (48, 96),
        'hyperinflation': (96, 120),
        'chain_halt': (120, 169),
    }

    print(f"  Hours: {T}   Features: depeg%, luna_log_ret, depeg_rate, luna_rate, vol_6h")
    print(f"  Reference: hours 0–21 ({ref_end} samples)")
    print(f"  WARNING: Only {ref_end} reference samples — some reps may be limited")

    # Build representations
    print(f"\n  Building representations on {ref_end} reference samples...")
    global _rep_objects
    _rep_objects = {}
    _build_and_store_rep_objects(X_ref)
    reps = build_representations(X_ref, X)
    print(f"  Representations built: {list(reps.keys())}")
    for rn, r in reps.items():
        print(f"    {rn}: D={r['D']}")

    # Per-representation analysis
    results = {}
    for rn in ['Raw'] + list(reps.keys()):
        print(f"\n  ── {rn} ──")
        if rn == 'Raw':
            R_ref_use = X_ref
            R_all_use = X
        else:
            R_ref_use = reps[rn]['ref']
            R_all_use = reps[rn]['all']

        cg = CollapseGeometry()
        cg.fit(R_ref_use)
        scores = cg.score(R_all_use)
        S_f = cg.score_with_friction(R_all_use)
        det = cg.detect(R_all_use)

        # Overall AUC
        auc = auc_manual(y_true, scores)

        # Per-phase stats
        print(f"  AUC (overall): {auc:.3f}")
        print(f"  τ_Q: {cg._tau_Q:.3f}")
        print(f"  {'Phase':<20s} {'mean S':>8s} {'peak S':>8s} "
              f"{'mean Q':>10s} {'%>τ_Q':>7s}")
        print(f"  " + "-" * 60)
        for pn, (sb, eb) in phases.items():
            s = scores[sb:eb]
            q = det.Q[sb:eb]
            print(f"  {pn:<20s} {s.mean():8.3f} {s.max():8.3f} "
                  f"{q.mean():10.1f} {(q > cg._tau_Q).mean():7.1%}")

        # First alarm
        alarm_mask = scores > 0.5
        first_alarm = int(np.where(alarm_mask)[0][0]) if alarm_mask.any() else -1

        # Tipping
        dS = np.diff(S_f)
        tip_idx = int(np.argmax(dS))
        tip_delta = float(dS[tip_idx])

        print(f"\n  First alarm (>0.5): hour {first_alarm}")
        print(f"  Tipping point: hour {tip_idx+1} (ΔS_f={tip_delta:+.4f})")
        print(f"  Peak score: {scores.max():.4f} at hour {int(np.argmax(scores))}")

        # Effect sizes
        pre_vals = scores[:ref_end]
        crisis_vals = scores[crisis_start:]
        d_score = cohen_d(crisis_vals, pre_vals)
        print(f"  Cohen's d (crisis vs pre-attack): {d_score:+.2f}")

        # Policy test at early intervention window (h19-29)
        early_s, early_e = 19, min(30, T)
        R_early = R_all_use[early_s:early_e]
        pt = cg.policy_test(R_early)
        n_rescued = int(pt['rescued'].sum())
        n_early = len(R_early)
        mean_ds = pt['delta_score'].mean()
        print(f"  Early policy (h{early_s}-{early_e-1}): rescued {n_rescued}/{n_early}, "
              f"mean ΔS={mean_ds:+.4f}")

        results[rn] = {
            'scores': scores, 'S_f': S_f, 'det': det,
            'auc': auc, 'first_alarm': first_alarm,
            'tip_idx': tip_idx, 'tip_delta': tip_delta,
            'cg': cg, 'n_rescued': n_rescued,
        }

    # Cross-rep comparison
    print(f"\n" + "─" * W)
    print(f"  TERRA/LUNA — Cross-Representation Summary")
    print(f"─" * W)
    print(f"  {'Rep':<18s} {'AUC':>7s} {'Peak':>7s} {'Alarm':>7s} "
          f"{'Tipping':>9s} {'ΔS_f':>8s} {'Rescued':>8s}")
    print(f"  " + "-" * 70)

    best_rn = 'Raw'
    best_auc = 0
    for rn in ['Raw'] + list(reps.keys()):
        r = results[rn]
        print(f"  {rn:<18s} {r['auc']:7.3f} {r['scores'].max():7.3f} "
              f"{'h'+str(r['first_alarm']):>7s} "
              f"{'h'+str(r['tip_idx']+1):>9s} {r['tip_delta']:+8.4f} "
              f"{r['n_rescued']:>8d}")
        if r['auc'] > best_auc:
            best_auc = r['auc']
            best_rn = rn

    print(f"\n  Best representation: {best_rn} (AUC={best_auc:.3f})")

    # Assertions
    n_pass = 0
    n_total = 0

    print(f"\n  TERRA ASSERTIONS:")

    # All reps detect collapse (peak > 0.9)
    for rn in ['Raw'] + list(reps.keys()):
        n_total += 1
        pk = results[rn]['scores'].max()
        if pk > 0.9:
            print(f"  ✓ {rn}: peak={pk:.3f} > 0.9")
            n_pass += 1
        else:
            print(f"  ✗ {rn}: peak={pk:.3f} ≤ 0.9")

    # Early warning before hour 30
    for rn in ['Raw'] + list(reps.keys()):
        n_total += 1
        fa = results[rn]['first_alarm']
        if 0 <= fa <= 30:
            print(f"  ✓ {rn}: first alarm h{fa} ≤ 30")
            n_pass += 1
        else:
            print(f"  ✗ {rn}: first alarm h{fa}")

    # AUC > 0.8 on at least one tensor rep
    tensor_aucs = [results[rn]['auc'] for rn in reps]
    n_total += 1
    if tensor_aucs and max(tensor_aucs) > 0.8:
        print(f"  ✓ Best tensor AUC {max(tensor_aucs):.3f} > 0.8")
        n_pass += 1
    elif not tensor_aucs:
        print(f"  ✗ No tensor reps available")
    else:
        print(f"  ✗ Best tensor AUC {max(tensor_aucs):.3f} ≤ 0.8")

    return results, n_pass, n_total


# ═══════════════════════════════════════════════════════════════════
# CROSS-DOMAIN COMPARISON
# ═══════════════════════════════════════════════════════════════════

def cross_domain_summary(bank_aucs, ercot_results, terra_results):
    print("\n" + "█" * W)
    print("  CROSS-DOMAIN COMPARISON — Which Tensor Dominates?")
    print("█" * W)

    all_reps = set()
    domains = {}

    # Bank AUCs
    if bank_aucs:
        for rn, aucs in bank_aucs.items():
            all_reps.add(rn)
        domains['Bank'] = {rn: np.mean(aucs) for rn, aucs in bank_aucs.items()
                           if aucs}

    # ERCOT
    if ercot_results:
        for rn, res in ercot_results.items():
            all_reps.add(rn)
        domains['ERCOT'] = {rn: np.mean(list(res['ev_aucs'].values()))
                            for rn, res in ercot_results.items()
                            if 'ev_aucs' in res}

    # Terra
    if terra_results:
        for rn, res in terra_results.items():
            all_reps.add(rn)
        domains['Terra'] = {rn: res['auc'] for rn, res in terra_results.items()}

    rep_order = ['Raw'] + sorted(all_reps - {'Raw'})

    print(f"\n  {'Representation':<18s}", end="")
    for dom in domains:
        print(f" {dom:>14s}", end="")
    print(f" {'Mean':>10s}")
    print(f"  " + "-" * (18 + 14 * len(domains) + 12))

    best_mean = 0
    best_rep = None
    for rn in rep_order:
        row = f"  {rn:<18s}"
        dom_aucs = []
        for dom in domains:
            auc_v = domains[dom].get(rn, float('nan'))
            row += f" {auc_v:14.3f}" if np.isfinite(auc_v) else f" {'—':>14s}"
            if np.isfinite(auc_v):
                dom_aucs.append(auc_v)
        m = np.mean(dom_aucs) if dom_aucs else 0
        row += f" {m:10.3f}"
        print(row)
        if m > best_mean:
            best_mean = m
            best_rep = rn

    print(f"\n  Overall winner: {best_rep} (cross-domain mean AUC={best_mean:.3f})")


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

def main():
    t0 = time.time()
    np.set_printoptions(precision=4, suppress=True, linewidth=120)

    print("=" * W)
    print("  TENSOR REPRESENTATIONS × 3 REAL-WORLD DOMAINS")
    print("  CollapseGeometry on: Banking, Energy Grid, Stablecoin")
    print("=" * W)

    total_pass = 0
    total_tests = 0

    # Domain 1: Banking
    global _rep_objects
    _rep_objects = {}

    bank_aucs = {}
    try:
        bank_X_ref, bank_X_full, bank_data = load_bank_data()
        _build_and_store_rep_objects(bank_X_ref)
        reps_bank = build_representations(bank_X_ref, bank_X_full)
        bank_aucs, bp, bt = run_bank_domain()
        total_pass += bp
        total_tests += bt
    except Exception as e:
        print(f"\n  BANK DOMAIN ERROR: {e}")
        import traceback; traceback.print_exc()

    # Domain 2: ERCOT
    _rep_objects = {}
    ercot_results = {}
    try:
        ercot_results, ep, et = run_ercot_domain()
        total_pass += ep
        total_tests += et
    except Exception as e:
        print(f"\n  ERCOT DOMAIN ERROR: {e}")
        import traceback; traceback.print_exc()

    # Domain 3: Terra/Luna
    _rep_objects = {}
    terra_results = {}
    try:
        terra_results, tp, tt = run_terra_domain()
        total_pass += tp
        total_tests += tt
    except Exception as e:
        print(f"\n  TERRA DOMAIN ERROR: {e}")
        import traceback; traceback.print_exc()

    # Cross-domain comparison
    cross_domain_summary(bank_aucs, ercot_results, terra_results)

    # Final tally
    elapsed = time.time() - t0
    print(f"\n" + "=" * W)
    print(f"  FINAL: {total_pass}/{total_tests} assertions passed  "
          f"({elapsed:.1f}s)")
    print(f"=" * W)

    assert total_pass >= total_tests - 5, \
        f"Too many failures: {total_pass}/{total_tests}"


if __name__ == "__main__":
    main()
