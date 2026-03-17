"""
1. Make MolecularEngine BSDT damping optional (use_bsdt_damping param).
2. Create Mode7GravityEngine: no damping (Mode4 iteration) + stacked BSDT correction layer.

Mode7 = pure physics (gravity + Lyapunov ISS step control, no friction)
        + BSDT channels on final positions
        + Fisher / QuadSurf / ExpoGate stacked correction layer.

The iteration sees NO damping force — Lyapunov only controls step size,
it does NOT contribute to prediction.
"""
import os

FILE = os.path.join('research', 'udl', 'udl', 'system_mode.py')

with open(FILE, encoding='utf-8') as f:
    content = f.read()

# ═══════════════════════════════════════════════════════════════════
#  PART 1: Make MolecularEngine BSDT damping optional
# ═══════════════════════════════════════════════════════════════════

# Add use_bsdt_damping parameter to __init__
old_mol_init = '''                 use_fused: bool = True,
                 calibrate: Optional[str] = None,
                 target_far: float = 0.05):
        self.epsilon = epsilon
        self.sigma_lj = sigma_lj
        self.alpha_radial = alpha_radial
        self.eta = eta
        self.iterations = iterations
        self.k_neighbors = k_neighbors
        self.normalize = normalize
        self.max_samples = max_samples
        self.use_fused = use_fused
        self.calibrate = calibrate
        self.target_far = target_far

        self.stabiliser = LyapunovStabiliser()'''

new_mol_init = '''                 use_fused: bool = True,
                 use_bsdt_damping: bool = True,
                 calibrate: Optional[str] = None,
                 target_far: float = 0.05):
        self.epsilon = epsilon
        self.sigma_lj = sigma_lj
        self.alpha_radial = alpha_radial
        self.eta = eta
        self.iterations = iterations
        self.k_neighbors = k_neighbors
        self.normalize = normalize
        self.max_samples = max_samples
        self.use_fused = use_fused
        self.use_bsdt_damping = use_bsdt_damping
        self.calibrate = calibrate
        self.target_far = target_far

        self.stabiliser = LyapunovStabiliser()'''

assert old_mol_init in content, "MolecularEngine __init__ not found!"
content = content.replace(old_mol_init, new_mol_init)

# Replace the BSDT damping block in fit_score with conditional
old_mol_bsdt = '''        # ── BSDT adaptive damping (Theorem C, eq:bsdamped) ──────
        # Ẋ = F(X) − γ(E_BS) · ∇E_BS(X)
        # γ(E) = E / (E + θ)   — adaptive friction coefficient
        # BSDT provides the damping that prevents collapse above
        # the critical manifold C*.  Lyapunov ISS handles step-size
        # control only.
        bsdt_damper = BSDTChannels(k=min(self.k_neighbors,
                                         len(X_work) - 1))
        X_ref_init = X_work[normal_mask] if normal_mask.sum() > 5 \\
            else X_work
        bsdt_damper.fit(X_ref_init)
        # θ = median E_BS on reference — damping is ~50% at normal
        e_ref = bsdt_damper.energy(X_ref_init)
        theta_bs = float(np.median(e_ref)) + 1e-10
        # MFLS scale factor: match gradient-norm scale to energy scale
        mfls_ref = bsdt_damper.mfls(X_ref_init)
        mfls_med = float(np.median(mfls_ref)) + 1e-10
        beta_mfls = theta_bs / mfls_med  # data-driven blend weight'''

new_mol_bsdt = '''        # ── Optional BSDT adaptive damping ──────
        # When enabled: Ẋ = F(X) − γ(E_BS) · ∇E_BS(X)
        # When disabled: Ẋ = F(X)  (pure physics, no friction)
        bsdt_damper = None
        theta_bs = 1.0
        beta_mfls = 0.0
        if self.use_bsdt_damping:
            bsdt_damper = BSDTChannels(k=min(self.k_neighbors,
                                             len(X_work) - 1))
            X_ref_init = X_work[normal_mask] if normal_mask.sum() > 5 \\
                else X_work
            bsdt_damper.fit(X_ref_init)
            e_ref = bsdt_damper.energy(X_ref_init)
            theta_bs = float(np.median(e_ref)) + 1e-10
            mfls_ref = bsdt_damper.mfls(X_ref_init)
            mfls_med = float(np.median(mfls_ref)) + 1e-10
            beta_mfls = theta_bs / mfls_med'''

