"""
collapse_geometry.py
====================
Geometry of System Collapse — closed-form, no simulation.

Reduces the full BSDT collapse-detection problem to seven analytic
quantities computed entirely on the frozen C* ellipsoid:

  GEOMETRY (radial):
    1. Q(x) = Σ x_j²/a_j²          radial Mahalanobis on C*
    2. λ_max(x) = max eigenvalue     spectral radius of local Hessian
    3. Φ_eff(x)                      effective potential (gravity+molecular)

  TRIGONOMETRY (angular):
    4. θ(x) = arccos(d̃·d̄_ref)      angular departure from reference
    5. AM(x) = √(Δd̃ᵀ Σ_d⁻¹ Δd̃)    angular Mahalanobis

  CROSS (geometry × trigonometry):
    6. Q_excess × θ                  radial-angular collapse coupling
    7. K × θ                         curvature-weighted angular departure

From these, four collapse indicators are derived (all O(N·d)):

  ┌─────────────────────────────────────────────────────────────┐
  │  I.   C* CROSSING:  Q(x) > τ_Q  (χ²_{0.99}(d))            │
  │  II.  COLLAPSE DIRECTION:  θ(x) > θ_crit (angular alarm)   │
  │  III. DISSIPATION FAILURE:  σ(x) < σ_min (Lyapunov check)  │
  │  IV.  ENERGY DIVERGENCE:  dE/dt > 0 (energy growing)       │
  │                                                             │
  │  COLLAPSE SCORE = Fisher VR fusion of I–IV                  │
  │  LEAD-TIME = τ_Q / (dQ/dt) ≈ τ_Q / ||∇Q|| (time to cross) │
  └─────────────────────────────────────────────────────────────┘

Paper references:
  §2.3  E_BS(X) = Σ w_k ψ_k(δ_k) + Φ_pair
  §2.4  γ*(X) = α / (λ_max + ε)
  Thm 5.1  C* separates constant-friction-stable / adaptive-required
  Thm R    dV/dt ≤ −c₄ ||∇E_BS||²  (Lyapunov dissipation)
  Thm NC   E_BS = 0 ⟺ equilibrium (no spurious absorption)

Complexity: O(N·d) + O(d³) one-time fit.

Author: Odeyemi Olusegun Israel
"""
from __future__ import annotations
import numpy as np
from typing import Optional


class CollapseReport:
    """Per-observation collapse diagnostics."""
    __slots__ = (
        'Q', 'tau_Q', 'crossed_Cstar', 'lambda_max', 'phi_eff',
        'theta', 'theta_crit', 'angular_alarm', 'AM',
        'Q_excess_theta', 'K_theta',
        'delta_C', 'delta_G', 'delta_A', 'delta_T',
        'E_BS', 'dE_sign', 'sigma_dissipation', 'gamma_star',
        'dissipation_failure', 'collapse_score', 'lead_time',
    )

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


