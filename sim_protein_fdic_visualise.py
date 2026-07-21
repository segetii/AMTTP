"""
Protein Folding + FDIC Banking Crisis — CGS Simulation & Multi-Dimensional Visualisation
==========================================================================================
Runs two domain simulations and renders the Geometric Compression Hierarchy signals
in 1-D, 2-D, 3-D and 4-D (3-D + time/colour encoding).

Protein domain (Go-model, 30-residue β-hairpin):
    Three temperature regimes: T_low (folded), T_mid (marginal), T_high (unfolded)
    State: (RMSD, Q, E_pot, E_BS, δ_C, δ_G, δ_A, δ_T)
    Physics: Cα Lennard-Jones 12-10 Go contacts + Langevin thermostat (BAOAB)

FDIC domain (sector-level call report panel 1990-2024):
    7 institutional sectors × 6 CAMELS features, quarterly
    Crisis labels: GFC (2008), Euro (2011), COVID (2020), SVB (2023)
    CGS signals: E(t), Kuramoto R(t), Safety Ratio, P(t)

Plots (saved to results/sim_plots/):
    protein_1d_signals.png     — time-series of 4 key signals, 3 temperatures
    protein_2d_phase.png       — 2-D phase portraits (RMSD vs Q, E_BS vs δ_C)
    protein_3d_trajectory.png  — 3-D PCA of 12-dim feature space, coloured by E_BS
    protein_4d_alarm.png       — 3-D PCA + time-axis animation frame (scatter size = E_BS)

    fdic_1d_signals.png        — time-series E(t), R(t), Safety Ratio, P(t)
    fdic_2d_phase.png          — E vs R phase portrait, coloured by crisis label
    fdic_3d_landscape.png      — 3-D PCA of 6 FDIC features, coloured by energy E
    fdic_4d_crisis.png         — 3-D PCA + time axis (4th dim = colour gradient)
"""

from __future__ import annotations

import os, sys, time, warnings
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.cm as cm
from matplotlib.gridspec import GridSpec
from mpl_toolkits.mplot3d import Axes3D           # noqa: F401
from mpl_toolkits.mplot3d.art3d import Line3DCollection
from scipy.stats import chi2 as scipy_chi2
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA

warnings.filterwarnings("ignore")

# ── paths ───────────────────────────────────────────────────────────────────
ROOT     = r"C:\amttp"
PLOTDIR  = os.path.join(ROOT, "research", "neural-stability", "results", "sim_plots")
os.makedirs(PLOTDIR, exist_ok=True)

sys.path.insert(0, os.path.join(ROOT, "research", "udl"))
sys.path.insert(0, os.path.join(ROOT, "research", "adaptive-friction", "upgraded"))

# ═══════════════════════════════════════════════════════════════════════════
# 0.  Style helpers
# ═══════════════════════════════════════════════════════════════════════════

DARK_BG    = "#0d1117"
PANEL_BG   = "#161b22"
GRID_CLR   = "#30363d"
TEXT_CLR   = "#e6edf3"
CMAP_MAIN  = "plasma"

TEMP_COLORS = {"T_low": "#22c55e", "T_mid": "#f59e0b", "T_high": "#ef4444"}
CRISIS_COLORS = {"normal": "#3b82f6", "GFC": "#ef4444",
                 "Euro": "#f59e0b", "COVID": "#a78bfa", "SVB": "#ec4899"}

def _fig(w=14, h=8):
    fig = plt.figure(figsize=(w, h), facecolor=DARK_BG)
    return fig


def _ax(fig, *args, **kw):
    ax = fig.add_subplot(*args, **kw)
    ax.set_facecolor(PANEL_BG)
    for sp in ax.spines.values():
        sp.set_color(GRID_CLR)
    ax.tick_params(colors=TEXT_CLR, labelsize=8)
    ax.xaxis.label.set_color(TEXT_CLR)
    ax.yaxis.label.set_color(TEXT_CLR)
    ax.title.set_color(TEXT_CLR)
    ax.grid(True, color=GRID_CLR, alpha=0.4, linewidth=0.5)
    return ax


def _ax3d(fig, *args, **kw):
    ax = fig.add_subplot(*args, projection="3d", **kw)
    ax.set_facecolor(PANEL_BG)
    ax.xaxis.pane.fill = False; ax.yaxis.pane.fill = False; ax.zaxis.pane.fill = False
    ax.xaxis.pane.set_edgecolor(GRID_CLR)
    ax.yaxis.pane.set_edgecolor(GRID_CLR)
    ax.zaxis.pane.set_edgecolor(GRID_CLR)
    ax.tick_params(colors=TEXT_CLR, labelsize=7)
    ax.xaxis.label.set_color(TEXT_CLR)
    ax.yaxis.label.set_color(TEXT_CLR)
    ax.zaxis.label.set_color(TEXT_CLR)
    ax.title.set_color(TEXT_CLR)
    return ax


def _draw_ellipsoid(ax, lambdas, center=None, q=0.90,
                    n_theta=24, n_phi=24, **kwargs):
    """Wireframe C* reference ellipsoid in 3-D PCA space.

    lambdas : (3,) explained_variance for first 3 PCs
    center  : (3,) centre in PCA space (default zeros)
    q       : chi-squared confidence quantile, df=3  (0.90 → r²=6.25)
    """
    if center is None:
        center = np.zeros(3)
    r2    = float(scipy_chi2.ppf(q, df=3))
    radii = np.sqrt(r2 * np.maximum(lambdas[:3], 1e-10))
    theta = np.linspace(0, np.pi, n_theta)
    phi   = np.linspace(0, 2 * np.pi, n_phi)
    TH, PH = np.meshgrid(theta, phi)
    Xw = radii[0] * np.sin(TH) * np.cos(PH) + center[0]
    Yw = radii[1] * np.sin(TH) * np.sin(PH) + center[1]
    Zw = radii[2] * np.cos(TH)              + center[2]
    return ax.plot_wireframe(Xw, Yw, Zw, **kwargs)


