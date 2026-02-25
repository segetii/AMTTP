"""
Numerical verification of the Universal Deviation Theorem:

    For every anomaly x, there exists at least one dimension k
    such that the deviation D_k(x) is non-zero.

    Equivalently: no anomaly is invisible across ALL dimensions
    simultaneously.

We verify this on mammography, shuttle, and pendigits by:
1. Computing per-dimension z-scores relative to normal data
2. Checking that every anomaly has max|z_k| > threshold in at least one dim
3. Computing the stacked Jacobian rank condition (for linear operators)
"""

import numpy as np
from scipy.io import loadmat
from pathlib import Path
import sys

DATA_DIR = Path(r"c:\amttp\data\external_validation\odds")

def load_dataset(name):
    mat = loadmat(str(DATA_DIR / f"{name}.mat"))
    X = np.asarray(mat['X'], dtype=np.float64)
    y = np.asarray(mat['y'], dtype=np.float64).ravel()
    return X, y

def verify_deviation_theorem(name):
    X, y = load_dataset(name)
    n, d = X.shape
    anomaly_mask = (y == 1)
    normal_mask = ~anomaly_mask
    n_anom = anomaly_mask.sum()
    n_norm = normal_mask.sum()
    
    print(f"\n{'='*60}")
    print(f"Dataset: {name}")
    print(f"  Samples: {n}, Features: {d}")
    print(f"  Normal: {n_norm}, Anomalies: {n_anom}")
    print(f"{'='*60}")
    
    # ----- Test 1: Raw z-score deviation -----
    # For each dimension, compute z-score of anomalies relative to normal distribution
    mu_normal = X[normal_mask].mean(axis=0)
    std_normal = X[normal_mask].std(axis=0)
    std_normal[std_normal < 1e-10] = 1e-10  # avoid division by zero
    
    X_anom = X[anomaly_mask]
    z_scores = np.abs((X_anom - mu_normal) / std_normal)  # (n_anom, d)
    
    # For each anomaly, find the maximum z-score across dimensions
    max_z_per_anomaly = z_scores.max(axis=1)  # (n_anom,)
    
    thresholds = [0.5, 1.0, 1.5, 2.0, 3.0]
    print(f"\n  Test 1: Raw z-score deviation")
    print(f"  {'Threshold':>10s} | {'Anomalies with max|z|>thresh':>30s} | {'Fraction':>8s}")
    print(f"  {'-'*10}-+-{'-'*30}-+-{'-'*8}")
    for t in thresholds:
        count = (max_z_per_anomaly > t).sum()
        frac = count / n_anom
        print(f"  {t:>10.1f} | {count:>30d} | {frac:>8.4f}")
    
    # The theorem says: for EVERY anomaly, there should be at least one dimension
    # with non-trivial deviation
    invisible_count = (max_z_per_anomaly < 0.5).sum()
    print(f"\n  Anomalies with max|z| < 0.5 in ALL dims (nearly invisible): {invisible_count}/{n_anom}")
    if invisible_count > 0:
        print(f"  WARNING: {invisible_count} anomalies are nearly invisible in raw z-scores")
        # Show their z-score profiles
        invisible_idx = np.where(max_z_per_anomaly < 0.5)[0][:5]
        for i in invisible_idx:
            print(f"    Anomaly z-scores: {z_scores[i].round(3)}")
    
    # ----- Test 2: Multi-operator deviation -----
    # Apply several "operators" and check deviation in each
    # Operators: identity, squared, log(1+|x|), pairwise ratios
    operators = {}
    
    # Op 1: Identity (raw features)
    operators['raw'] = X.copy()
    
    # Op 2: Squared features
    operators['squared'] = X ** 2
    
    # Op 3: Log transform
    operators['log1p'] = np.log1p(np.abs(X))
    
    # Op 4: Pairwise differences (first d-1 consecutive pairs)
    if d > 1:
        operators['diff'] = np.diff(X, axis=1)
    
    # Op 5: Gradient magnitude (sum of squared differences)
    if d > 2:
        diffs = np.diff(X, axis=1)
        operators['grad_mag'] = np.sqrt((diffs ** 2).sum(axis=1, keepdims=True))
    
    # For each operator, compute z-scores of anomalies
    print(f"\n  Test 2: Multi-operator deviation")
    print(f"  {'Operator':>12s} | {'Dims':>4s} | {'Mean max|z|':>12s} | {'Min max|z|':>12s} | {'All>0.5':>7s}")
    print(f"  {'-'*12}-+-{'-'*4}-+-{'-'*12}-+-{'-'*12}-+-{'-'*7}")
    
    combined_z = []
    for op_name, X_op in operators.items():
        mu_op = X_op[normal_mask].mean(axis=0)
        std_op = X_op[normal_mask].std(axis=0)
        std_op[std_op < 1e-10] = 1e-10
        z_op = np.abs((X_op[anomaly_mask] - mu_op) / std_op)
        max_z_op = z_op.max(axis=1)
        combined_z.append(z_op)
        all_above = (max_z_op > 0.5).all()
        print(f"  {op_name:>12s} | {X_op.shape[1]:>4d} | {max_z_op.mean():>12.4f} | {max_z_op.min():>12.4f} | {'YES' if all_above else 'NO':>7s}")
    
    # Combined: stack all operator outputs
    combined_z = np.hstack(combined_z)
    max_z_combined = combined_z.max(axis=1)
    all_visible = (max_z_combined > 0.5).all()
    print(f"\n  Combined across all operators:")
    print(f"    Min max|z| across all operator-dimensions: {max_z_combined.min():.4f}")
    print(f"    All anomalies visible (max|z|>0.5)? {'YES' if all_visible else 'NO'}")
    print(f"    Invisible anomalies: {(max_z_combined < 0.5).sum()}/{n_anom}")
    
    # ----- Test 3: Dimension-level separability -----
    # For each raw dimension, compute AUC (how well that single dimension separates)
    from sklearn.metrics import roc_auc_score
    print(f"\n  Test 3: Per-dimension AUC (single-feature separability)")
    aucs = []
    for k in range(d):
        try:
            auc_k = roc_auc_score(y, np.abs(X[:, k] - mu_normal[k]))
            aucs.append(auc_k)
        except:
            aucs.append(0.5)
    aucs = np.array(aucs)
    print(f"    Best single-dimension AUC: {aucs.max():.4f} (dim {aucs.argmax()})")
    print(f"    Worst single-dimension AUC: {aucs.min():.4f} (dim {aucs.argmin()})")
    print(f"    Mean single-dimension AUC: {aucs.mean():.4f}")
    print(f"    Dims with AUC > 0.6: {(aucs > 0.6).sum()}/{d}")
    print(f"    Per-dim AUCs: {aucs.round(4)}")
    
    # ----- Test 4: Stacked Jacobian rank -----
    # For linear operators, the Jacobian IS the operator matrix
    # Stack them and check rank
    # Our operators are: I_d, diag(2x_i), diag(1/(1+|x|)), diff_matrix
    print(f"\n  Test 4: Stacked Jacobian rank at normal centroid")
    jacobians = []
    # Identity
    jacobians.append(np.eye(d))
    # Squared: Jacobian = diag(2*mu_k)
    jacobians.append(np.diag(2 * mu_normal))
    # Log1p: Jacobian = diag(sign(mu_k)/(1+|mu_k|))
    jacobians.append(np.diag(np.sign(mu_normal) / (1 + np.abs(mu_normal))))
    # Diff: (d-1) x d matrix
    if d > 1:
        D = np.zeros((d-1, d))
        for i in range(d-1):
            D[i, i] = -1
            D[i, i+1] = 1
        jacobians.append(D)
    
    J_stacked = np.vstack(jacobians)
    rank = np.linalg.matrix_rank(J_stacked)
    print(f"    Stacked Jacobian shape: {J_stacked.shape}")
    print(f"    Rank: {rank} (need >= {d} for full column rank)")
    print(f"    Full column rank? {'YES' if rank >= d else 'NO'}")
    if rank >= d:
        print(f"    => Separating condition SATISFIED: joint map is locally injective")
        print(f"    => Every perturbation from normal is detectable by at least one operator")
    
    return {
        'name': name,
        'invisible_raw': invisible_count,
        'invisible_combined': (max_z_combined < 0.5).sum(),
        'best_single_auc': aucs.max(),
        'rank': rank,
        'full_rank': rank >= d,
        'n_anom': n_anom
    }

if __name__ == '__main__':
    results = []
    for ds in ['mammography', 'shuttle', 'pendigits']:
        try:
            r = verify_deviation_theorem(ds)
            results.append(r)
        except Exception as e:
            print(f"Error on {ds}: {e}")
            import traceback; traceback.print_exc()
    
    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    for r in results:
        status = "VERIFIED" if r['invisible_combined'] == 0 and r['full_rank'] else "PARTIAL"
        print(f"  {r['name']:>15s}: {status}")
        print(f"    Invisible anomalies (combined operators): {r['invisible_combined']}/{r['n_anom']}")
        print(f"    Stacked Jacobian full rank: {r['full_rank']}")
        print(f"    Best single-dim AUC: {r['best_single_auc']:.4f}")
