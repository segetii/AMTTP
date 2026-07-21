#!/usr/bin/env python3
"""
bank_retrospective_cv.py
========================
Three retrospective cross-validations for the BSDT banking signal.

CV1 – Crisis Chronology
  Was the aggregate signal elevated BEFORE each independently-dated
  crisis milestone? (Bear Stearns, Lehman, WaMu, Wachovia, FDIC wave,
  Euro sovereign, COVID freeze, COVID recovery.)

CV2 – Out-of-Sample Walk-Forward
  Split A: calibrate 2005Q1–2007Q3, test 2007Q4–2010Q4 (GFC OOS).
  Split B: calibrate 2005Q1–2013Q4, test 2014Q1–2020Q2 (COVID OOS).
  Were crisis quarters above the OOS threshold?

CV3 – Institution Ranking
  Per-bank mean canonical E in the 4 quarters BEFORE GFC onset.
  Rank 20 G-SIBs and compare against known vulnerability ordering.

Data: FDIC G-SIB panel  T=76 quarters (2005Q1–2023Q4), N=20, d=5
Features: loan_to_asset, equity_ratio, npl_ratio, roa, funding_cost

Author: Odeyemi Olusegun Israel — AMTTP/UDL
"""

import sys, os, warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── Load panel ─────────────────────────────────────────────────────────────
CACHE = r"research\adaptive-friction\banklevel_enhanced\gsib_cache_real"
import json

npz   = np.load(os.path.join(CACHE, "gsib_real_panel.npz"))
X_3d  = npz["X"].astype(np.float64)          # (T, N, d)
meta  = json.load(open(os.path.join(CACHE, "gsib_real_meta.json")))
T, N, d = X_3d.shape

dates = pd.date_range("2005-01-01", periods=T, freq="QE")
BANK_NAMES = [b["name"] for b in meta]

# ── Known GFC vulnerability (external ground truth for CV3) ────────────────
# Source: Congressional Oversight Panel (2010), FDIC loss data, BIS reports.
# Scale: 1=low stress, 5=extreme stress (systemic failure / state rescue).
KNOWN_VULNERABILITY = {
    # US
    "JPMorgan Chase":         2,   # Acquired Bear Stearns, net buyer of assets
    "Bank of America":        4,   # $45B TARP, Merrill Lynch acquisition disaster
    "Citibank NA":            5,   # $45B TARP + $300B guarantee, near-nationalised
    "Wells Fargo":            3,   # $25B TARP, acquired Wachovia (distressed)
    "Goldman Sachs Bank USA": 2,   # $10B TARP (repaid quickly), short positions
    "BNY Mellon":             1,   # $3B TARP, custodial bank, low credit risk
    # EU
    "HSBC":                   3,   # Large subprime write-downs (Household Finance)
    "BNP Paribas":            3,   # Triggered Aug-2007 MMF freeze, EU writedowns
    "Deutsche Bank":          4,   # Severe CDS stress, €7.5B capital raise 2013
    "Barclays":               4,   # Acquired Lehman assets, raised private capital
    "Societe Generale":       3,   # Kerviel fraud + structured credit losses
    "UniCredit":              3,   # Rights issues, Italian sovereign exposure
    "ING":                    4,   # Dutch government €10B rescue
    # Asia (relatively insulated from US subprime)
    "Mitsubishi UFJ":         1,   # Acquired 20% Morgan Stanley stake (strength)
    "Mizuho":                 2,   # Some structured credit exposure
    "Sumitomo Mitsui":        1,   # Limited direct subprime exposure
    "Bank of China":          2,   # US Treasury holdings, limited subprime
    "ICBC":                   1,   # Domestic China focus, little GFC exposure
    "China Construction Bank":1,   # Domestic China focus
    "Standard Chartered":     1,   # EM focus, no US subprime
}

# ── Canonical scoring functions ─────────────────────────────────────────────

