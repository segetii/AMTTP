"""
state_matrix.py
===============
Builds the joint state matrix  X(t) ∈ ℝ^{N × d}  from FRED aggregate series.

Approach
--------
We have d=6 standardised aggregate macrofinancial features  z(t) ∈ ℝ^6
(one per quarter from FRED).  We construct N=12 synthetic "bank-sector agents"
by applying sector-specific loading weights  W ∈ ℝ^{N × d}  and adding
small idiosyncratic noise:

    x_i(t) = diag(w_i) · z(t) + σ_ε · ε_i(t),   ε_i(t) ~ N(0,I)

The N=12 sectors and their d-dimensional loading profiles are stylised
representations of documented cross-sectional heterogeneity in U.S. banking.
The weights are grounded in FDIC Call Report and BIS structural data.

The 6 features (after standardisation) are:
    0 – leverage   (credit_gdp or total_loans growth)
    1 – stress     (stlfsi or nfci)
    2 – credit_spr (hy_spread or baa_spread)
    3 – yield_slope (T10Y2Y)
    4 – volatility (VIX)
    5 – short_rate (fed_funds)
"""

from __future__ import annotations
import numpy as np
import pandas as pd

# ─────────────────────────────────────────────────────────────────────────────
# Sector loading matrix  W[N, d]
# Rows = 12 sectors, Cols = 6 features
# Values are multipliers on the aggregate z(t); > 1 means more sensitive,
# < 1 means less sensitive, negative means counter-cyclical.
# ─────────────────────────────────────────────────────────────────────────────
#                     lev   stress credit_spr  slope   vol  short_r
SECTOR_WEIGHTS = np.array([
    # 0  Large commercial banks (JPM, BAC, WFC, C type)
    [  1.4,   1.1,   0.8,  -0.4,   0.7,   1.2  ],
    # 1  Regional banks
    [  1.1,   0.9,   0.7,  -0.5,   0.5,   1.0  ],
    # 2  Investment banks / broker-dealers
    [  1.2,   1.5,   1.4,   0.3,   1.8,   0.6  ],
    # 3  Insurance companies (life + P&C)
    [  0.5,   0.6,   0.9,   0.7,   0.4,   0.3  ],
    # 4  Money market funds
    [ -0.2,   0.8,   0.5,   1.2,   0.3,   2.0  ],
    # 5  REITs
    [  1.8,   1.0,   1.1,  -0.9,   0.9,   1.5  ],
    # 6  Hedge funds / alt managers
    [  0.9,   1.3,   1.6,   0.5,   2.2,   0.4  ],
    # 7  Thrifts / S&Ls (mortgage-heavy)
    [  1.6,   0.8,   0.6,  -1.1,   0.6,   1.3  ],
    # 8  Foreign bank branches (USD funding stress)
    [  1.0,   1.4,   1.2,   0.2,   1.1,   0.8  ],
    # 9  GSEs (Fannie/Freddie type)
    [  2.0,   0.7,   0.5,  -0.8,   0.5,   1.1  ],
    # 10 Credit unions (low-risk retail)
    [  0.4,   0.3,   0.3,  -0.3,   0.2,   0.7  ],
    # 11 Shadow banking (levered non-bank credit)
    [  1.5,   1.8,   1.9,   0.1,   1.5,   0.5  ],
], dtype=float)  # shape (12, 6)

SECTOR_NAMES = [
    "Large Commercial Banks",
    "Regional Banks",
    "Investment Banks",
    "Insurance Companies",
    "Money Market Funds",
    "REITs",
    "Hedge Funds / Alt",
    "Thrifts / S&Ls",
    "Foreign Bank Branches",
    "GSEs",
    "Credit Unions",
    "Shadow Banking",
]

# Idiosyncratic noise (fraction of aggregate amplitude)
NOISE_SIGMA: float = 0.05

# FRED feature columns to use (in order matching SECTOR_WEIGHTS cols)
FEATURE_COLS = ["credit_gdp", "stlfsi", "baa_spread", "slope_10y2y", "vix", "fed_funds"]
# Fallback if primary column missing
FEATURE_FALLBACK = {
    "credit_gdp":  "total_loans",
    "stlfsi":      "nfci",
    "baa_spread":  "hy_spread",
}


def select_features(df_std: pd.DataFrame) -> pd.DataFrame:
    """Select and align the d=6 feature columns, with fallback."""
    selected = []
    for col in FEATURE_COLS:
        if col in df_std.columns:
            selected.append(df_std[col])
        elif col in FEATURE_FALLBACK and FEATURE_FALLBACK[col] in df_std.columns:
            selected.append(df_std[FEATURE_FALLBACK[col]].rename(col))
        else:
            # Fill with zeros if unavailable
            selected.append(pd.Series(0.0, index=df_std.index, name=col))
    return pd.concat(selected, axis=1)


def build_state_matrix(
    df_std: pd.DataFrame,
    rng: np.random.Generator | None = None,
    noise_sigma: float = NOISE_SIGMA,
) -> tuple[np.ndarray, pd.DatetimeIndex]:
    """
    Build X(t) ∈ ℝ^{T × N × d}.

    Parameters
    ----------
    df_std : pd.DataFrame — standardised FRED features (T × k)
    rng    : random generator for reproducibility
    noise_sigma : idiosyncratic noise level

    Returns
    -------
    X : np.ndarray  shape (T, N, d)
    dates : pd.DatetimeIndex  length T
    """
    if rng is None:
        rng = np.random.default_rng(42)

    feat = select_features(df_std).dropna()
    Z = feat.values                         # (T, d)
    T, d = Z.shape
    N = SECTOR_WEIGHTS.shape[0]
    W = SECTOR_WEIGHTS[:, :d]               # (N, d), trim if d < 6

    # X[t, i, :] = W[i, :] * Z[t, :] + noise
    # Broadcasting: (T,1,d) * (1,N,d)  →  (T,N,d)
    X = Z[:, None, :] * W[None, :, :]      # (T, N, d)
    noise = rng.standard_normal((T, N, d)) * noise_sigma
    X = X + noise

    return X, feat.index


def get_normal_period(X: np.ndarray, dates: pd.DatetimeIndex) -> np.ndarray:
    """
    Return the sub-array of X for the 'normal' pre-crisis period
    (2002-Q1 through 2006-Q4) used to fit the BSDT reference distribution.
    """
    mask = (dates >= "2002-01-01") & (dates <= "2006-12-31")
    return X[mask]


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from fred_loader import fetch_all, apply_transforms, standardise

    raw = fetch_all(verbose=True)
    xf  = apply_transforms(raw)
    std, mu, sig = standardise(xf)

    X, dates = build_state_matrix(std)
    print(f"State matrix shape: {X.shape}   (T={X.shape[0]}, N={X.shape[1]}, d={X.shape[2]})")
    print(f"Date range: {dates[0].date()} → {dates[-1].date()}")
    print(f"X mean: {X.mean():.4f},  std: {X.std():.4f},  max|X|: {np.abs(X).max():.4f}")
