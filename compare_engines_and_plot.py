#!/usr/bin/env python3
"""
BSDT-Resonance vs Molecular vs Gravity Engine Comparison
=========================================================
1. Side-by-side performance comparison table (banking G-SIB)
2. 2D energy landscape of E_BS (distance, rate → alarm surface)
3. 3D energy surface with critical curvature identification
4. Hessian eigenvalue analysis to pinpoint phase-transition boundaries

Author: Odeyemi Olusegun Israel
"""
from __future__ import annotations
import os, sys, time, warnings, json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import cm
from mpl_toolkits.mplot3d import Axes3D
from matplotlib.colors import Normalize
from scipy.ndimage import gaussian_filter

warnings.filterwarnings('ignore')
np.random.seed(42)

ROOT = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(ROOT, 'results')
os.makedirs(RESULTS_DIR, exist_ok=True)

print("═══════════════════════════════════════════════════════════════════")
print("  Engine Comparison & Energy Landscape Visualization")
print("═══════════════════════════════════════════════════════════════════\n")

# ═════════════════════════════════════════════════════════════════════════════
# §1. PERFORMANCE COMPARISON TABLE
# ═════════════════════════════════════════════════════════════════════════════
print("┌─────────────────────────────────────────────────────────────────────────┐")
print("│  §1. HEAD-TO-HEAD ENGINE COMPARISON (from saved JSON results)       │")
print("└─────────────────────────────────────────────────────────────────────────┘\n")

# ===========================================================================
# BANKING — all results from results/*.json
# ===========================================================================
print("  ═══ A. G-SIB BANKING PANEL ═══\n")
print(f"  {'Engine':<30s} {'AUC':>7s} {'FAR%':>7s} {'Recall%':>8s} {'GFC Lead':>12s} {'COVID Lead':>12s} {'RateShock':>12s}")
print(f"  {'─'*30} {'─'*7} {'─'*7} {'─'*8} {'─'*12} {'─'*12} {'─'*12}")

# From full_engine_results.json + engine_early_warning_results.json
banking = [
    # engine, auc, far, recall, gfc_lead, covid_lead, rateshock_lead
    ("Molecular (full_engine)",  1.000, "100.0",  "100.0",  "no_alarm",   "60 months",   "60 months"),
    ("Molecular (Alg1+Fused)",  0.930,  "14.3",   "53.8",  "concurrent", "—",           "—"),
    ("HybridGravity",           1.000,  "84.6",  "100.0",  "no_alarm",   "60 months",   "60 months"),
    ("Gravity (full_engine)",   0.876,  "30.8",   "86.8",  "3 months",   "36 months",   "60 months"),
    ("Mode7-Fisher",            0.849,   "3.2",   "46.2",  "—",          "—",           "—"),
    ("Mode6-Fisher",            0.785,   "3.2",   "30.8",  "—",          "—",           "—"),
    ("Molecular+Fisher",        0.880,  "10.0",   "50.0",  "—",          "—",           "—"),
    ("BSDT-Resonance",          0.759,  "21.1",     "—",   "6 months",   "correct miss", "—"),
]

for name, auc, far, recall, gfc, covid, rate in banking:
    print(f"  {name:<30s} {auc:7.3f} {far:>7s} {recall:>8s} {gfc:>12s} {covid:>12s} {rate:>12s}")

print()
print("  Notes:")
print("    • Molecular (full_engine): AUC 1.0 BUT 100% FAR — every quarter alarms (z>2 threshold)")
print("    • Gravity:   GFC 3mo lead (alarm 2007-Q3), COVID 36mo lead (alarm 2017-Q1)")
print("    • Molecular: Misses GFC entirely at z>2, but catches COVID/RateShock 60mo early")
print("    • Hybrid:    Same pattern as Molecular — misses GFC, but 60mo COVID/RateShock leads")
print("    • BSDT-Resonance: GFC 6mo via d+r decomposition, EU Sovereign 24mo, COVID correctly missed")
print("    • Mode7/Mode6: Tested only with percentile threshold (no prospective lead time protocol)")

# ===========================================================================
# ERCOT — all results from engine_early_warning_results.json
# ===========================================================================
print()
print("  ═══ B. ERCOT ENERGY (Hourly, 2019–2022) ═══\n")
print(f"  {'Engine':<22s} {'AUC':>7s} {'FAR%':>7s} {'Uri Lead':>10s} {'COVID':>10s} {'SumPeak':>10s} {'Elliott':>10s}")
print(f"  {'─'*22} {'─'*7} {'─'*7} {'─'*10} {'─'*10} {'─'*10} {'─'*10}")

ercot = [
    ("Molecular",      0.547,  "1.6",  "12.5 days", "10.8 days", "13.0 days", "15.6 days"),
    ("Gravity",        0.538,  "1.9",  "12.5 days", "10.8 days", "13.0 days",  "no_alarm"),
    ("HybridGravity",  0.547,  "1.6",  "12.5 days", "10.8 days", "13.0 days", "15.6 days"),
    ("FrozenWindow",   0.000,  "1.0",  "12.5 days",   "no_alarm",  "no_alarm",  "6.4 days"),
    ("BSDT-Resonance", 0.529, "13.3",     "—",          "96h",      "—",        "48 hours"),
]

for name, auc, far, uri, covid, summer, elli in ercot:
    print(f"  {name:<22s} {auc:7.3f} {far:>7s} {uri:>10s} {covid:>10s} {summer:>10s} {elli:>10s}")

print()
print("  Notes:")
print("    • Molecular: ALL 4 ERCOT events detected with 10–16 day lead times")
print("    • Gravity:   3/4 events (misses Elliott), 12–13 day leads")
print("    • BSDT-Resonance: Elliott 48h, COVID 96h — shorter leads but different protocol")
print("    • Molecular/Gravity use weekly-rolling P99 threshold vs BSDT conformal p-values")

