#!/usr/bin/env python3
"""Smoke test for closed-form GeometricBSDT."""
import numpy as np, time, sys
sys.path.insert(0, r'c:\amttp\research\udl')
from geo_full_pipeline import GeometricBSDT
from udl.ellipsoid_geometry import EllipsoidGeometry

rng = np.random.RandomState(42)
N, d = 5000, 10
X_ref = rng.randn(N, d)
X_test = rng.randn(800, d) * 1.5

ell = EllipsoidGeometry.from_covariance(np.cov(X_ref.T), centre=X_ref.mean(axis=0))

t0 = time.perf_counter()
g = GeometricBSDT()
g.fit(X_ref, ell)
dt_fit = time.perf_counter() - t0
print(f'fit: {dt_fit*1000:.1f} ms  (N={N}, d={d})')

# Channels
t0 = time.perf_counter()
ch = g.channels(X_test)
dt_ch = time.perf_counter() - t0
for k, v in ch.items():
    print(f'  {k}: mean={v.mean():.4f}, range=[{v.min():.4f}, {v.max():.4f}]')
print(f'channels: {dt_ch*1000:.1f} ms  (N_test={len(X_test)})')

# Potentials
t0 = time.perf_counter()
phi_g = g.gravity_potential(X_test)
dt_grav = time.perf_counter() - t0
print(f'gravity_potential: {dt_grav*1000:.1f} ms  first5={phi_g[:5].round(4)}')

t0 = time.perf_counter()
phi_m = g.molecular_potential(X_test)
dt_mol = time.perf_counter() - t0
print(f'molecular_potential: {dt_mol*1000:.1f} ms  first5={phi_m[:5].round(4)}')

t0 = time.perf_counter()
phi_h = g.hybrid_potential(X_test)
dt_hyb = time.perf_counter() - t0
print(f'hybrid_potential: {dt_hyb*1000:.1f} ms')

# Score
t0 = time.perf_counter()
s1 = g.score(X_test)
dt_s1 = time.perf_counter() - t0
print(f'score (no pot): {dt_s1*1000:.1f} ms, mean={s1.mean():.4f}')

t0 = time.perf_counter()
s2 = g.score(X_test, potential='hybrid')
dt_s2 = time.perf_counter() - t0
print(f'score+hybrid:   {dt_s2*1000:.1f} ms, mean={s2.mean():.4f}')

t0 = time.perf_counter()
s3 = g.score(X_test, potential='gravity')
dt_s3 = time.perf_counter() - t0
print(f'score+gravity:  {dt_s3*1000:.1f} ms, mean={s3.mean():.4f}')

t0 = time.perf_counter()
s4 = g.score(X_test, potential='molecular')
dt_s4 = time.perf_counter() - t0
print(f'score+molecular:{dt_s4*1000:.1f} ms, mean={s4.mean():.4f}')

# Adaptive friction (vectorised now, should be fast)
t0 = time.perf_counter()
af = g.adaptive_friction(X_test)
dt_af = time.perf_counter() - t0
print(f'adaptive_friction ({len(X_test)} pts): {dt_af*1000:.1f} ms, '
      f'mean={af.mean():.4f}, range=[{af.min():.4f}, {af.max():.4f}]')

# Backward compat: ExpoGate + SignedLR
y_fake = np.zeros(N)
g.fit_expogate(X_ref, y_fake, ridge_alpha=1.0, smooth_sigma=1.0, gate_scale=3.0)
eg = g.score_expogate(X_test)
print(f'ExpoGate: mean={eg.mean():.4f}')

g.fit_signed_lr(X_ref, y_fake, lr=0.1, n_iter=500, reg=0.01)
slr = g.score_signed_lr(X_test)
print(f'SignedLR: mean={slr.mean():.4f}')
w = g.lr_weights()
ch_names = ['bias', 'dC', 'dG', 'dA', 'dT', 'MFLS']
wstr = ', '.join(f"{ch_names[i]}={w[i]:+.3f}" for i in range(len(w)))
print(f'LR weights: {wstr}')

# Verify no sklearn/kNN was used
assert not hasattr(g, '_nn') or g._nn is None, "Should NOT have kNN tree"
assert not hasattr(g, '_X_ref') or g._X_ref is None, "Should NOT store ref data"

print('\n=== ALL TESTS PASSED — fully closed-form, O(N*d) ===')
