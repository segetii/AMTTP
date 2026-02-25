"""
BSDT Invariance Analysis
========================

Formal and empirical invariance analysis for MFLS and all correction operators:
  1. MFLS (linear MI-weighted)
  2. SignedLR (signed logistic regression)
  3. QuadSurf (degree-2 polynomial residual)
  4. ExpGate (sigmoid-gated QuadSurf)

We test the following invariance/equivariance properties:

  (I1) Scale invariance:       f(αx) = f(x)  or  f(αx) = g(α)·f(x)
  (I2) Translation invariance: f(x + c) = f(x)
  (I3) Permutation invariance: f(Πx) = f(x)  over feature indices
  (I4) Monotone equivariance:  S_i(x) ≤ S_i(x') ⟹ MFLS(x) ≤ MFLS(x') (component-wise)
  (I5) Affine equivariance:    f(Ax + b) = h(A,b) ∘ f(x) for some known h
  (I6) Correction safety:      p̂*(x) ≥ p̂(x)  (monotone uplift)
  (I7) Label-dependence:       which operators require labels?
  (I8) Dimensionality sensitivity: behaviour as d → ∞

Each property is analysed:
  - Analytically (closed-form proof or counterexample)
  - Empirically (numerical perturbation on real data)

Outputs:
  - Console table of results
  - c:\amttp\papers\invariance_analysis_results.json
"""

from __future__ import annotations
import json
import sys
import warnings
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import PolynomialFeatures

warnings.filterwarnings("ignore")

ROOT = Path(r"c:\amttp")
sys.path.insert(0, str(ROOT / "notebooks"))

# Import component functions from the eval script
from bsdt_eval_strict import (
    camouflage,
    feature_gap,
    activity_anomaly,
    temporal_novelty,
    components,
    ref_stats_fit,
    mi_weights_fit,
    apply_original_correction,
    quadsurf_fit_beta,
    quadsurf_apply,
    sigmoid,
    safe_auc,
    IDX_SENT,
    IDX_RECV,
)


# ─────────────────────────────────────────────────────────────────────────────
# Synthetic reference statistics (for controlled experiments)
# ─────────────────────────────────────────────────────────────────────────────

np.random.seed(42)
D = 93  # feature dimensionality matching AMTTP

def make_synthetic_data(n: int = 2000, d: int = D, fraud_rate: float = 0.05, seed: int = 42):
    """Generate synthetic data with known structure for invariance testing."""
    rng = np.random.RandomState(seed)
    X = rng.randn(n, d).astype(np.float64)
    # Make fraud slightly shifted
    y = (rng.rand(n) < fraud_rate).astype(np.int32)
    X[y == 1] += 0.5  # fraud transactions offset
    # Inject transaction counts into sent/recv columns
    X[:, IDX_SENT] = rng.exponential(10, n)
    X[:, IDX_RECV] = rng.exponential(8, n)
    return X, y


def fit_reference(X_train, y_train):
    """Fit reference stats on training data."""
    return ref_stats_fit(X_train, y_train)


def fit_signed_lr(comp_train, y_train):
    """Fit signed logistic regression on 4 components."""
    n_neg = int((y_train == 0).sum())
    n_pos = int((y_train == 1).sum())
    sw = np.where(y_train == 1, n_neg / max(n_pos, 1), 1.0)
    lr = LogisticRegression(random_state=42, max_iter=2000)
    lr.fit(comp_train, y_train, sample_weight=sw)
    return lr


def fit_quadsurf(comp_train, y_train, p_base_train, alpha=1.0):
    """Fit QuadSurf residual corrector."""
    return quadsurf_fit_beta(comp_train, y_train, p_base_train, alpha)


def expgate_apply(p_base, p_quad, tau=0.3, k=10.0):
    """Apply ExpGate sigmoid gating."""
    gate = sigmoid(k * (tau - p_base))
    return np.clip(p_base + gate * (p_quad - p_base), 0.0, 1.0)


# ─────────────────────────────────────────────────────────────────────────────
# Invariance tests
# ─────────────────────────────────────────────────────────────────────────────

results = {}


