"""Quick 3-fold CV: Fisher vs QDA vs QDA+magnifier on mammography."""
import numpy as np, sys, warnings, time
warnings.filterwarnings('ignore')
sys.path.insert(0, r'c:\amttp')

from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler
from sklearn.discriminant_analysis import QuadraticDiscriminantAnalysis
from udl.spectra import (StatisticalSpectrum, ChaosSpectrum,
                         SpectralSpectrum, GeometricSpectrum,
                         ReconstructionSpectrum)
from udl.pipeline import UDLPipeline
from udl.magnifier import DimensionMagnifier
from udl.datasets import load_mammography

ops = [
    ('stat', StatisticalSpectrum()),
    ('chaos', ChaosSpectrum()),
    ('spec', SpectralSpectrum()),
    ('geo', GeometricSpectrum()),
    ('recon', ReconstructionSpectrum()),
]
X, y = load_mammography()

skf = StratifiedKFold(n_splits=3, shuffle=True, random_state=42)
res = {k: [] for k in ['Fisher', 'QDA_raw', 'QDA_scale', 'QDA_mag']}

for fold, (tr_i, te_i) in enumerate(skf.split(X, y)):
    t0 = time.time()
    p = UDLPipeline(operators=ops, centroid_method='auto',
                    projection_method='fisher')
    p.fit(X[tr_i], y[tr_i])
    R_tr = p.transform(X[tr_i])
    R_te = p.transform(X[te_i])

    # Fisher
    _, fs = p.projector.classify(R_te, return_scores=True)
    res['Fisher'].append(roc_auc_score(y[te_i], fs))

    # QDA raw
    q = QuadraticDiscriminantAnalysis()
    q.fit(R_tr, y[tr_i])
    res['QDA_raw'].append(roc_auc_score(y[te_i], q.predict_proba(R_te)[:, 1]))

    # QDA standard-scaled
    sc = StandardScaler()
    Rs_tr = sc.fit_transform(R_tr)
    Rs_te = sc.transform(R_te)
    q2 = QuadraticDiscriminantAnalysis()
    q2.fit(Rs_tr, y[tr_i])
    res['QDA_scale'].append(roc_auc_score(y[te_i], q2.predict_proba(Rs_te)[:, 1]))

    # QDA magnified (boundary-centred tanh)
    mag = DimensionMagnifier(gamma=3.0, verbose=False)
    mag.fit(R_tr, y[tr_i])
    Rm_tr = mag.magnify(R_tr)
    Rm_te = mag.magnify(R_te)
    q3 = QuadraticDiscriminantAnalysis()
    q3.fit(Rm_tr, y[tr_i])
    res['QDA_mag'].append(roc_auc_score(y[te_i], q3.predict_proba(Rm_te)[:, 1]))

    print(f"Fold {fold+1} done in {time.time()-t0:.0f}s")

print()
print("3-Fold CV — MAMMOGRAPHY")
print("=" * 50)
for k, v in res.items():
    print(f"  {k:15s} AUC = {np.mean(v):.4f} +/- {np.std(v):.4f}")

qm = np.mean(res['QDA_mag'])
qs = np.mean(res['QDA_scale'])
fi = np.mean(res['Fisher'])
print(f"\nMagnifier adds {qm - qs:+.4f} over plain scaling")
print(f"QDA+mag vs Fisher: {qm - fi:+.4f}")
