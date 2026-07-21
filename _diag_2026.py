import json,os
base=r'C:\amttp\research\adaptive-friction\pipeline\results'
d=json.load(open(os.path.join(base,'v35_top5_cb_transition','crypto_godmode_v35_top5_cb_transition.json'),encoding='utf-8'))
res=d['results']
best=max(res,key=lambda r:r.get('calmar',0))
print('=== Best variant ===')
print('r2023=',best['r2023'],' r2024=',best['r2024'],' r2025=',best['r2025'],' r2026=',best['r2026'])
print('pct_halted=',best['pct_halted'],' n_trips=',best['n_trips'])
print('cb_halt=',best['cb_halt'],' cb_resume=',best['cb_resume'],' cb_window_days=',best['cb_window_days'])
print()
# Show top-10 sorted by calmar with 2026 data
top10=sorted(res,key=lambda r:r.get('calmar',0),reverse=True)[:10]
print('calmar     final    r2026  halted%  d    q   cb')
for r in top10:
    print(f"  {r['calmar']:.2f}  {r['final']:.0f}  {r['r2026']:.3f}  {r['pct_halted']:.1%}  {r['d']}  {r['q']}  {r['cb_label']}")

print()
# Sort by r2026 to see which configs actually traded
print('=== By r2026 (desc) ===')
by26=sorted(res,key=lambda r:r.get('r2026',0),reverse=True)[:10]
for r in by26:
    print(f"  r2026={r['r2026']:.3f}  calmar={r['calmar']:.2f}  final={r['final']:.0f}  halted={r['pct_halted']:.1%}  d={r['d']} q={r['q']} cb={r['cb_label']}")