# ===========================================================================
# CYBER — only BSDT-Resonance has results here
# ===========================================================================
print()
print("  ═══ C. CYBERSECURITY (BSDT-Resonance only — no Molecular/Gravity cyber benchmarks) ═══\n")
print(f"  {'Dataset':<16s} {'AUC':>7s} {'BSDT%':>7s} {'Morse%':>7s} {'Betti%':>7s}")
print(f"  {'─'*16} {'─'*7} {'─'*7} {'─'*7} {'─'*7}")
cyber = [
    ("NSL-KDD",      0.9773,  1.0, 0.0, 0.0),
    ("CIC-IDS-2017", 0.8896, 20.0, 0.0, 0.0),
    ("UNSW-NB15",    0.5592, 74.9, 0.0, 0.0),
]
for ds, auc, bsdt, morse, betti in cyber:
    print(f"  {ds:<16s} {auc:7.4f} {bsdt:6.1f}% {morse:6.1f}% {betti:6.1f}%")

# ===========================================================================
# HONEST HEAD-TO-HEAD SUMMARY
# ===========================================================================
print()
print("  ═══ D. HONEST COMPARISON SUMMARY ═══\n")
print("  ┌──────────────────┬─────────────────────────┬─────────────────────────┬──────────────┐")
print("  │ Metric           │ Molecular/Gravity       │ BSDT-Resonance          │ Winner       │")
print("  ├──────────────────┼─────────────────────────┼─────────────────────────┼──────────────┤")
print("  │ Banking AUC      │ 1.000 (Mol) / 0.876 (G)│ 0.759                   │ Molecular    │")
print("  │ Banking FAR      │ 100% (Mol) / 30.8% (G) │ 21.1%                   │ BSDT         │")
print("  │ ERCOT AUC        │ 0.547 (Mol) / 0.538 (G)│ 0.529                   │ Molecular    │")
print("  │ ERCOT FAR        │ 1.6% (Mol) / 1.9% (G)  │ 13.3%                   │ Molecular    │")
print("  │ ERCOT Lead (Uri) │ 12.5 days               │ —                       │ Molecular    │")
print("  │ ERCOT Lead (Elli)│ 15.6d (Mol) / miss (G)  │ 48 hours                │ Molecular    │")
print("  │ Banking GFC Lead │ miss (Mol) / 3mo (G)    │ 6 months                │ BSDT         │")
print("  │ Banking EU Sov.  │ not tested              │ 24 months               │ BSDT         │")
print("  │ Cyber NSL-KDD    │ not tested              │ 0.977 AUC               │ BSDT (only)  │")
print("  │ Cyber CIC-IDS    │ not tested              │ 0.890 AUC               │ BSDT (only)  │")
print("  │ Cross-domain     │ Banking + ERCOT (2)     │ Banking+ERCOT+3Cyber (5)│ BSDT         │")
print("  │ Interpretability │ raw scores / threshold  │ d + r + 3-tier alarm    │ BSDT         │")
print("  │ Calibration      │ percentile / z-score    │ conformal p-values      │ BSDT         │")
print("  └──────────────────┴─────────────────────────┴─────────────────────────┴──────────────┘")
print()

# ═════════════════════════════════════════════════════════════════════════════
# §3. ENERGY LANDSCAPE E_BS — 2D CONTOUR PLOT
#      Using the ACTUAL CanonicalBSDT scoring on synthetic 2D data
# ═════════════════════════════════════════════════════════════════════════════
print("┌─────────────────────────────────────────────────────────────────┐")
print("│  §3. Computing Energy Landscape...                             │")
print("└─────────────────────────────────────────────────────────────────┘\n")

# Import CanonicalBSDT from the benchmark file
sys.path.insert(0, ROOT)
from run_bsdt_benchmarks import CanonicalBSDT

# Generate 2D data with a clear normal cluster + anomalous region
rng = np.random.default_rng(42)
# Normal cluster (centred at origin)
X_normal = rng.normal(0, 1, (500, 2))
# Anomalous points (spread further out)
X_anom = rng.normal(0, 1, (50, 2)) * 3.0 + np.array([3.0, 3.0])

X_all = np.vstack([X_normal, X_anom])
y_all = np.concatenate([np.zeros(500), np.ones(50)])

# Fit BSDT on normal reference
bsdt = CanonicalBSDT(k=10)
bsdt.fit(X_normal)

# Create fine grid covering the space
grid_n = 200
x_min, x_max = -6, 8
y_min, y_max = -6, 8
xx, yy = np.meshgrid(np.linspace(x_min, x_max, grid_n),
                      np.linspace(y_min, y_max, grid_n))
X_grid = np.column_stack([xx.ravel(), yy.ravel()])

# Compute E_BS on the grid
E_grid = bsdt.energy(X_grid).reshape(grid_n, grid_n)
MFLS_grid = bsdt.mfls(X_grid).reshape(grid_n, grid_n)
gamma_grid = bsdt.gamma(X_grid).reshape(grid_n, grid_n)

# Compute channels on grid for decomposition
ch_grid = bsdt.channels(X_grid)
dC = ch_grid['delta_C'].reshape(grid_n, grid_n)
dG = ch_grid['delta_G'].reshape(grid_n, grid_n)
dA = ch_grid['delta_A'].reshape(grid_n, grid_n)
dT = ch_grid['delta_T'].reshape(grid_n, grid_n)

print(f"  Grid: {grid_n}×{grid_n} = {grid_n**2} points")
print(f"  E_BS range: [{E_grid.min():.4f}, {E_grid.max():.4f}]")
print(f"  MFLS range: [{MFLS_grid.min():.4f}, {MFLS_grid.max():.4f}]")
print(f"  γ range:    [{gamma_grid.min():.4f}, {gamma_grid.max():.4f}]")