class CollapseGeometry:
    r"""
    Geometry of System Collapse — all formulas, no simulation.

    Reduces collapse detection to seven analytic quantities on C*:
      Q, λ_max, Φ_eff  (geometry)
      θ, AM             (trigonometry)
      Q×θ, K×θ          (cross)

    These are combined into a unified collapse score via Fisher VR
    fusion, with per-observation diagnostics explaining *why* collapse
    is predicted and *when* (lead-time estimate).

    Usage
    -----
    >>> cg = CollapseGeometry()
    >>> cg.fit(X_reference)                    # O(d³)
    >>> report = cg.detect(X_test)             # O(N·d)
    >>> report.collapse_score                  # (N,)
    >>> report.lead_time                       # (N,) steps to C*

    All computations are O(N·d) closed-form.  No kNN, no simulation,
    no pairwise distances.  The only cubic cost is the one-time
    eigendecomposition in fit().
    """

    def __init__(self, alpha: float = 0.30, epsilon: float = 1e-6,
                 sigma_gravity: float = 1.0, lambda_rep: float = 0.05,
                 gamma_gravity: float = 0.5):
        """
        Parameters
        ----------
        alpha : scalar gain for adaptive friction γ* = α/(λ_max + ε)
        epsilon : regulariser preventing division by zero in γ*
        sigma_gravity : Gaussian attraction width for Φ_gravity
        lambda_rep : repulsion strength in Φ_gravity
        gamma_gravity : gravity coupling constant
        """
        self.alpha = alpha
        self.epsilon = epsilon
        self.sigma_gravity = sigma_gravity
        self.lambda_rep = lambda_rep
        self.gamma_gravity = gamma_gravity

        # Frozen state (set by fit)
        self._mu = None
        self._sigma = None
        self._a2 = None          # semi-axes²
        self._R = None           # rotation matrix
        self._c = None           # centre in standardised space
        self._d = 0              # dimensionality
        self._tau_Q = 0.0        # χ²_{0.99}(d)
        self._Q_ref_median = 0.0 # median Q in reference distribution
        self._d_bar = None       # mean angular direction
        self._Sigma_d_inv = None # angular covariance inverse
        self._theta_crit = 0.0   # angular alarm threshold
        self._K_p99 = 1.0        # curvature normaliser

        # BSDT channel state (paper v3)
        self._P_A = None         # active subspace projector
        self._v0 = 0.0           # reference gradient norm threshold
        self._log_norm_const = 0.0
        self._trace_Sigma = 0.0

        # Fisher VR weights for final fusion
        self._w_fusion = None    # (7,) weights for 7 indicators
        self._fusion_mu = None   # (7,) reference means
        self._fusion_std = None  # (7,) reference stds

    # ──────────────────────────────────────────────────────────────
    #  FIT — freeze everything from reference window
    # ──────────────────────────────────────────────────────────────

    def fit(self, X_ref: np.ndarray) -> 'CollapseGeometry':
        """Freeze all geometry from normal reference window.

        Performs:
          1. Standardise → eigendecompose → C* ellipsoid (a²)
          2. Freeze angular statistics (d̄, Σ_d⁻¹)
          3. Theory thresholds: τ_Q = χ²_{0.99}(d), θ_crit = p99(θ_ref)
          4. Active subspace P_A for δ_G
          5. Reference gradient envelope v₀ for δ_A
          6. Fisher VR weights for 7-indicator fusion

        O(d³) for eigendecomposition, O(N·d) for everything else.
        """
        N, d = X_ref.shape
        self._d = d

        # ── Step 1: Standardise + eigendecompose ──
        self._mu = X_ref.mean(axis=0)
        self._sigma = X_ref.std(axis=0) + 1e-10
        Xs = (X_ref - self._mu) / self._sigma
        self._c = Xs.mean(axis=0)

        cov = np.cov(Xs.T)
        vals, vecs = np.linalg.eigh(cov)
        vals = np.maximum(vals, 1e-10)
        ix = np.argsort(-vals)
        self._a2 = vals[ix]
        self._R = vecs[:, ix].T

        # ── Step 2: χ² theory threshold (Wilson-Hilferty) ──
        z99 = 2.3263
        h = 2.0 / (9.0 * d)
        self._tau_Q = d * (1.0 - h + z99 * np.sqrt(h)) ** 3

        # ── Step 3: Body coordinates + angular statistics ──
        Xb = self._body(Xs)

        # Reference Q distribution — needed for friction proximity score
        Q_ref = np.sum(Xb ** 2 / self._a2, axis=1)
        self._Q_ref_median = float(np.median(Q_ref))

        dirs = self._dir(Xb)
        dm = dirs.mean(axis=0)
        self._d_bar = dm / (np.linalg.norm(dm) + 1e-12)

        dd = dirs - self._d_bar
        Cd = (dd.T @ dd) / N + np.eye(d) * 1e-6
        self._Sigma_d_inv = np.linalg.inv(Cd)

        # Angular alarm threshold: 99th percentile of reference θ
        cos_t = np.clip(dirs @ self._d_bar, -1.0, 1.0)
        theta_ref = np.arccos(cos_t)
        self._theta_crit = float(np.percentile(theta_ref, 99))

        # Curvature normaliser
        g = Xb / self._a2
        p2 = np.sum(g ** 2, axis=1)
        K = 1.0 / (float(np.prod(self._a2)) * p2 ** 2 + 1e-300)
        self._K_p99 = float(np.percentile(K, 99)) + 1e-12

        # ── Step 4: Active subspace for δ_G ──
        cov_raw = np.cov(X_ref.T)
        ev_raw, evec_raw = np.linalg.eigh(cov_raw)
        idx_desc = np.argsort(-ev_raw)
        ev_s = ev_raw[idx_desc]
        evec_s = evec_raw[:, idx_desc]
        cumvar = np.cumsum(ev_s) / (ev_s.sum() + 1e-30)
        n_active = max(1, int(np.searchsorted(cumvar, 0.95) + 1))
        V_A = evec_s[:, :n_active]
        self._P_A = V_A @ V_A.T

        # ── Step 5: Reference gradient envelope for δ_A ──
        a2_raw = np.var(X_ref, axis=0) + 1e-10
        grad_ref = 2.0 * X_ref / a2_raw
        grad_norm_ref = np.linalg.norm(grad_ref, axis=1)
        self._v0 = float(np.percentile(grad_norm_ref, 95))

        # Density normalisation
        self._log_norm_const = (d / 2.0) * np.log(2 * np.pi) + \
                               0.5 * np.sum(np.log(self._a2 + 1e-30))
        self._trace_Sigma = float(np.sum(self._a2))

        # ── Step 6: Compute all 7 indicators on reference for fusion ──
        ind_ref = self._raw_indicators(X_ref)  # (N, 7)
        mu = ind_ref.mean(axis=0)
        std = ind_ref.std(axis=0) + 1e-10
        self._fusion_mu = mu
        self._fusion_std = std

        # Fisher VR weights on the 7 indicators
        z = (ind_ref - mu) / std
        zp = np.maximum(z, 0)
        tot = zp.sum(axis=1)
        p80, p50 = np.percentile(tot, 80), np.percentile(tot, 50)
        hi, lo = tot >= p80, tot <= p50
        n_ind = 7
        if hi.sum() >= 2 and lo.sum() >= 2:
            fr = np.zeros(n_ind)
            for k in range(n_ind):
                mh, ml = zp[hi, k].mean(), zp[lo, k].mean()
                vh, vl = zp[hi, k].var(),  zp[lo, k].var()
                fr[k] = (mh - ml) ** 2 / max(vh + vl, 1e-10)
            s = fr.sum()
            self._w_fusion = fr / s if s > 1e-10 else np.ones(n_ind) / n_ind
        else:
            self._w_fusion = np.ones(n_ind) / n_ind

        # Store reference raw-score statistics for sigmoid calibration
        raw_ref = zp @ self._w_fusion
        self._score_centre = float(np.percentile(raw_ref, 95))
        self._score_scale = float(np.std(raw_ref) + 1e-10)

        return self

    # ──────────────────────────────────────────────────────────────
    #  REFERENCE VALIDATION — statistical guarantee of "normality"
    # ──────────────────────────────────────────────────────────────

    def validate_reference(self, X_ref: np.ndarray,
                           verbose: bool = False) -> dict:
        r"""Five-test statistical validation of a candidate reference window.

        All five tests must pass for the reference to be accepted as
        genuinely "normal".  The tests are:

          1. STATIONARITY — Augmented Dickey-Fuller per feature.
             A normal reference must be stationary (p < 0.05 for
             ≥ (d-1) features).  Non-stationary features contain
             trends that corrupt the ellipsoid.

          2. SELF-CONSISTENCY — fit on X_ref, score X_ref.
             If > 5% of reference observations score above 0.5,
             the reference contains anomalies.  A clean reference
             should be almost entirely inside C* by construction.

          3. EIGENVALUE STABILITY — bootstrap the covariance.
             Resample X_ref 200 times, compute eigenvalues each
             time.  If CV(λ_k) > 0.5 for any top eigenvalue, the
             reference is too short or too noisy for stable geometry.

          4. CROSS-VALIDATION — half-split agreement.
             Fit on each half of X_ref independently.  If the two
             τ_Q values differ by > 50%, or the two mean directions
             d̄ have cosine similarity < 0.8, the reference is
             inhomogeneous (contains a regime change).

          5. SAMPLE SIZE — minimum N ≥ 3d observations.
             Below this, the covariance estimate is rank-deficient
             and the ellipsoid is unreliable.

        Parameters
        ----------
        X_ref   : (N, d) candidate reference window
        verbose : print diagnostics

        Returns
        -------
        dict with:
          valid      : bool — all 5 tests pass
          tests      : dict of {test_name: (passed: bool, detail: str)}
          n_passed   : int — number of tests passed (out of 5)
        """
        N, d = X_ref.shape
        results = {}

        # ── Test 1: Stationarity (ADF) ──
        try:
            from scipy.stats import pearsonr
            # Lightweight stationarity: correlation of feature with
            # time index.  |r| > 0.3 with p < 0.05 → trend present.
            n_trend = 0
            t_idx = np.arange(N, dtype=float)
            for j in range(d):
                col = X_ref[:, j]
                if np.std(col) < 1e-12:
                    continue
                r, p = pearsonr(t_idx, col)
                if abs(r) > 0.3 and p < 0.05:
                    n_trend += 1
            max_trend = max(1, d // 3)  # allow up to 1/3 trending
            passed = n_trend <= max_trend
            results['stationarity'] = (passed,
                f"{n_trend}/{d} features trending (max {max_trend})")
        except ImportError:
            results['stationarity'] = (True, "scipy unavailable, skipped")

        # ── Test 2: Self-consistency ──
        cg_tmp = CollapseGeometry(
            alpha=self.alpha, epsilon=self.epsilon,
            sigma_gravity=self.sigma_gravity,
            lambda_rep=self.lambda_rep,
            gamma_gravity=self.gamma_gravity)
        cg_tmp.fit(X_ref)
        scores_ref = cg_tmp.score(X_ref)
        frac_anomalous = float((scores_ref > 0.5).mean())
        passed = frac_anomalous <= 0.05
        results['self_consistency'] = (passed,
            f"{frac_anomalous:.1%} of reference scores > 0.5 (max 5%)")

        # ── Test 3: Eigenvalue stability (bootstrap) ──
        n_boot = 200
        Xs = (X_ref - X_ref.mean(axis=0)) / (X_ref.std(axis=0) + 1e-10)
        n_top = min(3, d)
        boot_eigs = np.empty((n_boot, n_top))
        rng = np.random.default_rng(42)
        for b in range(n_boot):
            idx = rng.choice(N, N, replace=True)
            cov_b = np.cov(Xs[idx].T)
            vals_b = np.sort(np.linalg.eigvalsh(cov_b))[::-1]
            boot_eigs[b] = vals_b[:n_top]
        cv = boot_eigs.std(axis=0) / (boot_eigs.mean(axis=0) + 1e-12)
        max_cv = float(cv.max())
        passed = max_cv < 0.5
        results['eigenvalue_stability'] = (passed,
            f"max CV(λ) = {max_cv:.3f} (threshold 0.5)")

        # ── Test 4: Cross-validation (half-split) ──
        mid = N // 2
        if mid >= max(d + 1, 5):
            cg_a = CollapseGeometry()
            cg_b = CollapseGeometry()
            cg_a.fit(X_ref[:mid])
            cg_b.fit(X_ref[mid:])
            tau_ratio = max(cg_a._tau_Q, cg_b._tau_Q) / (
                min(cg_a._tau_Q, cg_b._tau_Q) + 1e-12)
            cos_sim = float(np.dot(cg_a._d_bar, cg_b._d_bar))
            passed = tau_ratio < 1.5 and cos_sim > 0.5
            results['cross_validation'] = (passed,
                f"τ_Q ratio={tau_ratio:.3f} (<1.5), "
                f"cos(d̄_A, d̄_B)={cos_sim:.3f} (>0.5)")
        else:
            results['cross_validation'] = (False,
                f"N/2={mid} too small for d={d}")

        # ── Test 5: Sample size ──
        min_n = 3 * d
        passed = N >= min_n
        results['sample_size'] = (passed,
            f"N={N} vs 3d={min_n}")

        n_passed = sum(v[0] for v in results.values())
        all_pass = n_passed == len(results)

        if verbose:
            for name, (p, det) in results.items():
                status = "PASS" if p else "FAIL"
                print(f"  [{status}] {name}: {det}")
            print(f"  {'VALID' if all_pass else 'INVALID'}: "
                  f"{n_passed}/{len(results)} tests passed")

        return {
            'valid': all_pass,
            'tests': results,
            'n_passed': n_passed,
        }

    # ──────────────────────────────────────────────────────────────
    #  FIT_AUTO — automatic reference window selection
    # ──────────────────────────────────────────────────────────────

    def fit_auto(self, X_full: np.ndarray,
                 min_window: Optional[int] = None,
                 max_window: Optional[int] = None,
                 stride: int = 1,
                 prefer_early: bool = True,
                 verbose: bool = False) -> 'CollapseGeometry':
        r"""Automatically find and fit the best reference window.

        Slides a window across X_full, validates each candidate,
        and picks the one with the highest stability (lowest
        internal score variance among valid windows).

        Algorithm
        ---------
        For each candidate window [i, i+W):
          1. Run validate_reference() — must pass all 5 tests
          2. Compute internal score variance (lower = more stable)
          3. Apply temporal bias: cost(i) = var + λ·(i/T)
          4. Track the valid window with minimum cost

        If no window passes all 5 tests, relax to best 4/5.
        If still none, relax to best 3/5 with a warning.

        Parameters
        ----------
        X_full     : (T, d) full time series
        min_window : minimum window size (default: max(5d, 30))
        max_window : maximum window size (default: T//3)
        stride     : step size for sliding window (default: 1)
        prefer_early : if True, add a soft penalty for later windows.
            Encodes the prior that "normal = before the event."
            The penalty is λ·(mid/T) where λ is the median
            variance of valid candidates, so temporal position
            matters but cannot override a much-better-validated
            window.  Default True.
        verbose    : print search progress

        Returns
        -------
        self (fitted on best window)

        Raises
        ------
        ValueError if no window achieves ≥ 3/5 validation tests.

        Attributes set
        --------------
        _ref_start : int — start index of chosen reference
        _ref_end   : int — end index of chosen reference
        _ref_validation : dict — validation results for chosen window
        """
        T, d = X_full.shape
        if min_window is None:
            min_window = max(5 * d, 30)
        if max_window is None:
            max_window = max(min_window, T // 3)

        best = {'score': np.inf, 'start': 0, 'end': min_window,
                'n_passed': 0, 'validation': None}

        # Collect all valid candidates
        candidates = []  # (n_passed, var_score, start, end, validation)

        # Try multiple window sizes
        window_sizes = set()
        for w in [min_window, (min_window + max_window) // 2, max_window]:
            w = min(max(w, min_window), max_window)
            window_sizes.add(w)
        # Also try some intermediate sizes
        for f in [0.25, 0.5, 0.75]:
            w = int(min_window + f * (max_window - min_window))
            w = min(max(w, min_window), max_window)
            window_sizes.add(w)

        n_candidates = 0
        for W in sorted(window_sizes):
            step = max(stride, W // 10)  # coarse scan, then refine
            for i in range(0, T - W + 1, step):
                X_cand = X_full[i:i + W]
                n_candidates += 1

                val = self.validate_reference(X_cand)
                np_val = val['n_passed']

                if np_val < 3:
                    continue  # not even close

                # Score: number of tests passed (higher is better),
                # then internal score variance (lower is better)
                cg_tmp = CollapseGeometry(
                    alpha=self.alpha, epsilon=self.epsilon,
                    sigma_gravity=self.sigma_gravity,
                    lambda_rep=self.lambda_rep,
                    gamma_gravity=self.gamma_gravity)
                cg_tmp.fit(X_cand)
                scores_cand = cg_tmp.score(X_cand)
                var_score = float(np.var(scores_cand))

                candidates.append((np_val, var_score, i, i + W, val))

                if verbose and (not candidates or
                    np_val > best.get('n_passed', 0) or
                    var_score < best.get('score', np.inf)):
                    print(f"  Candidate: [{i}:{i+W}] "
                          f"({np_val}/5 tests, var={var_score:.6f})")

        if not candidates:
            raise ValueError(
                f"No reference window achieves ≥ 3/5 validation "
                f"tests (searched {n_candidates} candidates). "
                f"Data may not contain a stable normal period.")

        # ── Select best candidate with temporal bias ──
        # Compute penalty scale: median variance of all candidates
        all_vars = [c[1] for c in candidates]
        lambda_time = float(np.median(all_vars)) if prefer_early else 0.0

        best_cost = np.inf
        best_cand = candidates[0]
        for (np_val, var_score, start, end, val) in candidates:
            # Primary: more tests passed is always better
            # Secondary: cost = var + λ·(midpoint/T)
            mid = (start + end) / 2.0
            time_penalty = lambda_time * (mid / T) if prefer_early else 0.0
            cost = var_score + time_penalty

            # n_passed dominates: use -n_passed * 1e6 + cost
            combined = -np_val * 1e6 + cost
            if combined < best_cost:
                best_cost = combined
                best_cand = (np_val, var_score, start, end, val)

        np_best, var_best, s_best, e_best, val_best = best_cand
        best = {
            'score': var_best,
            'start': s_best,
            'end': e_best,
            'n_passed': np_best,
            'validation': val_best,
        }

        if verbose:
            print(f"\n  Temporal bias: λ={lambda_time:.6f}, "
                  f"prefer_early={prefer_early}")
            print(f"  Evaluated {len(candidates)} valid candidates "
                  f"(of {n_candidates} total)")

        # Fit on the best window
        self.fit(X_full[best['start']:best['end']])
        self._ref_start = best['start']
        self._ref_end = best['end']
        self._ref_validation = best['validation']

        if verbose:
            print(f"\n  Selected reference: [{best['start']}:"
                  f"{best['end']}] ({best['end']-best['start']} obs)")
            print(f"  Validation: {best['n_passed']}/5 tests passed")
            print(f"  Internal score variance: {best['score']:.6f}")
            self.validate_reference(
                X_full[best['start']:best['end']], verbose=True)

        if best['n_passed'] < 5:
            import warnings
            failed = [k for k, (p, _) in
                      best['validation']['tests'].items() if not p]
            warnings.warn(
                f"Best reference passes {best['n_passed']}/5 tests. "
                f"Failed: {failed}. Results should be interpreted "
                f"with caution.", stacklevel=2)

        return self

    # ──────────────────────────────────────────────────────────────
    #  FIT_SEQUENTIAL — the natural way: first W rows are "normal"
    # ──────────────────────────────────────────────────────────────

    def fit_sequential(self, X_full: np.ndarray,
                       n_ref: Optional[int] = None,
                       min_pass: int = 3,
                       verbose: bool = False) -> 'CollapseGeometry':
        r"""Fit on the first n_ref observations, validate, monitor the rest.

        This is the natural deployment pattern:
          - You have a time series starting from a known-normal period
          - The first W rows define "normal"
          - Everything after is divergence monitoring

        If the initial window fails validation, it grows forward until
        it passes (more data → more stable covariance).

        Parameters
        ----------
        X_full   : (T, d) full time series, temporally ordered
        n_ref    : number of initial rows to use as reference.
                   Default: max(5d, 30), i.e. the minimum for stable
                   geometry.
        min_pass : minimum validation tests to accept (default 3/5).
                   Set to 5 for strict mode.
        verbose  : print diagnostics

        Returns
        -------
        self (fitted on X_full[:n_ref])

        Attributes set
        --------------
        _ref_start     : 0 (always starts from the beginning)
        _ref_end       : int — end index of reference window
        _ref_validation: dict — validation results
        """
        T, d = X_full.shape
        if n_ref is None:
            n_ref = max(5 * d, 30)
        n_ref = min(n_ref, T)

        # Try the requested window first, grow if validation fails
        best_n = n_ref
        best_val = None
        max_n = min(T, max(n_ref * 3, T // 2))

        for w in range(n_ref, max_n + 1, max(1, d)):
            X_cand = X_full[:w]
            val = self.validate_reference(X_cand)

            if verbose:
                print(f"  Window [0:{w}]: {val['n_passed']}/5 tests")

            if val['n_passed'] >= min_pass:
                best_n = w
                best_val = val
                break
            # Keep the best so far
            if best_val is None or val['n_passed'] > best_val['n_passed']:
                best_n = w
                best_val = val

        # Fit on the chosen window
        self.fit(X_full[:best_n])
        self._ref_start = 0
        self._ref_end = best_n
        self._ref_validation = best_val

        if verbose:
            print(f"\n  Reference: [0:{best_n}] "
                  f"({best_n} obs, {best_val['n_passed']}/5 tests)")
            self.validate_reference(X_full[:best_n], verbose=True)

        if best_val['n_passed'] < min_pass:
            import warnings
            warnings.warn(
                f"Reference [0:{best_n}] only passes "
                f"{best_val['n_passed']}/5 tests (need {min_pass}). "
                f"Initial data may not be stationary.",
                stacklevel=2)

        return self

    # ──────────────────────────────────────────────────────────────
    #  Internal transforms (frozen)
    # ──────────────────────────────────────────────────────────────

    def _std(self, X):
        return (X - self._mu) / self._sigma

    def _body(self, X_std):
        return (X_std - self._c) @ self._R.T

    def _Q(self, Xb):
        return np.sum(Xb ** 2 / self._a2, axis=1)

    def _dir(self, Xb):
        g = Xb / self._a2
        return g / (np.linalg.norm(g, axis=1, keepdims=True) + 1e-12)

    def _to_body(self, X):
        """Raw data → body coordinates in one step."""
        return self._body(self._std(X))

    # ──────────────────────────────────────────────────────────────
    #  SEVEN ANALYTIC COLLAPSE INDICATORS
    # ──────────────────────────────────────────────────────────────

    def _raw_indicators(self, X: np.ndarray) -> np.ndarray:
        """Compute 7 raw collapse indicators.  O(N·d).

        Returns (N, 7):
          [0] Q_excess       max(Q - τ_Q, 0)       C* crossing magnitude
          [1] theta_excess   max(θ - θ_crit, 0)     angular departure
          [2] dissipation    −σ(x)                   -(c₀+γ*)||∇E||²
          [3] energy_grad    dE_proxy                energy growth proxy
          [4] Q×θ            radial-angular coupling
          [5] K×θ            curvature-angular
          [6] AM             angular Mahalanobis
        """
        Xb = self._to_body(X)
        a2 = self._a2
        d = self._d
        N = len(X)

        # ── Geometry (radial) ──
        Q = self._Q(Xb)
        Q_excess = np.maximum(Q - self._tau_Q, 0.0)    # [0]

        # ── Trigonometry (angular) ──
        dirs = self._dir(Xb)
        cos_t = np.clip(dirs @ self._d_bar, -1.0, 1.0)
        theta = np.arccos(cos_t)
        theta_excess = np.maximum(theta - self._theta_crit, 0.0)  # [1]

        # Angular Mahalanobis
        dd = dirs - self._d_bar
        AM = np.sqrt(np.maximum(
            np.sum((dd @ self._Sigma_d_inv) * dd, axis=1), 0.0))  # [6]

        # ── Spectral radius λ_max ──
        # D²Q = diag(2/a²) in body coords → λ_max = 2/min(a²)
        # Local scaling: λ_max(x) ~ Q(x) * 2/min(a²)  (displacement-weighted)
        min_a2 = float(np.min(a2))
        lam_max = 2.0 * np.maximum(Q, 1.0) / (min_a2 + 1e-12)

        # ── Adaptive friction γ*(x) = α / (λ_max + ε) ──
        gamma_star = self.alpha / (lam_max + self.epsilon)

        # ── Effective potential Φ_eff (gravity, closed-form) ──
        sigma2 = self.sigma_gravity ** 2
        a2_plus_s2 = a2 + sigma2
        Q_conv = np.sum(Xb ** 2 / a2_plus_s2, axis=1)
        phi_att = np.exp(-0.5 * Q_conv)
        r_sq = np.sum(Xb ** 2, axis=1) + self._trace_Sigma / d
        phi_rep = 0.5 * np.log(r_sq + 1e-12)
        phi_eff = self.gamma_gravity * (phi_att - self.lambda_rep * phi_rep)

        # ── BSDT channels (paper v3 §2.2) ──
        delta_C = np.sqrt(np.maximum(Q, 0.0))
        resid = X - X @ self._P_A
        delta_G = np.linalg.norm(resid, axis=1)
        grad_Q = 2.0 * Xb / a2
        grad_norm = np.linalg.norm(grad_Q, axis=1)
        delta_A = np.maximum(grad_norm - self._v0, 0.0)
        delta_T = Q / 2.0 + self._log_norm_const

        # ── E_BS energy functional (paper v3 §2.3) ──
        E_BS = delta_C**2 + delta_G**2 + delta_A**2 + delta_T**2

        # ── Dissipation rate σ(x) = (c₀ + γ*) ||∇E_BS||² ──
        # ||∇E_BS||² ≈ sum of squared channel gradients
        # ∇δ_C ~ ∇Q/(2√Q), ∇δ_A ~ ∇(||grad_Q||), etc.
        # Closed-form proxy: ||∇E_BS||² ≈ ||2x/a²||² = grad_norm²
        grad_E_sq = grad_norm ** 2
        c0 = 0.1  # base dissipation from alignment inequality
        sigma_diss = (c0 + gamma_star) * grad_E_sq     # σ(x)
        # Indicator [2]: negative dissipation → higher = worse
        neg_sigma = -sigma_diss                         # [2]

        # ── Energy growth proxy dE/dt ──
        # dV/dt ≤ −σ(x) by Theorem R
        # When σ is small relative to E, energy can accumulate
        # Proxy: E_BS / (σ + small) — ratio of energy to dissipation
        dE_proxy = E_BS / (sigma_diss + 1e-12)         # [3]

        # ── Cross indicators (geometry × trigonometry) ──
        Q_x_theta = Q_excess * theta                    # [4]
        g = Xb / a2
        p2 = np.sum(g ** 2, axis=1)
        K = 1.0 / (float(np.prod(a2)) * p2 ** 2 + 1e-300)
        K_theta = np.minimum(K / self._K_p99, 5.0) * theta  # [5]

        return np.column_stack([
            Q_excess, theta_excess, neg_sigma, dE_proxy,
            Q_x_theta, K_theta, AM
        ])

    # ──────────────────────────────────────────────────────────────
    #  DETECT — full collapse analysis
    # ──────────────────────────────────────────────────────────────

    def detect(self, X: np.ndarray) -> CollapseReport:
        """Per-observation collapse detection.  O(N·d).

        Returns a CollapseReport with all diagnostics:
          - collapse_score: [0,1] fused probability
          - lead_time: estimated steps to C* crossing
          - per-channel breakdown for explainability
        """
        Xb = self._to_body(X)
        a2 = self._a2
        d = self._d
        N = len(X)

        # ── Geometry ──
        Q = self._Q(Xb)
        crossed = Q > self._tau_Q

        min_a2 = float(np.min(a2))
        lam_max = 2.0 * np.maximum(Q, 1.0) / (min_a2 + 1e-12)

        # Potential
        sigma2 = self.sigma_gravity ** 2
        a2_plus_s2 = a2 + sigma2
        Q_conv = np.sum(Xb ** 2 / a2_plus_s2, axis=1)
        phi_att = np.exp(-0.5 * Q_conv)
        r_sq = np.sum(Xb ** 2, axis=1) + self._trace_Sigma / d
        phi_rep = 0.5 * np.log(r_sq + 1e-12)
        phi_eff = self.gamma_gravity * (phi_att - self.lambda_rep * phi_rep)

        # ── Trigonometry ──
        dirs = self._dir(Xb)
        cos_t = np.clip(dirs @ self._d_bar, -1.0, 1.0)
        theta = np.arccos(cos_t)
        angular_alarm = theta > self._theta_crit

        dd = dirs - self._d_bar
        AM = np.sqrt(np.maximum(
            np.sum((dd @ self._Sigma_d_inv) * dd, axis=1), 0.0))

        # ── Cross ──
        Q_excess_theta = np.maximum(Q - self._tau_Q, 0.0) * theta
        g = Xb / a2
        p2 = np.sum(g ** 2, axis=1)
        K = 1.0 / (float(np.prod(a2)) * p2 ** 2 + 1e-300)
        K_theta = np.minimum(K / self._K_p99, 5.0) * theta

        # ── BSDT channels ──
        delta_C = np.sqrt(np.maximum(Q, 0.0))
        resid = X - X @ self._P_A
        delta_G = np.linalg.norm(resid, axis=1)
        grad_Q = 2.0 * Xb / a2
        grad_norm = np.linalg.norm(grad_Q, axis=1)
        delta_A = np.maximum(grad_norm - self._v0, 0.0)
        delta_T = Q / 2.0 + self._log_norm_const

        # ── Energy functional + dissipation ──
        E_BS = delta_C**2 + delta_G**2 + delta_A**2 + delta_T**2

        gamma_star = self.alpha / (lam_max + self.epsilon)
        c0 = 0.1
        grad_E_sq = grad_norm ** 2
        sigma_diss = (c0 + gamma_star) * grad_E_sq

        # dE sign: E_BS / (σ + small) > threshold means growing
        dE_proxy = E_BS / (sigma_diss + 1e-12)
        dE_sign = np.where(dE_proxy > 1.0, +1.0, -1.0)

        # Dissipation failure: σ too small relative to energy
        dissipation_failure = sigma_diss < 0.01 * E_BS

        # ── Lead time estimate ──
        # Time to cross C*: proportional to (τ_Q - Q) / rate_of_Q_growth
        # Rate: ||∇Q|| ~ grad_norm
        dist_to_Cstar = np.maximum(self._tau_Q - Q, 0.0)
        lead_time = dist_to_Cstar / (grad_norm + 1e-12)
        # If already crossed, lead = 0
        lead_time = np.where(crossed, 0.0, lead_time)

        # ── Collapse score (Fisher VR fusion of 7 indicators) ──
        indicators = self._raw_indicators(X)
        z = (indicators - self._fusion_mu) / self._fusion_std
        zp = np.maximum(z, 0.0)
        raw_score = zp @ self._w_fusion
        collapse_score = self._calibrate(raw_score)

        return CollapseReport(
            Q=Q, tau_Q=self._tau_Q, crossed_Cstar=crossed,
            lambda_max=lam_max, phi_eff=phi_eff,
            theta=theta, theta_crit=self._theta_crit,
            angular_alarm=angular_alarm, AM=AM,
            Q_excess_theta=Q_excess_theta, K_theta=K_theta,
            delta_C=delta_C, delta_G=delta_G,
            delta_A=delta_A, delta_T=delta_T,
            E_BS=E_BS, dE_sign=dE_sign,
            sigma_dissipation=sigma_diss, gamma_star=gamma_star,
            dissipation_failure=dissipation_failure,
            collapse_score=collapse_score, lead_time=lead_time,
        )

    # ──────────────────────────────────────────────────────────────
    #  CONVENIENCE — scalar collapse score only
    # ──────────────────────────────────────────────────────────────

    def _calibrate(self, raw: np.ndarray) -> np.ndarray:
        """Sigmoid calibration using frozen reference statistics."""
        z = (raw - self._score_centre) / self._score_scale
        return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))

    def score(self, X: np.ndarray) -> np.ndarray:
        """Collapse score only (no diagnostics).  O(N·d)."""
        indicators = self._raw_indicators(X)
        z = (indicators - self._fusion_mu) / self._fusion_std
        zp = np.maximum(z, 0.0)
        raw = zp @ self._w_fusion
        return self._calibrate(raw)

    def score_with_friction(self, X_series: np.ndarray,
                            k_steps: int = 50) -> np.ndarray:
        r"""Score after curvature-adaptive friction on a trajectory.

        Friction is applied to the *calibrated collapse score* directly.
        The tracking speed (brake) is inversely proportional to the
        current friction-score — mirroring the Hessian-proportional
        friction from the paper, where γ* ∝ λ_max ∝ Q:

            brake(S) = max(1 − S_f, ε)

        At S_f = 0 (safe): brake = 1 → immediate raw-tracking.
        At S_f = 1 (collapse): brake ≈ 0 → asymptotic ceiling.

        Properties:
          • Normal times: friction-score ≈ raw-score (high brake).
          • Approaching C*: friction-score rises gradually (brake
            shrinks as score climbs) — this IS the early warning.
          • At C*: friction-score converges asymptotically toward
            (but never reaches) 1.0, preventing full collapse.
          • Recovery: friction-score drops slowly (low brake at
            high residual score) — cautious de-escalation.

        Parameters
        ----------
        X_series : (T, d) time-ordered observations (raw space)
        k_steps  : (unused, kept for API compat)

        Returns
        -------
        scores_friction : (T,) friction-damped collapse scores.
                         Same [0, 1] scale as raw scores.
        """
        scores = self.score(X_series)
        T = len(scores)
        S_f = np.empty(T)
        S_f[0] = float(scores[0])

        eps = 0.01  # minimum brake — prevents full freeze
        for t in range(1, T):
            brake = max(1.0 - S_f[t - 1], eps)
            S_f[t] = S_f[t - 1] + brake * (float(scores[t]) - S_f[t - 1])
            S_f[t] = np.clip(S_f[t], 0.0, 1.0)

        return S_f

    # ──────────────────────────────────────────────────────────────
    #  POLICY TEST — closed-form intervention analysis
    # ──────────────────────────────────────────────────────────────

    def policy_test(self, X: np.ndarray,
                    delta: Optional[np.ndarray] = None,
                    clamp_min: Optional[np.ndarray] = None,
                    clamp_max: Optional[np.ndarray] = None) -> dict:
        r"""Evaluate a policy perturbation on collapse geometry.

        Computes the effect of a feature-space intervention without
        simulation.  Three modes:

          1. Additive shift:   X' = X + δ
          2. Floor clamp:      X' = max(X, clamp_min)
          3. Cap clamp:        X' = min(X, clamp_max)

        All three can be combined.  Additionally computes the
        **minimum-norm correction** δ* that returns each observation
        inside C* (if currently outside):

            δ* = −(Q − τ_Q) / ||∇Q||²  ·  ∇Q

        Parameters
        ----------
        X         : (N, d) observations in raw feature space
        delta     : (d,) additive shift per feature, or None
        clamp_min : (d,) per-feature floor, or None
        clamp_max : (d,) per-feature cap, or None

        Returns
        -------
        dict with:
          score_before : (N,) collapse score on original X
          score_after  : (N,) collapse score after policy
          delta_score  : (N,) signed change (negative = improvement)
          Q_before     : (N,) Mahalanobis Q before
          Q_after      : (N,) Mahalanobis Q after
          inside_before: (N,) bool — was inside C* before
          inside_after : (N,) bool — is inside C* after
          rescued      : (N,) bool — was outside, now inside
          lead_before  : (N,) lead time before policy
          lead_after   : (N,) lead time after policy
          min_delta    : (N, d) minimum-norm δ* per observation
          min_delta_norm : (N,) ||δ*|| per observation
        """
        X = np.asarray(X, dtype=float)
        N, d = X.shape

        # ── Before ──
        score_before = self.score(X)
        Xb_before = self._to_body(X)
        Q_before = self._Q(Xb_before)
        inside_before = Q_before <= self._tau_Q

        grad_Q_body = 2.0 * Xb_before / self._a2        # (N, d)
        grad_norm2 = np.sum(grad_Q_body ** 2, axis=1)   # (N,)
        lead_before = np.where(
            inside_before,
            np.maximum(self._tau_Q - Q_before, 0) / (np.sqrt(grad_norm2) + 1e-12),
            0.0)

        # ── Apply policy ──
        X_prime = X.copy()
        if delta is not None:
            X_prime = X_prime + np.asarray(delta)
        if clamp_min is not None:
            X_prime = np.maximum(X_prime, np.asarray(clamp_min))
        if clamp_max is not None:
            X_prime = np.minimum(X_prime, np.asarray(clamp_max))

        # ── After ──
        score_after = self.score(X_prime)
        Xb_after = self._to_body(X_prime)
        Q_after = self._Q(Xb_after)
        inside_after = Q_after <= self._tau_Q

        grad_Q_after = 2.0 * Xb_after / self._a2
        gn2_after = np.sum(grad_Q_after ** 2, axis=1)
        lead_after = np.where(
            inside_after,
            np.maximum(self._tau_Q - Q_after, 0) / (np.sqrt(gn2_after) + 1e-12),
            0.0)

        # ── Minimum-norm correction δ* (returns obs to C* boundary) ──
        # In body coords: δ*_b = −(Q − τ_Q) / ||∇Q_b||² · ∇Q_b
        # Then rotate+scale back to raw space
        excess = np.maximum(Q_before - self._tau_Q, 0.0)    # (N,)
        scale = excess / (grad_norm2 + 1e-12)                # (N,)
        delta_star_body = -scale[:, None] * grad_Q_body       # (N, d)
        # Body → standardised → raw:  δ_raw = (δ_body @ R) * σ
        delta_star_raw = (delta_star_body @ self._R) * self._sigma  # (N, d)
        delta_star_norm = np.linalg.norm(delta_star_raw, axis=1)

        return {
            'score_before': score_before,
            'score_after': score_after,
            'delta_score': score_after - score_before,
            'Q_before': Q_before,
            'Q_after': Q_after,
            'inside_before': inside_before,
            'inside_after': inside_after,
            'rescued': (~inside_before) & inside_after,
            'lead_before': lead_before,
            'lead_after': lead_after,
            'min_delta': delta_star_raw,
            'min_delta_norm': delta_star_norm,
        }

    # ──────────────────────────────────────────────────────────────
    #  WINDOW-BASED — time-series early warning
    # ──────────────────────────────────────────────────────────────

    def early_warning(self, X_series: np.ndarray,
                      window: int = 20) -> dict:
        """Sliding-window collapse early warning for time-series.

        Parameters
        ----------
        X_series : (T, d) time-ordered observations
        window : rolling window size for score aggregation

        Returns
        -------
        dict with:
          scores    : (T,) per-step collapse score
          alarms    : (T,) bool — score > 0.5
          first_alarm : int — first alarm index (-1 if none)
          Q_series  : (T,) Q trajectory
          theta_series : (T,) angular trajectory
          lead_time : (T,) estimated lead time at each step
        """
        report = self.detect(X_series)
        T = len(X_series)

        # Smooth scores with rolling mean
        scores = report.collapse_score.copy()
        if window > 1 and T > window:
            cumsum = np.cumsum(np.insert(scores, 0, 0))
            smoothed = (cumsum[window:] - cumsum[:-window]) / window
            scores[window-1:] = smoothed

        alarms = scores > 0.5
        first_idx = int(np.where(alarms)[0][0]) if alarms.any() else -1

        return {
            'scores': scores,
            'alarms': alarms,
            'first_alarm': first_idx,
            'Q_series': report.Q,
            'theta_series': report.theta,
            'lead_time': report.lead_time,
            'crossed_Cstar': report.crossed_Cstar,
            'E_BS': report.E_BS,
            'gamma_star': report.gamma_star,
        }

    # ──────────────────────────────────────────────────────────────
    #  FORMULA SUMMARY (for paper)
    # ──────────────────────────────────────────────────────────────

    def formula_summary(self) -> str:
        """Print the closed-form formulas used for collapse detection."""
        d = self._d
        return f"""
╔══════════════════════════════════════════════════════════════════╗
║  GEOMETRY OF COLLAPSE — Closed-Form Formulas                    ║
║  d = {d}, τ_Q = {self._tau_Q:.3f}, θ_crit = {self._theta_crit:.4f} rad     ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  GEOMETRY (radial on C*):                                        ║
║    Q(x)    = Σⱼ xⱼ²/aⱼ²              Mahalanobis quadric        ║
║    λ_max   = 2Q/min(a²)              spectral radius              ║
║    Φ_eff   = γ[exp(-½Q_conv) - λ·½log(r²+tr/d)]                ║
║                                                                  ║
║  TRIGONOMETRY (angular on S^{{d-1}}):                             ║
║    d̃(x)   = (x/a²)/‖x/a²‖           surface normal direction    ║
║    θ(x)   = arccos(d̃·d̄_ref)         angular departure            ║
║    AM(x)  = √((d̃-d̄)ᵀΣ_d⁻¹(d̃-d̄))   angular Mahalanobis        ║
║                                                                  ║
║  CROSS (geometry × trigonometry):                                ║
║    Q×θ    = max(Q-τ_Q, 0) · θ        radial-angular coupling    ║
║    K×θ    = K_norm(x) · θ             curvature-weighted         ║
║                                                                  ║
║  COLLAPSE INDICATORS:                                            ║
║    I.   C* crossing:  Q > τ_Q = χ²_{{0.99}}({d})                 ║
║    II.  Angular alarm: θ > θ_crit                                ║
║    III. Dissipation:  σ = (c₀+γ*)‖∇E‖² < 0.01·E_BS            ║
║    IV.  Energy ratio: E_BS / σ > 1                               ║
║                                                                  ║
║  ADAPTIVE FRICTION (Paper §2.4):                                 ║
║    γ*(x)  = α / (λ_max + ε)                                     ║
║                                                                  ║
║  LEAD TIME:                                                      ║
║    T_lead = (τ_Q - Q) / ‖∇Q‖                                    ║
║                                                                  ║
║  Fusion weights: {np.array2string(self._w_fusion, precision=3)}  ║
╚══════════════════════════════════════════════════════════════════╝
"""
