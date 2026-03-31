"""
Rewrite MolecularEngine damping to match the paper's Algorithm 1:

1. Compute normal forces ∇Φ (pairwise + radial)
2. Power iteration on pairwise Hessian → λ_max  (Rayleigh quotient)
3. Target γ* = α / λ_max  (marginal stability)
4. Refine actual γ via projected OGD  (O(√T) regret)
5. Damping force: −γ · ∇E_BS(X)
6. Euler step + Armijo line search

The E/(E+θ) form is the "dynamic programming alternative" — this code
implements the primary spectral-radius form with online learning.
"""
import os

FILE = os.path.join('research', 'udl', 'udl', 'system_mode.py')

with open(FILE, encoding='utf-8') as f:
    content = f.read()

# ═══════════════════════════════════════════════════════════════════
#  Step 1: Add power iteration method + OGD state to MolecularEngine
# ═══════════════════════════════════════════════════════════════════

# Find the insertion point: after __init__ body, before _lennard_jones_forces
old_after_init = (
    "    def _lennard_jones_forces(self, X: np.ndarray,\n"
    "                              eps: float = 1e-5) -> np.ndarray:\n"
    "        \"\"\"Compute Lennard-Jones forces between all particle pairs.\"\"\""
)

new_methods_plus_lj = '''    def _pairwise_hessian_lambda_max(self, X: np.ndarray,
                                    n_power_iters: int = 8,
                                    fd_eps: float = 1e-4) -> float:
        """Estimate λ_max of D²Φ_pair via power iteration (Rayleigh quotient).

        Uses matrix-free Hessian-vector products via finite differencing
        of the pairwise force (negative gradient of pairwise potential).
        Cost: n_power_iters × 1 extra force evaluation per iteration step.

        Returns
        -------
        lambda_max : float
            Estimated largest eigenvalue of the pairwise Hessian.
        """
        n, d = X.shape
        # Random initial direction (fixed seed for reproducibility)
        rng = np.random.RandomState(42)
        v = rng.randn(n, d).astype(np.float64)
        v /= (np.linalg.norm(v) + 1e-15)

        # Base pairwise force at current position
        F0 = self._lennard_jones_forces(X)

        lambda_est = 1.0
        for _ in range(n_power_iters):
            # Hessian-vector product via central finite difference:
            # H·v ≈ −(F(X + ε·v) − F(X − ε·v)) / (2ε)
            # (negative because F = −∇Φ, so ∇F = −H)
            F_plus = self._lennard_jones_forces(X + fd_eps * v)
            F_minus = self._lennard_jones_forces(X - fd_eps * v)
            Hv = -(F_plus - F_minus) / (2.0 * fd_eps)

            # Rayleigh quotient: λ ≈ v^T H v / v^T v
            lambda_est = float(np.sum(v * Hv)) / (float(np.sum(v * v)) + 1e-15)

            # Power iteration update: v ← Hv / ||Hv||
            norm_Hv = np.linalg.norm(Hv)
            if norm_Hv < 1e-15:
                break
            v = Hv / norm_Hv

        return max(abs(lambda_est), 1e-10)

    def _lennard_jones_forces(self, X: np.ndarray,
                              eps: float = 1e-5) -> np.ndarray:
        """Compute Lennard-Jones forces between all particle pairs."""'''

assert old_after_init in content, "MolecularEngine _lennard_jones_forces not found!"
content = content.replace(old_after_init, new_methods_plus_lj, 1)
print("Step 1: Added _pairwise_hessian_lambda_max method")


# ═══════════════════════════════════════════════════════════════════
#  Step 2: Replace the BSDT damping setup + loop with Algorithm 1
# ═══════════════════════════════════════════════════════════════════

