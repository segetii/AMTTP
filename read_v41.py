import json
from itertools import groupby

with open(r"c:\amttp\research\adaptive-friction\pipeline\results\v41_ramp\crypto_godmode_v41_ramp.json", encoding="utf-8") as f:
    data = json.load(f)
results = data["results"]
print(f"Total variants: {len(results)}")

best_dd  = max(results, key=lambda r: r.get("maxdd", -99))
best_cal = max(results, key=lambda r: r.get("calmar", 0))

print(f"\nBest MaxDD:  {best_dd['name']}")
print(f"  Calmar={best_dd['calmar']:.2f}  Final=${best_dd['final']:,.0f}  MaxDD={best_dd['maxdd']:.1%}  r2026={best_dd.get('r2026',0):+.4f}  ri={best_dd.get('ramp_init',1.0)}  rb={best_dd.get('ramp_bars',168)}")

print(f"\nBest Calmar: {best_cal['name']}")
print(f"  Calmar={best_cal['calmar']:.2f}  Final=${best_cal['final']:,.0f}  MaxDD={best_cal['maxdd']:.1%}  r2026={best_cal.get('r2026',0):+.4f}  ri={best_cal.get('ramp_init',1.0)}  rb={best_cal.get('ramp_bars',168)}")

# dd threshold scan
dd25 = [r for r in results if r.get("maxdd", -99) > -0.25]
if dd25:
    b = max(dd25, key=lambda r: r.get("final", 0))
    print(f"\nBest Final with |MaxDD|<25%: {b['name']}")
    print(f"  Calmar={b['calmar']:.2f}  Final=${b['final']:,.0f}  MaxDD={b['maxdd']:.1%}  r2026={b.get('r2026',0):+.4f}  ri={b.get('ramp_init',1.0)}  rb={b.get('ramp_bars',168)}")
else:
    print("\nNo variant with MaxDD better than -25%")

print()
print("Ramp sweep (d=0.25,q=0.5,km=none,eta>0,om=0.02,ra=0.5) best Calmar per (ri,rb):")
sub = [r for r in results if r["d"]==0.25 and r["q"]==0.50
       and r.get("kappa_max") is None and r["eta"]>0
       and r.get("omega_thresh")==0.02
       and abs(r.get("rho_alpha",0)-0.5)<1e-9]
sub.sort(key=lambda r: (r.get("ramp_init",1.0), r.get("ramp_bars",168)))
for key, grp in groupby(sub, key=lambda r: (r.get("ramp_init",1.0), r.get("ramp_bars",168))):
    g = list(grp)
    b = max(g, key=lambda r: r.get("calmar",0))
    print(f"  ri={key[0]:.2f} rb={key[1]:4d}:  Calmar={b['calmar']:.2f}  MaxDD={b['maxdd']:.1%}  Final=${b['final']:,.0f}  r2026={b.get('r2026',0):+.3f}")

print()
print("All (ri,rb) best-MaxDD per combo (sorted by MaxDD desc):")
sub2 = [r for r in results if r["d"]==0.25 and r["q"]==0.50
        and r.get("kappa_max") is None and r["eta"]>0]
sub2.sort(key=lambda r: (r.get("ramp_init",1.0), r.get("ramp_bars",168)))
seen = {}
for r in sub2:
    k = (r.get("ramp_init",1.0), r.get("ramp_bars",168))
    if k not in seen or r.get("maxdd",-99) > seen[k].get("maxdd",-99):
        seen[k] = r
ranked = sorted(seen.values(), key=lambda r: r.get("maxdd",-99), reverse=True)
for r in ranked:
    print(f"  ri={r.get('ramp_init',1.0):.2f} rb={r.get('ramp_bars',168):4d}:  MaxDD={r['maxdd']:.1%}  Calmar={r['calmar']:.2f}  Final=${r['final']:,.0f}  r2026={r.get('r2026',0):+.3f}")
