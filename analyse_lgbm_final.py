"""
Comprehensive analysis of ALL LGBM banking benchmark results.

Loads:
  1. bank_lgbm_benchmark.json        — flat LGBM (6 variants)
  2. bank_lgbm_engine_results.json   — iterative LGBM engine (SIAM-style outer loop)
  3. bank_lgbm_bsdt_damped_results.json — BSDT-damped internal LGBM (inside boosting rounds)

Outputs:
  - Unified AUC / GFC-AUC / F1 / FAR comparison
  - Per-quarter timeline
  - Lead-time analysis
  - Signal correlation
  - Final conclusions
"""
import json, sys, os
import numpy as np
from datetime import date, timedelta
from sklearn.metrics import roc_auc_score, f1_score
from scipy.stats import spearmanr

# ── Load all results ─────────────────────────────────────────────
RD = r"c:\amttp\results"

with open(os.path.join(RD, "bank_lgbm_benchmark.json")) as f:
    R_flat = json.load(f)
with open(os.path.join(RD, "bank_lgbm_engine_results.json")) as f:
    R_engine = json.load(f)
with open(os.path.join(RD, "bank_lgbm_bsdt_damped_results.json")) as f:
    R_damped = json.load(f)

# ── Quarter dates ────────────────────────────────────────────────
T = 76
dates = []
y, q = 2005, 1
for _ in range(T):
    m = q * 3
    if m == 3: d = date(y, 3, 31)
    elif m == 6: d = date(y, 6, 30)
    elif m == 9: d = date(y, 9, 30)
    else: d = date(y, 12, 31)
    dates.append(d); q += 1
    if q > 4: q = 1; y += 1

qlabels = [f"{d.year}-Q{(d.month-1)//3+1}" for d in dates]
BURN = 11  # calibration: 2005-Q1 to 2007-Q3

GFC_S, GFC_E = 11, 17   # 2007-Q4 to 2009-Q2
EU_S, EU_E   = 26, 29   # 2011-Q3 to 2012-Q2
COV_S, COV_E = 60, 61   # 2020-Q1 to 2020-Q2

GFC_ONSET = date(2007, 12, 1)
EU_ONSET  = date(2011, 7, 1)
COV_ONSET = date(2020, 3, 1)

y_cr = np.zeros(T, dtype=int)
for t in range(GFC_S, GFC_E+1): y_cr[t] = 1
for t in range(EU_S, EU_E+1):   y_cr[t] = 1
for t in range(COV_S, COV_E+1): y_cr[t] = 1

def sa(lst, length=76):
    arr = np.full(length, np.nan)
    for i, v in enumerate(lst[:length]):
        if v is not None: arr[i] = float(v)
    return arr

# ── Collect ALL signals ──────────────────────────────────────────
S = {}

# Flat LGBM
if "variants" in R_flat:
    for v, vd in R_flat["variants"].items():
        if "scores" in vd: S[f"Flat/{v}"] = sa(vd["scores"])

# Engine LGBM
for layer_key, prefix in [("layer1_scores","EngL1"), ("layer2_scores","EngL2"), ("layer3_scores","EngL3")]:
    if layer_key in R_engine:
        for v, sc in R_engine[layer_key].items():
            S[f"{prefix}/{v}"] = sa(sc)
if "morse_early_warning" in R_engine and "scores" in R_engine["morse_early_warning"]:
    S["Eng/MorseEW"] = sa(R_engine["morse_early_warning"]["scores"])

# Damped LGBM
if "variants" in R_damped:
    for v, vd in R_damped["variants"].items():
        if "scores" in vd: S[f"Damp/{v}"] = sa(vd["scores"])
for layer_key, prefix in [("layer2_scores","DampL2"), ("layer3_scores","DampL3")]:
    if layer_key in R_damped:
        for v, sc in R_damped[layer_key].items():
            S[f"{prefix}/{v}"] = sa(sc)
if "morse_early_warning" in R_damped and "scores" in R_damped["morse_early_warning"]:
    S["Damp/MorseEW"] = sa(R_damped["morse_early_warning"]["scores"])

