"""
FDIC G-SIB Panel — CEK-v4 Canonical Framework Diagnostics
==========================================================
Applies the full canonical framework update to the real-world GSIB banking
panel (FDIC call reports + ECB MIR + World Bank GFDD).

Data: T=76 quarters (2005-Q1 to 2023-Q4), N=25 G-SIBs, d=5 features
  Features: loan_to_asset, equity_ratio, npl_ratio, roa, funding_cost
  Crisis labels: GFC 2007Q4–2009Q2 · Euro Debt 2011Q3–2012Q2 · COVID 2020Q1–Q2

Protocol: Strict no-leakage expanding window (identical to test_no_leakage_all.py)
  (i)   Training: quarters 0..t  |  Test: quarter t+1 (never seen)
  (ii)  StandardScaler fit on training only
  (iii) Frozen params from pre-crisis window (2005Q1–2007Q3)
  (iv)  Fixed alarm threshold μ + 3σ from pre-crisis scores

New in this script — CEK-v4 canonical diagnostics per quarter:
  G7  κ(Σ₀) > 10        →  mandatory regularisation (Gap Addendum G7)
  cosθ_t → 0             →  Phase-2 alignment degradation precursor
  tanθ_t → ∞             →  Phase-3 collapse precursor
  ρ_eff = MFLS²(1−γ)/E  →  instantaneous convergence rate
  Phase-2 lead time      →  quarters cosθ fires BEFORE crisis quarter

Cross-domain connection
-----------------------
The same three-phase precursor found in:
  EEG seizures (CHB-MIT, 15 patients)   — Phase-2 confirmed 9/15
  Protein unfolding (Go-model, Tm=530K) — Phase-2 confirmed at Tm
  → Now tested on systemic banking risk transitions.

Author: Copilot — June 2026
Theory refs: canonical_system_v4.pdf, CGS_v1_manuscript.pdf,
             canonicalgapdocument_pdf.pdf, Trigonometry_of_Collapse.pdf,
             Complete_Derivations.pdf
"""
import sys, os, time, warnings, json, gc
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'research', 'udl'))

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler
from udl.system_mode import MolecularEngine, BSDTChannels

warnings.filterwarnings("ignore")

ROOT      = r'C:\amttp'
CACHE_DIR = os.path.join(ROOT, 'research', 'adaptive-friction',
                         'banklevel_enhanced', 'gsib_cache_real')
RESULT_DIR = os.path.join(ROOT, 'research', 'adaptive-friction',
                          'banklevel_enhanced', 'results')
os.makedirs(RESULT_DIR, exist_ok=True)

# ── Load panel ────────────────────────────────────────────────────────────────
npz = np.load(os.path.join(CACHE_DIR, 'gsib_real_panel.npz'))
X_3d = npz['X']                         # (T, N, d)

with open(os.path.join(CACHE_DIR, 'gsib_real_meta.json'), encoding='utf-8') as f:
    meta = json.load(f)

dates = pd.date_range('2005-01-01', '2023-12-31', freq='QE')[:X_3d.shape[0]]
T, N, d = X_3d.shape

FEATURE_NAMES = ['loan_to_asset', 'equity_ratio', 'npl_ratio', 'roa', 'funding_cost']

CRISIS_QUARTERS = {
    # GFC
    '2007-12-31','2008-03-31','2008-06-30','2008-09-30',
    '2008-12-31','2009-03-31','2009-06-30',
    # COVID
    '2020-03-31','2020-06-30',
    # Euro sovereign debt
    '2011-09-30','2011-12-31','2012-03-31','2012-06-30',
}
y_crisis = np.array([1 if str(d.date()) in CRISIS_QUARTERS else 0
                     for d in dates])

BURN_IN   = 4
calib_end = pd.Timestamp('2007-09-30')
n_calib   = int((dates <= calib_end).sum())

