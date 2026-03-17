"""Check False Alarm Rate (FAR) for all methods — with calibration."""
import sys, os, numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'udl'))

from system_mode import (
    ReducedTensorDescriptor,
    MolecularEngine, GravityModeEngine, HybridGravityEngine,
    BettiBarcodeSuite, MorseTopologyAlarm,
)
from sklearn.metrics import roc_auc_score, roc_curve, confusion_matrix
from sklearn.isotonic import IsotonicRegression

# Import data builders from bench_descriptor
from bench_descriptor import build_ercot_data, build_bank_data


def quantile_calibrate(scores, ref_scores):
    """Calibrate: score → empirical p-value against reference distribution.

    p(x) = fraction of reference scores < x.  Higher = more anomalous.
    This is a monotone transform, so AUC is preserved.
    """
    ref_sorted = np.sort(ref_scores)
    return np.searchsorted(ref_sorted, scores) / len(ref_sorted)


def isotonic_calibrate(scores, y, ref_scores):
    """Isotonic regression calibration on held-out split.

    Fit monotone mapping score → P(crisis) using 50% of data,
    apply to full dataset.  AUC preserved (monotone).
    """
    n = len(scores)
    rng = np.random.RandomState(42)
    idx = rng.permutation(n)
    half = n // 2
    train_idx, test_idx = idx[:half], idx[half:]

    ir = IsotonicRegression(out_of_bounds='clip')
    ir.fit(scores[train_idx], y[train_idx])
    calibrated = ir.predict(scores)
    return calibrated


def platt_calibrate(scores, ref_scores):
    """Platt scaling: fit sigmoid to map reference scores to ~0.

    score_cal = sigmoid(a * (score - mu) / sigma)
    where mu, sigma from reference distribution.
    a chosen so that 2-sigma maps to sigmoid active region.
    """
    mu = np.mean(ref_scores)
    sigma = np.std(ref_scores) + 1e-10
    z = (scores - mu) / sigma
    # Scale so 2-sigma → sigmoid(3) ≈ 0.95
    a = 1.5
    return 1.0 / (1.0 + np.exp(-a * z))

datasets = {}
X_e, y_e, T_e, N_e = build_ercot_data()
datasets['ERCOT'] = (X_e, y_e, T_e, N_e)
X_b, y_b, T_b, N_b = build_bank_data()
datasets['Bank'] = (X_b, y_b, T_b, N_b)

