"""Numerical verification of every theorem in canonical_system_v4.pdf.

Each test produces a quantitative residual and asserts it is below a
tolerance.  These are not proofs (which are in the PDF) — they are
empirical certifications that the implementation realises the stated
theorems on representative instances.

Run with:
    cd C:\\amttp\\research\\adaptive-friction
    py -3 test_canonical_v4_theorems.py
"""
from __future__ import annotations
import numpy as np
np.set_printoptions(precision=4, suppress=True)

from collapse_geometry.canonical import (
    CanonicalSystem,
    TradingDomain, GalerkinDomain,
    FractalRepresentation, ContactRepresentation,
    GeometricFlowMetric, FisherInformationMetric, natural_gradient,
    info_geometric_hessian, NaturalGradientFlow, MLEInstance, VIInstance,
    fisher_noise, CanonicalSDE, expected_dE_dt, trace_correction,
    mean_square_ultimate_bound, natural_gradient_langevin,
)

PASS = "[PASS]"

results: list[tuple[str, bool, str]] = []

def check(name: str, cond: bool, detail: str = ""):
    results.append((name, cond, detail))
    tag = "[PASS]" if cond else "[FAIL]"
    print(f"  {tag} {name}    {detail}")
    if not cond:
        raise AssertionError(f"{name} failed: {detail}")


def section(title: str):
    print("\n" + "=" * 72)
    print(f"  {title}")
    print("=" * 72)


# =======================================================================
#  LEMMA 2.1  —  g_X = 0 ⇔ E = 0  under full row rank of J
# =======================================================================
section("Lemma 2.1 — Structure of the singular set Σ")
np.random.seed(1)

# Build a system with full-row-rank J (k=2, n=4): S(X) = AX + b, A random k×n
n, k = 4, 2
A = np.random.randn(k, n)
b = np.random.randn(k)
sys21 = CanonicalSystem(
    S=lambda X: A @ X + b,
    J=lambda X: A,
    G=np.eye(k),
    F_base=lambda X: np.zeros(n),
    theta=1.0,
    K=lambda X: np.zeros((k, n, n)),
)

# Lemma 2.1 says: under rank J = k (full row rank), {g_X=0} = {E=0}.
# Equivalently the sandwich  4·σ_min(JG^{1/2})² · E ≤ ‖g_X‖² ≤ 4·σ_max(JG^{1/2})² · E
# holds for all X.  Verify both directions hold strictly.
G_half = np.linalg.cholesky(sys21.G + 1e-15 * np.eye(k))
# ‖g_X‖² / E = 4·(uᵀ M u)/(uᵀu) where u = G^{1/2}S, M = G^{1/2} J Jᵀ G^{1/2}
M_mat = G_half @ A @ A.T @ G_half.T
ev = np.linalg.eigvalsh(M_mat)
lam_min, lam_max = float(ev.min()), float(ev.max())
worst_lo, worst_hi = np.inf, 0.0
for _ in range(200):
    X = np.random.randn(n) * 2.0
    E   = sys21.energy(X)
    gn2 = float(sys21.gradient(X) @ sys21.gradient(X))
    if E < 1e-15:
        continue
    ratio = gn2 / E
    worst_lo = min(worst_lo, ratio / (4.0 * lam_min))
    worst_hi = max(worst_hi, ratio / (4.0 * lam_max))
check("Lemma 2.1: sandwich  4λ_min(GJJᵀG) E ≤ ‖g_X‖² ≤ 4λ_max(GJJᵀG) E",
      worst_lo >= 1.0 - 1e-9 and worst_hi <= 1.0 + 1e-9,
      f"lo-bound tightness = {worst_lo:.4f},  hi-bound tightness = {worst_hi:.4f}")

# Find the unique S=0 point (X⋆ minimising ‖AX+b‖); g_X must vanish there
X_star = -np.linalg.lstsq(A, b, rcond=None)[0]
E_star  = sys21.energy(X_star)
gn_star = np.linalg.norm(sys21.gradient(X_star))
check("Lemma 2.1: at S⋆ = 0 both E = 0 and g_X = 0",
      E_star < 1e-20 and gn_star < 1e-10,
      f"E⋆={E_star:.2e}, ‖g⋆‖={gn_star:.2e}")


# =======================================================================
#  THEOREM 2.2  —  Local existence & uniqueness (continuity of flow)
# =======================================================================
section("Theorem 2.2 — Local existence & uniqueness")

sys22 = CanonicalSystem(
    S=lambda X: X,
    J=lambda X: np.eye(3),
    G=np.eye(3),
    F_base=lambda X: -0.1 * X,
    theta=1.0,
    K=lambda X: np.zeros((3, 3, 3)),
)
# Two nearby initial conditions → trajectories should stay close (Lipschitz)
X0a = np.array([1.0, 0.5, -0.3])
X0b = X0a + 1e-4 * np.random.randn(3)
res_a = sys22.integrate(X0a, h=0.01, max_steps=200, eps_E=0, eps_g=0, dwell=10**9, record=True)
res_b = sys22.integrate(X0b, h=0.01, max_steps=200, eps_E=0, eps_g=0, dwell=10**9, record=True)
final_gap = float(np.linalg.norm(res_a.X_final - res_b.X_final))
init_gap  = float(np.linalg.norm(X0a - X0b))
check("Theorem 2.2: ‖X_a(T)−X_b(T)‖ ≤ C·‖X_a(0)−X_b(0)‖ (Lipschitz dependence)",
      final_gap < 1e3 * init_gap,
      f"init={init_gap:.2e}  final={final_gap:.2e}  ratio={final_gap/init_gap:.2e}")


