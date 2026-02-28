"""
Generate all results and figures for the UDL paper update.
Tests the consolidated 'qda-magnified' method and produces:
  1. Benchmark comparison table (all datasets)
  2. Figure: Per-dimension Cohen's d before/after magnification
  3. Figure: AUC comparison bar chart (QDA-magnified vs baselines)
  4. Figure: Magnifier scan heatmap
  5. Cross-validation results
"""
import numpy as np, sys, warnings, time, os
warnings.filterwarnings('ignore')
sys.path.insert(0, r'c:\amttp')

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from sklearn.model_selection import train_test_split, StratifiedKFold
from sklearn.metrics import roc_auc_score, average_precision_score, f1_score
from sklearn.neighbors import NearestNeighbors, LocalOutlierFactor
from sklearn.ensemble import IsolationForest
from sklearn.svm import OneClassSVM
from sklearn.covariance import EllipticEnvelope
from sklearn.preprocessing import StandardScaler

from udl.spectra import (StatisticalSpectrum, ChaosSpectrum,
                         SpectralSpectrum, GeometricSpectrum,
                         ReconstructionSpectrum)
from udl.pipeline import UDLPipeline
from udl.datasets import load_mammography, load_shuttle

PLOT_DIR = r'c:\amttp\plots'
PAPER_FIG_DIR = r'c:\amttp\papers\udl_figures'
os.makedirs(PLOT_DIR, exist_ok=True)
os.makedirs(PAPER_FIG_DIR, exist_ok=True)

ops = [
    ('stat', StatisticalSpectrum()),
    ('chaos', ChaosSpectrum()),
    ('spec', SpectralSpectrum()),
    ('geo', GeometricSpectrum()),
    ('recon', ReconstructionSpectrum()),
]

# ── Colour scheme ──
C_QDA_MAG = '#2ecc71'  # green
C_FISHER  = '#3498db'  # blue
C_QDA     = '#e67e22'  # orange
C_BASE    = '#95a5a6'  # grey
C_BEST    = '#e74c3c'  # red for new best

# ====================================================================
#  Part 1: Run the consolidated method on all datasets
# ====================================================================
print("=" * 70)
print("  UDL PAPER RESULTS — CONSOLIDATED QDA-MAGNIFIED METHOD")
print("=" * 70)

datasets = {
    'mammography': load_mammography,
    'shuttle': load_shuttle,
}

# Create synthetic + mimic inline
def make_synthetic(n_normal=1000, n_anomaly=50, n_features=10, seed=42):
    rng = np.random.RandomState(seed)
    X_n = rng.randn(n_normal, n_features)
    X_a = rng.randn(n_anomaly, n_features) + 4.0
    X = np.vstack([X_n, X_a])
    y = np.concatenate([np.zeros(n_normal), np.ones(n_anomaly)])
    return X, y

def make_mimic(n_normal=1000, n_anomaly=50, n_features=10, seed=42):
    rng = np.random.RandomState(seed)
    X_n = rng.randn(n_normal, n_features)
    X_a = rng.randn(n_anomaly, n_features)
    half = n_features // 2
    X_a[:, half:] += 4.0  # only half features offset
    X = np.vstack([X_n, X_a])
    y = np.concatenate([np.zeros(n_normal), np.ones(n_anomaly)])
    return X, y

all_results = {}

# Test synthetic and mimic first (fast)
for ds_name, loader in [("synthetic", make_synthetic), ("mimic", make_mimic)]:
    X, y = loader()
    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.3, random_state=42, stratify=y
    )

    p = UDLPipeline(operators=ops, projection_method='qda-magnified')
    p.fit(X_tr, y_tr)

    R_te = p.transform(X_te)
    R_te = p.magnifier_.magnify(R_te)
    preds, scores = p.projector.classify(R_te, return_scores=True)
    auc = roc_auc_score(y_te, scores)
    ap = average_precision_score(y_te, scores)
    f1 = f1_score(y_te, preds)

    all_results[ds_name] = {
        'auc': auc, 'ap': ap, 'f1': f1,
        'pipeline': p, 'X_tr': X_tr, 'y_tr': y_tr,
        'X_te': X_te, 'y_te': y_te,
    }
    print(f"  {ds_name:15s}  AUC={auc:.4f}  AP={ap:.4f}  F1={f1:.4f}")

