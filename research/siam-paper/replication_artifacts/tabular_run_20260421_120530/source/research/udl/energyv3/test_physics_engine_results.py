#!/usr/bin/env python3
"""
Physics Engine Results — Molecular / Gravity / Hybrid
======================================================
Runs the THREE physics simulation engines from system_mode:

  1. MolecularEngine  — Lennard-Jones 6-12 dynamics, kNN pairwise
                         Euler + Lyapunov → Morse+Betti+UDL+BSDT fusion
  2. GravityModeEngine — N-body gravity, ISS adaptive control
                         BSDT+MFLS blended damping
  3. HybridGravityEngine — Adaptive blend of Molecular + Gravity
                           Auto CV blend_weight

Across: 5 UDL representations × 3 domains (Banking, ERCOT, Terra/Luna)

Summary Tables per domain:
  TABLE 1  Lead-time detection (score > threshold before onset)
  TABLE 2  Accuracy (AUC / Prec / Rec / F1 / FAR)
  TABLE 3  False alarm rate at operational thresholds
  TABLE 4  Engine comparison (operational metrics table)
  TABLE 5  AUC ranking across representations
  TABLE 6  Cross-engine best per domain
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

# ── Import data loaders and helpers from the existing test ──
from test_full_collapse_x_domains import (
    build_reps, auc_manual, clean_array,
    GSIB_NPZ, GSIB_META, qidx,
    load_ercot, daily_aggregate, ERCOT_DIR,
    interpolate, build_terra_features, UST_PRICE, LUNA_PRICE,
)

# ── Import the three physics engines ──
from udl.system_mode import MolecularEngine, GravityModeEngine, HybridGravityEngine

W = 110

ENGINE_NAMES = ['Molecular(LJ)', 'Gravity(N-body)', 'Hybrid(Mol+Grav)']


# ═══════════════════════════════════════════════════════════════════
# METRIC HELPERS
# ═══════════════════════════════════════════════════════════════════

def _lead_time(scores, onset_idx, thresholds=(0.3, 0.5, 0.7)):
    """Periods BEFORE onset where score first exceeds threshold."""
    out = {}
    for th in thresholds:
        above = np.where(scores[:onset_idx] > th)[0]
        out[th] = int(onset_idx - above[0]) if len(above) else None
    return out


def _f1_metrics(y_true, scores):
    """F1-optimal threshold → Precision, Recall, F1, FAR, AUC."""
    a = auc_manual(y_true, scores)
    n_pos, n_neg = int(y_true.sum()), int(len(y_true) - y_true.sum())
    if n_pos == 0 or n_neg == 0:
        return dict(auc=a, thresh=0, prec=0, rec=0, f1=0, far=0)

    threshs = np.unique(scores)
    if len(threshs) > 200:
        threshs = np.percentile(scores, np.linspace(0, 100, 200))

    best = dict(f1=0, thresh=0, prec=0, rec=0, far=0)
    for th in threshs:
        pred = scores >= th
        tp = int((pred & (y_true == 1)).sum())
        fp = int((pred & (y_true == 0)).sum())
        fn = int((~pred & (y_true == 1)).sum())
        p = tp / (tp + fp) if (tp + fp) else 0
        r = tp / (tp + fn) if (tp + fn) else 0
        f1 = 2 * p * r / (p + r) if (p + r) else 0
        far = fp / n_neg
        if f1 > best['f1']:
            best = dict(f1=f1, thresh=th, prec=p, rec=r, far=far)
    best['auc'] = a
    return best


def _far_at(scores, y_true, thresholds=(0.3, 0.5, 0.7)):
    normal = scores[y_true == 0]
    if len(normal) == 0:
        return {th: 0.0 for th in thresholds}
    return {th: float((normal > th).sum()) / len(normal) for th in thresholds}


def _op_metrics(y, scores, label):
    """Operational metrics: FPR, FNR, Precision, Recall, TP/FN/FP/TN, AUC."""
    thr = float(np.percentile(scores, 100 * (1 - y.mean())))
    yp  = (scores > thr).astype(int)
    auc = auc_manual(y, scores)
    tp = int(((y == 1) & (yp == 1)).sum())
    fn = int(((y == 1) & (yp == 0)).sum())
    fp = int(((y == 0) & (yp == 1)).sum())
    tn = int(((y == 0) & (yp == 0)).sum())
    fpr = fp / max(fp + tn, 1)
    fnr = fn / max(fn + tp, 1)
    prec = tp / max(tp + fp, 1)
    rec  = tp / max(tp + fn, 1)
    return {'label': label, 'auc': auc, 'fpr': fpr, 'fnr': fnr,
            'prec': prec, 'rec': rec, 'tp': tp, 'fn': fn,
            'fp': fp, 'tn': tn, 'total': int(y.sum()), 'scores': scores}


def _mask(T, ev_info):
    if isinstance(ev_info, np.ndarray) and ev_info.dtype == bool:
        return ev_info
    if isinstance(ev_info, tuple) and len(ev_info) == 2:
        m = np.zeros(T, dtype=bool)
        m[ev_info[0]:ev_info[1]] = True
        return m
    return np.zeros(T, dtype=bool)


# ═══════════════════════════════════════════════════════════════════
# DATA LOADERS  (same as test_full_engine_results.py)
# ═══════════════════════════════════════════════════════════════════

def _load_bank():
    if not os.path.exists(GSIB_NPZ):
        return None
    X_panel = np.load(GSIB_NPZ)["X"]
    with open(GSIB_META) as f:
        meta = json.load(f)
    N_meta = len(meta); X_panel = X_panel[:, :N_meta, :]
    ref_end      = qidx(2007, 1)
    pred_start   = qidx(2006, 1)
    pred_end     = qidx(2010, 1)
    crisis_start = qidx(2007, 3)

    ref_c, pred_c, y_c = [], [], []
    for i in range(N_meta):
        Xb = clean_array(X_panel[:, i, :])
        if Xb.shape[0] < pred_end:
            continue
        Xr = Xb[:ref_end]
        if (Xr == 0).sum() / Xr.size > 0.25:
            continue
        if np.linalg.matrix_rank(Xr - Xr.mean(0), tol=1e-8) < 2:
            continue
        ref_c.append(Xr)
        pred_c.append(Xb[pred_start:pred_end])
        y_c.append(np.array([1 if t >= crisis_start else 0
                              for t in range(pred_start, pred_end)]))

    X_ref  = np.vstack(ref_c)
    X_pred = np.vstack(pred_c)
    y = np.concatenate(y_c)

    events = {
        'normal':     (y == 0),
        'pre_crisis': (y == 0),
        'GFC_crisis': (y == 1),
    }
    onset = crisis_start - pred_start
    return dict(X_ref=X_ref, X_pred=X_pred, y=y, events=events,
                event_onsets={'GFC_crisis': onset}, unit="quarters",
                n_banks=len(ref_c))


def _load_ercot():
    if not os.path.exists(ERCOT_DIR):
        return None
    X_hr, features, dates_hr, y_hr, labels_hr, ev_onsets = load_ercot("combined")
    X_daily, dates, y_daily, lab = daily_aggregate(X_hr, dates_hr, y_hr, labels_hr)
    N, d = X_daily.shape
    for c in range(d):
        bad = np.isnan(X_daily[:, c])
        if bad.any():
            X_daily[bad, c] = np.nanmean(X_daily[:, c])

    ref_mask = (dates >= "2019-04-01") & (dates < "2019-07-01")
    X_ref = X_daily[ref_mask]

    events = {'normal': (lab == "normal")}
    event_indices = {}
    for ev in ev_onsets:
        events[ev] = (lab == ev)
        onset_str = ev_onsets[ev][:10]
        oi = np.where(dates >= onset_str)[0]
        if len(oi):
            event_indices[ev] = int(oi[0])

    return dict(X_ref=X_ref, X_all=X_daily, y=y_daily, events=events,
                event_onsets=event_indices, unit="days",
                features=features, dates=dates, lab=lab)


def _load_terra():
    ust  = interpolate(UST_PRICE)
    luna = interpolate(LUNA_PRICE)
    X    = build_terra_features(ust, luna)
    T    = len(X)
    y    = np.array([1 if t >= 24 else 0 for t in range(T)])
    events = {
        'normal':          (0, 22),
        'LFG_withdraw':    (22, 24),
        'first_attack':    (24, 48),
        'death_spiral':    (48, 96),
        'hyperinflation':  (96, 120),
        'chain_halt':      (120, 169),
    }
    event_onsets = {
        'LFG_withdraw': 22, 'first_attack': 24,
        'death_spiral': 48, 'hyperinflation': 96, 'chain_halt': 120,
    }
    return dict(X_ref=X[:22], X_all=X, y=y, events=events,
                event_onsets=event_onsets, unit="hours")


# ═══════════════════════════════════════════════════════════════════
# RUN PHYSICS ENGINES  (Molecular / Gravity / Hybrid × reps)
# ═══════════════════════════════════════════════════════════════════

def _run_single_engine(name, X, y):
    """Run one physics engine, return scores or None on failure."""
    t0 = time.perf_counter()
    try:
        if name == 'Molecular(LJ)':
            eng = MolecularEngine(calibrate='combined', target_far=0.05)
        elif name == 'Gravity(N-body)':
            eng = GravityModeEngine(calibrate='combined', target_far=0.05)
        elif name == 'Hybrid(Mol+Grav)':
            eng = HybridGravityEngine(calibrate='combined', target_far=0.05)
        else:
            return None, 0
        scores = eng.fit_score(X, y)
        elapsed = (time.perf_counter() - t0) * 1000
        return scores, elapsed
    except Exception as ex:
        elapsed = (time.perf_counter() - t0) * 1000
        print(f"      [{name} FAILED: {ex}]")
        return None, elapsed


def _run_engines(X_ref, X_all, y, events, domain):
    """Build 5 UDL reps, run all 3 physics engines on each."""
    print(f"\n  Building 5 UDL representations …")
    reps = build_reps(X_ref, X_all)
    rep_names = ['Raw'] + list(reps.keys())
    print(f"  Built: {rep_names}")

    # results[rep_name][engine_name] = {'scores': ..., 'time_ms': ..., 'auc': ...}
    results = {}
    for rn in rep_names:
        Ra = X_all if rn == 'Raw' else reps[rn]['all']
        D  = Ra.shape[1]

        print(f"\n  {'─' * (W-2)}")
        print(f"  {rn} ({D}D)")
        print(f"  {'─' * (W-2)}")

        results[rn] = {}
        for eng_name in ENGINE_NAMES:
            print(f"    Running {eng_name} …", end='', flush=True)
            scores, t_ms = _run_single_engine(eng_name, Ra, y)
            if scores is not None:
                auc = auc_manual(y, scores)
                results[rn][eng_name] = {
                    'scores': scores, 'time_ms': t_ms, 'auc': auc,
                }
                print(f"  AUC={auc:.4f}  ({t_ms:.0f}ms)")
            else:
                results[rn][eng_name] = None
                print(f"  FAILED ({t_ms:.0f}ms)")

    return results


# ═══════════════════════════════════════════════════════════════════
# SUMMARY TABLES
# ═══════════════════════════════════════════════════════════════════

def _summary_tables(domain, results, y, events, event_onsets, unit):
    T = len(y)

    print(f"\n{'█' * W}")
    print(f"  {domain} — PHYSICS ENGINE SUMMARY TABLES")
    print(f"{'█' * W}")

    rep_names = list(results.keys())

    # ── TABLE 1: LEAD-TIME DETECTION ──
    if event_onsets:
        print(f"\n{'═' * W}")
        print(f"  TABLE 1 — LEAD-TIME DETECTION BEFORE COLLAPSE  [{domain}]")
        print(f"{'═' * W}")
        print(f"  Lead = periods score > threshold BEFORE event onset  (unit: {unit})")

        for ev, oi in event_onsets.items():
            for eng_name in ENGINE_NAMES:
                print(f"\n  ┌─ Event: {ev}  (onset {oi})  — {eng_name}")
                print(f"  │ {'Representation':<20s} │ {'S>0.3':>8s} │ {'S>0.5':>8s} │ {'S>0.7':>8s} │ {'Best':>6s}")
                print(f"  │ {'─' * 65}")
                for rn in rep_names:
                    r = results[rn].get(eng_name)
                    if r is None:
                        print(f"  │ {rn:<20s} │   FAILED │   FAILED │   FAILED │  FAIL")
                        continue
                    lt = _lead_time(r['scores'], oi)
                    best = max((v for v in lt.values() if v is not None), default=None)
                    row = f"  │ {rn:<20s} │"
                    for th in (0.3, 0.5, 0.7):
                        v = lt[th]
                        row += f" {v:>5d} {unit[0]:s}  │" if v is not None else f"    —    │"
                    row += f" {best:>4d} {unit[0]:s}" if best is not None else f"   —"
                    print(row)
                print(f"  └{'─' * 70}")

    # ── TABLE 2: ACCURACY ──
    print(f"\n{'═' * W}")
    print(f"  TABLE 2 — PHYSICS ENGINE ACCURACY  [{domain}]")
    print(f"{'═' * W}")

    for eng_name in ENGINE_NAMES:
        print(f"\n  {eng_name} (F1-optimal threshold):")
        print(f"  {'Rep':<20s} │ {'AUC':>6s} │ {'θ*':>8s} │ {'Prec':>6s} │ {'Rec':>6s} │ {'F1':>6s} │ {'FAR':>6s}")
        print(f"  {'─' * 72}")
        for rn in rep_names:
            r = results[rn].get(eng_name)
            if r is None:
                print(f"  {rn:<20s} │   —   │     —    │   —   │   —   │   —   │   —  ")
                continue
            m = _f1_metrics(y, r['scores'])
            print(f"  {rn:<20s} │ {m['auc']:6.3f} │ {m['thresh']:8.3f} │ "
                  f"{m['prec']:6.3f} │ {m['rec']:6.3f} │ {m['f1']:6.3f} │ {m['far']:6.3f}")

    # Best engine per rep
    print(f"\n  Best Physics Engine per Representation:")
    print(f"  {'Rep':<20s} │ {'Engine':<18s} │ {'AUC':>6s} │ {'Prec':>6s} │ {'Rec':>6s} │ {'F1':>6s} │ {'FAR':>6s}")
    print(f"  {'─' * 85}")
    for rn in rep_names:
        best_eng, best_auc = None, -1
        for eng_name in ENGINE_NAMES:
            r = results[rn].get(eng_name)
            if r is not None and r['auc'] > best_auc:
                best_eng, best_auc = eng_name, r['auc']
        if best_eng is None:
            print(f"  {rn:<20s} │ {'ALL FAILED':<18s} │   —   │   —   │   —   │   —   │   —  ")
            continue
        m = _f1_metrics(y, results[rn][best_eng]['scores'])
        print(f"  {rn:<20s} │ {best_eng:<18s} │ {m['auc']:6.3f} │ "
              f"{m['prec']:6.3f} │ {m['rec']:6.3f} │ {m['f1']:6.3f} │ {m['far']:6.3f}")

    # ── TABLE 3: FALSE ALARM RATE ──
    print(f"\n{'═' * W}")
    print(f"  TABLE 3 — FALSE ALARM RATE  [{domain}]")
    print(f"{'═' * W}")
    n_norm = int((y == 0).sum())
    print(f"  FAR = false alarms / {n_norm} normal periods")

    for eng_name in ENGINE_NAMES:
        print(f"\n  {eng_name}:")
        print(f"  {'Rep':<20s} │ {'FAR@0.3':>8s} │ {'FAR@0.5':>8s} │ {'FAR@0.7':>8s}")
        print(f"  {'─' * 50}")
        for rn in rep_names:
            r = results[rn].get(eng_name)
            if r is None:
                print(f"  {rn:<20s} │   FAIL   │   FAIL   │   FAIL  ")
                continue
            f = _far_at(r['scores'], y)
            print(f"  {rn:<20s} │ {f[0.3]:7.1%} │ {f[0.5]:7.1%} │ {f[0.7]:7.1%}")

    # ── TABLE 4: OPERATIONAL METRICS ──
    print(f"\n{'═' * W}")
    print(f"  TABLE 4 — OPERATIONAL METRICS  [{domain}]")
    print(f"{'═' * W}")
    print(f"  Threshold = prevalence-matched percentile")

    hdr = (f"    {'Method':<24} {'Rep':<16} {'AUC':>6} {'Prec':>6} {'FPR':>7} {'FNR':>7}"
           f" {'Caught':>12} {'Missed':>9} {'FAlarm':>7} {'Time':>8}")
    print(f"\n{hdr}")
    print(f"    {'─' * 105}")

    for eng_name in ENGINE_NAMES:
        for rn in rep_names:
            r = results[rn].get(eng_name)
            if r is None:
                continue
            m = _op_metrics(y, r['scores'], eng_name)
            caught = f"{m['tp']:>5}/{m['total']:<5}"
            missed = f"{m['fn']:>4}/{m['total']:<4}"
            t_ms = r['time_ms']
            print(f"    {eng_name:<24} {rn:<16} {m['auc']:6.4f} {m['prec']:6.3f} "
                  f"{m['fpr']:7.4f} {m['fnr']:7.4f} {caught:>12} {missed:>9} "
                  f"{m['fp']:>7} {t_ms:>7.0f}ms")
        print(f"    {'─' * 105}")

    # ── TABLE 5: AUC RANKING ──
    print(f"\n{'═' * W}")
    print(f"  TABLE 5 — AUC RANKING  [{domain}]")
    print(f"{'═' * W}")
    print(f"  Molecular(LJ) vs Gravity(N-body) vs Hybrid(Mol+Grav)")

    hdr = f"  {'Engine':<18s} │"
    for rn in rep_names:
        hdr += f" {rn[:14]:>14s} │"
    hdr += f" {'Mean':>6s} │ {'Best Rep':<16s}"
    print(f"\n{hdr}")
    print(f"  {'─' * (18 + (16 * len(rep_names)) + 30)}")

    for eng_name in ENGINE_NAMES:
        row = f"  {eng_name:<18s} │"
        vals = []
        best_rn_for_eng, best_auc_for_eng = None, -1
        for rn in rep_names:
            r = results[rn].get(eng_name)
            if r is not None:
                row += f" {r['auc']:14.4f} │"
                vals.append(r['auc'])
                if r['auc'] > best_auc_for_eng:
                    best_rn_for_eng = rn
                    best_auc_for_eng = r['auc']
            else:
                row += f" {'FAIL':>14s} │"
        mn = np.mean(vals) if vals else 0
        row += f" {mn:6.4f} │ {best_rn_for_eng or 'N/A':<16s}"
        print(row)

    # ── TABLE 6: TIMING ──
    print(f"\n{'═' * W}")
    print(f"  TABLE 6 — EXECUTION TIME (ms)  [{domain}]")
    print(f"{'═' * W}")

    hdr = f"  {'Engine':<18s} │"
    for rn in rep_names:
        hdr += f" {rn[:14]:>14s} │"
    hdr += f" {'Mean':>8s}"
    print(f"\n{hdr}")
    print(f"  {'─' * (18 + (16 * len(rep_names)) + 12)}")

    for eng_name in ENGINE_NAMES:
        row = f"  {eng_name:<18s} │"
        times = []
        for rn in rep_names:
            r = results[rn].get(eng_name)
            if r is not None:
                row += f" {r['time_ms']:13.0f}ms │"
                times.append(r['time_ms'])
            else:
                row += f" {'FAIL':>14s} │"
        mn = np.mean(times) if times else 0
        row += f" {mn:7.0f}ms"
        print(row)


# ═══════════════════════════════════════════════════════════════════
# DOMAIN RUNNERS
# ═══════════════════════════════════════════════════════════════════

def run_banking():
    print(f"\n{'█' * W}")
    print(f"  DOMAIN 1: WORLD BANKING (GFC) — Physics Engines")
    print(f"{'█' * W}")

    data = _load_bank()
    if data is None:
        print("  SKIPPED: GSIB data not found")
        return None, None

    X_ref, X_pred, y = data['X_ref'], data['X_pred'], data['y']
    events, eo, unit = data['events'], data['event_onsets'], data['unit']
    print(f"  Banks: {data['n_banks']}  Pooled ref: {X_ref.shape}  "
          f"pred: {X_pred.shape}  crisis frac: {y.mean():.1%}")

    results = _run_engines(X_ref, X_pred, y, events, "Bank")
    _summary_tables("BANKING (GFC)", results, y, events, eo, unit)
    return results, y


def run_ercot():
    print(f"\n{'█' * W}")
    print(f"  DOMAIN 2: ERCOT POWER GRID — Physics Engines")
    print(f"{'█' * W}")

    data = _load_ercot()
    if data is None:
        print("  SKIPPED: ERCOT data not found")
        return None, None

    X_ref, X_all, y = data['X_ref'], data['X_all'], data['y']
    events, eo, unit = data['events'], data['event_onsets'], data['unit']
    print(f"  Daily: {X_all.shape}  ref: {X_ref.shape}  crisis frac: {y.mean():.1%}")

    results = _run_engines(X_ref, X_all, y, events, "ERCOT")
    _summary_tables("ERCOT (Power Grid)", results, y, events, eo, unit)
    return results, y


def run_terra():
    print(f"\n{'█' * W}")
    print(f"  DOMAIN 3: TERRA/LUNA — Physics Engines")
    print(f"{'█' * W}")

    data = _load_terra()
    X_ref, X_all, y = data['X_ref'], data['X_all'], data['y']
    events, eo, unit = data['events'], data['event_onsets'], data['unit']
    print(f"  Hours: {len(X_all)}  ref: {X_ref.shape}  crisis frac: {y.mean():.1%}")

    results = _run_engines(X_ref, X_all, y, events, "Terra")
    _summary_tables("TERRA/LUNA", results, y, events, eo, unit)
    return results, y


# ═══════════════════════════════════════════════════════════════════
# CROSS-DOMAIN SUMMARY
# ═══════════════════════════════════════════════════════════════════

def cross_domain(bank, ercot, terra):
    print(f"\n{'█' * W}")
    print(f"  CROSS-DOMAIN SUMMARY — Physics Engines")
    print(f"{'█' * W}")

    domains = {}
    if bank[0] is not None:
        domains['Banking'] = bank
    if ercot[0] is not None:
        domains['ERCOT'] = ercot
    if terra[0] is not None:
        domains['Terra'] = terra

    # Best engine per domain (highest AUC across all reps)
    print(f"\n  A. Best Physics Engine per Domain:")
    print(f"  {'Domain':<12s} │ {'Rep':<16s} │ {'Engine':<18s} │ {'AUC':>6s} │ {'Prec':>6s} │ {'Rec':>6s} │ {'F1':>6s} │ {'FAR':>6s}")
    print(f"  {'─' * 95}")

    for dom_name, (results, y) in domains.items():
        best_rn, best_eng, best_auc = None, None, -1
        for rn, eng_dict in results.items():
            for eng_name, r in eng_dict.items():
                if r is not None and r['auc'] > best_auc:
                    best_rn, best_eng, best_auc = rn, eng_name, r['auc']
        if best_rn is not None:
            m = _f1_metrics(y, results[best_rn][best_eng]['scores'])
            print(f"  {dom_name:<12s} │ {best_rn:<16s} │ {best_eng:<18s} │ {m['auc']:6.3f} │ "
                  f"{m['prec']:6.3f} │ {m['rec']:6.3f} │ {m['f1']:6.3f} │ {m['far']:6.3f}")

    # Per-engine cross-domain mean AUC
    print(f"\n  B. Cross-Domain Mean AUC per Engine:")
    print(f"  {'Engine':<18s} │", end='')
    for dom_name in domains:
        print(f" {dom_name:>10s} │", end='')
    print(f" {'Overall':>8s}")
    print(f"  {'─' * (18 + 13 * len(domains) + 12)}")

    for eng_name in ENGINE_NAMES:
        row = f"  {eng_name:<18s} │"
        all_aucs = []
        for dom_name, (results, y) in domains.items():
            aucs = []
            for rn, eng_dict in results.items():
                r = eng_dict.get(eng_name)
                if r is not None:
                    aucs.append(r['auc'])
            if aucs:
                best = max(aucs)
                row += f" {best:10.4f} │"
                all_aucs.append(best)
            else:
                row += f" {'FAIL':>10s} │"
        overall = np.mean(all_aucs) if all_aucs else 0
        row += f" {overall:8.4f}"
        print(row)

    # Per-engine best representation across domains
    print(f"\n  C. Best Representation per Engine per Domain:")
    print(f"  {'Engine':<18s} │", end='')
    for dom_name in domains:
        print(f" {dom_name + ' (rep)':>22s} │", end='')
    print()
    print(f"  {'─' * (18 + 24 * len(domains) + 4)}")

    for eng_name in ENGINE_NAMES:
        row = f"  {eng_name:<18s} │"
        for dom_name, (results, y) in domains.items():
            best_rn, best_a = "N/A", -1
            for rn, eng_dict in results.items():
                r = eng_dict.get(eng_name)
                if r is not None and r['auc'] > best_a:
                    best_rn, best_a = rn, r['auc']
            if best_a > 0:
                row += f" {best_rn[:14]:>14s} {best_a:.3f} │"
            else:
                row += f" {'FAIL':>22s} │"
        print(row)


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    t_start = time.perf_counter()

    print("=" * W)
    print("  PHYSICS ENGINE BENCHMARK")
    print("  MolecularEngine (Lennard-Jones) │ GravityModeEngine (N-body) │ HybridGravityEngine")
    print("  Euler + Lyapunov integration │ BSDT+MFLS damping │ Auto CV blend")
    print("  × 5 UDL representations × 3 domains")
    print("=" * W)

    bank  = run_banking()
    ercot = run_ercot()
    terra = run_terra()

    cross_domain(bank, ercot, terra)

    elapsed = time.perf_counter() - t_start
    print(f"\n{'=' * W}")
    print(f"  COMPLETED in {elapsed:.1f}s")
    print(f"{'=' * W}")
