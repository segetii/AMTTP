"""
Optimise MolecularEngine Algorithm 1 for performance:
1. Power iteration uses a subsample (max 200 points) instead of all points
2. λ_max is only recomputed every 10 steps (cached between)
3. Default power iterations reduced to 3 (Rayleigh converges fast for dominant eigenvalue)
4. Reuse the base force F0 from the main loop instead of recomputing
"""
import os

FILE = os.path.join('research', 'udl', 'udl', 'system_mode.py')

with open(FILE, encoding='utf-8') as f:
    content = f.read()

# ═══════════════════════════════════════════════════════════════════
#  Replace _pairwise_hessian_lambda_max with subsampled version
# ═══════════════════════════════════════════════════════════════════

old_method = (
    '    def _pairwise_hessian_lambda_max(self, X: np.ndarray,\n'
    '                                    n_power_iters: int = 8,\n'
    '                                    fd_eps: float = 1e-4) -> float:\n'
    '        """Estimate λ_max of D²Φ_pair via power iteration (Rayleigh quotient).\n'
    '\n'
    '        Uses matrix-free Hessian-vector products via finite differencing\n'
    '        of the pairwise force (negative gradient of pairwise potential).\n'
    '        Cost: n_power_iters × 1 extra force evaluation per iteration step.\n'
    '\n'
    '        Returns\n'
    '        -------\n'
    '        lambda_max : float\n'
    '            Estimated largest eigenvalue of the pairwise Hessian.\n'
    '        """\n'
    '        n, d = X.shape\n'
    '        # Random initial direction (fixed seed for reproducibility)\n'
    '        rng = np.random.RandomState(42)\n'
    '        v = rng.randn(n, d).astype(np.float64)\n'
    '        v /= (np.linalg.norm(v) + 1e-15)\n'
    '\n'
    '        # Base pairwise force at current position\n'
    '        F0 = self._lennard_jones_forces(X)\n'
    '\n'
    '        lambda_est = 1.0\n'
    '        for _ in range(n_power_iters):\n'
    '            # Hessian-vector product via central finite difference:\n'
    '            # H·v ≈ −(F(X + ε·v) − F(X − ε·v)) / (2ε)\n'
    '            # (negative because F = −∇Φ, so ∇F = −H)\n'
    '            F_plus = self._lennard_jones_forces(X + fd_eps * v)\n'
    '            F_minus = self._lennard_jones_forces(X - fd_eps * v)\n'
    '            Hv = -(F_plus - F_minus) / (2.0 * fd_eps)\n'
    '\n'
    '            # Rayleigh quotient: λ ≈ v^T H v / v^T v\n'
    '            lambda_est = float(np.sum(v * Hv)) / (float(np.sum(v * v)) + 1e-15)\n'
    '\n'
    '            # Power iteration update: v ← Hv / ||Hv||\n'
    '            norm_Hv = np.linalg.norm(Hv)\n'
    '            if norm_Hv < 1e-15:\n'
    '                break\n'
    '            v = Hv / norm_Hv\n'
    '\n'
    '        return max(abs(lambda_est), 1e-10)'
)

