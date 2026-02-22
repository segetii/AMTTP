"""Validate energy framework integration with UDL pipeline."""
import numpy as np
from sklearn.datasets import fetch_openml
from sklearn.metrics import roc_auc_score

# Load mammography
data = fetch_openml('mammography', version=1, as_frame=False, parser='auto')
X, y_raw = data.data, data.target
y = (y_raw == '1').astype(int)  # '1' = anomaly minority class
print(f'Data: X={X.shape}, anomalies={y.sum()}/{len(y)}')

# Test 1: Pipeline with energy_score
print('\n=== Test 1: Pipeline energy_score ===')
from udl import UDLPipeline
from udl.spectra import GeometricSpectrum, RankOrderSpectrum
ops = [('geom', GeometricSpectrum()), ('rank', RankOrderSpectrum())]
pipe = UDLPipeline(
    operators=ops,
    centroid_method='geometric_median',
    energy_score=True,
    energy_alpha=1.0,
    energy_gamma=0.01,
)
pipe.fit(X, y)
print('Pipeline fit OK')

# Energy scores
e_scores = pipe.energy_scores(X)
print(f'Energy scores shape: {e_scores.shape}, mean={e_scores.mean():.4f}')

# AUC from energy
auc_e = roc_auc_score(y, e_scores)
print(f'Energy AUC: {auc_e:.4f}')

# Standard QDA scores for comparison
qda_scores = pipe.score(X)
auc_q = roc_auc_score(y, qda_scores)
print(f'QDA AUC: {auc_q:.4f}')

# Test 2: Energy decomposition
print('\n=== Test 2: Energy decomposition ===')
decomp = pipe.energy_decompose(X[:5])
for k, v in decomp.items():
    if isinstance(v, np.ndarray):
        print(f'  {k}: shape={v.shape}, mean={v.mean():.4f}')
    else:
        print(f'  {k}: {v}')

# Test 3: Gradient magnitude
print('\n=== Test 3: Gradient magnitude ===')
grad = pipe.energy_gradient_scores(X[:5])
print(f'Gradient scores shape: {grad.shape}, mean={grad.mean():.4f}')

# Test 4: Operator diversity
print('\n=== Test 4: Operator diversity ===')
div = pipe.operator_diversity_report(X[:50])
for k, v in div.items():
    print(f'  {k}: {v}')

# Test 5: Stability analysis
print('\n=== Test 5: Stability analysis ===')
stab = pipe.stability_analysis(X, y=y)
for k, v in stab.items():
    if isinstance(v, np.ndarray):
        print(f'  {k}: {v[:5]}...')
    elif isinstance(v, list):
        print(f'  {k}: [{", ".join(f"{x:.4f}" for x in v[:3])}...]')
    else:
        print(f'  {k}: {v}')

# Test 6: Pipeline with energy_flow
print('\n=== Test 6: Pipeline with energy_flow ===')
ops2 = [('geom', GeometricSpectrum()), ('rank', RankOrderSpectrum())]
pipe2 = UDLPipeline(
    operators=ops2,
    centroid_method='geometric_median',
    energy_flow=True,
    energy_flow_steps=5,
)
pipe2.fit(X, y)
print('Pipeline with energy_flow fit OK')
scores2 = pipe2.score(X)
auc2 = roc_auc_score(y, scores2)
print(f'Energy-flow QDA AUC: {auc2:.4f}')

print('\n=== ALL TESTS PASSED ===')
