"""
canonical_v4_engine.py
======================
Strict locked Canonical Dynamical Geometry System v4 + mathematically exact BSDT.

Locked execution (per v4 spec, identical to cyber_frozen_window_validation.py):
    S(X) = (X - mu_0) / sigma_0           (centred, scaled state)
    G    = Sigma_0^{-1}                   (frozen inverse covariance from reference)
    J    = I                              (Euclidean Rule 2)
    g_X  = 2 J^T G S = 2 G S              (energy gradient direction)
    E    = S^T G S                        (Lyapunov energy)
    F    = F_base - g_X      with F_base = -alpha_base * S
    gamma = E / (E + theta)              (adaptive brake, theta frozen from ref)
    X_dot = F - gamma * <F,g_X>/||g_X||^2 * g_X     (Euclidean projection)

Mathematically exact BSDT channels (only locked-ODE quantities):
    delta_C  Camouflage        = |gamma * <F,g_X>/||g_X||^2| * ||g_X||  (radial commitment)
    delta_A  Activity (MFLS)   = ||grad E||_F = ||g_X||
    delta_T  Temporal novelty  = |dE/dt|
    delta_G  Feature gap       = max_i (S_i^2)   (largest squared coordinate)

Alignment angle (v4):
    cos theta_t = <F, g_X> / (||F|| * ||g_X||)

This engine is reused unchanged by every real-data domain script:
    domain_real_climate.py        -> NASA GISTEMP global temperature anomalies
    domain_real_epidemiology.py   -> JHU CSSE COVID-19 confirmed time series
    domain_real_eeg.py            -> UCI EEG Eye State
    domain_real_social_media.py   -> Wikipedia pageviews (ChatGPT-era AI articles)

Author: Odeyemi Olusegun Israel
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict
import numpy as np

EPS = 1e-10


@dataclass
class CanonicalV4Result:
    E: np.ndarray
    g_norm: np.ndarray
    F_norm: np.ndarray
    gamma: np.ndarray
    cos_theta: np.ndarray
    theta: np.ndarray
    Edot: np.ndarray
    delta_C: np.ndarray
    delta_A: np.ndarray
    delta_T: np.ndarray
    delta_G: np.ndarray
    score: np.ndarray            # frozen anomaly score (normalised positive deviation)
    threshold: float             # frozen reference threshold
    alarms: np.ndarray           # boolean alarms over the full timeline


class FrozenCanonicalV4:
    """Frozen Canonical-v4 + BSDT engine.

    Calibrate once on a reference window (chronologically earliest, treated as
    'normal'); then score the entire timeline without refit.  No synthetic data,
    no labels are used for fitting.
    """

    def __init__(self, ridge: float = 1e-3, alpha_base: float = 0.05,
                 thresh_percentile: float = 99.0):
        self.ridge = float(ridge)
        self.alpha_base = float(alpha_base)
        self.thresh_percentile = float(thresh_percentile)
        self.fitted = False

    # ---- frozen calibration ------------------------------------------------
    def fit(self, X_ref: np.ndarray) -> "FrozenCanonicalV4":
        X_ref = np.asarray(X_ref, dtype=float)
        self.mu_ = X_ref.mean(axis=0)
        self.sigma_ = X_ref.std(axis=0) + EPS
        Z = self._standardize(X_ref)
        cov = np.cov(Z, rowvar=False)
        cov = np.atleast_2d(cov) + self.ridge * np.eye(Z.shape[1])
        self.G_ = np.linalg.pinv(cov)
        E_ref = self._energy(Z)
        self.theta_ = float(np.percentile(E_ref, 75.0) + EPS)
        ref_obs = self._observables(Z)
        feats_ref = self._features(ref_obs)
        self.f_mu_ = feats_ref.mean(axis=0)
        self.f_sigma_ = feats_ref.std(axis=0) + EPS
        self.weights_ = np.ones(feats_ref.shape[1]) / feats_ref.shape[1]
        self.ref_score_ = self._score(feats_ref)
        self.threshold_ = float(np.percentile(self.ref_score_, self.thresh_percentile))
        self.fitted = True
        return self

    # ---- locked v4 mechanics ----------------------------------------------
    def _standardize(self, X: np.ndarray) -> np.ndarray:
        return (X - self.mu_[None, :]) / self.sigma_[None, :]

    def _energy(self, Z: np.ndarray) -> np.ndarray:
        return np.einsum("ij,ij->i", Z, Z @ self.G_)

    def _observables(self, Z: np.ndarray) -> Dict[str, np.ndarray]:
        GS = Z @ self.G_
        gX = 2.0 * GS
        E = np.einsum("ij,ij->i", Z, GS)
        Fbase = -self.alpha_base * Z
        F = Fbase - gX
        g_norm = np.linalg.norm(gX, axis=1) + EPS
        F_norm = np.linalg.norm(F, axis=1) + EPS
        dot_fg = np.einsum("ij,ij->i", F, gX)
        gamma = E / (E + self.theta_)
        coeff = dot_fg / (g_norm ** 2 + EPS)
        Xdot = F - (gamma * coeff)[:, None] * gX
        Edot = np.einsum("ij,ij->i", gX, Xdot)
        cos_theta = dot_fg / (F_norm * g_norm)
        cos_theta = np.clip(cos_theta, -1.0, 1.0)
        theta = np.arccos(cos_theta)
        radial_commit = np.abs(gamma * coeff) * g_norm
        feat_gap = np.max(Z * Z, axis=1)
        return dict(
            E=E, g_norm=g_norm, F_norm=F_norm, gamma=gamma, cos_theta=cos_theta,
            theta=theta, Edot=Edot, radial_commit=radial_commit, feat_gap=feat_gap,
            rho_eff=-Edot / (E + EPS),
        )

    def _features(self, obs: Dict[str, np.ndarray]) -> np.ndarray:
        return np.column_stack([
            np.log1p(np.maximum(obs["E"], 0.0)),
            np.log1p(obs["g_norm"]),
            np.log1p(np.maximum(obs["rho_eff"], 0.0)),
            np.maximum(obs["cos_theta"], 0.0),
        ])

    def _score(self, feats: np.ndarray) -> np.ndarray:
        z = (feats - self.f_mu_[None, :]) / self.f_sigma_[None, :]
        return np.maximum(z, 0.0) @ self.weights_

    # ---- public scoring ----------------------------------------------------
    def evaluate(self, X: np.ndarray) -> CanonicalV4Result:
        if not self.fitted:
            raise RuntimeError("FrozenCanonicalV4 must be .fit() first")
        Z = self._standardize(np.asarray(X, dtype=float))
        obs = self._observables(Z)
        feats = self._features(obs)
        score = self._score(feats)
        return CanonicalV4Result(
            E=obs["E"], g_norm=obs["g_norm"], F_norm=obs["F_norm"],
            gamma=obs["gamma"], cos_theta=obs["cos_theta"], theta=obs["theta"],
            Edot=obs["Edot"],
            delta_C=obs["radial_commit"],
            delta_A=obs["g_norm"],
            delta_T=np.abs(obs["Edot"]),
            delta_G=obs["feat_gap"],
            score=score,
            threshold=self.threshold_,
            alarms=score > self.threshold_,
        )


def first_alarm_lead(alarms: np.ndarray, crisis_index: int) -> int:
    """Return number of steps the first alarm precedes the crisis (negative if late)."""
    fa = int(np.argmax(alarms)) if np.any(alarms) else len(alarms)
    return int(crisis_index - fa)


def channel_dominance(result: CanonicalV4Result, mask: np.ndarray | None = None) -> Dict[str, float]:
    if mask is None:
        mask = np.ones_like(result.score, dtype=bool)
    vals = {
        "delta_C": float(np.mean(result.delta_C[mask])),
        "delta_A": float(np.mean(result.delta_A[mask])),
        "delta_T": float(np.mean(result.delta_T[mask])),
        "delta_G": float(np.mean(result.delta_G[mask])),
    }
    s = sum(vals.values()) + EPS
    return {k: v / s for k, v in vals.items()}
