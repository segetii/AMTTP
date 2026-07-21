#!/usr/bin/env python3
"""
bank_systemic.py
================
v4 Canonical Dynamical Geometry System — full signal stack for the
G-SIB banking panel.

Signals implemented (from bank_fix_plan.md, v4 framework + addenda):
  S0   MFLS(t)           — leading gradient capacity (double-Mahalanobis)
  S0b  cosθ(t)           — direction predictor, Fbase = -α(X-μ₀) mean-reversion
  S1   R(t) + E_φ(t)     — Kuramoto order parameter + phase energy (clustering)
  S2   δ_G_frac(i,t)     — fractal multi-scale feature-gap (k=1,2,3, k^{-2} weights)
  S3   SBF(t)            — cross-sectional breadth (rolling per-bank Mahalanobis)
  S4   Ė sign test       — descent violation alarm (Theorem 9.1)
  S5   z_rank compound   — CV3 multi-signal institution ranking (Theorem P.2)

Diagnostics:
  γ(t), ρ_eff(t), η_cal(t), Ψ*, Ψ*_eff, δ_G_drift(t)

Cross-validations:
  CV1  Crisis chronology  (10 milestones, 3 splits)
  CV2  OOS walk-forward   (3 crisis-specific calib windows)
  CV3  Institution ranking (single signals + compound z_rank vs KNOWN_VULNERABILITY)

Alarm threshold: k=2.5 throughout (G5.3: ≈0.9 expected FP in 70-quarter panel)

Author: Odeyemi Olusegun Israel — AMTTP/UDL
"""

import sys, os, warnings, json
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── Data ────────────────────────────────────────────────────────────────────
CACHE = r"research\adaptive-friction\banklevel_enhanced\gsib_cache_real"
npz   = np.load(os.path.join(CACHE, "gsib_real_panel.npz"))
X_3d  = npz["X"].astype(np.float64)                     # (T, N, d)
meta  = json.load(open(os.path.join(CACHE, "gsib_real_meta.json")))
T, N, d = X_3d.shape
dates = pd.date_range("2005-01-01", periods=T, freq="QE")
BANK_NAMES = [b["name"] for b in meta]

# ── Ground truth ─────────────────────────────────────────────────────────────
KNOWN_VULNERABILITY = {
    "JPMorgan Chase":         2,
    "Bank of America":        4,
    "Citibank NA":            5,
    "Wells Fargo":            3,
    "Goldman Sachs Bank USA": 2,
    "BNY Mellon":             1,
    "HSBC":                   3,
    "BNP Paribas":            3,
    "Deutsche Bank":          4,
    "Barclays":               4,
    "Societe Generale":       3,
    "UniCredit":              3,
    "ING":                    4,
    "Mitsubishi UFJ":         1,
    "Mizuho":                 2,
    "Sumitomo Mitsui":        1,
    "Bank of China":          2,
    "ICBC":                   1,
    "China Construction Bank":1,
    "Standard Chartered":     1,
}

CRISIS_QUARTERS_SET = {
    "2007-12-31","2008-03-31","2008-06-30","2008-09-30",
    "2008-12-31","2009-03-31","2009-06-30",
    "2011-09-30","2011-12-31","2012-03-31","2012-06-30",
    "2020-03-31","2020-06-30",
}
y_crisis = np.array([1 if str(d.date()) in CRISIS_QUARTERS_SET else 0 for d in dates])

MILESTONES = [
    ("BNP MMF freeze",      "2007-09-30"),
    ("Bear Stearns rescue", "2008-03-31"),
    ("Lehman collapse",     "2008-09-30"),
    ("WaMu/Wachovia",       "2008-09-30"),
    ("TARP enacted",        "2008-12-31"),
    ("Stress test peak",    "2009-03-31"),
    ("Italian yield >7%",   "2011-12-31"),
    ("Draghi 'whatever'",   "2012-06-30"),
    ("WHO pandemic",        "2020-03-31"),
    ("COVID recovery",      "2020-06-30"),
]

K_ALARM = 2.5          # G5.3: expected FP ≈ 0.9 in 70-quarter normal window
W_IDIO  = 8            # rolling window quarters for per-bank Mahalanobis
EPS     = 1e-10


# ══════════════════════════════════════════════════════════════════════════════
#  HELPER UTILITIES
# ══════════════════════════════════════════════════════════════════════════════

def qt(date_str):
    ts = pd.Timestamp(date_str)
    idx = np.where((dates.year == ts.year) & (dates.quarter == ts.quarter))[0]
    return int(idx[0]) if len(idx) else None


def ql(t):
    d = dates[t]; return f"{d.year}-Q{d.quarter}"


def _g7_regularise(cov):
    """Cap κ(Σ) ≤ 10; return (Σ_reg, κ_raw, κ_eff)."""
    eigvals   = np.linalg.eigvalsh(cov)[::-1]
    lam_max   = float(eigvals[0])
    pos_eig   = eigvals[eigvals > 1e-12 * max(lam_max, 1e-30)]
    lam_min   = float(pos_eig[-1]) if len(pos_eig) else 1e-12
    kappa_raw = lam_max / max(lam_min, 1e-12)
    if kappa_raw > 10.0:
        lam_star = (lam_max - 10.0 * lam_min) / 9.0
        cov      = cov + max(lam_star, 0.0) * np.eye(cov.shape[0])
        kappa_eff = 10.0
    else:
        kappa_eff = kappa_raw
    return cov, kappa_raw, kappa_eff


def _zscore_signal(sig, mask):
    """Z-score 'sig' against the calibration portion selected by 'mask'."""
    ref = sig[mask]
    ref = ref[np.isfinite(ref)]
    mu  = float(ref.mean()) if len(ref) else 0.0
    std = float(ref.std())  if len(ref) else 1.0
    return (sig - mu) / max(std, EPS), mu, std


# ══════════════════════════════════════════════════════════════════════════════
#  STEP 1 — CANONICAL CALIBRATION
#  Implements: G7.3 θ-sequence, Ψ*, Ψ*_eff, PCA eigenvectors, α_reversion
# ══════════════════════════════════════════════════════════════════════════════

