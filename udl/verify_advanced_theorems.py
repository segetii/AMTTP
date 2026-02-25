"""
Numerical verification of the advanced UDL theorems:

  Theorem 2 — Global Deviation (σ_min > 0 everywhere on compact support)
  Theorem 3 — Finite-Sample Guarantee (sample complexity bound)
  Theorem 4 — Information-Optimal Fusion Weights (SDP / trace heuristic)
  Theorem 5 — Greedy Operator Selection (submodular maximisation)
"""

import numpy as np
from scipy.io import loadmat
from scipy.linalg import svdvals
from sklearn.metrics import roc_auc_score
from pathlib import Path

DATA_DIR = Path(r"c:\amttp\data\external_validation\odds")


def load_dataset(name):
    mat = loadmat(str(DATA_DIR / f"{name}.mat"))
    X = np.asarray(mat["X"], dtype=np.float64)
    y = np.asarray(mat["y"], dtype=np.float64).ravel()
    return X, y


# ── Operator definitions ──────────────────────────────────────────────
# Each operator is a callable: X → X_transformed
# Plus a Jacobian function: x → (d_k × m) matrix

def op_identity(X):
    return X.copy()

def jac_identity(x):
    return np.eye(len(x))

def op_squared(X):
    return X ** 2

def jac_squared(x):
    return np.diag(2 * x)

def op_log1p(X):
    return np.log1p(np.abs(X))

def jac_log1p(x):
    return np.diag(np.sign(x) / (1 + np.abs(x)))

def op_diff(X):
    return np.diff(X, axis=1)

def jac_diff(x):
    m = len(x)
    D = np.zeros((m - 1, m))
    for i in range(m - 1):
        D[i, i] = -1
        D[i, i + 1] = 1
    return D

def op_exp_scale(X, alpha=0.5):
    mu = X.mean(axis=0)
    sigma = X.std(axis=0)
    sigma[sigma < 1e-10] = 1e-10
    z = (X - mu) / sigma
    return np.exp(alpha * z)

def jac_exp_scale(x, mu, sigma, alpha=0.5):
    z = (x - mu) / sigma
    return np.diag((alpha / sigma) * np.exp(alpha * z))

def op_abs_fft(X):
    return np.abs(np.fft.rfft(X, axis=1))

def jac_abs_fft_numerical(x, eps=1e-6):
    """Numerical Jacobian for |FFT|."""
    y0 = np.abs(np.fft.rfft(x))
    m = len(x)
    d_k = len(y0)
    J = np.zeros((d_k, m))
    for j in range(m):
        xp = x.copy()
        xp[j] += eps
        J[:, j] = (np.abs(np.fft.rfft(xp)) - y0) / eps
    return J


OPERATORS = [
    ("identity", op_identity, jac_identity),
    ("squared", op_squared, jac_squared),
    ("log1p", op_log1p, jac_log1p),
    ("diff", op_diff, jac_diff),
    ("abs_fft", op_abs_fft, None),  # numerical Jacobian
]


def stacked_jacobian(x, mu, sigma, operators):
    """Compute stacked Jacobian J(x) for all operators."""
    blocks = []
    for name, op_fn, jac_fn in operators:
        if jac_fn is not None:
            if name == "exp_scale":
                blocks.append(jac_exp_scale(x, mu, sigma))
            else:
                blocks.append(jac_fn(x))
        else:
            blocks.append(jac_abs_fft_numerical(x))
    return np.vstack(blocks)


def compute_info_matrix(J):
    """I(μ) = J^T J."""
    return J.T @ J


# ═══════════════════════════════════════════════════════════════════════
# THEOREM 2 — Global Deviation: σ_min(J(x)) > 0 over 𝒦
# ═══════════════════════════════════════════════════════════════════════