# ═════════════════════════════════════════════════════════════════════════════
# §4. HESSIAN CURVATURE ANALYSIS — CRITICAL POINTS
# ═════════════════════════════════════════════════════════════════════════════
print("\n┌─────────────────────────────────────────────────────────────────┐")
print("│  §4. Hessian Curvature Analysis — Critical Points             │")
print("└─────────────────────────────────────────────────────────────────┘\n")

# Compute numerical Hessian of E_BS at grid points (subsampled)
curvature_n = 80
xx_c, yy_c = np.meshgrid(np.linspace(x_min, x_max, curvature_n),
                          np.linspace(y_min, y_max, curvature_n))
X_curv = np.column_stack([xx_c.ravel(), yy_c.ravel()])

# Compute Gaussian curvature K and mean curvature H via finite differences
eps_fd = 0.05
E_center = bsdt.energy(X_curv)

# Partial derivatives via central differences
E_xp = bsdt.energy(X_curv + np.array([eps_fd, 0]))
E_xm = bsdt.energy(X_curv - np.array([eps_fd, 0]))
E_yp = bsdt.energy(X_curv + np.array([0, eps_fd]))
E_ym = bsdt.energy(X_curv - np.array([0, eps_fd]))

E_xpyp = bsdt.energy(X_curv + np.array([eps_fd, eps_fd]))
E_xpym = bsdt.energy(X_curv + np.array([eps_fd, -eps_fd]))
E_xmyp = bsdt.energy(X_curv + np.array([-eps_fd, eps_fd]))
E_xmym = bsdt.energy(X_curv - np.array([eps_fd, eps_fd]))

# Second derivatives
E_xx = (E_xp - 2 * E_center + E_xm) / eps_fd**2
E_yy = (E_yp - 2 * E_center + E_ym) / eps_fd**2
E_xy = (E_xpyp - E_xpym - E_xmyp + E_xmym) / (4 * eps_fd**2)

# First derivatives (for gradient norm)
E_x = (E_xp - E_xm) / (2 * eps_fd)
E_y = (E_yp - E_ym) / (2 * eps_fd)
grad_norm = np.sqrt(E_x**2 + E_y**2)

# Gaussian curvature: K = det(H) / (1 + |∇f|²)²
# Mean curvature:     H_mean = ((1+fx²)fyy - 2fxfyfxy + (1+fy²)fxx) / (2(1+|∇f|²)^(3/2))
denom = (1 + E_x**2 + E_y**2)
gauss_curvature = (E_xx * E_yy - E_xy**2) / denom**2
mean_curvature = ((1 + E_x**2) * E_yy - 2 * E_x * E_y * E_xy + 
                  (1 + E_y**2) * E_xx) / (2 * denom**1.5)

# Hessian eigenvalues at each point
lambda_1 = 0.5 * (E_xx + E_yy - np.sqrt(np.maximum((E_xx - E_yy)**2 + 4 * E_xy**2, 0)))
lambda_2 = 0.5 * (E_xx + E_yy + np.sqrt(np.maximum((E_xx - E_yy)**2 + 4 * E_xy**2, 0)))

# Morse index: count of negative eigenvalues
morse_index = (lambda_1 < 0).astype(int) + (lambda_2 < 0).astype(int)

# Reshape for plotting
K_grid = gauss_curvature.reshape(curvature_n, curvature_n)
H_mean_grid = mean_curvature.reshape(curvature_n, curvature_n)
lam1_grid = lambda_1.reshape(curvature_n, curvature_n)
lam2_grid = lambda_2.reshape(curvature_n, curvature_n)
morse_grid = morse_index.reshape(curvature_n, curvature_n)
grad_grid = grad_norm.reshape(curvature_n, curvature_n)

# Find critical points (where gradient ≈ 0)
grad_threshold = np.percentile(grad_norm, 5)
critical_mask = grad_norm < grad_threshold
critical_points = X_curv[critical_mask]
critical_morse = morse_index[critical_mask]
critical_K = gauss_curvature[critical_mask]
critical_H = mean_curvature[critical_mask]
critical_E = E_center[critical_mask]

# Classify critical points
minima = critical_points[critical_morse == 0]  # Both λ positive → minimum
saddles = critical_points[critical_morse == 1]  # Mixed signs → saddle
maxima = critical_points[critical_morse == 2]   # Both λ negative → maximum

print(f"  Gradient threshold (5th pctl): {grad_threshold:.6f}")
print(f"  Critical points found: {len(critical_points)}")
print(f"    Minima  (morse_idx=0, K>0, H>0): {len(minima)}")
print(f"    Saddles (morse_idx=1, K<0):       {len(saddles)}")
print(f"    Maxima  (morse_idx=2, K>0, H<0):  {len(maxima)}")

# Identify the energy basin boundary (where K changes sign)
K_sign_change = np.diff(np.sign(K_grid.ravel())).reshape(-1)
n_sign_changes = np.count_nonzero(K_sign_change)
print(f"  Gaussian curvature sign changes: {n_sign_changes} (phase boundaries)")

# Key curvature statistics
print(f"\n  Curvature statistics:")
print(f"    Gaussian K: [{gauss_curvature.min():.4f}, {gauss_curvature.max():.4f}]")
print(f"    Mean H:     [{mean_curvature.min():.4f}, {mean_curvature.max():.4f}]")
print(f"    λ₁ (min):   [{lambda_1.min():.4f}, {lambda_1.max():.4f}]")
print(f"    λ₂ (max):   [{lambda_2.min():.4f}, {lambda_2.max():.4f}]")

# ═════════════════════════════════════════════════════════════════════════════
# §5. FIGURE 1 — 2D ENERGY LANDSCAPE + CURVATURE
# ═════════════════════════════════════════════════════════════════════════════
print("\n  Plotting 2D energy landscape...", end=" ", flush=True)

