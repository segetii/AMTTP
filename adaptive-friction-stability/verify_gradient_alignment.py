"""
Gradient Alignment Verification — Action 2 of 08_UNIFIED_PAPER.md
==================================================================
Numerically verifies the central claim of Theorem C:

    ∇E_BS(X) and −∇Φ(X) point in the same direction.

That is, the blind-spot energy gradient (computed from BSDT-style
deviation operators fitted on normal data) is aligned with the
restoring force of GravityEngine's potential (computed from the
actual simulation force field).

We measure the alignment angle
    cos θ(t) = ⟨∇E_BS(X(t)), −∇Φ(X(t))⟩
               ─────────────────────────────
               ‖∇E_BS(X(t))‖ · ‖−∇Φ(X(t))‖

at each step as the system evolves.  Theorem C predicts cos θ > 0.7
on average.  If this fails, the theorem needs re-scoping.

Setup
-----
- N=50 agents, d=4 dimensions
- Normal reference: X₀ ~ N(0, I_{N×d})
- BSDT operators: simplified as standardised Mahalanobis deviation
  (this is the core of all four BSDT operators — C, G, A, T — each
  of which is a different projection of deviation from normality)
- E_BS(X) = Σᵢ ψ(δᵢ(X)) + Σᵢ<ⱼ φ(‖Xᵢ−Xⱼ‖)   [blind-spot energy]
       Φ(X) = (α/2)Σᵢ‖xᵢ−μ‖² + pairwise         [GravityEngine potential]

Output
------
- cos_theta_history.json  — alignment per step
- alignment_plot.png       — visualisation
- alignment_summary.txt    — pass/fail verdict with statistics
"""

import sys
import os
import json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

# Allow importing udl from the repo root
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))

try:
    from udl.gravity import total_force, radial_pull, pairwise_forces
    GRAVITY_AVAILABLE = True
except ImportError:
    GRAVITY_AVAILABLE = False
    print("[warn] udl.gravity not importable — using local reimplementation")


# ─────────────────────────────────────────────
# Experiment parameters
# ─────────────────────────────────────────────
RNG_SEED   = 42
N_AGENTS   = 50
D_DIM      = 4
N_STEPS    = 200        # simulation steps
ETA        = 0.02       # step size

# GravityEngine parameters (match defaults in gravity.py)
ALPHA      = 0.1        # radial spring
GAMMA      = 1.0        # pairwise coupling
SIGMA      = 1.0        # attraction length-scale
LAMBDA_REP = 0.1        # repulsion coefficient
EPS        = 1e-5       # softening

# BSDT / blind-spot energy parameters
PSI_SCALE  = 1.0        # ψ(δ) = PSI_SCALE · δ²  (convex, increasing)
OUTPUT_DIR = Path(__file__).parent / "alignment_results"


# ─────────────────────────────────────────────
# Blind-spot energy and its gradient
# ─────────────────────────────────────────────

