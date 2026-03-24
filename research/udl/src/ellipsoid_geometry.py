"""
ellipsoid_geometry.py
=====================
Complete triaxial ellipsoid mathematics for the BSDT framework.

The critical manifold C* is the spectral boundary ellipsoid where
    sum_k w_k * delta_k^2 / alpha = 1
in the BSDT channel space.  Mahalanobis iso-distance surfaces are
concentric ellipsoids with semi-axes proportional to sqrt(lambda_i(Sigma)).

This module provides the full geometric and trigonometric toolkit for
working with these ellipsoids across all six validated domains of the
grand unification paper.

Geometry
--------
  quadric_value, contains, project_to_surface, surface_normal,
  gaussian_curvature, mean_curvature, principal_curvatures,
  eccentricities, volume, surface_area, ellipsoid_info

Trigonometry / Geodesy
----------------------
  to_ellipsoidal_coords, from_ellipsoidal_coords, parametric_angles,
  meridian_arc_length, parallel_arc_length, geodesic_distance,
  geodesic_distance_vincenty, angular_separation,
  loxodromic_distance, great_elliptic_section

BSDT Integration
----------------
  from_covariance, from_fisher_weights, from_bsdt,
  mahalanobis_contour, cross_domain_distance,
  domain_anisotropy, fisher_information_metric

Author: Odeyemi Olusegun Israel
"""

from __future__ import annotations

import numpy as np
from typing import Optional, Union