def _g7_regularise(cov):
    """Apply G7 condition-number cap: κ(Σ) ≤ 10."""
    eigvals = np.linalg.eigvalsh(cov)[::-1]
    lam_max = float(eigvals[0])
    pos_eig = eigvals[eigvals > 1e-12 * max(lam_max, 1e-30)]
    lam_min = float(pos_eig[-1]) if len(pos_eig) else 1e-12
    kappa   = lam_max / max(lam_min, 1e-12)
    if kappa > 10.0:
        lam_star = (lam_max - 10.0 * lam_min) / 9.0
        cov = cov + max(lam_star, 0.0) * np.eye(cov.shape[0])
        kappa_eff = 10.0
    else:
        kappa_eff = kappa
    return cov, kappa_eff


def calibrate(X_3d, dates, calib_end):
    """
    Fit calibration parameters on data up to calib_end (inclusive).
    Returns: mu, G (precision), theta (median E_calib), kappa.
    """
    mask = dates <= pd.Timestamp(calib_end)
    X_ref = X_3d[mask].reshape(-1, d)        # (T_calib*N, d)

    # Z-score within calibration window (each feature)
    from sklearn.preprocessing import StandardScaler
    scaler = StandardScaler()
    X_ref_s = scaler.fit_transform(X_ref)

    mu  = X_ref_s.mean(axis=0)
    Z   = X_ref_s - mu
    cov = (Z.T @ Z) / max(len(Z) - 1, 1)
    cov, kappa = _g7_regularise(cov)

    try:
        G = np.linalg.inv(cov)
    except np.linalg.LinAlgError:
        G = np.linalg.pinv(cov)

    # Median E on calibration set (adaptive gain denominator)
    e_calib = np.einsum("ni,ij,nj->n", Z, G, Z)
    theta   = float(np.median(e_calib)) + 1e-10

    return scaler, mu, G, theta, kappa


def score_panel(X_3d, dates, calib_end):
    """
    Score all T quarters and all N banks against a calibration frozen
    at calib_end.

    Returns:
      E_sys    (T,)    — cross-bank mean Mahalanobis E per quarter
      E_bank   (T, N)  — per-bank E per quarter
      cos_sys  (T,)    — cross-bank mean cosθ
      tan_sys  (T,)    — cross-bank mean tanθ
      mfls_sys (T,)    — cross-bank mean MFLS = 2‖Gz‖
      kappa    float   — κ(Σ₀) at calibration
    """
    scaler, mu, G, theta, kappa = calibrate(X_3d, dates, calib_end)
    eps = 1e-10

    E_sys  = np.full(T, np.nan)
    E_bank = np.full((T, N), np.nan)
    cos_sys  = np.full(T, np.nan)
    tan_sys  = np.full(T, np.nan)
    mfls_sys = np.full(T, np.nan)

    for t in range(T):
        X_t = scaler.transform(X_3d[t])          # (N, d)
        Z_t = X_t - mu                            # (N, d)
        GZ  = Z_t @ G.T                           # (N, d)

        E_t = np.einsum("ni,ni->n", Z_t, GZ)      # (N,)
        E_sys[t]    = float(E_t.mean())
        E_bank[t]   = E_t

        nz  = np.linalg.norm(Z_t, axis=1)
        nGz = np.linalg.norm(GZ,  axis=1)
        denom = nz * nGz
        cos_t = np.where(denom > eps,
                         np.clip(-E_t / denom, -1.0, 0.0),
                         0.0)
        sin2_t = np.maximum(1.0 - cos_t**2, 0.0)
        tan_t  = np.sqrt(sin2_t) / np.maximum(-cos_t, eps)
        mfls_t = 2.0 * nGz

        cos_sys[t]  = float(cos_t.mean())
        tan_sys[t]  = float(tan_t.mean())
        mfls_sys[t] = float(mfls_t.mean())

    return E_sys, E_bank, cos_sys, tan_sys, mfls_sys, kappa


