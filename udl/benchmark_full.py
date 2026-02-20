"""
UDL Full Benchmark — Synthetic + Real-World Cross-Domain Validation
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from sklearn.metrics import roc_auc_score, f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split

from udl import UDLPipeline, load_dataset

np.random.seed(42)

def benchmark(name, X, y):
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.3, stratify=y, random_state=42
    )
    pipe = UDLPipeline(centroid_method="auto", projection_method="fisher",
                       exp_alpha=1.0, score_weights=(0.7, 0.3))
    pipe.fit(X_train, y_train)
    scores = pipe.score(X_test)
    labels = pipe.predict(X_test)
    auc = roc_auc_score(y_test, scores)
    f1 = f1_score(y_test, labels, zero_division=0)
    prec = precision_score(y_test, labels, zero_division=0)
    rec = recall_score(y_test, labels, zero_division=0)
    diag = pipe.get_diagnostics()
    print(f"  {name:<20} N={len(X):>6}  d={X.shape[1]:>3}  anom={y.mean():.1%}"
          f"  AUC={auc:.4f}  F1={f1:.4f}  P={prec:.4f}  R={rec:.4f}"
          f"  centro={diag['centroid_method']}")
    # Decomposition diagnostic
    decomp = pipe.decompose(X_test)
    coupling = decomp['coupling_matrix']
    off_diag = coupling[np.triu_indices_from(coupling, k=1)]
    print(f"  {'':20} cross-law coupling: mean={off_diag.mean():.3f} max={off_diag.max():.3f}")
    return {"name": name, "auc": auc, "f1": f1}

print("=" * 80)
print("  UDL — Universal Deviation Law — Full Cross-Domain Benchmark")
print("=" * 80)
results = []

# Synthetic
for ds in ["synthetic", "mimic"]:
    X, y = load_dataset(ds)
    results.append(benchmark(ds, X, y))

# Real-world
print("\n  Loading real-world datasets...")
try:
    X, y = load_dataset("pendigits")
    results.append(benchmark("pendigits", X, y))
except Exception as e:
    print(f"  pendigits: SKIPPED ({e})")

try:
    X, y = load_dataset("mammography")
    results.append(benchmark("mammography", X, y))
except Exception as e:
    print(f"  mammography: SKIPPED ({e})")

try:
    X, y = load_dataset("shuttle")
    results.append(benchmark("shuttle", X, y))
except Exception as e:
    print(f"  shuttle: SKIPPED ({e})")

print("\n" + "=" * 80)
avg_auc = np.mean([r["auc"] for r in results])
avg_f1 = np.mean([r["f1"] for r in results])
print(f"  Average AUC: {avg_auc:.4f}   Average F1: {avg_f1:.4f}")
print(f"  Datasets tested: {len(results)}")
print("=" * 80)
