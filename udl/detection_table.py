"""
UDL Detection Table — Caught / Missed / False Alarm Analysis
===============================================================
For each method and each dataset, computes:
  - Caught:      TP / total anomalies  (true positives)
  - Missed:      FN / total anomalies  (false negatives = anomalies we failed to flag)
  - False Alarm: FP / total normals    (false positives = normals wrongly flagged)

Threshold is chosen at optimal F1 (best balance of precision/recall).
"""

import numpy as np
import sys, os, copy, warnings, time
warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sklearn.model_selection import train_test_split
from sklearn.metrics import precision_recall_curve, roc_auc_score
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor, NearestNeighbors
from sklearn.svm import OneClassSVM
from sklearn.covariance import EllipticEnvelope
from sklearn.preprocessing import StandardScaler

from udl.spectra import (
    StatisticalSpectrum, ChaosSpectrum, SpectralSpectrum,
    GeometricSpectrum, ExponentialSpectrum,
    ReconstructionSpectrum, RankOrderSpectrum,
)
from udl.experimental_spectra import (
    FourierBasisSpectrum, BSplineBasisSpectrum,
    WaveletBasisSpectrum, LegendreBasisSpectrum,
    PolarSpectrum, RadarPolygonSpectrum,
    PhaseCurveSpectrum, GramEigenSpectrum,
)
from udl.pipeline import UDLPipeline
from udl.datasets import (
    make_synthetic, make_mimic_anomalies,
    load_mammography, load_shuttle, load_pendigits,
)


# ═══════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════

def optimal_threshold(y_true, scores):
    """Find threshold that maximises F1."""
    prec, rec, thresholds = precision_recall_curve(y_true, scores)
    f1s = 2 * prec * rec / (prec + rec + 1e-10)
    best_idx = np.argmax(f1s)
    if best_idx < len(thresholds):
        return thresholds[best_idx]
    return thresholds[-1] if len(thresholds) > 0 else 0.5


def count_detections(y_true, scores):
    """Return TP, FN, FP, TN counts at optimal-F1 threshold."""
    thresh = optimal_threshold(y_true, scores)
    y_pred = (scores >= thresh).astype(int)

    tp = int(((y_pred == 1) & (y_true == 1)).sum())
    fn = int(((y_pred == 0) & (y_true == 1)).sum())
    fp = int(((y_pred == 1) & (y_true == 0)).sum())
    tn = int(((y_pred == 0) & (y_true == 0)).sum())

    total_anomalies = int(y_true.sum())
    total_normals = int((y_true == 0).sum())
    auc = roc_auc_score(y_true, scores)

    return {
        "tp": tp, "fn": fn, "fp": fp, "tn": tn,
        "total_anom": total_anomalies,
        "total_norm": total_normals,
        "auc": auc,
    }


# ═══════════════════════════════════════════════════════════════
#  Baseline runners (return scores)
# ═══════════════════════════════════════════════════════════════

def run_iforest(X_tr_n, X_te, y_te):
    clf = IsolationForest(n_estimators=200, contamination='auto', random_state=42, n_jobs=-1)
    clf.fit(X_tr_n); return -clf.decision_function(X_te)

def run_lof(X_tr_n, X_te, y_te):
    clf = LocalOutlierFactor(n_neighbors=20, contamination='auto', novelty=True)
    clf.fit(X_tr_n); return -clf.decision_function(X_te)

def run_ocsvm(X_tr_n, X_te, y_te):
    X_fit = X_tr_n
    if len(X_tr_n) > 5000:
        rng = np.random.RandomState(42)
        X_fit = X_tr_n[rng.choice(len(X_tr_n), 5000, replace=False)]
    clf = OneClassSVM(kernel='rbf', gamma='scale', nu=0.05)
    clf.fit(X_fit); return -clf.decision_function(X_te)

def run_elliptic(X_tr_n, X_te, y_te):
    try:
        clf = EllipticEnvelope(contamination=0.01, random_state=42, support_fraction=0.99)
        clf.fit(X_tr_n); return -clf.decision_function(X_te)
    except: return None

