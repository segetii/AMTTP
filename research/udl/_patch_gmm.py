"""Line-number-based patch for GMM fixes to ReducedTensorDescriptor."""
import sys, os

FP = os.path.join(os.path.dirname(__file__), 'udl', 'system_mode.py')
with open(FP, encoding='utf-8') as f:
    lines = f.readlines()

print(f'Original lines: {len(lines)}')
if '_batch_gmm_compute' in ''.join(lines):
    print('Already patched.'); sys.exit(0)

# Verify anchor lines (0-indexed)
assert 'self._ref_data' in lines[1611], f'L1612 mismatch: {repr(lines[1611])}'
assert 'self._fitted = False' in lines[1612], f'L1613 mismatch: {repr(lines[1612])}'
assert 'self.n_eigs = min(d, 10)' in lines[1652], f'L1653 mismatch: {repr(lines[1652])}'
assert 'self._fitted = True' in lines[1654], f'L1655 mismatch: {repr(lines[1654])}'
assert 'return self' in lines[1655], f'L1656 mismatch: {repr(lines[1655])}'
assert 'for i in range(N):' in lines[1690], f'L1691 mismatch: {repr(lines[1690])}'
assert 'n_eigs + 3' in lines[1713], f'L1714 mismatch: {repr(lines[1713])}'
assert '_to_scalar' in lines[1800], f'L1801 mismatch: {repr(lines[1800])}'
print('All anchors verified.')

# ─── PATCH 1: Add _gmm and _eps_adapted after line 1612 (self._ref_data) ──
insert1 = [
    '        self._gmm = None\n',
    '        self._eps_adapted: float = eps_hessian\n',
]
# Insert after line 1612 (index 1611) → after self._ref_data
idx = 1612  # insert before self._fitted = False
lines[idx:idx] = insert1
print(f'  [1/4] __init__:  +{len(insert1)} lines at {idx}')

# Adjust all subsequent indices by the insertion
off1 = len(insert1)  # 2

# ─── PATCH 2: Insert GMM fitting before self._fitted = True ──
# Original line 1655 → now 1655 + off1
fit_idx = 1654 + off1  # the blank line before self._fitted = True
gmm_block = [
    '        # -- GMM for non-trivial energy landscape --\n',
    '        # A single-Gaussian Mahalanobis energy is strictly convex\n',
    '        # (Hessian = cov_inv, always PD), so Morse index = 0 always.\n',
    '        # A GMM with k>=2 components creates saddle points between\n',
    '        # cluster boundaries, enabling meaningful Morse index detection.\n',
    '        from sklearn.mixture import GaussianMixture\n',
    '        n_comp = min(max(2, int(np.sqrt(N / 20))), 8)\n',
    '        self._gmm = GaussianMixture(\n',
    "            n_components=n_comp, covariance_type='full',\n",
    '            random_state=42, n_init=3, max_iter=200)\n',
    '        self._gmm.fit(self._ref_data)\n',
    '\n',
    '        # Adapt finite-difference step to data scale\n',
    '        self._eps_adapted = max(np.std(self._ref_data, axis=0).mean() * 0.01,\n',
    '                                1e-6)\n',
    '\n',
]
lines[fit_idx:fit_idx] = gmm_block
print(f'  [2/4] fit():     +{len(gmm_block)} lines at {fit_idx}')

off2 = off1 + len(gmm_block)  # total offset

# ─── PATCH 3: Replace gradient/Hessian loops (lines 1690-1714 orig) ──
# Original lines 1690-1714 become 1690+off2 to 1714+off2
loop_start = 1689 + off2   # 0-indexed for original line 1690
loop_end   = 1714 + off2   # 0-indexed for original line 1714 (inclusive)

new_loops = [
    '        # -- 1 & 2.  Gradient + Hessian (vectorised) --\n',
    '        if gradient_fn is not None or energy_fn is not None:\n',
    '            # Per-point fallback for custom energy / gradient\n',
    '            for i in range(N):\n',
    '                xi = X[i]\n',
    '                if gradient_fn is not None:\n',
    '                    grad = gradient_fn(xi)\n',
    '                elif energy_fn is not None:\n',
    '                    grad = self._numerical_gradient(xi, energy_fn)\n',
    '                else:\n',
    '                    diff = xi - self._ref_mean\n',
    '                    grad = self._ref_cov_inv @ diff\n',
    '                out[i, 0] = np.linalg.norm(grad)\n',
    '\n',
    '            for i in range(N):\n',
    '                xi = X[i]\n',
    '                if energy_fn is not None:\n',
    '                    eigs = self._hessian_eigenvalues(\n',
    '                        xi, energy_fn, n_eigs)\n',
    '                else:\n',
    '                    eigs = np.linalg.eigvalsh(\n',
    '                        self._ref_cov_inv)[:n_eigs]\n',
    '                out[i, 1:1+n_eigs] = np.sort(eigs)\n',
    '                out[i, n_eigs + 3] = np.sum(eigs)\n',
    '        else:\n',
    '            # Batch GMM-based computation -- non-trivial Hessian\n',
    '            # that can have negative eigenvalues (saddle points).\n',
    '            grad_mat, hess_eigs = self._batch_gmm_compute(X, n_eigs)\n',
    '            out[:, 0] = np.linalg.norm(grad_mat, axis=1)\n',
    '            out[:, 1:1+n_eigs] = hess_eigs\n',
    '            out[:, n_eigs + 3] = hess_eigs.sum(axis=1)  # trace\n',
]

lines[loop_start:loop_end+1] = new_loops
print(f'  [3/4] transform: replaced lines {loop_start}-{loop_end} with {len(new_loops)} lines')

off3 = off2 + (len(new_loops) - (loop_end - loop_start + 1))