def _save(fig, name, tight=True):
    path = os.path.join(PLOTDIR, name)
    if tight:
        plt.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(path, dpi=120, bbox_inches="tight",
                facecolor=DARK_BG, edgecolor="none")
    plt.close(fig)
    print(f"  Saved → {path}")


# ═══════════════════════════════════════════════════════════════════════════
# 1.  PROTEIN SIMULATION (Go-model, self-contained)
# ═══════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("  PROTEIN FOLDING SIMULATION — β-hairpin Go-model")
print("=" * 70)

# ── Build native structure ──────────────────────────────────────────────────
N_RES   = 30
D_BOND  = 3.8
STRAND  = 4.7
kB      = 0.001987
DT_MD   = 0.002
GAMMA_0 = 1.0
K_BOND  = 200.0
K_ANGLE = 5.0
THETA0  = 2.09
EPS_NAT = 0.5
SIG_NAT = 5.5
EPS_REP = 0.2
HYDRO   = frozenset([1,3,5,7,9,11,14,16,18,20,22,24,26,28])

def _build_native():
    pos = np.zeros((N_RES, 3))
    d   = D_BOND
    x_off = np.sqrt(max(d**2 - (STRAND/2)**2, 0.0))
    for i in range(14):
        pos[i] = [i * d, 0.0, 0.0]
    pos[14] = [13 * d + x_off, STRAND / 2, 0.0]
    for j in range(15):
        pos[15 + j] = [(13 - j) * d, STRAND, 0.0]
    return pos

def _native_contacts(nat, cutoff=8.0, seq_sep=3):
    pairs, dists = [], []
    for i in range(N_RES):
        for j in range(i + seq_sep, N_RES):
            d = float(np.linalg.norm(nat[i] - nat[j]))
            if d < cutoff:
                pairs.append([i, j])
                dists.append(d)
    return np.array(pairs, dtype=int), np.array(dists)

def _forces(pos, cp, cd):
    F = np.zeros_like(pos)
    E = 0.0
    # 1. Bond
    dr_b = pos[1:] - pos[:-1]
    d_b  = np.linalg.norm(dr_b, axis=1, keepdims=True) + 1e-10
    E   += K_BOND * np.sum((d_b.squeeze() - D_BOND)**2) * 0.5
    fb   = K_BOND * (d_b - D_BOND) * dr_b / d_b
    F[1:] -= fb; F[:-1] += fb
    # 2. Native contacts
    if len(cp):
        ci, cj = cp[:, 0], cp[:, 1]
        dr_c = pos[cj] - pos[ci]
        dist_c = np.linalg.norm(dr_c, axis=1) + 1e-10
        x12 = (cd / dist_c) ** 12
        x10 = (cd / dist_c) ** 10
        E  += EPS_NAT * np.sum(5*x12 - 6*x10)
        dVdr = 60.0 * EPS_NAT * (x10 - x12) / dist_c
        fc = (dVdr / dist_c)[:, None] * dr_c
        np.add.at(F, ci, fc); np.add.at(F, cj, -fc)
    return F, E

def _rmsd(pos, nat):
    p = pos - pos.mean(0); n = nat - nat.mean(0)
    H = p.T @ n
    U, _, Vt = np.linalg.svd(H)
    d = np.sign(np.linalg.det(Vt.T @ U.T))
    R = Vt.T @ np.diag([1, 1, d]) @ U.T
    return float(np.sqrt(np.mean(np.sum((p @ R.T - n)**2, axis=1))))

def _Q(pos, cp, cd, tol=1.2):
    if len(cp) == 0: return 1.0
    ci, cj = cp[:, 0], cp[:, 1]
    return float(np.mean(np.linalg.norm(pos[cj]-pos[ci], axis=1) < tol * cd))

def _features(pos, nat, cp, cd):
    """12 aggregate features per frame."""
    local_rmsd = np.linalg.norm(pos - nat, axis=1)
    cs = np.ones(N_RES)
    if len(cp):
        ci, cj = cp[:, 0], cp[:, 1]
        dc = np.linalg.norm(pos[cj]-pos[ci], axis=1)
        formed = dc < 1.2 * cd
        ct = np.zeros(N_RES); cf = np.zeros(N_RES)
        np.add.at(ct, ci, 1); np.add.at(ct, cj, 1)
        np.add.at(cf, ci, formed.astype(float)); np.add.at(cf, cj, formed.astype(float))
        mask = ct > 0
        cs[mask] = cf[mask] / ct[mask]
    D = np.linalg.norm(pos[:, None] - pos[None], axis=2)
    ld = np.sum(D < 8.0, axis=1) - 1
    v1 = pos[:-2] - pos[1:-1]; v2 = pos[2:] - pos[1:-1]
    n1 = np.linalg.norm(v1, axis=1)+1e-10; n2 = np.linalg.norm(v2, axis=1)+1e-10
    cos_a = np.clip(np.sum(v1*v2, axis=1)/(n1*n2), -1, 1)
    ad = np.zeros(N_RES); ad[1:-1] = np.abs(np.arccos(cos_a) - THETA0)
    bur = np.linalg.norm(pos - pos.mean(0), axis=1)
    bfac = np.array([np.var(D[i, D[i] < 10]) if np.sum(D[i] < 10) > 2 else 0.0
                     for i in range(N_RES)])
    return np.array([local_rmsd.mean(), local_rmsd.std(),
                     cs.mean(), cs.std(),
                     ld.mean().astype(float), ld.std().astype(float),
                     ad.mean(), ad.std(),
                     bur.mean(), bur.std(),
                     bfac.mean(), bfac.std()])