def run_knn(X_tr_n, X_te, y_te):
    nn = NearestNeighbors(n_neighbors=10, n_jobs=-1)
    nn.fit(X_tr_n)
    distances, _ = nn.kneighbors(X_te)
    return distances.mean(axis=1)


def run_udl_config(ops, X_train, X_test, y_train, score_method='v1'):
    try:
        pipe = UDLPipeline(operators=copy.deepcopy(ops), centroid_method='auto',
                           projection_method='fisher', score_method=score_method)
        pipe.fit(X_train, y_train)
        return pipe.score(X_test)
    except Exception as e:
        print(f"    [ERROR] {e}")
        return None


# ═══════════════════════════════════════════════════════════════
#  All Method Configs
# ═══════════════════════════════════════════════════════════════

def build_all_configs():
    baselines = {
        "Isolation Forest": ("baseline", run_iforest),
        "LOF":              ("baseline", run_lof),
        "One-Class SVM":    ("baseline", run_ocsvm),
        "Elliptic Envelope":("baseline", run_elliptic),
        "KNN Distance":     ("baseline", run_knn),
    }

    udl_configs = {
        "UDL-5laws": ("udl", [
            ("statistical", StatisticalSpectrum()), ("chaos", ChaosSpectrum()),
            ("spectral", SpectralSpectrum()), ("geometric", GeometricSpectrum()),
            ("exponential", ExponentialSpectrum(alpha=1.0)),
        ], 'v1'),
        "UDL-6laws-v2": ("udl", [
            ("statistical", StatisticalSpectrum()), ("chaos", ChaosSpectrum()),
            ("spectral", SpectralSpectrum()), ("geometric", GeometricSpectrum()),
            ("recon", ReconstructionSpectrum()), ("rank", RankOrderSpectrum()),
        ], 'v1'),
        "UDL-CombinedA": ("udl", [
            ("A1_fourier", FourierBasisSpectrum(n_coeffs=8)),
            ("A2_bspline", BSplineBasisSpectrum(n_basis=6)),
            ("A3_wavelet", WaveletBasisSpectrum(max_levels=4)),
            ("A4_legendre", LegendreBasisSpectrum(n_degree=6)),
        ], 'v1'),
        "UDL-CombinedB": ("udl", [
            ("B1_polar", PolarSpectrum()), ("B2_radar", RadarPolygonSpectrum()),
            ("B3_phase", PhaseCurveSpectrum()), ("B4_gram", GramEigenSpectrum()),
        ], 'v1'),
        "UDL-CombA+Recon": ("udl", [
            ("A1_fourier", FourierBasisSpectrum(n_coeffs=8)),
            ("A2_bspline", BSplineBasisSpectrum(n_basis=6)),
            ("A3_wavelet", WaveletBasisSpectrum(max_levels=4)),
            ("A4_legendre", LegendreBasisSpectrum(n_degree=6)),
            ("recon", ReconstructionSpectrum()), ("rank", RankOrderSpectrum()),
        ], 'v1'),
        "UDL-CombB+Recon": ("udl", [
            ("B1_polar", PolarSpectrum()), ("B2_radar", RadarPolygonSpectrum()),
            ("B3_phase", PhaseCurveSpectrum()), ("B4_gram", GramEigenSpectrum()),
            ("recon", ReconstructionSpectrum()), ("rank", RankOrderSpectrum()),
        ], 'v1'),
        "UDL-v3e-CombB+R": ("udl", [
            ("B1_polar", PolarSpectrum()), ("B2_radar", RadarPolygonSpectrum()),
            ("B3_phase", PhaseCurveSpectrum()), ("B4_gram", GramEigenSpectrum()),
            ("recon", ReconstructionSpectrum()), ("rank", RankOrderSpectrum()),
        ], 'v3e'),
        "UDL-v3e-CombA+R": ("udl", [
            ("A1_fourier", FourierBasisSpectrum(n_coeffs=8)),
            ("A2_bspline", BSplineBasisSpectrum(n_basis=6)),
            ("A3_wavelet", WaveletBasisSpectrum(max_levels=4)),
            ("A4_legendre", LegendreBasisSpectrum(n_degree=6)),
            ("recon", ReconstructionSpectrum()), ("rank", RankOrderSpectrum()),
        ], 'v3e'),
        "UDL-B3phase": ("udl", [("B3_phase", PhaseCurveSpectrum())], 'v1'),
        "UDL-A3wavelet": ("udl", [("A3_wavelet", WaveletBasisSpectrum(max_levels=4))], 'v1'),
    }

    return baselines, udl_configs