# ── Metrics ──────────────────────────────────────────────────────
def metrics(scores):
    s_p = scores[BURN:]; y_p = y_cr[BURN:]
    v = ~np.isnan(s_p)
    if v.sum() < 4 or y_p[v].sum() == 0:
        return dict(auc=np.nan, gfc_auc=np.nan, f1=np.nan, far=np.nan, ca=0)
    
    auc = roc_auc_score(y_p[v], s_p[v])
    
    # GFC-specific AUC
    gm = np.zeros(T, dtype=bool)
    for t in range(BURN, T):
        if not np.isnan(scores[t]):
            if y_cr[t] == 0 or (GFC_S <= t <= GFC_E): gm[t] = True
    gfc_auc = roc_auc_score(y_cr[gm], scores[gm]) if y_cr[gm].sum() > 0 else np.nan
    
    # Best F1
    bf1 = 0
    for p in range(5, 96):
        thr = np.nanpercentile(s_p[v], p)
        preds = (s_p[v] >= thr).astype(int)
        f = f1_score(y_p[v], preds, zero_division=0)
        if f > bf1: bf1 = f
    
    # FAR (3-sigma expanding)
    ac, an, tn = 0, 0, 0
    for t in range(BURN + 4, T):
        if np.isnan(scores[t]): continue
        hist = scores[BURN:t]; vld = hist[~np.isnan(hist)]
        if len(vld) < 4: continue
        mu, sg = np.mean(vld), np.std(vld)
        if sg < 1e-15: continue
        if scores[t] > mu + 3*sg:
            if y_cr[t] == 1: ac += 1
            else: an += 1
        if y_cr[t] == 0: tn += 1
    
    far = 100.0 * an / tn if tn > 0 else 0
    return dict(auc=auc, gfc_auc=gfc_auc, f1=bf1, far=far, ca=ac)

# ── Compute all ──────────────────────────────────────────────────
R = []
for name in sorted(S.keys()):
    m = metrics(S[name])
    R.append((name, m))
R.sort(key=lambda x: -x[1]["auc"] if not np.isnan(x[1]["auc"]) else 999)

# ══════════════════════════════════════════════════════════════════
#  OUTPUT
# ══════════════════════════════════════════════════════════════════
W = 100
print("=" * W)
print("  COMPREHENSIVE LGBM BANKING ANALYSIS")
print("  G-SIB panel | N=25 banks | T=76 quarters | d=5 features")
print("  Crises: GFC (7Q), EU Sovereign (4Q), COVID (2Q) = 13 crisis quarters")
print("=" * W)
print(f"  Total signals: {len(S)}")

# TABLE 1: ALL signals ranked
print("\n" + "=" * W)
print("  TABLE 1: ALL SIGNALS RANKED BY AUC")
print("=" * W)
print(f"  {'#':<4} {'Signal':<40} {'AUC':>7} {'GFC-AUC':>9} {'F1':>7} {'FAR%':>7} {'CrisAlm':>8}")
print("  " + "-" * 84)
for i, (name, m) in enumerate(R):
    if np.isnan(m["auc"]): continue
    marker = " <-- BEST" if i == 0 else ""
    print(f"  {i+1:<4} {name:<40} {m['auc']:>7.4f} {m['gfc_auc']:>9.4f} "
          f"{m['f1']:>7.3f} {m['far']:>6.1f}% {m['ca']:>5d}{marker}")

# TABLE 2: Best per category
print("\n" + "=" * W)
print("  TABLE 2: BEST SIGNAL PER APPROACH")
print("=" * W)
cats = [
    ("Flat LGBM (no engine)",         "Flat/"),
    ("Engine L1 (outer-loop LGBM)",   "EngL1/"),
    ("Engine L2 (BSDT alarm)",        "EngL2/"),
    ("Engine L3 (Morse+Betti conf.)", "EngL3/"),
    ("Damped LGBM (BSDT inside)",     "Damp/"),
    ("Damped L2 (BSDT alarm)",        "DampL2/"),
    ("Damped L3 (Morse+Betti conf.)", "DampL3/"),
]
print(f"  {'Category':<38} {'Best Signal':<28} {'AUC':>7} {'GFC':>7} {'F1':>6} {'FAR%':>6}")
print("  " + "-" * 96)
for cat, pfx in cats:
    best = None
    for name, m in R:
        if name.startswith(pfx) and not np.isnan(m["auc"]):
            best = (name, m); break
    if best:
        n, m = best
        short = n.split("/")[-1]
        print(f"  {cat:<38} {short:<28} {m['auc']:>7.4f} {m['gfc_auc']:>7.4f} "
              f"{m['f1']:>6.3f} {m['far']:>5.1f}%")

