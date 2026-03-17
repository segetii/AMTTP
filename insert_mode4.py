"""Insert Mode4GravityEngine into system_mode.py on disk."""
import re

FILE = r'C:\amttp\research\udl\udl\system_mode.py'

with open(FILE, 'r', encoding='utf-8') as f:
    content = f.read()

# Already inserted?
if 'class Mode4GravityEngine' in content:
    print("Mode4GravityEngine already exists — skipping.")
    exit(0)

MODE4_BLOCK = r'''

# ═══════════════════════════════════════════════════════════════════
#  MODE-4 GRAVITY ENGINE  (paper-era, no BSDT damping — FAR=1.6%)
#  Frozen snapshot from commit bb43ff5 (2026-03-08).
#  Pure N-body gravity + Lyapunov ISS + Morse/Fused scoring.
#  No blind-spot tensor channels, no adaptive friction.
# ═══════════════════════════════════════════════════════════════════

class Mode4GravityEngine:
    """Paper-era Gravity engine without BSDT adaptive damping.

    Identical physics to ``GravityModeEngine`` at commit bb43ff5
    (2026-03-08), which produced the published FAR = 1.6% result on
    the G-SIB prospective benchmark.

    Use this when you need the exact paper-reproducible behaviour:
    no ``BSDTChannels`` damping in the iteration loop, no MFLS
    gradient blending — just Lyapunov-stabilised N-body gravity
    with Morse-topology / fused scoring.
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
                 target_far: float = 0.05):
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

        self.stabiliser = LyapunovStabiliser(min_eta=1e-5)
        self.alarm = MorseTopologyAlarm(k=k_neighbors)
        self.fused_scorer = FusedSystemScorer(k=k_neighbors) if use_fused else None
        self._far_calibrator = None

        self.scaler_: Optional[StandardScaler] = None
        self.mu_: Optional[np.ndarray] = None
        self.X_final_: Optional[np.ndarray] = None

    # ── forces / energy (identical to GravityModeEngine) ─────────

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

    # ── core fit_score (NO BSDT damping) ─────────────────────────

    def fit_score(self, X: np.ndarray, y: Optional[np.ndarray] = None
                  ) -> np.ndarray:
        """Run gravity simulation and return noise-immune scores.

        This is the paper-era implementation: pure Lyapunov ISS
        integration with NO blind-spot tensor damping.
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

        # ── Euler integration with Lyapunov v2 + ISS tracking ──
        # NO BSDT damping — pure radial + pairwise forces only
        self.stabiliser.reset()
        eta = self.eta
        n_sim = len(X_work)
        iters = self.iterations if n_sim <= 1000 else max(20, self.iterations // 2)
        for step in range(iters):
            F_pair = self._pairwise_forces(X_work)
            F_radial = -self.alpha * (X_work - self.mu_)
            F_total = F_pair + F_radial

            # Barrier-augmented force clamping
            F_total = self.stabiliser.clamp_forces(F_total)

            # Armijo on radial energy with ISS margin for pairwise force
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

        # Calibrate on FINAL normal positions
        X_ref_final = X_work[normal_mask]
        if len(X_ref_final) > 1:
            if self.fused_scorer is not None:
                self.fused_scorer.fit(X_ref_final, X_sim=X_work)
                if subsampled:
                    scores = self.fused_scorer.score(X_all)
                else:
                    scores = self.fused_scorer.score(X_work)
            else:
                self.alarm.fit(X_ref_final)
                if subsampled:
                    scores = self.alarm.score(X_all)
                else:
                    scores = self.alarm.score(X_work)
        else:
            if subsampled:
                scores = np.linalg.norm(X_all - X_all.mean(axis=0), axis=1)
            else:
                scores = np.linalg.norm(X_work - X_initial, axis=1)

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

# Insert before the HYBRID ENGINE section
marker = '# ═══════════════════════════════════════════════════════════════════\n#  HYBRID ENGINE (Molecular + Gravity blend)'
if marker not in content:
    print("ERROR: Could not find HYBRID ENGINE marker")
    exit(1)

content = content.replace(marker, MODE4_BLOCK.rstrip('\n') + '\n\n\n' + marker)

with open(FILE, 'w', encoding='utf-8') as f:
    f.write(content)

# Verify
with open(FILE, 'r', encoding='utf-8') as f:
    final = f.read()
assert 'class Mode4GravityEngine' in final
print(f"SUCCESS — Mode4GravityEngine inserted. File now {len(final.splitlines())} lines.")