FROZEN_PARAMS = dict(
    epsilon=1.0, sigma_lj=1.0, alpha_radial=0.1, eta=0.01,
    iterations=80, k_neighbors=10, max_samples=2000,
    use_fused=True, use_bsdt_damping=True, normalize=False,
)

# ═══════════════════════════════════════════════════════════════
#  Canonical calibration + alignment  (CEK-v4 / Gap Addendum G7)
# ═══════════════════════════════════════════════════════════════

def _canonical_calibration(X_ref):
    """κ(Σ₀) check — Gap Addendum G7.

    Banking interpretation:
        X_ref  = pre-crisis normal-state bank feature vectors (T_pre × N, d)
        Σ₀     = covariance of pre-crisis banking conditions
        κ > 10 → ill-conditioned financial feature ellipsoid
                 (one direction = systemic correlation; orthogonal = idiosyncratic)
                 Ψ* < 10% ideal → mandatory G7 regularisation
    """
    n, d_ = X_ref.shape
    mu   = X_ref.mean(axis=0)
    Z    = X_ref - mu
    cov  = (Z.T @ Z) / max(n - 1, 1)

    eigvals  = np.linalg.eigvalsh(cov)[::-1]
    lam_max  = float(eigvals[0])
    pos_eig  = eigvals[eigvals > 1e-12 * max(lam_max, 1e-30)]
    lam_min  = float(pos_eig[-1]) if len(pos_eig) > 0 else 1e-12
    kappa    = lam_max / max(lam_min, 1e-12)
    eff_rank = int((eigvals > 1e-12 * max(lam_max, 1e-30)).sum())

    g7_flag   = kappa > 10.0
    lam_star  = float((lam_max - 10.0 * lam_min) / 9.0) if g7_flag else 0.0
    sigma_reg = cov + max(lam_star, 0.0) * np.eye(d_)

    return dict(
        kappa       = float(kappa),
        lambda_max  = lam_max,
        lambda_min  = lam_min,
        eff_rank    = eff_rank,
        g7_flag     = bool(g7_flag),
        lambda_star = lam_star,
        sigma_reg   = sigma_reg,
        mu_ref      = mu,
    )


def _canonical_alignment_batch(X_test, mu_ref, sigma_reg, theta):
    """Per-bank canonical alignment scalars for one test quarter.

    Parameters
    ----------
    X_test   : (N, d) — bank feature vectors at quarter t+1
    mu_ref   : (d,)   — reference centroid
    sigma_reg: (d, d) — regularised reference covariance
    theta    : float  — median reference energy (adaptive gain denominator)

    Returns dict of per-bank arrays, each length N.
    """
    try:
        G = np.linalg.inv(sigma_reg)
    except np.linalg.LinAlgError:
        G = np.linalg.pinv(sigma_reg)

    eps  = 1e-10
    N_   = len(X_test)
    costheta = np.zeros(N_)
    tantheta = np.zeros(N_)
    mfls     = np.zeros(N_)
    E_arr    = np.zeros(N_)
    rho_eff  = np.zeros(N_)

    for i, x in enumerate(X_test):
        z    = x - mu_ref
        Gz   = G @ z
        E    = float(z @ Gz)
        nz   = float(np.sqrt(z @ z))
        nGz  = float(np.sqrt(Gz @ Gz))
        denom = nz * nGz
        cos_t = float(np.clip(-E / max(denom, eps), -1.0, 0.0))
        sin2  = max(1.0 - cos_t ** 2, 0.0)
        tan_t = float(np.sqrt(sin2) / max(-cos_t, eps))
        mfls_i  = 2.0 * nGz
        gam_i   = E / (E + theta)
        rho_i   = mfls_i ** 2 * (1.0 - gam_i) / max(E, eps)

        costheta[i] = cos_t
        tantheta[i] = tan_t
        mfls[i]     = mfls_i
        E_arr[i]    = E
        rho_eff[i]  = rho_i

    return dict(costheta=costheta, tantheta=tantheta,
                mfls=mfls, E=E_arr, rho_eff=rho_eff)


