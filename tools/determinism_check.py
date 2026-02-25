"""Quick determinism check: run the full pipeline on one dataset with one seed, twice."""
import sys
sys.path.insert(0, r"c:\amttp\notebooks")
import hashlib
import numpy as np
from bsdt_eval_strict import (
    load_elliptic, make_4way_split, ref_stats_fit, components,
    mi_weights_fit, preprocess_fit_transform, platt_fit, platt_apply,
    tune_threshold_f1, metrics_at_threshold, try_load_transfer_bundle,
    build_X_for_transfer, _predict_transfer, quadsurf_fit_beta,
    quadsurf_apply, safe_auc
)
from pathlib import Path
from sklearn.linear_model import LogisticRegression

TRANSFER_DIR = Path(r"c:\amttp\_student_artifacts\amttp_models_20260213_213346")


def run_once():
    X, y = load_elliptic()
    y = y.astype(np.int32)
    split = make_4way_split(X, y, random_state=42)

    # Transfer model
    transfer = try_load_transfer_bundle(TRANSFER_DIR)
    proj = build_X_for_transfer(X, transfer)
    X_model_all, diag = proj

    p_raw_cal = _predict_transfer(transfer, X_model_all[split.cal])
    p_raw_val = _predict_transfer(transfer, X_model_all[split.val])
    p_raw_test = _predict_transfer(transfer, X_model_all[split.test])

    platt = platt_fit(p_raw_cal, y[split.cal])
    p_val = platt_apply(platt, p_raw_val)
    p_test = platt_apply(platt, p_raw_test)

    # BSDT
    stats = ref_stats_fit(X[split.train_fit], y[split.train_fit])
    comp_train = components(X[split.train_fit], stats)
    comp_val = components(X[split.val], stats)
    comp_test = components(X[split.test], stats)

    # SLR
    slr = LogisticRegression(random_state=42, max_iter=2000, class_weight="balanced")
    slr.fit(comp_train, y[split.train_fit])
    p_slr_test = slr.predict_proba(comp_test)[:, 1]

    pred_grid = np.arange(0.05, 0.95, 0.02)
    slr_th, _ = tune_threshold_f1(y[split.val], slr.predict_proba(comp_val)[:, 1], grid=pred_grid)
    slr_m = metrics_at_threshold(y[split.test], p_slr_test, slr_th)

    # QuadSurf
    p_train_fit = platt_apply(platt, _predict_transfer(transfer, X_model_all[split.train_fit]))
    poly, beta = quadsurf_fit_beta(comp_train, y[split.train_fit], p_train_fit, 0.1)
    p_quad_test = quadsurf_apply(poly, beta, p_test, comp_test)
    quad_m = metrics_at_threshold(y[split.test], p_quad_test, slr_th)

    return {
        "split_train_hash": hashlib.md5(split.train_fit.tobytes()).hexdigest(),
        "split_test_hash": hashlib.md5(split.test.tobytes()).hexdigest(),
        "p_test_hash": hashlib.md5(p_test.tobytes()).hexdigest(),
        "comp_test_hash": hashlib.md5(comp_test.tobytes()).hexdigest(),
        "slr_f1": slr_m["f1"],
        "slr_fa": slr_m["fa"],
        "slr_th": slr_th,
        "quad_f1": quad_m["f1"],
    }


print("Run 1...")
r1 = run_once()
print("Run 2...")
r2 = run_once()

print("\nComparison:")
for k in r1:
    match = "OK" if r1[k] == r2[k] else "MISMATCH"
    print(f"  {k}: {r1[k]} vs {r2[k]}  [{match}]")
