#!/usr/bin/env python3
"""
NeurIPS Full Evaluation — Fill ALL remaining gaps in the UDL paper.
===================================================================

Outputs:
  1. GravityEngine AUC on all 5 datasets (Table 2 fill)
  2. Multi-seed error bars (±std) for all methods (Table 2 upgrade)
  3. MDN unsupervised AUC (Table 2 new row)
  4. Empirical separation Δ per dataset (Theorem 4 evidence)
  5. Deep SVDD AUC on all datasets (Table 2 verify)

Run: python neurips_full_eval.py
"""
import sys, os, json, time, copy, warnings, gc
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score
from sklearn.neighbors import NearestNeighbors
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sklearn.svm import OneClassSVM
from sklearn.covariance import EllipticEnvelope

warnings.filterwarnings("ignore")

# Add parent so 'udl' package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from udl.pipeline import UDLPipeline
from udl.spectra import (
    StatisticalSpectrum, ChaosSpectrum, SpectralSpectrum,
    GeometricSpectrum, ExponentialSpectrum,
)
from udl.experimental_spectra import PhaseCurveSpectrum
from udl.gravity import GravityEngine
from udl.datasets import load_dataset

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════
SEEDS = [42, 123, 456, 789, 2024]
DATASETS = ["synthetic", "mimic", "mammography", "shuttle", "pendigits"]

# GravityEngine hyperparameters (mammography-optimised)
GE_PARAMS = dict(
    alpha=0.00496, gamma=0.0396, sigma=0.265,
    lambda_rep=0.620, eta=0.0678, iterations=15,
    k_neighbors=27, beta_dev=0.088,
    normalize=True, track_energy=True,
)

# Stack T — Tabular (default): Phase Curve replaces Dynamical
def make_operators():
    return [
        ("statistical", StatisticalSpectrum()),
        ("phase", PhaseCurveSpectrum()),
        ("spectral", SpectralSpectrum()),
        ("geometric", GeometricSpectrum()),
        ("exponential", ExponentialSpectrum(alpha=1.0)),
    ]


# Stack S — Signal/Time-Series: keeps Dynamical, adds Phase Curve
def make_signal_operators():
    return [
        ("statistical", StatisticalSpectrum()),
        ("chaos", ChaosSpectrum()),
        ("phase", PhaseCurveSpectrum()),
        ("spectral", SpectralSpectrum()),
        ("geometric", GeometricSpectrum()),
        ("exponential", ExponentialSpectrum(alpha=1.0)),
    ]


def safe_auc(y_true, scores):
    """Compute AUC, return NaN on failure."""
    try:
        if scores is None:
            return float("nan")
        return roc_auc_score(y_true, scores)
    except Exception:
        return float("nan")


# ═══════════════════════════════════════════════════════════════
# METHODS
# ═══════════════════════════════════════════════════════════════

def run_udl_qda_mag(X_train, X_test, y_train, y_test):
    """UDL-QDA-Magnified (supervised, single config)."""
    ops = make_operators()
    pipe = UDLPipeline(
        operators=ops, centroid_method='auto',
        projection_method='qda-magnified',
        score_method='v3d',
    )
    pipe.fit(X_train, y_train)
    return pipe.score(X_test)


def run_udl_fisher(X_train, X_test, y_train, y_test):
    """UDL-Fisher (supervised, single config)."""
    ops = make_operators()
    pipe = UDLPipeline(
        operators=ops, centroid_method='auto',
        projection_method='fisher',
    )
    pipe.fit(X_train, y_train)
    return pipe.score(X_test)


def run_mdn_unsupervised(X_train, X_test, y_train, y_test):
    """MDN unsupervised — magnitude-direction-novelty without labels."""
    ops = make_operators()
    pipe = UDLPipeline(
        operators=ops, centroid_method='auto',
        projection_method='pca',  # unsupervised
    )
    # Fit on all training data (no label info)
    pipe.fit(X_train, np.zeros(len(X_train)))
    return pipe.score(X_test)