# ═══════════════════════════════════════════════════════════════
#  Expanding-window loop
# ═══════════════════════════════════════════════════════════════

print("=" * 72)
print("  FDIC G-SIB PANEL — CEK-v4 Canonical Diagnostics")
print("  Molecular Engine + G7 · cosθ · tanθ · ρ_eff per quarter")
print("=" * 72)
print(f"  Data: FDIC call reports + ECB MIR + World Bank GFDD")
print(f"  Panel: T={T} quarters, N={N} G-SIBs, d={d} features")
print(f"  Features: {FEATURE_NAMES}")
print(f"  Date range: {dates[0].date()} → {dates[-1].date()}")
print(f"  Crisis quarters: {int(y_crisis.sum())}/{T} "
      f"(GFC + Euro Debt + COVID)")
print()

# Storage for all time-series
q_scores   = np.full(T, np.nan)     # Molecular engine score per quarter
q_costheta = np.full(T, np.nan)     # mean cosθ per quarter (cross-bank)
q_tantheta = np.full(T, np.nan)     # mean tanθ per quarter
q_rho_eff  = np.full(T, np.nan)     # mean ρ_eff per quarter
q_mfls     = np.full(T, np.nan)     # mean MFLS per quarter
q_E        = np.full(T, np.nan)     # mean E per quarter
q_kappa    = np.full(T, np.nan)     # κ(Σ₀) per quarter (from expanding training)
q_g7       = np.full(T, False)      # G7 flag per quarter

# Pre-crisis reference for canonical baseline (frozen at calib_end)
_calib_ref_built = False
_calib_mu   = None
_calib_sreg = None
_calib_theta = None
_calib_kappa = None
_calib_g7    = None

t0_total = time.time()

for t in range(BURN_IN, T - 1):
    # ── Training: quarters 0..t (no leakage: test is t+1) ──
    n_train_q   = t + 1
    X_train_raw = X_3d[:n_train_q].reshape(n_train_q * N, d)
    y_train     = np.zeros(n_train_q * N, dtype=int)
    for t_idx in range(n_train_q):
        if str(dates[t_idx].date()) in CRISIS_QUARTERS:
            y_train[t_idx * N:(t_idx + 1) * N] = 1

    scaler      = StandardScaler()
    X_train     = scaler.fit_transform(X_train_raw).astype(np.float64)

    X_test_raw  = X_3d[t + 1].reshape(N, d)
    X_test      = scaler.transform(X_test_raw).astype(np.float64)

    # ── MolecularEngine score ──
    eng = MolecularEngine(**FROZEN_PARAMS)
    _ = eng.fit_score(X_train, y_train)
    if eng.fused_scorer is not None:
        test_scores = eng.fused_scorer.score(X_test)
    else:
        test_scores = np.linalg.norm(X_test - X_test.mean(0), axis=1)
    q_scores[t + 1] = float(test_scores.mean())

    # ── Canonical calibration from NORMAL training data ──
    normal_mask = (y_train == 0)
    X_normal = X_train[normal_mask]
    if len(X_normal) < 3:
        X_normal = X_train

    calib = _canonical_calibration(X_normal)
    q_kappa[t + 1] = calib['kappa']
    q_g7[t + 1]    = calib['g7_flag']

    # Freeze reference at calib_end for canonical alignment baseline
    if not _calib_ref_built and dates[t] >= calib_end:
        _calib_mu    = calib['mu_ref'].copy()
        _calib_sreg  = calib['sigma_reg'].copy()
        _calib_theta = float(np.median(
            np.einsum('ni,ij,nj->n',
                      X_normal - calib['mu_ref'],
                      np.linalg.inv(calib['sigma_reg']),
                      X_normal - calib['mu_ref'])
        )) + 1e-10
        _calib_kappa = calib['kappa']
        _calib_g7    = calib['g7_flag']
        _calib_ref_built = True

    # ── Canonical alignment against FROZEN pre-crisis reference ──
    if _calib_ref_built:
        align = _canonical_alignment_batch(
            X_test, _calib_mu, _calib_sreg, _calib_theta)
        q_costheta[t + 1] = float(np.mean(align['costheta']))
        q_tantheta[t + 1] = float(np.mean(align['tantheta']))
        q_rho_eff[t + 1]  = float(np.mean(align['rho_eff']))
        q_mfls[t + 1]     = float(np.mean(align['mfls']))
        q_E[t + 1]        = float(np.mean(align['E']))

    del eng
    gc.collect()

    # Progress print
    ds = str(dates[t + 1].date())
    is_crisis = ds in CRISIS_QUARTERS
    g7_str    = '⚠G7' if calib['g7_flag'] else '  ok'
    cos_str   = f"cosθ={q_costheta[t+1]:.4f}" if not np.isnan(q_costheta[t+1]) else "cosθ=N/A"
    tan_str   = f"tanθ={q_tantheta[t+1]:.3f}" if not np.isnan(q_tantheta[t+1]) else "tanθ=N/A"
    crisis_tag = ' <<< CRISIS' if is_crisis else ''
    if is_crisis or (t + 1) % 8 == 0:
        print(f"  t={t+1:3d}  {ds}  score={q_scores[t+1]:.4f}  "
              f"{g7_str}  κ={q_kappa[t+1]:.2e}  "
              f"{cos_str}  {tan_str}{crisis_tag}")

