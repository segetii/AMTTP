"""
Build comprehensive early-detection results table across all benchmark generations.
Prints a structured text table to stdout.
"""
import json, os, math

ROOT = r"C:\amttp"

# ── Load all benchmark files ──────────────────────────────────────────────
def load(fname):
    with open(os.path.join(ROOT, fname)) as fh:
        return json.load(fh)

prod    = load("benchmark_production_results.json")
full    = load("benchmark_full_results.json")
dyn     = load("benchmark_dynamical_results.json")
curv    = load("benchmark_curv_results.json")
ricci   = load("benchmark_ricci_results.json")
v2      = load("benchmark_v2_results.json")
v3      = load("benchmark_v3_results.json")

def rows_of(d):
    r = d.get("results", d if isinstance(d, list) else [])
    return r

# ── Helper: is p significant ──────────────────────────────────────────────
def sig(p, threshold=0.05):
    if p is None or (isinstance(p, float) and math.isnan(p)):
        return False
    return float(p) < threshold

def fmt_p(p):
    if p is None or (isinstance(p, float) and math.isnan(p)):
        return "   n/a  "
    return ("%6.4f%s" % (p, "*" if sig(p) else " "))

def yesno(b):
    return "YES" if b else " no"

# ── 1. FULL benchmark (AUC / hit-rate style) ─────────────────────────────
print()
print("=" * 110)
print("GEN-0  benchmark_full  (classical precision/recall metrics, 2026-06-01)")
print("=" * 110)
hdr = "%-16s %-13s %7s %8s %8s %10s %8s" % (
    "domain", "engine", "AUROC", "hit_rate", "FAR", "lead(smp)", "betti_pk")
print(hdr)
print("-" * 110)
for r in rows_of(full):
    auroc = r.get("auroc")
    hr    = r.get("hit_rate")
    far   = r.get("far")
    lead  = r.get("lead_time")
    bp    = r.get("betti_peak")
    print("%-16s %-13s %7s %8s %8s %10s %8s" % (
        r["domain"], r["engine"],
        "%.3f" % auroc if auroc is not None else "  n/a",
        "%.3f" % hr    if hr    is not None else "  n/a",
        "%.3f" % far   if far   is not None else "  n/a",
        str(lead)      if lead  is not None else "  n/a",
        str(bp)        if bp    is not None else "  n/a",
    ))

# ── 2. DYNAMICAL benchmark ────────────────────────────────────────────────
print()
print("=" * 110)
print("GEN-1  benchmark_dynamical  (C1-C4 geometry drift pre-onset, 2026-06-01)")
print("Tiers: v4 / cgs1 / cgs1_stoch / cgs1_morse / cgs1_curv")
print("=" * 110)
hdr = "%-16s %-14s %5s %9s %9s %9s %9s %5s" % (
    "domain", "engine", "n_on", "pEdot", "pCos", "pGam", "pRho", "C4ok")
print(hdr)
print("-" * 110)
for r in rows_of(dyn):
    n_on = r.get("n_onsets", "?")
    pE   = r.get("pbonf_Edot")
    pC   = r.get("pbonf_cos_theta")
    pG   = r.get("pbonf_gamma")
    pR   = r.get("pbonf_rho_eff")
    c4ok = sum(bool(r.get("match_" + k, False))
               for k in ("Edot", "cos_theta", "gamma", "rho_eff"))
    print("%-16s %-14s %5s %9s %9s %9s %9s %5d" % (
        r["domain"], r["engine"], str(n_on),
        fmt_p(pE), fmt_p(pC), fmt_p(pG), fmt_p(pR), c4ok))

# ── 3. CURV benchmark ─────────────────────────────────────────────────────
print()
print("=" * 110)
print("GEN-2  benchmark_curv  (+ C7 kappa_norm §67 curvature, 2026-06-02)")
print("Tiers: v4 / cgs1 / cgs1_stoch / cgs1_morse / cgs1_curv")
print("=" * 110)
hdr = "%-16s %-14s %5s %9s %9s %5s %9s" % (
    "domain", "engine", "n_on", "pRho", "pKn", "C4ok", "kn_drift")