# ── Quarter index lookup ────────────────────────────────────────────────────

def qt(date_str):
    """Return integer index of the quarter for 'YYYY-MM-DD'."""
    ts = pd.Timestamp(date_str)
    idx = np.where((dates.year == ts.year) & (dates.quarter == ts.quarter))[0]
    return int(idx[0]) if len(idx) else None


def ql(t):
    """Return human-readable quarter label for index t."""
    d = dates[t]
    return f"{d.year}-Q{d.quarter}"


# ═══════════════════════════════════════════════════════════════════════════
#  COMMON CALIBRATION  (frozen at 2007-Q3, exactly as in test_gsib_canonical)
# ═══════════════════════════════════════════════════════════════════════════
CALIB_END_GFC = "2007-09-30"

E_sys, E_bank, cos_sys, tan_sys, mfls_sys, kappa_gfc = \
    score_panel(X_3d, dates, CALIB_END_GFC)

# Threshold from calibration window
calib_mask = dates <= pd.Timestamp(CALIB_END_GFC)
E_calib    = E_sys[calib_mask]
E_calib    = E_calib[~np.isnan(E_calib)]
mu_c  = float(E_calib.mean())
std_c = float(E_calib.std()) + 1e-10
THR_2S  = mu_c + 2.0 * std_c
THR_3S  = mu_c + 3.0 * std_c

print("=" * 72)
print("  BSDT BANKING — RETROSPECTIVE EVENT-STUDY VALIDATION")
print("  Three Cross-Validations on FDIC G-SIB Panel")
print("  T=76 quarters (2005-Q1 → 2023-Q4) · N=20 G-SIBs · d=5 features")
print("=" * 72)
print(f"  Calibration window  : 2005-Q1 → 2007-Q3  (n={calib_mask.sum()} quarters)")
print(f"  κ(Σ₀)               : {kappa_gfc:.1f}  {'[G7 regularised]' if kappa_gfc >= 9.9 else ''}")
print(f"  Calib E  μ±σ        : {mu_c:.3f} ± {std_c:.3f}")
print(f"  2σ threshold        : {THR_2S:.3f}")
print(f"  3σ threshold        : {THR_3S:.3f}")

# ═══════════════════════════════════════════════════════════════════════════
#  CV1 — CRISIS CHRONOLOGY
#  For each milestone: signal level 4 / 2 / 1 quarters before & at the event.
# ═══════════════════════════════════════════════════════════════════════════

print()
print("━" * 72)
print("  CV1 — CRISIS CHRONOLOGY")
print("  Q: Was the signal elevated BEFORE each independent milestone?")
print("━" * 72)

# Crisis milestones with independent external source / date
MILESTONES = [
    # GFC build-up
    ("BNP MMF freeze",     "2007-09-30", "Pre-GFC sentinel (Aug 2007 liquidity shock)"),
    ("Bear Stearns rescue","2008-03-31", "Fed-brokered JPM acquisition (March 2008)"),
    ("Lehman collapse",    "2008-09-30", "Lehman Chapter 11 (Sep 15, 2008)"),
    ("WaMu/Wachovia",      "2008-09-30", "WaMu seized Sep 25 / Wachovia distress"),
    ("TARP enacted",       "2008-12-31", "Emergency Economic Stabilization Act"),
    ("Stress test peak",   "2009-03-31", "SCAP / 'Stress Tests' announced Feb 2009"),
    # Euro sovereign
    ("Italian yield >7%",  "2011-12-31", "Italian 10Y > 7% (Nov 2011), SMP activated"),
    ("Draghi 'whatever'",  "2012-06-30", "Mario Draghi speech Jul 2012 — crisis end"),
    # COVID
    ("WHO pandemic",       "2020-03-31", "WHO declares pandemic, markets crash"),
    ("COVID recovery",     "2020-06-30", "Fed facilities, markets recovering"),
]