elapsed = time.time() - t0_total

# ═══════════════════════════════════════════════════════════════
#  Fixed threshold from pre-crisis calibration window
# ═══════════════════════════════════════════════════════════════
calib_scores = q_scores[BURN_IN + 1:n_calib + 1]
calib_scores = calib_scores[~np.isnan(calib_scores)]
mu_cal   = calib_scores.mean()
std_cal  = calib_scores.std() + 1e-10
FIXED_THR = mu_cal + 3.0 * std_cal

valid = ~np.isnan(q_scores)
q_valid   = q_scores[valid]
y_valid   = y_crisis[valid]
dates_valid = dates[valid]

auroc = roc_auc_score(y_valid, q_valid) \
    if 0 < y_valid.sum() < len(y_valid) else float('nan')

y_pred   = (q_valid >= FIXED_THR).astype(int)
TP = int(((y_pred == 1) & (y_valid == 1)).sum())
FP = int(((y_pred == 1) & (y_valid == 0)).sum())
FN = int(((y_pred == 0) & (y_valid == 1)).sum())
TN = int(((y_pred == 0) & (y_valid == 0)).sum())
far     = FP / (TN + FP) * 100 if (TN + FP) > 0 else 0.0
recall  = TP / (TP + FN) * 100 if (TP + FN) > 0 else 0.0
prec    = TP / (TP + FP) * 100 if (TP + FP) > 0 else 0.0

# GFC-only AUROC
gfc_qs   = {'2007-12-31','2008-03-31','2008-06-30','2008-09-30',
            '2008-12-31','2009-03-31','2009-06-30'}
gfc_mask = np.array([str(dates[i].date()) in gfc_qs for i in range(T)])
gfc_or_norm = valid & (gfc_mask | (y_crisis == 0))
auroc_gfc = roc_auc_score(y_crisis[gfc_or_norm], q_scores[gfc_or_norm]) \
    if gfc_or_norm.sum() > 2 else float('nan')

# ═══════════════════════════════════════════════════════════════
#  Canonical diagnostics — aggregate statistics
# ═══════════════════════════════════════════════════════════════

# Baseline: mean cosθ / tanθ in PRE-CRISIS quarters only
pre_crisis_mask = valid & (y_crisis == 0) & (dates < pd.Timestamp('2007-12-31'))
cos_baseline = float(np.nanmean(q_costheta[pre_crisis_mask])) \
    if pre_crisis_mask.sum() > 0 else np.nan