def _langevin_step(pos, vel, F_prev, T, gamma, cp, cd):
    dt = DT_MD
    maxF = 500.0
    # clamp
    fn = np.linalg.norm(F_prev, axis=1, keepdims=True)
    F_cl = np.where(fn > maxF, F_prev * maxF / (fn + 1e-10), F_prev)
    vel = vel + 0.5 * dt * F_cl
    pos = pos + 0.5 * dt * vel
    c1 = np.exp(-gamma * dt)
    c2 = np.sqrt(1.0 - c1**2) * np.sqrt(kB * T)
    vel = c1 * vel + c2 * np.random.randn(N_RES, 3)
    pos = pos + 0.5 * dt * vel
    F_new, E = _forces(pos, cp, cd)
    fn2 = np.linalg.norm(F_new, axis=1, keepdims=True)
    F_cl2 = np.where(fn2 > maxF, F_new * maxF / (fn2 + 1e-10), F_new)
    vel = vel + 0.5 * dt * F_cl2
    return pos, vel, F_new, E

# Build native, contacts
nat   = _build_native()
cp, cd = _native_contacts(nat)
print(f"  Native contacts: {len(cp)}")

# Reference ensemble at T=100K
np.random.seed(42)
rpos = nat.copy() + np.random.randn(N_RES, 3) * 0.05
rvel = np.random.randn(N_RES, 3) * np.sqrt(kB * 100.0) * 0.1
F0, _ = _forces(rpos, cp, cd)
ref_feats = []
for _ in range(600):
    rpos, rvel, F0, _ = _langevin_step(rpos, rvel, F0, 100.0, GAMMA_0 * 2, cp, cd)
for _ in range(400):
    rpos, rvel, F0, _ = _langevin_step(rpos, rvel, F0, 100.0, GAMMA_0 * 2, cp, cd)
    ref_feats.append(_features(rpos, nat, cp, cd))

X_ref_raw = np.stack(ref_feats)   # (80, 12)
scaler_p  = StandardScaler().fit(X_ref_raw)
X_ref_s   = scaler_p.transform(X_ref_raw)
mu_r_p    = X_ref_s.mean(0); sg_r_p = X_ref_s.std(0)
E_ref_vals= np.sum(X_ref_s**2, axis=1)
E_thresh  = float(np.mean(E_ref_vals) + 2 * np.std(E_ref_vals))
theta_p   = float(np.median(E_ref_vals))
d_p       = X_ref_s.shape[1]      # 12 features
print(f"  Ref frames: {len(X_ref_raw)}  E_thresh: {E_thresh:.2f}  θ_p: {theta_p:.2f}")

# PCA for 3D/4D projections (fit on reference)
pca_p = PCA(n_components=min(4, d_p)).fit(X_ref_s)

TEMPS_RUN = {"T_low": 150.0, "T_mid": 320.0, "T_high": 500.0}
N_EQUIL   = 2000
N_PROD    = 6000
SAMP      = 50

protein_sims = {}
for label, T_run in TEMPS_RUN.items():
    print(f"\n  Running T={T_run:.0f}K ({label}) …")
    np.random.seed(100 + int(T_run))
    pos = nat.copy() + np.random.randn(N_RES, 3) * 0.1
    vel = np.random.randn(N_RES, 3) * np.sqrt(kB * T_run) * 0.1
    F0, _ = _forces(pos, cp, cd)
    # Equilibration
    for _ in range(N_EQUIL):
        pos, vel, F0, _ = _langevin_step(pos, vel, F0, T_run, GAMMA_0, cp, cd)
    # Production
    traj = {"t": [], "rmsd": [], "Q": [], "E_pot": [],
            "E_cgs": [], "gamma_eff": [], "alarm": [],
            "feat": [], "com_x": [], "com_y": [], "com_z": []}
    for step in range(N_PROD):
        # Adaptive γ: boost friction when E_cgs > θ
        if traj["E_cgs"]:
            E_now = traj["E_cgs"][-1]
            gamma = GAMMA_0 * (1.0 + 5.0 * E_now / (E_now + theta_p))
        else:
            gamma = GAMMA_0
        pos, vel, F0, E_p = _langevin_step(pos, vel, F0, T_run, gamma, cp, cd)
        if step % SAMP == 0:
            feat = _features(pos, nat, cp, cd)
            fs   = scaler_p.transform(feat.reshape(1, -1))[0]
            E_cgs= float(np.dot(fs, fs))
            com  = pos.mean(0)
            traj["t"].append(step * DT_MD)
            traj["rmsd"].append(_rmsd(pos, nat))
            traj["Q"].append(_Q(pos, cp, cd))
            traj["E_pot"].append(E_p)
            traj["E_cgs"].append(E_cgs)
            traj["gamma_eff"].append(gamma)
            traj["alarm"].append(int(E_cgs > E_thresh))
            traj["feat"].append(fs)
            traj["com_x"].append(com[0])
            traj["com_y"].append(com[1])
            traj["com_z"].append(com[2])
    for k in traj:
        traj[k] = np.array(traj[k])
    F_arr = traj["feat"]   # (n, 12) scaled
    traj["pca"] = pca_p.transform(F_arr)    # (n, 4)
    # χ² p-value
    traj["pval"] = scipy_chi2.sf(traj["E_cgs"], df=d_p)
    # Safety ratio
    mfls   = 2.0 * np.sqrt(np.maximum(traj["E_cgs"], 1e-30))
    theta_a= np.arccos(np.clip(
        np.array([float(np.dot(
            F_arr[i] - (F_arr[i-1] if i > 0 else F_arr[i]),
            2.0 * F_arr[i]
        )) / (
            np.linalg.norm(F_arr[i] - (F_arr[i-1] if i > 0 else F_arr[i])) * mfls[i] + 1e-12
        ) for i in range(len(F_arr))]),
        -1, 1))
    M_max = float(np.percentile(np.sqrt(E_ref_vals), 99)) * 2
    traj["safety_ratio"] = theta_a / (M_max + 1e-10)
    protein_sims[label] = traj
    n_alarm = int(traj["alarm"].sum())
    print(f"    Frames: {len(traj['t'])}  Alarms: {n_alarm}  "
          f"RMSD_mean: {traj['rmsd'].mean():.2f} Å  Q_mean: {traj['Q'].mean():.3f}")