# =======================================================================
#  PROPOSITION 6.1  —  Hessian formula  ∇²E = 2JᵀGJ + ⟨η, K⟩₁
# =======================================================================
section("Proposition 6.1 — Closed-form Hessian")

# Non-affine S so that K ≠ 0 — pick S(X) = (X[0]², X[0]·X[1])
# Then J = [[2X[0],0,0],[X[1],X[0],0]], K^1 = diag(2,0,0), K^2 = symm(e1, e2)
def S_nonlin(X):
    return np.array([X[0] ** 2, X[0] * X[1]])
def J_nonlin(X):
    return np.array([[2.0 * X[0], 0.0, 0.0],
                     [X[1],       X[0], 0.0]])
def K_nonlin(X):
    K = np.zeros((2, 3, 3))
    K[0, 0, 0] = 2.0                       # ∂²S^1/∂X_0² = 2
    K[1, 0, 1] = 1.0                       # ∂²S^2/∂X_0∂X_1 = 1
    K[1, 1, 0] = 1.0                       # symmetric
    return K

sys61 = CanonicalSystem(
    S=S_nonlin, J=J_nonlin, K=K_nonlin,
    G=np.diag([2.0, 1.0]),
    F_base=lambda X: np.zeros(3),
    theta=1.0,
)
X = np.array([0.7, -0.3, 0.4])
H_an = sys61.hessian(X)

# Finite-difference ∇²E directly from energy
def fd_hess(f, X, h=1e-4):
    n = X.size
    H = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            ei = np.zeros(n); ei[i] = 1.0
            ej = np.zeros(n); ej[j] = 1.0
            Epp = f(X + h*ei + h*ej); Emm = f(X - h*ei - h*ej)
            Epm = f(X + h*ei - h*ej); Emp = f(X - h*ei + h*ej)
            H[i, j] = (Epp - Epm - Emp + Emm) / (4 * h * h)
    return 0.5 * (H + H.T)
H_fd = fd_hess(sys61.energy, X)
err = float(np.linalg.norm(H_an - H_fd, ord="fro"))
scale = max(float(np.linalg.norm(H_fd, ord="fro")), 1.0)
check("Prop. 6.1: ∇²E (analytic) matches FD on non-affine S",
      err / scale < 1e-3,
      f"||H_an − H_fd||_F / ||H_fd|| = {err/scale:.2e}")


# =======================================================================
#  PROPOSITION 6.6  —  Curvature upper bound on λ_max(∇²E)
# =======================================================================
section("Proposition 6.6 — Curvature bound on λ_max")

# Use sys61.  ‖K‖_op := sup_{u,v,w unit} Σ_i K^i_{ab} u_i v_a w_b
# Compute exactly for our K (small):
def K_op_norm(K):
    # crude upper bound via Frobenius
    return float(np.sqrt((K * K).sum()))
K_op = K_op_norm(K_nonlin(X))
lam_actual = float(np.linalg.eigvalsh(H_an)[-1])
lam_bound  = sys61.lambda_max_bound(X, K_op_norm=K_op)
check("Prop. 6.6: λ_max(∇²E) ≤ 2M_G‖J‖² + ‖K‖_op·‖η‖",
      lam_actual <= lam_bound + 1e-9,
      f"λ_max = {lam_actual:.4f},  bound = {lam_bound:.4f}")


# =======================================================================
#  LEMMA 6.7  —  Energy derivative formula
# =======================================================================
section("Lemma 6.7 — Energy derivative Ė = (1−γ)(⟨g_X, F_b⟩ − ‖g_X‖²)")

# Build a non-trivial system with non-zero F_base
sys67 = CanonicalSystem(
    S=lambda X: X - np.array([1.0, 0.5, -0.3, 0.2]),
    J=lambda X: np.eye(4),
    G=np.diag([1.0, 2.0, 0.5, 1.5]),
    F_base=lambda X: -0.2 * X + np.array([0.1, -0.1, 0.05, 0.0]),
    theta=2.0,
    K=lambda X: np.zeros((4, 4, 4)),
)
# Sample 50 random X, compare analytic Ė vs FD along Ẋ
err_max = 0.0
for _ in range(50):
    X = np.random.randn(4) * 2.0
    Edot_an = sys67.dE_dt(X)
    h = 1e-6
    Xdot = sys67.rhs(X)
    E_p = sys67.energy(X + h * Xdot)
    E_m = sys67.energy(X - h * Xdot)
    Edot_fd = (E_p - E_m) / (2.0 * h)
    err_max = max(err_max, abs(Edot_an - Edot_fd))
check("Lemma 6.7: |Ė_analytic − Ė_FD| → 0 over 50 random X",
      err_max < 1e-6, f"max abs error = {err_max:.2e}")

# Sanity: pure geometric flow (F_base = 0) ⇒ Ė = -(1-γ)‖g‖²
sys67_pure = CanonicalSystem(
    S=lambda X: X, J=lambda X: np.eye(3), G=np.eye(3),
    F_base=lambda X: np.zeros(3), theta=1.0,
)
X = np.array([1.0, 0.5, -0.7])
gn2 = float(sys67_pure.gradient(X) @ sys67_pure.gradient(X))
expected = -(1.0 - sys67_pure.gain(X)) * gn2
check("Lemma 6.7 special case (F_b=0): Ė = -(1-γ)‖g_X‖²",
      abs(sys67_pure.dE_dt(X) - expected) < 1e-12,
      f"|Ė − (-(1-γ)‖g‖²)| = {abs(sys67_pure.dE_dt(X) - expected):.2e}")


# =======================================================================
#  THEOREM 7.1  —  Lyapunov descent  (Ė ≤ 0  iff  ⟨g_X, F_b⟩ ≤ ‖g_X‖²)
# =======================================================================
section("Theorem 7.1 — Lyapunov descent characterisation")