def calibrate_canonical(calib_end):
    """
    Freeze calibration at calib_end.

    Returns a dict with:
      scaler, mu_0, Sigma_0_reg, Sigma_inv,
      V1, V2, V3   — top-3 PCA eigenvectors of Sigma_0_reg
      theta        — corrected by G7.3 (κ_raw/κ_max)
      kappa_raw, kappa_eff
      mu_G, M_G    — λ_min, λ_max of Sigma_inv
      Psi_star, Psi_star_eff
      alpha        — mean-reversion rate (scalar)
      E_sys_calib  — (n_calib,) energy values during calibration
    """
    from sklearn.preprocessing import StandardScaler

    mask   = dates <= pd.Timestamp(calib_end)
    X_ref  = X_3d[mask].reshape(-1, d)           # (T_c*N, d)

    scaler = StandardScaler()
    X_s    = scaler.fit_transform(X_ref)
    mu_0   = X_s.mean(axis=0)
    Z_ref  = X_s - mu_0

    cov_raw         = (Z_ref.T @ Z_ref) / max(len(Z_ref) - 1, 1)
    cov_reg, k_raw, k_eff = _g7_regularise(cov_raw)

    Sigma_inv = np.linalg.inv(cov_reg)

    # PCA eigenvectors from regularised covariance
    evals, evecs = np.linalg.eigh(cov_reg)        # ascending
    idx_sort     = np.argsort(evals)[::-1]
    evecs        = evecs[:, idx_sort]             # columns = eigenvectors, descending var
    V1, V2, V3   = evecs[:, 0], evecs[:, 1], evecs[:, 2]

    # G7.3 θ-sequence: compute E on RAW Sigma_inv first, then correct θ
    Sigma_inv_raw = np.linalg.inv(cov_raw + EPS * np.eye(d))
    n_c = mask.sum()
    E_raw = np.zeros(n_c)
    for t in range(n_c):
        Xt   = scaler.transform(X_3d[t])
        Zt   = Xt - mu_0                          # (N, d)
        GZt  = Zt @ Sigma_inv_raw.T
        E_raw[t] = float(np.einsum("ni,ni->n", Zt, GZt).mean())

    theta_pre = float(np.median(E_raw)) + EPS
    theta     = theta_pre * k_raw / max(min(k_raw, 10.0), 1.0)  # G7.3 correction

    # Eigenvalue bounds of Sigma_inv
    ev_inv  = np.linalg.eigvalsh(Sigma_inv)
    mu_G    = float(ev_inv.min())
    M_G     = float(ev_inv.max())

    Psi_star = theta * mu_G / max(np.sqrt(M_G), EPS)

    # Stochastic Ψ*_eff: estimate Σ_noise from within-quarter feature variance
    # Use std within each bank-quarter (quarterly reporting noise floor)
    # Approximate: Σ_noise ≈ diag(var of per-quarter deviations from annual trend)
    # Simpler: Σ_noise ≈ σ²_rep * I where σ_rep is median feature std across banks
    feature_stds = np.array([X_3d[mask, :, f].std() for f in range(d)])
    Sigma_noise  = np.diag(feature_stds ** 2 * 0.01)   # 1% noise assumption
    c_Sigma      = 0.5 * float(np.trace(Sigma_inv @ Sigma_noise))
    Psi_star_eff = max(Psi_star - c_Sigma, 0.0)

    # Mean-reversion rate: median |lag-1 autocorrelation| across features
    # Computed on calibration window, pooled across banks
    autocorrs = []
    for f in range(d):
        series = X_3d[mask, :, f].flatten()
        if len(series) > 2:
            ac = float(np.corrcoef(series[:-1], series[1:])[0, 1])
            autocorrs.append(abs(ac))
    alpha = float(np.median(autocorrs)) if autocorrs else 0.3

    # E_sys during calibration using regularised Sigma_inv (for diagnostics)
    E_calib = np.zeros(n_c)
    for t in range(n_c):
        Xt   = scaler.transform(X_3d[t])
        Zt   = Xt - mu_0
        GZt  = Zt @ Sigma_inv.T
        E_calib[t] = float(np.einsum("ni,ni->n", Zt, GZt).mean())

    return dict(
        scaler=scaler, mu_0=mu_0,
        Sigma_inv=Sigma_inv, cov_reg=cov_reg,
        V1=V1, V2=V2, V3=V3,
        theta=theta, kappa_raw=k_raw, kappa_eff=k_eff,
        mu_G=mu_G, M_G=M_G,
        Psi_star=Psi_star, Psi_star_eff=Psi_star_eff,
        alpha=alpha, E_sys_calib=E_calib,
        calib_end=calib_end, n_calib=n_c,
    )


# ══════════════════════════════════════════════════════════════════════════════
#  STEP 2 — S0/S0b: MFLS, E_sys, γ, cosθ
#  Under BSDT dictionary: J=I, S=X̃, G=Σ_inv
#  MFLS(t)² = 4 Σ_i x̃_i^T Σ_inv² x̃_i    (double-Mahalanobis, v4 §8.2)
#  cosθ_i   = <Fbase_i, gX_i>/(‖Fbase_i‖‖gX_i‖)   where Fbase_i=-α x̃_i
#  Note: Fbase_i = -α x̃_i  →  cosθ_i = -‖Σ_inv x̃_i‖ / (‖x̃_i‖‖Σ_inv x̃_i‖ + ε)
#       simplifies to cosθ_i = -‖Σ_inv x̃_i‖ / ‖Σ_inv x̃_i‖ · 1/(‖x̃_i‖/‖Σ_inv x̃_i‖)
#  Full derivation: gX_i = 2 Σ_inv x̃_i; Fbase_i = -α x̃_i
#  cosθ_i = <-αx̃_i, 2Σ_inv x̃_i> / (α‖x̃_i‖ · 2‖Σ_inv x̃_i‖)
#          = -<x̃_i, Σ_inv x̃_i> / (‖x̃_i‖‖Σ_inv x̃_i‖)
#          = -(x̃_i^T Σ_inv x̃_i) / (‖x̃_i‖ · ‖Σ_inv x̃_i‖)
# ══════════════════════════════════════════════════════════════════════════════

def compute_mfls_gamma_costheta(cal):
    """
    Returns arrays of shape (T,) for MFLS, E_sys, γ; (T,N) for E_bank, cosθ_i.
    """
    scaler   = cal["scaler"]
    mu_0     = cal["mu_0"]
    Sinv     = cal["Sigma_inv"]
    Sinv2    = Sinv @ Sinv        # Σ_inv²
    theta    = cal["theta"]

    MFLS    = np.zeros(T)
    E_sys   = np.zeros(T)
    E_bank  = np.zeros((T, N))
    gamma   = np.zeros(T)
    costh_i = np.zeros((T, N))
    costh_s = np.zeros(T)

    for t in range(T):
        Xt  = scaler.transform(X_3d[t])           # (N, d)
        Zt  = Xt - mu_0                            # x̃_i

        GZt = Zt @ Sinv.T                          # Σ_inv x̃_i, shape (N,d)
        E_n = np.einsum("ni,ni->n", Zt, GZt)       # x̃_i^T Σ_inv x̃_i, (N,)

        # MFLS² = 4 Σ_i x̃_i^T Σ_inv² x̃_i
        G2Zt   = Zt @ Sinv2.T                      # Σ_inv² x̃_i
        mfls2  = 4.0 * float(np.einsum("ni,ni->n", Zt, G2Zt).sum())
        MFLS[t]   = np.sqrt(max(mfls2, 0.0))
        E_bank[t] = E_n
        E_sys[t]  = float(E_n.mean())
        gamma[t]  = E_sys[t] / (E_sys[t] + theta)

        # cosθ_i = -(x̃_i^T Σ_inv x̃_i) / (‖x̃_i‖ · ‖Σ_inv x̃_i‖)
        nZt  = np.linalg.norm(Zt,  axis=1)        # ‖x̃_i‖
        nGZt = np.linalg.norm(GZt, axis=1)        # ‖Σ_inv x̃_i‖
        denom_ct = nZt * nGZt
        ct   = np.where(denom_ct > EPS,
                        -E_n / denom_ct, 0.0)
        ct   = np.clip(ct, -1.0, 1.0)
        costh_i[t] = ct
        costh_s[t] = float(ct.mean())

    return MFLS, E_sys, E_bank, gamma, costh_i, costh_s