tan_baseline = float(np.nanmean(q_tantheta[pre_crisis_mask])) \
    if pre_crisis_mask.sum() > 0 else np.nan
rho_baseline = float(np.nanmean(q_rho_eff[pre_crisis_mask])) \
    if pre_crisis_mask.sum() > 0 else np.nan

# Per-episode canonical means
episodes = {
    'Pre-crisis (2005Q1–2007Q3)': (dates < pd.Timestamp('2007-12-31')) & (y_crisis == 0) & valid,
    'GFC 2007Q4–2009Q2':          np.array([str(dates[i].date()) in gfc_qs for i in range(T)]) & valid,
    'Euro Debt 2011Q3–2012Q2':    np.array([str(dates[i].date()) in
                                            {'2011-09-30','2011-12-31','2012-03-31','2012-06-30'}
                                            for i in range(T)]) & valid,
    'COVID 2020Q1–Q2':            np.array([str(dates[i].date()) in
                                            {'2020-03-31','2020-06-30'}
                                            for i in range(T)]) & valid,
    'Post-COVID normal (2021+)':  (dates >= pd.Timestamp('2021-01-01')) & (y_crisis == 0) & valid,
}

# G7 statistics
g7_valid = q_g7[valid]
g7_crisis = q_g7[valid & (y_crisis == 1)]
g7_normal = q_g7[valid & (y_crisis == 0)]

# Phase-2 lead time: first quarter cosθ > cos_baseline + 0.05 before each crisis onset
COS_P2_THR = cos_baseline + 0.05 if not np.isnan(cos_baseline) else -0.85
TAN_P3_THR = tan_baseline + 0.5  if not np.isnan(tan_baseline) else 1.0

crisis_onsets = []
in_crisis = False
for i in range(T):
    if y_crisis[i] == 1 and not in_crisis:
        crisis_onsets.append(i)
        in_crisis = True
    elif y_crisis[i] == 0:
        in_crisis = False

lead_times_p2 = []
for onset_t in crisis_onsets:
    # Search backward up to 8 quarters (2 years) for first Phase-2 signal
    search_start = max(0, onset_t - 8)
    p2_quarter = None
    for look in range(onset_t - 1, search_start - 1, -1):
        if not np.isnan(q_costheta[look]) and q_costheta[look] > COS_P2_THR:
            p2_quarter = look
        else:
            break  # only count consecutive quarters
    if p2_quarter is not None:
        lead_times_p2.append(onset_t - p2_quarter)

# ═══════════════════════════════════════════════════════════════
#  Print results
# ═══════════════════════════════════════════════════════════════

print()
print("=" * 72)
print("  ENGINE PERFORMANCE (MolecularEngine + FusedSystemScorer)")
print("=" * 72)
print(f"  AUROC (all crisis):       {auroc:.3f}")
print(f"  AUROC (GFC only):         {auroc_gfc:.3f}")
print(f"  Threshold (μ+3σ calib):   {FIXED_THR:.4f}")
print(f"  Recall (sensitivity):     {recall:.1f}%  ({TP}/{TP+FN} crisis quarters flagged)")
print(f"  False Alarm Rate:         {far:.1f}%  ({FP}/{TN+FP} normal quarters)")
print(f"  Precision:                {prec:.1f}%")
print(f"  TP={TP}  FP={FP}  FN={FN}  TN={TN}")
print(f"  Elapsed: {elapsed:.1f}s")

print()
print("=" * 72)
print("  CANONICAL DIAGNOSTICS (CEK-v4 / Gap Addendum G7)")
print("=" * 72)

print(f"\n  Reference frozen at: {calib_end.date()}  "
      f"(pre-crisis normal-state calibration)")
print(f"  κ(Σ₀) at calibration freeze: {_calib_kappa:.3e}")
g7_str = f"⚠ G7 FLAGGED (ill-conditioned)" if _calib_g7 else "✓ well-conditioned"
print(f"  G7 status: {g7_str}")