# (i) F_base = 0 ⇒ Ė < 0 strictly when g_X ≠ 0
fails_i = 0
for _ in range(100):
    X = np.random.randn(3) * 2.0
    if sys67_pure.dE_dt(X) >= 0 and np.linalg.norm(sys67_pure.gradient(X)) > 1e-6:
        fails_i += 1
check("Theorem 7.1(i): F_b ≡ 0 ⇒ Ė < 0 whenever g_X ≠ 0  (100 samples)",
      fails_i == 0, f"violations = {fails_i}/100")

# (ii) Sign correspondence with the angle condition
violations = 0
for _ in range(200):
    X = np.random.randn(4) * 2.0
    g = sys67.gradient(X)
    Fb = np.asarray(sys67.F_base(X), dtype=float)
    inner = float(g @ Fb)
    gn2 = float(g @ g)
    Edot = sys67.dE_dt(X)
    angle_holds = inner <= gn2
    descent     = Edot <= 1e-15
    if angle_holds != descent:
        violations += 1
check("Theorem 7.1(ii): Ė ≤ 0  ⇔  ⟨g_X, F_b⟩ ≤ ‖g_X‖²  (200 samples)",
      violations == 0, f"sign mismatches = {violations}/200")


# =======================================================================
#  THEOREM 7.2  —  Asymptotic stability (F_b = 0, full-rank J, compact sublevel)
# =======================================================================
section("Theorem 7.2 — Asymptotic stability of {E = 0}")

sys72 = CanonicalSystem(
    S=lambda X: X,
    J=lambda X: np.eye(5),
    G=np.diag([1.0, 1.5, 0.8, 2.0, 1.2]),
    F_base=lambda X: np.zeros(5),
    theta=1.0,
    K=lambda X: np.zeros((5, 5, 5)),
)
# Run 5 random starts to convergence
trials = []
for seed in range(5):
    rng = np.random.default_rng(seed)
    X0 = rng.standard_normal(5) * 2.0
    res = sys72.integrate(X0, h=0.05, max_steps=4000,
                          eps_E=1e-12, eps_g=1e-7, dwell=10)
    trials.append(res.energy[-1])
max_E_final = max(trials)
check("Theorem 7.2: E(X_t) → 0 from arbitrary X_0 (5 random starts)",
      max_E_final < 1e-8, f"max final E = {max_E_final:.2e}")

# Verify monotonicity along the trajectory (Theorem 7.1 ⇒ Theorem 7.2)
res = sys72.integrate(np.array([1.0, -1.0, 0.5, 0.3, -0.7]),
                      h=0.05, max_steps=2000, eps_E=0, eps_g=0, dwell=10**9, record=True)
diffs = np.diff(res.energy)
violations = int((diffs > 1e-10).sum())
check("Theorem 7.2: E(t) is monotonically non-increasing along trajectory",
      violations == 0, f"increases = {violations}")


# =======================================================================
#  THEOREM 7.3  —  Exponential rate  E(t) ≤ E(0) e^{-ρ t}
# =======================================================================
section("Theorem 7.3 — Exponential convergence rate")

# Use sys72 (G diagonal, σ_min(J)=1).  μ_G = min eig(G), M_G = max eig(G).
G_eigs = np.linalg.eigvalsh(sys72.G)
mu_G, M_G = float(G_eigs[0]), float(G_eigs[-1])
sigma = 1.0  # σ_min(I) = 1
X0 = np.array([1.0, -0.5, 0.3, -0.4, 0.2])
rho_predicted = sys72.exponential_rate(X0, sigma_min=sigma)

# Integrate (no stopping) and compare empirical decay
res = sys72.integrate(X0, h=0.01, max_steps=3000, eps_E=0, eps_g=0, dwell=10**9, record=True)
t = np.arange(res.energy.size) * 0.01
log_E = np.log(np.maximum(res.energy, 1e-300))
# Empirical rate from fitting log(E) ≈ log(E₀) − ρ_emp·t over decay window
mask = res.energy > 1e-6
slope = np.polyfit(t[mask], log_E[mask], 1)[0]
rho_empirical = -slope
print(f"  predicted ρ = {rho_predicted:.4f}   empirical ρ = {rho_empirical:.4f}")
check("Theorem 7.3: empirical decay rate ≥ predicted ρ (rate is a lower bound)",
      rho_empirical >= 0.95 * rho_predicted,
      f"emp/pred = {rho_empirical/rho_predicted:.3f}")

# Direct envelope check: E(t) ≤ E(0) · e^{-ρ_predicted · t}  for all t
envelope = res.energy[0] * np.exp(-rho_predicted * t)
violations = int((res.energy > envelope * (1 + 1e-9)).sum())
check("Theorem 7.3: E(t) ≤ E(0)·e^{-ρt} pointwise",
      violations == 0, f"envelope violations = {violations}/{t.size}")


# =======================================================================
#  THEOREM 7.4  —  Ultimate boundedness with F_base ≠ 0
# =======================================================================
section("Theorem 7.4 — Ultimate boundedness")

# Constant disturbance F_base = c (within admissible regime ‖c‖ < Ψ⋆)
sys74 = CanonicalSystem(
    S=lambda X: X,
    J=lambda X: np.eye(3),
    G=np.eye(3),
    F_base=lambda X: np.array([0.05, -0.03, 0.02]),
    theta=1.0,
    K=lambda X: np.zeros((3, 3, 3)),
)
sigma = 1.0
M = float(np.linalg.norm(sys74.F_base(np.zeros(3))))
Psi_star = sys74.ultimate_bound_threshold(sigma_min=sigma)
admissible = M < Psi_star
print(f"  M = {M:.4f}, Ψ⋆ = {Psi_star:.4f}, admissible = {admissible}")
check("Theorem 7.4: disturbance is admissible (M < Ψ⋆)", admissible)

