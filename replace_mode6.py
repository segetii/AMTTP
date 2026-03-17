"""
Replace Mode6GravityEngine with QuadSurf/ExpoGate post-hoc MFLS recovery.
"""

FILE = r'C:\amttp\research\udl\udl\system_mode.py'
with open(FILE, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find start/end of Mode6 block
start_line = None
end_line = None
for i, line in enumerate(lines):
    if 'MODE-6 GRAVITY ENGINE' in line and start_line is None:
        # Go back to the blank line / comment header start
        start_line = i - 1  # the ═══ line before
        while start_line > 0 and lines[start_line].strip() == '':
            start_line -= 1
        start_line += 1  # keep the blank line
    if start_line is not None and i > start_line + 5:
        if '#  HYBRID ENGINE' in line:
            # end_line is the line before the ═══ header of HYBRID
            end_line = i - 1
            while end_line > start_line and lines[end_line].strip() == '':
                end_line -= 1
            end_line += 1  # include trailing blank
            break

print(f"Mode6 block: lines {start_line+1} to {end_line+1}")

NEW_MODE6 = r'''

# ═══════════════════════════════════════════════════════════════════
#  MODE-6 GRAVITY ENGINE  (BSDT damping + bb43ff5 scoring
#                          + MFLS QuadSurf / ExpoGate post-hoc)
#  The base score from _Mode4FusedScorer passes through BSDT's
#  QuadSurf or ExpoGate as a post-hoc signal recovery formula.
# ═══════════════════════════════════════════════════════════════════

class Mode6GravityEngine:
    """BSDT-damped gravity with MFLS post-hoc score recovery.

    Physics: BSDT adaptive damping in the iteration loop
    (identical to ``Mode5GravityEngine``).

    Scoring pipeline:
        1. ``_Mode4FusedScorer`` produces base anomaly scores.
        2. BSDT channels (δ_C, δ_G, δ_A, δ_T) are computed on the
           final simulation positions.
        3. The MFLS post-hoc formula maps the channels through either:
           - **QuadSurf**: Fisher-weighted degree-2 polynomial surface
             ``Q(c) = Σ w_k c_k' + Σ w_k c_k'^2 + Σ √(w_k w_j) c_k' c_j'``
           - **ExpoGate**: ``sigmoid(scale · tanh(Q(c) / σ))``
        4. Final score = ``(1 - λ) · base + λ · posthoc``

    This recovers the AUROC discrimination that BSDT damping
    compresses out of the base score.

    Parameters
    ----------
    posthoc : str
        Post-hoc formula: ``'quadsurf'`` or ``'expogate'``.
    posthoc_lambda : float
        Blend weight for the post-hoc signal (default 0.5).
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
                 use_fused: bool = True,
                 calibrate: Optional[str] = None,
                 target_far: float = 0.05,
                 posthoc: str = 'quadsurf',
                 posthoc_lambda: float = 0.5):
        self.alpha = alpha
        self.gamma = gamma
        self.sigma = sigma
        self.lambda_rep = lambda_rep
        self.eta = eta
        self.iterations = iterations
        self.k_neighbors = k_neighbors
        self.normalize = normalize
        self.max_samples = max_samples
        self.use_fused = use_fused
        self.calibrate = calibrate
        self.target_far = target_far
        self.posthoc = posthoc
        self.posthoc_lambda = posthoc_lambda

        self.stabiliser = LyapunovStabiliser(min_eta=1e-5)
        self.alarm = MorseTopologyAlarm(
            k=k_neighbors,
            weights=np.array([0.35, 0.30, 0.20, 0.15]))
        self.fused_scorer = _Mode4FusedScorer(k=k_neighbors) if use_fused else None
        self._far_calibrator = None

        self.scaler_: Optional[StandardScaler] = None
        self.mu_: Optional[np.ndarray] = None
        self.X_final_: Optional[np.ndarray] = None

    # ── forces / energy ──

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

    # ── post-hoc MFLS recovery ──

    @staticmethod
    def _percentile_norm(s: np.ndarray) -> np.ndarray:
        """Robust [0,1] normalisation via 1st-99th percentile clipping."""
        q1, q99 = np.percentile(s, [1, 99])
        if q99 - q1 < 1e-15:
            return np.zeros_like(s)
        return np.clip((s - q1) / (q99 - q1), 0.0, 1.0)

    def _posthoc_recover(self, scores_base: np.ndarray,
                         X_scored: np.ndarray,
                         bsdt: 'BSDTChannels') -> np.ndarray:
        """Post-hoc MFLS signal recovery via QuadSurf or ExpoGate.

        1. Compute BSDT channel scores on final positions.
        2. Map through QuadSurf or ExpoGate formula.
        3. Blend: ``(1 - lambda) * base + lambda * posthoc``.
        """
        if self.posthoc == 'expogate':
            posthoc_scores = bsdt.score_expogate(X_scored)
        else:  # quadsurf
            posthoc_scores = bsdt.score_quadsurf(X_scored)

        s_norm = self._percentile_norm(scores_base)
        p_norm = self._percentile_norm(posthoc_scores)
        lam = self.posthoc_lambda

        return (1.0 - lam) * s_norm + lam * p_norm

    # ── core fit_score ──

    def fit_score(self, X: np.ndarray, y: Optional[np.ndarray] = None
                  ) -> np.ndarray:
        """BSDT-damped gravity + bb43ff5 scoring + MFLS post-hoc recovery.

        Iteration: ``F_total = F_pair + F_radial + F_damp`` (BSDT).
        Scoring:   ``_Mode4FusedScorer`` -> QuadSurf/ExpoGate post-hoc.
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

        # ── BSDT adaptive damping ──
        bsdt_damper = BSDTChannels(k=min(self.k_neighbors,
                                         len(X_work) - 1))
        X_ref_init = X_work[normal_mask] if normal_mask.sum() > 5 \
            else X_work
        bsdt_damper.fit(X_ref_init)
        e_ref = bsdt_damper.energy(X_ref_init)
        theta_bs = float(np.median(e_ref)) + 1e-10
        mfls_ref = bsdt_damper.mfls(X_ref_init)
        mfls_med = float(np.median(mfls_ref)) + 1e-10
        beta_mfls = theta_bs / mfls_med

        # ── Euler integration with BSDT ──
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

        # ── Phase 2: bb43ff5 base scoring ──
        X_ref_final = X_work[normal_mask]
        if len(X_ref_final) > 1:
            if self.fused_scorer is not None:
                self.fused_scorer.fit(X_ref_final, X_sim=X_work)
                if subsampled:
                    scores_base = self.fused_scorer.score(X_all)
                else:
                    scores_base = self.fused_scorer.score(X_work)
            else:
                self.alarm.fit(X_ref_final)
                if subsampled:
                    scores_base = self.alarm.score(X_all)
                else:
                    scores_base = self.alarm.score(X_work)
        else:
            if subsampled:
                scores_base = np.linalg.norm(X_all - X_all.mean(axis=0), axis=1)
            else:
                scores_base = np.linalg.norm(X_work - X_initial, axis=1)

        # ── Phase 3: MFLS post-hoc recovery (QuadSurf / ExpoGate) ──
        bsdt_post = BSDTChannels(k=min(self.k_neighbors,
                                       max(len(X_ref_final) - 1, 1)))
        bsdt_post.fit(X_ref_final)
        if self.posthoc == 'expogate':
            bsdt_post.fit_expogate(X_ref_final)
        else:
            bsdt_post.fit_quadsurf(X_ref_final)

        if subsampled:
            scores = self._posthoc_recover(scores_base, X_all, bsdt_post)
        else:
            scores = self._posthoc_recover(scores_base, X_work, bsdt_post)

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

# Replace old Mode6 block
new_lines = lines[:start_line] + [NEW_MODE6 + '\n'] + lines[end_line:]
content = ''.join(new_lines)

with open(FILE, 'w', encoding='utf-8') as f:
    f.write(content)

line_count = content.count('\n') + 1
print(f"File written: {line_count} lines")

assert 'class Mode6GravityEngine:' in content
assert 'score_quadsurf' in content[content.index('class Mode6GravityEngine:'):]
assert 'score_expogate' in content[content.index('class Mode6GravityEngine:'):]
assert '_Mode4FusedScorer(k=k_neighbors)' in content[content.index('class Mode6GravityEngine:'):]
print("All assertions passed.")