print(f"\n  G7 flag rate over time:")
print(f"    All quarters:    {g7_valid.mean()*100:.0f}%  ({g7_valid.sum()}/{len(g7_valid)})")
print(f"    Crisis quarters: {g7_crisis.mean()*100:.0f}%  ({g7_crisis.sum()}/{len(g7_crisis)})")
print(f"    Normal quarters: {g7_normal.mean()*100:.0f}%  ({g7_normal.sum()}/{len(g7_normal)})")

print(f"\n  Canonical baselines (pre-crisis 2005Q1–2007Q3):")
print(f"    cosθ baseline: {cos_baseline:.4f}")
print(f"    tanθ baseline: {tan_baseline:.4f}")
print(f"    ρ_eff baseline: {rho_baseline:.6f}")

print(f"\n  Phase-2 alarm threshold (cosθ > baseline + 0.05): {COS_P2_THR:.4f}")
print(f"  Phase-3 alarm threshold (tanθ > baseline + 0.50): {TAN_P3_THR:.4f}")

print()
print(f"  {'Episode':<35} {'cosθ':>8} {'Δcosθ':>8} {'tanθ':>8} {'Δtanθ':>8} "
      f"{'ρ_eff':>9} {'P2':>4} {'P3':>4}")
print("  " + "─" * 80)

for ep_name, ep_mask in episodes.items():
    if ep_mask.sum() == 0:
        continue
    cos_m = float(np.nanmean(q_costheta[ep_mask]))
    tan_m = float(np.nanmean(q_tantheta[ep_mask]))
    rho_m = float(np.nanmean(q_rho_eff[ep_mask]))
    d_cos = cos_m - cos_baseline if not np.isnan(cos_baseline) else float('nan')
    d_tan = tan_m - tan_baseline if not np.isnan(tan_baseline) else float('nan')
    p2 = '★' if d_cos > 0.01 else ' '
    p3 = '★' if d_tan > 0.1  else ' '
    print(f"  {ep_name:<35} {cos_m:>8.4f} {d_cos:>+8.4f} "
          f"{tan_m:>8.4f} {d_tan:>+8.4f} {rho_m:>9.6f} {p2:>4} {p3:>4}")

# Phase-2 lead time
print(f"\n  Phase-2 lead-time analysis (cosθ > {COS_P2_THR:.4f} before crisis onset):")
print(f"    Crisis onset quarters detected: {len(crisis_onsets)}")
for i, onset_t in enumerate(crisis_onsets):
    ep_date = str(dates[onset_t].date())
    lead = lead_times_p2[i] if i < len(lead_times_p2) else None
    if lead is not None:
        print(f"    Crisis {i+1} onset {ep_date}: Phase-2 signal {lead} quarter(s) ahead")
    else:
        print(f"    Crisis {i+1} onset {ep_date}: no Phase-2 signal detected in prior 8Q")

if lead_times_p2:
    print(f"    Mean Phase-2 lead: {np.mean(lead_times_p2):.1f} quarters  "
          f"({np.mean(lead_times_p2)*3:.0f} months)")
else:
    print(f"    No Phase-2 lead times detected")

# ── Quarter-by-quarter canonical time series ──────────────────────────────
print()
print("=" * 72)
print("  QUARTERLY CANONICAL TIME-SERIES")
print("=" * 72)
print(f"  {'Quarter':<14} {'Score':>7} {'cosθ':>8} {'tanθ':>8} "
      f"{'ρ_eff':>9} {'κ':>10} {'G7':>3}  {'Label'}")
print("  " + "─" * 70)