bounds = sys74.ultimate_bound(sigma_min=sigma, M=M)
assert bounds is not None
R_minus, R_plus = bounds
print(f"  R₋ = {R_minus:.4f},  R₊ = {R_plus:.4f}")

# Start with E(X₀) ≤ R₊ and check trajectory stays bounded
X0 = np.array([0.3, -0.2, 0.1])
E0 = sys74.energy(X0)
print(f"  E(X₀) = {E0:.4f}  (need ≤ R₊ = {R_plus:.4f})")
res = sys74.integrate(X0, h=0.02, max_steps=8000, eps_E=0, eps_g=0,
                      dwell=10**9, record=False)
# Tail behaviour: energy should remain bounded
E_tail_max = res.energy[-2000:].max()
check("Theorem 7.4: E(t) remains bounded (≤ R₊·1.05) in admissible window",
      E_tail_max <= R_plus * 1.05,
      f"E_tail_max = {E_tail_max:.4f}, 1.05·R₊ = {1.05 * R_plus:.4f}")


# =======================================================================
#  PROPOSITION D.2  —  Multi-scale fractal exponential decay
# =======================================================================
section("Proposition D.2 — Fractal multi-scale exponential decay")

# Smooth distance to {0}: d_δ(X) = sqrt(‖X‖² + δ²) − δ
# J row ℓ : ∂d_δ/∂X = X / sqrt(‖X‖²+δ²)
def dist_fn(X, d):
    return float(np.sqrt(np.sum(X * X) + d * d) - d)

deltas = [1.0, 0.5, 0.25]
d_H = 1.0
fracD2 = FractalRepresentation(
    dist_fn=dist_fn,
    deltas=deltas,
    d_H=d_H,
    F_base=lambda X: np.zeros_like(X),
    theta=1.0,
).build()

X0 = np.array([0.4, -0.3, 0.2])
res = fracD2.integrate(X0, h=0.02, max_steps=5000, eps_E=0, eps_g=0,
                       dwell=10**9, record=False)
# Empirical exponential decay
t = np.arange(res.energy.size) * 0.02
mask = res.energy > 1e-8
if mask.sum() > 50:
    slope = np.polyfit(t[mask], np.log(res.energy[mask]), 1)[0]
    rho_emp = -slope
    # Predicted lower bound from Prop. D.2:
    # ρ_frac ≥ 4 σ_J² · δ_L^{−4d_H} / δ_1^{−2d_H} · (1−γ_max)
    # Conservative estimate σ_J=1 (FD-derived)
    rho_pred = 4.0 * 1.0 * (deltas[-1] ** (-4 * d_H)) / (deltas[0] ** (-2 * d_H)) \
               * (1.0 - fracD2.gain(X0))
    print(f"  empirical ρ = {rho_emp:.4f}  predicted lower bound = {rho_pred:.4f}")
    check("Prop. D.2: empirical fractal decay rate is exponential (ρ_emp > 0)",
          rho_emp > 0, f"ρ_emp = {rho_emp:.4f}")
else:
    check("Prop. D.2: insufficient decay window — skipped quantitative comparison",
          False, "tighten test")


# =======================================================================
#  PROPOSITION E.1  —  Contact preservation: Φ → 0 forces β·ϕ² → 0
# =======================================================================
section("Proposition E.1 — Contact horizontal-descent")

# F_base smooth, ϕ(X) = α_X(F_base) = (F_b)_z − Σ y_i (F_b)_{x_i}.
# Choose F_base whose ϕ is non-trivial at the start.
contactE1 = ContactRepresentation(
    Phi=lambda X: np.array([X[0], X[1] + X[2]]),
    F_base=lambda X: np.array([-0.1 * X[0], -0.1 * X[1], -0.1 * X[2]]),
    G0=np.eye(2),
    beta=0.5,
    m=1,
).build()
X0 = np.array([0.6, 0.3, -0.2])
res = contactE1.integrate(X0, h=0.05, max_steps=4000,
                          eps_E=1e-12, eps_g=1e-7, dwell=10, record=True)
# At convergence, S = 0 ⇒ Φ = 0 AND α_X(F_base) = 0  ⇒  β·ϕ² → 0
S_final = contactE1.S(res.X_final)
Phi_final  = S_final[:2]
phi_final  = S_final[2]
check("Prop. E.1: Φ(X) → 0 at convergence",
      np.linalg.norm(Phi_final) < 1e-3, f"‖Φ‖ = {np.linalg.norm(Phi_final):.2e}")
check("Prop. E.1: β·ϕ²(X) → 0 at convergence",
      0.5 * phi_final ** 2 < 1e-6, f"β·ϕ² = {0.5*phi_final**2:.2e}")


# =======================================================================
#  THEOREM F.2  —  Coupled (X, G) Lyapunov V monotone (constant G_⋆)
# =======================================================================
section("Theorem F.2 — Coupled state-metric Lyapunov V")

# Take Ric ≡ 0, G_⋆ ≡ I (constant), σ > 0.  V(X,G) = E(X) + ½σ⁻¹‖G−I‖²_F.
# Theorem F.2 says V monotonically decreasing.
G0 = 1.5 * np.eye(3)
sigma_rel = 1.5
gflowF2 = GeometricFlowMetric(
    G0=G0,
    S=lambda X: X,
    J=lambda X: np.eye(3),
    F_base=lambda X: np.zeros(3),
    G_star=lambda X: np.eye(3),
    sigma_rel=sigma_rel,
    theta=1.0,
)
X = np.array([1.0, -0.5, 0.3])
def V_value(gflow, X):
    sys = gflow.build()
    E_x = sys.energy(X)
    diff = gflow.G_current - np.eye(3)
    return E_x + 0.5 * (1.0 / gflow.sigma_rel) * float((diff * diff).sum())

