"""
geometric_predictor.py
======================
Predict BSDT detection metrics for ANY new data using only
ellipsoid trigonometry on C*.  No model training, no eigendecomposition,
no pipeline.  Takes raw channel deviations -> instant predictions.

Usage
-----
    from geometric_predictor import GeometricPredictor

    # Define your domain's Fisher VR weights (sum to 1 approximately)
    pred = GeometricPredictor(weights=[0.15, 0.30, 0.55], alpha=0.30)

    # New data: each row is (delta_C, delta_G, delta_A) for one observation
    import numpy as np
    X_new = np.array([
        [1.1, 0.3, 0.1],   # observation 1
        [0.2, 0.9, 0.5],   # observation 2
        [0.0, 0.1, 0.7],   # observation 3
    ])
    results = pred.predict(X_new)
    print(results)

Author: Odeyemi Olusegun Israel
"""

from __future__ import annotations
import numpy as np
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..', 'udl'))
from udl.ellipsoid_geometry import EllipsoidGeometry


class GeometricPredictor:
    """
    Single-call prediction engine based on C* ellipsoid geometry.

    Given Fisher VR weights for a domain, constructs C* and provides
    instant closed-form predictions for every new observation.

    Parameters
    ----------
    weights : array-like of shape (K,)
        Fisher VR weights for each BSDT channel (delta_C, delta_G, delta_A, ...).
    alpha : float
        Spectral threshold.  Default 0.30.
    """

    def __init__(self, weights, alpha: float = 0.30):
        self.weights = np.asarray(weights, dtype=float)
        self.alpha = float(alpha)
        self.ell = EllipsoidGeometry.from_fisher_weights(self.weights, alpha=self.alpha)
        self.a = self.ell.semi_axes
        self.K_min = self.ell.gaussian_curvature(
            self.ell.semi_axes[0:1].reshape(1, -1)  # Camouflage pole
            * np.eye(1, self.ell.d, 0))[0]
        self.K_max = self.ell.gaussian_curvature(
            np.eye(1, self.ell.d, self.ell.d-1)     # Activity pole
            * self.ell.semi_axes[-1])[0]

        # Threshold correction LUT: N(phi) = a / sqrt(1 - e2^2 * sin^2(phi))
        self._e2_sq = float(1.0 - (self.a[-1] / self.a[0])**2)

    # ─────────────────────────────────────────────────────────
    #  Main prediction call
    # ─────────────────────────────────────────────────────────

    def predict(self, X: np.ndarray, verbose: bool = True) -> dict:
        """
        Predict detection metrics for N new observations.

        Parameters
        ----------
        X : ndarray of shape (N, d)
            Each row is one observation's BSDT channel deviations
            (delta_C, delta_G, delta_A, ...).
        verbose : bool
            Print a formatted results table.

        Returns
        -------
        results : dict with keys:
            'Q'              : Mahalanobis quadric value (1 = on C*)
            'status'         : 'SAFE' | 'BOUNDARY' | 'ALARM'
            'K'              : Gaussian curvature at nearest surface point
            'alarm_score'    : Detection power  0..1 (proportional to K)
            'evasion_energy' : Energy required to escape detection
            'threshold_mult' : Threshold correction multiplier N(phi)/a
            'geodetic_lat'   : Geodetic latitude phi (degrees)
            'geodetic_lon'   : Geodetic longitude lambda (degrees)
            'surface_pt'     : Nearest point on C* surface
        """
        X = np.atleast_2d(np.asarray(X, dtype=float))
        N = len(X)

        # ── Step 1: Quadric value Q(x) ───────────────────────
        Q = self.ell.quadric_value(X)

        # ── Step 2: Classification ───────────────────────────
        status = np.where(Q < 0.95, 'SAFE',
                 np.where(Q > 1.05, 'ALARM', 'BOUNDARY'))

        # ── Step 3: Project to surface ───────────────────────
        surf = self.ell.project_to_surface(X)

        # ── Step 4: Gaussian curvature at surface point ──────
        K = self.ell.gaussian_curvature(surf)

        # ── Step 5: Alarm score (normalised K) ───────────────
        alarm_score = np.clip(K / (self.K_max + 1e-300), 0.0, 1.0)

        # ── Step 6: Evasion energy E = 1 / ||grad Q|| ────────
        a2 = self.ell.semi_axes ** 2
        a4_inv = 1.0 / (a2 ** 2 + 1e-300)
        pts_body = surf - self.ell.centre
        grad_norm = 2.0 * np.sqrt(np.sum(pts_body ** 2 * a4_inv, axis=1))
        evasion_energy = 1.0 / (grad_norm + 1e-300)

        # ── Step 7: Geodetic coordinates + N(phi) ────────────
        if self.ell.d == 3:
            phi, lam, h = self.ell.to_ellipsoidal_coords(surf)
        else:
            phi = np.zeros(N)
            lam = np.zeros(N)

        N_phi = self.a[0] / np.sqrt(
            1.0 - self._e2_sq * np.sin(phi) ** 2 + 1e-300)
        threshold_mult = N_phi / self.a[0]

        results = {
            'Q':              Q,
            'status':         status,
            'K':              K,
            'alarm_score':    alarm_score,
            'evasion_energy': evasion_energy,
            'threshold_mult': threshold_mult,
            'geodetic_lat':   np.degrees(phi),
            'geodetic_lon':   np.degrees(lam),
            'surface_pt':     surf,
        }

        if verbose:
            self._print_table(X, results)

        return results

    # ─────────────────────────────────────────────────────────
    #  Domain onboarding: given 3 weights, get instant profile
    # ─────────────────────────────────────────────────────────

    def onboard_domain(self, weights_new, alpha_new=None, name='NewDomain') -> dict:
        """
        Instantly profile a new domain given only its Fisher VR weights.
        No data needed.  Returns detection difficulty ranking and
        comparison to existing domains.

        Parameters
        ----------
        weights_new : array-like of shape (K,)
        alpha_new   : float or None (uses self.alpha if None)
        name        : str label for reporting

        Returns
        -------
        profile : dict with keys:
            'semi_axes', 'K_pole', 'K_equator', 'condition_number',
            'flattening', 'threshold_mult_90deg', 'alarm_rank',
            'detection_difficulty', 'closest_domain'
        """
        if alpha_new is None:
            alpha_new = self.alpha
        w = np.asarray(weights_new, dtype=float)
        new_ell = EllipsoidGeometry.from_fisher_weights(w, alpha=alpha_new)
        a = new_ell.semi_axes

        K_pole_activity = new_ell.gaussian_curvature(
            np.eye(1, new_ell.d, new_ell.d-1) * a[-1])[0]
        K_pole_camouflage = new_ell.gaussian_curvature(
            np.eye(1, new_ell.d, 0) * a[0])[0]

        e2_sq = 1.0 - (a[-1] / a[0]) ** 2
        N_90 = a[0] / np.sqrt(1.0 - e2_sq + 1e-300)
        threshold_mult_90 = float(N_90 / a[0])

        cond = float(a[0] / (a[-1] + 1e-300))
        flat = float((a[0] - a[-1]) / (a[0] + 1e-300))

        # Difficulty: condition number drives detection asymmetry
        if cond < 1.5:
            difficulty = 'LOW (near-spherical, uniform detection)'
        elif cond < 2.5:
            difficulty = 'MEDIUM (moderate blind spot)'
        else:
            difficulty = 'HIGH (strong blind spot in heaviest channel)'

        # Alarm rank: Activity pole curvature vs self (existing domain)
        alarm_rank_vs_self = float(K_pole_activity / (self.K_max + 1e-300))

        print(f'\n=== DOMAIN PROFILE: {name} ===')
        print(f'  Weights:  {w.tolist()}')
        print(f'  Alpha:    {alpha_new}')
        print(f'  Semi-axes: {[f"{x:.4f}" for x in a]}')
        print(f'  Condition number: {cond:.4f}  ({cond:.2f}x harder at blind spot)')
        print(f'  Flattening: {flat:.4f}')
        print(f'  K at Activity pole: {K_pole_activity:.4f}  (easy-to-detect direction)')
        print(f'  K at Camouflage pole: {K_pole_camouflage:.6f}  (blind-spot direction)')
        print(f'  K ratio (max/min): {K_pole_activity/(K_pole_camouflage+1e-300):.1f}x')
        print(f'  Threshold correction at 90deg: {threshold_mult_90:.4f}x')
        print(f'  Detection difficulty: {difficulty}')
        print(f'  Alarm rate vs reference domain: {alarm_rank_vs_self:.4f}')

        return {
            'semi_axes': a.tolist(),
            'K_pole_activity': K_pole_activity,
            'K_pole_camouflage': K_pole_camouflage,
            'condition_number': cond,
            'flattening': flat,
            'threshold_mult_90deg': threshold_mult_90,
            'detection_difficulty': difficulty,
            'alarm_rank_vs_reference': alarm_rank_vs_self,
        }

    # ─────────────────────────────────────────────────────────
    #  Threshold recommendation
    # ─────────────────────────────────────────────────────────

    def recommended_threshold(self, base_threshold: float,
                               X: np.ndarray) -> np.ndarray:
        """
        Given a single global base threshold, return the geometrically
        corrected threshold for each observation based on its geodetic
        latitude on C*.

        corrected_threshold(x) = base_threshold * N(phi(x)) / a

        This replaces grid-search cross-validation for threshold tuning.
        """
        X = np.atleast_2d(np.asarray(X, dtype=float))
        surf = self.ell.project_to_surface(X)
        if self.ell.d == 3:
            phi, _, _ = self.ell.to_ellipsoidal_coords(surf)
        else:
            phi = np.zeros(len(X))
        N_phi = self.a[0] / np.sqrt(
            1.0 - self._e2_sq * np.sin(phi) ** 2 + 1e-300)
        return base_threshold * (N_phi / self.a[0])

    # ─────────────────────────────────────────────────────────
    #  Internal helpers
    # ─────────────────────────────────────────────────────────

    def _print_table(self, X, r):
        N = len(X)
        print()
        print('─' * 95)
        print(f'  {"#":>3}  {"delta_C":>8} {"delta_G":>8} {"delta_A":>8} │'
              f' {"Q":>6} {"STATUS":>9} {"K":>8} {"alarm":>7}'
              f' {"E_evade":>8} {"thr_mult":>9} {"phi(d)":>7} {"lam(d)":>7}')
        print('─' * 95)
        for i in range(N):
            ch = X[i]
            ch_str = '  '.join(f'{v:8.4f}' for v in ch[:3])
            print(f'  {i+1:>3}  {ch_str} │'
                  f' {r["Q"][i]:>6.3f} {r["status"][i]:>9}'
                  f' {r["K"][i]:>8.4f} {r["alarm_score"][i]:>7.4f}'
                  f' {r["evasion_energy"][i]:>8.4f}'
                  f' {r["threshold_mult"][i]:>9.4f}'
                  f' {r["geodetic_lat"][i]:>7.1f}'
                  f' {r["geodetic_lon"][i]:>7.1f}')
        print('─' * 95)
        print(f'  {"":3}  {"":26}    Q<0.95=SAFE  Q~1=BOUNDARY  Q>1.05=ALARM')
        print()

    def __repr__(self):
        return (f'GeometricPredictor(weights={self.weights.tolist()}, '
                f'alpha={self.alpha}, semi_axes={[f"{x:.4f}" for x in self.a]})')