for i in range(T):
    if np.isnan(q_scores[i]):
        continue
    ds = str(dates[i].date())
    is_crisis = y_crisis[i] == 1
    cos_s  = f"{q_costheta[i]:.4f}" if not np.isnan(q_costheta[i]) else "  N/A  "
    tan_s  = f"{q_tantheta[i]:.4f}" if not np.isnan(q_tantheta[i]) else "  N/A  "
    rho_s  = f"{q_rho_eff[i]:.6f}"  if not np.isnan(q_rho_eff[i])  else "  N/A   "
    kap_s  = f"{q_kappa[i]:.2e}"    if not np.isnan(q_kappa[i])     else "  N/A  "
    g7_s   = "⚠" if q_g7[i] else " "
    p2_s   = " P2★" if (not np.isnan(q_costheta[i]) and q_costheta[i] > COS_P2_THR) else ""
    p3_s   = " P3★" if (not np.isnan(q_tantheta[i]) and q_tantheta[i] > TAN_P3_THR) else ""
    label  = "CRISIS" if is_crisis else "normal"
    alarm  = " ◄ALARM" if q_scores[i] >= FIXED_THR else ""
    print(f"  {ds:<14} {q_scores[i]:>7.4f} {cos_s:>8} {tan_s:>8} "
          f"{rho_s:>9} {kap_s:>10} {g7_s:>3}  {label}{alarm}{p2_s}{p3_s}")

# ── Save results ─────────────────────────────────────────────────────────────
out = {
    'metadata': {
        'T': T, 'N': N, 'd': d,
        'date_range': [str(dates[0].date()), str(dates[-1].date())],
        'features': FEATURE_NAMES,
        'crisis_quarters': list(CRISIS_QUARTERS),
        'calib_freeze_date': str(calib_end.date()),
        'calib_kappa': float(_calib_kappa) if _calib_kappa else None,
        'calib_g7': bool(_calib_g7) if _calib_g7 is not None else None,
        'cos_baseline': float(cos_baseline),
        'tan_baseline': float(tan_baseline),
        'rho_baseline': float(rho_baseline),
        'cos_p2_threshold': float(COS_P2_THR),
        'tan_p3_threshold': float(TAN_P3_THR),
    },
    'performance': {
        'auroc': float(auroc),
        'auroc_gfc': float(auroc_gfc),
        'threshold': float(FIXED_THR),
        'recall_pct': float(recall),
        'far_pct': float(far),
        'precision_pct': float(prec),
        'TP': TP, 'FP': FP, 'FN': FN, 'TN': TN,
    },
    'canonical': {
        'g7_rate_all':     float(g7_valid.mean()),
        'g7_rate_crisis':  float(g7_crisis.mean()),
        'g7_rate_normal':  float(g7_normal.mean()),
        'phase2_lead_times_q': lead_times_p2,
        'phase2_mean_lead_q':  float(np.mean(lead_times_p2)) if lead_times_p2 else None,
        'episodes': {
            ep: {
                'cos_mean': float(np.nanmean(q_costheta[m])),
                'tan_mean': float(np.nanmean(q_tantheta[m])),
                'rho_mean': float(np.nanmean(q_rho_eff[m])),
                'delta_cos': float(np.nanmean(q_costheta[m]) - cos_baseline),
                'delta_tan': float(np.nanmean(q_tantheta[m]) - tan_baseline),
            }
            for ep, m in episodes.items() if m.sum() > 0
        },
    },
    'timeseries': {
        'dates':     [str(d.date()) for d in dates],
        'y_crisis':  y_crisis.tolist(),
        'scores':    [float(x) if not np.isnan(x) else None for x in q_scores],
        'costheta':  [float(x) if not np.isnan(x) else None for x in q_costheta],
        'tantheta':  [float(x) if not np.isnan(x) else None for x in q_tantheta],
        'rho_eff':   [float(x) if not np.isnan(x) else None for x in q_rho_eff],
        'kappa':     [float(x) if not np.isnan(x) else None for x in q_kappa],
        'g7_flag':   [bool(x) for x in q_g7],
    },
}

out_path = os.path.join(RESULT_DIR, 'gsib_canonical_results.json')
with open(out_path, 'w') as f:
    json.dump(out, f, indent=2)
print(f"\n  Results → {out_path}")
print()