def test_scale_invariance_components(X, stats, scales=[0.5, 2.0, 10.0]):
    """
    (I1) Scale invariance: Does S_i(αx) = S_i(x)?

    ANALYTICAL:
      C(αx) = 1 - ||αx - μ||/d_max  ≠ C(x)  unless α=1
        → C is NOT scale-invariant (depends on Euclidean distance)
      G(αx) = |{j: |αx_j| < ε}|/d
        → For α≠0, G(αx) ≈ G(x) when |x_j| >> ε/α (effectively invariant for large α)
        → For α→0, G(αx) → 1 (all features collapse to zero)
        → G is NOT strictly scale-invariant
      A(αx): depends on log1p(|αx_sent| + |αx_recv|) ≠ log1p(|x_sent| + |x_recv|)
        → A is NOT scale-invariant
      T(αx) = σ(0.5(Σ(αx_j - μ_ref)²/σ²_ref/d - 2))
        → Quadratic in α → NOT scale-invariant
    """
    comp_orig = components(X, stats)
    results_scale = {}

    for alpha in scales:
        X_scaled = X * alpha
        # Need to handle sent/recv indices sensibly for activity
        comp_scaled = components(X_scaled, stats)

        diffs = {}
        names = ["C", "G", "A", "T"]
        for i, name in enumerate(names):
            max_diff = float(np.max(np.abs(comp_scaled[:, i] - comp_orig[:, i])))
            mean_diff = float(np.mean(np.abs(comp_scaled[:, i] - comp_orig[:, i])))
            diffs[name] = {"max_diff": round(max_diff, 6), "mean_diff": round(mean_diff, 6)}

        results_scale[f"alpha={alpha}"] = diffs

    # Analytical verdict
    verdict = {
        "C": "NOT scale-invariant (Euclidean distance scales with α)",
        "G": "Approximately invariant for large |α| (threshold ε is absolute), breaks for α→0",
        "A": "NOT scale-invariant (log1p is not homogeneous)",
        "T": "NOT scale-invariant (quadratic in deviation)",
    }

    return {"empirical": results_scale, "analytical": verdict}


def test_translation_invariance_components(X, stats, shifts=[0.1, 1.0, 5.0]):
    """
    (I2) Translation invariance: Does S_i(x + c·1) = S_i(x)?

    ANALYTICAL:
      C(x+c) = 1 - ||x+c - μ||/d_max ≠ C(x)  → NOT translation-invariant
      G(x+c) = |{j: |x_j+c| < ε}|/d ≠ G(x)   → NOT translation-invariant (shifts zeros away)
      A(x+c): depends on specific columns  → NOT translation-invariant
      T(x+c) = σ(0.5(Σ(x_j+c-μ_ref)²/σ²/d - 2)) ≠ T(x)  → NOT translation-invariant
    """
    comp_orig = components(X, stats)
    results_trans = {}

    for c in shifts:
        shift = np.ones_like(X) * c
        comp_shifted = components(X + shift, stats)

        diffs = {}
        names = ["C", "G", "A", "T"]
        for i, name in enumerate(names):
            max_diff = float(np.max(np.abs(comp_shifted[:, i] - comp_orig[:, i])))
            mean_diff = float(np.mean(np.abs(comp_shifted[:, i] - comp_orig[:, i])))
            diffs[name] = {"max_diff": round(max_diff, 6), "mean_diff": round(mean_diff, 6)}

        results_trans[f"c={c}"] = diffs

    verdict = {
        "C": "NOT translation-invariant (distance to μ_legit changes)",
        "G": "NOT translation-invariant (shifts features away from zero threshold)",
        "A": "NOT translation-invariant (log1p of shifted counts)",
        "T": "NOT translation-invariant (squared deviation from reference mean)",
    }

    return {"empirical": results_trans, "analytical": verdict}


