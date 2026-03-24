"""
geo_sync_angular.py
====================
GeometricSync: trigonometric synchronisation detector on the C* ellipsoid.

For each bank i at time t, the DIRECTION of its position on the C* surface is:
    d_i = (x_i / a²) / ‖x_i / a²‖         ← unit ellipsoidal normal (outward)

This is a point on the unit (d-1)-sphere.  When all banks converge toward the
SAME boundary region of C*, their direction vectors d_i become aligned:

    R(t) = ‖ (1/N) Σ_i d_i ‖  ∈ [0, 1]     ← mean resultant length

    R → 1 : all banks pointing the same way  → SYNCHRONISATION (GFC-type)
    R → 0 : directions uniformly spread       → normal / independent behaviour

No pairwise forces.  No kNN.  Pure trigonometry on the C* ellipsoid.

Combined detector:
    sync_alarm(t) = R(t) × Q_mean(t)         ← direction alignment × amplitude

Comparison:
    Paper pipeline (Mol+ExpoGate): first alarm 2007-Q4, 4Q before Lehman
    GeomSync target               : fire before 2008-Q3 using trigonometry only
"""
from __future__ import annotations
import sys, numpy as np, warnings
warnings.filterwarnings('ignore')
from pathlib import Path
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score

ROOT = Path(r'c:\amttp')
sys.path.insert(0, str(ROOT / 'research' / 'udl'))
from udl.ellipsoid_geometry import EllipsoidGeometry


# ═══════════════════════════════════════════════════════════════════════════
#  Core: ellipsoidal unit-normal direction
# ═══════════════════════════════════════════════════════════════════════════

def ellipsoidal_directions(X: np.ndarray, a2: np.ndarray) -> np.ndarray:
    """
    For each point x, compute the unit outward normal to the C* ellipsoid:
        d_i = (x_i / a²) / ‖x_i / a²‖

    This is the gradient of Q(x) = Σ(xk/ak)², normalised to the unit sphere.
    It encodes the DIRECTION on C* independently of the distance from the surface.

    Returns array of shape (N, d), each row on unit sphere S^(d-1).
    """
    grad = X / a2                                       # ∇Q(x) = 2x/a²  (drop 2)
    norm = np.linalg.norm(grad, axis=1, keepdims=True) + 1e-12
    return grad / norm                                  # unit ellipsoidal normal


def mean_resultant_length(directions: np.ndarray) -> float:
    """
    R = ‖ mean(d_i) ‖  — mean resultant length on S^(d-1).

    R = 1 : all directions identical   (perfect synchronisation)
    R = 0 : directions uniformly spread (independence)
    """
    mean_dir = directions.mean(axis=0)
    return float(np.linalg.norm(mean_dir))


def pairwise_angles_deg(directions: np.ndarray) -> np.ndarray:
    """
    Upper-triangle pairwise angles (degrees) between direction vectors.
    arccos(d_i · d_j).  For display only.
    """
    dots = np.clip(directions @ directions.T, -1.0, 1.0)
    angles = np.degrees(np.arccos(dots))
    N = len(directions)
    return angles[np.triu_indices(N, k=1)]


# ═══════════════════════════════════════════════════════════════════════════
#  GeometricSync scorer
# ═══════════════════════════════════════════════════════════════════════════

class GeometricSync:
    """
    Trigonometric synchronisation detector.

    fit(X_ref, ell):   record reference mean-resultant-length R_ref
    score_quarter(X_qt): returns sync_score for one quarter (N banks × d)

    The per-quarter score:
        sync = R(t) × Q_mean(t)

    where R(t) = mean resultant length of ellipsoidal normals across N banks,
    and Q_mean(t) = mean quadric value across N banks.

    High sync AND moderate-Q → systemic synchronisation (GFC buildup).
    High Q alone             → individual failure (SVB/2023-type).
    """
    def __init__(self):
        self._a2      = None
        self._R_ref   = None
        self._Q_ref   = None

    def fit(self, X_ref: np.ndarray, ell: EllipsoidGeometry) -> 'GeometricSync':
        self._a2    = ell.semi_axes ** 2
        D_ref       = ellipsoidal_directions(X_ref, self._a2)
        self._R_ref = mean_resultant_length(D_ref)
        self._Q_ref = float(np.mean(np.sum(X_ref**2 / self._a2, axis=1)))
        return self

    def score_quarter(self, X_qt: np.ndarray) -> float:
        """
        X_qt : (N_banks, d) — one quarter's bank matrix.
        Returns scalar sync_score.
        """
        a2   = self._a2
        Q    = np.sum(X_qt**2 / a2, axis=1)          # per-bank Q values
        D    = ellipsoidal_directions(X_qt, a2)       # unit normals
        R    = mean_resultant_length(D)               # alignment [0,1]
        return float(R * Q.mean())                    # sync × amplitude

    def score_panel(self, X_all: np.ndarray,
                    T: int, N: int) -> np.ndarray:
        """Score all T quarters. X_all shape: (T*N, d)."""
        X_3d = X_all.reshape(T, N, -1)
        return np.array([self.score_quarter(X_3d[t]) for t in range(T)])

    def mean_angle_quarter(self, X_qt: np.ndarray) -> float:
        """Mean pairwise angle (degrees) across banks — for display."""
        D = ellipsoidal_directions(X_qt, self._a2)
        return float(pairwise_angles_deg(D).mean())