# ══════════════════════════════════════════════════════════════════════════════
#  STEP 3 — S1: Kuramoto R(t) + E_φ
# ══════════════════════════════════════════════════════════════════════════════

def compute_kuramoto(cal):
    """
    Phase from top-2 PCA eigenvectors of Σ_0.
    φ_i(t) = arg(V1^T x̃_i + i V2^T x̃_i)
    R(t)   = |N^{-1} Σ exp(i φ_i)|
    δ_Φ_i  = 1 - |(N-1)^{-1} Σ_{j≠i} exp(i(φ_j - φ_i))|
    E_φ    = N^{-1} Σ δ_Φ_i²
    Returns: R (T,), E_phi (T,), delta_phi (T,N)
    """
    scaler = cal["scaler"]
    mu_0   = cal["mu_0"]
    V1, V2 = cal["V1"], cal["V2"]

    R         = np.zeros(T)
    E_phi     = np.zeros(T)
    delta_phi = np.zeros((T, N))

    for t in range(T):
        Xt = scaler.transform(X_3d[t])
        Zt = Xt - mu_0                             # (N, d)

        # Projections onto top-2 eigenvectors
        proj1 = Zt @ V1                            # (N,)
        proj2 = Zt @ V2                            # (N,)

        # Phase angles
        phi = np.arctan2(proj2, proj1)             # (N,) in (-π, π)

        # Kuramoto order parameter
        z_kuramoto = np.mean(np.exp(1j * phi))
        R[t] = float(abs(z_kuramoto))

        # Per-bank phase incoherence
        exp_phi = np.exp(1j * phi)                  # (N,)
        dp = np.zeros(N)
        for i in range(N):
            others = np.delete(exp_phi, i)
            # relative phases: exp(i(φ_j - φ_i)) = exp_φ_j · conj(exp_φ_i)
            rel    = others * np.conj(exp_phi[i])
            dp[i]  = 1.0 - abs(np.mean(rel))
        delta_phi[t] = dp
        E_phi[t]     = float(np.mean(dp**2))

    return R, E_phi, delta_phi


# ══════════════════════════════════════════════════════════════════════════════
#  STEP 4 — S2: δ_G_frac  (fractal multi-scale feature gap, v4 §D.2)
# ══════════════════════════════════════════════════════════════════════════════

def compute_delta_G_frac(cal):
    """
    δ_G_frac(i,t) = 1.0·‖(I-V1V1^T)x̃_i‖² + 0.25·‖(I-V2V2^T)x̃_i‖² + 0.11·‖(I-V3V3^T)x̃_i‖²
    Returns: delta_G_frac (T,N), also per-scale arrays.
    """
    scaler     = cal["scaler"]
    mu_0       = cal["mu_0"]
    V1, V2, V3 = cal["V1"], cal["V2"], cal["V3"]
    weights    = [1.0, 0.25, 0.11]                # k^{-2} for k=1,2,3

    dG_frac = np.zeros((T, N))
    # Pre-compute projection matrices (outer products)
    Pvecs = [V1[:, None], V2[:, None], V3[:, None]]

    for t in range(T):
        Xt = scaler.transform(X_3d[t])
        Zt = Xt - mu_0                             # (N, d)

        for w, Pvec in zip(weights, Pvecs):
            proj  = Zt @ Pvec.flatten()            # (N,) — projection scalar per bank
            resid = Zt - np.outer(proj, Pvec.flatten())  # (N, d) — gap component
            dG_frac[t] += w * np.sum(resid ** 2, axis=1)

    return dG_frac


# ══════════════════════════════════════════════════════════════════════════════
#  STEP 5 — S3: SBF (rolling per-bank idiosyncratic Mahalanobis)
# ══════════════════════════════════════════════════════════════════════════════

def compute_sbf(cal, W=W_IDIO):
    """
    Rolling W-quarter per-bank Mahalanobis E_idio vs own history.
    E_idio(i,t): Mahalanobis of bank i at t vs its [t-W:t] window mean/cov.
    SBF(t): fraction of banks above their own 2.5σ threshold.
    Returns: E_idio (T,N), SBF (T,), thresholds_idio (N,)
    """
    scaler = cal["scaler"]

    # Work in scaled space
    X_scaled = np.zeros_like(X_3d)
    for t in range(T):
        X_scaled[t] = scaler.transform(X_3d[t])

    E_idio = np.full((T, N), np.nan)

    for i in range(N):
        series = X_scaled[:, i, :]                # (T, d)
        for t in range(W, T):
            window = series[t - W:t]               # (W, d)
            mu_w   = window.mean(axis=0)
            Z_w    = window - mu_w
            cov_w  = (Z_w.T @ Z_w) / max(W - 1, 1)
            cov_w_reg, _, _ = _g7_regularise(cov_w)
            try:
                G_w = np.linalg.inv(cov_w_reg)
            except np.linalg.LinAlgError:
                G_w = np.linalg.pinv(cov_w_reg)
            z_t        = series[t] - mu_w
            E_idio[t, i] = float(z_t @ G_w @ z_t)

    # Per-bank thresholds from first available window
    thresholds = np.full(N, np.nan)
    for i in range(N):
        vals = E_idio[W:W + int(T * 0.4), i]
        vals = vals[np.isfinite(vals)]
        if len(vals) > 3:
            thresholds[i] = vals.mean() + K_ALARM * vals.std()

    # SBF: fraction of banks where E_idio > own threshold
    SBF = np.zeros(T)
    for t in range(W, T):
        above = 0
        valid = 0
        for i in range(N):
            if np.isfinite(E_idio[t, i]) and np.isfinite(thresholds[i]):
                valid += 1
                if E_idio[t, i] > thresholds[i]:
                    above += 1
        SBF[t] = above / max(valid, 1)

    return E_idio, SBF