# Real datasets
for ds_name, loader in datasets.items():
    X, y = loader()
    if ds_name == 'shuttle' and len(X) > 15000:
        # Subsample for speed
        rng = np.random.RandomState(42)
        idx = rng.choice(len(X), 10000, replace=False)
        X, y = X[idx], y[idx]

    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.3, random_state=42, stratify=y
    )

    t0 = time.time()
    p = UDLPipeline(operators=ops, projection_method='qda-magnified')
    p.fit(X_tr, y_tr)

    R_te = p.transform(X_te)
    R_te = p.magnifier_.magnify(R_te)
    preds, scores = p.projector.classify(R_te, return_scores=True)
    auc = roc_auc_score(y_te, scores)
    ap = average_precision_score(y_te, scores)
    f1 = f1_score(y_te, preds)
    elapsed = time.time() - t0

    all_results[ds_name] = {
        'auc': auc, 'ap': ap, 'f1': f1,
        'pipeline': p, 'X_tr': X_tr, 'y_tr': y_tr,
        'X_te': X_te, 'y_te': y_te,
    }
    print(f"  {ds_name:15s}  AUC={auc:.4f}  AP={ap:.4f}  F1={f1:.4f}  ({elapsed:.0f}s)")

# ====================================================================
#  Part 2: Run baseline methods on mammography for comparison
# ====================================================================
print("\n" + "=" * 70)
print("  BASELINE COMPARISON (Mammography)")
print("=" * 70)

X, y = load_mammography()
X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.3, random_state=42, stratify=y)

# Prepare normal-only training data (semi-supervised protocol)
X_tr_normal = X_tr[y_tr == 0]
scaler = StandardScaler().fit(X_tr_normal)
X_tr_s = scaler.transform(X_tr)
X_te_s = scaler.transform(X_te)
X_tr_normal_s = scaler.transform(X_tr_normal)

baseline_results = {}

# kNN Distance
nn = NearestNeighbors(n_neighbors=10).fit(X_tr_normal_s)
dists, _ = nn.kneighbors(X_te_s)
knn_scores = dists.mean(axis=1)
baseline_results['kNN-Distance'] = roc_auc_score(y_te, knn_scores)

# LOF
lof = LocalOutlierFactor(n_neighbors=20, novelty=True, contamination=0.01)
lof.fit(X_tr_normal_s)
lof_scores = -lof.decision_function(X_te_s)
baseline_results['LOF'] = roc_auc_score(y_te, lof_scores)

# Isolation Forest
iso = IsolationForest(n_estimators=200, contamination='auto', random_state=42)
iso.fit(X_tr_normal_s)
iso_scores = -iso.decision_function(X_te_s)
baseline_results['Isolation Forest'] = roc_auc_score(y_te, iso_scores)

# One-Class SVM
ocsvm = OneClassSVM(kernel='rbf', gamma='scale', nu=0.05)
ocsvm.fit(X_tr_normal_s)
ocsvm_scores = -ocsvm.decision_function(X_te_s)
baseline_results['One-Class SVM'] = roc_auc_score(y_te, ocsvm_scores)

# Elliptic Envelope
ee = EllipticEnvelope(contamination=0.01, random_state=42)
ee.fit(X_tr_normal_s)
ee_scores = -ee.decision_function(X_te_s)
baseline_results['Elliptic Env.'] = roc_auc_score(y_te, ee_scores)