def run_gravity_engine(X_train, X_test, y_train, y_test):
    """GravityEngine on the full feature space."""
    # Combine train+test for N-body simulation (GE is transductive)
    X_all = np.vstack([X_train, X_test])
    scaler = StandardScaler()
    scaler.fit(X_train[y_train == 0])
    X_scaled = scaler.transform(X_all)

    ge = GravityEngine(**GE_PARAMS)
    try:
        ge.fit_transform(X_scaled)
        scores_all = ge.anomaly_scores()
        # Return only test portion
        return scores_all[len(X_train):]
    except Exception as e:
        print(f"    [GravityEngine ERROR] {e}")
        return None


def run_isolation_forest(X_train_normal, X_test):
    clf = IsolationForest(n_estimators=200, contamination='auto',
                          random_state=42, n_jobs=-1)
    clf.fit(X_train_normal)
    return -clf.decision_function(X_test)


def run_lof(X_train_normal, X_test):
    clf = LocalOutlierFactor(n_neighbors=20, contamination='auto', novelty=True)
    clf.fit(X_train_normal)
    return -clf.decision_function(X_test)


def run_ocsvm(X_train_normal, X_test):
    X_fit = X_train_normal
    if len(X_fit) > 5000:
        rng = np.random.RandomState(42)
        idx = rng.choice(len(X_fit), 5000, replace=False)
        X_fit = X_fit[idx]
    clf = OneClassSVM(kernel='rbf', gamma='scale', nu=0.05)
    clf.fit(X_fit)
    return -clf.decision_function(X_test)


def run_elliptic(X_train_normal, X_test):
    try:
        # EllipticEnvelope uses robust covariance (O(n·d³)) — skip when d is
        # large to avoid hanging (e.g. Pendigits d=64).
        if X_train_normal.shape[1] > 30:
            return None
        clf = EllipticEnvelope(contamination=0.01, random_state=42,
                               support_fraction=0.99)
        clf.fit(X_train_normal)
        return -clf.decision_function(X_test)
    except Exception:
        return None


def run_knn(X_train_normal, X_test):
    nn = NearestNeighbors(n_neighbors=10, n_jobs=-1)
    nn.fit(X_train_normal)
    distances, _ = nn.kneighbors(X_test)
    return distances.mean(axis=1)


def run_deep_svdd(X_train_normal, X_test):
    """Deep SVDD — uses PyOD if available."""
    try:
        from pyod.models.deep_svdd import DeepSVDD
        clf = DeepSVDD(n_features=X_train_normal.shape[1],
                       epochs=50, random_state=42, verbose=0)
        clf.fit(X_train_normal)
        return clf.decision_function(X_test)
    except ImportError:
        print("    [Deep SVDD] PyOD not installed, skipping")
        return None
    except Exception as e:
        print(f"    [Deep SVDD ERROR] {e}")
        return None


def run_ecod(X_train_normal, X_test):
    """ECOD — uses PyOD if available."""
    try:
        from pyod.models.ecod import ECOD
        clf = ECOD(contamination=0.05)
        clf.fit(X_train_normal)
        return clf.decision_function(X_test)
    except ImportError:
        print("    [ECOD] PyOD not installed, skipping")
        return None
    except Exception as e:
        print(f"    [ECOD ERROR] {e}")
        return None


# ═══════════════════════════════════════════════════════════════
# EMPIRICAL SEPARATION Δ (Theorem 4 support)
# ═══════════════════════════════════════════════════════════════