# ══════════════════════════════════════════════════════════════════════════════
#  STEP 6 — S4: Ė sign test (descent violation, Theorem 9.1)
# ══════════════════════════════════════════════════════════════════════════════

def compute_descent_violation(E_sys, tau=1):
    """
    Theorem 9.1: Ė ≤ 0 under canonical descent.
    A violation: Ė > 0 for tau consecutive quarters.
    tau=1 (default): any single-quarter E increase is flagged.
    Returns: violation_mask (T,) bool, Edot (T,) float
    """
    Edot = np.diff(E_sys, prepend=E_sys[0])
    violation = np.zeros(T, dtype=bool)
    for t in range(tau, T):
        if all(Edot[t - tau + 1:t + 1] > 0):
            violation[t] = True
    return violation, Edot


def compute_mfls_rolling_z(MFLS, W=8):
    """
    Rolling z-score of MFLS relative to its own trailing W-quarter window.
    MFLS_rz(t) = (MFLS(t) - mean(MFLS[t-W:t])) / std(MFLS[t-W:t])

    This is structural-break-robust: alarm fires when MFLS rises sharply
    relative to recent history, regardless of the absolute level.
    Alarm threshold applied externally at k (same k=2.5 convention).
    For t < W: returns 0 (no alarm possible without full window).
    """
    rz = np.zeros(T)
    for t in range(W, T):
        window = MFLS[t - W:t]
        mu = window.mean()
        sd = window.std()
        if sd > EPS:
            rz[t] = (MFLS[t] - mu) / sd
    return rz


# ══════════════════════════════════════════════════════════════════════════════
#  STEP 7 — Diagnostics: γ, ρ_eff, η_cal
# ══════════════════════════════════════════════════════════════════════════════

def compute_diagnostics(E_sys, cal):
    """
    γ(t) = E/(E+θ), ρ_eff(t) = -ΔE/E, ρ_CR, η_cal = ρ_eff/ρ_CR
    Under BSDT (J=I): ρ_CR = 4·(μG/MG)·(1-γ_max)
    """
    theta  = cal["theta"]
    mu_G   = cal["mu_G"]
    M_G    = cal["M_G"]

    gamma  = E_sys / (E_sys + theta)
    gamma_max = float(gamma.max())
    # Complete_Derivations §10.1: ρ = 4σ²μG²/MG·(1−γmax); for BSDT J=I σ=1
    rho_CR    = 4.0 * (mu_G ** 2 / max(M_G, EPS)) * (1.0 - gamma_max)

    Edot   = np.diff(E_sys, prepend=E_sys[0])
    rho_eff = -Edot / np.maximum(E_sys, EPS)
    eta_cal = rho_eff / max(rho_CR, EPS)

    # Metric drift δ_G_drift vs calibration (G3: safe to recalibrate when < 0.1)
    cov_star = cal["cov_reg"]
    delta_G_drift = np.zeros(T)
    scaler = cal["scaler"]
    mu_0   = cal["mu_0"]
    Sinv_star = cal["Sigma_inv"]
    for t in range(T):
        Xt = scaler.transform(X_3d[t])
        Zt = Xt - mu_0
        cov_t = (Zt.T @ Zt) / max(N - 1, 1)
        denom = np.linalg.norm(cov_star, "fro")
        delta_G_drift[t] = np.linalg.norm(cov_t - cov_star, "fro") / max(denom, EPS)

    return gamma, rho_eff, rho_CR, eta_cal, delta_G_drift


# ══════════════════════════════════════════════════════════════════════════════
#  STEP 8 — S5: Compound z-rank for CV3 (Theorem P.2)
# ══════════════════════════════════════════════════════════════════════════════

def compute_z_rank(dG_frac_window, MFLS_bank_window, delta_phi_window,
                   dG_frac_calib_base, MFLS_bank_calib_base):
    """
    Compound vulnerability rank using RELATIVE (idiosyncratic) signals.

    Key change vs naive approach: use per-bank z-score of δ_G_frac and MFLS
    relative to each bank's OWN calibration baseline — this removes structural
    outliers (Goldman's business model) and isolates CHANGE in gap energy.

    dG_frac_window       : (n_w, N)  pre-crisis window values
    MFLS_bank_window     : (n_w, N)  pre-crisis window values
    delta_phi_window     : (n_w, N)  pre-crisis window values
    dG_frac_calib_base   : (n_c, N)  full calibration baseline for z-scoring
    MFLS_bank_calib_base : (n_c, N)  full calibration baseline for z-scoring

    Returns z_rank (N,) — higher = more vulnerable.
    """
    def _z(arr):
        arr = arr.astype(float)
        mu  = arr.mean(); std = arr.std()
        return (arr - mu) / max(std, EPS)

    # Per-bank RELATIVE gap energy: z-score each bank against its own calib baseline
    # This removes structural size/business-model differences
    mean_dG_window   = dG_frac_window.mean(axis=0)           # (N,)
    mean_dG_base     = dG_frac_calib_base.mean(axis=0)       # (N,)
    std_dG_base      = dG_frac_calib_base.std(axis=0) + EPS
    dG_rel           = (mean_dG_window - mean_dG_base) / std_dG_base  # per-bank z-score

    mean_mfls_window = MFLS_bank_window.mean(axis=0)
    mean_mfls_base   = MFLS_bank_calib_base.mean(axis=0)
    std_mfls_base    = MFLS_bank_calib_base.std(axis=0) + EPS
    mfls_rel         = (mean_mfls_window - mean_mfls_base) / std_mfls_base

    mean_dp          = delta_phi_window.mean(axis=0)          # high = phase-isolated = LESS vulnerable

    # Combine: higher on each dimension = more vulnerable
    # dG_rel: more positive = more gap growth = more exposed
    # mfls_rel: more positive = faster gradient growth = more stressed
    # 1 - mean_dp: lower phase isolation = higher synchrony exposure
    z_rank = _z(dG_rel) + _z(mfls_rel) + _z(1.0 - mean_dp)
    return z_rank, dG_rel, mfls_rel, mean_dp


# ══════════════════════════════════════════════════════════════════════════════
#  ALARM HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _alarm_mask(signal, calib_mask, k=K_ALARM):
    """Return bool array: signal > calib_mean + k·calib_std."""
    ref = signal[calib_mask]
    ref = ref[np.isfinite(ref)]
    mu  = ref.mean(); std = ref.std()
    return signal > (mu + k * std), mu, std


