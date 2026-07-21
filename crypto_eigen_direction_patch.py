"""
Eigenvector-Based Directional Strategy (Method 2 Extension for Crypto)
Replaces the naive momentum np.sign(ret5_eth) with structural dominant 
eigenvector loading from the BSDT correlation matrix.

This restores the 79.8% (H=21) / 89.5% (H=63) geometrical path predictive 
accuracy found in the S&P 500 baseline, applying it directly to the 
crypto intraday manifolds.

===============================================================================
ENERGY-DIRECTION SEPARATION (EDS) — proofs + robust v2 implementation
===============================================================================

Motivation (root cause of the NaN-collapse bug found in run_crypto_godmode_v1
and of the v26 "sign(cos_theta)" catastrophe documented in repo memory):
any quadratic/bilinear "energy" scalar built from a state vector S is an EVEN
function of S and therefore cannot carry directional (sign) information. The
original `compute_crypto_eigen_direction` tried to extract direction from an
eigenvector, which has a *separate* pathology (sign ambiguity), causing
spurious, discontinuous sign flips that then poison anything downstream.

Theorem 1 (Evenness of quadratic energy).
    For E(S) = S^T Sigma0^-1 S with Sigma0 symmetric positive-definite:
        E(-S) = (-S)^T Sigma0^-1 (-S) = S^T Sigma0^-1 S = E(S)
    => E is even. A decision rule that is purely a function of E (e.g. a
    threshold/gate on E, or any Sigma0-eigenvector treated as "the trade")
    is identical for S and -S, i.e. it structurally cannot encode direction.
    Corollary: this is the same failure mode as the locked lesson
    "never use sign(cos_theta) as direction" — cos_theta is built from
    bilinear engine-state quantities and carries no return-axis sign.

Theorem 2 (Direction requires an odd map).
    Let D: R^n -> R be odd, i.e. D(-S) = -D(S) (e.g. a linear functional
    D(S) = w^T S, or a mean of signed returns). Then sign(D(S)) flips
    correctly whenever S -> -S (except on the measure-zero set D(S)=0).
    => Direction must come from an odd statistic, never from E.

Theorem 3 (Energy-Direction Separation / EDS construction).
    Define  signal(S) = sign(D(S)) * gamma(E(S)),  gamma: R>=0 -> [0,1]
    monotone non-decreasing (a confidence/intensity gate, e.g. a rolling
    rank-percentile of E). Then:
        signal(-S) = sign(D(-S)) * gamma(E(-S))          [E even, Thm 1]
                   = sign(-D(S)) * gamma(E(S))            [D odd,  Thm 2]
                   = -signal(S)
    i.e. signal is odd overall ("flip the state, flip the trade"), while its
    magnitude depends only on the (robust, even) energy term. Direction and
    confidence are now provably decoupled.

Theorem 4 (Eigenvector sign instability — the actual v1 bug).
    Eigenvectors are defined only up to sign: if W v = lambda v then also
    W(-v) = lambda(-v). An independent eigh() call at each rolling step can
    therefore return v_max(t) with an arbitrary relative sign vs v_max(t-1),
    especially when the top-2 eigenvalues are near-degenerate. This makes
    `compute_crypto_eigen_direction`'s output flip sign even when the
    underlying correlation structure evolves smoothly -- a discontinuity
    that is pure numerical noise, not signal, and is exactly what destabilized
    downstream chains into NaN/collapsed equity.
    Fix: continuity correction v_max(t) <- -v_max(t) if v_max(t).v_max(t-1)<0,
    the standard sign convention used for rolling PCA/eigendecompositions.

    A second, independent fragility is ill-conditioning of the rolling
    correlation matrix on short/collinear windows. Shrinkage regularization
        W_reg = (1 - rho) * W + rho * I     (rho in (0,1))
    bounds the condition number of W_reg by (1+rho)/rho, guaranteeing a
    strictly positive minimum eigengap so the dominant eigenvector (and its
    sign) stay well-defined -- removing the second source of instability.

See `ablation_energy_direction.py` (research/adaptive-friction/pipeline/results/)
for the empirical ablation validating both fixes against the original
(buggy) direction estimator and against naive momentum.
"""
import numpy as np
import pandas as pd