# Fisher (original UDL)
p_fisher = UDLPipeline(operators=ops, projection_method='fisher', score_method='v3e')
p_fisher.fit(X_tr, y_tr)
R_te_f = p_fisher.transform(X_te)
_, fisher_scores = p_fisher.projector.classify(R_te_f, return_scores=True)
baseline_results['UDL-Fisher'] = roc_auc_score(y_te, fisher_scores)

# QDA-magnified (our method)
baseline_results['UDL-QDA-Mag'] = all_results['mammography']['auc']

for name, auc in sorted(baseline_results.items(), key=lambda x: -x[1]):
    marker = " ← NEW BEST" if name == 'UDL-QDA-Mag' else ""
    print(f"  {name:20s}  AUC={auc:.4f}{marker}")

# ====================================================================
#  Part 3: Cross-validation (mammography)
# ====================================================================
print("\n" + "=" * 70)
print("  3-FOLD CROSS-VALIDATION (Mammography)")
print("=" * 70)

X_m, y_m = load_mammography()
skf = StratifiedKFold(n_splits=3, shuffle=True, random_state=42)
cv_qda_mag = []
cv_fisher = []

for fold, (tr_idx, te_idx) in enumerate(skf.split(X_m, y_m)):
    X_tr_cv, X_te_cv = X_m[tr_idx], X_m[te_idx]
    y_tr_cv, y_te_cv = y_m[tr_idx], y_m[te_idx]

    # QDA-magnified
    p = UDLPipeline(operators=ops, projection_method='qda-magnified')
    p.fit(X_tr_cv, y_tr_cv)
    R_cv = p.transform(X_te_cv)
    R_cv = p.magnifier_.magnify(R_cv)
    _, sc = p.projector.classify(R_cv, return_scores=True)
    auc_qm = roc_auc_score(y_te_cv, sc)
    cv_qda_mag.append(auc_qm)

    # Fisher baseline
    pf = UDLPipeline(operators=ops, projection_method='fisher', score_method='v3e')
    pf.fit(X_tr_cv, y_tr_cv)
    R_cv_f = pf.transform(X_te_cv)
    _, sc_f = pf.projector.classify(R_cv_f, return_scores=True)
    auc_f = roc_auc_score(y_te_cv, sc_f)
    cv_fisher.append(auc_f)

    print(f"  Fold {fold+1}: QDA-Mag={auc_qm:.4f}  Fisher={auc_f:.4f}  Δ={auc_qm - auc_f:+.4f}")

print(f"  Mean:  QDA-Mag={np.mean(cv_qda_mag):.4f}±{np.std(cv_qda_mag):.4f}  "
      f"Fisher={np.mean(cv_fisher):.4f}±{np.std(cv_fisher):.4f}")

# ====================================================================
#  Part 4: FIGURES
# ====================================================================
print("\n" + "=" * 70)
print("  GENERATING FIGURES")
print("=" * 70)

# ── Figure A: Per-dimension Cohen's d before vs after magnification ──
# Use mammography pipeline
p_mamm = all_results['mammography']['pipeline']
X_tr_m = all_results['mammography']['X_tr']
y_tr_m = all_results['mammography']['y_tr']
R_before = p_mamm.transform(X_tr_m)
R_after = p_mamm.magnifier_.magnify(R_before)

cohen_before = []
cohen_after = []
dim_labels = []
D = R_before.shape[1]

law_names = p_mamm.stack.law_names_
law_dims = p_mamm.stack.law_dims_
offset = 0
for name, nd in zip(law_names, law_dims):
    for i in range(nd):
        dim_labels.append(f"{name[:4]}_{i}")
        mask_n = y_tr_m == 0
        mask_a = y_tr_m == 1

        # Before
        v_n = R_before[mask_n, offset + i]
        v_a = R_before[mask_a, offset + i]
        ps = np.sqrt((v_n.var(ddof=1) + v_a.var(ddof=1)) / 2 + 1e-15)
        cohen_before.append(abs(v_a.mean() - v_n.mean()) / ps)

        # After
        v_n2 = R_after[mask_n, offset + i]
        v_a2 = R_after[mask_a, offset + i]
        ps2 = np.sqrt((v_n2.var(ddof=1) + v_a2.var(ddof=1)) / 2 + 1e-15)
        cohen_after.append(abs(v_a2.mean() - v_n2.mean()) / ps2)
    offset += nd

