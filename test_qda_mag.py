"""Test just QDA + magnifier (the others are already known)."""
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

print("Known results:")
print("  Fisher              AUC = 0.9005")
print("  QDA                 AUC = 0.9345")
print("  Fisher + magnify    AUC = 0.8606")
print()

t0 = time.time()
p = UDLPipeline(operators=ops, centroid_method='auto',
                projection_method='qda', magnify=True)
p.fit(X_tr, y_tr)

R_te_rep = p.transform(X_te)
R_te_mag = p.magnifier_.magnify(R_te_rep)
_, scores = p.projector.classify(R_te_mag, return_scores=True)
auc = roc_auc_score(y_te, scores)
print(f"  QDA + magnify       AUC = {auc:.4f}  ({time.time()-t0:.0f}s)")
print()
print(f"  Improvement over Fisher: +{auc - 0.9005:.4f}")
print(f"  Improvement over QDA:    +{auc - 0.9345:.4f}")
