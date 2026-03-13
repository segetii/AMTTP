"""
UDL Classification Benchmark
==============================
Evaluates UDLClassifier on standard multi-class tabular datasets
against baseline classifiers under 5-fold stratified CV.

Datasets (from sklearn / OpenML):
  - Iris (4 features, 3 classes)
  - Wine (13 features, 3 classes)
  - Breast Cancer Wisconsin (30 features, 2 classes)
  - Digits (64 features, 10 classes)
  - Vehicle (18 features, 4 classes)  [OpenML #54]
  - Segment (19 features, 7 classes)  [OpenML #36]

Baselines:
  - Random Forest (200 trees)
  - LightGBM (if available, else XGBoost, else skip)
  - SVM (RBF)
  - kNN (k=5)
  - LDA (raw features, same head as UDL-LDA but without operators)

Metrics:
  - Accuracy (5-fold CV mean ± std)
  - Macro F1 (5-fold CV mean ± std)
  - Cohen's Kappa

Output: results/classification_benchmark.json
"""

import sys, os, json, time, warnings
import numpy as np
from pathlib import Path

warnings.filterwarnings("ignore")

# Ensure udl package is importable
sys.path.insert(0, str(Path(__file__).parent))

from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import accuracy_score, f1_score, cohen_kappa_score
from sklearn.preprocessing import StandardScaler

# ── Baselines ──
from sklearn.ensemble import RandomForestClassifier
from sklearn.svm import SVC
from sklearn.neighbors import KNeighborsClassifier
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.linear_model import LogisticRegression

# ── UDL ──
from udl.classifier import UDLClassifier


# ═══════════════════════════════════════════════════════════════
#  Dataset loaders
# ═══════════════════════════════════════════════════════════════

def load_datasets():
    """Load standard classification datasets."""
    datasets = {}

    # --- sklearn built-ins ---
    from sklearn.datasets import load_iris, load_wine, load_breast_cancer, load_digits

    for name, loader in [
        ("Iris", load_iris),
        ("Wine", load_wine),
        ("BreastCancer", load_breast_cancer),
        ("Digits", load_digits),
    ]:
        d = loader()
        datasets[name] = (d.data, d.target)
        print(f"  {name}: {d.data.shape[0]} samples, {d.data.shape[1]} features, "
              f"{len(np.unique(d.target))} classes")

    # --- OpenML datasets (Vehicle, Segment) ---
    try:
        from sklearn.datasets import fetch_openml
        for name, did in [("Vehicle", 54), ("Segment", 36)]:
            try:
                d = fetch_openml(data_id=did, as_frame=False, parser="auto")
                X = d.data.astype(np.float64)
                # Encode string labels
                from sklearn.preprocessing import LabelEncoder
                le = LabelEncoder()
                y = le.fit_transform(d.target)
                # Remove NaN rows
                mask = ~np.isnan(X).any(axis=1)
                X, y = X[mask], y[mask]
                datasets[name] = (X, y)
                print(f"  {name}: {X.shape[0]} samples, {X.shape[1]} features, "
                      f"{len(np.unique(y))} classes")
            except Exception as e:
                print(f"  {name}: SKIP ({e})")
    except ImportError:
        pass

    return datasets


# ═══════════════════════════════════════════════════════════════
#  Build methods
# ═══════════════════════════════════════════════════════════════

def build_methods():
    """Return dict of method_name -> constructor callable."""
    methods = {}

    # UDL variants — core 6 operators
    methods["UDL-LDA"] = lambda: UDLClassifier(head="lda")
    methods["UDL-QDA"] = lambda: UDLClassifier(head="qda")
    methods["UDL-Logistic"] = lambda: UDLClassifier(head="logistic")
    methods["UDL-RF"] = lambda: UDLClassifier(head="rf")

    # UDL variants — extended 14 operators
    methods["UDL-Ext-QDA"] = lambda: UDLClassifier(head="qda", extended_operators=True)
    methods["UDL-Ext-RF"] = lambda: UDLClassifier(head="rf", extended_operators=True)

    # UDL variants — core + SubspaceScan
    methods["UDL-SS-QDA"] = lambda: UDLClassifier(head="qda", use_subspace_scan=True)
    methods["UDL-SS-RF"] = lambda: UDLClassifier(head="rf", use_subspace_scan=True)

    # UDL variants — extended + SubspaceScan (full pipeline)
    methods["UDL-Full-QDA"] = lambda: UDLClassifier(head="qda", extended_operators=True, use_subspace_scan=True)
    methods["UDL-Full-RF"] = lambda: UDLClassifier(head="rf", extended_operators=True, use_subspace_scan=True)

    # Baselines (raw features)
    methods["RF-200"] = lambda: RandomForestClassifier(
        n_estimators=200, random_state=42, n_jobs=-1)
    methods["SVM-RBF"] = lambda: SVC(kernel="rbf", probability=True,
                                      gamma="scale", random_state=42)
    methods["kNN-5"] = lambda: KNeighborsClassifier(n_neighbors=5)
    methods["LDA-raw"] = lambda: LinearDiscriminantAnalysis(solver="svd")
    methods["Logistic-raw"] = lambda: LogisticRegression(
        max_iter=2000, solver="lbfgs", multi_class="multinomial",
        random_state=42)

    # LightGBM / XGBoost
    try:
        from lightgbm import LGBMClassifier
        methods["LightGBM"] = lambda: LGBMClassifier(
            n_estimators=200, max_depth=6, random_state=42,
            verbose=-1, n_jobs=-1)
    except ImportError:
        try:
            from xgboost import XGBClassifier
            methods["XGBoost"] = lambda: XGBClassifier(
                n_estimators=200, max_depth=6, random_state=42,
                use_label_encoder=False, eval_metric="mlogloss",
                verbosity=0, n_jobs=-1)
        except ImportError:
            pass

    return methods