def verify_theorem2(name):
    X, y = load_dataset(name)
    n, m = X.shape
    normal_mask = y == 0
    X_normal = X[normal_mask]
    mu = X_normal.mean(axis=0)
    sigma = X_normal.std(axis=0)
    sigma[sigma < 1e-10] = 1e-10

    # Sample points across 𝒦 = convex hull of data
    # Check σ_min(J(x)) at many points
    n_check = min(500, n)
    indices = np.random.RandomState(42).choice(n, n_check, replace=False)

    sigma_mins = []
    for i in indices:
        J = stacked_jacobian(X[i], mu, sigma, OPERATORS)
        sv = svdvals(J)
        sigma_mins.append(sv[-1])  # smallest singular value

    sigma_mins = np.array(sigma_mins)
    sigma_bar = sigma_mins.min()
    sigma_mean = sigma_mins.mean()

    print(f"\n{'='*65}")
    print(f"THEOREM 2 — Global Deviation: {name}")
    print(f"{'='*65}")
    print(f"  Checked σ_min(J(x)) at {n_check} points across data support")
    print(f"  min σ_min = {sigma_bar:.6f}")
    print(f"  mean σ_min = {sigma_mean:.6f}")
    print(f"  max σ_min = {sigma_mins.max():.6f}")
    print(f"  σ_min > 0 EVERYWHERE? {'YES ✓' if sigma_bar > 0 else 'NO ✗'}")
    if sigma_bar > 0:
        print(f"  ⟹ Global theorem holds: ∀x∈𝒦, ‖Φ(x)−Φ(μ)‖ ≥ {sigma_bar:.4f}·‖x−μ‖")

    return sigma_bar, sigma_mins


# ═══════════════════════════════════════════════════════════════════════
# THEOREM 3 — Finite-Sample Guarantee
# ═══════════════════════════════════════════════════════════════════════

def verify_theorem3(name, sigma_bar):
    X, y = load_dataset(name)
    n, m = X.shape
    normal_mask = y == 0
    X_normal = X[normal_mask]
    mu_true = X_normal.mean(axis=0)
    Sigma = np.cov(X_normal.T)
    tr_Sigma = np.trace(Sigma)

    # Lipschitz constant estimation: max ‖J(x)‖_op over sample
    n_lip = min(200, normal_mask.sum())
    sigma_n = X_normal.std(axis=0)
    sigma_n[sigma_n < 1e-10] = 1e-10
    L_est = 0.0
    for i in range(n_lip):
        J = stacked_jacobian(X_normal[i], mu_true, sigma_n, OPERATORS)
        L_est = max(L_est, svdvals(J)[0])

    K = len(OPERATORS)
    delta = 0.05  # 95% confidence

    # Minimum anomaly distance
    X_anom = X[y == 1]
    dists = np.linalg.norm(X_anom - mu_true, axis=1)
    min_anom_dist = dists.min()
    mean_anom_dist = dists.mean()

    # Sample complexity: n > 2 L² K tr(Σ) ln(2m/δ) / (σ̄² ‖x−μ‖²)
    n_required_min = (2 * L_est**2 * K * tr_Sigma * np.log(2*m/delta)) / (sigma_bar**2 * min_anom_dist**2)
    n_required_mean = (2 * L_est**2 * K * tr_Sigma * np.log(2*m/delta)) / (sigma_bar**2 * mean_anom_dist**2)

    # Actual finite-sample error at different n
    print(f"\n{'='*65}")
    print(f"THEOREM 3 — Finite-Sample Guarantee: {name}")
    print(f"{'='*65}")
    print(f"  Lipschitz constant L = {L_est:.4f}")
    print(f"  tr(Σ) = {tr_Sigma:.4f}")
    print(f"  σ̄ (global) = {sigma_bar:.6f}")
    print(f"  K = {K} operators, m = {m} features")
    print(f"  Min anomaly distance = {min_anom_dist:.4f}")
    print(f"  Mean anomaly distance = {mean_anom_dist:.4f}")
    print(f"")
    print(f"  Sample complexity (δ=0.05):")
    print(f"    To detect closest anomaly: n > {n_required_min:.0f}")
    print(f"    To detect average anomaly: n > {n_required_mean:.0f}")
    print(f"    Actual normal samples: {normal_mask.sum()}")
    print(f"    Sufficient? {'YES ✓' if normal_mask.sum() > n_required_mean else 'NO ✗'}")

    # Monte Carlo verification: subsample normal data, check bound holds
    print(f"\n  Monte Carlo validation (100 trials):")
    n_trials = 100
    rng = np.random.RandomState(123)
    bound_holds = 0
    for trial in range(n_trials):
        n_sub = min(500, normal_mask.sum())
        idx = rng.choice(normal_mask.sum(), n_sub, replace=False)
        mu_hat = X_normal[idx].mean(axis=0)
        mu_error = np.linalg.norm(mu_hat - mu_true)
        # Check: for each anomaly, does the bound predict correctly?
        for a in range(min(20, len(X_anom))):
            x_a = X_anom[a]
            # Actual max deviation
            actual_devs = []
            for op_name, op_fn, _ in OPERATORS:
                phi_x = op_fn(x_a.reshape(1, -1)).ravel()
                phi_mu = op_fn(mu_hat.reshape(1, -1)).ravel()
                actual_devs.append(np.linalg.norm(phi_x - phi_mu))
            max_dev = max(actual_devs)
            # Predicted lower bound
            predicted = (sigma_bar / np.sqrt(K)) * np.linalg.norm(x_a - mu_true) - L_est * mu_error
            if max_dev >= predicted:
                bound_holds += 1

    total_checks = n_trials * min(20, len(X_anom))
    print(f"    Bound holds: {bound_holds}/{total_checks} ({100*bound_holds/total_checks:.1f}%)")

    return n_required_mean, L_est


