import json

with open('v38_ito_tightcb/crypto_godmode_v38_ito_tightcb.json') as f:
    data = json.load(f)
results = data['results']
print(f'Total variants: {len(results)}')

# Top 10 by Calmar
top_calmar = sorted(results, key=lambda r: -r.get('calmar', 0))[:10]
print('\n--- TOP 10 BY CALMAR ---')
for r in top_calmar:
    lbl = r['name'][:62]
    print(f'  {lbl:62s}  {r["calmar"]:6.2f}  ${r["final"]:>12,.0f}  {r["maxdd"]*100:7.1f}%  r2026={r.get("r2026",0):+.3f}  resets={r.get("ito_resets",0)}')

# Top 5 by equity
top_eq = sorted(results, key=lambda r: -r.get('final', 0))[:5]
print('\n--- TOP 5 BY FINAL EQUITY ---')
for r in top_eq:
    lbl = r['name'][:62]
    print(f'  {lbl:62s}  {r["calmar"]:6.2f}  ${r["final"]:>12,.0f}  {r["maxdd"]*100:7.1f}%  r2026={r.get("r2026",0):+.3f}')

# Best with MaxDD > -30%
dd30 = sorted([r for r in results if r.get('maxdd', -99) > -0.30], key=lambda r: -r['calmar'])[:10]
print('\n--- TOP 10 WITH MaxDD > -30% ---')
for r in dd30:
    lbl = r['name'][:62]
    print(f'  {lbl:62s}  {r["calmar"]:6.2f}  ${r["final"]:>12,.0f}  {r["maxdd"]*100:7.1f}%  r2026={r.get("r2026",0):+.3f}  resets={r.get("ito_resets",0)}')

# G7 km10 with any DD improvement
print('\n--- km10 variants (best by calmar) ---')
km10_all = sorted([r for r in results if r.get('kappa_max') == 10], key=lambda r: -r['calmar'])[:10]
for r in km10_all:
    lbl = r['name'][:62]
    print(f'  {lbl:62s}  {r["calmar"]:6.2f}  ${r["final"]:>12,.0f}  {r["maxdd"]*100:7.1f}%  r2026={r.get("r2026",0):+.3f}')

# G7 km5 with any DD improvement
print('\n--- km5 variants (best by calmar) ---')
km5_all = sorted([r for r in results if r.get('kappa_max') == 5], key=lambda r: -r['calmar'])[:10]
for r in km5_all:
    lbl = r['name'][:62]
    print(f'  {lbl:62s}  {r["calmar"]:6.2f}  ${r["final"]:>12,.0f}  {r["maxdd"]*100:7.1f}%  r2026={r.get("r2026",0):+.3f}')

print('\n--- OVERALL BEST MaxDD achieved (best by MaxDD threshold) ---')
best_dd = sorted(results, key=lambda r: r.get('maxdd', -99), reverse=True)[:10]
for r in best_dd:
    lbl = r['name'][:62]
    print(f'  {lbl:62s}  {r["calmar"]:6.2f}  ${r["final"]:>12,.0f}  {r["maxdd"]*100:7.1f}%  r2026={r.get("r2026",0):+.3f}')