# ═══════════════════════════════════════════════════════════════
#  Cross-validation loop
# ═══════════════════════════════════════════════════════════════

def run_benchmark():
    print("=" * 60)
    print("UDL Classification Benchmark")
    print("=" * 60)

    print("\nLoading datasets...")
    datasets = load_datasets()
    methods = build_methods()

    n_folds = 5
    results = {}

    for ds_name, (X, y) in datasets.items():
        print(f"\n{'─' * 50}")
        print(f"Dataset: {ds_name}  ({X.shape[0]}×{X.shape[1]}, "
              f"{len(np.unique(y))} classes)")
        print(f"{'─' * 50}")

        results[ds_name] = {}
        skf = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=42)

        for m_name, m_factory in methods.items():
            accs, f1s, kappas = [], [], []
            t0 = time.time()
            failed = False

            for fold_idx, (train_idx, test_idx) in enumerate(skf.split(X, y)):
                X_train, X_test = X[train_idx], X[test_idx]
                y_train, y_test = y[train_idx], y[test_idx]

                try:
                    clf = m_factory()

                    # For non-UDL methods, standardize raw features
                    if not m_name.startswith("UDL"):
                        sc = StandardScaler()
                        X_tr = sc.fit_transform(X_train)
                        X_te = sc.transform(X_test)
                    else:
                        X_tr, X_te = X_train, X_test

                    clf.fit(X_tr, y_train)
                    y_pred = clf.predict(X_te)
                    accs.append(accuracy_score(y_test, y_pred))
                    f1s.append(f1_score(y_test, y_pred, average="macro",
                                        zero_division=0))
                    kappas.append(cohen_kappa_score(y_test, y_pred))
                except Exception as e:
                    print(f"  {m_name} fold {fold_idx}: ERROR - {e}")
                    failed = True
                    break

            dt = time.time() - t0
            if failed:
                print(f"  {m_name:20s}  FAILED")
                results[ds_name][m_name] = {"status": "failed"}
                continue

            acc_m, acc_s = np.mean(accs), np.std(accs)
            f1_m, f1_s = np.mean(f1s), np.std(f1s)
            kappa_m = np.mean(kappas)

            results[ds_name][m_name] = {
                "accuracy_mean": round(acc_m, 4),
                "accuracy_std": round(acc_s, 4),
                "f1_macro_mean": round(f1_m, 4),
                "f1_macro_std": round(f1_s, 4),
                "kappa_mean": round(kappa_m, 4),
                "time_s": round(dt, 2),
                "folds": n_folds,
            }
            print(f"  {m_name:20s}  acc={acc_m:.4f}±{acc_s:.4f}  "
                  f"F1={f1_m:.4f}±{f1_s:.4f}  κ={kappa_m:.4f}  "
                  f"({dt:.1f}s)")

    # ── Save results ──
    out_dir = Path(__file__).parent / "results"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "classification_benchmark.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved → {out_path}")

    # ── Summary table ──
    print("\n" + "=" * 80)
    print("SUMMARY: Mean accuracy across all datasets")
    print("=" * 80)

    method_means = {}
    for m_name in methods:
        vals = []
        for ds_name in datasets:
            r = results[ds_name].get(m_name, {})
            if "accuracy_mean" in r:
                vals.append(r["accuracy_mean"])
        if vals:
            method_means[m_name] = np.mean(vals)

    for m_name, m_acc in sorted(method_means.items(),
                                 key=lambda x: -x[1]):
        marker = "★" if m_name.startswith("UDL") else " "
        print(f"  {marker} {m_name:20s}  mAcc = {m_acc:.4f}")

    return results


if __name__ == "__main__":
    run_benchmark()