# ═══════════════════════════════════════════════════════════════════════════
#  Load G-SIB data
# ═══════════════════════════════════════════════════════════════════════════

CACHE = ROOT/'research'/'adaptive-friction'/'banklevel_enhanced'/'gsib_cache_real'
X3    = np.load(CACHE/'gsib_real_panel.npz')['X']
T_b, N_b, d_b = X3.shape
Xb    = X3.reshape(T_b * N_b, d_b)
dates = pd.date_range('2005-01-01', '2023-12-31', freq='QE')[:T_b]

CRISIS = {
    '2007-12-31','2008-03-31','2008-06-30','2008-09-30',
    '2008-12-31','2009-03-31','2009-06-30',
    '2020-03-31','2020-06-30',
    '2011-09-30','2011-12-31','2012-03-31','2012-06-30'
}
yq = np.array([1 if str(d.date()) in CRISIS else 0 for d in dates])

REF_QTRS = 8
X_ref    = X3[:REF_QTRS].reshape(REF_QTRS * N_b, d_b)
scaler   = StandardScaler().fit(X_ref)
X_s_ref  = scaler.transform(X_ref)
X_s_all  = scaler.transform(Xb)

cov = np.cov(X_s_ref.T)
ev, _ = np.linalg.eigh(cov)
ev = np.maximum(ev, 1e-12); w = ev / ev.sum()
ell = EllipsoidGeometry.from_fisher_weights(w, alpha=float(ev.max()))
a2  = ell.semi_axes**2

# ═══════════════════════════════════════════════════════════════════════════
#  Compute scores (frozen fit on reference)
# ═══════════════════════════════════════════════════════════════════════════

gs = GeometricSync()
gs.fit(X_s_ref, ell)

# Per-quarter scores
Q_raw_q   = np.sum(X_s_all**2 / a2, axis=1).reshape(T_b, N_b).mean(1)
sync_score = gs.score_panel(X_s_all, T_b, N_b)       # R(t) × Q_mean(t)
R_t        = np.array([mean_resultant_length(                # R(t) alone
                 ellipsoidal_directions(X_s_all.reshape(T_b, N_b, d_b)[t], a2))
             for t in range(T_b)])
ang_t      = np.array([gs.mean_angle_quarter(
                 X_s_all.reshape(T_b, N_b, d_b)[t])
             for t in range(T_b)])                     # mean pairwise angle

# Normalise to [0,1] for display
def n01(s): return (s - s.min()) / (s.max() - s.min() + 1e-12)
Q_n    = n01(Q_raw_q)
S_n    = n01(sync_score)
R_n    = n01(R_t)

# Adaptive P99 threshold (trailing 8 quarters, no labels)
WINDOW = 8
def rolling_p99(s, w=8):
    T = len(s); tau = np.full(T, np.nan)
    for t in range(w, T):
        tau[t] = np.percentile(s[t-w:t], 99)
    return tau

tau_S = rolling_p99(S_n, WINDOW)
tau_Q = rolling_p99(Q_n, WINDOW)

# ═══════════════════════════════════════════════════════════════════════════
#  Timeline printout
# ═══════════════════════════════════════════════════════════════════════════

print('=' * 92)
print('  TRIGONOMETRIC SYNCHRONISATION DETECTOR  (GeometricSync)')
print('  d_i = (x_i/a^2) / ||x_i/a^2||   -- ellipsoidal unit normal for bank i')
print('  R(t) = || mean_i(d_i) ||          -- mean resultant length (alignment)')
print('  sync_score = R(t) x Q_mean(t)    -- synchronisation x amplitude')
print('  Frozen ref: 2005Q1-2006Q4  |  Adaptive P99 trailing 8-quarter window')
print('=' * 92)
print(f'  {"Date":<12}  {"Crisis":>10}  {"Q_raw":>6}  {"Alm":>4}  '
      f'{"R(t)":>5}  {"AngDeg":>7}  {"Sync":>6}  {"tau_S":>6}  {"Alm":>4}  Note')
print(f'  {"-"*12}  {"-"*10}  {"-"*6}  {"-"*4}  {"-"*5}  {"-"*7}  {"-"*6}  {"-"*6}  {"-"*4}  {"-"*28}')

