import json
from pathlib import Path
ms = json.loads(Path("simulation_master_strategy.json").read_text())
print("Keys:", list(ms.keys()))
best = ms["best"]
print("Best config:", best.get("config","?"))
oos = best.get("oos", best.get("TEST", {}))
for k in ("calmar","return_pct","cagr","sharpe","maxdd","final"):
    print(f"  OOS {k}: {oos.get(k,'n/a')}")
print()
print("Yearly:")
for r in best.get("yearly_oos", best.get("yearly", [])):
    print(f"  {r['period']}  ret={r.get('return_pct',0):+.1%}  sharpe={r.get('sharpe',0):+.3f}  maxdd={r.get('maxdd',0):+.2%}  end={r.get('end_eq',0):,.2f}")
print()
print("Top drawdowns:")
for r in best.get("drawdowns", [])[:6]:
    print(f"  {str(r['dd_start'])[:10]} -> {str(r['trough'])[:10]} -> {str(r.get('dd_end','ongoing'))[:10]}  DD={r['drawdown']:+.2%}  days={r['duration_days']}  peak={r['peak_eq']:,.0f}  trough={r['trough_eq']:,.0f}")
print()
print("Grid:")
for row in ms.get("grid", []):
    oos2 = row.get("oos", {})
    cnt  = row.get("counts", {})
    print(f"  trail={row.get('trail_trigger',0):.2f}/{row.get('trail_dist',0):.2f}  K_crash={row.get('K_crash',0)}  "
          f"Calmar={oos2.get('calmar',0):+.3f}  Ret={oos2.get('return_pct',0):+.1%}  "
          f"MaxDD={oos2.get('maxdd',0):+.2%}  Sharpe={oos2.get('sharpe',0):+.3f}  "
          f"entries={cnt.get('entries',0):,}  trail_exits={cnt.get('trail_exit',0)}")
