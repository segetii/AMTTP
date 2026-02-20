"""Test integrated pipeline: Fisher vs QDA vs QDA+magnifier."""
import numpy as np, sys, warnings, time
warnings.filterwarnings('ignore')
sys.path.insert(0, r'c:\amttp')

from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score
from udl.spectra import (StatisticalSpectrum, ChaosSpectrum,
                         SpectralSpectrum, GeometricSpectrum,
                         ReconstructionSpectrum)
from udl.pipeline import UDLPipeline
from udl.datasets import load_mammography

ops = [
    ('stat', StatisticalSpectrum()),
    ('chaos', ChaosSpectrum()),
    ('spec', SpectralSpectrum()),
    ('geo', GeometricSpectrum()),
    ('recon', ReconstructionSpectrum()),
]
X, y = load_mammography()
X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.3, 
                                            random_state=42, stratify=y)

configs = [
    ("Fisher (baseline)",       dict(projection_method='fisher')),
    ("QDA (no magnify)",        dict(projection_method='qda')),
    ("Fisher + magnify",        dict(projection_method='fisher', magnify=True)),
    ("QDA + magnify",           dict(projection_method='qda', magnify=True)),
]

print("=" * 60)
print("MAMMOGRAPHY — Integrated Pipeline Comparison")
print("=" * 60)

for label, kw in configs:
    t0 = time.time()
    p = UDLPipeline(operators=ops, centroid_method='auto', **kw)
    p.fit(X_tr, y_tr)
    
    # Get classify scores
    R_te_rep = p.transform(X_te)
    if p.magnifier_ is not None:
        R_te_rep = p.magnifier_.magnify(R_te_rep)
    _, scores = p.projector.classify(R_te_rep, return_scores=True)
    auc = roc_auc_score(y_te, scores)
    
    elapsed = time.time() - t0
    print(f"  {label:25s}  AUC = {auc:.4f}  ({elapsed:.0f}s)")

print()
print("Done.")