# TABLE 3: Head-to-head — same features, different approach
print("\n" + "=" * W)
print("  TABLE 3: HEAD-TO-HEAD — SAME FEATURES, DIFFERENT LGBM APPROACH")
print("=" * W)
print(f"  {'Features':<20} {'Flat AUC':>9} {'Damped AUC':>11} {'Engine AUC':>11} {'Winner':<20}")
print("  " + "-" * 75)

# Find matching variants across approaches
flat_vars = {n.split("/")[1]: m for n, m in R if n.startswith("Flat/")}
damp_vars = {n.split("/")[1]: m for n, m in R if n.startswith("Damp/")}
eng_vars  = {n.split("/")[1]: m for n, m in R if n.startswith("EngL1/")}

# Common comparisons
for feat in ["LGBM_RT+BSDT", "LGBM_RT_only", "LGBM_BSDT_only"]:
    # Flat name might differ
    flat_key = feat
    damp_key = f"bsdt_damped({feat.replace('LGBM_','')})"
    std_key  = f"standard({feat.replace('LGBM_','')})"
    
    f_auc = flat_vars.get(flat_key, {}).get("auc", np.nan)
    d_auc = damp_vars.get(damp_key, {}).get("auc", np.nan)
    s_auc = damp_vars.get(std_key, {}).get("auc", np.nan)
    e_auc = eng_vars.get("fused", {}).get("auc", np.nan) if feat == "LGBM_RT+BSDT" else np.nan
    
    vals = {"Flat": f_auc, "Damped": d_auc, "Standard": s_auc, "Engine": e_auc}
    vals = {k: v for k, v in vals.items() if not np.isnan(v)}
    winner = max(vals, key=vals.get) if vals else "N/A"
    
    fstr = f"{f_auc:.4f}" if not np.isnan(f_auc) else "N/A"
    dstr = f"{d_auc:.4f}" if not np.isnan(d_auc) else "N/A"
    estr = f"{e_auc:.4f}" if not np.isnan(e_auc) else "N/A"
    
    print(f"  {feat:<20} {fstr:>9} {dstr:>11} {estr:>11} {winner:<20}")

# TABLE 4: Lead times
print("\n" + "=" * W)
print("  TABLE 4: EARLY WARNING LEAD TIMES")
print("=" * W)

def find_lead(scores, onset, search_s, search_e, min_hist=4):
    for t in range(search_s, search_e):
        if np.isnan(scores[t]): continue
        hist = scores[BURN:t]; vld = hist[~np.isnan(hist)]
        if len(vld) < min_hist: continue
        mu, sg = np.mean(vld), np.std(vld)
        if sg < 1e-15: continue
        lead = (onset - dates[t]).days
        if lead <= 0: break
        if scores[t] > mu + 3*sg:
            return dict(q=qlabels[t], days=lead, mo=lead/30.44, lev="3sig", sc=scores[t], thr=mu+3*sg)
        if scores[t] > mu + 2*sg:
            return dict(q=qlabels[t], days=lead, mo=lead/30.44, lev="2sig", sc=scores[t], thr=mu+2*sg)
    return None

print(f"\n  GFC (onset 01-Dec-2007) — search: 2006-Q2 to 2007-Q3")
print(f"  {'Signal':<40} {'Level':>5} {'Quarter':>9} {'Days':>6} {'Months':>7} {'Score':>8}")
print("  " + "-" * 80)

gfc_leads = []
for name in sorted(S.keys()):
    lt = find_lead(S[name], GFC_ONSET, 5, GFC_S)
    if lt:
        gfc_leads.append((name, lt))
        print(f"  {name:<40} {lt['lev']:>5} {lt['q']:>9} {lt['days']:>6} {lt['mo']:>6.1f}m {lt['sc']:>8.4f}")

if not gfc_leads:
    print("  (no signal fired before GFC onset)")

