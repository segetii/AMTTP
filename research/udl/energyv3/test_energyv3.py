"""Smoke test for energyv3 — Paper v3 reconciled implementation."""
import sys
import importlib.util
import numpy as np

# Explicit import from energyv3 path to avoid name clash with original
_spec = importlib.util.spec_from_file_location(
    'energyv3_pipeline',
    r'c:\amttp\research\udl\energyv3\geo_full_pipeline.py')
mod = importlib.util.module_from_spec(_spec)
sys.modules['energyv3_pipeline'] = mod
_spec.loader.exec_module(mod)
print(f'Loaded from: {mod.__file__}')

# Pull classes from explicitly loaded module
FrozenWindowScorer = mod.FrozenWindowScorer
GeometricBSDT = mod.GeometricBSDT
GeometricFusedScorer = mod.GeometricFusedScorer
adaptive_friction = mod.adaptive_friction

sys.path.insert(0, r'c:\amttp\research\udl\energyv3')
sys.path.insert(0, r'c:\amttp\research\udl')
from udl.ellipsoid_geometry import EllipsoidGeometry
print('[OK] Imports successful')

# Test 2: Create synthetic reference data
np.random.seed(42)
d = 5
N_ref = 500
N_test = 100
X_ref = np.random.randn(N_ref, d)
X_test = np.random.randn(N_test, d) * 1.5

# Build ellipsoid
cov = np.cov(X_ref.T)
evals, _ = np.linalg.eigh(cov)
evals = np.maximum(evals, 1e-12)
w = evals / evals.sum()
ell = EllipsoidGeometry.from_fisher_weights(w, alpha=float(evals.max()))
print(f'[OK] Ellipsoid built: d={d}, semi_axes={ell.semi_axes[:3]}...')

# Test 3: GeometricBSDT with paper-aligned channels
bsdt = GeometricBSDT()
bsdt.fit(X_ref, ell)
ch = bsdt.channels(X_test)
print(f'[OK] Paper channels:')
print(f'     delta_C mean={ch["delta_C"].mean():.3f}')
print(f'     delta_G mean={ch["delta_G"].mean():.3f}')
print(f'     delta_A mean={ch["delta_A"].mean():.3f}')
print(f'     delta_T mean={ch["delta_T"].mean():.3f}')
print(f'     FVR weights: {bsdt._ch_weights}')

# Test 4: BSDT score
scores_bsdt = bsdt.score(X_test)
print(f'[OK] BSDT score: mean={scores_bsdt.mean():.4f} std={scores_bsdt.std():.4f}')

# Test 5: FrozenWindowScorer
fws = FrozenWindowScorer()
fws.fit(X_ref)
scores_fws = fws.score(X_test)
print(f'[OK] FrozenWindowScorer: mean={scores_fws.mean():.4f} std={scores_fws.std():.4f}')

# Test 6: Paper friction on FrozenWindowScorer
scores_pf = fws.score_with_paper_friction(X_test)
print(f'[OK] Paper friction score: mean={scores_pf.mean():.4f} std={scores_pf.std():.4f}')

# Test 7: Paper friction features
feats_pf = fws.features_with_paper_friction(X_test)
print(f'[OK] Paper friction features: shape={feats_pf.shape}')

# Test 8: Original boundary-reflection friction still works
scores_bf = fws.score_with_friction(X_test, theta=fws._tau_Q)
print(f'[OK] Boundary-reflection friction: mean={scores_bf.mean():.4f}')

# Test 9: Channel sanity checks (paper alignment)
a2 = ell.semi_axes ** 2
Q_test_vals = np.sum(X_test ** 2 / a2, axis=1)

# delta_C = sqrt(Q) per Paper §2.2
expected_delta_C = np.sqrt(np.maximum(Q_test_vals, 0.0))
assert np.allclose(ch['delta_C'], expected_delta_C), 'delta_C mismatch!'
print('[OK] delta_C = sqrt(Q) verified (Paper section 2.2)')

# delta_T = Q/2 + log_norm per Paper §2.2
expected_delta_T = Q_test_vals / 2.0 + bsdt._log_norm_const
assert np.allclose(ch['delta_T'], expected_delta_T), 'delta_T mismatch!'
print('[OK] delta_T = Q/2 + C verified (Paper section 2.2)')

# delta_A = max(0, ||grad_Q|| - v0) per Paper §2.2
grad_Q = 2.0 * X_test / a2
grad_norm = np.linalg.norm(grad_Q, axis=1)
expected_delta_A = np.maximum(grad_norm - bsdt._v0, 0.0)
assert np.allclose(ch['delta_A'], expected_delta_A), 'delta_A mismatch!'
print('[OK] delta_A = max(0, ||grad Q|| - v0) verified (Paper section 2.2)')

# delta_G = ||(I - P_A)X|| per Paper §2.2
resid = X_test - X_test @ bsdt._P_A
expected_delta_G = np.linalg.norm(resid, axis=1)
assert np.allclose(ch['delta_G'], expected_delta_G), 'delta_G mismatch!'
print('[OK] delta_G = ||(I - P_A)X|| verified (Paper section 2.2)')

# Test 10: E_BS uses Fisher VR weights (not equal 1/4)
print(f'[OK] E_BS Fisher VR channel weights: {bsdt._ch_weights}')
assert not np.allclose(bsdt._ch_weights, np.ones(4)/4), 'Weights should not be uniform!'
print('[OK] Fisher VR weights are non-uniform (Paper Theorem W)')

# Test 11: Score with potential
scores_hybrid = bsdt.score(X_test, potential='hybrid')
print(f'[OK] Score with hybrid potential: mean={scores_hybrid.mean():.4f}')

print()
print('=' * 60)
print('  ALL TESTS PASSED — energyv3 Paper v3 reconciled')
print('=' * 60)