def _compute_hit_fa(alarm_bool, y_crisis_test):
    tp = (alarm_bool & (y_crisis_test == 1)).sum()
    fp = (alarm_bool & (y_crisis_test == 0)).sum()
    crisis_n = (y_crisis_test == 1).sum()
    normal_n = (y_crisis_test == 0).sum()
    hit = tp / max(crisis_n, 1)
    fa  = fp / max(normal_n, 1)
    return hit, fa


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN PIPELINE — one calibration window
# ══════════════════════════════════════════════════════════════════════════════

def run_full_pipeline(calib_end_str):
    """Run all signals against a calibration frozen at calib_end_str."""
    cal = calibrate_canonical(calib_end_str)
    calib_mask = dates <= pd.Timestamp(calib_end_str)

    # --- S0, S0b ---
    MFLS, E_sys, E_bank, gamma, costh_i, costh_s = compute_mfls_gamma_costheta(cal)

    # --- S1 ---
    R, E_phi, delta_phi = compute_kuramoto(cal)

    # --- S2 ---
    dG_frac = compute_delta_G_frac(cal)

    # --- S3 ---
    E_idio, SBF = compute_sbf(cal)

    # --- S4 ---
    violation, Edot = compute_descent_violation(E_sys, tau=1)

    # --- MFLS rolling z-score (structural-break-robust alarm) ---
    MFLS_rz = compute_mfls_rolling_z(MFLS, W=8)

    # --- Diagnostics ---
    gamma_d, rho_eff, rho_CR, eta_cal, delta_G_drift = compute_diagnostics(E_sys, cal)

    return dict(
        cal=cal, calib_mask=calib_mask,
        MFLS=MFLS, MFLS_rz=MFLS_rz,
        E_sys=E_sys, E_bank=E_bank,
        gamma=gamma, costh_i=costh_i, costh_s=costh_s,
        R=R, E_phi=E_phi, delta_phi=delta_phi,
        dG_frac=dG_frac,
        E_idio=E_idio, SBF=SBF,
        violation=violation, Edot=Edot,
        rho_eff=rho_eff, rho_CR=rho_CR, eta_cal=eta_cal,
        delta_G_drift=delta_G_drift,
    )


# ══════════════════════════════════════════════════════════════════════════════
#  RUN THREE CALIBRATION WINDOWS
# ══════════════════════════════════════════════════════════════════════════════

print("=" * 76)
print("  BANK SYSTEMIC — v4 CANONICAL FULL SIGNAL STACK")
print("  S0: MFLS  S0b: cosθ  S1: Kuramoto  S2: δ_G_frac  S3: SBF  S4: Ė  S5: z_rank")
print("  k=2.5 alarm threshold throughout (G5.3)")
print("=" * 76)

print("\n[1/3] GFC calibration  (2005Q1–2007Q2)…")
P_GFC  = run_full_pipeline("2007-06-30")

print("[2/3] Euro calibration (2009Q3–2011Q2)…")
P_EURO = run_full_pipeline("2011-06-30")

print("[3/3] COVID calibration (2016Q1–2019Q4)…")
P_COV  = run_full_pipeline("2019-12-31")

print("  Done.\n")

# Shorthand
pg = P_GFC;  pe = P_EURO;  pc = P_COV
cg = pg["calib_mask"]
ce = pe["calib_mask"]
cc = pc["calib_mask"]


# ══════════════════════════════════════════════════════════════════════════════
#  CALIBRATION SUMMARY
# ══════════════════════════════════════════════════════════════════════════════

print("━" * 76)
print("  CALIBRATION SUMMARY")
print("━" * 76)
for label, P, mask in [("GFC  (≤2007Q2)", pg, cg),
                        ("Euro (≤2011Q2)", pe, ce),
                        ("COVID(≤2019Q4)", pc, cc)]:
    cal = P["cal"]
    E_c = P["E_sys"][mask]
    R_c = P["R"][mask]
    print(f"\n  [{label}]")
    print(f"    κ_raw={cal['kappa_raw']:.1f}  κ_eff={cal['kappa_eff']:.1f}  "
          f"θ={cal['theta']:.3f}  α={cal['alpha']:.3f}")
    print(f"    E_sys: μ={E_c.mean():.3f} σ={E_c.std():.3f}")
    print(f"    R(t) calm: {R_c.mean():.3f}±{R_c.std():.3f}")
    print(f"    Ψ*={cal['Psi_star']:.4f}  Ψ*_eff={cal['Psi_star_eff']:.4f}")
    print(f"    ρ_CR={P['rho_CR']:.4f}  μG={cal['mu_G']:.3f}  MG={cal['M_G']:.3f}")


# ══════════════════════════════════════════════════════════════════════════════
#  CV1 — CRISIS CHRONOLOGY (GFC calibration)
#  Check MFLS, R, cosθ, E_sys, Ė violation at each milestone
# ══════════════════════════════════════════════════════════════════════════════

print()
print("━" * 76)
print("  CV1 — CRISIS CHRONOLOGY  (calibration: 2005Q1–2007Q2)")
print("  Signal firing vs 10 independently-dated crisis milestones")
print("━" * 76)

P = pg; mask = cg

# Compute per-signal alarm bounds from calibration window
mfls_alarm,  mu_mfls,  sd_mfls  = _alarm_mask(P["MFLS"],    mask)
R_alarm,     mu_R,     sd_R     = _alarm_mask(P["R"],        mask)
Ephi_alarm,  mu_Ep,    sd_Ep    = _alarm_mask(P["E_phi"],    mask)
# cosθ alarm: cosθ_s is always negative (mean-reversion anti-aligned with gX).
# More negative cosθ = stronger anti-alignment = ascending stress.
# We alarm when cosθ FALLS below calib_mean - k·σ (lower = more stressed).
# Implement: flip sign for _alarm_mask so that alarm fires when cosθ gets more negative.
costh_alarm, mu_ct,    sd_ct    = _alarm_mask(-P["costh_s"], mask)   # flip: alarm when cosθ drops
SBF_alarm,   mu_sbf,   sd_sbf   = _alarm_mask(P["SBF"],      mask)

print(f"\n  Calibration thresholds (k={K_ALARM}):")
print(f"    MFLS : μ={mu_mfls:.3f}  thr={mu_mfls+K_ALARM*sd_mfls:.3f}")
print(f"    R(t) : μ={mu_R:.3f}     thr={mu_R+K_ALARM*sd_R:.3f}")
print(f"    cosθ : μ={mu_ct:.3f}    thr={mu_ct+K_ALARM*sd_ct:.3f}")
print(f"    E_φ  : μ={mu_Ep:.3f}    thr={mu_Ep+K_ALARM*sd_Ep:.3f}")
print(f"    SBF  : μ={mu_sbf:.3f}   thr={mu_sbf+K_ALARM*sd_sbf:.3f}")
print()