class EllipsoidGeometry:
    r"""
    Complete triaxial ellipsoid mathematics for the BSDT framework.

    The critical manifold C* is defined by the quadric

        Q(x) = sum_k ((x_k - c_k) / a_k)^2 = 1

    where c is the centre and a = [a_1, ..., a_d] are the semi-axes.

    Parameters
    ----------
    semi_axes : array-like of shape (d,)
        Semi-axis lengths, sorted largest to smallest by convention.
    centre : array-like of shape (d,) or None
        Centre of the ellipsoid.  Default is the origin.
    rotation : array-like of shape (d, d) or None
        Rotation matrix R such that x_body = R @ (x_world - c).
        Default is identity (axis-aligned).
    """

    def __init__(
        self,
        semi_axes,
        centre=None,
        rotation=None,
    ):
        self.semi_axes = np.asarray(semi_axes, dtype=np.float64)
        self.d = len(self.semi_axes)
        self.centre = (
            np.zeros(self.d, dtype=np.float64)
            if centre is None
            else np.asarray(centre, dtype=np.float64)
        )
        self.rotation = (
            np.eye(self.d, dtype=np.float64)
            if rotation is None
            else np.asarray(rotation, dtype=np.float64)
        )
        self._a2 = self.semi_axes ** 2
        self._a2_inv = 1.0 / (self._a2 + 1e-300)

    # ──────────────────────────────────────────────────────────
    #  Class-method constructors
    # ──────────────────────────────────────────────────────────

    @classmethod
    def from_covariance(cls, cov, centre=None, chi2_level: float = 1.0):
        """Construct from a covariance matrix Sigma.

        The ellipsoid is the chi2_level Mahalanobis contour:
            (x - mu)^T Sigma^{-1} (x - mu) = chi2_level.

        Semi-axes: a_k = sqrt(chi2_level * lambda_k(Sigma)).
        """
        cov = np.asarray(cov, dtype=np.float64)
        eigvals, eigvecs = np.linalg.eigh(cov)
        eigvals = np.maximum(eigvals, 1e-300)
        semi = np.sqrt(chi2_level) * np.sqrt(eigvals)
        idx = np.argsort(-semi)          # largest first
        return cls(
            semi[idx],
            centre=centre,
            rotation=eigvecs[:, idx].T,
        )

    @classmethod
    def from_fisher_weights(
        cls,
        weights,
        alpha: float = 1.0,
        centre=None,
    ):
        """Construct C* from Fisher VR channel weights.

        The critical-manifold semi-axis for channel k is
            a_k = sqrt(alpha / w_k)
        (higher weight w_k → smaller axis → tighter detection,
         lower weight w_k → larger axis → harder to detect).

        Parameters
        ----------
        weights : array-like of shape (K,)
            Fisher Variance-Ratio weights for each BSDT channel.
        alpha : float
            Spectral threshold (default 1.0).
        """
        w = np.asarray(weights, dtype=np.float64)
        semi = np.sqrt(alpha / (w + 1e-300))
        idx = np.argsort(-semi)          # largest axis first
        return cls(semi[idx], centre=centre)

    @classmethod
    def from_bsdt(cls, bsdt_channels, alpha=None):
        """Construct C* from a BSDTChannels instance.

        Reads w_C, w_G, w_A, w_S weights and the stored alpha.
        """
        w = np.array([
            bsdt_channels.w_C,
            bsdt_channels.w_G,
            bsdt_channels.w_A,
            bsdt_channels.w_S,
        ])
        if alpha is None:
            alpha = getattr(bsdt_channels, "alpha", 1.0)
        return cls.from_fisher_weights(w, alpha=alpha)

    # ──────────────────────────────────────────────────────────
    #  Core geometry
    # ──────────────────────────────────────────────────────────

    def quadric_value(self, points) -> np.ndarray:
        """Q(x) = sum_k ((x_k - c_k) / a_k)^2.

        Q < 1 → inside, Q = 1 → on surface, Q > 1 → outside.

        Parameters
        ----------
        points : array-like of shape (N, d) or (d,)

        Returns
        -------
        Q : ndarray of shape (N,)
        """
        pts = np.atleast_2d(points).astype(float) - self.centre
        if self.rotation is not None:
            pts = pts @ self.rotation.T
        return np.sum(pts ** 2 * self._a2_inv, axis=1)

    def contains(self, points, tol: float = 1e-8) -> np.ndarray:
        """True iff Q(x) <= 1 + tol (point inside or on surface)."""
        return self.quadric_value(points) <= 1.0 + tol

    def project_to_surface(
        self,
        points,
        max_iter: int = 60,
        tol: float = 1e-12,
    ) -> np.ndarray:
        """Project points onto the ellipsoid surface (nearest point).

        Uses Eberly's bisection on the Lagrange multiplier t in
            g(t) = sum_k ( a_k^2 p_k / (a_k^2 + t) )^2 / a_k^2 - 1 = 0.

        Returns
        -------
        proj : ndarray of shape (N, d)
        """
        pts_body = np.atleast_2d(points).astype(float) - self.centre
        if self.rotation is not None:
            pts_body = pts_body @ self.rotation.T

        result = np.zeros_like(pts_body)
        a2 = self._a2

        for i in range(len(pts_body)):
            p = pts_body[i]
            # Handle exactly-zero coordinates
            absap = np.abs(p) * self.semi_axes
            lo = -np.min(a2) + np.max(absap)
            hi = float(np.linalg.norm(p) * np.max(self.semi_axes) + 1.0)

            for _ in range(max_iter):
                t = 0.5 * (lo + hi)
                denom = a2 + t
                proj = a2 * p / denom
                g = np.sum(proj ** 2 * self._a2_inv) - 1.0
                if abs(g) < tol:
                    break
                if g > 0.0:
                    lo = t
                else:
                    hi = t

            result[i] = a2 * p / (a2 + t)

        # Rotate back to world frame
        if self.rotation is not None:
            result = result @ self.rotation

        return result + self.centre

    def surface_normal(self, points) -> np.ndarray:
        """Outward unit normal at surface points.

        n_k = (x_k - c_k) / a_k^2,  then normalised.

        Returns
        -------
        normals : ndarray of shape (N, d)
        """
        pts = np.atleast_2d(points).astype(float) - self.centre
        if self.rotation is not None:
            pts = pts @ self.rotation.T
        grad = 2.0 * pts * self._a2_inv               # gradient of Q
        norms = np.linalg.norm(grad, axis=1, keepdims=True)
        normals_body = grad / (norms + 1e-300)
        if self.rotation is not None:
            return normals_body @ self.rotation
        return normals_body

    def gaussian_curvature(self, points) -> np.ndarray:
        """Gaussian curvature K at surface points.

        For a triaxial ellipsoid x^2/a^2 + y^2/b^2 + z^2/c^2 = 1,
            K = (1 / a^2 b^2 c^2) / p^4
        where p = sqrt(x^2/a^4 + y^2/b^4 + z^2/c^4).

        Returns
        -------
        K : ndarray of shape (N,)
        """
        pts = np.atleast_2d(points).astype(float) - self.centre
        if self.rotation is not None:
            pts = pts @ self.rotation.T
        a2 = self._a2
        # p^2 = sum_k x_k^2 / a_k^4
        a4_inv = 1.0 / (a2 ** 2 + 1e-300)
        p2 = np.sum(pts ** 2 * a4_inv, axis=1)
        p4 = p2 ** 2
        denom = np.prod(a2) * p4                      # a^2 b^2 c^2 p^4
        return 1.0 / (denom + 1e-300)

    def mean_curvature(self, points) -> np.ndarray:
        """Mean curvature H = (kappa_1 + kappa_2) / 2 at surface points.

        Uses the closed-form expression for triaxial ellipsoids.

        Returns
        -------
        H : ndarray of shape (N,)
        """
        pts = np.atleast_2d(points).astype(float) - self.centre
        if self.rotation is not None:
            pts = pts @ self.rotation.T
        a2 = self._a2
        a4 = a2 ** 2
        a4_inv = 1.0 / (a4 + 1e-300)
        a6_inv = 1.0 / (a4 * a2 + 1e-300)

        # p = sqrt(sum x_k^2 / a_k^4)
        p2 = np.sum(pts ** 2 * a4_inv, axis=1)
        p = np.sqrt(p2 + 1e-300)

        # Trace term = sum_k (1/a_k^2) * (p^2 - x_k^2/a_k^4) / (a_k^2 p^2)
        # Simplified to numerically stable form:
        #   H = (1 / (2 p^3)) * sum_k (x_k^2 / a_k^4) * (1/a_k^2)
        #       + correction (cross terms vanish on axis-aligned)
        # Standard result (Kühnel):
        #   H = (a1 a2 / (2 p^3)) * [term involving a1, a2, a3]
        # Numerically:  H = 0.5 * |grad Q|^{-3} * Laplacian(Q) restricted to surface

        # Full formula (do Carmo / Goldman 2005):
        #   H = - 1 / (2 p^3 * abc) * [
        #         x^2(b^2+c^2)/(a^4) + y^2(a^2+c^2)/(b^4) + z^2(a^2+b^2)/(c^4)
        #       ] / (abc)    [only valid for 3D]
        if self.d == 3:
            a2x, a2y, a2z = a2[0], a2[1], a2[2]
            x, y, z = pts[:, 0], pts[:, 1], pts[:, 2]
            numer = (
                x**2 * (a2y + a2z) / (a2x**2)
                + y**2 * (a2x + a2z) / (a2y**2)
                + z**2 * (a2x + a2y) / (a2z**2)
            )
            abc = float(np.prod(self.semi_axes))
            H = numer / (2.0 * (p ** 3) * abc + 1e-300)
        else:
            # General d: use average of principal curvatures approximation
            K = self.gaussian_curvature(points)
            # H ≈ sqrt(K) for near-spherical; refine if needed
            H = np.sqrt(np.abs(K) + 1e-300)
        return H

    def principal_curvatures(self, points):
        """Principal curvatures (kappa_1, kappa_2) at 3-D surface points.

        Only implemented for d=3.

        Returns
        -------
        kappa1, kappa2 : ndarray of shape (N,), kappa1 >= kappa2
        """
        if self.d != 3:
            raise NotImplementedError("principal_curvatures only for d=3")
        K = self.gaussian_curvature(points)
        H = self.mean_curvature(points)
        discriminant = np.maximum(H**2 - K, 0.0)
        sqrt_disc = np.sqrt(discriminant)
        return H + sqrt_disc, H - sqrt_disc         # kappa1, kappa2

    def volume(self) -> float:
        """Volume of the d-dimensional ellipsoid.

        V = (pi^{d/2} / Gamma(d/2 + 1)) * prod(a_k)
        """
        from math import gamma, pi
        d = self.d
        prefactor = pi ** (d / 2.0) / gamma(d / 2.0 + 1.0)
        return prefactor * float(np.prod(self.semi_axes))

    def surface_area(self) -> float:
        """Surface area of the ellipsoid.

        d=3: exact via Legendre elliptic integrals.
        d!=3: Knud Thomsen approximation (relative error < 1.06%).
        """
        if self.d == 3:
            return self._surface_area_3d()
        else:
            return self._surface_area_thomsen()

    def _surface_area_3d(self) -> float:
        """Exact surface area for triaxial ellipsoid using elliptic integrals."""
        from scipy.special import ellipkinc, ellipeinc
        a, b, c = float(self.semi_axes[0]), float(self.semi_axes[1]), float(self.semi_axes[2])
        # Ensure a >= b >= c
        vals = sorted([a, b, c], reverse=True)
        a, b, c = vals[0], vals[1], vals[2]

        if abs(a - b) < 1e-10 and abs(b - c) < 1e-10:
            # Sphere
            return 4.0 * np.pi * a**2

        if abs(a - b) < 1e-10:
            # Oblate spheroid (a = b > c)
            e = np.sqrt(1.0 - (c/a)**2)
            return 2.0 * np.pi * a**2 * (1.0 + (c**2 / (a**2 * e)) * np.arctanh(e))

        if abs(b - c) < 1e-10:
            # Prolate spheroid (a > b = c)
            e = np.sqrt(1.0 - (b/a)**2)
            return 2.0 * np.pi * b**2 * (1.0 + (a / (b * e)) * np.arcsin(e))

        # General triaxial ellipsoid
        phi = np.arccos(c / a)
        k2 = (a**2 * (b**2 - c**2)) / (b**2 * (a**2 - c**2) + 1e-300)
        k = np.sqrt(np.clip(k2, 0, 1))
        sin_phi = np.sin(phi)

        F_val = ellipkinc(phi, k2)
        E_val = ellipeinc(phi, k2)

        S = (2.0 * np.pi * c**2
             + 2.0 * np.pi * a * b
             * (E_val * sin_phi**2 + F_val * np.cos(phi)**2)
             / (sin_phi + 1e-300))
        return float(S)

    def _surface_area_thomsen(self) -> float:
        """Knud Thomsen approximation for d-dim ellipsoid surface area."""
        p = 1.6075
        a = self.semi_axes
        n = self.d
        product_ap = float(np.sum(a ** p) / n)
        return (4.0 * np.pi * (
            (np.prod(a ** (2.0 / n)) * product_ap) ** (1.0 / (2.0 / n + 1.0))
        ))

    def eccentricities(self) -> dict:
        """Eccentricity measures for the triaxial or general ellipsoid.

        Returns
        -------
        dict with keys:
            e1, e2, e3 : primary, secondary, tertiary eccentricities
            flattening  : (a - c) / a
            anisotropy  : (lambda_max - lambda_min) / lambda_max
            axis_ratios : [a/a, a/b, a/c] normalised ratios
            condition_number : max_axis / min_axis
        """
        a = self.semi_axes
        a_max, a_min = float(a.max()), float(a.min())
        a_mid = float(np.sort(a)[len(a) // 2])

        e1 = float(np.sqrt(1.0 - (a_mid / a_max) ** 2)) if a_max > 0 else 0.0
        e2 = float(np.sqrt(1.0 - (a_min / a_max) ** 2)) if a_max > 0 else 0.0
        e3 = float(np.sqrt(1.0 - (a_min / a_mid) ** 2)) if a_mid > 0 else 0.0
        flattening = float((a_max - a_min) / (a_max + 1e-300))
        anisotropy = float((a_max - a_min) / (a_max + 1e-300))
        axis_ratios = [float(a_max / (v + 1e-300)) for v in a]

        return {
            "e1": e1,
            "e2": e2,
            "e3": e3,
            "flattening": flattening,
            "anisotropy": anisotropy,
            "axis_ratios": axis_ratios,
            "condition_number": float(a_max / (a_min + 1e-300)),
        }

    # ──────────────────────────────────────────────────────────
    #  Ellipsoidal / geodetic trigonometry
    # ──────────────────────────────────────────────────────────

    def to_ellipsoidal_coords(self, points) -> tuple:
        """Convert Cartesian points to ellipsoidal (geodetic) coordinates.

        Returns (phi, lam, h) for 3-D ellipsoids:
            phi : geodetic latitude  (radians, -pi/2 to pi/2)
            lam : longitude          (radians, -pi to pi)
            h   : altitude above the surface

        Uses iterative Bowring / Vermeille conversion.

        Parameters
        ----------
        points : array-like of shape (N, 3)

        Returns
        -------
        phi, lam, h : ndarrays of shape (N,)
        """
        if self.d != 3:
            raise NotImplementedError("to_ellipsoidal_coords requires d=3")
        pts = np.atleast_2d(points).astype(float) - self.centre
        x, y, z = pts[:, 0], pts[:, 1], pts[:, 2]
        a, b, c = self.semi_axes[0], self.semi_axes[1], self.semi_axes[2]

        lam = np.arctan2(y, x)
        rho = np.sqrt(x**2 + y**2)
        phi = np.arctan2(z, rho * (1.0 - (a**2 - c**2) / (a**2 + 1e-300)))

        # Iterative Bowring refinement (5 iterations)
        for _ in range(5):
            sin_phi = np.sin(phi)
            cos_phi = np.cos(phi)
            N = a / np.sqrt(1.0 - (a**2 - c**2) / a**2 * sin_phi**2 + 1e-300)
            phi = np.arctan2(z + (a**2 - c**2) / a**2 * N * sin_phi,
                             rho)

        sin_phi = np.sin(phi)
        cos_phi = np.cos(phi)
        N_phi = a / np.sqrt(1.0 - (a**2 - c**2) / a**2 * sin_phi**2 + 1e-300)
        h = rho * cos_phi + z * sin_phi - N_phi * (1.0 - (a**2 - c**2) / a**2 * sin_phi**2)
        return phi, lam, h

    def from_ellipsoidal_coords(self, phi, lam, h=0.0) -> np.ndarray:
        """Convert ellipsoidal (geodetic) coordinates to Cartesian.

        Parameters
        ----------
        phi, lam : float or ndarray
            Geodetic latitude and longitude (radians).
        h : float or ndarray
            Altitude above the ellipsoid surface.

        Returns
        -------
        points : ndarray of shape (N, 3)
        """
        if self.d != 3:
            raise NotImplementedError("from_ellipsoidal_coords requires d=3")
        phi = np.asarray(phi, dtype=float)
        lam = np.asarray(lam, dtype=float)
        h = np.asarray(h, dtype=float) * np.ones_like(phi)
        a, b, c = self.semi_axes[0], self.semi_axes[1], self.semi_axes[2]
        e2 = 1.0 - (c / a) ** 2
        N = a / np.sqrt(1.0 - e2 * np.sin(phi) ** 2 + 1e-300)
        x = (N + h) * np.cos(phi) * np.cos(lam)
        y = (N + h) * np.cos(phi) * np.sin(lam)
        z = (N * (1.0 - e2) + h) * np.sin(phi)
        return np.column_stack([x, y, z]) + self.centre

    def parametric_angles(self, points) -> tuple:
        """Compute reduced (parametric) latitude beta and longitude lam.

        The parametric latitude beta is related to geodetic phi by
            tan(beta) = (c/a) tan(phi).

        Returns
        -------
        beta, lam : ndarrays of shape (N,)
        """
        if self.d != 3:
            raise NotImplementedError("parametric_angles requires d=3")
        pts = np.atleast_2d(points).astype(float) - self.centre
        a, b, c = self.semi_axes[0], self.semi_axes[1], self.semi_axes[2]
        x, y, z = pts[:, 0], pts[:, 1], pts[:, 2]
        beta = np.arctan2(z / (c + 1e-300), np.sqrt(x**2 + y**2) / (a + 1e-300))
        lam = np.arctan2(y, x)
        return beta, lam

    def meridian_arc_length(self, phi1: float, phi2: float,
                             lam: float = 0.0,
                             n_points: int = 500) -> float:
        """Numerical arc length along a meridian from phi1 to phi2.

        Integrates ds = sqrt(dx^2 + dy^2 + dz^2) along the line lam=const.
        """
        if self.d != 3:
            raise NotImplementedError("meridian_arc_length requires d=3")
        phi = np.linspace(phi1, phi2, n_points + 1)
        pts = self.from_ellipsoidal_coords(phi, lam * np.ones_like(phi))
        return float(np.sum(np.linalg.norm(np.diff(pts, axis=0), axis=1)))

    def parallel_arc_length(self, lam1: float, lam2: float,
                             phi: float = 0.0,
                             n_points: int = 500) -> float:
        """Numerical arc length along a parallel (constant phi)."""
        if self.d != 3:
            raise NotImplementedError("parallel_arc_length requires d=3")
        lam = np.linspace(lam1, lam2, n_points + 1)
        pts = self.from_ellipsoidal_coords(phi * np.ones_like(lam), lam)
        return float(np.sum(np.linalg.norm(np.diff(pts, axis=0), axis=1)))

    def geodesic_distance(self, p1, p2, n_interp: int = 200) -> float:
        """Approximate geodesic distance along the ellipsoid surface.

        Uses the projected path: interpolate linearly in 3-space then
        project each point onto the surface, and sum chord lengths.
        This gives a very close approximation for smooth ellipsoids.
        """
        p1 = np.asarray(p1, dtype=float).ravel()
        p2 = np.asarray(p2, dtype=float).ravel()
        t = np.linspace(0.0, 1.0, n_interp + 1)
        # Build the path by interpolating and projecting
        path = np.outer(1.0 - t, p1) + np.outer(t, p2)
        proj = self.project_to_surface(path)
        return float(np.sum(np.linalg.norm(np.diff(proj, axis=0), axis=1)))

    def geodesic_distance_vincenty(self, phi1: float, lam1: float,
                                    phi2: float, lam2: float,
                                    max_iter: int = 200,
                                    tol: float = 1e-12) -> float:
        """Geodesic distance via the Vincenty formula (oblate spheroid).

        Strictly valid for a=b > c (oblate spheroid).  For the triaxial
        case use geodesic_distance() instead.

        Returns
        -------
        s : float
            Geodesic distance in the same units as the semi-axes.
        """
        if self.d != 3:
            raise NotImplementedError("Vincenty requires d=3")
        a = float(self.semi_axes[0])
        c = float(self.semi_axes[2])
        f = (a - c) / (a + 1e-300)
        b_ell = a * (1.0 - f)

        U1 = np.arctan((1.0 - f) * np.tan(phi1))
        U2 = np.arctan((1.0 - f) * np.tan(phi2))
        L = lam2 - lam1

        sin_U1, cos_U1 = np.sin(U1), np.cos(U1)
        sin_U2, cos_U2 = np.sin(U2), np.cos(U2)

        lam = L
        for _ in range(max_iter):
            sin_lam, cos_lam = np.sin(lam), np.cos(lam)
            sin_sigma = np.sqrt(
                (cos_U2 * sin_lam) ** 2
                + (cos_U1 * sin_U2 - sin_U1 * cos_U2 * cos_lam) ** 2
            )
            if sin_sigma < 1e-16:
                return 0.0
            cos_sigma = sin_U1 * sin_U2 + cos_U1 * cos_U2 * cos_lam
            sigma = np.arctan2(sin_sigma, cos_sigma)

            sin_alpha = cos_U1 * cos_U2 * sin_lam / (sin_sigma + 1e-300)
            cos2_alpha = 1.0 - sin_alpha ** 2
            cos_2sigm = (cos_sigma - 2.0 * sin_U1 * sin_U2
                         / (cos2_alpha + 1e-300)) if cos2_alpha > 1e-10 else 0.0

            C = f / 16.0 * cos2_alpha * (4.0 + f * (4.0 - 3.0 * cos2_alpha))
            lam_new = L + (1.0 - C) * f * sin_alpha * (
                sigma + C * sin_sigma * (
                    cos_2sigm + C * cos_sigma * (-1.0 + 2.0 * cos_2sigm ** 2)
                )
            )
            if abs(lam_new - lam) < tol:
                lam = lam_new
                break
            lam = lam_new

        u2 = cos2_alpha * (a ** 2 - b_ell ** 2) / (b_ell ** 2 + 1e-300)
        A_v = 1.0 + u2 / 16384.0 * (4096.0 + u2 * (-768.0 + u2 * (320.0 - 175.0 * u2)))
        B_v = u2 / 1024.0 * (256.0 + u2 * (-128.0 + u2 * (74.0 - 47.0 * u2)))
        delta_sigma = B_v * sin_sigma * (
            cos_2sigm + B_v / 4.0 * (
                cos_sigma * (-1.0 + 2.0 * cos_2sigm ** 2)
                - B_v / 6.0 * cos_2sigm * (-3.0 + 4.0 * sin_sigma ** 2)
                * (-3.0 + 4.0 * cos_2sigm ** 2)
            )
        )
        return float(b_ell * A_v * (sigma - delta_sigma))

    def angular_separation(self, p1, p2) -> np.ndarray:
        """Central angle between two points as seen from the ellipsoid centre.

        Uses the spherical-law-of-cosines on the normalised directions.

        Parameters
        ----------
        p1, p2 : array-like of shape (N, d) or (d,)

        Returns
        -------
        sigma : ndarray of shape (N,) in radians
        """
        q1 = np.atleast_2d(p1).astype(float) - self.centre
        q2 = np.atleast_2d(p2).astype(float) - self.centre
        q1 /= np.linalg.norm(q1, axis=1, keepdims=True) + 1e-300
        q2 /= np.linalg.norm(q2, axis=1, keepdims=True) + 1e-300
        cos_sigma = np.clip(np.sum(q1 * q2, axis=1), -1.0, 1.0)
        return np.arccos(cos_sigma)

    def loxodromic_distance(self, phi1: float, lam1: float,
                             phi2: float, lam2: float) -> float:
        """Rhumb-line (loxodromic) distance on the oblate spheroid.

        The loxodrome is the path of constant bearing.  Uses the
        Mercator isometric latitude psi = ln(tan(pi/4 + phi/2)).
        """
        if self.d != 3:
            raise NotImplementedError("loxodromic_distance requires d=3")
        a = float(self.semi_axes[0])
        e2 = float(1.0 - (self.semi_axes[2] / a) ** 2)
        e = np.sqrt(max(e2, 0.0))

        def psi(phi):
            s = np.sin(phi)
            return (np.log(np.tan(np.pi / 4.0 + phi / 2.0))
                    - e / 2.0 * np.log((1.0 + e * s) / (1.0 - e * s + 1e-300)))

        d_phi = phi2 - phi1
        d_lam = lam2 - lam1
        d_psi = psi(phi2) - psi(phi1)
        q = d_phi / (d_psi + 1e-300) if abs(d_psi) > 1e-10 else np.cos(phi1)
        dist = a * np.sqrt(d_phi ** 2 + q ** 2 * d_lam ** 2)
        return float(dist)

    def great_elliptic_section(self, normal, n_points: int = 200) -> np.ndarray:
        """Points on the great elliptic section cut by a plane.

        The cutting plane passes through the centre with the given normal.

        Parameters
        ----------
        normal : array-like of shape (d,)
            Unit normal of the cutting plane.

        Returns
        -------
        curve : ndarray of shape (n_points + 1, d)
        """
        normal = np.asarray(normal, dtype=float)
        normal = normal / (np.linalg.norm(normal) + 1e-300)

        # Build two orthonormal vectors in the cutting plane
        # via Gram-Schmidt
        dummy = np.zeros(self.d)
        idx = np.argmin(np.abs(normal))
        dummy[idx] = 1.0
        u = dummy - np.dot(dummy, normal) * normal
        u /= np.linalg.norm(u) + 1e-300
        if self.d >= 3:
            v = np.cross(normal, u) if self.d == 3 else np.zeros(self.d)
            if self.d > 3:
                # For d > 3 just use another Gram-Schmidt direction
                dummy2 = np.zeros(self.d)
                dummy2[(idx + 1) % self.d] = 1.0
                v = dummy2 - np.dot(dummy2, normal) * normal - np.dot(dummy2, u) * u
                v /= np.linalg.norm(v) + 1e-300
        else:
            v = np.array([-u[1], u[0]])

        theta = np.linspace(0, 2 * np.pi, n_points + 1)
        # Parametric curve in the plane: p(theta) = cos(t)*u + sin(t)*v
        pts_plane = np.outer(np.cos(theta), u) + np.outer(np.sin(theta), v)
        # Scale to ellipsoid surface by projecting
        projected = self.project_to_surface(pts_plane)
        return projected + self.centre

    # ──────────────────────────────────────────────────────────
    #  BSDT integration
    # ──────────────────────────────────────────────────────────

    def mahalanobis_contour(self, r: float = 1.0) -> 'EllipsoidGeometry':
        """Return the Mahalanobis contour ellipsoid at radius r.

        The surface {x : Q(x) = r^2} has semi-axes = r * self.semi_axes.
        """
        return EllipsoidGeometry(
            r * self.semi_axes,
            centre=self.centre,
            rotation=self.rotation,
        )

    def cross_domain_distance(self, other: 'EllipsoidGeometry') -> float:
        """Euclidean distance between centres of two ellipsoids.

        Useful for measuring how far two domain critical manifolds are
        from each other in the BSDT channel space.
        """
        return float(np.linalg.norm(self.centre - other.centre))

    def domain_anisotropy(self) -> dict:
        """Anisotropy measures relevant to BSDT domain characterisation.

        Returns
        -------
        dict with:
            condition_number      : a_max / a_min
            prolate_index         : (a_max - a_mid) / (a_max - a_min + eps)
            oblate_index          : (a_mid - a_min) / (a_max - a_min + eps)
            detection_sensitivity : sum of 1/a_k (harder channels are weighted more)
        """
        a = self.semi_axes
        a_max = float(a.max())
        a_min = float(a.min())
        a_mid = float(np.sort(a)[len(a) // 2])
        span = a_max - a_min + 1e-300

        return {
            "condition_number": a_max / (a_min + 1e-300),
            "prolate_index": (a_max - a_mid) / span,
            "oblate_index": (a_mid - a_min) / span,
            "detection_sensitivity": float(np.sum(1.0 / (a + 1e-300))),
        }

    def fisher_information_metric(self, point) -> np.ndarray:
        """Fisher information metric (local quadratic form) at a surface point.

        Approximation: the curvature tensor in BSDT channel space is
        the Hessian of Q at the surface point.  Returns the d×d matrix.
        """
        # grad^2 Q = diag(2 / a_k^2) in body frame
        hess = np.diag(2.0 * self._a2_inv)
        # Restrict to tangent plane (project out normal direction)
        n = self.surface_normal(np.atleast_2d(point))[0]
        P = np.eye(self.d) - np.outer(n, n)
        return P @ hess @ P

    # ──────────────────────────────────────────────────────────
    #  Summary
    # ──────────────────────────────────────────────────────────

    def ellipsoid_info(self) -> dict:
        """Return a summary dictionary of all ellipsoid properties."""
        ecc = self.eccentricities()
        aniso = self.domain_anisotropy()
        info = {
            "dimension": self.d,
            "semi_axes": self.semi_axes.tolist(),
            "centre": self.centre.tolist(),
            "volume": self.volume(),
            "eccentricities": ecc,
            "domain_anisotropy": aniso,
        }
        if self.d <= 3:
            info["surface_area"] = self.surface_area()
        return info

    def __repr__(self) -> str:
        axes_str = ", ".join(f"{a:.4f}" for a in self.semi_axes)
        return (f"EllipsoidGeometry(d={self.d}, "
                f"semi_axes=[{axes_str}], "
                f"centre={self.centre.tolist()})")