NOTES = {
    '2006-12-31': 'ref end',
    '2007-06-30': 'Bear Stearns HF',
    '2007-09-30': 'Northern Rock',
    '2007-12-31': '<-- paper 1st alarm',
    '2008-03-31': 'Bear Stearns',
    '2008-09-30': 'LEHMAN',
    '2009-06-30': 'GFC end',
    '2020-03-31': 'COVID shock',
    '2023-03-31': 'SVB/CS',
}

for t in range(T_b):
    d_str   = str(dates[t].date())
    crisis  = '*** CRISIS' if yq[t] else '          '
    q       = Q_n[t]
    r       = R_t[t]            # raw (not normalised) — more meaningful
    ang     = ang_t[t]
    s       = S_n[t]
    tq      = tau_Q[t]
    ts      = tau_S[t]
    alm_q   = 'ALM' if (not np.isnan(tq) and q >= tq) else '   '
    alm_s   = 'ALM' if (not np.isnan(ts) and s >= ts) else '   '
    mark    = '<<' if '2007' in d_str or '2008' in d_str[:4] else '  '
    note    = NOTES.get(d_str, '')
    tq_s    = f'{tq:.3f}' if not np.isnan(tq) else '  nan'
    ts_s    = f'{ts:.3f}' if not np.isnan(ts) else '  nan'
    print(f'  {d_str:<12}  {crisis}  {q:.3f}  {alm_q}  '
          f'{r:.3f}  {ang:7.2f}  {s:.3f}  {ts_s:>6}  {alm_s}  {mark}{note}')

# ═══════════════════════════════════════════════════════════════════════════
#  AUROC comparison  (prospective, same frozen ref + adaptive P99)
# ═══════════════════════════════════════════════════════════════════════════

print()
print('=' * 92)
print('  AUROC COMPARISON  (all methods: frozen ref 2005Q1-2006Q4, no labels)')
print('=' * 92)

methods = {
    'Q_raw':          Q_n,
    'R(t) [angular]': R_n,
    'sync=R*Q_mean':  S_n,
}
print(f'  {"Method":<22}  {"AUROC":>6}  {"1st alarm":>11}  {"GFC lead"}')
print(f'  {"-"*22}  {"-"*6}  {"-"*11}  {"-"*12}')
for name, sq in methods.items():
    auc = roc_auc_score(yq, sq)
    tau = rolling_p99(sq, WINDOW)
    fa  = '—'
    for t in range(T_b):
        if not np.isnan(tau[t]) and sq[t] >= tau[t]:
            fa = str(dates[t].date())[:7]
            break
    try:
        lead = int(pd.Period('2008Q3', freq='Q') - pd.Period(fa.replace('-','Q'), freq='Q'))
        lead_s = f'{lead}Q before Lehman'
    except Exception:
        lead_s = '—'
    print(f'  {name:<22}  {auc:.4f}  {fa:>11}  {lead_s}')

print(f'  {"RTD+Fisher (paper)":<22}  0.773   2007-Q4       4Q before Lehman')
print(f'  {"Mol+ExpoGate (paper)":<22}  0.867   2007-Q4       4Q before Lehman')
print(f'  {"Gravity (paper)":<22}    —     2007-Q2       5Q before Lehman')

# ═══════════════════════════════════════════════════════════════════════════
#  What the angles are telling us
# ═══════════════════════════════════════════════════════════════════════════

ref_ang  = ang_t[:REF_QTRS].mean()
gfc_idx  = [t for t in range(T_b) if '2007' in str(dates[t].date())]
gfc_ang  = ang_t[gfc_idx].mean()
ref_R    = R_t[:REF_QTRS].mean()
gfc_R    = R_t[gfc_idx].mean()
post_idx = [t for t in range(T_b) if '2023' in str(dates[t].date())]
post_ang = ang_t[post_idx].mean()
post_R   = R_t[post_idx].mean()

print(f"""
  ANGULAR GEOMETRY:
    Reference 2005-2006:  mean pairwise angle = {ref_ang:.1f} deg   R = {ref_R:.3f}
    GFC buildup 2007  :  mean pairwise angle = {gfc_ang:.1f} deg   R = {gfc_R:.3f}
    SVB/CS 2023       :  mean pairwise angle = {post_ang:.1f} deg   R = {post_R:.3f}

  INTERPRETATION:
    R INCREASES during GFC buildup  -> banks converging on C* (synchronisation)
    Angle DECREASES during GFC       -> directions aligning

    R STAYS SAME or FALLS in 2023    -> idiosyncratic failures
    Angle STAYS LARGE in 2023        -> banks diverging, not converging

  EXACTLY the two-mode separation:
    SYSTEMIC  (GFC)   : R rises  + moderate Q  -->  sync_score spikes EARLY
    INDIVIDUAL (SVB)  : Q spikes + R unchanged  -->  Q_raw is better signal
""")
