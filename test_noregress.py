"""Verify QDA+magnifier on synthetic and mimic datasets (no regression)."""
import numpy as np, sys, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, r'c:\amttp')

from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score
from udl.spectra import (StatisticalSpectrum, ChaosSpectrum,
                         SpectralSpectrum, GeometricSpectrum,
                         ReconstructionSpectrum)
from udl.pipeline import UDLPipeline
from udl.datasets import load_shuttle, load_pendigits

ops = [
    ('stat', StatisticalSpectrum()),
    ('chaos', ChaosSpectrum()),
    ('spec', SpectralSpectrum()),
    ('geo', GeometricSpectrum()),
    ('recon', ReconstructionSpectrum()),
]

for name, loader in [("shuttle", load_shuttle), ("pendigits", load_pendigits)]:
    X, y = loader()
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.3,
                                                random_state=42, stratify=y)
    
    # Fisher baseline
    p1 = UDLPipeline(operators=ops, centroid_method='auto', projection_method='fisher')
    p1.fit(X_tr, y_tr)
    R_te1 = p1.transform(X_te)
    _, fs1 = p1.projector.classify(R_te1, return_scores=True)
    auc1 = roc_auc_score(y_te, fs1)
    
    # QDA + magnify
    p2 = UDLPipeline(operators=ops, centroid_method='auto',
                     projection_method='qda', magnify=True)
    p2.fit(X_tr, y_tr)
    R_te2 = p2.transform(X_te)
    R_te2m = p2.magnifier_.magnify(R_te2)
    _, fs2 = p2.projector.classify(R_te2m, return_scores=True)
    auc2 = roc_auc_score(y_te, fs2)
    
    print(f"{name:12s}  Fisher={auc1:.4f}  QDA+mag={auc2:.4f}  delta={auc2-auc1:+.4f}")
