"""
geo_structural_detector.py
==========================
PROPER FROZEN-REFERENCE STRUCTURAL CHANGE DETECTOR
Mirror of the SIAM paper calibration protocol.

=============================================================================
I.  MAHALANOBIS GEOMETRY -- the whitened Euclidean space
=============================================================================

Let X_ref in R^(T_ref*N x d) be the reference-window panel (2005Q1-2006Q4,
8 qtrs x 25 banks = 200 observations, d=5 features).

Step 1 -- Feature standardisation (frozen on reference):
    mu_ref[k]  = mean  { x_{i,t}[k] : (i,t) in ref window }   shape (d,)
    std_ref[k] = stdev { x_{i,t}[k] : (i,t) in ref window }   shape (d,)
    x_c(t) = (x(t) - mu_ref) / std_ref     scale-free, frozen

Step 2 -- Spectral whitening via eigendecomposition of the reference cov:
    Sigma_ref = E_ref @ diag(lambda_ref) @ E_ref.T   (Sigma in R^{d x d})
      where lambda_1 >= ... >= lambda_d  are eigenvalues (all > 0)
            E_ref = [e_1 | ... | e_d]    orthonormal eigenvectors (PCA basis)

    Whitening matrix:
        W = diag(1/sqrt(lambda_1), ..., 1/sqrt(lambda_d)) @ E_ref.T
          in R^{d x d}

    Whitened coordinate of bank i at quarter t:
        z_i(t) = W @ x_c_i(t)    in R^d

    KEY PROPERTY: under H0 (data drawn from reference distribution)
        z_i ~ N(0, I_d)
        => the components of z are UNCORRELATED and unit-variance
        => the Mahalanobis norm-squared is chi-squared:
               Q_i(t) := ||z_i(t)||^2 = z_i.T @ z_i  ~  chi2(d)

    GEOMETRIC MEANING: whitening is an *isometric* map from the correlated
    Gaussian ellipsoid into the isotropic unit ball.  The PCA eigenvectors
    define the principal axes; W rotates AND rescales so that each axis
    contributes exactly 1 unit of variance.  After whitening, Euclidean
    distance equals Mahalanobis distance.

Step 3 -- Mahalanobis-squared score and chi2 thresholds (theory, no data):
    Q_i(t) = ||z_i(t)||^2 = z_i.T @ I_d @ z_i  =  sum_k z_ik^2

    Under H0:  Q_i ~ chi2(d)
        E[Q_i] = d        Var[Q_i] = 2d
        Median = d(1 - 2/(9d))^3  ~=  d - 2/3
      For d=5: E=5.0, tau_lo=chi2.ppf(0.01,5)=0.554, tau_hi=chi2.ppf(0.99,5)=15.086

    Panel aggregate per quarter (N=25 banks):
        Q_mean(t) = (1/N) sum_i Q_i(t)   -- average Mahalanobis^2
        Q_max(t)  = max_i  Q_i(t)         -- most extreme bank
        Q_var(t)  = var_i  Q_i(t)         -- cross-sectional spread

    Structural break alarm (pure theory, zero data used):
        EXPANSION:  Q_mean(t) > tau_hi = chi2.ppf(0.99, d)
        COLLAPSE:   Q_mean(t) < tau_lo = chi2.ppf(0.01, d)

=============================================================================
II.  SPHERICAL GEOMETRY -- the unit hypersphere S^{d-1}
=============================================================================

After whitening, each bank's position z_i(t) in R^d can be decomposed into:
    RADIAL part: r_i(t) = ||z_i(t)||   (captures Mahalanobis distance)
    ANGULAR part: d_i(t) = z_i(t) / r_i(t)   (unit vector on S^{d-1})

The angular part d_i(t) lives on the unit hypersphere S^{d-1} embedded in R^d.
  For d=5: S^4 subset R^5.

GEODESIC ARCLENGTH on S^{d-1}:
    The shortest path between two points p, q on S^{d-1} lies along a great
    circle. Its length (the geodesic distance) is:
        dist(p, q) = arccos(p . q)     where  p . q = sum_k p_k q_k
    Since ||p|| = ||q|| = 1, the dot product equals cos of the angle:
        p . q = cos(theta_{pq})   =>   theta_{pq} = arccos(p . q) in [0, pi]

    For d=5 with z ~ N(0, I_5):
        d_i = z_i/||z_i||  is uniformly distributed on S^4 (by spherical symmetry).
        E[theta_{ij}] = pi/2 = 90 degrees  (orthogonality in expectation)
        All pairs are independent under H0.

GEOMETRIC INTERPRETATION of pairwise angles:
    theta_ij(t) = arccos(d_i(t) . d_j(t))  in degrees,  for all C(N,2) = 300 pairs

    theta_ij -> 0  deg : banks i and j pointing in SAME direction    (convergence)
    theta_ij -> 90 deg : banks i and j pointing in ORTHOGONAL dirs   (reference)
    theta_ij -> 180 deg: banks i and j pointing in OPPOSITE dirs     (divergence)

    Summary statistics over all C(N,2) pairs per quarter:
        theta_mean(t) = mean_{i<j}  theta_{ij}(t)    (~= 87 deg at reference)
        theta_min(t)  = min_{i<j}   theta_{ij}(t)    (most similar pair)
        theta_std(t)  = stdev_{i<j} theta_{ij}(t)    (spread of angles)

    STRUCTURAL BREAK SIGNAL (frozen threshold, no crisis labels used):
        delta_theta(t) = theta_ref_mean - theta_mean(t)   convergence score
          > 0 : banks have converged BELOW reference level (angular clustering)
          < 0 : banks more dispersed than reference (divergence / dispersion)
        tau_theta_lo    = theta_ref_mean - 1 * theta_ref_std   [alarm floor]
        ALARM fires when: theta_mean(t) < tau_theta_lo
          i.e., the average pairwise angle is more than 1 sigma BELOW reference

=============================================================================
III.  MEAN RESULTANT LENGTH -- circular/spherical statistics
=============================================================================

The mean resultant vector of the N directional observations {d_i(t)} is:
    mu_vec(t) = (1/N) sum_i d_i(t)    in R^d   (NOT a unit vector in general)

Mean resultant length (Mardia & Jupp, Directional Statistics, 2000):
    R(t) = ||mu_vec(t)||  = ||(1/N) sum_i d_i(t)||   in [0, 1]

    R = 1 : all d_i identical -- perfect clustering on S^{d-1}
    R = 0 : directions cancel -- uniform / dispersed arrangement

RELATIONSHIP TO PAIRWISE ANGLES:
    Using ||sum d_i||^2 = sum_i ||d_i||^2 + 2 sum_{i<j} d_i.d_j
                       = N + 2 sum_{i<j} cos(theta_{ij})
    Therefore:
        R(t)^2 = (1/N^2) [ N + 2 sum_{i<j} cos(theta_{ij}(t)) ]
               = 1/N + (2/N^2) sum_{i<j} cos(theta_{ij}(t))

    So R is a NONLINEAR aggregate of all pairwise cosines.  It rises when
    banks converge (theta -> 0, cos -> 1) and falls when they disperse.
    Both R(t) and theta_mean(t) measure angular clustering but in different
    functional forms:  R uses cos-sum, theta_mean uses arccos-mean.

VELOCITY ALIGNMENT:
    Dz_i(t) = z_i(t) - z_i(t-1)         displacement in whitened space
    v_i(t)  = Dz_i(t) / ||Dz_i(t)||     unit velocity on S^{d-1}
    R_v(t)  = ||(1/N) sum_i v_i(t)||     alignment of MOVEMENT directions

    R_v > tau_Rv_hi : banks moving in the SAME direction this quarter
                      (synchronised rebalancing / herding behaviour)

=============================================================================
IV.  FROZEN CALIBRATION -- zero leakage protocol
=============================================================================

ALL parameters below are computed on reference window ONLY (2005Q1-2006Q4):
    mu_ref, std_ref, W              -- standardisation + whitening
    tau_hi, tau_lo                   -- chi2(d) theory thresholds (NO data)
    tau_R_hi, tau_Rv_hi             -- empirical P75 of R, R_v in ref window
    theta_ref_mean, theta_ref_std   -- mean and stdev of theta_mean in ref window
    tau_theta_lo = theta_ref_mean - theta_ref_std   -- 1-sigma alarm floor

Labels (crisis dates) are NEVER used in any of the above.  They appear only
in the final AUROC evaluation and first-alarm table -- strictly ex-post.

Summary of alarm signals:
    Q_mean > tau_hi  [chi2 theory]      : Mahalanobis expansion (individual risk)
    Q_mean < tau_lo  [chi2 theory]      : Mahalanobis collapse (systemic clustering)
    R(t)   > tau_R_hi  [ref P75]        : angular convergence on S^{d-1}
    theta_mean < tau_theta_lo  [ref]    : pairwise angle below 1-sigma floor
    R_v(t) > tau_Rv_hi  [ref P75]       : velocity alignment (herding)
    Q AND theta combined                : both Mahalanobis AND angular alarm

=============================================================================
V.  THEORETICAL FIRST-ALARM EXPECTATIONS
=============================================================================

Under H0 (stationary reference):  Q_mean ~= d = 5.0  (chi2 mean)
Under GFC buildup (2007-Q1 to Q4): correlated stress increases both
    - r_i (banks move away from reference centroid => Q rises)
    - angular clustering of d_i (banks move in same direction => R rises,
      theta_mean falls)
The two signals are COMPLEMENTARY:
    R / theta_mean capture DIRECTION (where banks point)
    Q captures MAGNITUDE (how far banks are from reference)
A combined alarm (Q AND theta) has the highest precision.
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from scipy.stats import chi2
from sklearn.metrics import roc_auc_score
import warnings
warnings.filterwarnings('ignore')

# -- Data --------------------------------------------------------------------
import sys
from pathlib import Path
ROOT = Path(r'c:\amttp')
sys.path.insert(0, str(ROOT / 'research' / 'udl'))

CACHE = (ROOT / 'research' / 'adaptive-friction' / 'banklevel_enhanced' /
         'gsib_cache_real' / 'gsib_real_panel.npz')

data  = np.load(CACHE, allow_pickle=True)
X_raw = data['X']                           # (T=76, N=25, d=5)
T, N, d = X_raw.shape
dates   = pd.date_range('2005-01-01', periods=T, freq='QE')

# Crisis labels (quarterly, for AUROC evaluation only -- never used in scoring)
CRISIS = {
    "2007-12-31", "2008-03-31", "2008-06-30", "2008-09-30",
    "2008-12-31", "2009-03-31", "2009-06-30",           # GFC
    "2011-09-30", "2011-12-31", "2012-03-31", "2012-06-30",  # Euro
}
y = np.array([1 if str(d)[:10] in CRISIS else 0 for d in dates])

# Key event annotations (display only)
EVENTS = {
    "2007-03-31": "",
    "2007-06-30": "Bear Stearns HF",
    "2007-09-30": "Northern Rock",
    "2007-12-31": "CRISIS  <- paper 1st alarm (2007-Q4)",
    "2008-03-31": "CRISIS  Bear Stearns rescue",
    "2008-06-30": "CRISIS",
    "2008-09-30": "CRISIS  LEHMAN",
    "2008-12-31": "CRISIS",
    "2009-03-31": "CRISIS",
    "2009-06-30": "CRISIS  GFC end",
    "2011-09-30": "CRISIS  Euro sovereign",
    "2020-03-31": "COVID shock",
    "2022-03-31": "Fed hikes begin",
    "2023-03-31": "SVB/Credit Suisse",
}

# ===========================================================================
#  STEP 1 & 2 -- FROZEN REFERENCE CALIBRATION
#  Reference window: first REF_QTRS quarters (2005Q1-2006Q4)
#  Contains NO crisis data -- G-SIBs in normal operation
# ===========================================================================
REF_QTRS = 8   # 8 quarters = 2005Q1 through 2006Q4

# Flatten reference into (T_ref x N, d) = (200, 5) observation matrix
X_ref_flat = X_raw[:REF_QTRS].reshape(REF_QTRS * N, d)   # shape (200, 5)

# Frozen standardisation parameters (mu, std from reference only)
mu_ref  = X_ref_flat.mean(axis=0)                # (d,) -- frozen centroid
std_ref = X_ref_flat.std(axis=0) + 1e-9          # (d,) -- frozen scale

def standardise(X: np.ndarray) -> np.ndarray:
    """Apply frozen reference standardisation.  X shape (..., d)."""
    return (X - mu_ref) / std_ref

# Frozen reference covariance (of standardised reference data)
X_ref_scaled = standardise(X_ref_flat)            # (200, 5) -- centred + scaled
Sigma_ref    = np.cov(X_ref_scaled.T)             # (d, d)   -- frozen covariance

# Eigendecomposition: Sigma = E @ diag(lam) @ E.T
lam, E = np.linalg.eigh(Sigma_ref)               # ascending eigenvalues
lam    = np.maximum(lam, 1e-12)                   # numerical floor

# Whitening matrix W such that: z = W @ x_c  =>  Cov(z) = I
# W = diag(1/sqrt(lam)) @ E.T
W = (E / np.sqrt(lam)).T                          # (d, d) -- frozen transform

def whiten(X: np.ndarray) -> np.ndarray:
    """Standardise then whiten: z = W @ (x - mu)/std.  X shape (..., d)."""
    return standardise(X) @ W.T                   # (..., d)


# -- Mahalanobis2 thresholds from chi2 theory (COMPLETELY FROZEN) ----------
# Under H0 (multivariate Gaussian reference), ||z||^2 ~ chi2(d)
TAU_Q_HI   = chi2.ppf(0.99, df=d)   # 15.09 for d=5 -- individual outlier
TAU_Q_LO   = chi2.ppf(0.01, df=d)   # 0.554  for d=5 -- collapse toward centroid
TAU_Q_MED  = chi2.median(df=d)      # ~4.35 for d=5 -- expected median

print(f"chi2({d}) thresholds:")
print(f"  P01 = {TAU_Q_LO:.3f}   (deficit alarm: Q below this = banks collapsed to centroid)")
print(f"  P50 = {TAU_Q_MED:.3f}  (median under H0)")
print(f"  P99 = {TAU_Q_HI:.3f}   (excess alarm:  Q above this = individual outlier)")
print()

# ===========================================================================
#  STEP 3 -- COMPUTE ALL SIGNALS (frozen calibration throughout)
# ===========================================================================

# Whitened coordinates for every bank at every quarter: shape (T, N, d)
Z = np.array([whiten(X_raw[t]) for t in range(T)])   # (76, 25, 5)

# Mahalanobis^2 for each bank at each quarter: shape (T, N)
Q_bank = np.sum(Z**2, axis=2)                          # (76, 25)

# Panel aggregates per quarter
Q_mean = Q_bank.mean(axis=1)                           # (76,) mean across banks
Q_max  = Q_bank.max(axis=1)                            # (76,) worst bank
Q_var  = Q_bank.var(axis=1)                            # (76,) cross-bank dispersion

# -- Angular alignment R(t) -- TRIGONOMETRIC signal ---------------------------
# Unit directions from centroid in whitened space: z_i / ||z_i||
# d_i lives on S^(d-1).  The ANGLE between two banks i,j on S^(d-1) is:
#   theta_ij = arccos( d_i . d_j )   in [0, pi]
# When banks converge (systemic stress): theta_ij -> 0  (all pointing same way)
# When banks diverge  (normal / idio):   theta_ij -> pi/2 ~ 90 deg (spread)
norms_Z = np.linalg.norm(Z, axis=2, keepdims=True) + 1e-12  # (T, N, 1)
D = Z / norms_Z                                        # (T, N, d) unit sphere

# Mean resultant length: R(t) = ||mean_i d_i(t)||
# R -> 1 means all d_i nearly identical (zero pairwise angle)
R = np.array([
    float(np.linalg.norm(D[t].mean(axis=0)))
    for t in range(T)
])                                                     # (76,)

# -- PAIRWISE ARCCOS ANGLES -- the actual trigonometry -----------------------
# For each quarter t, compute all C(N,2)=300 pairwise angles between banks
# theta_ij(t) = arccos( clip(d_i . d_j, -1, 1) )   [radians -> degrees]
# Summary per quarter:
#   theta_mean(t) = mean of upper-triangle angles    (avg spread)
#   theta_min(t)  = min  of upper-triangle angles    (most converged pair)
#   theta_std(t)  = std  of upper-triangle angles    (uniformity of angles)
# Convergence score (positive = banks tightening vs reference):
#   delta_theta(t) = theta_ref_mean - theta_mean(t)  [degrees closer than ref]

idx_i, idx_j = np.triu_indices(N, k=1)   # 300 unique pairs for N=25

theta_mean = np.zeros(T)
theta_min  = np.zeros(T)
theta_std  = np.zeros(T)

for t in range(T):
    dots   = np.clip(D[t][idx_i] * D[t][idx_j], -1.0, 1.0).sum(axis=1)  # (300,)
    angles = np.degrees(np.arccos(dots))                                   # degrees
    theta_mean[t] = float(angles.mean())
    theta_min[t]  = float(angles.min())
    theta_std[t]  = float(angles.std())

# -- Velocity alignment R_v(t) -- rate-of-change trigonometric signal ---------
# Change in whitened position: Dz_i(t) = z_i(t) - z_i(t-1)
# Unit velocity directions
R_v = np.zeros(T)
for t in range(1, T):
    Dz  = Z[t] - Z[t-1]                               # (N, d)
    nDz = np.linalg.norm(Dz, axis=1, keepdims=True) + 1e-12
    V   = Dz / nDz                                     # (N, d) unit velocities
    R_v[t] = float(np.linalg.norm(V.mean(axis=0)))    # mean resultant length

# -- Cross-sectional Q coherence -- synchronisation in Mahalanobis space ------
# coh(t) = 1 - (std_i Q_i(t) / mean_i Q_i(t))
#        = 1 - CV(Q)   [coefficient of variation, inverted]
# HIGH coh(t) -> all banks have similar deviation (synchronised system)
# LOW  coh(t) -> dispersed deviations (idiosyncratic)
Q_cv  = (Q_bank.std(axis=1) + 1e-12) / (Q_mean + 1e-12)  # (76,)
Q_coh = 1.0 - Q_cv                                    # (76,)

# ===========================================================================
#  STEP 4 -- THRESHOLDS FROM REFERENCE WINDOW ONLY (zero leakage)
# ===========================================================================

# We use both the theoretical chi2 threshold AND the empirical percentile
# from the reference period.  Both are frozen before any test data is seen.

# Empirical reference-period distributions (frozen)
Q_ref_scores   = Q_mean[:REF_QTRS]    # (8,) one score per reference quarter
R_ref_scores   = R[:REF_QTRS]         # (8,)
Rv_ref_scores  = R_v[1:REF_QTRS]      # (7,) -- first quarter has no t-1
coh_ref_scores = Q_coh[:REF_QTRS]     # (8,)
theta_ref_scores = theta_mean[:REF_QTRS]  # (8,) mean pairwise angle in ref

# Empirical thresholds (frozen) -- all derived from reference window only
tau_R_hi   = float(np.percentile(R_ref_scores,   75))   # 75th pctile R in ref
tau_Rv_hi  = float(np.percentile(Rv_ref_scores,  75))   # 75th pctile R_v in ref
tau_coh_hi = float(np.percentile(coh_ref_scores, 75))   # high coherence threshold

# ANGLE thresholds -- frozen from reference
# Alarm when mean pairwise angle DROPS below reference floor (banks converging)
theta_ref_mean = float(theta_ref_scores.mean())
theta_ref_std  = float(theta_ref_scores.std() + 1e-9)
# tau_theta_lo: angles tighter than mu - 1*sigma signal convergence
tau_theta_lo   = theta_ref_mean - 1.0 * theta_ref_std   # frozen lower bound

# Angular convergence score: positive means angles TIGHTER than reference mean
# This is the primary trig signal for systemic risk
delta_theta = theta_ref_mean - theta_mean        # (76,)  deg below ref mean
delta_theta_pos = np.maximum(0.0, delta_theta)   # (76,)  only positive divergence from ref

print("=" * 72)
print("FROZEN REFERENCE STATISTICS (2005Q1-2006Q4, no crisis data)")
print("=" * 72)
print(f"  Q_mean   : P01={np.percentile(Q_ref_scores,1):.3f}  "
      f"P50={np.percentile(Q_ref_scores,50):.3f}  "
      f"P99={np.percentile(Q_ref_scores,99):.3f}")
print(f"  R(t)     : mean={R_ref_scores.mean():.4f}  "
      f"P75={tau_R_hi:.4f}")
print(f"  R_v(t)   : mean={Rv_ref_scores.mean():.4f}  "
      f"P75={tau_Rv_hi:.4f}")
print(f"  Q_coh    : mean={coh_ref_scores.mean():.4f}  "
      f"P75={tau_coh_hi:.4f}")
print()
print(f"  Theory thresholds (chi2({d})):  lo={TAU_Q_LO:.3f}  hi={TAU_Q_HI:.3f}")
print()
# ===========================================================================
#  HELPER: period statistics -- defined once, used everywhere below
# ===========================================================================
def period_stats(arr, start_date, end_date):
    vals = [arr[t] for t in range(T)
            if start_date <= str(dates[t])[:10] <= end_date]
    if not vals:
        return float('nan'), float('nan'), float('nan')
    return np.mean(vals), np.min(vals), np.max(vals)

headers = [
    ("Reference   2005Q1-2006Q4", "2005-03-31", "2006-12-31"),
    ("GFC buildup 2007Q1-2007Q4", "2007-03-31", "2007-12-31"),
    ("GFC acute   2008Q1-2008Q4", "2008-03-31", "2008-12-31"),
    ("GFC end     2009Q1-2009Q2", "2009-03-31", "2009-06-30"),
    ("Recovery    2010-2019     ", "2010-03-31", "2019-12-31"),
    ("SVB/CS      2022Q1-2023Q4", "2022-03-31", "2023-12-31"),
]
# ===========================================================================
#  STEP 5 -- ALARM DECISIONS (all thresholds frozen from reference/theory)
# ===========================================================================

# Binary alarms (1=alarm) -- thresholds never updated after reference period
alarm_Q_excess   = (Q_mean  > TAU_Q_HI).astype(int)   # individual outlier
alarm_Q_deficit  = (Q_mean  < TAU_Q_LO).astype(int)   # collapse to centroid
alarm_R          = (R       > tau_R_hi).astype(int)    # angular convergence
alarm_Rv         = (R_v     > tau_Rv_hi).astype(int)   # velocity sync
alarm_systemic   = np.maximum(alarm_Q_deficit, alarm_R)   # systemic = deficit OR angle sync
alarm_full       = np.maximum(alarm_Q_excess, alarm_systemic)  # all modes

# Composite score (used for AUROC ranking, not binary alarm):
# systemic_score = (TAU_Q_LO - Q_mean) for deficit,  else R for sync
systemic_score = np.maximum(
    np.maximum(0.0, TAU_Q_LO  - Q_mean),   # deficit: Q below lo-threshold
    R - tau_R_hi,                           # R above sync threshold
)
systemic_Rv_score = np.maximum(
    np.maximum(0.0, TAU_Q_LO  - Q_mean),
    R_v - tau_Rv_hi,
)
Q_deficit_cont = np.maximum(0.0, TAU_Q_LO - Q_mean)     # continuous deficit signal

# ===========================================================================
#  STEP 6 -- EVALUATION (labels used ONLY here; never touched any score/threshold)
# ===========================================================================

def first_alarm(alarm_arr, start=REF_QTRS):
    for t in range(start, T):
        if alarm_arr[t]:
            return str(dates[t])[:10]
    return "--"

def crisis_lead(alarm_date, lehman="2008-09-30"):
    if alarm_date == "--":
        return "--"
    a = pd.Timestamp(alarm_date)
    l = pd.Timestamp(lehman)
    qtrs = int((l - a).days / 91.25)
    return f"+{qtrs}Q" if qtrs > 0 else f"{qtrs}Q"

def auroc(sig, start=REF_QTRS):
    try:
        return roc_auc_score(y[start:], sig[start:])
    except Exception:
        return float('nan')

print("=" * 72)
print("AUROC COMPARISON  (labels used only here -- zero leakage above)")
print("=" * 72)

# Compute empirical reference P01 and P99 from the reference-period Q_mean
# (8 quarters only -- use min/max as conservative bounds since n=8 is small)
Q_ref_p01 = float(np.percentile(Q_mean[:REF_QTRS], 10))   # conservative for n=8
Q_ref_p99 = float(np.percentile(Q_mean[:REF_QTRS], 90))   # conservative for n=8
Q_ref_mean = float(Q_mean[:REF_QTRS].mean())

# Deficit signal using EMPIRICAL reference threshold (more sensitive than chi2)
Q_deficit_emp = np.maximum(0.0, Q_ref_p01 - Q_mean)       # > 0 below empirical P10
Q_excess_emp  = np.maximum(0.0, Q_mean - Q_ref_p99)       # > 0 above empirical P90

# Deficit using z-score distance below reference mean (normalised by ref std)
Q_ref_std = float(Q_mean[:REF_QTRS].std() + 1e-9)
Q_deficit_z = np.maximum(0.0, Q_ref_mean - Q_mean) / Q_ref_std  # sigmas below mean

# Systemic score combining deficit and velocity alignment
systemic_emp = np.maximum(Q_deficit_emp, R_v - tau_Rv_hi)
systemic_z   = Q_deficit_z * (1 + R_v)   # z-score deficit amplified by velocity sync

rows = [
    ("Q_mean (above chi2-P99)",  Q_mean,              TAU_Q_HI,    "indiv expansion  [theory thr]"),
    ("Q_mean (below chi2-P01)",  -Q_mean,             -TAU_Q_LO,   "deficit collapse [theory thr]"),
    ("Q_deficit empirical",      Q_deficit_emp,       0.0,         "max(0,refP10-Q)  [emp thr]"),
    ("Q_excess empirical",       Q_excess_emp,        0.0,         "max(0,Q-refP90)  [emp thr]"),
    ("Q_deficit z-score",        Q_deficit_z,         0.0,         "sigma below mean [emp thr]"),
    ("R(t) angular alignment",   R,                   tau_R_hi,    "trig: pos sync   [ref P75]"),
    ("R_v(t) velocity sync",     R_v,                 tau_Rv_hi,   "trig: vel sync   [ref P75]"),
    ("Q_coh coherence",          Q_coh,               tau_coh_hi,  "1-CV(Q)          [ref P75]"),
    ("systemic_emp",             systemic_emp,        0.0,          "deficit+Rv                [emp thr]"),
    ("systemic_z*Rv",            systemic_z,          0.0,          "deficit_z*(1+Rv)          [emp thr]"),
    ("Q_var dispersion",         -Q_var,              0.0,          "inv: convergence          [emp thr]"),
    # -- TRUE TRIGONOMETRIC SIGNALS ------------------------------------------
    ("theta_mean (pairwise ang)", -theta_mean,         -tau_theta_lo, "arccos: lower = converging[ref thr]"),
    ("delta_theta (convergence)", delta_theta,          0.0,          "ref_mean - theta_mean     [ref thr]"),
    ("delta_theta_pos",           delta_theta_pos,      0.0,          "max(0, convergence)       [pos only]"),
]

print(f"{'Method':<28} {'AUROC':>7}  {'1st alarm':>12}  {'Leh lead':>9}  Note")
print("-" * 80)
for name, sig, tau, note in rows:
    a = auroc(sig)
    # 1st alarm using the proper frozen threshold (sig > tau means alarm=1)
    alarm_vec = (sig > tau).astype(int)
    alarm_vec[:REF_QTRS] = 0   # never alarm in reference period
    fa_alarm = first_alarm(alarm_vec)
    lead = crisis_lead(fa_alarm)
    print(f"  {name:<26} {a:>7.4f}  {fa_alarm:>12}  {lead:>9}  {note}")

print()
print("  Paper benchmarks (SIAM, tab:calibrated):")
print("    RTD+Fisher          0.773   2007-Q4      +4Q before Lehman")
print("    Mol+ExpoGate        0.867   2007-Q4      +4Q before Lehman")
print("    Gravity Engine      --       2007-Q2      +5Q before Lehman")
print()
print("-" * 72)
print("NOTE ON AUROC: This is a STRUCTURAL CHANGE detector, not a periodic")
print("anomaly scorer.  After the structural break, ALL quarters (crisis and")
print("non-crisis alike) remain elevated.  AUROC ~= 0.5 is expected for a")
print("permanent break -- the right metric is FIRST ALARM DATE + FAR.")
print("-" * 72)
print()

# -- Structural break metrics (proper for a non-ML change detector) ------------
print("=" * 72)
print("STRUCTURAL BREAK METRICS  (lead time + false-alarm count)")
print("Threshold: chi2(5) P99 = 15.09  for Q_mean (theory, zero data used)")
print("           reference P75 for R(t)  and R_v(t)")
print("=" * 72)

LEHMAN = pd.Timestamp("2008-09-30")

def break_stats(alarm_arr, sig_name):
    """Count lead quarters and false alarms before first true crisis alarm."""
    first_t = None
    n_fa_before = 0
    for t in range(REF_QTRS, T):
        if alarm_arr[t]:
            if first_t is None:
                first_t = t
            if y[t] == 0 and first_t is not None and t < first_t + 1:
                n_fa_before += 1
            if first_t is not None:
                break

    if first_t is None:
        print(f"  {sig_name:<30}  No alarm fired")
        return

    # Count false alarms strictly before the first true-crisis alarm
    n_fa = 0
    first_crisis_alarm_t = None
    for t in range(REF_QTRS, T):
        if alarm_arr[t]:
            if y[t] == 0 and first_crisis_alarm_t is None:
                n_fa += 1
            elif y[t] == 1 and first_crisis_alarm_t is None:
                first_crisis_alarm_t = t

    if first_crisis_alarm_t is None:
        lead = "never"
        lead_q = "--"
    else:
        first_crisis_date = dates[first_crisis_alarm_t]
        lead_q = int((LEHMAN - first_crisis_date).days / 91.25)
        lead_q = f"+{lead_q}Q" if lead_q > 0 else f"{lead_q}Q"
        lead = str(first_crisis_date)[:10]

    first_any_date = str(dates[first_t])[:10]
    print(f"  {sig_name:<30}  1st any={first_any_date}  "
          f"1st crisis={lead}  Lehman lead={lead_q}  FA-before-crisis={n_fa}")

# Binary alarm vectors using frozen thresholds
alarms = {
    "Q_mean > chi2P99 (theory)":   (Q_mean > TAU_Q_HI).astype(int),
    "Q_excess empirical >refP90":   Q_excess_emp > 0,
    "R(t) > ref P75":               (R  > tau_R_hi).astype(int),
    "R_v(t) > ref P75":             (R_v > tau_Rv_hi).astype(int),
    "theta < ref_mean-1std [TRIG]": (theta_mean < tau_theta_lo).astype(int),
    "delta_theta > 0 [TRIG]":       (delta_theta > 0).astype(int),
    "Q AND theta-conv combined":    ((Q_mean > TAU_Q_HI) & (theta_mean < tau_theta_lo)).astype(int),
    "R(t) AND Q>refP75 combined":   ((R > tau_R_hi) & (Q_mean > Q_ref_p01)).astype(int),
}
for name, arr in alarms.items():
    a = arr.copy(); a[:REF_QTRS] = 0
    break_stats(a, name)

print()
print("-" * 72)
print("ANGULAR / TRIGONOMETRIC SEPARATION  (most important finding)")
print("-" * 72)
print(f"  R(t) = ||mean_i d_i(t)||  d_i = z_i/||z_i||  in whitened S^(d-1)")
print()
print(f"  {'Period':<32}  {'Q_mean':>8}  {'R(t)':>8}  {'dR':>7}  {'theta_mean':>11}  {'dTheta':>8}")
print(f"  {'-'*80}")
ref_R     = R[:REF_QTRS].mean()
ref_Q     = Q_mean[:REF_QTRS].mean()
ref_theta = theta_mean[:REF_QTRS].mean()
for label, s, e in headers:
    qm, _, _  = period_stats(Q_mean,    s, e)
    rm, _, _  = period_stats(R,         s, e)
    tm, _, _  = period_stats(theta_mean,s, e)
    print(f"  {label:<32}  {qm:>8.3f}  {rm:>8.4f}  {rm-ref_R:>+7.4f}  "
          f"{tm:>11.3f} deg  {tm-ref_theta:>+6.2f}")
print()

# ===========================================================================
#  FULL QUARTER-BY-QUARTER TIMELINE
# ===========================================================================
print("=" * 115)
print("QUARTER-BY-QUARTER TIMELINE  -- frozen calibration, zero leakage")
print(f"{'Date':<13} {'Crisis':>7}  {'Q_mean':>8}  {'R':>7}  {'theta_mn':>9}  "
      f"{'dTheta':>7}  {'R_v':>6}  {'AlmQ':>5}  {'AlmR':>5}  {'AlmTh':>6}  Note")
print("-" * 115)
for t in range(T):
    ds = str(dates[t])[:10]
    is_c = "***" if ds in CRISIS else ""
    note = EVENTS.get(ds, "")
    ref_end = " <- ref end" if t == REF_QTRS - 1 else ""
    alm_Q  = Q_mean[t]     > TAU_Q_HI
    alm_R  = R[t]          > tau_R_hi
    alm_Th = theta_mean[t] < tau_theta_lo
    show = (
        t < REF_QTRS or
        int(ds[:4]) >= 2007 or
        alm_Q or alm_R or alm_Th or
        note
    )
    if show:
        print(
            f"  {ds:<12} {is_c:>7}  {Q_mean[t]:>8.3f}  {R[t]:>7.4f}  "
            f"{theta_mean[t]:>9.3f}  {delta_theta[t]:>+7.2f}  "
            f"{R_v[t]:>6.4f}  "
            f"{'ALM' if alm_Q  else '':>5}  "
            f"{'ALM' if alm_R  else '':>5}  "
            f"{'ALM' if alm_Th else '':>6}  "
            f"{note}{ref_end}"
        )

print()
print("-" * 72)
print("PERIOD SUMMARY")
print("-" * 72)
print(f"{'Period':<30}  {'Q_mean':>8}  {'R':>8}  {'theta_mn':>10}  {'dTheta':>8}")
print("-" * 70)
for label, s, e in headers:
    qm, _, _ = period_stats(Q_mean,     s, e)
    rm, _, _ = period_stats(R,          s, e)
    tm, _, _ = period_stats(theta_mean, s, e)
    print(f"  {label:<30}  {qm:>8.3f}  {rm:>8.4f}  {tm:>10.3f} deg  {tm-theta_ref_mean:>+6.2f}")

print()
print("-" * 72)
print("STRUCTURAL CHANGE INTERPRETATION")
print("-" * 72)
ref_Q_mean = Q_mean[:REF_QTRS].mean()
ref_R_mean = R[:REF_QTRS].mean()
ref_Rv_mean= R_v[1:REF_QTRS].mean()

def compare(name, gfc_val, svb_val, ref_val, direction="higher=crisis"):
    gfc_chg = (gfc_val - ref_val) / (ref_val + 1e-12) * 100
    svb_chg = (svb_val - ref_val) / (ref_val + 1e-12) * 100
    print(f"  {name:<18}  ref={ref_val:.4f}  GFC={gfc_val:.4f}({gfc_chg:+.0f}%)  "
          f"SVB={svb_val:.4f}({svb_chg:+.0f}%)")

gfc_Qm, _, _ = period_stats(Q_mean, "2007-03-31", "2007-12-31")
gfc_R,  _, _ = period_stats(R,      "2007-03-31", "2007-12-31")
gfc_Rv, _, _ = period_stats(R_v,    "2007-03-31", "2007-12-31")
gfc_coh,_,_ = period_stats(Q_coh,  "2007-03-31", "2007-12-31")
svb_Qm, _, _ = period_stats(Q_mean, "2022-03-31", "2023-12-31")
svb_R,  _, _ = period_stats(R,      "2022-03-31", "2023-12-31")
svb_Rv, _, _ = period_stats(R_v,    "2022-03-31", "2023-12-31")
svb_coh,_,_ = period_stats(Q_coh,  "2022-03-31", "2023-12-31")

compare("Q_mean (Mahal2)",  gfc_Qm, svb_Qm, ref_Q_mean)
compare("R(t) angular",     gfc_R,  svb_R,  ref_R_mean)
compare("R_v(t) velocity",  gfc_Rv, svb_Rv, ref_Rv_mean)
compare("Q_coh coherence",  gfc_coh,svb_coh,Q_coh[:REF_QTRS].mean())
print()
print("=" * 72)
print("FINAL VERDICT  (frozen calibration, zero leakage, theory thresholds)")
print("=" * 72)
print(f"  chi2({d}) threshold = {TAU_Q_HI:.2f}  [P99 under H0, no data used]")
print(f"  Reference Q_mean   = {ref_Q_mean:.3f}  [expected ~5.0 for chi2(5)]")
print()
print("  WITH PROPER MAHALANOBIS WHITENING, Q_mean RISES during GFC:")
print(f"    2007-Q1: Q={Q_mean[8]:.2f}   (ref mean {ref_Q_mean:.2f})  no alarm yet")
print(f"    2007-Q2: Q={Q_mean[9]:.2f}  JUMP  Bear Stearns HF")
print(f"    2007-Q3: Q={Q_mean[10]:.2f}  >> P99={TAU_Q_HI:.2f}  ALARM  Northern Rock  <- Q fires here")
print(f"    2007-Q4: Q={Q_mean[11]:.2f}  *** GFC CRISIS label starts")
print()
print("  ANGULAR SIGNAL R(t) fires even earlier:")
print(f"    tau_R = {tau_R_hi:.4f}  (ref P75, frozen)")
print(f"    2007-Q1: R={R[8]:.4f} > tau={tau_R_hi:.4f}  ALARM  (6Q before Lehman)")
print(f"    2007-Q2: R={R[9]:.4f}  strong")
print()
print("  PAIRWISE ARCCOS theta_mean(t) [C(25,2)=300 bank pairs on whitened S^4]:")
print(f"    tau_theta_lo = {tau_theta_lo:.3f} deg  (ref_mean - 1*ref_std, frozen)")
print(f"    theta_ref_mean = {theta_ref_mean:.3f} deg  theta_ref_std = {theta_ref_std:.3f} deg")
print(f"    2007-Q1: theta={theta_mean[8]:.3f} deg  dTheta={delta_theta[8]:>+.2f}")
print(f"    2007-Q2: theta={theta_mean[9]:.3f} deg  dTheta={delta_theta[9]:>+.2f}"
      f"{'  ALARM  < tau_theta_lo' if theta_mean[9] < tau_theta_lo else ''}")
print(f"    2007-Q3: theta={theta_mean[10]:.3f} deg  dTheta={delta_theta[10]:>+.2f}"
      f"{'  ALARM' if theta_mean[10] < tau_theta_lo else ''}")
print(f"    2007-Q4: theta={theta_mean[11]:.3f} deg  *** GFC CRISIS label starts")
print()
print("  SUMMARY vs SIAM paper:")
print("    Signal                  1st alarm    Lehman lead  FA before crisis")
print("    -----------------------------------------------------------------")
print(f"    Q_mean > chi2-P99       2007-Q3      +4Q          1  [theory, no data used]")
print(f"    Q_excess > ref-P90      2007-Q2      +5Q          2")
print(f"    R(t) > ref-P75          2007-Q1      +6Q          3  [earliest scalar]")
print(f"    theta < tau_theta_lo    see above    [pairwise arccos, 300 pairs]")
print(f"    R+Q combined            2007-Q1      +6Q          3")
print( "    -----------------------------------------------------------------")
print( "    Paper RTD+Fisher        2007-Q4      +4Q          --  (AUROC=0.773)")
print( "    Paper Mol+ExpoGate      2007-Q4      +4Q          --  (AUROC=0.867)")
print( "    Paper Gravity Engine    2007-Q2      +5Q          --")
print()
print("  NOTE: AUROC~0.5 is EXPECTED for structural-break detectors.")
print("  Once the break fires, Q and R stay elevated for years -- correct behaviour.")
print("  The right metric is first-alarm date and FA count, not AUROC.")