print("\n  Protein simulation complete.")


# ═══════════════════════════════════════════════════════════════════════════
# 2.  FDIC SIMULATION (real call-report data)
# ═══════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("  FDIC BANKING CRISIS SIMULATION — Sector-level Call Report 1990-2024")
print("=" * 70)

from fdic_loader import fetch_fdic_specgrp, compute_sector_features, build_panel, FEATURE_NAMES
try:
    from fred_loader import fetch_all as fetch_fred_all
    raw_fred  = fetch_fred_all(use_cache=True, verbose=False)
    fred_slope = raw_fred["slope_10y2y"]
except Exception as _e:
    print(f"  [warning] FRED loader failed ({_e}); using zero yield slope")
    import pandas as pd
    fred_slope = pd.Series(0.0, index=pd.date_range("1990-01-01", "2024-12-31", freq="QE"))

fdic_df       = fetch_fdic_specgrp(start="1990-01-01", end="2024-12-31",
                                    use_cache=True, verbose=False)
sector_feats  = compute_sector_features(fdic_df, fred_slope)
X_fdic, dates_fdic, sectors_fdic = build_panel(sector_feats)
import pandas as pd
dates_fdic = pd.DatetimeIndex(dates_fdic)
T_fdic, N_fdic, d_fdic = X_fdic.shape
print(f"  Panel: T={T_fdic}, N={N_fdic} sectors, d={d_fdic} features")
print(f"  Date range: {dates_fdic[0].date()} → {dates_fdic[-1].date()}")
print(f"  Features: {FEATURE_NAMES}")

# Cross-sectional mean per quarter
Xagg = np.nanmean(X_fdic, axis=1)  # (T, d)
for j in range(d_fdic):
    col = Xagg[:, j]
    med = float(np.nanmedian(col[np.isfinite(col)])) if np.any(np.isfinite(col)) else 0.0
    col[~np.isfinite(col)] = med
    Xagg[:, j] = col

# Reference = pre-2008
ref_mask_f  = np.asarray(dates_fdic < pd.Timestamp("2008-01-01"))
X_ref_f     = Xagg[ref_mask_f]
scaler_f    = StandardScaler().fit(X_ref_f)
X_ref_fs    = scaler_f.transform(X_ref_f)
X_all_fs    = scaler_f.transform(Xagg)
E_ref_f     = np.sum(X_ref_fs**2, axis=1)
theta_f     = float(np.median(E_ref_f))
d_f         = d_fdic
sigma_f     = float(np.std(E_ref_f))

# Crisis labels
CRISIS_WINDOWS_FDIC = [
    ("GFC",   "2008-09-30", "2009-03-31"),
    ("Euro",  "2011-09-30", "2012-03-31"),
    ("COVID", "2020-03-31", "2020-06-30"),
    ("SVB",   "2023-03-31", "2023-06-30"),
]
crisis_label = np.array(["normal"] * T_fdic, dtype=object)
for cname, lo, hi in CRISIS_WINDOWS_FDIC:
    mask = np.asarray((dates_fdic >= pd.Timestamp(lo)) & (dates_fdic <= pd.Timestamp(hi)))
    crisis_label[mask] = cname

# CGS signals
E_fdic   = np.sum(X_all_fs**2, axis=1)   # Level-3 energy
mfls_fdic = 2.0 * np.sqrt(np.maximum(E_fdic, 1e-30))
gamma_fdic = E_fdic / (E_fdic + theta_f + 1e-30)
E_dot_fdic = np.gradient(E_fdic)
pval_fdic  = scipy_chi2.sf(E_fdic, df=d_f)

# Kuramoto per-sector phases (1 feature each, use PCA 2D per sector)
pca_f  = PCA(n_components=min(4, d_f)).fit(X_ref_fs)
Z4_fdic = pca_f.transform(X_all_fs)        # (T, ≤4)

# Per-sector energy + Kuramoto across sectors
phases_fdic = np.zeros((T_fdic, N_fdic))
for n in range(N_fdic):
    xn = X_fdic[:, n, :]
    xn = np.where(np.isfinite(xn), xn, 0.0)
    xn_s = scaler_f.transform(xn)
    if hasattr(pca_f, 'components_') and len(pca_f.components_) >= 2:
        v1, v2 = pca_f.components_[0], pca_f.components_[1]
        a = xn_s @ v1; b = xn_s @ v2
        phases_fdic[:, n] = np.arctan2(b, a)
    else:
        phases_fdic[:, n] = 0.0

R_fdic   = np.abs(np.mean(np.exp(1j * phases_fdic), axis=1)).real
R_dot_f  = np.gradient(R_fdic)

# Safety ratio
theta_angle_f = np.arccos(np.clip(
    np.array([
        float(np.dot(X_all_fs[t] - (X_all_fs[t-1] if t>0 else X_all_fs[t]),
                     2.0 * X_all_fs[t])) /
        (np.linalg.norm(X_all_fs[t] - (X_all_fs[t-1] if t>0 else X_all_fs[t])) *
         mfls_fdic[t] + 1e-12)
        for t in range(T_fdic)
    ]), -1, 1))
M_max_f = float(np.percentile(np.sqrt(E_ref_f), 99)) * 2
safety_fdic = theta_angle_f / (M_max_f + 1e-10)

# P(t) = Ė>0 ∧ Ṙ>0 (at quarterly resolution θ̈ is always noisy; use 2-phase)
theta_ddot_f = np.gradient(np.gradient(theta_angle_f))
P_fdic = (E_dot_fdic > 0) & (R_dot_f > 0) & (theta_ddot_f > 0)

