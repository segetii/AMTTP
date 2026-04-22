#!/usr/bin/env python3
"""
Full Engine Early Warning Results
===================================
Runs the COMPLETE CollapseGeometry + Adaptive Geometry pipeline —  
exactly the same full_geometry_analysis() engine from
test_full_collapse_x_domains.py — and then adds focused summary tables:

  TABLE 1  Lead-time detection before collapse  
  TABLE 2  Early warning accuracy (Prec / Recall / F1)  
  TABLE 3  False alarm rate at operational thresholds  
  TABLE 4  BSDT channel decomposition (δ_C / δ_G / δ_A / δ_T / E_BS)  
  TABLE 5  Adaptive friction & dissipation (σ, γ*, E/σ, %fail)  
  TABLE 6  Full scorer AUC ranking  (CG + FWS + all 7 adaptive families)

FrozenWindowScorer ≡ Algorithm 2 from the SIAM paper:
  – Frozen reference calibration (zero lookahead bias)
  – 5-feature (Q, θ, AM, Q×θ, K×θ) geometric-trigonometric scoring
  – Fisher VR optimal weights on frozen window
  – score_with_friction → adaptive friction γ*(x) = α/(λ_max + ε)
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

# ── Import the FULL engine and helpers from the existing test ──
from test_full_collapse_x_domains import (
    build_reps, full_geometry_analysis, auc_manual, clean_array,
    GSIB_NPZ, GSIB_META, qidx,
    load_ercot, daily_aggregate, ERCOT_DIR,
    interpolate, build_terra_features, UST_PRICE, LUNA_PRICE,
)

W = 110


# ═══════════════════════════════════════════════════════════════════
# EARLY-WARNING METRIC HELPERS  (post-process full engine output)
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


def _mask(T, ev_info):
    """Convert event info to boolean mask (same helper as original test)."""
    if isinstance(ev_info, np.ndarray) and ev_info.dtype == bool:
        return ev_info
    if isinstance(ev_info, tuple) and len(ev_info) == 2:
        m = np.zeros(T, dtype=bool)
        m[ev_info[0]:ev_info[1]] = True
        return m
    return np.zeros(T, dtype=bool)


# ═══════════════════════════════════════════════════════════════════
# DATA LOADERS  (same logic as the domain runners in the original test)
# ═══════════════════════════════════════════════════════════════════

def _load_bank():
    if not os.path.exists(GSIB_NPZ):
        return None
    X_panel = np.load(GSIB_NPZ)["X"]
    with open(GSIB_META) as f:
        meta = json.load(f)
    N_meta = len(meta); X_panel = X_panel[:, :N_meta, :]
    ref_end     = qidx(2007, 1)
    pred_start  = qidx(2006, 1)
    pred_end    = qidx(2010, 1)
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

    X_ref = np.vstack(ref_c)
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
# RUN FULL ENGINE  (CG + all 7 adaptive families × every representation)
# ═══════════════════════════════════════════════════════════════════

def _run_engine(X_ref, X_all, y, events, domain):
    """Build 5 UDL reps, run full_geometry_analysis on each."""
    print(f"\n  Building 5 UDL representations …")
    reps = build_reps(X_ref, X_all)
    print(f"  Built: {list(reps.keys())}")

    results = {}
    for rn in ['Raw'] + list(reps.keys()):
        Rr = X_ref  if rn == 'Raw' else reps[rn]['ref']
        Ra = X_all  if rn == 'Raw' else reps[rn]['all']
        D  = Ra.shape[1]

        print(f"\n  {'═' * (W-2)}")
        print(f"  {rn} ({D}D) — FULL GEOMETRY")
        print(f"  {'═' * (W-2)}")

        try:
            res = full_geometry_analysis(rn, Rr, Ra, y, events,
                                          domain_name=domain)
            # Compute AUC for every adaptive scorer
            sa = {}
            for sn, arr in res.get('scorer_results', {}).items():
                sa[sn] = auc_manual(y, arr)
            res['scorer_aucs'] = sa
            results[rn] = res
        except Exception as e:
            print(f"    ERROR on {rn}: {e}")
            import traceback; traceback.print_exc()

    return results


# ═══════════════════════════════════════════════════════════════════
# FOCUSED SUMMARY TABLES  (printed AFTER full engine output)
# ═══════════════════════════════════════════════════════════════════

def _summary_tables(domain, results, y, events, event_onsets, unit):
    T = len(y)

    print(f"\n{'█' * W}")
    print(f"  {domain} — EARLY-WARNING SUMMARY TABLES  (Full Engine)")
    print(f"{'█' * W}")

    # ────── TABLE 1: LEAD-TIME DETECTION ──────
    if event_onsets:
        print(f"\n{'═' * W}")
        print(f"  TABLE 1 — LEAD-TIME DETECTION BEFORE COLLAPSE  [{domain}]")
        print(f"{'═' * W}")
        print(f"  Lead = periods score > threshold BEFORE event onset  (unit: {unit})")

        for ev, oi in event_onsets.items():
            print(f"\n  ┌─ Event: {ev}  (onset index {oi})")
            print(f"  │ {'Representation':<20s} │ {'S>0.3':>8s} │ {'S>0.5':>8s} │ {'S>0.7':>8s} │ {'Best':>6s}")
            print(f"  │ {'─' * 65}")
            for rn, res in results.items():
                lt = _lead_time(res['scores'], oi)
                best = max((v for v in lt.values() if v is not None), default=None)
                row = f"  │ {rn:<20s} │"
                for th in (0.3, 0.5, 0.7):
                    v = lt[th]
                    row += f" {v:>5d} {unit[0]:s}  │" if v is not None else f"    —    │"
                row += f" {best:>4d} {unit[0]:s}" if best is not None else f"   —"
                print(row)
            print(f"  └{'─' * 70}")

    # ────── TABLE 2: ACCURACY ──────
    print(f"\n{'═' * W}")
    print(f"  TABLE 2 — EARLY WARNING SIGNAL ACCURACY  [{domain}]")
    print(f"{'═' * W}")

    # -- CG score
    print(f"\n  A. CollapseGeometry S(x) (F1-optimal threshold):")
    print(f"  {'Rep':<20s} │ {'AUC':>6s} │ {'θ*':>6s} │ {'Prec':>6s} │ {'Rec':>6s} │ {'F1':>6s} │ {'FAR':>6s}")
    print(f"  {'─' * 72}")
    for rn, res in results.items():
        m = _f1_metrics(y, res['scores'])
        print(f"  {rn:<20s} │ {m['auc']:6.3f} │ {m['thresh']:6.3f} │ "
              f"{m['prec']:6.3f} │ {m['rec']:6.3f} │ {m['f1']:6.3f} │ {m['far']:6.3f}")

    # -- FrozenWindow (Algorithm 2)
    print(f"\n  B. FrozenWindowScorer — SIAM Algorithm 2 (F1-optimal):")
    print(f"  {'Rep':<20s} │ {'AUC':>6s} │ {'θ*':>6s} │ {'Prec':>6s} │ {'Rec':>6s} │ {'F1':>6s} │ {'FAR':>6s}")
    print(f"  {'─' * 72}")
    for rn, res in results.items():
        sr = res.get('scorer_results', {})
        if 'FWS' in sr:
            m = _f1_metrics(y, sr['FWS'])
            print(f"  {rn:<20s} │ {m['auc']:6.3f} │ {m['thresh']:6.3f} │ "
                  f"{m['prec']:6.3f} │ {m['rec']:6.3f} │ {m['f1']:6.3f} │ {m['far']:6.3f}")

    # -- FrozenWindow + Friction
    print(f"\n  C. FrozenWindow + Adaptive Friction (score_with_friction):")
    print(f"  {'Rep':<20s} │ {'AUC':>6s} │ {'θ*':>6s} │ {'Prec':>6s} │ {'Rec':>6s} │ {'F1':>6s} │ {'FAR':>6s}")
    print(f"  {'─' * 72}")
    for rn, res in results.items():
        sr = res.get('scorer_results', {})
        if 'FWS_fric' in sr:
            m = _f1_metrics(y, sr['FWS_fric'])
            print(f"  {rn:<20s} │ {m['auc']:6.3f} │ {m['thresh']:6.3f} │ "
                  f"{m['prec']:6.3f} │ {m['rec']:6.3f} │ {m['f1']:6.3f} │ {m['far']:6.3f}")

    # -- Best adaptive overall
    print(f"\n  D. Best Adaptive Scorer per Representation:")
    print(f"  {'Rep':<20s} │ {'Scorer':<14s} │ {'AUC':>6s} │ {'Prec':>6s} │ {'Rec':>6s} │ {'F1':>6s} │ {'FAR':>6s}")
    print(f"  {'─' * 80}")
    for rn, res in results.items():
        sa = res.get('scorer_aucs', {})
        if not sa:
            continue
        bsn = max(sa, key=sa.get)
        m = _f1_metrics(y, res['scorer_results'][bsn])
        print(f"  {rn:<20s} │ {bsn:<14s} │ {m['auc']:6.3f} │ "
              f"{m['prec']:6.3f} │ {m['rec']:6.3f} │ {m['f1']:6.3f} │ {m['far']:6.3f}")

    # ────── TABLE 3: FALSE ALARM RATE ──────
    print(f"\n{'═' * W}")
    print(f"  TABLE 3 — FALSE ALARM RATE  [{domain}]")
    print(f"{'═' * W}")
    n_norm = int((y == 0).sum())
    print(f"  FAR = false alarms / {n_norm} normal periods")

    print(f"\n  CG S(x):")
    print(f"  {'Rep':<20s} │ {'FAR@0.3':>8s} │ {'FAR@0.5':>8s} │ {'FAR@0.7':>8s}")
    print(f"  {'─' * 50}")
    for rn, res in results.items():
        f = _far_at(res['scores'], y)
        print(f"  {rn:<20s} │ {f[0.3]:7.1%} │ {f[0.5]:7.1%} │ {f[0.7]:7.1%}")

    print(f"\n  FrozenWindow (Alg 2):")
    print(f"  {'Rep':<20s} │ {'FAR@0.3':>8s} │ {'FAR@0.5':>8s} │ {'FAR@0.7':>8s}")
    print(f"  {'─' * 50}")
    for rn, res in results.items():
        sr = res.get('scorer_results', {})
        if 'FWS' not in sr:
            continue
        f = _far_at(sr['FWS'], y)
        print(f"  {rn:<20s} │ {f[0.3]:7.1%} │ {f[0.5]:7.1%} │ {f[0.7]:7.1%}")

    print(f"\n  FrozenWindow + Friction:")
    print(f"  {'Rep':<20s} │ {'FAR@0.3':>8s} │ {'FAR@0.5':>8s} │ {'FAR@0.7':>8s}")
    print(f"  {'─' * 50}")
    for rn, res in results.items():
        sr = res.get('scorer_results', {})
        if 'FWS_fric' not in sr:
            continue
        f = _far_at(sr['FWS_fric'], y)
        print(f"  {rn:<20s} │ {f[0.3]:7.1%} │ {f[0.5]:7.1%} │ {f[0.7]:7.1%}")

    # ────── TABLE 4: BSDT CHANNEL DECOMPOSITION ──────
    print(f"\n{'═' * W}")
    print(f"  TABLE 4 — BSDT CHANNEL DECOMPOSITION  [{domain}]")
    print(f"{'═' * W}")
    print(f"  δ_C=camouflage  δ_G=gap  δ_A=activity  δ_T=temporal  E_BS=energy")
    print(f"  Shown for best representation (highest CG AUC)")

    best_rn = max(results, key=lambda r: results[r]['cg_auc'])
    det = results[best_rn]['det']

    norm = _mask(T, events.get('normal', y == 0))
    if isinstance(norm, np.ndarray) and norm.dtype != bool:
        norm = y == 0
    n_ch = {
        'δ_C': det.delta_C[norm].mean(), 'δ_G': det.delta_G[norm].mean(),
        'δ_A': det.delta_A[norm].mean(), 'δ_T': det.delta_T[norm].mean(),
        'E_BS': det.E_BS[norm].mean(),
    }

    print(f"\n  Rep: {best_rn}  (CG AUC={results[best_rn]['cg_auc']:.3f})")
    print(f"  Normal baseline: δ_C={n_ch['δ_C']:.3f}  δ_G={n_ch['δ_G']:.3f}"
          f"  δ_A={n_ch['δ_A']:.3f}  δ_T={n_ch['δ_T']:.3f}  E_BS={n_ch['E_BS']:.1f}")

    print(f"\n  {'Event':<22s} │ {'δ_C':>8s} │ {'δ_G':>8s} │ {'δ_A':>8s} │ "
          f"{'δ_T':>8s} │ {'E_BS':>10s} │ {'Dominant':>9s}")
    print(f"  {'─' * 82}")

    crisis_evs = {k: v for k, v in events.items() if k != 'normal' and k != 'pre_crisis'}
    for ev, info in crisis_evs.items():
        m = _mask(T, info)
        if m.sum() == 0:
            continue
        ec = {
            'δ_C': det.delta_C[m].mean(), 'δ_G': det.delta_G[m].mean(),
            'δ_A': det.delta_A[m].mean(), 'δ_T': det.delta_T[m].mean(),
            'E_BS': det.E_BS[m].mean(),
        }
        # Dominant channel
        ratios = {}
        for c in ['δ_C', 'δ_G', 'δ_A', 'δ_T']:
            nv = n_ch[c]
            ratios[c] = abs(ec[c] / nv) if abs(nv) > 1e-12 else abs(ec[c])
        dominant = max(ratios, key=ratios.get)
        print(f"  {ev:<22s} │ {ec['δ_C']:8.3f} │ {ec['δ_G']:8.3f} │ {ec['δ_A']:8.3f} │ "
              f"{ec['δ_T']:8.3f} │ {ec['E_BS']:10.1f} │ {dominant:>9s}")

    # ────── TABLE 5: ADAPTIVE FRICTION & DISSIPATION ──────
    print(f"\n{'═' * W}")
    print(f"  TABLE 5 — ADAPTIVE FRICTION & DISSIPATION  [{domain}]")
    print(f"{'═' * W}")
    print(f"  σ=dissipation  γ*=friction coeff  E/σ=energy-to-dissipation  %fail=dissipation failure")
    print(f"  Rep: {best_rn}")

    print(f"\n  {'Event':<22s} │ {'σ_diss':>10s} │ {'γ*':>12s} │ "
          f"{'E/σ ratio':>10s} │ {'%fail':>7s} │ {'Φ_eff':>8s} │ {'S_f mean':>8s}")
    print(f"  {'─' * 90}")

    S_f = results[best_rn]['S_f']
    for ev_name in ['normal'] + list(crisis_evs.keys()):
        if ev_name == 'normal':
            m = norm
        else:
            m = _mask(T, events[ev_name])
        if m.sum() == 0:
            continue
        sd  = det.sigma_dissipation[m].mean()
        gs  = det.gamma_star[m].mean()
        ebs = det.E_BS[m].mean()
        es  = ebs / (sd + 1e-12)
        fl  = det.dissipation_failure[m].mean()
        phi = det.phi_eff[m].mean()
        sf  = S_f[m].mean()
        print(f"  {ev_name:<22s} │ {sd:10.4f} │ {gs:12.6f} │ "
              f"{es:10.0f} │ {fl:6.1%} │ {phi:8.4f} │ {sf:8.4f}")

    # ────── TABLE 6: FULL SCORER AUC RANKING ──────
    print(f"\n{'═' * W}")
    print(f"  TABLE 6 — FULL SCORER AUC RANKING  [{domain}]")
    print(f"{'═' * W}")
    print(f"  CG(S) + FWS(Alg2) + FWS+Friction + Morse + Betti + BSDT×3 + UDL + Trig + Fused×2")

    # Collect all scorer names across reps
    all_sn = set()
    for res in results.values():
        all_sn.update(res.get('scorer_aucs', {}).keys())
    scorer_order = ['CG(S)'] + sorted(all_sn)
    reps = list(results.keys())

    hdr = f"  {'Scorer':<14s} │"
    for rn in reps:
        hdr += f" {rn[:12]:>12s} │"
    hdr += f" {'Mean':>6s}"
    print(f"\n{hdr}")
    print(f"  {'─' * (14 + (14 * len(reps)) + 10)}")

    for sn in scorer_order:
        row = f"  {sn:<14s} │"
        vals = []
        for rn, res in results.items():
            if sn == 'CG(S)':
                v = res['cg_auc']
            else:
                v = res.get('scorer_aucs', {}).get(sn, float('nan'))
            if np.isfinite(v):
                row += f" {v:12.3f} │"
                vals.append(v)
            else:
                row += f" {'—':>12s} │"
        m = np.mean(vals) if vals else 0
        row += f" {m:6.3f}"
        print(row)


# ═══════════════════════════════════════════════════════════════════
# DOMAIN RUNNERS
# ═══════════════════════════════════════════════════════════════════

def run_banking():
    print(f"\n{'█' * W}")
    print(f"  DOMAIN 1: WORLD BANKING (GFC) — Full Engine")
    print(f"{'█' * W}")

    data = _load_bank()
    if data is None:
        print("  SKIPPED: GSIB data not found")
        return None, None

    X_ref, X_pred, y = data['X_ref'], data['X_pred'], data['y']
    events, eo, unit = data['events'], data['event_onsets'], data['unit']
    print(f"  Banks: {data['n_banks']}  Pooled ref: {X_ref.shape}  "
          f"pred: {X_pred.shape}  crisis frac: {y.mean():.1%}")

    results = _run_engine(X_ref, X_pred, y, events, "Bank")
    _summary_tables("BANKING (GFC)", results, y, events, eo, unit)
    return results, y


def run_ercot():
    print(f"\n{'█' * W}")
    print(f"  DOMAIN 2: ERCOT POWER GRID (Combined d=10) — Full Engine")
    print(f"{'█' * W}")

    data = _load_ercot()
    if data is None:
        print("  SKIPPED: ERCOT data not found")
        return None, None

    X_ref, X_all, y = data['X_ref'], data['X_all'], data['y']
    events, eo, unit = data['events'], data['event_onsets'], data['unit']
    print(f"  Daily: {X_all.shape}  ref: {X_ref.shape}  crisis frac: {y.mean():.1%}")

    results = _run_engine(X_ref, X_all, y, events, "ERCOT")
    _summary_tables("ERCOT (Power Grid)", results, y, events, eo, unit)
    return results, y


def run_terra():
    print(f"\n{'█' * W}")
    print(f"  DOMAIN 3: TERRA/LUNA — Full Engine")
    print(f"{'█' * W}")

    data = _load_terra()
    X_ref, X_all, y = data['X_ref'], data['X_all'], data['y']
    events, eo, unit = data['events'], data['event_onsets'], data['unit']
    print(f"  Hours: {len(X_all)}  ref: {X_ref.shape}  crisis frac: {y.mean():.1%}")

    results = _run_engine(X_ref, X_all, y, events, "Terra")
    _summary_tables("TERRA/LUNA", results, y, events, eo, unit)
    return results, y


# ═══════════════════════════════════════════════════════════════════
# CROSS-DOMAIN SUMMARY
# ═══════════════════════════════════════════════════════════════════

def cross_domain(bank, ercot, terra):
    print(f"\n{'█' * W}")
    print(f"  CROSS-DOMAIN SUMMARY — Full Engine")
    print(f"{'█' * W}")

    domains = {}
    if bank[0]:
        domains['Banking'] = bank
    if ercot[0]:
        domains['ERCOT'] = ercot
    if terra[0]:
        domains['Terra'] = terra

    # Best CG per domain
    print(f"\n  A. Best CollapseGeometry S(x) per Domain:")
    print(f"  {'Domain':<12s} │ {'Rep':<16s} │ {'AUC':>6s} │ {'Prec':>6s} │ {'Rec':>6s} │ {'F1':>6s} │ {'FAR':>6s}")
    print(f"  {'─' * 75}")
    for dname, (res, y) in domains.items():
        br = max(res, key=lambda r: res[r]['cg_auc'])
        m = _f1_metrics(y, res[br]['scores'])
        print(f"  {dname:<12s} │ {br:<16s} │ {m['auc']:6.3f} │ "
              f"{m['prec']:6.3f} │ {m['rec']:6.3f} │ {m['f1']:6.3f} │ {m['far']:6.3f}")

    # Best FrozenWindow per domain
    print(f"\n  B. Best FrozenWindow (SIAM Alg 2) per Domain:")
    print(f"  {'Domain':<12s} │ {'Rep':<16s} │ {'AUC':>6s} │ {'Prec':>6s} │ {'Rec':>6s} │ {'F1':>6s} │ {'FAR':>6s}")
    print(f"  {'─' * 75}")
    for dname, (res, y) in domains.items():
        best_a, best_rn = 0, "—"
        for rn, r in res.items():
            if 'FWS' in r.get('scorer_results', {}):
                a = auc_manual(y, r['scorer_results']['FWS'])
                if a > best_a:
                    best_a, best_rn = a, rn
        if best_rn != "—":
            m = _f1_metrics(y, res[best_rn]['scorer_results']['FWS'])
            print(f"  {dname:<12s} │ {best_rn:<16s} │ {m['auc']:6.3f} │ "
                  f"{m['prec']:6.3f} │ {m['rec']:6.3f} │ {m['f1']:6.3f} │ {m['far']:6.3f}")

    # Best FWS + Friction per domain
    print(f"\n  C. Best FrozenWindow + Adaptive Friction per Domain:")
    print(f"  {'Domain':<12s} │ {'Rep':<16s} │ {'AUC':>6s} │ {'Prec':>6s} │ {'Rec':>6s} │ {'F1':>6s} │ {'FAR':>6s}")
    print(f"  {'─' * 75}")
    for dname, (res, y) in domains.items():
        best_a, best_rn = 0, "—"
        for rn, r in res.items():
            if 'FWS_fric' in r.get('scorer_results', {}):
                a = auc_manual(y, r['scorer_results']['FWS_fric'])
                if a > best_a:
                    best_a, best_rn = a, rn
        if best_rn != "—":
            m = _f1_metrics(y, res[best_rn]['scorer_results']['FWS_fric'])
            print(f"  {dname:<12s} │ {best_rn:<16s} │ {m['auc']:6.3f} │ "
                  f"{m['prec']:6.3f} │ {m['rec']:6.3f} │ {m['f1']:6.3f} │ {m['far']:6.3f}")

    # Best overall scorer per domain
    print(f"\n  D. Best OVERALL Scorer per Domain (any method, any rep):")
    print(f"  {'Domain':<12s} │ {'Rep':<16s} │ {'Scorer':<14s} │ {'AUC':>6s} │ {'F1':>6s} │ {'FAR':>6s}")
    print(f"  {'─' * 80}")
    for dname, (res, y) in domains.items():
        best_a, best_rn, best_sn = 0, "", ""
        for rn, r in res.items():
            # CG
            a = r['cg_auc']
            if a > best_a:
                best_a, best_rn, best_sn = a, rn, "CG(S)"
            for sn, sarr in r.get('scorer_results', {}).items():
                a = auc_manual(y, sarr)
                if a > best_a:
                    best_a, best_rn, best_sn = a, rn, sn
        m = _f1_metrics(y, (res[best_rn]['scores'] if best_sn == "CG(S)"
                            else res[best_rn]['scorer_results'][best_sn]))
        print(f"  {dname:<12s} │ {best_rn:<16s} │ {best_sn:<14s} │ "
              f"{m['auc']:6.3f} │ {m['f1']:6.3f} │ {m['far']:6.3f}")


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

def main():
    t0 = time.time()
    np.set_printoptions(precision=4, suppress=True, linewidth=120)

    print("=" * W)
    print("  FULL ENGINE EARLY WARNING RESULTS")
    print("  CollapseGeometry + FrozenWindow(SIAM Alg2) + Morse + Betti")
    print("  + BSDT(base/grav/hybrid) + UDL + Trig + Fused")
    print("  ×  5 UDL representations  ×  3 real-world domains")
    print("=" * W)

    bank  = run_banking()
    ercot = run_ercot()
    terra = run_terra()

    cross_domain(bank, ercot, terra)

    elapsed = time.time() - t0
    print(f"\n{'=' * W}")
    print(f"  COMPLETED in {elapsed:.1f}s")
    print(f"{'=' * W}")


if __name__ == "__main__":
    main()