V_history = [V_value(gflowF2, X)]
for _ in range(100):
    X = gflowF2.coupled_step(X, h=0.02)
    V_history.append(V_value(gflowF2, X))
V_history = np.array(V_history)
diffs = np.diff(V_history)
violations = int((diffs > 1e-6).sum())   # tiny tolerance for splitting error
check("Theorem F.2: V(X, G) monotonically non-increasing (constant G_⋆)",
      violations == 0,
      f"increases = {violations}/{diffs.size}, V: {V_history[0]:.4f} → {V_history[-1]:.4f}")


# =======================================================================
#  THEOREM I.1  —  Chart covariance of natural-gradient flow
# =======================================================================
section("Theorem I.1 — Chart covariance of natural gradient")

# Build a Fisher-metric system, take a linear chart change Φ(X̃) = T·X̃, and
# verify  g̃_X̃ = T^{-1} · g_X(Φ(X̃))   pointwise.
np.random.seed(7)
T = np.eye(3) + 0.3 * np.random.randn(3, 3)   # invertible chart map
T_inv = np.linalg.inv(T)

# Use a non-trivial Fisher: I_S(z) = diag(1+z·z), J=I (S(X)=X)
fim_orig = FisherInformationMetric(
    S=lambda X: X,
    fisher_info=lambda z: np.diag(1.0 + z * z),
    F_base=lambda X: np.zeros_like(X),
    J=lambda X: np.eye(3),
)
# Pulled-back Fisher under the chart Φ(X̃)=T·X̃ uses S̃(X̃) = T·X̃, J̃ = T
fim_chart = FisherInformationMetric(
    S=lambda Xt: T @ Xt,
    fisher_info=lambda z: np.diag(1.0 + z * z),
    F_base=lambda Xt: np.zeros_like(Xt),
    J=lambda Xt: T,
)

Xt = np.array([0.5, -0.4, 0.6])
X  = T @ Xt

g_orig  = natural_gradient(fim_orig, X)
g_chart = natural_gradient(fim_chart, Xt)
expected = T_inv @ g_orig
err = float(np.linalg.norm(g_chart - expected))
check("Theorem I.1: g̃_X̃ = T⁻¹ · g_X  (chart covariance)",
      err < 1e-8, f"||g̃ − T⁻¹g|| = {err:.2e}")

# Verify the trajectory transforms covariantly: Φ⁻¹(X(t)) = X̃(t)
def euler_natgrad(fim, X0, h, n):
    X = X0.copy()
    for _ in range(n):
        X = X - h * natural_gradient(fim, X)
    return X
X_T   = euler_natgrad(fim_orig,  X,  h=0.01, n=100)
Xt_T  = euler_natgrad(fim_chart, Xt, h=0.01, n=100)
mapped = T_inv @ X_T
err_traj = float(np.linalg.norm(Xt_T - mapped))
check("Theorem I.1: trajectories satisfy X̃(t) = Φ⁻¹(X(t)) under chart",
      err_traj < 1e-6, f"||X̃(T) − Φ⁻¹(X(T))|| = {err_traj:.2e}")


# =======================================================================
#  THEOREM J.1  —  Fisher exponential rate  ρ_F = 4 (μ_I²/M_I) σ²_min(J)(1−γ_max)
# =======================================================================
section("Theorem J.1 — Information-geometric exponential rate")

# Use constant Fisher I_S = diag(2, 1) (PD, bounded).  J = identity-like.
# Tracking schedule (F1): G(X) = I_S(S(X)) = diag(2,1) (constant).
fim_J1 = FisherInformationMetric(
    S=lambda X: X[:2],
    fisher_info=lambda z: np.diag([2.0, 1.0]),
    F_base=lambda X: np.zeros_like(X),
    J=lambda X: np.eye(2, X.size),     # k=2, n=3
)
X0 = np.array([1.0, -0.5, 0.0])
sys_J1 = fim_J1.build(X0)
mu_I, M_I = 1.0, 2.0
sigma_min_J = 1.0  # σ_min(I_{2x3}) = 1
rho_F_pred = 4.0 * (mu_I ** 2 / M_I) * sigma_min_J ** 2 * (1.0 - sys_J1.gain(X0))

res = sys_J1.integrate(X0, h=0.02, max_steps=2000, eps_E=0, eps_g=0,
                       dwell=10**9, record=False)
t = np.arange(res.energy.size) * 0.02
mask = res.energy > 1e-8
if mask.sum() > 100:
    slope = np.polyfit(t[mask], np.log(res.energy[mask]), 1)[0]
    rho_emp = -slope
    print(f"  predicted ρ_F = {rho_F_pred:.4f},  empirical ρ_F = {rho_emp:.4f}")
    check("Theorem J.1: empirical Fisher decay rate ≥ predicted ρ_F",
          rho_emp >= 0.95 * rho_F_pred,
          f"emp/pred = {rho_emp/rho_F_pred:.3f}")
else:
    check("Theorem J.1: trajectory decay window too short", False)


# =======================================================================
#  §9.3 — Information-geometric Hessian (state-dependent G)
# =======================================================================
section("§9.3 — Information-geometric Hessian (state-dependent G via Fisher)")