new_method = (
    '    def _pairwise_hessian_lambda_max(self, X: np.ndarray,\n'
    '                                    n_power_iters: int = 3,\n'
    '                                    fd_eps: float = 1e-4,\n'
    '                                    max_hessian_pts: int = 200) -> float:\n'
    '        """Estimate λ_max of D²Φ_pair via power iteration (Rayleigh quotient).\n'
    '\n'
    '        Uses matrix-free Hessian-vector products via finite differencing\n'
    '        of the pairwise force (negative gradient of pairwise potential).\n'
    '        Subsamples to max_hessian_pts for efficiency.\n'
    '\n'
    '        Returns\n'
    '        -------\n'
    '        lambda_max : float\n'
    '            Estimated largest eigenvalue of the pairwise Hessian.\n'
    '        """\n'
    '        n, d = X.shape\n'
    '        # Subsample for Hessian estimation if dataset is large\n'
    '        if n > max_hessian_pts:\n'
    '            rng_sub = np.random.RandomState(7)\n'
    '            idx = rng_sub.choice(n, max_hessian_pts, replace=False)\n'
    '            Xs = X[idx]\n'
    '        else:\n'
    '            Xs = X\n'
    '        ns = len(Xs)\n'
    '\n'
    '        rng = np.random.RandomState(42)\n'
    '        v = rng.randn(ns, d).astype(np.float64)\n'
    '        v /= (np.linalg.norm(v) + 1e-15)\n'
    '\n'
    '        lambda_est = 1.0\n'
    '        for _ in range(n_power_iters):\n'
    '            # H·v ≈ −(F(Xs + ε·v) − F(Xs − ε·v)) / (2ε)\n'
    '            F_plus = self._lennard_jones_forces(Xs + fd_eps * v)\n'
    '            F_minus = self._lennard_jones_forces(Xs - fd_eps * v)\n'
    '            Hv = -(F_plus - F_minus) / (2.0 * fd_eps)\n'
    '\n'
    '            # Rayleigh quotient\n'
    '            lambda_est = float(np.sum(v * Hv)) / (float(np.sum(v * v)) + 1e-15)\n'
    '\n'
    '            norm_Hv = np.linalg.norm(Hv)\n'
    '            if norm_Hv < 1e-15:\n'
    '                break\n'
    '            v = Hv / norm_Hv\n'
    '\n'
    '        return max(abs(lambda_est), 1e-10)'
)

assert old_method in content, "Old _pairwise_hessian_lambda_max not found!"
content = content.replace(old_method, new_method, 1)
print("1. Replaced _pairwise_hessian_lambda_max with subsampled version")


# ═══════════════════════════════════════════════════════════════════
#  Add λ_max caching: only recompute every 10 steps
# ═══════════════════════════════════════════════════════════════════

old_loop_hessian = (
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
    "                gamma_target = self.alpha_radial / (lambda_max + 1e-10)"
)

new_loop_hessian = (
    "            if bsdt_damper is not None:\n"
    "                # Step 2: Power iteration on pairwise Hessian → λ_max\n"
    "                # Cached: recompute every 10 steps (smooth enough for OGD)\n"
    "                if step % 10 == 0:\n"
    "                    lambda_max = self._pairwise_hessian_lambda_max(\n"
    "                        X_work, n_power_iters=3)\n"
    "\n"
    "                # Step 3: Target γ* = α / λ_max (marginal stability)\n"
    "                gamma_target = self.alpha_radial / (lambda_max + 1e-10)"
)

assert old_loop_hessian in content, "Old loop Hessian block not found!"
content = content.replace(old_loop_hessian, new_loop_hessian, 1)
print("2. λ_max cached: recomputed every 10 steps")

# Need to initialise lambda_max before the loop
old_before_loop = "        # OGD state: initialise γ at 0 (no damping initially)\n        gamma_ogd = 0.0"
new_before_loop = (
    "        # OGD state: initialise γ at 0 (no damping initially)\n"
    "        gamma_ogd = 0.0\n"
    "        lambda_max = 1.0  # will be updated on first step"
)
assert old_before_loop in content, "OGD init block not found!"
content = content.replace(old_before_loop, new_before_loop, 1)
print("3. Added lambda_max init before loop")


# ═══════════════════════════════════════════════════════════════════
#  Write and verify
# ═══════════════════════════════════════════════════════════════════
with open(FILE, 'w', encoding='utf-8') as f:
    f.write(content)

with open(FILE, encoding='utf-8') as f:
    v = f.read()

total = v.count('\n') + 1
print(f"\nTotal lines: {total}")

# Verify
mol_start = v.index('class MolecularEngine:')
mol_end = v.index('class GravityModeEngine:')
mol_text = v[mol_start:mol_end]

checks = {
    'max_hessian_pts': 'max_hessian_pts' in mol_text,
    'subsample Hessian': 'Xs = X[idx]' in mol_text,
    'step % 10': 'step % 10 == 0' in mol_text,
    'n_power_iters=3': 'n_power_iters=3' in mol_text,
    'gamma_target': 'gamma_target' in mol_text,
    'gamma_ogd': 'gamma_ogd' in mol_text,
    'lambda_max init': 'lambda_max = 1.0' in mol_text,
}

all_ok = True
for name, ok in checks.items():
    status = "OK" if ok else "FAIL"
    print(f"  {status}: {name}")
    if not ok:
        all_ok = False

print("\nAll checks passed!" if all_ok else "\nSome checks FAILED!")