hdr = (f"  {'Milestone':<23} {'Qtr':<8} {'E_sys':<7} {'MFLS':<6} "
       f"{'R(t)':<6} {'cosθ':<7} {'SBF':<6} {'Ė>0':<5} {'Lead?'}")
print(hdr)
print("  " + "-" * (len(hdr) - 2))

cv1_results = []
for name, date_str in MILESTONES:
    t_ev = qt(date_str)
    if t_ev is None: continue

    def _z(sig, mu, sd):
        return (sig[t_ev] - mu) / max(sd, EPS)

    es  = float(P["E_sys"][t_ev])
    ml  = float(P["MFLS"][t_ev])
    r   = float(P["R"][t_ev])
    ct  = float(P["costh_s"][t_ev])
    sb  = float(P["SBF"][t_ev])
    viol= P["violation"][t_ev]

    # Lead: earliest quarter in [-8, 0] where ANY signal fired
    lead = None
    for lag in range(1, 9):
        tl = t_ev - lag
        if tl < 0: break
        any_fire = (mfls_alarm[tl] or R_alarm[tl] or
                    Ephi_alarm[tl] or costh_alarm[tl])
        if any_fire:
            lead = lag

    fire_str = (
        ("M" if mfls_alarm[t_ev] else ".") +
        ("R" if R_alarm[t_ev]    else ".") +
        ("C" if costh_alarm[t_ev] else ".") +
        ("S" if SBF_alarm[t_ev]  else ".") +
        ("V" if viol             else ".")
    )
    # Lead: look back for ANY alarm in [-8, -1] quarters
    lead_str = f"+{lead}q" if lead else "—"

    print(f"  {name:<23} {ql(t_ev):<8} "
          f"{es:6.2f}  {ml:6.2f}  {r:.3f}  {ct:+.3f}  "
          f"{sb:.3f}  {'✓' if viol else '.':<5}  "
          f"{fire_str}  {lead_str}")

    cv1_results.append(dict(
        milestone=name, quarter=ql(t_ev),
        E_sys=es, MFLS=ml, R=r, costh=ct, SBF=sb,
        violation=bool(viol), fires=fire_str, lead=lead,
    ))

print(f"\n  M=MFLS  R=Kuramoto  C=cosθ  S=SBF  V=Ė violation")
n_any_fire  = sum(1 for r in cv1_results if any(c != '.' for c in r["fires"]))
n_with_lead = sum(1 for r in cv1_results if r["lead"] and r["lead"] >= 2)
print(f"\n  {n_any_fire}/{len(cv1_results)} milestones: at least one signal fired")
print(f"  {n_with_lead}/{len(cv1_results)} milestones: ≥2q advance signal")


# ══════════════════════════════════════════════════════════════════════════════
#  CV2 — OOS WALK-FORWARD  (3 crisis-specific splits)
# ══════════════════════════════════════════════════════════════════════════════

print()
print("━" * 76)
print("  CV2 — OUT-OF-SAMPLE WALK-FORWARD  (3 crisis-specific calibrations)")
print("  Expected FP per split at k=2.5: ~0.9 in 70 normal quarters")
print("━" * 76)

cv2_splits = [
    # label, pipeline, calib_end, test_start, test_end, primary signal keys
    # Test windows start 4-6 quarters BEFORE crisis onset to include normal quarters for FA measurement
    # MFLS_rz = rolling z-score of MFLS (structural-break-robust; alarm at k=2.5)
    ("GFC  (calib ≤2007Q2)", pg, cg,
     "2006-09-30", "2009-06-30",             # 5 pre-crisis normals + 7 GFC crisis quarters
     ["MFLS_rz", "violation", "R"]),
    ("Euro (calib ≤2011Q2)", pe, ce,
     "2010-06-30", "2012-06-30",             # 5 normal + 4 Euro crisis quarters
     ["MFLS_rz", "violation", "SBF"]),
    ("COVID(calib ≤2019Q4)", pc, cc,
     "2018-09-30", "2020-06-30",             # 6 normal + 2 COVID crisis quarters
     ["MFLS_rz", "violation", "R"]),
]

# Approximate expected FP (G5.3)
import math
def _expected_fp(k, n_normal):
    from scipy.stats import norm
    lambda_fp = 2.0 * (1.0 - norm.cdf(k))
    return lambda_fp * n_normal

cv2_results = []
for label, P, mask, ts, te, primaries in cv2_splits:
    print(f"\n  ── {label}")

    t_start = pd.Timestamp(ts)
    t_end   = pd.Timestamp(te)
    test_m  = (dates >= t_start) & (dates <= t_end)
    y_test  = y_crisis[test_m]

    n_crisis = int(y_test.sum())
    n_normal = int((y_test == 0).sum())
    exp_fp   = _expected_fp(K_ALARM, n_normal)

    row = dict(label=label, n_crisis=n_crisis, n_normal=n_normal,
               exp_fp=round(exp_fp, 2))

    for sig_key in primaries:
        # Boolean signals (violation) are already alarm arrays
        if sig_key == "violation":
            alarm_test = P["violation"][test_m]
        else:
            sig = P[sig_key]
            # cosθ_s: alarm when cosθ drops (negate)
            sig_use = -sig if sig_key == "costh_s" else sig
            alarm, _mu, _sd = _alarm_mask(sig_use, mask)
            alarm_test = alarm[test_m]

        hit, fa = _compute_hit_fa(alarm_test, y_test)
        row[f"hit_{sig_key}"] = round(hit, 2)
        row[f"fa_{sig_key}"]  = round(fa,  2)
        verdict_s = "✓" if hit >= 0.40 else ("~" if hit >= 0.25 else "✗")
        print(f"    {sig_key:<12}: hit={hit:.2f}  FA={fa:.2f}  "
              f"(exp FP≈{exp_fp:.1f} of {n_normal}n)  {verdict_s}")

    # Overall verdict: best primary hit (CONFIRMED ≥0.40, MARGINAL ≥0.25)
    best_hit = max((row.get(f"hit_{k}", 0) for k in primaries), default=0)
    if best_hit >= 0.40:
        verdict = "CONFIRMED ✓"
    elif best_hit >= 0.25:
        verdict = "MARGINAL ~"
    else:
        verdict = "NOT CONFIRMED ✗"
    row["verdict"] = verdict
    print(f"    Verdict: {verdict}  (best hit={best_hit:.2f})")
    cv2_results.append(row)


# ══════════════════════════════════════════════════════════════════════════════
#  CV3 — INSTITUTION RANKING  (GFC calibration: 2005Q1–2007Q2)
# ══════════════════════════════════════════════════════════════════════════════

print()
print("━" * 76)
print("  CV3 — INSTITUTION RANKING  (calibration: 2005Q1–2007Q2)")
print("  Q: Does the signal correctly rank vulnerability before GFC?")
print("━" * 76)