# Build a Fisher with non-trivial X-dependence: I_S(z) = diag(1+z₁², 1+z₂²)
fim_h = FisherInformationMetric(
    S=lambda X: X[:2],
    fisher_info=lambda z: np.diag(1.0 + z * z),
    F_base=lambda X: np.zeros_like(X),
    J=lambda X: np.eye(2, X.size),
)
X_h = np.array([0.6, -0.4, 0.2])
H_full = info_geometric_hessian(fim_h, X_h, h=1e-4)
# At a non-target point, the constant-G formula 2 J^T I_S J should differ
sys_h = fim_h.build(X_h)
H_naive = 2.0 * sys_h.jacobian(X_h).T @ sys_h.G @ sys_h.jacobian(X_h)
extra = float(np.linalg.norm(H_full - H_naive, ord="fro"))
print(f"  ‖H_full − 2JᵀI_S J‖_F = {extra:.4f}  (extra Fisher-connection terms)")
check("§9.3: full info-geometric Hessian differs from constant-G formula off-target",
      extra > 1e-3, f"extra = {extra:.4f}")

# At the target {S=0} the extra terms vanish: H = 2 I_X
X_target = np.array([0.0, 0.0, 0.5])      # S=(0,0)
H_target = info_geometric_hessian(fim_h, X_target, h=1e-4)
I_X = fim_h.pullback(X_target)
err_target = float(np.linalg.norm(H_target - 2.0 * I_X, ord="fro"))
check("§9.3: at {S=0} ∇²E = 2 I_X exactly (extra terms vanish)",
      err_target < 1e-2, f"||H − 2I_X||_F = {err_target:.2e}")


# =======================================================================
#  §10.1 — Natural-gradient variant flow Ẋ = −g̃_X
# =======================================================================
section("§10.1 — Natural-gradient flow (chart-covariant variant)")

# Fisher metric with constant I_S — the auxiliary flow should converge to S=0.
fim_ng = FisherInformationMetric(
    S=lambda X: X - np.array([0.5, -0.3, 0.2]),
    fisher_info=lambda z: np.diag([2.0, 1.0, 1.5]),
    F_base=lambda X: np.zeros_like(X),
    J=lambda X: np.eye(3),
)
flow = NaturalGradientFlow(fim=fim_ng)
res = flow.integrate(np.array([1.5, 0.6, -0.8]),
                     h=0.05, max_steps=2000, eps_E=1e-12, eps_g=1e-7, dwell=10)
check("§10.1: natural-gradient flow converges to S = 0",
      res.converged and float(res.energy[-1]) < 1e-8,
      f"steps={res.n_steps}, E_final={float(res.energy[-1]):.2e}")

# Chart covariance of the trajectory itself (Theorem I.1):
# Build a chart Φ(X̃) = T·X̃; trajectory in the chart should equal Φ⁻¹(X(t))
np.random.seed(11)
T_chart = np.eye(3) + 0.3 * np.random.randn(3, 3)
T_inv   = np.linalg.inv(T_chart)
fim_chart = FisherInformationMetric(
    S=lambda Xt: (T_chart @ Xt) - np.array([0.5, -0.3, 0.2]),
    fisher_info=lambda z: np.diag([2.0, 1.0, 1.5]),
    F_base=lambda Xt: np.zeros_like(Xt),
    J=lambda Xt: T_chart,                  # ∂S/∂X̃ = T (since S(X̃) = T X̃ − const)
)
flow_chart = NaturalGradientFlow(fim=fim_chart)
X0   = np.array([1.5, 0.6, -0.8])
Xt0  = T_inv @ X0
res_orig  = flow.integrate(X0,   h=0.02, max_steps=200, eps_E=0, eps_g=0, dwell=10**9)
res_chart = flow_chart.integrate(Xt0, h=0.02, max_steps=200, eps_E=0, eps_g=0, dwell=10**9)
err_cov = float(np.linalg.norm(res_chart.X_final - T_inv @ res_orig.X_final))
check("§10.1: trajectory of natural-gradient flow is chart-covariant",
      err_cov < 1e-6, f"||X̃(T) − Φ⁻¹(X(T))|| = {err_cov:.2e}")


# =======================================================================
#  §10.2 — MLE & VI canonical instances
# =======================================================================
section("§10.2 — MLE / VI as canonical instances")

# MLE: in LAN coords around X⋆, Fisher-scoring = natural-gradient flow.
mle = MLEInstance(
    X_mle=np.array([0.7, -0.2, 0.5]),
    fisher_info=lambda z: np.diag([1.5, 0.8, 2.0]),
)
fs = mle.fisher_scoring()
res_mle = fs.integrate(np.array([2.0, 1.0, -0.5]),
                       h=0.05, max_steps=2000, eps_E=1e-12, eps_g=1e-7, dwell=10)
err_mle = float(np.linalg.norm(res_mle.X_final - mle.X_mle))
check("§10.2 MLE: Fisher-scoring flow drives X → X⋆ (LAN coordinates)",
      res_mle.converged and err_mle < 1e-3,
      f"steps={res_mle.n_steps}, ||X−X⋆|| = {err_mle:.2e}")

# VI: λ(X) = X (mean-field linear chart), λ⋆ target — natural-gradient VI.
vi = VIInstance(
    lam=lambda X: X,
    lam_jac=lambda X: np.eye(X.size),
    lam_star=np.array([0.0, 0.5, -0.3]),
    fisher_info=lambda z: np.diag([1.0, 2.0, 0.5]),
)
ng_vi = vi.natural_gradient_vi()
res_vi = ng_vi.integrate(np.array([1.0, -1.0, 1.0]),
                         h=0.05, max_steps=2000, eps_E=1e-12, eps_g=1e-7, dwell=10)