# ─── PATCH 4: Add _batch_gmm_compute + score() before _to_scalar ──
# Original line 1800 (_to_scalar) → adjusted
to_scalar_orig = 1799  # 0-indexed for original line 1800 (@staticmethod)
# But we need to insert BEFORE line 1798 (# -- private helpers) 
# Actually, insert AFTER the "# -- private helpers --" + blank line, BEFORE @staticmethod
helpers_line = 1797 + off3  # 0-indexed => original 1798 (comment)
# Insert after blank line (1798) = 1799 orig → 1799 + off3
insert_before = 1799 + off3  # @staticmethod line

new_methods = [
    '    def _batch_gmm_compute(self, X: np.ndarray,\n',
    '                           n_eigs: int):\n',
    '        """Vectorised gradient + Hessian eigenvalues via GMM energy.\n',
    '\n',
    '        Uses ``-log p_GMM(x)`` as the energy function.  The GMM creates\n',
    '        saddle points at cluster boundaries, giving non-trivial\n',
    '        Morse indices (number of negative Hessian eigenvalues).\n',
    '\n',
    '        Total GMM score_samples calls = 2d + 4*d(d+1)/2\n',
    '        = 2d + 2d(d+1) ~ 2d^2 + 4d  (e.g. 70 calls for d=5).\n',
    '\n',
    '        Returns\n',
    '        -------\n',
    '        grad : (N, d) array  -- gradient vectors\n',
    '        eigs : (N, n_eigs)   -- sorted ascending Hessian eigenvalues\n',
    '        """\n',
    '        N, d = X.shape\n',
    '        eps = self._eps_adapted\n',
    '\n',
    '        # -- Gradient via central difference --\n',
    '        grad = np.zeros((N, d), dtype=np.float64)\n',
    '        for i in range(d):\n',
    '            delta = np.zeros(d, dtype=np.float64)\n',
    '            delta[i] = eps\n',
    '            fp = -self._gmm.score_samples(X + delta)\n',
    '            fm = -self._gmm.score_samples(X - delta)\n',
    '            grad[:, i] = (fp - fm) / (2 * eps)\n',
    '\n',
    '        # -- Hessian via finite difference (symmetric) --\n',
    '        H = np.zeros((N, d, d), dtype=np.float64)\n',
    '        eps2_inv = 1.0 / (4 * eps * eps)\n',
    '        for i in range(d):\n',
    '            ei = np.zeros(d, dtype=np.float64); ei[i] = eps\n',
    '            for j in range(i, d):\n',
    '                ej = np.zeros(d, dtype=np.float64); ej[j] = eps\n',
    '                fpp = -self._gmm.score_samples(X + ei + ej)\n',
    '                fpm = -self._gmm.score_samples(X + ei - ej)\n',
    '                fmp = -self._gmm.score_samples(X - ei + ej)\n',
    '                fmm = -self._gmm.score_samples(X - ei - ej)\n',
    '                H[:, i, j] = (fpp - fpm - fmp + fmm) * eps2_inv\n',
    '                if j != i:\n',
    '                    H[:, j, i] = H[:, i, j]\n',
    '\n',
    '        eigs = np.linalg.eigvalsh(H)          # (N, d) ascending\n',
    '        return grad, eigs[:, :n_eigs]\n',
    '\n',
    '    def score(self, X: np.ndarray,\n',
    '              energy_fn=None,\n',
    '              gradient_fn=None) -> np.ndarray:\n',
    '        """Combined anomaly score from the descriptor.\n',
    '\n',
    '        Uses robust percentile normalisation (instead of min-max)\n',
    '        and learned weights that emphasise Morse index + Mahalanobis.\n',
    '\n',
    '        Returns\n',
    '        -------\n',
    '        scores : (N,) array -- higher = more anomalous\n',
    '        """\n',
    '        D = self.transform(X, energy_fn, gradient_fn)\n',
    '        n_eigs = min(self.n_eigs, X.shape[1])\n',
    '\n',
    '        grad_norm = D[:, 0]\n',
    '        mahalanobis = D[:, n_eigs + 1]\n',
    '        medoid_dist = D[:, n_eigs + 2]\n',
    '        trace_h = D[:, n_eigs + 3]\n',
    '        morse_idx = D[:, n_eigs + 5]\n',
    '\n',
    '        def robust_norm(x):\n',
    '            q1, q99 = np.percentile(x, [1, 99])\n',
    '            xn = (x - q1) / (q99 - q1 + 1e-15)\n',
    '            return np.clip(xn, 0.0, 1.0)\n',
    '\n',
    '        s = (0.25 * robust_norm(grad_norm) +\n',
    '             0.30 * robust_norm(mahalanobis) +\n',
    '             0.15 * robust_norm(medoid_dist) +\n',
    '             0.10 * robust_norm(np.abs(trace_h)) +\n',
    '             0.20 * robust_norm(morse_idx.astype(np.float64)))\n',
    '        return s\n',
    '\n',
]

lines[insert_before:insert_before] = new_methods
print(f'  [4/4] methods:   +{len(new_methods)} lines at {insert_before}')

# Write back
with open(FP, 'w', encoding='utf-8') as f:
    f.writelines(lines)

total = len(lines)
joined = ''.join(lines)
print(f'\nPatched OK.  Total lines: {total}')
print(f'  _gmm:              {"self._gmm" in joined}')
print(f'  _batch_gmm_compute: {"_batch_gmm_compute" in joined}')
print(f'  score():           {"def score(self, X" in joined}')
print(f'  robust_norm:       {"robust_norm" in joined}')
print(f'  GaussianMixture:   {"GaussianMixture" in joined}')
print(f'  _eps_adapted:      {"_eps_adapted" in joined}')