# ─────────────────────────────────────────────────────────────────
#  DEMO
# ─────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    np.random.seed(42)

    print('=' * 70)
    print('  GEOMETRIC PREDICTION DEMO')
    print('  Domain: AML Fraud Detection')
    print('  Weights: w_C=0.15, w_G=0.30, w_A=0.55')
    print('=' * 70)

    pred = GeometricPredictor(weights=[0.15, 0.30, 0.55], alpha=0.30)
    print(pred)

    # ── Example 1: Manual observations ───────────────────────
    print('\n── Example 1: Known observations ──')
    X_known = np.array([
        [0.5,  0.3,  0.2],   # deep inside C* -> SAFE
        [1.1,  0.8,  0.5],   # outside C*     -> ALARM
        [1.3,  0.0,  0.0],   # near Camouflage pole -> ALARM but low K -> easy to miss
        [0.0,  0.0,  0.7],   # near Activity pole   -> outside, high K -> certain alarm
        [0.95, 0.65, 0.35],  # near boundary        -> BOUNDARY
    ])
    r = pred.predict(X_known)

    # ── Example 2: Random new data ────────────────────────────
    print('\n── Example 2: 10 random new observations ──')
    X_random = np.random.randn(10, 3) * 0.8
    r2 = pred.predict(X_random)

    # ── Example 3: Threshold recommendations ─────────────────
    print('\n── Example 3: Threshold correction for each observation ──')
    base = 0.95
    thresholds = pred.recommended_threshold(base, X_known)
    print(f'  Base threshold: {base}')
    print(f'  Corrected thresholds: {[f"{t:.4f}" for t in thresholds]}')
    print(f'  (Higher phi = tighter boundary = smaller effective threshold)')

    # ── Example 4: Onboard a completely new domain ───────────
    print('\n── Example 4: Onboard new domain (Protein Folding) ──')
    pred.onboard_domain(
        weights_new=[0.40, 0.40, 0.20],
        alpha_new=0.30,
        name='ProteinFolding'
    )

    print('\n── Example 5: Onboard very easy domain ──')
    pred.onboard_domain(
        weights_new=[0.10, 0.10, 0.80],
        alpha_new=0.30,
        name='HighActivityDomain'
    )

    print('\n── Example 6: Onboard very hard domain ──')
    pred.onboard_domain(
        weights_new=[0.70, 0.20, 0.10],
        alpha_new=0.30,
        name='HighCamouflageDomain'
    )