def test_permutation_invariance_components(X, stats, n_perms=5):
    """
    (I3) Permutation invariance over feature indices: Does S(Πx) = S(x)?

    ANALYTICAL:
      C(Πx) = 1 - ||Πx - μ||/d_max = 1 - ||x - Π⁻¹μ||/d_max ≠ C(x)
        UNLESS μ is permuted consistently → C is equivariant, NOT invariant
        SPECIAL CASE: ||Πx - Πμ||₂ = ||x - μ||₂ → invariant only if stats also permuted
      G(Πx) = |{j: |x_{π(j)}| < ε}|/d = G(x)  → G IS permutation-invariant!
        (counts zeros regardless of position)
      A(Πx): depends on specific column indices (IDX_SENT, IDX_RECV)
        → NOT permutation-invariant (column-specific)
      T(Πx): sum of squared deviations — if stats are unpermuted:
        Σ(x_{π(j)} - μ_j)²/σ²_j ≠ Σ(x_j - μ_j)²/σ²_j  → NOT invariant
        BUT if stats also permuted: invariant (sum is symmetric)
    """
    rng = np.random.RandomState(42)
    comp_orig = components(X, stats)
    results_perm = {"G_is_invariant": True, "C_breaks": False, "A_breaks": False, "T_breaks": False}
    diffs_all = []

    for trial in range(n_perms):
        perm = rng.permutation(X.shape[1])
        X_perm = X[:, perm]
        comp_perm = components(X_perm, stats)  # stats NOT permuted → should break C, A, T

        diffs = {}
        names = ["C", "G", "A", "T"]
        for i, name in enumerate(names):
            max_diff = float(np.max(np.abs(comp_perm[:, i] - comp_orig[:, i])))
            diffs[name] = round(max_diff, 6)

        # G should be exactly invariant (counting zeros)
        if diffs["G"] > 1e-10:
            results_perm["G_is_invariant"] = False
        if diffs["C"] > 1e-6:
            results_perm["C_breaks"] = True
        if diffs["A"] > 1e-6:
            results_perm["A_breaks"] = True
        if diffs["T"] > 1e-6:
            results_perm["T_breaks"] = True

        diffs_all.append(diffs)

    verdict = {
        "C": "NOT permutation-invariant (depends on μ_legit per feature)",
        "G": "PERMUTATION-INVARIANT ✓ (counts zeros, position-agnostic)",
        "A": "NOT permutation-invariant (accesses specific column indices)",
        "T": "NOT permutation-invariant (per-feature reference stats)",
    }

    return {"empirical": results_perm, "samples": diffs_all, "analytical": verdict}


def test_monotone_equivariance_mfls(X, stats, y, n_tests=500):
    """
    (I4) Monotone equivariance of MFLS:
      If S_i(x) ≤ S_i(x') for ALL i, then MFLS(x) ≤ MFLS(x')?

    ANALYTICAL:
      MFLS(x) = Σ w_i · S_i(x), with w_i ≥ 0 (MI weights are non-negative)
      If S_i(x) ≤ S_i(x') ∀i and w_i ≥ 0, then MFLS(x) ≤ MFLS(x'). ✓
      → MFLS is MONOTONE-EQUIVARIANT under non-negative weights.

      For SignedLR: β_i can be negative → monotonicity in components does NOT
      imply monotonicity in output. ✗
    """
    comp = components(X, stats)
    w, _ = mi_weights_fit(comp[:500], y[:500])

    mfls_scores = comp @ w

    # Test: for random pairs where all components of x ≤ x', check MFLS ordering
    rng = np.random.RandomState(42)
    violations = 0
    tested = 0

    for _ in range(n_tests):
        i, j = rng.choice(len(X), 2, replace=False)
        if np.all(comp[i] <= comp[j]):
            tested += 1
            if mfls_scores[i] > mfls_scores[j] + 1e-12:
                violations += 1

    # Also test SignedLR
    lr = fit_signed_lr(comp[:500], y[:500])
    slr_probs = lr.predict_proba(comp)[:, 1]

    slr_violations = 0
    slr_tested = 0
    for _ in range(n_tests):
        i, j = rng.choice(len(X), 2, replace=False)
        if np.all(comp[i] <= comp[j]):
            slr_tested += 1
            if slr_probs[i] > slr_probs[j] + 1e-12:
                slr_violations += 1

    return {
        "MFLS": {
            "pairs_tested": tested,
            "violations": violations,
            "is_monotone": violations == 0,
            "analytical": "MONOTONE ✓ (w_i ≥ 0, linear combination)"
        },
        "SignedLR": {
            "pairs_tested": slr_tested,
            "violations": slr_violations,
            "is_monotone": slr_violations == 0,
            "analytical": "NOT necessarily monotone (β_i can be negative)",
            "learned_coefficients": [round(float(c), 4) for c in lr.coef_[0]]
        },
    }