fig, axes = plt.subplots(2, 3, figsize=(22, 14))
fig.suptitle("BSDT-Resonance Engine — Energy Landscape $E_{BS}$ & Critical Curvature",
             fontsize=16, fontweight='bold', y=0.98)

# --- Panel (a): E_BS contour with data points ---
ax = axes[0, 0]
E_smooth = gaussian_filter(E_grid, sigma=1.5)
levels = np.linspace(0, np.percentile(E_grid, 99), 30)
cf = ax.contourf(xx, yy, E_smooth, levels=levels, cmap='magma', extend='max')
ax.contour(xx, yy, E_smooth, levels=levels[::3], colors='white', linewidths=0.3, alpha=0.5)
# Data points
ax.scatter(X_normal[:, 0], X_normal[:, 1], s=4, c='cyan', alpha=0.3, label='Normal', zorder=5)
ax.scatter(X_anom[:, 0], X_anom[:, 1], s=15, c='red', marker='^', alpha=0.8, label='Anomaly', zorder=6)
# Critical points
if len(minima) > 0:
    ax.scatter(minima[:, 0], minima[:, 1], s=80, c='lime', marker='*', 
               edgecolors='black', linewidths=0.5, zorder=10, label=f'Minima ({len(minima)})')
if len(saddles) > 0:
    ax.scatter(saddles[:, 0], saddles[:, 1], s=60, c='yellow', marker='D',
               edgecolors='black', linewidths=0.5, zorder=10, label=f'Saddles ({len(saddles)})')
if len(maxima) > 0:
    ax.scatter(maxima[:, 0], maxima[:, 1], s=60, c='orange', marker='s',
               edgecolors='black', linewidths=0.5, zorder=10, label=f'Maxima ({len(maxima)})')
ax.set_xlabel('$x_1$', fontsize=11)
ax.set_ylabel('$x_2$', fontsize=11)
ax.set_title('(a) $E_{BS} = \\sum w_k \\delta_k^2$ — Blind-Spot Energy', fontsize=12)
ax.legend(fontsize=8, loc='upper left')
plt.colorbar(cf, ax=ax, label='$E_{BS}$', shrink=0.8)

# --- Panel (b): MFLS (gradient norm) ---
ax = axes[0, 1]
MFLS_smooth = gaussian_filter(MFLS_grid, sigma=1.5)
levels_m = np.linspace(0, np.percentile(MFLS_grid, 99), 30)
cf2 = ax.contourf(xx, yy, MFLS_smooth, levels=levels_m, cmap='inferno', extend='max')
ax.contour(xx, yy, MFLS_smooth, levels=levels_m[::3], colors='white', linewidths=0.3, alpha=0.5)
ax.scatter(X_normal[:, 0], X_normal[:, 1], s=4, c='cyan', alpha=0.3, zorder=5)
ax.scatter(X_anom[:, 0], X_anom[:, 1], s=15, c='red', marker='^', alpha=0.8, zorder=6)
ax.set_xlabel('$x_1$', fontsize=11)
ax.set_ylabel('$x_2$', fontsize=11)
ax.set_title('(b) $\\|\\nabla E_{BS}\\|_F$ — MFLS Gradient Norm', fontsize=12)
plt.colorbar(cf2, ax=ax, label='MFLS', shrink=0.8)

# --- Panel (c): γ friction surface ---
ax = axes[0, 2]
gamma_smooth = gaussian_filter(gamma_grid, sigma=1.5)
cf3 = ax.contourf(xx, yy, gamma_smooth, levels=30, cmap='RdYlGn_r')
ax.contour(xx, yy, gamma_smooth, levels=[0.5], colors='white', linewidths=2, linestyles='--')
ax.scatter(X_normal[:, 0], X_normal[:, 1], s=4, c='blue', alpha=0.3, zorder=5)
ax.scatter(X_anom[:, 0], X_anom[:, 1], s=15, c='red', marker='^', alpha=0.8, zorder=6)
ax.set_xlabel('$x_1$', fontsize=11)
ax.set_ylabel('$x_2$', fontsize=11)
ax.set_title('(c) $\\gamma = e/(e + \\theta_{BS})$ — Adaptive Friction', fontsize=12)
plt.colorbar(cf3, ax=ax, label='$\\gamma$', shrink=0.8)

# --- Panel (d): Gaussian curvature K ---
ax = axes[1, 0]
K_smooth = gaussian_filter(K_grid, sigma=1.2)
K_clip = np.clip(K_smooth, np.percentile(K_smooth, 2), np.percentile(K_smooth, 98))
cf4 = ax.contourf(xx_c, yy_c, K_clip, levels=30, cmap='RdBu_r')
# Phase boundary: K = 0 contour
ax.contour(xx_c, yy_c, K_smooth, levels=[0], colors='lime', linewidths=2.5, 
           linestyles='-', zorder=8)
if len(saddles) > 0:
    ax.scatter(saddles[:, 0], saddles[:, 1], s=80, c='yellow', marker='D',
               edgecolors='black', linewidths=1, zorder=10, label=f'Saddles ({len(saddles)})')
ax.set_xlabel('$x_1$', fontsize=11)
ax.set_ylabel('$x_2$', fontsize=11)
ax.set_title('(d) Gaussian Curvature $K = \\lambda_1 \\lambda_2$ — Phase Boundaries', fontsize=12)
ax.legend(fontsize=9)
plt.colorbar(cf4, ax=ax, label='$K$', shrink=0.8)

# --- Panel (e): Morse index map ---
ax = axes[1, 1]
morse_smooth = morse_grid.astype(float)
im5 = ax.imshow(morse_smooth, extent=[x_min, x_max, y_min, y_max], origin='lower',
                cmap='Set1', vmin=-0.5, vmax=2.5, aspect='auto', interpolation='nearest')