P = pg; mask_c = cg
n_c = int(mask_c.sum())

# Per-bank MFLS in calibration window
# gX_i = 2 Σ_inv x̃_i  →  ‖gX_i‖ = 2 ‖Σ_inv x̃_i‖  (per bank)
cal  = P["cal"]
Sinv = cal["Sigma_inv"]
scaler = cal["scaler"]
mu_0   = cal["mu_0"]

MFLS_bank_calib = np.zeros((n_c, N))
for ti, t in enumerate(np.where(mask_c)[0]):
    Xt  = scaler.transform(X_3d[t])
    Zt  = Xt - mu_0
    GZt = Zt @ Sinv.T
    MFLS_bank_calib[ti] = 2.0 * np.linalg.norm(GZt, axis=1)

dG_frac_calib   = P["dG_frac"][mask_c]                    # (n_c, N)
delta_phi_calib = P["delta_phi"][mask_c]                   # (n_c, N)
costh_i_calib   = P["costh_i"][mask_c]                     # (n_c, N)

# Use 4-quarter pre-crisis window for the RANKING signal (2006Q4–2007Q3)
# This matches the test: "what did the signal show JUST BEFORE the crisis?"
PRE_CRISIS_STRS = ["2006-12-31", "2007-03-31", "2007-06-30", "2007-09-30"]
pre_idx = [qt(d) for d in PRE_CRISIS_STRS if qt(d) is not None]

dG_frac_pre   = P["dG_frac"][np.array(pre_idx), :]          # (4, N)
delta_phi_pre = P["delta_phi"][np.array(pre_idx), :]         # (4, N)
costh_i_pre   = P["costh_i"][np.array(pre_idx), :]           # (4, N)

# Per-bank MFLS in pre-crisis window
MFLS_bank_pre = np.zeros((len(pre_idx), N))
for ti, t in enumerate(pre_idx):
    Xt  = scaler.transform(X_3d[t])
    Zt  = Xt - mu_0
    GZt = Zt @ Sinv.T
    MFLS_bank_pre[ti] = 2.0 * np.linalg.norm(GZt, axis=1)

# Per-signal means over pre-crisis window
mean_dG   = dG_frac_pre.mean(axis=0)
mean_mfls = MFLS_bank_pre.mean(axis=0)
mean_dp   = delta_phi_pre.mean(axis=0)
mean_ct   = costh_i_pre.mean(axis=0)   # more negative = more stressed

# MFLS slope over 8-quarter pre-crisis window (2005Q3–2007Q2)
# Slope = OLS beta of MFLS_bank_i ~ t over the 8 quarters immediately before GFC onset.
# Accelerating MFLS (positive slope) = bank stress building.
SLOPE_WINDOW_STRS = [
    "2005-09-30","2005-12-31","2006-03-31","2006-06-30",
    "2006-09-30","2006-12-31","2007-03-31","2007-06-30",
]
slope_idx = [qt(d) for d in SLOPE_WINDOW_STRS if qt(d) is not None]
MFLS_bank_slope_window = np.zeros((len(slope_idx), N))
for ti, t in enumerate(slope_idx):
    Xt  = scaler.transform(X_3d[t])
    Zt  = Xt - mu_0
    GZt = Zt @ Sinv.T
    MFLS_bank_slope_window[ti] = 2.0 * np.linalg.norm(GZt, axis=1)

x_t = np.arange(len(slope_idx), dtype=float)
x_t -= x_t.mean()
mfls_slope = np.array([
    float(np.polyfit(x_t, MFLS_bank_slope_window[:, i], 1)[0])
    for i in range(N)
])  # (N,) — positive = accelerating, negative = decelerating

# Compound z_rank (S5) — uses RELATIVE z-scores vs full calibration baseline
z_rank, dG_rel, mfls_rel, _ = compute_z_rank(
    dG_frac_pre, MFLS_bank_pre, delta_phi_pre,
    dG_frac_calib, MFLS_bank_calib
)

# Known vulnerability array aligned to BANK_NAMES
vuln_vec = np.array([KNOWN_VULNERABILITY.get(b, 2) for b in BANK_NAMES])

def _spearman_report(score_vec, label, higher_is_worse=True):
    """Higher score = more vulnerable if higher_is_worse=True."""
    if not higher_is_worse:
        score_vec = -score_vec
    rho, p = spearmanr(score_vec, vuln_vec)
    return rho, p

rho_dG,    p_dG    = _spearman_report(mean_dG,    "δ_G_frac abs")
rho_rel,   p_rel   = _spearman_report(dG_rel,     "δ_G_frac relative")
rho_mfls,  p_mfls  = _spearman_report(mean_mfls,  "MFLS abs")
rho_mr,    p_mr    = _spearman_report(mfls_rel,   "MFLS relative")
rho_dp,    p_dp    = _spearman_report(mean_dp,    "δ_Φ phase isol.", higher_is_worse=False)
rho_ct,    p_ct    = _spearman_report(mean_ct,    "cosθ per-bank",   higher_is_worse=False)
rho_z,     p_z     = _spearman_report(z_rank,     "z_rank compound")
rho_slope, p_slope = _spearman_report(mfls_slope, "MFLS slope (8Q)")

print()
print(f"  {'Signal':<26} {'Spearman ρ':>10}  {'p-value':>8}  Verdict")
print("  " + "-" * 64)
for sig, rho, pv in [
    ("δ_G_frac absolute",    rho_dG,    p_dG),
    ("δ_G_frac relative",    rho_rel,   p_rel),
    ("MFLS absolute",        rho_mfls,  p_mfls),
    ("MFLS relative",        rho_mr,    p_mr),
    ("δ_Φ phase isolation",  rho_dp,    p_dp),
    ("cosθ per-bank",        rho_ct,    p_ct),
    ("MFLS slope 8Q",        rho_slope, p_slope),
    ("z_rank compound",      rho_z,     p_z),
]:
    v = "✓" if rho > 0.40 and pv < 0.10 else ("~" if rho > 0.25 else "✗")
    print(f"  {sig:<24}  {rho:+.3f}      {pv:.3f}    {v}")

# Detailed ranking table — show both z_rank and slope columns
rank_order = np.argsort(z_rank)[::-1]  # highest z_rank = most vulnerable first
print()
print(f"  {'Rank':<5} {'Bank':<30} {'z_rank':>8} {'slope':>7} {'mfls_r':>7} {'cosθ':>7} {'Known':>6}  OK?")
print("  " + "-" * 82)
for rank, n in enumerate(rank_order, start=1):
    name   = BANK_NAMES[n]
    vuln   = KNOWN_VULNERABILITY.get(name, 2)
    pred_h = rank <= 10
    act_h  = vuln >= 3
    conc   = "✓" if pred_h == act_h else "✗"
    print(f"  {rank:<5} {name:<30} {z_rank[n]:+7.2f}  "
          f"{mfls_slope[n]:+6.2f}  {mfls_rel[n]:+6.2f}  "
          f"{mean_ct[n]:+6.3f}  {vuln:>5}  {conc}")