for name, (X, y, T, Nent) in datasets.items():
    X_ref = X[y == 0]
    Ntotal = len(y)
    n_pos = int(y.sum())
    n_neg = Ntotal - n_pos

    print(f"\n{'=' * 72}")
    print(f"  {name}: N={Ntotal}, crisis={n_pos}, normal={n_neg}")
    print(f"{'=' * 72}")

    methods = {}

    # ── Semi-supervised: engines know which data is normal (reference) ──
    # Labels only used to identify reference set (standard AD paradigm).
    # The simulation is transductive (all particles interact).
    # The scorer is calibrated on normal particles' final positions.
    for EngCls, ename in [
        (GravityModeEngine, 'Gravity'),
        (MolecularEngine, 'Molecular'),
    ]:
        eng = EngCls()
        scores = eng.fit_score(X, y)
        methods[ename] = scores

    # Hybrid: equal blend (no label-optimized weighting)
    if 'Gravity' in methods and 'Molecular' in methods:
        mol_s = methods['Molecular']
        grav_s = methods['Gravity']
        def mm(x):
            r = x.max() - x.min()
            return (x - x.min()) / r if r > 1e-10 else np.zeros_like(x)
        methods['Hybrid'] = 0.5 * mm(mol_s) + 0.5 * mm(grav_s)

    # RTD — fit on normal reference (semi-supervised, standard for kNN methods)
    desc = ReducedTensorDescriptor(k_neighbors=10)
    desc.fit(X_ref)
    methods['RTD_FitScore'] = desc.fit_score(X, y)

    # Betti — fit on normal reference (semi-supervised)
    betti = BettiBarcodeSuite(k=10)
    betti.fit(X_ref)
    methods['Betti'] = betti.score(X)

    # Universal scoring (quarter-level)
    for EngCls, ename in [
        (GravityModeEngine, 'Gravity_Univ'),
    ]:
        eng = EngCls()
        raw = eng.fit_score(X, y)
        try:
            raw_2d = raw.reshape(T, Nent)
            q_scores = raw_2d.mean(axis=1)  # (T,)
            q_broad = np.repeat(q_scores, Nent)
            methods[ename] = q_broad
        except Exception:
            pass

    hdr = f"  {'Method':<20} {'AUC':>7}  {'FAR@95':>7} {'FAR@90':>7} {'FAR@80':>7}  {'FP':>5} {'FN':>5} {'TP':>5} {'TN':>5}"
    print(hdr)
    print(f"  {'-' * 68}")

    # ── Collect raw results first ──
    raw_results = {}
    for mname, scores in methods.items():
        if scores is None:
            continue
        auc = roc_auc_score(y, scores)
        fpr, tpr, thresholds = roc_curve(y, scores)

        def far_at_tpr(target):
            idx = np.argmin(np.abs(tpr - target))
            return fpr[idx]

        far95 = far_at_tpr(0.95)
        far90 = far_at_tpr(0.90)
        far80 = far_at_tpr(0.80)

        j = tpr - fpr
        best_idx = np.argmax(j)
        best_thresh = thresholds[best_idx]
        y_pred = (scores >= best_thresh).astype(int)
        tn, fp, fn, tp = confusion_matrix(y, y_pred).ravel()

        print(f"  {mname:<20} {auc:>7.4f}  {far95:>6.1%} {far90:>6.1%} {far80:>6.1%}  {fp:>5} {fn:>5} {tp:>5} {tn:>5}")
        raw_results[mname] = scores

    # ── Calibrated scoring ──
    # Pick the top methods worth calibrating
    calibrate_methods = ['Hybrid', 'Gravity', 'Molecular', 'RTD_FitScore',
                         'Betti', 'Gravity_Univ']

    print(f"\n  === CALIBRATED (quantile p-value against reference) ===")
    print(hdr)
    print(f"  {'-' * 68}")
    for mname in calibrate_methods:
        if mname not in raw_results:
            continue
        scores = raw_results[mname]
        ref_scores = scores[y == 0]
        cal_scores = quantile_calibrate(scores, ref_scores)
        auc = roc_auc_score(y, cal_scores)
        fpr, tpr, thresholds = roc_curve(y, cal_scores)

        def far_at_tpr(target):
            idx = np.argmin(np.abs(tpr - target))
            return fpr[idx]

        far95 = far_at_tpr(0.95)
        far90 = far_at_tpr(0.90)
        far80 = far_at_tpr(0.80)

        j = tpr - fpr
        best_idx = np.argmax(j)
        best_thresh = thresholds[best_idx]
        y_pred = (cal_scores >= best_thresh).astype(int)
        tn, fp, fn, tp = confusion_matrix(y, y_pred).ravel()

        cname = f"Q_{mname}"[:20]
        print(f"  {cname:<20} {auc:>7.4f}  {far95:>6.1%} {far90:>6.1%} {far80:>6.1%}  {fp:>5} {fn:>5} {tp:>5} {tn:>5}")

    print(f"\n  === CALIBRATED (isotonic regression) ===")
    print(hdr)
    print(f"  {'-' * 68}")
    for mname in calibrate_methods:
        if mname not in raw_results:
            continue
        scores = raw_results[mname]
        try:
            cal_scores = isotonic_calibrate(scores, y, scores[y == 0])
            auc = roc_auc_score(y, cal_scores)
            fpr, tpr, thresholds = roc_curve(y, cal_scores)

            def far_at_tpr(target):
                idx = np.argmin(np.abs(tpr - target))
                return fpr[idx]

            far95 = far_at_tpr(0.95)
            far90 = far_at_tpr(0.90)
            far80 = far_at_tpr(0.80)

            j = tpr - fpr
            best_idx = np.argmax(j)
            best_thresh = thresholds[best_idx]
            y_pred = (cal_scores >= best_thresh).astype(int)
            tn, fp, fn, tp = confusion_matrix(y, y_pred).ravel()

            cname = f"I_{mname}"[:20]
            print(f"  {cname:<20} {auc:>7.4f}  {far95:>6.1%} {far90:>6.1%} {far80:>6.1%}  {fp:>5} {fn:>5} {tp:>5} {tn:>5}")
        except Exception as e:
            print(f"  I_{mname:<18} FAIL: {e}")

    # ── Fusion: calibrate then combine top methods ──
    print(f"\n  === FUSED CALIBRATED ENSEMBLES ===")
    print(hdr)
    print(f"  {'-' * 68}")
    fusion_sets = {
        'Fuse_Top3': ['Gravity_Univ', 'Betti', 'Molecular'],
        'Fuse_All5': ['Gravity_Univ', 'Betti', 'Molecular', 'Hybrid', 'Gravity'],
        'Fuse_Eng+Betti': ['Hybrid', 'Gravity', 'Molecular', 'Betti'],
    }
    for fname, members in fusion_sets.items():
        avail = [m for m in members if m in raw_results]
        if len(avail) < 2:
            continue
        # Quantile-calibrate each, then average
        cal_all = []
        for m in avail:
            s = raw_results[m]
            ref_s = s[y == 0]
            cal_all.append(quantile_calibrate(s, ref_s))
        fused = np.mean(cal_all, axis=0)
        auc = roc_auc_score(y, fused)
        fpr, tpr, thresholds = roc_curve(y, fused)

        def far_at_tpr(target):
            idx = np.argmin(np.abs(tpr - target))
            return fpr[idx]

        far95 = far_at_tpr(0.95)
        far90 = far_at_tpr(0.90)
        far80 = far_at_tpr(0.80)

        j = tpr - fpr
        best_idx = np.argmax(j)
        best_thresh = thresholds[best_idx]
        y_pred = (fused >= best_thresh).astype(int)
        tn, fp, fn, tp = confusion_matrix(y, y_pred).ravel()

        print(f"  {fname:<20} {auc:>7.4f}  {far95:>6.1%} {far90:>6.1%} {far80:>6.1%}  {fp:>5} {fn:>5} {tp:>5} {tn:>5}")

    # ── PANEL-AWARE SCORING ──────────────────────────────────────────
    # Key insight: labels are per-quarter (all N banks share the label).
    # 275 FP = 11 normal quarters flagged; 25 FN = 1 crisis missed.
    # Strategy: per-bank z-norm → exceedance ratio → multi-engine
    #           consensus → conformal p-value for statistical FAR control
    # ─────────────────────────────────────────────────────────────────

    def mm(x):
        """Min-max normalize to [0, 1]."""
        r = x.max() - x.min()
        return (x - x.min()) / r if r > 1e-10 else np.zeros_like(x)

    y_q = y.reshape(T, Nent)[:, 0]  # quarter-level labels
    ref_q = (y_q == 0)

    print(f"\n  === PANEL-AWARE SCORING (per-bank z-norm + exceedance) ===")
    print(hdr)
    print(f"  {'-' * 68}")

    panel_q_scores = {}

    for mname in ['Hybrid', 'Gravity', 'Molecular', 'RTD_FitScore', 'Betti']:
        if mname not in raw_results:
            continue
        raw = raw_results[mname]
        S = raw.reshape(T, Nent)

        # ① Per-bank z-normalization against reference period
        S_ref = S[ref_q]                       # (T_ref, N)
        bank_mu = S_ref.mean(axis=0)            # (N,)
        bank_sigma = S_ref.std(axis=0) + 1e-10  # (N,)
        Z = (S - bank_mu) / bank_sigma          # (T, N) — bank-normalized

        # ② Quarter-level features
        q_median  = np.median(Z, axis=1)        # robust central tendency
        q_exceed  = (Z > 1.5).mean(axis=1)      # systemic breadth
        q_max     = Z.max(axis=1)               # worst-case bank

        # ③ Combined: heavy exceedance weight (systemic indicator)
        combined = 0.40 * mm(q_median) + 0.35 * mm(q_exceed) + 0.25 * mm(q_max)
        panel_q_scores[mname] = combined

        # ④ Conformal p-value against reference quarters
        ref_vals = combined[ref_q]
        ref_sorted = np.sort(ref_vals)
        pvals = np.searchsorted(ref_sorted, combined) / len(ref_sorted)

        panel_obs = np.repeat(pvals, Nent)

        auc = roc_auc_score(y, panel_obs)
        fpr, tpr, thresholds = roc_curve(y, panel_obs)

        def far_at_tpr(target):
            idx = np.argmin(np.abs(tpr - target))
            return fpr[idx]

        far95 = far_at_tpr(0.95)
        far90 = far_at_tpr(0.90)
        far80 = far_at_tpr(0.80)

        j = tpr - fpr
        best_idx = np.argmax(j)
        best_thresh = thresholds[best_idx]
        y_pred = (panel_obs >= best_thresh).astype(int)
        tn, fp, fn, tp = confusion_matrix(y, y_pred).ravel()

        pname = f"P_{mname}"[:20]
        print(f"  {pname:<20} {auc:>7.4f}  {far95:>6.1%} {far90:>6.1%} {far80:>6.1%}  {fp:>5} {fn:>5} {tp:>5} {tn:>5}")

    # ── Multi-engine panel consensus ──
    print(f"\n  === MULTI-ENGINE PANEL CONSENSUS ===")
    print(hdr)
    print(f"  {'-' * 68}")

    consensus_sets = {
        'Cons_G+B':     ['Gravity', 'Betti'],
        'Cons_Top3':    ['Gravity', 'Betti', 'Molecular'],
        'Cons_All5':    ['Hybrid', 'Gravity', 'Molecular', 'RTD_FitScore', 'Betti'],
    }

    for cname, members in consensus_sets.items():
        avail = [m for m in members if m in panel_q_scores]
        if len(avail) < 2:
            continue

        # Average quarter-level combined scores
        consensus_q = np.mean([panel_q_scores[m] for m in avail], axis=0)

        # Conformal p-value
        ref_vals = consensus_q[ref_q]
        ref_sorted = np.sort(ref_vals)
        pvals = np.searchsorted(ref_sorted, consensus_q) / len(ref_sorted)

        consensus_obs = np.repeat(pvals, Nent)

        auc = roc_auc_score(y, consensus_obs)
        fpr, tpr, thresholds = roc_curve(y, consensus_obs)

        def far_at_tpr(target):
            idx = np.argmin(np.abs(tpr - target))
            return fpr[idx]

        far95 = far_at_tpr(0.95)
        far90 = far_at_tpr(0.90)
        far80 = far_at_tpr(0.80)

        j = tpr - fpr
        best_idx = np.argmax(j)
        best_thresh = thresholds[best_idx]
        y_pred = (consensus_obs >= best_thresh).astype(int)
        tn, fp, fn, tp = confusion_matrix(y, y_pred).ravel()

        print(f"  {cname:<20} {auc:>7.4f}  {far95:>6.1%} {far90:>6.1%} {far80:>6.1%}  {fp:>5} {fn:>5} {tp:>5} {tn:>5}")

    # ── Diagnostic: which normal quarters are flagged? ──
    if 'Gravity' in panel_q_scores:
        print(f"\n  --- Quarter-level diagnostic (Gravity panel score) ---")
        gq = panel_q_scores['Gravity']
        ref_sorted_g = np.sort(gq[ref_q])
        thresh_90 = ref_sorted_g[int(0.90 * len(ref_sorted_g))] if len(ref_sorted_g) > 0 else 0
        print(f"  {'Qtr':<5} {'Label':>6} {'Score':>7} {'Flag':>5}")
        import pandas as pd
        dates = pd.date_range('2005-01-01', '2023-12-31', freq='QE')[:T]
        for t in range(T):
            label = 'CRISIS' if y_q[t] == 1 else 'normal'
            flag = '*** ' if gq[t] > thresh_90 and y_q[t] == 0 else \
                   'MISS' if gq[t] <= thresh_90 and y_q[t] == 1 else ''
            d = f"{dates[t].year}Q{(dates[t].month-1)//3+1}" if t < len(dates) else f"Q{t}"
            print(f"  {d:<8} {label:>6} {gq[t]:>7.4f}  {flag}")

    # Zero false alarm check
    print(f"\n  Zero-FA check (threshold = max normal score):")
    for mname, scores in methods.items():
        if scores is None:
            continue
        normal_max = scores[y == 0].max()
        tp_at_zero_fa = (scores[y == 1] > normal_max).sum()
        print(f"    {mname:<20} TP@ZeroFA={tp_at_zero_fa}/{n_pos}  ({tp_at_zero_fa/n_pos:.1%})")

    # Also check panel methods zero-FA
    for mname, q_combined in panel_q_scores.items():
        pvals = np.searchsorted(np.sort(q_combined[ref_q]), q_combined) / ref_q.sum()
        panel_obs = np.repeat(pvals, Nent)
        normal_max = panel_obs[y == 0].max()
        tp_at_zero_fa = (panel_obs[y == 1] > normal_max).sum()
        print(f"    P_{mname:<18} TP@ZeroFA={tp_at_zero_fa}/{n_pos}  ({tp_at_zero_fa/n_pos:.1%})")

    # ══════════════════════════════════════════════════════════════════
    #  EXPANDING-WINDOW PROSPECTIVE SCORING
    #  Protocol: score quarter t using only data up to t
    #  Threshold: 99th percentile of 2005Q1-2007Q3 calm window
    #  NO labels ever passed to engines — fully unsupervised
    # ══════════════════════════════════════════════════════════════════
    if name != 'Bank':
        continue  # Only Bank has the panel structure for expanding window

    import pandas as pd
    dates = pd.date_range('2005-01-01', '2023-12-31', freq='QE')[:T]
    X_3d = X.reshape(T, Nent, -1)
    d_feat = X_3d.shape[2]

    # Calibration: 2005Q1-2007Q3 (11 quarters)
    calib_end = pd.Timestamp("2007-09-30")
    calib_mask = dates <= calib_end
    n_calib = int(calib_mask.sum())

    print(f"\n{'=' * 72}")
    print(f"  EXPANDING-WINDOW PROSPECTIVE SCORING (Bank)")
    print(f"  Calibration: 2005Q1-2007Q3 ({n_calib} quarters)")
    print(f"  Protocol: fit engine on data[:t] only, score quarter t")
    print(f"  Labels: NEVER passed - fully unsupervised")
    print(f"{'=' * 72}")

    ew_hdr = f"  {'Method':<22} {'AUC':>7}  {'FAR':>6}  {'Recall':>7}  {'TP':>3} {'FP':>3} {'FN':>3} {'TN':>3}  {'1st_alarm':<12} {'Lead(Q)':<8}"
    print(ew_hdr)
    print(f"  {'-' * 90}")

    lehman = pd.Timestamp("2008-09-30")
    gfc_start = pd.Timestamp("2007-12-31")

    # ── Cache: compute per-bank scores once per engine ──
    def ew_bank_scores(eng_cls, eng_kw, label):
        """Expanding window → returns (T, Nent) bank-level scores, computed once."""
        S = np.full((T, Nent), np.nan)

        # Phase 1: calibration (fit on calm data)
        X_cal = X_3d[:n_calib].reshape(n_calib * Nent, d_feat)
        y_cal = np.zeros(n_calib * Nent, dtype=int)
        eng = eng_cls(**eng_kw)
        s_cal = eng.fit_score(X_cal, y_cal)
        for t in range(n_calib):
            S[t] = s_cal[t * Nent:(t + 1) * Nent]

        # Phase 2: expanding window
        for t in range(n_calib, T):
            n_pts = (t + 1) * Nent
            X_up = X_3d[:t + 1].reshape(n_pts, d_feat)
            y_dum = np.zeros(n_pts, dtype=int)
            eng = eng_cls(**eng_kw)
            s_all = eng.fit_score(X_up, y_dum)
            S[t] = s_all[-Nent:]
            if (t - n_calib) % 10 == 0:
                print(f"    {label} t={t}/{T}", flush=True)

        print(f"    {label} done.", flush=True)
        return S

    def ew_topo_bank_scores(topo_cls, topo_kw, label):
        """Expanding window → (T, Nent) scores for fit/score API (Betti, Morse)."""
        S = np.full((T, Nent), np.nan)

        X_cal = X_3d[:n_calib].reshape(n_calib * Nent, d_feat)
        t_obj = topo_cls(**topo_kw)
        t_obj.fit(X_cal)
        s_cal = t_obj.score(X_cal)
        for t in range(n_calib):
            S[t] = s_cal[t * Nent:(t + 1) * Nent]

        for t in range(n_calib, T):
            X_up = X_3d[:t + 1].reshape((t + 1) * Nent, d_feat)
            t_obj = topo_cls(**topo_kw)
            t_obj.fit(X_up)
            s_all = t_obj.score(X_up)
            S[t] = s_all[-Nent:]
            if (t - n_calib) % 10 == 0:
                print(f"    {label} t={t}/{T}", flush=True)

        print(f"    {label} done.", flush=True)
        return S

    # ── Derive quarter scores from bank-level cache ──
    def quarter_mean(S):
        """Mean across banks → quarter-level score."""
        return np.nanmean(S, axis=1)

    def panel_score(S):
        """Per-bank z-norm + exceedance → quarter-level score."""
        q = np.full(T, np.nan)
        S_cal = S[:n_calib]
        s_mu = np.nanmean(S_cal, axis=0)   # (N,)
        s_sig = np.nanstd(S_cal, axis=0) + 1e-10
        for t in range(n_calib, T):
            Z_t = (S[t] - s_mu) / s_sig
            q[t] = 0.40 * np.median(Z_t) + 0.35 * (Z_t > 1.5).mean() + 0.25 * np.nanmax(Z_t)
        # Also fill calibration period
        for t in range(n_calib):
            Z_t = (S[t] - s_mu) / s_sig
            q[t] = 0.40 * np.median(Z_t) + 0.35 * (Z_t > 1.5).mean() + 0.25 * np.nanmax(Z_t)
        return q

    def banktail_score(S, tail_frac=0.20):
        """Bank-wise quantile calibration + top-tail aggregation.

        This is more robust than quarter means when only a subset of banks
        goes stressed. Each bank is calibrated against its own calm-period
        distribution, then the quarter score is the mean of the top tail.
        """
        q = np.full(T, np.nan)
        topk = max(1, int(np.ceil(tail_frac * Nent)))
        refs = []
        for j in range(Nent):
            ref = S[:n_calib, j]
            ref = ref[~np.isnan(ref)]
            refs.append(np.sort(ref))

        for t in range(T):
            row = np.full(Nent, np.nan)
            for j, ref in enumerate(refs):
                if len(ref) == 0 or np.isnan(S[t, j]):
                    continue
                row[j] = np.searchsorted(ref, S[t, j], side='right') / len(ref)
            vals = row[~np.isnan(row)]
            if len(vals) == 0:
                continue
            tail = np.sort(vals)[-min(topk, len(vals)):]
            q[t] = tail.mean()
        return q

    def zscore_transform(q_raw):
        """Rolling z-score (Basel cyclical gap) from raw quarter scores."""
        z = np.full(T, np.nan)
        for t in range(2, T):
            past = q_raw[:t]
            valid = past[~np.isnan(past)]
            if len(valid) < 2:
                continue
            z[t] = (q_raw[t] - valid.mean()) / (valid.std() + 1e-10)
        return z

    def eval_ew(q_scores, thresh, label):
        """Evaluate expanding-window results."""
        valid = ~np.isnan(q_scores)
        if valid.sum() < 5:
            print(f"  {label:<22} SKIP — insufficient data")
            return

        auc = roc_auc_score(y_q[valid], q_scores[valid])
        alarm = q_scores > thresh
        tp = int((alarm & (y_q == 1) & valid).sum())
        fp = int((alarm & (y_q == 0) & valid).sum())
        fn = int((~alarm & (y_q == 1) & valid).sum())
        tn = int((~alarm & (y_q == 0) & valid).sum())
        far = fp / max(fp + tn, 1)
        recall = tp / max(tp + fn, 1)

        # Find first alarm before GFC
        pre_gfc = [dates[t] for t in range(T) if valid[t] and alarm[t]
                   and dates[t] < gfc_start and dates[t] >= pd.Timestamp("2007-01-01")]
        if pre_gfc:
            first = min(pre_gfc)
            lead = len(pd.date_range(first, lehman, freq="QE")) - 1
            first_str = f"{first.year}Q{(first.month-1)//3+1}"
        else:
            first_str = "none"
            lead = 0

        print(f"  {label:<22} {auc:>7.4f}  {far:>5.1%}  {recall:>6.1%}  {tp:>3} {fp:>3} {fn:>3} {tn:>3}  {first_str:<12} {lead:<8}")

    # ── Phase 1: Compute bank-level scores (cached, one pass per engine) ──
    print(f"\n  Computing bank-level scores (cached)...", flush=True)
    S_grav = ew_bank_scores(GravityModeEngine, {}, 'Gravity')
    S_mol  = ew_bank_scores(MolecularEngine, {}, 'Molecular')
    S_betti = ew_topo_bank_scores(BettiBarcodeSuite, {'k': 10}, 'EW_Betti')
    S_morse = ew_topo_bank_scores(MorseTopologyAlarm, {'k': 15}, 'EW_Morse')
    S_rtd   = ew_topo_bank_scores(ReducedTensorDescriptor, {'k_neighbors': 10}, 'EW_RTD')
    print(f"  All bank scores cached.\n", flush=True)

    # ── Phase 2: Derive all variants from cache ──

    # Raw quarter means
    q_grav = quarter_mean(S_grav)
    q_mol  = quarter_mean(S_mol)
    q_betti = quarter_mean(S_betti)
    q_morse = quarter_mean(S_morse)
    q_rtd   = quarter_mean(S_rtd)

    th_grav = np.nanpercentile(q_grav[:n_calib], 99)
    th_mol  = np.nanpercentile(q_mol[:n_calib], 99)
    th_betti = np.nanpercentile(q_betti[:n_calib], 99)
    th_morse = np.nanpercentile(q_morse[:n_calib], 99)
    th_rtd  = np.nanpercentile(q_rtd[:n_calib], 99)

    eval_ew(q_grav, th_grav, 'EW_Gravity')
    eval_ew(q_mol, th_mol, 'EW_Molecular')
    eval_ew(q_betti, th_betti, 'EW_Betti')
    eval_ew(q_morse, th_morse, 'EW_Morse')
    eval_ew(q_rtd, th_rtd, 'EW_RTD')

    # Panel-aware (z-norm + exceedance)
    p_grav = panel_score(S_grav)
    p_mol  = panel_score(S_mol)
    p_betti = panel_score(S_betti)
    p_morse = panel_score(S_morse)
    p_rtd   = panel_score(S_rtd)

    bt_grav = banktail_score(S_grav)
    bt_mol  = banktail_score(S_mol)
    bt_betti = banktail_score(S_betti)
    bt_morse = banktail_score(S_morse)
    bt_rtd   = banktail_score(S_rtd)

    th_pg = np.nanpercentile(p_grav[:n_calib], 99)
    th_pm = np.nanpercentile(p_mol[:n_calib], 99)
    th_pb = np.nanpercentile(p_betti[:n_calib], 99)
    th_pmo = np.nanpercentile(p_morse[:n_calib], 99)
    th_prtd = np.nanpercentile(p_rtd[:n_calib], 99)

    th_btg = np.nanpercentile(bt_grav[:n_calib], 99)
    th_btm = np.nanpercentile(bt_mol[:n_calib], 99)
    th_btb = np.nanpercentile(bt_betti[:n_calib], 99)
    th_btmo = np.nanpercentile(bt_morse[:n_calib], 99)
    th_btr = np.nanpercentile(bt_rtd[:n_calib], 99)

    eval_ew(p_grav, th_pg, 'EWP_Gravity')
    eval_ew(p_mol, th_pm, 'EWP_Molecular')
    eval_ew(p_betti, th_pb, 'EWP_Betti')
    eval_ew(p_morse, th_pmo, 'EWP_Morse')
    eval_ew(p_rtd, th_prtd, 'EWP_RTD')

    eval_ew(bt_grav, th_btg, 'EWT_Gravity')
    eval_ew(bt_mol, th_btm, 'EWT_Molecular')
    eval_ew(bt_betti, th_btb, 'EWT_Betti')
    eval_ew(bt_morse, th_btmo, 'EWT_Morse')
    eval_ew(bt_rtd, th_btr, 'EWT_RTD')

    # Z-score (Basel cyclical gap, z > 2.0)
    z_grav = zscore_transform(q_grav)
    z_mol  = zscore_transform(q_mol)
    z_betti = zscore_transform(q_betti)
    z_morse = zscore_transform(q_morse)
    z_rtd   = zscore_transform(q_rtd)

    eval_ew(z_grav, 2.0, 'EWZ_Gravity')
    eval_ew(z_mol, 2.0, 'EWZ_Molecular')
    eval_ew(z_betti, 2.0, 'EWZ_Betti')
    eval_ew(z_morse, 2.0, 'EWZ_Morse')
    eval_ew(z_rtd, 2.0, 'EWZ_RTD')

    # ── Phase 3: Fused expanding-window ensembles ──
    print(f"\n  --- Fused expanding-window ensembles ---")
    print(ew_hdr)
    print(f"  {'-' * 90}")

    def cal_q(qs, n_cal):
        """Quantile calibrate against calibration window."""
        ref = qs[:n_cal]
        ref = ref[~np.isnan(ref)]
        ref_sorted = np.sort(ref)
        out = np.full_like(qs, np.nan)
        valid = ~np.isnan(qs)
        out[valid] = np.searchsorted(ref_sorted, qs[valid]) / len(ref_sorted)
        return out

    cg = cal_q(q_grav, n_calib)
    cm = cal_q(q_mol, n_calib)
    cb = cal_q(q_betti, n_calib)
    cmo = cal_q(q_morse, n_calib)
    cr = cal_q(q_rtd, n_calib)

    # Also calibrate panel scores
    cpg = cal_q(p_grav, n_calib)
    cpm = cal_q(p_mol, n_calib)
    cpb = cal_q(p_betti, n_calib)
    cpmo = cal_q(p_morse, n_calib)
    cpr = cal_q(p_rtd, n_calib)
    czr = cal_q(z_rtd, n_calib)

    ctg = cal_q(bt_grav, n_calib)
    ctm = cal_q(bt_mol, n_calib)
    ctb = cal_q(bt_betti, n_calib)
    ctmo = cal_q(bt_morse, n_calib)
    ctr = cal_q(bt_rtd, n_calib)

    fusion_sets_ew = {
        'EWF_G+R':       [cg, cr],
        'EWF_G+B':       [cg, cb],
        'EWF_G+Mo':      [cg, cmo],
        'EWF_G+R+Mo':    [cg, cr, cmo],
        'EWF_G+B+R':     [cg, cb, cr],
        'EWF_G+B+Mo':    [cg, cb, cmo],
        'EWF_G+B+R+Mo':  [cg, cb, cr, cmo],
        'EWF_G+B+M':     [cg, cb, cm],
        'EWF_G+B+M+Mo':  [cg, cb, cm, cmo],
        'EWF_All5':      [cg, cb, cm, cmo, cr],
        'EWF_G+M':       [cg, cm],
        'EWF_R+Mo':      [cr, cmo],
        'EWF_B+R':       [cb, cr],
        'EWF_B+Mo':      [cb, cmo],
        'EWF_B+M':       [cb, cm],
        'EWPF_G+B':      [cpg, cpb],
        'EWPF_G+R':      [cpg, cpr],
        'EWPF_G+B+R':    [cpg, cpb, cpr],
        'EWPF_G+B+Mo':   [cpg, cpb, cpmo],
        'EWPF_G+B+R+Mo': [cpg, cpb, cpr, cpmo],
        'EWPF_G+B+M':    [cpg, cpb, cpm],
        'EWPF_G+B+M+Mo': [cpg, cpb, cpm, cpmo],
        'EWPF_All5':     [cpg, cpb, cpm, cpmo, cpr],
        'EWTF_G+R':      [ctg, ctr],
        'EWTF_G+Mo':     [ctg, ctmo],
        'EWTF_G+R+Mo':   [ctg, ctr, ctmo],
        'EWTF_G+B+R':    [ctg, ctb, ctr],
        'EWTF_G+B+R+Mo': [ctg, ctb, ctr, ctmo],
        'EWTF_All5':     [ctg, ctb, ctm, ctmo, ctr],
    }

    for fname, cal_list in fusion_sets_ew.items():
        fused = np.nanmean(cal_list, axis=0)
        cal_vals = fused[:n_calib]
        cal_vals = cal_vals[~np.isnan(cal_vals)]
        th = np.percentile(cal_vals, 99) if len(cal_vals) > 0 else 0.99
        eval_ew(fused, th, fname)

    print(f"\n  --- Consensus expanding-window ensembles ---")
    print(ew_hdr)
    print(f"  {'-' * 90}")

    consensus_sets = {
        'EWCG_GxMo':      [cg, cmo],
        'EWCG_GxR':       [cg, cr],
        'EWCG_MoxZR':     [cmo, czr],
        'EWCG_GxMoxZR':   [cg, cmo, czr],
        'EWCG_GxRxMo':    [cg, cr, cmo],
        'EWCG_GxBxMo':    [cg, cb, cmo],
        'EWCG_GxBxMoxZR': [cg, cb, cmo, czr],
    }

    for fname, cal_list in consensus_sets.items():
        arr = np.vstack([np.clip(x, 1e-6, 1.0) for x in cal_list])
        fused = np.exp(np.nanmean(np.log(arr), axis=0))
        cal_vals = fused[:n_calib]
        cal_vals = cal_vals[~np.isnan(cal_vals)]
        th = np.percentile(cal_vals, 99) if len(cal_vals) > 0 else 0.99
        eval_ew(fused, th, fname)
