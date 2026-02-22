"""
Energy vs SOTA Benchmark — Detection Table with Caught/Missed Ratios
====================================================================
Compares UDL Energy scoring against LOF, IForest, KNN, OCSVM, 
Elliptic Envelope, and standard UDL QDA on multiple datasets.

Reports: Total anomalies, Caught, Missed, Caught%, AUC
"""
import numpy as np
import sys, os, warnings, copy
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, f1_score
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sklearn.svm import OneClassSVM
from sklearn.covariance import EllipticEnvelope
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler

from udl.spectra import (
    StatisticalSpectrum, GeometricSpectrum,
    ReconstructionSpectrum, RankOrderSpectrum,
)
from udl.pipeline import UDLPipeline
from udl.datasets import load_mammography, load_shuttle


def optimal_f1_threshold(y_true, scores):
    """Find threshold that maximises F1."""
    thresholds = np.percentile(scores, np.arange(80, 100, 0.5))
    best_f1, best_t = 0, np.median(scores)
    for t in thresholds:
        preds = (scores >= t).astype(int)
        f1 = f1_score(y_true, preds, zero_division=0)
        if f1 > best_f1:
            best_f1 = f1
            best_t = t
    return best_t, best_f1


def count_detections(y_true, scores):
    """Get TP/FN/FP/TN at optimal F1 threshold."""
    t, f1 = optimal_f1_threshold(y_true, scores)
    preds = (scores >= t).astype(int)
    tp = int(((preds == 1) & (y_true == 1)).sum())
    fn = int(((preds == 0) & (y_true == 1)).sum())
    fp = int(((preds == 1) & (y_true == 0)).sum())
    tn = int(((preds == 0) & (y_true == 0)).sum())
    return tp, fn, fp, tn, f1


# ── Load datasets ──
datasets = {}
try:
    datasets["mammography"] = load_mammography()
except Exception as e:
    print(f"SKIP mammography: {e}")
try:
    X_s, y_s = load_shuttle()
    rng = np.random.RandomState(42)
    idx = rng.choice(len(y_s), min(len(y_s), 10000), replace=False)
    datasets["shuttle"] = (X_s[idx], y_s[idx])
except Exception as e:
    print(f"SKIP shuttle: {e}")


# ── Results storage ──
all_results = []

