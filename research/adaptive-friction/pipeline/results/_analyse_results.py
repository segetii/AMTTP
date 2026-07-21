"""Quick analysis script — dump full yearly + drawdown tables from the two JSON files."""
import json
from pathlib import Path

ms = json.loads(Path("simulation_master_strategy.json").read_text())
vq = json.loads(Path("simulation_v63_quadrant.json").read_text())

SEP  = "=" * 110
SSEP = "-" * 110

print("\nMASTER STRATEGY JSON top-level keys:")
print(list(ms.keys())[:20])
print("\nQUADRANT JSON top-level keys:")
print(list(vq.keys())[:20])

# ── master strategy details ────────────────────────────────────────────────────
def show_config(label, d):
    oos  = d.get("oos",   d.get("TEST", {}))
    full = d.get("full",  d.get("FULL", {}))
    train= d.get("train", d.get("TRAIN", {}))
    yr   = d.get("yearly", d.get("yearly_oos", []))
    dds  = d.get("drawdowns", [])
    cnt  = d.get("counts", {})

    print(f"\n{SEP}")
    print(f"  {label}")
    print(SEP)
    print(f"  {'Metric':<32} {'FULL':>14} {'TRAIN':>14} {'OOS':>14}")
    print(SSEP)
    for k in ("calmar","return_pct","cagr","sharpe","maxdd","final"):
        fv = full.get(k,  float("nan"))
        tv = train.get(k, float("nan"))
        ov = oos.get(k,   float("nan"))
        if k in ("return_pct","cagr","sharpe","maxdd","calmar"):
            print(f"  {k:<32} {fv:>+14.3f} {tv:>+14.3f} {ov:>+14.3f}")
        else:
            print(f"  {k:<32} {fv:>14,.2f} {tv:>14,.2f} {ov:>14,.2f}")

    if cnt:
        print(f"\n  Counts: entries={cnt.get('entries',0):,}  "
              f"stop={cnt.get('stop',0)}  tp={cnt.get('tp',0)}  "
              f"trail={cnt.get('trail_exit',0)}  signal={cnt.get('signal_exit',0)}  "
              f"killed={cnt.get('killed',0)}  gh_th={cnt.get('gh_th',0)}")
        cb_h = d.get("cb_halted_pct", cnt.get("pct_halted", float("nan")))
        ntrips = d.get("n_cb_trips", cnt.get("n_trips", "?"))
        print(f"  CB: {cb_h:.1%} halted  {ntrips} trips")

    if yr:
        print(f"\n  Yearly breakdown:")
        print(f"  {'Period':<14} {'Start$':>12} {'End$':>12} {'P&L':>12} {'Ret':>9} {'Sharpe':>8} {'MaxDD':>9}")
        print("  " + "-"*80)
        for r in yr:
            print(f"  {r['period']:<14} {r.get('start_eq',r.get('start',0)):>12,.2f} "
                  f"{r.get('end_eq',r.get('end',0)):>12,.2f} "
                  f"{r.get('profit',0):>+12,.2f} "
                  f"{r.get('return_pct',0):>+8.1%} "
                  f"{r.get('sharpe',0):>+8.3f} "
                  f"{r.get('maxdd',0):>+8.2%}")

    if dds:
        print(f"\n  Top drawdowns:")
        print(f"  {'Start':<14} {'Trough':<14} {'End':<14} {'DD':>9} {'Days':>6} {'Peak$':>12} {'Trough$':>12}")
        print("  " + "-"*80)
        for r in dds[:8]:
            end = str(r.get("dd_end","ongoing"))[:10]
            print(f"  {str(r['dd_start'])[:10]:<14} {str(r['trough'])[:10]:<14} {end:<14} "
                  f"{r['drawdown']:>+8.2%} {r['duration_days']:>6,} "
                  f"{r['peak_eq']:>12,.2f} {r['trough_eq']:>12,.2f}")

# ── show each config ───────────────────────────────────────────────────────────
show_config("MASTER (daily filter, no trail, no crash)  — NEW 4-CH BIFURCATED", ms)

for k in ("layered_daily_no_crash", "layered_daily_with_crash",
          "strict_kill_no_crash",   "strict_kill_with_crash",
          "no_gate_daily_no_crash", "no_gate_daily_with_crash"):
    if k in vq:
        show_config(f"QUADRANT: {k}", vq[k])

# ── champion comparison table ──────────────────────────────────────────────────
print(f"\n{SEP}")
print("  CHAMPION COMPARISON TABLE")
print(f"{SEP}")
print(f"  {'Config':<50} {'Calmar':>8} {'OOS Ret':>10} {'CAGR':>8} {'Sharpe':>8} {'MaxDD':>9} {'Final$':>12}")
print(SSEP)

rows = [
    ("Old 3-ch champion (trail 1.5σ K=1)",         2.818,  8.246,  None,  None,  -0.338,  None),
]
def add(label, d):
    oos = d.get("oos", {})
    rows.append((label, oos.get("calmar"), oos.get("return_pct"),
                 oos.get("cagr"), oos.get("sharpe"), oos.get("maxdd"), oos.get("final")))

add("New bifurcated: daily, no trail, no crash",  ms)
for k in ("layered_daily_no_crash", "layered_daily_with_crash",
          "strict_kill_no_crash", "no_gate_daily_with_crash"):
    if k in vq:
        add(f"  Quadrant/{k}", vq[k])

for label, cal, ret, cagr, sh, dd, fin in rows:
    cal_s  = f"{cal:>+8.3f}" if cal  is not None else f"{'n/a':>8}"
    ret_s  = f"{ret:>+9.1%}"  if ret  is not None else f"{'n/a':>9}"
    cagr_s = f"{cagr:>+7.1%}" if cagr is not None else f"{'n/a':>7}"
    sh_s   = f"{sh:>+8.3f}"  if sh   is not None else f"{'n/a':>8}"
    dd_s   = f"{dd:>+8.2%}"  if dd   is not None else f"{'n/a':>8}"
    fin_s  = f"{fin:>12,.2f}" if fin  is not None else f"{'n/a':>12}"
    print(f"  {label:<50} {cal_s} {ret_s} {cagr_s} {sh_s} {dd_s} {fin_s}")
