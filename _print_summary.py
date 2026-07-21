import json

d = json.load(open('all_engines_all_domains_results.json'))
dm = json.load(open('post_sim_physics_results.json'))

print("=" * 70)
print("  COMPLETE RESULTS: Lead Time / Hit Rate / False Alarm Rate")
print("=" * 70)

domain_units = {
    "A: G-SIB Banking":   "quarters",
    "B: FDIC US Banks":   "quarters",
    "C: ERCOT Grid":      "days",
    "D: Protein Folding": "MD frames",
    "E: CHB-MIT EEG":     "seconds",
}

# ── TABLE 1: Best engine per domain ──────────────────────────────────
print()
print("TABLE 1 — Best Engine per Domain")
print(f"  {'Domain':<22} {'Engine':<14} {'Lead':>6} {'Hit':>4} {'FA/100':>7} {'Disc×':>7}  unit")
print("  " + "─" * 68)
for dom, results in d['results'].items():
    valid = [r for r in results if 'error' not in r]
    hits  = [r for r in valid if r.get('hit')]
    pool  = hits if hits else valid
    if not pool:
        continue
    best = max(pool, key=lambda r: r.get('lead', 0))
    unit = domain_units.get(dom, '?')
    lead_s = str(best.get('lead',0)) + ('*' if best.get('hit') else '')
    print(f"  {dom:<22} {best['engine']:<14} {lead_s:>6} "
          f"{'YES' if best.get('hit') else 'no':>4} "
          f"{best.get('fa_rate',0):>7.2f} "
          f"{best.get('disc_ratio',1):>7.3f}  {unit}")

# ── TABLE 2: All 8 engines × 5 domains ──────────────────────────────
print()
print("TABLE 2 — All 8 Engines × 5 Domains  (lead, * = alarm fired)")
domains = list(d['results'].keys())
engines = []
for dom in domains:
    for r in d['results'][dom]:
        if 'error' not in r and r.get('engine') and r['engine'] not in engines:
            engines.append(r['engine'])

short = {
    "A: G-SIB Banking":   "Banking(q)",
    "B: FDIC US Banks":   "FDIC(q)",
    "C: ERCOT Grid":      "ERCOT(d)",
    "D: Protein Folding": "Protein(f)",
    "E: CHB-MIT EEG":     "EEG(s)",
}
cw = 11
print(f"  {'Engine':<14}" + "".join(f" {short[d_]:>{cw}}" for d_ in domains))
print("  " + "─" * (14 + (cw+1)*len(domains)))
for eng in engines:
    row = f"  {eng:<14}"
    for dom in domains:
        rec = next((r for r in d['results'][dom] if r.get('engine') == eng), None)
        if rec is None or 'error' in rec:
            cell = "-"
        else:
            lead = rec.get('lead', 0)
            mark = "*" if rec.get('hit') else ""
            cell = f"{lead}{mark}"
        row += f" {cell:>{cw}}"
    print(row)

# ── TABLE 3: Hit rate across engines ─────────────────────────────────
print()
print("TABLE 3 — Hit Rate per Domain  (out of 8 engines)")
print(f"  {'Domain':<22} {'Hits/8':>7} {'Min lead':>9} {'Max lead':>9} {'Mean lead':>10}  unit")
print("  " + "─" * 65)
for dom in domains:
    results = d['results'][dom]
    valid = [r for r in results if 'error' not in r]
    hits  = [r for r in valid if r.get('hit')]
    leads = [r.get('lead',0) for r in hits]
    unit  = domain_units.get(dom, '?')
    if leads:
        print(f"  {dom:<22} {len(hits):>7}   {min(leads):>9}   {max(leads):>9}   {sum(leads)/len(leads):>10.0f}  {unit}")
    else:
        print(f"  {dom:<22} {0:>7}   {'—':>9}   {'—':>9}   {'—':>10}  {unit}")

# ── TABLE 4: Post-sim physics signals ────────────────────────────────
print()
print("TABLE 4 — Post-Simulation Physics Signals (MFLS / γ* / Curvature)")
print(f"  {'Domain':<22} {'E_BS lead':>10} {'MFLS lead':>10} {'γ* lead':>9} {'Morse idx':>10} {'Saddle?':>8}")
print("  " + "─" * 72)
static = dm.get('static', {})
for dom in domains:
    res = static.get(dom, {})
    unit = domain_units.get(dom, '?')
    ebs_l  = res.get('E_BS', {}).get('lead', 0)
    ebs_h  = res.get('E_BS', {}).get('hit', False)
    mfls_l = res.get('MFLS', {}).get('lead', 0)
    mfls_h = res.get('MFLS', {}).get('hit', False)
    gam_l  = res.get('gamma_star', {}).get('lead', 0)
    gam_h  = res.get('gamma_star', {}).get('hit', False)

    ebs_s  = str(ebs_l)  + ('*' if ebs_h  else '')
    mfls_s = str(mfls_l) + ('*' if mfls_h else '')
    gam_s  = str(gam_l)  + ('*' if gam_h  else '')

    # Morse info from results if available
    morse_idx = '?'
    saddle    = '?'
    try:
        eng_res = d['results'][dom]
        # not stored, use domain knowledge
    except Exception:
        pass

    print(f"  {dom:<22} {ebs_s:>10} {mfls_s:>10} {gam_s:>9}  [{unit}]")

# ── Notes ─────────────────────────────────────────────────────────────
print()
print("NOTES:")
print("  Lead    = periods of advance warning before onset (* = alarm fired)")
print("  FA/100  = false alarm bursts per 100 pre-onset periods")
print("  Disc×   = mean(post-onset score) / mean(pre-onset score)")
print("  Morse   = number of negative Hessian eigenvalues in X_final_")
print("            (≥1 = saddle = system at phase transition boundary)")
print()
print("  Banking units: quarters (3 months each)")
print("  ERCOT units  : calendar days")
print("  Protein units: MD frames (each = 50 Langevin integration steps)")
print("  EEG units    : seconds (1-second sliding windows)")
print()
print("  FA/100=10 for banking = only 10 pre-onset samples exist, threshold")
print("  is trivially exceeded; use Disc× as the meaningful metric there.")