class BSDTEnergyOperator:
    """
    Simplified BSDT blind-spot energy.

    Fits a reference distribution N on normal data X_normal.
    Computes E_BS(X) = Σᵢ ψ(δᵢ(X)) + pairwise(X)

    The deviation operator δᵢ(X) is the squared Mahalanobis distance
    of agent i from the normal reference:
        δᵢ(X) = (xᵢ − μ₀)ᵀ Σ₀⁻¹ (xᵢ − μ₀)

    This is the algebraic core of all four BSDT operators.  Each
    operator (Camouflage, Feature Gap, Activity Anomaly, Temporal Novelty)
    applies a different linear projection before computing the Mahalanobis
    distance; their sum is upper/lower bounded by multiples of this
    combined form.

    ψ(δ) = δ  (identity: convex, increasing, 1-Lipschitz)
    """

    def __init__(self, alpha=ALPHA, gamma=GAMMA, sigma=SIGMA,
                 lambda_rep=LAMBDA_REP, eps=EPS, psi_scale=PSI_SCALE):
        self.alpha = alpha
        self.gamma = gamma
        self.sigma = sigma
        self.lambda_rep = lambda_rep
        self.eps = eps
        self.psi_scale = psi_scale
        # Fitted on normal data
        self.mu0_ = None
        self.Sigma0_inv_ = None

    def fit(self, X_normal: np.ndarray):
        """Fit reference distribution from N×d normal data."""
        self.mu0_ = X_normal.mean(axis=0)           # (d,)
        cov = np.cov(X_normal.T) + 1e-6 * np.eye(X_normal.shape[1])
        self.Sigma0_inv_ = np.linalg.inv(cov)        # (d, d)
        return self

    def deviation(self, X: np.ndarray) -> np.ndarray:
        """
        δᵢ(X) = (xᵢ − μ₀)ᵀ Σ₀⁻¹ (xᵢ − μ₀)   shape (N,)
        """
        z = X - self.mu0_                           # (N, d)
        return np.sum(z @ self.Sigma0_inv_ * z, axis=1)  # (N,)

    def energy(self, X: np.ndarray) -> float:
        """E_BS(X) = Σᵢ ψ(δᵢ) + Σᵢ<ⱼ γ·erf-potential"""
        from scipy.special import erf as _erf
        delta = self.deviation(X)                   # (N,)
        E_dev = self.psi_scale * np.sum(delta)

        # Pairwise term — same formula as GravityEngine
        n = X.shape[0]
        diff = X[:, None, :] - X[None, :, :]        # (N, N, d)
        dist = np.linalg.norm(diff, axis=2) + self.eps  # (N, N)
        np.fill_diagonal(dist, self.eps)
        s = self.sigma
        E_att = 0.5 * self.gamma * (s * np.sqrt(np.pi) * 0.5) * np.sum(_erf(dist / s))
        E_rep = -0.5 * self.gamma * self.lambda_rep * np.sum(np.log(dist))
        # Remove self-interaction diagonal
        E_att -= n * self.gamma * (s * np.sqrt(np.pi) * 0.5) * _erf(0.0)
        E_rep += n * self.gamma * self.lambda_rep * np.log(self.eps)
        return float(E_dev + E_att + E_rep)

    def gradient(self, X: np.ndarray) -> np.ndarray:
        """
        ∇_X E_BS(X)  shape (N, d)

        Deviation term: ∂/∂xᵢ [ψ(δᵢ)] = ψ'(δᵢ) · 2Σ₀⁻¹(xᵢ − μ₀)
        For ψ(δ) = δ: ψ'(δ) = 1, so:
            ∂E_dev/∂xᵢ = 2Σ₀⁻¹(xᵢ − μ₀)

        Pairwise term: same as GravityEngine ∇Φ_pair, computed via
        finite differences (exact formula would duplicate gravity.py).
        """
        N, d = X.shape

        # ── Deviation gradient (analytic) ──
        z = X - self.mu0_                           # (N, d)
        grad_dev = self.psi_scale * 2.0 * (z @ self.Sigma0_inv_.T)  # (N, d)

        # ── Pairwise gradient (finite differences, step h) ──
        # We reuse the same force functions from gravity.py so the
        # pairwise terms are *identical* between E_BS and Φ — they
        # cancel in the alignment test, making the test conservative:
        # alignment is driven entirely by the deviation vs. radial terms.
        h = 1e-5
        grad_pair = np.zeros_like(X)
        for i in range(N):
            for j in range(d):
                Xp = X.copy(); Xp[i, j] += h
                Xm = X.copy(); Xm[i, j] -= h
                grad_pair[i, j] = (self._pairwise_energy(Xp) -
                                   self._pairwise_energy(Xm)) / (2 * h)

        return grad_dev + grad_pair

    def _pairwise_energy(self, X: np.ndarray) -> float:
        from scipy.special import erf as _erf
        n = X.shape[0]
        diff = X[:, None, :] - X[None, :, :]
        dist = np.linalg.norm(diff, axis=2) + self.eps
        np.fill_diagonal(dist, self.eps)
        s = self.sigma
        E_att = 0.5 * self.gamma * (s * np.sqrt(np.pi) * 0.5) * np.sum(_erf(dist / s))
        E_rep = -0.5 * self.gamma * self.lambda_rep * np.sum(np.log(dist))
        E_att -= n * self.gamma * (s * np.sqrt(np.pi) * 0.5) * _erf(0.0)
        E_rep += n * self.gamma * self.lambda_rep * np.log(self.eps)
        return float(E_att + E_rep)

    def gradient_fast(self, X: np.ndarray) -> np.ndarray:
        """
        Faster gradient: analytic deviation term + analytic pairwise term.

        The pairwise force from gravity.py is -∇Φ_pair, so ∇E_BS_pair = +∇Φ_pair
        (i.e. the negative of the force).  We compute the force via total_force
        minus the radial component, then negate.
        """
        N, d = X.shape
        mu = X.mean(axis=0)

        # Analytic deviation gradient
        z = X - self.mu0_
        grad_dev = self.psi_scale * 2.0 * (z @ self.Sigma0_inv_.T)  # (N, d)

        if GRAVITY_AVAILABLE:
            # Get pairwise force from gravity.py (= -∇Φ_pair)
            F_rad = radial_pull(X, mu, self.alpha)
            F_pair, _ = pairwise_forces(X, self.gamma, self.sigma,
                                        self.lambda_rep, self.eps)
            # ∇E_BS_pair = -F_pair  (force = -gradient)
            grad_pair = -F_pair
        else:
            grad_pair = np.zeros_like(X)

        return grad_dev + grad_pair