# The whole damping setup + iteration needs to be replaced
old_damping_and_loop = (
    "        # ── Optional BSDT adaptive damping ──────\n"
    "        # When enabled: Ẋ = F(X) − γ(E_BS) · ∇E_BS(X)\n"
    "        # When disabled: Ẋ = F(X)  (pure physics, no friction)\n"
    "        bsdt_damper = None\n"
    "        theta_bs = 1.0\n"
    "        beta_mfls = 0.0\n"
    "        if self.use_bsdt_damping:\n"
    "            bsdt_damper = BSDTChannels(k=min(self.k_neighbors,\n"
    "                                             len(X_work) - 1))\n"
    "            X_ref_init = X_work[normal_mask] if normal_mask.sum() > 5 \\\n"
    "                else X_work\n"
    "            bsdt_damper.fit(X_ref_init)\n"
    "            e_ref = bsdt_damper.energy(X_ref_init)\n"
    "            theta_bs = float(np.median(e_ref)) + 1e-10\n"
    "            mfls_ref = bsdt_damper.mfls(X_ref_init)\n"
    "            mfls_med = float(np.median(mfls_ref)) + 1e-10\n"
    "            beta_mfls = theta_bs / mfls_med\n"
    "\n"
    "        # ── Euler integration with Lyapunov v2 stability control ──\n"
    "        self.stabiliser.reset()\n"
    "        eta = self.eta\n"
    "        n_sim = len(X_work)\n"
    "        # Reduce iterations for large subsamples\n"
    "        iters = self.iterations if n_sim <= 1000 else max(20, self.iterations // 2)\n"
    "        for step in range(iters):\n"
    "            # Compute physics forces\n"
    "            F_lj = self._lennard_jones_forces(X_work)\n"
    "            F_radial = -self.alpha_radial * (X_work - self.mu_)\n"
    "\n"
    "            # Damping: optional BSDT adaptive friction\n"
    "            if bsdt_damper is not None:\n"
    "                e_bs = bsdt_damper.energy(X_work)\n"
    "                grad_bs = bsdt_damper._gradient_vectors(X_work)\n"
    "                mfls_bs = np.linalg.norm(grad_bs, axis=1)\n"
    "                e_combined = e_bs + beta_mfls * mfls_bs\n"
    "                gamma_bs = e_combined / (e_combined + theta_bs)\n"
    "                F_damp = -gamma_bs[:, None] * grad_bs\n"
    "                F_total = F_lj + F_radial + F_damp\n"
    "            else:\n"
    "                F_total = F_lj + F_radial\n"
    "\n"
    "            # Barrier-augmented force clamping (solver stability only)\n"
    "            F_total = self.stabiliser.clamp_forces(F_total)\n"
    "\n"
    "            # Armijo backtracking with descent certificate\n"
    "            E_old = self._lj_energy(X_work)\n"
    "            grad_norm_sq = float(np.sum(F_total ** 2))\n"
    "            X_candidate = X_work + eta * F_total\n"
    "\n"
    "            E_new = self._lj_energy(X_candidate)\n"
    "            accept, eta = self.stabiliser.accept_step(\n"
    "                E_old, E_new, grad_norm_sq, eta\n"
    "            )\n"
    "\n"
    "            if accept:\n"
    "                X_work = X_candidate\n"
    "            else:\n"
    "                # Reduced step\n"
    "                X_work = X_work + eta * F_total\n"
    "\n"
    "            # La Salle convergence check (∇E → 0) with displacement fallback\n"
    "            displacement = eta * np.max(np.linalg.norm(F_total, axis=1))\n"
    "            if self.stabiliser.check_convergence(grad_norm_sq, displacement):\n"
    "                break"
)

