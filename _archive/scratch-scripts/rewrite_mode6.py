"""
Rewrite Mode6GravityEngine with correct stacked-layer architecture.

Architecture:
  Layer 1: BSDT adaptive damping in gravity iteration (gradient descent / Lyapunov ISS)
  Layer 2: BSDT channel extraction on final positions -> (N, 4) channel matrix
  Layer 3: MFLSQuadSurf or MFLSExpoGate stacked on channels
           (supervised polynomial ridge regression, labels from y)

QuadSurf/ExpoGate are NOT for iterating — BSDT handles that.
They are post-hoc correction layers stacked on the model output.
Reference: mfls_variants.py and mfls-sdk/mfls/core/scoring.py
"""
import sys, os

FILE = os.path.join('research', 'udl', 'udl', 'system_mode.py')

with open(FILE, encoding='utf-8') as f:
    content = f.read()
    lines = content.split('\n')

# Find Mode6 boundaries
mode6_start = None
mode6_end = None
for i, line in enumerate(lines):
    if line.startswith('class Mode6GravityEngine:'):
        mode6_start = i
    elif mode6_start is not None and i > mode6_start + 5:
        # Find next top-level class/section or end
        if (line.startswith('class ') or
            (line.startswith('# ') and '===' in line and i > mode6_start + 20)):
            mode6_end = i
            break

if mode6_start is None:
    print("ERROR: Mode6GravityEngine not found!")
    sys.exit(1)

# Also find the banner comment block before Mode6
# Look for the "MODE-6 GRAVITY ENGINE" banner
banner_start = mode6_start
for i in range(mode6_start - 1, max(mode6_start - 15, 0), -1):
    stripped = lines[i].strip()
    if stripped == '' or stripped.startswith('#'):
        banner_start = i
    else:
        break

print(f"Mode6 banner starts at line {banner_start + 1}")
print(f"Mode6 class starts at line {mode6_start + 1}")
print(f"Mode6 ends at line {mode6_end + 1}")
print(f"Replacing {mode6_end - banner_start} lines")

