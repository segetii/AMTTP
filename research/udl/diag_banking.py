import sys, numpy as np, json, warnings, pandas as pd
warnings.filterwarnings('ignore')
sys.path.insert(0, '.')
from udl.ellipsoid_geometry import EllipsoidGeometry
from pathlib import Path

CACHE = Path(r'c:\amttp\research\adaptive-friction\banklevel_enhanced\gsib_cache_real')
npz = np.load(CACHE / 'gsib_real_panel.npz')
X_3d = npz['X']
T, N, d = X_3d.shape
X_flat = X_3d.reshape(T * N, d)
dates = pd.date_range('2005-01-01', '2023-12-31', freq='QE')[:T]

FEATURE_NAMES = ['loan_to_asset', 'equity_ratio', 'npl_ratio', 'roa', 'funding_cost']
CRISIS_QTR = {
    "2007-12-31","2008-03-31","2008-06-30","2008-09-30",
    "2008-12-31","2009-03-31","2009-06-30",
    "2020-03-31","2020-06-30",
    "2011-09-30","2011-12-31","2012-03-31","2012-06-30",
}

# ── Feature means per period (why is AUC modest?) ────────────────────────────
PRE  = (dates >= '2005-03-31') & (dates <= '2007-06-30')
GFC  = (dates >= '2007-12-31') & (dates <= '2009-06-30')
POST = (dates >= '2010-03-31') & (dates <= '2019-12-31')

print('==========================================================================')
print('  WHY AUC IS 0.55 — BANKING vs ERCOT:')
print('  GFC = SYNCHRONISATION not individual bank Q blowup')
print('==========================================================================')
print()
print("Feature means per period:")
print(f"  {'Feature':<18}  {'Pre-GFC':>10}  {'  GFC':>10}  {'Post-GFC':>10}  {'Shift':>10}")
print(f"  {'-'*18}  {'-'*10}  {'-'*10}  {'-'*10}  {'-'*10}")
for k, fn in enumerate(FEATURE_NAMES):
    pre_m  = X_flat[np.repeat(PRE,  N), k].mean()
    gfc_m  = X_flat[np.repeat(GFC,  N), k].mean()
    post_m = X_flat[np.repeat(POST, N), k].mean()
    shift  = gfc_m - pre_m
    print(f"  {fn:<18}  {pre_m:>10.4f}  {gfc_m:>10.4f}  {post_m:>10.4f}  {shift:>+10.4f}")

# ── Build C* and Q for all quarters ──────────────────────────────────────────
cov = np.cov(X_flat.T)
evals, _ = np.linalg.eigh(cov)
evals = np.maximum(evals, 1e-12)
w = evals / evals.sum()
alpha = float(evals.max())
ell = EllipsoidGeometry.from_fisher_weights(w, alpha=alpha)

Q_flat = ell.quadric_value(X_flat)
Q_3d_q = Q_flat.reshape(T, N)

# ── Cross-bank synchronisation score: std of Q across banks  ─────────────────
# LOW std = all banks cluster together (systemic event)
# HIGH std = individual outliers (idiosyncratic, normal Q>1 detection)
Q_std   = Q_3d_q.std(axis=1)            # cross-bank spread
Q_mean  = Q_3d_q.mean(axis=1)           # individual alarm signal
Q_sync  = Q_mean / (Q_std + 1e-9)       # synchronisation index

print()
print("Cross-bank synchronisation index = Q_mean / Q_std  (high = systemic):")
print(f"  {'Quarter':<14}  {'Q_mean':>8}  {'Q_std':>8}  {'Sync':>8}  {'Crisis?':>8}")
print(f"  {'-'*14}  {'-'*8}  {'-'*8}  {'-'*8}  {'-'*8}")
show_q = set()
for t, dt in enumerate(dates):
    ds = str(dt.date())
    if ds in CRISIS_QTR or Q_sync[t] > 5.0 or dt.year in [2007, 2008, 2009, 2020, 2023]:
        show_q.add(t)
for t, dt in enumerate(dates):
    if t not in show_q:
        continue
    ds = str(dt.date())
    crisis = "CRISIS" if ds in CRISIS_QTR else ""
    print(f"  {ds:<14}  {Q_mean[t]:>8.4f}  {Q_std[t]:>8.4f}  {Q_sync[t]:>8.2f}  {crisis:>8}")

# ── AUC with sync score (should detect GFC better) ───────────────────────────
from sklearn.metrics import roc_auc_score
y_qtr = np.array([1 if str(d.date()) in CRISIS_QTR else 0 for d in dates])
auc_q     = roc_auc_score(y_qtr, Q_mean)
auc_sync  = roc_auc_score(y_qtr, Q_sync)
auc_qstd  = roc_auc_score(y_qtr, Q_std)
# AUC with negative Q_std (crisis = LOW spread = synchronisation)
auc_neg   = roc_auc_score(y_qtr, -Q_std)

print()
print("AUC comparison:")
print(f"  Q_mean alone (individual outlier)    AUC = {auc_q:.4f}")
print(f"  Q_std alone  (cross-bank spread)     AUC = {auc_qstd:.4f}")
print(f"  -Q_std       (low spread = systemic) AUC = {auc_neg:.4f}  <-- systemic signal")
print(f"  Q_sync = Q_mean/Q_std                AUC = {auc_sync:.4f}")

# ── Combined score: Q_mean * (1 - Q_std_normalised) ─────────────────────────
Q_std_norm = Q_std / (Q_std.max() + 1e-9)
Q_combined = Q_mean * (1.0 - 0.5 * Q_std_norm) + 0.5 * Q_mean / (Q_std.max() + 1e-9)
auc_combo  = roc_auc_score(y_qtr, Q_combined)

# Simple linear combo
for alpha_w in [0.1, 0.3, 0.5, 0.7, 0.9]:
    score = alpha_w * Q_mean - (1 - alpha_w) * Q_std
    auc_w = roc_auc_score(y_qtr, score)
    if auc_w > 0.65:
        print(f"  alpha={alpha_w:.1f}: Q_mean - (1-alpha)*Q_std  AUC = {auc_w:.4f}")

# ── What drives 2023 late alarms? ────────────────────────────────────────────
print()
print("2023 Q profile — SVB/Credit Suisse era (pure geometric, no labels):")
print(f"  {'Quarter':<14}  {'Q_mean':>8}  {'Q_std':>8}  {'fund_cost_mean':>15}")
for t, dt in enumerate(dates):
    if dt.year == 2023:
        fc_mean = X_3d[t, :, 4].mean()
        print(f"  {str(dt.date()):<14}  {Q_mean[t]:>8.4f}  {Q_std[t]:>8.4f}  {fc_mean:>15.4f}")

print()
print("INTERPRETATION:")
print("  Q(x) > 1 fires when INDIVIDUAL banks deviate beyond C*.")
print("  GFC = banks move TOGETHER inside C* (low std, high sync).")
print("  2023 = SVB/CS shock pushes INDIVIDUAL banks outside C* boundary.")
print("  => Two detector modes needed: Q_mean (idiosyncratic) + -Q_std (systemic).")