print(f"  E range: [{E_fdic.min():.2f}, {E_fdic.max():.2f}]  "
      f"R range: [{R_fdic.min():.3f}, {R_fdic.max():.3f}]")
crisis_any = crisis_label != "normal"
print(f"  Crisis quarters: {int(crisis_any.sum())}  "
      f"E_crisis_mean: {E_fdic[crisis_any].mean():.2f}  "
      f"E_normal_mean: {E_fdic[~crisis_any].mean():.2f}")
print(f"  P(t) crisis rate: {P_fdic[crisis_any].mean()*100:.1f}%  "
      f"normal rate: {P_fdic[~crisis_any].mean()*100:.1f}%")

years_fdic = np.array([d.year + (d.month - 1) / 12 for d in dates_fdic])

print("\n  FDIC simulation complete.")


# ═══════════════════════════════════════════════════════════════════════════
# 3.  PLOTS
# ═══════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("  PLOTTING 1D / 2D / 3D / 4D")
print("=" * 70)


# ─────────────────────────────────────────────────────────────────────────
# PROTEIN — 1-D  time-series
# ─────────────────────────────────────────────────────────────────────────
print("\n  [1/8] protein_1d_signals.png …")
fig = _fig(16, 10)
fig.suptitle("Protein Folding — 1-D Signal Time Series  (Go-model, 30 residues)",
             color=TEXT_CLR, fontsize=13, fontweight="bold")
signal_specs = [
    ("rmsd",         "RMSD (Å)",         "Backbone RMSD from native"),
    ("Q",            "Q (fraction)",      "Native contact fraction Q"),
    ("E_cgs",        "E_CGS",             "CGS Level-3 energy E(t)"),
    ("safety_ratio", "Safety ratio",      "θ(t) / M_max  (→0 at collapse)"),
]
for pi, (key, ylbl, ttl) in enumerate(signal_specs, 1):
    ax = _ax(fig, 2, 2, pi)
    ax.set_title(ttl, color=TEXT_CLR, fontsize=9)
    ax.set_xlabel("MD time (ps)", fontsize=8)
    ax.set_ylabel(ylbl, fontsize=8)
    for label, sim in protein_sims.items():
        ax.plot(sim["t"], sim[key], color=TEMP_COLORS[label],
                lw=0.8, alpha=0.85, label=f"{label} T={TEMPS_RUN[label]:.0f}K")
    # alarm threshold for E_cgs
    if key == "E_cgs":
        ax.axhline(E_thresh, color="#ffffff", ls="--", lw=0.8, alpha=0.6, label="alarm threshold")
    ax.legend(fontsize=7, framealpha=0.25, labelcolor=TEXT_CLR,
              facecolor=PANEL_BG, edgecolor=GRID_CLR)
_save(fig, "protein_1d_signals.png")


# ─────────────────────────────────────────────────────────────────────────
# PROTEIN — 2-D  phase portraits
# ─────────────────────────────────────────────────────────────────────────
print("  [2/8] protein_2d_phase.png …")
fig = _fig(16, 8)
fig.suptitle("Protein Folding — 2-D Phase Portraits", color=TEXT_CLR,
             fontsize=13, fontweight="bold")

ax1 = _ax(fig, 1, 2, 1)
ax1.set_title("RMSD vs Q  (folding landscape)", color=TEXT_CLR, fontsize=10)
ax1.set_xlabel("RMSD from native (Å)", fontsize=9)
ax1.set_ylabel("Native contact fraction Q", fontsize=9)
for label, sim in protein_sims.items():
    sc = ax1.scatter(sim["rmsd"], sim["Q"], c=sim["t"],
                     cmap=CMAP_MAIN, s=6, alpha=0.6,
                     label=f"{label} T={TEMPS_RUN[label]:.0f}K")
    ax1.plot(sim["rmsd"][:1], sim["Q"][:1], "^", color=TEMP_COLORS[label],
             ms=7, zorder=5)  # start marker
cbar1 = fig.colorbar(sc, ax=ax1, pad=0.01)
cbar1.set_label("MD time (ps)", color=TEXT_CLR, fontsize=8)
cbar1.ax.yaxis.set_tick_params(labelcolor=TEXT_CLR)
ax1.legend(fontsize=8, framealpha=0.25, labelcolor=TEXT_CLR,
           facecolor=PANEL_BG, edgecolor=GRID_CLR)

ax2 = _ax(fig, 1, 2, 2)
ax2.set_title("CGS Energy vs Contact Fraction Q  (phase space coloured by T)", color=TEXT_CLR, fontsize=10)
ax2.set_xlabel("Native contact fraction Q", fontsize=9)
ax2.set_ylabel("CGS Energy E(t)  [Mahalanobis]", fontsize=9)
for label, sim in protein_sims.items():
    alarm_c = np.where(sim["alarm"].astype(bool), "#ef4444", TEMP_COLORS[label])
    ax2.scatter(sim["Q"], sim["E_cgs"], c=TEMP_COLORS[label], s=5, alpha=0.5,
                label=f"{label}")
    ax2.scatter(sim["Q"][sim["alarm"].astype(bool)],
                sim["E_cgs"][sim["alarm"].astype(bool)],
                color="#ef4444", s=10, alpha=0.8, marker="x", linewidths=0.8)
ax2.axhline(E_thresh, color="#ffffff", ls="--", lw=0.8, alpha=0.6, label="alarm threshold")
ax2.legend(fontsize=8, framealpha=0.25, labelcolor=TEXT_CLR,
           facecolor=PANEL_BG, edgecolor=GRID_CLR)
_save(fig, "protein_2d_phase.png")