# ─────────────────────────────────────────────
# GravityEngine force: −∇Φ(X)
# ─────────────────────────────────────────────

def gravity_force(X: np.ndarray, mu: np.ndarray) -> np.ndarray:
    """Total GravityEngine force = −∇Φ(X).  Shape (N, d)."""
    if GRAVITY_AVAILABLE:
        F, _ = total_force(X, mu, alpha=ALPHA, gamma=GAMMA,
                           sigma=SIGMA, lambda_rep=LAMBDA_REP, eps=EPS)
        return F
    else:
        # Fallback: local reimplementation
        F = -ALPHA * (X - mu)
        diff = X[:, None, :] - X[None, :, :]
        dist = np.linalg.norm(diff, axis=2, keepdims=True) + EPS
        att = np.exp(-(dist**2) / (SIGMA**2))
        rep = LAMBDA_REP / dist
        mag = -GAMMA * (att - rep)
        unit = diff / dist
        F += np.sum(mag * unit, axis=1)
        return F


# ─────────────────────────────────────────────
# Cosine alignment
# ─────────────────────────────────────────────

def cosine_alignment(A: np.ndarray, B: np.ndarray) -> float:
    """Mean per-agent cosine alignment between two (N, d) force fields."""
    dot = np.sum(A * B, axis=1)                     # (N,)
    normA = np.linalg.norm(A, axis=1) + 1e-12
    normB = np.linalg.norm(B, axis=1) + 1e-12
    cos = dot / (normA * normB)
    return float(np.mean(cos))


def global_cosine_alignment(A: np.ndarray, B: np.ndarray) -> float:
    """Global cosine alignment: treat the full (N*d,) vector."""
    a = A.ravel()
    b = B.ravel()
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))


# ─────────────────────────────────────────────
# Main experiment
# ─────────────────────────────────────────────

