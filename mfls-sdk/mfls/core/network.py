"""
Ledoit-Wolf correlation network and spectral analysis.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
from numpy.linalg import eigh


@dataclass
class NetworkInfo:
    """Summary of the inter-institution correlation network."""
    W: np.ndarray                  # (N, N) correlation matrix
    shrinkage: float               # Ledoit-Wolf shrinkage intensity
    spectral_radius: float         # lambda_max(W)
    n_institutions: int
    mean_off_diag: float
    max_off_diag: float


def lw_correlation_network(X: np.ndarray) -> NetworkInfo:
    """
    Build a Ledoit-Wolf shrinkage correlation network.

    Parameters
    ----------
    X : ndarray, shape (T, N, d)
        Panel of state matrices.

    Returns
    -------
    NetworkInfo
    """
    T, N, d = X.shape
    # Leverage = feature 0 (loan_to_asset) by convention
    leverage = X[:, :, 0]  # (T, N)

    # Ledoit-Wolf analytical shrinkage
    n, p = leverage.shape
    mu = leverage.mean(axis=0)
    Xc = leverage - mu
    S = (Xc.T @ Xc) / n  # sample covariance

    # Shrinkage target: scaled identity
    trace_S = np.trace(S)
    target = (trace_S / p) * np.eye(p)

    # Analytical shrinkage intensity (Oracle Approximating)
    Xc2 = Xc ** 2
    sum_sq = (Xc2.T @ Xc2) / n - S ** 2
    rho_num = sum_sq.sum() / n
    rho_den = ((S - target) ** 2).sum()
    rho = max(0.0, min(1.0, rho_num / (rho_den + 1e-30)))

    # Shrunk covariance → correlation
    cov = (1 - rho) * S + rho * target
    std = np.sqrt(np.diag(cov) + 1e-30)
    W = cov / np.outer(std, std)
    np.fill_diagonal(W, 1.0)
    W = (W + W.T) / 2  # enforce symmetry

    # Spectral radius
    eigvals = eigh(W)[0]  # eigh returns (eigenvalues, eigenvectors)
    lmax = float(np.max(np.abs(eigvals)))

    # Off-diagonal stats
    mask = ~np.eye(N, dtype=bool)
    off = W[mask]

    return NetworkInfo(
        W=W,
        shrinkage=rho,
        spectral_radius=lmax,
        n_institutions=N,
        mean_off_diag=float(off.mean()),
        max_off_diag=float(off.max()),
    )


def spectral_radius(W: np.ndarray) -> float:
    """Compute lambda_max(W) = largest eigenvalue by absolute value."""
    eigvals = eigh(W, eigvals_only=True)
    return float(np.max(np.abs(eigvals)))