# New Mode6 code with stacked-layer architecture
new_code = '''
# ═══════════════════════════════════════════════════════════════════
#  MFLS STACKED LAYERS  (from mfls_variants.py / scoring.py)
#  Supervised polynomial ridge and gated variants for post-hoc
#  correction on BSDT channel output.  Zero heuristics.
# ═══════════════════════════════════════════════════════════════════

class _MFLSQuadSurf:
    """Degree-2 polynomial ridge regression on BSDT channels.

    Input:  (T, K) channel matrix — the 4 BSDT operator outputs
            (delta_C, delta_G, delta_A, delta_T).
    Output: (T,) anomaly score per row.

    Fit uses ridge regression against crisis labels:
        beta = (Phi^T Phi + alpha I)^{-1} Phi^T y

    Reference: Odeyemi O.I., "Blind Spot Decomposition Theory", 2025.
    """

    def __init__(self, ridge_alpha: float = 1.0):
        self.ridge_alpha = ridge_alpha
        self.beta_ = None
        self.channel_means_ = None
        self.channel_stds_ = None

    @staticmethod
    def _poly_features(C: np.ndarray) -> np.ndarray:
        """Expand (T, K) channels to degree-2 polynomial features.

        For K=4: [1, c1..c4, c1^2, c1*c2, ..., c4^2] -> 15 features.
        """
        T, K = C.shape
        feats = [np.ones((T, 1)), C]
        for i in range(K):
            for j in range(i, K):
                feats.append((C[:, i] * C[:, j]).reshape(-1, 1))
        return np.hstack(feats)

    def fit(self, channels: np.ndarray, y: np.ndarray) -> '_MFLSQuadSurf':
        """Fit polynomial ridge on channel matrix.

        Parameters
        ----------
        channels : (T, K) array — BSDT channel scores.
        y : (T,) array — binary crisis labels (0 = normal, 1 = crisis).
        """
        self.channel_means_ = channels.mean(axis=0)
        self.channel_stds_ = channels.std(axis=0) + 1e-10
        C = (channels - self.channel_means_) / self.channel_stds_
        Phi = self._poly_features(C)
        n_feat = Phi.shape[1]
        I_reg = np.eye(n_feat)
        I_reg[0, 0] = 0.0  # don't regularise bias
        self.beta_ = np.linalg.solve(
            Phi.T @ Phi + self.ridge_alpha * I_reg,
            Phi.T @ y.astype(float),
        )
        return self

    def score(self, channels: np.ndarray) -> np.ndarray:
        """Score: max(0, Phi @ beta)."""
        C = (channels - self.channel_means_) / self.channel_stds_
        raw = self._poly_features(C) @ self.beta_
        return np.maximum(raw, 0.0)


class _MFLSExpoGate:
    """QuadSurf output capped by tanh saturation + sigmoid gating.

    raw  = QuadSurf polynomial output
    sat  = tanh(raw / sigma)         — saturation
    gate = sigmoid(scale * sat)      — probability calibration

    Reference: Odeyemi O.I., "Blind Spot Decomposition Theory", 2025.
    """

    def __init__(self, ridge_alpha: float = 1.0,
                 smooth_sigma: float = 1.0,
                 gate_scale: float = 3.0):
        self.smooth_sigma = smooth_sigma
        self.gate_scale = gate_scale
        self._quad = _MFLSQuadSurf(ridge_alpha=ridge_alpha)

    def fit(self, channels: np.ndarray, y: np.ndarray) -> '_MFLSExpoGate':
        """Fit polynomial ridge (delegated to internal QuadSurf)."""
        self._quad.fit(channels, y)
        return self

    def score(self, channels: np.ndarray) -> np.ndarray:
        """Saturated + gated score: sigmoid(scale * tanh(Q/sigma))."""
        raw = self._quad.score(channels)
        sat = np.tanh(raw / (self.smooth_sigma + 1e-10))
        return 1.0 / (1.0 + np.exp(-self.gate_scale * sat))


# ═══════════════════════════════════════════════════════════════════
#  MODE-6 GRAVITY ENGINE  (BSDT damping + MFLS stacked post-hoc)
#  The BSDT channels from the simulation pass through a supervised
#  MFLSQuadSurf / ExpoGate stacked layer — no heuristic blending.
# ═══════════════════════════════════════════════════════════════════

class Mode6GravityEngine:
    """BSDT-damped gravity with MFLS stacked post-hoc scorer.

    Architecture (3-layer stack):
        Layer 1 — BSDT adaptive damping in the gravity iteration loop.
                  Uses gradient descent + Lyapunov ISS for iterating.
                  BSDT is for iteration, NOT for scoring.
        Layer 2 — BSDT channel extraction on final positions.
                  Produces (N, 4) channel matrix:
                  [delta_C, delta_G, delta_A, delta_T]
        Layer 3 — MFLSQuadSurf or MFLSExpoGate stacked on channels.
                  Supervised polynomial ridge regression (labels = y).
                  This IS the final score — no blending.

    QuadSurf: degree-2 polynomial features + ridge regression
        score = max(0, Phi @ beta)
        where Phi = [1, c1..c4, c1^2, c1*c2, ..., c4^2]
        and beta = (Phi^T Phi + alpha I)^-1 Phi^T y

    ExpoGate: QuadSurf output -> tanh saturation -> sigmoid gating
        score = sigmoid(scale * tanh(QuadSurf / sigma))

    Parameters
    ----------
    posthoc : str
        Stacked layer type: ``'quadsurf'`` or ``'expogate'``.
    ridge_alpha : float
        Ridge penalty for polynomial regression (default 1.0).
    smooth_sigma : float
        Tanh saturation scale for ExpoGate (default 1.0).
    gate_scale : float
        Sigmoid gate steepness for ExpoGate (default 3.0).
    """

    def __init__(self,
                 alpha: float = 0.1,
                 gamma: float = 0.5,
                 sigma: float = 1.0,
                 lambda_rep: float = 0.05,
                 eta: float = 0.05,
                 iterations: int = 60,
                 k_neighbors: int = 15,
                 normalize: bool = True,
                 max_samples: int = 3000,
                 calibrate: Optional[str] = None,
                 target_far: float = 0.05,
                 posthoc: str = 'quadsurf',
                 ridge_alpha: float = 1.0,
                 smooth_sigma: float = 1.0,
                 gate_scale: float = 3.0):
        self.alpha = alpha
        self.gamma = gamma
        self.sigma = sigma
        self.lambda_rep = lambda_rep
        self.eta = eta
        self.iterations = iterations
        self.k_neighbors = k_neighbors
        self.normalize = normalize
        self.max_samples = max_samples
        self.calibrate = calibrate
        self.target_far = target_far
        self.posthoc = posthoc
        self.ridge_alpha = ridge_alpha
        self.smooth_sigma = smooth_sigma
        self.gate_scale = gate_scale

        self.stabiliser = LyapunovStabiliser(min_eta=1e-5)
        self.alarm = MorseTopologyAlarm(
            k=k_neighbors,
            weights=np.array([0.35, 0.30, 0.20, 0.15]))
        self._far_calibrator = None

        self.scaler_: Optional[StandardScaler] = None
        self.mu_: Optional[np.ndarray] = None
        self.X_final_: Optional[np.ndarray] = None

    # ── forces / energy (same physics as Mode5) ──

    def _pairwise_forces(self, X: np.ndarray,
                         eps: float = 1e-5) -> np.ndarray:
        """Gravitational attraction + short-range repulsion (kNN-limited)."""
        n, d = X.shape
        gamma = self.gamma
        sigma = self.sigma
        lambda_rep = self.lambda_rep

        from sklearn.neighbors import NearestNeighbors
        k = min(self.k_neighbors, n - 1)
        nn = NearestNeighbors(n_neighbors=k + 1, algorithm='auto')
        nn.fit(X.astype(np.float32))
        _, indices = nn.kneighbors(X.astype(np.float32))
        nbr_idx = indices[:, 1:]

        X_nbrs = X[nbr_idx]
        diff = X[:, None, :] - X_nbrs
        r_sq = np.sum(diff ** 2, axis=2, keepdims=True) + eps
        r = np.sqrt(r_sq)

        attraction = np.exp(-r_sq / (sigma ** 2))
        repulsion = lambda_rep / r
        magnitude = -gamma * (attraction - repulsion)

        unit = diff / r
        forces = np.sum(magnitude * unit, axis=1)
        return forces

    def _gravity_energy(self, X: np.ndarray, eps: float = 1e-5) -> float:
        """Radial-only Lyapunov candidate energy."""
        diff_mu = X - self.mu_[None, :]
        E_radial = 0.5 * self.alpha * np.sum(diff_mu ** 2)
        return float(E_radial)

    # ── core fit_score ──

    def fit_score(self, X: np.ndarray, y: Optional[np.ndarray] = None
                  ) -> np.ndarray:
        """BSDT-damped gravity -> BSDT channels -> MFLS stacked layer.

        Phase 1: BSDT adaptive damping in Euler integration
                 (gradient descent + Lyapunov ISS — same as Mode5).
        Phase 2: Extract BSDT channels on final positions.
        Phase 3: MFLSQuadSurf / ExpoGate stacked on channels
                 (supervised ridge, no heuristic blending).
        """
        if self.normalize:
            self.scaler_ = StandardScaler()
            X_all = self.scaler_.fit_transform(X).astype(np.float64)
        else:
            X_all = X.astype(np.float64).copy()

        n = len(X_all)
        normal_mask_all = (y == 0) if y is not None else np.ones(n, dtype=bool)

        # Subsample for simulation if dataset is large
        if n > self.max_samples:
            rng = np.random.RandomState(42)
            anom_idx = np.where(y == 1)[0] if y is not None else np.array([], dtype=int)
            other_idx = np.where(y != 1)[0] if y is not None else np.arange(n)

            if len(anom_idx) >= self.max_samples:
                n_anom = min(len(anom_idx), self.max_samples // 2)
                n_other = self.max_samples - n_anom
                anom_sample = rng.choice(anom_idx, n_anom, replace=False)
                other_sample = rng.choice(other_idx, min(n_other, len(other_idx)), replace=False)
                sim_idx = np.sort(np.concatenate([anom_sample, other_sample]))
            else:
                n_other = max(0, self.max_samples - len(anom_idx))
                if len(other_idx) > n_other:
                    other_sample = rng.choice(other_idx, n_other, replace=False)
                else:
                    other_sample = other_idx
                sim_idx = np.sort(np.concatenate([anom_idx, other_sample]))

            X_work = X_all[sim_idx].copy()
            normal_mask = normal_mask_all[sim_idx]
            subsampled = True
        else:
            X_work = X_all.copy()
            normal_mask = normal_mask_all
            subsampled = False

        self.mu_ = X_work.mean(axis=0)
        X_initial = X_work.copy()

        # ══════════════════════════════════════════════════════════
        #  Phase 1: BSDT adaptive damping (gradient descent / ISS)
        # ══════════════════════════════════════════════════════════
        bsdt_damper = BSDTChannels(k=min(self.k_neighbors,
                                         len(X_work) - 1))
        X_ref_init = X_work[normal_mask] if normal_mask.sum() > 5 \\
            else X_work
        bsdt_damper.fit(X_ref_init)
        e_ref = bsdt_damper.energy(X_ref_init)
        theta_bs = float(np.median(e_ref)) + 1e-10
        mfls_ref = bsdt_damper.mfls(X_ref_init)
        mfls_med = float(np.median(mfls_ref)) + 1e-10
        beta_mfls = theta_bs / mfls_med

        # Euler integration with BSDT adaptive damping
        self.stabiliser.reset()
        eta = self.eta
        n_sim = len(X_work)
        iters = self.iterations if n_sim <= 1000 else max(20, self.iterations // 2)
        for step in range(iters):
            F_pair = self._pairwise_forces(X_work)
            F_radial = -self.alpha * (X_work - self.mu_)

            e_bs = bsdt_damper.energy(X_work)
            grad_bs = bsdt_damper._gradient_vectors(X_work)
            mfls_bs = np.linalg.norm(grad_bs, axis=1)
            e_combined = e_bs + beta_mfls * mfls_bs
            gamma_bs = e_combined / (e_combined + theta_bs)
            F_damp = -gamma_bs[:, None] * grad_bs

            F_total = F_pair + F_radial + F_damp

            F_total = self.stabiliser.clamp_forces(F_total)

            E_old = self._gravity_energy(X_work)
            grad_norm_sq = float(np.sum(F_total ** 2))
            perturbation_norm = float(np.sqrt(np.sum(F_pair ** 2)))

            X_candidate = X_work + eta * F_total
            E_new = self._gravity_energy(X_candidate)

            accept, eta = self.stabiliser.accept_step(
                E_old, E_new, grad_norm_sq, eta,
                perturbation_norm=perturbation_norm
            )

            if accept:
                X_work = X_candidate
            else:
                X_work = X_work + eta * F_total

            displacement = eta * np.max(np.linalg.norm(F_total, axis=1))
            if self.stabiliser.check_convergence(grad_norm_sq, displacement):
                break

        self.X_final_ = X_work
        self._convergence_report = self.stabiliser.report()

        # ══════════════════════════════════════════════════════════
        #  Phase 2: BSDT channel extraction on final positions
        # ══════════════════════════════════════════════════════════
        X_ref_final = X_work[normal_mask]
        if len(X_ref_final) < 2:
            X_ref_final = X_work

        bsdt_scorer = BSDTChannels(k=min(self.k_neighbors,
                                         max(len(X_ref_final) - 1, 1)))
        bsdt_scorer.fit(X_ref_final)

        X_scored = X_all if subsampled else X_work
        ch = bsdt_scorer.channels(X_scored)
        C = np.column_stack([ch['delta_C'], ch['delta_G'],
                             ch['delta_A'], ch['delta_T']])

        # ══════════════════════════════════════════════════════════
        #  Phase 3: MFLS stacked layer (supervised ridge)
        # ══════════════════════════════════════════════════════════
        if y is not None:
            y_scored = y.astype(float)
            if self.posthoc == 'expogate':
                layer = _MFLSExpoGate(
                    ridge_alpha=self.ridge_alpha,
                    smooth_sigma=self.smooth_sigma,
                    gate_scale=self.gate_scale,
                )
            else:
                layer = _MFLSQuadSurf(ridge_alpha=self.ridge_alpha)

            layer.fit(C, y_scored)
            scores = layer.score(C)
        else:
            # Unsupervised fallback: raw BSDT score
            scores = bsdt_scorer.score(X_scored)

        # ── FAR-targeted calibration (optional) ──
        if self.calibrate is not None and y is not None:
            from .calibration import FARTargetCalibrator
            cal = FARTargetCalibrator(
                target_far=self.target_far,
                method=self.calibrate
            )
            cal.fit(scores, y)
            scores = cal.transform(scores)
            self._far_calibrator = cal

        return scores

'''