print(hdr)
print("-" * 110)
for r in rows_of(curv):
    n_on = r.get("n_onsets", "?")
    pR   = r.get("pbonf_rho_eff")
    pkn  = r.get("p_kappa_norm")
    c4ok = sum(bool(r.get("match_" + k, False))
               for k in ("Edot", "cos_theta", "gamma", "rho_eff"))
    knd  = r.get("kappa_norm_drift")
    knd_str = ("%+.3f" % knd) if knd is not None else "  n/a"
    print("%-16s %-14s %5s %9s %9s %5d %9s" % (
        r["domain"], r["engine"], str(n_on),
        fmt_p(pR), fmt_p(pkn), c4ok, knd_str))

# ── 4. RICCI benchmark ────────────────────────────────────────────────────
print()
print("=" * 110)
print("GEN-3  benchmark_ricci  (+ C8-C10 manifold curvature, 2026-06-02)")
print("Tiers: v4 / cgs1 / cgs1_stoch / cgs1_morse / cgs1_curv")
print("=" * 110)
hdr = "%-16s %-14s %5s %9s %9s %9s %5s" % (
    "domain", "engine", "n_on", "pOlliv", "pForman", "pBG", "nRicci")
print(hdr)
print("-" * 110)
seen = set()
for r in rows_of(ricci):
    dom = r["domain"]
    if dom in seen:
        continue
    seen.add(dom)
    n_on = r.get("n_onsets", "?")
    po   = r.get("pbonf_ricci_ollivier")
    pf   = r.get("pbonf_ricci_forman")
    pb   = r.get("pbonf_ricci_bg")
    nr   = sum(bool(r.get("match_ricci_" + k, False))
               for k in ("ollivier", "forman", "bg"))
    print("%-16s %-14s %5s %9s %9s %9s %5d" % (
        dom, "(all tiers)", str(n_on),
        fmt_p(po), fmt_p(pf), fmt_p(pb), nr))

# ── 5. V2 benchmark ───────────────────────────────────────────────────────
print()
print("=" * 110)
print("GEN-4  benchmark_v2  (C2=accel, C3=retired, C5=Betti, C6=norm-Kramers, 2026-06-02)")
print("Tiers: v4 / cgs1 / cgs1_stoch / cgs1_curv")
print("=" * 110)
hdr = "%-16s %-14s %5s %9s %9s %9s %9s %5s %9s %9s" % (
    "domain", "engine", "n_on", "pAccel", "pRho", "pBetti", "pKram", "C4ok", "kn_drift", "pKn")
print(hdr)
print("-" * 110)
for r in rows_of(v2):
    n_on = r.get("n_onsets", "?")
    pAc  = r.get("pbonf_Edot_accel")
    pR   = r.get("pbonf_rho_eff")
    pBt  = r.get("p_betti")
    pKr  = r.get("p_kramers")
    c4ok = sum(bool(r.get("match_" + k, False))
               for k in ("Edot_accel", "cos_theta", "gamma", "rho_eff"))
    knd  = r.get("kappa_norm_drift")
    pkn  = r.get("p_kappa_norm")
    knd_str = ("%+.3f" % knd) if knd is not None else "     -"
    print("%-16s %-14s %5s %9s %9s %9s %9s %5d %9s %9s" % (
        r["domain"], r["engine"], str(n_on),
        fmt_p(pAc), fmt_p(pR), fmt_p(pBt), fmt_p(pKr), c4ok,
        knd_str, fmt_p(pkn)))

# ── 6. V3 benchmark ───────────────────────────────────────────────────────
print()
print("=" * 110)
print("GEN-5  benchmark_v3  (C5=persistence-filter, C6=sigma_n fixed, 2026-06-02) ← LATEST")
print("Tiers: v4 / cgs1 / cgs1_stoch / cgs1_curv")
print("=" * 110)
hdr = "%-16s %-14s %5s %9s %9s %9s %9s %5s %9s %9s" % (
    "domain", "engine", "n_on", "pAccel", "pRho", "pBetti", "pKram", "C4ok", "kn_drift", "pKn")