hdr = (f"{'Milestone':<24} {'Date':<9} {'E(t)':<7} {'Z(t)':<6} "
       f"{'E(t-1)':<7} {'E(t-2)':<7} {'E(t-4)':<7} "
       f"{'↑2σ?':5} {'↑3σ?':5} {'Lead':<6}")
print(f"\n  {hdr}")
print("  " + "-" * (len(hdr) + 2))

cv1_rows = []
for name, date_str, desc in MILESTONES:
    t_event = qt(date_str)
    if t_event is None or t_event >= T:
        continue
    E_t    = E_sys[t_event]
    E_tm1  = E_sys[t_event - 1] if t_event >= 1 else np.nan
    E_tm2  = E_sys[t_event - 2] if t_event >= 2 else np.nan
    E_tm4  = E_sys[t_event - 4] if t_event >= 4 else np.nan
    Z_t    = (E_t - mu_c) / std_c

    above_2s = "YES" if E_t >= THR_2S else "no"
    above_3s = "YES" if E_t >= THR_3S else "no"

    # Lead: how many quarters BEFORE the event was 2σ first breached?
    lead = None
    for lag in range(1, 9):
        if t_event - lag < 0:
            break
        if E_sys[t_event - lag] >= THR_2S:
            lead = lag

    lead_str = f"+{lead}q" if lead else "—"

    row = (f"  {name:<24} {ql(t_event):<9} "
           f"{E_t:6.3f}  {Z_t:+5.2f}  "
           f"{E_tm1:6.3f}  {E_tm2:6.3f}  {E_tm4:6.3f}  "
           f"{above_2s:5} {above_3s:5} {lead_str:<6}")
    print(row)
    cv1_rows.append({
        "milestone": name, "quarter": ql(t_event),
        "E_t": E_t, "Z_t": Z_t,
        "E_tm1": E_tm1, "E_tm2": E_tm2, "E_tm4": E_tm4,
        "above_2s": above_2s == "YES", "above_3s": above_3s == "YES",
        "lead_q": lead,
        "desc": desc,
    })

print(f"\n  Threshold: 2σ = {THR_2S:.3f}  |  3σ = {THR_3S:.3f}")
print(f"  Lead = #quarters prior that first breached 2σ (before event quarter)")

n_above_2s = sum(1 for r in cv1_rows if r["above_2s"])
n_above_3s = sum(1 for r in cv1_rows if r["above_3s"])
n_lead      = sum(1 for r in cv1_rows if r["lead_q"] and r["lead_q"] >= 2)
print(f"\n  Summary: {n_above_2s}/{len(cv1_rows)} milestones above 2σ  |  "
      f"{n_above_3s}/{len(cv1_rows)} above 3σ  |  "
      f"{n_lead}/{len(cv1_rows)} had ≥2-quarter advance signal")

# ═══════════════════════════════════════════════════════════════════════════
#  CV2 — OUT-OF-SAMPLE WALK-FORWARD
#  Calibrate on period A; test on period B (never seen during calibration).
#  Report: hit rate on crisis quarters, false-alarm rate on normal quarters.
# ═══════════════════════════════════════════════════════════════════════════

print()
print("━" * 72)
print("  CV2 — OUT-OF-SAMPLE WALK-FORWARD")
print("  Q: Does the signal identify crises in periods unseen during calibration?")
print("━" * 72)

CRISIS_QUARTERS_SET = {
    # GFC
    "2007-12-31","2008-03-31","2008-06-30","2008-09-30",
    "2008-12-31","2009-03-31","2009-06-30",
    # Euro sovereign
    "2011-09-30","2011-12-31","2012-03-31","2012-06-30",
    # COVID
    "2020-03-31","2020-06-30",
}
y_crisis = np.array([1 if str(d.date()) in CRISIS_QUARTERS_SET else 0 for d in dates])