# Overlay K=0 boundary
ax.contour(xx_c, yy_c, K_smooth, levels=[0], colors='lime', linewidths=2, zorder=8)
if len(minima) > 0:
    ax.scatter(minima[:, 0], minima[:, 1], s=60, c='white', marker='*',
               edgecolors='black', linewidths=0.5, zorder=10)
if len(saddles) > 0:
    ax.scatter(saddles[:, 0], saddles[:, 1], s=50, c='yellow', marker='D',
               edgecolors='black', linewidths=0.5, zorder=10)
ax.set_xlabel('$x_1$', fontsize=11)
ax.set_ylabel('$x_2$', fontsize=11)
ax.set_title('(e) Morse Index — Phase Regions', fontsize=12)
cbar = plt.colorbar(im5, ax=ax, ticks=[0, 1, 2], shrink=0.8)
cbar.set_ticklabels(['0 (min)', '1 (saddle)', '2 (max)'])

# --- Panel (f): Channel decomposition along a radial slice ---
ax = axes[1, 2]
# Radial slice from centroid through anomaly region
angles = np.linspace(0, 2 * np.pi, 360, endpoint=False)
r_vals = np.linspace(0, 7, 200)
# One specific slice: from origin toward (3, 3)
theta_target = np.arctan2(3, 3)  # 45°
x_slice = r_vals * np.cos(theta_target)
y_slice = r_vals * np.sin(theta_target)
X_slice = np.column_stack([x_slice, y_slice])

ch_slice = bsdt.channels(X_slice)
E_slice = bsdt.energy(X_slice)
w = bsdt.fisher_w_

ax.plot(r_vals, w[0] * ch_slice['delta_C']**2, 'b-', linewidth=1.5, label=f'$w_C \\delta_C^2$ (w={w[0]:.2f})')
ax.plot(r_vals, w[1] * ch_slice['delta_G']**2, 'g-', linewidth=1.5, label=f'$w_G \\delta_G^2$ (w={w[1]:.2f})')
ax.plot(r_vals, w[2] * ch_slice['delta_A']**2, 'r-', linewidth=1.5, label=f'$w_A \\delta_A^2$ (w={w[2]:.2f})')
ax.plot(r_vals, w[3] * ch_slice['delta_T']**2, 'm-', linewidth=1.5, label=f'$w_T \\delta_T^2$ (w={w[3]:.2f})')
ax.plot(r_vals, E_slice, 'k-', linewidth=2.5, label='$E_{BS}$ (total)')
# Mark critical distance (where E_BS crosses alarm threshold equivalent)
E_ref_median = float(np.median(bsdt.energy(X_normal)))
ax.axhline(E_ref_median, color='gray', linestyle='--', alpha=0.5, label=f'Reference median ({E_ref_median:.3f})')
ax.axvline(2.0, color='orange', linestyle=':', alpha=0.7, label='1σ boundary')
ax.axvline(3.0, color='red', linestyle=':', alpha=0.7, label='Phase transition')
ax.set_xlabel('Radial distance $r$ from centroid (toward anomaly region)', fontsize=11)
ax.set_ylabel('Channel energy contribution', fontsize=11)
ax.set_title('(f) Channel Decomposition Along Radial Slice (45°)', fontsize=12)
ax.legend(fontsize=8, loc='upper left')
ax.set_xlim(0, 7)

plt.tight_layout(rect=[0, 0, 1, 0.95])
fig_path_2d = os.path.join(RESULTS_DIR, 'bsdt_energy_landscape_2d.png')
plt.savefig(fig_path_2d, dpi=180, bbox_inches='tight')
plt.close()
print(f"SAVED → {fig_path_2d}")

# ═════════════════════════════════════════════════════════════════════════════
# §6. FIGURE 2 — 3D ENERGY SURFACE + CRITICAL CURVATURE
# ═════════════════════════════════════════════════════════════════════════════
print("  Plotting 3D energy surface...", end=" ", flush=True)

fig = plt.figure(figsize=(22, 10))
fig.suptitle("BSDT-Resonance Engine — 3D Energy Surface & Critical Curvature",
             fontsize=16, fontweight='bold', y=0.98)

# --- Panel (a): 3D E_BS surface ---
ax1 = fig.add_subplot(131, projection='3d')
E_smooth_3d = gaussian_filter(E_grid, sigma=2.0)
# Subsample for 3D rendering
stride = 4
xs, ys = xx[::stride, ::stride], yy[::stride, ::stride]
es = E_smooth_3d[::stride, ::stride]
surf = ax1.plot_surface(xs, ys, es, cmap='magma', alpha=0.85,
                        edgecolor='none', antialiased=True,
                        rstride=1, cstride=1)

# Plot critical points on the surface
if len(minima) > 0:
    min_E = bsdt.energy(minima)
    ax1.scatter(minima[:, 0], minima[:, 1], min_E, s=100, c='lime', marker='*',
                edgecolors='black', linewidths=0.5, zorder=10, label='Minima')
if len(saddles) > 0:
    sad_E = bsdt.energy(saddles)
    ax1.scatter(saddles[:, 0], saddles[:, 1], sad_E, s=80, c='yellow', marker='D',
                edgecolors='black', linewidths=0.5, zorder=10, label='Saddles')

ax1.set_xlabel('$x_1$', fontsize=10)
ax1.set_ylabel('$x_2$', fontsize=10)
ax1.set_zlabel('$E_{BS}$', fontsize=10)
ax1.set_title('(a) $E_{BS}$ Surface\n(Minima=★, Saddles=◆)', fontsize=11)
ax1.view_init(elev=25, azim=-60)
fig.colorbar(surf, ax=ax1, shrink=0.5, label='$E_{BS}$')

