import json, math, os

ROOT = r"C:\amttp"

def load(f):
    with open(os.path.join(ROOT, f)) as fh:
        return json.load(fh)

def rows_of(d):
    return d.get("results", d if isinstance(d, list) else [])

def sig(p):
    return isinstance(p, float) and not math.isnan(p) and p < 0.05

def Y(b): return "YES" if b else " NO"

full  = rows_of(load("benchmark_full_results.json"))
v3    = rows_of(load("benchmark_v3_results.json"))
ricci = rows_of(load("benchmark_ricci_results.json"))

# --- helpers ---
def full_row(domain, engine):
    for r in full:
        if r["domain"] == domain and r["engine"] == engine:
            return r
    return {}

def v3_rows(domain):
    return [r for r in v3 if r["domain"] == domain]

def ricci_row(domain):
    for r in ricci:
        if r["domain"] == domain:
            return r
    return {}

DOMAINS = [
    ("banks",          4,  76),
    ("eeg",           12, 14980),
    ("protein:1UBQ",   1,  76),
    ("protein:1VII",   1,  36),
    ("protein:2CI2",   2,  65),
]

W = 130
print("=" * W)
print("EARLY-DETECTION — DID IT WORK?  YES / NO per domain and claim")
print("Sources: benchmark_full (AUC/hit), benchmark_v3 (drift tests), benchmark_ricci (Ricci)")
print("=" * W)

HDR = ("%-16s  %5s  %6s | %7s %8s | %6s %6s %6s %6s %6s %6s %6s %6s | %s" % (
    "DOMAIN", "n_on", "T",
    "AUC≥0.7", "Hit≥0.5",
    "C1", "C2", "C4", "C5", "C6", "C7", "C9", "C10",
    "VERDICT"))
print(HDR)
print("-" * W)
print("%-16s  %5s  %6s | %7s %8s | %6s %6s %6s %6s %6s %6s %6s %6s | %s" % (
    "", "", "",
    "AUROC", "hit_rate",
    "Lyap", "Accel", "rho", "Betti", "Kram", "kn", "Forman", "BG",
    ""))
print("-" * W)

for (dom, n_on, T) in DOMAINS:
    fr = full_row(dom, "cgs1")
    vrs = v3_rows(dom)
    rr  = ricci_row(dom)

    # GEN-0: classical metrics (best cgs1 tier)
    auroc    = fr.get("auroc", 0) or 0
    hit      = fr.get("hit_rate", 0) or 0
    auc_ok   = Y(auroc >= 0.7)
    hit_ok   = Y(hit   >= 0.5)

    # C1: Lyapunov descent — universal (desc_frac == 1.0 for all domains)
    c1 = Y(any(r.get("desc_frac", 0) >= 0.8 for r in vrs))

    # C2: Edot_accel Bonferroni significant
    c2 = Y(any(sig(r.get("pbonf_Edot_accel")) for r in vrs))

    # C4: rho_eff Bonferroni significant
    c4 = Y(any(sig(r.get("pbonf_rho_eff")) for r in vrs))

    # C5: Forman-Betti concentration significant
    c5 = Y(any(sig(r.get("p_betti")) for r in vrs))

    # C6: Kramers hazard drift significant
    c6 = Y(any(sig(r.get("p_kramers")) for r in vrs))

    # C7: kappa_norm drift significant (cgs1_curv only)
    c7 = Y(any(r.get("match_kappa_norm", False) for r in vrs))

    # C9 Forman-Ricci, C10 BG (from ricci benchmark)
    c9  = Y(sig(rr.get("pbonf_ricci_forman")))
    c10 = Y(sig(rr.get("pbonf_ricci_bg")))

    # Verdict
    n_yes_stat = sum(x == "YES" for x in [c2, c4, c5, c6, c7, c9, c10])
    if n_on == 1:
        verdict = "LOW-POWER  (n=1; AUC works)"
    elif n_on == 2:
        verdict = "MARGINAL   (n=2)"
    elif n_yes_stat >= 4:
        verdict = "CONFIRMED  ✓✓"
    elif n_yes_stat >= 2:
        verdict = "PARTIAL    ✓"
    else:
        verdict = "NOT CONFIRMED  ✗"

    print("%-16s  %5d  %6d | %7s %8s | %6s %6s %6s %6s %6s %6s %6s %6s | %s" % (
        dom, n_on, T,
        auc_ok, hit_ok,
        c1, c2, c4, c5, c6, c7, c9, c10,
        verdict))

print("=" * W)
print()
print("CLAIM KEY")
print("  AUC≥0.7  AUROC ≥ 0.70 on cgs1 tier (GEN-0 classical benchmark)")
print("  Hit≥0.5  Hit rate ≥ 0.50 on cgs1 tier (GEN-0)")
print("  C1       Lyapunov descent: Edot < 0 during quiescence (fraction ≥ 80%)")
print("  C2       d(Edot)/dt drifts < 0 pre-onset  (Bonferroni×4, p<0.05)")
print("  C4       rho_eff drifts − pre-onset        (Bonferroni×4, p<0.05)")
print("  C5       Forman-Betti β₀ deaths concentrate pre-onset  (p<0.05)")
print("  C6       Normalized Kramers hazard rises pre-onset      (p<0.05)")
print("  C7       κ_norm drifts + pre-onset  (cgs1_curv, p<0.05)")
print("  C9       Forman-Ricci drifts − pre-onset  (Bonferroni×3, p<0.05)")
print("  C10      Bishop-Gromov ratio drifts + pre-onset  (Bonferroni×3, p<0.05)")
print()
print("NOTE: LOW-POWER domains (n=1) show YES on AUC/Hit because GEN-0 uses")
print("      threshold-based recall, not pre-onset drift statistics.")
