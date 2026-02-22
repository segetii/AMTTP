"""
DIAGNOSTIC: Why is energy scoring losing signal vs QDA?
=======================================================
Breaks down exactly where QDA beats energy, component by component.
"""
import numpy as np
import warnings
warnings.filterwarnings("ignore")

from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler

from udl.datasets import load_mammography, load_shuttle
from udl.pipeline import UDLPipeline
from udl.spectra import StatisticalSpectrum, GeometricSpectrum, RankOrderSpectrum
from udl.energy import DeviationEnergy, OperatorDiversity

# ═══════════════════════════════════════════
#  MAMMOGRAPHY
# ═══════════════════════════════════════════
X, y = load_mammography()
X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.3, stratify=y, random_state=42)

ops = [('stat', StatisticalSpectrum()), ('geom', GeometricSpectrum()), ('rank', RankOrderSpectrum())]
pipe = UDLPipeline(operators=ops, centroid_method='geometric_median',
                   energy_score=True, energy_alpha=1.0, energy_gamma=0.01)
pipe.fit(X_tr, y_tr)

print("="*70)
print(" MAMMOGRAPHY — Energy vs QDA Diagnostic")
print("="*70)

# 1. What does each energy COMPONENT contribute?
E_total, E_radial, E_law, E_inter = pipe._energy_model.score(X_te, return_components=True)

for name, E in [("E_total", E_total), ("E_radial", E_radial), ("E_law", E_law), ("E_inter", E_inter)]:
    try:
        auc = roc_auc_score(y_te, E)
    except:
        auc = 0.0
    e_norm = E[y_te == 0].mean()
    e_anom = E[y_te == 1].mean()
    print(f"  {name:12s}  AUC={auc:.4f}  E(normal)={e_norm:.4f}  E(anomaly)={e_anom:.4f}  ratio={e_anom/(e_norm+1e-10):.1f}x")

# 2. Per-law energy AUC
print("\n  Per-law energy contribution:")
decomp = pipe._energy_model.per_law_energy(X_te)
for law_name, E_k in decomp.items():
    try:
        auc = roc_auc_score(y_te, E_k)
    except:
        auc = 0.0
    e_n = E_k[y_te == 0].mean()
    e_a = E_k[y_te == 1].mean()
    print(f"    {law_name:10s}  AUC={auc:.4f}  mean_normal={e_n:.4f}  mean_anomaly={e_a:.4f}  beta={0:.4f}")
print(f"    beta_k_ = {pipe._energy_model.beta_k_}")

# 3. What does QDA see that energy doesn't?
print("\n  QDA pipeline path — what MAGNIFIER does:")
qda_scores = pipe.score(X_te)
auc_qda = roc_auc_score(y_te, qda_scores)
print(f"  QDA AUC: {auc_qda:.4f}")

# 4. Raw per-law features — AUC of each dimension
print("\n  Raw per-law feature AUCs (no magnifier, no QDA):")
for name, op in pipe.stack.operators:
    R = op.transform(X_te)
    for j in range(R.shape[1]):
        try:
            auc_j = roc_auc_score(y_te, R[:, j])
            if auc_j < 0.5:
                auc_j = 1 - auc_j  # flip
        except:
            auc_j = 0.5
        if auc_j > 0.6:
            print(f"    {name}_d{j}: AUC={auc_j:.4f}")

# 5. Compare: raw vs magnified features
print("\n  MAGNIFIED feature AUCs (what QDA actually sees):")
R_te_raw = pipe.stack.transform(X_te)
R_tr_all = pipe.stack.transform(X_tr)
# Magnifier operates on R directly, not on tensor
if pipe.magnifier_ is not None:
    M_te = pipe.magnifier_.magnify(R_te_raw)
    M_tr = pipe.magnifier_.magnify(R_tr_all)
else:
    M_te = R_te_raw
    M_tr = R_tr_all
for j in range(min(M_te.shape[1], 15)):  # first 15 dims
    try:
        auc_j = roc_auc_score(y_te, M_te[:, j])
        if auc_j < 0.5:
            auc_j = 1 - auc_j
    except:
        auc_j = 0.5
    if auc_j > 0.6:
        print(f"    magnified_d{j}: AUC={auc_j:.4f}  (mean_n={M_te[y_te==0, j].mean():.3f}  mean_a={M_te[y_te==1, j].mean():.3f})")

