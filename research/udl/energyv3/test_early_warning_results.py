#!/usr/bin/env python3
"""
Early Warning Detection Results — Proper Presentation
======================================================
Focuses on the metrics that MATTER for collapse detection:

  TABLE 1  Lead-Time  — how many periods before event onset the alarm fires
  TABLE 2  Detection Accuracy — Precision, Recall, F1 at optimal threshold
  TABLE 3  False Alarm Rate — FAR at thresholds 0.3 / 0.5 / 0.7
  TABLE 4  BSDT Channel Decomposition — which energy channel drives each event
  TABLE 5  Adaptive Friction & Dissipation — γ*, Φ potentials, energy balance
  TABLE 6  Best Scorer Ranking — adaptive geometry families head-to-head

Uses the FULL geometry of collapse (CollapseGeometry + all 7 adaptive families).
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
from ellipsoid_geometry import EllipsoidGeometry
from geo_full_pipeline import (
    adaptive_friction,
    GeometricMorse, GeometricBetti, GeometricBSDT,
    GeometricUDL, GeometricTrigScore,
    GeometricFusedScorer, FrozenWindowScorer,
)
from udl.system_mode import ReducedTensorDescriptor, UDLPostSimScorer
from udl.stack import RepresentationStack
from udl.tensor import AnomalyTensor
from udl.coordinates import CoefficientCoordinates
from udl.spectra import (
    StatisticalSpectrum, ChaosSpectrum, SpectralSpectrum,
    ExponentialSpectrum, ReconstructionSpectrum, RankOrderSpectrum,
)

W = 110
IND_NAMES = ['Q_ex', 'θ_ex', '−σ', 'dE', 'Q×θ', 'K×θ', 'AM']

# ═══════════════════════════════════════════════════════════════════
# UTILITIES
# ═══════════════════════════════════════════════════════════════════

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


def build_ellipsoid(R_ref):
    cov = np.cov(R_ref.T)
    eigvals, eigvecs = np.linalg.eigh(cov)
    eigvals = np.maximum(eigvals, 1e-10)
    idx = np.argsort(-eigvals)
    semi_axes = np.sqrt(eigvals[idx])
    rotation = eigvecs[:, idx].T
    centre = R_ref.mean(axis=0)
    return EllipsoidGeometry(semi_axes=semi_axes, centre=centre,
                             rotation=rotation)


def to_body(X, ell):
    return (X - ell.centre) @ ell.rotation.T


# ═══════════════════════════════════════════════════════════════════
# EARLY WARNING METRIC COMPUTATION
# ═══════════════════════════════════════════════════════════════════

def compute_lead_time(scores, event_onset_idx, thresholds=(0.3, 0.5, 0.7)):
    """
    For each threshold, find earliest index where score > threshold
    BEFORE the event onset. Return lead time in periods.
    """
    results = {}
    for thresh in thresholds:
        alarm_indices = np.where(scores[:event_onset_idx] > thresh)[0]
        if len(alarm_indices) > 0:
            first_alarm = int(alarm_indices[0])
            lead = event_onset_idx - first_alarm
            results[thresh] = {'first_alarm': first_alarm, 'lead_time': lead}
        else:
            results[thresh] = {'first_alarm': -1, 'lead_time': 0}
    return results


def compute_detection_metrics(scores, y_true, n_thresholds=200):
    """
    Sweep thresholds, compute Precision, Recall, F1, FAR.
    Return metrics at optimal F1 threshold.
    """
    thresholds = np.linspace(0, scores.max() + 1e-6, n_thresholds)
    best_f1 = -1
    best_metrics = None
    normal_mask = y_true == 0
    event_mask = y_true == 1
    n_normal = normal_mask.sum()
    n_event = event_mask.sum()

    if n_event == 0 or n_normal == 0:
        return {'threshold': 0.5, 'precision': 0, 'recall': 0,
                'f1': 0, 'far': 0, 'tpr': 0, 'fpr': 0}

    for t in thresholds:
        pred = scores > t
        tp = (pred & event_mask).sum()
        fp = (pred & normal_mask).sum()
        fn = (~pred & event_mask).sum()
        tn = (~pred & normal_mask).sum()

        prec = tp / (tp + fp) if (tp + fp) > 0 else 0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0
        far = fp / n_normal
        fpr = fp / (fp + tn) if (fp + tn) > 0 else 0

        if f1 > best_f1:
            best_f1 = f1
            best_metrics = {
                'threshold': float(t),
                'precision': float(prec),
                'recall': float(rec),
                'f1': float(f1),
                'far': float(far),
                'tpr': float(rec),
                'fpr': float(fpr),
            }

    return best_metrics


def compute_far_at_thresholds(scores, y_true, thresholds=(0.3, 0.5, 0.7)):
    """False alarm rate on normal periods at fixed thresholds."""
    normal_scores = scores[y_true == 0]
    if len(normal_scores) == 0:
        return {t: 0 for t in thresholds}
    return {t: float((normal_scores > t).mean()) for t in thresholds}


# ═══════════════════════════════════════════════════════════════════
# REPRESENTATION BUILDER (same as main test)
# ═══════════════════════════════════════════════════════════════════

_rep_objects = {}


def build_reps(X_ref, X_all):
    global _rep_objects
    _rep_objects = {}
    n_ref = len(X_ref)
    reps = {}

    try:
        stack = RepresentationStack(operators=[
            ("stat", StatisticalSpectrum()), ("chaos", ChaosSpectrum()),
            ("freq", SpectralSpectrum()), ("exp", ExponentialSpectrum()),
            ("recon", ReconstructionSpectrum()), ("rank", RankOrderSpectrum()),
        ])
        stack.fit(X_ref)
        _rep_objects['FullTensor'] = stack
        reps['FullTensor'] = {'ref': stack.transform(X_ref),
                              'all': stack.transform(X_all),
                              'D': stack.transform(X_ref).shape[1]}
    except Exception as e:
        print(f"    FullTensor SKIPPED: {e}")

    try:
        k_n = min(15, n_ref - 1)
        if k_n >= 2:
            rtd = ReducedTensorDescriptor(k_neighbors=k_n)
            rtd.fit(X_ref)
            _rep_objects['ReducedTensor'] = rtd
            reps['ReducedTensor'] = {'ref': rtd.transform(X_ref),
                                     'all': rtd.transform(X_all),
                                     'D': rtd.transform(X_ref[:1]).shape[1]}
    except Exception as e:
        print(f"    ReducedTensor SKIPPED: {e}")

    if 'FullTensor' in reps:
        try:
            mdn = AnomalyTensor()
            mdn.fit(reps['FullTensor']['ref'])
            tr_ref = mdn.build(reps['FullTensor']['ref'],
                               _rep_objects['FullTensor'].law_dims_)
            mdn.store_ref_law_stats(tr_ref)
            _rep_objects['MDN'] = mdn
            tr_all = mdn.build(reps['FullTensor']['all'],
                               _rep_objects['FullTensor'].law_dims_)
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

    try:
        coord = CoefficientCoordinates(views=['sorted', 'variance'])
        coord.fit(X_ref)
        _rep_objects['Coordinate'] = coord
        R_c_ref, _ = coord.transform(X_ref)
        R_c_all, _ = coord.transform(X_all)
        reps['Coordinate'] = {'ref': R_c_ref, 'all': R_c_all,
                              'D': R_c_ref.shape[1]}
    except Exception as e:
        print(f"    Coordinate SKIPPED: {e}")

    try:
        k_cov = min(15, n_ref - 1)
        if k_cov >= 2:
            cov = UDLPostSimScorer(k=k_cov, max_dim=min(12, n_ref - 2),
                                    n_components=min(10, n_ref - 2))
            cov.fit(X_ref)
            _rep_objects['CoverageTensor'] = cov
            reps['CoverageTensor'] = {'ref': cov.transform(X_ref),
                                      'all': cov.transform(X_all),
                                      'D': cov.transform(X_ref).shape[1]}
    except Exception as e:
        print(f"    CoverageTensor SKIPPED: {e}")

    return reps


# ═══════════════════════════════════════════════════════════════════
# FULL GEOMETRY PIPELINE (compute everything, store for tables)
# ═══════════════════════════════════════════════════════════════════

def run_full_geometry(rep_name, R_ref, R_all, y_true):
    """Run CollapseGeometry + all adaptive families. Return raw data dict."""
    cg = CollapseGeometry()
    cg.fit(R_ref)
    det = cg.detect(R_all)
    scores = cg.score(R_all)
    S_f = cg.score_with_friction(R_all)
    raw_ind = cg._raw_indicators(R_all)

    ell = build_ellipsoid(R_ref)
    Xb_ref = to_body(R_ref, ell)
    Xb_all = to_body(R_all, ell)

    # Adaptive geometry families
    scorer_results = {}
    scorer_aucs = {}
    bsdt_data = {}

    try:
        fws = FrozenWindowScorer()
        fws.fit(R_ref)
        scorer_results['FrozenWindow'] = fws.score(R_all)
        scorer_results['FWS+Friction'] = fws.score_with_friction(R_all, k_steps=10)
    except Exception:
        pass

    try:
        morse = GeometricMorse()
        morse.fit(Xb_ref, ell)
        scorer_results['Morse'] = morse.score(Xb_all)
    except Exception:
        pass

    try:
        betti = GeometricBetti(n_scales=8)
        betti.fit(Xb_ref, ell)
        scorer_results['Betti'] = betti.score(Xb_all)
    except Exception:
        pass

    try:
        k_bsdt = min(15, len(Xb_ref) - 1)
        gbsdt = GeometricBSDT(k=k_bsdt)
        gbsdt.fit(Xb_ref, ell)
        ch = gbsdt.channels(Xb_all)
        bsdt_data = {
            'channels': ch,
            'phi_gravity': gbsdt.gravity_potential(Xb_all),
            'phi_molecular': gbsdt.molecular_potential(Xb_all),
            'phi_hybrid': gbsdt.hybrid_potential(Xb_all),
            'gamma_star_af': gbsdt.adaptive_friction(Xb_all, alpha=0.3),
        }
        scorer_results['BSDT_base'] = gbsdt.score(Xb_all, potential=None)
        scorer_results['BSDT_gravity'] = gbsdt.score(Xb_all, potential='gravity')
        scorer_results['BSDT_hybrid'] = gbsdt.score(Xb_all, potential='hybrid')
    except Exception:
        pass

    try:
        gudl = GeometricUDL()
        gudl.fit(Xb_ref, ell)
        scorer_results['UDL'] = gudl.score(Xb_all)
    except Exception:
        pass

    try:
        trig = GeometricTrigScore()
        trig.fit(Xb_ref, ell)
        scorer_results['TrigScore'] = trig.score(Xb_all)
    except Exception:
        pass

    try:
        gfs = GeometricFusedScorer(k_af=5, eta_af=0.25)
        gfs.fit(Xb_ref, ell)
        scorer_results['Fused_base'] = gfs.base_score(Xb_all)
        scorer_results['Fused_full'] = gfs.score(Xb_all)
    except Exception:
        pass

    # Compute AUC for each scorer
    for sn, sarr in scorer_results.items():
        scorer_aucs[sn] = auc_manual(y_true, sarr)

    return {
        'cg': cg, 'det': det, 'scores': scores, 'S_f': S_f,
        'raw_ind': raw_ind,
        'scorer_results': scorer_results,
        'scorer_aucs': scorer_aucs,
        'bsdt_data': bsdt_data,
        'ell': ell,
    }


# ═══════════════════════════════════════════════════════════════════
# DATA LOADERS
# ═══════════════════════════════════════════════════════════════════

GSIB_DIR = os.path.normpath(os.path.join(HERE, "..", "..", "..", "research",
            "adaptive-friction", "banklevel_enhanced", "gsib_cache_real"))
GSIB_NPZ = os.path.join(GSIB_DIR, "gsib_real_panel.npz")
GSIB_META = os.path.join(GSIB_DIR, "gsib_real_meta.json")
ERCOT_DIR = os.path.join(ROOT, "data", "ercot")


def qidx(year, qtr):
    return 4 * (year - 2005) + (qtr - 1)


def load_bank():
    X_panel = np.load(GSIB_NPZ)["X"]
    with open(GSIB_META) as f:
        meta = json.load(f)
    N_meta = len(meta)
    X_panel = X_panel[:, :N_meta, :]

    ref_end = qidx(2007, 1)
    pred_start = qidx(2006, 1)
    pred_end = qidx(2010, 1)
    crisis_start = qidx(2007, 3)

    ref_chunks, pred_chunks, y_chunks = [], [], []
    for i in range(N_meta):
        Xb = clean_array(X_panel[:, i, :])
        if Xb.shape[0] < pred_end:
            continue
        X_ref_i = Xb[:ref_end]
        if (X_ref_i == 0).sum() / X_ref_i.size > 0.25:
            continue
        if np.linalg.matrix_rank(X_ref_i - X_ref_i.mean(0), tol=1e-8) < 2:
            continue
        ref_chunks.append(X_ref_i)
        pred_chunks.append(Xb[pred_start:pred_end])
        y_chunks.append(np.array([1 if t >= crisis_start else 0
                                   for t in range(pred_start, pred_end)]))

    X_ref = np.vstack(ref_chunks)
    X_pred = np.vstack(pred_chunks)
    y = np.concatenate(y_chunks)

    # Event structure: quarterly, crisis onset at quarter index
    # crisis_start relative to pred_start
    onset_rel = crisis_start - pred_start  # quarters into prediction window
    events_idx = {'GFC': onset_rel}  # onset index within X_pred (per-bank)

    return X_ref, X_pred, y, events_idx, 'quarters', len(ref_chunks)


def load_ercot(mode="combined"):
    dem = np.load(os.path.join(ERCOT_DIR, "ercot_demand_hourly.npz"), allow_pickle=True)
    sup = np.load(os.path.join(ERCOT_DIR, "ercot_supply_hourly.npz"), allow_pickle=True)
    if mode == "supply":
        X = sup["X"]
        features = list(sup["feature_names"])
    elif mode == "demand":
        X = dem["X"]
        features = list(dem["feature_names"])
    else:
        X = np.column_stack([dem["X"], sup["X"]])
        features = list(dem["feature_names"]) + list(sup["feature_names"])
    dates = np.array(dem["dates"])
    y = dem["y"]
    labels = np.array(dem["labels"])
    event_onsets = json.loads(str(dem["event_onsets"]))

    # Daily aggregate
    day_strs = np.array([d[:10] for d in dates])
    unique_days = np.unique(day_strs)
    N = len(unique_days)
    X_daily = np.empty((N, X.shape[1]))
    y_daily = np.empty(N, dtype=int)
    lab_daily = np.empty(N, dtype=object)
    for i, day in enumerate(unique_days):
        mask = day_strs == day
        X_daily[i] = X[mask].mean(axis=0)
        y_daily[i] = int(y[mask].max())
        nl = labels[mask]
        non_norm = nl[nl != "normal"]
        lab_daily[i] = non_norm[0] if len(non_norm) > 0 else "normal"

    for col in range(X_daily.shape[1]):
        nans = np.isnan(X_daily[:, col])
        if nans.any():
            X_daily[nans, col] = np.nanmean(X_daily[:, col])

    ref_mask = (unique_days >= "2019-04-01") & (unique_days < "2019-07-01")
    X_ref = X_daily[ref_mask]

    # Event onset indices (daily)
    events_idx = {}
    for ev, onset_str in event_onsets.items():
        onset_date = onset_str[:10]
        oi = np.where(unique_days >= onset_date)[0]
        if len(oi) > 0:
            events_idx[ev] = int(oi[0])

    return X_ref, X_daily, y_daily, lab_daily, events_idx, unique_days, features


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


def interpolate(d, n=169):
    h = sorted(d.keys()); v = [d[k] for k in h]
    return np.interp(np.arange(n), h, v)


def load_terra():
    ust = interpolate(UST_PRICE)
    luna = interpolate(LUNA_PRICE)
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
    X = np.column_stack([depeg, luna_log, depeg_rate, luna_rate, vol_6h])

    ref_end = 22
    X_ref = X[:ref_end]
    y_true = np.array([1 if t >= 24 else 0 for t in range(T)])
    events_idx = {
        'LFG_withdraw': 22,
        'first_attack': 24,
        'death_spiral': 48,
        'hyperinflation': 96,
        'chain_halt': 120,
    }
    return X_ref, X, y_true, events_idx


# ═══════════════════════════════════════════════════════════════════
# TABLE RENDERERS
# ═══════════════════════════════════════════════════════════════════

def print_header(title):
    print(f"\n{'═' * W}")
    print(f"  {title}")
    print(f"{'═' * W}")


def table1_lead_time(domain_name, results, events_idx, unit, y_true):
    """TABLE 1: Lead-time detection before collapse."""
    print_header(f"TABLE 1 — LEAD-TIME BEFORE CRISIS  [{domain_name}]")
    print(f"  Unit: {unit}  |  θ* = F1-optimal threshold per rep")
    print(f"  Lead = {unit} from first alarm to event onset")
    print()

    for ev_name, onset in events_idx.items():
        print(f"  ┌─ Event: {ev_name}  (onset at {unit[:-1]} {onset})")
        hdr = f"  │ {'Rep':<18s} │ {'θ*(F1)':>7s} │ {'Lead(θ*)':>9s} │ {'1st alarm':>10s}"
        for t in (0.3, 0.5, 0.7):
            hdr += f" │ S>{t:.1f}"
        hdr += f" │ {'Best':>6s}"
        print(hdr)
        print(f"  │ " + "─" * 105)

        for rn, res in results.items():
            m = compute_detection_metrics(res['scores'], y_true)
            thresh = m['threshold']

            # F1-optimal threshold lead-time
            lt_f1 = compute_lead_time(res['scores'], onset, (thresh,))
            lead_f1 = lt_f1[thresh]['lead_time']
            alarm_f1 = lt_f1[thresh]['first_alarm']

            # Fixed threshold lead-times
            lt = compute_lead_time(res['scores'], onset, (0.3, 0.5, 0.7))

            row = f"  │ {rn:<18s} │ {thresh:7.3f}"
            if lead_f1 > 0:
                row += f" │ {lead_f1:5d} {unit[:1]}   │ {alarm_f1:>10d}"
            else:
                row += f" │     —     │        —  "

            best_lead = lead_f1
            for t in (0.3, 0.5, 0.7):
                l = lt[t]['lead_time']
                if l > 0:
                    row += f" │ {l:4d}"
                    best_lead = max(best_lead, l)
                else:
                    row += f" │   — "

            if best_lead > 0:
                row += f" │ {best_lead:4d}{unit[:1]}"
            else:
                row += f" │  none"
            print(row)
        print(f"  └{'─' * 110}")
        print()


def table2_detection_accuracy(domain_name, results, y_true):
    """TABLE 2: Detection accuracy — Precision, Recall, F1, AUC."""
    print_header(f"TABLE 2 — EARLY WARNING SIGNAL ACCURACY  [{domain_name}]")
    print(f"  F1-optimal threshold  |  CG = CollapseGeometry score")
    print()

    # CollapseGeometry scores
    print(f"  {'Rep':<18s} │ {'AUC':>6s} │ {'Thresh':>7s} │ {'Prec':>6s} │"
          f" {'Recall':>6s} │ {'F1':>6s} │ {'FAR':>6s}")
    print(f"  " + "─" * 80)

    for rn, res in results.items():
        m = compute_detection_metrics(res['scores'], y_true)
        a = auc_manual(y_true, res['scores'])
        print(f"  {rn:<18s} │ {a:6.3f} │ {m['threshold']:7.3f} │"
              f" {m['precision']:6.3f} │ {m['recall']:6.3f} │"
              f" {m['f1']:6.3f} │ {m['far']:6.3f}")

    # Best adaptive scorer per rep
    print(f"\n  Best Adaptive Scorer per Rep:")
    print(f"  {'Rep':<18s} │ {'Scorer':<16s} │ {'AUC':>6s} │ {'Thresh':>7s} │"
          f" {'Prec':>6s} │ {'Recall':>6s} │ {'F1':>6s} │ {'FAR':>6s}")
    print(f"  " + "─" * 95)

    for rn, res in results.items():
        best_sn = None
        best_auc = 0
        for sn, sa in res['scorer_aucs'].items():
            if sa > best_auc:
                best_auc = sa
                best_sn = sn
        if best_sn:
            m = compute_detection_metrics(res['scorer_results'][best_sn], y_true)
            print(f"  {rn:<18s} │ {best_sn:<16s} │ {best_auc:6.3f} │"
                  f" {m['threshold']:7.3f} │ {m['precision']:6.3f} │"
                  f" {m['recall']:6.3f} │ {m['f1']:6.3f} │ {m['far']:6.3f}")
    print()


def table_fa_per_event(domain_name, results, events_idx, unit, y_true, window=None):
    """FALSE ALARMS PER EVENT — count in pre-event window."""
    wstr = f"{window} {unit}" if window else "all pre-event"
    print_header(f"FALSE ALARMS PER EVENT  [{domain_name}]")
    print(f"  Window: {wstr} before each event onset")
    print(f"  FA = normal periods with score > F1-optimal threshold")
    print()

    event_names = list(events_idx.keys())

    hdr = f"  {'Rep':<18s} │"
    for ev in event_names:
        hdr += f" {ev[:14]:>14s} │"
    hdr += f" {'Total FA':>8s} │ {'FA rate':>8s}"
    print(hdr)
    print(f"  " + "─" * (20 + 16 * len(event_names) + 22))

    for rn, res in results.items():
        m = compute_detection_metrics(res['scores'], y_true)
        thresh = m['threshold']
        row = f"  {rn:<18s} │"
        total_fa, total_norm = 0, 0

        for ev in event_names:
            onset = events_idx[ev]
            if window is not None:
                start = max(0, onset - window)
            else:
                start = 0
            pre_y = y_true[start:onset]
            pre_s = res['scores'][start:onset]
            norm_mask = pre_y == 0
            n_norm = int(norm_mask.sum())
            n_fa = int((pre_s[norm_mask] > thresh).sum()) if n_norm > 0 else 0
            total_fa += n_fa
            total_norm += n_norm
            row += f" {n_fa:>5d}/{n_norm:<7d} │"

        fa_rate = total_fa / total_norm if total_norm > 0 else 0.0
        row += f" {total_fa:>8d} │ {fa_rate:8.1%}"
        print(row)
    print()


def table3_false_alarm(domain_name, results, y_true):
    """TABLE 3: False alarm rates at fixed thresholds."""
    print_header(f"TABLE 3 — FALSE ALARM RATE  [{domain_name}]")
    print(f"  FAR = fraction of NORMAL periods where score > threshold")
    print()

    print(f"  {'Rep':<18s} │ {'FAR@0.3':>8s} │ {'FAR@0.5':>8s} │"
          f" {'FAR@0.7':>8s} │ {'Normal N':>8s}")
    print(f"  " + "─" * 65)

    for rn, res in results.items():
        far = compute_far_at_thresholds(res['scores'], y_true, (0.3, 0.5, 0.7))
        n_normal = (y_true == 0).sum()
        print(f"  {rn:<18s} │ {far[0.3]:8.1%} │ {far[0.5]:8.1%} │"
              f" {far[0.7]:8.1%} │ {n_normal:8d}")

    # Also show for best adaptive scorer per rep
    print(f"\n  Best Adaptive Scorer FAR:")
    print(f"  {'Rep':<18s} │ {'Scorer':<16s} │ {'FAR@0.3':>8s} │"
          f" {'FAR@0.5':>8s} │ {'FAR@0.7':>8s}")
    print(f"  " + "─" * 75)

    for rn, res in results.items():
        best_sn = max(res['scorer_aucs'], key=res['scorer_aucs'].get,
                      default=None)
        if best_sn:
            far = compute_far_at_thresholds(
                res['scorer_results'][best_sn], y_true, (0.3, 0.5, 0.7))
            print(f"  {rn:<18s} │ {best_sn:<16s} │ {far[0.3]:8.1%} │"
                  f" {far[0.5]:8.1%} │ {far[0.7]:8.1%}")
    print()


def table4_bsdt(domain_name, results, events_dict, T):
    """TABLE 4: BSDT channel decomposition per event."""
    print_header(f"TABLE 4 — BSDT CHANNEL DECOMPOSITION  [{domain_name}]")
    print(f"  δ_C=camouflage  δ_G=gap  δ_A=activity  δ_T=temporal  E_BS=total energy")
    print(f"  Ratio = event_mean / normal_mean  (>1 = above normal)")
    print()

    for rn, res in results.items():
        det = res['det']
        print(f"  ┌─ Rep: {rn} ({res['det'].Q.shape[0]} obs)")

        # Get normal baseline
        normal_mask = events_dict.get('normal')
        if normal_mask is None:
            continue

        if isinstance(normal_mask, tuple):
            nm = np.zeros(T, dtype=bool)
            nm[normal_mask[0]:normal_mask[1]] = True
            normal_mask = nm
        elif isinstance(normal_mask, np.ndarray) and normal_mask.dtype != bool:
            normal_mask = normal_mask.astype(bool)

        n_dc = det.delta_C[normal_mask].mean()
        n_dg = det.delta_G[normal_mask].mean()
        n_da = det.delta_A[normal_mask].mean()
        n_dt = det.delta_T[normal_mask].mean()
        n_ebs = det.E_BS[normal_mask].mean()

        print(f"  │ Normal baseline: δ_C={n_dc:.3f}  δ_G={n_dg:.3f}  "
              f"δ_A={n_da:.3f}  δ_T={n_dt:.3f}  E_BS={n_ebs:.1f}")
        print(f"  │")
        print(f"  │ {'Event':<22s} │ {'δ_C':>7s} {'(×)':>5s} │ {'δ_G':>7s} {'(×)':>5s} │"
              f" {'δ_A':>7s} {'(×)':>5s} │ {'δ_T':>7s} {'(×)':>5s} │"
              f" {'E_BS':>9s} {'(×)':>5s} │ {'Dom':>5s}")
        print(f"  │ " + "─" * 100)

        for ev_name, ev_info in events_dict.items():
            if ev_name == 'normal':
                continue

            if isinstance(ev_info, tuple):
                mask = np.zeros(T, dtype=bool)
                mask[ev_info[0]:ev_info[1]] = True
            elif isinstance(ev_info, np.ndarray):
                mask = ev_info.astype(bool) if ev_info.dtype != bool else ev_info
            else:
                continue

            if mask.sum() == 0:
                continue

            dc = det.delta_C[mask].mean()
            dg = det.delta_G[mask].mean()
            da = det.delta_A[mask].mean()
            dt_ = det.delta_T[mask].mean()
            ebs = det.E_BS[mask].mean()

            rc = dc / (n_dc + 1e-12)
            rg = dg / (n_dg + 1e-12)
            ra = da / (n_da + 1e-12) if n_da > 1e-6 else 0
            rt = dt_ / (n_dt + 1e-12)
            re = ebs / (n_ebs + 1e-12)

            # Dominant channel
            ch_vals = {'C': dc, 'G': dg, 'A': da, 'T': dt_}
            dom_ch = max(ch_vals, key=ch_vals.get)

            print(f"  │ {ev_name:<22s} │ {dc:7.3f} {rc:4.1f}× │ {dg:7.3f} {rg:4.1f}× │"
                  f" {da:7.3f} {ra:4.1f}× │ {dt_:7.3f} {rt:4.1f}× │"
                  f" {ebs:9.1f} {re:4.1f}× │ δ_{dom_ch:>1s}")

        print(f"  └{'─' * 105}")
        print()


def table5_friction(domain_name, results, events_dict, T):
    """TABLE 5: Adaptive friction, dissipation, potentials."""
    print_header(f"TABLE 5 — ADAPTIVE FRICTION & DISSIPATION  [{domain_name}]")
    print(f"  σ_diss = dissipation rate  |  γ* = adaptive friction coefficient")
    print(f"  E/σ = energy-to-dissipation ratio (>100 = friction overwhelmed)")
    print(f"  %fail = fraction where σ < 0.01·E_BS (dissipation failure)")
    print()

    for rn, res in results.items():
        det = res['det']
        bsdt = res.get('bsdt_data', {})

        print(f"  ┌─ Rep: {rn}")
        print(f"  │ {'Event':<22s} │ {'σ_diss':>9s} │ {'γ*':>9s} │"
              f" {'E_BS':>9s} │ {'E/σ':>7s} │ {'%fail':>6s} │"
              f" {'Φ_grav':>9s} │ {'Φ_mol':>9s} │ {'Φ_hyb':>9s}")
        print(f"  │ " + "─" * 110)

        for ev_name, ev_info in events_dict.items():
            if isinstance(ev_info, tuple):
                mask = np.zeros(T, dtype=bool)
                mask[ev_info[0]:ev_info[1]] = True
            elif isinstance(ev_info, np.ndarray):
                mask = ev_info.astype(bool) if ev_info.dtype != bool else ev_info
            else:
                continue

            if mask.sum() == 0:
                continue

            sigma = det.sigma_dissipation[mask].mean()
            gamma = det.gamma_star[mask].mean()
            ebs = det.E_BS[mask].mean()
            e_over_s = ebs / (sigma + 1e-12)
            dfail = det.dissipation_failure[mask].mean()

            # Potentials from BSDT adaptive geometry
            pg = bsdt.get('phi_gravity', np.zeros(T))
            pm = bsdt.get('phi_molecular', np.zeros(T))
            ph = bsdt.get('phi_hybrid', np.zeros(T))
            if isinstance(pg, np.ndarray) and len(pg) == T:
                pg_v = pg[mask].mean()
                pm_v = pm[mask].mean()
                ph_v = ph[mask].mean()
            else:
                pg_v = pm_v = ph_v = 0

            print(f"  │ {ev_name:<22s} │ {sigma:9.4f} │ {gamma:9.6f} │"
                  f" {ebs:9.1f} │ {e_over_s:7.0f} │ {dfail:6.1%} │"
                  f" {pg_v:9.4f} │ {pm_v:9.4f} │ {ph_v:9.4f}")

        print(f"  └{'─' * 115}")
        print()


def table6_scorer_ranking(domain_name, results, y_true):
    """TABLE 6: All adaptive geometry scorers ranked."""
    print_header(f"TABLE 6 — ADAPTIVE GEOMETRY SCORER RANKING  [{domain_name}]")
    print(f"  All 11 scorers: CG + FWS + Morse + Betti + 3×BSDT + UDL + Trig + 2×Fused")
    print()

    # Collect all scorer names across reps
    all_scorers = set()
    for res in results.values():
        all_scorers.update(res['scorer_aucs'].keys())
    all_scorers = sorted(all_scorers)

    # Header
    hdr = f"  {'Scorer':<16s}"
    for rn in results:
        hdr += f" │ {rn[:14]:>14s}"
    hdr += f" │ {'Mean':>6s}"
    print(hdr)
    print(f"  " + "─" * (16 + 17 * len(results) + 10))

    # CG first
    row = f"  {'CG(collapse)':16s}"
    cg_vals = []
    for rn, res in results.items():
        a = auc_manual(y_true, res['scores'])
        row += f" │ {a:14.3f}"
        cg_vals.append(a)
    row += f" │ {np.mean(cg_vals):6.3f}"
    print(row)

    # Each adaptive scorer
    for sn in all_scorers:
        row = f"  {sn:<16s}"
        vals = []
        for rn, res in results.items():
            a = res['scorer_aucs'].get(sn)
            if a is not None:
                row += f" │ {a:14.3f}"
                vals.append(a)
            else:
                row += f" │ {'—':>14s}"
        m = np.mean(vals) if vals else 0
        row += f" │ {m:6.3f}"
        print(row)

    print()


def table7_fisher_vr(domain_name, results, events_dict, T):
    """TABLE 7: Fisher VR weight decomposition — what drives detection."""
    print_header(f"TABLE 7 — FISHER VR INDICATOR DECOMPOSITION  [{domain_name}]")
    print(f"  7 indicators: Q_ex=radial excess, θ_ex=angular, −σ=dissipation,")
    print(f"  dE=energy ratio, Q×θ=coupling, K×θ=curvature, AM=Mahalanobis")
    print()

    for rn, res in results.items():
        cg = res['cg']
        raw_ind = res['raw_ind']
        z = (raw_ind - cg._fusion_mu) / (cg._fusion_std + 1e-12)
        z_pos = np.maximum(z, 0)
        wz = z_pos * cg._w_fusion

        print(f"  ┌─ Rep: {rn}  weights={np.array2string(cg._w_fusion, precision=3)}")
        hdr = f"  │ {'Event':<22s}"
        for n in IND_NAMES:
            hdr += f" │ {n:>6s}"
        hdr += f" │ {'Dominant':>10s}"
        print(hdr)
        print(f"  │ " + "─" * 90)

        for ev_name, ev_info in events_dict.items():
            if isinstance(ev_info, tuple):
                mask = np.zeros(T, dtype=bool)
                mask[ev_info[0]:ev_info[1]] = True
            elif isinstance(ev_info, np.ndarray):
                mask = ev_info.astype(bool) if ev_info.dtype != bool else ev_info
            else:
                continue
            if mask.sum() == 0:
                continue

            wm = wz[mask].mean(axis=0)
            total = wm.sum() + 1e-12
            pcts = wm / total * 100

            dom_idx = int(np.argmax(pcts))
            dom_name = IND_NAMES[dom_idx]

            row = f"  │ {ev_name:<22s}"
            for j in range(7):
                row += f" │ {pcts[j]:5.1f}%"
            row += f" │ {dom_name:>10s}"
            print(row)

        print(f"  └{'─' * 95}")
        print()


# ═══════════════════════════════════════════════════════════════════
# DOMAIN RUNNERS
# ═══════════════════════════════════════════════════════════════════

def run_domain_bank():
    print("\n" + "█" * W)
    print("  DOMAIN: WORLD BANKING (GFC) — quarterly, 5D, pooled GSIB panel")
    print("█" * W)

    X_ref, X_pred, y, events_idx, unit, n_banks = load_bank()
    print(f"  {n_banks} banks, ref={X_ref.shape}, pred={X_pred.shape}, "
          f"crisis rate={y.mean():.1%}")

    events_dict = {
        'normal': (y == 0),
        'GFC_crisis': (y == 1),
    }

    print(f"\n  Building representations...")
    reps = build_reps(X_ref, X_pred)
    print(f"  Built: {list(reps.keys())}")

    results = {}
    for rn in ['Raw'] + list(reps.keys()):
        R_ref = X_ref if rn == 'Raw' else reps[rn]['ref']
        R_all = X_pred if rn == 'Raw' else reps[rn]['all']
        print(f"  Computing {rn} ({R_all.shape[1]}D)...", end=" ", flush=True)
        results[rn] = run_full_geometry(rn, R_ref, R_all, y)
        a = auc_manual(y, results[rn]['scores'])
        print(f"AUC={a:.3f}")

    T = len(y)
    table1_lead_time("BANKING", results, events_idx, unit, y)
    table_fa_per_event("BANKING", results, events_idx, unit, y, window=4)
    table2_detection_accuracy("BANKING", results, y)
    table3_false_alarm("BANKING", results, y)
    table4_bsdt("BANKING", results, events_dict, T)
    table5_friction("BANKING", results, events_dict, T)
    table6_scorer_ranking("BANKING", results, y)
    table7_fisher_vr("BANKING", results, events_dict, T)

    return results, y


def run_domain_ercot(mode="combined"):
    tag = {"combined": "COMBINED d=10",
           "supply":   "SUPPLY-ONLY d=5"}[mode]
    print("\n" + "█" * W)
    print(f"  DOMAIN: ERCOT POWER GRID — {tag} — daily")
    print("█" * W)

    X_ref, X_daily, y_daily, lab_daily, events_idx, dates, features = \
        load_ercot(mode)
    N = len(X_daily)
    print(f"  {N} days, {X_daily.shape[1]} features, ref={X_ref.shape[0]} days")
    print(f"  Events: {list(events_idx.keys())}")

    events_dict = {'normal': (lab_daily == "normal")}
    for ev in events_idx:
        events_dict[ev] = (lab_daily == ev)

    print(f"\n  Building representations...")
    reps = build_reps(X_ref, X_daily)
    print(f"  Built: {list(reps.keys())}")

    results = {}
    for rn in ['Raw'] + list(reps.keys()):
        R_ref = X_ref if rn == 'Raw' else reps[rn]['ref']
        R_all = X_daily if rn == 'Raw' else reps[rn]['all']
        print(f"  Computing {rn} ({R_all.shape[1]}D)...", end=" ", flush=True)
        results[rn] = run_full_geometry(rn, R_ref, R_all, y_daily)
        a = auc_manual(y_daily, results[rn]['scores'])
        print(f"AUC={a:.3f}")

    table1_lead_time(f"ERCOT {tag}", results, events_idx, 'days', y_daily)
    table_fa_per_event(f"ERCOT {tag}", results, events_idx, 'days', y_daily, window=30)
    table2_detection_accuracy(f"ERCOT {tag}", results, y_daily)
    table3_false_alarm(f"ERCOT {tag}", results, y_daily)
    table4_bsdt(f"ERCOT {tag}", results, events_dict, N)
    table5_friction(f"ERCOT {tag}", results, events_dict, N)
    table6_scorer_ranking(f"ERCOT {tag}", results, y_daily)
    table7_fisher_vr(f"ERCOT {tag}", results, events_dict, N)

    return results, y_daily


def run_domain_terra():
    print("\n" + "█" * W)
    print("  DOMAIN: TERRA/LUNA — hourly, 5D, UST depeg + LUNA collapse")
    print("█" * W)

    X_ref, X, y_true, events_idx = load_terra()
    T = len(X)
    print(f"  {T} hours, ref={X_ref.shape[0]}h, crisis rate={y_true.mean():.1%}")

    events_dict = {
        'normal': (0, 22),
        'early_attack': (22, 48),
        'death_spiral': (48, 96),
        'hyperinflation': (96, 120),
        'chain_halt': (120, 169),
    }

    print(f"\n  Building representations...")
    reps = build_reps(X_ref, X)
    print(f"  Built: {list(reps.keys())}")

    results = {}
    for rn in ['Raw'] + list(reps.keys()):
        R_ref = X_ref if rn == 'Raw' else reps[rn]['ref']
        R_all = X if rn == 'Raw' else reps[rn]['all']
        print(f"  Computing {rn} ({R_all.shape[1]}D)...", end=" ", flush=True)
        results[rn] = run_full_geometry(rn, R_ref, R_all, y_true)
        a = auc_manual(y_true, results[rn]['scores'])
        print(f"AUC={a:.3f}")

    table1_lead_time("TERRA/LUNA", results, events_idx, 'hours', y_true)
    table_fa_per_event("TERRA/LUNA", results, events_idx, 'hours', y_true, window=10)
    table2_detection_accuracy("TERRA/LUNA", results, y_true)
    table3_false_alarm("TERRA/LUNA", results, y_true)
    table4_bsdt("TERRA/LUNA", results, events_dict, T)
    table5_friction("TERRA/LUNA", results, events_dict, T)
    table6_scorer_ranking("TERRA/LUNA", results, y_true)
    table7_fisher_vr("TERRA/LUNA", results, events_dict, T)

    return results, y_true


# ═══════════════════════════════════════════════════════════════════
# CROSS-DOMAIN SUMMARY
# ═══════════════════════════════════════════════════════════════════

def cross_domain_summary(all_results):
    """Final cross-domain comparison table."""
    print_header("CROSS-DOMAIN COMPARISON — BEST RESULTS PER DOMAIN")

    for dom_name, (results, y_true) in all_results.items():
        print(f"\n  ┌─ {dom_name}")

        # Find best rep by CG AUC
        best_rep_cg = max(results, key=lambda r: auc_manual(y_true, results[r]['scores']))
        best_cg_auc = auc_manual(y_true, results[best_rep_cg]['scores'])
        best_cg_m = compute_detection_metrics(results[best_rep_cg]['scores'], y_true)

        # Find best overall (CG or adaptive)
        best_score_name = "CG"
        best_score_auc = best_cg_auc
        best_score_rep = best_rep_cg
        best_score_arr = results[best_rep_cg]['scores']

        for rn, res in results.items():
            for sn, sa in res['scorer_aucs'].items():
                if sa > best_score_auc:
                    best_score_auc = sa
                    best_score_name = sn
                    best_score_rep = rn
                    best_score_arr = res['scorer_results'][sn]

        best_m = compute_detection_metrics(best_score_arr, y_true)

        print(f"  │ Best CG:       {best_rep_cg:<16s}  AUC={best_cg_auc:.3f}  "
              f"F1={best_cg_m['f1']:.3f}  Prec={best_cg_m['precision']:.3f}  "
              f"Rec={best_cg_m['recall']:.3f}  FAR={best_cg_m['far']:.3f}")
        print(f"  │ Best Overall:  {best_score_rep:<16s}  {best_score_name:<14s}  "
              f"AUC={best_score_auc:.3f}  F1={best_m['f1']:.3f}  "
              f"Prec={best_m['precision']:.3f}  Rec={best_m['recall']:.3f}  "
              f"FAR={best_m['far']:.3f}")

        # BSDT verdict
        for rn, res in results.items():
            if rn == best_rep_cg:
                bsdt_aucs = {sn: a for sn, a in res['scorer_aucs'].items()
                             if 'BSDT' in sn}
                if bsdt_aucs:
                    best_bsdt = max(bsdt_aucs, key=bsdt_aucs.get)
                    print(f"  │ Best BSDT:     {rn:<16s}  {best_bsdt:<14s}  "
                          f"AUC={bsdt_aucs[best_bsdt]:.3f}")

        print(f"  └{'─' * 95}")

    # Final ranking table
    print(f"\n  DOMAIN × METRIC SUMMARY:")
    print(f"  {'Domain':<20s} │ {'Best Rep':>14s} │ {'AUC':>6s} │ {'F1':>6s} │"
          f" {'Prec':>6s} │ {'Rec':>6s} │ {'FAR':>6s} │ {'Method':>14s}")
    print(f"  " + "─" * 105)

    for dom_name, (results, y_true) in all_results.items():
        best_auc = 0
        best_info = None
        for rn, res in results.items():
            a = auc_manual(y_true, res['scores'])
            if a > best_auc:
                best_auc = a
                best_info = (rn, 'CG', res['scores'])
            for sn, sa in res['scorer_aucs'].items():
                if sa > best_auc:
                    best_auc = sa
                    best_info = (rn, sn, res['scorer_results'][sn])

        if best_info:
            rn, method, arr = best_info
            m = compute_detection_metrics(arr, y_true)
            print(f"  {dom_name:<20s} │ {rn:>14s} │ {best_auc:6.3f} │"
                  f" {m['f1']:6.3f} │ {m['precision']:6.3f} │ {m['recall']:6.3f} │"
                  f" {m['far']:6.3f} │ {method:>14s}")


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

def main():
    t0 = time.time()
    np.set_printoptions(precision=4, suppress=True, linewidth=120)

    print("=" * W)
    print("  EARLY WARNING DETECTION — FULL GEOMETRY OF COLLAPSE")
    print("  Lead-Time | Accuracy | False Alarms | BSDT | Friction | Scorers")
    print("=" * W)

    all_results = {}

    # Banking
    bank_res, bank_y = run_domain_bank()
    all_results['Banking (GFC)'] = (bank_res, bank_y)

    # ERCOT Combined
    ercot_res, ercot_y = run_domain_ercot(mode="combined")
    all_results['ERCOT Combined'] = (ercot_res, ercot_y)

    # Terra/Luna
    terra_res, terra_y = run_domain_terra()
    all_results['Terra/Luna'] = (terra_res, terra_y)

    # Cross-domain
    cross_domain_summary(all_results)

    elapsed = time.time() - t0
    print(f"\n{'=' * W}")
    print(f"  COMPLETED in {elapsed:.1f}s")
    print(f"{'=' * W}")


if __name__ == "__main__":
    main()