# Build new content
before = lines[:banner_start]
after = lines[mode6_end:]
new_lines = new_code.split('\n')

new_content = '\n'.join(before) + '\n' + new_code + '\n'.join(after)

with open(FILE, 'w', encoding='utf-8') as f:
    f.write(new_content)

# Verify
with open(FILE, encoding='utf-8') as f:
    verify = f.read()

assert 'class Mode6GravityEngine:' in verify, "Mode6 not found after rewrite!"
assert '_MFLSQuadSurf' in verify, "_MFLSQuadSurf not found!"
assert '_MFLSExpoGate' in verify, "_MFLSExpoGate not found!"
assert 'class HybridGravityEngine:' in verify, "HybridGravityEngine lost!"
assert 'class Mode5GravityEngine:' in verify, "Mode5 lost!"
assert 'class Mode4GravityEngine:' in verify, "Mode4 lost!"
assert 'stacked layer' in verify.lower() or 'stacked' in verify, "Docstring check"

# Check no blending remnants
m6_section = verify[verify.index('class Mode6GravityEngine:'):]
m6_section = m6_section[:m6_section.index('class HybridGravityEngine:')]
assert 'posthoc_lambda' not in m6_section, "posthoc_lambda should be removed!"
assert '_Mode4FusedScorer' not in m6_section, "_Mode4FusedScorer should not be in Mode6!"
assert 'layer.fit(C, y_scored)' in m6_section, "Supervised stacked layer missing!"

# Count lines
total = verify.count('\n') + 1
print(f"\nDone. File: {FILE}")
print(f"Total lines: {total}")
print("Mode6 rewritten with MFLS stacked-layer architecture.")
print("  - No heuristic blending")
print("  - No _Mode4FusedScorer in scoring pipeline")
print("  - QuadSurf/ExpoGate as supervised stacked layer on BSDT channels")