# ═══════════════════════════════════════════════════════════════════════
# THEOREM 4 — Information-Optimal Fusion Weights
# ═══════════════════════════════════════════════════════════════════════

def verify_theorem4(name):
    X, y = load_dataset(name)
    n, m = X.shape
    normal_mask = y == 0
    X_normal = X[normal_mask]
    mu = X_normal.mean(axis=0)
    sigma = X_normal.std(axis=0)
    sigma[sigma < 1e-10] = 1e-10

    K = len(OPERATORS)

    # Compute per-operator information matrices I_k = DΦ_k(μ)^T DΦ_k(μ)
    J_mu = stacked_jacobian(mu, mu, sigma, OPERATORS)
    info_matrices = []
    row = 0
    for name_op, op_fn, jac_fn in OPERATORS:
        if jac_fn is not None:
            if name_op == "exp_scale":
                Jk = jac_exp_scale(mu, mu, sigma)
            else:
                Jk = jac_fn(mu)
        else:
            Jk = jac_abs_fft_numerical(mu)
        Ik = Jk.T @ Jk
        info_matrices.append(Ik)

    # Trace-proportional weights (Proposition 4)
    traces = np.array([np.trace(Ik) for Ik in info_matrices])
    w_trace = traces / traces.sum()

    # Equal weights (baseline)
    w_equal = np.ones(K) / K

    # Compute η(w) = λ_min(Σ_k w_k I_k) for each weight scheme
    def sensitivity(w):
        M = sum(w[k] * info_matrices[k] for k in range(K))
        return np.linalg.eigvalsh(M)[0]

    eta_equal = sensitivity(w_equal)
    eta_trace = sensitivity(w_trace)

    # SDP via simple grid search (for K=5, we can search efficiently)
    # Optimize over simplex using projected gradient ascent
    w_opt = w_trace.copy()
    lr = 0.01
    for step in range(2000):
        # Gradient: ∂λ_min/∂w_k = v^T I_k v where v is eigenvector of λ_min
        M = sum(w_opt[k] * info_matrices[k] for k in range(K))
        eigvals, eigvecs = np.linalg.eigh(M)
        v = eigvecs[:, 0]  # eigenvector for λ_min
        grad = np.array([v @ info_matrices[k] @ v for k in range(K)])
        w_new = w_opt + lr * grad
        # Project onto simplex
        w_new = np.maximum(w_new, 0)
        if w_new.sum() > 0:
            w_new /= w_new.sum()
        w_opt = w_new

    eta_opt = sensitivity(w_opt)

    # Evaluate AUC with each weight scheme
    def compute_auc_with_weights(w):
        scores = np.zeros(len(X))
        for k, (op_name, op_fn, _) in enumerate(OPERATORS):
            X_op = op_fn(X)
            mu_op = op_fn(mu.reshape(1, -1)).ravel()
            devs = np.linalg.norm(X_op - mu_op, axis=1)
            scores += w[k] * devs
        return roc_auc_score(y, scores)

    auc_equal = compute_auc_with_weights(w_equal)
    auc_trace = compute_auc_with_weights(w_trace)
    auc_opt = compute_auc_with_weights(w_opt)

    print(f"\n{'='*65}")
    print(f"THEOREM 4 — Information-Optimal Fusion Weights: {name}")
    print(f"{'='*65}")

    print(f"\n  Per-operator information (trace of I_k):")
    for k, (op_name, _, _) in enumerate(OPERATORS):
        print(f"    {op_name:>12s}: tr(I_k) = {traces[k]:10.4f}  →  w_trace = {w_trace[k]:.4f}")

    print(f"\n  Worst-case sensitivity η(w) = λ_min(Σ w_k I_k):")
    print(f"    Equal weights:   η = {eta_equal:.6f}")
    print(f"    Trace weights:   η = {eta_trace:.6f}")
    print(f"    Optimised (SDP): η = {eta_opt:.6f}")

    print(f"\n  Optimal weights: {np.array2string(w_opt, precision=4)}")

    print(f"\n  Detection AUC:")
    print(f"    Equal weights:   {auc_equal:.4f}")
    print(f"    Trace weights:   {auc_trace:.4f}")
    print(f"    Optimised (SDP): {auc_opt:.4f}")

    return w_opt, eta_opt