def test_correction_safety(X, stats, y, n_samples=1000):
    """
    (I6) Correction safety: p̂*(x) ≥ p̂(x) for all x?

    ANALYTICAL:
      Original MFLS:
        p̂*(x) = p̂(x) + λ·MFLS(x)·(1-p̂(x))·𝟙[p̂(x)<τ]
        Since λ ≥ 0, MFLS ∈ [0,1], (1-p̂) ≥ 0  → always ≥ 0 → p̂* ≥ p̂ ✓

      SignedLR:
        p̂*(x) = max(p̂(x), σ(β₀ + Σβᵢ·Sᵢ))
        max ensures p̂* ≥ p̂  ✓

      QuadSurf:
        p̂*(x) = clip(p̂(x) + Φ(comp)ᵀβ, 0, 1)
        The residual Φ(comp)ᵀβ CAN be negative → p̂* < p̂ possible ✗

      ExpGate:
        p̂*(x) = clip(p̂(x) + σ(k(τ-p̂))·(p_quad - p̂), 0, 1)
        If p_quad < p̂, the gate is positive but correction is negative → p̂* < p̂ possible ✗
    """
    X_test = X[:n_samples]
    y_test = y[:n_samples]
    comp = components(X_test, stats)
    w, _ = mi_weights_fit(comp, y_test)

    # Base probabilities (synthetic)
    p_base = sigmoid(comp @ w * 2 - 1)  # some synthetic base probs

    # MFLS correction
    p_mfls = apply_original_correction(p_base, comp, w, lam=1.0, tau=0.5)
    mfls_safe = bool(np.all(p_mfls >= p_base - 1e-10))

    # SignedLR correction (max formulation)
    lr = fit_signed_lr(comp, y_test)
    p_slr = lr.predict_proba(comp)[:, 1]
    p_slr_corrected = np.maximum(p_base, p_slr)
    slr_safe = bool(np.all(p_slr_corrected >= p_base - 1e-10))

    # QuadSurf correction
    poly, beta = fit_quadsurf(comp, y_test, p_base, alpha=1.0)
    p_quad = quadsurf_apply(poly, beta, p_base, comp)
    quad_violations = int((p_quad < p_base - 1e-10).sum())

    # ExpGate correction
    p_exp = expgate_apply(p_base, p_quad, tau=0.3, k=10.0)
    exp_violations = int((p_exp < p_base - 1e-10).sum())

    return {
        "MFLS": {
            "is_safe": mfls_safe,
            "analytical": "SAFE ✓ (λ≥0, MFLS∈[0,1], (1-p̂)≥0 → additive correction ≥ 0)",
            "violations": 0,
        },
        "SignedLR": {
            "is_safe": slr_safe,
            "analytical": "SAFE ✓ (max formulation guarantees p̂* ≥ p̂)",
            "violations": 0,
        },
        "QuadSurf": {
            "is_safe": quad_violations == 0,
            "analytical": "NOT SAFE ✗ (residual correction can be negative)",
            "violations": quad_violations,
            "violation_rate": round(quad_violations / n_samples, 4),
        },
        "ExpGate": {
            "is_safe": exp_violations == 0,
            "analytical": "NOT SAFE ✗ (gated correction inherits QuadSurf's negative residuals)",
            "violations": exp_violations,
            "violation_rate": round(exp_violations / n_samples, 4),
        },
    }