# 6. The fundamental gap: energy = distance² vs QDA = learned boundary
print("\n" + "="*70)
print(" ROOT CAUSE ANALYSIS")
print("="*70)
print("""
  ISSUE 1: Energy = squared Euclidean distance (isotropic)
           QDA  = quadratic boundary (covariance-aware per class)
           
  Energy treats all standardized directions equally.
  QDA learns that anomalies deviate specifically in certain
  correlated directions and builds a quadratic surface there.
  
  ISSUE 2: Energy bypasses the Magnifier
           The magnifier is THE key innovation — it amplifies
           discriminative dimensions (d>1.0, AUC>0.8) by 3-5x
           and silences noise dimensions. Energy operates on
           raw operator output where signal/noise aren't separated.
           
  ISSUE 3: Per-law Z-standardization zeros out the centroid
           After Z-normalizing, mu_per_law ≈ 0, so law deviation = 
           ||z_k||² = sum of squared z-scores. This is just the 
           chi-squared statistic — misses cross-dim correlations.
           
  ISSUE 4: Interaction term is negligible
           gamma=0.01 contributes ~0.01 to total E while radial ~5.0.
           The N-body clustering insight is drowned out.
""")

# 7. Quantify the magnifier boost
print("  MAGNIFIER IMPACT:")
from sklearn.discriminant_analysis import QuadraticDiscriminantAnalysis

# QDA on raw representation (no magnifier)
qda_raw = QuadraticDiscriminantAnalysis(reg_param=1e-4)
qda_raw.fit(R_tr_all, y_tr)
scores_raw_qda = qda_raw.predict_proba(R_te_raw)[:, 1]
auc_raw_qda = roc_auc_score(y_te, scores_raw_qda)
print(f"  QDA on RAW representation:        AUC = {auc_raw_qda:.4f}")

# QDA on magnified representation
qda_mag = QuadraticDiscriminantAnalysis(reg_param=1e-4)
qda_mag.fit(M_tr, y_tr)
scores_mag_qda = qda_mag.predict_proba(M_te)[:, 1]
auc_mag_qda = roc_auc_score(y_te, scores_mag_qda)
print(f"  QDA on MAGNIFIED representation:  AUC = {auc_mag_qda:.4f}")
print(f"  Magnifier AUC lift:               +{auc_mag_qda - auc_raw_qda:.4f}")

# 8. What if energy used MAGNIFIED features?
print("\n  WHAT IF energy used magnified features?")
# Simple energy on magnified: ||m - mu_normal||²
mu_mag = M_tr[y_tr == 0].mean(axis=0)
E_magnified = np.sum((M_te - mu_mag)**2, axis=1)
auc_emag = roc_auc_score(y_te, E_magnified)
print(f"  ||magnified - mu||² AUC:          {auc_emag:.4f}")

# Mahalanobis on magnified
n_feat = M_tr.shape[1]
cov_mag = np.cov(M_tr[y_tr == 0].T) + 1e-4 * np.eye(n_feat)
cov_inv = np.linalg.inv(cov_mag)
diff_mag = M_te - mu_mag
E_mahal = np.sum(diff_mag @ cov_inv * diff_mag, axis=1)
auc_emahal = roc_auc_score(y_te, E_mahal)
print(f"  Mahalanobis on magnified AUC:     {auc_emahal:.4f}")

# Energy radial vs magnified radial
# Standardised distance on raw operator output
R_te_norm = pipe.stack.transform(X_te)
mu_raw_op = pipe.stack.transform(X_tr[y_tr==0]).mean(axis=0)
std_raw_op = pipe.stack.transform(X_tr[y_tr==0]).std(axis=0) + 1e-10
E_raw_radius = np.sum(((R_te_norm - mu_raw_op) / std_raw_op)**2, axis=1)
auc_raw_radius = roc_auc_score(y_te, E_raw_radius)
print(f"  ||raw_ops - mu||² (z-scored):     {auc_raw_radius:.4f}")

# Cohen's d comparison: raw vs magnified
for label, feats_tr, feats_te in [("raw", R_tr_all, R_te_raw), ("magnified", M_tr, M_te)]:
    d_values = []
    for j in range(feats_te.shape[1]):
        mu0 = feats_te[y_te==0, j].mean()
        mu1 = feats_te[y_te==1, j].mean()
        s0 = feats_te[y_te==0, j].std() + 1e-10
        s1 = feats_te[y_te==1, j].std() + 1e-10
        s_pooled = np.sqrt((s0**2 + s1**2) / 2)
        d = abs(mu1 - mu0) / (s_pooled + 1e-10)
        d_values.append(d)
    d_values = np.array(d_values)
    print(f"  Cohen's d ({label:10s}):  mean={d_values.mean():.2f}  max={d_values.max():.2f}  >#1.0: {(d_values>1).sum()}/{len(d_values)}")

print(f"\n  CONCLUSION: Energy on raw features = {roc_auc_score(y_te, E_total):.4f}")
print(f"              Energy on magnified   = {auc_emag:.4f}")
print(f"              Mahalanobis magnified  = {auc_emahal:.4f}")
print(f"              QDA on raw             = {auc_raw_qda:.4f}")
print(f"              QDA on magnified       = {auc_mag_qda:.4f}")
print(f"\n  The magnifier is responsible for the discriminative gap.")
print(f"  Energy without magnifier is just isotropic distance in a noisy space.")