for ds_name, (X, y) in datasets.items():
    print(f"\n{'='*80}")
    print(f" DATASET: {ds_name}")
    print(f" Samples: {len(y)}, Features: {X.shape[1]}, "
          f"Anomalies: {y.sum()}/{len(y)} ({100*y.mean():.1f}%)")
    print(f"{'='*80}")

    # Train/test split
    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.3, stratify=y, random_state=42
    )
    X_tr_normal = X_tr[y_tr == 0]

    # Standardise (fit on normal training only)
    scaler = StandardScaler()
    scaler.fit(X_tr_normal)
    X_tr_n_s = scaler.transform(X_tr_normal)
    X_te_s = scaler.transform(X_te)

    n_anomalies_test = int(y_te.sum())

    methods = {}

    # ── Baselines ──
    print("\n  Running baselines...")

    # 1. LOF
    try:
        lof = LocalOutlierFactor(n_neighbors=20, novelty=True, contamination='auto')
        lof.fit(X_tr_n_s)
        methods["LOF"] = -lof.decision_function(X_te_s)
    except:
        pass

    # 2. Isolation Forest
    try:
        ifo = IsolationForest(n_estimators=200, contamination='auto', random_state=42)
        ifo.fit(X_tr_n_s)
        methods["IForest"] = -ifo.decision_function(X_te_s)
    except:
        pass

    # 3. KNN
    try:
        knn = NearestNeighbors(n_neighbors=10)
        knn.fit(X_tr_n_s)
        dists, _ = knn.kneighbors(X_te_s)
        methods["KNN"] = dists.mean(axis=1)
    except:
        pass

    # 4. OCSVM
    try:
        n_fit = min(len(X_tr_n_s), 5000)
        rng = np.random.RandomState(42)
        idx_fit = rng.choice(len(X_tr_n_s), n_fit, replace=False)
        ocsvm = OneClassSVM(kernel='rbf', gamma='scale', nu=0.05)
        ocsvm.fit(X_tr_n_s[idx_fit])
        methods["OCSVM"] = -ocsvm.decision_function(X_te_s)
    except:
        pass

    # 5. Elliptic Envelope
    try:
        ee = EllipticEnvelope(contamination=0.01, random_state=42, support_fraction=0.99)
        ee.fit(X_tr_n_s)
        methods["Elliptic"] = -ee.decision_function(X_te_s)
    except:
        pass

    # ── UDL Methods ──
    print("  Running UDL variants...")

    # 6. UDL QDA (auto operators)
    try:
        pipe_qda = UDLPipeline(operators='auto', centroid_method='geometric_median')
        pipe_qda.fit(X_tr, y_tr)
        methods["UDL-QDA"] = pipe_qda.score(X_te)
    except Exception as e:
        print(f"    UDL-QDA failed: {e}")

    # 7. UDL Energy
    try:
        ops_e = [
            ('stat', StatisticalSpectrum()),
            ('geom', GeometricSpectrum()),
            ('rank', RankOrderSpectrum()),
        ]
        pipe_e = UDLPipeline(
            operators=ops_e,
            centroid_method='geometric_median',
            energy_score=True, energy_alpha=1.0, energy_gamma=0.01,
        )
        pipe_e.fit(X_tr, y_tr)
        methods["UDL-Energy"] = pipe_e.energy_scores(X_te)
    except Exception as e:
        print(f"    UDL-Energy failed: {e}")

    # 8. UDL Fused (QDA + Energy)
    try:
        ops_f = [
            ('stat', StatisticalSpectrum()),
            ('geom', GeometricSpectrum()),
            ('rank', RankOrderSpectrum()),
        ]
        pipe_f = UDLPipeline(
            operators=ops_f,
            centroid_method='geometric_median',
            energy_score=True, energy_alpha=1.0, energy_gamma=0.01,
        )
        pipe_f.fit(X_tr, y_tr)
        q = pipe_f.score(X_te)
        e = pipe_f.energy_scores(X_te)
        q_n = (q - q.min()) / (q.max() - q.min() + 1e-10)
        e_n = (e - e.min()) / (e.max() - e.min() + 1e-10)
        methods["UDL-Fused"] = 0.5 * q_n + 0.5 * e_n
    except Exception as e:
        print(f"    UDL-Fused failed: {e}")

    # 9. UDL Full Stack QDA
    try:
        pipe_full = UDLPipeline(operators=None, centroid_method='geometric_median')
        pipe_full.fit(X_tr, y_tr)
        methods["UDL-Full"] = pipe_full.score(X_te)
    except Exception as e:
        print(f"    UDL-Full failed: {e}")

    # ── Compute results ──
    print(f"\n  {'Method':<16s} {'AUC':>6s} {'Total':>6s} {'Caught':>7s} "
          f"{'Missed':>7s} {'FP':>5s} {'Caught%':>8s} {'F1':>6s}")
    print(f"  {'-'*70}")

    for mname, scores in methods.items():
        try:
            auc = roc_auc_score(y_te, scores)
        except:
            auc = 0.0
        tp, fn, fp, tn, f1 = count_detections(y_te, scores)
        caught_pct = 100.0 * tp / max(n_anomalies_test, 1)
        print(f"  {mname:<16s} {auc:6.4f} {n_anomalies_test:6d} {tp:7d} "
              f"{fn:7d} {fp:5d} {caught_pct:7.1f}% {f1:6.4f}")
        all_results.append({
            'dataset': ds_name, 'method': mname,
            'auc': auc, 'total': n_anomalies_test,
            'caught': tp, 'missed': fn, 'fp': fp, 'f1': f1,
            'caught_pct': caught_pct,
        })


# ── Grand Summary ──
print(f"\n\n{'='*85}")
print(f" GRAND SUMMARY — Anomaly Detection: Caught / Missed")
print(f"{'='*85}")

ds_names = sorted(set(r['dataset'] for r in all_results))
method_names = []
for r in all_results:
    if r['method'] not in method_names:
        method_names.append(r['method'])

# Header
hdr = f"  {'Method':<16s}"
for ds in ds_names:
    hdr += f" | {ds:>20s}"
hdr += f" | {'Mean AUC':>9s}"
print(hdr)
print(f"  {'-' * (16 + (23 * len(ds_names)) + 14)}")

for mname in method_names:
    row = f"  {mname:<16s}"
    aucs = []
    for ds in ds_names:
        matches = [r for r in all_results if r['dataset'] == ds and r['method'] == mname]
        if matches:
            r = matches[0]
            cell = f"{r['caught']}/{r['total']} ({r['caught_pct']:.0f}%)"
            row += f" | {cell:>20s}"
            aucs.append(r['auc'])
        else:
            row += f" | {'—':>20s}"
    mean_auc = np.mean(aucs) if aucs else 0
    row += f" | {mean_auc:9.4f}"
    print(row)

print(f"\n  AUC Breakdown:")
print(f"  {'Method':<16s}", end="")
for ds in ds_names:
    print(f" | {ds:>10s}", end="")
print(f" | {'Mean':>6s}")
print(f"  {'-' * (16 + (13 * len(ds_names)) + 10)}")
for mname in method_names:
    print(f"  {mname:<16s}", end="")
    aucs = []
    for ds in ds_names:
        matches = [r for r in all_results if r['dataset'] == ds and r['method'] == mname]
        if matches:
            print(f" | {matches[0]['auc']:10.4f}", end="")
            aucs.append(matches[0]['auc'])
        else:
            print(f" | {'—':>10s}", end="")
    mean_auc = np.mean(aucs) if aucs else 0
    print(f" | {mean_auc:6.4f}")

print(f"{'='*85}")