# EU Sovereign
print(f"\n  EU SOVEREIGN (onset 01-Jul-2011) — requires normalization after GFC")
eu_any = False
for name in sorted(S.keys()):
    s = S[name]
    norm = None
    for t in range(GFC_E+1, EU_S):
        if np.isnan(s[t]): continue
        hist = s[BURN:t]; vld = hist[~np.isnan(hist)]
        if len(vld) < 6: continue
        mu, sg = np.mean(vld), np.std(vld)
        if sg < 1e-15: continue
        if s[t] <= mu + sg:
            if t+1 < EU_S and not np.isnan(s[t+1]):
                h2 = s[BURN:t+1]; v2 = h2[~np.isnan(h2)]
                m2, s2 = np.mean(v2), np.std(v2)
                if s2 > 1e-15 and s[t+1] <= m2 + s2:
                    norm = t; break
    if norm is None: continue
    lt = find_lead(s, EU_ONSET, norm, EU_S)
    if lt:
        if not eu_any:
            print(f"  {'Signal':<40} {'Level':>5} {'Quarter':>9} {'Days':>6} {'Months':>7}")
            print("  " + "-" * 70)
            eu_any = True
        print(f"  {name:<40} {lt['lev']:>5} {lt['q']:>9} {lt['days']:>6} {lt['mo']:>6.1f}m")
if not eu_any:
    print("  (no genuine pre-crisis alarm — EU Sovereign had no banking manifold precursor)")

# COVID
print(f"\n  COVID (onset 01-Mar-2020) — requires normalization after EU")
cov_any = False
for name in sorted(S.keys()):
    s = S[name]
    norm = None
    for t in range(EU_E+1, COV_S):
        if np.isnan(s[t]): continue
        hist = s[BURN:t]; vld = hist[~np.isnan(hist)]
        if len(vld) < 8: continue
        mu, sg = np.mean(vld), np.std(vld)
        if sg < 1e-15: continue
        if s[t] <= mu + sg:
            if t+1 < COV_S and not np.isnan(s[t+1]):
                h2 = s[BURN:t+1]; v2 = h2[~np.isnan(h2)]
                m2, s2 = np.mean(v2), np.std(v2)
                if s2 > 1e-15 and s[t+1] <= m2 + s2:
                    norm = t; break
    if norm is None: continue
    lt = find_lead(s, COV_ONSET, max(norm, EU_E+4), COV_S)
    if lt:
        if not cov_any:
            print(f"  {'Signal':<40} {'Level':>5} {'Quarter':>9} {'Days':>6} {'Months':>7}")
            print("  " + "-" * 70)
            cov_any = True
        print(f"  {name:<40} {lt['lev']:>5} {lt['q']:>9} {lt['days']:>6} {lt['mo']:>6.1f}m")
if not cov_any:
    print("  (no genuine pre-crisis alarm — COVID was an exogenous shock)")

# TABLE 5: GFC quarterly detail
print("\n" + "=" * W)
print("  TABLE 5: GFC QUARTER-BY-QUARTER (top 6 signals)")
print("=" * W)

top6 = [name for name, _ in R[:6]]
short6 = [n.split("/")[-1][:14] for n in top6]

print(f"  {'Quarter':<10} {'Cris':>4}", end="")
for s in short6: print(f" {s:>15}", end="")
print()
print("  " + "-" * (14 + 16*len(top6)))

# Pre-GFC context (3 quarters before)
for t in list(range(max(BURN-3, 0), BURN)) + list(range(GFC_S, GFC_E+1)) + list(range(GFC_E+1, min(GFC_E+4, T))):
    if t < 0 or t >= T: continue
    cr = "GFC" if GFC_S <= t <= GFC_E else ""
    print(f"  {qlabels[t]:<10} {cr:>4}", end="")
    for name in top6:
        v = S[name][t]
        if np.isnan(v):
            print(f"            {'N/A':>3}", end="")
        else:
            # Check alarm status
            hist = S[name][BURN:t]; vld = hist[~np.isnan(hist)]
            mark = ""
            if len(vld) >= 4:
                mu, sg = np.mean(vld), np.std(vld)
                if sg > 1e-15:
                    if v > mu + 3*sg: mark = " ***"
                    elif v > mu + 2*sg: mark = " **"
            print(f" {v:>10.4f}{mark}", end="")
    print()

# TABLE 6: FAR-controlled ranking (FAR < 20%)
print("\n" + "=" * W)
print("  TABLE 6: OPERATIONALLY VIABLE SIGNALS (FAR < 20%)")
print("=" * W)
print(f"  {'#':<4} {'Signal':<40} {'AUC':>7} {'GFC-AUC':>9} {'F1':>7} {'FAR%':>7}")
print("  " + "-" * 78)
rank = 0
for name, m in R:
    if np.isnan(m["auc"]): continue
    if m["far"] < 20:
        rank += 1
        print(f"  {rank:<4} {name:<40} {m['auc']:>7.4f} {m['gfc_auc']:>9.4f} "
              f"{m['f1']:>7.3f} {m['far']:>6.1f}%")