# ─────────────────────────────────────────────────────────────────────────
# PROTEIN — 3-D  PCA of feature space
# ─────────────────────────────────────────────────────────────────────────
print("  [3/8] protein_3d_trajectory.png …")
fig = _fig(18, 7)
fig.suptitle("Protein Folding — 3-D PCA of Feature Space  (12-dim → 3 PC)",
             color=TEXT_CLR, fontsize=13, fontweight="bold")

def _protein_3d_panel(fig, subplot_idx, label, sim, title_extra=""):
    ax = _ax3d(fig, 1, 3, subplot_idx)
    pca3 = sim["pca"][:, :3]
    E_n  = (sim["E_cgs"] - sim["E_cgs"].min()) / (np.ptp(sim["E_cgs"]) + 1e-10)
    # ── Reference data cloud (ensures axes extend to include origin region) ──
    ref_pca3 = pca_p.transform(X_ref_s)[:, :3]
    ax.scatter(ref_pca3[:, 0], ref_pca3[:, 1], ref_pca3[:, 2],
               c="#40e0d0", s=5, alpha=0.4, depthshade=True,
               label="T=100K ref", zorder=2)
    # C* reference ellipsoid (90% confidence of reference distribution)
    lam3_p = pca_p.explained_variance_[:3]
    ctr3_p = ref_pca3.mean(axis=0)
    _draw_ellipsoid(ax, lam3_p, center=ctr3_p, q=0.90,
                    color="#40e0d0", alpha=0.15, linewidth=0.5,
                    rstride=3, cstride=3, zorder=1)
    sc = ax.scatter(pca3[:, 0], pca3[:, 1], pca3[:, 2],
                    c=E_n, cmap=CMAP_MAIN, s=8, alpha=0.75, depthshade=True)
    ax.plot(pca3[:, 0], pca3[:, 1], pca3[:, 2],
            color=TEMP_COLORS[label], lw=0.4, alpha=0.3)
    ax.set_xlabel("PC1", fontsize=7); ax.set_ylabel("PC2", fontsize=7)
    ax.set_zlabel("PC3", fontsize=7)
    T_lbl = f"T={TEMPS_RUN[label]:.0f}K"
    ax.set_title(f"{label}  {T_lbl}{title_extra}", color=TEXT_CLR, fontsize=9)
    cbar = fig.colorbar(sc, ax=ax, pad=0.08, shrink=0.6)
    cbar.set_label("E_CGS (norm)", color=TEXT_CLR, fontsize=7)
    cbar.ax.yaxis.set_tick_params(labelcolor=TEXT_CLR)

for idx, lbl in enumerate(["T_low", "T_mid", "T_high"], 1):
    _protein_3d_panel(fig, idx, lbl, protein_sims[lbl])
_save(fig, "protein_3d_trajectory.png")


# ─────────────────────────────────────────────────────────────────────────
# PROTEIN — 4-D  3-D PCA + time as colour + size = alarm
# ─────────────────────────────────────────────────────────────────────────
print("  [4/8] protein_4d_alarm.png …")
fig = _fig(18, 7)
fig.suptitle("Protein Folding — 4-D Visualisation  (PC1/2/3 + time gradient + alarm size)",
             color=TEXT_CLR, fontsize=13, fontweight="bold")

for idx, lbl in enumerate(["T_low", "T_mid", "T_high"], 1):
    sim  = protein_sims[lbl]
    ax   = _ax3d(fig, 1, 3, idx)
    pca3 = sim["pca"][:, :3]
    t_n  = (sim["t"] - sim["t"].min()) / (np.ptp(sim["t"]) + 1e-10)   # 4th dim
    sizes= 8 + sim["alarm"].astype(float) * 40                        # big = alarm
    # Reference cloud + ellipsoid
    ref_pca3 = pca_p.transform(X_ref_s)[:, :3]
    ax.scatter(ref_pca3[:, 0], ref_pca3[:, 1], ref_pca3[:, 2],
               c="#40e0d0", s=4, alpha=0.35, depthshade=True, zorder=2)
    _draw_ellipsoid(ax, pca_p.explained_variance_[:3],
                    center=ref_pca3.mean(axis=0), q=0.90,
                    color="#40e0d0", alpha=0.12, linewidth=0.4,
                    rstride=3, cstride=3, zorder=1)
    sc   = ax.scatter(pca3[:, 0], pca3[:, 1], pca3[:, 2],
                      c=t_n, cmap="viridis", s=sizes, alpha=0.7, depthshade=True)
    # Mark alarm points explicitly
    alm_idx = sim["alarm"].astype(bool)
    if alm_idx.any():
        ax.scatter(pca3[alm_idx, 0], pca3[alm_idx, 1], pca3[alm_idx, 2],
                   c="#ef4444", s=50, alpha=0.9, marker="*",
                   label="alarm", depthshade=False, zorder=5)
    ax.set_xlabel("PC1", fontsize=7); ax.set_ylabel("PC2", fontsize=7)
    ax.set_zlabel("PC3", fontsize=7)
    ax.set_title(f"{lbl}  T={TEMPS_RUN[lbl]:.0f}K  (size∝alarm)",
                 color=TEXT_CLR, fontsize=9)
    cbar = fig.colorbar(sc, ax=ax, pad=0.08, shrink=0.6)
    cbar.set_label("Time (norm)  [4th dim]", color=TEXT_CLR, fontsize=7)
    cbar.ax.yaxis.set_tick_params(labelcolor=TEXT_CLR)
_save(fig, "protein_4d_alarm.png")


# ─────────────────────────────────────────────────────────────────────────
# FDIC — 1-D  time-series
# ─────────────────────────────────────────────────────────────────────────
print("  [5/8] fdic_1d_signals.png …")
fig = _fig(16, 10)
fig.suptitle("FDIC Banking Crisis — 1-D CGS Signal Time Series  (1990-2024)",
             color=TEXT_CLR, fontsize=13, fontweight="bold")