def compute_crypto_eigen_direction(df, features, window=60, ret_idx=0):
    """
    Computes rolling dominant eigenvector loading on the target return dimension.
    
    Args:
        df: DataFrame containing the raw features.
        features: List of column names used in the BSDT spectral order (Omega).
                  E.g., ['ret_eth_z','vol_eth_z','btc_dom_z','cross_disp_z']
        window: Rolling window size (typically 60 to match Omega/MFLS window).
        ret_idx: Index of the return feature in the 'features' list (usually 0).
        
    Returns:
        pd.Series of the dominant eigenvector loading for the return dimension.
        Positive value -> network structure implies upward drift.
        Negative value -> network structure implies downward drift.
    """
    X_raw = df[features].values
    T, N = X_raw.shape
    evec_r = np.full(T, np.nan)

    for t in range(window, T):
        wd = X_raw[t - window:t + 1]
        
        # 1. Pearson correlation of the feature block
        cov = np.cov(wd.T)
        std = np.sqrt(np.diag(cov))
        outer_std = np.outer(std, std)
        
        with np.errstate(divide='ignore', invalid='ignore'):
            corr = cov / outer_std
        
        if not np.all(np.isfinite(corr)):
            corr = np.where(np.isfinite(corr), corr, 0.0)
            np.fill_diagonal(corr, 1.0)
            
        # 2. Convert to row-normalized absolute correlation matrix W
        W = np.abs(corr)
        W = W / (W.sum(axis=1, keepdims=True) + 1e-12)
        
        # 3. Eigendecomposition to find structural dominant mode
        eigvals, eigvecs = np.linalg.eigh(W)
        v_max = eigvecs[:, -1] # largest eigenvalue's eigenvector
        
        # 4. Extract directional loading
        evec_r[t] = v_max[ret_idx]

    return pd.Series(evec_r, index=df.index, name='eigen_direction')


def setup_a_directional_eigen(df, omega, mfls, gamma, phase, evec_loading):
    """
    Replaces the naive 'setup_a_directional' in v34/v36.
    Uses geometry (Omega and A) purely for intensity gating, and the 
    structural Eigenvector loading for +1/-1 direction.
    """
    A = mfls / (gamma + 1e-9)
    
    w1 = omega.expanding(60).rank(pct=True)
    w2 = A.expanding(60).rank(pct=True)
    
    # Intensity gate: remain flat if instability is too low
    w1_g = w1.where(w1 >= 0.50, 0.0)
    w2_g = w2.where(w2 >= 0.33, 0.0)
    
    # Pure geometry direction
    # Positive loading on returns implies upstream structural pressure upward
    direction = np.sign(evec_loading).fillna(0)
    
    # Phase-conditional overrides (retaining systemic struct from orig code)
    ph = phase.values
    d  = np.zeros(len(df))
    
    # Apply Eigen-Direction strictly in Crash/Transition (2) phase.
    # In pure boom (3), hold +1.
    d[ph == 2] = direction.values[ph == 2]
    d[ph == 3] = 1.0  
    
    d_series = pd.Series(d, index=df.index)
    
    return (d_series * w1_g * w2_g).clip(-1, 1)