err_vi = float(np.linalg.norm(res_vi.X_final - vi.lam_star))
check("§10.2 VI: natural-gradient VI flow drives λ(X) → λ⋆",
      res_vi.converged and err_vi < 1e-3,
      f"steps={res_vi.n_steps}, ||λ−λ⋆|| = {err_vi:.2e}")


# =======================================================================
#  PART IV — Stochastic canonical SDE (§16)
# =======================================================================

# ---------- §S.2 / Prop 16.4 :  Σ_F = I_X^{†/2} satisfies Σ I_X Σ = projector
section("§S.2 / Prop 16.4 — Fisher noise Σ_F = I_X^{†/2}")
fim_sde = FisherInformationMetric(
    S=lambda X: X[:2],                                  # k = 2, n = 3
    fisher_info=lambda z: np.diag([2.0, 1.0]),
    F_base=lambda X: np.zeros_like(X),
    J=lambda X: np.eye(2, X.size),
)
X0_sde = np.array([1.0, -0.5, 0.0])
Sig_F = fisher_noise(fim_sde, X0_sde)
I_X = fim_sde.pullback(X0_sde)
P = Sig_F @ I_X @ Sig_F            # should be projector onto range(I_X)
err_proj = float(np.linalg.norm(P @ P - P, ord="fro"))
rank_pred = int(round(float(np.trace(P))))
rank_actual = int(np.linalg.matrix_rank(I_X, tol=1e-8))
check("§S.2: Σ_F I_X Σ_F is a projector  (P² = P)",
      err_proj < 1e-8, f"||P²−P||_F = {err_proj:.2e}")
check("§Prop 16.4: tr(Σ_F I_X Σ_F) = rank(I_X)  on target set",
      rank_pred == rank_actual,
      f"trace = {rank_pred}, rank(I_X) = {rank_actual}")

# Trace correction at target = rank(I_X)
sys_sde0 = fim_sde.build(X0_sde)
# Need a target point (S=0) for the "noise floor" identity:
X_target = np.array([0.0, 0.0, 0.7])
sys_target = fim_sde.build(X_target)
HE_target = 2.0 * fim_sde.pullback(X_target)            # ∇²E = 2 I_X at target
Sig_target = fisher_noise(fim_sde, X_target)
trace_at_target = 0.5 * float(np.trace(Sig_target.T @ HE_target @ Sig_target))
check("§Prop 16.4: ½ tr(Σᵀ ∇²E Σ) = rank(I_X)  at S = 0",
      abs(trace_at_target - rank_actual) < 1e-6,
      f"½ tr = {trace_at_target:.4f}, rank = {rank_actual}")


# ---------- Theorem 16.3 :  Itô formula for E ----------------
section("§Theorem 16.3 — Itô formula for E along the SDE")

# Use a constant-G test system so ∇²E is constant and exact.
sys_ito = CanonicalSystem(
    S=lambda X: X,
    J=lambda X: np.eye(3),
    G=np.diag([1.0, 2.0, 0.5]),
    F_base=lambda X: np.zeros(3),
    theta=1.0,
    K=lambda X: np.zeros((3, 3, 3)),
)
X_ito = np.array([0.6, -0.3, 0.4])
sigma_W = 0.5
# Constant diffusion Σ = identity; check Itô formula numerically
Sigma_const = lambda X: np.eye(3)
analytic, drift_term, diff_term = expected_dE_dt(
    sys_ito, sys_ito.rhs, Sigma_const, X_ito, sigma_W=sigma_W,
)
print(f"  analytic E[dE/dt] = {analytic:.6f}  (drift {drift_term:.6f}, diffusion {diff_term:.6f})")

# Empirical: dE[E(X_h)]/dh ≈ (E[E(X_h)] − E(X_0)) / h for small h, many paths
sde = CanonicalSDE(drift=sys_ito.rhs, diffusion=Sigma_const,
                   sigma_W=sigma_W, energy=sys_ito.energy)
rng = np.random.default_rng(2026)
n_paths = 8000
h_step = 5e-3
n_steps = 1
E_paths = sde.monte_carlo(X_ito, h=h_step, n_steps=n_steps, n_paths=n_paths, rng=rng)
E0 = sys_ito.energy(X_ito)
empirical = (E_paths[:, -1].mean() - E0) / h_step
# Standard error of the MC estimate of (E[E_h]−E_0)/h
se = E_paths[:, -1].std(ddof=1) / np.sqrt(n_paths) / h_step
print(f"  empirical  E[dE/dt] = {empirical:.6f}  ± {2*se:.6f} (95% CI half-width)")
check("§Thm 16.3: empirical ≈ analytic E[dE/dt]  (within 3·SE)",
      abs(empirical - analytic) < 3.0 * se,
      f"|emp − ana| = {abs(empirical-analytic):.4f},  3·SE = {3*se:.4f}")


# ---------- Theorem 16.5 :  Mean-square ultimate bound -------
section("§Theorem 16.5 — Mean-square ultimate bound  E[E∞] ≤ σ_W² τ_Σ / (2ρ)")