fdic_signals_1d = [
    (E_fdic,       "CGS Energy  E(t)",       "Level-3 Mahalanobis departure"),
    (R_fdic,       "Kuramoto  R(t)",          "Level-2 cross-sector synchrony"),
    (safety_fdic,  "Safety Ratio  θ/M_max",  "Imminent collapse proximity"),
    (-np.log10(pval_fdic + 1e-300), "−log₁₀(p-value)",
     "Probabilistic significance (χ²)"),
]
crisis_bands = [
    ("GFC",   "2008-09-30", "2009-03-31", "#ef4444"),
    ("Euro",  "2011-09-30", "2012-03-31", "#f59e0b"),
    ("COVID", "2020-03-31", "2020-06-30", "#a78bfa"),
    ("SVB",   "2023-03-31", "2023-06-30", "#ec4899"),
]

for pi, (arr, ylbl, ttl) in enumerate(fdic_signals_1d, 1):
    ax = _ax(fig, 2, 2, pi)
    ax.set_title(ttl, color=TEXT_CLR, fontsize=9)
    ax.set_xlabel("Year", fontsize=8); ax.set_ylabel(ylbl, fontsize=8)
    ax.plot(years_fdic, arr, color="#60a5fa", lw=1.0, alpha=0.9)
    for cname, lo, hi, col in crisis_bands:
        y0 = float(pd.Timestamp(lo).year) + (float(pd.Timestamp(lo).month)-1)/12
        y1 = float(pd.Timestamp(hi).year) + (float(pd.Timestamp(hi).month)-1)/12
        ax.axvspan(y0, y1, alpha=0.25, color=col, label=cname)
    if pi == 1:
        ax.legend(fontsize=7, framealpha=0.3, labelcolor=TEXT_CLR,
                  facecolor=PANEL_BG, edgecolor=GRID_CLR)
_save(fig, "fdic_1d_signals.png")


# ─────────────────────────────────────────────────────────────────────────
# FDIC — 2-D  phase portrait
# ─────────────────────────────────────────────────────────────────────────
print("  [6/8] fdic_2d_phase.png …")
fig = _fig(16, 8)
fig.suptitle("FDIC Banking Crisis — 2-D Phase Portraits", color=TEXT_CLR,
             fontsize=13, fontweight="bold")

ax1 = _ax(fig, 1, 2, 1)
ax1.set_title("Energy E(t) vs Kuramoto R(t)  (crisis labelled)", color=TEXT_CLR, fontsize=10)
ax1.set_xlabel("Kuramoto synchrony R(t)", fontsize=9)
ax1.set_ylabel("CGS Energy E(t)", fontsize=9)
for cname, col in CRISIS_COLORS.items():
    msk = crisis_label == cname
    if msk.any():
        ax1.scatter(R_fdic[msk], E_fdic[msk], color=col, s=20,
                    alpha=0.85, label=cname, zorder=3 if cname != "normal" else 2)
ax1.legend(fontsize=8, framealpha=0.3, labelcolor=TEXT_CLR,
           facecolor=PANEL_BG, edgecolor=GRID_CLR)

ax2 = _ax(fig, 1, 2, 2)
ax2.set_title("PC1 vs PC2  (feature-space trajectory, coloured by time)",
              color=TEXT_CLR, fontsize=10)
ax2.set_xlabel("PC1  (FDIC 6-dim features)", fontsize=9)
ax2.set_ylabel("PC2", fontsize=9)
sc2 = ax2.scatter(Z4_fdic[:, 0], Z4_fdic[:, 1], c=years_fdic,
                  cmap="plasma", s=12, alpha=0.8)
# Overlay crisis markers
for cname, col in CRISIS_COLORS.items():
    if cname == "normal": continue
    msk = crisis_label == cname
    if msk.any():
        ax2.scatter(Z4_fdic[msk, 0], Z4_fdic[msk, 1],
                    color=col, s=60, marker="*", alpha=0.95, label=cname, zorder=5)
cbar2 = fig.colorbar(sc2, ax=ax2, pad=0.01)
cbar2.set_label("Year  [2nd time dimension]", color=TEXT_CLR, fontsize=8)
cbar2.ax.yaxis.set_tick_params(labelcolor=TEXT_CLR)
ax2.legend(fontsize=8, framealpha=0.3, labelcolor=TEXT_CLR,
           facecolor=PANEL_BG, edgecolor=GRID_CLR)
_save(fig, "fdic_2d_phase.png")


# ─────────────────────────────────────────────────────────────────────────
# FDIC — 3-D  energy landscape
# ─────────────────────────────────────────────────────────────────────────
print("  [7/8] fdic_3d_landscape.png …")
fig = _fig(14, 9)
fig.suptitle("FDIC Banking — 3-D PCA of 6 Financial Features  (colour = CGS energy)",
             color=TEXT_CLR, fontsize=13, fontweight="bold")

ax3d = _ax3d(fig, 1, 1, 1)
E_n_f = (E_fdic - E_fdic.min()) / (np.ptp(E_fdic) + 1e-10)
n_pts = len(Z4_fdic)

# C* reference ellipsoid (90% confidence region of pre-2008 reference)
lam3_f  = pca_f.explained_variance_[:3]
ctr3_f  = pca_f.transform(X_ref_fs).mean(axis=0)[:3]
_draw_ellipsoid(ax3d, lam3_f, center=ctr3_f, q=0.90,
                color="#40e0d0", alpha=0.12, linewidth=0.35,
                rstride=3, cstride=3, zorder=1)

# Draw trajectory line in grey
for i in range(n_pts - 1):
    ax3d.plot(Z4_fdic[i:i+2, 0], Z4_fdic[i:i+2, 1], Z4_fdic[i:i+2, 2],
              color="#444d56", lw=0.6, alpha=0.4, zorder=1)

sc3d = ax3d.scatter(Z4_fdic[:, 0], Z4_fdic[:, 1], Z4_fdic[:, 2],
                    c=E_n_f, cmap="inferno", s=18, alpha=0.85, depthshade=True, zorder=3)
