import json
from itertools import groupby

with open('v41_ramp/crypto_godmode_v41_ramp.json') as f:
    data = json.load(f)
results = data['results']
print(f'Total variants: {len(results)}')

# Best by MaxDD (least negative)
best_dd = max(results, key=lambda r: r.get('maxdd', -99))
pos = [r for r in results if r.get('r2026', 0) > 0]
best_cal = max(pos, key=lambda r: r.get('calmar', 0)) if pos else None

# Ramp sweep: d=0.25, q=0.50, km=None, eta>0, om=0.02, ra=0.5
sub = [r for r in results if r.get('d') == 0.25 and r.get('q') == 0.50
       and r.get('kappa_max') is None and r.get('eta', 0) > 0
       and r.get('omega_thresh') == 0.02 and abs(r.get('rho_alpha', 0) - 0.5) < 1e-9]

sub.sort(key=lambda r: (r.get('ramp_init', 1.0), r.get('ramp_bars', 168)))
print('\n  ri     rb    Calmar       Final       MaxDD    r2026')
for k, g in groupby(sub, key=lambda r: (r.get('ramp_init', 1.0), r.get('ramp_bars', 168))):
    best = max(g, key=lambda r: r.get('calmar', 0))
    ri, rb = k
    print(f'  {ri:.2f}  {rb:5d}  {best["calmar"]:7.2f}  ${best["final"]:>11,.0f}  {best["maxdd"]:7.1%}  {best.get("r2026",0):+.3f}')

print(f'\nBest MaxDD overall: {best_dd["name"]}')
print(f'  MaxDD={best_dd["maxdd"]:.1%}  Calmar={best_dd["calmar"]:.2f}  Final=${best_dd["final"]:,.0f}  ramp_init={best_dd.get("ramp_init",1.0)}  ramp_bars={best_dd.get("ramp_bars",168)}')

if best_cal:
    print(f'\nBest Calmar (r2026>0): {best_cal["name"]}')
    print(f'  Calmar={best_cal["calmar"]:.2f}  MaxDD={best_cal["maxdd"]:.1%}  Final=${best_cal["final"]:,.0f}')

# Show best MaxDD per ramp_init
print('\n--- Best MaxDD per ramp_init ---')
for ri in [1.0, 0.5, 0.3]:
    sub2 = [r for r in results if abs(r.get('ramp_init', 1.0) - ri) < 1e-9]
    if sub2:
        b = max(sub2, key=lambda r: r.get('maxdd', -99))
        print(f'  ri={ri:.1f}: MaxDD={b["maxdd"]:.1%}  Calmar={b["calmar"]:.2f}  Final=${b["final"]:,.0f}  {b["name"][:80]}')
