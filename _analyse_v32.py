import json
data = json.load(open(r'C:\amttp\research\adaptive-friction\pipeline\results\v32_true_fractional\crypto_godmode_v32_true_fractional.json'))
r = sorted(data['results'], key=lambda x: x['final'], reverse=True)
hdr = f"{'Name':<25} {'d':>4} {'s':>4} {'q':>4} {'Final_k':>8} {'Calmar':>7} {'MaxDD%':>7} {'Sharpe':>6} {'Halt%':>6} {'r2023':>6} {'r2024':>6} {'r2025':>6} {'r2026':>6} {'cond_b':>14} {'cond_f':>14}"
print(hdr)
print('-'*120)
for v in r:
    sig = v['sigma']
    print(f"{v['name']:<25} {v['d']:>4.1f} {v['s_frac']:>4.1f} {v['q']:>4.2f} "
          f"{v['final']/1000:>8.1f} {v['calmar']:>7.2f} {v['maxdd']*100:>7.2f} {v['sharpe']:>6.3f} "
          f"{v['pct_halted']*100:>6.1f} {v['r2023']:>6.4f} {v['r2024']:>6.4f} {v['r2025']:>6.4f} {v['r2026']:>6.4f} "
          f"{sig['cond_before']:>14.3e} {sig['cond_final']:>14.3e}")

print()
print("=== BEST BY CALMAR ===")
rb = sorted(data['results'], key=lambda x: x['calmar'], reverse=True)
for v in rb[:5]:
    print(f"  {v['name']}: Calmar={v['calmar']:.3f}  Final=${v['final']:,.0f}  MaxDD={v['maxdd']*100:.2f}%")

print()
print("=== VS v29 BASELINE ===")
print("  v29 baseline: Final=$164,721  Calmar=19.459  MaxDD=-18.32%  Sharpe=~1.82")
print(f"  v32 best final: ${r[0]['final']:,.0f} ({r[0]['name']})  Calmar={r[0]['calmar']:.3f}  MaxDD={r[0]['maxdd']*100:.2f}%")
print(f"  v32 best calmar: {rb[0]['calmar']:.3f} ({rb[0]['name']})  Final=${rb[0]['final']:,.0f}  MaxDD={rb[0]['maxdd']*100:.2f}%")

print()
print("=== DIAGNOSTICS ===")
v0 = data['results'][0]
print(f"  pct_halted ALL variants: {v0['pct_halted']*100:.1f}%  (SAME for all — circuit breaker structural issue)")
print(f"  r2026 ALL variants: {v0['r2026']}  (NO trades in 2026)")
print(f"  cond_before typical: {v0['sigma']['cond_before']:.3e}  (still ~3e12 — GL differencing does NOT fix raw conditioning)")
print(f"  cond_after regularisation: {v0['sigma']['cond_after']:.3e}  (clamped to 20)")
print()
print("=== PATTERN: s_frac EFFECT ===")
for d in [0.3, 0.5, 0.7]:
    print(f"  d={d}:")
    for s in [0.0, 0.3, 0.6]:
        variants = [v for v in data['results'] if v['d']==d and v['s_frac']==s]
        avg_f = sum(v['final'] for v in variants)/len(variants)
        avg_c = sum(v['calmar'] for v in variants)/len(variants)
        print(f"    s_frac={s}: avg_final=${avg_f:,.0f}  avg_calmar={avg_c:.3f}")
