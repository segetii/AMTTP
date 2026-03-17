"""Benchmark new UDL classifier variants (extended ops + SubspaceScan)."""
import sys, os, time, warnings, traceback, json
import numpy as np
warnings.filterwarnings('ignore')
sys.path.insert(0, os.path.dirname(__file__))

from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import accuracy_score, f1_score
from sklearn.preprocessing import LabelEncoder
from sklearn.datasets import load_iris, load_wine, load_breast_cancer, load_digits
from udl.classifier import UDLClassifier

# Datasets
datasets = {}
for name, loader in [
    ('Iris', load_iris), ('Wine', load_wine),
    ('BreastCancer', load_breast_cancer), ('Digits', load_digits),
]:
    d = loader()
    datasets[name] = (d.data, d.target)
    print(f"{name}: {d.data.shape}, {len(np.unique(d.target))} classes")

# OpenML datasets
try:
    from sklearn.datasets import fetch_openml
    for name, did in [("Vehicle", 54), ("Segment", 36)]:
        try:
            d = fetch_openml(data_id=did, as_frame=False, parser="auto")
            X = d.data.astype(np.float64)
            le = LabelEncoder()
            y = le.fit_transform(d.target)
            mask = ~np.isnan(X).any(axis=1)
            X, y = X[mask], y[mask]
            datasets[name] = (X, y)
            print(f"{name}: {X.shape}, {len(np.unique(y))} classes")
        except Exception as e:
            print(f"{name}: SKIP ({e})")
except ImportError:
    pass

# New UDL variants to test
variants = {
    # Core 6 ops (baseline for comparison)
    'UDL-QDA':      lambda: UDLClassifier(head='qda'),
    'UDL-RF':       lambda: UDLClassifier(head='rf'),
    # Extended 14 ops
    'UDL-Ext-QDA':  lambda: UDLClassifier(head='qda', extended_operators=True),
    'UDL-Ext-RF':   lambda: UDLClassifier(head='rf', extended_operators=True),
    # Core + SubspaceScan
    'UDL-SS-QDA':   lambda: UDLClassifier(head='qda', use_subspace_scan=True),
    'UDL-SS-RF':    lambda: UDLClassifier(head='rf', use_subspace_scan=True),
    # Extended + SubspaceScan (full pipeline)
    'UDL-Full-QDA': lambda: UDLClassifier(head='qda', extended_operators=True, use_subspace_scan=True),
    'UDL-Full-RF':  lambda: UDLClassifier(head='rf', extended_operators=True, use_subspace_scan=True),
}

n_folds = 5
results = {}
for ds_name, (X, y) in datasets.items():
    nc = len(np.unique(y))
    print(f"\n{'='*60}")
    print(f"Dataset: {ds_name}  ({X.shape[0]}x{X.shape[1]}, {nc} classes)")
    print(f"{'='*60}")
    results[ds_name] = {}
    skf = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=42)

    for m_name, m_factory in variants.items():
        accs, f1s = [], []
        t0 = time.time()
        try:
            for fold_idx, (tr_i, te_i) in enumerate(skf.split(X, y)):
                clf = m_factory()
                clf.fit(X[tr_i], y[tr_i])
                y_pred = clf.predict(X[te_i])
                accs.append(accuracy_score(y[te_i], y_pred))
                f1s.append(f1_score(y[te_i], y_pred, average='macro', zero_division=0))
            dt = time.time() - t0
            acc_m, acc_s = np.mean(accs), np.std(accs)
            f1_m = np.mean(f1s)
            results[ds_name][m_name] = {
                'accuracy_mean': round(acc_m, 4),
                'accuracy_std': round(acc_s, 4),
                'f1_macro_mean': round(f1_m, 4),
                'time_s': round(dt, 1),
            }
            print(f"  {m_name:20s} acc={acc_m:.4f}+/-{acc_s:.4f}  F1={f1_m:.4f}  ({dt:.1f}s)")
        except Exception as e:
            dt = time.time() - t0
            print(f"  {m_name:20s} FAILED: {e} ({dt:.1f}s)")
            traceback.print_exc()
            results[ds_name][m_name] = {'status': 'failed', 'error': str(e)}

# Save results
os.makedirs('results', exist_ok=True)
with open('results/classification_new_variants.json', 'w') as f:
    json.dump(results, f, indent=2)
print(f"\nResults saved to results/classification_new_variants.json")

# Summary
print(f"\n{'='*80}")
print("SUMMARY: Mean accuracy across datasets")
print(f"{'='*80}")
for m_name in variants:
    vals = []
    for ds_name in datasets:
        r = results.get(ds_name, {}).get(m_name, {})
        if 'accuracy_mean' in r:
            vals.append(r['accuracy_mean'])
    if vals:
        marker = "★" if 'Full' in m_name or 'Ext' in m_name or 'SS' in m_name else " "
        print(f"  {marker} {m_name:20s}  mAcc = {np.mean(vals):.4f}  ({len(vals)} datasets)")

print("\nDONE")