def _oos_analysis(calib_end, test_start, test_end, label):
    """Score out-of-sample test window using frozen calibration."""
    E_s, _, cos_s, tan_s, mfls_s, kap = score_panel(X_3d, dates, calib_end)

    cal_m  = dates <= pd.Timestamp(calib_end)
    E_cal  = E_s[cal_m]; E_cal = E_cal[~np.isnan(E_cal)]
    mu_l   = E_cal.mean(); std_l = E_cal.std() + 1e-10
    thr2   = mu_l + 2.0 * std_l
    thr3   = mu_l + 3.0 * std_l

    test_m = (dates >= pd.Timestamp(test_start)) & (dates <= pd.Timestamp(test_end))
    E_test = E_s[test_m]
    y_test = y_crisis[test_m]
    d_test = dates[test_m]

    crisis_E   = E_test[y_test == 1]
    normal_E   = E_test[y_test == 0]
    hit_2s     = (crisis_E >= thr2).mean() if len(crisis_E) else np.nan
    hit_3s     = (crisis_E >= thr3).mean() if len(crisis_E) else np.nan
    far_2s     = (normal_E >= thr2).mean() if len(normal_E) else np.nan
    far_3s     = (normal_E >= thr3).mean() if len(normal_E) else np.nan

    # Lead time: first quarter above 2σ before first crisis quarter
    first_crisis_t = None
    for tt, yy in zip(d_test, y_test):
        if yy == 1:
            first_crisis_t = tt; break

    lead_q = None
    if first_crisis_t is not None:
        pre_mask = (dates < first_crisis_t) & (dates >= pd.Timestamp(test_start))
        pre_E    = E_s[pre_mask]
        pre_d    = dates[pre_mask]
        for i in range(len(pre_E) - 1, -1, -1):
            if pre_E[i] >= thr2:
                lead_q = int((first_crisis_t - pre_d[i]).days // 90)
                break

    # Mean E by state
    mean_crisis = float(np.nanmean(crisis_E)) if len(crisis_E) else np.nan
    mean_normal = float(np.nanmean(normal_E)) if len(normal_E) else np.nan

    print(f"\n  ── {label}")
    print(f"     Calibration : up to {calib_end}  (n_calib={cal_m.sum()}q, "
          f"κ={kap:.1f})")
    print(f"     Test window : {test_start} → {test_end}  "
          f"(n={test_m.sum()}q: {int(y_test.sum())} crisis, "
          f"{int((y_test==0).sum())} normal)")
    print(f"     Calib E     : μ={mu_l:.3f}, σ={std_l:.3f}  "
          f"→  2σ thr={thr2:.3f}, 3σ thr={thr3:.3f}")
    print(f"     Mean E (crisis vs normal): {mean_crisis:.3f} vs {mean_normal:.3f}")
    print(f"     Hit rate @2σ : {hit_2s:.2f}  |  FA rate @2σ : {far_2s:.2f}  "
          f"→  HR/FA = {hit_2s/max(far_2s,1e-6):.1f}×")
    print(f"     Hit rate @3σ : {hit_3s:.2f}  |  FA rate @3σ : {far_3s:.2f}")
    if lead_q:
        print(f"     First alarm before crisis : {lead_q} quarters lead")
    else:
        print(f"     First alarm before crisis : none (no pre-crisis breach)")

    # Verdict
    if hit_2s >= 0.5 and far_2s < 0.3:
        verdict = "CONFIRMED OOS ✓"
    elif hit_2s >= 0.4:
        verdict = "MARGINAL OOS ~"
    else:
        verdict = "NOT CONFIRMED OOS ✗"
    print(f"     Verdict      : {verdict}")
    return dict(label=label, hit_2s=hit_2s, hit_3s=hit_3s,
                far_2s=far_2s, lead_q=lead_q,
                mean_crisis=mean_crisis, mean_normal=mean_normal,
                verdict=verdict)

# Split A: calibrate on 2005Q1–2007Q3, test GFC out-of-sample 2007Q4–2010Q4
cv2a = _oos_analysis(
    calib_end  = "2007-09-30",
    test_start = "2007-12-31",
    test_end   = "2010-12-31",
    label      = "Split A — GFC OOS  (calib 2005Q1–2007Q3, test 2007Q4–2010Q4)"
)

# Split B: calibrate on 2005Q1–2013Q4, test COVID out-of-sample 2014Q1–2020Q2
cv2b = _oos_analysis(
    calib_end  = "2013-12-31",
    test_start = "2014-03-31",
    test_end   = "2020-06-30",
    label      = "Split B — COVID OOS  (calib 2005Q1–2013Q4, test 2014Q1–2020Q2)"
)

# ═══════════════════════════════════════════════════════════════════════════
#  CV3 — INSTITUTION RANKING
#  Which banks had the highest canonical E in the 4 quarters before GFC onset?
#  Compare predicted vulnerability ranking vs known bailout severity.
# ═══════════════════════════════════════════════════════════════════════════

print()
print("━" * 72)
print("  CV3 — INSTITUTION RANKING")
print("  Q: Do pre-crisis bank scores correctly rank vulnerability?")
print("  Metric: mean per-bank E  in 4 quarters before GFC onset (2007Q4)")
print("━" * 72)

# 4 pre-crisis quarters: 2006-Q4, 2007-Q1, 2007-Q2, 2007-Q3
PRE_CRISIS_DATES = ["2006-12-31", "2007-03-31", "2007-06-30", "2007-09-30"]
pre_idx = [qt(d) for d in PRE_CRISIS_DATES if qt(d) is not None]

# E_bank[t, n] already computed against GFC calibration (above)
E_pre = E_bank[np.array(pre_idx), :]      # (4, N)
E_mean_pre = E_pre.mean(axis=0)            # (N,) — mean pre-crisis E per bank

# Rank by score (descending = highest risk first)
rank_order = np.argsort(E_mean_pre)[::-1]

print()
hdr3 = (f"  {'Rank':<5} {'Bank':<30} {'E_mean':<9} {'Z_score':<9} "
        f"{'Score_rank':<12} {'Known_vuln':>10}  Concordant?")
print(hdr3)
print("  " + "-" * (len(hdr3)))

# Z-score of institution ranking (across all banks)
mu_inst  = E_mean_pre.mean()
std_inst = E_mean_pre.std() + 1e-10

rank_scores  = []
vuln_scores  = []

for rank, n in enumerate(rank_order, start=1):
    name   = BANK_NAMES[n]
    E_n    = float(E_mean_pre[n])
    Z_n    = (E_n - mu_inst) / std_inst
    vuln   = KNOWN_VULNERABILITY.get(name, 2)
    rank_scores.append(rank)
    vuln_scores.append(vuln)

    # Concordant: predicted risk rank ≤ 10 and known vulnerability ≥ 3
    # OR predicted risk rank > 10 and known vulnerability ≤ 2
    predicted_high = rank <= 10
    actually_high  = vuln >= 3
    concordant = (predicted_high == actually_high)
    c_str = "✓" if concordant else "✗"

    vuln_str = "●" * vuln + "○" * (5 - vuln)
    print(f"  {rank:<5} {name:<30} {E_n:8.4f}  {Z_n:+7.3f}  "
          f"rank={rank:2d}/20  {vuln_str}  {c_str}")

# Rank correlation (Spearman) between predicted rank and known vulnerability
from scipy.stats import spearmanr
# Note: higher rank = less risky in our ordering; higher vuln = more risky.
# So we negate rank_scores to align direction.
neg_ranks = [-r for r in rank_scores]
rho, p_val = spearmanr(neg_ranks, vuln_scores)

n_concordant = sum(
    1 for rank, n in enumerate(rank_order, start=1)
    if (rank <= 10) == (KNOWN_VULNERABILITY.get(BANK_NAMES[n], 2) >= 3)
)

print()
print(f"  Spearman ρ (score_rank vs known_vulnerability) = {rho:+.3f}  "
      f"(p={p_val:.3f})")
print(f"  Concordance: {n_concordant}/{N} banks correctly classified (high/low risk)")

if rho > 0.3 and p_val < 0.1:
    cv3_verdict = "RANKING CONFIRMED ✓ (positive correlation, p<0.10)"
elif rho > 0.2:
    cv3_verdict = "RANKING MARGINAL ~ (weak positive correlation)"
else:
    cv3_verdict = "RANKING NOT CONFIRMED ✗"
print(f"  Verdict: {cv3_verdict}")

# ═══════════════════════════════════════════════════════════════════════════
#  FINAL SUMMARY TABLE
# ═══════════════════════════════════════════════════════════════════════════

print()
print("=" * 72)
print("  RETROSPECTIVE VALIDATION — FINAL SUMMARY")
print("=" * 72)
print()
print("  Test                           | Key Result                    | Verdict")
print("  -------------------------------|-------------------------------|----------------")

# CV1 summary
gfc_milestones = [r for r in cv1_rows if r["milestone"] in
    {"BNP MMF freeze","Bear Stearns rescue","Lehman collapse",
     "WaMu/Wachovia","TARP enacted","Stress test peak"}]
n_gfc_above = sum(1 for r in gfc_milestones if r["above_2s"])
lead_vals = [r["lead_q"] for r in gfc_milestones if r["lead_q"]]
max_lead  = max(lead_vals) if lead_vals else 0
if n_gfc_above >= 4:
    cv1_verdict = "CHRONOLOGY CONFIRMED ✓"
elif n_gfc_above >= 2:
    cv1_verdict = "CHRONOLOGY MARGINAL ~"
else:
    cv1_verdict = "CHRONOLOGY WEAK ✗"

print(f"  CV1  Crisis Chronology         | {n_gfc_above}/6 GFC milestones ≥2σ,"
      f" max lead={max_lead}q | {cv1_verdict}")
print(f"  CV2a GFC OOS (calib to 2007Q3) | hit={cv2a['hit_2s']:.2f},"
      f" FA={cv2a['far_2s']:.2f}, "
      f"lead={cv2a['lead_q'] or 0}q       | {cv2a['verdict']}")
print(f"  CV2b COVID OOS (calib to 2013) | hit={cv2b['hit_2s']:.2f},"
      f" FA={cv2b['far_2s']:.2f}, "
      f"lead={cv2b['lead_q'] or 0}q       | {cv2b['verdict']}")
print(f"  CV3  Institution Ranking       | Spearman ρ={rho:+.3f}, p={p_val:.3f},"
      f" concordance={n_concordant}/20  | {cv3_verdict}")

print()
all_ok = (
    (n_gfc_above >= 4) and
    (cv2a["hit_2s"] >= 0.5 and cv2a["far_2s"] < 0.3) and
    (cv2b["hit_2s"] >= 0.5 and cv2b["far_2s"] < 0.3) and
    (rho > 0.3)
)
print("  Overall retrospective verdict:",
      "ACTIONABLE SIGNAL (3/4 CVs confirmed)" if sum([
          n_gfc_above >= 4,
          cv2a["hit_2s"] >= 0.5 and cv2a["far_2s"] < 0.3,
          cv2b["hit_2s"] >= 0.5 and cv2b["far_2s"] < 0.3,
          rho > 0.3,
      ]) >= 3 else "MIXED EVIDENCE (further data needed)")

print()
print("  What this means:")
print("    - CV1 tests whether the signal preceded INDEPENDENT dated milestones")
print("    - CV2 tests whether calibration generalises to UNSEEN future crises")
print("    - CV3 tests whether the RANKING of institutions matches realised losses")
print("    - Together these are much stronger than a single AUROC number")