def run_experiment():
    OUTPUT_DIR.mkdir(exist_ok=True)
    rng = np.random.default_rng(RNG_SEED)

    # ── Step 1: Normal reference data ──
    # N_REF points drawn from N(0, I) — represents "healthy" system states
    N_REF = 200
    X_normal = rng.standard_normal((N_REF, D_DIM))

    # ── Step 2: Fit BSDT operator on normal data ──
    op = BSDTEnergyOperator()
    op.fit(X_normal)
    print(f"[fit] Normal reference: N={N_REF}, d={D_DIM}")
    print(f"      μ₀ = {op.mu0_.round(3)}")
    print(f"      Σ₀⁻¹ diagonal = {np.diag(op.Sigma0_inv_).round(3)}")

    # ── Step 3: Initial system state (perturbed — starting near instability) ──
    # Start from a state that is displaced from the normal reference
    # so both forces are non-trivial from step 0
    X = rng.standard_normal((N_AGENTS, D_DIM)) * 1.5 + 0.5
    mu = X.mean(axis=0)

    # ── Step 4: Simulation loop ──
    cos_mean_history  = []   # mean per-agent cosine
    cos_global_history = []  # global cosine (flattened vector)
    energy_bs_history  = []
    displacement_history = []

    print(f"\n[sim] Running {N_STEPS} steps, N={N_AGENTS}, d={D_DIM}, η={ETA}")
    print(f"      {'Step':>5}  {'cos_mean':>10}  {'cos_global':>12}  {'E_BS':>12}  {'max_disp':>10}")
    print("      " + "-"*58)

    for t in range(N_STEPS):
        mu = X.mean(axis=0)

        # −∇Φ(X): GravityEngine restoring force
        F_gravity = gravity_force(X, mu)             # (N, d)

        # ∇E_BS(X): blind-spot energy gradient
        grad_bs = op.gradient_fast(X)                # (N, d)

        # Alignment: compare ∇E_BS with −∇Φ = F_gravity
        cos_m = cosine_alignment(grad_bs, F_gravity)
        cos_g = global_cosine_alignment(grad_bs, F_gravity)
        cos_mean_history.append(cos_m)
        cos_global_history.append(cos_g)

        # Energy
        E_bs = op.energy(X)
        energy_bs_history.append(E_bs)

        # Evolve: gradient flow step X ← X + η · F_gravity
        dX = ETA * F_gravity
        max_disp = float(np.max(np.abs(dX)))
        displacement_history.append(max_disp)
        X = X + dX

        if t % 20 == 0 or t == N_STEPS - 1:
            print(f"      {t:>5}  {cos_m:>10.4f}  {cos_g:>12.4f}  {E_bs:>12.4f}  {max_disp:>10.6f}")

        # Early stop if converged
        if max_disp < 1e-6:
            print(f"      [converged at step {t}]")
            break

    # ── Step 5: Summary statistics ──
    cos_arr = np.array(cos_mean_history)
    mean_cos  = float(np.mean(cos_arr))
    median_cos = float(np.median(cos_arr))
    min_cos   = float(np.min(cos_arr))
    frac_above_07 = float(np.mean(cos_arr > 0.7))
    frac_positive  = float(np.mean(cos_arr > 0.0))

    THRESHOLD = 0.7
    PASS = mean_cos >= THRESHOLD

    summary = {
        "verdict": "PASS" if PASS else "FAIL",
        "threshold": THRESHOLD,
        "mean_cosine": mean_cos,
        "median_cosine": median_cos,
        "min_cosine": min_cos,
        "frac_steps_above_07": frac_above_07,
        "frac_steps_positive": frac_positive,
        "n_steps_run": len(cos_arr),
        "N_agents": N_AGENTS,
        "d_dim": D_DIM,
        "alpha": ALPHA,
        "gamma": GAMMA,
        "sigma": SIGMA,
        "lambda_rep": LAMBDA_REP,
        "gravity_available": GRAVITY_AVAILABLE,
        "interpretation": (
            "Theorem C is EMPIRICALLY SUPPORTED. Proceed to formal proof."
            if PASS else
            "Theorem C alignment is BELOW THRESHOLD. Re-examine the deviation "
            "operator construction before attempting the formal proof."
        )
    }

    # ── Step 6: Save results ──
    results_path = OUTPUT_DIR / "cos_theta_history.json"
    with open(results_path, "w") as f:
        json.dump({
            "summary": summary,
            "cos_mean_per_step": cos_mean_history,
            "cos_global_per_step": cos_global_history,
            "energy_bs_per_step": energy_bs_history,
        }, f, indent=2)

    summary_path = OUTPUT_DIR / "alignment_summary.txt"
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("=" * 60 + "\n")
        f.write("GRADIENT ALIGNMENT VERIFICATION — THEOREM C\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"Verdict:                {summary['verdict']}\n")
        f.write(f"Threshold:              {THRESHOLD}\n\n")
        f.write(f"Mean cosine θ:          {mean_cos:.4f}\n")
        f.write(f"Median cosine θ:        {median_cos:.4f}\n")
        f.write(f"Min cosine θ:           {min_cos:.4f}\n")
        f.write(f"Fraction steps > 0.7:   {frac_above_07:.2%}\n")
        f.write(f"Fraction steps > 0:     {frac_positive:.2%}\n")
        f.write(f"Steps run:              {len(cos_arr)}\n\n")
        f.write(f"Setup:\n")
        f.write(f"  N agents = {N_AGENTS}, d = {D_DIM}\n")
        f.write(f"  α={ALPHA}, γ={GAMMA}, σ={SIGMA}, λ={LAMBDA_REP}\n")
        f.write(f"  GravityEngine available: {GRAVITY_AVAILABLE}\n\n")
        f.write(f"Interpretation:\n  {summary['interpretation']}\n\n")
        f.write("What cos θ measures:\n")
        f.write("  cos θ = ⟨∇E_BS(X), −∇Φ(X)⟩ / (‖∇E_BS‖ · ‖−∇Φ‖)\n")
        f.write("  cos θ = 1.0  →  perfect alignment (same direction)\n")
        f.write("  cos θ = 0.0  →  orthogonal (no overlap)\n")
        f.write("  cos θ = −1.0 →  anti-aligned (opposite)\n")
        f.write("\nTheorem C predicts cos θ ≥ 0.7 on average.\n")
        f.write("If this holds, ∇E_BS is a valid substitute for −∇Φ\n")
        f.write("in the stabilisation law, and Theorem C is worth proving.\n")

    # ── Step 7: Plot ──
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    fig.suptitle("Gradient Alignment Verification — Theorem C\n"
                 f"N={N_AGENTS} agents, d={D_DIM}, verdict: {summary['verdict']} "
                 f"(mean cos θ = {mean_cos:.3f})", fontsize=13)

    steps = np.arange(len(cos_mean_history))

    # Panel 1: mean per-agent cosine
    ax = axes[0, 0]
    ax.plot(steps, cos_mean_history, lw=1.5, color="steelblue", label="mean per-agent cos θ")
    ax.axhline(THRESHOLD, color="red", ls="--", lw=1, label=f"threshold = {THRESHOLD}")
    ax.axhline(0, color="gray", ls=":", lw=0.8)
    ax.fill_between(steps, cos_mean_history, THRESHOLD,
                    where=np.array(cos_mean_history) < THRESHOLD,
                    alpha=0.2, color="red", label="below threshold")
    ax.set_xlabel("Step"); ax.set_ylabel("cos θ (mean per-agent)")
    ax.set_title("Per-agent cosine alignment"); ax.legend(fontsize=8); ax.grid(alpha=0.3)

    # Panel 2: global cosine
    ax = axes[0, 1]
    ax.plot(steps, cos_global_history, lw=1.5, color="darkorange", label="global cos θ")
    ax.axhline(THRESHOLD, color="red", ls="--", lw=1)
    ax.axhline(0, color="gray", ls=":", lw=0.8)
    ax.set_xlabel("Step"); ax.set_ylabel("cos θ (global)")
    ax.set_title("Global cosine alignment (flattened vector)"); ax.legend(fontsize=8); ax.grid(alpha=0.3)

    # Panel 3: blind-spot energy over time
    ax = axes[1, 0]
    ax.plot(steps, energy_bs_history, lw=1.5, color="seagreen")
    ax.set_xlabel("Step"); ax.set_ylabel("E_BS(X)")
    ax.set_title("Blind-spot energy E_BS over time\n(should decrease = Theorem 1 holds)"); ax.grid(alpha=0.3)

    # Panel 4: histogram of cos θ values
    ax = axes[1, 1]
    ax.hist(cos_mean_history, bins=30, color="steelblue", edgecolor="white", alpha=0.8)
    ax.axvline(THRESHOLD, color="red", ls="--", lw=1.5, label=f"threshold {THRESHOLD}")
    ax.axvline(mean_cos, color="navy", ls="-", lw=1.5, label=f"mean {mean_cos:.3f}")
    ax.set_xlabel("cos θ"); ax.set_ylabel("Count")
    ax.set_title("Distribution of per-step cos θ"); ax.legend(fontsize=8); ax.grid(alpha=0.3)

    plt.tight_layout()
    plot_path = OUTPUT_DIR / "alignment_plot.png"
    plt.savefig(plot_path, dpi=150, bbox_inches="tight")
    plt.close()

    # ── Final report ──
    print("\n" + "=" * 60)
    print(f"VERDICT: {summary['verdict']}")
    print(f"Mean cosine alignment: {mean_cos:.4f}  (threshold: {THRESHOLD})")
    print(f"Fraction of steps above threshold: {frac_above_07:.1%}")
    print(f"\n{summary['interpretation']}")
    print("=" * 60)
    print(f"\nOutputs written to: {OUTPUT_DIR}/")
    print(f"  alignment_summary.txt")
    print(f"  cos_theta_history.json")
    print(f"  alignment_plot.png")

    return summary


if __name__ == "__main__":
    run_experiment()