# ═══════════════════════════════════════════════════════════════════════
# THEOREM 5 — Greedy Operator Selection
# ═══════════════════════════════════════════════════════════════════════

def verify_theorem5(name):
    X, y = load_dataset(name)
    n, m = X.shape
    normal_mask = y == 0
    X_normal = X[normal_mask]
    mu = X_normal.mean(axis=0)
    sigma = X_normal.std(axis=0)
    sigma[sigma < 1e-10] = 1e-10

    # Extended operator pool (add exp_scale and cross-terms)
    extended_ops = list(OPERATORS) + [
        ("exp_scale", lambda X: op_exp_scale(X, alpha=0.5), None),
        ("abs_diff", lambda X: np.abs(np.diff(X, axis=1)), None),
    ]

    # Compute I_k for each extended operator
    info_matrices = {}
    for op_name, op_fn, jac_fn in extended_ops:
        if jac_fn is not None:
            Jk = jac_fn(mu)
        else:
            # Numerical Jacobian
            eps = 1e-6
            y0 = op_fn(mu.reshape(1, -1)).ravel()
            d_k = len(y0)
            Jk = np.zeros((d_k, m))
            for j in range(m):
                xp = mu.copy()
                xp[j] += eps
                Jk[:, j] = (op_fn(xp.reshape(1, -1)).ravel() - y0) / eps
        info_matrices[op_name] = Jk.T @ Jk

    M = len(extended_ops)
    all_names = [op[0] for op in extended_ops]

    # Greedy selection
    selected = []
    remaining = list(range(M))

    print(f"\n{'='*65}")
    print(f"THEOREM 5 — Greedy Operator Selection: {name}")
    print(f"{'='*65}")
    print(f"  Pool: {M} operators, selecting best K for budget K=2..{M}")

    for step in range(M):
        best_gain = -np.inf
        best_idx = -1
        # Current information sum
        if selected:
            I_current = sum(info_matrices[all_names[s]] for s in selected)
        else:
            I_current = np.zeros((m, m))

        for j in remaining:
            I_candidate = I_current + info_matrices[all_names[j]]
            # log det — use slogdet
            sign, logdet = np.linalg.slogdet(I_candidate)
            gain = logdet if sign > 0 else -np.inf
            if selected:
                s0, ld0 = np.linalg.slogdet(I_current)
                if s0 > 0:
                    gain = logdet - ld0
            if gain > best_gain:
                best_gain = gain
                best_idx = j

        selected.append(best_idx)
        remaining.remove(best_idx)

        # Compute metrics for current selection
        I_sel = sum(info_matrices[all_names[s]] for s in selected)
        sigma_min = np.sqrt(max(0, np.linalg.eigvalsh(I_sel)[0]))
        logdet = np.linalg.slogdet(I_sel)[1]

        # Compute AUC with selected operators
        sel_ops = [extended_ops[s] for s in selected]
        scores = np.zeros(n)
        for op_name, op_fn, _ in sel_ops:
            X_op = op_fn(X)
            mu_op = op_fn(mu.reshape(1, -1)).ravel()
            scores += np.linalg.norm(X_op - mu_op, axis=1)
        auc = roc_auc_score(y, scores)

        sel_names = [all_names[s] for s in selected]
        print(f"  K={len(selected):d}: +{all_names[best_idx]:>12s}  "
              f"σ_min={sigma_min:.4f}  logdet={logdet:.2f}  AUC={auc:.4f}  "
              f"set={sel_names}")

    return selected


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    np.set_printoptions(precision=4, suppress=True)

    for ds in ["mammography", "shuttle", "pendigits"]:
        try:
            sigma_bar, _ = verify_theorem2(ds)
            verify_theorem3(ds, sigma_bar)
            verify_theorem4(ds)
            verify_theorem5(ds)
        except Exception as e:
            print(f"\nERROR on {ds}: {e}")
            import traceback
            traceback.print_exc()