assert old_mol_bsdt in content, "MolecularEngine BSDT damping block not found!"
content = content.replace(old_mol_bsdt, new_mol_bsdt)

# Replace the damping force computation in the iteration loop
old_mol_loop = '''            # BSDT + MFLS adaptive damping (eq:bsdamped extended)
            # E_combined = E_BS + β·MFLS catches transitional states
            # where gradients are steep but energy hasn't peaked.
            e_bs = bsdt_damper.energy(X_work)       # (n_sim,)
            grad_bs = bsdt_damper._gradient_vectors(X_work)  # (n,d)
            mfls_bs = np.linalg.norm(grad_bs, axis=1)  # MFLS per point
            e_combined = e_bs + beta_mfls * mfls_bs  # blended energy
            gamma_bs = e_combined / (e_combined + theta_bs)  # adaptive coeff
            F_damp = -gamma_bs[:, None] * grad_bs    # damping force

            F_total = F_lj + F_radial + F_damp'''

new_mol_loop = '''            # Damping: optional BSDT adaptive friction
            if bsdt_damper is not None:
                e_bs = bsdt_damper.energy(X_work)
                grad_bs = bsdt_damper._gradient_vectors(X_work)
                mfls_bs = np.linalg.norm(grad_bs, axis=1)
                e_combined = e_bs + beta_mfls * mfls_bs
                gamma_bs = e_combined / (e_combined + theta_bs)
                F_damp = -gamma_bs[:, None] * grad_bs
                F_total = F_lj + F_radial + F_damp
            else:
                F_total = F_lj + F_radial'''

assert old_mol_loop in content, "MolecularEngine loop damping block not found!"
content = content.replace(old_mol_loop, new_mol_loop)

# Fix the morse_alarm call (uses bsdt_damper which may be None)
old_mol_morse = '''        self._morse_alarm = bsdt_damper.morse_alarm(X_work)'''
new_mol_morse = '''        if bsdt_damper is not None:
            self._morse_alarm = bsdt_damper.morse_alarm(X_work)
        else:
            self._morse_alarm = None'''

assert old_mol_morse in content, "MolecularEngine morse_alarm call not found!"
content = content.replace(old_mol_morse, new_mol_morse)


# ═══════════════════════════════════════════════════════════════════
#  PART 2: Create Mode7GravityEngine
# ═══════════════════════════════════════════════════════════════════

