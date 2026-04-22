#!/usr/bin/env python3
"""
Causal Physics Engine Evaluation — SIAM Paper Protocol
========================================================
Strictly prospective ("the model never sees the future"):

  1. Representations are fitted on PRE-CRISIS reference data only
  2. Physics engines receive y=None (no crisis labels ever)
  3. Thresholds are set from calibration-period score distribution only
  4. Expanding-window variant: at each time step t, score using only data [0..t]
  5. Conformal p-values provide distribution-free alarm probabilities

Three evaluation modes:
  A. Conformal split  — fit_reference(X_ref) → score_conformal(X_test)
  B. Percentile freeze — score all, set threshold from ref-period percentile
  C. Expanding window  — re-score at each step with data up to t

Domains: Banking GFC (quarterly), ERCOT (daily), Terra/Luna (hourly)
Engines: Molecular(LJ), Gravity(N-body), Hybrid(Mol+Grav)
Reps:    Raw, FullTensor, ReducedTensor, MDN, Coordinate, CoverageTensor
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

from test_full_collapse_x_domains import (
    build_reps, auc_manual, clean_array,
    GSIB_NPZ, GSIB_META, qidx,
    load_ercot, daily_aggregate, ERCOT_DIR,
    interpolate, build_terra_features, UST_PRICE, LUNA_PRICE,
)
from udl.system_mode import MolecularEngine, GravityModeEngine, HybridGravityEngine

W = 110
ENGINE_CLS = {
    'Molecular(LJ)':     MolecularEngine,
    'Gravity(N-body)':   GravityModeEngine,
    'Hybrid(Mol+Grav)':  HybridGravityEngine,
}
ENGINE_NAMES = list(ENGINE_CLS.keys())
REP_NAMES_ALL = ['Raw', 'FullTensor', 'ReducedTensor', 'MDN', 'Coordinate', 'CoverageTensor']

# ═══════════════════════════════════════════════════════════════════
#  CAUSAL SCORING — y is NEVER passed to engines
# ═══════════════════════════════════════════════════════════════════

def _make_engine(name):
    """Create engine with NO calibration (purely unsupervised)."""
    return ENGINE_CLS[name](calibrate=None)


def score_conformal(engine_name, X_ref, X_test):
    """Mode A: Conformal split — fit on ref, score test.

    Engine never sees crisis labels. Threshold comes from
    conformal p-values (ref calibration set).
    """
    eng = _make_engine(engine_name)
    eng.fit_reference(X_ref, y_ref=None, cal_frac=0.2)
    scores = eng.score_conformal(X_test)
    pvalues = eng.predict_pvalue(X_test)
    return scores, pvalues


def score_frozen_threshold(engine_name, X_ref, X_all, n_ref):
    """Mode B: Score everything, freeze threshold from ref period.

    Engine fitted on X_ref (pre-crisis) with y=None.
    Then scores ALL data using _score_new().
    Threshold = P75/P90/P95 of ref-period scores only.

    Also extracts per-component scores (BSDT, MFLS, Morse, Betti, UDL)
    from the engine's internal FusedSystemScorer.
    """
    eng = _make_engine(engine_name)
    # Fit on reference data only — no labels
    eng.fit_score(X_ref, y=None)
    # Score all data through fitted model
    scores_all = eng._score_new(X_all)
    # Threshold from reference period scores only
    ref_scores = scores_all[:n_ref]
    thresholds = {
        'P75': float(np.percentile(ref_scores, 75)),
        'P90': float(np.percentile(ref_scores, 90)),
        'P95': float(np.percentile(ref_scores, 95)),
    }

    # ── Extract per-component scores from the fitted engine ──
    components = {}
    fused = getattr(eng, 'fused_scorer', None)
    if fused is not None:
        # Need to score X_all in the engine's normalised space
        if eng.scaler_ is not None:
            X_scaled = eng.scaler_.transform(X_all)
        else:
            X_scaled = np.asarray(X_all, dtype=np.float64)

        try:
            if fused.bsdt is not None and getattr(fused.bsdt, '_fitted', False):
                components['BSDT'] = fused.bsdt.score(X_scaled)
                components['E_BS'] = fused.bsdt.energy(X_scaled)
                components['MFLS'] = fused.bsdt.mfls(X_scaled)
        except Exception:
            pass
        try:
            if fused.morse is not None:
                components['Morse'] = fused.morse.score(X_scaled)
        except Exception:
            pass
        try:
            if fused.betti is not None:
                components['Betti'] = fused.betti.score(X_scaled)
        except Exception:
            pass
        try:
            if fused.udl is not None and getattr(fused.udl, '_fitted', False):
                components['UDL'] = fused.udl.score(X_scaled)
        except Exception:
            pass

    return scores_all, thresholds, components


def score_expanding_window(engine_name, X_all, n_ref, step=1):
    """Mode C: Expanding window — at each step t, use only [0..t].

    For each time step t >= n_ref:
      1. Take X[0:t+1]
      2. Fit engine on this window (y=None)
      3. Record score for time t
    Reference period (0..n_ref-1) scored from initial fit.
    """
    n = len(X_all)
    scores = np.full(n, np.nan)

    # Phase 1: Fit on reference, score reference
    eng = _make_engine(engine_name)
    eng.fit_score(X_all[:n_ref], y=None)
    scores[:n_ref] = eng._score_new(X_all[:n_ref])

    # Phase 2: Expanding window
    for t in range(n_ref, n, step):
        t_end = min(t + step, n)
        X_up_to_t = X_all[:t_end]
        eng_t = _make_engine(engine_name)
        eng_t.fit_score(X_up_to_t, y=None)
        # Only take the new scores (last t_end - t points)
        new_scores = eng_t._score_new(X_all[t:t_end])
        scores[t:t_end] = new_scores

    # Threshold from reference period only
    ref_scores = scores[:n_ref]
    thresholds = {
        'P75': float(np.nanpercentile(ref_scores, 75)),
        'P90': float(np.nanpercentile(ref_scores, 90)),
        'P95': float(np.nanpercentile(ref_scores, 95)),
    }
    return scores, thresholds


# ═══════════════════════════════════════════════════════════════════
#  METRIC HELPERS — thresholds are FROZEN from pre-crisis period
# ═══════════════════════════════════════════════════════════════════

def metrics_at_threshold(y_true, scores, threshold):
    """Compute metrics at a single FROZEN threshold."""
    pred = (scores >= threshold).astype(int)
    tp = int(((y_true == 1) & (pred == 1)).sum())
    fp = int(((y_true == 0) & (pred == 1)).sum())
    fn = int(((y_true == 1) & (pred == 0)).sum())
    tn = int(((y_true == 0) & (pred == 0)).sum())
    prec = tp / (tp + fp) if (tp + fp) else 0
    rec  = tp / (tp + fn) if (tp + fn) else 0
    f1   = 2 * prec * rec / (prec + rec) if (prec + rec) else 0
    far  = fp / (fp + tn) if (fp + tn) else 0
    return dict(prec=prec, rec=rec, f1=f1, far=far, tp=tp, fp=fp, fn=fn, tn=tn)


def lead_time_causal(scores, onset_idx, threshold):
    """Lead-time: how many periods before onset is threshold exceeded."""
    above = np.where(scores[:onset_idx] >= threshold)[0]
    if len(above) == 0:
        return None
    return int(onset_idx - above[0])


def false_alarms_in_window(scores, event_start, event_end, threshold, window):
    """Count false alarm episodes in normal period before event."""
    t0 = max(0, event_start - window)
    normal_segment = scores[t0:event_start]
    if len(normal_segment) == 0:
        return 0
    alarms = (normal_segment >= threshold).astype(int)
    # Count episodes (transitions from 0 to 1)
    episodes = 0
    in_alarm = False
    for a in alarms:
        if a == 1 and not in_alarm:
            episodes += 1
            in_alarm = True
        elif a == 0:
            in_alarm = False
    return episodes


# ═══════════════════════════════════════════════════════════════════
#  DATA LOADERS — same as existing scripts
# ═══════════════════════════════════════════════════════════════════

def _load_bank():
    if not os.path.exists(GSIB_NPZ):
        return None
    X_panel = np.load(GSIB_NPZ)["X"]
    with open(GSIB_META) as f:
        meta = json.load(f)
    N_meta = len(meta); X_panel = X_panel[:, :N_meta, :]
    ref_end      = qidx(2007, 1)   # 2005-Q1 through 2006-Q4
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
    onset = crisis_start - pred_start
    return dict(X_ref=X_ref, X_all=X_pred, y=y,
                event_onsets={'GFC_crisis': onset}, unit="quarters",
                n_ref=len(X_ref), normal_window=4)


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

    # ── COLLAPSE-ONLY: keep only supply-side grid failures ──
    # COVID_Collapse is a demand anomaly, SummerPeak2019 is seasonal.
    # Only WinterStormUri and WinterStormElliott are actual grid collapses.
    COLLAPSE_EVENTS = {"WinterStormUri", "WinterStormElliott"}
    collapse_ev_onsets = {k: v for k, v in ev_onsets.items() if k in COLLAPSE_EVENTS}

    # Rebuild y: 1 only for collapse events, 0 for everything else
    y_collapse = np.zeros(N, dtype=int)
    for ev in COLLAPSE_EVENTS:
        y_collapse[lab == ev] = 1

    ref_mask = (dates >= "2019-04-01") & (dates < "2019-07-01")
    X_ref = X_daily[ref_mask]
    n_ref = int(ref_mask.sum())

    # Find index of first ref day in full series
    ref_start_idx = int(np.where(ref_mask)[0][0])

    event_indices = {}
    for ev in collapse_ev_onsets:
        onset_str = collapse_ev_onsets[ev][:10]
        oi = np.where(dates >= onset_str)[0]
        if len(oi):
            event_indices[ev] = int(oi[0])

    return dict(X_ref=X_ref, X_all=X_daily, y=y_collapse,
                event_onsets=event_indices, unit="days",
                n_ref=n_ref, ref_start=ref_start_idx,
                dates=dates, lab=lab, normal_window=30)


def _load_terra():
    ust  = interpolate(UST_PRICE)
    luna = interpolate(LUNA_PRICE)
    X    = build_terra_features(ust, luna)
    T    = len(X)
    y    = np.array([1 if t >= 24 else 0 for t in range(T)])
    event_onsets = {
        'LFG_withdraw': 22, 'first_attack': 24,
        'death_spiral': 48, 'hyperinflation': 96, 'chain_halt': 120,
    }
    return dict(X_ref=X[:22], X_all=X, y=y,
                event_onsets=event_onsets, unit="hours",
                n_ref=22, normal_window=10)


# ═══════════════════════════════════════════════════════════════════
#  PRINTING HELPERS
# ═══════════════════════════════════════════════════════════════════

def _hdr(title, ch='═'):
    print(f"\n{'':2}{ch*W}")
    print(f"  {title}")
    print(f"{'':2}{ch*W}")


def _table_row(cells, widths):
    parts = []
    for c, w in zip(cells, widths):
        parts.append(f"{c:>{w}}")
    return "  " + " │ ".join(parts)


# ═══════════════════════════════════════════════════════════════════
#  MAIN: Run Causal Evaluation per Domain
# ═══════════════════════════════════════════════════════════════════

def run_domain(name, data, mode='frozen'):
    """
    Run causal evaluation for one domain.

    mode='frozen'   → Mode B (frozen threshold from ref period)
    mode='conformal'→ Mode A (conformal split)
    mode='expanding'→ Mode C (expanding window, SLOW)
    """
    X_ref = data['X_ref']
    X_all = data['X_all']
    y     = data['y']
    n_ref = data['n_ref']
    unit  = data['unit']
    events = data['event_onsets']
    normal_window = data.get('normal_window', 10)

    print(f"\n{'█'*W}")
    print(f"  DOMAIN: {name}  (n_ref={n_ref}, n_total={len(X_all)}, d={X_all.shape[1]}, "
          f"events={len(events)}, mode={mode})")
    print(f"  CAUSAL PROTOCOL: engine never sees y, threshold frozen from pre-crisis ref")
    print(f"{'█'*W}")

    # Build representations on reference data only
    print(f"\n  Building UDL representations on REFERENCE data only (n={n_ref}) …")
    reps = build_reps(X_ref, X_all)
    rep_names = ['Raw'] + [r for r in REP_NAMES_ALL[1:] if r in reps]
    print(f"  Built: {rep_names}")

    # ── Results storage ──
    all_results = {}  # all_results[rep][engine] = {scores, thresholds, ...}

    for rn in rep_names:
        if rn == 'Raw':
            R_ref = X_ref
            R_all = X_all
        else:
            R_ref = reps[rn]['ref']
            R_all = reps[rn]['all']

        D = R_all.shape[1]
        # Ensure n_ref is correct for rep
        rn_nref = len(R_ref)

        all_results[rn] = {}

        for en in ENGINE_NAMES:
            t0 = time.perf_counter()
            try:
                if mode == 'conformal':
                    # Need enough ref for conformal split
                    if rn_nref < 15:
                        print(f"    {en} × {rn}: SKIP (n_ref={rn_nref} too small for conformal)")
                        continue
                    scores_test, pvals = score_conformal(en, R_ref, R_all)
                    # For conformal, threshold = p-value < alpha
                    ref_scores = scores_test[:rn_nref] if rn_nref <= len(scores_test) else scores_test
                    thresholds = {
                        'P75': float(np.percentile(ref_scores, 75)),
                        'P90': float(np.percentile(ref_scores, 90)),
                        'P95': float(np.percentile(ref_scores, 95)),
                    }
                    scores = scores_test
                    components = {}

                elif mode == 'expanding':
                    step = max(1, len(R_all) // 50)  # ~50 re-fits max
                    scores, thresholds = score_expanding_window(en, R_all, rn_nref, step=step)
                    components = {}

                else:  # frozen
                    scores, thresholds, components = score_frozen_threshold(en, R_ref, R_all, rn_nref)

                elapsed = (time.perf_counter() - t0) * 1000

                # AUC (valid regardless — it's threshold-free)
                valid = np.isfinite(scores)
                auc = auc_manual(y[valid], scores[valid]) if valid.sum() > 10 else 0.5

                all_results[rn][en] = dict(
                    scores=scores, thresholds=thresholds,
                    auc=auc, time_ms=elapsed,
                    components=components,
                )
                print(f"    {en:22s} × {rn:16s}  AUC={auc:.4f}  [{elapsed:.0f}ms]")

            except Exception as ex:
                elapsed = (time.perf_counter() - t0) * 1000
                print(f"    {en:22s} × {rn:16s}  FAILED: {ex}  [{elapsed:.0f}ms]")

    # ═══════════════════════════════════════════════════════════
    #  TABLE 1 — CAUSAL ACCURACY (frozen threshold)
    # ═══════════════════════════════════════════════════════════
    for th_name in ['P75', 'P90', 'P95']:
        _hdr(f"TABLE — CAUSAL ACCURACY @ {th_name} threshold  [{name}]")
        print(f"  Threshold frozen from PRE-CRISIS reference period ({th_name} of ref scores)")
        print()

        for en in ENGINE_NAMES:
            print(f"  {en}:")
            hdr = f"  {'Rep':20s} │ {'AUC':>7s} │ {'θ_ref':>9s} │ {'Prec':>6s} │ "
            hdr += f"{'Rec':>6s} │ {'F1':>7s} │ {'FAR':>6s}"
            print(hdr)
            print(f"  {'─'*78}")

            for rn in rep_names:
                if rn not in all_results or en not in all_results[rn]:
                    continue
                r = all_results[rn][en]
                th = r['thresholds'][th_name]
                valid = np.isfinite(r['scores'])
                m = metrics_at_threshold(y[valid], r['scores'][valid], th)
                print(f"  {rn:20s} │ {r['auc']:7.3f} │ {th:9.3f} │ "
                      f"{m['prec']:6.3f} │ {m['rec']:6.3f} │ {m['f1']:7.3f} │ {m['far']:6.3f}")
            print()

    # ═══════════════════════════════════════════════════════════
    #  TABLE 2 — CAUSAL LEAD-TIME (frozen threshold)
    # ═══════════════════════════════════════════════════════════
    for th_name in ['P75', 'P90', 'P95']:
        _hdr(f"TABLE — CAUSAL LEAD-TIME @ {th_name}  [{name}]  (unit: {unit})")
        print(f"  Lead = periods score ≥ threshold BEFORE event onset")
        print(f"  Threshold frozen from pre-crisis reference only")
        print()

        for ev_name, onset in sorted(events.items(), key=lambda x: x[1]):
            for en in ENGINE_NAMES:
                print(f"  ┌─ Event: {ev_name}  (onset {onset})  — {en}")
                hdr_line = f"  │ {'Representation':20s} │ {'Lead':>8s} │ {'FA_eps':>6s}"
                print(hdr_line)
                print(f"  │ {'─'*45}")

                for rn in rep_names:
                    if rn not in all_results or en not in all_results[rn]:
                        continue
                    r = all_results[rn][en]
                    th = r['thresholds'][th_name]
                    lt = lead_time_causal(r['scores'], onset, th)
                    fa = false_alarms_in_window(r['scores'], onset - normal_window,
                                                onset, th, normal_window)
                    lt_str = f"{lt:>5d} {unit[0]}" if lt is not None else "   —  "
                    print(f"  │ {rn:20s} │ {lt_str:>8s} │ {fa:>6d}")

                print(f"  └{'─'*48}")
            print()

    # ═══════════════════════════════════════════════════════════
    #  TABLE 3 — FALSE ALARM RATE (causal)
    # ═══════════════════════════════════════════════════════════
    _hdr(f"TABLE — FALSE ALARM RATE (causal)  [{name}]")
    print(f"  FAR = fraction of normal periods above frozen threshold")
    print()

    for en in ENGINE_NAMES:
        print(f"  {en}:")
        hdr = f"  {'Rep':20s} │ {'FAR@P75':>8s} │ {'FAR@P90':>8s} │ {'FAR@P95':>8s}"
        print(hdr)
        print(f"  {'─'*60}")

        for rn in rep_names:
            if rn not in all_results or en not in all_results[rn]:
                continue
            r = all_results[rn][en]
            parts = []
            for th_name in ['P75', 'P90', 'P95']:
                th = r['thresholds'][th_name]
                normal_scores = r['scores'][y == 0]
                valid_normal = normal_scores[np.isfinite(normal_scores)]
                far = float((valid_normal >= th).sum()) / max(len(valid_normal), 1)
                parts.append(f"{far*100:7.1f}%")
            print(f"  {rn:20s} │ {parts[0]:>8s} │ {parts[1]:>8s} │ {parts[2]:>8s}")
        print()

    # ═══════════════════════════════════════════════════════════
    #  TABLE 4 — BEST ENGINE RANKING (causal AUC)
    # ═══════════════════════════════════════════════════════════
    _hdr(f"TABLE — AUC RANKING (causal, threshold-free)  [{name}]")
    print(f"  AUC is valid regardless of threshold — measures separability")
    print()

    hdr_parts = [f"{'Engine':20s}"]
    for rn in rep_names:
        hdr_parts.append(f"{rn:>14s}")
    hdr_parts.extend([f"{'Mean':>7s}", f"{'Best Rep':16s}"])
    print("  " + " │ ".join(hdr_parts))
    print(f"  {'─'*130}")

    for en in ENGINE_NAMES:
        parts = [f"{en:20s}"]
        aucs = []
        best_auc, best_rep = 0, ""
        for rn in rep_names:
            if rn in all_results and en in all_results[rn]:
                a = all_results[rn][en]['auc']
                parts.append(f"{a:14.4f}")
                aucs.append(a)
                if a > best_auc:
                    best_auc = a
                    best_rep = rn
            else:
                parts.append(f"{'—':>14s}")
        mean_auc = np.mean(aucs) if aucs else 0
        parts.extend([f"{mean_auc:7.4f}", f"{best_rep:16s}"])
        print("  " + " │ ".join(parts))
    print()

    # ═══════════════════════════════════════════════════════════
    #  TABLE 5 — COMPONENT BREAKDOWN (BSDT, MFLS, Morse, Betti, UDL)
    # ═══════════════════════════════════════════════════════════
    if mode == 'frozen':
        _hdr(f"TABLE — ENGINE COMPONENT BREAKDOWN  [{name}]")
        print(f"  Per-component AUC from the engine's internal FusedSystemScorer")
        print(f"  All components fitted on pre-crisis ref only (causal)")
        print()

        COMP_NAMES = ['BSDT', 'E_BS', 'MFLS', 'Morse', 'Betti', 'UDL']

        for en in ENGINE_NAMES:
            print(f"  {en}:")
            hdr = f"  {'Rep':20s} │ {'Fused':>7s}"
            for cn in COMP_NAMES:
                hdr += f" │ {cn:>7s}"
            print(hdr)
            print(f"  {'─'*90}")

            for rn in rep_names:
                if rn not in all_results or en not in all_results[rn]:
                    continue
                r = all_results[rn][en]
                comps = r.get('components', {})
                parts = [f"{rn:20s}", f"{r['auc']:7.3f}"]
                for cn in COMP_NAMES:
                    if cn in comps:
                        ca = auc_manual(y, comps[cn])
                        parts.append(f"{ca:7.3f}")
                    else:
                        parts.append(f"{'—':>7s}")
                print("  " + " │ ".join(parts))
            print()

        # ── Per-event lead-time from each component (P90 threshold) ──
        _hdr(f"TABLE — COMPONENT DETECTION LEAD-TIME @ P90  [{name}]  ({unit})")
        print(f"  First period each component score ≥ its own P90(ref) BEFORE event onset")
        print()

        for ev_name, onset in sorted(events.items(), key=lambda x: x[1]):
            print(f"  ┌─ Event: {ev_name}  (onset {onset})")
            hdr = f"  │ {'Engine':20s} {'Rep':16s} │ {'Fused':>7s}"
            for cn in COMP_NAMES:
                hdr += f" │ {cn:>7s}"
            print(hdr)
            print(f"  │ {'─'*100}")

            for en in ENGINE_NAMES:
                # Use best rep for this engine
                best_rn, best_auc = None, -1
                for rn in rep_names:
                    if rn in all_results and en in all_results[rn]:
                        if all_results[rn][en]['auc'] > best_auc:
                            best_auc = all_results[rn][en]['auc']
                            best_rn = rn
                if best_rn is None:
                    continue
                r = all_results[best_rn][en]
                comps = r.get('components', {})

                # Fused lead-time
                th_fused = r['thresholds']['P90']
                lt_fused = lead_time_causal(r['scores'], onset, th_fused)
                lt_str = f"{lt_fused:>5d} {unit[0]}" if lt_fused else "   —  "

                parts = [f"{en:20s} {best_rn:16s}", f"{lt_str:>7s}"]
                for cn in COMP_NAMES:
                    if cn in comps:
                        cs = comps[cn]
                        ref_cs = cs[:n_ref]
                        th_c = float(np.percentile(ref_cs, 90))
                        lt_c = lead_time_causal(cs, onset, th_c)
                        lt_c_str = f"{lt_c:>5d} {unit[0]}" if lt_c else "   —  "
                        parts.append(f"{lt_c_str:>7s}")
                    else:
                        parts.append(f"{'—':>7s}")
                print("  │ " + " │ ".join(parts))

            print(f"  └{'─'*108}")
        print()

    return all_results


# ═══════════════════════════════════════════════════════════════════
#  CROSS-DOMAIN SUMMARY
# ═══════════════════════════════════════════════════════════════════

def cross_domain_summary(domain_results):
    print(f"\n{'█'*W}")
    print(f"  CROSS-DOMAIN SUMMARY — Causal Physics Engines (SIAM Protocol)")
    print(f"{'█'*W}")

    # A. Best per domain
    _hdr("A. Best Physics Engine per Domain (causal AUC)")
    print(f"  {'Domain':12s} │ {'Rep':16s} │ {'Engine':20s} │ {'AUC':>7s} │ "
          f"{'Prec@P90':>8s} │ {'Rec@P90':>7s} │ {'F1@P90':>7s} │ {'FAR@P90':>7s}")
    print(f"  {'─'*100}")

    for dname, dres in domain_results.items():
        best_auc = 0
        best_combo = None
        for rn, eng_dict in dres['results'].items():
            for en, r in eng_dict.items():
                if r['auc'] > best_auc:
                    best_auc = r['auc']
                    best_combo = (rn, en, r)
        if best_combo:
            rn, en, r = best_combo
            th = r['thresholds']['P90']
            m = metrics_at_threshold(dres['y'], r['scores'], th)
            print(f"  {dname:12s} │ {rn:16s} │ {en:20s} │ {best_auc:7.3f} │ "
                  f"{m['prec']:8.3f} │ {m['rec']:7.3f} │ {m['f1']:7.3f} │ {m['far']:7.3f}")

    # B. Cross-domain mean AUC per engine
    _hdr("B. Cross-Domain Mean AUC per Engine (causal)")
    domain_names = list(domain_results.keys())
    hdr = f"  {'Engine':20s}"
    for dn in domain_names:
        hdr += f" │ {dn:>10s}"
    hdr += f" │ {'Overall':>9s}"
    print(hdr)
    print(f"  {'─'*80}")

    for en in ENGINE_NAMES:
        parts = [f"{en:20s}"]
        all_aucs = []
        for dn in domain_names:
            dr = domain_results[dn]['results']
            eng_aucs = []
            for rn in dr:
                if en in dr[rn]:
                    eng_aucs.append(dr[rn][en]['auc'])
            mean_a = np.mean(eng_aucs) if eng_aucs else 0
            parts.append(f"{mean_a:10.4f}")
            all_aucs.extend(eng_aucs)
        overall = np.mean(all_aucs) if all_aucs else 0
        parts.append(f"{overall:9.4f}")
        print("  " + " │ ".join(parts))

    # C. Comparison: leaky vs causal
    _hdr("C. Protocol Comparison Note")
    print("  Previous (leaky) results used:")
    print("    - fit_score(X, y) with crisis labels → engine knows which points are anomalies")
    print("    - F1-optimal threshold swept over FULL y → hindsight oracle")
    print("    - calibrate='combined' with isotonic regression on (scores, y)")
    print()
    print("  This causal evaluation uses:")
    print("    - fit_score(X_ref, y=None) on pre-crisis data only")
    print("    - Threshold frozen: P75/P90/P95 of reference-period scores")
    print("    - No crisis labels ever seen by any component")
    print("    - AUC is threshold-free (valid in both protocols)")
    print()


# ═══════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    t_global = time.perf_counter()
    mode = 'frozen'  # Default: frozen threshold (fast, principled)

    if len(sys.argv) > 1:
        mode = sys.argv[1]

    print("=" * W)
    print(f"  CAUSAL PHYSICS ENGINE EVALUATION — SIAM PAPER PROTOCOL")
    print(f"  Mode: {mode}")
    print(f"  Engine y= NONE | Threshold frozen from pre-crisis ref | No future leakage")
    print("=" * W)

    domain_results = {}

    # ── Banking ──
    print("\n  Loading Banking (G-SIB GFC) …")
    bank = _load_bank()
    if bank:
        res = run_domain("Banking (GFC)", bank, mode=mode)
        domain_results['Banking'] = dict(results=res, y=bank['y'])
    else:
        print("  [SKIPPED — data not found]")

    # ── ERCOT ──
    print("\n  Loading ERCOT (Power Grid) …")
    ercot = _load_ercot()
    if ercot:
        res = run_domain("ERCOT (Power Grid)", ercot, mode=mode)
        domain_results['ERCOT'] = dict(results=res, y=ercot['y'])
    else:
        print("  [SKIPPED — data not found]")

    # ── Terra/Luna ──
    print("\n  Loading Terra/Luna (Crypto) …")
    terra = _load_terra()
    if terra:
        res = run_domain("Terra/Luna", terra, mode=mode)
        domain_results['Terra'] = dict(results=res, y=terra['y'])
    else:
        print("  [SKIPPED — data not found]")

    # Cross-domain summary
    if domain_results:
        cross_domain_summary(domain_results)

    elapsed = time.perf_counter() - t_global
    print(f"\n{'='*W}")
    print(f"  COMPLETED in {elapsed:.1f}s")
    print(f"{'='*W}")