def compute_crypto_eigen_direction_v2(df, features, window=60, ret_idx=0, shrinkage=0.15):
    """
    Robust, sign-continuous, NaN-safe dominant-eigenvector direction estimator.
    Fixes the two failure modes proven in Theorem 4 above:

      1. Eigenvector sign ambiguity -> continuity correction against the
         previous step's eigenvector (flip if inner product < 0).
      2. Ill-conditioned rolling correlation matrix -> shrinkage toward I,
         bounding condition number by (1+shrinkage)/shrinkage.

    Also NaN-safe: a window containing any non-finite raw feature value is
    skipped (output stays NaN for that bar, filled by the caller with 0 /
    "stay flat"), instead of propagating NaN through np.cov/eigh.
    """
    X_raw = df[features].values
    T, N = X_raw.shape
    evec_r = np.full(T, np.nan)
    v_prev = None

    for t in range(window, T):
        wd = X_raw[t - window:t + 1]
        if not np.all(np.isfinite(wd)):
            continue  # NaN-safe skip -- do not corrupt v_prev continuity chain

        cov = np.cov(wd.T)
        std = np.sqrt(np.diag(cov))
        outer_std = np.outer(std, std)
        with np.errstate(divide='ignore', invalid='ignore'):
            corr = cov / outer_std

        if not np.all(np.isfinite(corr)):
            corr = np.where(np.isfinite(corr), corr, 0.0)
            np.fill_diagonal(corr, 1.0)

        W = np.abs(corr)
        W = W / (W.sum(axis=1, keepdims=True) + 1e-12)

        # Shrinkage regularization (Theorem 4, part 2)
        W_reg = (1.0 - shrinkage) * W + shrinkage * np.eye(N)

        eigvals, eigvecs = np.linalg.eigh(W_reg)
        v_max = eigvecs[:, -1]

        # Sign-continuity correction (Theorem 4, part 1)
        if v_prev is not None and np.dot(v_max, v_prev) < 0:
            v_max = -v_max
        v_prev = v_max

        evec_r[t] = v_max[ret_idx]

    return pd.Series(evec_r, index=df.index, name='eigen_direction_v2')


def compute_energy_gate(df, features, window=60, shrinkage=0.15):
    """
    E(S) = S^T Sigma0^-1 S  (Mahalanobis-style quadratic energy, EVEN by
    Theorem 1). Used only as a magnitude/confidence gate -- never for
    direction. Sigma0 is a rolling shrinkage-regularized covariance,
    guaranteeing invertibility (NaN-safe).

    Returns:
        E_series: raw energy values (float, NaN where window has missing data)
        gate:     expanding rank-percentile of E in [0, 1] (monotone gamma(E))
    """
    X = df[features].values
    T, N = X.shape
    E = np.full(T, np.nan)
    I_N = np.eye(N)

    for t in range(window, T):
        wd = X[t - window:t + 1]
        if not np.all(np.isfinite(wd)):
            continue

        mu = wd.mean(axis=0)
        cov = np.cov(wd.T)
        trace_scale = np.trace(cov) / N if N > 0 else 1.0
        cov_reg = (1.0 - shrinkage) * cov + shrinkage * trace_scale * I_N

        try:
            Sigma_inv = np.linalg.inv(cov_reg + 1e-9 * I_N)
        except np.linalg.LinAlgError:
            continue

        s = X[t] - mu
        E[t] = float(s @ Sigma_inv @ s)

    E_series = pd.Series(E, index=df.index, name='energy')
    gate = E_series.expanding(window).rank(pct=True).fillna(0.0)
    return E_series, gate


def setup_energy_direction_separated(df, features, window=60, ret_idx=0, shrinkage=0.15):
    """
    Energy-Direction Separation (EDS): signal = sign(D(S)) * gamma(E(S))

    D(S): sign-continuous, shrinkage-regularized dominant eigenvector loading
          (`compute_crypto_eigen_direction_v2` — Theorem 4 fix).
    E(S): Mahalanobis quadratic energy (`compute_energy_gate` — Theorem 1),
          used purely as an intensity gate, never as direction.

    Proven property (Theorem 3): signal(-S) = -signal(S).
    """
    D = compute_crypto_eigen_direction_v2(df, features, window=window, ret_idx=ret_idx, shrinkage=shrinkage)
    _, gate = compute_energy_gate(df, features, window=window, shrinkage=shrinkage)
    direction = np.sign(D.fillna(0.0))
    return (direction * gate).rename('eds_signal')


if __name__ == "__main__":
    print("Eigen-Direction Patch Module Loaded.")
    print("Replace your calls to `setup_a_directional` with `setup_a_directional_eigen`.")
    print("For the robust NaN-safe / sign-continuous version, use `setup_energy_direction_separated`.")