# --- Panel (b): 3D Gaussian curvature ---
ax2 = fig.add_subplot(132, projection='3d')
K_smooth_3d = gaussian_filter(K_grid, sigma=1.5)
K_clip_3d = np.clip(K_smooth_3d, np.percentile(K_smooth_3d, 5), np.percentile(K_smooth_3d, 95))
stride_c = max(1, curvature_n // 50)
xs_c, ys_c = xx_c[::stride_c, ::stride_c], yy_c[::stride_c, ::stride_c]
ks_c = K_clip_3d[::stride_c, ::stride_c]

# Color map: red for K > 0 (elliptic), blue for K < 0 (hyperbolic)
norm_k = Normalize(vmin=K_clip_3d.min(), vmax=K_clip_3d.max())
colors = cm.RdBu_r(norm_k(ks_c))
surf2 = ax2.plot_surface(xs_c, ys_c, ks_c, facecolors=colors, alpha=0.85,
                         edgecolor='none', antialiased=True, rstride=1, cstride=1)

# K = 0 plane (phase boundary)
ax2.plot_surface(xs_c, ys_c, np.zeros_like(ks_c), alpha=0.15, color='green')

ax2.set_xlabel('$x_1$', fontsize=10)
ax2.set_ylabel('$x_2$', fontsize=10)
ax2.set_zlabel('$K$', fontsize=10)
ax2.set_title('(b) Gaussian Curvature $K$\n(Red=elliptic, Blue=hyperbolic)', fontsize=11)
ax2.view_init(elev=20, azim=-45)

# --- Panel (c): 3D γ friction surface ---
ax3 = fig.add_subplot(133, projection='3d')
gamma_smooth_3d = gaussian_filter(gamma_grid, sigma=2.0)
gs = gamma_smooth_3d[::stride, ::stride]
surf3 = ax3.plot_surface(xs, ys, gs, cmap='RdYlGn_r', alpha=0.85,
                         edgecolor='none', antialiased=True, rstride=1, cstride=1)

# γ = 0.5 plane (transition threshold)
ax3.plot_surface(xs, ys, np.full_like(gs, 0.5), alpha=0.2, color='cyan')

ax3.set_xlabel('$x_1$', fontsize=10)
ax3.set_ylabel('$x_2$', fontsize=10)
ax3.set_zlabel('$\\gamma$', fontsize=10)
ax3.set_title('(c) Friction $\\gamma = e/(e + \\theta_{BS})$\n(Cyan plane = transition)', fontsize=11)
ax3.view_init(elev=25, azim=-50)
fig.colorbar(surf3, ax=ax3, shrink=0.5, label='$\\gamma$')

plt.tight_layout(rect=[0, 0, 1, 0.94])
fig_path_3d = os.path.join(RESULTS_DIR, 'bsdt_energy_landscape_3d.png')
plt.savefig(fig_path_3d, dpi=180, bbox_inches='tight')
plt.close()
print(f"SAVED → {fig_path_3d}")

# ═════════════════════════════════════════════════════════════════════════════
# §7. FIGURE 3 — DISTANCE + RATE ALARM SURFACE (OPERATIONAL VIEW)
# ═════════════════════════════════════════════════════════════════════════════
print("  Plotting distance+rate alarm surface...", end=" ", flush=True)

fig, axes = plt.subplots(1, 3, figsize=(20, 6))
fig.suptitle("BSDT-Resonance Engine — Distance/Rate Alarm Decision Surface",
             fontsize=14, fontweight='bold', y=1.02)

# (a) Temporal alarm: d + max(r, 0) > 1.0
d_range = np.linspace(-1, 4, 300)
r_range = np.linspace(-2, 3, 300)
dd, rr = np.meshgrid(d_range, r_range)
alarm_temporal = dd + np.maximum(rr, 0)  # d + max(r, 0)
alarm_nontemporal = dd.copy()  # d only

ax = axes[0]
cf = ax.contourf(dd, rr, alarm_temporal, levels=50, cmap='RdYlGn_r')
ax.contour(dd, rr, alarm_temporal, levels=[1.0], colors='white', linewidths=3, linestyles='-')
ax.contourf(dd, rr, (alarm_temporal > 1.0).astype(float), levels=[0.5, 1.5], 
            colors=['red'], alpha=0.15)
# Mark key events
events = {
    'GFC Q8':       (0.80, 0.50, 'red'),
    'EU Q13':       (1.11, -0.10, 'orange'),
    'COVID':        (0.31, -0.07, 'green'),
    'Elliott 48h':  (0.71, 0.31, 'blue'),
}
for name, (d_val, r_val, clr) in events.items():
    ax.scatter(d_val, r_val, s=70, c=clr, edgecolors='black', linewidths=1, zorder=10)
    ax.annotate(name, (d_val, r_val), textcoords="offset points",
                xytext=(8, 5), fontsize=8, fontweight='bold', color=clr)
ax.set_xlabel('Distance $d$ ($\\sigma$ from normal)', fontsize=11)
ax.set_ylabel('Rate $r$ ($\\sigma / \\Delta t$)', fontsize=11)
ax.set_title('(a) Temporal Alarm: $d + \\max(r,0) > 1$', fontsize=12)
ax.axhline(0, color='gray', linestyle=':', alpha=0.3)
ax.axvline(1, color='gray', linestyle=':', alpha=0.3)
plt.colorbar(cf, ax=ax, label='$d + \\max(r, 0)$', shrink=0.85)

# (b) Non-temporal alarm: d > 1.0
ax = axes[1]
cf2 = ax.contourf(dd, rr, alarm_nontemporal, levels=50, cmap='RdYlGn_r')
ax.contour(dd, rr, alarm_nontemporal, levels=[1.0], colors='white', linewidths=3, linestyles='-')
ax.contourf(dd, rr, (alarm_nontemporal > 1.0).astype(float), levels=[0.5, 1.5],
            colors=['red'], alpha=0.15)
ax.set_xlabel('Distance $d$ ($\\sigma$ from normal)', fontsize=11)
ax.set_ylabel('Rate $r$ (ignored)', fontsize=11)
ax.set_title('(b) Non-Temporal Alarm: $d > 1$ (cyber)', fontsize=12)
ax.axhline(0, color='gray', linestyle=':', alpha=0.3)
ax.axvline(1, color='gray', linestyle=':', alpha=0.3)
plt.colorbar(cf2, ax=ax, label='$d$', shrink=0.85)

# (c) Curvature of the alarm boundary
ax = axes[2]
# The alarm boundary d + max(r, 0) = 1 has curvature = 0 (it's a line),
# but the ENERGY surface beneath it has curvature — show the second derivative
# of E_BS along the d-axis as a function of d
d_1d = np.linspace(-1, 5, 500)
# Approximate: E_BS ≈ sigmoid along d, so d²E/dd² shows inflection
# Use actual E_BS along the radial slice
E_radial = bsdt.energy(np.column_stack([d_1d * np.cos(theta_target) * 1.5,
                                         d_1d * np.sin(theta_target) * 1.5]))
dE_dd = np.gradient(E_radial, d_1d)
d2E_dd2 = np.gradient(dE_dd, d_1d)

ax.plot(d_1d, E_radial / max(E_radial.max(), 1e-10), 'k-', linewidth=2, label='$E_{BS}$ (normalized)')
ax.plot(d_1d, dE_dd / max(abs(dE_dd).max(), 1e-10), 'b--', linewidth=1.5, label="$E'_{BS}$ (gradient)")
ax.plot(d_1d, d2E_dd2 / max(abs(d2E_dd2).max(), 1e-10), 'r-', linewidth=1.5, label="$E''_{BS}$ (curvature)")
ax.axhline(0, color='gray', linestyle=':', alpha=0.3)
ax.axvline(1, color='orange', linestyle='--', alpha=0.7, label='Alarm threshold (d=1σ)')

# Find inflection points (where d²E/dd² ≈ 0)
zero_crossings = np.where(np.diff(np.sign(d2E_dd2)))[0]
for zc in zero_crossings:
    ax.axvline(d_1d[zc], color='green', linestyle=':', alpha=0.5)
    ax.scatter(d_1d[zc], 0, s=40, c='green', zorder=10)
    ax.annotate(f'Inflection\n({d_1d[zc]:.1f}σ)', (d_1d[zc], 0),
                textcoords="offset points", xytext=(10, 10), fontsize=8, color='green')

ax.set_xlabel('Distance from normal ($\\sigma$)', fontsize=11)
ax.set_ylabel('Normalized value', fontsize=11)
ax.set_title("(c) $E_{BS}$ Curvature Along Radial Direction", fontsize=12)
ax.legend(fontsize=8, loc='upper left')
ax.set_xlim(-1, 5)

plt.tight_layout(rect=[0, 0, 1, 0.96])
fig_path_alarm = os.path.join(RESULTS_DIR, 'bsdt_alarm_surface.png')
plt.savefig(fig_path_alarm, dpi=180, bbox_inches='tight')
plt.close()
print(f"SAVED → {fig_path_alarm}")

# ═════════════════════════════════════════════════════════════════════════════
# §8. FIGURE 4 — FULL CURVATURE ANALYSIS (DEDICATED)
# ═════════════════════════════════════════════════════════════════════════════
print("  Plotting full curvature analysis...", end=" ", flush=True)

fig, axes = plt.subplots(2, 2, figsize=(16, 14))
fig.suptitle("BSDT Energy Surface — Critical Curvature Analysis",
             fontsize=16, fontweight='bold', y=0.98)

# (a) Hessian eigenvalue λ₁ (minimum eigenvalue)
ax = axes[0, 0]
lam1_smooth = gaussian_filter(lam1_grid, sigma=1.2)
l1_clip = np.clip(lam1_smooth, np.percentile(lam1_smooth, 3), np.percentile(lam1_smooth, 97))
cf = ax.contourf(xx_c, yy_c, l1_clip, levels=30, cmap='coolwarm')
ax.contour(xx_c, yy_c, lam1_smooth, levels=[0], colors='lime', linewidths=2.5, zorder=8)
if len(saddles) > 0:
    ax.scatter(saddles[:, 0], saddles[:, 1], s=60, c='yellow', marker='D',
               edgecolors='black', linewidths=1, zorder=10)
ax.set_xlabel('$x_1$', fontsize=11)
ax.set_ylabel('$x_2$', fontsize=11)
ax.set_title('(a) $\\lambda_1$ (min eigenvalue)\nGreen line: $\\lambda_1 = 0$ boundary', fontsize=12)
plt.colorbar(cf, ax=ax, label='$\\lambda_1$', shrink=0.8)

# (b) Hessian eigenvalue λ₂ (maximum eigenvalue)
ax = axes[0, 1]
lam2_smooth = gaussian_filter(lam2_grid, sigma=1.2)
l2_clip = np.clip(lam2_smooth, np.percentile(lam2_smooth, 3), np.percentile(lam2_smooth, 97))
cf2 = ax.contourf(xx_c, yy_c, l2_clip, levels=30, cmap='coolwarm')
ax.contour(xx_c, yy_c, lam2_smooth, levels=[0], colors='lime', linewidths=2.5, zorder=8)
ax.set_xlabel('$x_1$', fontsize=11)
ax.set_ylabel('$x_2$', fontsize=11)
ax.set_title('(b) $\\lambda_2$ (max eigenvalue)\nGreen line: $\\lambda_2 = 0$ boundary', fontsize=12)
plt.colorbar(cf2, ax=ax, label='$\\lambda_2$', shrink=0.8)

# (c) Mean curvature H
ax = axes[1, 0]
H_smooth = gaussian_filter(H_mean_grid, sigma=1.2)
H_clip = np.clip(H_smooth, np.percentile(H_smooth, 3), np.percentile(H_smooth, 97))
cf3 = ax.contourf(xx_c, yy_c, H_clip, levels=30, cmap='PuOr')
ax.contour(xx_c, yy_c, H_smooth, levels=[0], colors='lime', linewidths=2.5, zorder=8)
ax.set_xlabel('$x_1$', fontsize=11)
ax.set_ylabel('$x_2$', fontsize=11)
ax.set_title('(c) Mean Curvature $H = (\\lambda_1 + \\lambda_2)/2$\nGreen: $H = 0$ (inflection)', fontsize=12)
plt.colorbar(cf3, ax=ax, label='$H$', shrink=0.8)

# (d) Gradient magnitude |∇E_BS| with streamlines
ax = axes[1, 1]
grad_smooth = gaussian_filter(grad_grid, sigma=1.2)
g_clip = np.clip(grad_smooth, 0, np.percentile(grad_smooth, 97))
cf4 = ax.contourf(xx_c, yy_c, g_clip, levels=30, cmap='viridis')
# Streamlines (gradient flow)
E_for_stream = gaussian_filter(
    bsdt.energy(np.column_stack([xx_c.ravel(), yy_c.ravel()])).reshape(curvature_n, curvature_n),
    sigma=2.0)
gy, gx = np.gradient(E_for_stream, (y_max-y_min)/curvature_n, (x_max-x_min)/curvature_n)
speed = np.sqrt(gx**2 + gy**2) + 1e-10
ax.streamplot(xx_c, yy_c, gx, gy, color='white', linewidth=0.5, density=1.2,
              arrowsize=0.8, arrowstyle='->')
if len(minima) > 0:
    ax.scatter(minima[:, 0], minima[:, 1], s=80, c='lime', marker='*',
               edgecolors='black', linewidths=1, zorder=10, label='Minima')
if len(saddles) > 0:
    ax.scatter(saddles[:, 0], saddles[:, 1], s=60, c='yellow', marker='D',
               edgecolors='black', linewidths=1, zorder=10, label='Saddles')
ax.set_xlabel('$x_1$', fontsize=11)
ax.set_ylabel('$x_2$', fontsize=11)
ax.set_title('(d) $|\\nabla E_{BS}|$ + Gradient Streamlines\n(Flow toward minima)', fontsize=12)
ax.legend(fontsize=9, loc='upper left')
plt.colorbar(cf4, ax=ax, label='$|\\nabla E_{BS}|$', shrink=0.8)

plt.tight_layout(rect=[0, 0, 1, 0.95])
fig_path_curv = os.path.join(RESULTS_DIR, 'bsdt_curvature_analysis.png')
plt.savefig(fig_path_curv, dpi=180, bbox_inches='tight')
plt.close()
print(f"SAVED → {fig_path_curv}")

# ═════════════════════════════════════════════════════════════════════════════
# §9. SUMMARY
# ═════════════════════════════════════════════════════════════════════════════
print("\n" + "═" * 70)
print("  HONEST COMPARISON SUMMARY")
print("═" * 70)
print()
print("  Molecular/Gravity STRENGTHS over BSDT-Resonance:")
print("    ✓ Higher banking AUC: Molecular 1.0 / 0.93 vs BSDT 0.76")
print("    ✓ Better ERCOT lead times: 12–16 DAYS vs BSDT 48–96 HOURS")
print("    ✓ Lower ERCOT FAR: 1.6% vs BSDT 13.3%")
print("    ✓ Molecular detects ALL 4 ERCOT events (BSDT only 2 with d+r)")
print("    ✓ Gravity detects GFC 3 months early (Molecular misses GFC)")
print()
print("  BSDT-Resonance STRENGTHS over Molecular/Gravity:")
print("    ✓ Cross-domain: 5 datasets (vs 2 for Molecular/Gravity)")
print("    ✓ Cyber: NSL-KDD 0.977 AUC, CIC-IDS 0.890 (no Molecular/Gravity cyber results)")
print("    ✓ GFC lead: 6 months (vs 3mo Gravity, miss for Molecular)")
print("    ✓ EU Sovereign: 24 months lead (unique — not tested by others)")
print("    ✓ COVID correct miss (exogenous) vs Molecular's 100% FAR on banking")
print("    ✓ Interpretable: d + r decomposition explains WHY alarms fire")
print("    ✓ Conformal p-values vs ad-hoc percentile/z-score thresholds")
print("    ✓ 3-tier topology-aware alarm (BSDT → Morse → Betti)")
print()
print("  BOTTOM LINE: Different tools for different jobs")
print("    - Molecular/Gravity: BEST for single-domain max discrimination + long leads")
print("    - BSDT-Resonance: BEST for multi-domain, interpretable, calibrated monitoring")
print()
print("  Critical curvature findings:")
print(f"    • {len(minima)} energy minima (stable basins in normal region)")
print(f"    • {len(saddles)} saddle points (phase transition boundaries)")
print(f"    • {len(maxima)} energy maxima (deep anomaly region)")
print(f"    • K=0 contour defines the critical phase boundary between")
print(f"      elliptic (stable, K>0) and hyperbolic (unstable, K<0) regimes")
print(f"    • Morse index transitions from 0→1→2 mark topological bifurcations")
print()
print("  Figures saved:")
print(f"    {fig_path_2d}")
print(f"    {fig_path_3d}")
print(f"    {fig_path_alarm}")
print(f"    {fig_path_curv}")
print()
print("Done.")
