# ═══════════════════════════════════════════════════════════════════════════════
# §12. BSDT RESONANCE ENGINE — SIAM PIPELINE
#      (Physics Simulation + BSDT Scoring + Conformal P-values)
# ═══════════════════════════════════════════════════════════════════════════════
class BSDTResonanceEngine:
    """SIAM Paper Pipeline — Physics Simulation + BSDT Scoring + Conformal P-values.

    YOUR multi-scale force engines (LJ Micro, Hybrid Meso, MHD Macro) provide
    the physics forces. The SIAM pipeline provides the simulation framework,
    scoring, and statistical calibration.

    Phase 1 — Euler Integration with Lyapunov Control:
        F_total = F_lj + F_grav + F_radial + F_damp
        F_damp = -γ(E_BS) · ∇E_BS(X)   [BSDT adaptive friction, Theorem C]
        Armijo backtracking + barrier clamping + La Salle convergence

    Phase 2 — Score on CONVERGED Positions:
        CanonicalBSDT → δ_C, δ_G, δ_A, δ_T → E_BS, MFLS, score
        Morse alarm: D²E_BS eigenvalues (morse_index ≥ 1 = saddle point)
        Betti alarm: kNN topology Conley/β₀ z-score > 2
        Fused score: Fisher VR over [BSDT, Morse, Betti] views

    Phase 3 — Conformal P-values:
        p*(x) = (1 + #{cal_i ≥ score(x)}) / (n_cal + 1)
        BSDT alarm: mean(p_value) < 2α  [statistically calibrated]
    """

    def __init__(self, d, N_ref=200, sigma_lj=1.0, epsilon_lj=1.0,
                 alpha_meso=0.1, gamma_meso=1.0, sigma_h=1.0, lambda_h=0.1,
                 mu_0=1.0, eta_0=0.01, lambda_mfls=0.3, tau_mfls=0.5,
                 K=None, enable_streaming=False, hnsw_M=16, hnsw_ef=200,
                 iterations=60, eta_sim=0.01, alpha_radial=0.1,
                 use_bsdt_damping=True, target_far=0.05):
        self.d = d
        self.iterations = iterations
        self.eta_sim = eta_sim
        self.alpha_radial = alpha_radial
        self.use_bsdt_damping = use_bsdt_damping
        self.target_far = target_far

        # Reference statistics + index
        self.ref = ReferenceStatistics(d=d, sigma_lj=sigma_lj, epsilon_lj=epsilon_lj)
        self.index = InteractionIndex(d=d, M=hnsw_M, ef_construction=hnsw_ef)

        # YOUR three force engines — unchanged
        self.micro = LJMicroscaleEngine(self.ref)
        self.meso = HybridMesoscaleEngine(self.ref, alpha=alpha_meso, gamma=gamma_meso,
                                           sigma_h=sigma_h, lambda_h=lambda_h, K=K)
        self.macro = MHDMacroscaleEngine(self.ref, mu_0=mu_0, eta_0=eta_0)

        # SIAM pipeline components
        self.stabiliser = LyapunovStabiliser()
        self.bsdt = CanonicalBSDT(k=min(K or 10, 15))
        self.betti = BettiTopologyConfirmer(k=min(K or 10, 15))
        self.weight_mgr = WeightManager()
        self.streaming = StreamingSketchEngine() if enable_streaming else None

        # Conformal calibration state
        self._cal_sorted = None
        self._conformal_fitted = False

        # Simulation state
        self._mu = None
        self._theta_bs = 1.0
        self._beta_mfls = 1.0
        self._fitted = False
        self._t = 0

    # ─── Force computation ───────────────────────────────────────────────

    def _compute_forces(self, X):
        """Combined forces: F_lj (micro) + F_grav (meso) + F_radial (centering)."""
        F_lj = self.micro.compute_forces(X)
        F_grav = self.meso.compute_forces(X, t=self._t)
        F_radial = -self.alpha_radial * (X - self._mu)
        return F_lj + F_grav + F_radial

    def _lj_energy(self, X):
        """Total LJ potential for Lyapunov energy tracking."""
        from scipy.spatial.distance import pdist
        sigma = self.ref.sigma_lj
        epsilon = self.ref.epsilon_lj
        rs = pdist(X)
        rs = np.maximum(rs, sigma * 0.3)
        sr6 = (sigma / rs) ** 6
        return float(np.sum(4.0 * epsilon * (sr6 ** 2 - sr6)))

    # ─── Phase 1: Physics simulation (Euler + Lyapunov) ─────────────────

    def _simulate(self, X):
        """Phase 1: Euler integration with Lyapunov control + BSDT damping.

        Runs physics simulation to converge particles to equilibrium.
        Anomalous points resist convergence → higher E_BS after convergence.

        Returns (X_final, sim_report_dict).
        """
        X_sim = X.copy().astype(np.float64)
        N = len(X_sim)
        eta = self.eta_sim
        self.stabiliser.reset()
        iters = self.iterations if N <= 200 else max(20, self.iterations // 2)
        disp = 0.0

        for step in range(iters):
            # Combined physics forces from YOUR multi-scale engines
            F_phys = self._compute_forces(X_sim)

            # BSDT adaptive damping (Theorem C, SIAM eq:bsdamped)
            # Ẋ = F(X) - γ(E_BS) · ∇E_BS(X)
            if self.use_bsdt_damping and self.bsdt._fitted:
                e_bs = self.bsdt.energy(X_sim)
                grad_bs = self.bsdt._gradient_vectors(X_sim)
                mfls_bs = np.linalg.norm(grad_bs, axis=1)
                e_combined = e_bs + self._beta_mfls * mfls_bs
                gamma_bs = e_combined / (e_combined + self._theta_bs)
                F_damp = -gamma_bs[:, None] * grad_bs
                F_total = F_phys + F_damp
            else:
                F_total = F_phys

            # Barrier-augmented force clamping (C¹ smooth)
            F_total = self.stabiliser.clamp_forces(F_total)

            # Armijo backtracking with ISS margin
            E_old = self._lj_energy(X_sim)
            grad_norm_sq = float(np.sum(F_total ** 2))
            X_cand = X_sim + eta * F_total
            E_new = self._lj_energy(X_cand)
            accept, eta = self.stabiliser.accept_step(E_old, E_new, grad_norm_sq, eta)

            if accept:
                X_sim = X_cand
            else:
                X_sim = X_sim + eta * F_total

            # Safety: prevent NaN/explosion
            X_sim = np.clip(X_sim, -100, 100)
            if np.any(np.isnan(X_sim)):
                X_sim = np.nan_to_num(X_sim, nan=0.0)

            # La Salle convergence check
            disp = eta * float(np.max(np.linalg.norm(F_total, axis=1)))
            if self.stabiliser.check_convergence(grad_norm_sq, disp):
                break

        return X_sim, {'n_steps': step + 1,
                       'accept_rate': self.stabiliser.acceptance_rate,
                       'final_disp': disp}

    # ─── Phase 2: Scoring on converged positions ────────────────────────

    @staticmethod
    def _fisher_fuse(views):
        """Fisher VR fusion across views (identical to FusedSystemScorer)."""
        names = list(views.keys())
        V = np.column_stack([views[n] for n in names])
        total = V.sum(axis=1)
        p80, p50 = np.percentile(total, 80), np.percentile(total, 50)
        hi, lo = total >= p80, total <= p50
        K = len(names)
        if hi.sum() >= 2 and lo.sum() >= 2:
            fr = np.zeros(K)
            for i in range(K):
                mu_h, mu_l = V[hi, i].mean(), V[lo, i].mean()
                fr[i] = (mu_h - mu_l) ** 2 / (V[hi, i].var() + V[lo, i].var() + 1e-10)
            s = fr.sum()
            w = fr / s if s > 1e-10 else np.ones(K) / K
        else:
            w = np.ones(K) / K
        return (V * w).sum(axis=1)

    def _score_fused(self, X_final):
        """Fused scoring on converged positions: BSDT + Morse + Betti views.

        Three complementary views fused via Fisher VR:
          1. BSDT: E_BS + MFLS combined score (from CanonicalBSDT)
          2. Morse: per-point kNN distance features (topological anomaly)
          3. Betti: Conley stability index (topological instability)
        """
        # View 1: BSDT score (E_BS + MFLS)
        bsdt_score = self.bsdt.score(X_final)

        # View 2: Morse topology (mean kNN distance, reference-normalized)
        from sklearn.neighbors import NearestNeighbors
        k = min(self.bsdt.k, len(X_final) - 1)
        if k >= 2:
            nn = NearestNeighbors(n_neighbors=k + 1, algorithm='auto').fit(X_final)
            dists, _ = nn.kneighbors(X_final)
            morse_score = dists[:, 1:].mean(axis=1)
            morse_score = morse_score / (np.median(morse_score) + 1e-10)
        else:
            morse_score = np.ones(len(X_final))

        # View 3: Betti topology (Conley stability, reference-normalized)
        betti_feats = self.betti._compute_features(X_final)
        betti_score = betti_feats['conley']
        betti_score = betti_score / (np.median(betti_score) + 1e-10)

        return self._fisher_fuse({'bsdt': bsdt_score,
                                   'morse': morse_score,
                                   'betti': betti_score})

    # ─── Phase 3: Conformal p-values ────────────────────────────────────

    def predict_pvalue(self, scores):
        """Conformal p-values: p(x) = (1 + #{cal ≥ score(x)}) / (n_cal + 1).

        Guaranteed: P(p* ≤ α) ≤ α for any α ∈ (0,1).
        """
        if not self._conformal_fitted:
            return np.full(len(scores), 0.5)
        n_cal = len(self._cal_sorted)
        rank = n_cal - np.searchsorted(self._cal_sorted, scores, side='left')
        return (1.0 + rank) / (n_cal + 1)

    # ─── Fit reference (calibration) ────────────────────────────────────

    def fit_reference(self, X_ref):
        """Fit: simulate reference → calibrate BSDT → conformal split → Betti.

        SIAM paper pipeline:
        1. Fit CanonicalBSDT on raw reference (for damping during simulation)
        2. Conformal split: 80% fit, 20% calibration
        3. Simulate fit set → converge → re-fit BSDT on final positions
        4. Simulate + score calibration set → store sorted scores
        5. Calibrate Betti on converged reference topology
        """
        self.ref.fit(X_ref)
        self.index.build(X_ref)
        self._mu = X_ref.mean(axis=0)

        # Auto-calibrate σ, ε from reference distance distribution
        from scipy.spatial.distance import pdist
        N_sub = min(500, len(X_ref))
        ds = pdist(X_ref[:N_sub])
        self.ref.sigma_lj = float(np.percentile(ds, 25))
        self.ref.epsilon_lj = float(np.std(ds) + 1e-10)

        # (1) Initial BSDT fit on raw reference (for damping)
        self.bsdt.fit(X_ref)
        self._theta_bs = self.bsdt.theta_bs_
        self._beta_mfls = self.bsdt.beta_mfls_

        # (2) Conformal split
        N = len(X_ref)
        n_cal = max(10, int(N * 0.2))
        rng = np.random.default_rng(42)
        perm = rng.permutation(N)
        X_fit = X_ref[perm[:-n_cal]]
        X_cal = X_ref[perm[-n_cal:]]

        # (3) Simulate fit set → converge → re-fit BSDT on final positions
        self._fitted = True
        self.meso._fit_clusters(X_fit, 0)
        X_fit_final, sim_rep = self._simulate(X_fit)
        self.bsdt.fit(X_fit_final)
        self._theta_bs = self.bsdt.theta_bs_
        self._beta_mfls = self.bsdt.beta_mfls_

        # (4) Simulate + score calibration set → conformal sorted
        X_cal_final, _ = self._simulate(X_cal)
        cal_scores = self._score_fused(X_cal_final)
        self._cal_sorted = np.sort(cal_scores)
        self._conformal_fitted = True

        # (5) Betti on converged reference topology
        self.betti.fit(X_fit_final)

        # Diagnostics
        fw = self.bsdt.fisher_w_
        print(f"    BSDT calibrated: θ_BS={self._theta_bs:.6f}, "
              f"β_MFLS={self._beta_mfls:.4f}")
        print(f"    Simulation: {sim_rep['n_steps']} steps, "
              f"accept={sim_rep['accept_rate']:.1%}")
        print(f"    Fisher VR channels: C={fw[0]:.3f} G={fw[1]:.3f} "
              f"A={fw[2]:.3f} T={fw[3]:.3f}")
        print(f"    Conformal cal: {len(self._cal_sorted)} pts, "
              f"range [{self._cal_sorted[0]:.4f}, {self._cal_sorted[-1]:.4f}]")
        print(f"    Betti: ref_conley_μ={self.betti._ref_conley_mu:.4f}, "
              f"ref_β₀_μ={self.betti._ref_beta0_mu:.4f}")

    # ─── Main compute step ──────────────────────────────────────────────

    def compute_step(self, X, dt=1.0, activity_counts=None, streaming_keys=None):
        """Full SIAM pipeline: simulate → score → conformal p-value → alarm.

        Phase 1: Physics simulation (Euler + LJ + gravity + BSDT damping)
        Phase 2: Score on converged positions (BSDT + Morse + Betti fusion)
        Phase 3: Conformal p-values + 3-tier alarm system

        Returns dict compatible with all benchmark functions.
        """
        assert self._fitted
        self._t += 1

        # ═══ PHASE 1: Physics Simulation ═══
        X_final, sim_rep = self._simulate(X)

        # ═══ PHASE 2: Score on Converged Positions ═══
        E_BS = self.bsdt.energy(X_final)
        MFLS = self.bsdt.mfls(X_final)
        gamma_vals = self.bsdt.gamma(X_final)
        fused = self._score_fused(X_final)

        # ═══ PHASE 3: Conformal P-values ═══
        p_vals = self.predict_pvalue(fused)
        # 1 - p_value: higher = more anomalous (AUC-compatible)
        anomaly_scores = 1.0 - p_vals

        # ═══ 3-TIER ALARM SYSTEM ═══
        # Tier 1: BSDT — conformal p-value test (statistically calibrated)
        bsdt_alarm = bool(np.mean(p_vals) < self.target_far * 2)

        # Tier 2: Morse — Hessian of E_BS (phase transition, morse_index ≥ 1)
        morse_alarm = self.bsdt.morse_alarm(X_final)

        # Tier 3: Betti — topological shift (Conley/β₀ z-score > 2)
        betti_alarm, z_conley, z_beta0, betti_detail = self.betti.check(X_final)

        # Combined alarm level
        alarm_level = 0
        if bsdt_alarm:
            alarm_level = 1
            if morse_alarm:
                alarm_level = 2
                if betti_alarm:
                    alarm_level = 3
        # Morse+Betti can escalate even without BSDT
        if morse_alarm and not bsdt_alarm:
            alarm_level = max(alarm_level, 2 if betti_alarm else 1)

        # MHD macro diagnostics (system-level, post-simulation)
        macro_r = self.macro.compute(X_final, float(np.mean(E_BS)),
                                     self._t, dt=dt)

        return {'p_star': anomaly_scores,
                'p_value': p_vals,
                'E_BS': E_BS, 'MFLS': MFLS,
                'fused_score': fused,
                'gamma_total': float(np.mean(gamma_vals)),
                'E_BS_mean': float(np.mean(E_BS)),
                'E_BS_max': float(np.max(E_BS)),
                'MFLS_mean': float(np.mean(MFLS)),
                'MFLS_max': float(np.max(MFLS)),
                'score_mean': float(np.mean(fused)),
                'score_max': float(np.max(fused)),
                'sim_steps': sim_rep['n_steps'],
                'sim_accept_rate': sim_rep['accept_rate'],
                # 3-tier alarm
                'bsdt_alarm': bsdt_alarm,
                'morse_alarm': morse_alarm,
                'morse_index': 1 if morse_alarm else 0,
                'betti_alarm': betti_alarm,
                'z_conley': z_conley, 'z_beta0': z_beta0,
                'alarm_level': alarm_level,
                # legacy compat
                'macro': macro_r,
                'weights': {s: dict(self.weight_mgr.weights[s])
                            for s in self.weight_mgr.scales},
                't': self._t}
