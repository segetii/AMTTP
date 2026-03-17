"""
Insert Mode6GravityEngine into system_mode.py.
Mode6 = Mode5 (BSDT damping + bb43ff5 scoring) + MFLS post-hoc correction.

The MFLS correction re-scores the final positions using the blind-spot
gradient norm as a post-hoc signal, blended with the base _Mode4FusedScorer
output to recover discrimination lost by BSDT damping.
"""

FILE = r'C:\amttp\research\udl\udl\system_mode.py'
with open(FILE, 'r', encoding='utf-8') as f:
    content = f.read()

MODE6_CLASS = r'''

# ═══════════════════════════════════════════════════════════════════
#  MODE-6 GRAVITY ENGINE  (Mode5 + MFLS post-hoc score correction)
#  = BSDT adaptive damping + bb43ff5 scoring + MFLS correction.
#  The MFLS gradient-norm signal is computed on final positions and
#  blended with the base score to recover AUROC lost by damping.
# ═══════════════════════════════════════════════════════════════════

class Mode6GravityEngine:
    """Mode5 + MFLS post-hoc correction on the final scores.

    Physics: BSDT adaptive damping in the iteration loop
    (identical to ``Mode5GravityEngine``).

    Scoring: ``_Mode4FusedScorer`` (bb43ff5-era), then a post-hoc
    MFLS correction that blends the base anomaly score with the
    blind-spot gradient norm ``‖∇E_BS‖_F`` computed on the final
    simulation positions:

        ``score_corrected = (1 - λ) · score_base + λ · MFLS_norm``

    where ``MFLS_norm`` is the percentile-normalised gradient norm
    and ``λ`` is a data-driven blending weight derived from the
    Fisher variance-ratio between the two signals on the reference
    population.  This recovers the discrimination that BSDT damping
    compresses out of the raw score.
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
                 mfls_lambda: Optional[float] = None):
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
        self.mfls_lambda = mfls_lambda  # None = auto (Fisher VR)

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

    # ── MFLS post-hoc correction ──

    @staticmethod
    def _percentile_norm(s: np.ndarray) -> np.ndarray:
        """Robust [0,1] normalisation via 1st–99th percentile clipping."""
        q1, q99 = np.percentile(s, [1, 99])
        if q99 - q1 < 1e-15:
            return np.zeros_like(s)
        return np.clip((s - q1) / (q99 - q1), 0.0, 1.0)

    def _mfls_correction(self, scores_base: np.ndarray,
                         X_final: np.ndarray,
                         bsdt: 'BSDTChannels',
                         normal_mask: np.ndarray) -> np.ndarray:
        """Post-hoc MFLS correction: blend base score with gradient norm.

        score = (1 - λ) · norm(score_base) + λ · norm(MFLS)

        λ is auto-derived via Fisher variance-ratio between the two
        signals on the reference (normal) population, unless overridden
        by ``self.mfls_lambda``.
        """
        mfls_raw = bsdt.mfls(X_final)              # ‖∇E_BS‖_F per point
        s_norm = self._percentile_norm(scores_base)
        m_norm = self._percentile_norm(mfls_raw)

        if self.mfls_lambda is not None:
            lam = self.mfls_lambda
        else:
            # Auto λ via Fisher VR on the reference population
            ref = normal_mask
            if ref.sum() < 10:
                lam = 0.3  # fallback
            else:
                # Regime split on base score (p80 / p50)
                s_ref = s_norm[ref]
                m_ref = m_norm[ref]
                p80 = np.percentile(s_ref, 80)
                p50 = np.percentile(s_ref, 50)
                hi = s_ref >= p80
                lo = s_ref <= p50
                if hi.sum() < 2 or lo.sum() < 2:
                    lam = 0.3
                else:
                    # FR for base score
                    fr_s = (s_ref[hi].mean() - s_ref[lo].mean()) ** 2 / \
                           max(s_ref[hi].var() + s_ref[lo].var(), 1e-15)
                    # FR for MFLS
                    fr_m = (m_ref[hi].mean() - m_ref[lo].mean()) ** 2 / \
                           max(m_ref[hi].var() + m_ref[lo].var(), 1e-15)
                    total = fr_s + fr_m
                    if total < 1e-15:
                        lam = 0.3
                    else:
                        lam = fr_m / total  # MFLS weight proportional to its discriminative power

        return (1.0 - lam) * s_norm + lam * m_norm

    # ── core fit_score ──

    def fit_score(self, X: np.ndarray, y: Optional[np.ndarray] = None
                  ) -> np.ndarray:
        """Run BSDT-damped gravity, score with bb43ff5 + MFLS correction.

        Iteration: ``F_total = F_pair + F_radial + F_damp`` (BSDT).
        Scoring:   ``_Mode4FusedScorer`` → MFLS post-hoc blend.
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

        # ── BSDT adaptive damping (Theorem C, eq:bsdamped) ──
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

        # ── Phase 2: bb43ff5 scoring ──
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

        # ── Phase 3: MFLS post-hoc correction ──
        # Re-fit BSDT on final reference positions for clean gradient
        bsdt_post = BSDTChannels(k=min(self.k_neighbors,
                                       len(X_ref_final) - 1))
        bsdt_post.fit(X_ref_final)

        if subsampled:
            scores = self._mfls_correction(
                scores_base, X_all, bsdt_post, normal_mask_all)
        else:
            scores = self._mfls_correction(
                scores_base, X_work, bsdt_post, normal_mask)

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

# Insert before HYBRID ENGINE section
hybrid_marker = '#  HYBRID ENGINE (Molecular + Gravity blend)'
hybrid_idx = content.index(hybrid_marker)
line_start = content.rfind('\n', 0, hybrid_idx)
section_start = content.rfind('\n', 0, line_start)

if 'class Mode6GravityEngine:' in content:
    print("Mode6GravityEngine already exists, skipping")
else:
    content = content[:section_start] + MODE6_CLASS + content[section_start:]
    print("Inserted Mode6GravityEngine class")

with open(FILE, 'w', encoding='utf-8') as f:
    f.write(content)

line_count = content.count('\n') + 1
print(f"File written: {line_count} lines")

assert 'class Mode6GravityEngine:' in content
assert '_mfls_correction' in content
assert '_Mode4FusedScorer(k=k_neighbors)' in content[content.index('class Mode6GravityEngine:'):]
print("All assertions passed.")