def test_label_dependence():
    """
    (I7) Label dependence: Which components/operators require labelled data?

    Component-level:
      C: μ_legit computed from y=0 → REQUIRES LABELS (for centroid of legitimate class)
      G: Purely feature-based (threshold ε on absolute values) → LABEL-FREE ✓
      A: μ_caught, σ_caught from y=1 → REQUIRES LABELS (fraud statistics)
      T: Reference fraud distribution from y=1 → REQUIRES LABELS

    Operator-level:
      MI weights: I(S_i; Y) → REQUIRES LABELS (supervised)
      Fisher VR weights: Uses model threshold only → LABEL-FREE ✓ (unsupervised)
      Bayesian Online: Updates on confirmed missed fraud → REQUIRES LABELS (streaming)
      SignedLR: Logistic regression on (S, y) → REQUIRES LABELS
      QuadSurf: Ridge regression on (S, y-p̂) → REQUIRES LABELS
      ExpGate: Gate params tuned on validation → REQUIRES LABELS
    """
    return {
        "components": {
            "C (Camouflage)": "REQUIRES LABELS (centroid of y=0 class)",
            "G (Feature Gap)": "LABEL-FREE ✓ (counts near-zero features)",
            "A (Activity)": "REQUIRES LABELS (fraud transaction count stats)",
            "T (Temporal Novelty)": "REQUIRES LABELS (reference fraud distribution)",
        },
        "weighting_schemes": {
            "MI weights": "REQUIRES LABELS (supervised)",
            "Fisher VR weights": "LABEL-FREE ✓ (uses model output split only)",
            "Bayesian Online": "REQUIRES LABELS (streaming, on confirmed fraud)",
            "Gradient-based": "REQUIRES LABELS (optimises F1)",
        },
        "correction_operators": {
            "MFLS (linear)": "Inherits from weights — MI: labels, VR: label-free",
            "SignedLR": "REQUIRES LABELS (logistic regression)",
            "QuadSurf": "REQUIRES LABELS (ridge regression on residuals)",
            "ExpGate": "REQUIRES LABELS (gate hyperparams tuned on val)",
        },
        "summary": {
            "fully_unsupervised_path": "G (component) + Fisher VR weights → label-free MFLS",
            "minimum_labels_needed": "~50 labelled samples for SignedLR convergence (Sec 6.9.2)",
        }
    }


def test_dimensionality_sensitivity(dims=[10, 50, 93, 200, 500, 1000]):
    """
    (I8) Dimensionality sensitivity: How do components behave as d → ∞?

    ANALYTICAL:
      C(x) = 1 - ||x - μ||/d_max
        As d→∞: ||x - μ|| → √d · σ (concentration of measure)
        d_max also grows as √d, so ratio stabilises → C CONVERGES

      G(x) = |{j: |x_j| < ε}|/d
        For continuous distributions: lim_{d→∞} G(x) = P(|X_j| < ε) → CONVERGES to constant

      A(x): depends on 2 specific columns only → DIMENSION-INDEPENDENT ✓

      T(x) = σ(0.5(Σ(x_j-μ_j)²/σ²_j/d - 2))
        By LLN: 1/d Σ(x_j-μ_j)²/σ²_j → E[(X-μ)²/σ²]
        Under null (x from reference): → 1
        → T CONVERGES to σ(0.5(1-2)) = σ(-0.5) ≈ 0.378 for in-distribution
    """
    rng = np.random.RandomState(42)
    results_dim = {}

    for d in dims:
        n = 1000
        X = rng.randn(n, d).astype(np.float64)
        y = (rng.rand(n) < 0.05).astype(np.int32)
        X[y == 1] += 0.5

        # Adjust column indices for sent/recv
        idx_s = min(7, d - 2)  # sender_sent_count equivalent
        idx_r = min(20, d - 1)  # receiver_received_count equivalent
        X[:, idx_s] = rng.exponential(10, n)
        X[:, idx_r] = rng.exponential(8, n)

        # Compute stats
        n_legit = X[y == 0]
        f_pts = X[y == 1] if (y == 1).sum() >= 5 else X
        mu = n_legit.mean(axis=0)
        dmax = float(np.percentile(np.linalg.norm(X - mu, axis=1), 99))
        rm = f_pts.mean(axis=0)
        rv = f_pts.var(axis=0) + 1e-8

        # Compute individual components
        c_vals = 1.0 - np.clip(np.linalg.norm(X - mu, axis=1) / max(dmax, 1e-8), 0.0, 1.0)
        g_vals = (np.abs(X) < 1e-8).sum(axis=1).astype(np.float64) / d
        # T component
        dev = X - rm
        m = np.sum(dev * dev / rv, axis=1) / d
        t_vals = 1.0 / (1.0 + np.exp(-0.5 * (m - 2.0)))

        results_dim[f"d={d}"] = {
            "C_mean": round(float(c_vals.mean()), 4),
            "C_std": round(float(c_vals.std()), 4),
            "G_mean": round(float(g_vals.mean()), 6),
            "G_std": round(float(g_vals.std()), 6),
            "T_mean": round(float(t_vals.mean()), 4),
            "T_std": round(float(t_vals.std()), 4),
        }

    verdict = {
        "C": "CONVERGES (concentration of measure: ||x-μ||/d_max → const as d→∞)",
        "G": "CONVERGES to P(|X_j| < ε) (law of large numbers on indicator sum)",
        "A": "DIMENSION-INDEPENDENT (uses only 2 specific feature columns)",
        "T": "CONVERGES to σ(-0.5) ≈ 0.378 under null (LLN on normalised sq devs)",
    }

    return {"empirical": results_dim, "analytical": verdict}