fig, ax = plt.subplots(figsize=(12, 5))
x = np.arange(D)
w = 0.35
bars1 = ax.bar(x - w/2, cohen_before, w, label='Before magnification', color='#3498db', alpha=0.8)
bars2 = ax.bar(x + w/2, cohen_after, w, label='After magnification', color='#2ecc71', alpha=0.8)
ax.set_xlabel('Dimension')
ax.set_ylabel("Cohen's d")
ax.set_title("Per-Dimension Cohen's d: Before vs After Boundary-Centred Magnification\n(Mammography dataset)")
ax.set_xticks(x)
ax.set_xticklabels(dim_labels, rotation=45, ha='right', fontsize=8)
ax.legend()
ax.grid(axis='y', alpha=0.3)

# Add law domain separators
offset = 0
for name, nd in zip(law_names, law_dims):
    if offset > 0:
        ax.axvline(offset - 0.5, color='grey', linestyle='--', alpha=0.4)
    ax.text(offset + nd/2 - 0.5, ax.get_ylim()[1] * 0.95, name,
            ha='center', fontsize=8, style='italic', color='grey')
    offset += nd

plt.tight_layout()
fig_path = os.path.join(PLOT_DIR, '11_cohen_d_magnifier.png')
plt.savefig(fig_path, dpi=150)
plt.savefig(os.path.join(PAPER_FIG_DIR, 'cohen_d_magnifier.pdf'), dpi=300)
plt.close()
print(f"  Saved: {fig_path}")

# ── Figure B: AUC comparison bar chart ──
methods = list(baseline_results.keys())
aucs = [baseline_results[m] for m in methods]

# Sort by AUC
sorted_pairs = sorted(zip(methods, aucs), key=lambda x: x[1])
methods_sorted, aucs_sorted = zip(*sorted_pairs)

fig, ax = plt.subplots(figsize=(10, 6))
colours = []
for m in methods_sorted:
    if m == 'UDL-QDA-Mag':
        colours.append(C_BEST)
    elif 'UDL' in m:
        colours.append(C_FISHER)
    else:
        colours.append(C_BASE)

bars = ax.barh(range(len(methods_sorted)), aucs_sorted, color=colours, alpha=0.85, edgecolor='white')

for i, (m, a) in enumerate(zip(methods_sorted, aucs_sorted)):
    ax.text(a + 0.002, i, f'{a:.4f}', va='center', fontsize=9, fontweight='bold' if m == 'UDL-QDA-Mag' else 'normal')

ax.set_yticks(range(len(methods_sorted)))
ax.set_yticklabels(methods_sorted, fontsize=10)
ax.set_xlabel('AUC-ROC')
ax.set_title('Mammography: QDA-Magnified vs Baselines\n(Semi-supervised protocol, 70/30 split, seed=42)')
ax.set_xlim(0.75, max(aucs_sorted) + 0.04)
ax.axvline(baseline_results['UDL-QDA-Mag'], color=C_BEST, linestyle='--', alpha=0.3)
ax.grid(axis='x', alpha=0.3)
plt.tight_layout()

fig_path = os.path.join(PLOT_DIR, '12_qda_mag_comparison.png')
plt.savefig(fig_path, dpi=150)
plt.savefig(os.path.join(PAPER_FIG_DIR, 'qda_mag_comparison.pdf'), dpi=300)
plt.close()
print(f"  Saved: {fig_path}")