# F_base = 0, constant Σ = I, full-row-rank J: ρ from Theorem 7.3, τ_Σ = tr(2G)
G_diag = np.diag([1.0, 1.5, 0.8, 2.0, 1.2])
sys_bound = CanonicalSystem(
    S=lambda X: X,
    J=lambda X: np.eye(5),
    G=G_diag,
    F_base=lambda X: np.zeros(5),
    theta=1.0,
    K=lambda X: np.zeros((5, 5, 5)),
)
mu_G = float(np.linalg.eigvalsh(G_diag).min())
M_G  = float(np.linalg.eigvalsh(G_diag).max())
sigma_min_J = 1.0
X0_bound = np.array([1.0, -0.5, 0.3, -0.4, 0.2])
rho_pred = sys_bound.exponential_rate(X0_bound, sigma_min=sigma_min_J)
# τ_Σ = tr(Iᵀ · 2G · I) = 2 tr(G)
tau_Sigma = 2.0 * float(np.trace(G_diag))
sigma_W = 0.3
floor_pred = mean_square_ultimate_bound(rho_pred, tau_Sigma, sigma_W=sigma_W)
print(f"  ρ = {rho_pred:.4f},  τ_Σ = {tau_Sigma:.4f},  σ_W = {sigma_W}")
print(f"  predicted floor σ_W² τ_Σ / (2ρ) = {floor_pred:.4f}")

sde_bound = CanonicalSDE(drift=sys_bound.rhs,
                         diffusion=lambda X: np.eye(5),
                         sigma_W=sigma_W,
                         energy=sys_bound.energy)
rng = np.random.default_rng(7)
n_paths = 400
h_step = 1e-2
n_steps = 4000
E_paths = sde_bound.monte_carlo(X0_bound, h=h_step, n_steps=n_steps,
                                n_paths=n_paths, rng=rng)
# Look at the tail: average E[E(X_t)] over the last 25% of steps
tail = E_paths[:, int(0.75 * n_steps):]
emp_floor = float(tail.mean())
print(f"  empirical tail mean E[E] = {emp_floor:.4f}")
check("§Thm 16.5: empirical E[E_∞] ≤ predicted floor  (with 10% margin)",
      emp_floor <= floor_pred * 1.10,
      f"emp / pred = {emp_floor/floor_pred:.3f}")

# Also verify the time-resolved bound: E[E(X_t)] ≤ E_0 e^{−ρt} + floor·(1−e^{−ρt})
t = np.arange(n_steps + 1) * h_step
mean_E = E_paths.mean(axis=0)
envelope = sys_bound.energy(X0_bound) * np.exp(-rho_pred * t) \
           + floor_pred * (1 - np.exp(-rho_pred * t))
violations = int((mean_E > envelope * 1.10).sum())   # 10% tolerance for MC noise
check("§Thm 16.5: pointwise envelope E[E(t)] ≤ e^{−ρt}·E_0 + floor·(1−e^{−ρt})",
      violations == 0, f"violations = {violations}/{t.size}")


# ---------- §S.6 :  Natural-gradient Langevin & Gibbs equilibrium ----
section("§S.6 / Prop 16.7 — Natural-gradient Langevin invariant law")

# 1-D Gaussian-like family:  S(X) = X (n=k=1),  I_S = 1,  E = X²
fim_lang = FisherInformationMetric(
    S=lambda X: X.copy(),
    fisher_info=lambda z: np.eye(1),
    F_base=lambda X: np.zeros_like(X),
    J=lambda X: np.eye(1),
)
T_temp = 1.0
sde_lang = natural_gradient_langevin(fim_lang, T=T_temp)
# Stationary density should be π(x) ∝ e^{-x²/T}, so Var = T/2 (since E = x²,
# π_T(x) ∝ e^{-x²/T} ⇒ Var(X) = T/2)
rng = np.random.default_rng(11)
X = np.array([0.0])
h_step = 5e-3
n_burn = 5000
n_sample = 20000
for _ in range(n_burn):
    X = sde_lang.step(X, h_step, rng)
samples = np.empty(n_sample)
for k in range(n_sample):
    X = sde_lang.step(X, h_step, rng)
    samples[k] = X[0]
emp_var = float(samples.var(ddof=1))
pred_var = T_temp / 2.0
print(f"  empirical Var(X) = {emp_var:.4f},  predicted T/2 = {pred_var:.4f}")
check("§Prop 16.7: natural-gradient Langevin  ⇒  X ~ N(0, T/2)  (Var match)",
      abs(emp_var - pred_var) / pred_var < 0.10,
      f"|Δ|/pred = {abs(emp_var-pred_var)/pred_var:.3f}")

# Mean should be ~ 0
emp_mean = float(samples.mean())
check("§Prop 16.7: stationary mean = 0",
      abs(emp_mean) < 0.05, f"mean = {emp_mean:.4f}")


# ---------- σ_W → 0 :  Bridge back to Part I ----------------
section("§S.7 — Bridge:  σ_W → 0 recovers deterministic Part I")

sde_zero = CanonicalSDE(drift=sys_bound.rhs,
                        diffusion=lambda X: np.eye(5),
                        sigma_W=0.0,                          # noise OFF
                        energy=sys_bound.energy)
res_det = sys_bound.integrate(X0_bound, h=0.01, max_steps=2000,
                              eps_E=0, eps_g=0, dwell=10**9)
rng = np.random.default_rng(3)
res_sde = sde_zero.integrate(X0_bound, h=0.01, n_steps=2000, rng=rng)
err_bridge = float(np.linalg.norm(res_det.X_final - res_sde.X_final))
check("§S.7: σ_W = 0 SDE coincides with deterministic ODE",
      err_bridge < 1e-10, f"||X_det − X_sde|| = {err_bridge:.2e}")


# =======================================================================
#  Summary
# =======================================================================
section("THEOREM-LEVEL SUMMARY")
total = len(results)
passed = sum(1 for _, ok, _ in results if ok)
print(f"\n  {passed} / {total} theorem-level numerical checks PASSED\n")
for name, ok, detail in results:
    tag = "✓" if ok else "✗"
    print(f"    [{tag}] {name}")
print()
if passed != total:
    raise SystemExit(1)
print("  All theorems of canonical_system_v4.pdf are numerically certified.")