n_conc = sum(1 for rank, n in enumerate(rank_order, start=1)
             if (rank <= 10) == (KNOWN_VULNERABILITY.get(BANK_NAMES[n], 2) >= 3))
print(f"\n  Concordance: {n_conc}/{N} banks correctly classified (compound z_rank)")

# Slope-based ranking concordance
slope_order  = np.argsort(mfls_slope)[::-1]
n_conc_slope = sum(1 for rank, n in enumerate(slope_order, start=1)
                   if (rank <= 10) == (KNOWN_VULNERABILITY.get(BANK_NAMES[n], 2) >= 3))
print(f"  Concordance: {n_conc_slope}/{N} banks correctly classified (MFLS slope 8Q)")


# ══════════════════════════════════════════════════════════════════════════════
#  DIAGNOSTIC PANEL
# ══════════════════════════════════════════════════════════════════════════════

print()
print("━" * 76)
print("  DIAGNOSTIC PANEL  (GFC calibration, full series)")
print("━" * 76)

P = pg; cal = pg["cal"]
# η_cal over selected quarters
sel_qtrs = [
    ("2006-Q1 (calm)",    "2006-03-31"),
    ("2007-Q2 (pre-GFC)", "2007-06-30"),
    ("2007-Q3 (onset)",   "2007-09-30"),
    ("2008-Q3 (Lehman)",  "2008-09-30"),
    ("2009-Q2 (trough)",  "2009-06-30"),
    ("2011-Q4 (Euro)",    "2011-12-31"),
    ("2020-Q1 (COVID)",   "2020-03-31"),
]
print(f"\n  {'Quarter':<22} {'E_sys':>7} {'γ':>6} {'η_cal':>8} {'R(t)':>7} "
      f"{'MFLS':>8} {'cosθ':>7} {'δ_G_dr':>8} {'Ė>0?':>5}")
print("  " + "-" * 80)
for qlabel, ds in sel_qtrs:
    t = qt(ds)
    if t is None: continue
    print(f"  {qlabel:<22} "
          f"{P['E_sys'][t]:7.3f}  "
          f"{P['gamma'][t]:5.3f}  "
          f"{P['eta_cal'][t]:8.3f}  "
          f"{P['R'][t]:6.3f}  "
          f"{P['MFLS'][t]:7.3f}  "
          f"{P['costh_s'][t]:+6.3f}  "
          f"{P['delta_G_drift'][t]:7.3f}  "
          f"{'✓' if P['violation'] p_dG),
    ("MFLS slope 8Q",   rho_slope, p_slope),
    ("z_rank compound", rho_z,     p_z),
    ("cosθ per-bank",   rho_ct,    p_ct),
]:
    print(f"    {sig:<22}: ρ={rho:+.3f}  p={pv:.3f}")
print(f"    Concordance (z_rank):  {n_conc}/{N}")
print(f"    Concordance (slope):   {n_conc_slope
# Note on η_cal interpretation
print(f"\n  Note: η_cal=1 under Gaussianity (BSDT is at Fisher optimum by construction).")
print(f"  η_cal≠1 measures non-Gaussianity onset (leptokurtosis pre-crisis).")


# ══════════════════════════════════════════════════════════════════════════════
#  FINAL SUMMARY
# ══════════════════════════════════════════════════════════════════════════════
 4), "p": round(float(p_mr),    4)},
            "delta_phi":         {"rho": round(float(rho_dp),    4), "p": round(float(p_dp),    4)},
            "costheta":          {"rho": round(float(rho_ct),    4), "p": round(float(p_ct),    4)},
            "MFLS_slope_8Q":     {"rho": round(float(rho_slope), 4), "p": round(float(p_slope), 4)},
            "z_rank":            {"rho": round(float(rho_z),     4), "p": round(float(p_z), 
print("=" * 76)
print()
print(f"  CV1 milestones fired (any signal): {n_any_fire}/{len(cv1_results)}")
print(f"  CV1 milestones with ≥2q lead     : {n_with_lead}/{len(cv1_results)}")
print()
print("  CV2 OOS hits:")
for row in cv2_results:
    best = max((v for k, v in row.items() if k.startswith("hit_") and isinstance(v, float)), default=0)
    print(f"    {row['label']}: best_hit={best:.2f}  {row['verdict']}")
print()
print("  CV3 Spearman ρ:")
for sig, rho, pv in [
    ("δ_G_frac single", rho_dG,   p_dG),
    ("z_rank compound", rho_z,    p_z),
    ("cosθ per-bank",   rho_ct,   p_ct),
]:
    print(f"    {sig:<22}: ρ={rho:+.3f}  p={pv:.3f}")
print(f"    Concordance (compound): {n_conc}/{N}")

# ── Save JSON ─────────────────────────────────────────────────────────────────
results = {
    "cv1": cv1_results,
    "cv2": cv2_results,
    "cv3": {
        "spearman": {
            "delta_G_frac_abs":  {"rho": round(float(rho_dG),   4), "p": round(float(p_dG),   4)},
            "delta_G_frac_rel":  {"rho": round(float(rho_rel),  4), "p": round(float(p_rel),  4)},
            "MFLS_abs":          {"rho": round(float(rho_mfls), 4), "p": round(float(p_mfls), 4)},
            "MFLS_rel":          {"rho": round(float(rho_mr),   4), "p": round(float(p_mr),   4)},
            "delta_phi":         {"rho": round(float(rho_dp),   4), "p": round(float(p_dp),   4)},
            "costheta":          {"rho": round(float(rho_ct),   4), "p": round(float(p_ct),   4)},
         concordance_slope":    n_conc_slope,
        "   "z_rank":            {"rho": round(float(rho_z),    4), "p": round(float(p_z),    4)},
        },
        "concordance_compound": n_conc,
        "N": N,
    },
    "diagnostics": {
        "rho_CR": round(float(pg["rho_CR"]), 6),
        "Psi_star": round(float(pg["cal"]["Psi_star"]), 6),
        "Psi_star_eff": round(float(pg["cal"]["Psi_star_eff"]), 6),
        "kappa_raw_GFC": round(float(pg["cal"]["kappa_raw"]), 2),
        "theta_GFC": round(float(pg["cal"]["theta"]), 4),
        "alpha_GFC": round(float(pg["cal"]["alpha"]), 4),
    },
}
with open("bank_systemic_results.json", "w") as f:
    json.dump(results, f, indent=2, default=str)
print("\n  Results saved → bank_systemic_results.json")
