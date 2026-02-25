#!/usr/bin/env python3
"""Quick script to get Deep SVDD + ECOD numbers now that numba works."""
import sys, os, json, warnings
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from udl.datasets import load_dataset

SEEDS = [42, 123, 456, 789, 2024]
DATASETS = ["synthetic", "mimic", "mammography", "shuttle", "pendigits"]

def safe_auc(y, s):
    try:
        return roc_auc_score(y, s) if s is not None else float("nan")
    except:
        return float("nan")

results = {}
for ds_name in DATASETS:
    print(f"\n── {ds_name.upper()} ──")
    X, y = load_dataset(ds_name)
    if ds_name == "shuttle" and len(y) > 12000:
        rng = np.random.RandomState(42)
        idx = rng.choice(len(y), 12000, replace=False)
        X, y = X[idx], y[idx]

    for mname in ["ECOD", "DeepSVDD"]:
        aucs = []
        for seed in SEEDS:
            X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.3, stratify=y, random_state=seed)
            X_tr_n = X_tr[y_tr == 0]
            scaler = StandardScaler()
            scaler.fit(X_tr_n)
            X_tr_s = scaler.transform(X_tr_n)
            X_te_s = scaler.transform(X_te)
            try:
                if mname == "ECOD":
                    from pyod.models.ecod import ECOD
                    clf = ECOD(contamination=0.05)
                    clf.fit(X_tr_s)
                    scores = clf.decision_function(X_te_s)
                else:
                    from pyod.models.deep_svdd import DeepSVDD
                    clf = DeepSVDD(n_features=X_tr_s.shape[1], epochs=50, random_state=seed, verbose=0)
                    clf.fit(X_tr_s)
                    scores = clf.decision_function(X_te_s)
                auc = safe_auc(y_te, scores)
            except Exception as e:
                print(f"  {mname} seed {seed}: {e}")
                auc = float("nan")
            aucs.append(auc)
        mean = np.nanmean(aucs)
        std = np.nanstd(aucs)
        print(f"  {mname:<12s}  {mean:.4f} ± {std:.4f}  {[round(a,4) for a in aucs]}")
        results[f"{mname}_{ds_name}"] = {"mean": round(mean, 4), "std": round(std, 4), "aucs": aucs}

out = os.path.join(os.path.dirname(__file__), "pyod_results.json")
with open(out, "w") as f:
    json.dump(results, f, indent=2)
print(f"\nSaved to {out}")