def compute_separation_delta(X_train, y_train, X_test, y_test):
    """
    Compute empirical separation Δ = dist(Φ(A), Φ(N)) in representation space.

    Φ is the UDL multi-spectrum embedding.
    Δ = ||μ_A - μ_N|| / σ_pool  (Cohen's d in representation space)
    """
    ops = make_operators()
    pipe = UDLPipeline(
        operators=ops, centroid_method='auto',
        projection_method='fisher',
    )
    pipe.fit(X_train, y_train)

    # Get representation vectors for test data
    R_test = pipe.stack.transform(X_test)

    # Split by true label
    R_normal = R_test[y_test == 0]
    R_anomaly = R_test[y_test == 1]

    if len(R_anomaly) == 0:
        return {"delta_cohen": float("nan"), "delta_raw": float("nan")}

    mu_n = R_normal.mean(axis=0)
    mu_a = R_anomaly.mean(axis=0)

    raw_dist = np.linalg.norm(mu_a - mu_n)

    # Pooled std
    var_n = np.var(np.linalg.norm(R_normal - mu_n, axis=1))
    var_a = np.var(np.linalg.norm(R_anomaly - mu_a, axis=1))
    n_n, n_a = len(R_normal), len(R_anomaly)
    pooled_var = ((n_n - 1) * var_n + (n_a - 1) * var_a) / (n_n + n_a - 2)
    pooled_std = max(np.sqrt(pooled_var), 1e-10)

    cohen_d = raw_dist / pooled_std

    # Also compute per-law separation
    law_dims = pipe.stack.law_dims_
    per_law_delta = {}
    offset = 0
    for (name, _), dim in zip(ops, law_dims):
        r_n = R_normal[:, offset:offset + dim]
        r_a = R_anomaly[:, offset:offset + dim]
        d = np.linalg.norm(r_a.mean(axis=0) - r_n.mean(axis=0))
        s = max(np.std(np.linalg.norm(r_n - r_n.mean(axis=0), axis=1)), 1e-10)
        per_law_delta[name] = d / s
        offset += dim

    return {
        "delta_cohen": round(cohen_d, 3),
        "delta_raw": round(raw_dist, 3),
        "per_law": {k: round(v, 3) for k, v in per_law_delta.items()},
    }


# ═══════════════════════════════════════════════════════════════
# MAIN EVALUATION LOOP
# ═══════════════════════════════════════════════════════════════