MODE7_CODE = '''

# ═══════════════════════════════════════════════════════════════════
#  MODE-7 GRAVITY ENGINE  (NO damping + stacked BSDT correction)
#  Pure gravity physics (Lyapunov ISS step control only, no friction)
#  + BSDT channel extraction + Fisher / QuadSurf / ExpoGate layer.
# ═══════════════════════════════════════════════════════════════════

class Mode7GravityEngine:
    """Pure-physics gravity engine with stacked BSDT correction layer.

    Architecture (3-layer stack):
        Layer 1 — Gravity iteration with NO damping.
                  F_total = F_pair + F_radial
                  Lyapunov ISS controls step size only —
                  it does NOT contribute to prediction.
        Layer 2 — BSDT channel extraction on final positions.
                  (delta_C, delta_G, delta_A, delta_T)
        Layer 3 — Stacked correction layer on channels.
                  This IS the final score — no blending.

    No friction/damping force in the iteration loop.  The physics
    is purely conservative: gravitational attraction + short-range
    repulsion + radial centering.  This lets you test whether the
    stacked correction layer can recover anomaly discrimination
    without adaptive friction (useful for cases like TerraLuna,
    World Bank, ERCOT where you want to isolate what the friction
    control contributes vs what the correction layer contributes).

    Correction layers (``posthoc`` parameter):
        ``'fisher'``   — Fisher VR dynamic channel weights (unsupervised)
        ``'quadsurf'`` — degree-2 polynomial ridge (supervised)
        ``'expogate'`` — QuadSurf + tanh + sigmoid (supervised)

    Parameters
    ----------
    posthoc : str
        Stacked layer: ``'fisher'``, ``'quadsurf'``, or ``'expogate'``.
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
                 posthoc: str = 'fisher',
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
        self._far_calibrator = None

        self.scaler_: Optional[StandardScaler] = None
        self.mu_: Optional[np.ndarray] = None
        self.X_final_: Optional[np.ndarray] = None

    # ── forces / energy (pure physics, no damping) ──

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
        """Pure gravity iteration -> BSDT channels -> stacked correction.

        Phase 1: Euler integration with NO damping.
                 F_total = F_pair + F_radial
                 Lyapunov ISS controls step size only.
        Phase 2: Extract BSDT channels on final positions.
        Phase 3: Stacked correction layer (Fisher / QuadSurf / ExpoGate).
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

        # ══════════════════════════════════════════════════════════
        #  Phase 1: Pure gravity iteration — NO damping
        #  Lyapunov ISS controls step size only (Armijo, clamping).
        # ══════════════════════════════════════════════════════════
        self.stabiliser.reset()
        eta = self.eta
        n_sim = len(X_work)
        iters = self.iterations if n_sim <= 1000 else max(20, self.iterations // 2)
        for step in range(iters):
            F_pair = self._pairwise_forces(X_work)
            F_radial = -self.alpha * (X_work - self.mu_)
            F_total = F_pair + F_radial

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
        #  Phase 3: Stacked correction layer on BSDT channels
        # ══════════════════════════════════════════════════════════
        has_labels = y is not None and y.sum() > 0

        if self.posthoc == 'fisher':
            # ── BSDT baseline: Fisher VR dynamic weights (unsupervised) ──
            layer = _MFLSFisherBSDT()
            layer.fit(C)
            scores = layer.score(C)

        elif has_labels:
            # ── Supervised stacking: MFLSQuadSurf / ExpoGate ──
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
            # ── Unsupervised fallback: Fisher VR on channels ──
            if self.posthoc == 'expogate':
                bsdt_scorer.fit_expogate(X_ref_final)
                scores = bsdt_scorer.score_expogate(X_scored)
            else:
                bsdt_scorer.fit_quadsurf(X_ref_final)
                scores = bsdt_scorer.score_quadsurf(X_scored)

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

# Insert Mode7 before HybridGravityEngine
hybrid_marker = 'class HybridGravityEngine:'
idx = content.index(hybrid_marker)
# Find the banner before it
banner_start = content.rfind('\n#', 0, idx)
# Go back to find start of blank lines / comments
content = content[:banner_start] + MODE7_CODE + content[banner_start:]

# ── Write ──
with open(FILE, 'w', encoding='utf-8') as f:
    f.write(content)

# ── Verify ──
with open(FILE, encoding='utf-8') as f:
    v = f.read()
assert 'class Mode7GravityEngine:' in v, "Mode7 missing!"
assert 'class Mode6GravityEngine:' in v, "Mode6 lost!"
assert 'class Mode5GravityEngine:' in v, "Mode5 lost!"
assert 'class Mode4GravityEngine:' in v, "Mode4 lost!"
assert 'class HybridGravityEngine:' in v, "Hybrid lost!"
assert 'class MolecularEngine:' in v, "Molecular lost!"
assert 'use_bsdt_damping' in v, "MolecularEngine damping param missing!"
# Mode7 should NOT have BSDT damping in iteration
m7 = v[v.index('class Mode7GravityEngine:'):v.index('class HybridGravityEngine:')]
assert 'F_damp' not in m7, "Mode7 should have no damping force!"
assert 'bsdt_damper' not in m7, "Mode7 should have no bsdt_damper in iteration!"
assert '_MFLSFisherBSDT' in m7, "Mode7 should use Fisher stacked layer!"

total = v.count('\n') + 1
print(f"Done. Total lines: {total}")
print("1. MolecularEngine: use_bsdt_damping param added (default True)")
print("2. Mode7GravityEngine: no damping + stacked BSDT correction layer")