# ═══════════════════════════════════════════════════════════════
#  Load Datasets
# ═══════════════════════════════════════════════════════════════

def load_datasets():
    ds = {}
    ds["Synthetic"] = make_synthetic()
    ds["Mimic"] = make_mimic_anomalies()
    try: ds["Mammography"] = load_mammography()
    except: pass
    try:
        X, y = load_shuttle()
        rng = np.random.RandomState(42)
        idx = rng.choice(len(y), min(len(y), 10000), replace=False)
        ds["Shuttle"] = (X[idx], y[idx])
    except: pass
    try: ds["Pendigits"] = load_pendigits()
    except: pass
    return ds


# ═══════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════

def main():
    print("=" * 100)
    print("  DETECTION TABLE: Caught / Missed / False Alarm  (at optimal-F1 threshold)")
    print("=" * 100)
    print()

    datasets = load_datasets()
    baselines, udl_configs = build_all_configs()
    all_method_names = list(baselines.keys()) + list(udl_configs.keys())

    # results[dataset][method] = {tp, fn, fp, tn, total_anom, total_norm, auc}
    results = {}

    for ds_name, (X, y) in datasets.items():
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.3, stratify=y, random_state=42
        )
        X_train_normal = X_train[y_train == 0]
        scaler = StandardScaler()
        scaler.fit(X_train_normal)
        X_train_normal_scaled = scaler.transform(X_train_normal)
        X_test_scaled = scaler.transform(X_test)

        n_anom_test = int(y_test.sum())
        n_norm_test = int((y_test == 0).sum())
        print(f"  Processing {ds_name}  (test: {n_norm_test} normal + {n_anom_test} anomalies = {len(y_test)} total)")

        results[ds_name] = {}

        # Baselines
        for mname, (mtype, fn) in baselines.items():
            scores = fn(X_train_normal_scaled, X_test_scaled, y_test)
            if scores is not None:
                results[ds_name][mname] = count_detections(y_test, scores)
            else:
                results[ds_name][mname] = {"tp":0,"fn":n_anom_test,"fp":0,"tn":n_norm_test,
                                           "total_anom":n_anom_test,"total_norm":n_norm_test,"auc":0}

        # UDL
        for mname, (mtype, ops, sm) in udl_configs.items():
            scores = run_udl_config(ops, X_train, X_test, y_train, score_method=sm)
            if scores is not None:
                results[ds_name][mname] = count_detections(y_test, scores)
            else:
                results[ds_name][mname] = {"tp":0,"fn":n_anom_test,"fp":0,"tn":n_norm_test,
                                           "total_anom":n_anom_test,"total_norm":n_norm_test,"auc":0}

    # ═══════════════════════════════════════════════════════════
    #  Print Tables — one per dataset
    # ═══════════════════════════════════════════════════════════

    output_lines = []
    def out(msg=""):
        print(msg)
        output_lines.append(msg)

    out()
    out("=" * 120)
    out("  COMPLETE DETECTION TABLE")
    out("  Threshold: optimal F1 per method per dataset")
    out("=" * 120)

    for ds_name in datasets:
        ds_res = results[ds_name]
        sample = list(ds_res.values())[0]
        total_a = sample["total_anom"]
        total_n = sample["total_norm"]

        out()
        out("=" * 120)
        out(f"  DATASET: {ds_name.upper()}")
        out(f"  Test Set: {total_n} Normal  +  {total_a} Anomalies  =  {total_n + total_a} Total")
        out("=" * 120)
        out(f"  {'Method':<22s} │ {'Caught':>12s} │ {'Missed':>12s} │ {'False Alarm':>16s} │ {'AUC':>7s} │ {'Catch%':>7s} │ {'FA%':>7s}")
        out("  " + "─" * 22 + "─┼─" + "─" * 12 + "─┼─" + "─" * 12 + "─┼─" + "─" * 16 + "─┼─" + "─" * 7 + "─┼─" + "─" * 7 + "─┼─" + "─" * 7)

        # Sort methods by catch rate desc, then false alarm asc
        sorted_methods = sorted(ds_res.keys(),
                                key=lambda m: (ds_res[m]["tp"] / max(ds_res[m]["total_anom"], 1),
                                               -ds_res[m]["fp"] / max(ds_res[m]["total_norm"], 1)),
                                reverse=True)

        for mname in sorted_methods:
            r = ds_res[mname]
            tp, fn, fp = r["tp"], r["fn"], r["fp"]
            ta, tn = r["total_anom"], r["total_norm"]
            auc = r["auc"]
            catch_pct = 100.0 * tp / max(ta, 1)
            fa_pct = 100.0 * fp / max(tn, 1)

            is_udl = mname.startswith("UDL")
            marker = "★" if mname == "UDL-v3e-CombB+R" else ("▸" if is_udl else " ")

            caught_str = f"{tp:>4d} / {ta:<4d}"
            missed_str = f"{fn:>4d} / {ta:<4d}"
            fa_str     = f"{fp:>6d} / {tn:<6d}"

            out(f"{marker} {mname:<21s} │ {caught_str:>12s} │ {missed_str:>12s} │ {fa_str:>16s} │ {auc:>7.4f} │ {catch_pct:>6.1f}% │ {fa_pct:>6.1f}%")

    # ═══════════════════════════════════════════════════════
    #  Cross-Dataset Summary
    # ═══════════════════════════════════════════════════════

    out()
    out("=" * 120)
    out("  CROSS-DATASET SUMMARY: Total Caught / Total Missed / Total False Alarm (all datasets combined)")
    out("=" * 120)

    ds_names_list = list(datasets.keys())
    all_methods_seen = set()
    for ds in ds_names_list:
        all_methods_seen.update(results[ds].keys())
    all_methods_sorted = sorted(all_methods_seen)

    # Header
    out(f"  {'Method':<22s} │ {'Total Caught':>14s} │ {'Total Missed':>14s} │ {'Total FA':>14s} │ {'Catch%':>7s} │ {'FA%':>7s} │ {'Mean AUC':>9s}")
    out("  " + "─" * 22 + "─┼─" + "─" * 14 + "─┼─" + "─" * 14 + "─┼─" + "─" * 14 + "─┼─" + "─" * 7 + "─┼─" + "─" * 7 + "─┼─" + "─" * 9)

    summaries = []
    for mname in all_methods_sorted:
        sum_tp = sum_fn = sum_fp = sum_ta = sum_tn = 0
        aucs = []
        for ds in ds_names_list:
            if mname in results[ds]:
                r = results[ds][mname]
                sum_tp += r["tp"]; sum_fn += r["fn"]; sum_fp += r["fp"]
                sum_ta += r["total_anom"]; sum_tn += r["total_norm"]
                aucs.append(r["auc"])
        mean_auc = np.mean(aucs) if aucs else 0
        catch_pct = 100.0 * sum_tp / max(sum_ta, 1)
        fa_pct = 100.0 * sum_fp / max(sum_tn, 1)
        summaries.append((mname, sum_tp, sum_fn, sum_fp, sum_ta, sum_tn, catch_pct, fa_pct, mean_auc))

    summaries.sort(key=lambda x: (x[6], -x[7]), reverse=True)

    for (mname, stp, sfn, sfp, sta, stn, cp, fap, mauc) in summaries:
        marker = "★" if mname == "UDL-v3e-CombB+R" else ("▸" if mname.startswith("UDL") else " ")
        out(f"{marker} {mname:<21s} │ {stp:>5d} / {sta:<5d} │ {sfn:>5d} / {sta:<5d} │ {sfp:>5d} / {stn:<5d} │ {cp:>6.1f}% │ {fap:>6.1f}% │ {mauc:>9.4f}")

    out()
    out("=" * 120)
    out("  TABLE COMPLETE")
    out("=" * 120)

    # Save to file
    outpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "detection_table.txt")
    with open(outpath, "w", encoding="utf-8") as f:
        f.write("\n".join(output_lines))
    print(f"\n  Saved to: {outpath}")

    return results


if __name__ == "__main__":
    main()
