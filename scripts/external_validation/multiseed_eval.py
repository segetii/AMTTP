"""Multi-seed evaluation wrapper for calibrated_mlfs_eval.

Runs the full evaluation pipeline with 5 different random seeds,
collects per-seed results, and reports mean +/- std for all metrics.
Outputs JSON with per-seed and aggregated statistics.
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# Reuse the existing evaluation module
sys.path.insert(0, str(Path(__file__).parent))
from calibrated_mlfs_eval import (
    PARQUET,
    ARTIFACTS_DIR,
    build_X_93,
    load_v2_artifacts,
    v2_preprocess_raw,
    v2_build_boost,
    v2_score,
    make_4way_split,
    platt_fit,
    platt_apply,
    isotonic_fit,
    isotonic_apply,
    ref_stats_fit,
    bsdt_components,
    mi_weights_fit,
    apply_mlfs_base,
    tune_mlfs_base,
    tune_threshold_f1,
    metrics_at_threshold,
    quadsurf_fit_beta,
    quadsurf_apply,
    safe_auc,
    safe_ap,
    sigmoid,
)
from sklearn.linear_model import LogisticRegression

SEEDS = [42, 123, 456, 789, 2025]
OUT_JSON = Path(r"C:\amttp\reports\external_validation\multiseed_results.json")


def run_one_seed(
    X_scaled_93, X_boost, xgb_raw_all, lgb_raw_all, y, seed: int
) -> dict:
    """Run the full evaluation pipeline for one seed. Returns metrics dict."""
    split = make_4way_split(y, random_state=seed)
    y_train_fit = y[split.train_fit]
    y_cal = y[split.cal]
    y_val = y[split.val]
    y_test = y[split.test]

    pred_grid = np.linspace(0.05, 0.95, 91)
    results = {}

    for model_name, p_all_orig in [("XGB", xgb_raw_all), ("LGB", lgb_raw_all)]:
        p_all = p_all_orig.copy()

        # Orientation check on cal split
        auc_cal = safe_auc(y_cal, p_all[split.cal])
        if auc_cal < 0.5:
            p_all = 1.0 - p_all

        p_train_fit = p_all[split.train_fit]
        p_cal_raw = p_all[split.cal]
        p_val_raw = p_all[split.val]
        p_test_raw = p_all[split.test]

        # 1. Uncalibrated
        uncal_auc = safe_auc(y_test, p_test_raw)
        uncal_ap = safe_ap(y_test, p_test_raw)
        th_uncal, _ = tune_threshold_f1(y_val, p_val_raw, grid=pred_grid)
        uncal_m = metrics_at_threshold(y_test, p_test_raw, th_uncal)

        # 2. Isotonic calibration
        iso = isotonic_fit(p_cal_raw, y_cal)
        p_val_iso = isotonic_apply(iso, p_val_raw)
        p_test_iso = isotonic_apply(iso, p_test_raw)
        p_train_fit_iso = isotonic_apply(iso, p_train_fit)

        iso_auc = safe_auc(y_test, p_test_iso)
        iso_ap = safe_ap(y_test, p_test_iso)
        th_iso, _ = tune_threshold_f1(y_val, p_val_iso, grid=pred_grid)
        iso_m = metrics_at_threshold(y_test, p_test_iso, th_iso)

        # 3. Platt calibration (base for BSDT corrections)
        platt = platt_fit(p_cal_raw, y_cal)
        p_train_fit_platt = platt_apply(platt, p_train_fit)
        p_val_platt = platt_apply(platt, p_val_raw)
        p_test_platt = platt_apply(platt, p_test_raw)

        # 4. BSDT components
        stats = ref_stats_fit(X_scaled_93[split.train_fit], y_train_fit)
        comp_train = bsdt_components(X_scaled_93[split.train_fit], stats)
        comp_val = bsdt_components(X_scaled_93[split.val], stats)
        comp_test = bsdt_components(X_scaled_93[split.test], stats)

        mi_w, _ = mi_weights_fit(comp_train, y_train_fit)

        p_base_train = p_train_fit_platt
        p_base_val = p_val_platt
        p_base_test = p_test_platt

        # 5. QuadSurf
        quad_alpha_grid = [0.01, 0.1, 1.0]
        quad_best = {"f1": -1.0}
        quad_best_alpha = quad_best_th = 0.0
        quad_best_poly = quad_best_beta = None
        for alpha in quad_alpha_grid:
            poly, beta = quadsurf_fit_beta(comp_train, y_train_fit, p_base_train, float(alpha))
            p_q_val = quadsurf_apply(poly, beta, p_base_val, comp_val)
            th_q, m_q = tune_threshold_f1(y_val, p_q_val, grid=pred_grid)
            if m_q["f1"] > quad_best["f1"]:
                quad_best = m_q
                quad_best_alpha = float(alpha)
                quad_best_th = float(th_q)
                quad_best_poly = poly
                quad_best_beta = beta

        p_quad_test = quadsurf_apply(quad_best_poly, quad_best_beta, p_base_test, comp_test)
        quad_auc = safe_auc(y_test, p_quad_test)
        quad_ap = safe_ap(y_test, p_quad_test)
        quad_m = metrics_at_threshold(y_test, p_quad_test, quad_best_th)

        # 6. ExpGate
        gate_k_grid = np.array([2.0, 4.0, 8.0, 12.0])
        gate_tau_grid = np.array([0.2, 0.3, 0.5, 0.7])
        qexp_best = {"f1": -1.0}
        qexp_best_alpha = qexp_best_k = qexp_best_tau = qexp_best_th = 0.0
        qexp_best_poly = qexp_best_beta = None
        for alpha in quad_alpha_grid:
            poly, beta = quadsurf_fit_beta(comp_train, y_train_fit, p_base_train, float(alpha))
            p_q_val = quadsurf_apply(poly, beta, p_base_val, comp_val)
            delta_val = p_q_val - p_base_val
            for gate_tau in gate_tau_grid:
                for gate_k in gate_k_grid:
                    gate = sigmoid(float(gate_k) * (float(gate_tau) - p_base_val))
                    p_qexp_val = np.clip(p_base_val + gate * delta_val, 0.0, 1.0)
                    th_e, m_e = tune_threshold_f1(y_val, p_qexp_val, grid=pred_grid)
                    if m_e["f1"] > qexp_best["f1"]:
                        qexp_best = m_e
                        qexp_best_alpha = float(alpha)
                        qexp_best_k = float(gate_k)
                        qexp_best_tau = float(gate_tau)
                        qexp_best_th = float(th_e)
                        qexp_best_poly = poly
                        qexp_best_beta = beta

        p_q_test_eg = quadsurf_apply(qexp_best_poly, qexp_best_beta, p_base_test, comp_test)
        delta_test = p_q_test_eg - p_base_test
        gate_test = sigmoid(qexp_best_k * (qexp_best_tau - p_base_test))
        p_qexp_test = np.clip(p_base_test + gate_test * delta_test, 0.0, 1.0)
        qexp_auc = safe_auc(y_test, p_qexp_test)
        qexp_ap = safe_ap(y_test, p_qexp_test)
        qexp_m = metrics_at_threshold(y_test, p_qexp_test, qexp_best_th)

        # 7. SignedLR
        slr = LogisticRegression(random_state=seed, max_iter=2000, class_weight="balanced")
        slr.fit(comp_train, y_train_fit)
        p_slr_val = slr.predict_proba(comp_val)[:, 1]
        p_slr_test = slr.predict_proba(comp_test)[:, 1]
        slr_auc = safe_auc(y_test, p_slr_test)
        slr_ap = safe_ap(y_test, p_slr_test)
        slr_th, _ = tune_threshold_f1(y_val, p_slr_val, grid=pred_grid)
        slr_m = metrics_at_threshold(y_test, p_slr_test, slr_th)

        results[model_name] = {
            "uncalibrated": {"auc": uncal_auc, "ap": uncal_ap, "f1": uncal_m["f1"], "prec": uncal_m["prec"], "fdr": uncal_m["fdr"]},
            "isotonic":     {"auc": iso_auc,   "ap": iso_ap,   "f1": iso_m["f1"],   "prec": iso_m["prec"],   "fdr": iso_m["fdr"]},
            "quadsurf":     {"auc": quad_auc,  "ap": quad_ap,  "f1": quad_m["f1"],  "prec": quad_m["prec"],  "fdr": quad_m["fdr"]},
            "expgate":      {"auc": qexp_auc,  "ap": qexp_ap,  "f1": qexp_m["f1"],  "prec": qexp_m["prec"],  "fdr": qexp_m["fdr"]},
            "signed_lr":    {"auc": slr_auc,   "ap": slr_ap,   "f1": slr_m["f1"],   "prec": slr_m["prec"],   "fdr": slr_m["fdr"]},
        }

    return results


def main():
    print("Loading data and artifacts...")
    df = pd.read_parquet(PARQUET)
    y = pd.to_numeric(df["label_unified"], errors="coerce").fillna(0).astype(int).to_numpy()

    bundle = load_v2_artifacts(ARTIFACTS_DIR)
    fc = bundle["feature_config"]
    raw_features = fc["raw_features"]
    boost_features = fc["boost_features"]

    X_raw_93 = build_X_93(df)
    X_scaled_93 = v2_preprocess_raw(X_raw_93, bundle["preprocessors"])
    X_boost = v2_build_boost(X_scaled_93, raw_features, boost_features)

    # V2 raw scores (full dataset, before orientation flip)
    xgb_raw_all, lgb_raw_all = v2_score(X_boost, bundle)

    print(f"  Samples: {len(y)}, Positives: {int(y.sum())} ({100*y.mean():.1f}%)")

    all_seeds_results = {}
    for seed in SEEDS:
        print(f"\n{'='*60}")
        print(f"  SEED = {seed}")
        print(f"{'='*60}")
        all_seeds_results[seed] = run_one_seed(
            X_scaled_93, X_boost, xgb_raw_all.copy(), lgb_raw_all.copy(), y, seed
        )

    # Aggregate: compute mean +/- std across seeds
    aggregate = {}
    for model_name in ["XGB", "LGB"]:
        aggregate[model_name] = {}
        for variant in ["uncalibrated", "isotonic", "quadsurf", "expgate", "signed_lr"]:
            vals = {}
            for metric in ["auc", "ap", "f1", "prec", "fdr"]:
                per_seed = [all_seeds_results[s][model_name][variant][metric] for s in SEEDS]
                vals[f"{metric}_mean"] = float(np.mean(per_seed))
                vals[f"{metric}_std"] = float(np.std(per_seed))
                vals[f"{metric}_per_seed"] = per_seed
            aggregate[model_name][variant] = vals

    # Print summary
    print(f"\n{'='*90}")
    print(f"  AGGREGATED RESULTS (mean +/- std over {len(SEEDS)} seeds)")
    print(f"{'='*90}")
    print(f"{'Model':<6} {'Variant':<15} {'AUC':>14} {'AP':>14} {'F1':>14} {'Prec':>14} {'FDR':>14}")
    print("-" * 90)
    for mname in ["XGB", "LGB"]:
        for vname, vkey in [("Uncalibrated", "uncalibrated"), ("Isotonic", "isotonic"),
                            ("QuadSurf", "quadsurf"), ("ExpGate", "expgate"),
                            ("SignedLR", "signed_lr")]:
            d = aggregate[mname][vkey]
            def fmt(m, d=d):
                return f"{d[f'{m}_mean']:.3f}+/-{d[f'{m}_std']:.3f}"
            print(f"{mname:<6} {vname:<15} {fmt('auc'):>14} {fmt('ap'):>14} {fmt('f1'):>14} {fmt('prec'):>14} {fmt('fdr'):>14}")
        print("-" * 90)

    # Save
    output = {"seeds": SEEDS, "per_seed": {str(k): v for k, v in all_seeds_results.items()}, "aggregate": aggregate}
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"\nWrote: {OUT_JSON}")


if __name__ == "__main__":
    main()