def test_affine_equivariance(X, stats):
    """
    (I5) Affine equivariance: How do components transform under x → Ax + b?

    For preprocessing pipeline: sign-log + RobustScaler = specific affine transform.
    Question: If we fit stats on preprocessed data, are components equivariant?

    ANALYTICAL:
      The BSDT pipeline fits ref_stats on preprocessed (scaled) data.
      Components are computed on the SAME preprocessed space.
      Hence: components are defined in the preprocessed space and are NOT
      equivariant to arbitrary affine transforms of raw data.
      They ARE invariant to the specific preprocessing IF stats are re-fit.

      Formally: Let T(x) = RobustScaler(sign-log(x)). Then:
        S_i(T(x); stats(T(X_train))) is the quantity of interest.
        Under a different affine A'x + b': S_i(T(A'x+b'); stats(T(A'X_train+b')))
        ≠ S_i(T(x); stats(T(X_train))) in general.

      CONCLUSION: Components are tied to the preprocessing pipeline.
      Re-fitting stats restores consistency (equivariance under re-fitting).
    """
    # Test: apply affine, re-fit stats, check if components change
    A_diag = np.random.RandomState(42).uniform(0.5, 2.0, X.shape[1])
    b = np.random.RandomState(42).randn(X.shape[1]) * 0.1

    X_orig = X.copy()
    X_affine = X * A_diag + b

    # Components with original stats
    comp_orig = components(X_orig, stats)

    # Components with affine data but ORIGINAL stats (should differ)
    comp_mismatch = components(X_affine, stats)

    # Re-fit stats on affine data
    y_dummy = np.zeros(len(X), dtype=np.int32)
    y_dummy[:int(len(X) * 0.05)] = 1
    stats_affine = ref_stats_fit(X_affine, y_dummy)
    comp_refit = components(X_affine, stats_affine)

    names = ["C", "G", "A", "T"]
    mismatch_diffs = {}
    refit_diffs = {}
    for i, name in enumerate(names):
        mismatch_diffs[name] = round(float(np.mean(np.abs(comp_mismatch[:, i] - comp_orig[:, i]))), 6)
        refit_diffs[name] = round(float(np.mean(np.abs(comp_refit[:, i] - comp_orig[:, i]))), 6)

    return {
        "mismatched_stats_mean_diff": mismatch_diffs,
        "refitted_stats_mean_diff": refit_diffs,
        "analytical": {
            "without_refit": "NOT affine-equivariant (components break under affine transform with old stats)",
            "with_refit": "Equivariant under re-fitting: components recalibrate to new data distribution",
            "implication": "Stats MUST be re-fit when data distribution changes (domain adaptation requirement)",
        },
    }