new_damping_and_loop = (
    "        # ══════════════════════════════════════════════════════════\n"
    "        #  Algorithm 1: Adaptive GravityEngine (paper-correct)\n"
    "        #\n"
    "        #  Ẋ = −∇Φ(X) − γ(E_BS) · ∇E_BS(X)\n"
    "        #\n"
    "        #  Step 1: Compute normal forces ∇Φ (pairwise + radial)\n"
    "        #  Step 2: Power iteration on D²Φ_pair → λ_max\n"
    "        #  Step 3: Target γ* = α / λ_max  (marginal stability)\n"
    "        #  Step 4: Refine γ via projected OGD  (O(√T) regret)\n"
    "        #  Step 5: Damping force = −γ · ∇E_BS(X)\n"
    "        #  Step 6: Euler step + Armijo line search\n"
    "        # ══════════════════════════════════════════════════════════\n"
    "\n"
    "        # ── BSDT blind-spot energy for damping direction ──\n"
    "        bsdt_damper = None\n"
    "        if self.use_bsdt_damping:\n"
    "            bsdt_damper = BSDTChannels(k=min(self.k_neighbors,\n"
    "                                             len(X_work) - 1))\n"
    "            X_ref_init = X_work[normal_mask] if normal_mask.sum() > 5 \\\n"
    "                else X_work\n"
    "            bsdt_damper.fit(X_ref_init)\n"
    "\n"
    "        # ── Euler integration with Lyapunov stability + Algorithm 1 damping ──\n"
    "        self.stabiliser.reset()\n"
    "        eta = self.eta\n"
    "        n_sim = len(X_work)\n"
    "        iters = self.iterations if n_sim <= 1000 else max(20, self.iterations // 2)\n"
    "\n"
    "        # OGD state: initialise γ at 0 (no damping initially)\n"
    "        gamma_ogd = 0.0\n"
    "\n"
    "        for step in range(iters):\n"
    "            # Step 1: Compute normal forces ∇Φ\n"
    "            F_lj = self._lennard_jones_forces(X_work)\n"
    "            F_radial = -self.alpha_radial * (X_work - self.mu_)\n"
    "\n"
    "            if bsdt_damper is not None:\n"
    "                # Step 2: Power iteration on pairwise Hessian → λ_max\n"
    "                # Rayleigh quotient estimate (8 iterations is sufficient\n"
    "                # for the dominant eigenvalue to converge).\n"
    "                lambda_max = self._pairwise_hessian_lambda_max(\n"
    "                    X_work, n_power_iters=8)\n"
    "\n"
    "                # Step 3: Target γ* = α / λ_max (marginal stability)\n"
    "                # This pins damping at exactly the level needed to\n"
    "                # neutralise the largest curvature of the pairwise\n"
    "                # potential — marginal stability at C*.\n"
    "                gamma_target = self.alpha_radial / (lambda_max + 1e-10)\n"
    "\n"
    "                # Step 4: Projected online gradient descent\n"
    "                # Learning rate η_ogd = 1/√(t+1) gives O(√T) regret.\n"
    "                # Loss: ℓ(γ) = (γ − γ*)² — track the spectral target.\n"
    "                # Projection: γ ∈ [0, 2·γ*] (prevent over-damping).\n"
    "                eta_ogd = 1.0 / np.sqrt(step + 1)\n"
    "                grad_ogd = 2.0 * (gamma_ogd - gamma_target)\n"
    "                gamma_ogd = gamma_ogd - eta_ogd * grad_ogd\n"
    "                gamma_ogd = float(np.clip(gamma_ogd, 0.0,\n"
    "                                         2.0 * gamma_target))\n"
    "\n"
    "                # Step 5: Damping force = −γ · ∇E_BS(X)\n"
    "                # Direction from blind-spot energy gradient;\n"
    "                # magnitude from spectral-radius adaptive coefficient.\n"
    "                grad_bs = bsdt_damper._gradient_vectors(X_work)\n"
    "                F_damp = -gamma_ogd * grad_bs\n"
    "                F_total = F_lj + F_radial + F_damp\n"
    "            else:\n"
    "                F_total = F_lj + F_radial\n"
    "\n"
    "            # Barrier-augmented force clamping (solver stability only)\n"
    "            F_total = self.stabiliser.clamp_forces(F_total)\n"
    "\n"
    "            # Step 6: Armijo backtracking with descent certificate\n"
    "            E_old = self._lj_energy(X_work)\n"
    "            grad_norm_sq = float(np.sum(F_total ** 2))\n"
    "            X_candidate = X_work + eta * F_total\n"
    "\n"
    "            E_new = self._lj_energy(X_candidate)\n"
    "            accept, eta = self.stabiliser.accept_step(\n"
    "                E_old, E_new, grad_norm_sq, eta\n"
    "            )\n"
    "\n"
    "            if accept:\n"
    "                X_work = X_candidate\n"
    "            else:\n"
    "                # Reduced step\n"
    "                X_work = X_work + eta * F_total\n"
    "\n"
    "            # La Salle convergence check\n"
    "            displacement = eta * np.max(np.linalg.norm(F_total, axis=1))\n"
    "            if self.stabiliser.check_convergence(grad_norm_sq, displacement):\n"
    "                break"
)

assert old_damping_and_loop in content, "Old damping+loop block not found!"
content = content.replace(old_damping_and_loop, new_damping_and_loop, 1)
print("Step 2: Replaced damping with Algorithm 1 (power iteration + OGD)")


# ═══════════════════════════════════════════════════════════════════
#  Write and verify
# ═══════════════════════════════════════════════════════════════════
with open(FILE, 'w', encoding='utf-8') as f:
    f.write(content)

with open(FILE, encoding='utf-8') as f:
    v = f.read()

total = v.count('\n') + 1
print(f"\nTotal lines: {total}")

# Find MolecularEngine and verify contents
mol_start = v.index('class MolecularEngine:')
mol_end = v.index('class GravityModeEngine:')
mol_text = v[mol_start:mol_end]

checks = {
    '_pairwise_hessian_lambda_max': 'def _pairwise_hessian_lambda_max' in mol_text,
    'power_iteration': 'Power iteration' in mol_text,
    'gamma_target': 'gamma_target = self.alpha_radial / (lambda_max' in mol_text,
    'projected OGD': 'eta_ogd' in mol_text,
    'gamma_ogd': 'gamma_ogd' in mol_text,
    'F_damp = -gamma_ogd': 'F_damp = -gamma_ogd * grad_bs' in mol_text,
    'Armijo': 'Armijo' in mol_text,
    'no E/(E+theta)': 'e_combined' not in mol_text,
    'no beta_mfls': 'beta_mfls' not in mol_text,
}

all_ok = True
for name, ok in checks.items():
    status = "OK" if ok else "FAIL"
    print(f"  {status}: {name}")
    if not ok:
        all_ok = False

# Verify other engines still present
for cls in ['Mode4GravityEngine', 'Mode5GravityEngine', 'Mode6GravityEngine',
            'Mode7GravityEngine', 'HybridGravityEngine']:
    if f'class {cls}:' in v:
        print(f"  OK: {cls} present")
    else:
        print(f"  FAIL: {cls} missing!")
        all_ok = False

if all_ok:
    print("\nAll checks passed! Algorithm 1 damping implemented.")
else:
    print("\nSome checks FAILED!")
