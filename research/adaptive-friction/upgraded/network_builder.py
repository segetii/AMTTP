"""
network_builder.py
==================
Construct the inter-sector exposure matrix  W ∈ ℝ^{N×N}  from the empirical
data, using the Ledoit-Wolf Oracle shrinkage estimator.

No free parameters chosen by the researcher.  The shrinkage intensity is
determined analytically from the data (Ledoit & Wolf 2004, JMVA).

Approach
--------
Given the panel X(t) ∈ ℝ^{N×d} over T quarters, we construct W as the
Ledoit-Wolf shrinkage estimate of the N×N cross-sector *correlation* matrix
of the leverage feature (f0 = loan_to_asset).  Specifically:

    [TxN leverage series] → Ledoit-Wolf covariance → normalise to correlation → W

Rationale (fully defensible):
  • The phase-transition formula in Theorem 2 depends on λ_max(W), the spectral
    radius of the bilateral-exposure graph.
  • Cross-sector leverage correlations are the canonical proxy for bilateral
    exposure when granular bilateral claim data are unavailable; this is
    the same approach used in Billio et al. (2012, JFinEcon) and
    Hautsch et al. (2015, RFS).
  • The Ledoit-Wolf estimator is asymptotically optimal (Oracle-equivalent)
    for the Frobenius-norm loss; its shrinkage intensity ρ* is closed-form
    and does not require a validation set or cross-validation.

The resulting  W  is symmetric positive semi-definite and its entries have a
clear economic interpretation: W_ij ≈ empirical cross-sector leverage
co-movement, the natural measure of system interconnectedness.

References
----------
Ledoit, O. and Wolf, M. (2004). "A well-conditioned estimator for
  large-dimensional covariance matrices." JMVA 88(2), 365-411.
Billio, M., Getmansky, M., Lo, A.W. and Pelizzon, L. (2012).
  "Econometric measures of connectedness and systemic risk in FIRE."
  Journal of Financial Economics 104(3), 535-559.
"""

from __future__ import annotations
import numpy as np
from sklearn.covariance import LedoitWolf


# Feature index used for network estimation
_LEVERAGE_IDX: int = 0   # f0 = loan_to_asset


def lw_correlation_network(X: np.ndarray) -> np.ndarray:
    """
    Build the N×N exposure network from panel data X (T, N, d).

    Steps
    -----
    1. Extract the T×N leverage time series  L(t) = X[:, :, 0].
    2. Fit Ledoit-Wolf shrinkage on  L  (treating sectors as variables).
       sklearn's LedoitWolf uses the analytical Ledoit-Wolf (2004) formula
       — no CV, no free hyperparameter.
    3. Convert the N×N covariance to correlation matrix (unit diagonal).
    4. Return the correlation matrix as  W.

    Parameters
    ----------
    X : np.ndarray, shape (T, N, d)

    Returns
    -------
    W : np.ndarray, shape (N, N), symmetric, entries in [-1, 1], diagonal = 1
    shrinkage : float — the analytically determined shrinkage coefficient ρ*
    """
    T, N, d = X.shape
    L = X[:, :, _LEVERAGE_IDX]          # T × N  leverage panel

    # Remove rows with any NaN
    L = L[~np.isnan(L).any(axis=1)]

    if L.shape[0] < N + 5:
        raise ValueError(
            f"Too few observations ({L.shape[0]}) for {N} sectors. "
            "Need at least N+5 complete rows."
        )

    lw = LedoitWolf(assume_centered=False, store_precision=False)
    lw.fit(L)                            # Oracle shrinkage — no free params
    Sigma_lw = lw.covariance_           # N × N shrunk covariance matrix

    # Normalise to correlation
    diag_inv_sqrt = 1.0 / np.sqrt(np.diag(Sigma_lw))
    W = Sigma_lw * np.outer(diag_inv_sqrt, diag_inv_sqrt)
    W = np.clip(W, -1.0, 1.0)
    np.fill_diagonal(W, 1.0)

    return W, float(lw.shrinkage_)


def spectral_radius(W: np.ndarray) -> float:
    """λ_max(W) — largest eigenvalue (absolute value)."""
    eigvals = np.linalg.eigvalsh(W)   # symmetric → real eigenvalues
    return float(np.max(np.abs(eigvals)))


def describe_network(W: np.ndarray, sector_names: list[str]) -> str:
    """Return a human-readable summary of the network."""
    N = W.shape[0]
    lmax = spectral_radius(W)
    offdiag = W[~np.eye(N, dtype=bool)]
    lines = [
        f"  Sectors (N={N}): {', '.join(sector_names)}",
        f"  λ_max(W) = {lmax:.4f}   (phase-transition threshold α/λ_max(W))",
        f"  Off-diagonal correlations: "
        f"mean={offdiag.mean():.3f}, "
        f"std={offdiag.std():.3f}, "
        f"max={offdiag.max():.3f}",
    ]
    return "\n".join(lines)