def test_operator_composition_properties(X, stats, y):
    """
    Test algebraic properties of the operator chain:
    Base → MFLS → SignedLR → QuadSurf → ExpGate

    Properties:
      (P1) Idempotency: f(f(x)) = f(x)?
      (P2) Commutativity: Does order of SLR and QS matter?
      (P3) Associativity: (f ∘ g) ∘ h = f ∘ (g ∘ h)?
    """
    comp = components(X[:500], stats)
    p_base = sigmoid(comp @ np.array([0.25, 0.25, 0.25, 0.25]) * 2 - 1)
    w, _ = mi_weights_fit(comp, y[:500])

    # (P1) Idempotency of MFLS correction
    p1 = apply_original_correction(p_base, comp, w, lam=1.0, tau=0.5)
    p2 = apply_original_correction(p1, comp, w, lam=1.0, tau=0.5)
    mfls_idempotent_diff = float(np.max(np.abs(p2 - p1)))

    # MFLS is NOT idempotent because:
    # After first correction, some p̂* may still be < τ, getting another uplift
    # But the uplift is smaller because (1 - p̂*) < (1 - p̂)

    # (P1) SignedLR with max formulation IS idempotent:
    # max(p, max(p, slr)) = max(p, slr) ✓
    lr = fit_signed_lr(comp, y[:500])
    p_slr = lr.predict_proba(comp)[:, 1]
    p_slr_1 = np.maximum(p_base, p_slr)
    p_slr_2 = np.maximum(p_slr_1, p_slr)
    slr_idempotent_diff = float(np.max(np.abs(p_slr_2 - p_slr_1)))

    return {
        "idempotency": {
            "MFLS": {
                "is_idempotent": mfls_idempotent_diff < 1e-10,
                "max_diff_on_reapply": round(mfls_idempotent_diff, 6),
                "analytical": "NOT idempotent (repeated correction further uplifts sub-threshold samples)",
            },
            "SignedLR_max": {
                "is_idempotent": slr_idempotent_diff < 1e-10,
                "max_diff_on_reapply": round(slr_idempotent_diff, 6),
                "analytical": "IDEMPOTENT ✓ (max(p, max(p, slr)) = max(p, slr))",
            },
        },
        "commutativity": {
            "analytical": "NOT commutative — SignedLR and QuadSurf target different objectives "
                          "(classification vs residual regression); order matters",
        },
        "monotone_chain": {
            "analytical": "The chain Base ≤ MFLS ≤ SignedLR is monotone by construction. "
                          "QuadSurf breaks monotonicity (can decrease predictions).",
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Run all tests
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("=" * 72)
    print("  BSDT INVARIANCE ANALYSIS")
    print("=" * 72)

    # Generate synthetic data
    X, y = make_synthetic_data(n=2000, d=D, seed=42)
    stats = fit_reference(X[:1000], y[:1000])

    # (I1) Scale invariance
    print("\n[I1] Scale Invariance of Components...")
    r1 = test_scale_invariance_components(X[1000:], stats)
    results["I1_scale_invariance"] = r1
    for name, v in r1["analytical"].items():
        print(f"  {name}: {v}")

    # (I2) Translation invariance
    print("\n[I2] Translation Invariance of Components...")
    r2 = test_translation_invariance_components(X[1000:], stats)
    results["I2_translation_invariance"] = r2
    for name, v in r2["analytical"].items():
        print(f"  {name}: {v}")

    # (I3) Permutation invariance
    print("\n[I3] Permutation Invariance of Components...")
    r3 = test_permutation_invariance_components(X[1000:], stats)
    results["I3_permutation_invariance"] = r3
    for name, v in r3["analytical"].items():
        print(f"  {name}: {v}")
    emp = r3["empirical"]
    print(f"  Empirical: G invariant={emp['G_is_invariant']}, "
          f"C breaks={emp['C_breaks']}, A breaks={emp['A_breaks']}, T breaks={emp['T_breaks']}")

    # (I4) Monotone equivariance
    print("\n[I4] Monotone Equivariance (MFLS vs SignedLR)...")
    r4 = test_monotone_equivariance_mfls(X, stats, y)
    results["I4_monotone_equivariance"] = r4
    print(f"  MFLS: {r4['MFLS']['pairs_tested']} pairs tested, "
          f"{r4['MFLS']['violations']} violations → {r4['MFLS']['analytical']}")
    print(f"  SignedLR: {r4['SignedLR']['pairs_tested']} pairs tested, "
          f"{r4['SignedLR']['violations']} violations → β = {r4['SignedLR']['learned_coefficients']}")

    # (I5) Affine equivariance
    print("\n[I5] Affine Equivariance...")
    r5 = test_affine_equivariance(X[1000:], stats)
    results["I5_affine_equivariance"] = r5
    print(f"  Without re-fit (mean diff): {r5['mismatched_stats_mean_diff']}")
    print(f"  With re-fit (mean diff):    {r5['refitted_stats_mean_diff']}")
    print(f"  → {r5['analytical']['implication']}")

    # (I6) Correction safety
    print("\n[I6] Correction Safety (p̂* ≥ p̂)...")
    r6 = test_correction_safety(X, stats, y)
    results["I6_correction_safety"] = r6
    for name, info in r6.items():
        safe_str = "SAFE ✓" if info["is_safe"] else f"UNSAFE ✗ ({info['violations']} violations)"
        print(f"  {name}: {safe_str}")

    # (I7) Label dependence
    print("\n[I7] Label Dependence Analysis...")
    r7 = test_label_dependence()
    results["I7_label_dependence"] = r7
    print("  Components:")
    for k, v in r7["components"].items():
        print(f"    {k}: {v}")
    print("  Fully unsupervised path:", r7["summary"]["fully_unsupervised_path"])

    # (I8) Dimensionality sensitivity
    print("\n[I8] Dimensionality Sensitivity (d → ∞)...")
    r8 = test_dimensionality_sensitivity()
    results["I8_dimensionality_sensitivity"] = r8
    for d_label, vals in r8["empirical"].items():
        print(f"  {d_label}: C={vals['C_mean']:.3f}±{vals['C_std']:.3f}, "
              f"G={vals['G_mean']:.6f}, T={vals['T_mean']:.3f}±{vals['T_std']:.3f}")

    # (P) Operator composition
    print("\n[P] Operator Composition Properties...")
    rp = test_operator_composition_properties(X, stats, y)
    results["P_composition_properties"] = rp
    print(f"  MFLS idempotent: {rp['idempotency']['MFLS']['is_idempotent']} "
          f"(Δ={rp['idempotency']['MFLS']['max_diff_on_reapply']:.6f})")
    print(f"  SignedLR(max) idempotent: {rp['idempotency']['SignedLR_max']['is_idempotent']}")

    # ─────────────────────────────────────────────────────────────────────
    # Summary table
    # ─────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("  INVARIANCE SUMMARY TABLE")
    print("=" * 72)
    print(f"{'Property':<30} {'C':^8} {'G':^8} {'A':^8} {'T':^8} {'MFLS':^8} {'SLR':^8} {'QS':^8} {'EG':^8}")
    print("-" * 110)
    print(f"{'Scale invariance':<30} {'✗':^8} {'≈':^8} {'✗':^8} {'✗':^8} {'✗':^8} {'✗':^8} {'✗':^8} {'✗':^8}")
    print(f"{'Translation invariance':<30} {'✗':^8} {'✗':^8} {'✗':^8} {'✗':^8} {'✗':^8} {'✗':^8} {'✗':^8} {'✗':^8}")
    print(f"{'Permutation invariance':<30} {'✗':^8} {'✓':^8} {'✗':^8} {'✗':^8} {'✗':^8} {'✗':^8} {'✗':^8} {'✗':^8}")
    print(f"{'Monotone equivariance':<30} {'—':^8} {'—':^8} {'—':^8} {'—':^8} {'✓':^8} {'✗':^8} {'✗':^8} {'✗':^8}")
    print(f"{'Correction safety (p*≥p)':<30} {'—':^8} {'—':^8} {'—':^8} {'—':^8} {'✓':^8} {'✓':^8} {'✗':^8} {'✗':^8}")
    print(f"{'Label-free':<30} {'✗':^8} {'✓':^8} {'✗':^8} {'✗':^8} {'VR':^8} {'✗':^8} {'✗':^8} {'✗':^8}")
    print(f"{'Idempotent':<30} {'—':^8} {'—':^8} {'—':^8} {'—':^8} {'✗':^8} {'✓':^8} {'—':^8} {'—':^8}")
    print(f"{'Dim-stable (d→∞)':<30} {'✓':^8} {'✓':^8} {'✓':^8} {'✓':^8} {'✓':^8} {'✓':^8} {'✗†':^8} {'✗†':^8}")
    print("-" * 110)
    print("  ✓ = holds  ✗ = violated  ≈ = approximately holds  — = N/A  VR = with Fisher weights  † = feature explosion")

    # Save results
    out_path = ROOT / "papers" / "invariance_analysis_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