# Highlight crises
for cname, col in CRISIS_COLORS.items():
    if cname == "normal": continue
    msk = crisis_label == cname
    if msk.any():
        ax3d.scatter(Z4_fdic[msk, 0], Z4_fdic[msk, 1], Z4_fdic[msk, 2],
                     c=col, s=80, marker="*", alpha=0.95,
                     label=cname, depthshade=False, zorder=5)

ax3d.set_xlabel("PC1  (yield-curve)", fontsize=8)
ax3d.set_ylabel("PC2  (leverage)", fontsize=8)
ax3d.set_zlabel("PC3  (credit stress)", fontsize=8)
ax3d.legend(fontsize=9, framealpha=0.3, labelcolor=TEXT_CLR,
            facecolor=PANEL_BG, edgecolor=GRID_CLR, loc="upper left")
cbar3 = fig.colorbar(sc3d, ax=ax3d, pad=0.04, shrink=0.7)
cbar3.set_label("CGS Energy E(t) (norm)", color=TEXT_CLR, fontsize=8)
cbar3.ax.yaxis.set_tick_params(labelcolor=TEXT_CLR)
_save(fig, "fdic_3d_landscape.png")


# ─────────────────────────────────────────────────────────────────────────
# FDIC — 4-D  PC1/PC2/PC3 + year (colour) + energy (size)
# ─────────────────────────────────────────────────────────────────────────
print("  [8/8] fdic_4d_crisis.png …")
fig = _fig(14, 9)
fig.suptitle(
    "FDIC Banking — 4-D Visualisation\n"
    "PC1/PC2/PC3  ·  colour = year  ·  size ∝ CGS energy  ·  ★ = crisis",
    color=TEXT_CLR, fontsize=12, fontweight="bold")

ax4d = _ax3d(fig, 1, 1, 1)
sizes4 = 15 + E_n_f * 120   # larger at higher energy

# C* reference ellipsoid
_draw_ellipsoid(ax4d, lam3_f, center=ctr3_f, q=0.90,
                color="#40e0d0", alpha=0.10, linewidth=0.3,
                rstride=3, cstride=3, zorder=1)

sc4d = ax4d.scatter(Z4_fdic[:, 0], Z4_fdic[:, 1], Z4_fdic[:, 2],
                    c=years_fdic, cmap="plasma",
                    s=sizes4, alpha=0.75, depthshade=True, zorder=2)
for cname, col in CRISIS_COLORS.items():
    if cname == "normal": continue
    msk = crisis_label == cname
    if msk.any():
        ax4d.scatter(Z4_fdic[msk, 0], Z4_fdic[msk, 1], Z4_fdic[msk, 2],
                     c=col, s=200, marker="*", alpha=0.98,
                     label=cname, depthshade=False, zorder=5)
# P(t)=1 windows annotated
P_idx = np.where(P_fdic)[0]
if len(P_idx):
    ax4d.scatter(Z4_fdic[P_idx, 0], Z4_fdic[P_idx, 1], Z4_fdic[P_idx, 2],
                 c="#ffffff", s=20, marker="+", alpha=0.6,
                 label="P(t)=1  (precursor)", depthshade=False, zorder=4)

ax4d.set_xlabel("PC1", fontsize=8); ax4d.set_ylabel("PC2", fontsize=8)
ax4d.set_zlabel("PC3", fontsize=8)
ax4d.legend(fontsize=9, framealpha=0.3, labelcolor=TEXT_CLR,
            facecolor=PANEL_BG, edgecolor=GRID_CLR, loc="upper left")
cbar4 = fig.colorbar(sc4d, ax=ax4d, pad=0.04, shrink=0.7)
cbar4.set_label("Year  [4th dimension]", color=TEXT_CLR, fontsize=8)
cbar4.ax.yaxis.set_tick_params(labelcolor=TEXT_CLR)
_save(fig, "fdic_4d_crisis.png")


# ═══════════════════════════════════════════════════════════════════════════
# 4.  COMBINED SUMMARY PRINT
# ═══════════════════════════════════════════════════════════════════════════

print("\n" + "█" * 70)
print("  SIMULATION SUMMARY")
print("█" * 70)

print("\n  ── PROTEIN (Go-model 30 residues, β-hairpin) ──────────────────────")
for label, sim in protein_sims.items():
    alm_rate = sim["alarm"].mean() * 100
    print(f"  {label:8s} T={TEMPS_RUN[label]:.0f}K  "
          f"RMSD_μ={sim['rmsd'].mean():.2f}Å  Q_μ={sim['Q'].mean():.3f}  "
          f"E_CGS_μ={sim['E_cgs'].mean():.2f}  alarm_rate={alm_rate:.1f}%")

print(f"\n  ── FDIC (sector panel 1990-2024, d={d_f}) ─────────────────────────")
print(f"  Reference quarters:   {int(ref_mask_f.sum())}  (pre-2008)")
for cname, lo, hi, _ in crisis_bands:
    msk = crisis_label == cname
    if msk.any():
        print(f"  {cname:6s} quarters: {int(msk.sum())}  "
              f"E_μ={E_fdic[msk].mean():.2f}  R_μ={R_fdic[msk].mean():.3f}  "
              f"P_rate={P_fdic[msk].mean()*100:.1f}%  "
              f"disc={E_fdic[msk].mean()/(E_fdic[~crisis_any].mean()+1e-10):.2f}×")

print(f"\n  Plots saved to: {PLOTDIR}")
print(f"    protein_1d_signals.png   protein_2d_phase.png")
print(f"    protein_3d_trajectory.png  protein_4d_alarm.png")
print(f"    fdic_1d_signals.png      fdic_2d_phase.png")
print(f"    fdic_3d_landscape.png    fdic_4d_crisis.png")
print("█" * 70)