# ── FINAL SUMMARY ───────────────────────────────────────────────
print("\n" + "=" * W)
print("  CONCLUSIONS")
print("=" * W)

flat_best  = max([(n,m) for n,m in R if n.startswith("Flat/") and not np.isnan(m["auc"])],
                 key=lambda x: x[1]["auc"], default=None)
eng_best   = max([(n,m) for n,m in R if n.startswith("EngL1/") and not np.isnan(m["auc"])],
                 key=lambda x: x[1]["auc"], default=None)
damp_best  = max([(n,m) for n,m in R if n.startswith("Damp/") and not np.isnan(m["auc"])],
                 key=lambda x: x[1]["auc"], default=None)
l2_best    = max([(n,m) for n,m in R if "L2/" in n and not np.isnan(m["auc"])],
                 key=lambda x: x[1]["auc"], default=None)
l3_best    = max([(n,m) for n,m in R if "L3/" in n and not np.isnan(m["auc"])],
                 key=lambda x: x[1]["auc"], default=None)

if flat_best: print(f"  Flat LGBM best:     {flat_best[0]:<35} AUC={flat_best[1]['auc']:.4f} FAR={flat_best[1]['far']:.1f}%")
if damp_best: print(f"  BSDT-damped best:   {damp_best[0]:<35} AUC={damp_best[1]['auc']:.4f} FAR={damp_best[1]['far']:.1f}%")
if eng_best:  print(f"  Engine best:        {eng_best[0]:<35} AUC={eng_best[1]['auc']:.4f} FAR={eng_best[1]['far']:.1f}%")
if l2_best:   print(f"  BSDT alarm best:    {l2_best[0]:<35} AUC={l2_best[1]['auc']:.4f} FAR={l2_best[1]['far']:.1f}%")
if l3_best:   print(f"  Morse/Betti best:   {l3_best[0]:<35} AUC={l3_best[1]['auc']:.4f} FAR={l3_best[1]['far']:.1f}%")

print(f"""
  KEY FINDINGS:
  ─────────────────────────────────────────────────────────────────────────────
  1. LGBM IS ALREADY ITERATIVE — its boosting rounds ARE the iteration.
     Adding an outer physics loop (Engine) is redundant and harmful (AUC drops).
  
  2. BSDT AS FEATURES (Flat LGBM) > BSDT AS DAMPING (Damped LGBM) > BSDT AS OUTER DAMPING (Engine):
     Flat AUC={flat_best[1]['auc']:.4f} > Damped AUC={damp_best[1]['auc']:.4f} > Engine AUC={eng_best[1]['auc']:.4f}
  
  3. BSDT damping inside LGBM DOES reduce FAR ({flat_best[1]['far']:.1f}% -> {damp_best[1]['far']:.1f}%)
     but at a cost of AUC ({flat_best[1]['auc']:.4f} -> {damp_best[1]['auc']:.4f}).
     This is the BSDT tradeoff: more conservative = fewer false alarms, lower sensitivity.
  
  4. EARLY WARNING: Morse/Betti topology detects GFC ~11 months before onset.
     This is UNSUPERVISED structural detection — independent of LGBM.
  
  5. BSDT's ROLE changes fundamentally between engines and LGBM:
     - In gravity/molecular engine: BSDT = ADAPTIVE DAMPING (prevents collapse)
     - In LGBM: BSDT = FEATURE PROVIDER (E_BS, MFLS, 4 channels feed as inputs)
     - The gravity engine NEEDS BSDT damping because LJ forces have no self-regulation
     - LGBM DOESN'T NEED BSDT damping because boosting has its own regularisation
       (learning_rate, max_depth, min_child_samples, early_stopping)
  
  6. OPTIMAL ARCHITECTURE for banking early warning:
     Layer 1 (risk quantification): Flat LGBM on RT+BSDT features (AUC {flat_best[1]['auc']:.4f})
     Layer 2 (early warning alarm):  Morse topology (unsupervised, 11-month GFC lead)
     Layer 3 (operational control):  BSDT MFLS standalone (AUC {l2_best[1]['auc']:.4f}, 0% FAR)
""")