def main():
    print("=" * 80)
    print("  NeurIPS FULL EVALUATION — UDL Paper Gap-Filler")
    print("=" * 80)

    results = {
        "multi_seed": {},  # method -> dataset -> [auc per seed]
        "gravity_engine": {},  # dataset -> [auc per seed]
        "mdn_unsupervised": {},  # dataset -> [auc per seed]
        "separation_delta": {},  # dataset -> delta info
        "deep_svdd": {},  # dataset -> [auc per seed]
        "ecod": {},  # dataset -> [auc per seed]
    }

    # ── Load all datasets ──
    print("\n  Loading datasets...")
    all_data = {}
    for ds_name in DATASETS:
        print(f"    {ds_name}...", end=" ", flush=True)
        X, y = load_dataset(ds_name)
        # Subsample shuttle (49K is slow for multi-seed)
        if ds_name == "shuttle" and len(y) > 12000:
            rng = np.random.RandomState(42)
            idx = rng.choice(len(y), 12000, replace=False)
            X, y = X[idx], y[idx]
        all_data[ds_name] = (X, y)
        print(f"N={len(y)}, m={X.shape[1]}, anom%={100*y.mean():.1f}%")

    # ── Multi-seed evaluation ──
    print("\n" + "=" * 80)
    print("  SECTION 1: Multi-seed evaluation (5 seeds)")
    print("=" * 80)

    supervised_methods = {
        "UDL-QDA-Mag": run_udl_qda_mag,
        "UDL-Fisher": run_udl_fisher,
    }

    for ds_name, (X, y) in all_data.items():
        print(f"\n  ── {ds_name.upper()} ──")

        for method_name, method_fn in supervised_methods.items():
            aucs = []
            for seed in SEEDS:
                X_tr, X_te, y_tr, y_te = train_test_split(
                    X, y, test_size=0.3, stratify=y, random_state=seed)
                try:
                    scores = method_fn(X_tr, X_te, y_tr, y_te)
                    auc = safe_auc(y_te, scores)
                except Exception as e:
                    print(f"    {method_name} seed {seed}: ERROR {e}")
                    auc = float("nan")
                aucs.append(auc)

            key = method_name
            if key not in results["multi_seed"]:
                results["multi_seed"][key] = {}
            results["multi_seed"][key][ds_name] = aucs
            mean_auc = np.nanmean(aucs)
            std_auc = np.nanstd(aucs)
            print(f"    {method_name:<18s}  {mean_auc:.4f} ± {std_auc:.4f}  {aucs}")

        # Unsupervised baselines
        unsup_methods = {
            "IF": run_isolation_forest,
            "LOF": run_lof,
            "OCSVM": run_ocsvm,
            "EE": run_elliptic,
            "kNN": run_knn,
        }

        for method_name, method_fn in unsup_methods.items():
            aucs = []
            for seed in SEEDS:
                X_tr, X_te, y_tr, y_te = train_test_split(
                    X, y, test_size=0.3, stratify=y, random_state=seed)
                X_tr_n = X_tr[y_tr == 0]
                scaler = StandardScaler()
                scaler.fit(X_tr_n)
                X_tr_n_s = scaler.transform(X_tr_n)
                X_te_s = scaler.transform(X_te)
                try:
                    scores = method_fn(X_tr_n_s, X_te_s)
                    auc = safe_auc(y_te, scores)
                except BaseException as e:
                    print(f"    {method_name} seed {seed}: ERROR {e}")
                    auc = float("nan")
                aucs.append(auc)

            if method_name not in results["multi_seed"]:
                results["multi_seed"][method_name] = {}
            results["multi_seed"][method_name][ds_name] = aucs
            mean_auc = np.nanmean(aucs)
            std_auc = np.nanstd(aucs)
            print(f"    {method_name:<18s}  {mean_auc:.4f} ± {std_auc:.4f}")

    # ── GravityEngine on all datasets ──
    print("\n" + "=" * 80)
    print("  SECTION 2: GravityEngine on all datasets")
    print("=" * 80)

    for ds_name, (X, y) in all_data.items():
        print(f"\n  ── {ds_name.upper()} ──")
        aucs = []
        for seed in SEEDS:
            X_tr, X_te, y_tr, y_te = train_test_split(
                X, y, test_size=0.3, stratify=y, random_state=seed)
            try:
                scores = run_gravity_engine(X_tr, X_te, y_tr, y_te)
                auc = safe_auc(y_te, scores)
            except Exception as e:
                print(f"    GE seed {seed}: ERROR {e}")
                auc = float("nan")
            aucs.append(auc)

        results["gravity_engine"][ds_name] = aucs
        mean_auc = np.nanmean(aucs)
        std_auc = np.nanstd(aucs)
        print(f"    GravityEngine    {mean_auc:.4f} ± {std_auc:.4f}  {aucs}")

    # ── MDN Unsupervised ──
    print("\n" + "=" * 80)
    print("  SECTION 3: MDN Unsupervised on all datasets")
    print("=" * 80)

    for ds_name, (X, y) in all_data.items():
        print(f"\n  ── {ds_name.upper()} ──")
        aucs = []
        for seed in SEEDS:
            X_tr, X_te, y_tr, y_te = train_test_split(
                X, y, test_size=0.3, stratify=y, random_state=seed)
            try:
                scores = run_mdn_unsupervised(X_tr, X_te, y_tr, y_te)
                auc = safe_auc(y_te, scores)
            except Exception as e:
                print(f"    MDN seed {seed}: ERROR {e}")
                auc = float("nan")
            aucs.append(auc)

        results["mdn_unsupervised"][ds_name] = aucs
        mean_auc = np.nanmean(aucs)
        std_auc = np.nanstd(aucs)
        print(f"    MDN-unsup        {mean_auc:.4f} ± {std_auc:.4f}  {aucs}")

    # ── Deep SVDD + ECOD ──
    print("\n" + "=" * 80)
    print("  SECTION 4: Deep SVDD + ECOD (PyOD)")
    print("=" * 80)

    MAX_TRAIN_PYOD = 8000  # cap training-normal size to avoid OOM

    for ds_name, (X, y) in all_data.items():
        print(f"\n  ── {ds_name.upper()} ──")

        for mname, mfn in [("DeepSVDD", run_deep_svdd), ("ECOD", run_ecod)]:
            aucs = []
            for seed in SEEDS:
                X_tr, X_te, y_tr, y_te = train_test_split(
                    X, y, test_size=0.3, stratify=y, random_state=seed)
                X_tr_n = X_tr[y_tr == 0]
                # Cap training set to avoid OOM on 16 GB machine
                if len(X_tr_n) > MAX_TRAIN_PYOD:
                    rng = np.random.RandomState(seed)
                    idx = rng.choice(len(X_tr_n), MAX_TRAIN_PYOD, replace=False)
                    X_tr_n = X_tr_n[idx]
                scaler = StandardScaler()
                scaler.fit(X_tr_n)
                X_tr_n_s = scaler.transform(X_tr_n)
                X_te_s = scaler.transform(X_te)
                try:
                    scores = mfn(X_tr_n_s, X_te_s)
                    auc = safe_auc(y_te, scores)
                except Exception as e:
                    auc = float("nan")
                aucs.append(auc)
                del scores, X_tr_n_s, X_te_s, X_tr_n
                gc.collect()

            key = "deep_svdd" if mname == "DeepSVDD" else "ecod"
            results[key][ds_name] = aucs
            mean_auc = np.nanmean(aucs)
            std_auc = np.nanstd(aucs)
            print(f"    {mname:<18s}  {mean_auc:.4f} ± {std_auc:.4f}")

    # ── Separation Δ ──
    print("\n" + "=" * 80)
    print("  SECTION 5: Empirical Separation Δ")
    print("=" * 80)

    for ds_name, (X, y) in all_data.items():
        print(f"\n  ── {ds_name.upper()} ──")
        X_tr, X_te, y_tr, y_te = train_test_split(
            X, y, test_size=0.3, stratify=y, random_state=42)
        try:
            delta = compute_separation_delta(X_tr, y_tr, X_te, y_te)
            results["separation_delta"][ds_name] = delta
            print(f"    Cohen's d:  {delta['delta_cohen']:.3f}")
            print(f"    Raw dist:   {delta['delta_raw']:.3f}")
            if "per_law" in delta:
                for law, d in delta["per_law"].items():
                    print(f"      {law}: Δ = {d:.3f}")
        except Exception as e:
            print(f"    ERROR: {e}")
            results["separation_delta"][ds_name] = {"delta_cohen": float("nan")}

    # ── Summary ──
    print("\n" + "=" * 80)
    print("  SUMMARY — Paper-Ready Numbers")
    print("=" * 80)

    print("\n  Table 2: GravityEngine AUC (mean ± std over 5 seeds)")
    for ds_name in DATASETS:
        aucs = results["gravity_engine"].get(ds_name, [])
        if aucs:
            print(f"    {ds_name:<15s}  {np.nanmean(aucs):.3f} ± {np.nanstd(aucs):.3f}")

    print("\n  Table 2: MDN unsupervised AUC (mean ± std)")
    for ds_name in DATASETS:
        aucs = results["mdn_unsupervised"].get(ds_name, [])
        if aucs:
            print(f"    {ds_name:<15s}  {np.nanmean(aucs):.3f} ± {np.nanstd(aucs):.3f}")

    print("\n  Theorem 4: Separation Δ")
    for ds_name in DATASETS:
        d = results["separation_delta"].get(ds_name, {})
        print(f"    {ds_name:<15s}  Cohen's d = {d.get('delta_cohen', 'N/A')}")

    # Save JSON
    out_path = os.path.join(os.path.dirname(__file__), "neurips_eval_results.json")

    # Clean NaN for JSON serialisation
    def clean_nan(obj):
        if isinstance(obj, float) and np.isnan(obj):
            return None
        if isinstance(obj, dict):
            return {k: clean_nan(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [clean_nan(v) for v in obj]
        if isinstance(obj, np.floating):
            return float(obj) if not np.isnan(obj) else None
        return obj

    with open(out_path, "w") as f:
        json.dump(clean_nan(results), f, indent=2)
    print(f"\n  Results saved to: {out_path}")


if __name__ == "__main__":
    main()