# ── Figure C: Magnifier steepness heatmap ──
fig, ax = plt.subplots(figsize=(10, 2.5))
steepness = p_mamm.magnifier_.steepness_
disc_scores = p_mamm.magnifier_.disc_scores_

# Reshape as 1 x D heatmap
im = ax.imshow(steepness.reshape(1, -1), aspect='auto', cmap='RdYlGn',
               vmin=0, vmax=max(steepness.max(), 3.0))
ax.set_yticks([])
ax.set_xticks(range(D))
ax.set_xticklabels(dim_labels, rotation=45, ha='right', fontsize=8)
ax.set_title('Magnifier Steepness k_d per Dimension (Mammography)\nGreen=Saturated (clear), Red=Silenced (blind)')
plt.colorbar(im, ax=ax, label='Steepness k_d', shrink=0.8)

# Annotate clear vs blind
for d in range(D):
    label = f'{steepness[d]:.1f}'
    colour = 'white' if steepness[d] > 1.5 else 'black'
    ax.text(d, 0, label, ha='center', va='center', fontsize=7, fontweight='bold', color=colour)

plt.tight_layout()
fig_path = os.path.join(PLOT_DIR, '13_magnifier_heatmap.png')
plt.savefig(fig_path, dpi=150)
plt.savefig(os.path.join(PAPER_FIG_DIR, 'magnifier_heatmap.pdf'), dpi=300)
plt.close()
print(f"  Saved: {fig_path}")

# ── Figure D: CV comparison boxplot ──
fig, ax = plt.subplots(figsize=(6, 5))
bp = ax.boxplot([cv_fisher, cv_qda_mag], labels=['Fisher LDA', 'QDA-Magnified'],
                patch_artist=True, widths=0.5)
bp['boxes'][0].set_facecolor(C_FISHER)
bp['boxes'][1].set_facecolor(C_QDA_MAG)
for b in bp['boxes']:
    b.set_alpha(0.7)

# Overlay individual points
for i, data in enumerate([cv_fisher, cv_qda_mag]):
    ax.scatter([i + 1] * len(data), data, c='black', s=40, zorder=5, alpha=0.7)

ax.set_ylabel('AUC-ROC')
ax.set_title('3-Fold Cross-Validation: Mammography\nFisher LDA vs QDA-Magnified')
ax.grid(axis='y', alpha=0.3)
plt.tight_layout()

fig_path = os.path.join(PLOT_DIR, '14_cv_boxplot.png')
plt.savefig(fig_path, dpi=150)
plt.savefig(os.path.join(PAPER_FIG_DIR, 'cv_boxplot.pdf'), dpi=300)
plt.close()
print(f"  Saved: {fig_path}")

# ====================================================================
#  Part 5: Write summary for paper
# ====================================================================
print("\n" + "=" * 70)
print("  SUMMARY FOR PAPER")
print("=" * 70)

print(f"\n  QDA-Magnified results:")
for ds in ['synthetic', 'mimic', 'mammography', 'shuttle']:
    r = all_results[ds]
    print(f"    {ds:15s}  AUC={r['auc']:.4f}")

mean_auc = np.mean([all_results[ds]['auc'] for ds in ['synthetic', 'mimic', 'mammography', 'shuttle']])
print(f"    {'Mean':15s}  AUC={mean_auc:.4f}")

print(f"\n  Cross-validation (Mammography):")
print(f"    QDA-Mag: {np.mean(cv_qda_mag):.4f} ± {np.std(cv_qda_mag):.4f}")
print(f"    Fisher:  {np.mean(cv_fisher):.4f} ± {np.std(cv_fisher):.4f}")

print(f"\n  Mammography comparison:")
for name, auc in sorted(baseline_results.items(), key=lambda x: -x[1]):
    delta = auc - baseline_results['UDL-QDA-Mag']
    print(f"    {name:20s}  AUC={auc:.4f}  Δ={delta:+.4f}")

print("\n  DONE — all figures saved to plots/ and papers/udl_figures/")