print(hdr)
print("-" * 110)
for r in rows_of(v3):
    n_on = r.get("n_onsets", "?")
    pAc  = r.get("pbonf_Edot_accel")
    pR   = r.get("pbonf_rho_eff")
    pBt  = r.get("p_betti")
    pKr  = r.get("p_kramers")
    c4ok = sum(bool(r.get("match_" + k, False))
               for k in ("Edot_accel", "cos_theta", "gamma", "rho_eff"))
    knd  = r.get("kappa_norm_drift")
    pkn  = r.get("p_kappa_norm")
    knd_str = ("%+.3f" % knd) if knd is not None else "     -"
    print("%-16s %-14s %5s %9s %9s %9s %9s %5d %9s %9s" % (
        r["domain"], r["engine"], str(n_on),
        fmt_p(pAc), fmt_p(pR), fmt_p(pBt), fmt_p(pKr), c4ok,
        knd_str, fmt_p(pkn)))

# ── 7. SUMMARY TABLE — one row per domain ────────────────────────────────
print()
print("=" * 110)
print("DOMAIN SUMMARY — does early detection work? (v3 final, best tier per domain)")
print("=" * 110)
print("%-17s %5s %6s  %-9s  %-9s  %-9s  %-9s  %-9s  %-8s  %-8s  %-8s  %-8s" % (
    "domain", "n_on", "T",
    "C1-desc", "C2-accel", "C4-rho", "C5-betti", "C6-kram",
    "C7-kn", "C9-Forman", "C10-BG", "VERDICT"))
print("-" * 110)

# For each domain pick any row (domain-level signals same across tiers for Ricci/Betti)
# but tier-specific for C2/C4/C6/C7 — use best tier
rows_v3 = rows_of(v3)
rows_r  = rows_of(ricci)

domain_order = ["banks", "eeg", "protein:1UBQ", "protein:1VII", "protein:2CI2"]

def best_v3(domain):
    candidates = [r for r in rows_v3 if r["domain"] == domain]
    if not candidates:
        return None
    # Pick row with most matches
    def score(r):
        s = 0
        for k in ("Edot_accel","cos_theta","gamma","rho_eff"):
            if r.get("match_"+k): s += 1
        if r.get("match_kappa_norm"): s += 1
        if sig(r.get("p_kramers")): s += 1
        if sig(r.get("p_betti")): s += 1
        return s
    return max(candidates, key=score)

def best_ricci(domain):
    candidates = [r for r in rows_r if r["domain"] == domain]
    if not candidates:
        return None
    return candidates[0]

for dom in domain_order:
    r3 = best_v3(dom)
    rr = best_ricci(dom)
    if r3 is None:
        continue

    n_on = r3.get("n_onsets", "?")
    T    = r3.get("T", "?")

    c1  = yesno(r3.get("desc_frac", 0) >= 0.8)
    c2  = yesno(sig(r3.get("pbonf_Edot_accel")))
    c4  = yesno(sig(r3.get("pbonf_rho_eff")))
    c5  = yesno(sig(r3.get("p_betti")))
    c6  = yesno(sig(r3.get("p_kramers")))
    c7  = yesno(r3.get("match_kappa_norm", False))

    pof = "n/a" if rr is None else fmt_p(rr.get("pbonf_ricci_forman")).strip()
    pob = "n/a" if rr is None else fmt_p(rr.get("pbonf_ricci_bg")).strip()

    # Verdict
    n_yes = sum([c2=="YES", c4=="YES", c5=="YES", c6=="YES", c7=="YES",
                 sig(None if rr is None else rr.get("pbonf_ricci_forman")),
                 sig(None if rr is None else rr.get("pbonf_ricci_bg"))])
    if   n_on == 1:   verdict = "LOW-POWER (n=1)"
    elif n_on == 2:   verdict = "MARGINAL  (n=2)"
    elif n_yes >= 4:  verdict = "WORKS  ✓✓"
    elif n_yes >= 2:  verdict = "PARTIAL ✓"
    else:             verdict = "FAILS   ✗"

    print("%-17s %5s %6s  %-9s  %-9s  %-9s  %-9s  %-9s  %-8s  %-8s  %-8s  %-8s" % (
        dom, str(n_on), str(T),
        c1, c2, c4, c5, c6, c7, pof, pob, verdict))

print()
print("* p<0.05 (Bonferroni-corrected where applicable)")
print("C1=Lyapunov descent  C2=Edot_accel  C4=rho_eff  C5=Forman-Betti  C6=Kramers  C7=kappa_norm")
print("C9=Forman-Ricci  C10=BG-ratio  (C9/C10 from benchmark_ricci, best tier)")
print("=" * 110)
